import platform
import re
from functools import lru_cache
from typing import Tuple

from .. import __version__
from ..constants import APP_NAME, MAC, WINDOWS


@lru_cache(maxsize=1)
def _get_current_os_details() -> Tuple[str, str, str]:
    """Get OS details: name, full version, simplified version [x.y].

    Examples:
        - ("macOS", "10.15.3", "10.15")
        - ("Windows", "10.0.19041", "10.0")
        - ("Ubuntu", "18.04.5", "18.04")
    """
    if MAC:
        name = "macOS"
        mac_ver = platform.mac_ver()[0]
        if re.fullmatch(r"\d{2}\.\d{1,2}\.\d{1,2}$", mac_ver):
            ver_full = mac_ver  # 10.15.3
        else:
            ver_full = f"{mac_ver}.0"
    elif WINDOWS:
        name = "Windows"
        ver_full = platform.win32_ver()[1]  # 10.0.19041
    else:
        import distro

        name = distro.name()  # Ubuntu
        ver_full = distro.version(best=True)  # 18.04.5

    ver_simplified = ".".join(ver_full.split(".")[:2])  # 10.15.3 -> 10.15
    return name, ver_full, ver_simplified


@lru_cache(maxsize=2)
def current_os(*, full: bool = False) -> str:
    """Return a well formatted OS name and version.
    If *full* is true, the full version will be used instead of the x.y simplified one.
    """
    name, version_full, version_simplified = _get_current_os_details()
    return f"{name} {version_full}" if full else f"{name} {version_simplified}"


@lru_cache(maxsize=1)
def user_agent() -> str:
    """Minimal user agent for all HTTP requests.
    Example: Nuxeo-Drive/5.1.0 (macOS 10.15)
    """
    return f"{APP_NAME.replace(' ', '-')}/{__version__} ({current_os()})"
