# coding: utf-8
import re
from distutils.version import LooseVersion
from logging import getLogger
from typing import Any, Dict, Optional, Tuple

from .constants import (
    UPDATE_STATUS_DOWNGRADE_NEEDED,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_UP_TO_DATE,
)
from ..utils import version_le, version_lt

__all__ = ("get_update_status",)

log = getLogger(__name__)

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
    version_regex = r"^\d+(\.\d+)+(-HF\d+|)(-SNAPSHOT|)$"
    if not server_ver or not re.match(version_regex, server_ver, re.I):
        log.debug("No bound account, skipping the update check.")
        return "", {}

    # Remove HF and SNAPSHOT
    base_server_ver = server_ver.split("-")[0]

    # Skip not revelant release type
    versions = {
        version: info
        for version, info in versions.items()
        if info.get("type", "").lower() in (nature, "release")
    }

    if not versions:
        log.debug("No version found in that channel.")
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

        if any(
            [
                not ver_min,
                version_lt(server_ver, ver_min),
                ver_max and version_lt(ver_max, server_ver),
            ]
        ):
            continue

        candidates[version] = info

    if not candidates:  # ¯\_(ツ)_/¯
        log.debug("No version found for that server version.")
        return "", {}

    highest = str(max(map(LooseVersion, candidates.keys())))
    return highest, candidates[highest]  # ᕦ(ò_óˇ)ᕤ


def get_update_status(
    current_version: str,
    versions: Versions,
    nature: str,
    server_version: Optional[str],
    has_browser_login: bool,
) -> Tuple[str, str]:
    """Given a Drive version, determine the definitive status of the application."""

    if current_version not in versions:
        log.debug(
            "Unknown version: this is the case when the current packaged application"
            " has a version unknown on the server, typically the development one."
            " Ignoring updates."
        )
        return "", ""

    # Find the latest available version
    latest, info = get_latest_compatible_version(
        versions, nature, server_version, has_browser_login
    )

    if not latest:
        status = "", ""
    elif current_version == latest:
        status = UPDATE_STATUS_UP_TO_DATE, ""
    elif not version_le(latest, current_version):
        status = UPDATE_STATUS_UPDATE_AVAILABLE, latest
    else:
        status = UPDATE_STATUS_DOWNGRADE_NEEDED, latest

    return status
