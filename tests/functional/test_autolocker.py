"""
nxdrive/autolocker functional tests
"""

from unittest.mock import patch

import psutil

from nxdrive.autolocker import MONITORED_PROCESSES, get_open_files

from ..markers import windows_only


class TestGetOpenFiles:
    @windows_only
    def test_get_open_files_windows(self):
        # Adding an inaccessible process to the monitored list
        MONITORED_PROCESSES.add("svchost")
        open_files = list(get_open_files())
        assert open_files  # Should return a non-empty list

        # Forcing NoSuchProcess Exception in open_files
        with patch("psutil.Process.open_files") as mock_open_files:
            mock_open_files.side_effect = psutil.NoSuchProcess(
                pid=600000, msg="Forced NoSuchProcess Error"
            )
            open_files = list(get_open_files())
            assert not open_files  # Should return empty list

        # Forcing Exception in open_files
        with patch("psutil.Process.open_files") as mock_open_files:
            mock_open_files.side_effect = Exception("Forced Exception in open_files")
            open_files = list(get_open_files())
            assert not open_files  # Should return empty list

        # Clearing added process from the monitored list
        MONITORED_PROCESSES.remove("svchost")

    def test_process_iter_fault(self):
        # Forcing Exception in psutil.process_iter
        with patch("psutil.process_iter") as mock_process_iter:
            mock_process_iter.side_effect = Exception(
                "Forced Exception in process_iter"
            )
            open_files = list(get_open_files())
            assert not open_files  # Should return empty list
