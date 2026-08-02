"""Tests for nxdrive/drive/metrics/utils.py — OS detection branches."""

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _clear_lru_caches():
    """Clear lru_cache between tests so patched values take effect."""
    from nxdrive.drive.metrics.utils import _get_current_os_details, current_os, user_agent

    _get_current_os_details.cache_clear()
    current_os.cache_clear()
    user_agent.cache_clear()
    yield
    _get_current_os_details.cache_clear()
    current_os.cache_clear()
    user_agent.cache_clear()


# --------------------------------------------------------------------------
# Windows branch (lines 22, 25-26)
# --------------------------------------------------------------------------


def test_get_current_os_details_windows():
    """WINDOWS branch: uses platform.win32_ver()."""
    with patch("nxdrive.drive.metrics.utils.MAC", False), \
         patch("nxdrive.drive.metrics.utils.WINDOWS", True), \
         patch("platform.win32_ver", return_value=("10", "10.0.19041", "", "")):
        from nxdrive.drive.metrics.utils import _get_current_os_details

        name, ver_full, ver_simplified = _get_current_os_details()

    assert name == "Windows"
    assert ver_full == "10.0.19041"
    assert ver_simplified == "10.0"


# --------------------------------------------------------------------------
# Linux branch (lines 27, 29, 31-32)
# --------------------------------------------------------------------------


def test_get_current_os_details_linux():
    """Linux branch: imports distro and uses distro.name() / distro.version()."""
    import sys
    from nxdrive.drive.metrics.utils import _get_current_os_details

    mock_distro = MagicMock()
    mock_distro.name.return_value = "Ubuntu"
    mock_distro.version.return_value = "22.04.3"

    _get_current_os_details.cache_clear()
    sys.modules["distro"] = mock_distro
    try:
        with patch("nxdrive.drive.metrics.utils.MAC", False), \
             patch("nxdrive.drive.metrics.utils.WINDOWS", False):
            name, ver_full, ver_simplified = _get_current_os_details()
    finally:
        sys.modules.pop("distro", None)
        _get_current_os_details.cache_clear()

    assert name == "Ubuntu"
    assert ver_full == "22.04.3"
    assert ver_simplified == "22.04"


def test_get_current_os_details_linux_single_part_version():
    """Linux with a version that has fewer than 2 dots."""
    import sys
    from nxdrive.drive.metrics.utils import _get_current_os_details

    mock_distro = MagicMock()
    mock_distro.name.return_value = "Fedora"
    mock_distro.version.return_value = "39"

    import sys

    with patch("nxdrive.drive.metrics.utils.MAC", False), \
         patch("nxdrive.drive.metrics.utils.WINDOWS", False):
        sys.modules["distro"] = mock_distro
        try:
            from nxdrive.drive.metrics.utils import _get_current_os_details

            name, ver_full, ver_simplified = _get_current_os_details()
        finally:
            sys.modules.pop("distro", None)

    assert name == "Fedora"
    assert ver_full == "39"
    assert ver_simplified == "39"


# --------------------------------------------------------------------------
# current_os
# --------------------------------------------------------------------------


def test_current_os_full():
    """current_os(full=True) returns name + full version."""
    with patch("nxdrive.drive.metrics.utils._get_current_os_details",
               return_value=("Windows", "10.0.19041", "10.0")):
        from nxdrive.drive.metrics.utils import current_os

        result = current_os(full=True)

    assert result == "Windows 10.0.19041"


def test_current_os_simplified():
    """current_os(full=False) returns name + simplified version."""
    with patch("nxdrive.drive.metrics.utils._get_current_os_details",
               return_value=("Ubuntu", "22.04.3", "22.04")):
        from nxdrive.drive.metrics.utils import current_os

        result = current_os(full=False)

    assert result == "Ubuntu 22.04"


# --------------------------------------------------------------------------
# user_agent
# --------------------------------------------------------------------------


def test_user_agent():
    """user_agent() returns formatted string."""
    with patch("nxdrive.drive.metrics.utils.APP_NAME", "Nuxeo Drive"), \
         patch("nxdrive.drive.metrics.utils.APP_VERSION", "5.4.0"), \
         patch("nxdrive.drive.metrics.utils.current_os", return_value="macOS 14.5"):
        from nxdrive.drive.metrics.utils import user_agent

        result = user_agent()

    assert result == "Nuxeo-Drive/5.4.0 (macOS 14.5)"
