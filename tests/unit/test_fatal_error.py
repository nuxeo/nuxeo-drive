import platform
from unittest.mock import Mock, patch

from nxdrive import fatal_error
from nxdrive.constants import MAC

from ..markers import linux_only, mac_only, windows_only


def test_check_os_version(monkeypatch):
    """Check the OS version compatibility for Nuxeo Drive"""
    assert fatal_error.check_os_version()

    if MAC:
        # Test for lower version of MacOS. It will pop-up a Fatal error screen
        def mac_ver():
            return ["10.2.1"]

        monkeypatch.setattr(platform, "mac_ver", mac_ver)

        fatal_error.fatal_error_mac = Mock()
        assert not fatal_error.check_os_version()


@patch("nxdrive.fatal_error.fatal_error_qt")
@patch("traceback.format_exception")
@patch("sys.exc_info")
def test_show_critical_error(mock_exc_info, mock_traceback, mock_fatal_error_qt):
    mock_exc_info.return_value = "dummy_exc_info"
    mock_traceback.return_value = ["dummy_exception1", "dummy_exception2"]
    assert fatal_error.show_critical_error() is None


@windows_only
@patch("nxdrive.fatal_error.fatal_error_win")
@patch("nxdrive.fatal_error.fatal_error_qt")
@patch("traceback.format_exception")
@patch("sys.exc_info")
def test_show_critical_error_windows(
    mock_exc_info, mock_traceback, mock_fatal_error_qt, mock_fatal_error_win
):
    mock_exc_info.return_value = "dummy_exc_info"
    mock_traceback.return_value = ["dummy_exception1", "dummy_exception2"]
    mock_fatal_error_qt.side_effect = Exception("Dummy Windows Exception")
    assert fatal_error.show_critical_error() is None


@mac_only
@patch("nxdrive.fatal_error.fatal_error_mac")
@patch("nxdrive.fatal_error.fatal_error_qt")
@patch("traceback.format_exception")
@patch("sys.exc_info")
def test_show_critical_error_mac(
    mock_exc_info, mock_traceback, mock_fatal_error_qt, mock_fatal_error_mac
):
    mock_exc_info.return_value = "dummy_exc_info"
    mock_traceback.return_value = ["dummy_exception1", "dummy_exception2"]
    mock_fatal_error_qt.side_effect = Exception("Dummy MacOS Exception")
    assert fatal_error.show_critical_error() is None


@linux_only
@patch("nxdrive.fatal_error.fatal_error_qt")
@patch("traceback.format_exception")
@patch("sys.exc_info")
def test_show_critical_error_linux(mock_exc_info, mock_traceback, mock_fatal_error_qt):
    mock_exc_info.return_value = "dummy_exc_info"
    mock_traceback.return_value = ["dummy_exception1", "dummy_exception2"]
    mock_fatal_error_qt.side_effect = Exception("Dummy Linux Exception")
    assert fatal_error.show_critical_error() is None
