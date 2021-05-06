import errno
import shutil
import sqlite3
import sys
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from threading import Lock
from time import monotonic_ns, sleep
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from nuxeo.exceptions import (
    Conflict,
    CorruptedFile,
    Forbidden,
    HTTPError,
    OngoingRequestError,
    Unauthorized,
    UploadError,
)
from urllib3.exceptions import MaxRetryError

from ..behavior import Behavior
from ..client.local import FileInfo
from ..client.uploader.direct_transfer import DirectTransferUploader
from ..constants import (
    CONNECTION_ERROR,
    LONG_FILE_ERRORS,
    MAC,
    NO_SPACE_ERRORS,
    UNACCESSIBLE_HASH,
    WINDOWS,
    DigestStatus,
    TransferStatus,
)
from ..exceptions import (
    DownloadPaused,
    DuplicationDisabledError,
    NotFound,
    PairInterrupt,
    ParentNotSynced,
    ThreadInterrupt,
    UnknownDigest,
    UploadCancelled,
    UploadPaused,
)
from ..objects import DocPair, RemoteFileInfo
from ..qt.imports import pyqtSignal
from ..utils import (
    digest_status,
    is_generated_tmp_file,
    lock_path,
    safe_filename,
    unlock_path,
)
from .workers import EngineWorker

if TYPE_CHECKING:
    from .engine import Engine  # noqa

__all__ = ("Processor",)

log = getLogger(__name__)


class Processor(EngineWorker):
    pairSyncStarted = pyqtSignal(object)
    pairSyncEnded = pyqtSignal(object)
    path_locker = Lock()
    soft_locks: Dict[str, Dict[Path, bool]] = {}
    readonly_locks: Dict[str, Dict[Path, List[int]]] = {}
    readonly_locker = Lock()

    def __init__(self, engine: "Engine", item_getter: Callable, /) -> None:
        super().__init__(engine, engine.dao, "Processor")
        self._get_item = item_getter
        self.engine = engine
        self.local = self.engine.local
        self.remote = self.engine.remote
        self._current_doc_pair: Optional[DocPair] = None
        self._current_metrics: Dict[str, Any] = {}

    def _unlock_soft_path(self, path: Path, /) -> None:
        log.debug(f"Soft unlocking {path!r}")
        path = Path(str(path).lower())
        with Processor.path_locker:
            if self.engine.uid not in Processor.soft_locks:
                Processor.soft_locks[self.engine.uid] = {}
            else:
                Processor.soft_locks[self.engine.uid].pop(path, None)

    def _unlock_readonly(self, path: Path, /) -> None:
        with Processor.readonly_locker:
            if self.engine.uid not in Processor.readonly_locks:
                Processor.readonly_locks[self.engine.uid] = {}

            if path in Processor.readonly_locks[self.engine.uid]:
                log.debug(f"Readonly unlock: increase count on {path!r}")
                Processor.readonly_locks[self.engine.uid][path][0] += 1
            else:
                lock = self.local.unlock_ref(path)
                log.debug(f"Readonly unlock: unlock on {path!r} with {lock}")
                Processor.readonly_locks[self.engine.uid][path] = [1, lock]

    def _lock_readonly(self, path: Path, /) -> None:
        with Processor.readonly_locker:
            if self.engine.uid not in Processor.readonly_locks:
                Processor.readonly_locks[self.engine.uid] = {}

            if path not in Processor.readonly_locks[self.engine.uid]:
                log.info(f"Readonly lock: cannot find reference on {path!r}")
                return

            Processor.readonly_locks[self.engine.uid][path][0] -= 1
            idx, lock = Processor.readonly_locks[self.engine.uid][path]

            log.debug(f"Readonly lock: update lock count on {path!r} to {idx}")

            if idx <= 0:
                self.local.lock_ref(path, lock)
                log.debug(f"Readonly lock: relocked {path!r} with {lock}")
                del Processor.readonly_locks[self.engine.uid][path]

    def _lock_soft_path(self, path: Path, /) -> Path:
        log.debug(f"Soft locking {path!r}")
        path = Path(str(path).lower())
        with Processor.path_locker:
            if self.engine.uid not in Processor.soft_locks:
                Processor.soft_locks[self.engine.uid] = {}
            if path in Processor.soft_locks[self.engine.uid]:
                raise PairInterrupt
            Processor.soft_locks[self.engine.uid][path] = True
            return path

    def get_current_pair(self) -> Optional[DocPair]:
        return self._current_doc_pair

    @staticmethod
    def check_pair_state(doc_pair: DocPair, /) -> bool:
        """Eliminate unprocessable states."""
        return all(
            (
                doc_pair.pair_state not in ("synchronized", "unsynchronized"),
                not doc_pair.pair_state.startswith("parent_"),
                doc_pair.remote_state != "todo",  # Specific to Direct Transfer
            )
        )

    @staticmethod
    def _digest_status(doc_pair: DocPair) -> DigestStatus:
        """Get the digest status of the given *doc_pair*."""
        if doc_pair.folderish or doc_pair.pair_state != "remotely_created":
            return DigestStatus.OK
        return digest_status(doc_pair.remote_digest)

    def _handle_doc_pair_sync(self, doc_pair: DocPair, sync_handler: Callable) -> None:
        """Actions to be done to handle a synchronization item. Called by ._execute()."""

        status = self._digest_status(doc_pair)
        if status is not DigestStatus.OK:
            # Ignoring the document, it will still be present in the database.
            # A future Audit event may resolve its state.
            log.info(f"Skip non-standard remote digest {doc_pair.remote_digest!r}")
            self.dao.unsynchronize_state(doc_pair, status.name)
            return

        self.engine.manager.osi.send_sync_status(
            doc_pair, self.local.abspath(doc_pair.local_path)
        )

        if MAC:
            finder_info = self.local.get_remote_id(
                doc_pair.local_path, name="com.apple.FinderInfo"
            )
            if finder_info and "brokMACS" in finder_info:
                log.debug("Skip as pair is in use by Finder")
                self._postpone_pair(doc_pair, "Finder using file", interval=3)
                return

        # TODO Update as the server don't take hash to avoid conflict yet
        if doc_pair.pair_state.startswith("locally") and doc_pair.remote_ref:
            try:
                remote_info = self.remote.get_fs_info(doc_pair.remote_ref)
                if (
                    remote_info.digest != doc_pair.remote_digest
                    and doc_pair.remote_digest is not None
                ):
                    doc_pair.remote_state = "modified"
                elif doc_pair.folderish and remote_info.name != doc_pair.remote_name:
                    doc_pair.remote_state = "moved"
                self._refresh_remote(doc_pair, remote_info)

                # Can run into conflict
                if doc_pair.pair_state == "conflicted":
                    return

                refreshed = self.dao.get_state_from_id(doc_pair.id)
                if not (refreshed and self.check_pair_state(refreshed)):
                    return
                doc_pair = refreshed or doc_pair
            except NotFound:
                doc_pair.remote_ref = ""

        # NXDRIVE-842: parent is in disabled duplication error
        parent_pair = self._get_normal_state_from_remote_ref(doc_pair.remote_parent_ref)
        if parent_pair and parent_pair.last_error == "DEDUP":
            return

        parent_path = doc_pair.local_parent_path

        if not self.local.exists(parent_path):
            if not parent_pair or doc_pair.local_parent_path == parent_pair.local_path:
                self.dao.remove_state(doc_pair)
                return

            # The parent folder has been renamed sooner
            # in the current synchronization
            doc_pair.local_parent_path = parent_pair.local_path

        # Skip downloads in process
        download = self.engine.dao.get_download(doc_pair=doc_pair.id)
        if download and download.status not in (
            TransferStatus.ONGOING,
            TransferStatus.DONE,
        ):
            log.info(f"Download is paused for {doc_pair!r}")
            return

        # Skip uploads in process
        upload = self.engine.dao.get_upload(doc_pair=doc_pair.id)
        if upload and upload.status not in (
            TransferStatus.ONGOING,
            TransferStatus.DONE,
        ):
            log.info(f"Upload is paused for {doc_pair!r}")
            return

        self.pairSyncStarted.emit(self._current_metrics)
        soft_lock = self._lock_soft_path(doc_pair.local_path)
        log.debug(f"Calling {sync_handler.__name__}()")
        try:
            sync_handler(doc_pair)
        finally:
            self._unlock_soft_path(soft_lock)

        pair = self.dao.get_state_from_id(doc_pair.id)
        if pair and "deleted" not in pair.pair_state:
            self.engine.manager.osi.send_sync_status(
                pair, self.local.abspath(pair.local_path)
            )

        self.pairSyncEnded.emit(self._current_metrics)

    def _handle_doc_pair_dt(self, doc_pair: DocPair, sync_handler: Callable) -> None:
        """Actions to be done to handle a Direct Transfer item. Called by ._execute()."""
        log.debug(f"Calling {sync_handler.__name__}()")
        try:
            sync_handler(doc_pair)
        except NotFound:
            # It means the FileManager did not find the batchId, meaning it is being (or was already) processed.
            # No need to upload it again, the document should already be created on will be "shortly".
            self._direct_transfer_cancel(doc_pair)
            raise
        except HTTPError as exc:
            if exc.status != 404:
                raise
            self._postpone_pair(doc_pair, "Parent not yet synced")
        except UploadCancelled as exc:
            # Triggered when an Upload status change from ONGOING to CANCELLED while being processed.
            upload = self.engine.dao.get_dt_upload(uid=exc.transfer_id)
            if not upload or not upload.doc_pair:
                return
            self.remote.cancel_batch(upload.batch)
            refreshed_doc_pair = self.engine.dao.get_state_from_id(upload.doc_pair)
            if not refreshed_doc_pair:
                return
            self._direct_transfer_cancel(refreshed_doc_pair)
            log.debug(f"Cancelled upload {exc.transfer_id!r}")
        except UploadPaused:
            raise
        except RuntimeError:
            raise
        except Exception:
            # Show a notification on error
            file = doc_pair.local_path if WINDOWS else Path(f"/{doc_pair.local_path}")
            self.engine.directTranferError.emit(file)
            raise

    def _get_next_doc_pair(self, item: DocPair) -> Optional[DocPair]:
        """Get the *doc_pair* to handle from the database."""
        try:
            return self.dao.acquire_state(self.thread_id, item.id)
        except sqlite3.OperationalError:
            state = self.dao.get_state_from_id(item.id)
            if state:
                if (
                    WINDOWS
                    and state.pair_state == "locally_moved"
                    and not state.remote_can_rename
                ):
                    log.info(
                        "A local rename on a read-only folder is allowed "
                        " on Windows, but it should not. Skipping."
                    )
                else:
                    log.debug(f"Cannot acquire state for item {item!r} ({state!r})")
                    self._postpone_pair(item, "Pair in use", interval=3)
        return None

    def _execute(self) -> None:
        while "There are items in the queue":
            item = self._get_item()
            if not item:
                break

            doc_pair = self._get_next_doc_pair(item)
            if not doc_pair:
                log.debug(f"Did not acquire state, dropping {item!r}")
                self._current_doc_pair = None
                continue
            self._current_doc_pair = doc_pair

            handler_name = f"_synchronize_{doc_pair.pair_state}"
            sync_handler = getattr(self, handler_name, None)
            try:
                if not self.check_pair_state(doc_pair):
                    log.debug(f"Skip non-processable {doc_pair!r}")
                    self.remove_void_transfers(doc_pair)
                    continue

                log.info(f"Executing processor on {doc_pair!r}({doc_pair.version})")
                if not sync_handler:
                    log.info(f"Unhandled {doc_pair.pair_state=}")
                    self.increase_error(doc_pair, "ILLEGAL_STATE")
                    continue

                self._current_metrics = {
                    "handler": doc_pair.pair_state,
                    "start_ns": monotonic_ns(),
                }

                if doc_pair.local_state == "direct":
                    self._handle_doc_pair_dt(doc_pair, sync_handler)
                else:
                    self._handle_doc_pair_sync(doc_pair, sync_handler)
            except ThreadInterrupt:
                self.engine.queue_manager.push(doc_pair)
                raise
            except NotFound:
                log.warning("The document or its parent does not exist anymore")
                self.remove_void_transfers(doc_pair)
            except Unauthorized:
                self.giveup_error(doc_pair, "INVALID_CREDENTIALS")
            except Forbidden:
                log.warning(
                    f"Access to the document {doc_pair.remote_ref!r} on server {self.engine.hostname!r}"
                    f" is forbidden for user {self.engine.remote_user!r}"
                )
            except (PairInterrupt, ParentNotSynced) as exc:
                log.info(f"{type(exc).__name__}, wait 1s and requeue")
                sleep(1)
                self.engine.queue_manager.push(doc_pair)
            except CONNECTION_ERROR:
                # TODO:
                #  Add detection for server unavailability to stop all sync
                #  instead of putting files in error
                log.debug("Connection issue", exc_info=True)
                self._postpone_pair(doc_pair, "CONNECTION_ERROR")
            except MaxRetryError:
                log.warning("Connection retries issue", exc_info=True)
                self._postpone_pair(doc_pair, "MAX_RETRY_ERROR")
            except OngoingRequestError as exc:
                # The idempotent request is being processed, just recheck later
                log.info(exc)
                self._postpone_pair(doc_pair, "OngoingRequest", exception=exc)
            except Conflict:
                # It could happen on multiple files drag'n drop
                # starting with identical characters.
                log.warning("Delaying conflicted document")
                self._postpone_pair(doc_pair, "Conflict")
            except HTTPError as exc:
                if exc.status == 404:
                    # We saw it happened once a migration is done.
                    # Nuxeo kept the document reference but it does
                    # not exist physically anywhere.
                    log.info("The document does not exist anymore")
                    self.dao.remove_state(doc_pair)
                elif exc.status == 416:
                    log.warning("Invalid downloaded temporary file")
                    tmp_folder = (
                        self.engine.download_dir / doc_pair.remote_ref.split("#")[-1]
                    )
                    with suppress(FileNotFoundError):
                        shutil.rmtree(tmp_folder)
                    self._postpone_pair(doc_pair, "Requested Range Not Satisfiable")
                elif exc.status in (405, 408, 500):
                    self.increase_error(doc_pair, "SERVER_ERROR", exception=exc)
                elif exc.status in (502, 503, 504):
                    log.warning("Server is unavailable", exc_info=True)
                    self._check_exists_on_the_server(doc_pair)
                else:
                    error = f"{handler_name}_http_error_{exc.status}"
                    self._handle_pair_handler_exception(doc_pair, error, exc)
            except UploadError as exc:
                exc_info = True
                if "ExpiredToken" in exc.info:
                    # It happens to non-chunked uploads, it is safe to restart the upload completely
                    log.debug("AWS credentials are exprired for a non-chunked upload")
                    self.dao.remove_transfer(
                        "upload",
                        doc_pair=doc_pair.id,
                        is_direct_transfer=doc_pair.local_state == "direct",
                    )
                    exc_info = False
                log.warning(
                    f"Delaying failed upload of {exc.name!r} (error: {exc.info})",
                    exc_info=exc_info,
                )
                self._postpone_pair(doc_pair, "Upload")
            except (DownloadPaused, UploadPaused) as exc:
                nature = "download" if isinstance(exc, DownloadPaused) else "upload"
                log.info(f"Pausing {nature} {exc.transfer_id!r}")
                self.engine.dao.set_transfer_doc(
                    nature, exc.transfer_id, self.engine.uid, doc_pair.id
                )
            except DuplicationDisabledError:
                self.giveup_error(doc_pair, "DEDUP")
            except CorruptedFile as exc:
                self.increase_error(doc_pair, "CORRUPT", exception=exc)
            except UnknownDigest as exc:
                # This happens when locally creating a file and the server has async blob digest computation.
                # Ignoring the document, it will still be present in the database.
                # A future Audit event may resolve its state.
                log.info(
                    "Putting the document in the ignore list as it has a "
                    f"non-standard remote digest {exc.digest!r}"
                )
                status = DigestStatus.REMOTE_HASH_ASYNC
                self.dao.unsynchronize_state(doc_pair, status.name)
            except PermissionError:
                """
                WindowsError: [Error 32] The process cannot access the
                file because it is being used by another process
                """
                log.info(
                    "Document used by another software, delaying "
                    f"action({doc_pair.pair_state}) "
                    f"on {doc_pair.local_path!r}, ref={doc_pair.remote_ref!r}"
                )
                self.engine.errorOpenedFile.emit(doc_pair)
                self._postpone_pair(doc_pair, "Used by another process")
            except OSError as exc:
                # Try to handle different kind of Windows error
                error = getattr(exc, "winerror", exc.errno)
                if error in (errno.ENOENT, errno.ESRCH):
                    """
                    ENOENT: No such file or directory
                    ESRCH: No such process (The system cannot find the file specified, on Windows)
                    """
                    log.info("The document does not exist anymore locally")
                    self.dao.remove_state(doc_pair)
                elif error in LONG_FILE_ERRORS:
                    self.dao.remove_filter(
                        doc_pair.remote_parent_path + "/" + doc_pair.remote_ref
                    )
                    self.engine.longPathError.emit(doc_pair)
                elif hasattr(exc, "trash_issue"):
                    """
                    Special value to handle trash issues from filters on
                    Windows when there is one or more files opened by
                    another software blocking any action.
                    """
                    self.engine.errorOpenedFile.emit(doc_pair)
                    self._postpone_pair(doc_pair, "Trashing not possible")
                else:
                    self._handle_pair_handler_exception(doc_pair, handler_name, exc)
            except RuntimeError as exc:
                if "but the refreshed credentials are still expired" in str(exc):
                    log.warning(
                        "AWS credentials were refreshed, but the refreshed credentials are still expired"
                    )
                    log.info("Reinitializing the upload")
                    self.dao.remove_transfer(
                        "upload",
                        doc_pair=doc_pair.id,
                        is_direct_transfer=doc_pair.local_state == "direct",
                    )
                else:
                    raise
            except Exception as exc:
                # Workaround to forward unhandled exceptions to sys.excepthook between all Qthreads
                sys.excepthook(*sys.exc_info())
                self._handle_pair_handler_exception(doc_pair, handler_name, exc)
            finally:
                self.dao.release_state(self.thread_id)

            self._interact()

    def _check_exists_on_the_server(self, doc_pair: DocPair, /) -> None:
        """Used when the server is not available to do specific actions.
        Note that this check is not yet handled for Direct Transfer.
        """
        if doc_pair.pair_state != "locally_created":
            # Simply retry later
            self._postpone_pair(doc_pair, "Server unavailable")
            return

        # As seen with NXDRIVE-1753, an uploaded file may have worked
        # but for some reason the final state is in error. So, let's
        # check if the document is present on the server to bypass
        # (infinite|useless) retries.
        # Note: this is ugly as there are hardcoded values, maybe need to review that.
        local_path = str(doc_pair.local_path)
        if WINDOWS:
            local_path = local_path.replace("\\", "/")
        path = f"/default-domain/workspaces/{local_path}"
        try:
            fs_item = self.remote.fetch(path)
        except Exception:
            pass
        else:
            log.debug("The document has already been uploaded to the server")

            # Fetch the remote item to update the local pair details
            doc_pair.remote_ref = (
                f"defaultFileSystemItemFactory#default#{fs_item['uid']}"
            )
            remote_info = self.remote.get_fs_info(doc_pair.remote_ref)
            paths = remote_info.path.partition("/defaultFileSystemItemFactory")
            doc_pair.remote_parent_path = paths[0]
            self._refresh_remote(doc_pair, remote_info)

            # Set the synced states and remote name
            doc_pair.remote_name = remote_info.name
            self.dao.synchronize_state(doc_pair)
            self.dao.update_last_transfer(doc_pair.id, "upload")
            self.dao.update_remote_name(doc_pair.id, remote_info.name)

            # Transfer is completed, delete the upload from the database
            self.remove_void_transfers(doc_pair)

            # Trigger a refresh of the systray menu
            self.pairSyncEnded.emit(self._current_metrics)

    def _handle_pair_handler_exception(
        self, doc_pair: DocPair, handler_name: str, e: Exception, /
    ) -> None:
        if isinstance(e, OSError) and e.errno in NO_SPACE_ERRORS:
            self.engine.suspend()
            log.warning("No space left on device!", exc_info=True)
            self.increase_error(doc_pair, "NO_SPACE_LEFT_ON_DEVICE")
            self.engine.noSpaceLeftOnDevice.emit()
        else:
            log.exception("Unknown error")
            self.increase_error(doc_pair, f"SYNC_HANDLER_{handler_name}", exception=e)

    def _synchronize_direct_transfer(self, doc_pair: DocPair, /) -> None:
        """Direct Transfer of a local path."""
        session = self.dao.get_session(doc_pair.session)
        if session and session.status is TransferStatus.PAUSED:
            # No need to repush the *doc_pair* into the queue, it will be handled when resuming the session
            log.debug(f"The session is paused, skipping <DocPair[{doc_pair.id}]>")
            return

        if WINDOWS:
            path = doc_pair.local_path
        else:
            # The path retrieved from the database will have its starting slash trimmed, restore it
            path = Path(f"/{doc_pair.local_path}")

        if not path.exists():
            log.warning(
                f"Cancelling Direct Transfer of {path!r} because it does not exist anymore"
            )
            self._direct_transfer_cancel(doc_pair)
            self.engine.directTranferError.emit(path)
            return

        # Do the upload
        self.remote.upload(
            path,
            engine_uid=self.engine.uid,
            uploader=DirectTransferUploader,
            doc_pair=doc_pair,
        )

        self._direct_transfer_end(doc_pair, False)

    def _direct_transfer_cancel(self, doc_pair: DocPair, /) -> None:
        """Actions to do to cancel a Direct Transfer."""
        self._direct_transfer_end(doc_pair, True, recursive=True)

    def _direct_transfer_end(
        self,
        doc_pair: DocPair,
        cancelled_transfer: bool,
        /,
        *,
        recursive: bool = False,
    ) -> None:
        """Actions to do to at the end of a Direct Transfer."""

        # Transfer is completed, delete the upload from the database
        self.dao.remove_transfer(
            "upload", doc_pair=doc_pair.id, is_direct_transfer=True
        )

        # Clean-up
        self.dao.remove_state(doc_pair, recursive=recursive)

        # Update session then handle the status
        session = self.dao.get_session(doc_pair.session)
        if session:
            if (
                not cancelled_transfer
                and session.status is not TransferStatus.CANCELLED
            ):
                session = self.dao.update_session(doc_pair.session)
            elif cancelled_transfer:
                session = self.dao.decrease_session_counts(doc_pair.session)
            self.engine.handle_session_status(session)

        # For analytics
        self.engine.manager.directTransferStats.emit(doc_pair.folderish, doc_pair.size)

    def _synchronize_conflicted(self, doc_pair: DocPair, /) -> None:
        if doc_pair.local_state == "moved" and doc_pair.remote_state in (
            "moved",
            "unknown",
        ):
            # Manual conflict resolution needed
            self.dao.set_conflict_state(doc_pair)

        # Auto-resolve conflict
        elif not doc_pair.folderish:
            if self.local.is_equal_digests(
                doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path
            ):
                log.info("Auto-resolve conflict as digests are the same")
                self.dao.synchronize_state(doc_pair)
        elif self.local.get_remote_id(doc_pair.local_path) == doc_pair.remote_ref:
            log.info("Auto-resolve conflict as folder has same remote UID")
            self.dao.synchronize_state(doc_pair)

    def _synchronize_if_not_remotely_dirty(
        self, doc_pair: DocPair, /, *, remote_info: RemoteFileInfo = None
    ) -> None:
        if remote_info is not None and (
            remote_info.name != doc_pair.local_name
            or remote_info.digest != doc_pair.local_digest
        ):
            modified = self.dao.get_state_from_local(doc_pair.local_path)
            if modified:
                log.info(
                    f"Forcing remotely_modified for pair={modified!r} "
                    f"with info={remote_info!r}"
                )
                self._synchronize_remotely_modified(modified)
            return

        # Force computation of local digest to catch local modifications
        dynamic_states = False
        if not (
            doc_pair.folderish
            or self.local.is_equal_digests(
                None, doc_pair.remote_digest, doc_pair.local_path
            )
        ):
            # Note: set 1st argument of is_equal_digests() to None
            # to force digest computation
            try:
                info = self.local.get_info(doc_pair.local_path)
            except NotFound:
                doc_pair.local_state = "created"
                dynamic_states = True
            else:
                doc_pair.local_digest = info.get_digest()
                if doc_pair.local_digest != doc_pair.remote_digest:
                    doc_pair.local_state = "modified"
                    dynamic_states = True

        self.dao.synchronize_state(doc_pair, dynamic_states=dynamic_states)

    def _synchronize_locally_modified(self, doc_pair: DocPair, /) -> None:
        fs_item_info = None
        if doc_pair.local_digest == UNACCESSIBLE_HASH:
            # Try to update
            info = self.local.get_info(doc_pair.local_path)
            log.debug(f"Modification of postponed local file: {doc_pair!r}")
            doc_pair.local_digest = info.get_digest()

            if doc_pair.local_digest == UNACCESSIBLE_HASH:
                self._postpone_pair(doc_pair, "Unaccessible hash")
                return
            self.dao.update_local_state(doc_pair, info, versioned=False, queue=False)

        if not self.local.is_equal_digests(
            doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path
        ):
            if doc_pair.remote_can_update:
                if doc_pair.local_digest == UNACCESSIBLE_HASH:
                    self._postpone_pair(doc_pair, "Unaccessible hash")
                    return
                log.info(f"Updating remote document {doc_pair.local_name!r}")
                fs_item_info = self.remote.stream_update(
                    doc_pair.remote_ref,
                    self.local.abspath(doc_pair.local_path),
                    parent_fs_item_id=doc_pair.remote_parent_ref,
                    # Use remote name to avoid rename in case of duplicate
                    filename=doc_pair.remote_name,
                    engine_uid=self.engine.uid,
                )
                self.dao.update_last_transfer(doc_pair.id, "upload")
                self.dao.update_remote_state(doc_pair, fs_item_info, versioned=False)
                # TODO refresh_client
            else:
                log.info(
                    f"Skip update of remote document {doc_pair.local_name!r} "
                    "as it is read-only."
                )
                if self.engine.local_rollback():
                    self.local.delete(doc_pair.local_path)
                    self.dao.mark_descendants_remotely_created(doc_pair)
                else:
                    log.info(f"Set pair unsynchronized: {doc_pair!r}")
                    try:
                        fs_info: Optional[RemoteFileInfo] = self.remote.get_fs_info(
                            doc_pair.remote_ref
                        )
                    except NotFound:
                        fs_info = None

                    if fs_info is None or fs_info.lock_owner is None:
                        self.dao.unsynchronize_state(doc_pair, "READONLY")
                        self.engine.newReadonly.emit(doc_pair.local_name, None)
                    else:
                        self.dao.unsynchronize_state(doc_pair, "LOCKED")
                        self.engine.newLocked.emit(
                            doc_pair.local_name,
                            fs_info.lock_owner,
                            fs_info.lock_created,
                        )
                    self._handle_unsynchronized(doc_pair)
                return
        if fs_item_info is None:
            fs_item_info = self.remote.get_fs_info(doc_pair.remote_ref)
            self.dao.update_remote_state(doc_pair, fs_item_info, versioned=False)
        self._synchronize_if_not_remotely_dirty(doc_pair, remote_info=fs_item_info)

    def _get_normal_state_from_remote_ref(self, ref: str, /) -> Optional[DocPair]:
        # TODO Select the only states that is not a collection
        return self.dao.get_normal_state_from_remote(ref)

    def _postpone_pair(
        self,
        doc_pair: DocPair,
        reason: str,
        /,
        *,
        exception: Exception = None,
        interval: int = None,
    ) -> None:
        """Wait *interval* sec for it."""

        log.debug(f"Postpone action on document({reason}): {doc_pair!r}")
        doc_pair.error_count = 1
        self.engine.queue_manager.push_error(
            doc_pair, exception=exception, interval=interval
        )
        self.engine.send_metric("sync", "error", reason)

    def _synchronize_locally_resolved(self, doc_pair: DocPair, /) -> None:
        """NXDRIVE-766: processes a locally resolved conflict."""
        self._synchronize_locally_created(doc_pair, overwrite=True)

    def _synchronize_locally_created(
        self, doc_pair: DocPair, /, *, overwrite: bool = False
    ) -> None:
        """
        :param bool overwrite: Allows to overwrite an existing document
                               with the same title on the server.
        """

        name = doc_pair.local_path.name
        if not doc_pair.folderish:
            ignore, delay = is_generated_tmp_file(name)
            if ignore:
                # Might be a tierce software temporary file
                if not delay:
                    log.info(f"Ignoring generated tmp file: {name!r}")
                    return
                if doc_pair.error_count == 0:
                    # Save the error_count to not ignore next time
                    log.info(f"Delaying generated tmp file like: {name!r}")
                    self.increase_error(doc_pair, "Can be a temporary file")
                    return

        remote_ref = self.local.get_remote_id(doc_pair.local_path)
        # Find the parent pair to find the ref of the remote folder to
        # create the document
        parent_pair = self.dao.get_state_from_local(doc_pair.local_parent_path)
        log.debug(f"Entered _synchronize_locally_created, parent_pair={parent_pair!r}")

        if parent_pair is None:
            # Try to get it from xattr
            log.debug("Fallback to xattr")
            if self.local.exists(doc_pair.local_parent_path):
                ref = self.local.get_remote_id(doc_pair.local_parent_path)
                parent_pair = (
                    self._get_normal_state_from_remote_ref(ref) if ref else None
                )
        if parent_pair is None or not parent_pair.remote_ref:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            if parent_pair is not None and parent_pair.pair_state == "unsynchronized":
                self.dao.unsynchronize_state(doc_pair, "PARENT_UNSYNC")
                self._handle_unsynchronized(doc_pair)
                return
            raise ParentNotSynced(
                str(doc_pair.local_path), str(doc_pair.local_parent_path)
            )

        uid = info = None
        if remote_ref and "#" in remote_ref:
            # Verify it is not already synced elsewhere (a missed move?)
            # If same hash don't do anything and reconcile
            uid = remote_ref.split("#")[-1]
            info = self.remote.get_info(
                uid, raise_if_missing=False, fetch_parent_uid=False
            )
            log.warning(
                f"This document {doc_pair!r} has remote_ref {remote_ref}, info={info!r}"
            )
            if not info:
                # The document has an invalid remote ID.
                # Continue the document creation after purging the ID.
                log.info(f"Removing xattr(s) on {doc_pair.local_path!r}")
                func = ("remove_remote_id", "clean_xattr_folder_recursive")[
                    doc_pair.folderish
                ]
                getattr(self.local, func)(doc_pair.local_path)
                remote_ref = ""

        if remote_ref and info:
            try:
                if uid and info.is_trashed:
                    log.info(f"Untrash from the client: {doc_pair!r}")
                    self.remote.undelete(uid)
                    remote_parent_path = (
                        parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
                    )
                    fs_item_info = self.remote.get_fs_info(remote_ref)
                    # Handle document move
                    if fs_item_info.parent_uid != parent_pair.remote_ref:
                        fs_item_info = self.remote.move(
                            fs_item_info.uid, parent_pair.remote_ref
                        )
                    # Handle document rename
                    if fs_item_info.name != doc_pair.local_name:
                        fs_item_info = self.remote.rename(
                            fs_item_info.uid, doc_pair.local_name
                        )
                    self.dao.update_remote_state(
                        doc_pair,
                        fs_item_info,
                        remote_parent_path=remote_parent_path,
                        versioned=False,
                    )
                    # Handle document modification - update the doc_pair
                    refreshed = self.dao.get_state_from_id(doc_pair.id)
                    if refreshed:
                        self._synchronize_locally_modified(refreshed)
                    return

                fs_item_info = self.remote.get_fs_info(remote_ref)
                log.debug(
                    "Compare parents: "
                    f"{fs_item_info.parent_uid!r} | {parent_pair.remote_ref!r}"
                )
                # Document exists on the server
                if (
                    parent_pair.remote_ref
                    and parent_pair.remote_ref == fs_item_info.parent_uid
                    and self.local.is_equal_digests(
                        doc_pair.local_digest, fs_item_info.digest, doc_pair.local_path
                    )
                    and (
                        doc_pair.local_name == info.name
                        or doc_pair.local_state == "resolved"
                    )
                ):
                    if overwrite and info.folderish:
                        self._synchronize_locally_moved(doc_pair)
                    else:
                        log.warning(
                            "Document is already on the server, should not create: "
                            f"{doc_pair!r} | {fs_item_info!r}"
                        )
                    self.dao.synchronize_state(doc_pair)
                    return
                # Document exists on the server but is different
                elif (
                    parent_pair.remote_ref
                    and parent_pair.remote_ref == fs_item_info.parent_uid
                    and not self.local.is_equal_digests(
                        doc_pair.local_digest, fs_item_info.digest, doc_pair.local_path
                    )
                    and (
                        doc_pair.local_name == info.name
                        or doc_pair.local_state == "resolved"
                    )
                ):
                    if doc_pair.pair_state == "locally_resolved":
                        if fs_item_info.name != doc_pair.local_name:
                            fs_item_info = self.remote.rename(
                                fs_item_info.uid, doc_pair.local_name
                            )
                        remote_parent_path = (
                            parent_pair.remote_parent_path
                            + "/"
                            + parent_pair.remote_ref
                        )
                        self.dao.update_remote_state(
                            doc_pair,
                            fs_item_info,
                            remote_parent_path=remote_parent_path,
                            versioned=False,
                        )
                        # Handle document modification - update the doc_pair
                        refreshed = self.dao.get_state_from_id(doc_pair.id)
                        if refreshed and overwrite:
                            self._synchronize_locally_modified(refreshed)
                    return
            except HTTPError as e:
                # undelete will fail if you don't have the rights
                if e.status not in {401, 403}:
                    raise e
                log.debug(
                    "Create new document as current known document "
                    f"is not accessible: {remote_ref}"
                )
            except NotFound:
                # The document has an invalid remote ID.
                # It happens when locally untrashing a folder
                # containing files. Just ignore the error and proceed
                # to the document creation.
                log.info(f"Removing xattr on {doc_pair.local_path!r}")
                self.local.remove_remote_id(doc_pair.local_path)

        parent_ref: str = parent_pair.remote_ref
        if parent_pair.remote_can_create_child:
            remote_parent_path = (
                parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
            )
            if doc_pair.folderish:
                log.info(
                    f"Creating remote folder {name!r} "
                    f"in folder {parent_pair.remote_name!r}"
                )
                fs_item_info = self.remote.make_folder(
                    parent_ref, name, overwrite=overwrite
                )
                remote_ref = fs_item_info.uid
            else:
                # TODO Check if the file is already on the server with the good digest
                log.info(
                    f"Creating remote document {name!r} "
                    f"in folder {parent_pair.remote_name!r}"
                )
                local_info = self.local.get_info(doc_pair.local_path)
                if local_info.size != doc_pair.size:
                    # Size has changed (copy must still be running)
                    doc_pair.local_digest = UNACCESSIBLE_HASH
                    self.dao.update_local_state(
                        doc_pair, local_info, versioned=False, queue=False
                    )
                    # We need to recheck soon, and not put the doc in error after 3 tries
                    # (copying a 100 GB file can take quit some time for example)
                    doc_pair.error_count = 0
                    self._postpone_pair(doc_pair, "Unaccessible hash", interval=5)
                    return

                if doc_pair.local_digest == UNACCESSIBLE_HASH:
                    log.debug(f"Creation of postponed local file: {doc_pair!r}")
                    doc_pair.local_digest = local_info.get_digest()
                    self.dao.update_local_state(
                        doc_pair, local_info, versioned=False, queue=False
                    )
                if doc_pair.local_digest == UNACCESSIBLE_HASH:
                    self._postpone_pair(doc_pair, "Unaccessible hash")
                    return

                fs_item_info = self.remote.stream_file(
                    parent_ref,
                    self.local.abspath(doc_pair.local_path),
                    filename=name,
                    overwrite=overwrite,
                    engine_uid=self.engine.uid,
                )
                remote_ref = fs_item_info.uid
                self.dao.update_last_transfer(doc_pair.id, "upload")

            with self.dao.lock:
                remote_id_done = False
                # NXDRIVE-599: set as soon as possible the remote_id as
                # update_remote_state can crash with InterfaceError
                with suppress(NotFound):
                    self.local.set_remote_id(doc_pair.local_path, remote_ref)
                    remote_id_done = True
                self.dao.update_remote_state(
                    doc_pair,
                    fs_item_info,
                    remote_parent_path=remote_parent_path,
                    versioned=False,
                    queue=False,
                )
            log.debug(f"Put remote_ref in {remote_ref}")
            try:
                if not remote_id_done:
                    self.local.set_remote_id(doc_pair.local_path, remote_ref)
            except NotFound:
                new_pair = self.dao.get_state_from_id(doc_pair.id)
                # File has been moved during creation
                if new_pair and new_pair.local_path != doc_pair.local_path:
                    self.local.set_remote_id(new_pair.local_path, remote_ref)
                    self._synchronize_locally_moved(new_pair, update=False)
                    return
            self._synchronize_if_not_remotely_dirty(doc_pair, remote_info=fs_item_info)
        else:
            child_type = "folder" if doc_pair.folderish else "file"
            log.warning(
                f"Will not synchronize {child_type} {doc_pair.local_name!r} created in "
                f"local folder {parent_pair.local_name!r} since it is readonly"
            )
            if doc_pair.folderish:
                doc_pair.remote_can_create_child = False
            if self.engine.local_rollback():
                self.local.delete(doc_pair.local_path)
                self.dao.remove_state(doc_pair)
            else:
                log.info(f"Set pair unsynchronized: {doc_pair!r}")
                self.dao.unsynchronize_state(doc_pair, "READONLY")
                self.engine.newReadonly.emit(
                    doc_pair.local_name, parent_pair.remote_name
                )
                self._handle_unsynchronized(doc_pair)

    def _synchronize_locally_deleted(self, doc_pair: DocPair, /) -> None:
        if not doc_pair.remote_ref:
            self.dao.remove_state(doc_pair)
            self._search_for_dedup(doc_pair)
            self.remove_void_transfers(doc_pair)
            return

        if not Behavior.server_deletion:
            log.debug(
                "Server deletions are forbidden, skipping the remote deletion"
                f" and marking {doc_pair.local_path!r} as filtered"
            )
            self.dao.remove_state(doc_pair)
            self.dao.add_filter(f"{doc_pair.remote_parent_path}/{doc_pair.remote_ref}")
            return

        if doc_pair.remote_can_delete:
            log.info(
                "Deleting or unregistering remote document "
                f"{doc_pair.remote_name!r} ({doc_pair.remote_ref})"
            )
            if doc_pair.remote_state != "deleted":
                self.remote.delete(
                    doc_pair.remote_ref, parent_fs_item_id=doc_pair.remote_parent_ref
                )
            self.dao.remove_state(doc_pair)
        else:
            log.info(
                f"{doc_pair.local_path!r} can not be remotely deleted: "
                "either it is readonly or it is a virtual folder that "
                "does not exist in the server hierarchy"
            )
            if doc_pair.remote_state != "deleted":
                log.info(
                    f"Marking {doc_pair!r} as filter since remote document "
                    f"{doc_pair.remote_name!r} ({doc_pair.remote_ref}]) "
                    "can not be deleted"
                )
                self.dao.remove_state(doc_pair)
                self.dao.add_filter(
                    doc_pair.remote_parent_path + "/" + doc_pair.remote_ref
                )
                self.engine.deleteReadonly.emit(doc_pair.local_name)
        self._search_for_dedup(doc_pair)
        self.remove_void_transfers(doc_pair)

    def _synchronize_locally_moved_remotely_modified(
        self, doc_pair: DocPair, /
    ) -> None:
        self._synchronize_locally_moved(doc_pair, update=False)
        refreshed_pair = self.dao.get_state_from_id(doc_pair.id)
        if refreshed_pair:
            self._synchronize_remotely_modified(refreshed_pair)

    def _synchronize_locally_moved_created(self, doc_pair: DocPair, /) -> None:
        doc_pair.remote_ref = ""
        self._synchronize_locally_created(doc_pair)

    def _synchronize_locally_moved(
        self, doc_pair: DocPair, /, *, update: bool = True
    ) -> None:
        """A file has been moved locally."""

        remote_info = None
        self._search_for_dedup(doc_pair, name=doc_pair.remote_name)

        parent_ref = self.local.get_remote_id(doc_pair.local_parent_path)
        if not parent_ref:
            parent_pair = self.dao.get_state_from_local(doc_pair.local_parent_path)
            parent_ref = parent_pair.remote_ref if parent_pair else ""
        else:
            parent_pair = self._get_normal_state_from_remote_ref(parent_ref)

        if doc_pair.remote_name and doc_pair.local_name != doc_pair.remote_name:
            if not doc_pair.remote_can_rename:
                log.warning(f"Renaming is prohibited for {doc_pair!r}")
                self._handle_failed_remote_rename(doc_pair, doc_pair)
                return

            log.info(f"Renaming remote document according to local {doc_pair!r}")
            try:
                remote_info = self.remote.rename(
                    doc_pair.remote_ref, doc_pair.local_name
                )

                if parent_ref and parent_ref == doc_pair.remote_parent_ref:
                    # Handle cases when the user creates a new folder, it has the default name
                    # set to the local system: "New folder", "Nouveau dossier (2)" ...
                    # The folder is created directly and it generates useless URLs.
                    # So we move the document to get back good URLs.
                    # The trick here is that we move the document inside the same
                    # parent folder but with a different name.
                    log.info(f"Moving remote document according to local {doc_pair!r}")
                    self.remote.move2(
                        doc_pair.remote_ref, parent_ref, doc_pair.local_name
                    )

                self._refresh_remote(doc_pair, remote_info)
            except Exception as e:
                log.error(str(e))
                self._handle_failed_remote_rename(doc_pair, doc_pair)
                return

        if not parent_pair:
            raise ValueError("Should have a parent pair")

        if parent_ref != doc_pair.remote_parent_ref:
            if (
                doc_pair.remote_can_delete
                and not parent_pair.pair_state == "unsynchronized"
                and parent_pair.remote_can_create_child
            ):
                log.info(f"Moving remote file according to local {doc_pair!r}")
                # Bug if move in a parent with no rights / partial move
                # if rename at the same time
                parent_path = (
                    f"{parent_pair.remote_parent_path}/{parent_pair.remote_ref}"
                )
                remote_info = self.remote.move(
                    doc_pair.remote_ref, parent_pair.remote_ref
                )
                self.dao.update_remote_state(
                    doc_pair,
                    remote_info,
                    remote_parent_path=parent_path,
                    versioned=False,
                )
            else:
                # Move it back
                self._handle_failed_remote_move(doc_pair, doc_pair)

        # Handle modification at the same time if needed
        if update:
            if doc_pair.local_state == "moved":
                self._synchronize_if_not_remotely_dirty(
                    doc_pair, remote_info=remote_info
                )
            else:
                self._synchronize_locally_modified(doc_pair)

    def _synchronize_deleted_unknown(self, doc_pair: DocPair, /) -> None:
        """
        Somehow a pair can get to an inconsistent state:
        <local_state='deleted',remote_state='unknown',pair_state='unknown'>
        Even though we are not able to figure out how this can happen we
        need to handle this case to put the database back to a consistent
        state.
        This is tracked by https://jira.nuxeo.com/browse/NXP-14039
        """
        log.warning("Inconsistency should not happens anymore")
        log.warning(
            f"Detected inconsistent doc pair {doc_pair!r}, deleting it hoping the "
            "synchronizer will fix this case at next iteration"
        )
        self.dao.remove_state(doc_pair)

    def _download_content(self, doc_pair: DocPair, file_path: Path, /) -> Path:
        # Check if the file is already on the HD
        pair = self.dao.get_valid_duplicate_file(doc_pair.remote_digest)
        tmp_folder = self.engine.download_dir / doc_pair.remote_ref.split("#")[-1]
        tmp_folder.mkdir(parents=True, exist_ok=True)
        file_out = tmp_folder / file_path.name
        if pair:
            locker = unlock_path(file_out)
            try:
                # copyfile() is used to prevent metadata copy
                shutil.copyfile(self.local.abspath(pair.local_path), file_out)
            except (FileNotFoundError, IsADirectoryError):
                # IsADirectoryError may raise if the local path stored in DB is pointing
                #     to an obsolete path. And for whatever reason, that path points to
                #     a folder ...
                # Let's re-download the file.
                pass
            else:
                return file_out
            finally:
                lock_path(file_out, locker)

        return self.remote.stream_content(
            doc_pair.remote_ref,
            file_path,
            file_out,
            parent_fs_item_id=doc_pair.remote_parent_ref,
            engine_uid=self.engine.uid,
            doc_pair_id=doc_pair.id,
        )

    def _update_remotely(self, doc_pair: DocPair, is_renaming: bool, /) -> None:
        os_path = self.local.abspath(doc_pair.local_path)
        if is_renaming:
            new_os_path = os_path.with_name(safe_filename(doc_pair.remote_name))
            log.info(f"Replacing local file {os_path!r} by {new_os_path!r}")
        else:
            new_os_path = os_path
        log.info(f"Updating content of local file {os_path!r}")
        tmp_file = self._download_content(doc_pair, new_os_path)

        # Delete original file and rename tmp file
        remote_id = self.local.get_remote_id(doc_pair.local_path)
        self.local.delete_final(doc_pair.local_path)
        if remote_id:
            self.local.set_remote_id(tmp_file, doc_pair.remote_ref)
        updated_info = self.local.move(
            tmp_file, doc_pair.local_parent_path, name=doc_pair.remote_name
        )

        with suppress(OSError):
            shutil.rmtree(tmp_file.parent)

        # Set the modification time of the file to the server one
        self.local.change_file_date(
            updated_info.filepath, mtime=doc_pair.last_remote_updated
        )

        doc_pair.local_digest = updated_info.get_digest()
        self.dao.update_last_transfer(doc_pair.id, "download")
        self._refresh_local_state(doc_pair, updated_info)

    def _search_for_dedup(self, doc_pair: DocPair, /, *, name: str = None) -> None:
        if name is None:
            name = doc_pair.local_name
        # Auto resolve duplicate
        log.info(f"Search for dupe pair with {name!r} {doc_pair.remote_parent_ref}")
        dupe_pair = self.dao.get_dedupe_pair(
            name, doc_pair.remote_parent_ref, doc_pair.id
        )
        if dupe_pair is not None:
            log.info(f"Dupe pair found {dupe_pair!r}")
            self.dao.reset_error(dupe_pair)

    def _synchronize_remotely_modified(self, doc_pair: DocPair, /) -> None:
        is_renaming = safe_filename(doc_pair.remote_name) != doc_pair.local_name
        try:
            if (
                not doc_pair.folderish
                and doc_pair.local_digest is not None
                and not self.local.is_equal_digests(
                    doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path
                )
            ):
                self._update_remotely(doc_pair, is_renaming)
            else:
                # Digest agree so this might be a renaming and/or a move,
                # and no need to transfer additional bytes over the network
                is_move, new_parent_pair = self._is_remote_move(doc_pair)
                if self.remote.is_filtered(doc_pair.remote_parent_path):
                    # A move to a filtered parent (treat it as deletion)
                    self._synchronize_remotely_deleted(doc_pair)
                    return

                if not new_parent_pair:
                    # A move to a folder that has not yet been processed
                    self._postpone_pair(doc_pair, "PARENT_UNSYNC")
                    return

                if not (is_move or is_renaming):
                    log.info(
                        "No local impact of metadata update on document "
                        f"{doc_pair.remote_name!r}"
                    )
                else:
                    file_or_folder = "folder" if doc_pair.folderish else "file"
                    if doc_pair.folderish:
                        self.engine.set_local_folder_lock(doc_pair.local_path)
                    if is_move:
                        # Move and potential rename
                        moved_name = (
                            doc_pair.remote_name if is_renaming else doc_pair.local_name
                        )
                        old_path = doc_pair.local_path
                        new_path = new_parent_pair.local_path / moved_name
                        if old_path == new_path:
                            log.info(f"Wrong guess for move: {doc_pair!r}")
                            self._is_remote_move(doc_pair)
                            self.dao.synchronize_state(doc_pair)

                        log.info(
                            f"DOC_PAIR({doc_pair!r}): "
                            f"old_path[exists={self.local.exists(old_path)!r},"
                            f"id={self.local.get_remote_id(old_path)!r}]: {old_path!r},"
                            f" new_path[exists={self.local.exists(new_path)!r}, "
                            f"id={self.local.get_remote_id(new_path)!r}]: {new_path!r}"
                        )

                        old_path_abs = self.local.abspath(old_path)
                        new_path_abs = self.local.abspath(new_path)
                        log.info(
                            f"Moving local {file_or_folder} "
                            f"{old_path_abs!r} to {new_path_abs!r}"
                        )

                        # May need to add a lock for move
                        updated_info = self.local.move(
                            doc_pair.local_path,
                            new_parent_pair.local_path,
                            name=moved_name,
                        )
                        new_parent_path = (
                            new_parent_pair.remote_parent_path
                            + "/"
                            + new_parent_pair.remote_ref
                        )
                        self.dao.update_remote_parent_path(doc_pair, new_parent_path)
                    else:
                        log.info(
                            f"Renaming local {file_or_folder} "
                            f"{self.local.abspath(doc_pair.local_path)!r} "
                            f"to {doc_pair.remote_name!r}"
                        )
                        updated_info = self.local.rename(
                            doc_pair.local_path, doc_pair.remote_name
                        )

                    if updated_info:
                        # Should call a DAO method
                        new_path = updated_info.path.parent
                        self.dao.update_local_parent_path(
                            doc_pair, updated_info.path.name, new_path
                        )
                        self._search_for_dedup(doc_pair)
                        self._refresh_local_state(doc_pair, updated_info)
            self._handle_readonly(doc_pair)
            self.dao.synchronize_state(doc_pair)
        finally:
            if doc_pair.folderish:
                # Release folder lock in any case
                self.engine.release_folder_lock()

    def _synchronize_remotely_created(self, doc_pair: DocPair, /) -> None:
        name = doc_pair.remote_name

        # Find the parent pair to find the path of the local folder to
        # create the document into
        parent_pair = self._get_normal_state_from_remote_ref(doc_pair.remote_parent_ref)
        if parent_pair is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ParentNotSynced(name, doc_pair.remote_ref)

        if parent_pair.local_path is None:
            if parent_pair.pair_state == "unsynchronized":
                self.dao.unsynchronize_state(doc_pair, "PARENT_UNSYNC")
                self._handle_unsynchronized(doc_pair)
                return

            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ParentNotSynced(name, doc_pair.remote_ref)

        remote_path = f"{doc_pair.remote_parent_path}/{doc_pair.remote_ref}"
        if self.remote.is_filtered(remote_path):
            nature = ("file", "folder")[doc_pair.folderish]
            log.debug(f"Skip filtered {nature} {doc_pair.local_path!r}")
            self.dao.remove_state(doc_pair)
            return

        if not self.local.exists(doc_pair.local_path):
            # Check the parent's UID. A file cannot be created
            # if the parent's name is equal but not the UID.
            remote_parent_ref = self.local.get_remote_id(parent_pair.local_path)
            if remote_parent_ref != parent_pair.remote_ref:
                return
            try:
                path = self._create_remotely(doc_pair, parent_pair, name)
            except NotFound:
                # Drive was shut while syncing a root.  While stopped, the root
                # was unsynced via the Web-UI.  At the restart, remotely
                # created files queue may have obsolete information.
                # To prevent inconsistency, we remotely remove the pair.
                self._synchronize_remotely_deleted(doc_pair)
                return
        else:
            path = doc_pair.local_path
            remote_ref = self.local.get_remote_id(doc_pair.local_path)
            if remote_ref and remote_ref == doc_pair.remote_ref:
                log.info(
                    f"remote_ref (xattr) = {remote_ref}, "
                    f"doc_pair.remote_ref = {doc_pair.remote_ref} "
                    "=> setting conflicted state"
                )
                # Set conflict state for now
                # TO_REVIEW May need to overwrite
                self.dao.set_conflict_state(doc_pair)
                return
            elif remote_ref:
                # Case of several documents with same name
                # or case insensitive hard drive
                path = self._create_remotely(doc_pair, parent_pair, name)

        self.local.set_remote_id(path, doc_pair.remote_ref)
        if path != doc_pair.local_path and doc_pair.folderish:
            # Update children
            self.dao.update_local_parent_path(doc_pair, path.name, path.parent)
        self._refresh_local_state(doc_pair, self.local.get_info(path))
        self._handle_readonly(doc_pair)
        if not self.dao.synchronize_state(doc_pair):
            log.info(f"Pair is not in synchronized state (version issue): {doc_pair!r}")
            # Need to check if this is a remote or local change
            new_pair = self.dao.get_state_from_id(doc_pair.id)
            if not new_pair:
                return
            # Only local 'moved' change that can happen on
            # a pair with processor
            if new_pair.local_state == "moved":
                self._synchronize_locally_moved(new_pair, update=False)
            else:
                if new_pair.remote_state == "deleted":
                    self._synchronize_remotely_deleted(new_pair)
                else:
                    self._synchronize_remotely_modified(new_pair)

    def _create_remotely(
        self, doc_pair: DocPair, parent_pair: DocPair, name: str, /
    ) -> Path:
        # TODO Shared this locking system / Can have concurrent lock
        local_parent_path = parent_pair.local_path
        self._unlock_readonly(local_parent_path)
        try:
            if doc_pair.folderish:
                log.info(
                    f"Creating local folder {name!r} "
                    f"in {self.local.abspath(local_parent_path)!r}"
                )
                return self.local.make_folder(local_parent_path, name)

            path, os_path, name = self.local.get_new_file(local_parent_path, name)
            log.info(
                f"Creating local file {name!r} "
                f"in {self.local.abspath(local_parent_path)!r}"
            )
            tmp_file = self._download_content(doc_pair, os_path)

            # Set remote id on the TMP file already
            self.local.set_remote_id(tmp_file, doc_pair.remote_ref)

            # Move the TMP file to the local sync folder
            info = self.local.move(tmp_file, local_parent_path, name=name)

            # Set the modification time of the file to the server one
            mtime = doc_pair.last_remote_updated
            ctime = doc_pair.creation_date
            self.local.change_file_date(info.filepath, mtime=mtime, ctime=ctime)

            self.dao.update_last_transfer(doc_pair.id, "download")

            # Clean-up the TMP file
            with suppress(OSError):
                shutil.rmtree(tmp_file.parent)

            return path
        finally:
            self._lock_readonly(local_parent_path)

    def _synchronize_remotely_deleted(self, doc_pair: DocPair, /) -> None:
        remote_id = self.local.get_remote_id(doc_pair.local_path)
        if remote_id != doc_pair.remote_ref:
            log.warning(
                f"Tried to delete doc at {doc_pair.local_path} but its id "
                f"{remote_id} doesn't match the remote {doc_pair.remote_ref}"
            )
            return
        try:
            if doc_pair.local_state == "deleted":
                pass
            elif doc_pair.local_state == "unsynchronized":
                self.dao.remove_state(doc_pair)
                return
            else:
                log.info(
                    f"Deleting locally {self.local.abspath(doc_pair.local_path)!r}"
                )
                if doc_pair.folderish:
                    self.engine.set_local_folder_lock(doc_pair.local_path)
                else:
                    # Delete partial download if it exists
                    tmpdir = (
                        self.engine.download_dir / doc_pair.remote_ref.split("#")[-1]
                    )
                    with suppress(OSError):
                        shutil.rmtree(tmpdir)

                if not self.engine.use_trash():
                    # Force the complete file deletion
                    self.local.delete_final(doc_pair.local_path)
                else:
                    self.local.delete(doc_pair.local_path)
            self.dao.remove_state(doc_pair)
            self._search_for_dedup(doc_pair)
        finally:
            if doc_pair.folderish:
                self.engine.release_folder_lock()

    def _synchronize_unknown_deleted(self, doc_pair: DocPair, /) -> None:
        # Somehow a pair can get to an inconsistent state:
        # <local_state='unknown', remote_state='deleted', pair_state='unknown'>
        # Even though we are not able to figure out how this can happen we
        # need to handle this case to put the database back to a consistent
        # state.
        # This is tracked by https://jira.nuxeo.com/browse/NXP-13216
        log.info("Inconsistency should not happens anymore")
        log.info(
            f"Detected inconsistent doc pair {doc_pair!r}, deleting it hoping the "
            "synchronizer will fix this case at next iteration"
        )
        self.dao.remove_state(doc_pair)
        if doc_pair.local_path:
            log.info(
                f"Since the local path is set: {doc_pair.local_path!r}, "
                "the synchronizer will probably consider this as a local creation at "
                "next iteration and create the file or folder remotely"
            )
        else:
            log.info(
                "Since the local path is _not_ set, the synchronizer will "
                "probably do nothing at next iteration"
            )

    def _refresh_remote(
        self, doc_pair: DocPair, remote_info: RemoteFileInfo, /
    ) -> None:
        if remote_info is None:
            remote_info = self.remote.get_fs_info(doc_pair.remote_ref)
        if remote_info:
            self.dao.update_remote_state(
                doc_pair, remote_info, versioned=False, queue=False
            )

    def _refresh_local_state(self, doc_pair: DocPair, local_info: FileInfo, /) -> None:
        if doc_pair.local_digest is None and not doc_pair.folderish:
            doc_pair.local_digest = local_info.get_digest()
        self.dao.update_local_state(doc_pair, local_info, versioned=False, queue=False)
        doc_pair.local_path = local_info.path
        doc_pair.local_name = local_info.path.name
        doc_pair.last_local_updated = local_info.last_modification_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def _is_remote_move(self, doc_pair: DocPair, /) -> Tuple[bool, Optional[DocPair]]:
        local_parent = self.dao.get_state_from_local(doc_pair.local_parent_path)
        remote_parent = self._get_normal_state_from_remote_ref(
            doc_pair.remote_parent_ref
        )
        state = bool(
            local_parent and remote_parent and local_parent.id != remote_parent.id
        )
        log.info(
            f"is_remote_move={state!r}: name={doc_pair.remote_name!r}, "
            f"local={local_parent!r}, remote={remote_parent!r}"
        )
        return state, remote_parent

    def _handle_failed_remote_move(
        self, source_pair: DocPair, target_pair: DocPair, /
    ) -> None:
        pass

    def _handle_failed_remote_rename(
        self, source_pair: DocPair, target_pair: DocPair, /
    ) -> bool:
        """Cancel a local rename using the remote name."""

        # Being in such situation is not possible on Unix,
        # this is a Windows feature only :D
        if not self.engine.local_rollback(force=WINDOWS):
            return False

        # For an unknown reason yet, the remote name is set to None.
        # In that case, just ignore the rollback.
        if not target_pair.remote_name:
            return False

        log.warning(
            f"Renaming {target_pair.remote_name!r} "
            f"to {target_pair.local_name!r} canceled"
        )

        try:
            info = self.local.rename(target_pair.local_path, target_pair.remote_name)
            self.dao.update_local_state(source_pair, info, queue=False)
            if source_pair != target_pair:
                if target_pair.folderish:
                    # Remove "new" created tree
                    pairs = self.dao.get_states_from_partial_local(
                        target_pair.local_path
                    )
                    for pair in pairs:
                        self.dao.remove_state(pair)
                    pairs = self.dao.get_states_from_partial_local(
                        source_pair.local_path
                    )
                    for pair in pairs:
                        self.dao.synchronize_state(pair)
                else:
                    self.dao.remove_state(target_pair)
            self.dao.synchronize_state(source_pair)
            return True
        except Exception:
            log.exception("Cannot rollback local modification")
        return False

    def _handle_unsynchronized(self, doc_pair: DocPair, /) -> None:
        # Used for overwrite
        pass

    def _handle_readonly(self, doc_pair: DocPair, /) -> None:
        # Don't use readonly on folder for win32 and on Locally Edited
        if doc_pair.folderish and WINDOWS:
            return

        if doc_pair.is_readonly():
            log.info(f"Setting {doc_pair.local_path!r} as readonly")
            self.local.set_readonly(doc_pair.local_path)
        else:
            log.info(f"Unsetting {doc_pair.local_path!r} as readonly")
            self.local.unset_readonly(doc_pair.local_path)
