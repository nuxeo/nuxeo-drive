# coding: utf-8
import errno
import re
import shutil
from datetime import datetime
from logging import getLogger
from pathlib import Path
from queue import Empty, Queue
from time import sleep
from threading import Lock
from typing import Any, Dict, List, Optional, Pattern, TYPE_CHECKING
from urllib.parse import quote

from nuxeo.exceptions import Forbidden, HTTPError, Unauthorized
from nuxeo.utils import get_digest_algorithm
from nuxeo.models import Blob
from PyQt5.QtCore import pyqtSignal, pyqtSlot
from requests import codes
from watchdog.events import FileSystemEvent
from watchdog.observers import Observer

from .client.local import LocalClient
from .client.remote_client import Remote
from .constants import CONNECTION_ERROR, DOC_UID_REG, ROOT
from .engine.activity import tooltip
from .engine.blacklist_queue import BlacklistQueue
from .engine.watcher.local_watcher import DriveFSEventHandler
from .engine.workers import Worker
from .exceptions import DocumentAlreadyLocked, NotFound, ThreadInterrupt, UnknownDigest
from .objects import DirectEditDetails, Metrics, NuxeoDocumentInfo
from .options import Options
from .utils import (
    current_milli_time,
    force_decode,
    normalize_event_filename,
    safe_filename,
    simplify_url,
    unset_path_readonly,
    safe_rename,
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

    # Microsoft Office, (Libre|Open)Office
    return name.startswith(("~$", ".~lock."))


class DirectEdit(Worker):
    localScanFinished = pyqtSignal()
    directEditUploadCompleted = pyqtSignal(str)
    openDocument = pyqtSignal(str, int)
    editDocument = pyqtSignal(str, int)
    directEditLockError = pyqtSignal(str, str, str)
    directEditConflict = pyqtSignal(str, Path, str)
    directEditError = pyqtSignal(str, list)
    directEditForbidden = pyqtSignal(str, str, str)
    directEditReadonly = pyqtSignal(str)
    directEditStarting = pyqtSignal(str, str)
    directEditLocked = pyqtSignal(str, str, datetime)

    def __init__(self, manager: "Manager", folder: Path) -> None:
        super().__init__()

        self._manager = manager
        self._folder = folder
        self.url = Options.protocol_url
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
        self.watchdog_queue: Queue = Queue()

        self.thread.started.connect(self.run)
        self.autolock.orphanLocks.connect(self._autolock_orphans)
        self._manager.directEdit.connect(self.edit)

    @pyqtSlot(object)
    def _autolock_orphans(self, locks: List[Path]) -> None:
        log.debug(f"Orphans lock: {locks!r}")
        for lock in locks:
            if self._folder in lock.parents:
                log.info(f"Should unlock {lock!r}")
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

    def _is_valid_folder_name(
        self, name: str, pattern: Pattern = re.compile(f"^{DOC_UID_REG}_")
    ) -> bool:
        """
        Return True if the given *name* is a valid document UID followed by the xpath.
        As we cannot guess the xpath used, we just check the name starts with "UID_".
        Example: 19bf2a19-e95b-4cfb-8fd7-b45e1d7d022f_file-content
        """
        # Prevent TypeError when the given name is None
        if not name:
            return False

        return bool(pattern.match(name))

    @tooltip("Clean up folder")
    def _cleanup(self) -> None:
        """
        - Unlock any remaining doc that has not been unlocked
        - Upload forgotten changes
        - Remove obsolete folders
        """

        if not self.local.exists(ROOT):
            self._folder.mkdir(exist_ok=True)
            return

        def purge(rel_path: Path) -> None:
            """Helper to skip errors while deleting a folder and its content."""
            path = self.local.abspath(rel_path)
            log.debug(f"Removing {path!r}")
            shutil.rmtree(path, ignore_errors=True)

        log.info("Cleanup DirectEdit folder")

        for child in self.local.get_children_info(ROOT):
            # We need a folder
            if not child.folderish:
                log.debug(f"Skipping clean-up of {child.path!r} (not a folder)")
                continue

            # We also need a valid folder name
            if not self._is_valid_folder_name(child.name):
                log.debug(f"Skipping clean-up of {child.path!r} (invalid folder name)")
                continue

            children = self.local.get_children_info(child.path)
            if not children:
                purge(child.path)
                continue

            ref = children[0].path
            try:
                details = self._extract_edit_info(ref)
            except NotFound:
                # Engine is not known anymore
                purge(child.path)
                continue

            try:
                # Don't update if digest are the same
                info = self.local.get_info(ref)
                current_digest = info.get_digest(digest_func=details.digest_func)
                if current_digest != details.digest:
                    log.warning(
                        "Document has been modified and "
                        "not synchronized, add to upload queue"
                    )
                    self._upload_queue.put(ref)
                    continue
            except Exception:
                log.exception("Unhandled clean-up error")
                continue

            # Place for handle reopened of interrupted DirectEdit
            purge(child.path)

    def __get_engine(self, url: str, user: str = None) -> Optional["Engine"]:
        if not url:
            return None

        url = simplify_url(url)
        for engine in self._manager.engines.values():
            bind = engine.get_binder()
            server_url = bind.server_url.rstrip("/")
            if server_url == url and (not user or user == bind.username):
                return engine

        # Some backend are case insensitive
        if not user:
            return None

        user = user.lower()
        for engine in self._manager.engines.values():
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
            # Ping again the user in case it is not obvious
            engine.invalidAuthentication.emit()
            engine = None

        return engine

    def _download(
        self,
        engine: "Engine",
        info: NuxeoDocumentInfo,
        file_path: Path,
        file_out: Path,
        blob: Blob,
        xpath: str,
        url: str = None,
    ) -> Path:
        # Close to processor method - should try to refactor ?
        pair = None
        kwargs: Dict[str, Any] = {}

        if blob.digest:
            # The digest is available in the Blob, use it and disable parameters check
            # as 'digest' is not a recognized param for the Blob.Get operation.
            kwargs["digest"] = blob.digest
            kwargs["check_params"] = False

            pair = engine.dao.get_valid_duplicate_file(blob.digest)

        if pair:
            existing_file_path = engine.local.abspath(pair.local_path)
            try:
                # copyfile() is used to prevent metadata copy
                shutil.copyfile(existing_file_path, file_out)
            except FileNotFoundError:
                pair = None
            else:
                log.info(
                    f"Local file matches remote digest {blob.digest!r}, "
                    f"copied it from {existing_file_path!r}"
                )
                if pair.is_readonly():
                    log.info(f"Unsetting readonly flag on copied file {file_out!r}")
                    unset_path_readonly(file_out)

        if not pair:
            if url:
                try:
                    engine.remote.download(
                        quote(url, safe="/:"),
                        file_path,
                        file_out,
                        blob.digest,
                        callback=self.stop_client,
                        is_direct_edit=True,
                        engine_uid=engine.uid,
                    )
                finally:
                    engine.dao.remove_transfer("download", file_path)
            else:
                engine.remote.get_blob(
                    info,
                    xpath=xpath,
                    file_out=file_out,
                    callback=self.stop_client,
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
        except Unauthorized:
            engine.set_invalid_credentials()
            return None
        except NotFound:
            values = [doc_id, engine.hostname]
            self.directEditError.emit("DIRECT_EDIT_NOT_FOUND", values)
            return None

        doc.update(
            {
                "root": engine.remote.base_folder_ref,
                "repository": engine.remote.client.repository,
            }
        )
        info = NuxeoDocumentInfo.from_dict(doc)

        if info.is_version:
            self.directEditError.emit(
                "DIRECT_EDIT_VERSION", [info.version, info.name, info.uid]
            )
            return None

        if info.lock_owner and info.lock_owner != engine.remote_user:
            # Retrieve the user full name, will be cached
            owner = engine.get_user_full_name(info.lock_owner)

            log.info(
                f"Doc {info.name!r} was locked by {owner} ({info.lock_owner}) "
                f"on {info.lock_created}, edit not allowed"
            )
            self.directEditLocked.emit(info.name, owner, info.lock_created)
            return None
        elif info.permissions and "Write" not in info.permissions:
            log.info(f"Doc {info.name!r} is readonly for you, edit not allowed")
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

        xpath = url_info.get("xpath")
        if not xpath:
            if info.doc_type == "Note":
                xpath = "note:note"
            else:
                xpath = "file:content"
        elif xpath == "blobholder:0":
            xpath = "file:content"

        blob = info.get_blob(xpath)
        if not blob:
            log.warning(f"No blob associated with xpath {xpath} for file {info.path}")
            return None

        filename = blob.name
        self.directEditStarting.emit(engine.hostname, filename)

        # Create local structure
        folder_name = safe_filename(f"{doc_id}_{xpath}")
        dir_path = self._folder / folder_name
        dir_path.mkdir(exist_ok=True)

        log.info(f"Editing {filename!r}")
        file_path = dir_path / filename
        tmp_folder = self._folder / f"{doc_id}.dl"
        tmp_folder.mkdir(parents=True, exist_ok=True)
        file_out = tmp_folder / filename

        try:
            # Download the file
            tmp_file = self._download(
                engine, info, file_path, file_out, blob, xpath, url=url
            )
            if tmp_file is None:
                log.warning("Download failed")
                return None
        except CONNECTION_ERROR:
            log.warning("Unable to perform DirectEdit", exc_info=True)
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

        safe_rename(tmp_file, file_path)

        timing = current_milli_time() - start_time
        self.openDocument.emit(filename, timing)
        return file_path

    @pyqtSlot(str, str, str, str)
    def edit(
        self, server_url: str, doc_id: str, user: str = None, download_url: str = None
    ) -> None:
        log.info(f"Direct Editing doc {doc_id!r} on {server_url!r}")
        try:
            # Download the file
            file_path = self._prepare_edit(
                server_url, doc_id, user=user, download_url=download_url
            )
            log.debug("Direct Edit preparation returned file path {file_path!r}")

            # Launch it
            if file_path:
                self._manager.open_local_file(file_path)
        except OSError as e:
            if e.errno == errno.EACCES:
                # Open file anyway
                if e.filename is not None:
                    self._manager.open_local_file(e.filename)
            else:
                raise e

    def _extract_edit_info(self, ref: Path) -> DirectEditDetails:
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
        editing = self.local.get_remote_id(dir_path, name="nxdirecteditlock") == "1"

        details = DirectEditDetails(
            uid=uid,
            engine=engine,
            digest_func=digest_algorithm,
            digest=digest,
            xpath=xpath,
            editing=editing,
        )
        log.debug(f"DirectEdit {details}")
        return details

    def force_update(self, ref: Path, digest: str) -> None:
        dir_path = ref.parent
        self.local.set_remote_id(
            dir_path, digest.encode("utf-8"), name="nxdirecteditdigest"
        )
        self._upload_queue.put(ref)

    def _lock(self, remote: Remote, uid: str) -> bool:
        """Lock a document."""
        try:
            remote.lock(uid)
        except HTTPError as exc:
            if exc.status in (codes.CONFLICT, codes.INTERNAL_SERVER_ERROR):
                # CONFLICT if NXP-24359 is part of the current server HF
                # else INTERNAL_SERVER_ERROR is raised on double lock.
                username = re.findall(r"Document already locked by (.+):", exc.message)
                if username:
                    if username[0] == remote.user_id:
                        # Already locked by the same user
                        log.debug("You already locked that document!")
                        return False
                    else:
                        # Already locked by someone else
                        raise DocumentAlreadyLocked(username[0])
            raise exc
        else:
            # Document locked!
            return True

        return False

    def _handle_lock_queue(self) -> None:
        errors = []

        while "items":
            try:
                item = self._lock_queue.get_nowait()
            except Empty:
                break

            ref, action = item
            log.debug(f"Handling DirectEdit lock queue: action={action}, ref={ref!r}")
            uid = ""

            try:
                details = self._extract_edit_info(ref)
                uid = details.uid
                remote = details.engine.remote
                if action == "lock":
                    self._lock(remote, uid)
                    self.local.set_remote_id(ref.parent, b"1", name="nxdirecteditlock")
                    # Emit the lock signal only when the lock is really set
                    self._send_lock_status(ref)
                    self.autolock.documentLocked.emit(ref.name)
                    continue

                try:
                    remote.unlock(uid)
                except NotFound:
                    purge = True
                else:
                    purge = False

                if purge or action == "unlock_orphan":
                    path = self.local.abspath(ref)
                    log.debug(f"Remove orphan: {path!r}")
                    self.autolock.orphan_unlocked(path)
                    shutil.rmtree(path, ignore_errors=True)
                    continue

                self.local.remove_remote_id(ref.parent, name="nxdirecteditlock")
                # Emit the signal only when the unlock is done
                self._send_lock_status(ref)
                self.autolock.documentUnlocked.emit(ref.name)
            except ThreadInterrupt:
                raise
            except NotFound:
                log.debug(f"Document {ref!r} no more exists")
            except DocumentAlreadyLocked as exc:
                log.warning(f"Document {ref!r} already locked by {exc.username}")
                self.directEditLockError.emit(action, ref.name, uid)
            except CONNECTION_ERROR:
                # Try again in 30s
                log.warning(
                    f"Connection error while trying to {action} document {ref!r}",
                    exc_info=True,
                )
                errors.append(item)
            except Exception:
                log.exception(f"Cannot {action} document {ref!r}")
                self.directEditLockError.emit(action, ref.name, uid)

        # Requeue errors
        for item in errors:
            self._lock_queue.put(item)

    def _send_lock_status(self, ref: str) -> None:
        manager = self._manager
        for engine in manager.engines.values():
            dao = engine.dao
            state = dao.get_normal_state_from_remote(ref)
            if state:
                path = engine.local_folder / state.local_path
                manager.osi.send_sync_status(state, path)

    def _handle_upload_queue(self) -> None:
        while "items":
            try:
                ref = self._upload_queue.get_nowait()
            except Empty:
                break

            os_path = self.local.abspath(ref)

            if os_path.is_dir():
                # The upload file is a folder?!
                # It *may* happen when the user DirectEdit'ed a ZIP file,
                # the OS opened it and automatically decompressed it in-place.
                log.debug(f"Skipping DirectEdit queue ref {ref!r} (folder)")
                continue

            log.debug(f"Handling DirectEdit queue ref: {ref!r}")

            details = self._extract_edit_info(ref)
            xpath = details.xpath
            engine = details.engine
            remote = engine.remote

            if not xpath:
                xpath = "file:content"
                log.info(f"DirectEdit on {ref!r} has no xpath, defaulting to {xpath!r}")

            try:
                # Don't update if digest are the same
                info = self.local.get_info(ref)
                current_digest = info.get_digest(digest_func=details.digest_func)
                if not current_digest or current_digest == details.digest:
                    continue

                start_time = current_milli_time()
                log.debug(
                    f"Local digest: {current_digest} is different from the recorded "
                    f"one: {details.digest} - modification detected for {ref!r}"
                )

                if not details.editing:
                    # Check the remote hash to prevent data loss
                    remote_info = remote.get_info(details.uid)
                    if remote_info.is_version:
                        log.warning(
                            f"Unable to process DirectEdit on {remote_info.name} "
                            f"({details.uid}) because it is a version."
                        )
                        continue
                    remote_blob = remote_info.get_blob(xpath) if remote_info else None
                    if remote_blob and remote_blob.digest != details.digest:
                        log.debug(
                            f"Remote digest: {remote_blob.digest} is different from the "
                            f"recorded  one: {details.digest} - conflict detected for {ref!r}"
                        )
                        self.directEditConflict.emit(ref.name, ref, remote_blob.digest)
                        continue

                log.info(f"Uploading file {os_path!r}")

                if xpath == "note:note":
                    kwargs: Dict[str, Any] = {"applyVersioningPolicy": True}
                    cmd = "NuxeoDrive.AttachBlob"
                else:
                    kwargs = {"xpath": xpath, "void_op": True}
                    cmd = "Blob.AttachOnDocument"

                remote.upload(
                    os_path,
                    command=cmd,
                    document=remote.check_ref(details.uid),
                    engine_uid=engine.uid,
                    is_direct_edit=True,
                    **kwargs,
                )

                # Update hash value
                dir_path = ref.parent
                self.local.set_remote_id(
                    dir_path, current_digest, name="nxdirecteditdigest"
                )
                timing = current_milli_time() - start_time
                self.directEditUploadCompleted.emit(os_path.name)
                self.editDocument.emit(ref.name, timing)
            except ThreadInterrupt:
                raise
            except NotFound:
                # Not found on the server, just skip it
                pass
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
            except CONNECTION_ERROR:
                # Try again in 30s
                log.warning(f"Connection error while uploading {ref!r}", exc_info=True)
                self._error_queue.push(ref)
            except Exception as e:
                if (
                    isinstance(e, HTTPError)
                    and e.status == 500
                    and "Cannot set property on a version" in e.message
                ):
                    log.warning(
                        f"Unable to process DirectEdit on {ref} "
                        f"({details}) because it is a version."
                    )
                    continue
                # Try again in 30s
                log.exception(f"DirectEdit unhandled error for ref {ref!r}")
                self._error_queue.push(ref)

    def _handle_queues(self) -> None:
        # Lock any document
        self._handle_lock_queue()

        # Unqueue any errors
        for item in self._error_queue.get():
            self._upload_queue.put(item.path)

        # Handle the upload queue
        self._handle_upload_queue()

        while not self.watchdog_queue.empty():
            evt = self.watchdog_queue.get()
            try:
                self.handle_watchdog_event(evt)
            except ThreadInterrupt:
                raise
            except Exception:
                log.exception("Watchdog error")

    def _execute(self) -> None:
        try:
            self._cleanup()
            self._setup_watchdog()

            while True:
                self._interact()
                try:
                    self._handle_queues()
                except NotFound:
                    continue
                except ThreadInterrupt:
                    raise
                except Exception:
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
        return {**metrics, **self._metrics}

    @tooltip("Setup watchdog")
    def _setup_watchdog(self) -> None:
        log.info(f"Watching FS modification on {self._folder!r}")
        self._event_handler = DriveFSEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(self._event_handler, str(self._folder), recursive=True)
        self._observer.start()

    def _stop_watchdog(self) -> None:
        log.info("Stopping the FS observer thread")
        try:
            self._observer.stop()
            self._observer.join()
        except Exception:
            log.warning("Cannot stop the FS observer")
        finally:
            self._observer = None

    @tooltip("Handle watchdog event")
    def handle_watchdog_event(self, evt: FileSystemEvent) -> None:
        src_path = normalize_event_filename(evt.src_path)

        # Event on the folder by itself
        if src_path.is_dir():
            return

        if self.local.is_temp_file(src_path):
            return

        log.info(f"Handling watchdog event [{evt.event_type}] on {evt.src_path!r}")

        if evt.event_type == "moved":
            src_path = normalize_event_filename(evt.dest_path)

        ref = self.local.get_path(src_path)
        dir_path = self.local.get_path(src_path.parent)
        name = self.local.get_remote_id(dir_path, name="nxdirecteditname")

        if not name:
            return

        editing = self.local.get_remote_id(dir_path, name="nxdirecteditlock") == "1"

        if force_decode(name) != src_path.name:
            if _is_lock_file(src_path.name):
                if evt.event_type == "created" and self.use_autolock and not editing:
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

        if self.use_autolock and not editing:
            self.autolock.set_autolock(src_path, self)

        if evt.event_type != "deleted":
            self._upload_queue.put(ref)
