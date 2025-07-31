"""
Functional test for nxdrive/fatal_error.py
"""

from pathlib import Path
from unittest.mock import patch

from nxdrive.fatal_error import (
    check_executable_path,
    check_executable_path_error_qt,
    fatal_error_mac,
    fatal_error_win,
)
from nxdrive.options import Options
from tests.functional.mocked_classes import Mock_Qt

from ..markers import mac_only, not_linux, windows_only


@not_linux(reason="Qt does not work correctly on Linux")
def test_check_executable_path_error_qt():
    mock_qt = Mock_Qt()
    with patch("nxdrive.qt.imports.QApplication") as mock_application, patch(
        "nxdrive.qt.imports.QPixmap"
    ) as mock_pixmap, patch("nxdrive.qt.imports.QMessageBox") as mock_message_box:
        mock_application.return_value = mock_qt
        mock_pixmap.return_value = "dummy_icon.svg"
        mock_message_box.return_value = mock_qt
        output = check_executable_path_error_qt(Path())
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
def test_check_executable_path():
    Options.is_frozen = True
    with patch("subprocess.Popen") as mock_popen, patch(
        "nxdrive.fatal_error.check_executable_path_error_qt"
    ) as mock_exec_path:
        mock_popen.return_value = None
        mock_exec_path.side_effect = Exception("dummy exception")
        output = check_executable_path()
        assert output is False
