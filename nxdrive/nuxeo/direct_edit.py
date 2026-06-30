"""Nuxeo-specific Direct Edit implementation.

Inherits generic infrastructure from ``nxdrive.drive.direct_edit.DirectEdit``
and adds Nuxeo server operations (locking, blob download/upload, etc.).
"""

import shutil
from collections import defaultdict
from logging import getLogger
from pathlib import Path
from queue import Empty
from time import sleep
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional
from urllib.parse import quote

from nuxeo.exceptions import CorruptedFile, Forbidden, HTTPError, Unauthorized
from nuxeo.handlers.default import Uploader
from nuxeo.models import Blob
from requests import codes
from watchdog.observers import Observer

from nxdrive.drive.constants import CONNECTION_ERROR
from nxdrive.drive.direct_edit import DirectEdit as _DirectEditBase
from nxdrive.drive.direct_edit import DriveFSEventHandler
from nxdrive.drive.direct_edit import _is_lock_file
from nxdrive.drive.engine.activity import tooltip
from nxdrive.drive.exceptions import DocumentAlreadyLocked, NotFound, ThreadInterrupt
from nxdrive.drive.feature import Feature
from nxdrive.drive.metrics.constants import (
    DE_CONFLICT_HIT,
    DE_ERROR_COUNT,
    DE_RECOVERY_HIT,
    DE_SAVE_COUNT,
)
from nxdrive.drive.utils import (
    current_milli_time,
    force_decode,
    normalize_event_filename,
    unset_path_readonly,
)
from nxdrive.nuxeo.client.remote_client import Remote
from nxdrive.nuxeo.objects import NuxeoDocumentInfo

if TYPE_CHECKING:
    from nxdrive.drive.manager import Manager  # noqa
    from nxdrive.nuxeo.engine.engine import Engine  # noqa

__all__ = ("DirectEdit",)

log = getLogger(__name__)


class DirectEdit(_DirectEditBase):
    """Nuxeo-specific Direct Edit.

    Inherits all generic infrastructure from
    ``nxdrive.drive.direct_edit.DirectEdit`` and overrides only the
    server-specific operations.
    """

    # ------------------------------------------------------------------ Nuxeo overrides

    def stop_client(self, uploader: Uploader, /) -> None:
        if self._stop:
            raise ThreadInterrupt()

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
            if not self.use_autolock:
                log.warning(
                    "Server-side document locking is disabled: you are not protected against concurrent updates."
                )
                doc = engine.remote.fetch(
                    doc_id,
                    headers={"fetch-document": "lock"},
                    enrichers=["permissions"],
                )
            else:
                doc = engine.remote.lock(doc_id)
                self.is_already_locked = True

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
        """Override to add Nuxeo-specific HTTPError handling."""
        try:
            return super()._prepare_edit(
                server_url,
                doc_id,
                user=user,
                download_url=download_url,
                callback=callback,
            )
        except HTTPError as exc:
            if exc.status == 404:
                info_name = doc_id
                engine = self._get_engine(server_url, doc_id=doc_id, user=user)
                if engine:
                    info = self._get_info(engine, doc_id)
                    if info:
                        info_name = info.name
                self.directEditError[str, list, str].emit(
                    "DIRECT_EDIT_DOC_NOT_FOUND", [info_name], str(exc.message)
                )
                return None
            raise exc

    @tooltip("Setup watchdog")
    def _setup_watchdog(self) -> None:
        """Nuxeo override for backward-compatible monkeypatch targets."""
        log.info(f"Watching FS modification on {self._folder!r}")
        self._event_handler = DriveFSEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(self._event_handler, str(self._folder), recursive=True)
        self._observer.start()

    def _lock(self, remote: Remote, uid: str, ref: Any = None, /) -> Any:
        """Lock a document."""
        data = None
        try:
            if self.is_already_locked:
                self.is_already_locked = False
            else:
                data = remote.lock(uid)
                if ref:
                    self.send_notification(ref)
        except HTTPError as exc:
            if exc.status in (codes.CONFLICT, codes.INTERNAL_SERVER_ERROR):
                # INTERNAL_SERVER_ERROR on old servers (<11.1, <2021.0) [missing NXP-24359]
                if user := self._guess_user_from_http_error(exc.message):
                    if user != remote.user_id:
                        raise DocumentAlreadyLocked(user)
                    log.debug("You already locked that document!")
                    return
            raise exc

        # Document locked!
        return data

    def _unlock(self, remote: Remote, uid: str, ref: Path, /) -> bool:
        """Unlock a document. Return True if purge is needed."""
        try:
            remote.unlock(uid, headers=self._file_metrics.pop(ref, {}))
        except NotFound:
            return True
        except HTTPError as exc:
            if exc.status in (codes.CONFLICT, codes.INTERNAL_SERVER_ERROR):
                # INTERNAL_SERVER_ERROR on old servers (< 7.10)
                if user := self._guess_user_from_http_error(exc.message):
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
                    self.local.set_remote_id(ref.parent, b"1", name="nxdirecteditlock")
                    if self.use_autolock:
                        self._lock(remote, uid, ref)
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
        super()._handle_queues()

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

    @tooltip("Handle watchdog event")
    def handle_watchdog_event(self, evt: Any, /) -> None:
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

        if not editing and self.use_autolock:
            self.autolock.set_autolock(src_path, self)

        if evt.event_type != "deleted":
            self._upload_queue.put(ref)
            self._file_metrics[ref][DE_SAVE_COUNT] += 1

    def _get_ref(self, src_path: Path) -> Path:
        ref = self.local.get_path(src_path)
        if ref not in self._file_metrics:
            self._file_metrics[ref] = defaultdict(int)
        return ref
