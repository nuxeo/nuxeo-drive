# coding: utf-8
import os
import shutil
from datetime import datetime
from logging import getLogger
from queue import Empty, Queue
from time import sleep
from typing import List, Optional, Tuple, TYPE_CHECKING
from urllib.parse import quote

from nuxeo.utils import get_digest_algorithm
from PyQt5.QtCore import pyqtSignal, pyqtSlot
from watchdog.events import FileSystemEvent
from watchdog.observers import Observer

from .client.local_client import LocalClient
from .constants import DOWNLOAD_TMP_FILE_PREFIX, DOWNLOAD_TMP_FILE_SUFFIX, WINDOWS
from .engine.activity import tooltip
from .engine.blacklist_queue import BlacklistQueue
from .engine.watcher.local_watcher import DriveFSEventHandler
from .engine.workers import Worker
from .exceptions import NotFound, ThreadInterrupt, UnknownDigest
from .objects import Metrics, NuxeoDocumentInfo
from .utils import (
    current_milli_time,
    force_decode,
    normalize_event_filename,
    parse_protocol_url,
    simplify_url,
    unset_path_readonly,
)

if TYPE_CHECKING:
    from .engine.engine import Engine  # noqa
    from .manager import Manager  # noqa

__all__ = ("DirectEdit",)

log = getLogger(__name__)


class DirectEdit(Worker):
    localScanFinished = pyqtSignal()
    directEditUploadCompleted = pyqtSignal(str)
    openDocument = pyqtSignal(object)
    editDocument = pyqtSignal(object)
    directEditLockError = pyqtSignal(str, str, str)
    directEditConflict = pyqtSignal(str, str, str)
    directEditError = pyqtSignal(str, list)
    directEditReadonly = pyqtSignal(str)
    directEditStarting = pyqtSignal(str, str)
    directEditLocked = pyqtSignal(str, str, datetime)

    def __init__(self, manager: "Manager", folder: str, url: str) -> None:
        super().__init__()

        self._manager = manager
        self._folder = force_decode(folder)
        self.url = url

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
    def _autolock_orphans(self, locks: List[str]) -> None:
        log.trace(f"Orphans lock: {locks!r}")
        for lock in locks:
            if lock.startswith(self._folder):
                log.debug(f"Should unlock {lock!r}")
                if not os.path.exists(lock):
                    self.autolock.orphan_unlocked(lock)
                    continue

                ref = self.local.get_path(lock)
                self._lock_queue.put((ref, "unlock_orphan"))

    def autolock_lock(self, src_path: str) -> None:
        ref = self.local.get_path(src_path)
        self._lock_queue.put((ref, "lock"))

    def autolock_unlock(self, src_path: str) -> None:
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

        if not self.local.exists("/"):
            os.mkdir(self._folder)
            return

        def purge(path):
            shutil.rmtree(self.local.abspath(path), ignore_errors=True)

        log.debug("Cleanup DirectEdit folder")

        for child in self.local.get_children_info("/"):
            children = self.local.get_children_info(child.path)
            if not children:
                purge(child.path)
                continue

            ref = children[0].path
            try:
                _, _, func, digest = self._extract_edit_info(ref)
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
                        "not synchronized, readd to upload queue"
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
        self, engine: "Engine", info: NuxeoDocumentInfo, file_path: str, url: str = None
    ) -> str:
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        file_out = os.path.join(
            file_dir, DOWNLOAD_TMP_FILE_PREFIX + file_name + DOWNLOAD_TMP_FILE_SUFFIX
        )

        # Close to processor method - should try to refactor ?
        pair = None
        if info.digest:
            pair = engine.get_dao().get_valid_duplicate_file(info.digest)
        if pair:
            existing_file_path = engine.local.abspath(pair.local_path)
            log.debug(
                f"Local file matches remote digest {info.digest!r}, "
                f"copying it from {existing_file_path!r}"
            )
            shutil.copy(existing_file_path, file_out)
            if pair.is_readonly():
                log.debug(f"Unsetting readonly flag on copied file {file_out!r}")
                unset_path_readonly(file_out)
        else:
            log.debug(f"Downloading file {info.filename!r}")
            if url:
                engine.remote.download(
                    quote(url, safe="/:"),
                    file_out=file_out,
                    digest=info.digest,
                    check_suspended=self.stop_client,
                )
            else:
                engine.remote.get_blob(
                    info, file_out=file_out, check_suspended=self.stop_client
                )
        return file_out

    def _get_info(self, engine: "Engine", doc_id: str) -> Optional[NuxeoDocumentInfo]:
        doc = engine.remote.fetch(
            doc_id, headers={"fetch-document": "lock"}, enrichers=["permissions"]
        )
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
    ) -> Optional[str]:
        start_time = current_milli_time()
        engine = self._get_engine(server_url, doc_id=doc_id, user=user)
        if not engine:
            return None

        # Avoid any link with the engine, remote_doc are not cached so we
        # can do that
        info = self._get_info(engine, doc_id)
        if not info:
            return None

        filename = info.filename
        self.directEditStarting.emit(engine.hostname, filename)

        # Create local structure
        dir_path = os.path.join(self._folder, doc_id)
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)

        log.debug(f"Editing {filename!r}")
        file_path = os.path.join(dir_path, filename)

        # Download the file
        url = None
        if download_url:
            url = server_url
            if not url.endswith("/"):
                url += "/"
            url += download_url

        tmp_file = self._download(engine, info, file_path, url=url)
        if tmp_file is None:
            log.error("Download failed")
            return None

        # Set the remote_id
        dir_path = self.local.get_path(os.path.dirname(file_path))
        self.local.set_remote_id(dir_path, doc_id)
        self.local.set_remote_id(dir_path, server_url, name="nxdirectedit")

        if user:
            self.local.set_remote_id(dir_path, user, name="nxdirectedituser")

        if info.digest:
            self.local.set_remote_id(dir_path, info.digest, name="nxdirecteditdigest")
            # Set digest algorithm if not sent by the server
            digest_algorithm = info.digest_algorithm
            if not digest_algorithm:
                digest_algorithm = get_digest_algorithm(info.digest)
                if not digest_algorithm:
                    raise UnknownDigest(info.digest)
            self.local.set_remote_id(
                dir_path,
                digest_algorithm.encode("utf-8"),
                name="nxdirecteditdigestalgorithm",
            )
        self.local.set_remote_id(dir_path, filename, name="nxdirecteditname")

        # Rename to final filename
        # Under Windows first need to delete target file if exists,
        # otherwise will get a 183 WindowsError
        if WINDOWS and os.path.exists(file_path):
            os.unlink(file_path)
        os.rename(tmp_file, file_path)

        self._last_action_timing = current_milli_time() - start_time
        self.openDocument.emit(info)
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

    def _extract_edit_info(self, ref: str) -> Tuple[str, "Engine", str, str]:
        dir_path = os.path.dirname(ref)
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

        return uid, engine, digest_algorithm, digest

    def force_update(self, ref: str, digest: str) -> None:
        dir_path = os.path.dirname(ref)
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
                uid, engine, _, _ = self._extract_edit_info(ref)
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
        for engine in manager._engine_definitions:
            dao = manager._engines[engine.uid]._dao
            state = dao.get_normal_state_from_remote(ref)
            if state:
                path = os.path.join(engine.local_folder, state.local_path)
                manager.osi.send_sync_status(state, path)

    def _handle_upload_queue(self) -> None:
        while not self._upload_queue.empty():
            try:
                ref = self._upload_queue.get_nowait()
            except Empty:
                break

            log.trace(f"Handling DirectEdit queue ref: {ref!r}")

            uid, engine, algorithm, digest = self._extract_edit_info(ref)
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
                if remote_info and remote_info.digest != digest:
                    # Conflict detect
                    log.trace(
                        f"Remote digest: {remote_info.digest} is different from the "
                        f"recorded  one: {digest} - conflict detected for {ref!r}"
                    )
                    self.directEditConflict.emit(
                        os.path.basename(ref), ref, remote_info.digest
                    )
                    continue

                os_path = self.local.abspath(ref)
                log.debug(f"Uploading file {os_path!r}")
                engine.remote.stream_attach(uid, os_path)

                # Update hash value
                dir_path = os.path.dirname(ref)
                self.local.set_remote_id(
                    dir_path, current_digest, name="nxdirecteditdigest"
                )
                self._last_action_timing = current_milli_time() - start_time
                self.directEditUploadCompleted.emit(os.path.basename(os_path))
                self.editDocument.emit(remote_info)
            except NotFound:
                # Not found on the server, just skip it
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
            self.handle_watchdog_event(evt)

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
                sleep(0.01)
        except ThreadInterrupt:
            raise
        finally:
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
        self._observer.schedule(self._event_handler, self._folder, recursive=True)
        self._observer.start()

    def _stop_watchdog(self) -> None:
        if not self._observer:
            return

        log.info("Stopping FS Observer thread")
        try:
            self._observer.stop()
        except:
            log.exception("Cannot stop the FS observer")

        # Wait for the observer to stop
        try:
            self._observer.join()
        except:
            log.exception("Cannot join the FS observer")

        # Delete the observer
        self._observer = None

    @staticmethod
    def _is_lock_file(name: str) -> bool:
        """
        Check if a given file name is a temporary one created by
        a tierce software.
        """

        return name.startswith(
            ("~$", ".~lock.")  # Microsoft Office  # (Libre|Open)Office
        )

    @tooltip("Handle watchdog event")
    def handle_watchdog_event(self, evt: FileSystemEvent) -> None:
        try:
            src_path = normalize_event_filename(evt.src_path)

            # Event on the folder by itself
            if os.path.isdir(src_path):
                return

            file_name = force_decode(os.path.basename(src_path))
            if self.local.is_temp_file(file_name):
                return

            log.debug(f"Handling watchdog event [{evt.event_type}] on {evt.src_path!r}")

            if evt.event_type == "moved":
                src_path = normalize_event_filename(evt.dest_path)
                file_name = force_decode(os.path.basename(src_path))

            ref = self.local.get_path(src_path)
            dir_path = self.local.get_path(os.path.dirname(src_path))
            name = self.local.get_remote_id(dir_path, name="nxdirecteditname")

            if not name:
                return

            editing = self.local.get_remote_id(dir_path, name="nxdirecteditlock")

            if force_decode(name) != file_name:
                if self._is_lock_file(file_name):
                    if (
                        evt.event_type == "created"
                        and self.use_autolock
                        and editing != "1"
                    ):
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
                        path = os.path.join(os.path.dirname(src_path), name)
                        self.autolock.set_autolock(path, self)
                    elif evt.event_type == "deleted":
                        # Free the xattr to let _cleanup() does its work
                        self.local.remove_remote_id(dir_path, name="nxdirecteditlock")
                return

            if self.use_autolock and editing != "1":
                self.autolock.set_autolock(src_path, self)

            if evt.event_type != "deleted":
                self._upload_queue.put(ref)
        except ThreadInterrupt:
            raise
        except:
            log.exception("Watchdog error")
