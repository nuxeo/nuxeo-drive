"""
Functional test for nxdrive/fatal_error.py
"""

from unittest.mock import patch

from nxdrive.fatal_error import (
    check_executable_path,
    fatal_error_mac,
    fatal_error_qt,
    fatal_error_win,
)
from nxdrive.options import Options

from ..markers import mac_only, not_linux, windows_only


@not_linux(reason="Qt does not work correctly on Linux")
def test_fatal_error_qt():
    with patch("nxdrive.qt.imports.QApplication.exec_") as mock_app_exec:
        mock_app_exec.return_value = None
        output = fatal_error_qt("Dummy exception")
        assert output is None


@windows_only
@patch("ctypes.windll.user32.MessageBoxW")
def test_fatal_error_win(mock_messagebox):
    output = fatal_error_win("dummy_error")
    assert output is None


@mac_only
@patch("subprocess.Popen")
def test_fatal_error_mac(mock_popen):
    output = fatal_error_mac("dummy_error")
    assert output is None


@mac_only
@patch("nxdrive.qt.imports.QMessageBox.exec_")
def test_check_executable_path(mock_exec):
    Options.is_frozen = True
    output = check_executable_path()
    assert output is False


@mac_only
@patch("nxdrive.qt.imports.QMessageBox.exec_")
@patch("subprocess.Popen")
def test_check_executable_path_exception(mock_popen, mock_exec):
    Options.is_frozen = True
    mock_exec.return_value = None
    mock_exec.side_effect = Exception("dummy_exception")
    output = check_executable_path()
    assert output is False
