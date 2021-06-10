import errno
import re
import shutil
from collections import defaultdict
from datetime import datetime
from logging import getLogger
from pathlib import Path
from queue import Empty, Queue
from threading import Lock
from time import sleep
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Pattern
from urllib.parse import quote

from nuxeo.exceptions import CorruptedFile, Forbidden, HTTPError, Unauthorized
from nuxeo.handlers.default import Uploader
from nuxeo.models import Blob
from requests import codes
from watchdog.events import FileSystemEvent
from watchdog.observers import Observer

from .client.local import LocalClient
from .client.remote_client import Remote
from .constants import APP_NAME, CONNECTION_ERROR, DOC_UID_REG, ROOT
from .engine.activity import tooltip
from .engine.blocklist_queue import BlocklistQueue
from .engine.watcher.local_watcher import DriveFSEventHandler
from .engine.workers import Worker
from .exceptions import (
    DocumentAlreadyLocked,
    NoAssociatedSoftware,
    NotFound,
    ThreadInterrupt,
)
from .feature import Feature
from .metrics.constants import (
    DE_CONFLICT_HIT,
    DE_ERROR_COUNT,
    DE_RECOVERY_HIT,
    DE_SAVE_COUNT,
)
from .objects import DirectEditDetails, Metrics, NuxeoDocumentInfo
from .options import Options
from .qt.imports import pyqtSignal, pyqtSlot
from .utils import (
    current_milli_time,
    force_decode,
    normalize_event_filename,
    safe_filename,
    safe_rename,
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

    # Microsoft Office, (Libre|Open)Office
    return name.startswith(("~$", ".~lock."))


class DirectEdit(Worker):
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
        self.use_autolock = self._manager.get_direct_edit_auto_lock()
        self._event_handler: Optional[DriveFSEventHandler] = None
        self._metrics = {"edit_files": 0}
        self._observer: Observer = None
        self.local = LocalClient(self._folder)
        self._upload_queue: Queue = Queue()
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

    def start(self) -> None:
        self._stop = False
        super().start()

    def stop(self) -> None:
        super().stop()
        self._stop = True

    def stop_client(self, uploader: Uploader, /) -> None:
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

    def _download(
        self,
        engine: "Engine",
        info: NuxeoDocumentInfo,
        file_path: Path,
        file_out: Path,
        blob: Blob,
        xpath: str,
        /,
        *,
        callback: Optional[Callable] = None,
        url: str = None,
    ) -> Optional[Path]:
        # Close to processor method - should try to refactor ?
        pair = None
        kwargs: Dict[str, Any] = {}

        if blob.digest:
            # The digest is available in the Blob, use it and disable parameters check
            # as 'digest' is not a recognized param for the Blob.Get operation.
            kwargs["digest"] = blob.digest
            kwargs["check_params"] = False

            pair = engine.dao.get_valid_duplicate_file(blob.digest)

        # Remove the eventual temporary file. We do not want to be able to resume an
        # old download because of several issues and does not make sens for that feature.
        # See NXDRIVE-2112 and NXDRIVE-2116 for more context.
        file_out.unlink(missing_ok=True)

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
                    for try_count in range(self._error_threshold):
                        try:
                            engine.remote.download(
                                quote(url, safe="/:"),
                                file_path,
                                file_out,
                                blob.digest,
                                callback=callback or self.stop_client,
                                is_direct_edit=True,
                                engine_uid=engine.uid,
                            )
                            break
                        except CorruptedFile:
                            self.directEditError.emit(
                                "DIRECT_EDIT_CORRUPTED_DOWNLOAD_RETRY", []
                            )

                            # Remove the faultive tmp file
                            file_out.unlink(missing_ok=True)

                            # Wait before the next try
                            delay = 5 * (try_count + 1)
                            sleep(delay)
                    else:
                        self.directEditError.emit(
                            "DIRECT_EDIT_CORRUPTED_DOWNLOAD_FAILURE", []
                        )
                        return None
                finally:
                    engine.dao.remove_transfer("download", path=file_path)
            else:
                engine.remote.get_blob(
                    info,
                    xpath=xpath,
                    file_out=file_out,
                    callback=self.stop_client,
                    **kwargs,
                )

        return file_out

    def _get_info(
        self, engine: "Engine", doc_id: str, /
    ) -> Optional[NuxeoDocumentInfo]:
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

        if not isinstance(doc, dict):
            err = "Cannot parse the server response: invalid data from the server"
            log.warning(err)
            values = [doc_id, engine.hostname]
            self.directEditError.emit("DIRECT_EDIT_BAD_RESPONSE", values)
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
        if info.is_proxy:
            self.directEditError.emit("DIRECT_EDIT_PROXY", [info.name])
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

    def _get_tmp_file(self, doc_id: str, filename: str, /) -> Path:
        """Return the temporary file that will be used to download contents.
        Using a method to help testing.
        """
        tmp_folder = self._folder / f"{doc_id}.dl"
        tmp_folder.mkdir(parents=True, exist_ok=True)
        return tmp_folder / filename

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

        # Avoid any link with the engine, remote_doc are not cached so we
        # can do that
        info = self._get_info(engine, doc_id)
        if not info:
            return None

        if not self.use_autolock:
            log.warning(
                "Server-side document locking is disabled: you are not protected against concurrent updates."
            )

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
        dir_path = self._folder / folder_name
        dir_path.mkdir(exist_ok=True)

        log.info(f"Editing {filename!r}")
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
        except HTTPError as exc:
            if exc.status == 404:
                self.directEditError[str, list, str].emit(
                    "DIRECT_EDIT_DOC_NOT_FOUND", [info.name], str(exc.message)
                )
                return None
            raise exc

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
            if e.errno == errno.EACCES:
                # Open file anyway
                if e.filename is not None:
                    self._manager.open_local_file(e.filename)
            else:
                raise e

    def _extract_edit_info(self, ref: Path, /) -> DirectEditDetails:
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

    def _lock(self, remote: Remote, uid: str, /) -> bool:
        """Lock a document."""
        try:
            remote.lock(uid)
        except HTTPError as exc:
            if exc.status in (codes.CONFLICT, codes.INTERNAL_SERVER_ERROR):
                # INTERNAL_SERVER_ERROR on old servers (<11.1, <2021.0) [missing NXP-24359]
                user = self._guess_user_from_http_error(exc.message)
                if user:
                    if user != remote.user_id:
                        raise DocumentAlreadyLocked(user)
                    log.debug("You already locked that document!")
                    return False
            raise exc

        # Document locked!
        return True

    def _unlock(self, remote: Remote, uid: str, ref: Path, /) -> bool:
        """Unlock a document. Return True if purge is needed."""
        try:
            remote.unlock(uid, headers=self._file_metrics.pop(ref, {}))
        except NotFound:
            return True
        except HTTPError as exc:
            if exc.status in (codes.CONFLICT, codes.INTERNAL_SERVER_ERROR):
                # INTERNAL_SERVER_ERROR on old servers (< 7.10)
                user = self._guess_user_from_http_error(exc.message)
                if user:
                    log.warning(f"Skipping document unlock as it's locked by {user!r}")
                    return True
            raise exc

        # Document unlocked! No need to purge.
        return False

    def _handle_lock_queue(self) -> None:
        errors = []

        while "items":
            try:
                item = self._lock_queue.get_nowait()
            except Empty:
                break

            ref, action = item
            log.debug(f"Handling Direct Edit lock queue: action={action}, ref={ref!r}")
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

                purge = self._unlock(remote, uid, ref)

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
            except Forbidden:
                log.warning(
                    f"Document {ref!r} cannot be locked for {details.engine.remote_user!r}",
                    exc_info=True,
                )
                self.directEditLockError.emit(action, ref.name, uid)
            except CONNECTION_ERROR:
                # Try again in 30s
                log.warning(
                    f"Connection error while trying to {action} document {ref!r}",
                    exc_info=True,
                )
                errors.append(item)
            except HTTPError as exc:
                if exc.status not in (502, 503, 504):
                    raise
                # Try again in 30s
                log.warning(
                    f"Server error while trying to {action} document {ref!r}",
                    exc_info=True,
                )
                errors.append(item)
            except Exception:
                log.exception(f"Cannot {action} document {ref!r}")
                self.directEditLockError.emit(action, ref.name, uid)

        # Requeue errors
        for item in errors:
            self._lock_queue.put(item)

    def _send_lock_status(self, ref: str, /) -> None:
        manager = self._manager
        for engine in manager.engines.copy().values():
            dao = engine.dao
            state = dao.get_normal_state_from_remote(ref)
            if state:
                path = engine.local_folder / state.local_path
                manager.osi.send_sync_status(state, path)

    def _handle_upload_queue(self) -> None:
        while "items":
            try:
                ref: Path = self._upload_queue.get_nowait()
            except Empty:
                break

            os_path = self.local.abspath(ref)

            if os_path.is_dir():
                # The upload file is a folder?!
                # It *may* happen when the user Direct Edit'ed a ZIP file,
                # the OS opened it and automatically decompressed it in-place.
                log.debug(f"Skipping Direct Edit queue ref {ref!r} (folder)")
                continue

            log.debug(f"Handling Direct Edit queue ref: {ref!r}")

            details = self._extract_edit_info(ref)
            xpath = details.xpath
            engine = details.engine
            remote = engine.remote

            if not xpath:
                xpath = "file:content"
                log.info(
                    f"Direct Edit on {ref!r} has no xpath, defaulting to {xpath!r}"
                )

            try:
                # Don't update if digest are the same
                info = self.local.get_info(ref)
                current_digest = info.get_digest(digest_func=details.digest_func)
                if current_digest == details.digest:
                    continue

                start_time = current_milli_time()
                log.debug(
                    f"Local digest {current_digest!r} is different from the recorded "
                    f"one {details.digest!r} - modification detected for {ref!r}"
                )

                if not details.editing:
                    # Check the remote hash to prevent data loss
                    remote_info = remote.get_info(details.uid)
                    if remote_info.is_version:
                        log.warning(
                            f"Unable to process Direct Edit on {remote_info.name} "
                            f"({details.uid}) because it is a version."
                        )
                        continue

                    if remote_info.is_proxy:
                        log.warning(
                            f"Unable to process Direct Edit on {remote_info.name} "
                            f"({details.uid}) because it is a proxy."
                        )
                        continue

                    remote_blob = remote_info.get_blob(xpath) if remote_info else None
                    log.debug(f"Got remote blob {remote_blob!r}")
                    if (
                        remote_blob
                        and remote_blob.digest
                        and remote_blob.digest_algorithm
                        and remote_blob.digest != details.digest
                    ):
                        log.debug(
                            f"Remote digest {remote_blob.digest!r} is different from the "
                            f"recorded one {details.digest!r} - conflict detected for {ref!r}"
                        )
                        self.directEditConflict.emit(ref.name, ref, remote_blob.digest)
                        remote.metrics.send({DE_CONFLICT_HIT: 1})
                        continue

                log.info(f"Uploading file {os_path!r}")

                kwargs: Dict[str, Any] = {}
                if xpath == "note:note":
                    cmd = "NuxeoDrive.AttachBlob"
                else:
                    kwargs["xpath"] = xpath
                    kwargs["void_op"] = True
                    cmd = "Blob.AttachOnDocument"

                remote.upload(
                    os_path,
                    command=cmd,
                    document=remote.check_ref(details.uid),
                    engine_uid=engine.uid,
                    is_direct_edit=True,
                    **kwargs,
                )

                # The file is in the upload queue but not in the dict if it is pushed by the recovery system.
                if ref not in self._file_metrics:
                    remote.metrics.send({DE_RECOVERY_HIT: 1})

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
                self._handle_upload_error(ref, os_path, remote)
            except HTTPError as e:
                if e.status == 500 and "Cannot set property on a version" in e.message:
                    log.warning(
                        f"Unable to process Direct Edit on {ref} "
                        f"({details}) because it is a version."
                    )
                elif e.status == 413:  # Request Entity Too Large
                    log.warning(
                        f"Unable to process Direct Edit on {ref} "
                        f"({details}) because it is a proxy."
                    )
                elif e.status in (502, 503, 504):
                    log.warning(
                        f"Unable to process Direct Edit on {ref} "
                        f"({details}) because server is unavailable."
                    )
                    self._handle_upload_error(ref, os_path, remote)
                else:
                    # Try again in 30s
                    log.exception(f"Direct Edit unhandled HTTP error for ref {ref!r}")
                    self._handle_upload_error(ref, os_path, remote)
            except Exception:
                # Try again in 30s
                log.exception(f"Direct Edit unhandled error for ref {ref!r}")
                self._handle_upload_error(ref, os_path, remote)

    def _handle_upload_error(self, ref: Path, os_path: Path, remote: Remote, /) -> None:
        """Retry the upload if the number of attempts is below *._error_threshold* else discard it."""
        if ref not in self._file_metrics:
            self._file_metrics[ref] = defaultdict(int)
        self._file_metrics[ref][DE_ERROR_COUNT] += 1

        self._upload_errors[ref] += 1
        if self._upload_errors[ref] < self._error_threshold:
            self._error_queue.push(ref)
            return

        log.error(f"Upload queue: too many failures for {ref!r}, skipping it!")
        self.directEditError.emit(
            "DIRECT_EDIT_UPLOAD_FAILED",
            [f'<a href="file:///{os_path.parent}">{ref.name}</a>'],
        )
        remote.metrics.send(self._file_metrics.pop(ref, {}))
        self._upload_errors.pop(ref, None)

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
                    log.exception("Unhandled Direct Edit error")
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
    def handle_watchdog_event(self, evt: FileSystemEvent, /) -> None:
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
            self._file_metrics[ref][DE_SAVE_COUNT] += 1

    def _get_ref(self, src_path: Path) -> Path:
        ref = self.local.get_path(src_path)
        if ref not in self._file_metrics:
            self._file_metrics[ref] = defaultdict(int)
        return ref
