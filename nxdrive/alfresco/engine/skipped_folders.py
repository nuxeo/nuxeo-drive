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
    "find_skipped_ancestor",
    "is_under",
    "load_skipped_folders",
    "save_skipped_folders",
    "skipped_folder_pairs",
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


def skipped_folder_pairs(
    dao: "EngineDAO", /, *, uids: Optional[Iterable[str]] = None
) -> List["DocPair"]:
    """Rows of the skipped folders that are still synced."""
    if uids is None:
        uids = load_skipped_folders(dao)
    pairs = (dao.get_normal_state_from_remote(uid) for uid in uids)
    return [pair for pair in pairs if pair]


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
