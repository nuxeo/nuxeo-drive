"""
Remote watcher for Alfresco — polls the Alfresco Sync Service for changes.

Replaces the Nuxeo-specific ``RemoteWatcher`` which relies on
``GetChangeSummary`` and NuxeoDrive operations.
"""

from logging import getLogger
from time import monotonic, sleep
from typing import TYPE_CHECKING, Dict, Optional

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

    def get_metrics(self) -> Metrics:
        metrics = super().get_metrics()
        metrics["last_since_marker"] = self._since_marker
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

    @tooltip("Remote scanning (Alfresco)")
    def _handle_changes(self, first_pass: bool = False) -> bool:
        """Fetch and process remote changes from the Alfresco Sync Service."""
        remote = self.engine.remote
        if not remote:
            return False

        if first_pass:
            self.initiate.emit()
            if not first_pass:
                return True

        try:
            changes_response = remote.get_changes(
                since=self._since_marker, max_items=100
            )
        except Exception:
            log.warning("Error fetching Alfresco changes", exc_info=True)
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

        for change in changes:
            try:
                self._process_change(change)
            except Exception:
                log.warning(f"Error processing change: {change}", exc_info=True)

        # Persist the cursor for the next poll
        self._since_marker = new_marker
        self.dao.update_config("alfresco_last_since_marker", new_marker)

        self.updated.emit()
        return True

    def _process_change(self, change: Dict) -> None:
        """Process a single change entry from the Alfresco Sync Service.

        The change dict typically has keys like ``id``, ``name``,
        ``nodeType``, ``status`` (CREATED / MODIFIED / DELETED), etc.
        """
        node_id = change.get("id", "")
        status = change.get("status", "").upper()
        name = change.get("name", "")

        if status == "DELETED":
            pair = self.dao.get_normal_state_from_remote(node_id)
            if pair:
                log.info(f"Remote delete detected for {name!r} ({node_id})")
                self.dao.mark_descendants_remotely_deleted(pair)
        elif status == "CREATED":
            log.info(f"Remote creation detected: {name!r} ({node_id})")
            # Build a RemoteFileInfo from the change data
            remote_info = self._change_to_remote_info(change)
            parent_pair = self._find_parent_pair(change)
            if parent_pair:
                self.dao.insert_remote_state(
                    remote_info,
                    parent_pair.remote_ref,
                    parent_pair.local_path,
                    parent_pair.local_path / name,
                )
        elif status == "MODIFIED":
            pair = self.dao.get_normal_state_from_remote(node_id)
            if pair:
                log.info(f"Remote modification detected for {name!r} ({node_id})")
                remote_info = self._change_to_remote_info(change)
                self.dao.update_remote_state(
                    pair,
                    remote_info,
                    remote_parent_path=pair.remote_parent_path,
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
