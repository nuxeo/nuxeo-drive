"""
Remote watcher for Alfresco — polls the Device Sync change feed.

The standalone Sync Service reports a server-side delta (created, updated,
deleted, moved and renamed nodes) per subscription, so this watcher applies
changes instead of walking the whole remote tree.

There is intentionally **no fallback** to the legacy full-tree scan: any
Device Sync failure is logged via ``log.error``/``log.exception`` so it is
visible rather than silently masked.  ``scan_remote()`` is retained because
the delta path shares its reconcile logic.
"""

from contextlib import suppress
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from alfresco.exceptions import AuthenticationError as AlfrescoAuthError
from alfresco.exceptions import NetworkError as AlfrescoNetworkError
from alfresco.models.subscription import Change, ChangeType, SyncState

from nxdrive.alfresco.client.device_sync import (
    CONF_BOOTSTRAPPED_FOR,
    DEVICE_SYNC_CLIENT_VERSION,
    DeviceSyncProvisioner,
)
from nxdrive.alfresco.sync_filters import is_top_folder_excluded
from nxdrive.drive.constants import MAC, ROOT, WINDOWS
from nxdrive.drive.engine.activity import tooltip
from nxdrive.drive.engine.watcher.remote_watcher_base import RemoteWatcherBase
from nxdrive.drive.exceptions import ThreadInterrupt
from nxdrive.drive.objects import DocPair, Metrics, RemoteFileInfo
from nxdrive.drive.options import Options

if TYPE_CHECKING:
    from nxdrive.alfresco.engine.engine import AlfrescoEngine
    from nxdrive.drive.dao.engine import EngineDAO

__all__ = ("AlfrescoRemoteWatcher",)

log = getLogger(__name__)

#: Upper bound on ``get_sync`` calls for a single sync round. Guards against
#: a server that never leaves ``notReady`` or never clears ``more_changes``.
MAX_SYNC_POLLS = 120

#: Pause between polls while the service reports ``notReady``.
NOT_READY_POLL_DELAY = 0.5

#: Grace period after a filter change before acting on it. The folder picker
#: applies its selection one path at a time, and each call pushes this
#: deadline out again, so a whole burst collapses into a single pass.
FILTER_RESCAN_DELAY = 2.0

#: Platform label reported when registering the Device Sync subscriber.
DEVICE_OS = "windows" if WINDOWS else "macos" if MAC else "linux"


class AlfrescoRemoteWatcher(RemoteWatcherBase):
    """Poll the Alfresco Device Sync change feed for remote changes."""

    def __init__(self, engine: "AlfrescoEngine", dao: "EngineDAO", /) -> None:
        super().__init__(engine, dao, "AlfrescoRemoteWatcher")

        # Track last full remote scan timestamp (persisted to DAO)
        self._last_remote_full_scan: Optional[datetime] = self.dao.get_config(
            "remote_last_full_scan"
        )

        #: Device Sync provisioning state, built lazily on the first poll.
        self._provisioner: Optional[DeviceSyncProvisioner] = None
        self._root_node_id: str = ""

        #: Nodes whose filter was just lifted, pending resolution.
        self._unfiltered_nodes: Set[str] = set()
        #: Set when a lifted filter carried no node id, so only a walk can
        #: discover what we are now missing.
        self._unfiltered_needs_scan = False

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
                    # @tooltip decorator swallows return values,
                    # so always flip first_pass after the first call.
                    first_pass = False
                    self._next_check = now() + Options.delay

                interact()
                sleep(0.5)
        except ThreadInterrupt:
            self.remoteWatcherStopped.emit()
            raise

    # -- Subtree rescan ------------------------------------------------------

    @tooltip("Remote full scan (Alfresco)")
    def scan_remote(self, *, from_state: Optional[DocPair] = None) -> None:
        """Recursively scan the remote tree below *from_state* (root by default).

        Not part of the polling cycle — Device Sync supplies the delta. This
        runs once to seed a new subscription (the change feed only reports
        events *after* the subscription was created) and from
        ``Engine.rollback_delete()`` when a restored folder needs its subtree
        repopulated.
        """
        self._scan_remote_tree(from_state=from_state)

    def _scan_remote_tree(self, *, from_state: Optional[DocPair] = None) -> bool:
        """Body of :meth:`scan_remote`, reporting whether the walk completed.

        Separate from the decorated entry point because ``@tooltip`` discards
        return values, and the bootstrap must know if the scan actually ran
        before recording it as done.
        """
        log.info("Starting Alfresco remote scan")
        start = monotonic()
        remote = self.engine.remote
        if not remote:
            return False

        root_pair = from_state or self.dao.get_state_from_local(ROOT)
        if not root_pair or not root_pair.remote_ref:
            log.warning("No root pair found, cannot scan remote tree")
            return False

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
            return False
        except (AlfrescoNetworkError, OSError):
            log.warning(
                "Remote scan failed due to network error, will retry", exc_info=True
            )
            return False
        except Exception:
            log.warning("Remote scan failed unexpectedly", exc_info=True)
            return False

        # Recursive walk
        self._scan_remote_recursive(root_pair, root_info)

        self._last_remote_full_scan = datetime.now(tz=timezone.utc)
        self.dao.update_config("remote_last_full_scan", self._last_remote_full_scan)

        log.info(f"Alfresco full remote scan finished in {monotonic() - start:.2f}s")
        self.remoteScanFinished.emit()
        return True

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

            if self._is_filtered_path(child_info.path):
                continue

            child_pair = children.pop(child_info.uid, None)
            reconciled = self._reconcile_child(
                child_pair, child_info, remote_parent_path, doc_pair.local_path
            )
            if child_info.folderish and reconciled:
                to_scan.append((reconciled, child_info))

        # Mark remaining DB children as deleted on server
        for deleted_pair in children.values():
            if deleted_pair.pair_state in ("locally_created", "locally_modified"):
                log.debug(
                    f"Skipping remote deletion for {deleted_pair.local_name!r}: "
                    f"pair is {deleted_pair.pair_state!r} (processor active)"
                )
                continue
            self.dao.delete_remote_state(deleted_pair)

        # Recurse into sub-folders
        for pair, info in to_scan:
            self._scan_remote_recursive(pair, info)

    # -- Shared reconcile logic ----------------------------------------------

    def _is_filtered_path(self, path: str, /) -> bool:
        """Return whether *path* must be excluded from synchronisation.

        Applied identically by the full scan and the Device Sync delta so
        both honour the same scope.
        """
        # Alfresco system folders (Data Dictionary, IMAP Home, Guest Home,
        # IMAP Attachments, Sites/rm) must never be synced by default.
        # Admins can override via the ``alfresco_force_sync_top_folders``
        # and ``alfresco_excluded_top_folders`` options in ``config.ini``.
        # See ``nxdrive/alfresco/sync_filters.py`` for the exact rule.
        if is_top_folder_excluded(path):
            return True

        # Filtered paths ("Choose folders to sync" in the GUI). Uses the
        # human-readable Alfresco path, matching what the dialog stores.
        if self.dao.is_filter(path):
            return True

        return False

    def _reconcile_child(
        self,
        child_pair: Optional[DocPair],
        child_info: RemoteFileInfo,
        remote_parent_path: str,
        local_parent_path: Path,
        /,
    ) -> Optional[DocPair]:
        """Apply a remote node's state to the DAO and return the pair.

        *child_pair* is the known pair for ``child_info.uid``, or ``None``
        when the node has not been seen before.

        This is the single place where a remote node is reconciled against
        local state: it is shared by the full remote scan and the Device
        Sync change feed so both inherit the same conflict, processor and
        digest handling.
        """
        if child_pair is None:
            # New item — adopt an existing local pair or insert into DAO
            local_path = local_parent_path / child_info.name
            return self._match_or_create_child(
                child_info, local_path, local_parent_path, remote_parent_path
            )
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
            not child_info.folderish and remote_ts_str and remote_ts_str != db_ts_str
        )
        if content_changed:
            # Pair is already flagged as conflicted: don't touch
            # remote state, don't re-queue.  ``update_remote_state``
            # would recompute ``pair_state`` from PAIR_STATES and
            # (because Alfresco digests are ``None``) the "similar"
            # short-circuit would demote the row back to
            # ``locally_modified`` — undoing the conflict marking
            # and hiding the row from the systray Conflicts panel.
            if child_pair.pair_state == "conflicted":
                log.debug(
                    f"Skipping update for {child_info.name!r}: "
                    "pair is already conflicted (awaiting user)"
                )
            # Skip if the pair is currently being processed by the
            # Processor (e.g. an upload is in progress).  Forcing
            # remotely_modified mid-upload causes a redundant
            # download cycle and can create ghost queue items.
            elif child_pair.pair_state in (
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
        elif child_pair.pair_state == "conflicted":
            log.debug(
                f"Skipping update for {child_info.name!r}: "
                "pair is already conflicted (awaiting user)"
            )
        else:
            self.dao.update_remote_state(
                child_pair,
                child_info,
                remote_parent_path=remote_parent_path,
            )

        return child_pair

    def _match_or_create_child(
        self,
        child_info: RemoteFileInfo,
        local_path: Path,
        local_parent_path: Path,
        remote_parent_path: str,
        /,
    ) -> Optional[DocPair]:
        """Link ``child_info`` to an existing local pair, or insert a new one.

        Mirrors ``RemoteWatcher._find_remote_child_match_or_create()``.
        Without this step a document created locally (still unlinked,
        ``remote_ref=''``) and picked up by a remote scan before its
        upload completed would get a *second* row for the same
        ``local_path``.  Both rows then race, and the loser hits
        ``UNIQUE constraint failed: States.remote_ref, States.local_path``
        on every retry, looping forever.
        """
        existing = self.dao.get_state_from_local(local_path)

        # Checked before the remote-ref guard below: the processor binds a
        # conflicted pair to the node it conflicts with, so that ref is
        # legitimately already in the database.
        if existing and existing.pair_state == "conflicted":
            # Refreshing ``last_remote_updated`` here would make the engine's
            # freshness check see an unchanged remote and auto-resolve a
            # conflict the user has not arbitrated yet.
            log.debug(
                f"Not linking {child_info.name!r}: pair is already "
                "conflicted (awaiting user)"
            )
            return None

        if self.dao.get_normal_state_from_remote(child_info.uid):
            log.warning(
                "Illegal state: a remote creation cannot happen if there "
                f"already is the same remote ref in the database: {child_info!r}"
            )
            return None

        if existing:
            if existing.remote_ref and existing.remote_ref != child_info.uid:
                log.info(
                    "Got an existing pair with a different remote ref: "
                    f"{existing!r} | {child_info!r}"
                )
                return None

            log.info(
                f"Linking remote {child_info.name!r} ({child_info.uid}) to the "
                f"existing local pair {existing!r}"
            )
            # A local creation that was never uploaded means the remote node
            # was created independently: same name on both sides is a
            # conflict, not a link.  ``versioned`` bumps the row version so
            # an in-flight processor holding stale state cannot overwrite
            # the conflict via ``synchronize_state``'s optimistic lock.
            conflicting = not existing.remote_ref and existing.local_state == "created"
            if conflicting:
                existing.remote_state = "created"
            self.dao.update_remote_state(
                existing,
                child_info,
                remote_parent_path=remote_parent_path,
                versioned=conflicting,
            )
            # Claiming the node in the xattr would make the processor treat
            # it as its own interrupted upload and overwrite the remote.
            if not conflicting:
                with suppress(Exception):
                    self.engine.local.set_remote_id(local_path, child_info.uid)
            return self.dao.get_state_from_id(existing.id, from_write=True)

        row_id = self.dao.insert_remote_state(
            child_info, remote_parent_path, local_path, local_parent_path
        )
        return self.dao.get_state_from_id(row_id, from_write=True) if row_id else None

    # -- Device Sync change polling ------------------------------------------

    @tooltip("Remote scanning (Alfresco)")
    def _handle_changes(self, first_pass: bool = False) -> bool:
        """Poll the Device Sync change feed and apply the delta locally.

        There is deliberately **no fallback to the legacy full remote
        scan**: if Device Sync cannot be provisioned or a poll fails, the
        failure is logged loudly and the cycle is skipped so the problem
        surfaces instead of being masked by an O(tree) walk.

        The pass is always notified, even when the cycle aborts early:
        ``initiate`` (emitted on the first pass) is what starts the queue
        manager's processors, so skipping it would leave the engine with no
        workers for the rest of the session.
        """
        try:
            return self._do_handle_changes(first_pass)
        finally:
            self._notify_pass_done(first_pass)
            # Directly call _check_last_sync because the @tooltip decorator
            # swallows return values, preventing the signal-based path from
            # working reliably.
            if not first_pass:
                self.engine._check_last_sync()

    def _do_handle_changes(self, first_pass: bool, /) -> bool:
        remote = self.engine.remote
        if not remote:
            log.warning("No remote client available, skipping poll")
            return False

        # Snapshot queue size before the poll to detect new work
        qm_before = self.engine.queue_manager.get_overall_size()

        if not self._ensure_provisioned():
            self.updated.emit()
            return False

        # An on-demand re-scan (e.g. the user just chose folders to sync)
        # means our local view is incomplete, not that the subscription is
        # stale — re-seed rather than throwing away the change feed.
        if self.dao.get_config("remote_need_full_scan") is not None:
            log.info("On-demand re-scan requested, forcing a re-seed")
            self.dao.update_config("remote_need_full_scan", None)
            self.dao.update_config(CONF_BOOTSTRAPPED_FOR, None)

        # A new subscription starts empty: the feed only carries events from
        # its creation onward, so existing content must be seeded once.
        self._bootstrap_if_needed()

        # Widening the selection exposes content the feed will never mention.
        self._apply_unfiltered()

        try:
            self._poll_device_sync()
        except AlfrescoAuthError:
            log.warning("Change poll failed, credentials are invalid", exc_info=True)
            self.engine.set_invalid_credentials(
                reason="Device Sync poll failed — re-login required"
            )
            self.updated.emit()
            return False
        except Exception:
            # Not an auth error, so do NOT push the user through a
            # re-authentication cycle: the banner is misleading and blocks
            # recovery on the next poll.
            log.exception("Change poll failed unexpectedly")
            self.updated.emit()
            return False

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

        return True

    def scan_pair(self, remote_path: str, /) -> None:
        """Nudge the poll timer after a filter change.

        The work itself is queued by :meth:`queue_unfiltered`, which
        ``AlfrescoEngine.remove_filter`` calls with the node ids.
        """
        self._next_check = monotonic() + FILTER_RESCAN_DELAY

    def queue_unfiltered(self, remote_path: str, node_ids: List[str], /) -> None:
        """Record nodes whose filter was just lifted.

        Un-filtering exposes content that already exists on the server, so the
        change feed has nothing to report — we have to go and fetch it. With a
        node id that is one request per node; without one, only a full walk can
        find it.
        """
        if node_ids:
            self._unfiltered_nodes.update(node_ids)
            log.debug(f"Unfiltered {remote_path!r}: queued {len(node_ids)} node(s)")
        else:
            log.debug(
                f"Unfiltered {remote_path!r} has no recorded node id, "
                "a full re-seed will be needed"
            )
            self._unfiltered_needs_scan = True

        self._next_check = monotonic() + FILTER_RESCAN_DELAY

    def _apply_unfiltered(self) -> None:
        """Pull in whatever the widened selection now covers."""
        if self._unfiltered_needs_scan:
            log.debug("Unfiltered content needs a full re-seed")
            self._unfiltered_needs_scan = False
            self._unfiltered_nodes.clear()
            self.dao.update_config(CONF_BOOTSTRAPPED_FOR, None)
            return

        if not self._unfiltered_nodes:
            return

        node_ids = sorted(self._unfiltered_nodes)
        self._unfiltered_nodes.clear()
        log.debug(f"Resolving {len(node_ids)} unfiltered node(s)")
        for node_id in node_ids:
            self._interact()
            self._resolve_unfiltered_node(node_id)

    def _resolve_unfiltered_node(self, node_id: str, /) -> None:
        remote = self.engine.remote
        try:
            node = remote.get_node(node_id, include=["path"])
        except Exception:
            log.warning(
                f"Could not fetch unfiltered node {node_id!r}; it may have "
                "been deleted since it was filtered",
                exc_info=True,
            )
            return

        info = remote._node_to_remote_file_info(node)
        if self._is_filtered_path(info.path):
            log.debug(f"Unfiltered {info.path!r} is still excluded by another rule")
            return

        parent_pair = self._resolve_parent(info)
        if parent_pair is None:
            # The parent is filtered too, so there is no row to hang this off.
            log.debug(
                f"Parent of unfiltered {info.path!r} is unknown, "
                "falling back to a full re-seed"
            )
            self.dao.update_config(CONF_BOOTSTRAPPED_FOR, None)
            return

        remote_parent_path = (
            parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
        )
        existing = self.dao.get_normal_state_from_remote(node_id)
        pair = self._reconcile_child(
            existing, info, remote_parent_path, parent_pair.local_path
        )
        log.debug(
            f"Restored unfiltered {info.path!r} "
            f"({'dir' if info.folderish else 'file'})"
        )

        if info.folderish and pair:
            self._scan_remote_recursive(pair, info)

    # -- Device Sync provisioning --------------------------------------------

    def _ensure_provisioned(self) -> bool:
        """Make sure a subscriber and subscription exist for this engine.

        Runs on the watcher thread, but only ever completes before the first
        pass finishes — the queue manager starts its processors on the
        ``initiate`` signal, so no worker thread shares the client yet. That
        matters because binding the Sync Service URL reconfigures the client,
        which the vendor documents as unsafe once it is shared.
        """
        if self._provisioner and self._provisioner.provisioned:
            return True

        remote = self.engine.remote
        if not remote:
            return False

        root_pair = self.dao.get_state_from_local(ROOT)
        if not root_pair or not root_pair.remote_ref:
            log.warning(
                "No root pair yet, cannot provision Device Sync "
                "(waiting for folder selection?)"
            )
            return False

        if self._provisioner is None:
            self._provisioner = DeviceSyncProvisioner(
                remote,
                self.dao,
                device_os=DEVICE_OS,
                client_version=DEVICE_SYNC_CLIENT_VERSION,
            )

        self._root_node_id = root_pair.remote_ref
        if not self._provisioner.provision(self._root_node_id):
            log.error(
                "Device Sync provisioning failed — no changes will be "
                "detected this cycle"
            )
            return False

        return True

    def _resubscribe(self) -> None:
        """Recreate the subscription so the server replays the full content."""
        if not self._provisioner or not self._root_node_id:
            return
        if not self._provisioner.resubscribe(self._root_node_id):
            log.error("Re-subscription failed, change feed is stale")

    # -- Initial seeding -----------------------------------------------------

    def _bootstrap_if_needed(self) -> None:
        """Seed the DAO with existing remote content, once per subscription.

        Device Sync reports events from subscription creation onward, so a
        brand-new subscription yields an empty delta even when the repository
        is full. A single tree walk populates that starting state; the change
        feed handles everything afterwards.

        Keyed on the subscription id rather than a boolean so that a
        re-subscription (after a server-side reset) seeds again.
        """
        provisioner = self._provisioner
        if not provisioner or not provisioner.subscription_id:
            return

        done_for = self.dao.get_config(CONF_BOOTSTRAPPED_FOR)
        if done_for == provisioner.subscription_id:
            return

        log.info(
            "Seeding initial content for subscription "
            f"{provisioner.subscription_id!r} (previous seed: {done_for!r})"
        )
        start = monotonic()
        queue_before = self.engine.queue_manager.get_overall_size()

        if not self._scan_remote_tree():
            log.error(
                "Initial scan did not complete; will retry on the next poll cycle"
            )
            return

        self.dao.update_config(CONF_BOOTSTRAPPED_FOR, provisioner.subscription_id)
        queue_after = self.engine.queue_manager.get_overall_size()
        log.info(
            f"Seeding finished in {monotonic() - start:.2f}s, "
            f"queued {queue_after - queue_before} item(s)"
        )

    # -- Device Sync change feed ---------------------------------------------

    def _poll_device_sync(self) -> None:
        """Run one full sync round: start, drain every page, then clear."""
        provisioner = self._provisioner
        if not provisioner:
            return

        remote = self.engine.remote
        subscriber_id = provisioner.subscriber_id
        subscription_id = provisioner.subscription_id

        started = remote.start_sync(
            subscriber_id, subscription_id, client_version=provisioner.client_version
        )

        if started.status == SyncState.ERROR:
            log.error(
                f"Server refused to start a sync: {started.message!r} "
                f"(subscriber={subscriber_id!r}, subscription={subscription_id!r})"
            )
            return

        sync_id = started.sync_id
        if not sync_id:
            log.error(f"start_sync returned no sync_id: {started!r}")
            return

        total_changes = 0
        try:
            total_changes = self._drain_sync(subscriber_id, subscription_id, sync_id)
        finally:
            # Always release the server-side sync, even if applying the
            # changes raised: an uncleared syncId pins server state.
            try:
                remote.clear_sync(subscriber_id, subscription_id, sync_id)
            except Exception:
                log.warning(f"Could not clear sync {sync_id!r}", exc_info=True)

        if total_changes:
            log.debug(f"Sync {sync_id!r} applied {total_changes} change(s)")

    def _drain_sync(
        self, subscriber_id: str, subscription_id: str, sync_id: str, /
    ) -> int:
        """Poll *sync_id* until it is exhausted, applying every page.

        Handles both async states the Sync Service can report: ``notReady``
        (still preparing, keep polling) and ``ready`` with ``more_changes``
        (another page is waiting).
        """
        remote = self.engine.remote
        total = 0

        for attempt in range(1, MAX_SYNC_POLLS + 1):
            self._interact()

            status = remote.get_sync(subscriber_id, subscription_id, sync_id)
            if status.changes or status.resets or status.missing:
                log.debug(
                    f"get_sync #{attempt} -> status={status.status!r} "
                    f"changes={len(status.changes)} more={status.more_changes} "
                    f"resets={status.resets} missing={status.missing}"
                )

            if status.status == SyncState.ERROR:
                log.error(f"Sync {sync_id!r} failed: {status.message!r}")
                return total

            if status.status == SyncState.NOT_READY:
                sleep(NOT_READY_POLL_DELAY)
                continue

            # Both signals invalidate the sync we are draining, so stop
            # here rather than paging through a feed we no longer trust.
            if status.missing:
                log.error(
                    f"Server does not know subscriptions {status.missing} "
                    "— re-provisioning on the next cycle"
                )
                self._invalidate_provisioning()
                return total

            if status.resets:
                log.warning(
                    f"Server requested a reset of {status.resets} — the "
                    "local view is stale, re-subscribing for a full replay"
                )
                self._resubscribe()
                return total

            total += self._apply_changes(status.changes)

            if not status.more_changes:
                return total

        log.error(
            f"Sync {sync_id!r} did not complete within "
            f"{MAX_SYNC_POLLS} polls, abandoning this cycle"
        )
        return total

    def _apply_changes(self, changes: List[Change], /) -> int:
        """Apply one page of the change feed. Returns how many were applied."""
        applied = 0
        for change in self._dedupe_changes(changes):
            self._interact()
            if self._apply_change(change):
                applied += 1
        return applied

    @staticmethod
    def _dedupe_changes(changes: List[Change], /) -> List[Change]:
        """Order by ``seq_no`` and keep only the latest change per node.

        A single content update emits both ``UPDATE_REPOS`` and
        ``NODECHECKEDIN`` when it creates a version, so without this a
        trivial edit would be reconciled twice.
        """
        latest: Dict[str, Change] = {}
        for change in changes:
            if not change.node_id:
                log.warning(f"Ignoring change with no node id: {change!r}")
                continue
            previous = latest.get(change.node_id)
            if previous is None or (change.seq_no or 0) >= (previous.seq_no or 0):
                latest[change.node_id] = change

        ordered = sorted(latest.values(), key=lambda c: c.seq_no or 0)
        if len(ordered) != len(changes):
            log.debug(f"Collapsed {len(changes)} change(s) into {len(ordered)}")
        return ordered

    def _apply_change(self, change: Change, /) -> bool:
        """Apply a single change to the DAO. Returns whether it was applied."""
        remote = self.engine.remote
        log.debug(
            f"Change seq={change.seq_no} type={change.change_type!r} "
            f"node={change.node_id!r} path={change.path!r} "
            f"to_path={change.to_path!r} folder={change.is_folder}"
        )

        if change.change_type == ChangeType.DELETE:
            return self._apply_delete(change)

        # A move or rename lands at the node's *new* location, so the
        # post-change fields are the ones to reconcile against.
        moved = change.change_type in (ChangeType.MOVE, ChangeType.RENAME)

        info = remote._change_to_remote_file_info(change, target=moved)
        if self._is_filtered_path(info.path):
            # Moving a node into a filtered folder makes it leave our scope:
            # treat it as a deletion so the local copy is removed.
            if moved:
                log.debug(f"{info.name!r} moved into a filtered path, removing locally")
                return self._apply_delete(change)
            log.debug(f"Ignoring change for filtered path {info.path!r}")
            return False

        existing = self.dao.get_normal_state_from_remote(change.node_id)

        # A create needs the full node: the feed carries no creation time or
        # last contributor, and a new row persists both. One extra GET per
        # new node is negligible next to downloading its content.
        if existing is None:
            info = self._fetch_node_info(change) or info

        parent_pair = self._resolve_parent(info)
        if parent_pair is None:
            log.warning(
                f"Parent {info.parent_uid!r} of {info.name!r} is unknown, "
                "skipping (it should have arrived earlier in seq_no order)"
            )
            return False

        remote_parent_path = (
            parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
        )
        self._reconcile_child(
            existing, info, remote_parent_path, parent_pair.local_path
        )
        return True

    def _apply_delete(self, change: Change, /) -> bool:
        """Mark every pair bound to the change's node as remotely deleted."""
        pairs = self.dao.get_states_from_remote(change.node_id)
        if not pairs:
            log.debug(f"Delete for unknown node {change.node_id!r}, nothing to do")
            return False

        for pair in pairs:
            if pair.pair_state in ("locally_created", "locally_modified"):
                log.debug(
                    f"Skipping remote deletion for {pair.local_name!r}: "
                    f"pair is {pair.pair_state!r} (processor active)"
                )
                continue
            log.debug(f"Marking {pair.local_path!r} as remotely deleted")
            self.dao.delete_remote_state(pair)
        return True

    def _fetch_node_info(self, change: Change, /) -> Optional[RemoteFileInfo]:
        """Fetch full node metadata for a newly-created node."""
        remote = self.engine.remote
        try:
            node = remote.get_node(change.node_id, include=["path"])
        except Exception:
            # The node may already be gone again by the time we look.
            log.warning(
                f"Could not fetch node {change.node_id!r} "
                f"({change.name!r}); using change payload only",
                exc_info=True,
            )
            return None
        return remote._node_to_remote_file_info(node)

    def _resolve_parent(self, info: RemoteFileInfo, /) -> Optional[DocPair]:
        """Return the DocPair of *info*'s parent, or the root pair for it."""
        root_pair = self.dao.get_state_from_local(ROOT)
        if root_pair and info.parent_uid == root_pair.remote_ref:
            return root_pair
        return self.dao.get_normal_state_from_remote(info.parent_uid)

    def _invalidate_provisioning(self) -> None:
        """Force a full re-provision on the next cycle."""
        if self._provisioner:
            self._provisioner.subscriber_id = ""
            self._provisioner.subscription_id = ""

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

        # Two aggregators threaded through the recursion.
        #   seen_remote_refs: every ``remote_id`` xattr encountered while
        #     walking the tree. Used to distinguish a genuine local
        #     deletion from a rename/move whose watchdog event has not
        #     yet been processed (NXDRIVE-3221).
        #   pending_deletions: pairs whose local path is missing on disk.
        #     Deletion is *deferred* until the full tree walk completes so
        #     we can consult ``seen_remote_refs`` for the whole workspace,
        #     not just the current directory.
        seen_remote_refs: Set[str] = set()
        pending_deletions: List[DocPair] = []
        self._scan_local_recursive(
            ROOT, local, dao, seen_remote_refs, pending_deletions
        )
        self._process_pending_deletions(pending_deletions, seen_remote_refs)

        log.debug(f"Alfresco local change scan finished in {monotonic() - start:.2f}s")

    def _process_pending_deletions(
        self,
        pending_deletions: List[DocPair],
        seen_remote_refs: Set[str],
        /,
    ) -> None:
        """Finalize deletion detection after the full tree walk.

        A pair whose original local path is missing on disk is only a
        genuine deletion if its ``remote_ref`` did not resurface on disk
        elsewhere. If it did, the file was renamed or moved and the
        local watcher's ``moved`` event will handle it — invoking
        ``delete_doc`` here would destroy the pair state and cause the
        renamed file to be duplicated on the server and re-downloaded.
        """
        for child_pair in pending_deletions:
            if child_pair.remote_ref and child_pair.remote_ref in seen_remote_refs:
                log.debug(
                    f"Skip local deletion of {child_pair.local_path!r}: "
                    f"remote_ref {child_pair.remote_ref!r} still present on disk "
                    "(likely a rename/move — deferring to watchdog)"
                )
                continue
            log.info(
                f"Local deletion detected for {child_pair.local_path!r} "
                f"(missing on disk)"
            )
            self.engine.delete_doc(child_pair.local_path)

    def _scan_local_recursive(
        self,
        path: Path,
        local: Any,
        dao: Any,
        seen_remote_refs: Set[str],
        pending_deletions: List[DocPair],
        /,
    ) -> None:
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

            # Record the ``remote_id`` xattr for every visited child so a
            # deferred deletion candidate can be recognised as a rename.
            remote_ref = local.get_remote_id(child_info.path)
            if remote_ref:
                seen_remote_refs.add(remote_ref)

            if child_name in db_by_name:
                child_pair = db_by_name[child_name]

                if child_pair.pair_state != "synchronized":
                    # Already queued for processing, skip
                    if child_info.folderish:
                        self._scan_local_recursive(
                            child_info.path,
                            local,
                            dao,
                            seen_remote_refs,
                            pending_deletions,
                        )
                    continue

                if child_pair.processor > 0:
                    # Being processed, skip
                    if child_info.folderish:
                        self._scan_local_recursive(
                            child_info.path,
                            local,
                            dao,
                            seen_remote_refs,
                            pending_deletions,
                        )
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
                    self._scan_local_recursive(
                        child_info.path,
                        local,
                        dao,
                        seen_remote_refs,
                        pending_deletions,
                    )
            else:
                # New local file/folder not in DB — check it has no remote_id
                # (if it does, the local watcher should handle it)
                if not remote_ref:
                    log.info(
                        f"New local {'folder' if child_info.folderish else 'file'} "
                        f"detected: {child_info.path!r}"
                    )
                    dao.insert_local_state(child_info, path)

                if child_info.folderish:
                    self._scan_local_recursive(
                        child_info.path,
                        local,
                        dao,
                        seen_remote_refs,
                        pending_deletions,
                    )

        # Detect files/folders deleted locally while the app was not running.
        # Remaining db_by_name entries have no corresponding local file.
        # Only consider pairs that were previously synchronized — skip
        # pairs still waiting for download (remotely_created, unknown, etc.).
        # Actual delete_doc() is deferred to _process_pending_deletions()
        # so we can distinguish deletions from renames after the full
        # tree walk has collected every surviving remote_id xattr.
        for child_name, child_pair in db_by_name.items():
            if child_pair.pair_state != "synchronized":
                continue
            if not local.exists(child_pair.local_path):
                pending_deletions.append(child_pair)
