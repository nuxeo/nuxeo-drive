"""
Remote watcher for Alfresco — polls the server for changes via full
remote tree scans.

Replaces the Nuxeo-specific ``RemoteWatcher`` which relies on
``GetChangeSummary`` and NuxeoDrive operations.
"""

from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from time import monotonic, sleep
from typing import TYPE_CHECKING, Dict, List, Optional

from alfresco.exceptions import AuthenticationError as AlfrescoAuthError
from alfresco.exceptions import NetworkError as AlfrescoNetworkError

from nxdrive.drive.constants import ROOT
from nxdrive.drive.engine.activity import tooltip
from nxdrive.drive.engine.workers import EngineWorker
from nxdrive.drive.exceptions import ThreadInterrupt
from nxdrive.drive.objects import DocPair, Metrics, RemoteFileInfo
from nxdrive.drive.options import Options
from nxdrive.drive.qt.imports import pyqtSignal

if TYPE_CHECKING:
    from nxdrive.alfresco.engine.engine import AlfrescoEngine
    from nxdrive.drive.dao.engine import EngineDAO

__all__ = ("AlfrescoRemoteWatcher",)

log = getLogger(__name__)


class AlfrescoRemoteWatcher(EngineWorker):
    """Poll the Alfresco server for remote changes via full tree scans."""

    initiate = pyqtSignal()
    updated = pyqtSignal()
    remoteScanFinished = pyqtSignal()
    remoteWatcherStopped = pyqtSignal()

    def __init__(self, engine: "AlfrescoEngine", dao: "EngineDAO", /) -> None:
        super().__init__(engine, dao, "AlfrescoRemoteWatcher")

        self.empty_polls = 0
        self._next_check = 0.0
        # Track last full remote scan timestamp (persisted to DAO)
        self._last_remote_full_scan: Optional[datetime] = self.dao.get_config(
            "remote_last_full_scan"
        )

    def get_metrics(self) -> Metrics:
        metrics = super().get_metrics()
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
                    handle_changes(first_pass)
                    # Note: @tooltip decorator swallows return values,
                    # so we always flip first_pass after the first call.
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
            from nxdrive.drive.constants import ROOT

            root_pair = self.dao.get_state_from_local(ROOT)
        if not root_pair or not root_pair.remote_ref:
            log.warning("No root pair found, cannot scan remote tree")
            return

        # Refresh root metadata.
        # IMPORTANT: we intentionally do NOT call update_remote_state()
        # for the root pair.  The local folder name (e.g. "Alfresco")
        # always differs from the Alfresco root node name
        # (e.g. "Company Home").  update_remote_state's folder-rename
        # detection treats this mismatch as a rename on every scan,
        # permanently re-queuing the root pair and blocking sync
        # completion.
        try:
            root_info = remote._node_to_remote_file_info(
                remote.get_node(root_pair.remote_ref, include=["path"])
            )
        except AlfrescoAuthError:
            log.warning("Remote scan failed, credentials are invalid", exc_info=True)
            self.engine.set_invalid_credentials(
                reason="remote scan failed — re-login required"
            )
            return
        except (AlfrescoNetworkError, OSError):
            log.warning(
                "Remote scan failed due to network error, will retry", exc_info=True
            )
            return
        except Exception:
            log.warning("Remote scan failed unexpectedly", exc_info=True)
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
                # Alfresco does not expose a content hash, so digest is
                # always None.  Detect content changes by comparing the
                # modification timestamp instead.
                # The DB stores timestamps as 'YYYY-MM-DD HH:MM:SS'
                # (no microseconds/timezone), while the server returns
                # full datetime objects.  Normalise both sides to the
                # DB format before comparing.
                remote_ts = child_info.last_modification_time
                if hasattr(remote_ts, "strftime"):
                    remote_ts_str = remote_ts.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    remote_ts_str = str(remote_ts)[:19]
                db_ts_str = str(child_pair.last_remote_updated or "")[:19]
                content_changed = (
                    not child_info.folderish
                    and remote_ts_str
                    and remote_ts_str != db_ts_str
                )
                if content_changed:
                    # Skip if the pair is currently being processed by the
                    # Processor (e.g. an upload is in progress).  Forcing
                    # remotely_modified mid-upload causes a redundant
                    # download cycle and can create ghost queue items.
                    if child_pair.pair_state in (
                        "locally_created",
                        "locally_modified",
                    ):
                        log.debug(
                            f"Skipping force_remote for {child_info.name!r}: "
                            f"pair is {child_pair.pair_state!r} (processor active)"
                        )
                        self.dao.update_remote_state(
                            child_pair,
                            child_info,
                            remote_parent_path=remote_parent_path,
                        )
                    else:
                        log.info(
                            f"Content change detected for {child_info.name!r}: "
                            f"old={child_pair.last_remote_updated!r} "
                            f"new={child_info.last_modification_time!r}"
                        )
                        # Step 1: update metadata (esp. last_remote_updated)
                        # without bumping version, so force_remote can match
                        # the current version with its optimistic lock.
                        self.dao.update_remote_state(
                            child_pair,
                            child_info,
                            remote_parent_path=remote_parent_path,
                            force_update=True,
                            versioned=False,
                        )
                        # Step 2: set pair to "remotely_modified" and queue.
                        # update_remote_state's no-change block resets
                        # remote_state to "synchronized" (because
                        # None in (local_digest, None)), so we must
                        # override it with force_remote.
                        self.dao.force_remote(child_pair)
                else:
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
        """Poll for remote changes by performing a full remote scan."""
        remote = self.engine.remote
        if not remote:
            return False

        # Check for an on-demand re-scan request (mirrors Nuxeo's
        # ``remote_need_full_scan`` config flag).
        need_rescan = self.dao.get_config("remote_need_full_scan")
        if need_rescan is not None:
            log.info("On-demand full remote re-scan requested")
            self.dao.update_config("remote_need_full_scan", None)

        # Snapshot queue size before scan to detect changes
        qm_before = self.engine.queue_manager.get_overall_size()

        try:
            self.scan_remote()
        except Exception:
            log.warning("Remote scan failed, credentials may be invalid", exc_info=True)
            self.engine.set_invalid_credentials(
                reason="remote scan failed — re-login required"
            )
            self.updated.emit()
            return first_pass

        # Detect local changes that the watchdog may have missed
        # (atomic saves, copies during busy event loop, etc.)
        try:
            self._scan_local_changes()
        except Exception:
            log.warning("Error during local change scan", exc_info=True)

        # Track whether the poll found any new work
        qm_after = self.engine.queue_manager.get_overall_size()
        if qm_after > qm_before:
            self.empty_polls = 0
        else:
            self.empty_polls += 1

        (self.updated, self.initiate)[first_pass].emit()

        # Directly call _check_last_sync because the @tooltip decorator
        # swallows return values, preventing the signal-based path from
        # working reliably.
        if not first_pass:
            self.engine._check_last_sync()

        return True

    def scan_pair(self, remote_path: str, /) -> None:
        """Schedule a remote path for re-scan on the next poll cycle."""
        self._next_check = 0

    # -- Local change detection ----------------------------------------------

    @tooltip("Local change scan (Alfresco)")
    def _scan_local_changes(self) -> None:
        """Walk the local sync folder and detect modifications or new files.

        The watchdog-based local watcher can miss changes when:
        - An application saves via atomic temp-file + rename (e.g. Word, LibreOffice)
        - A file is copied while the watchdog event loop is busy
        - The watchdog ``[modified]`` event fires before the actual write completes

        This method compensates by doing a periodic digest comparison for
        existing pairs and discovering new files not yet tracked.
        """
        log.info("Starting Alfresco local change scan")
        start = monotonic()
        local = self.engine.local
        dao = self.dao

        if not local.exists(ROOT):
            log.warning("Local sync root does not exist, skipping local scan")
            return

        self._scan_local_recursive(ROOT, local, dao)

        log.info(f"Alfresco local change scan finished in {monotonic() - start:.2f}s")

    def _scan_local_recursive(self, path: Path, local, dao) -> None:
        """Recursively scan *path* for local changes."""
        self._interact()

        try:
            children_info = local.get_children_info(path)
        except OSError:
            return

        # Build a map of DB children keyed by name
        db_children = dao.get_local_children(path)
        db_by_name = {child.local_name: child for child in db_children}

        for child_info in children_info:
            child_name = child_info.path.name

            if local.is_ignored(path, child_name):
                continue

            if child_name in db_by_name:
                child_pair = db_by_name[child_name]

                if child_pair.pair_state != "synchronized":
                    # Already queued for processing, skip
                    if child_info.folderish:
                        self._scan_local_recursive(child_info.path, local, dao)
                    continue

                if child_pair.processor > 0:
                    # Being processed, skip
                    if child_info.folderish:
                        self._scan_local_recursive(child_info.path, local, dao)
                    continue

                if not child_info.folderish:
                    # Compare digest for files
                    try:
                        digest = child_info.get_digest()
                    except Exception:
                        log.debug(
                            f"Cannot compute digest for {child_info.path!r}",
                            exc_info=True,
                        )
                        continue

                    if child_pair.local_digest and digest != child_pair.local_digest:
                        log.info(
                            f"Local change detected for {child_info.path!r}: "
                            f"old={child_pair.local_digest!r} new={digest!r}"
                        )
                        child_pair.local_digest = digest
                        child_pair.local_state = "modified"
                        dao.update_local_state(child_pair, child_info)
                else:
                    self._scan_local_recursive(child_info.path, local, dao)
            else:
                # New local file/folder not in DB — check it has no remote_id
                # (if it does, the local watcher should handle it)
                remote_ref = local.get_remote_id(child_info.path)
                if not remote_ref:
                    log.info(
                        f"New local {'folder' if child_info.folderish else 'file'} "
                        f"detected: {child_info.path!r}"
                    )
                    dao.insert_local_state(child_info, path)

                if child_info.folderish:
                    self._scan_local_recursive(child_info.path, local, dao)

        # Detect files/folders deleted locally while the app was not running.
        # Remaining db_by_name entries have no corresponding local file.
        # Only consider pairs that were previously synchronized — skip
        # pairs still waiting for download (remotely_created, unknown, etc.).
        for child_name, child_pair in db_by_name.items():
            if child_pair.pair_state != "synchronized":
                continue
            if not local.exists(child_pair.local_path):
                log.info(
                    f"Local deletion detected for {child_pair.local_path!r} "
                    f"(missing on disk)"
                )
                self.engine.delete_doc(child_pair.local_path)
