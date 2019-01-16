# coding: utf-8
import shutil
import sqlite3
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from threading import Lock
from time import sleep
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from PyQt5.QtCore import pyqtSignal
from nuxeo.exceptions import CorruptedFile, HTTPError
from requests import ConnectionError

from .activity import Action
from .workers import EngineWorker
from ..client.local_client import FileInfo
from ..constants import (
    DOWNLOAD_TMP_FILE_PREFIX,
    DOWNLOAD_TMP_FILE_SUFFIX,
    MAC,
    UNACCESSIBLE_HASH,
    WINDOWS,
)
from ..exceptions import (
    DuplicationDisabledError,
    NotFound,
    PairInterrupt,
    ParentNotSynced,
    ThreadInterrupt,
    UnknownDigest,
)
from ..objects import DocPair, RemoteFileInfo
from ..utils import (
    current_milli_time,
    is_generated_tmp_file,
    lock_path,
    safe_filename,
    unlock_path,
)

if TYPE_CHECKING:
    from .engine import Engine  # noqa

__all__ = ("Processor",)

log = getLogger(__name__)


class Processor(EngineWorker):
    pairSync = pyqtSignal(object)
    path_locker = Lock()
    soft_locks: Dict[str, Dict[Path, bool]] = dict()
    readonly_locks: Dict[str, Dict[Path, List[int]]] = dict()
    readonly_locker = Lock()

    _current_doc_pair: Optional[DocPair] = None

    def __init__(self, engine: "Engine", item_getter: Callable, **kwargs: Any) -> None:
        super().__init__(engine, engine.get_dao(), **kwargs)
        self._get_item = item_getter
        self.engine = engine
        self.local = self.engine.local
        self.remote = self.engine.remote

    def _unlock_soft_path(self, path: Path) -> None:
        log.trace(f"Soft unlocking {path!r}")
        path = Path(str(path).lower())
        with Processor.path_locker:
            if self.engine.uid not in Processor.soft_locks:
                Processor.soft_locks[self.engine.uid] = dict()
            else:
                Processor.soft_locks[self.engine.uid].pop(path, None)

    def _unlock_readonly(self, path: Path) -> None:
        with Processor.readonly_locker:
            if self.engine.uid not in Processor.readonly_locks:
                Processor.readonly_locks[self.engine.uid] = dict()

            if path in Processor.readonly_locks[self.engine.uid]:
                log.trace(f"Readonly unlock: increase count on {path!r}")
                Processor.readonly_locks[self.engine.uid][path][0] += 1
            else:
                lock = self.local.unlock_ref(path)
                log.trace(f"Readonly unlock: unlock on {path!r} with {lock}")
                Processor.readonly_locks[self.engine.uid][path] = [1, lock]

    def _lock_readonly(self, path: Path) -> None:
        with Processor.readonly_locker:
            if self.engine.uid not in Processor.readonly_locks:
                Processor.readonly_locks[self.engine.uid] = dict()

            if path not in Processor.readonly_locks[self.engine.uid]:
                log.debug(f"Readonly lock: cannot find reference on {path!r}")
                return

            Processor.readonly_locks[self.engine.uid][path][0] -= 1
            idx, lock = Processor.readonly_locks[self.engine.uid][path]

            log.trace(f"Readonly lock: update lock count on {path!r} to {idx}")

            if idx <= 0:
                self.local.lock_ref(path, lock)
                log.trace(f"Readonly lock: relocked {path!r} with {lock}")
                del Processor.readonly_locks[self.engine.uid][path]

    def _lock_soft_path(self, path: Path) -> Path:
        log.trace(f"Soft locking {path!r}")
        path = Path(str(path).lower())
        with Processor.path_locker:
            if self.engine.uid not in Processor.soft_locks:
                Processor.soft_locks[self.engine.uid] = dict()
            if path in Processor.soft_locks[self.engine.uid]:
                raise PairInterrupt
            else:
                Processor.soft_locks[self.engine.uid][path] = True
                return path

    def get_current_pair(self) -> Optional[DocPair]:
        return self._current_doc_pair

    @staticmethod
    def check_pair_state(doc_pair: DocPair) -> bool:
        """ Eliminate unprocessable states. """

        if any(
            (
                doc_pair.pair_state in ("synchronized", "unsynchronized"),
                doc_pair.pair_state.startswith("parent_"),
            )
        ):
            log.trace(f"Skip pair in non-processable state: {doc_pair!r}")
            return False
        return True

    def _execute(self) -> None:
        while "There are items in the queue":
            item = self._get_item()
            if not item:
                break

            try:
                doc_pair = self._dao.acquire_state(self.get_thread_id(), item.id)
            except sqlite3.OperationalError:
                state = self._dao.get_state_from_id(item.id)
                if state:
                    if (
                        WINDOWS
                        and state.pair_state == "locally_moved"
                        and not state.remote_can_rename
                    ):
                        log.debug(
                            "A local rename on a read-only folder is allowed "
                            " on Windows, but it should not. Skipping."
                        )
                        continue

                    log.trace(f"Cannot acquire state for item {item!r} ({state!r})")
                    self._postpone_pair(item, "Pair in use", interval=3)
                continue

            if not doc_pair:
                log.trace(f"Did not acquire state, dropping {item!r}")
                continue

            soft_lock = None
            try:
                log.debug(f"Executing processor on {doc_pair!r}({doc_pair.version})")
                self._current_doc_pair = doc_pair
                if not self.check_pair_state(doc_pair):
                    continue

                # Ensure we are using the good clients
                if self.remote is not self.engine.remote:
                    self.remote = self.engine.remote
                if self.local is not self.engine.local:
                    self.local = self.engine.local

                self.engine.manager.osi.send_sync_status(
                    doc_pair, self.local.abspath(doc_pair.local_path)
                )

                if MAC and self.local.exists(doc_pair.local_path):
                    with suppress(OSError):
                        finder_info = self.local.get_remote_id(
                            doc_pair.local_path, "com.apple.FinderInfo"
                        )
                        if "brokMACS" in finder_info:
                            log.trace(f"Skip as pair is in use by Finder: {doc_pair!r}")
                            self._postpone_pair(
                                doc_pair, "Finder using file", interval=3
                            )
                            continue

                # TODO Update as the server dont take hash to avoid conflict yet
                if doc_pair.pair_state.startswith("locally") and doc_pair.remote_ref:
                    try:
                        remote_info = self.remote.get_fs_info(doc_pair.remote_ref)
                        if (
                            remote_info.digest != doc_pair.remote_digest
                            and doc_pair.remote_digest is not None
                        ):
                            doc_pair.remote_state = "modified"
                        elif (
                            doc_pair.folderish
                            and remote_info.name != doc_pair.remote_name
                        ):
                            doc_pair.remote_state = "moved"
                        self._refresh_remote(doc_pair, remote_info)

                        # Can run into conflict
                        if doc_pair.pair_state == "conflicted":
                            continue

                        refreshed = self._dao.get_state_from_id(doc_pair.id)
                        if not refreshed or not self.check_pair_state(refreshed):
                            continue
                        doc_pair = refreshed or doc_pair
                    except NotFound:
                        doc_pair.remote_ref = ""

                # NXDRIVE-842: parent is in disabled duplication error
                parent_pair = self._get_normal_state_from_remote_ref(
                    doc_pair.remote_parent_ref
                )
                if parent_pair and parent_pair.last_error == "DEDUP":
                    continue

                parent_path = doc_pair.local_parent_path

                if not self.local.exists(parent_path):
                    if (
                        not parent_pair
                        or doc_pair.local_parent_path == parent_pair.local_path
                    ):
                        self._dao.remove_state(doc_pair)
                        continue

                    # The parent folder has been renamed sooner
                    # in the current synchronization
                    doc_pair.local_parent_path = parent_pair.local_path

                handler_name = f"_synchronize_{doc_pair.pair_state}"
                sync_handler = getattr(self, handler_name, None)
                if not sync_handler:
                    log.debug(
                        f"Unhandled pair_state {doc_pair.pair_state!r} for {doc_pair!r}"
                    )
                    self.increase_error(doc_pair, "ILLEGAL_STATE")
                    continue

                Action(handler_name)
                self._current_metrics = {
                    "handler": doc_pair.pair_state,
                    "start_time": current_milli_time(),
                }
                log.trace(f"Calling {handler_name}() on doc pair {doc_pair!r}")

                try:
                    soft_lock = self._lock_soft_path(doc_pair.local_path)
                    sync_handler(doc_pair)
                    self._current_metrics["end_time"] = current_milli_time()

                    pair = self._dao.get_state_from_id(doc_pair.id)
                    if pair and "deleted" not in pair.pair_state:
                        self.engine.manager.osi.send_sync_status(
                            pair, self.local.abspath(pair.local_path)
                        )

                    self.pairSync.emit(self._current_metrics)
                except ThreadInterrupt:
                    raise
                except HTTPError as exc:
                    if exc.status == 404:
                        # We saw it happened once a migration is done.
                        # Nuxeo kept the document reference but it does
                        # not exist physically anywhere.
                        log.debug(f"The document does not exist anymore: {doc_pair!r}")
                        self._dao.remove_state(doc_pair)
                    elif exc.status == 409:  # Conflict
                        # It could happen on multiple files drag'n drop
                        # starting with identical characters.
                        log.error(f"Delaying conflicted document: {doc_pair!r}")
                        self._postpone_pair(doc_pair, "Conflict")
                    elif exc.status == 500:
                        self.increase_error(doc_pair, "SERVER_ERROR", exception=exc)
                    else:
                        error = f"{handler_name}_http_error_{exc.status}"
                        self._handle_pair_handler_exception(doc_pair, error, exc)
                    continue
                except (ConnectionError, PairInterrupt, ParentNotSynced) as exc:
                    log.debug(
                        f"{type(exc).__name__} on {doc_pair!r}, wait 1s and requeue"
                    )
                    sleep(1)
                    self.engine.get_queue_manager().push(doc_pair)
                    continue
                except DuplicationDisabledError:
                    self.giveup_error(doc_pair, "DEDUP")
                    continue
                except CorruptedFile as exc:
                    self.increase_error(doc_pair, "CORRUPT", exception=exc)
                    continue
                except NotFound as exc:
                    log.debug(
                        f"The document or its parent does not exist anymore: {doc_pair!r}"
                    )
                    self.giveup_error(doc_pair, "NOT_FOUND", exception=exc)
                    continue
                except UnknownDigest as exc:
                    log.debug(
                        f"The document's digest has no corresponding algorithm: {doc_pair!r}"
                    )
                    self.giveup_error(doc_pair, "UNKNOWN_DIGEST", exception=exc)
                    continue
                except OSError as exc:
                    # Try to handle different kind of Windows error
                    error = getattr(exc, "winerror", exc.errno)

                    if error in {2, 3}:
                        """
                        WindowsError: [Error 2] The specified file is not found
                        WindowsError: [Error 3] The system cannot find the file specified
                        """
                        log.debug(f"The document does not exist anymore:{doc_pair!r}")
                        self._dao.remove_state(doc_pair)
                    elif error == 32:
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
                    elif error in {111, 121, 124, 206, 1223}:
                        """
                        WindowsError: [Error 111] ??? (seems related to deep
                        tree)
                        Cause: short paths are disabled on Windows

                        WindowsError: [Error 121] The source or destination
                        path exceeded or would exceed MAX_PATH.
                        Cause: short paths are disabled on Windows

                        WindowsError: [Error 124] The path in the source or
                        destination or both was invalid.
                        Cause: dealing with different drives, ie when the sync
                        folder is not on the same drive as Nuxeo Drive one

                        WindowsError: [Error 206] The filename or extension is
                        too long.
                        Cause: even the full short path is too long

                        OSError: Couldn't perform operation. Error code: 1223
                        Seems related to long paths
                        """
                        self._dao.remove_filter(
                            doc_pair.remote_parent_path + "/" + doc_pair.remote_ref
                        )
                        self.engine.fileDeletionErrorTooLong.emit(doc_pair)
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
                    continue
                except Exception as exc:
                    self._handle_pair_handler_exception(doc_pair, handler_name, exc)
                    continue
            except ThreadInterrupt:
                self.engine.get_queue_manager().push(doc_pair)
                raise
            except Exception as exc:
                log.exception("Pair error")
                self.increase_error(doc_pair, "EXCEPTION", exception=exc)
                raise exc
            finally:
                if soft_lock:
                    self._unlock_soft_path(soft_lock)
                self._dao.release_state(self.get_thread_id())
            self._interact()

    def _handle_pair_handler_exception(
        self, doc_pair: DocPair, handler_name: str, e: Exception
    ) -> None:
        if isinstance(e, OSError) and e.errno == 28:
            self.engine.noSpaceLeftOnDevice.emit()
            self.engine.suspend()
        log.exception("Unknown error")
        self.increase_error(doc_pair, f"SYNC_HANDLER_{handler_name}", exception=e)

    def _synchronize_conflicted(self, doc_pair: DocPair) -> None:
        if doc_pair.local_state == "moved" and doc_pair.remote_state in (
            "moved",
            "unknown",
        ):
            # Manual conflict resolution needed
            self._dao.set_conflict_state(doc_pair)

        # Auto-resolve conflict
        elif not doc_pair.folderish:
            if self.local.is_equal_digests(
                doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path
            ):
                log.debug("Auto-resolve conflict has digest are the same")
                self._dao.synchronize_state(doc_pair)
        elif self.local.get_remote_id(doc_pair.local_path) == doc_pair.remote_ref:
            log.debug("Auto-resolve conflict has folder has same remote_id")
            self._dao.synchronize_state(doc_pair)

    def _update_speed_metrics(self) -> None:
        action = Action.get_last_file_action()
        if action:
            duration = action.end_time - action.start_time
            # Too fast for clock resolution
            if duration <= 0:
                return
            speed = (action.size / duration) * 1000
            log.trace(f"Transfer speed {speed / 1024} ko/s")
            self._current_metrics["speed"] = speed

    def _synchronize_if_not_remotely_dirty(
        self, doc_pair: DocPair, remote_info: RemoteFileInfo = None
    ) -> None:
        if remote_info is not None and (
            remote_info.name != doc_pair.local_name
            or remote_info.digest != doc_pair.local_digest
        ):
            modified = self._dao.get_state_from_local(doc_pair.local_path)
            if modified:
                log.debug(
                    f"Forcing remotely_modified for pair={modified!r} "
                    f"with info={remote_info!r}"
                )
                self._synchronize_remotely_modified(modified)
            return

        # Force computation of local digest to catch local modifications
        dynamic_states = False
        if not doc_pair.folderish and not self.local.is_equal_digests(
            None, doc_pair.remote_digest, doc_pair.local_path
        ):
            # Note: setted 1st argument of is_equal_digests() to None
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

        self._dao.synchronize_state(doc_pair, dynamic_states=dynamic_states)

    def _synchronize_locally_modified(self, doc_pair: DocPair) -> None:
        fs_item_info = None
        if doc_pair.local_digest == UNACCESSIBLE_HASH:
            # Try to update
            info = self.local.get_info(doc_pair.local_path)
            log.trace(f"Modification of postponed local file: {doc_pair!r}")
            doc_pair.local_digest = info.get_digest()

            if doc_pair.local_digest == UNACCESSIBLE_HASH:
                self._postpone_pair(doc_pair, "Unaccessible hash")
                return
            self._dao.update_local_state(doc_pair, info, versioned=False, queue=False)

        if not self.local.is_equal_digests(
            doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path
        ):
            if doc_pair.remote_can_update:
                if doc_pair.local_digest == UNACCESSIBLE_HASH:
                    self._postpone_pair(doc_pair, "Unaccessible hash")
                    return
                log.debug(f"Updating remote document {doc_pair.local_name!r}")
                fs_item_info = self.remote.stream_update(
                    doc_pair.remote_ref,
                    self.local.abspath(doc_pair.local_path),
                    parent_fs_item_id=doc_pair.remote_parent_ref,
                    # Use remote name to avoid rename in case of duplicate
                    filename=doc_pair.remote_name,
                )
                self._dao.update_last_transfer(doc_pair.id, "upload")
                self._update_speed_metrics()
                self._dao.update_remote_state(doc_pair, fs_item_info, versioned=False)
                # TODO refresh_client
            else:
                log.debug(
                    f"Skip update of remote document {doc_pair.local_name!r} "
                    "as it is read-only."
                )
                if self.engine.local_rollback():
                    self.local.delete(doc_pair.local_path)
                    self._dao.mark_descendants_remotely_created(doc_pair)
                else:
                    log.debug(f"Set pair unsynchronized: {doc_pair!r}")
                    try:
                        fs_info: Optional[RemoteFileInfo] = self.remote.get_fs_info(
                            doc_pair.remote_ref
                        )
                    except NotFound:
                        fs_info = None

                    if fs_info is None or fs_info.lock_owner is None:
                        self._dao.unsynchronize_state(doc_pair, "READONLY")
                        self.engine.newReadonly.emit(doc_pair.local_name, None)
                    else:
                        self._dao.unsynchronize_state(doc_pair, "LOCKED")
                        self.engine.newLocked.emit(
                            doc_pair.local_name,
                            fs_info.lock_owner,
                            fs_info.lock_created,
                        )
                    self._handle_unsynchronized(doc_pair)
                return
        if fs_item_info is None:
            fs_item_info = self.remote.get_fs_info(doc_pair.remote_ref)
            self._dao.update_remote_state(doc_pair, fs_item_info, versioned=False)
        self._synchronize_if_not_remotely_dirty(doc_pair, remote_info=fs_item_info)

    def _get_normal_state_from_remote_ref(self, ref: str) -> Optional[DocPair]:
        # TODO Select the only states that is not a collection
        return self._dao.get_normal_state_from_remote(ref)

    def _postpone_pair(
        self, doc_pair: DocPair, reason: str = "", interval: int = None
    ) -> None:
        """ Wait 60 sec for it. """

        log.trace(f"Postpone action on document({reason}): {doc_pair!r}")
        doc_pair.error_count = 1
        self.engine.get_queue_manager().push_error(
            doc_pair, exception=None, interval=interval
        )

    def _synchronize_locally_resolved(self, doc_pair: DocPair) -> None:
        """ NXDRIVE-766: processes a locally resolved conflict. """
        self._synchronize_locally_created(doc_pair, overwrite=True)

    def _synchronize_locally_created(
        self, doc_pair: DocPair, overwrite: bool = False
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
                    log.debug(f"Ignoring generated tmp file: {name!r}")
                    return
                if doc_pair.error_count == 0:
                    # Save the error_count to not ignore next time
                    log.debug(f"Delaying generated tmp file like: {name!r}")
                    self.increase_error(doc_pair, "Can be a temporary file")
                    return

        remote_ref = self.local.get_remote_id(doc_pair.local_path)
        # Find the parent pair to find the ref of the remote folder to
        # create the document
        parent_pair = self._dao.get_state_from_local(doc_pair.local_parent_path)
        log.trace(f"Entered _synchronize_locally_created, parent_pair={parent_pair!r}")

        if parent_pair is None:
            # Try to get it from xattr
            log.trace("Fallback to xattr")
            if self.local.exists(doc_pair.local_parent_path):
                ref = self.local.get_remote_id(doc_pair.local_parent_path)
                if ref:
                    parent_pair = self._get_normal_state_from_remote_ref(ref)
                else:
                    parent_pair = None

        if parent_pair is None or not parent_pair.remote_ref:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            if parent_pair is not None and parent_pair.pair_state == "unsynchronized":
                self._dao.unsynchronize_state(doc_pair, "PARENT_UNSYNC")
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
                uid, raise_if_missing=False, fetch_parent_uid=False, use_trash=False
            )
            log.warning(
                f"This document {doc_pair!r} has remote_ref {remote_ref}, info={info!r}"
            )
            if not info:
                # The document has an invalid remote ID.
                # Continue the document creation after purging the ID.
                log.debug(f"Removing xattr(s) on {doc_pair.local_path!r}")
                func = ("remove_remote_id", "clean_xattr_folder_recursive")[
                    doc_pair.folderish
                ]
                getattr(self.local, func)(doc_pair.local_path)
                remote_ref = ""

        if remote_ref and info:
            try:
                if uid and info.is_trashed:
                    log.debug(f"Untrash from the client: {doc_pair!r}")
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
                    self._dao.update_remote_state(
                        doc_pair,
                        fs_item_info,
                        remote_parent_path=remote_parent_path,
                        versioned=False,
                    )
                    # Handle document modification - update the doc_pair
                    refreshed = self._dao.get_state_from_id(doc_pair.id)
                    if refreshed:
                        self._synchronize_locally_modified(refreshed)
                    return

                fs_item_info = self.remote.get_fs_info(remote_ref)
                log.trace(
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
                    self._dao.synchronize_state(doc_pair)
                    return
            except HTTPError as e:
                # undelete will fail if you dont have the rights
                if e.status != 403:
                    raise e
                log.trace(
                    "Create new document as current known document "
                    f"is not accessible: {remote_ref}"
                )
            except NotFound:
                # The document has an invalid remote ID.
                # It happens when locally untrashing a folder
                # containing files. Just ignore the error and proceed
                # to the document creation.
                log.debug(f"Removing xattr on {doc_pair.local_path!r}")
                self.local.remove_remote_id(doc_pair.local_path)

        parent_ref: str = parent_pair.remote_ref
        if parent_pair.remote_can_create_child:
            remote_parent_path = (
                parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
            )
            if doc_pair.folderish:
                log.debug(
                    f"Creating remote folder {name!r} "
                    f"in folder {parent_pair.remote_name!r}"
                )
                fs_item_info = self.remote.make_folder(
                    parent_ref, name, overwrite=overwrite
                )
                remote_ref = fs_item_info.uid
            else:
                # TODO Check if the file is already on the server with the
                # TODO good digest
                log.debug(
                    f"Creating remote document {name!r} "
                    f"in folder {parent_pair.remote_name!r}"
                )
                local_info = self.local.get_info(doc_pair.local_path)
                if local_info.size != doc_pair.size:
                    # Size has changed ( copy must still be running )
                    doc_pair.local_digest = UNACCESSIBLE_HASH
                    self._dao.update_local_state(
                        doc_pair, local_info, versioned=False, queue=False
                    )
                    self._postpone_pair(doc_pair, "Unaccessible hash")
                    return
                if doc_pair.local_digest == UNACCESSIBLE_HASH:
                    doc_pair.local_digest = local_info.get_digest()
                    log.trace(f"Creation of postponed local file: {doc_pair!r}")
                    self._dao.update_local_state(
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
                )
                remote_ref = fs_item_info.uid
                self._dao.update_last_transfer(doc_pair.id, "upload")
                self._update_speed_metrics()

            with self._dao._lock:
                remote_id_done = False
                # NXDRIVE-599: set as soon as possible the remote_id as
                # update_remote_state can crash with InterfaceError
                with suppress(NotFound):
                    self.local.set_remote_id(doc_pair.local_path, remote_ref)
                    remote_id_done = True
                self._dao.update_remote_state(
                    doc_pair,
                    fs_item_info,
                    remote_parent_path=remote_parent_path,
                    versioned=False,
                    queue=False,
                )
            log.trace(f"Put remote_ref in {remote_ref}")
            try:
                if not remote_id_done:
                    self.local.set_remote_id(doc_pair.local_path, remote_ref)
            except NotFound:
                new_pair = self._dao.get_state_from_id(doc_pair.id)
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
                self._dao.remove_state(doc_pair)
            else:
                log.debug(f"Set pair unsynchronized: {doc_pair!r}")
                self._dao.unsynchronize_state(doc_pair, "READONLY")
                self.engine.newReadonly.emit(
                    doc_pair.local_name, parent_pair.remote_name
                )
                self._handle_unsynchronized(doc_pair)

    def _synchronize_locally_deleted(self, doc_pair: DocPair) -> None:
        if not doc_pair.remote_ref:
            self._dao.remove_state(doc_pair)
            self._search_for_dedup(doc_pair)
            return

        if doc_pair.remote_can_delete:
            log.debug(
                "Deleting or unregistering remote document "
                f"{doc_pair.remote_name!r} ({doc_pair.remote_ref})"
            )
            if doc_pair.remote_state != "deleted":
                self.remote.delete(
                    doc_pair.remote_ref, parent_fs_item_id=doc_pair.remote_parent_ref
                )
            self._dao.remove_state(doc_pair)
        else:
            log.debug(
                f"{doc_pair.local_path!r} can not be remotely deleted: "
                "either it is readonly or it is a virtual folder that "
                "does not exist in the server hierarchy"
            )
            if doc_pair.remote_state != "deleted":
                log.debug(
                    f"Marking {doc_pair!r} as filter since remote document "
                    f"{doc_pair.remote_name!r} ({doc_pair.remote_ref}]) "
                    "can not be deleted"
                )
                self._dao.remove_state(doc_pair)
                self._dao.add_filter(
                    doc_pair.remote_parent_path + "/" + doc_pair.remote_ref
                )
                self.engine.deleteReadonly.emit(doc_pair.local_name)
        self._search_for_dedup(doc_pair)

    def _synchronize_locally_moved_remotely_modified(self, doc_pair: DocPair) -> None:
        self._synchronize_locally_moved(doc_pair, update=False)
        refreshed_pair = self._dao.get_state_from_id(doc_pair.id)
        if refreshed_pair:
            self._synchronize_remotely_modified(refreshed_pair)

    def _synchronize_locally_moved_created(self, doc_pair: DocPair) -> None:
        doc_pair.remote_ref = ""
        self._synchronize_locally_created(doc_pair)

    def _synchronize_locally_moved(
        self, doc_pair: DocPair, update: bool = True
    ) -> None:
        """
        A file has been moved locally, and an error occurs when tried to
        move on the server.
        """

        remote_info = None
        self._search_for_dedup(doc_pair, doc_pair.remote_name)
        if doc_pair.local_name != doc_pair.remote_name:
            try:
                if not doc_pair.remote_can_rename:
                    self._handle_failed_remote_rename(doc_pair, doc_pair)
                    return

                log.debug(f"Renaming remote document according to local {doc_pair!r}")
                remote_info = self.remote.rename(
                    doc_pair.remote_ref, doc_pair.local_name
                )
                self._refresh_remote(doc_pair, remote_info=remote_info)
            except Exception as e:
                log.debug(str(e))
                self._handle_failed_remote_rename(doc_pair, doc_pair)
                return

        parent_ref = self.local.get_remote_id(doc_pair.local_parent_path)
        if not parent_ref:
            parent_pair = self._dao.get_state_from_local(doc_pair.local_parent_path)
            parent_ref = parent_pair.remote_ref if parent_pair else ""
        else:
            parent_pair = self._get_normal_state_from_remote_ref(parent_ref)

        if not parent_pair:
            raise ValueError("Should have a parent pair")

        if parent_ref != doc_pair.remote_parent_ref:
            if (
                doc_pair.remote_can_delete
                and not parent_pair.pair_state == "unsynchronized"
                and parent_pair.remote_can_create_child
            ):
                log.debug(f"Moving remote file according to local : {doc_pair!r}")
                # Bug if move in a parent with no rights / partial move
                # if rename at the same time
                parent_path = (
                    parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
                )
                remote_info = self.remote.move(
                    doc_pair.remote_ref, parent_pair.remote_ref
                )
                self._dao.update_remote_state(
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

    def _synchronize_deleted_unknown(self, doc_pair: DocPair, *_) -> None:
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
            f"Detected inconsistent doc pair {doc_pair!r}, deleting it hoping thev"
            "synchronizer will fix this case at next iteration"
        )
        self._dao.remove_state(doc_pair)

    @staticmethod
    def _get_temporary_file(file_path: Path) -> Path:
        return file_path.with_name(
            DOWNLOAD_TMP_FILE_PREFIX + file_path.name + DOWNLOAD_TMP_FILE_SUFFIX
        )

    def _download_content(self, doc_pair: DocPair, file_path: Path) -> Path:
        # Check if the file is already on the HD
        pair = self._dao.get_valid_duplicate_file(doc_pair.remote_digest)
        if pair:
            file_out = self._get_temporary_file(file_path)
            locker = unlock_path(file_out)
            try:
                shutil.copy(self.local.abspath(pair.local_path), file_out)
            finally:
                lock_path(file_out, locker)
            return file_out

        tmp_file = self.remote.stream_content(
            doc_pair.remote_ref, file_path, parent_fs_item_id=doc_pair.remote_parent_ref
        )
        self._update_speed_metrics()
        return tmp_file

    def _update_remotely(self, doc_pair: DocPair, is_renaming: bool) -> None:
        os_path = self.local.abspath(doc_pair.local_path)
        if is_renaming:
            new_os_path = os_path.with_name(safe_filename(doc_pair.remote_name))
            log.debug(f"Replacing local file {os_path!r} by {new_os_path!r}")
        else:
            new_os_path = os_path
        log.debug(f"Updating content of local file {os_path!r}")
        self.tmp_file: Optional[Path] = self._download_content(doc_pair, new_os_path)

        # Delete original file and rename tmp file
        remote_id = self.local.get_remote_id(doc_pair.local_path)
        self.local.delete_final(doc_pair.local_path)
        tmp_path = self.local.get_path(self.tmp_file)
        if remote_id:
            self.local.set_remote_id(tmp_path, doc_pair.remote_ref)
        updated_info = self.local.rename(tmp_path, doc_pair.remote_name)

        # Set the modification time of the file to the server one
        self.local.change_file_date(
            updated_info.filepath, mtime=doc_pair.last_remote_updated
        )

        doc_pair.local_digest = updated_info.get_digest()
        self._dao.update_last_transfer(doc_pair.id, "download")
        self._refresh_local_state(doc_pair, updated_info)

    def _search_for_dedup(self, doc_pair: DocPair, name: str = None) -> None:
        if name is None:
            name = doc_pair.local_name
        # Auto resolve duplicate
        log.debug(f"Search for dupe pair with {name!r} {doc_pair.remote_parent_ref}")
        dupe_pair = self._dao.get_dedupe_pair(
            name, doc_pair.remote_parent_ref, doc_pair.id
        )
        if dupe_pair is not None:
            log.debug(f"Dupe pair found {dupe_pair!r}")
            self._dao.reset_error(dupe_pair)

    def _synchronize_remotely_modified(self, doc_pair: DocPair) -> None:
        self.tmp_file = None
        is_renaming = safe_filename(doc_pair.remote_name) != doc_pair.local_name
        try:
            if doc_pair.local_digest is not None and not self.local.is_equal_digests(
                doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path
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
                    self._postpone_pair(doc_pair, reason="PARENT_UNSYNC")
                    return

                if not is_move and not is_renaming:
                    log.debug(
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
                            log.debug(f"Wrong guess for move: {doc_pair!r}")
                            self._is_remote_move(doc_pair)
                            self._dao.synchronize_state(doc_pair)

                        log.debug(
                            f"DOC_PAIR({doc_pair!r}): "
                            f"old_path[exists={self.local.exists(old_path)!r},"
                            f"id={self.local.get_remote_id(old_path)!r}]: {old_path!r},"
                            f" new_path[exists={self.local.exists(new_path)!r}, "
                            f"id={self.local.get_remote_id(new_path)!r}]: {new_path!r}"
                        )

                        old_path_abs = self.local.abspath(old_path)
                        new_path_abs = self.local.abspath(new_path)
                        log.debug(
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
                        self._dao.update_remote_parent_path(doc_pair, new_parent_path)
                    else:
                        log.debug(
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
                        self._dao.update_local_parent_path(
                            doc_pair, updated_info.path.name, new_path
                        )
                        self._search_for_dedup(doc_pair)
                        self._refresh_local_state(doc_pair, updated_info)
            self._handle_readonly(doc_pair)
            self._dao.synchronize_state(doc_pair)
        finally:
            if doc_pair.folderish:
                # Release folder lock in any case
                self.engine.release_folder_lock()

        if not self.tmp_file:
            return
        with suppress(OSError):
            self.tmp_file.unlink()

    def _synchronize_remotely_created(self, doc_pair: DocPair) -> None:
        name = doc_pair.remote_name
        # Find the parent pair to find the path of the local folder to
        # create the document into
        parent_pair = self._get_normal_state_from_remote_ref(doc_pair.remote_parent_ref)
        if parent_pair is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ValueError(
                f"Could not find parent folder of doc {name!r} "
                f"({doc_pair.remote_ref!r}) folder"
            )

        if parent_pair.local_path is None:
            if parent_pair.pair_state == "unsynchronized":
                self._dao.unsynchronize_state(doc_pair, "PARENT_UNSYNC")
                self._handle_unsynchronized(doc_pair)
                return

            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ParentNotSynced(name, doc_pair.remote_ref)

        remote_path = f"{doc_pair.remote_parent_path}/{doc_pair.remote_ref}"
        if self.remote.is_filtered(remote_path):
            nature = ("file", "folder")[doc_pair.folderish]
            log.trace(f"Skip filtered {nature} {doc_pair.local_path!r}")
            self._dao.remove_state(doc_pair)
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
                # created files queue may have obsolete informations.
                # To prevent inconsistency, we remotely remove the pair.
                self._synchronize_remotely_deleted(doc_pair)
                return
        else:
            path = doc_pair.local_path
            remote_ref = self.local.get_remote_id(doc_pair.local_path)
            if remote_ref and remote_ref == doc_pair.remote_ref:
                log.debug(
                    f"remote_ref (xattr) = {remote_ref}, "
                    f"doc_pair.remote_ref = {doc_pair.remote_ref} "
                    "=> setting conflicted state"
                )
                # Set conflict state for now
                # TO_REVIEW May need to overwrite
                self._dao.set_conflict_state(doc_pair)
                return
            elif remote_ref:
                # Case of several documents with same name
                # or case insensitive hard drive
                path = self._create_remotely(doc_pair, parent_pair, name)

        self.local.set_remote_id(path, doc_pair.remote_ref)
        if path != doc_pair.local_path and doc_pair.folderish:
            # Update childs
            self._dao.update_local_parent_path(doc_pair, path.name, path.parent)
        self._refresh_local_state(doc_pair, self.local.get_info(path))
        self._handle_readonly(doc_pair)
        if not self._dao.synchronize_state(doc_pair):
            log.debug(
                f"Pair is not in synchronized state (version issue): {doc_pair!r}"
            )
            # Need to check if this is a remote or local change
            new_pair = self._dao.get_state_from_id(doc_pair.id)
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
        self, doc_pair: DocPair, parent_pair: DocPair, name: str
    ) -> Path:
        # TODO Shared this locking system / Can have concurrent lock
        local_parent_path = parent_pair.local_path
        self._unlock_readonly(local_parent_path)
        try:
            if doc_pair.folderish:
                log.debug(
                    f"Creating local folder {name!r} "
                    f"in {self.local.abspath(local_parent_path)!r}"
                )
                return self.local.make_folder(local_parent_path, name)

            path, os_path, name = self.local.get_new_file(local_parent_path, name)
            log.debug(
                f"Creating local file {name!r} "
                f"in {self.local.abspath(local_parent_path)!r}"
            )
            tmp_file = self._download_content(doc_pair, os_path)
            tmp_path = self.local.get_path(tmp_file)

            # Set remote id on TMP file already
            self.local.set_remote_id(tmp_path, doc_pair.remote_ref)

            # Rename TMP file
            info = self.local.rename(tmp_path, name)

            # Set the modification time of the file to the server one
            # (until NXDRIVE-1130 is done, the creation time is also
            # the last modified time)
            mtime = doc_pair.last_remote_updated
            ctime = doc_pair.creation_date
            self.local.change_file_date(info.filepath, mtime=mtime, ctime=ctime)

            self._dao.update_last_transfer(doc_pair.id, "download")

            # Clean-up the TMP file
            with suppress(OSError):
                tmp_file.unlink()

            return path
        finally:
            self._lock_readonly(local_parent_path)

    def _synchronize_remotely_deleted(self, doc_pair: DocPair) -> None:
        try:
            if doc_pair.local_state == "unsynchronized":
                self._dao.remove_state(doc_pair)
                return
            if doc_pair.local_state != "deleted":
                log.debug(
                    f"Deleting locally {self.local.abspath(doc_pair.local_path)!r}"
                )
                if doc_pair.folderish:
                    self.engine.set_local_folder_lock(doc_pair.local_path)
                else:
                    # Check for nxpart to clean up
                    file_out = self._get_temporary_file(
                        self.local.abspath(doc_pair.local_path)
                    )
                    if file_out.exists():
                        file_out.unlink()

                if not self.engine.use_trash():
                    # Force the complete file deletion
                    self.local.delete_final(doc_pair.local_path)
                else:
                    self.local.delete(doc_pair.local_path)
            self._dao.remove_state(doc_pair)
            self._search_for_dedup(doc_pair)
        finally:
            if doc_pair.folderish:
                self.engine.release_folder_lock()

    def _synchronize_unknown_deleted(self, doc_pair: DocPair) -> None:
        # Somehow a pair can get to an inconsistent state:
        # <local_state='unknown', remote_state='deleted', pair_state='unknown'>
        # Even though we are not able to figure out how this can happen we
        # need to handle this case to put the database back to a consistent
        # state.
        # This is tracked by https://jira.nuxeo.com/browse/NXP-13216
        log.debug("Inconsistency should not happens anymore")
        log.debug(
            f"Detected inconsistent doc pair {doc_pair!r}, deleting it hoping the "
            "synchronizer will fix this case at next iteration"
        )
        self._dao.remove_state(doc_pair)
        if doc_pair.local_path:
            log.debug(
                f"Since the local path is set: {doc_pair.local_path!r}, "
                "the synchronizer will probably consider this as a local creation at "
                "next iteration and create the file or folder remotely"
            )
        else:
            log.debug(
                "Since the local path is _not_ set, the synchronizer will "
                "probably do nothing at next iteration"
            )

    def _refresh_remote(
        self, doc_pair: DocPair, remote_info: RemoteFileInfo = None
    ) -> None:
        if remote_info is None:
            remote_info = self.remote.get_fs_info(doc_pair.remote_ref)
        if remote_info:
            self._dao.update_remote_state(
                doc_pair, remote_info, versioned=False, queue=False
            )

    def _refresh_local_state(self, doc_pair: DocPair, local_info: FileInfo) -> None:
        if doc_pair.local_digest is None and not doc_pair.folderish:
            doc_pair.local_digest = local_info.get_digest()
        self._dao.update_local_state(doc_pair, local_info, versioned=False, queue=False)
        doc_pair.local_path = local_info.path
        doc_pair.local_name = local_info.path.name
        doc_pair.last_local_updated = local_info.last_modification_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def _is_remote_move(self, doc_pair: DocPair) -> Tuple[bool, Optional[DocPair]]:
        local_parent = self._dao.get_state_from_local(doc_pair.local_parent_path)
        remote_parent = self._get_normal_state_from_remote_ref(
            doc_pair.remote_parent_ref
        )
        state = bool(
            local_parent and remote_parent and local_parent.id != remote_parent.id
        )
        log.debug(
            f"is_remote_move={state!r}: name={doc_pair.remote_name!r}, "
            f"local={local_parent!r}, remote={remote_parent!r}"
        )
        return state, remote_parent

    def _handle_failed_remote_move(
        self, source_pair: DocPair, target_pair: DocPair
    ) -> None:
        pass

    def _handle_failed_remote_rename(
        self, source_pair: DocPair, target_pair: DocPair
    ) -> bool:
        """  Return False if an error occurs. """

        if not self.engine.local_rollback(force=WINDOWS):
            return False

        log.error(
            f"Renaming {target_pair.remote_name!r} "
            f"to {target_pair.local_name!r} canceled"
        )

        try:
            info = self.local.rename(target_pair.local_path, target_pair.remote_name)
            self._dao.update_local_state(source_pair, info, queue=False)
            if source_pair != target_pair:
                if target_pair.folderish:
                    # Remove "new" created tree
                    pairs = self._dao.get_states_from_partial_local(
                        target_pair.local_path
                    )
                    for pair in pairs:
                        self._dao.remove_state(pair)
                    pairs = self._dao.get_states_from_partial_local(
                        source_pair.local_path
                    )
                    for pair in pairs:
                        self._dao.synchronize_state(pair)
                else:
                    self._dao.remove_state(target_pair)
            self._dao.synchronize_state(source_pair)
            return True
        except:
            log.exception("Cannot rollback local modification")
        return False

    def _handle_unsynchronized(self, doc_pair: DocPair) -> None:
        # Used for overwrite
        pass

    def _handle_readonly(self, doc_pair: DocPair) -> None:
        # Don't use readonly on folder for win32 and on Locally Edited
        if doc_pair.folderish and WINDOWS:
            return

        if doc_pair.is_readonly():
            log.debug(f"Setting {doc_pair.local_path!r} as readonly")
            self.local.set_readonly(doc_pair.local_path)
        else:
            log.debug(f"Unsetting {doc_pair.local_path!r} as readonly")
            self.local.unset_readonly(doc_pair.local_path)
