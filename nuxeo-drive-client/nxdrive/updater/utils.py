# coding: utf-8
from logging import getLogger

from nxdrive.utils import version_between

log = getLogger(__name__)


def get_latest_compatible_version(versions, nature, server_ver):
    # type: (Dict, unicode, unicode) -> Tuple[unicode, Dict]
    """
    Find the latest version sorted by type and the current Nuxeo version.
    """

    default = ('', {})

    # Skip not revelant release type
    versions = {version: info for version, info in versions.items()
                if info.get('type', '').lower() == nature}

    if not versions:
        return default

    if not server_ver:
        # No engine found, just returns the latest version
        # (this allows to update Drive without any account)
        latest = max(versions.keys())
        info = versions.get(latest, {})
        log.debug('No bound engine: using version %r, info=%r', latest, info)
        return latest, info

    # Skip outbound versions
    for version, info in versions.items():
        server_ver_min = info.get('min', '0.0.0').upper()
        server_ver_max = info.get('max', '999.999.999').upper()
        if not version_between(server_ver_min, server_ver, server_ver_max):
            versions.pop(version)

    try:
        # Found a version candidate?
        latest = max(versions.keys())
    except ValueError:
        return default
    else:
        return latest, versions.get(latest, {})
