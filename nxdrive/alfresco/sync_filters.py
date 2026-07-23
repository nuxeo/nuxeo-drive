"""
Top-level path filtering for the Alfresco sync scope.

Certain Alfresco system folders under ``/Company Home`` must never be
synchronised to end-user machines by default:

* ``/Company Home/Data Dictionary`` — administrative content /
  client update payloads.
* ``/Company Home/Guest Home`` — guest-user landing folder.
* ``/Company Home/IMAP Home`` and ``/Company Home/IMAP Attachments`` —
  internal storage for the Alfresco IMAP subsystem.
* ``/Company Home/Sites/rm`` — Records Management site (compliance /
  legal-hold rules forbid pulling these documents outside the server).

This mirrors the behaviour of the legacy Alfresco Desktop Sync client
(``alfresco-desktop-sync-master/SyncCoreLib/source/CMISAPI.cpp``), which
also hard-excludes those five locations.

Two optional configuration keys let administrators override the defaults
from ``config.ini`` (neither is present by default):

* ``alfresco_force_sync_top_folders`` — comma-separated paths from the
  hard-coded exclusion list that should be re-enabled.
* ``alfresco_excluded_top_folders`` — comma-separated *additional* paths
  the administrator wants to exclude on top of the hard-coded list.

Paths in both overrides may be written **with or without** the leading
``/Company Home`` segment — the matcher normalises both forms before
comparing.

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


#: Alfresco repository root under which every user-visible folder lives.
#: Node paths returned by the Alfresco REST API (``path.elements`` +
#: ``node.name``) are always rooted here — e.g. ``/Company Home/Sites``.
_ALFRESCO_ROOT: str = "/Company Home"


#: Hard-coded system folders that are excluded from Alfresco sync by
#: default.  Paths are stored without a trailing slash and are matched
#: as prefixes (so a listed folder covers all its descendants).  They
#: are stored in the fully-qualified form the Alfresco REST API returns
#: so the matcher is a plain string comparison at runtime.
HARDCODED_EXCLUDED_TOP_FOLDERS: Tuple[str, ...] = (
    f"{_ALFRESCO_ROOT}/Data Dictionary",
    f"{_ALFRESCO_ROOT}/Guest Home",
    f"{_ALFRESCO_ROOT}/IMAP Home",
    f"{_ALFRESCO_ROOT}/IMAP Attachments",
    f"{_ALFRESCO_ROOT}/Sites/rm",
)


def _normalise(path: str) -> str:
    """Strip the trailing slash and prepend the ``/Company Home`` root
    if the caller supplied the shorter admin-friendly form.
    """
    if not path:
        return ""
    path = path.strip().rstrip("/")
    if not path:
        return ""
    if not path.startswith("/"):
        path = "/" + path
    if path == _ALFRESCO_ROOT or path.startswith(_ALFRESCO_ROOT + "/"):
        return path
    return _ALFRESCO_ROOT + path


def _parse_paths(value: str) -> Tuple[str, ...]:
    """Split a comma-separated ``config.ini`` value into a tuple of
    normalised, fully-qualified paths.  Empty entries and surrounding
    whitespace are stripped.
    """
    if not value:
        return ()
    return tuple(_normalise(entry) for entry in value.split(",") if entry.strip())


def _covered_by(path: str, prefixes: Iterable[str]) -> bool:
    """Return ``True`` if ``path`` equals or is a descendant of any
    prefix in ``prefixes``.

    Comparison is **case-insensitive** because Alfresco deployments
    routinely differ on the casing of the system-folder names — e.g.
    ``/Company Home/IMAP Attachments`` vs ``/Company Home/Imap
    Attachments``.  Alfresco itself treats sibling names as
    case-sensitive at the storage layer, but the exclusion list
    should match either spelling so admins do not have to hand-tune
    it per server.
    """
    if not path:
        return False
    normalised = path.rstrip("/").casefold()
    for prefix in prefixes:
        if not prefix:
            continue
        lowered = prefix.casefold()
        if normalised == lowered or normalised.startswith(lowered + "/"):
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
