import re
from distutils.version import LooseVersion
from logging import getLogger
from typing import Any, Dict, Optional, Tuple

from nuxeo.utils import version_le, version_lt

from ..feature import Feature
from ..options import Options
from .constants import (
    UPDATE_STATUS_INCOMPATIBLE_SERVER,
    UPDATE_STATUS_UP_TO_DATE,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_WRONG_CHANNEL,
    AutoUpdateState,
    Login,
)

__all__ = ("get_update_status", "auto_updates_state")

log = getLogger(__name__)

Version = Dict[str, Any]
Versions = Dict[str, Version]


def auto_updates_state() -> AutoUpdateState:
    """Check the auto-update state as it may evolve over the application runtime."""
    if not (Feature.auto_update and Options.is_frozen):
        # Cannot update if the feature is completely disabled
        # Cannot update non-packaged versions
        return AutoUpdateState.DISABLED

    if Options.update_check_delay > 0:
        # Auto-updates are enabled
        return AutoUpdateState.ENABLED

    if Options.channel == "centralized" and Options.client_version:
        # We are in the scenario where:
        #   - update_check_delay is set to 0
        #   - channel is set to centralized
        #   - client_version is set
        # We still want to allow updates in that case. See NXDRIVE-2047.
        return AutoUpdateState.FORCED

    return AutoUpdateState.DISABLED


def is_version_compatible(
    version_id: str, version: Version, server: str, has_browser_login: bool, /
) -> bool:
    """
    Check Drive <-> server version compatibility.

    Try first the min_all and max_all keys that contain all server versions.
    Fallback on min and max keys that contain only one server version:
    the oldest supported.
    """
    if not (has_browser_login or version_lt(version_id, "4")):
        return False

    # Remove HF and SNAPSHOT
    base_server = server.split("-")[0]

    ver_min = (
        version.get("min_all", {}).get(base_server) or version.get("min", "")
    ).upper()
    if not ver_min or version_lt(server, ver_min):
        return False

    ver_max = (
        version.get("max_all", {}).get(base_server) or version.get("max", "")
    ).upper()

    return not (ver_max and version_lt(ver_max, server))


def get_compatible_versions(
    versions: Versions, server_ver: Optional[str], has_browser_login: bool, /
) -> Versions:
    """
    Find all Drive versions compatible with the current server instance.
    """

    # If no server_ver, then we cannot know in advance if Drive
    # will be compatible with a higher version of the server.
    # This is the case when there is no bound account.
    version_regex = r"^\d+(\.\d+)+(-HF\d+|)(-SNAPSHOT|)(-I.*|)$"
    if not (server_ver and re.match(version_regex, server_ver, re.I)):
        log.info("No bound account, skipping the update check.")
        return {}

    # Filter version candidates
    candidates = {
        version: info
        for version, info in versions.items()
        if is_version_compatible(version, info, server_ver, has_browser_login)
    }

    if not candidates:  # ¯\_(ツ)_/¯
        log.info("No version found for that server version.")

    return candidates


def get_latest_version(versions: Versions, channel: str, /) -> str:
    """Get the most recent version of a given channel."""
    versions_list = [
        version
        for version, info in versions.items()
        if info.get("type", "").lower() in (channel, "release")
    ]

    if not versions_list:
        log.debug(f"No version found in {channel} channel.")
        return ""

    highest = str(max(map(LooseVersion, versions_list)))
    return highest  # ᕦ(ò_óˇ)ᕤ


def get_update_status(
    current_version: str,
    versions: Versions,
    channel: str,
    server_version: Optional[str],
    login_type: Login,
    /,
) -> Tuple[str, str]:
    """Given a Drive version, determine the definitive status of the application."""

    if not isinstance(versions, dict):
        log.warning(
            f"versions has invalid type: {type(versions).__name__}, dict required"
        )
        return "", ""

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

    # Filter versions based on their compatibility with the server
    versions = get_compatible_versions(versions, server_version, has_browser_login)

    # If the update channel is Centralized, we do not filter anything more
    # and just return the desired version.
    original_channel = channel
    latest = None
    if channel == "centralized":
        if Options.client_version:
            latest = Options.client_version
        else:
            log.debug(
                "Update channel is 'centralized' but no 'client_version' set."
                " Falling back to the 'release' channel."
            )
            channel = "release"

    if latest is None:
        # Find the latest available version
        latest = get_latest_version(versions, channel)

    # No version available
    if not latest:
        return "", ""

    # Up-to-date, the current version is already the latest one
    if current_version == latest:
        return UPDATE_STATUS_UP_TO_DATE, ""

    # A new version is available
    if not version_le(latest, current_version):
        return UPDATE_STATUS_UPDATE_AVAILABLE, latest

    # The current version came from another channel
    if current_version in versions.keys():
        # For the Centralized channel, this is not an issue as administrators must
        # have checked that the desired version is working fine whatever the channel
        if original_channel == "centralized" and Options.client_version:
            return UPDATE_STATUS_UPDATE_AVAILABLE, latest
        else:
            return UPDATE_STATUS_WRONG_CHANNEL, latest

    # The latest version is not compatible with the server
    return UPDATE_STATUS_INCOMPATIBLE_SERVER, latest
