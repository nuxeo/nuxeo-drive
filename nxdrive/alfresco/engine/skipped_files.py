#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""Documents whose change the server refused for lack of permission.

A 403 (or a permission read beforehand) means the change cannot go through as
long as the user's rights on the server stay the same. Retrying it every 60
seconds only floods the log, so the processor lists the document in the
Errors with a clear reason and records it here; the remote watcher retries
these documents every :data:`SKIPPED_FILE_RETRY_INTERVAL` seconds, in case
the rights were granted meanwhile.

The processor threads add to this list while the watcher thread drains it,
hence the read-modify-write under the DAO lock.
"""

import json
from logging import getLogger
from typing import TYPE_CHECKING, Iterable, Set

if TYPE_CHECKING:
    from nxdrive.drive.dao.engine import EngineDAO

__all__ = (
    "CONF_SKIPPED_FILES",
    "NO_PERMISSION_ERROR",
    "SKIPPED_FILE_RETRY_INTERVAL",
    "add_skipped_file",
    "load_skipped_files",
    "remove_skipped_files",
)

log = getLogger(__name__)

#: DAO ``Config`` key holding the ``States`` row ids of skipped files (JSON).
CONF_SKIPPED_FILES = "device_sync_skipped_files"

#: ``last_error`` of a skipped file. Rendered by ``FileCard.qml`` as
#: ``ERROR_REASON_<code>``.
NO_PERMISSION_ERROR = "NO_PERMISSION"

#: Minimum delay between two retries of the skipped files.
SKIPPED_FILE_RETRY_INTERVAL = 600.0


def load_skipped_files(dao: "EngineDAO", /) -> Set[int]:
    raw = dao.get_config(CONF_SKIPPED_FILES)
    if not raw:
        return set()
    try:
        ids = json.loads(raw)
        if not isinstance(ids, list):
            raise TypeError(f"expected a list, got {type(ids).__name__}")
        return {int(row_id) for row_id in ids}
    except (TypeError, ValueError):
        log.warning(f"Ignoring unreadable {CONF_SKIPPED_FILES!r}: {raw!r}")
        return set()


def _save(dao: "EngineDAO", ids: Set[int], /) -> None:
    dao.update_config(CONF_SKIPPED_FILES, json.dumps(sorted(ids)) if ids else None)


def add_skipped_file(dao: "EngineDAO", row_id: int, /) -> None:
    with dao.lock:
        ids = load_skipped_files(dao)
        if row_id not in ids:
            _save(dao, ids | {row_id})


def remove_skipped_files(dao: "EngineDAO", row_ids: Iterable[int], /) -> None:
    with dao.lock:
        ids = load_skipped_files(dao)
        remaining = ids - set(row_ids)
        if remaining != ids:
            _save(dao, remaining)
