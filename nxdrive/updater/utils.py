# coding: utf-8
from typing import Any, Dict, Optional, Tuple

from .constants import (
    UPDATE_STATUS_DOWNGRADE_NEEDED,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_UP_TO_DATE,
)
from ..utils import version_le, version_lt

__all__ = ("get_update_status",)

Version = Dict[str, Any]
Versions = Dict[str, Version]


def get_latest_compatible_version(
    versions: Versions, nature: str, server_ver: Optional[str], has_browser_login: bool
) -> Tuple[str, Version]:
    """
    Find the latest version sorted by type and the current Nuxeo version.
    """

    # If no server_version, then we cannot know in advance if Drive
    # will be compatible with a higher version of the server.
    # This is the case when there is no bound account.
    if not server_ver:
        return "", {}

    # Remove HF and SNAPSHOT
    base_server_ver = server_ver.split("-")[0]

    # Skip not revelant release type
    versions = {
        version: info
        for version, info in versions.items()
        if info.get("type", "").lower() == nature
    }

    if not versions:
        return "", {}

    # Filter version candidates
    candidates = {}
    for version, info in versions.items():
        # Check for new login compatibility
        if not has_browser_login and not version_lt(version, "4"):
            continue

        # Try first the min_all and max_all keys that contain all server versions.
        # Fallback on min and max keys that contain only one server version: the oldest supported.
        ver_min = (
            info.get("min_all", {}).get(base_server_ver) or info.get("min", "")
        ).upper()
        ver_max = (
            info.get("max_all", {}).get(base_server_ver) or info.get("max", "")
        ).upper()

        if not ver_min or not ver_min.startswith(base_server_ver):
            continue

        # Min server version is required
        is_candidate = version_le(ver_min, server_ver)

        # Max server version is optional
        if ver_max and ver_max.startswith(base_server_ver):
            is_candidate &= version_le(server_ver, ver_max)

        if is_candidate:
            candidates[version] = info

    if not candidates:  # ¯\_(ツ)_/¯
        return "", {}

    highest = max(candidates.keys())
    return highest, candidates[highest]  # ᕦ(ò_óˇ)ᕤ


def get_update_status(
    current_version: str, versions: Versions, nature: str, server_version: Optional[str], has_browser_login: bool
) -> Tuple[str, Version]:
    """Given a Drive version, determine the definitive status of the application."""

    # Find the latest available version
    latest, info = get_latest_compatible_version(versions, nature, server_version, has_browser_login)

    if not latest:
        status = None, None
    elif current_version == latest:
        status = UPDATE_STATUS_UP_TO_DATE, None
    elif not version_le(latest, current_version):
        status = UPDATE_STATUS_UPDATE_AVAILABLE, latest
    else:
        status = UPDATE_STATUS_DOWNGRADE_NEEDED, latest

    return status
