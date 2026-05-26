"""
Remote watcher for Alfresco — polls the Alfresco Sync Service for changes.

Replaces the Nuxeo-specific ``RemoteWatcher`` which relies on
``GetChangeSummary`` and NuxeoDrive operations.
"""

from datetime import datetime, timezone
from logging import getLogger
from time import monotonic, sleep
from typing import TYPE_CHECKING, Dict, List, Optional

from ...exceptions import ThreadInterrupt
from ...objects import DocPair, Metrics, RemoteFileInfo
from ...options import Options
from ...qt.imports import pyqtSignal
from ..activity import tooltip
from ..workers import EngineWorker

if TYPE_CHECKING:
    from ...dao.engine import EngineDAO
    from ..alfresco_engine import AlfrescoEngine

__all__ = ("AlfrescoRemoteWatcher",)

log = getLogger(__name__)

# Defer reason constants — used for structured logging so operators
# can grep for "ALFRESCO_DEFER" and see why changes were postponed.
DEFER_PARENT_NOT_SYNCED = "ParentNotSynced"
DEFER_MOVE_TARGET_NOT_SYNCED = "MoveTargetNotSynced"
DEFER_SERVER_OFFLINE = "ServerOffline"
DEFER_NETWORK_ERROR = "NetworkError"
DEFER_CHECKED_OUT = "CheckedOut"
DEFER_SOURCE_LOCKED = "SourceLocked"
DEFER_NO_WRITE_PERMISSION = "NoWritePermission"
DEFER_TRANSFER_TIMEOUT = "TransferTimeout"
DEFER_CONFLICT = "Conflict"
DEFER_FREE_SPACE = "FreeSpace"


class AlfrescoRemoteWatcher(EngineWorker):
    """Poll the Alfresco Sync Service for remote changes."""

    initiate = pyqtSignal()
    updated = pyqtSignal()
    remoteScanFinished = pyqtSignal()
    changesFound = pyqtSignal(int)
    noChangesFound = pyqtSignal()
    remoteWatcherStopped = pyqtSignal()

    def __init__(self, engine: "AlfrescoEngine", dao: "EngineDAO", /) -> None:
        super().__init__(engine, dao, "AlfrescoRemoteWatcher")

        self.empty_polls = 0
        self._next_check = 0.0
        # Opaque change cursor from the Alfresco Sync Service
        self._since_marker: Optional[str] = self.dao.get_config(
            "alfresco_last_since_marker"
        )
        # Deferred changes that could not be processed immediately
        # (e.g. parent not synced yet).  Retried on the next poll cycle.
        self._deferred_changes: List[Dict] = []
        # Track last full remote scan timestamp (persisted to DAO)
        self._last_remote_full_scan: Optional[datetime] = self.dao.get_config(
            "remote_last_full_scan"
        )

    def get_metrics(self) -> Metrics:
        metrics = super().get_metrics()
        metrics["last_since_marker"] = self._since_marker
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
                    self._next_check = now() + Options.delay

                interact()
                sleep(0.5)
        except ThreadInterrupt:
            self.remoteWatcherStopped.emit()
            raise

    # -- Initial full tree scan ----------------------------------------------

    @tooltip("Remote full scan (Alfresco)")
    def scan_remote(self) -> None:
        """Perform a full recursive scan of the remote tree.

        Walks the Alfresco folder hierarchy via ``list_children`` and
        populates the DAO with ``DocPair`` entries for every file and
        folder found on the server.  This mirrors the Nuxeo
        ``RemoteWatcher.scan_remote()`` flow.

        Called once on the first pass, or when re-scan is needed.
        """
        log.info("Starting Alfresco full remote scan")
        start = monotonic()
        remote = self.engine.remote
        if not remote:
            return

        root_pair = self.dao.get_state_from_local(
            self.engine.download_dir
            if hasattr(self.engine, "download_dir")
            else __import__("pathlib").PurePosixPath("/")
        )
        if not root_pair:
            # Try ROOT constant
            from ...constants import ROOT

            root_pair = self.dao.get_state_from_local(ROOT)
        if not root_pair or not root_pair.remote_ref:
            log.warning("No root pair found, cannot scan remote tree")
            return

        # Refresh root metadata
        try:
            root_info = remote._node_to_remote_file_info(
                remote.get_node(root_pair.remote_ref, include=["path"])
            )
            self.dao.update_remote_state(
                root_pair,
                root_info,
                remote_parent_path=root_pair.remote_parent_path,
            )
        except Exception:
            log.warning("Error refreshing root info", exc_info=True)
            return

        # Recursive walk
        self._scan_remote_recursive(root_pair, root_info)

        self._last_remote_full_scan = datetime.now(tz=timezone.utc)
        self.dao.update_config("remote_last_full_scan", self._last_remote_full_scan)

        log.info(f"Alfresco full remote scan finished in {monotonic() - start:.2f}s")
        self.remoteScanFinished.emit()

    def _scan_remote_recursive(
        self,
        doc_pair: DocPair,
        remote_info: RemoteFileInfo,
    ) -> None:
        """Recursively scan children of a folder and insert/update DAO state.

        Mirrors ``RemoteWatcher._scan_remote_recursive()``: fetch
        children, match or create ``DocPair`` entries, recurse into
        sub-folders, and mark missing children as deleted.
        """
        if not remote_info.folderish:
            return

        self._interact()

        remote = self.engine.remote
        if not remote:
            return

        remote_parent_path = doc_pair.remote_parent_path + "/" + remote_info.uid

        # Fetch DB children for this folder
        db_children = self.dao.get_remote_children(doc_pair.remote_ref)
        children: Dict[str, DocPair] = {
            child.remote_ref: child for child in db_children
        }

        # Fetch remote children via the Alfresco Nodes API
        try:
            nodes = list(
                remote.client.nodes.iter_children(remote_info.uid, include=["path"])
            )
        except Exception:
            log.warning(
                f"Error listing children of {remote_info.name!r}", exc_info=True
            )
            return

        to_scan: List[tuple] = []

        for node in nodes:
            child_info = remote._node_to_remote_file_info(node)

            # Skip filtered paths ("Choose folders to sync" in the GUI).
            # Use the human-readable Alfresco path (from the node's path
            # property) which matches the format stored by the filter dialog.
            if self.dao.is_filter(child_info.path):
                log.debug(f"Skipping filtered path {child_info.path}")
                continue

            if child_info.uid in children:
                # Already known — update state
                child_pair = children.pop(child_info.uid)
                self.dao.update_remote_state(
                    child_pair,
                    child_info,
                    remote_parent_path=remote_parent_path,
                )
                if child_info.folderish:
                    to_scan.append((child_pair, child_info))
            else:
                # New item — insert into DAO
                local_path = doc_pair.local_path / child_info.name
                row_id = self.dao.insert_remote_state(
                    child_info,
                    remote_parent_path,
                    local_path,
                    doc_pair.local_path,
                )
                if child_info.folderish and row_id:
                    child_pair = self.dao.get_state_from_id(row_id, from_write=True)
                    if child_pair:
                        to_scan.append((child_pair, child_info))

        # Mark remaining DB children as deleted on server
        for deleted_pair in children.values():
            self.dao.delete_remote_state(deleted_pair)

        # Recurse into sub-folders
        for pair, info in to_scan:
            self._scan_remote_recursive(pair, info)

    # -- Incremental change polling ------------------------------------------

    @tooltip("Remote scanning (Alfresco)")
    def _handle_changes(self, first_pass: bool = False) -> bool:
        """Fetch and process remote changes from the Alfresco Sync Service."""
        remote = self.engine.remote
        if not remote:
            return False

        # If no full scan has ever been done, do one now.
        # This covers the first pass as well as any scenario where
        # the persisted timestamp was cleared (e.g. forced re-scan).
        if not self._last_remote_full_scan:
            self.scan_remote()
            if first_pass:
                self.initiate.emit()
            return True

        # Check for an on-demand re-scan request (mirrors Nuxeo's
        # ``remote_need_full_scan`` config flag).
        need_rescan = self.dao.get_config("remote_need_full_scan")
        if need_rescan is not None:
            log.info("On-demand full remote re-scan requested")
            self.dao.update_config("remote_need_full_scan", None)
            self.scan_remote()
            return False

        try:
            changes_response = remote.get_changes(
                since=self._since_marker, max_items=100
            )
        except OSError as exc:
            log.warning(
                "ALFRESCO_DEFER: reason=%s node=- name=- " "detail='%s'",
                DEFER_NETWORK_ERROR,
                exc,
            )
            return first_pass
        except Exception as exc:
            log.warning(
                "ALFRESCO_DEFER: reason=%s node=- name=- " "detail='%s'",
                DEFER_SERVER_OFFLINE,
                exc,
            )
            return first_pass

        changes = changes_response.get("changes", [])
        new_marker = changes_response.get("since", self._since_marker)

        if not changes:
            self.empty_polls += 1
            self.noChangesFound.emit()
            if first_pass:
                # Even with no changes, we consider the first pass done
                self.initiate.emit()
                return True
            self.updated.emit()
            return True

        self.empty_polls = 0
        log.info(f"Found {len(changes)} remote change(s) from Alfresco")
        self.changesFound.emit(len(changes))

        # Retry previously deferred changes first
        still_deferred: List[Dict] = []
        for deferred in self._deferred_changes:
            try:
                self._process_change(deferred)
            except _DeferChange as exc:
                log.info(
                    "ALFRESCO_DEFER: reason=%s node=%s name=%s "
                    "detail='retry pending'",
                    exc.reason,
                    deferred.get("id", "-"),
                    deferred.get("name", "-"),
                )
                still_deferred.append(deferred)
            except Exception:
                log.warning(
                    f"Error retrying deferred change: {deferred}", exc_info=True
                )
        self._deferred_changes = still_deferred

        for change in changes:
            try:
                self._process_change(change)
            except _DeferChange as exc:
                log.info(
                    "ALFRESCO_DEFER: reason=%s node=%s name=%s "
                    "detail='deferred for next cycle'",
                    exc.reason,
                    change.get("id", "-"),
                    change.get("name", "-"),
                )
                self._deferred_changes.append(change)
            except Exception:
                log.warning(f"Error processing change: {change}", exc_info=True)

        # Acknowledge processed changes to the Sync Service so it can
        # advance its internal cursor.  This mirrors how the Nuxeo
        # remote watcher reports processed events back to the server.
        try:
            remote.sync()
        except Exception:
            log.warning("Error acknowledging changes to Sync Service", exc_info=True)

        # Persist the cursor for the next poll
        self._since_marker = new_marker
        self.dao.update_config("alfresco_last_since_marker", new_marker)

        self.updated.emit()
        return True

    def _process_change(self, change: Dict) -> None:
        """Process a single change entry from the Alfresco Sync Service.

        The change dict typically has keys like ``id``, ``name``,
        ``nodeType``, ``status`` (CREATED / MODIFIED / DELETED / MOVED /
        RENAMED / LOCKED / UNLOCKED / CHECKOUT / CHECKIN /
        PERMISSION_CHANGED), etc.

        Move and rename detection follows the same pattern as the Nuxeo
        remote watcher: the new metadata is pushed into the DAO via
        ``update_remote_state()``, which sets ``remote_state = 'modified'``.
        The Processor's ``_synchronize_remotely_modified()`` then detects
        the path/name difference and performs the local filesystem operation.

        Raises ``_DeferChange`` if the change cannot be processed now
        (e.g. parent not synced yet) so the caller can retry later.
        """
        node_id = change.get("id", "")
        status = change.get("status", "").upper()
        name = change.get("name", "")

        # Skip changes inside filtered folders.
        # The change may carry a ``path`` from the Sync Service; if so,
        # check it against the selective-sync filters.
        change_path = change.get("path", "")
        if change_path and self.dao.is_filter(change_path):
            log.debug(f"Skipping filtered change {name!r} at {change_path}")
            return

        if status == "DELETED":
            pair = self.dao.get_normal_state_from_remote(node_id)
            if pair:
                log.info(f"Remote delete detected for {name!r} ({node_id})")
                self.dao.delete_remote_state(pair)

        elif status == "CREATED":
            log.info(f"Remote creation detected: {name!r} ({node_id})")
            remote_info = self._change_to_remote_info(change)
            parent_pair = self._find_parent_pair(change)
            if not parent_pair:
                log.debug(f"Parent not synced yet for {name!r}, deferring")
                raise _DeferChange(change, DEFER_PARENT_NOT_SYNCED)
            self.dao.insert_remote_state(
                remote_info,
                parent_pair.remote_ref,
                parent_pair.local_path,
                parent_pair.local_path / name,
            )

        elif status in ("MODIFIED", "MOVED", "RENAMED"):
            pair = self.dao.get_normal_state_from_remote(node_id)
            if pair:
                log.info(f"Remote {status.lower()} detected for {name!r} ({node_id})")
                remote_info = self._change_to_remote_info(change)
                remote_parent_path = pair.remote_parent_path
                new_parent_id = change.get("parentId", "")
                if new_parent_id and new_parent_id != pair.remote_parent_ref:
                    parent_pair = self._find_parent_pair(change)
                    if parent_pair:
                        remote_parent_path = (
                            parent_pair.remote_parent_path
                            + "/"
                            + parent_pair.remote_ref
                        )
                    else:
                        log.debug(
                            f"Move target parent not synced for {name!r}, deferring"
                        )
                        raise _DeferChange(change, DEFER_MOVE_TARGET_NOT_SYNCED)
                self.dao.update_remote_state(
                    pair,
                    remote_info,
                    remote_parent_path=remote_parent_path,
                )

        elif status in ("LOCKED", "CHECKOUT"):
            pair = self.dao.get_normal_state_from_remote(node_id)
            if pair:
                log.info(f"Remote lock detected for {name!r} ({node_id})")
                remote_info = self._change_to_remote_info(change)
                # Mark file as not updatable while locked
                remote_info = RemoteFileInfo(
                    name=remote_info.name,
                    uid=remote_info.uid,
                    parent_uid=remote_info.parent_uid,
                    path=remote_info.path,
                    folderish=remote_info.folderish,
                    last_modification_time=remote_info.last_modification_time,
                    creation_time=remote_info.creation_time,
                    last_contributor=remote_info.last_contributor,
                    digest=remote_info.digest,
                    digest_algorithm=remote_info.digest_algorithm,
                    download_url=remote_info.download_url,
                    can_rename=False,
                    can_delete=False,
                    can_update=False,
                    can_create_child=remote_info.can_create_child,
                    lock_owner=change.get("lockOwner", ""),
                    lock_created=None,
                    can_scroll_descendants=False,
                )
                self.dao.update_remote_state(
                    pair,
                    remote_info,
                    remote_parent_path=pair.remote_parent_path,
                    force_update=True,
                )

        elif status in ("UNLOCKED", "CHECKIN"):
            pair = self.dao.get_normal_state_from_remote(node_id)
            if pair:
                log.info(f"Remote unlock detected for {name!r} ({node_id})")
                remote_info = self._change_to_remote_info(change)
                self.dao.update_remote_state(
                    pair,
                    remote_info,
                    remote_parent_path=pair.remote_parent_path,
                    force_update=True,
                )

        elif status == "PERMISSION_CHANGED":
            pair = self.dao.get_normal_state_from_remote(node_id)
            if pair:
                # Fetch fresh node metadata to get current permissions
                remote = self.engine.remote
                if remote:
                    try:
                        node = remote.get_node(node_id, include=["allowableOperations"])
                        ops = node._raw.get("allowableOperations", [])
                        can_delete = "delete" in ops
                        can_update = "update" in ops
                        can_create = "create" in ops

                        if not any(
                            op in ops for op in ("read", "update", "delete", "create")
                        ):
                            # User lost all access — treat as deletion
                            log.info(
                                f"Access revoked for {name!r} ({node_id}), "
                                "marking as remotely deleted"
                            )
                            self.dao.delete_remote_state(pair)
                        else:
                            log.info(
                                f"Permission change for {name!r} ({node_id}): "
                                f"ops={ops}"
                            )
                            remote_info = self._change_to_remote_info(change)
                            remote_info = RemoteFileInfo(
                                name=remote_info.name,
                                uid=remote_info.uid,
                                parent_uid=remote_info.parent_uid,
                                path=remote_info.path,
                                folderish=remote_info.folderish,
                                last_modification_time=remote_info.last_modification_time,
                                creation_time=remote_info.creation_time,
                                last_contributor=remote_info.last_contributor,
                                digest=remote_info.digest,
                                digest_algorithm=remote_info.digest_algorithm,
                                download_url=remote_info.download_url,
                                can_rename=can_delete,
                                can_delete=can_delete,
                                can_update=can_update,
                                can_create_child=can_create,
                                lock_owner=remote_info.lock_owner,
                                lock_created=remote_info.lock_created,
                                can_scroll_descendants=False,
                            )
                            self.dao.update_remote_state(
                                pair,
                                remote_info,
                                remote_parent_path=pair.remote_parent_path,
                                force_update=True,
                            )
                    except Exception:
                        log.warning(
                            f"Error fetching permissions for {node_id}",
                            exc_info=True,
                        )

    def _change_to_remote_info(self, change: Dict) -> RemoteFileInfo:
        """Convert a sync-service change entry to RemoteFileInfo."""
        node_type = change.get("nodeType", "")
        is_folder = "folder" in node_type.lower()

        return RemoteFileInfo(
            name=change.get("name", ""),
            uid=change.get("id", ""),
            parent_uid=change.get("parentId", ""),
            path=change.get("path", ""),
            folderish=is_folder,
            last_modification_time=None,
            creation_time=None,
            last_contributor=None,
            digest=change.get("digest"),
            digest_algorithm=change.get("digestAlgorithm"),
            download_url=None,
            can_rename=True,
            can_delete=True,
            can_update=not is_folder,
            can_create_child=is_folder,
            lock_owner=None,
            lock_created=None,
            can_scroll_descendants=False,
        )

    def _find_parent_pair(self, change: Dict) -> Optional[DocPair]:
        """Find the DocPair for the parent of a changed node."""
        parent_id = change.get("parentId", "")
        if parent_id:
            return self.dao.get_normal_state_from_remote(parent_id)
        return None

    def scan_pair(self, remote_path: str, /) -> None:
        """Schedule a remote path for re-scan on the next poll cycle."""
        self._next_check = 0


class _DeferChange(Exception):
    """Raised by ``_process_change`` to signal that a change cannot be
    processed now and should be retried on the next poll cycle.

    The *reason* should be one of the ``DEFER_*`` constants defined at
    module level so that log messages are consistent and grep-friendly.
    """

    def __init__(self, change: Dict, reason: str = "Unknown") -> None:
        self.change = change
        self.reason = reason
        super().__init__(f"{change.get('id', '')} ({reason})")
