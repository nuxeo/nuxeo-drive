#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""Server folders whose content the remote watcher still has to fetch.

Two actions bring back content the change feed will never report, because it
already existed on the server: lifting a filter (``remove_filter``) and
cancelling a local deletion (``rollback_delete``). Both first drop the local
rows, then hand the node ids to the remote watcher.

The ids are saved here *before* the rows are dropped, and removed only once
fetched, so a restart in between does not leave those folders empty for good.
The engine (GUI thread) and the watcher thread both write this value, hence the
read-modify-write under the DAO lock.
"""

import json
from logging import getLogger
from typing import TYPE_CHECKING, Iterable, Set, Tuple

if TYPE_CHECKING:
    from nxdrive.drive.dao.engine import EngineDAO

__all__ = (
    "CONF_PENDING_UNFILTERED",
    "add_pending_unfiltered",
    "clear_pending_unfiltered",
    "load_pending_unfiltered",
    "remove_pending_unfiltered",
)

log = getLogger(__name__)

#: DAO ``Config`` key: ``{"nodes": [...], "full_scan": bool}``.
CONF_PENDING_UNFILTERED = "device_sync_pending_unfiltered"


def load_pending_unfiltered(dao: "EngineDAO", /) -> Tuple[Set[str], bool]:
    """Return the node ids still to fetch, and whether a full re-seed is owed."""
    raw = dao.get_config(CONF_PENDING_UNFILTERED)
    if not raw:
        return set(), False
    try:
        data = json.loads(raw)
        return {str(uid) for uid in data["nodes"]}, bool(data["full_scan"])
    except (KeyError, TypeError, ValueError):
        log.warning(f"Ignoring unreadable {CONF_PENDING_UNFILTERED!r}: {raw!r}")
        return set(), False


def _save(dao: "EngineDAO", nodes: Set[str], full_scan: bool, /) -> None:
    value = (
        json.dumps({"nodes": sorted(nodes), "full_scan": full_scan})
        if nodes or full_scan
        else None
    )
    dao.update_config(CONF_PENDING_UNFILTERED, value)


def add_pending_unfiltered(
    dao: "EngineDAO", node_ids: Iterable[str], /, *, full_scan: bool = False
) -> None:
    with dao.lock:
        nodes, owed = load_pending_unfiltered(dao)
        _save(dao, nodes | set(node_ids), owed or full_scan)


def remove_pending_unfiltered(dao: "EngineDAO", node_ids: Iterable[str], /) -> None:
    with dao.lock:
        nodes, owed = load_pending_unfiltered(dao)
        _save(dao, nodes - set(node_ids), owed)


def clear_pending_unfiltered(dao: "EngineDAO", /) -> None:
    dao.update_config(CONF_PENDING_UNFILTERED, None)
