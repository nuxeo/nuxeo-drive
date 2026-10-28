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

Every request gets a new generation number. The watcher notes it before a
fetch and removes the request only if it is unchanged afterwards, so a newer
request for the same folder, saved while the fetch was running, is kept.
The engine (GUI thread) and the watcher thread both write this value, hence the
read-modify-write under the DAO lock.
"""

import json
from logging import getLogger
from typing import TYPE_CHECKING, Dict, Iterable, Mapping, NamedTuple, Set, Tuple

if TYPE_CHECKING:
    from nxdrive.drive.dao.engine import EngineDAO

__all__ = (
    "CONF_PENDING_UNFILTERED",
    "Pending",
    "add_pending_unfiltered",
    "load_pending_unfiltered",
    "remove_pending_unfiltered",
    "snapshot_pending_unfiltered",
)

log = getLogger(__name__)

#: DAO ``Config`` key: ``{"nodes": {id: generation}, "full_scan": generation,
#: "seq": last generation}``. A ``full_scan`` of 0 means none is owed.
CONF_PENDING_UNFILTERED = "device_sync_pending_unfiltered"


class Pending(NamedTuple):
    """The saved requests, each with the generation that saved it."""

    nodes: Dict[str, int]
    full_scan: int
    seq: int


def snapshot_pending_unfiltered(dao: "EngineDAO", /) -> Pending:
    raw = dao.get_config(CONF_PENDING_UNFILTERED)
    if not raw:
        return Pending({}, 0, 0)
    try:
        data = json.loads(raw)
        nodes = data["nodes"]
        if isinstance(nodes, list):
            # Written before generations existed.
            nodes = dict.fromkeys(nodes, 0)
        return Pending(
            {str(uid): int(gen) for uid, gen in nodes.items()},
            int(data["full_scan"]),
            int(data.get("seq", 0)),
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        log.warning(f"Ignoring unreadable {CONF_PENDING_UNFILTERED!r}: {raw!r}")
        return Pending({}, 0, 0)


def load_pending_unfiltered(dao: "EngineDAO", /) -> Tuple[Set[str], bool]:
    """Return the node ids still to fetch, and whether a full re-seed is owed."""
    pending = snapshot_pending_unfiltered(dao)
    return set(pending.nodes), bool(pending.full_scan)


def _save(dao: "EngineDAO", pending: Pending, /) -> None:
    value = None
    if pending.nodes or pending.full_scan:
        value = json.dumps(
            {
                "nodes": dict(sorted(pending.nodes.items())),
                "full_scan": pending.full_scan,
                "seq": pending.seq,
            }
        )
    dao.update_config(CONF_PENDING_UNFILTERED, value)


def add_pending_unfiltered(
    dao: "EngineDAO", node_ids: Iterable[str], /, *, full_scan: bool = False
) -> int:
    """Save a request and return its generation."""
    with dao.lock:
        current = snapshot_pending_unfiltered(dao)
        seq = current.seq + 1
        nodes = {**current.nodes, **{str(uid): seq for uid in node_ids}}
        _save(dao, Pending(nodes, seq if full_scan else current.full_scan, seq))
        return seq


def remove_pending_unfiltered(
    dao: "EngineDAO",
    done: Mapping[str, int],
    /,
    *,
    full_scan: int = 0,
) -> None:
    """Drop the requests that were handled, if nothing newer replaced them.

    *done* maps each fetched node id to the generation noted before fetching;
    *full_scan* is the generation of a handled full re-seed request.
    """
    with dao.lock:
        current = snapshot_pending_unfiltered(dao)
        nodes = {uid: gen for uid, gen in current.nodes.items() if done.get(uid) != gen}
        owed = 0 if full_scan and current.full_scan == full_scan else current.full_scan
        _save(dao, Pending(nodes, owed, current.seq))
