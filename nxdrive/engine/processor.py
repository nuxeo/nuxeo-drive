# coding: utf-8
import os
import shutil
import socket
import sqlite3
from contextlib import suppress
from logging import getLogger
from threading import Lock
from time import sleep
from typing import Any, Callable, Optional, Tuple

from PyQt5.QtCore import pyqtSignal
from nuxeo.exceptions import CorruptedFile, HTTPError
from requests import ConnectionError

from .activity import Action
from .workers import EngineWorker
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
)
from ..objects import DocPair, NuxeoDocumentInfo
from ..utils import (
    current_milli_time,
    is_generated_tmp_file,
    lock_path,
    safe_filename,
    unlock_path,
)

__all__ = ("Processor",)

log = getLogger(__name__)


class Processor(EngineWorker):
    pairSync = pyqtSignal(object)
    path_locker = Lock()
    soft_locks = dict()
    readonly_locks = dict()
    readonly_locker = Lock()

    def __init__(self, engine: "Engine", item_getter: Callable, **kwargs: Any) -> None:
        super().__init__(engine, engine.get_dao(), **kwargs)
        self._current_doc_pair = None
        self._get_item = item_getter
        self.engine = engine
        self.local = self.engine.local
        self.remote = self.engine.remote

    def _unlock_soft_path(self, path: str) -> None:
        log.trace("Soft unlocking %r", path)
        path = path.lower()
        with Processor.path_locker:
            if self.engine.uid not in Processor.soft_locks:
                Processor.soft_locks[self.engine.uid] = dict()
            else:
                Processor.soft_locks[self.engine.uid].pop(path, None)

    def _unlock_readonly(self, path: str) -> None:
        with Processor.readonly_locker:
            if self.engine.uid not in Processor.readonly_locks:
                Processor.readonly_locks[self.engine.uid] = dict()

            if path in Processor.readonly_locks[self.engine.uid]:
                log.trace("Readonly unlock: increase count on %r", path)
                Processor.readonly_locks[self.engine.uid][path][0] += 1
            else:
                lock = self.local.unlock_ref(path)
                log.trace("Readonly unlock: unlock on %r with %d", path, lock)
                Processor.readonly_locks[self.engine.uid][path] = [1, lock]

    def _lock_readonly(self, path: str) -> None:
        with Processor.readonly_locker:
            if self.engine.uid not in Processor.readonly_locks:
                Processor.readonly_locks[self.engine.uid] = dict()

            if path not in Processor.readonly_locks[self.engine.uid]:
                log.debug("Readonly lock: cannot find reference on %r", path)
                return

            Processor.readonly_locks[self.engine.uid][path][0] -= 1
            log.trace(
                "Readonly lock: update lock count on %r to %d",
                path,
                Processor.readonly_locks[self.engine.uid][path][0],
            )

            if Processor.readonly_locks[self.engine.uid][path][0] <= 0:
                self.local.lock_ref(
                    path, Processor.readonly_locks[self.engine.uid][path][1]
                )
                log.trace(
                    "Readonly lock: relocked %r with %d",
                    path,
                    Processor.readonly_locks[self.engine.uid][path][1],
                )
                del Processor.readonly_locks[self.engine.uid][path]

    def _lock_soft_path(self, path: str) -> str:
        log.trace("Soft locking %r", path)
        path = path.lower()
        with Processor.path_locker:
            if self.engine.uid not in Processor.soft_locks:
                Processor.soft_locks[self.engine.uid] = dict()
            if path in Processor.soft_locks[self.engine.uid]:
                raise PairInterrupt
            else:
                Processor.soft_locks[self.engine.uid][path] = True
                return path

    def get_current_pair(self) -> NuxeoDocumentInfo:
        return self._current_doc_pair

    @staticmethod
    def check_pair_state(doc_pair: NuxeoDocumentInfo) -> bool:
        """ Eliminate unprocessable states. """

        if any(
            (
                doc_pair.pair_state in ("synchronized", "unsynchronized"),
                doc_pair.pair_state.startswith("parent_"),
            )
        ):
            log.trace("Skip pair in non-processable state: %r", doc_pair)
            return False
        return True

    def _execute(self) -> None:
        while "There are items in the queue":
            item = self._get_item()
            if not item:
                break

            try:
                doc_pair = self._dao.acquire_state(self._thread_id, item.id)
            except sqlite3.OperationalError:
                state = self._dao.get_state_from_id(item.id)
                if state:
                    if (
                        WINDOWS
                        and state.pair_state == "locally_moved"
                        and not state.remote_can_rename
                    ):
                        log.debug(
                            "A local rename on a read-only folder is"
                            " allowed on Windows, but it should not."
                            " Skipping."
                        )
                        continue

                    log.trace("Cannot acquire state for item %r (%r)", item, state)
                    self._postpone_pair(item, "Pair in use", interval=3)
                continue

            if not doc_pair:
                log.trace("Did not acquire state, dropping %r", item)
                continue

            soft_lock = None
            try:
                # In case of duplicate we remove the local_path as it
                # has conflict
                if doc_pair.local_path == "":
                    doc_pair.local_path = os.path.join(
                        doc_pair.local_parent_path, doc_pair.remote_name
                    )
                    log.trace("Re-guess local_path from duplicate: %r", doc_pair)

                log.debug("Executing processor on %r(%d)", doc_pair, doc_pair.version)
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
                        if finder_info is not None and "brokMACS" in finder_info:
                            log.trace("Skip as pair is in use by Finder: %r", doc_pair)
                            self._postpone_pair(
                                doc_pair, "Finder using file", interval=3
                            )
                            continue

                # TODO Update as the server dont take hash to avoid conflict yet
                if (
                    doc_pair.pair_state.startswith("locally")
                    and doc_pair.remote_ref is not None
                ):
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

                        doc_pair = self._dao.get_state_from_id(doc_pair.id)
                        if not doc_pair or not self.check_pair_state(doc_pair):
                            continue
                    except NotFound:
                        doc_pair.remote_ref = None

                # NXDRIVE-842: parent is in disabled duplication error
                parent_pair = self._get_normal_state_from_remote_ref(
                    doc_pair.remote_parent_ref
                )
                if parent_pair and parent_pair.last_error == "DEDUP":
                    continue

                parent_path = doc_pair.local_parent_path
                if parent_path == "":
                    parent_path = "/"

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

                handler_name = "_synchronize_" + doc_pair.pair_state
                sync_handler = getattr(self, handler_name, None)
                if not sync_handler:
                    log.debug(
                        "Unhandled pair_state %r for %r", doc_pair.pair_state, doc_pair
                    )
                    self.increase_error(doc_pair, "ILLEGAL_STATE")
                    continue

                Action(handler_name)
                self._current_metrics = {
                    "handler": doc_pair.pair_state,
                    "start_time": current_milli_time(),
                }
                log.trace("Calling %s() on doc pair %r", handler_name, doc_pair)

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
                        log.debug("The document does not exist anymore: %r", doc_pair)
                        self._dao.remove_state(doc_pair)
                    elif exc.status == 409:  # Conflict
                        # It could happen on multiple files drag'n drop
                        # starting with identical characters.
                        log.error("Delaying conflicted document: %r", doc_pair)
                        self._postpone_pair(doc_pair, "Conflict")
                    else:
                        self._handle_pair_handler_exception(doc_pair, handler_name, exc)
                    continue
                except (
                    ConnectionError,
                    socket.error,
                    PairInterrupt,
                    ParentNotSynced,
                ) as exc:
                    # socket.error for SSLError
                    log.error(
                        "%s on %r, wait 1s and requeue", type(exc).__name__, doc_pair
                    )
                    sleep(1)
                    self.engine.get_queue_manager().push(doc_pair)
                    continue
                except DuplicationDisabledError:
                    self.giveup_error(doc_pair, "DEDUP")
                    log.debug("Removing local_path on %r", doc_pair)
                    self._dao.remove_local_path(doc_pair.id)
                    continue
                except CorruptedFile as exc:
                    self.increase_error(doc_pair, "CORRUPT", exception=exc)
                    continue
                except NotFound as exc:
                    log.debug(
                        "The document or its parent does " "not exist anymore: %r",
                        doc_pair,
                    )
                    self.giveup_error(doc_pair, "NOT_FOUND", exception=exc)
                    continue
                except OSError as exc:
                    # Try to handle different kind of Windows error
                    error = getattr(exc, "winerror", exc.errno)

                    if error == 2:
                        """
                        WindowsError: [Error 2] The specified file is not found
                        """
                        log.debug("The document does not exist anymore: %r", doc_pair)
                        self._dao.remove_state(doc_pair)
                    elif error == 32:
                        """
                        WindowsError: [Error 32] The process cannot access the
                        file because it is being used by another process
                        """
                        log.info(
                            "Document used by another software, delaying"
                            " action(%s) on %r, ref=%r",
                            doc_pair.pair_state,
                            doc_pair.local_path,
                            doc_pair.remote_ref,
                        )
                        self.engine.errorOpenedFile.emit(doc_pair)
                        self._postpone_pair(doc_pair, "Used by another process")
                    elif error in (111, 121, 124, 206, 1223):
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
                    elif getattr(exc, "trash_issue", False):
                        """
                        Special value to handle trash issues from filters on
                        Windows when there is one or more files opened by
                        another software blocking any action.
                        """
                        doc_pair.trash_issue = True
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
                self._dao.release_state(self._thread_id)
            self._interact()

    def _handle_pair_handler_exception(
        self, doc_pair: NuxeoDocumentInfo, handler_name: str, e: Exception
    ) -> None:
        if isinstance(e, OSError) and e.errno == 28:
            self.engine.noSpaceLeftOnDevice.emit()
            self.engine.suspend()
        log.exception("Unknown error")
        self.increase_error(doc_pair, "SYNC_HANDLER_%s" % handler_name, exception=e)

    def _synchronize_conflicted(self, doc_pair: NuxeoDocumentInfo) -> None:
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
            log.trace("Transfer speed %d ko/s", speed / 1024)
            self._current_metrics["speed"] = speed

    def _synchronize_if_not_remotely_dirty(
        self, doc_pair: NuxeoDocumentInfo, remote_info: Optional[NuxeoDocumentInfo]
    ) -> None:
        if remote_info is not None and (
            remote_info.name != doc_pair.local_name
            or remote_info.digest != doc_pair.local_digest
        ):
            doc_pair = self._dao.get_state_from_local(doc_pair.local_path)
            log.debug(
                "Forcing remotely_modified for pair=%r with info=%r",
                doc_pair,
                remote_info,
            )
            self._synchronize_remotely_modified(doc_pair)
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

    def _synchronize_locally_modified(self, doc_pair: NuxeoDocumentInfo) -> None:
        fs_item_info = None
        if doc_pair.local_digest == UNACCESSIBLE_HASH:
            # Try to update
            info = self.local.get_info(doc_pair.local_path)
            log.trace("Modification of postponed local file: %r", doc_pair)
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
                log.debug("Updating remote document %r", doc_pair.local_name)
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
                    "Skip update of remote document %r as " "it is read-only.",
                    doc_pair.local_name,
                )
                if self.engine.local_rollback():
                    self.local.delete(doc_pair.local_path)
                    self._dao.mark_descendants_remotely_created(doc_pair)
                else:
                    log.debug("Set pair unsynchronized: %r", doc_pair)
                    info = self.remote.get_fs_info(
                        doc_pair.remote_ref, raise_if_missing=False
                    )
                    if info is None or info.lock_owner is None:
                        self._dao.unsynchronize_state(doc_pair, "READONLY")
                        self.engine.newReadonly.emit(doc_pair.local_name, None)
                    else:
                        self._dao.unsynchronize_state(doc_pair, "LOCKED")
                        self.engine.newLocked.emit(
                            doc_pair.local_name, info.lock_owner, info.lock_created
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
        self,
        doc_pair: NuxeoDocumentInfo,
        reason: str = "",
        interval: Optional[int] = None,
    ) -> None:
        """ Wait 60 sec for it. """

        log.trace("Postpone action on document(%s): %r", reason, doc_pair)
        doc_pair.error_count = 1
        self.engine.get_queue_manager().push_error(
            doc_pair, exception=None, interval=interval
        )

    def _synchronize_locally_resolved(self, doc_pair: NuxeoDocumentInfo) -> None:
        """ NXDRIVE-766: processes a locally resolved conflict. """
        self._synchronize_locally_created(doc_pair, overwrite=True)

    def _synchronize_locally_created(
        self, doc_pair: NuxeoDocumentInfo, overwrite: bool = False
    ) -> None:
        """
        :param bool overwrite: Allows to overwrite an existing document
                               with the same title on the server.
        """

        name = os.path.basename(doc_pair.local_path)
        if not doc_pair.folderish:
            ignore, delay = is_generated_tmp_file(name)
            if ignore:
                # Might be a tierce software temporary file
                if not delay:
                    log.debug("Ignoring generated tmp file: %r", name)
                    return
                if doc_pair.error_count == 0:
                    # Save the error_count to not ignore next time
                    log.debug("Delaying generated tmp file like: %r", name)
                    self.increase_error(doc_pair, "Can be a temporary file")
                    return

        remote_ref = self.local.get_remote_id(doc_pair.local_path)
        # Find the parent pair to find the ref of the remote folder to
        # create the document
        parent_pair = self._dao.get_state_from_local(doc_pair.local_parent_path)
        log.trace("Entered _synchronize_locally_created, parent_pair = %r", parent_pair)

        if parent_pair is None:
            # Try to get it from xattr
            log.trace("Fallback to xattr")
            if self.local.exists(doc_pair.local_parent_path):
                parent_ref = self.local.get_remote_id(doc_pair.local_parent_path)
                parent_pair = self._get_normal_state_from_remote_ref(parent_ref)

        if parent_pair is None or parent_pair.remote_ref is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            if parent_pair is not None and parent_pair.pair_state == "unsynchronized":
                self._dao.unsynchronize_state(doc_pair, "PARENT_UNSYNC")
                self._handle_unsynchronized(doc_pair)
                return
            raise ParentNotSynced(doc_pair.local_path, doc_pair.local_parent_path)

        uid = info = None
        if remote_ref and "#" in remote_ref:
            # Verify it is not already synced elsewhere (a missed move?)
            # If same hash don't do anything and reconcile
            uid = remote_ref.split("#")[-1]
            info = self.remote.get_info(
                uid, raise_if_missing=False, fetch_parent_uid=False, use_trash=False
            )
            log.warning(
                "This document %r has remote_ref %s, info=%r",
                doc_pair,
                remote_ref,
                info,
            )
            if not info:
                # The document has an invalid remote ID.
                # Continue the document creation after purging the ID.
                log.debug("Removing xattr(s) on %r", doc_pair.local_path)
                func = ("remove_remote_id", "clean_xattr_folder_recursive")[
                    doc_pair.folderish
                ]
                getattr(self.local, func)(doc_pair.local_path)
                remote_ref = None

        if remote_ref:
            try:
                if info.is_trashed:
                    log.debug("Untrash from the client: %r", doc_pair)
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
                    doc_pair = self._dao.get_state_from_id(doc_pair.id)
                    self._synchronize_locally_modified(doc_pair)
                    return

                fs_item_info = self.remote.get_fs_info(remote_ref)
                log.trace(
                    "Compare parents: %r | %r",
                    fs_item_info.parent_uid,
                    parent_pair.remote_ref,
                )
                # Document exists on the server
                if (
                    parent_pair.remote_ref is not None
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
                            "Document is already on the server, "
                            "should not create: %r | %r",
                            doc_pair,
                            fs_item_info,
                        )
                    self._dao.synchronize_state(doc_pair)
                    return
            except HTTPError as e:
                # undelete will fail if you dont have the rights
                if e.status != 403:
                    raise e
                log.trace(
                    "Create new document as current known document"
                    " is not accessible: %s",
                    remote_ref,
                )
            except NotFound:
                # The document has an invalid remote ID.
                # It happens when locally untrashing a folder
                # containing files. Just ignore the error and proceed
                # to the document creation.
                log.debug("Removing xattr on %r", doc_pair.local_path)
                self.local.remove_remote_id(doc_pair.local_path)

        parent_ref = parent_pair.remote_ref
        if parent_pair.remote_can_create_child:
            remote_parent_path = (
                parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
            )
            if doc_pair.folderish:
                log.debug(
                    "Creating remote folder %r in folder %r",
                    name,
                    parent_pair.remote_name,
                )
                fs_item_info = self.remote.make_folder(
                    parent_ref, name, overwrite=overwrite
                )
                remote_ref = fs_item_info.uid
            else:
                # TODO Check if the file is already on the server with the
                # TODO good digest
                log.debug(
                    "Creating remote document %r in folder %r",
                    name,
                    parent_pair.remote_name,
                )
                info = self.local.get_info(doc_pair.local_path)
                if info.size != doc_pair.size:
                    # Size has changed ( copy must still be running )
                    doc_pair.local_digest = UNACCESSIBLE_HASH
                    self._dao.update_local_state(
                        doc_pair, info, versioned=False, queue=False
                    )
                    self._postpone_pair(doc_pair, "Unaccessible hash")
                    return
                if doc_pair.local_digest == UNACCESSIBLE_HASH:
                    doc_pair.local_digest = info.get_digest()
                    log.trace("Creation of postponed local file: %r", doc_pair)
                    self._dao.update_local_state(
                        doc_pair, info, versioned=False, queue=False
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
            log.trace("Put remote_ref in %s", remote_ref)
            try:
                if not remote_id_done:
                    self.local.set_remote_id(doc_pair.local_path, remote_ref)
            except NotFound:
                new_pair = self._dao.get_state_from_id(doc_pair.id)
                # File has been moved during creation
                if new_pair.local_path != doc_pair.local_path:
                    self.local.set_remote_id(new_pair.local_path, remote_ref)
                    self._synchronize_locally_moved(new_pair, update=False)
                    return
            self._synchronize_if_not_remotely_dirty(doc_pair, remote_info=fs_item_info)
        else:
            child_type = "folder" if doc_pair.folderish else "file"
            log.warning(
                "Will not synchronize %s %r created in"
                " local folder %r since it is readonly",
                child_type,
                doc_pair.local_name,
                parent_pair.local_name,
            )
            if doc_pair.folderish:
                doc_pair.remote_can_create_child = False
            if self.engine.local_rollback():
                self.local.delete(doc_pair.local_path)
                self._dao.remove_state(doc_pair)
            else:
                log.debug("Set pair unsynchronized: %r", doc_pair)
                self._dao.unsynchronize_state(doc_pair, "READONLY")
                self.engine.newReadonly.emit(
                    doc_pair.local_name, parent_pair.remote_name
                )
                self._handle_unsynchronized(doc_pair)

    def _synchronize_locally_deleted(self, doc_pair: NuxeoDocumentInfo) -> None:
        if not doc_pair.remote_ref:
            self._dao.remove_state(doc_pair)
            self._search_for_dedup(doc_pair)
            return

        if doc_pair.remote_can_delete:
            log.debug(
                "Deleting or unregistering remote document %r (%s)",
                doc_pair.remote_name,
                doc_pair.remote_ref,
            )
            if doc_pair.remote_state != "deleted":
                self.remote.delete(
                    doc_pair.remote_ref, parent_fs_item_id=doc_pair.remote_parent_ref
                )
            self._dao.remove_state(doc_pair)
        else:
            log.debug(
                "%r can not be remotely deleted: either it is readonly "
                "or it is a virtual folder that does not exist "
                "in the server hierarchy",
                doc_pair.local_path,
            )
            if doc_pair.remote_state != "deleted":
                log.debug(
                    "Marking %r as filter since remote document %r (%s) "
                    "can not be deleted",
                    doc_pair,
                    doc_pair.remote_name,
                    doc_pair.remote_ref,
                )
                self._dao.remove_state(doc_pair)
                self._dao.add_filter(
                    doc_pair.remote_parent_path + "/" + doc_pair.remote_ref
                )
                self.engine.deleteReadonly.emit(doc_pair.local_name)
        self._search_for_dedup(doc_pair)

    def _synchronize_locally_moved_remotely_modified(
        self, doc_pair: NuxeoDocumentInfo
    ) -> None:
        self._synchronize_locally_moved(doc_pair, update=False)
        refreshed_pair = self._dao.get_state_from_id(doc_pair.id)
        self._synchronize_remotely_modified(refreshed_pair)

    def _synchronize_locally_moved_created(self, doc_pair: NuxeoDocumentInfo) -> None:
        doc_pair.remote_ref = None
        self._synchronize_locally_created(doc_pair)

    def _synchronize_locally_moved(
        self, doc_pair: NuxeoDocumentInfo, update: bool = True
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

                log.debug("Renaming remote document according to local %r", doc_pair)
                remote_info = self.remote.rename(
                    doc_pair.remote_ref, doc_pair.local_name
                )
                self._refresh_remote(doc_pair, remote_info=remote_info)
            except Exception as e:
                log.debug(str(e))
                self._handle_failed_remote_rename(doc_pair, doc_pair)
                return

        parent_ref = self.local.get_remote_id(doc_pair.local_parent_path)
        if parent_ref is None:
            parent_pair = self._dao.get_state_from_local(doc_pair.local_parent_path)
            parent_ref = parent_pair.remote_ref
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
                log.debug("Moving remote file according to local : %r", doc_pair)
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

    def _synchronize_deleted_unknown(self, doc_pair: NuxeoDocumentInfo, *_) -> None:
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
            "Detected inconsistent doc pair %r, deleting it hoping the"
            " synchronizer will fix this case at next iteration",
            doc_pair,
        )
        self._dao.remove_state(doc_pair)

    @staticmethod
    def _get_temporary_file(file_path: str) -> str:
        return os.path.join(
            os.path.dirname(file_path),
            (
                DOWNLOAD_TMP_FILE_PREFIX
                + os.path.basename(file_path)
                + DOWNLOAD_TMP_FILE_SUFFIX
            ),
        )

    def _download_content(self, doc_pair: NuxeoDocumentInfo, file_path: str) -> str:
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

    def _update_remotely(self, doc_pair: NuxeoDocumentInfo, is_renaming: bool) -> None:
        os_path = self.local.abspath(doc_pair.local_path)
        if is_renaming:
            new_os_path = os.path.join(
                os.path.dirname(os_path), safe_filename(doc_pair.remote_name)
            )
            log.debug("Replacing local file %r by %r", os_path, new_os_path)
        else:
            new_os_path = os_path
        log.debug("Updating content of local file %r", os_path)
        self.tmp_file = self._download_content(doc_pair, new_os_path)

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

    def _search_for_dedup(
        self, doc_pair: NuxeoDocumentInfo, name: Optional[str] = None
    ) -> None:
        if name is None:
            name = doc_pair.local_name
        # Auto resolve duplicate
        log.debug("Search for dupe pair with %r %s", name, doc_pair.remote_parent_ref)
        dupe_pair = self._dao.get_dedupe_pair(
            name, doc_pair.remote_parent_ref, doc_pair.id
        )
        if dupe_pair is not None:
            log.debug("Dupe pair found %r", dupe_pair)
            self._dao.reset_error(dupe_pair)

    def _synchronize_remotely_modified(self, doc_pair: NuxeoDocumentInfo) -> None:
        self.tmp_file = None
        is_renaming = safe_filename(doc_pair.remote_name) != doc_pair.local_name
        try:
            if (
                not self.local.is_equal_digests(
                    doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path
                )
                and doc_pair.local_digest is not None
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
                        "No local impact of metadata update on" " document %r.",
                        doc_pair.remote_name,
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
                        new_path = new_parent_pair.local_path + "/" + moved_name
                        if old_path == new_path:
                            log.debug("Wrong guess for move: %r", doc_pair)
                            self._is_remote_move(doc_pair)
                            self._dao.synchronize_state(doc_pair)

                        log.debug(
                            "DOC_PAIR(%r):"
                            " old_path[exists=%r, id=%r]: %r,"
                            " new_path[exists=%r, id=%r]: %r",
                            doc_pair,
                            self.local.exists(old_path),
                            self.local.get_remote_id(old_path),
                            old_path,
                            self.local.exists(new_path),
                            self.local.get_remote_id(new_path),
                            new_path,
                        )

                        old_path_abs = self.local.abspath(old_path)
                        new_path_abs = self.local.abspath(new_path)
                        log.debug(
                            "Moving local %s %r to %r",
                            file_or_folder,
                            old_path_abs,
                            new_path_abs,
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
                            "Renaming local %s %r to %r",
                            file_or_folder,
                            self.local.abspath(doc_pair.local_path),
                            doc_pair.remote_name,
                        )
                        updated_info = self.local.rename(
                            doc_pair.local_path, doc_pair.remote_name
                        )

                    if updated_info:
                        # Should call a DAO method
                        new_path = os.path.dirname(updated_info.path)
                        self._dao.update_local_parent_path(
                            doc_pair, os.path.basename(updated_info.path), new_path
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
            os.remove(self.tmp_file)

    def _synchronize_remotely_created(self, doc_pair: NuxeoDocumentInfo) -> None:
        name = doc_pair.remote_name
        # Find the parent pair to find the path of the local folder to
        # create the document into
        parent_pair = self._get_normal_state_from_remote_ref(doc_pair.remote_parent_ref)
        if parent_pair is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ValueError(
                "Could not find parent folder of doc %r (%r)"
                " folder" % (name, doc_pair.remote_ref)
            )

        if parent_pair.local_path is None:
            if parent_pair.pair_state == "unsynchronized":
                self._dao.unsynchronize_state(doc_pair, "PARENT_UNSYNC")
                self._handle_unsynchronized(doc_pair)
                return

            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ParentNotSynced(name, doc_pair.remote_ref)

        path = doc_pair.remote_parent_path + "/" + doc_pair.remote_ref
        if self.remote.is_filtered(path):
            nature = ("file", "folder")[doc_pair.folderish]
            log.trace("Skip filtered %s %r", nature, doc_pair.local_path)
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
            if remote_ref is not None and remote_ref == doc_pair.remote_ref:
                log.debug(
                    "remote_ref (xattr) = %s, doc_pair.remote_ref = %s"
                    " => setting conflicted state",
                    remote_ref,
                    doc_pair.remote_ref,
                )
                # Set conflict state for now
                # TO_REVIEW May need to overwrite
                self._dao.set_conflict_state(doc_pair)
                return
            elif remote_ref is not None:
                # Case of several documents with same name
                # or case insensitive hard drive
                path = self._create_remotely(doc_pair, parent_pair, name)

        self.local.set_remote_id(path, doc_pair.remote_ref)
        if path != doc_pair.local_path and doc_pair.folderish:
            # Update childs
            self._dao.update_local_parent_path(
                doc_pair, os.path.basename(path), os.path.dirname(path)
            )
        self._refresh_local_state(doc_pair, self.local.get_info(path))
        self._handle_readonly(doc_pair)
        if not self._dao.synchronize_state(doc_pair):
            log.debug("Pair is not in synchronized state (version issue): %r", doc_pair)
            # Need to check if this is a remote or local change
            new_pair = self._dao.get_state_from_id(doc_pair.id)
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
        self, doc_pair: NuxeoDocumentInfo, parent_pair: NuxeoDocumentInfo, name: str
    ) -> str:
        # TODO Shared this locking system / Can have concurrent lock
        local_parent_path = parent_pair.local_path
        self._unlock_readonly(local_parent_path)
        try:
            if doc_pair.folderish:
                log.debug(
                    "Creating local folder %r in %r",
                    name,
                    self.local.abspath(local_parent_path),
                )
                return self.local.make_folder(local_parent_path, name)

            path, os_path, name = self.local.get_new_file(local_parent_path, name)
            log.debug(
                "Creating local file %r in %r",
                name,
                self.local.abspath(local_parent_path),
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
                os.remove(tmp_file)

            return path
        finally:
            self._lock_readonly(local_parent_path)

    def _synchronize_remotely_deleted(self, doc_pair: NuxeoDocumentInfo) -> None:
        try:
            if doc_pair.local_state != "deleted":
                log.debug(
                    "Deleting locally %r", self.local.abspath(doc_pair.local_path)
                )
                if doc_pair.folderish:
                    self.engine.set_local_folder_lock(doc_pair.local_path)
                else:
                    # Check for nxpart to clean up
                    file_out = self._get_temporary_file(
                        self.local.abspath(doc_pair.local_path)
                    )
                    if os.path.exists(file_out):
                        os.remove(file_out)

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

    def _synchronize_unknown_deleted(self, doc_pair: NuxeoDocumentInfo) -> None:
        # Somehow a pair can get to an inconsistent state:
        # <local_state='unknown', remote_state='deleted',
        # pair_state='unknown'>
        # Even though we are not able to figure out how this can happen we
        # need to handle this case to put the database back to a consistent
        # state.
        # This is tracked by https://jira.nuxeo.com/browse/NXP-13216
        log.debug("Inconsistency should not happens anymore")
        log.debug(
            "Detected inconsistent doc pair %r, deleting it hoping the "
            "synchronizer will fix this case at next iteration",
            doc_pair,
        )
        self._dao.remove_state(doc_pair)
        if doc_pair.local_path is not None:
            log.debug(
                "Since the local path is not None: %r, the synchronizer "
                "will probably consider this as a local creation at "
                "next iteration and create the file or folder remotely",
                doc_pair.local_path,
            )
        else:
            log.debug(
                "Since the local path is None the synchronizer will "
                "probably do nothing at next iteration"
            )

    def _refresh_remote(
        self,
        doc_pair: NuxeoDocumentInfo,
        remote_info: Optional[NuxeoDocumentInfo] = None,
    ) -> None:
        if remote_info is None:
            remote_info = self.remote.get_fs_info(doc_pair.remote_ref)
        self._dao.update_remote_state(
            doc_pair, remote_info, versioned=False, queue=False
        )

    def _refresh_local_state(
        self, doc_pair: NuxeoDocumentInfo, local_info: NuxeoDocumentInfo
    ) -> None:
        if doc_pair.local_digest is None and not doc_pair.folderish:
            doc_pair.local_digest = local_info.get_digest()
        self._dao.update_local_state(doc_pair, local_info, versioned=False, queue=False)
        doc_pair.local_path = local_info.path
        doc_pair.local_name = os.path.basename(local_info.path)
        doc_pair.last_local_updated = local_info.last_modification_time

    def _is_remote_move(
        self, doc_pair: NuxeoDocumentInfo
    ) -> Tuple[bool, Optional[DocPair]]:
        local_parent = self._dao.get_state_from_local(doc_pair.local_parent_path)
        remote_parent = self._get_normal_state_from_remote_ref(
            doc_pair.remote_parent_ref
        )
        state = local_parent and remote_parent and local_parent.id != remote_parent.id
        log.debug(
            "is_remote_move=%r: name=%r, local=%r, remote=%r",
            state,
            doc_pair.remote_name,
            local_parent,
            remote_parent,
        )
        return state, remote_parent

    def _handle_failed_remote_move(
        self, source_pair: NuxeoDocumentInfo, target_pair: NuxeoDocumentInfo
    ) -> None:
        pass

    def _handle_failed_remote_rename(
        self, source_pair: NuxeoDocumentInfo, target_pair: NuxeoDocumentInfo
    ) -> bool:
        """ An error occurs return False. """

        if not self.engine.local_rollback(force=WINDOWS):
            return False

        log.error(
            "Renaming %r to %r canceled",
            target_pair.remote_name,
            target_pair.local_name,
        )

        try:
            info = self.local.rename(target_pair.local_path, target_pair.remote_name)
            self._dao.update_local_state(source_pair, info, queue=False)
            if source_pair != target_pair:
                if target_pair.folderish:
                    # Remove "new" created tree
                    pairs = self._dao.get_states_from_partial_local(
                        target_pair.local_path
                    ).all()
                    for pair in pairs:
                        self._dao.remove_state(pair)
                    pairs = self._dao.get_states_from_partial_local(
                        source_pair.local_path
                    ).all()
                    for pair in pairs:
                        self._dao.synchronize_state(pair)
                else:
                    self._dao.remove_state(target_pair)
            self._dao.synchronize_state(source_pair)
            return True
        except:
            log.exception("Cannot rollback local modification")

    def _handle_unsynchronized(self, doc_pair: NuxeoDocumentInfo) -> None:
        # Used for overwrite
        pass

    def _handle_readonly(self, doc_pair: NuxeoDocumentInfo) -> None:
        # Don't use readonly on folder for win32 and on Locally Edited
        if doc_pair.folderish and WINDOWS:
            return

        if doc_pair.is_readonly():
            log.debug("Setting %r as readonly", doc_pair.local_path)
            self.local.set_readonly(doc_pair.local_path)
        else:
            log.debug("Unsetting %r as readonly", doc_pair.local_path)
            self.local.unset_readonly(doc_pair.local_path)
