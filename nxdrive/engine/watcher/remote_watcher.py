# coding: utf-8
import os
import socket
from datetime import datetime
from logging import getLogger
from time import sleep
from typing import Any, Dict, Optional, Set, Tuple, TYPE_CHECKING

from PyQt5.QtCore import pyqtSignal, pyqtSlot
from nuxeo.exceptions import BadQuery, HTTPError
from requests import ConnectionError

from ..activity import Action, tooltip
from ..dao.sqlite import EngineDAO
from ..workers import EngineWorker
from ...constants import WINDOWS
from ...exceptions import NotFound, ThreadInterrupt
from ...objects import Metrics, RemoteFileInfo, DocPair, DocPairs
from ...utils import current_milli_time, path_join, safe_filename

if TYPE_CHECKING:
    from .engine import Engine  # noqa

__all__ = ("RemoteWatcher",)

log = getLogger(__name__)
COLLECTION_SYNC_ROOT_FACTORY_NAME = "collectionSyncRootFolderItemFactory"


class RemoteWatcher(EngineWorker):
    initiate = pyqtSignal()
    updated = pyqtSignal()
    remoteScanFinished = pyqtSignal()
    changesFound = pyqtSignal(int)
    noChangesFound = pyqtSignal()
    remoteWatcherStopped = pyqtSignal()

    def __init__(self, engine: "Engine", dao: EngineDAO, delay: int) -> None:
        super().__init__(engine, dao)
        self.server_interval = delay

        self._next_check = 0
        self._last_sync_date = int(self._dao.get_config("remote_last_sync_date", 0))
        self._last_event_log_id = int(
            self._dao.get_config("remote_last_event_log_id", 0)
        )
        self._last_root_definitions = self._dao.get_config(
            "remote_last_root_definitions", ""
        )
        self._last_remote_full_scan = self._dao.get_config("remote_last_full_scan")
        self._metrics = {
            "last_remote_scan_time": -1,
            "last_remote_update_time": -1,
            "empty_polls": 0,
        }

    def get_metrics(self) -> Metrics:
        metrics = super().get_metrics()
        metrics["last_remote_sync_date"] = self._last_sync_date
        metrics["last_event_log_id"] = self._last_event_log_id
        metrics["last_root_definitions"] = self._last_root_definitions
        metrics["last_remote_full_scan"] = self._last_remote_full_scan
        metrics["next_polling"] = self._next_check
        return {**metrics, **self._metrics}

    def _execute(self) -> None:
        first_pass = True
        try:
            while True:
                self._interact()
                now = current_milli_time()
                if self._next_check < now:
                    self._next_check = now + self.server_interval * 1000
                    if self._handle_changes(first_pass):
                        first_pass = False
                sleep(0.01)
        except ThreadInterrupt:
            self.remoteWatcherStopped.emit()
            raise

    @tooltip("Remote scanning")
    def _scan_remote(self, from_state: DocPair = None):
        """Recursively scan the bound remote folder looking for updates"""
        log.trace("Remote full scan")
        start_ms = current_milli_time()
        try:
            from_state = from_state or self._dao.get_state_from_local("/")
            if from_state:
                remote_info = self.engine.remote.get_fs_info(from_state.remote_ref)
                self._dao.update_remote_state(
                    from_state,
                    remote_info,
                    remote_parent_path=from_state.remote_parent_path,
                )
            else:
                return
        except NotFound:
            log.debug(f"Marking {from_state!r} as remotely deleted")
            # Should unbind ?
            # from_state.update_remote(None)
            self._metrics["last_remote_scan_time"] = current_milli_time() - start_ms
            return

        self._get_changes()
        # recursive update
        self._do_scan_remote(from_state, remote_info)
        self._last_remote_full_scan = datetime.utcnow()
        self._dao.update_config("remote_last_full_scan", self._last_remote_full_scan)
        self._dao.clean_scanned()
        self._metrics["last_remote_scan_time"] = current_milli_time() - start_ms
        log.debug(f"Remote scan finished in {self._metrics['last_remote_scan_time']}ms")
        self.remoteScanFinished.emit()

    @pyqtSlot(str)
    def scan_pair(self, remote_path: str) -> None:
        self._dao.add_path_to_scan(str(remote_path))
        self._next_check = 0

    def _scan_pair(self, remote_path: str) -> None:
        if remote_path is None:
            return
        remote_path = str(remote_path)
        if self._dao.is_filter(remote_path):
            # Skip if filter
            return
        if remote_path[-1:] == "/":
            remote_path = remote_path[0:-1]
        remote_ref = os.path.basename(remote_path)
        parent_path = os.path.dirname(remote_path)
        if parent_path == "/":
            parent_path = ""
        # If pair is present already
        try:
            child_info = self.engine.remote.get_fs_info(remote_ref)
        except NotFound:
            # The folder has been deleted
            return
        doc_pair = self._dao.get_state_from_remote_with_path(remote_ref, parent_path)
        if doc_pair is not None:
            self._do_scan_remote(doc_pair, child_info)
            return
        log.debug(
            f"parent_path: {parent_path!r}\t"
            f"{os.path.basename(parent_path)!r}\t"
            f"{os.path.dirname(parent_path)!r}"
        )
        parent_pair = self._dao.get_state_from_remote_with_path(
            os.path.basename(parent_path), os.path.dirname(parent_path)
        )
        log.debug(f"scan_pair: parent_pair: {parent_pair!r}")
        if parent_pair is None:
            return
        local_path = path_join(parent_pair.local_path, safe_filename(child_info.name))
        remote_parent_path = (
            parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
        )
        if os.path.dirname(child_info.path) == remote_parent_path:
            row_id = self._dao.insert_remote_state(
                child_info, remote_parent_path, local_path, parent_pair.local_path
            )
            doc_pair = self._dao.get_state_from_id(row_id, from_write=True)
            if doc_pair and child_info.folderish:
                self._do_scan_remote(doc_pair, child_info)
        else:
            log.debug(f"Remote scan_pair: {remote_path!r} is not available")
            self._scan_remote()

    @staticmethod
    def _check_modified(pair: DocPair, info: RemoteFileInfo) -> bool:
        return any(
            {
                pair.remote_can_delete != info.can_delete,
                pair.remote_can_rename != info.can_rename,
                pair.remote_can_update != info.can_update,
                pair.remote_can_create_child != info.can_create_child,
                pair.remote_name != info.name,
                pair.remote_digest != info.digest,
                pair.remote_parent_ref != info.parent_uid,
            }
        )

    def _do_scan_remote(
        self,
        doc_pair: DocPair,
        remote_info: RemoteFileInfo,
        force_recursion: bool = True,
        moved: bool = False,
    ) -> None:
        if remote_info.can_scroll_descendants:
            log.debug(
                "Performing scroll remote scan "
                f"for {remote_info.name!r} ({remote_info})"
            )
            self._scan_remote_scroll(doc_pair, remote_info, moved=moved)
        else:
            log.debug(
                "Scroll scan not available, performing recursive remote scan "
                f"for {remote_info.name!r} ({remote_info})"
            )
            self._scan_remote_recursive(
                doc_pair, remote_info, force_recursion=force_recursion
            )

    def _scan_remote_scroll(
        self, doc_pair: DocPair, remote_info: RemoteFileInfo, moved: bool = False
    ) -> None:
        """
        Perform a scroll scan of the bound remote folder looking for updates.
        """

        remote_parent_path = self._init_scan_remote(doc_pair, remote_info)
        if remote_parent_path is None:
            return

        # Detect recently deleted children
        if moved:
            db_descendants = self._dao.get_remote_descendants_from_ref(
                doc_pair.remote_ref
            )
        else:
            db_descendants = self._dao.get_remote_descendants(remote_parent_path)
        descendants = {desc.remote_ref: desc for desc in db_descendants}

        to_process = []
        scroll_id = None
        batch_size = 100
        t1 = None

        while "Scrolling":
            t0 = datetime.now()
            if t1 is not None:
                elapsed = self._get_elapsed_time_milliseconds(t1, t0)
                log.trace(
                    f"Local processing of descendants "
                    f"of {remote_info.name!r} ({remote_info.uid}) took {elapsed} ms"
                )

            # Scroll through a batch of descendants
            log.trace(
                f"Scrolling through at most [{batch_size}] descendants "
                f"of {remote_info.name!r} ({remote_info.uid})"
            )
            scroll_res = self.engine.remote.scroll_descendants(
                remote_info.uid, scroll_id, batch_size=batch_size
            )
            t1 = datetime.now()
            elapsed = self._get_elapsed_time_milliseconds(t0, t1)
            descendants_info = scroll_res["descendants"]
            if not descendants_info:
                log.trace(
                    "Remote scroll request retrieved no descendants "
                    f"of {remote_info.name!r} ({remote_info.uid}), took {elapsed} ms"
                )
                break

            log.trace(
                f"Remote scroll request retrieved {len(descendants_info)} descendants "
                f"of {remote_info.name!r} ({remote_info.uid}), took {elapsed} ms"
            )
            scroll_id = scroll_res["scroll_id"]

            # Results are not necessarily sorted
            descendants_info = sorted(descendants_info, key=lambda x: x.path)

            # Handle descendants
            for descendant_info in descendants_info:
                if self.filtered(descendant_info):
                    log.debug(f"Ignoring banned document {descendant_info}")
                    descendants.pop(descendant_info.uid, None)
                    continue

                if self._dao.is_filter(descendant_info.path):
                    # Skip filtered document
                    descendants.pop(descendant_info.uid, None)
                    continue

                log.trace(f"Handling remote descendant {descendant_info!r}")
                if descendant_info.uid in descendants:
                    descendant_pair = descendants.pop(descendant_info.uid)
                    if self._check_modified(descendant_pair, descendant_info):
                        descendant_pair.remote_state = "modified"
                    self._dao.update_remote_state(descendant_pair, descendant_info)
                    continue

                parent_pair = self._dao.get_normal_state_from_remote(
                    descendant_info.parent_uid
                )
                if not parent_pair:
                    log.trace(
                        "Cannot find parent pair of remote descendant, "
                        f"postponing processing of {descendant_info}"
                    )
                    to_process.append(descendant_info)
                    continue

                self._find_remote_child_match_or_create(parent_pair, descendant_info)

            # Check if synchronization thread was suspended
            self._interact()

        if to_process:
            t0 = datetime.now()
            to_process = sorted(to_process, key=lambda x: x.path)
            log.trace(
                f"Processing [{len(to_process)}] postponed descendants of "
                f"{remote_info.name!r} ({remote_info.uid})"
            )
            for descendant_info in to_process:
                parent_pair = self._dao.get_normal_state_from_remote(
                    descendant_info.parent_uid
                )
                if not parent_pair:
                    log.error(
                        "Cannot find parent pair of postponed remote descendant, "
                        f"ignoring {descendant_info}"
                    )
                    continue

                self._find_remote_child_match_or_create(parent_pair, descendant_info)

            t1 = datetime.now()
            elapsed = self._get_elapsed_time_milliseconds(t0, t1)
            log.trace(f"Postponed descendants processing took {elapsed} ms")

        # Delete remaining
        for deleted in descendants.values():
            self._dao.delete_remote_state(deleted)

    @staticmethod
    def _get_elapsed_time_milliseconds(t0: datetime, t1: datetime) -> float:
        delta = t1 - t0
        return delta.seconds * 1000 + delta.microseconds / 1000

    def _scan_remote_recursive(
        self,
        doc_pair: DocPair,
        remote_info: RemoteFileInfo,
        force_recursion: bool = True,
    ) -> None:
        """
        Recursively scan the bound remote folder looking for updates

        If force_recursion is True, recursion is done even on
        non newly created children.
        """

        remote_parent_path = self._init_scan_remote(doc_pair, remote_info)
        if remote_parent_path is None:
            return

        # Check if synchronization thread was suspended
        self._interact()

        # Detect recently deleted children
        db_children = self._dao.get_remote_children(doc_pair.remote_ref)
        children: Dict[str, DocPair] = {
            child.remote_ref: child for child in db_children
        }
        children_info = self.engine.remote.get_fs_children(remote_info.uid)

        to_scan = []
        for child_info in children_info:
            if self.filtered(child_info):
                log.debug(f"Ignoring banned file: {child_info!r}")
                continue

            log.trace(f"Scanning remote child: {child_info!r}")
            new_pair = False
            if child_info.uid in children:
                child_pair = children.pop(child_info.uid)
                if self._check_modified(child_pair, child_info):
                    child_pair.remote_state = "modified"
                self._dao.update_remote_state(
                    child_pair, child_info, remote_parent_path=remote_parent_path
                )
            else:
                match_pair = self._find_remote_child_match_or_create(
                    doc_pair, child_info
                )
                if match_pair:
                    child_pair, new_pair = match_pair

            if (new_pair or force_recursion) and child_info.folderish:
                to_scan.append((child_pair, child_info))

        # Delete remaining
        for deleted in children.values():
            self._dao.delete_remote_state(deleted)

        for pair, info in to_scan:
            # TODO Optimize by multithreading this too ?
            self._do_scan_remote(pair, info, force_recursion=force_recursion)
        self._dao.add_path_scanned(remote_parent_path)

    def _init_scan_remote(
        self, doc_pair: DocPair, remote_info: RemoteFileInfo
    ) -> Optional[str]:
        if remote_info is None:
            raise ValueError(f"Cannot bind {doc_pair!r} to missing remote info")
        if not remote_info.folderish:
            # No children to align, early stop.
            log.trace(
                f"Skip remote scan as it is not a folderish document: {remote_info!r}"
            )
            return None
        remote_parent_path = doc_pair.remote_parent_path + "/" + remote_info.uid
        if self._dao.is_path_scanned(remote_parent_path):
            log.trace(f"Skip already remote scanned: {doc_pair.local_path!r}")
            return None
        if doc_pair.local_path is not None:
            Action(f"Remote scanning {doc_pair.local_path!r}")
            log.debug(f"Remote scanning: {doc_pair.local_path!r}")
        return remote_parent_path

    def _find_remote_child_match_or_create(
        self, parent_pair: DocPair, child_info: RemoteFileInfo
    ) -> Optional[Tuple[DocPair, bool]]:
        if not parent_pair.local_path:
            # The parent folder has an empty local_path,
            # it probably means that it has been put in error as a duplicate
            # by a processor => ignoring this child.
            log.debug(
                f"Ignoring child {child_info!r} of a duplicate folder "
                f"in error {parent_pair!r}"
            )
            return None

        if self._dao.get_normal_state_from_remote(child_info.uid):
            log.warning(
                "Illegal state: a remote creation cannot happen if "
                "there already is the same remote ref in the database"
            )
            return None

        local_path = path_join(parent_pair.local_path, safe_filename(child_info.name))
        remote_parent_path = (
            parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
        )
        # Try to get the local definition if not linked
        child_pair = self._dao.get_state_from_local(local_path)
        if (
            child_pair is None
            and parent_pair is not None
            and self.engine.local.exists(parent_pair.local_path)
        ):
            for child in self.engine.local.get_children_info(parent_pair.local_path):
                if self.engine.local.get_remote_id(child.path) == child_info.uid:
                    log.debug(
                        f"Found a local rename case: {child_info!r} on {child.path!r}"
                    )
                    child_pair = self._dao.get_state_from_local(child.path)
                    break
        if child_pair is not None:
            if child_pair.remote_ref and child_pair.remote_ref != child_info.uid:
                log.debug(
                    "Got an existing pair with different id: "
                    f"{child_pair!r} | {child_info!r}"
                )
            else:
                if (
                    child_pair.folderish == child_info.folderish
                    and self.engine.local.is_equal_digests(
                        child_pair.local_digest,
                        child_info.digest,
                        child_pair.local_path,
                        remote_digest_algorithm=child_info.digest_algorithm,
                    )
                ):
                    # Local rename
                    if child_pair.local_path != local_path:
                        child_pair.local_state = "moved"
                        child_pair.remote_state = "unknown"
                        local_info = self.engine.local.get_info(child_pair.local_path)
                        self._dao.update_local_state(child_pair, local_info)
                        self._dao.update_remote_state(
                            child_pair,
                            child_info,
                            remote_parent_path=remote_parent_path,
                        )
                    else:
                        self._dao.update_remote_state(
                            child_pair,
                            child_info,
                            remote_parent_path=remote_parent_path,
                        )
                        # Use version+1 as we just update the remote info
                        synced = self._dao.synchronize_state(
                            child_pair, version=child_pair.version + 1
                        )
                        if not synced:
                            # Try again, might happen that it has been modified locally and remotely
                            refreshed = self._dao.get_state_from_id(child_pair.id)
                            if (
                                refreshed
                                and refreshed.folderish is child_info.folderish is False
                                and self.engine.local.is_equal_digests(
                                    refreshed.local_digest,
                                    child_info.digest,
                                    refreshed.local_path,
                                    remote_digest_algorithm=child_info.digest_algorithm,
                                )
                            ):
                                self._dao.synchronize_state(refreshed)
                                refreshed = self._dao.get_state_from_id(refreshed.id)
                                synced = bool(
                                    refreshed and refreshed.pair_state == "synchronized"
                                )

                            if refreshed:
                                child_pair = refreshed
                        # Can be updated in previous call
                        if synced:
                            self.engine.stop_processor_on(child_pair.local_path)
                        # Push the remote_Id
                        log.debug(
                            f"Set remote ID on {child_pair!r} / "
                            f"{child_pair.local_path!r} == {child_pair.local_path!r}"
                        )
                        self.engine.local.set_remote_id(
                            child_pair.local_path, child_info.uid
                        )
                        if child_pair.folderish:
                            self._dao.queue_children(child_pair)
                else:
                    child_pair.remote_state = "modified"
                    self._dao.update_remote_state(
                        child_pair, child_info, remote_parent_path=remote_parent_path
                    )
                child_pair = self._dao.get_state_from_id(child_pair.id, from_write=True)
                return (child_pair, False) if child_pair else None
        row_id = self._dao.insert_remote_state(
            child_info, remote_parent_path, local_path, parent_pair.local_path
        )
        child_pair = self._dao.get_state_from_id(row_id, from_write=True)
        return (child_pair, True) if child_pair else None

    def _handle_readonly(self, doc_pair: DocPair) -> None:
        # Don't use readonly on folder for win32 and on Locally Edited
        if doc_pair.folderish and WINDOWS:
            return
        if doc_pair.is_readonly():
            log.debug(f"Setting {doc_pair.local_path!r} as readonly")
            self.engine.local.set_readonly(doc_pair.local_path)
        else:
            log.debug(f"Unsetting {doc_pair.local_path!r} as readonly")
            self.engine.local.unset_readonly(doc_pair.local_path)

    def _partial_full_scan(self, path: str) -> None:
        log.debug(f"Continue full scan of {path!r}")
        if path == "/":
            self._scan_remote()
        else:
            self._scan_pair(path)
        self._dao.delete_path_to_scan(path)
        self._dao.delete_config("remote_need_full_scan")
        self._dao.clean_scanned()

    def _check_offline(self) -> bool:
        if not self.engine.is_offline():
            return False

        online = self.engine.remote.client.is_reachable()
        if online:
            self.engine.set_offline(value=False)

        return not online

    def _handle_changes(self, first_pass: bool = False) -> bool:
        log.trace(f"Handle remote changes, first_pass={first_pass!r}")
        self._check_offline()
        try:
            if not self._last_remote_full_scan:
                self._scan_remote()

                # Might need to handle the changes now
                if first_pass:
                    self.initiate.emit()
                return True

            full_scan = self._dao.get_config("remote_need_full_scan", None)
            if full_scan is not None:
                self._partial_full_scan(full_scan)
                return False

            for remote_ref in self._dao.get_paths_to_scan():
                self._dao.update_config("remote_need_full_scan", remote_ref)
                self._partial_full_scan(remote_ref)

            self._update_remote_states()
            (self.updated, self.initiate)[first_pass].emit()
        except HTTPError as e:
            err = f"HTTP error {e.status} while trying to handle remote changes"
            if e.status in (401, 403):
                self.engine.set_invalid_credentials(reason=err)
                self.engine.set_offline()
            else:
                log.error(err)
        except (ConnectionError, socket.error) as exc:
            log.error(f"Network error: {exc}")
        except BadQuery:
            # This should never happen: there is an error in the operation's
            # parameters sent to the server.  This exception is possible only
            # in debug mode or when running the test suite.
            log.critical("Oops! Bad query parameter", exc_info=True)
            raise
        except ThreadInterrupt:
            raise
        except:
            log.exception("Unexpected error")
        else:
            return True
        finally:
            Action.finish_action()
        return False

    def _get_changes(self) -> Dict[str, Any]:
        """Fetch incremental change summary from the server"""
        summary = self.engine.remote.get_changes(
            self._last_root_definitions, self._last_event_log_id, self._last_sync_date
        )

        root_defs = summary["activeSynchronizationRootDefinitions"]
        self._last_root_definitions = root_defs
        self._last_sync_date = int(summary["syncDate"])
        # If available, read 'upperBound' key as last event log id
        # according to the new implementation of the audit change finder,
        # see https://jira.nuxeo.com/browse/NXP-14826.
        self._last_event_log_id = int(summary.get("upperBound", 0))

        self._dao.update_config("remote_last_sync_date", self._last_sync_date)
        self._dao.update_config("remote_last_event_log_id", self._last_event_log_id)
        self._dao.update_config(
            "remote_last_root_definitions", self._last_root_definitions
        )

        return summary

    def _force_remote_scan(
        self,
        doc_pair: DocPair,
        remote_info: RemoteFileInfo,
        remote_path: str = None,
        force_recursion: bool = True,
        moved: bool = False,
    ) -> None:
        if remote_path is None:
            remote_path = remote_info.path
        if force_recursion:
            self._dao.add_path_to_scan(remote_path)
        else:
            self._do_scan_remote(
                doc_pair, remote_info, force_recursion=force_recursion, moved=moved
            )

    @tooltip("Handle remote changes")
    def _update_remote_states(self) -> None:
        """Incrementally update the state of documents from a change summary"""
        summary = self._get_changes()
        if summary["hasTooManyChanges"]:
            log.debug("Forced full scan by server")
            remote_path = "/"
            self._dao.add_path_to_scan(remote_path)
            self._dao.update_config("remote_need_full_scan", remote_path)
            return

        if not summary["fileSystemChanges"]:
            self._metrics["empty_polls"] += 1
            self.noChangesFound.emit()
            return

        # Fetch all events and consider the most recent first
        sorted_changes = sorted(
            summary["fileSystemChanges"], key=lambda x: x["eventDate"], reverse=True
        )

        n_changes = len(sorted_changes)
        self._metrics["last_changes"] = n_changes
        self._metrics["empty_polls"] = 0
        self.changesFound.emit(n_changes)

        # Scan events and update the related pair states
        refreshed: Set[str] = set()
        delete_queue = []
        for change in sorted_changes:
            # Check if synchronization thread was suspended
            # TODO In case of pause or stop: save the last event id
            self._interact()

            log.trace(f"Processing event: {change!r}")

            event_id = change.get("eventId")
            remote_ref = change["fileSystemItemId"]
            processed = False
            for refreshed_ref in refreshed:
                if refreshed_ref.endswith(remote_ref):
                    processed = True
                    break

            if processed:
                # A more recent version was already processed
                continue
            fs_item = change.get("fileSystemItem")
            new_info = RemoteFileInfo.from_dict(fs_item) if fs_item else None

            if self.filtered(new_info):
                log.debug(f"Ignoring banned file: {new_info!r}")
                continue

            # Possibly fetch multiple doc pairs as the same doc
            # can be synchronized in 2 places,
            # typically if under a sync root and locally edited.
            # See https://jira.nuxeo.com/browse/NXDRIVE-125
            doc_pairs = self._dao.get_states_from_remote(remote_ref)
            if not doc_pairs:
                # Relax constraint on factory name in FileSystemItem id to
                # match 'deleted' or 'securityUpdated' events.
                # See https://jira.nuxeo.com/browse/NXDRIVE-167
                doc_pair = self._dao.get_first_state_from_partial_remote(remote_ref)
                if doc_pair:
                    doc_pairs = [doc_pair]

            updated = False
            doc_pairs = doc_pairs or []
            for doc_pair in doc_pairs:
                if not doc_pair:
                    continue
                doc_pair_repr = (
                    doc_pair.local_path
                    if doc_pair.local_path is not None
                    else doc_pair.remote_name
                )
                if event_id == "deleted":
                    if fs_item is None or new_info is None:
                        if doc_pair.local_path == "":
                            log.debug(f"Delete pair from duplicate: {doc_pair!r}")
                            self._dao.remove_state(doc_pair, remote_recursion=True)
                            continue
                        log.debug(f"Push doc_pair {doc_pair_repr!r} in delete queue")
                        delete_queue.append(doc_pair)
                    else:
                        log.debug(
                            f"Ignore delete on doc_pair {doc_pair_repr!r} "
                            "as a fsItem is attached"
                        )
                        # To ignore completely put updated to true
                        updated = True
                        break
                elif fs_item is None or new_info is None:
                    if event_id == "securityUpdated":
                        log.debug(
                            f"Security has been updated for doc_pair {doc_pair_repr!r} "
                            "denying Read access, marking it as deleted"
                        )
                        self._dao.delete_remote_state(doc_pair)
                    else:
                        log.warning(f"Unknown event: {event_id!r}")
                else:
                    remote_parent_factory = doc_pair.remote_parent_ref.split("#", 1)[0]
                    new_info_parent_factory = new_info.parent_uid.split("#", 1)[0]
                    # Specific cases of a move on a locally edited doc
                    if (
                        remote_parent_factory == COLLECTION_SYNC_ROOT_FACTORY_NAME
                        and event_id == "documentMoved"
                    ):
                        # If moved from a non sync root to a sync root,
                        # break to creation case (updated is False).
                        # If moved from a sync root to a non sync root,
                        # break to noop (updated is True).
                        break
                    elif (
                        new_info_parent_factory == COLLECTION_SYNC_ROOT_FACTORY_NAME
                        and event_id == "documentMoved"
                    ):
                        # If moved from a sync root to a non sync root,
                        # delete from local sync root
                        log.debug(f"Marking doc_pair {doc_pair_repr!r} as deleted")
                        self._dao.delete_remote_state(doc_pair)
                    else:
                        """
                        Make new_info consistent with actual doc pair parent
                        path for a doc member of a collection (typically the
                        Locally Edited one) that is also under a sync root.
                        Indeed, in this case, when adapted as a FileSystemItem,
                        its parent path will be the one of the sync root because
                        it takes precedence over the collection, see
                        AbstractDocumentBackedFileSystemItem constructor.
                        """
                        consistent_new_info = new_info
                        if remote_parent_factory == COLLECTION_SYNC_ROOT_FACTORY_NAME:
                            consistent_new_info = RemoteFileInfo(  # type: ignore
                                new_info.name,
                                new_info.uid,
                                doc_pair.remote_parent_ref,
                                doc_pair.remote_parent_path + "/" + remote_ref,
                                new_info.folderish,
                                new_info.last_modification_time,
                                new_info.creation_time,
                                new_info.last_contributor,
                                new_info.digest,
                                new_info.digest_algorithm,
                                new_info.download_url,
                                new_info.can_rename,
                                new_info.can_delete,
                                new_info.can_update,
                                new_info.can_create_child,
                                new_info.lock_owner,
                                new_info.lock_created,
                                new_info.can_scroll_descendants,
                            )
                        # Perform a regular document update on a document
                        # that has been updated, renamed or moved
                        log.debug(
                            f"Refreshing remote state info for "
                            f"doc_pair={doc_pair_repr!r}, "
                            f"event_id={event_id!r}, "
                            f"new_info={new_info!r} "
                            f"(force_recursion={event_id == 'securityUpdated'})"
                        )

                        # Force remote state update in case of a
                        # locked / unlocked event since lock info is not
                        # persisted, so not part of the dirty check
                        lock_update = event_id in {"documentLocked", "documentUnlocked"}

                        # Perform a regular document update on a document
                        # that has been updated, renamed or moved

                        if doc_pair.remote_state != "created" and any(
                            (
                                new_info.digest != doc_pair.remote_digest,
                                safe_filename(new_info.name) != doc_pair.remote_name,
                                new_info.parent_uid != doc_pair.remote_parent_ref,
                                event_id == "securityUpdated",
                                lock_update,
                            )
                        ):
                            doc_pair.remote_state = "modified"

                        log.debug(
                            f"Refreshing remote state info for doc_pair={doc_pair!r}, "
                            f"event_id={event_id!r}, new_info={new_info!r} "
                            f"(force_recursion={event_id == 'securityUpdated'})"
                        )

                        remote_parent_path = os.path.dirname(new_info.path)
                        # TODO Add modify local_path and local_parent_path
                        # if needed
                        self._dao.update_remote_state(
                            doc_pair,
                            new_info,
                            remote_parent_path=remote_parent_path,
                            force_update=lock_update,
                        )

                        if doc_pair.folderish:
                            if (
                                event_id == "securityUpdated"
                                and not doc_pair.remote_can_create_child
                                and new_info.can_create_child
                            ):
                                log.debug("Force local scan after permissions change")
                                self._dao.unset_unsychronised(doc_pair)

                            log.trace(
                                f"Force scan recursive on {doc_pair!r}, "
                                f"permissions change={event_id == 'securityUpdated'!r}"
                            )
                            self._force_remote_scan(
                                doc_pair,
                                consistent_new_info,
                                remote_path=new_info.path,
                                force_recursion=event_id == "securityUpdated",
                                moved=event_id == "documentMoved",
                            )

                        if lock_update:
                            locked_pair = self._dao.get_state_from_id(doc_pair.id)
                            try:
                                if locked_pair:
                                    self._handle_readonly(locked_pair)
                            except OSError as exc:
                                log.trace(
                                    f"Cannot handle readonly for {locked_pair!r} ({exc!r})"
                                )

                pair = self._dao.get_state_from_id(doc_pair.id)
                if pair:
                    self.engine.manager.osi.send_sync_status(
                        pair, self.engine.local.abspath(pair.local_path)
                    )

                updated = True
                refreshed.add(remote_ref)

            if new_info and not updated:
                # Handle new document creations
                created = False
                parent_pairs = self._dao.get_states_from_remote(new_info.parent_uid)
                for parent_pair in parent_pairs:
                    match_pair = self._find_remote_child_match_or_create(
                        parent_pair, new_info
                    )
                    if match_pair:
                        child_pair, new_pair = match_pair
                        if child_pair.folderish:
                            log.debug(
                                "Remote recursive scan of the content "
                                f"of {child_pair.remote_name!r}"
                            )
                            remote_path = (
                                child_pair.remote_parent_path + "/" + new_info.uid
                            )
                            self._force_remote_scan(child_pair, new_info, remote_path)
                        else:
                            log.debug(
                                f"Marked doc_pair {child_pair.remote_name!r} "
                                "as remote creation"
                            )

                    created = True
                    refreshed.add(remote_ref)
                    break

                if not created:
                    log.debug(
                        "Could not match changed document to a bound "
                        f"local folder: {new_info!r}"
                    )

        # Sort by path the deletion to only mark parent
        sorted_deleted = sorted(delete_queue, key=lambda x: x.local_path)
        delete_processed: DocPairs = []
        for delete_pair in sorted_deleted:
            # Mark as deleted
            skip = False
            for processed_pair in delete_processed:
                path = processed_pair.local_path

                if path[-1] != "/":
                    path += "/"

                if delete_pair.local_path.startswith(path):
                    skip = True
                    break

            if skip:
                continue

            # Verify the file is really deleted
            if self.engine.remote.get_fs_item(delete_pair.remote_ref):
                continue

            delete_processed.append(delete_pair)
            log.debug(f"Marking doc_pair {delete_pair!r} as deleted")
            self._dao.delete_remote_state(delete_pair)

    def filtered(self, info: Optional[RemoteFileInfo]) -> bool:
        """ Check if a remote document is locally ignored. """
        return (
            info is not None
            and not info.folderish
            and self.engine.local.is_ignored("/", info.name)
        )
