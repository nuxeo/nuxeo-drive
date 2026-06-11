"""
Alfresco Processor — handles sync operations for Alfresco engines.

Implements the ``_execute`` loop and sync handlers that process queue
items (remotely_created, locally_created, etc.) using the
``AlfrescoRemote`` adapter methods.
"""

import shutil
import sqlite3
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from time import monotonic_ns, sleep
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from nxdrive.drive.client.local import FileInfo
from nxdrive.drive.constants import (
    CONNECTION_ERROR,
    MAC,
    UNACCESSIBLE_HASH,
    WINDOWS,
    TransferStatus,
)
from nxdrive.drive.engine.processor import Processor as _ProcessorBase
from nxdrive.drive.exceptions import (
    NotFound,
    PairInterrupt,
    ParentNotSynced,
    ThreadInterrupt,
)
from nxdrive.drive.objects import DocPair, RemoteFileInfo
from nxdrive.drive.utils import (
    is_generated_tmp_file,
    lock_path,
    safe_filename,
    unlock_path,
)

if TYPE_CHECKING:
    from nxdrive.alfresco.engine.engine import AlfrescoEngine

__all__ = ("AlfrescoProcessor",)

log = getLogger(__name__)


class AlfrescoProcessor(_ProcessorBase):
    """Processor for Alfresco sync operations."""

    def __init__(self, engine: "AlfrescoEngine", item_getter: Callable, /) -> None:
        super().__init__(engine, item_getter)
        self._current_metrics: Dict[str, Any] = {}

    # -- helpers -------------------------------------------------------------

    def _get_normal_state_from_remote_ref(self, ref: str, /) -> Optional[DocPair]:
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
        log.debug(f"Postpone action on document({reason}): {doc_pair!r}")
        doc_pair.error_count = 1
        self.engine.queue_manager.push_error(
            doc_pair, exception=exception, interval=interval
        )

    def increase_error(
        self, doc_pair: DocPair, error: str, /, *, exception: Exception = None
    ) -> None:
        self.dao.increase_error(doc_pair, error, "error")
        self._postpone_pair(doc_pair, error, exception=exception)

    def giveup_error(
        self, doc_pair: DocPair, error: str, /, *, exception: Exception = None
    ) -> None:
        self.dao.increase_error(doc_pair, error, "error")
        self.engine.queue_manager.push_error(doc_pair, exception=exception)

    def _refresh_local_state(self, doc_pair: DocPair, local_info: FileInfo, /) -> None:
        self.dao.update_local_state(doc_pair, local_info, versioned=False, queue=False)

    def _refresh_remote(
        self, doc_pair: DocPair, remote_info: RemoteFileInfo = None, /
    ) -> None:
        if remote_info is None:
            remote_info = self.remote.get_fs_info(doc_pair.remote_ref)
        if remote_info:
            self.dao.update_remote_state(
                doc_pair, remote_info, versioned=False, queue=False
            )

    def _handle_readonly(self, doc_pair: DocPair, /) -> None:
        if doc_pair.folderish and WINDOWS:
            return
        if doc_pair.is_readonly():
            self.local.set_readonly(doc_pair.local_path)
        else:
            self.local.unset_readonly(doc_pair.local_path)

    @staticmethod
    def check_pair_state(doc_pair: DocPair, /) -> bool:
        return all(
            (
                doc_pair.pair_state not in ("synchronized", "unsynchronized"),
                not doc_pair.pair_state.startswith("parent_"),
            )
        )

    def remove_void_transfers(self, doc_pair: DocPair, /) -> None:
        with suppress(Exception):
            for nature in ("download", "upload"):
                meth = getattr(self.dao, f"get_{nature}")
                transfer = meth(doc_pair=doc_pair.id)
                if transfer and transfer.status is not TransferStatus.ONGOING:
                    self.dao.remove_transfer(nature, doc_pair=doc_pair.id)

    # -- Main loop -----------------------------------------------------------

    def _get_next_doc_pair(self, item: DocPair) -> Optional[DocPair]:
        try:
            return self.dao.acquire_state(self.thread_id, item.id)
        except sqlite3.OperationalError:
            state = self.dao.get_state_from_id(item.id)
            if state:
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

                self._handle_doc_pair_sync(doc_pair, sync_handler)

            except ThreadInterrupt:
                self.engine.queue_manager.push(doc_pair)
                raise
            except NotFound:
                log.warning("The document or its parent does not exist anymore")
                self.remove_void_transfers(doc_pair)
            except (PairInterrupt, ParentNotSynced) as exc:
                log.info(f"{type(exc).__name__}, wait 1s and requeue")
                sleep(1)
                self.engine.queue_manager.push(doc_pair)
            except CONNECTION_ERROR:
                log.debug("Connection issue", exc_info=True)
                self._postpone_pair(doc_pair, "CONNECTION_ERROR")
            except OSError as exc:
                if exc.errno == 28:  # No space left
                    self.engine.noSpaceLeftOnDevice.emit()
                    raise ThreadInterrupt()
                log.exception("OS error")
                self.increase_error(doc_pair, "OS_ERROR", exception=exc)
            except Exception:
                log.exception("Unhandled error")
                self.increase_error(doc_pair, "UNKNOWN")
            finally:
                self._current_doc_pair = None

    def _handle_doc_pair_sync(
        self, doc_pair: DocPair, sync_handler: Callable, /
    ) -> None:
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

        parent_path = doc_pair.local_parent_path
        if parent_path and not self.local.exists(parent_path):
            parent_pair = self._get_normal_state_from_remote_ref(
                doc_pair.remote_parent_ref
            )
            if not parent_pair or doc_pair.local_parent_path == parent_pair.local_path:
                self.dao.remove_state(doc_pair)
                return
            doc_pair.local_parent_path = parent_pair.local_path

        # Skip paused transfers
        download = self.engine.dao.get_download(doc_pair=doc_pair.id)
        if download and download.status not in (
            TransferStatus.ONGOING,
            TransferStatus.DONE,
        ):
            log.info(f"Download is paused for {doc_pair!r}")
            return

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

    # -- Soft locks (from Nuxeo processor) -----------------------------------

    def _unlock_soft_path(self, path: Path, /) -> None:
        path = Path(str(path).lower())
        with AlfrescoProcessor.path_locker:
            if self.engine.uid not in AlfrescoProcessor.soft_locks:
                AlfrescoProcessor.soft_locks[self.engine.uid] = {}
            else:
                AlfrescoProcessor.soft_locks[self.engine.uid].pop(path, None)

    def _lock_soft_path(self, path: Path, /) -> Path:
        path = Path(str(path).lower())
        with AlfrescoProcessor.path_locker:
            if self.engine.uid not in AlfrescoProcessor.soft_locks:
                AlfrescoProcessor.soft_locks[self.engine.uid] = {}
            if path in AlfrescoProcessor.soft_locks[self.engine.uid]:
                raise PairInterrupt
            AlfrescoProcessor.soft_locks[self.engine.uid][path] = True
            return path

    # -- Sync handlers -------------------------------------------------------

    def _synchronize_remotely_created(self, doc_pair: DocPair, /) -> None:
        name = doc_pair.remote_name
        parent_pair = self._get_normal_state_from_remote_ref(doc_pair.remote_parent_ref)
        if parent_pair is None:
            raise ParentNotSynced(name, doc_pair.remote_ref)
        if parent_pair.local_path is None:
            raise ParentNotSynced(name, doc_pair.remote_ref)

        if not self.local.exists(doc_pair.local_path):
            remote_parent_ref = self.local.get_remote_id(parent_pair.local_path)
            if remote_parent_ref != parent_pair.remote_ref:
                return
            path = self._create_remotely(doc_pair, parent_pair, name)
        else:
            path = doc_pair.local_path
            remote_ref = self.local.get_remote_id(doc_pair.local_path)
            if remote_ref and remote_ref == doc_pair.remote_ref:
                self.dao.set_conflict_state(doc_pair)
                return
            elif remote_ref:
                path = self._create_remotely(doc_pair, parent_pair, name)

        self.local.set_remote_id(path, doc_pair.remote_ref)
        if path != doc_pair.local_path and doc_pair.folderish:
            self.dao.update_local_parent_path(doc_pair, path.name, path.parent)
        local_info = self.local.get_info(path)
        # Store the actual digest so the watchdog "modified" event
        # sees a matching digest and doesn't trigger a re-upload.
        doc_pair.local_digest = local_info.get_digest()
        self._refresh_local_state(doc_pair, local_info)
        self._handle_readonly(doc_pair)
        self.dao.synchronize_state(doc_pair)

    def _create_remotely(
        self, doc_pair: DocPair, parent_pair: DocPair, name: str, /
    ) -> Path:
        local_parent_path = parent_pair.local_path
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

        self.local.set_remote_id(tmp_file, doc_pair.remote_ref)
        info = self.local.move(tmp_file, local_parent_path, name=name)

        mtime = doc_pair.last_remote_updated
        ctime = doc_pair.creation_date
        self.local.change_file_date(info.filepath, mtime=mtime, ctime=ctime)

        self.dao.update_last_transfer(doc_pair.id, "download")

        with suppress(OSError):
            shutil.rmtree(tmp_file.parent)

        return path

    def _download_content(self, doc_pair: DocPair, file_path: Path, /) -> Path:
        # Alfresco nodes use simple IDs (no '#' separator)
        safe_id = (
            doc_pair.remote_ref.split("#")[-1]
            if "#" in doc_pair.remote_ref
            else doc_pair.remote_ref
        )
        tmp_folder = self.engine.download_dir / safe_id
        tmp_folder.mkdir(parents=True, exist_ok=True)
        file_out = tmp_folder / file_path.name

        # Try to re-use a local duplicate
        if doc_pair.remote_digest:
            pair = self.dao.get_valid_duplicate_file(doc_pair.remote_digest)
            if pair:
                locker = unlock_path(file_out)
                try:
                    shutil.copyfile(self.local.abspath(pair.local_path), file_out)
                except (FileNotFoundError, IsADirectoryError):
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
        )

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
                is_move, new_parent_pair = self._is_remote_move(doc_pair)
                if self.remote.is_filtered(doc_pair.remote_parent_path):
                    self._synchronize_remotely_deleted(doc_pair)
                    return
                if not new_parent_pair:
                    self._postpone_pair(doc_pair, "PARENT_UNSYNC")
                    return
                if is_move or is_renaming:
                    file_or_folder = "folder" if doc_pair.folderish else "file"
                    if doc_pair.folderish:
                        self.engine.set_local_folder_lock(doc_pair.local_path)
                    if is_move:
                        moved_name = (
                            doc_pair.remote_name if is_renaming else doc_pair.local_name
                        )
                        old_path = doc_pair.local_path
                        new_path = new_parent_pair.local_path / moved_name
                        if old_path == new_path:
                            self.dao.synchronize_state(doc_pair)
                        else:
                            log.info(
                                f"Moving local {file_or_folder} "
                                f"{self.local.abspath(old_path)!r} "
                                f"to {self.local.abspath(new_path)!r}"
                            )
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
                            self.dao.update_remote_parent_path(
                                doc_pair, new_parent_path
                            )
                            if updated_info:
                                self.dao.update_local_parent_path(
                                    doc_pair,
                                    updated_info.path.name,
                                    updated_info.path.parent,
                                )
                                self._refresh_local_state(doc_pair, updated_info)
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
                            self.dao.update_local_parent_path(
                                doc_pair,
                                updated_info.path.name,
                                updated_info.path.parent,
                            )
                            self._refresh_local_state(doc_pair, updated_info)
            self._handle_readonly(doc_pair)
            self.dao.synchronize_state(doc_pair)
        finally:
            if doc_pair.folderish:
                self.engine.release_folder_lock()

    def _is_remote_move(self, doc_pair: DocPair, /) -> tuple:
        local_parent = self.dao.get_state_from_local(doc_pair.local_parent_path)
        remote_parent = self._get_normal_state_from_remote_ref(
            doc_pair.remote_parent_ref
        )
        state = bool(
            local_parent and remote_parent and local_parent.id != remote_parent.id
        )
        return state, remote_parent

    def _update_remotely(self, doc_pair: DocPair, is_renaming: bool, /) -> None:
        os_path = self.local.abspath(doc_pair.local_path)
        if is_renaming:
            new_os_path = os_path.with_name(safe_filename(doc_pair.remote_name))
        else:
            new_os_path = os_path
        log.info(f"Updating content of local file {os_path!r}")
        tmp_file = self._download_content(doc_pair, new_os_path)

        remote_id = self.local.get_remote_id(doc_pair.local_path)
        self.local.delete_final(doc_pair.local_path)
        if remote_id:
            self.local.set_remote_id(tmp_file, doc_pair.remote_ref)
        updated_info = self.local.move(
            tmp_file, doc_pair.local_parent_path, name=doc_pair.remote_name
        )

        with suppress(OSError):
            shutil.rmtree(tmp_file.parent)

        self.local.change_file_date(
            updated_info.filepath, mtime=doc_pair.last_remote_updated
        )
        doc_pair.local_digest = updated_info.get_digest()
        self.dao.update_last_transfer(doc_pair.id, "download")
        self._refresh_local_state(doc_pair, updated_info)

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
                if not self.engine.use_trash():
                    self.local.delete_final(doc_pair.local_path)
                else:
                    self.local.delete(doc_pair.local_path)
            self.dao.remove_state(doc_pair)
        finally:
            if doc_pair.folderish:
                self.engine.release_folder_lock()

    def _synchronize_locally_created(self, doc_pair: DocPair, /) -> None:
        name = doc_pair.local_path.name
        if not doc_pair.folderish:
            ignore, delay = is_generated_tmp_file(name)
            if ignore:
                if not delay:
                    log.info(f"Ignoring generated tmp file: {name!r}")
                    return
                if doc_pair.error_count == 0:
                    log.info(f"Delaying generated tmp file like: {name!r}")
                    self.increase_error(doc_pair, "Can be a temporary file")
                    return

        parent_pair = self.dao.get_state_from_local(doc_pair.local_parent_path)
        if parent_pair is None:
            if self.local.exists(doc_pair.local_parent_path):
                ref = self.local.get_remote_id(doc_pair.local_parent_path)
                parent_pair = (
                    self._get_normal_state_from_remote_ref(ref) if ref else None
                )
        if parent_pair is None or not parent_pair.remote_ref:
            raise ParentNotSynced(
                str(doc_pair.local_path), str(doc_pair.local_parent_path)
            )

        parent_ref = parent_pair.remote_ref
        if not parent_pair.remote_can_create_child:
            log.warning(
                f"Cannot create {doc_pair.local_name!r} in read-only "
                f"folder {parent_pair.local_name!r}"
            )
            self.dao.unsynchronize_state(doc_pair, "READONLY")
            return

        remote_parent_path = (
            parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
        )
        if doc_pair.folderish:
            log.info(
                f"Creating remote folder {name!r} "
                f"in folder {parent_pair.remote_name!r}"
            )
            fs_item_info = self.remote.make_folder(parent_ref, name)
            remote_ref = fs_item_info.uid
        else:
            log.info(
                f"Creating remote document {name!r} "
                f"in folder {parent_pair.remote_name!r}"
            )
            if doc_pair.local_digest == UNACCESSIBLE_HASH:
                info = self.local.get_info(doc_pair.local_path)
                doc_pair.local_digest = info.get_digest()
                self.dao.update_local_state(
                    doc_pair, info, versioned=False, queue=False
                )
            if doc_pair.local_digest == UNACCESSIBLE_HASH:
                self._postpone_pair(doc_pair, "Unaccessible hash")
                return

            fs_item_info = self.remote.stream_file(
                parent_ref,
                self.local.abspath(doc_pair.local_path),
                filename=name,
            )
            remote_ref = fs_item_info.uid
            self.dao.update_last_transfer(doc_pair.id, "upload")

        with suppress(NotFound):
            self.local.set_remote_id(doc_pair.local_path, remote_ref)
        # After upload, store the digest computed by stream_file/make_folder
        # so that the next remote scan doesn't see a spurious mismatch.
        if fs_item_info.digest:
            doc_pair.local_digest = fs_item_info.digest
        self.dao.update_remote_state(
            doc_pair,
            fs_item_info,
            remote_parent_path=remote_parent_path,
            versioned=False,
            queue=False,
        )
        self.dao.synchronize_state(doc_pair)

    def _synchronize_locally_modified(self, doc_pair: DocPair, /) -> None:
        if doc_pair.local_digest == UNACCESSIBLE_HASH:
            info = self.local.get_info(doc_pair.local_path)
            doc_pair.local_digest = info.get_digest()
            if doc_pair.local_digest == UNACCESSIBLE_HASH:
                self._postpone_pair(doc_pair, "Unaccessible hash")
                return
            self.dao.update_local_state(doc_pair, info, versioned=False, queue=False)

        fs_item_info = None
        if not self.local.is_equal_digests(
            doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path
        ):
            if doc_pair.remote_can_update:
                log.info(f"Updating remote document {doc_pair.local_name!r}")
                fs_item_info = self.remote.stream_update(
                    doc_pair.remote_ref,
                    self.local.abspath(doc_pair.local_path),
                    filename=doc_pair.remote_name,
                )
                self.dao.update_last_transfer(doc_pair.id, "upload")
                self.dao.update_remote_state(doc_pair, fs_item_info, versioned=False)
            else:
                log.info(
                    f"Skip update of remote document {doc_pair.local_name!r} "
                    "as it is read-only."
                )
                self.dao.unsynchronize_state(doc_pair, "READONLY")
                return
        if fs_item_info is None:
            fs_item_info = self.remote.get_fs_info(doc_pair.remote_ref)
            self.dao.update_remote_state(doc_pair, fs_item_info, versioned=False)
        self.dao.synchronize_state(doc_pair)

    def _synchronize_locally_deleted(self, doc_pair: DocPair, /) -> None:
        if not doc_pair.remote_ref:
            self.dao.remove_state(doc_pair)
            self.remove_void_transfers(doc_pair)
            return

        if doc_pair.remote_can_delete:
            log.info(
                f"Deleting remote document {doc_pair.remote_name!r} "
                f"({doc_pair.remote_ref})"
            )
            if doc_pair.remote_state != "deleted":
                self.remote.delete(
                    doc_pair.remote_ref,
                    parent_fs_item_id=doc_pair.remote_parent_ref,
                )
            self.dao.remove_state(doc_pair)
        else:
            log.info(f"{doc_pair.local_path!r} cannot be remotely deleted (read-only)")
            self.dao.remove_state(doc_pair)
            self.dao.add_filter(doc_pair.remote_parent_path + "/" + doc_pair.remote_ref)
        self.remove_void_transfers(doc_pair)

    def _synchronize_locally_moved(self, doc_pair: DocPair, /) -> None:
        parent_ref = self.local.get_remote_id(doc_pair.local_parent_path)
        if not parent_ref:
            parent_pair = self.dao.get_state_from_local(doc_pair.local_parent_path)
            parent_ref = parent_pair.remote_ref if parent_pair else ""
        else:
            parent_pair = self._get_normal_state_from_remote_ref(parent_ref)

        if not parent_pair:
            raise ParentNotSynced(
                str(doc_pair.local_path), str(doc_pair.local_parent_path)
            )

        remote_info = None
        if doc_pair.remote_name and doc_pair.local_name != doc_pair.remote_name:
            log.info(f"Renaming remote document {doc_pair!r}")
            remote_info = self.remote.rename(doc_pair.remote_ref, doc_pair.local_name)

        if parent_pair.remote_ref != doc_pair.remote_parent_ref:
            log.info(f"Moving remote document {doc_pair!r}")
            remote_info = self.remote.move(doc_pair.remote_ref, parent_pair.remote_ref)

        if remote_info:
            remote_parent_path = (
                parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
            )
            self.dao.update_remote_state(
                doc_pair,
                remote_info,
                remote_parent_path=remote_parent_path,
                versioned=False,
            )
        self.dao.synchronize_state(doc_pair)

    def _synchronize_conflicted(self, doc_pair: DocPair, /) -> None:
        # Auto-resolve if digests match
        if self.local.is_equal_digests(
            doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path
        ):
            self.dao.synchronize_state(doc_pair)

    def _synchronize_unknown_deleted(self, doc_pair: DocPair, /) -> None:
        log.info(f"Removing inconsistent pair: {doc_pair!r}")
        self.dao.remove_state(doc_pair)

    def _synchronize_deleted_unknown(self, doc_pair: DocPair, /) -> None:
        log.info(f"Removing inconsistent pair: {doc_pair!r}")
        self.dao.remove_state(doc_pair)
