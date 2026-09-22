"""
Enterprise-only Sync Service (dsync) change provider for the Alfresco engine.

This module turns the Alfresco Enterprise **Sync Service** change feed into a
drop-in replacement for the remote watcher's full recursive tree scan. Where the
full scan costs O(total tree) on every poll, the change feed costs O(changes) —
matching Nuxeo's ``GetChangeSummary`` model.

Responsibilities
----------------
* **Capability detection** — is this an Enterprise server with a reachable Sync
  Service and a compatible client version? (:meth:`SyncServiceChangeProvider.is_available`)
* **Device provisioning** — register a *subscriber* and a node *subscription*
  (repo-side private API) and persist their ids in the engine DAO so they are
  reused across restarts. (:meth:`SyncServiceChangeProvider.ensure_provisioned`)
* **Delta pull** — drive the async ``start_sync`` → ``get_sync`` → ``clear_sync``
  protocol, draining all pending change batches and advancing the server-side
  ``seqNo`` marker. (:meth:`SyncServiceChangeProvider.poll`)
* **Delta → DAO mapping** — translate each change into the same DAO operations
  the full scan performs, but only for the affected nodes.
  (:meth:`SyncServiceChangeProvider.apply`)

The wire protocol was reverse-engineered and verified live in Phase 0; see
``docs/alfresco_sync_service.md`` and the captured payloads under
``tests/alfresco/sync_service/fixtures/``.

The pure :func:`classify` helper (change dict → :class:`ChangeAction`) is kept
free of any Qt / DAO / network dependency so it can be unit-tested against those
fixtures without a live server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from logging import getLogger
from time import sleep
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from nxdrive.alfresco.engine.watcher.remote_watcher import AlfrescoRemoteWatcher

__all__ = (
    "ChangeAction",
    "SyncServiceChangeProvider",
    "classify",
)

log = getLogger(__name__)

# -- DAO config keys (persisted device/subscription state) -------------------
CONF_SUBSCRIBER = "alfresco_sync_subscriber_id"
CONF_SUBSCRIPTION = "alfresco_sync_subscription_id"
CONF_TARGET = "alfresco_sync_target_node_id"
CONF_LAST_SEQNO = "alfresco_sync_last_seqno"
CONF_SEEDED = "alfresco_sync_seeded"
CONF_CYCLE = "alfresco_sync_cycle"

# -- Change kinds (normalized) -----------------------------------------------
KIND_CREATE = "create"
KIND_UPDATE = "update"
KIND_RENAME = "rename"
KIND_MOVE = "move"
KIND_DELETE = "delete"
KIND_RESET = "reset"
KIND_UNKNOWN = "unknown"

#: Minimum ``clientVersion`` the Sync Service accepts in a sync request body.
#: Both this and a ``changes`` list are mandatory (Phase 0 finding).
DEFAULT_CLIENT_VERSION = "1.0.1"

# Wire ``type`` → normalized kind. The wire type is coarser than the full
# ``ChangeType`` enum (Phase 0: content edits arrive as generic ``UPDATE_REPOS``).
_TYPE_TO_KIND: Dict[str, str] = {
    "CREATE_REPOS": KIND_CREATE,
    "UPDATE_REPOS": KIND_UPDATE,
    "UPDATE_CONTENT_REPOS": KIND_UPDATE,
    "UPDATE_METADATA_REPOS": KIND_UPDATE,
    "RENAME_REPOS": KIND_RENAME,
    "RENAME_UPDATE_REPOS": KIND_RENAME,
    "MOVE_REPOS": KIND_MOVE,
    "DELETE_REPOS": KIND_DELETE,
    "RESET": KIND_RESET,
}


@dataclass
class ChangeAction:
    """A single Sync Service change, normalized for DAO application.

    Built by :func:`classify` from a raw change dict (the ``changes[]`` entries
    of a ``SyncStatus`` payload). All the structural fidelity we need —
    rename (``name`` → ``to_name``), move (``parent_node_ids`` →
    ``to_parent_node_ids``) and tombstones — is preserved.
    """

    kind: str
    node_id: str
    seq_no: int = -1
    name: str = ""
    to_name: Optional[str] = None
    path: str = ""
    to_path: Optional[str] = None
    parent_node_ids: List[str] = field(default_factory=list)
    to_parent_node_ids: List[str] = field(default_factory=list)
    node_type: str = ""
    size: int = -1
    is_folder: bool = False
    change_type: str = ""

    @property
    def new_parent_id(self) -> str:
        """Best-known parent node id *after* the change (nearest ancestor)."""
        if self.to_parent_node_ids:
            return self.to_parent_node_ids[0]
        if self.parent_node_ids:
            return self.parent_node_ids[0]
        return ""

    @property
    def effective_name(self) -> str:
        """Node name *after* the change (``to_name`` wins for renames)."""
        return self.to_name or self.name


def _as_int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def classify(raw: Dict[str, Any]) -> ChangeAction:
    """Normalize one raw Sync Service change dict into a :class:`ChangeAction`.

    Pure function (no I/O) so it is unit-testable against the captured fixtures.
    Unknown wire types map to :data:`KIND_UNKNOWN`, which the provider treats as
    a signal to fall back to a full reconciliation scan rather than guess.
    """
    change_type = str(raw.get("type") or raw.get("changeType") or "")
    kind = _TYPE_TO_KIND.get(change_type, KIND_UNKNOWN)

    node_type = str(raw.get("nodeType") or "")
    is_folder = bool(raw.get("folderChange")) or node_type.endswith(":folder")

    return ChangeAction(
        kind=kind,
        node_id=str(raw.get("nodeId") or raw.get("id") or ""),
        seq_no=_as_int(raw.get("seqNo")),
        name=str(raw.get("name") or ""),
        to_name=raw.get("toName"),
        path=str(raw.get("path") or ""),
        to_path=raw.get("toPath"),
        parent_node_ids=list(raw.get("parentNodeIds") or []),
        to_parent_node_ids=list(raw.get("toParentNodeIds") or []),
        node_type=node_type,
        size=_as_int(raw.get("size")),
        is_folder=is_folder,
        change_type=change_type,
    )


class SyncServiceChangeProvider:
    """Delta-driven remote change source backing :class:`AlfrescoRemoteWatcher`.

    A plain (non-Qt) helper owned by the watcher. It reuses the watcher's proven
    per-node DAO helpers (``_match_or_create_child`` etc.) so the mapping from a
    change to database state is identical to what the full scan would produce —
    only the *discovery* of what changed is different (and far cheaper).
    """

    #: Max poll iterations before giving up waiting for ``ready``/``error``.
    _POLL_ATTEMPTS = 40
    #: Delay between status polls while a sync is still running.
    _POLL_INTERVAL = 0.25
    #: Max drain rounds per :meth:`poll` (each acknowledges a batch).
    _DRAIN_ROUNDS = 8

    def __init__(self, watcher: "AlfrescoRemoteWatcher", /) -> None:
        self.watcher = watcher
        self.dao = watcher.dao
        # Cached provisioning identifiers (loaded lazily from the DAO).
        self._subscriber_id: str = ""
        self._subscription_id: str = ""
        self._available: Optional[bool] = None
        self._client_version: str = DEFAULT_CLIENT_VERSION
        #: Set when a change we cannot safely apply incrementally is seen, so
        #: the watcher performs a full reconciliation scan this cycle instead.
        self.needs_full_scan: bool = False

    # -- capability detection -----------------------------------------------

    @property
    def remote(self) -> Any:
        return self.watcher.engine.remote

    def is_available(self) -> bool:
        """Return whether the delta feed can be used against this server.

        Requires: the feature flag on, a configured/discoverable Sync Service
        URL, an Enterprise repository and a compatible client version. The
        result is cached; a negative result makes the watcher use the full scan.
        """
        if self._available is not None:
            return self._available

        remote = self.remote
        if not remote or not getattr(remote, "sync_service_url", ""):
            self._available = False
            return False

        try:
            cfg = remote.get_device_sync_config()
        except Exception:
            log.warning("Sync Service capability probe failed", exc_info=True)
            self._available = False
            return False

        edition = (
            getattr(getattr(cfg, "repo_info", None), "edition", "") or ""
        ).lower()
        if edition and edition != "enterprise":
            log.info("Sync Service unavailable: repository edition is %r", edition)
            self._available = False
            return False

        min_version = getattr(cfg, "dsync_client_version_min", "") or ""
        if min_version:
            self._client_version = min_version

        self._available = True
        log.info(
            "Sync Service available (edition=%r, min_client_version=%r)",
            edition or "enterprise",
            self._client_version,
        )
        return True

    # -- provisioning / persistence -----------------------------------------

    def _load_ids(self) -> None:
        if not self._subscriber_id:
            self._subscriber_id = self.dao.get_config(CONF_SUBSCRIBER) or ""
        if not self._subscription_id:
            self._subscription_id = self.dao.get_config(CONF_SUBSCRIPTION) or ""

    def ensure_provisioned(self, root_node_id: str, /) -> bool:
        """Ensure a subscriber + subscription exist for ``root_node_id``.

        Reuses persisted ids when the subscription still targets the same root;
        otherwise registers a fresh subscriber and node subscription and stores
        their ids. Returns ``True`` when provisioning is in place.
        """
        self._load_ids()

        prev_target = self.dao.get_config(CONF_TARGET) or ""
        if (
            self._subscriber_id
            and self._subscription_id
            and prev_target == root_node_id
        ):
            return True

        remote = self.remote
        device_os = (getattr(remote, "device_id", "") and "desktop") or "desktop"
        try:
            subscriber = remote.create_subscriber(device_os, self._client_version)
            subscriber_id = getattr(subscriber, "id", "") or ""
            subscription = remote.create_subscription(
                subscriber_id, root_node_id, "BOTH"
            )
            subscription_id = getattr(subscription, "id", "") or ""
        except Exception:
            log.warning(
                "Sync Service provisioning failed for root %r",
                root_node_id,
                exc_info=True,
            )
            return False

        if not subscriber_id or not subscription_id:
            log.warning("Sync Service provisioning returned empty ids")
            return False

        self._subscriber_id = subscriber_id
        self._subscription_id = subscription_id
        self.dao.update_config(CONF_SUBSCRIBER, subscriber_id)
        self.dao.update_config(CONF_SUBSCRIPTION, subscription_id)
        self.dao.update_config(CONF_TARGET, root_node_id)
        self.dao.update_config(CONF_LAST_SEQNO, None)
        self.dao.update_config(CONF_SEEDED, None)
        log.info(
            "Provisioned Sync Service device (subscriber=%s, subscription=%s) "
            "for root %s",
            subscriber_id,
            subscription_id,
            root_node_id,
        )
        return True

    def reset_provisioning(self) -> None:
        """Forget persisted ids so the next cycle re-provisions from scratch."""
        self._subscriber_id = ""
        self._subscription_id = ""
        for key in (CONF_SUBSCRIBER, CONF_SUBSCRIPTION, CONF_TARGET, CONF_LAST_SEQNO):
            self.dao.update_config(key, None)

    # -- seeding / reconciliation bookkeeping --------------------------------

    def is_seeded(self) -> bool:
        """Whether the baseline full scan has run since (re)provisioning.

        Deltas only make sense once the DB mirrors the current tree; before that
        the watcher must do one full scan to seed ``DocPair`` rows.
        """
        return bool(self.dao.get_config(CONF_SEEDED))

    def on_full_scan_done(self) -> None:
        """Record that a full scan completed: mark seeded, reset the counter."""
        self.dao.update_config(CONF_SEEDED, "1")
        self.dao.update_config(CONF_CYCLE, "0")

    def due_for_reconcile(self, every: int, /) -> bool:
        """Whether a periodic full reconciliation scan is due.

        Increments a per-cycle counter; returns ``True`` once ``every`` delta
        cycles have elapsed (the counter is reset by :meth:`on_full_scan_done`
        after the reconciliation scan). ``every <= 0`` disables it.
        """
        if every <= 0:
            return False
        count = _as_int(self.dao.get_config(CONF_CYCLE), 0) + 1
        self.dao.update_config(CONF_CYCLE, str(count))
        return count >= every

    # -- delta pull + apply --------------------------------------------------

    def pull_and_apply(self) -> bool:
        """Drain all pending changes, applying each batch *before* acking it.

        Acknowledging (``clear_sync``) advances the server-side ``seqNo`` marker
        and drops the batch from the feed forever, so it must happen only after
        the batch has been written to the DAO — otherwise a crash between ack
        and apply would silently lose those changes.

        Returns ``True`` when the delta feed fully handled remote change
        detection this cycle. Returns ``False`` (caller should run a full scan)
        on a protocol error/reset, an incomplete sync, or any change that could
        not be applied incrementally (:attr:`needs_full_scan`). Subscription
        problems (error / reset / missing) also drop the persisted provisioning
        so the next cycle re-registers.
        """
        self._load_ids()
        if not self._subscriber_id or not self._subscription_id:
            return False

        self.needs_full_scan = False
        remote = self.remote
        request = {"clientVersion": self._client_version, "changes": []}

        for _ in range(self._DRAIN_ROUNDS):
            try:
                started = remote.start_sync(
                    self._subscriber_id, self._subscription_id, request
                )
                sync_id = getattr(started, "sync_id", "") or ""
                status = started
                for _ in range(self._POLL_ATTEMPTS):
                    if getattr(status, "status", "") in ("ready", "error"):
                        break
                    sleep(self._POLL_INTERVAL)
                    status = remote.get_sync(
                        self._subscriber_id, self._subscription_id, sync_id
                    )
            except Exception:
                log.warning("Sync Service poll failed", exc_info=True)
                return False

            state = getattr(status, "status", "")
            if state == "error":
                log.warning(
                    "Sync Service returned error: %s",
                    getattr(status, "message", ""),
                )
                self._safe_clear(sync_id)
                self.reset_provisioning()
                return False

            if state != "ready":
                # The sync never completed within the poll window. Do NOT
                # acknowledge it (that would drop its unseen changes); just
                # fall back to a full scan this cycle.
                log.warning(
                    "Sync Service sync did not complete (status=%r); full scan",
                    state,
                )
                return False

            raw = getattr(status, "_raw", {}) or {}
            if raw.get("resets") or raw.get("missing"):
                log.info("Sync Service requested reset/re-subscribe")
                self._safe_clear(sync_id)
                self.reset_provisioning()
                return False

            actions = [
                classify(change)
                for change in (raw.get("changes") or [])
                if isinstance(change, dict)
            ]

            if actions:
                self.apply(actions)
                max_seq = max((a.seq_no for a in actions if a.seq_no >= 0), default=-1)
                if max_seq >= 0:
                    self.dao.update_config(CONF_LAST_SEQNO, str(max_seq))

            # Ack only now that the batch is durably applied.
            self._safe_clear(sync_id)

            if not getattr(status, "more_changes", False):
                break

        return not self.needs_full_scan

    def _safe_clear(self, sync_id: str) -> None:
        if not sync_id:
            return
        try:
            self.remote.clear_sync(self._subscriber_id, self._subscription_id, sync_id)
        except Exception:
            log.debug("clear_sync failed for %s", sync_id, exc_info=True)

    # -- delta application ---------------------------------------------------

    def apply(self, actions: List[ChangeAction], /) -> None:
        """Apply changes to the DAO in ``seqNo`` order.

        Deletes are exact and O(1). Creates/updates/renames/moves re-fetch just
        the affected node and reuse the watcher's per-node helpers. Anything we
        cannot place confidently (unknown type, reset, or a create whose parent
        is not yet synced) flips :attr:`needs_full_scan` so the watcher performs
        a reconciliation scan this cycle.
        """
        for action in sorted(actions, key=lambda a: a.seq_no):
            try:
                self._apply_one(action)
            except Exception:
                log.warning(
                    "Failed to apply change %s on %s; requesting full scan",
                    action.change_type,
                    action.node_id,
                    exc_info=True,
                )
                self.needs_full_scan = True

    def _apply_one(self, action: ChangeAction, /) -> None:
        if action.kind in (KIND_RESET, KIND_UNKNOWN):
            log.info(
                "Change %r not incrementally applicable; requesting full scan",
                action.change_type,
            )
            self.needs_full_scan = True
            return

        if not action.node_id:
            return

        if action.kind == KIND_DELETE:
            self._apply_delete(action)
            return

        if action.kind == KIND_MOVE:
            self._apply_move(action)
            return

        self._apply_upsert(action)

    def _apply_delete(self, action: ChangeAction, /) -> None:
        pairs = self.dao.get_states_from_remote(action.node_id)
        for pair in pairs:
            if pair.pair_state in ("locally_created", "locally_modified"):
                log.debug(
                    "Skip remote deletion of %r: pair is %r",
                    pair.local_name,
                    pair.pair_state,
                )
                continue
            log.info("Marking %r as remotely deleted (delta)", pair.local_path)
            self.dao.delete_remote_state(pair)

    def _apply_move(self, action: ChangeAction, /) -> None:
        """Relocate a moved node incrementally (no full scan).

        A ``MOVE_REPOS`` change carries the node's new parent. We re-parent the
        existing ``DocPair`` (``update_remote_state`` with the *new* remote
        parent path/ref) and flag it ``remotely_modified`` so the processor's
        move branch relocates the local file/folder on disk — and, for folders,
        heals every descendant's stored path via the cascading
        ``update_{remote,local}_parent_path`` helpers. Only the *discovery* is
        incremental; the relocation reuses the exact same processor path the
        full scan would.

        Falls back to a full scan only when the node's new parent is not yet
        synced (its local placement is unknown this cycle).
        """
        existing = self.dao.get_states_from_remote(action.node_id)
        if not existing:
            # Node isn't tracked yet: place it under its new parent as a create.
            self._apply_upsert(action)
            return

        parent_pair = self.dao.get_normal_state_from_remote(action.new_parent_id)
        if not parent_pair:
            log.info(
                "Move of %s lands under unsynced parent %s; requesting full scan",
                action.node_id,
                action.new_parent_id,
            )
            self.needs_full_scan = True
            return

        try:
            node = self.remote.get_node(action.node_id, include=["path"])
        except Exception:
            log.debug("Moved node %s not found; treating as delete", action.node_id)
            self._apply_delete(action)
            return

        if not self.remote.is_syncable_node(node):
            log.debug(
                "Skipping content-less moved node %s (%s)",
                action.node_id,
                node.node_type,
            )
            return

        info = self.remote._node_to_remote_file_info(node)
        new_remote_parent_path = (
            parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
        )

        for pair in existing:
            if pair.pair_state in (
                "locally_created",
                "locally_modified",
                "conflicted",
            ):
                log.debug(
                    "Skip remote move of %r: pair is %r",
                    pair.local_name,
                    pair.pair_state,
                )
                continue
            # Re-parent the remote side (``remote_parent_ref`` now points at the
            # new parent) then flag ``remotely_modified``. ``versioned=False``
            # keeps the row version stable so ``force_remote``'s optimistic lock
            # still matches. The processor's ``_is_remote_move`` then sees the
            # local parent differ from the remote parent and relocates.
            self.dao.update_remote_state(
                pair,
                info,
                remote_parent_path=new_remote_parent_path,
                versioned=False,
            )
            self.dao.force_remote(pair)
            log.info("Applying remote move of %r (delta)", pair.local_path)

    def _apply_upsert(self, action: ChangeAction, /) -> None:
        """Create/update/rename/move: re-fetch the node and reconcile its pair."""
        remote = self.remote
        try:
            node = remote.get_node(action.node_id, include=["path"])
        except Exception:
            # The node is gone by the time we look — treat as a deletion.
            log.debug("Node %s not found on upsert; treating as delete", action.node_id)
            self._apply_delete(action)
            return

        info = remote._node_to_remote_file_info(node)

        # Skip Alfresco metadata records (e.g. dl:issue dataList items) that
        # report isFile=True but have no content stream — downloading them
        # yields HTTP 404. Mirrors the full scan. See ``is_syncable_node``.
        if not remote.is_syncable_node(node):
            log.debug(
                "Skipping content-less node %s (%s)",
                action.node_id,
                node.node_type,
            )
            return

        from nxdrive.alfresco.sync_filters import is_top_folder_excluded

        if is_top_folder_excluded(info.path) or self.dao.is_filter(info.path):
            log.debug("Skipping filtered/system node %r", info.path)
            return

        existing = self.dao.get_states_from_remote(action.node_id)
        if existing:
            # Same-parent update (content/metadata) or rename: the node keeps
            # its stored parent path (moves are handled earlier via full scan).
            for pair in existing:
                self.watcher._apply_remote_update(pair, info, pair.remote_parent_path)
            return

        # New node: needs its parent pair to compute local placement.
        parent_pair = self.dao.get_normal_state_from_remote(action.new_parent_id)
        if not parent_pair:
            log.info(
                "Parent %s of new node %s not yet synced; requesting full scan",
                action.new_parent_id,
                action.node_id,
            )
            self.needs_full_scan = True
            return

        remote_parent_path = (
            parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
        )
        local_path = parent_pair.local_path / info.name
        self.watcher._match_or_create_child(
            info, local_path, parent_pair.local_path, remote_parent_path
        )
