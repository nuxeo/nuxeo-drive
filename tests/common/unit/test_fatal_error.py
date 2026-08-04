import platform
from unittest.mock import Mock, patch

import pytest

from nxdrive import fatal_error
from nxdrive.drive.constants import MAC
from nxdrive.drive.state import State

from ...markers import linux_only, mac_only, windows_only


@pytest.fixture(autouse=True)
def restore_application_state():
    """Prevent crash-reporting tests from leaking process-wide state."""
    saved_state = vars(State).copy()
    yield
    vars(State).clear()
    vars(State).update(saved_state)


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


@patch("nxdrive.drive.fatal_error.fatal_error_qt")
@patch("traceback.format_exception")
@patch("sys.exc_info")
def test_show_critical_error(mock_exc_info, mock_traceback, mock_fatal_error_qt):
    mock_exc_info.return_value = "dummy_exc_info"
    mock_traceback.return_value = ["dummy_exception1", "dummy_exception2"]
    assert fatal_error.show_critical_error() is None


@windows_only
@patch("nxdrive.drive.fatal_error.fatal_error_win")
@patch("nxdrive.drive.fatal_error.fatal_error_qt")
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
@patch("nxdrive.drive.fatal_error.fatal_error_mac")
@patch("nxdrive.drive.fatal_error.fatal_error_qt")
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
@patch("nxdrive.drive.fatal_error.fatal_error_qt")
@patch("traceback.format_exception")
@patch("sys.exc_info")
def test_show_critical_error_linux(mock_exc_info, mock_traceback, mock_fatal_error_qt):
    mock_exc_info.return_value = "dummy_exc_info"
    mock_traceback.return_value = ["dummy_exception1", "dummy_exception2"]
    mock_fatal_error_qt.side_effect = Exception("Dummy Linux Exception")
    assert fatal_error.show_critical_error() is None
