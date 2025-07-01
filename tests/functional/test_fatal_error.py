"""
Functional test for nxdrive/fatal_error.py
"""

from pathlib import Path
from unittest.mock import patch

from nxdrive.fatal_error import check_executable_path_error_qt


@patch("nxdrive.qt.imports.QMessageBox.exec_")
def test_check_executable_path_error_qt(mock_exec):
    mock_exec.return_value = None
    output = check_executable_path_error_qt(Path())
    assert output is None
