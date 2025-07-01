"""
Functional test for nxdrive/fatal_error.py
"""

from pathlib import Path
from unittest.mock import patch

from nxdrive.fatal_error import check_executable_path_error_qt, fatal_error_qt

from ..markers import not_linux


@not_linux(reason="Qt does not work correctly on Linux")
@patch("nxdrive.qt.imports.QMessageBox.exec_")
def test_check_executable_path_error_qt(mock_exec):
    mock_exec.return_value = None
    output = check_executable_path_error_qt(Path())
    assert output is None


@not_linux(reason="Qt does not work correctly on Linux")
@patch("nxdrive.qt.imports.QApplication.exec_")
def test_fatal_error_qt(mock_exec):
    mock_exec.return_value = None
    output = fatal_error_qt("Dummy exception")
    assert output is None
