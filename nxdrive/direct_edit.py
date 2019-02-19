# coding: utf-8
import os
import shutil
from datetime import datetime
from logging import getLogger
from pathlib import Path
from queue import Empty, Queue
from time import sleep
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from urllib.parse import quote

from nuxeo.utils import get_digest_algorithm
from PyQt5.QtCore import pyqtSignal, pyqtSlot
from watchdog.events import FileSystemEvent
from watchdog.observers import Observer

from .client.local_client import LocalClient
from .constants import DOWNLOAD_TMP_FILE_PREFIX, DOWNLOAD_TMP_FILE_SUFFIX, ROOT, WINDOWS
from .engine.activity import tooltip
from .engine.blacklist_queue import BlacklistQueue
from .engine.watcher.local_watcher import DriveFSEventHandler
from .engine.workers import Worker
from .exceptions import Forbidden, NotFound, ThreadInterrupt, UnknownDigest
from .objects import Metrics, NuxeoDocumentInfo
from .utils import (
    current_milli_time,
    force_decode,
    normalize_event_filename,
    parse_protocol_url,
    safe_os_filename,
    simplify_url,
    unset_path_readonly,
)

if TYPE_CHECKING:
    from .engine.engine import Engine  # noqa
    from .manager import Manager  # noqa

__all__ = ("DirectEdit",)

log = getLogger(__name__)


def _is_lock_file(name: str) -> bool:
    """
    Check if a given file name is a temporary one created by
    third-party software.
    """

    return name.startswith(("~$", ".~lock."))  # Microsoft Office  # (Libre|Open)Office


class DirectEdit(Worker):
    localScanFinished = pyqtSignal()
    directEditUploadCompleted = pyqtSignal(str)
    openDocument = pyqtSignal(object)
    editDocument = pyqtSignal(object)
    directEditLockError = pyqtSignal(str, str, str)
    directEditConflict = pyqtSignal(str, Path, str)
    directEditError = pyqtSignal(str, list)
    directEditForbidden = pyqtSignal(str, str, str)
    directEditReadonly = pyqtSignal(str)
    directEditStarting = pyqtSignal(str, str)
    directEditLocked = pyqtSignal(str, str, datetime)

    def __init__(self, manager: "Manager", folder: Path, url: str) -> None:
        super().__init__()

        self._manager = manager
        self._folder = folder
        self.url = url
        self.lock = Lock()

        self.autolock = self._manager.autolock_service
        self.use_autolock = self._manager.get_direct_edit_auto_lock()
        self._event_handler: Optional[DriveFSEventHandler] = None
        self._metrics = {"edit_files": 0}
        self._observer: Observer = None
        self.local = LocalClient(self._folder)
        self._upload_queue: Queue = Queue()
        self._lock_queue: Queue = Queue()
        self._error_queue = BlacklistQueue()
        self._stop = False
        self._last_action_timing = -1
        self.watchdog_queue: Queue = Queue()

        self._thread.started.connect(self.run)
        self.autolock.orphanLocks.connect(self._autolock_orphans)

    @pyqtSlot(object)
    def _autolock_orphans(self, locks: List[Path]) -> None:
        log.trace(f"Orphans lock: {locks!r}")
        for lock in locks:
            if self._folder in lock.parents:
                log.debug(f"Should unlock {lock!r}")
                if not lock.exists():
                    self.autolock.orphan_unlocked(lock)
                    continue

                ref = self.local.get_path(lock)
                self._lock_queue.put((ref, "unlock_orphan"))

    def autolock_lock(self, src_path: Path) -> None:
        ref = self.local.get_path(src_path)
        self._lock_queue.put((ref, "lock"))

    def autolock_unlock(self, src_path: Path) -> None:
        ref = self.local.get_path(src_path)
        self._lock_queue.put((ref, "unlock"))

    def start(self) -> None:
        self._stop = False
        super().start()

    def stop(self) -> None:
        super().stop()
        self._stop = True

    def stop_client(self, message: str = None) -> None:
        if self._stop:
            raise ThreadInterrupt()

    def handle_url(self, url: str = None) -> None:
        url = url or self.url
        if not url:
            return

        log.debug(f"DirectEdit load: {url!r}")

        info = parse_protocol_url(url)

        if not info:
            return

        self.edit(
            info["server_url"],
            info["doc_id"],
            user=info["user"],
            download_url=info["download_url"],
        )

    @tooltip("Clean up folder")
    def _cleanup(self) -> None:
        """
        - Unlock any remaining doc that has not been unlocked
        - Upload forgotten changes
        - Remove obsolete folders
        """

        if not self.local.exists(ROOT):
            self._folder.mkdir()
            return

        def purge(path):
            shutil.rmtree(self.local.abspath(path), ignore_errors=True)

        log.debug("Cleanup DirectEdit folder")

        for child in self.local.get_children_info(ROOT):
            children = self.local.get_children_info(child.path)
            if not children:
                purge(child.path)
                continue

            ref = children[0].path
            try:
                _, _, func, digest, _ = self._extract_edit_info(ref)
            except NotFound:
                # Engine is not known anymore
                purge(child.path)
                continue

            try:
                # Don't update if digest are the same
                info = self.local.get_info(ref)
                current_digest = info.get_digest(digest_func=func)
                if current_digest != digest:
                    log.warning(
                        "Document has been modified and "
                        "not synchronized, add to upload queue"
                    )
                    self._upload_queue.put(ref)
                    continue
            except:
                log.exception("Unhandled clean-up error")
                continue

            # Place for handle reopened of interrupted Edit
            purge(child.path)

    def __get_engine(self, url: str, user: str = None) -> Optional["Engine"]:
        if not url:
            return None

        url = simplify_url(url)
        for engine in self._manager.get_engines().values():
            bind = engine.get_binder()
            server_url = bind.server_url.rstrip("/")
            if server_url == url and (not user or user == bind.username):
                return engine

        # Some backend are case insensitive
        if not user:
            return None

        user = user.lower()
        for engine in self._manager.get_engines().values():
            bind = engine.get_binder()
            server_url = simplify_url(bind.server_url)
            if server_url == url and user == bind.username.lower():
                return engine

        return None

    def _get_engine(
        self, server_url: str, doc_id: str = None, user: str = None
    ) -> Optional["Engine"]:
        engine = self.__get_engine(server_url, user=user)

        if not engine:
            values = [force_decode(user) if user else "Unknown", server_url]
            log.warning(
                f"No engine found for user {user!r} on server {server_url!r}, "
                f"doc_id={doc_id!r}"
            )
            self.directEditError.emit("DIRECT_EDIT_CANT_FIND_ENGINE", values)
        elif engine.has_invalid_credentials():
            values = [engine.remote_user, engine.server_url]
            log.warning(
                f"Invalid credentials for user {engine.remote_user!r} "
                f"on server {engine.server_url!r}"
            )
            self.directEditError.emit("DIRECT_EDIT_INVALID_CREDS", values)
            engine = None

        return engine

    def _download(
        self,
        engine: "Engine",
        info: NuxeoDocumentInfo,
        file_path: Path,
        xpath: str,
        url: str = None,
    ) -> Path:
        filename = DOWNLOAD_TMP_FILE_PREFIX + file_path.name + DOWNLOAD_TMP_FILE_SUFFIX
        file_out = file_path.parent / filename

        # Close to processor method - should try to refactor ?
        pair = None
        blob = info.blobs[xpath]
        kwargs: Dict[str, Any] = {}

        if blob.digest:
            # The digest is available in the Blob, use it and disable parameters check
            # as 'digest' is not a recognized param for the Blob.Get operation.
            kwargs["digest"] = blob.digest
            kwargs["check_params"] = False

            pair = engine.get_dao().get_valid_duplicate_file(blob.digest)
        if pair:
            existing_file_path = engine.local.abspath(pair.local_path)
            log.debug(
                f"Local file matches remote digest {blob.digest!r}, "
                f"copying it from {existing_file_path!r}"
            )
            shutil.copy(existing_file_path, file_out)
            if pair.is_readonly():
                log.debug(f"Unsetting readonly flag on copied file {file_out!r}")
                unset_path_readonly(file_out)
        else:
            log.debug(f"Downloading file {blob.name!r}")
            if url:
                engine.remote.download(
                    quote(url, safe="/:"),
                    file_out=file_out,
                    digest=blob.digest,
                    check_suspended=self.stop_client,
                )
            else:
                engine.remote.get_blob(
                    info,
                    xpath=xpath,
                    file_out=file_out,
                    check_suspended=self.stop_client,
                    **kwargs,
                )
        return file_out

    def _get_info(self, engine: "Engine", doc_id: str) -> Optional[NuxeoDocumentInfo]:
        try:
            doc = engine.remote.fetch(
                doc_id, headers={"fetch-document": "lock"}, enrichers=["permissions"]
            )
        except Forbidden:
            msg = (
                f" Access to the document {doc_id!r} on server {engine.hostname!r}"
                f" is forbidden for user {engine.remote_user!r}"
            )
            log.warning(msg)
            self.directEditForbidden.emit(doc_id, engine.hostname, engine.remote_user)
            return None

        doc.update(
            {
                "root": engine.remote._base_folder_ref,
                "repository": engine.remote.client.repository,
            }
        )
        info = NuxeoDocumentInfo.from_dict(doc)

        if info.lock_owner and info.lock_owner != engine.remote_user:
            # Retrieve the user full name, will be cached
            owner = engine.get_user_full_name(info.lock_owner)

            log.debug(
                f"Doc {info.name!r} was locked by {owner} ({info.lock_owner}) "
                f"on {info.lock_created}, edit not allowed"
            )
            self.directEditLocked.emit(info.name, owner, info.lock_created)
            return None
        elif info.permissions and "Write" not in info.permissions:
            log.debug(f"Doc {info.name!r} is readonly for you, edit not allowed")
            self.directEditReadonly.emit(info.name)
            return None

        return info

    def _prepare_edit(
        self, server_url: str, doc_id: str, user: str = None, download_url: str = None
    ) -> Optional[Path]:
        start_time = current_milli_time()
        engine = self._get_engine(server_url, doc_id=doc_id, user=user)
        if not engine:
            return None

        # Avoid any link with the engine, remote_doc are not cached so we
        # can do that
        info = self._get_info(engine, doc_id)
        if not info:
            return None

        url = None
        url_info: Dict[str, str] = {}
        if download_url:
            import re

            urlmatch = re.match(
                r"([^\/]+\/){3}(?P<xpath>.+)\/(?P<filename>[^\?]*).*",
                download_url,
                re.I,
            )
            if urlmatch:
                url_info = urlmatch.groupdict()

            url = server_url
            if not url.endswith("/"):
                url += "/"
            url += download_url

        xpath = url_info.get("xpath", "file:content")
        if xpath == "blobholder:0":
            xpath = "file:content"
        if xpath not in info.blobs and info.doc_type == "Note":
            xpath = "note:note"

        blob = info.blobs.get(xpath)
        if not blob:
            return None

        filename = blob.name
        self.directEditStarting.emit(engine.hostname, filename)

        # Create local structure
        folder_name = safe_os_filename(f"{doc_id}_{xpath}")
        dir_path = self._folder / folder_name
        dir_path.mkdir(exist_ok=True)

        log.debug(f"Editing {filename!r}")
        file_path = dir_path / filename

        # Download the file
        tmp_file = self._download(engine, info, file_path, xpath, url=url)
        if tmp_file is None:
            log.error("Download failed")
            return None

        # Set the remote_id
        dir_path = self.local.get_path(dir_path)
        self.local.set_remote_id(dir_path, doc_id)
        self.local.set_remote_id(dir_path, server_url, name="nxdirectedit")

        if user:
            self.local.set_remote_id(dir_path, user, name="nxdirectedituser")

        if xpath:
            self.local.set_remote_id(dir_path, xpath, name="nxdirecteditxpath")

        if blob.digest:
            self.local.set_remote_id(dir_path, blob.digest, name="nxdirecteditdigest")
            # Set digest algorithm if not sent by the server
            digest_algorithm = blob.digest_algorithm
            if not digest_algorithm:
                digest_algorithm = get_digest_algorithm(blob.digest)
                if not digest_algorithm:
                    raise UnknownDigest(blob.digest)
            self.local.set_remote_id(
                dir_path,
                digest_algorithm.encode("utf-8"),
                name="nxdirecteditdigestalgorithm",
            )
        self.local.set_remote_id(dir_path, filename, name="nxdirecteditname")

        # Rename to final filename
        # Under Windows first need to delete target file if exists,
        # otherwise will get a 183 WindowsError
        if WINDOWS and file_path.exists():
            file_path.unlink()
        tmp_file.rename(file_path)

        self._last_action_timing = current_milli_time() - start_time
        self.openDocument.emit(blob)
        return file_path

    def edit(
        self, server_url: str, doc_id: str, user: str = None, download_url: str = None
    ) -> None:
        log.debug(f"Editing doc {doc_id!r} on {server_url!r}")
        try:
            # Download the file
            file_path = self._prepare_edit(
                server_url, doc_id, user=user, download_url=download_url
            )

            # Launch it
            if file_path:
                self._manager.open_local_file(file_path)
        except OSError as e:
            if e.errno == 13:
                # Open file anyway
                if e.filename is not None:
                    self._manager.open_local_file(e.filename)
            else:
                raise e

    def _extract_edit_info(self, ref: Path) -> Tuple[str, "Engine", str, str, str]:
        dir_path = ref.parent
        server_url = self.local.get_remote_id(dir_path, name="nxdirectedit")
        if not server_url:
            raise NotFound()

        user = self.local.get_remote_id(dir_path, name="nxdirectedituser")
        engine = self._get_engine(server_url, user=user)
        if not engine:
            raise NotFound()

        uid = self.local.get_remote_id(dir_path)
        if not uid:
            raise NotFound()

        digest_algorithm = self.local.get_remote_id(
            dir_path, name="nxdirecteditdigestalgorithm"
        )
        digest = self.local.get_remote_id(dir_path, name="nxdirecteditdigest")
        if not digest or not digest_algorithm:
            raise NotFound()

        xpath = self.local.get_remote_id(dir_path, name="nxdirecteditxpath")
        return uid, engine, digest_algorithm, digest, xpath

    def force_update(self, ref: Path, digest: str) -> None:
        dir_path = ref.parent
        self.local.set_remote_id(
            dir_path, digest.encode("utf-8"), name="nxdirecteditdigest"
        )
        self._upload_queue.put(ref)

    def _handle_lock_queue(self) -> None:
        while "items":
            try:
                item = self._lock_queue.get_nowait()
            except Empty:
                break

            ref, action = item
            log.trace(f"Handling DirectEdit lock queue: action={action}, ref={ref!r}")
            uid = ""
            dir_path = os.path.dirname(ref)

            try:
                uid, engine, _, _, _ = self._extract_edit_info(ref)
                if action == "lock":
                    engine.remote.lock(uid)
                    self.local.set_remote_id(dir_path, b"1", name="nxdirecteditlock")
                    # Emit the lock signal only when the lock is really set
                    self._send_lock_status(ref)
                    self.autolock.documentLocked.emit(os.path.basename(ref))
                    continue

                try:
                    engine.remote.unlock(uid)
                except NotFound:
                    purge = True
                else:
                    purge = False

                if purge or action == "unlock_orphan":
                    path = self.local.abspath(ref)
                    log.trace(f"Remove orphan: {path!r}")
                    self.autolock.orphan_unlocked(path)
                    shutil.rmtree(path, ignore_errors=True)
                    continue

                self.local.remove_remote_id(dir_path, name="nxdirecteditlock")
                # Emit the signal only when the unlock is done
                self._send_lock_status(ref)
                self.autolock.documentUnlocked.emit(os.path.basename(ref))
            except ThreadInterrupt:
                raise
            except:
                # Try again in 30s
                log.exception(f"Cannot {action} document {ref!r}")
                self.directEditLockError.emit(action, os.path.basename(ref), uid)

    def _send_lock_status(self, ref: str) -> None:
        manager = self._manager
        for engine in manager._engines.values():
            dao = engine._dao
            state = dao.get_normal_state_from_remote(ref)
            if state:
                path = engine.local_folder / state.local_path
                manager.osi.send_sync_status(state, path)

    def _handle_upload_queue(self) -> None:
        while not self._upload_queue.empty():
            try:
                ref = self._upload_queue.get_nowait()
            except Empty:
                break

            log.trace(f"Handling DirectEdit queue ref: {ref!r}")

            uid, engine, algorithm, digest, xpath = self._extract_edit_info(ref)
            if not xpath:
                log.debug(
                    f"DirectEdit on {ref} has no xpath, defaulting to 'file:content'"
                )
                xpath = "file:content"
            # Don't update if digest are the same
            try:
                info = self.local.get_info(ref)
                current_digest = info.get_digest(digest_func=algorithm)
                if not current_digest or current_digest == digest:
                    continue

                start_time = current_milli_time()
                log.trace(
                    f"Local digest: {current_digest} is different from the recorded "
                    f"one: {digest} - modification detected for {ref!r}"
                )

                # TO_REVIEW Should check if server-side blob has changed ?
                # Update the document, should verify
                # the remote hash NXDRIVE-187
                remote_info = engine.remote.get_info(uid)
                remote_blob = remote_info.blobs.get(xpath) if remote_info else None
                if remote_blob and remote_blob.digest != digest:
                    # Conflict detect
                    log.trace(
                        f"Remote digest: {remote_blob.digest} is different from the "
                        f"recorded  one: {digest} - conflict detected for {ref!r}"
                    )
                    self.directEditConflict.emit(ref.name, ref, remote_blob.digest)
                    continue

                os_path = self.local.abspath(ref)
                log.debug(f"Uploading file {os_path!r}")

                if xpath == "note:note":
                    kwargs: Dict[str, Any] = {"applyVersioningPolicy": True}
                    cmd = "NuxeoDrive.AttachBlob"
                else:
                    kwargs = {"xpath": xpath}
                    cmd = "Blob.AttachOnDocument"

                engine.remote.upload(
                    os_path,
                    command=cmd,
                    document=engine.remote._check_ref(uid),
                    **kwargs,
                )

                # Update hash value
                dir_path = ref.parent
                self.local.set_remote_id(
                    dir_path, current_digest, name="nxdirecteditdigest"
                )
                self._last_action_timing = current_milli_time() - start_time
                self.directEditUploadCompleted.emit(os_path.name)
                self.editDocument.emit(remote_blob)
            except NotFound:
                # Not found on the server, just skip it
                continue
            except Forbidden:
                msg = (
                    "Upload queue error:"
                    f" Access to the document {ref!r} on server {engine.hostname!r}"
                    f" is forbidden for user {engine.remote_user!r}"
                )
                log.warning(msg)
                self.directEditForbidden.emit(
                    str(ref), engine.hostname, engine.remote_user
                )
                continue
            except ThreadInterrupt:
                raise
            except:
                # Try again in 30s
                log.exception(f"DirectEdit unhandled error for ref {ref!r}")
                self._error_queue.push(ref, ref)

    def _handle_queues(self) -> None:
        # Lock any document
        self._handle_lock_queue()

        # Unqueue any errors
        for item in self._error_queue.get():
            self._upload_queue.put(item.get())

        # Handle the upload queue
        self._handle_upload_queue()

        while not self.watchdog_queue.empty():
            evt = self.watchdog_queue.get()
            try:
                self.handle_watchdog_event(evt)
            except ThreadInterrupt:
                raise
            except:
                log.exception("Watchdog error")

    def _execute(self) -> None:
        try:
            self._cleanup()
            self._setup_watchdog()

            # Load the target URL if Drive was not launched before
            self.handle_url()

            while True:
                self._interact()
                try:
                    self._handle_queues()
                except NotFound:
                    pass
                except ThreadInterrupt:
                    raise
                except:
                    log.exception("Unhandled DirectEdit error")
                sleep(0.5)
        except ThreadInterrupt:
            raise
        finally:
            with self.lock:
                self._stop_watchdog()

    def get_metrics(self) -> Metrics:
        metrics = super().get_metrics()
        if self._event_handler:
            metrics["fs_events"] = self._event_handler.counter
        metrics["last_action_timing"] = self._last_action_timing
        return {**metrics, **self._metrics}

    @tooltip("Setup watchdog")
    def _setup_watchdog(self) -> None:
        log.debug(f"Watching FS modification on {self._folder!r}")
        self._event_handler = DriveFSEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(self._event_handler, str(self._folder), recursive=True)
        self._observer.start()

    def _stop_watchdog(self) -> None:
        if not self._observer:
            return

        if self._observer.is_alive():
            log.info("Stopping FS observer thread")
            try:
                self._observer.stop()
            except:
                log.exception("Cannot stop the FS observer")

        if self._observer and self._observer._started.is_set():
            log.info("Wait for the FS oobserver to stop")
            try:
                self._observer.join()
            except:
                log.exception("Cannot join the FS observer")

        # Delete the observer
        self._observer = None

    @tooltip("Handle watchdog event")
    def handle_watchdog_event(self, evt: FileSystemEvent) -> None:
        src_path = normalize_event_filename(evt.src_path)

        # Event on the folder by itself
        if src_path.is_dir():
            return

        if self.local.is_temp_file(src_path.name):
            return

        log.debug(f"Handling watchdog event [{evt.event_type}] on {evt.src_path!r}")

        if evt.event_type == "moved":
            src_path = normalize_event_filename(evt.dest_path)

        ref = self.local.get_path(src_path)
        dir_path = self.local.get_path(src_path.parent)
        name = self.local.get_remote_id(dir_path, name="nxdirecteditname")

        if not name:
            return

        editing = self.local.get_remote_id(dir_path, name="nxdirecteditlock")

        if force_decode(name) != src_path.name:
            if _is_lock_file(src_path.name):
                if evt.event_type == "created" and self.use_autolock and editing != "1":
                    """
                    [Windows 10] The original file is not modified until
                    we specifically click on the save button. Instead, it
                    applies changes to the temporary file.
                    So the auto-lock does not happen because there is no
                    'modified' event on the original file.
                    Here we try to address that by checking the lock state
                    and use the lock if not already done.
                    """
                    # Recompute the path from 'dir/temp_file' -> 'dir/file'
                    path = src_path.parent / name
                    self.autolock.set_autolock(path, self)
                elif evt.event_type == "deleted":
                    # Free the xattr to let _cleanup() does its work
                    self.local.remove_remote_id(dir_path, name="nxdirecteditlock")
            return

        if self.use_autolock and editing != "1":
            self.autolock.set_autolock(src_path, self)

        if evt.event_type != "deleted":
            self._upload_queue.put(ref)
