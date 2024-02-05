import platform
from unittest.mock import Mock

from nxdrive import fatal_error


def test_check_os_version(monkeypatch):
    """Check the OS version compatibility for Nuxeo Drive"""
    assert fatal_error.check_os_version()

    # Test for lower version of MacOS. It will pop-up a Fatal error screen
    def mac_ver():
        return ["10.2.1"]

    monkeypatch.setattr(platform, "mac_ver", mac_ver)

    fatal_error.fatal_error_mac = Mock()
    assert not fatal_error.check_os_version()
