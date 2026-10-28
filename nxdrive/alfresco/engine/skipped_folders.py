#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""Folders the remote watcher could not read, and the local changes held under them.

A folder whose content cannot be listed is skipped so that it stops blocking
the first pass for the whole tree (see ``AlfrescoRemoteWatcher``). Without a
listing, nothing can be checked before an upload, and Alfresco's upload
silently replaces a same-named document. So no local change is sent into a
skipped folder: the processor holds it back (``HELD_UNDER_SKIPPED_FOLDER``),
and the remote watcher releases it once the folder can be read again.

Both sides share the database as the source of truth, so the state survives
restarts and the processor threads never touch the watcher's memory.
"""

import json
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, List, Optional, Set

if TYPE_CHECKING:
    from nxdrive.drive.dao.engine import EngineDAO
    from nxdrive.drive.objects import DocPair

__all__ = (
    "CONF_SKIPPED_FOLDERS",
    "HELD_UNDER_SKIPPED_FOLDER",
    "LISTING_FAILED_ERROR",
    "find_blocking_skipped_folder",
    "find_skipped_ancestor",
    "is_under",
    "load_skipped_folders",
    "save_skipped_folders",
    "skipped_folder_pairs",
    "skipped_folder_rows",
)

log = getLogger(__name__)

#: DAO ``Config`` key holding the node ids of skipped folders (JSON list).
CONF_SKIPPED_FOLDERS = "device_sync_skipped_folders"

#: ``last_error`` written on a folder the seed had to skip.
#: Rendered by ``FileCard.qml`` as ``ERROR_REASON_<code>``.
LISTING_FAILED_ERROR = "DEVICE_SYNC_LISTING_FAILED"

#: ``last_error`` written on a local change held back because it sits under a
#: skipped folder. Rendered as ``ERROR_REASON_<code>`` too.
HELD_UNDER_SKIPPED_FOLDER = "DEVICE_SYNC_FOLDER_UNREADABLE"

#: Rows on their way out, which no longer describe a synced folder.
_GONE_STATES = ("deleted", "remotely_deleted", "parent_remotely_deleted")


def load_skipped_folders(dao: "EngineDAO", /) -> Set[str]:
    raw = dao.get_config(CONF_SKIPPED_FOLDERS)
    if not raw:
        return set()
    try:
        return {str(uid) for uid in json.loads(raw)}
    except (TypeError, ValueError):
        log.warning(f"Ignoring unreadable {CONF_SKIPPED_FOLDERS!r}: {raw!r}")
        return set()


def save_skipped_folders(dao: "EngineDAO", uids: Iterable[str], /) -> None:
    uids = sorted(uids)
    dao.update_config(CONF_SKIPPED_FOLDERS, json.dumps(uids) if uids else None)


def skipped_folder_rows(dao: "EngineDAO", uid: str, /) -> List["DocPair"]:
    """Synced folder rows for the skipped node *uid*.

    A node id can have several ``States`` rows (``UNIQUE`` is on the id
    *and* the local path), and the first one is not necessarily the folder.
    Only folder rows that are not being deleted are kept; the caller decides
    what to do when more than one is left.
    """
    return [
        row
        for row in dao.get_states_from_remote(uid)
        if row.folderish
        and row.remote_state != "deleted"
        and row.pair_state not in _GONE_STATES
    ]


def skipped_folder_pairs(
    dao: "EngineDAO", /, *, uids: Optional[Iterable[str]] = None
) -> List["DocPair"]:
    """Rows of the skipped folders that are still synced.

    Every candidate row is returned, so a node id matching several rows holds
    local changes under each of them rather than under a guessed one.
    """
    if uids is None:
        uids = load_skipped_folders(dao)
    return [row for uid in uids for row in skipped_folder_rows(dao, uid)]


def is_under(path: Path, folder: Path, /) -> bool:
    return path == folder or folder in path.parents


def find_skipped_ancestor(
    dao: "EngineDAO", path: Path, /, *, folders: Optional[List["DocPair"]] = None
) -> Optional["DocPair"]:
    """Return the skipped folder *path* is in (or is), if any."""
    if folders is None:
        folders = skipped_folder_pairs(dao)
    for folder in folders:
        if is_under(path, folder.local_path):
            return folder
    return None


def find_blocking_skipped_folder(
    dao: "EngineDAO", pair: "DocPair", /, *, folders: Optional[List["DocPair"]] = None
) -> Optional["DocPair"]:
    """Return the skipped folder that forbids sending *pair*'s local change.

    That is the skipped folder *pair* is in (or is). A folder deletion is also
    held when a skipped folder sits *under* it: deleting the parent on the
    server would delete the content Drive could not read along with it.
    """
    if folders is None:
        folders = skipped_folder_pairs(dao)
    found = find_skipped_ancestor(dao, pair.local_path, folders=folders)
    if found or not (pair.folderish and pair.pair_state == "locally_deleted"):
        return found
    for folder in folders:
        if is_under(folder.local_path, pair.local_path):
            return folder
    return None
