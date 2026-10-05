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
from time import monotonic, sleep, time
from typing import TYPE_CHECKING, Any, Dict, List, NamedTuple, Optional, Set

from alfresco.exceptions import AuthenticationError as AlfrescoAuthError
from alfresco.exceptions import NetworkError as AlfrescoNetworkError
from alfresco.exceptions import NotFoundError
from alfresco.models.subscription import Change, ChangeType, SyncState

from nxdrive.alfresco.client.device_sync import (
    CONF_BOOTSTRAPPED_FOR,
    CONF_LAST_SYNC_CLEAR,
    CONF_SEEDING_FOR,
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
from nxdrive.drive.qt.imports import Slot

if TYPE_CHECKING:
    from nxdrive.alfresco.engine.engine import AlfrescoEngine
    from nxdrive.drive.dao.engine import EngineDAO

__all__ = ("AlfrescoRemoteWatcher",)

log = getLogger(__name__)


class _SyncBatch(NamedTuple):
    """Outcome of one ``POST``/``GET`` round of the change feed."""

    applied: int
    #: Clearing a batch we did not fully apply commits a bookmark that covers
    #: changes we dropped, so this gates the acknowledgement.
    acknowledge: bool
    more: bool
    last_seq: Optional[int]
    #: The server had nothing for us; its pending bookmark is unsafe to commit.
    idle: bool
    #: The subscription was replaced, so nothing seeded so far describes it.
    reset: bool = False


#: Upper bound on ``get_sync`` calls while a batch is still being prepared.
#: Guards against a server that never leaves ``notReady``.
MAX_SYNC_POLLS = 120

#: Upper bound on batches consumed in one cycle. The service hands out 100
#: changes at a time and only moves its cursor when a batch is cleared, so a
#: backlog needs one POST/GET/DELETE round per batch. Anything left over is
#: picked up by the next cycle.
MAX_SYNC_ROUNDS = 200

#: Backoff while the service reports ``notReady``. Starting a sync is
#: asynchronous, so the first poll or two normally answer ``notReady`` and
#: most batches resolve in well under a second.
NOT_READY_POLL_DELAY = 0.1
NOT_READY_POLL_MAX = 2.0
NOT_READY_TIMEOUT = 60.0

#: How long an idle subscription may go without acknowledging a sync. Only a
#: cleared sync refreshes the server's staleness clock, and we otherwise skip
#: clearing empty batches.
SYNC_KEEPALIVE_INTERVAL = 86400.0

#: Grace period after a filter change before acting on it. The folder picker
#: applies its selection one path at a time, and each call pushes this
#: deadline out again, so a whole burst collapses into a single pass.
FILTER_RESCAN_DELAY = 2.0

#: How many cycles a single change may fail before it is abandoned. Failing
#: changes are retried by *not* acknowledging the sync, so a change that can
#: never be applied would otherwise block every later change forever.
MAX_CHANGE_RETRIES = 3

#: ``last_error`` written on a pair whose change could not be applied.
#: Rendered by ``FileCard.qml`` as ``ERROR_REASON_<code>``.
CHANGE_FAILED_ERROR = "DEVICE_SYNC_CHANGE_FAILED"

#: Extra attempts at listing a folder before the seed gives up on it.
#: ``Errno 49`` (ephemeral ports exhausted) clears on its own, and an
#: abandoned folder is queued for the next cycle rather than lost.
LISTING_RETRIES = 2
LISTING_RETRY_DELAY = 5.0

#: Entries examined per local scan cycle. The sweep resumes where it left
#: off, so a large workspace no longer keeps the watcher busy for minutes.
LOCAL_SCAN_CHUNK = 100

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

        #: Consecutive apply failures per node id, so a transient error is
        #: retried but a permanently broken change is eventually abandoned.
        self._change_failures: Dict[str, int] = {}

        #: Resumable local sweep. Walking a large workspace in one cycle kept
        #: the watcher busy for minutes, so it advances a chunk at a time.
        self._local_scan_dirs: List[Path] = []
        self._local_scan_seen: Set[str] = set()
        self._local_scan_deletions: List[DocPair] = []
        self._local_scan_incomplete = False

    def get_metrics(self) -> Metrics:
        metrics = super().get_metrics()
        metrics["last_remote_full_scan"] = self._last_remote_full_scan
        metrics["next_polling"] = self._next_check
        return metrics

    def _execute(self) -> None:
        now = monotonic
        handle_changes = self._handle_changes
        interact = self._interact

        try:
            while "working":
                if now() > self._next_check:
                    # ``first_pass_done`` is the authority rather than a local
                    # flag: a failed first pass must be retried as a first pass,
                    # or local creations stay blocked for the whole session.
                    # Re-emitting ``initiate`` is harmless, ``init_processors()``
                    # is idempotent.
                    handle_changes(not self.first_pass_done)
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

        # Recursive walk. An explicit subtree rescan rebuilds rows that have
        # just been removed, so it must not stop at a seed checkpoint.
        complete = self._scan_remote_recursive(
            root_pair, root_info, force=from_state is not None
        )
        if not complete:
            log.error(
                "Alfresco full remote scan was incomplete; some subtrees could "
                "not be listed and will not be recorded as seeded"
            )
            return False

        self._last_remote_full_scan = datetime.now(tz=timezone.utc)
        self.dao.update_config("remote_last_full_scan", self._last_remote_full_scan)

        log.info(f"Alfresco full remote scan finished in {monotonic() - start:.2f}s")
        self.remoteScanFinished.emit()
        return True

    def _scan_remote_recursive(
        self,
        doc_pair: DocPair,
        remote_info: RemoteFileInfo,
        /,
        *,
        force: bool = False,
    ) -> bool:
        """Recursively scan children of a folder and insert/update DAO state.

        Returns whether the whole subtree was walked successfully. A partial
        walk must never be recorded as a completed bootstrap: the change feed
        only carries events from subscription creation onward, so content
        missed here would never be replayed.

        *force* ignores the seed checkpoints. Callers rebuilding rows they
        just deleted need the walk to happen even for a folder an unfinished
        seed already visited.
        """
        if not remote_info.folderish:
            return True

        # Resume support: a folder already walked during this seed is skipped,
        # so a retry costs only what actually failed. Keyed on the node id
        # because Alfresco paths are human-readable and change on rename.
        if not force and self.dao.is_path_scanned(remote_info.uid):
            return True

        self._interact()

        remote = self.engine.remote
        if not remote:
            return False

        remote_parent_path = doc_pair.remote_parent_path + "/" + remote_info.uid

        # Fetch DB children for this folder
        db_children = self.dao.get_remote_children(doc_pair.remote_ref)
        children: Dict[str, DocPair] = {
            child.remote_ref: child for child in db_children
        }

        nodes = self._list_children(remote, remote_info)
        if nodes is None:
            self.dao.add_path_to_scan(remote_info.uid)
            return False

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
        complete = True
        for pair, info in to_scan:
            if not self._scan_remote_recursive(pair, info, force=force):
                complete = False

        if complete:
            self.dao.add_path_scanned(remote_info.uid)
            self.dao.delete_path_to_scan(remote_info.uid)
        return complete

    def _list_children(self, remote: Any, remote_info: RemoteFileInfo, /) -> Any:
        """List a folder's children, or ``None`` once the retries are spent."""
        for attempt in range(LISTING_RETRIES + 1):
            try:
                return list(
                    remote.client.nodes.iter_children(remote_info.uid, include=["path"])
                )
            except (AlfrescoNetworkError, OSError):
                if attempt == LISTING_RETRIES:
                    break
                log.warning(
                    f"Could not list children of {remote_info.name!r} "
                    f"(attempt {attempt + 1}/{LISTING_RETRIES + 1}), "
                    f"retrying in {LISTING_RETRY_DELAY}s",
                    exc_info=True,
                )
                sleep(LISTING_RETRY_DELAY)
            except AlfrescoAuthError:
                # Returning None here would only mark the seed incomplete, so
                # the watcher would retry forever without ever telling the user
                # their credentials expired.
                raise
            except Exception:
                log.exception(f"Error listing children of {remote_info.name!r}")
                return None

        log.error(
            f"Giving up listing children of {remote_info.name!r}; "
            "it will be retried on the next cycle"
        )
        return None

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

        # Widening the selection brings back a row that add_filter() marked
        # deleted. update_remote_state() alone cannot revive it: Alfresco
        # digests are None, so its "not dirty" short-circuit returns before
        # persisting anything and the row stays remotely_deleted — the
        # processor would then delete the local copy we just restored.
        if child_pair.remote_state == "deleted" or child_pair.pair_state in (
            "remotely_deleted",
            "parent_remotely_deleted",
        ):
            log.info(f"Restoring {child_info.name!r} from {child_pair.pair_state!r}")
            self.dao.update_remote_state(
                child_pair,
                child_info,
                remote_parent_path=remote_parent_path,
                force_update=True,
                versioned=False,
            )
            self.dao.force_remote(child_pair)
            return self.dao.get_state_from_id(child_pair.id, from_write=True)

        # Alfresco does not expose a content hash, so digest is
        # always None.  Detect content changes by comparing the
        # modification timestamp instead.
        # The DB stores timestamps as 'YYYY-MM-DD HH:MM:SS'
        # (no microseconds/timezone), while the server returns
        # full datetime objects.  Normalise both sides to the
        # DB format before comparing.
        remote_ts = child_info.last_modification_time
        if isinstance(remote_ts, datetime):
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
            # was created independently: for a document, same name on both
            # sides is a conflict rather than a link. Folders are merged
            # instead -- the processor already adopts a same-named remote
            # folder, and "keep local or remote" cannot be answered for a
            # folder without discarding its children. ``versioned`` bumps the
            # row version so an in-flight processor holding stale state cannot
            # overwrite the conflict via ``synchronize_state``'s optimistic
            # lock.
            conflicting = (
                not child_info.folderish
                and not existing.remote_ref
                and existing.local_state == "created"
            )
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

        The signal is always emitted, but the pass is only *recorded* as done
        when it succeeded. These are separate concerns that the base class
        bundles together:

        - ``initiate`` starts the queue manager's processors. Skipping it
          leaves the engine with no workers for the rest of the session.
        - ``first_pass_done`` gates local creations
          (``Processor._ensure_remote_first_pass``). Setting it before the
          remote view is complete duplicates documents created server-side
          while Drive was stopped, instead of flagging them as conflicts.
        """
        succeeded = False
        try:
            succeeded = bool(self._do_handle_changes(first_pass))
            return succeeded
        finally:
            if first_pass:
                if succeeded:
                    self.first_pass_done = True
                self.initiate.emit()
            else:
                self.updated.emit()
                # Called directly because the @tooltip decorator swallows
                # return values, breaking the signal-based path.
                self.engine._check_last_sync()

    def _do_handle_changes(self, first_pass: bool, /) -> bool:
        remote = self.engine.remote
        if not remote:
            log.warning("No remote client available, skipping poll")
            return False

        # Snapshot queue size before the poll to detect new work
        qm_before = self.engine.queue_manager.get_overall_size()

        # Provisioning, seeding and un-filtering all do remote work, so they
        # share the poll's recovery boundary: an exception escaping here
        # reaches Worker.run(), which quits the thread and silently ends
        # remote synchronisation for the rest of the session.
        try:
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

            # A new subscription starts empty: the feed only carries events
            # from its creation onward, so existing content is seeded once.
            seeded = self._bootstrap_if_needed()

            # Widening the selection exposes content the feed never mentions.
            self._apply_unfiltered()

            drained = self._poll_device_sync()
            completed = seeded and drained
        except ThreadInterrupt:
            # Cooperative shutdown from _interact(), not a failure.
            raise
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

        if not completed:
            log.warning(
                "Remote view is not complete after this cycle; local "
                "creations stay held until a pass finishes cleanly"
            )
        return completed

    def scan_pair(self, remote_path: str, /) -> None:
        """Nudge the poll timer after a filter change.

        The work itself is queued by :meth:`queue_unfiltered`, which
        ``AlfrescoEngine.remove_filter`` calls with the node ids.
        """
        self._next_check = monotonic() + FILTER_RESCAN_DELAY

    @Slot(str, object)
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
        for index, node_id in enumerate(node_ids):
            self._interact()
            try:
                resolved = self._resolve_unfiltered_node(node_id)
            except Exception:
                # An auth failure (or a shutdown) aborts the loop, so put back
                # this id and every one still untouched: the change feed never
                # replays already-existing content, and a dropped id is the
                # only handle we have on it.
                self._unfiltered_nodes.update(node_ids[index:])
                self._next_check = monotonic() + FILTER_RESCAN_DELAY
                raise
            if not resolved:
                self._unfiltered_nodes.add(node_id)

        if self._unfiltered_nodes:
            log.error(
                f"{len(self._unfiltered_nodes)} unfiltered node(s) could not be "
                "resolved; retrying on the next poll cycle"
            )
            self._next_check = monotonic() + FILTER_RESCAN_DELAY

    def _resolve_unfiltered_node(self, node_id: str, /) -> bool:
        """Pull one un-filtered node back into scope.

        Returns ``False`` only when the caller should retry later.
        """
        remote = self.engine.remote
        try:
            node = remote.get_node(node_id, include=["path"])
        except AlfrescoAuthError:
            log.exception(f"Cannot fetch unfiltered node {node_id!r}, auth failed")
            raise
        except NotFoundError:
            log.warning(
                f"Unfiltered node {node_id!r} no longer exists on the server, "
                "nothing to restore"
            )
            return True
        except Exception:
            log.exception(f"Could not fetch unfiltered node {node_id!r}")
            return False

        info = remote._node_to_remote_file_info(node)
        if self._is_filtered_path(info.path):
            log.debug(f"Unfiltered {info.path!r} is still excluded by another rule")
            return True

        parent_pair = self._resolve_parent(info)
        if parent_pair is None:
            # The parent is filtered too, so there is no row to hang this off.
            log.debug(
                f"Parent of unfiltered {info.path!r} is unknown, "
                "falling back to a full re-seed"
            )
            self.dao.update_config(CONF_BOOTSTRAPPED_FOR, None)
            return True

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

        # Filtering marked every descendant deleted, so the subtree has to be
        # rebuilt even where an unfinished seed already checkpointed it.
        if (
            info.folderish
            and pair
            and not self._scan_remote_recursive(pair, info, force=True)
        ):
            log.error(
                f"Subtree of restored {info.path!r} was only partially scanned; "
                "forcing a re-seed"
            )
            self.dao.update_config(CONF_BOOTSTRAPPED_FOR, None)

        return True

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

    def _resubscribe(self) -> bool:
        """Recreate the subscription so the server replays the full content."""
        if not self._provisioner or not self._root_node_id:
            return False
        if not self._provisioner.resubscribe(self._root_node_id):
            log.error("Re-subscription failed, change feed is stale")
            return False
        return True

    # -- Initial seeding -----------------------------------------------------

    def _bootstrap_if_needed(self) -> bool:
        """Seed the DAO with existing remote content, once per subscription.

        Device Sync reports events from subscription creation onward, so a
        brand-new subscription yields an empty delta even when the repository
        is full. A single tree walk populates that starting state; the change
        feed handles everything afterwards.

        Keyed on the subscription id rather than a boolean so that a
        re-subscription (after a server-side reset) seeds again.

        Returns whether the local view can be considered seeded -- the first
        pass must not complete on a half-walked tree, or local creations are
        released against an incomplete remote view and get duplicated.
        """
        provisioner = self._provisioner
        if not provisioner or not provisioner.subscription_id:
            return False

        done_for = self.dao.get_config(CONF_BOOTSTRAPPED_FOR)
        if done_for == provisioner.subscription_id:
            return True

        # Checkpoints belong to one subscription; a different one invalidates
        # them, otherwise a resumed seed would skip folders it never walked.
        if self.dao.get_config(CONF_SEEDING_FOR) != provisioner.subscription_id:
            self._reset_scan_progress()
            self.dao.update_config(CONF_SEEDING_FOR, provisioner.subscription_id)

        log.info(
            "Seeding initial content for subscription "
            f"{provisioner.subscription_id!r} (previous seed: {done_for!r})"
        )
        start = monotonic()
        queue_before = self.engine.queue_manager.get_overall_size()

        if not self._scan_remote_tree():
            owed = len(self.dao.get_paths_to_scan())
            log.error(
                f"Initial scan did not complete; {owed} folder(s) will be "
                "retried on the next poll cycle (already-walked folders are "
                "skipped)"
            )
            return False

        self._reset_scan_progress()
        self.dao.update_config(CONF_SEEDING_FOR, None)
        self.dao.update_config(CONF_BOOTSTRAPPED_FOR, provisioner.subscription_id)
        queue_after = self.engine.queue_manager.get_overall_size()
        log.info(
            f"Seeding finished in {monotonic() - start:.2f}s, "
            f"queued {queue_after - queue_before} item(s)"
        )
        return True

    def _reset_scan_progress(self) -> None:
        """Drop the per-folder checkpoints of a seed."""
        self.dao.clean_scanned()
        for path in self.dao.get_paths_to_scan():
            self.dao.delete_path_to_scan(path)

    # -- Device Sync change feed ---------------------------------------------

    def _poll_device_sync(self) -> bool:
        """Consume the change feed, one batch per POST/GET/DELETE round.

        The service caps a batch at 100 changes and only moves its cursor
        (``last_seq_num``) when a sync is cleared, so a backlog is drained by
        repeating the whole cycle -- re-polling one sync returns the identical
        payload forever.

        The pending bookmark is stored per *subscription*, not per sync, so
        clearing anything other than the most recently started sync would
        commit a bookmark that belongs to a batch we never applied.

        Returns whether the feed was drained: a cycle that left changes
        undelivered must not count as a completed first pass.
        """
        provisioner = self._provisioner
        if not provisioner:
            return False

        remote = self.engine.remote
        subscriber_id = provisioner.subscriber_id
        subscription_id = provisioner.subscription_id
        total_changes = 0
        previous_seq: Optional[int] = None
        rounds = 0
        drained = False

        for rounds in range(1, MAX_SYNC_ROUNDS + 1):
            self._interact()

            started = remote.start_sync(
                subscriber_id,
                subscription_id,
                client_version=provisioner.client_version,
            )

            if started.status == SyncState.ERROR:
                log.error(
                    f"Server refused to start a sync: {started.message!r} "
                    f"(subscriber={subscriber_id!r}, "
                    f"subscription={subscription_id!r})"
                )
                return False

            sync_id = started.sync_id
            if not sync_id:
                log.error(f"start_sync returned no sync_id: {started!r}")
                return False

            batch = self._consume_sync(subscriber_id, subscription_id, sync_id)
            total_changes += batch.applied

            if not batch.acknowledge:
                log.warning(
                    f"Leaving sync {sync_id!r} unacknowledged so the server "
                    "re-delivers its changes on the next cycle"
                )
                break

            # An empty batch's pending bookmark is the highest sequence number
            # ever handed out, which runs ahead of changes that are allocated
            # but not yet visible. Committing it would skip them for good, so
            # an idle sync is abandoned rather than cleared.
            if batch.idle and not self._sync_keepalive_due():
                drained = True
                break

            # DELETE is what commits ``last_seq_num``; until it lands the
            # server keeps serving this same batch.
            try:
                remote.clear_sync(subscriber_id, subscription_id, sync_id)
            except Exception:
                log.error(
                    f"Could not clear sync {sync_id!r}, stopping this cycle "
                    "so the batch is not re-applied",
                    exc_info=True,
                )
                break
            self.dao.update_config(CONF_LAST_SYNC_CLEAR, str(time()))

            if batch.reset:
                # The replacement subscription replays everything as fresh
                # CREATEs, and none of it has been seeded yet.
                log.warning(
                    "Subscription was replaced after a reset; the remote view "
                    "is incomplete until the new one is seeded"
                )
                break

            if not batch.more:
                drained = True
                break

            # An expired sync is cleared with a 204 without moving the cursor,
            # so an identical batch means we would loop on it indefinitely.
            if batch.last_seq is not None and batch.last_seq == previous_seq:
                log.error(
                    f"Batch ending at seq={batch.last_seq} was delivered twice "
                    "in a row, the server cursor is not advancing; abandoning "
                    "this cycle"
                )
                break
            previous_seq = batch.last_seq
        else:
            log.warning(
                f"Stopped after {MAX_SYNC_ROUNDS} batches with more changes "
                "pending, the rest follows on the next cycle"
            )

        if total_changes:
            log.debug(f"Applied {total_changes} change(s) in {rounds} batch(es)")
        return drained

    def _sync_keepalive_due(self) -> bool:
        """Whether an idle sync should be cleared anyway.

        Only a cleared sync refreshes the server's ``last_sync_time``, and a
        subscription left untouched for ``sync.cleanup.keepPeriod`` is forced
        into a full replay.
        """
        last = self.dao.get_config(CONF_LAST_SYNC_CLEAR)
        if not last:
            return True
        return time() - float(last) >= SYNC_KEEPALIVE_INTERVAL

    def _consume_sync(
        self, subscriber_id: str, subscription_id: str, sync_id: str, /
    ) -> "_SyncBatch":
        """Wait for one batch to be ready and apply it."""
        remote = self.engine.remote
        total = 0
        delay = NOT_READY_POLL_DELAY
        deadline = monotonic() + NOT_READY_TIMEOUT
        attempt = 0

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
                return _SyncBatch(total, False, False, None, False)

            # Starting a sync is asynchronous, so this is the normal answer
            # until the worker thread has built the batch.
            if status.status == SyncState.NOT_READY:
                if monotonic() >= deadline:
                    break
                sleep(delay)
                delay = min(delay * 1.5, NOT_READY_POLL_MAX)
                continue

            # Both signals invalidate the sync we are draining, so stop
            # here rather than paging through a feed we no longer trust.
            if status.missing:
                log.error(
                    f"Server does not know subscriptions {status.missing} "
                    "— re-provisioning on the next cycle"
                )
                self._invalidate_provisioning()
                return _SyncBatch(total, False, False, None, False)

            # A reset rides along with an otherwise successful response and its
            # bookmark is already pending, so it has to be cleared or the
            # server replays it forever.
            if status.resets:
                log.warning(
                    f"Server requested a reset of {status.resets} — the "
                    "local view is stale, re-subscribing for a full replay"
                )
                return _SyncBatch(
                    total, self._resubscribe(), False, None, False, reset=True
                )

            total += self._apply_changes(status.changes)
            last_seq = (
                max((c.seq_no or 0) for c in status.changes) if status.changes else None
            )
            return _SyncBatch(
                total,
                True,
                bool(status.more_changes),
                last_seq,
                not status.changes,
            )

        log.error(
            f"Sync {sync_id!r} was still not ready after {attempt} polls, "
            "abandoning this cycle"
        )
        return _SyncBatch(total, False, False, None, False)

    def _apply_changes(self, changes: List[Change], /) -> int:
        """Apply one page of the change feed. Returns how many were applied.

        A failing change is re-raised so the sync goes unacknowledged and the
        server re-delivers it, which recovers transient faults. Once a node has
        failed :data:`MAX_CHANGE_RETRIES` times it is abandoned instead, or it
        would block every later change forever.
        """
        applied = 0
        for change in self._dedupe_changes(changes):
            self._interact()
            try:
                if self._apply_change(change):
                    applied += 1
            except (ThreadInterrupt, AlfrescoAuthError):
                raise
            except Exception as exc:
                if self._retry_change(change, exc):
                    raise
            else:
                self._change_failures.pop(change.node_id, None)
        return applied

    def _retry_change(self, change: Change, exc: Exception, /) -> bool:
        """Record a failed change; return whether it should be retried."""
        failures = self._change_failures.get(change.node_id, 0) + 1
        self._change_failures[change.node_id] = failures

        if failures < MAX_CHANGE_RETRIES:
            log.warning(
                f"Could not apply change seq={change.seq_no} "
                f"node={change.node_id!r} (attempt {failures}/"
                f"{MAX_CHANGE_RETRIES}), leaving it unacknowledged to retry",
                exc_info=True,
            )
            return True

        log.error(
            f"Abandoning change seq={change.seq_no} node={change.node_id!r} "
            f"after {failures} attempts: {exc}",
            exc_info=True,
        )
        self._change_failures.pop(change.node_id, None)
        self._report_change_failure(change, exc)
        return False

    def _report_change_failure(self, change: Change, exc: Exception, /) -> None:
        """Surface an abandoned change to the user.

        Acknowledging the sync drops the change for good, so the mismatch has
        to become visible: the pair is pushed past the queue manager's error
        threshold, which lists it in the systray and fires ``newError``.
        """
        pair = self.dao.get_normal_state_from_remote(change.node_id)
        if not pair:
            # Nothing local to attach the error to, so the only way back to a
            # correct state is to walk the tree again on the next cycle.
            log.error(
                f"Abandoned change for unsynced node {change.node_id!r}; "
                "forcing a re-seed to recover it"
            )
            self.dao.update_config(CONF_BOOTSTRAPPED_FOR, None)
            return

        threshold = self.engine.queue_manager.get_error_threshold()
        self.dao.increase_error(
            pair,
            CHANGE_FAILED_ERROR,
            details=str(exc),
            incr=threshold + 1,
        )
        self.engine.queue_manager.push_error(pair)

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
            # Normally the parent arrived earlier in seq_no order, but a seed
            # that missed it (or an earlier page that failed) breaks that.
            # Acknowledging here would drop the child for good, so record the
            # parent as owed work and force a seed that can find it.
            log.error(
                f"Parent {info.parent_uid!r} of {info.name!r} is unknown; "
                "scheduling a re-seed so it is not lost"
            )
            self.dao.add_path_to_scan(info.parent_uid)
            self.dao.update_config(CONF_BOOTSTRAPPED_FOR, None)
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
        except AlfrescoAuthError:
            # Must reach _do_handle_changes so credentials are flagged invalid;
            # falling back to the payload would insert a half-populated row.
            log.exception(
                f"Cannot fetch node {change.node_id!r} ({change.name!r}), "
                "auth failed"
            )
            raise
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
        """Advance the local sweep by one chunk, resuming across cycles.

        The watchdog-based local watcher can miss changes when:
        - An application saves via atomic temp-file + rename (e.g. Word, LibreOffice)
        - A file is copied while the watchdog event loop is busy
        - The watchdog ``[modified]`` event fires before the actual write completes

        This method compensates by doing a periodic digest comparison for
        existing pairs and discovering new files not yet tracked. Only
        :data:`LOCAL_SCAN_CHUNK` entries are examined per cycle so a large
        workspace cannot monopolise the watcher thread.
        """
        local = self.engine.local
        dao = self.dao

        if not local.exists(ROOT):
            log.warning("Local sync root does not exist, skipping local scan")
            return

        if not self._local_scan_dirs:
            # Two aggregators threaded through the sweep.
            #   _local_scan_seen: every ``remote_id`` xattr encountered while
            #     walking the tree. Used to distinguish a genuine local
            #     deletion from a rename/move whose watchdog event has not
            #     yet been processed (NXDRIVE-3221).
            #   _local_scan_deletions: pairs whose local path is missing on
            #     disk. Deletion is *deferred* until the whole tree has been
            #     walked so we can consult the complete set of surviving refs.
            log.info("Starting Alfresco local change scan")
            self._local_scan_dirs = [ROOT]
            self._local_scan_seen = set()
            self._local_scan_deletions = []
            self._local_scan_incomplete = False

        start = monotonic()
        examined = 0
        while self._local_scan_dirs and examined < LOCAL_SCAN_CHUNK:
            self._interact()
            examined += self._scan_local_directory(
                self._local_scan_dirs.pop(0), local, dao
            )

        if self._local_scan_dirs:
            log.debug(
                f"Local scan paused after {examined} entr(ies) in "
                f"{monotonic() - start:.2f}s, "
                f"{len(self._local_scan_dirs)} folder(s) left"
            )
            return

        # Only a completed sweep has seen every surviving xattr, so deletions
        # can finally be told apart from renames.
        if self._local_scan_incomplete:
            log.warning(
                "Local scan finished with unreadable directories; skipping "
                f"{len(self._local_scan_deletions)} deletion candidate(s) "
                "until a clean sweep confirms them"
            )
        else:
            self._process_pending_deletions(
                self._local_scan_deletions, self._local_scan_seen
            )
        self._local_scan_seen = set()
        self._local_scan_deletions = []
        log.debug(f"Alfresco local change scan finished in {monotonic() - start:.2f}s")

    def _scan_local_directory(self, path: Path, local: Any, dao: Any, /) -> int:
        """Scan one directory, queueing its sub-folders. Returns entries seen.

        A directory is always processed whole: the leftover entries of
        ``db_by_name`` are what reveal local deletions.
        """
        try:
            children_info = local.get_children_info(path)
        except OSError:
            # Deletion is decided by what the sweep did *not* see, so a
            # directory we failed to list would make anything moved into it
            # look deleted.
            log.error(
                f"Could not list {path!r}; local deletions will not be "
                "processed for this sweep",
                exc_info=True,
            )
            self._local_scan_incomplete = True
            return 0

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
                self._local_scan_seen.add(remote_ref)

            if child_name in db_by_name:
                child_pair = db_by_name[child_name]

                # Already queued, or being processed: nothing to compare, but
                # sub-folders still need walking.
                if child_pair.pair_state != "synchronized" or child_pair.processor > 0:
                    if child_info.folderish:
                        self._local_scan_dirs.append(child_info.path)
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
                    self._local_scan_dirs.append(child_info.path)
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
                    # Jump the queue: appending would hold this folder's
                    # contents back until the rest of the tree has been swept,
                    # which is minutes on a large workspace.
                    self._local_scan_dirs.insert(0, child_info.path)

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
                self._local_scan_deletions.append(child_pair)

        return len(children_info)

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
