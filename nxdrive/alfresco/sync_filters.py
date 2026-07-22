"""
Top-level path filtering for the Alfresco sync scope.

Certain Alfresco system folders (``/Data Dictionary``, ``/Guest Home``,
``/IMAP Home``, ``/IMAP Attachments``, ``/Sites/rm``) must never be
synchronised to end-user machines by default:

* ``/Data Dictionary`` — administrative content / client update payloads.
* ``/Guest Home`` — guest-user landing folder.
* ``/IMAP Home`` and ``/IMAP Attachments`` — internal storage for the
  Alfresco IMAP subsystem.
* ``/Sites/rm`` — Records Management site (compliance / legal-hold rules
  forbid pulling these documents outside the server).

This mirrors the behaviour of the legacy Alfresco Desktop Sync client
(``alfresco-desktop-sync-master/SyncCoreLib/source/CMISAPI.cpp``), which
also hard-excludes those five locations.

Two optional configuration keys let administrators override the defaults
from ``config.ini`` (neither is present by default):

* ``alfresco_force_sync_top_folders`` — comma-separated paths from the
  hard-coded exclusion list that should be re-enabled.
* ``alfresco_excluded_top_folders`` — comma-separated *additional* paths
  the administrator wants to exclude on top of the hard-coded list.

Runtime rule for a path *P*:

    Skip *P* if:
        (*P* is under ``HARDCODED_EXCLUDED_TOP_FOLDERS``
         **and** *P* is **not** in ``alfresco_force_sync_top_folders``)
        **or** *P* is under ``alfresco_excluded_top_folders``.

    Otherwise sync *P*.

Precedence: if a path appears in both override lists, the exclusion
wins (safer default — the administrator explicitly said "don't sync").
"""

from typing import Iterable, Tuple

from nxdrive.drive.options import Options

__all__ = (
    "HARDCODED_EXCLUDED_TOP_FOLDERS",
    "is_top_folder_excluded",
)


#: Hard-coded system folders that are excluded from Alfresco sync by
#: default.  Paths are stored without a trailing slash and are matched
#: as prefixes (so a listed folder covers all its descendants).
HARDCODED_EXCLUDED_TOP_FOLDERS: Tuple[str, ...] = (
    "/Data Dictionary",
    "/Guest Home",
    "/IMAP Home",
    "/IMAP Attachments",
    "/Sites/rm",
)


def _parse_paths(value: str) -> Tuple[str, ...]:
    """Split a comma-separated ``config.ini`` value into a tuple of
    normalised paths.  Empty entries and surrounding whitespace are
    stripped; trailing slashes are removed so prefix matching is stable.
    """
    if not value:
        return ()
    return tuple(
        entry.strip().rstrip("/") for entry in value.split(",") if entry.strip()
    )


def _covered_by(path: str, prefixes: Iterable[str]) -> bool:
    """Return ``True`` if ``path`` equals or is a descendant of any
    prefix in ``prefixes``.
    """
    if not path:
        return False
    normalised = path.rstrip("/")
    for prefix in prefixes:
        if not prefix:
            continue
        if normalised == prefix or normalised.startswith(prefix + "/"):
            return True
    return False


def is_top_folder_excluded(path: str, /) -> bool:
    """Return ``True`` when *path* should be excluded from Alfresco sync
    based on the hard-coded exclusion list and the admin overrides in
    ``config.ini`` (``alfresco_force_sync_top_folders`` and
    ``alfresco_excluded_top_folders``).
    """
    if not path:
        return False

    force_sync = _parse_paths(Options.alfresco_force_sync_top_folders or "")
    extra_excluded = _parse_paths(Options.alfresco_excluded_top_folders or "")

    # Extra admin-defined exclusions always win.
    if _covered_by(path, extra_excluded):
        return True

    # Hard-coded exclusions apply unless the admin re-enabled them.
    if _covered_by(path, HARDCODED_EXCLUDED_TOP_FOLDERS):
        return not _covered_by(path, force_sync)

    return False
