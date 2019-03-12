# coding: utf-8
import re
from distutils.version import LooseVersion
from logging import getLogger
from typing import Any, Dict, Optional, Tuple

from .constants import (
    UPDATE_STATUS_INCOMPATIBLE_SERVER,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_UP_TO_DATE,
    UPDATE_STATUS_WRONG_CHANNEL,
    Login,
)
from ..utils import version_le, version_lt

__all__ = ("get_update_status",)

log = getLogger(__name__)

Version = Dict[str, Any]
Versions = Dict[str, Version]


def is_version_compatible(
    version_id: str, version: Version, server: str, has_browser_login: bool
) -> bool:
    """
    Check Drive <-> server version compatibility.

    Try first the min_all and max_all keys that contain all server versions.
    Fallback on min and max keys that contain only one server version:
        the oldest supported.
    """
    if not has_browser_login and not version_lt(version_id, "4"):
        return False

    ver_min = (version.get("min_all", {}).get(server) or version.get("min", "")).upper()
    if not ver_min or version_lt(server, ver_min):
        return False

    ver_max = (version.get("max_all", {}).get(server) or version.get("max", "")).upper()

    if ver_max and version_lt(ver_max, server):
        return False

    return True


def get_compatible_versions(
    versions: Versions, server_ver: Optional[str], has_browser_login: bool
) -> Versions:
    """
    Find all Drive versions compatible with the current server instance.
    """

    # If no server_version, then we cannot know in advance if Drive
    # will be compatible with a higher version of the server.
    # This is the case when there is no bound account.
    version_regex = r"^\d+(\.\d+)+(-HF\d+|)(-SNAPSHOT|)(-I.*|)$"
    if not server_ver or not re.match(version_regex, server_ver, re.I):
        log.info("No bound account, skipping the update check.")
        return {}

    # Remove HF and SNAPSHOT
    base_server_ver = server_ver.split("-")[0]

    # Filter version candidates
    candidates = {
        version: info
        for version, info in versions.items()
        if is_version_compatible(version, info, base_server_ver, has_browser_login)
    }

    if not candidates:  # ¯\_(ツ)_/¯
        log.info("No version found for that server version.")

    return candidates


def get_latest_version(versions: Versions, nature: str) -> str:
    """ Get the most recent version of a given channel. """
    versions_list = [
        version
        for version, info in versions.items()
        if info.get("type", "").lower() in (nature, "release")
    ]

    if not versions_list:
        log.debug(f"No version found in {nature} channel.")
        return ""

    highest = str(max(map(LooseVersion, versions_list)))
    return highest  # ᕦ(ò_óˇ)ᕤ


def get_update_status(
    current_version: str,
    versions: Versions,
    nature: str,
    server_version: Optional[str],
    login_type: Login,
) -> Tuple[str, str]:
    """Given a Drive version, determine the definitive status of the application."""

    if current_version not in versions:
        log.info(
            "Unknown version: this is the case when the current packaged application "
            "has a version unknown on the server, typically the development one. "
            "Ignoring updates."
        )
        return "", ""

    has_browser_login = Login.OLD not in login_type
    if Login.UNKNOWN in login_type and has_browser_login:
        log.info(
            "Unable to retrieve server login compatibility info. Ignoring updates."
        )
        return "", ""

    # Find the latest available version
    versions = get_compatible_versions(versions, server_version, has_browser_login)
    latest = get_latest_version(versions, nature)

    if not latest:
        status = "", ""
    elif current_version == latest:
        status = UPDATE_STATUS_UP_TO_DATE, ""
    elif not version_le(latest, current_version):
        status = UPDATE_STATUS_UPDATE_AVAILABLE, latest
    elif current_version in versions.keys():
        status = UPDATE_STATUS_WRONG_CHANNEL, latest
    else:
        status = UPDATE_STATUS_INCOMPATIBLE_SERVER, latest

    return status
