"""Server-agnostic Direct Edit base class.

Provides the generic file-watching, queue management, cleanup, and
autolock integration.  Server-specific operations (document locking,
blob download, upload) are abstract and must be supplied by a subclass
in each server-type package (e.g. ``nuxeo/direct_edit.py``).
"""

import errno
import re
import shutil
from collections import defaultdict
from datetime import datetime
from logging import getLogger
from os import path
from pathlib import Path
from queue import Queue
from threading import Lock
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Pattern

from watchdog.events import FileSystemEvent
from watchdog.observers import Observer, api

from nxdrive.drive.client.local import LocalClient
from nxdrive.drive.constants import APP_NAME, CONNECTION_ERROR, DOC_UID_REG, ROOT
from nxdrive.drive.engine.activity import tooltip
from nxdrive.drive.engine.blocklist_queue import BlocklistQueue
from nxdrive.drive.engine.watcher.local_watcher import DriveFSEventHandler
from nxdrive.drive.engine.workers import Worker
from nxdrive.drive.exceptions import NoAssociatedSoftware, NotFound, ThreadInterrupt
from nxdrive.drive.feature import Feature
from nxdrive.drive.objects import DirectEditDetails, Metrics
from nxdrive.drive.options import Options
from nxdrive.drive.qt.imports import pyqtSignal, pyqtSlot
from nxdrive.drive.utils import (
    current_milli_time,
    force_decode,
    normalize_event_filename,
    safe_filename,
    safe_rename,
    simplify_url,
)

if TYPE_CHECKING:
    from nxdrive.drive.engine.engine import Engine  # noqa
    from nxdrive.drive.manager import Manager  # noqa

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
    """Server-agnostic Direct Edit worker.

    Subclass in each server-type package and override the abstract hooks:
    ``_download()``, ``_get_info()``, ``_lock()``, ``_unlock()``,
    ``stop_client()``, ``_handle_upload_queue()``, ``_handle_lock_queue()``.
    """

    localScanFinished = pyqtSignal()
    directEditUploadCompleted = pyqtSignal(str)
    openDocument = pyqtSignal(str, int)
    editDocument = pyqtSignal(str, int)
    directEditLockError = pyqtSignal(str, str, str)
    directEditConflict = pyqtSignal(str, Path, str)
    directEditError = pyqtSignal([str, list], [str, list, str])
    directEditForbidden = pyqtSignal(str, str, str)
    directEditReadonly = pyqtSignal(str)
    directEditStarting = pyqtSignal(str, str)
    directEditLocked = pyqtSignal(str, str, datetime)

    def __init__(self, manager: "Manager", folder: Path, /) -> None:
        super().__init__("DirectEdit")

        self._manager = manager
        self._folder = folder
        self.url = Options.protocol_url
        self.lock = Lock()

        self.autolock = self._manager.autolock_service

        self._event_handler: Optional[DriveFSEventHandler] = None
        self._metrics: Metrics = {"edit_files": 0}
        self._observer: api.BaseObserver = None
        self.local = LocalClient(self._folder)
        self._upload_queue: Queue = Queue()
        self.is_already_locked = False
        self._upload_errors: Dict[Path, int] = defaultdict(int)
        self._lock_queue: Queue = Queue()
        self._error_queue = BlocklistQueue(delay=Options.delay)
        self._stop = False
        self.watchdog_queue: Queue = Queue()
        self._error_threshold = Options.max_errors

        self.thread.started.connect(self.run)
        self.autolock.orphanLocks.connect(self._autolock_orphans)
        self._manager.directEdit.connect(self.edit)

        # Notification signals
        self.directEditLockError.connect(
            self._manager.notification_service._directEditLockError
        )
        self.directEditStarting.connect(
            self._manager.notification_service._directEditStarting
        )
        self.directEditForbidden.connect(
            self._manager.notification_service._directEditForbidden
        )
        self.directEditReadonly.connect(
            self._manager.notification_service._directEditReadonly
        )
        self.directEditLocked.connect(
            self._manager.notification_service._directEditLocked
        )
        self.directEditUploadCompleted.connect(
            self._manager.notification_service._directEditUpdated
        )
        self._file_metrics: Dict[Path, Any] = {}

    # ------------------------------------------------------------------ properties

    @property
    def use_autolock(self) -> bool:
        """Return True if document locking mechanism should be used on the server."""
        return bool(self._manager.get_direct_edit_auto_lock())

    # ------------------------------------------------------------------ autolock helpers

    @pyqtSlot(object)
    def _autolock_orphans(self, locks: List[Path], /) -> None:
        log.debug(f"Orphans lock: {locks!r}")
        for lock in locks:
            if self._folder in lock.parents:
                log.info(f"Should unlock {lock!r}")
                ref = self.local.get_path(lock)
                self._lock_queue.put((ref, "unlock_orphan"))

    def autolock_lock(self, src_path: Path, /) -> None:
        ref = self._get_ref(src_path)
        self._lock_queue.put((ref, "lock"))

    def autolock_unlock(self, src_path: Path) -> None:
        ref = self._get_ref(src_path)
        self._lock_queue.put((ref, "unlock"))

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self._stop = False
        super().start()

    def stop(self) -> None:
        super().stop()
        self._stop = True

    # ------------------------------------------------------------------ abstract hooks (override in subclass)

    def stop_client(self, uploader: Any = None, /) -> None:
        """Interrupt the current transfer if the worker is stopping.
        Override to integrate with the server-specific uploader."""
        if self._stop:
            raise ThreadInterrupt()

    def _download(
        self,
        engine: "Engine",
        info: Any,
        file_path: Path,
        file_out: Path,
        blob: Any,
        xpath: str,
        /,
        **kwargs: Any,
    ) -> Optional[Path]:
        """Download the document blob.  **Must be overridden.**"""
        raise NotImplementedError

    def _get_info(self, engine: "Engine", doc_id: str, /) -> Any:
        """Fetch document info from the server (lock if autolock).
        **Must be overridden.**"""
        raise NotImplementedError

    def _lock(self, remote: Any, uid: str, ref: Any = None, /) -> Any:
        """Lock a document on the server.  **Must be overridden.**"""
        raise NotImplementedError

    def _unlock(self, remote: Any, uid: str, ref: Path, /) -> bool:
        """Unlock a document on the server.  Return True if purge needed.
        **Must be overridden.**"""
        raise NotImplementedError

    def _handle_upload_queue(self) -> None:
        """Process the upload queue.  **Must be overridden.**"""
        raise NotImplementedError

    def _handle_lock_queue(self) -> None:
        """Process the lock/unlock queue.  **Must be overridden.**"""
        raise NotImplementedError

    # ------------------------------------------------------------------ helpers

    def _is_valid_folder_name(self, name: str) -> bool:
        """
        Return True if the given *name* is a valid document UID followed by the xpath.
        As we cannot guess the xpath used, we just check the name starts with "UID_".
        Example: 19bf2a19-e95b-4cfb-8fd7-b45e1d7d022f_file-content
        """
        pattern: Pattern = re.compile(f"^{DOC_UID_REG}_")
        dl_files_pattern: Pattern = re.compile(f"^{DOC_UID_REG}.dl")
        if not name:
            return False
        if name.endswith(".dl"):
            return bool(dl_files_pattern.match(name))
        else:
            return bool(pattern.match(name))

    def __get_engine(self, url: str, /, *, user: str = None) -> Optional["Engine"]:
        if not url:
            return None

        url = simplify_url(url)
        for engine in self._manager.engines.copy().values():
            bind = engine.get_binder()
            server_url = simplify_url(bind.server_url.rstrip("/"))
            if server_url == url and (not user or user == bind.username):
                return engine

        # Some backend are case insensitive
        if not user:
            return None

        user = user.lower()
        for engine in self._manager.engines.copy().values():
            bind = engine.get_binder()
            server_url = simplify_url(bind.server_url)
            if server_url == url and user == bind.username.lower():
                return engine

        return None

    def _get_engine(
        self, server_url: str, /, *, doc_id: str = None, user: str = None
    ) -> Optional["Engine"]:
        engine = self.__get_engine(server_url, user=user)

        if not engine:
            values = [force_decode(user) if user else "Unknown", server_url, APP_NAME]
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

    def _get_tmp_file(self, doc_id: str, filename: str, /) -> Path:
        """Return the temporary file that will be used to download contents.
        Using a method to help testing.
        """
        tmp_folder = self._folder / f"{doc_id}.dl"
        tmp_folder.mkdir(parents=True, exist_ok=True)
        return tmp_folder / filename

    def _extract_edit_info(self, ref: Path, /) -> DirectEditDetails:
        dir_path = ref.parent
        server_url = self.local.get_remote_id(dir_path, name="nxdirectedit")
        if not server_url:
            raise NotFound(f"Could not find server url: {server_url}")

        user = self.local.get_remote_id(dir_path, name="nxdirectedituser")
        engine = self._get_engine(server_url, user=user)
        if not engine:
            raise NotFound(f"Could not find engine: {engine}")

        uid = self.local.get_remote_id(dir_path)
        if not uid:
            raise NotFound(f"Could not find uid: {uid}")

        digest_algorithm = self.local.get_remote_id(
            dir_path, name="nxdirecteditdigestalgorithm"
        )
        digest = self.local.get_remote_id(dir_path, name="nxdirecteditdigest")
        xpath = self.local.get_remote_id(dir_path, name="nxdirecteditxpath")
        editing = self.local.get_remote_id(dir_path, name="nxdirecteditlock") == "1"

        details = DirectEditDetails(
            uid=uid,
            engine=engine,
            digest_func=digest_algorithm or "",
            digest=digest or "",
            xpath=xpath,
            editing=editing,
        )
        log.debug(f"Direct Edit {details}")
        return details

    def force_update(self, ref: Path, digest: str, /) -> None:
        dir_path = ref.parent
        self.local.set_remote_id(
            dir_path, digest.encode("utf-8"), name="nxdirecteditdigest"
        )
        self._upload_queue.put(ref)

    @staticmethod
    def _guess_user_from_http_error(message: str, /) -> str:
        """Find the username from the error *message*.
        *message* is an HTTP error and likely contains the username
        when it is about document (un)locking issues.
        """
        matches = re.findall(r"Document already locked by ([^:]+)", message)
        user: str = matches[0] if matches else ""
        return user

    def send_notification(self, ref: Any, filename: Any = None) -> None:
        # Emit the lock signal only when the lock is really set
        self._send_lock_status(ref)
        if not filename:
            filename = ref.name
        self.autolock.documentLocked.emit(filename)

    def _send_lock_status(self, ref: str, /) -> None:
        manager = self._manager
        for engine in manager.engines.copy().values():
            dao = engine.dao
            if state := dao.get_normal_state_from_remote(ref):
                path_ = engine.local_folder / state.local_path
                manager.osi.send_sync_status(state, path_)

    # ------------------------------------------------------------------ cleanup

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
            p = self.local.abspath(rel_path)
            log.debug(f"Removing {p!r}")
            shutil.rmtree(p, ignore_errors=True)

        log.info("Cleanup Direct Edit folder")

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

            # Get filename stored in folder nxdirecteditname attribute
            expected_name = self.local.get_remote_id(
                child.path, name="nxdirecteditname"
            )
            if not expected_name:
                continue

            filtered = [file for file in children if file.name == expected_name]
            # Folder doesn't contain the expected file so we do nothing.
            if not filtered:
                continue

            # The expected file is found so we use it
            ref = filtered[0].path

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

            # Other files are present next to the edited file, we should not delete them nor the edit file
            if len(children) > 1:
                continue

            # Place for handle reopened of interrupted Direct Edit
            # Orphans locked files are ignored here as they are deleted later after being unlocked
            locks = self._manager.dao.get_locked_paths()
            if any(child.filepath for lock in locks if child.filepath in lock.parents):
                continue

            # Finally
            purge(child.path)

    # ------------------------------------------------------------------ prepare / edit

    def _prepare_edit(
        self,
        server_url: str,
        doc_id: str,
        /,
        *,
        user: str = None,
        download_url: str = None,
        callback: Optional[Callable] = None,
    ) -> Optional[Path]:
        start_time = current_milli_time()
        engine = self._get_engine(server_url, doc_id=doc_id, user=user)
        if not engine:
            return None

        info = self._get_info(engine, doc_id)

        if not info:
            return None

        url = None
        url_info: Dict[str, str] = {}
        if download_url:
            import re

            if urlmatch := re.match(
                r"([^\/]+\/){3}(?P<xpath>.+)\/(?P<filename>[^\?]*).*",
                download_url,
                re.I,
            ):
                url_info = urlmatch.groupdict()

            url = server_url
            if not url.endswith("/"):
                url += "/"
            url += download_url

        xpath = url_info.get("xpath")
        if not xpath and info.doc_type == "Note":
            xpath = "note:note"
        elif not xpath or xpath == "blobholder:0":
            xpath = "file:content"

        blob = info.get_blob(xpath)
        if not blob:
            log.warning(
                f"No blob associated with xpath {xpath!r} for file {info.path!r}"
            )
            return None

        filename = blob.name
        self.directEditStarting.emit(engine.hostname, filename)

        # Create local structure
        folder_name = safe_filename(f"{doc_id}_{xpath}")
        ref = path.join(folder_name, filename)
        dir_path = self._folder / folder_name
        dir_path.mkdir(exist_ok=True)
        log.debug(f"Editing file at {ref!r}")
        if self.is_already_locked:
            self.send_notification(ref, filename)

        if filename != safe_filename(filename):
            filename = safe_filename(filename)
            log.info(f"Filename sanitized to {filename!r}")

        file_path = dir_path / filename
        file_out = self._get_tmp_file(doc_id, filename)

        try:
            # Download the file
            tmp_file = self._download(
                engine,
                info,
                file_path,
                file_out,
                blob,
                xpath,
                url=url,
                callback=callback,
            )
            if tmp_file is None:
                log.warning("Download failed")
                return None
        except CONNECTION_ERROR:
            log.warning("Unable to perform Direct Edit", exc_info=True)
            return None

        # Set the remote_id
        dir_path = self.local.get_path(dir_path)
        self.local.set_remote_id(dir_path, doc_id)
        self.local.set_remote_id(dir_path, server_url, name="nxdirectedit")

        if user:
            self.local.set_remote_id(dir_path, user, name="nxdirectedituser")

        if xpath:
            self.local.set_remote_id(dir_path, xpath, name="nxdirecteditxpath")

        self.local.set_remote_id(dir_path, blob.digest, name="nxdirecteditdigest")
        self.local.set_remote_id(
            dir_path,
            blob.digest_algorithm.encode("utf-8"),
            name="nxdirecteditdigestalgorithm",
        )
        self.local.set_remote_id(dir_path, filename, name="nxdirecteditname")

        safe_rename(tmp_file, file_path)

        timing = current_milli_time() - start_time
        self.openDocument.emit(filename, timing)
        return file_path

    @pyqtSlot(str, str, str, str)
    def edit(
        self,
        server_url: str,
        doc_id: str,
        user: Optional[str],
        download_url: Optional[str],
        /,
    ) -> None:
        if not Feature.direct_edit:
            self.directEditError.emit("DIRECT_EDIT_NOT_ENABLED", [])
            return

        log.info(
            f"Direct Editing {doc_id=} on {server_url=} for {user=} with {download_url=}"
        )
        try:
            # Download the file
            file_path = self._prepare_edit(
                server_url, doc_id, user=user, download_url=download_url
            )
            log.debug(f"Direct Edit preparation returned file path {file_path!r}")

            # Launch it
            if file_path:
                self._manager.open_local_file(file_path)
        except NoAssociatedSoftware as exc:
            self.directEditError.emit(
                "DIRECT_EDIT_NO_ASSOCIATED_SOFTWARE",
                [exc.filename, exc.mimetype],
            )
        except OSError as e:
            if e.errno != errno.EACCES:
                raise e
            # Open file anyway
            if e.filename is not None:
                self._manager.open_local_file(e.filename)

    # ------------------------------------------------------------------ queues / main loop

    def _handle_queues(self) -> None:
        """Process lock, error and upload queues.  Override to extend."""
        # Lock any document
        self._handle_lock_queue()

        # Unqueue any errors
        for item in self._error_queue.get():
            self._upload_queue.put(item.path)

        # Handle the upload queue
        self._handle_upload_queue()

    def _execute(self) -> None:
        """Main execution loop.  Override to customise the loop body."""
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
                    log.exception("Unhandled Direct Edit error")
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

    # ------------------------------------------------------------------ watchdog

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
    def handle_watchdog_event(self, evt: FileSystemEvent, /) -> None:
        """Handle a single file-system event.  Override for richer behaviour."""
        src_path = normalize_event_filename(evt.src_path)

        # Event on the folder by itself
        if src_path.is_dir():
            return

        if self.local.is_temp_file(src_path):
            return

        log.info(f"Handling watchdog event [{evt.event_type}] on {evt.src_path!r}")

        if evt.event_type == "moved":
            src_path = normalize_event_filename(evt.dest_path)

        ref = self._get_ref(src_path)
        dir_path = self.local.get_path(src_path.parent)
        name = self.local.get_remote_id(dir_path, name="nxdirecteditname")

        if not name:
            return

        editing = self.local.get_remote_id(dir_path, name="nxdirecteditlock") == "1"

        if force_decode(name) != src_path.name:
            if _is_lock_file(src_path.name):
                if not editing and evt.event_type == "created" and self.use_autolock:
                    # Recompute the path from 'dir/temp_file' -> 'dir/file'
                    _path = src_path.parent / name
                    self.autolock.set_autolock(_path, self)
                elif evt.event_type == "deleted":
                    # Free the xattr to let _cleanup() does its work
                    self.local.remove_remote_id(dir_path, name="nxdirecteditlock")
            return

        if not editing and self.use_autolock:
            self.autolock.set_autolock(src_path, self)

        if evt.event_type != "deleted":
            self._upload_queue.put(ref)

    def _get_ref(self, src_path: Path) -> Path:
        return self.local.get_path(src_path)
