import os
from datetime import datetime
from logging import getLogger
from operator import attrgetter, itemgetter
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any, Dict, Optional, Set, Tuple

from nuxeo.exceptions import BadQuery, HTTPError, Unauthorized

from ...client.local import FileInfo
from ...constants import BATCH_SIZE, CONNECTION_ERROR, ROOT, WINDOWS
from ...exceptions import NotFound, ScrollDescendantsError, ThreadInterrupt
from ...feature import Feature
from ...objects import DocPair, DocPairs, Metrics, RemoteFileInfo
from ...options import Options
from ...qt.imports import pyqtSignal, pyqtSlot
from ...utils import get_date_from_sqlite, safe_filename
from ..activity import Action, tooltip
from ..workers import EngineWorker
from .constants import (
    DELETED_EVENT,
    DOCUMENT_LOCKED,
    DOCUMENT_MOVED,
    DOCUMENT_UNLOCKED,
    SECURITY_UPDATED_EVENT,
)

if TYPE_CHECKING:
    from ...dao.engine import EngineDAO  # noqa
    from ..engine import Engine  # noqa

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

    def __init__(self, engine: "Engine", dao: "EngineDAO", /) -> None:
        super().__init__(engine, dao, "RemoteWatcher")

        self.empty_polls = 0
        self._next_check = 0.0
        self._last_sync_date: int = self.dao.get_int("remote_last_sync_date")
        self._last_event_log_id: int = self.dao.get_int("remote_last_event_log_id")
        self._last_root_definitions = self.dao.get_config(
            "remote_last_root_definitions", default=""
        )
        self._last_remote_full_scan: Optional[datetime] = self.dao.get_config(
            "remote_last_full_scan"
        )

    def get_metrics(self) -> Metrics:
        metrics = super().get_metrics()
        metrics["last_remote_sync_date"] = self._last_sync_date
        metrics["last_event_log_id"] = self._last_event_log_id
        metrics["last_root_definitions"] = self._last_root_definitions
        metrics["last_remote_full_scan"] = self._last_remote_full_scan
        metrics["next_polling"] = self._next_check
        return metrics

    def _execute(self) -> None:
        first_pass = True
        now = monotonic
        handle_changes = self._handle_changes
        interact = self._interact

        try:
            while "working":
                if now() > self._next_check:
                    if handle_changes(first_pass):
                        first_pass = False

                    # Plan the next execution
                    self._next_check = now() + Options.delay

                interact()
                sleep(0.5)
        except ThreadInterrupt:
            self.remoteWatcherStopped.emit()
            raise

    @tooltip("Remote scanning")
    def scan_remote(self, *, from_state: DocPair = None) -> None:
        """Recursively scan the bound remote folder looking for updates"""
        log.debug("Remote full scan")
        start = monotonic()

        try:
            from_state = from_state or self.dao.get_state_from_local(ROOT)
            if not from_state:
                return

            remote_info = self.engine.remote.get_fs_info(from_state.remote_ref)
            if self.dao.update_remote_state(
                from_state,
                remote_info,
                remote_parent_path=from_state.remote_parent_path,
            ):
                self.remove_void_transfers(from_state)
        except NotFound:
            log.info(f"Marking {from_state!r} as remotely deleted")
            # Should unbind ?
            # from_state.update_remote(None)
            return

        self._get_changes()

        # Recursive update
        self._do_scan_remote(from_state, remote_info)
        self._last_remote_full_scan = datetime.utcnow()
        self.dao.update_config("remote_last_full_scan", self._last_remote_full_scan)
        self.dao.clean_scanned()

        log.info(f"Remote scan finished in {monotonic() - start:.02f} sec")
        self.remoteScanFinished.emit()

    @pyqtSlot(str)
    def scan_pair(self, remote_path: str, /) -> None:
        self.dao.add_path_to_scan(str(remote_path))
        self._next_check = 0

    def _scan_pair(self, remote_path: str, /) -> None:
        if remote_path is None:
            return
        remote_path = str(remote_path)
        if self.dao.is_filter(remote_path):
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
        doc_pair = self.dao.get_state_from_remote_with_path(remote_ref, parent_path)
        if doc_pair is not None:
            self._do_scan_remote(doc_pair, child_info)
            return
        log.info(
            f"parent_path: {parent_path!r}\t"
            f"{os.path.basename(parent_path)!r}\t"
            f"{os.path.dirname(parent_path)!r}"
        )
        parent_pair = self.dao.get_state_from_remote_with_path(
            os.path.basename(parent_path), os.path.dirname(parent_path)
        )
        log.info(f"scan_pair: parent_pair: {parent_pair!r}")
        if parent_pair is None:
            return
        local_path = parent_pair.local_path / safe_filename(child_info.name)
        remote_parent_path = (
            parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
        )
        if os.path.dirname(child_info.path) == remote_parent_path:
            row_id = self.dao.insert_remote_state(
                child_info, remote_parent_path, local_path, parent_pair.local_path
            )
            doc_pair = self.dao.get_state_from_id(row_id, from_write=True)
            if doc_pair and child_info.folderish:
                self._do_scan_remote(doc_pair, child_info)
        else:
            log.info(f"Remote scan_pair: {remote_path!r} is not available")
            self.scan_remote()

    @staticmethod
    def _check_modified(pair: DocPair, info: RemoteFileInfo, /) -> bool:
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
        /,
        *,
        force_recursion: bool = True,
        moved: bool = False,
    ) -> None:
        if remote_info.can_scroll_descendants:
            log.info(
                "Performing scroll remote scan "
                f"for {remote_info.name!r} ({remote_info})"
            )
            self._scan_remote_scroll(doc_pair, remote_info, moved=moved)
        else:
            log.info(
                "Scroll scan not available, performing recursive remote scan "
                f"for {remote_info.name!r} ({remote_info})"
            )
            self._scan_remote_recursive(
                doc_pair, remote_info, force_recursion=force_recursion
            )

    def _scan_remote_scroll(
        self, doc_pair: DocPair, remote_info: RemoteFileInfo, /, *, moved: bool = False
    ) -> None:
        """
        Perform a scroll scan of the bound remote folder looking for updates.
        """

        def sorting_func(descendant: RemoteFileInfo) -> Tuple[int, str, str]:
            """Sort function used when sorting descendants in a remote scroll scan.

            The sorting is done on:
                1: the path length to sync parents first;
                2: the parent's UID to sync children of a same parent consecutively;
                3: the document's name to sync document alphabetically (no natural sorting).

            That sorting will make the app to sync all files from the 1st (sub*)folder,
            then sync all files from the next (sub*)folder, ... , until the sync of all
            files of the latest (sub*)folder.
            """
            return len(descendant.path), descendant.parent_uid, descendant.name

        remote_parent_path = self._init_scan_remote(doc_pair, remote_info)
        if remote_parent_path is None:
            return

        # Detect recently deleted children
        if moved:
            db_descendants = self.dao.get_remote_descendants_from_ref(
                doc_pair.remote_ref
            )
        else:
            db_descendants = self.dao.get_remote_descendants(remote_parent_path)
        descendants = {desc.remote_ref: desc for desc in db_descendants}

        to_process = []
        scroll_id = None

        while "Scrolling":
            # Scroll through a batch of descendants
            log.debug(
                f"Scrolling through at most [{BATCH_SIZE}] descendants "
                f"of {remote_info.name!r} ({remote_info.uid})"
            )
            scroll_res = self.engine.remote.scroll_descendants(
                remote_info.uid, scroll_id, batch_size=BATCH_SIZE
            )

            descendants_info = scroll_res["descendants"]
            if not descendants_info:
                break

            log.debug(
                f"Remote scroll request retrieved {len(descendants_info)} descendants "
                f"for {remote_info.name!r} ({remote_info.uid})"
            )

            scroll_id = scroll_res["scroll_id"]

            # Results are not necessarily sorted
            descendants_info = sorted(descendants_info, key=sorting_func)

            # Handle descendants
            for descendant_info in descendants_info:
                if self.filtered(descendant_info):
                    log.info(f"Ignoring banned document {descendant_info}")
                    descendants.pop(descendant_info.uid, None)
                    continue

                if self.dao.is_filter(descendant_info.path):
                    log.debug(f"Skipping filtered document {descendant_info}")
                    descendants.pop(descendant_info.uid, None)
                    continue

                if descendant_info.digest == "notInBinaryStore":
                    log.debug(
                        f"Skipping unsyncable document {descendant_info} (digest is 'notInBinaryStore')"
                    )
                    self.engine.send_metric("sync", "skip", "notInBinaryStore")
                    descendants.pop(descendant_info.uid, None)
                    continue

                log.debug(f"Handling remote descendant {descendant_info!r}")
                if descendant_info.uid in descendants:
                    descendant_pair = descendants.pop(descendant_info.uid)
                    if self._check_modified(descendant_pair, descendant_info):
                        descendant_pair.remote_state = "modified"
                    if self.dao.update_remote_state(descendant_pair, descendant_info):
                        self.remove_void_transfers(descendant_pair)
                    continue

                parent_pair = self.dao.get_normal_state_from_remote(
                    descendant_info.parent_uid
                )
                if not parent_pair:
                    log.debug(
                        "Cannot find parent pair of remote descendant, "
                        f"postponing processing of {descendant_info}"
                    )
                    to_process.append(descendant_info)
                    continue

                self._find_remote_child_match_or_create(parent_pair, descendant_info)

            """
            # That code is kept for information purpose as it seems to be a good idea to stop now (see NXDRIVE-1636)
            # but the NuxeoDrive.ScrollDescendants operation contract is to return *at most* BATCH_SIZE documents.
            # This is because the batch size represents the max number of descendant docs IDs to handle (query),
            # then they get adapted to FileSystemItem in Java, so this post-filtering can remove some docs comparing
            # to the max size, typically the docs for which permissions are denied.
            # (comment added when investigating the issue with NXDRIVE-1832)
            if len(descendants_info) < BATCH_SIZE:
                log.debug(f"Less descendants than {BATCH_SIZE}, finishing scroll.")
                break
            """

            # Check if synchronization thread was suspended
            self._interact()

        if to_process:
            log.debug(
                f"Processing [{len(to_process)}] postponed descendants of "
                f"{remote_info.name!r} ({remote_info.uid})"
            )
            for descendant_info in sorted(to_process, key=sorting_func):
                parent_pair = self.dao.get_normal_state_from_remote(
                    descendant_info.parent_uid
                )
                if not parent_pair:
                    log.warning(
                        "Cannot find parent pair of postponed remote descendant, "
                        f"ignoring {descendant_info}"
                    )
                    continue

                self._find_remote_child_match_or_create(parent_pair, descendant_info)

        # Delete remaining
        for deleted in descendants.values():
            self.dao.delete_remote_state(deleted)
            self.remove_void_transfers(deleted)

    def _scan_remote_recursive(
        self,
        doc_pair: DocPair,
        remote_info: RemoteFileInfo,
        /,
        *,
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
        db_children = self.dao.get_remote_children(doc_pair.remote_ref)
        children: Dict[str, DocPair] = {
            child.remote_ref: child for child in db_children
        }
        children_info = self.engine.remote.get_fs_children(remote_info.uid)

        to_scan = []
        for child_info in children_info:
            if self.filtered(child_info):
                log.info(f"Ignoring banned file: {child_info!r}")
                continue

            if child_info.digest == "notInBinaryStore":
                log.debug(
                    f"Skipping unsyncable document {child_info} (digest is 'notInBinaryStore')"
                )
                self.engine.send_metric("sync", "skip", "notInBinaryStore")
                continue

            log.debug(f"Scanning remote child: {child_info!r}")
            new_pair = False
            child_pair = None
            if child_info.uid in children:
                child_pair = children.pop(child_info.uid)
                if self._check_modified(child_pair, child_info):
                    child_pair.remote_state = "modified"
                if self.dao.update_remote_state(
                    child_pair, child_info, remote_parent_path=remote_parent_path
                ):
                    self.remove_void_transfers(child_pair)
            else:
                match_pair = self._find_remote_child_match_or_create(
                    doc_pair, child_info
                )
                if match_pair:
                    child_pair, new_pair = match_pair

            if not child_pair:
                log.error(
                    f"child_pair is None, it should not happen (NXDRIVE-1571, child_info={child_info!r})."
                )
            elif (new_pair or force_recursion) and child_info.folderish:
                to_scan.append((child_pair, child_info))

        # Delete remaining
        for deleted in children.values():
            self.dao.delete_remote_state(deleted)
            self.remove_void_transfers(deleted)

        for pair, info in to_scan:
            # TODO Optimize by multithreading this too ?
            self._do_scan_remote(pair, info, force_recursion=force_recursion)
        self.dao.add_path_scanned(remote_parent_path)

    def _init_scan_remote(
        self, doc_pair: DocPair, remote_info: RemoteFileInfo, /
    ) -> Optional[str]:
        if remote_info is None:
            raise ValueError(f"Cannot bind {doc_pair!r} to missing remote info")

        if not remote_info.folderish:
            # No children to align, early stop.
            log.debug(
                f"Skip remote scan as it is not a folderish document: {remote_info!r}"
            )
            return None

        remote_parent_path = doc_pair.remote_parent_path + "/" + remote_info.uid
        if self.dao.is_path_scanned(remote_parent_path):
            log.debug(f"Skip already remote scanned: {doc_pair.local_path!r}")
            return None

        if doc_pair.local_path:
            Action(f"Remote scanning „{doc_pair.local_path}“")
            log.info(f"Remote scanning: {doc_pair.local_path!r}")

        return remote_parent_path

    def _find_remote_child_match_or_create(
        self, parent_pair: DocPair, child_info: RemoteFileInfo, /
    ) -> Optional[Tuple[DocPair, bool]]:
        if parent_pair.last_error == "DEDUP":
            log.info(
                f"Ignoring child {child_info!r} of a duplicate folder "
                f"in error {parent_pair!r}"
            )
            return None

        if self.dao.get_normal_state_from_remote(child_info.uid):
            log.warning(
                "Illegal state: a remote creation cannot happen if "
                "there already is the same remote ref in the database"
            )
            return None

        local_path = parent_pair.local_path / safe_filename(child_info.name)
        remote_parent_path = (
            parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
        )
        # Try to get the local definition if not linked
        child_pair = self.dao.get_state_from_local(local_path)
        if (
            child_pair is None
            and parent_pair is not None
            and self.engine.local.exists(parent_pair.local_path)
        ):
            for child in self.engine.local.get_children_info(parent_pair.local_path):
                if self.engine.local.get_remote_id(child.path) == child_info.uid:
                    log.info(
                        f"Found a local rename case: {child_info!r} on {child.path!r}"
                    )
                    child_pair = self.dao.get_state_from_local(child.path)
                    break
        if child_pair:
            if child_pair.remote_ref and child_pair.remote_ref != child_info.uid:
                log.info(
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
                        self.remove_void_transfers(child_pair)
                        local_info = self.engine.local.get_info(child_pair.local_path)
                        self.dao.update_local_state(child_pair, local_info)
                        self.dao.update_remote_state(
                            child_pair,
                            child_info,
                            remote_parent_path=remote_parent_path,
                        )
                    else:
                        self.dao.update_remote_state(
                            child_pair,
                            child_info,
                            remote_parent_path=remote_parent_path,
                        )
                        # Use version+1 as we just update the remote info
                        synced = self.dao.synchronize_state(
                            child_pair, version=child_pair.version + 1
                        )
                        if not synced:
                            # Try again, might happen that it has been modified locally and remotely
                            refreshed = self.dao.get_state_from_id(child_pair.id)
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
                                self.dao.synchronize_state(refreshed)
                                refreshed = self.dao.get_state_from_id(refreshed.id)
                                synced = bool(
                                    refreshed and refreshed.pair_state == "synchronized"
                                )

                            child_pair = refreshed or child_pair
                        # Can be updated in previous call
                        if synced:
                            self.engine.stop_processor_on(child_pair.local_path)
                        # Push the remote_Id
                        log.info(
                            f"Set remote ID on {child_pair!r} / "
                            f"{child_pair.local_path!r} == {child_pair.local_path!r}"
                        )
                        self.engine.local.set_remote_id(
                            child_pair.local_path, child_info.uid
                        )
                        if child_pair.folderish:
                            self.dao.queue_children(child_pair)
                else:
                    child_pair.remote_state = "modified"
                    if self.dao.update_remote_state(
                        child_pair, child_info, remote_parent_path=remote_parent_path
                    ):
                        self.remove_void_transfers(child_pair)
                child_pair = self.dao.get_state_from_id(child_pair.id, from_write=True)
                return (child_pair, False) if child_pair else None
        row_id = self.dao.insert_remote_state(
            child_info, remote_parent_path, local_path, parent_pair.local_path
        )
        child_pair = self.dao.get_state_from_id(row_id, from_write=True)
        return (child_pair, True) if child_pair else None

    def _handle_readonly(self, doc_pair: DocPair, /) -> None:
        # Don't use readonly on folder for win32 and on Locally Edited
        if doc_pair.folderish and WINDOWS:
            return
        if doc_pair.is_readonly():
            log.info(f"Setting {doc_pair.local_path!r} as readonly")
            self.engine.local.set_readonly(doc_pair.local_path)
        else:
            log.info(f"Unsetting {doc_pair.local_path!r} as readonly")
            self.engine.local.unset_readonly(doc_pair.local_path)

    def _partial_full_scan(self, path: str, /) -> None:
        log.info(f"Continue full scan of {path!r}")
        if path == "/":
            self.scan_remote()
        else:
            self._scan_pair(path)
        self.dao.delete_path_to_scan(path)
        self.dao.delete_config("remote_need_full_scan")
        self.dao.clean_scanned()

    def _check_offline(self) -> bool:
        """Return True if the engine is offline."""
        if not self.engine.is_offline():
            return False

        online = self.engine.remote.client.is_reachable()
        if online:
            self.engine.set_offline(value=False)

        return not online

    def _handle_changes(self, first_pass: bool, /) -> bool:
        # If synchronization features are disabled, we just need to emit
        # the appropriate signal to let the systray icon be updated.
        if not Feature.synchronization:
            if first_pass:
                self.initiate.emit()
                return True
            self.updated.emit()
            return False

        if self._check_offline():
            return False

        log.debug(f"Handle remote changes, first_pass={first_pass!r}")

        try:
            if not self._last_remote_full_scan:
                self.scan_remote()

                # Might need to handle the changes now
                if first_pass:
                    self.initiate.emit()
                return True

            full_scan = self.dao.get_config("remote_need_full_scan")
            if full_scan is not None:
                self._partial_full_scan(full_scan)
                return False

            paths = self.dao.get_paths_to_scan()
            while paths:
                remote_ref = paths[0]
                self.dao.update_config("remote_need_full_scan", remote_ref)
                self._partial_full_scan(remote_ref)
                paths = self.dao.get_paths_to_scan()

            self._update_remote_states()
            (self.updated, self.initiate)[first_pass].emit()
        except BadQuery:
            # This should never happen: there is an error in the operation's
            # parameters sent to the server.  This exception is possible only
            # in debug mode or when running the test suite.
            log.critical("Oops! Bad query parameter", exc_info=True)
            raise
        except ScrollDescendantsError as exc:
            log.warning(exc)
        except Unauthorized:
            self.engine.set_invalid_credentials()
            self.engine.set_offline()
        except (*CONNECTION_ERROR, OSError) as exc:
            log.warning(f"Network error: {exc}")
        except HTTPError as exc:
            status = exc.status
            err = f"HTTP error {status} while trying to handle remote changes"
            if status == 504:
                log.warning(f"Gateaway timeout: {exc}")
            else:
                log.warning(err)
        except ThreadInterrupt:
            raise
        except Exception:
            log.exception("Unexpected error")
        else:
            return True
        finally:
            Action.finish_action()

        return False

    def _call_and_measure_gcs(self) -> Optional[Dict[str, Any]]:
        """Call the NuxeoDrive.GetChangesSummary operation and measure the time taken."""
        start = monotonic()
        try:
            return self.engine.remote.get_changes(
                self._last_root_definitions, log_id=self._last_event_log_id
            )
        finally:
            end = monotonic()
            elapsed = round(end - start)
            self.engine.send_metric(
                "operation", "NuxeoDrive.GetChangesSummary", str(elapsed)
            )

    def _get_changes(self) -> Optional[Dict[str, Any]]:
        """Fetch incremental change summary from the server"""
        summary = self._call_and_measure_gcs()
        if not isinstance(summary, dict):
            log.warning("Change summary is not a valid dictionary.")
            return None

        root_defs = summary.get("activeSynchronizationRootDefinitions")
        if root_defs is None:
            log.warning(
                "Change summary is missing the root definitions, "
                "We'll skip its processing."
            )
            return None

        self._last_root_definitions = root_defs
        self._last_sync_date = int(summary.get("syncDate", 0))
        # If available, read 'upperBound' key as last event log id
        # according to the new implementation of the audit change finder,
        # see https://jira.nuxeo.com/browse/NXP-14826.
        self._last_event_log_id = int(summary.get("upperBound", 0))

        self.dao.store_int("remote_last_sync_date", self._last_sync_date)
        self.dao.store_int("remote_last_event_log_id", self._last_event_log_id)
        self.dao.update_config(
            "remote_last_root_definitions", self._last_root_definitions
        )

        return summary

    def _force_remote_scan(
        self,
        doc_pair: DocPair,
        remote_info: RemoteFileInfo,
        /,
        *,
        remote_path: str = None,
        force_recursion: bool = True,
        moved: bool = False,
    ) -> None:
        if remote_path is None:
            remote_path = remote_info.path
        if force_recursion:
            self.dao.add_path_to_scan(remote_path)
        else:
            self._do_scan_remote(
                doc_pair, remote_info, force_recursion=force_recursion, moved=moved
            )

    @tooltip("Handle remote changes")
    def _update_remote_states(self) -> None:
        """Incrementally update the state of documents from a change summary"""
        summary = self._get_changes()
        if not summary:
            return

        if summary.get("hasTooManyChanges"):
            log.info("Forced full scan by server")
            remote_path = "/"
            self.dao.add_path_to_scan(remote_path)
            self.dao.update_config("remote_need_full_scan", remote_path)
            return

        if not summary.get("fileSystemChanges"):
            self.empty_polls += 1
            self.noChangesFound.emit()
            return

        # Fetch all events and consider the most recent first
        sorted_changes = sorted(
            summary["fileSystemChanges"], key=itemgetter("eventDate"), reverse=True
        )

        self.empty_polls = 0
        self.changesFound.emit(len(sorted_changes))

        # Scan events and update the related pair states
        refreshed: Set[str] = set()
        delete_queue = []
        for change in sorted_changes:
            # Check if synchronization thread was suspended
            # TODO In case of pause or stop: save the last event id
            self._interact()

            fs_item = change.get("fileSystemItem")

            if fs_item and fs_item.get("digest", "") == "notInBinaryStore":
                log.debug(
                    f"Skipping unsyncable document {change} (digest is 'notInBinaryStore')"
                )
                self.engine.send_metric("sync", "skip", "notInBinaryStore")
                continue

            log.debug(f"Processing event: {change!r}")

            event_id = change.get("eventId")
            remote_ref = change["fileSystemItemId"]

            if any(refreshed_ref.endswith(remote_ref) for refreshed_ref in refreshed):
                log.debug("A more recent version was already processed")
                continue

            new_info = RemoteFileInfo.from_dict(fs_item) if fs_item else None
            if self.filtered(new_info):
                log.info(f"Ignoring banned file: {new_info!r}")
                continue

            # Possibly fetch multiple doc pairs as the same doc
            # can be synchronized in 2 places,
            # typically if under a sync root and locally edited.
            # See https://jira.nuxeo.com/browse/NXDRIVE-125
            doc_pairs = self.dao.get_states_from_remote(remote_ref)
            if not doc_pairs:
                # Relax constraint on factory name in FileSystemItem id to
                # match 'deleted' or 'securityUpdated' events.
                # See https://jira.nuxeo.com/browse/NXDRIVE-167
                doc_pair = self.dao.get_first_state_from_partial_remote(remote_ref)
                if doc_pair:
                    doc_pairs = [doc_pair]

            updated = False
            doc_pairs = doc_pairs or []
            for doc_pair in doc_pairs:
                if not doc_pair:
                    continue

                doc_pair_repr = doc_pair.local_path or doc_pair.remote_name
                if event_id == DELETED_EVENT:
                    if fs_item is None or new_info is None:
                        if doc_pair.last_error == "DEDUP":
                            log.info(f"Delete pair from duplicate: {doc_pair!r}")
                            self.dao.remove_state(doc_pair, remote_recursion=True)
                            self.remove_void_transfers(doc_pair)
                            continue
                        log.info(f"Push doc_pair {doc_pair_repr!r} in delete queue")
                        delete_queue.append(doc_pair)
                    else:
                        log.info(
                            f"Ignore delete on doc_pair {doc_pair_repr!r} "
                            "as a fsItem is attached"
                        )
                        # To ignore completely put updated to true
                        updated = True
                        break
                elif fs_item is None or new_info is None:
                    if event_id == SECURITY_UPDATED_EVENT:
                        log.info(
                            f"Security has been updated for doc_pair {doc_pair_repr!r} "
                            "denying Read access, marking it as deleted"
                        )
                        self.dao.delete_remote_state(doc_pair)
                        self.remove_void_transfers(doc_pair)
                    else:
                        log.warning(f"Unknown event: {event_id!r}")
                else:
                    remote_parent_factory = doc_pair.remote_parent_ref.split("#", 1)[0]
                    new_info_parent_factory = new_info.parent_uid.split("#", 1)[0]
                    # Specific cases of a move on a locally edited doc
                    if (
                        remote_parent_factory == COLLECTION_SYNC_ROOT_FACTORY_NAME
                        and event_id == DOCUMENT_MOVED
                    ):
                        # If moved from a non sync root to a sync root,
                        # break to creation case (updated is False).
                        # If moved from a sync root to a non sync root,
                        # break to noop (updated is True).
                        break
                    elif (
                        new_info_parent_factory == COLLECTION_SYNC_ROOT_FACTORY_NAME
                        and event_id == DOCUMENT_MOVED
                    ):
                        # If moved from a sync root to a non sync root,
                        # delete from local sync root
                        log.info(f"Marking doc_pair {doc_pair_repr!r} as deleted")
                        self.dao.delete_remote_state(doc_pair)
                        self.remove_void_transfers(doc_pair)
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
                            consistent_new_info = RemoteFileInfo(
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

                        # Force remote state update in case of a
                        # locked / unlocked event since lock info is not
                        # persisted, so not part of the dirty check
                        lock_update = event_id in (DOCUMENT_LOCKED, DOCUMENT_UNLOCKED)

                        # Perform a regular document update on a document
                        # that has been updated, renamed or moved

                        if doc_pair.remote_state != "created" and any(
                            (
                                new_info.digest != doc_pair.remote_digest,
                                safe_filename(new_info.name) != doc_pair.remote_name,
                                new_info.parent_uid != doc_pair.remote_parent_ref,
                                event_id == SECURITY_UPDATED_EVENT,
                                lock_update,
                            )
                        ):
                            doc_pair.remote_state = "modified"

                        log.info(
                            f"Refreshing remote state info for doc_pair={doc_pair!r}, "
                            f"event_id={event_id!r}, new_info={new_info!r} "
                            f"(force_recursion={event_id == SECURITY_UPDATED_EVENT})"
                        )

                        remote_parent_path = os.path.dirname(new_info.path)

                        # TODO Add modify local_path and local_parent_path
                        # if needed

                        if doc_pair.pair_state == "remotely_created" and (
                            not doc_pair.local_path.exists()  # file doesn't exists yet
                            or self.engine.local.get_remote_id(doc_pair.local_path)
                            != doc_pair.remote_ref  # file exists but belongs to another document
                        ):
                            # We are trying to synchronize a duplicate
                            # that has been renamed remotely (NXDRIVE-980 for context)

                            # Make name safe by removing invalid chars
                            name = safe_filename(new_info.name)

                            info = FileInfo(
                                self.engine.local_folder,
                                doc_pair.local_path.with_name(name),
                                doc_pair.folderish,
                                get_date_from_sqlite(doc_pair.last_remote_updated)
                                or datetime.now(),
                            )
                            log.info(
                                f"Trying to synchronize remote duplicate rename of {doc_pair}, "
                                f"forcing new local path {info}"
                            )
                            self.dao.update_local_state(doc_pair, info, versioned=False)

                        if self.dao.update_remote_state(
                            doc_pair,
                            new_info,
                            remote_parent_path=remote_parent_path,
                            force_update=lock_update,
                        ):
                            self.remove_void_transfers(doc_pair)

                        if doc_pair.folderish:
                            if (
                                event_id == SECURITY_UPDATED_EVENT
                                and not doc_pair.remote_can_create_child
                                and new_info.can_create_child
                            ):
                                log.info("Force local scan after permissions change")
                                self.dao.unset_unsychronised(doc_pair)

                            log.debug(
                                f"Force scan recursive on {doc_pair!r}, "
                                f"permissions change={event_id == SECURITY_UPDATED_EVENT!r}"
                            )
                            self._force_remote_scan(
                                doc_pair,
                                consistent_new_info,
                                remote_path=new_info.path,
                                force_recursion=event_id == SECURITY_UPDATED_EVENT,
                                moved=event_id == DOCUMENT_MOVED,
                            )

                        if lock_update:
                            locked_pair = self.dao.get_state_from_id(doc_pair.id)
                            if locked_pair:
                                try:
                                    self._handle_readonly(locked_pair)
                                except OSError as exc:
                                    log.warning(
                                        f"Cannot handle readonly for {locked_pair!r} ({exc!r})"
                                    )

                pair = self.dao.get_state_from_id(doc_pair.id)
                if pair and pair.last_error != "DEDUP":
                    self.engine.manager.osi.send_sync_status(
                        pair, self.engine.local.abspath(pair.local_path)
                    )

                updated = True
                refreshed.add(remote_ref)

            if new_info and not updated:
                # Handle new document creations
                created = False
                parent_pairs = self.dao.get_states_from_remote(new_info.parent_uid)
                for parent_pair in parent_pairs:
                    match_pair = self._find_remote_child_match_or_create(
                        parent_pair, new_info
                    )
                    if match_pair:
                        child_pair = match_pair[0]
                        if child_pair.folderish:
                            log.info(
                                "Remote recursive scan of the content "
                                f"of {child_pair.remote_name!r}"
                            )
                            remote_path = (
                                f"{child_pair.remote_parent_path}/{new_info.uid}"
                            )
                            self._force_remote_scan(
                                child_pair, new_info, remote_path=remote_path
                            )
                        else:
                            log.info(
                                f"Marked doc_pair {child_pair.remote_name!r} "
                                "as remote creation"
                            )

                    created = True
                    refreshed.add(remote_ref)
                    break

                if not created:
                    log.info(
                        "Could not match changed document to a bound "
                        f"local folder: {new_info!r}"
                    )

        # Sort by path the deletion to only mark parent
        sorted_deleted = sorted(delete_queue, key=attrgetter("local_path"))
        delete_processed: DocPairs = []
        for delete_pair in sorted_deleted:
            # Mark as deleted
            skip = False
            for processed_pair in delete_processed:
                if processed_pair.local_path in delete_pair.local_path.parents:
                    skip = True
                    break

            if skip:
                continue

            # Verify the file is really deleted
            if self.engine.remote.get_fs_item(delete_pair.remote_ref):
                continue

            delete_processed.append(delete_pair)
            log.info(f"Marking doc_pair {delete_pair!r} as deleted")
            self.dao.delete_remote_state(delete_pair)
            self.remove_void_transfers(delete_pair)

    def filtered(self, info: Optional[RemoteFileInfo], /) -> bool:
        """Check if a remote document is locally ignored."""
        return (
            info is not None
            and not info.folderish
            and self.engine.local.is_ignored(ROOT, info.name)
        )
