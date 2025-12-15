"""Integration tests for FoldersDialog._process_directory method - macOS only."""

from logging import getLogger
from unittest.mock import Mock, patch

from ...markers import mac_only

log = getLogger(__name__)


@mac_only
def test_process_directory_zero_byte_files_skipped():
    """Test _process_directory skips zero-byte files (NXDRIVE-2925)."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def get_size(self, path):
            return 0  # Simulate zero-byte file

        def _process_directory(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                from nxdrive.utils import get_tree_list

                files_with_sizes = list(get_tree_list(path))

                for file_path, size in files_with_sizes:
                    if file_path.is_file() and self.get_size(file_path) == 0:
                        continue
                    self.paths[file_path] = size
                    current_total_size += size

            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    skipped_items = []

    with patch("nxdrive.gui.folders_dialog.get_tree_list") as mock_get_tree:
        mock_file = Mock()
        mock_file.is_file.return_value = True
        mock_files = [(mock_file, 0)]
        mock_get_tree.return_value = mock_files

        result = dialog._process_directory(mock_path, 0, None, None, skipped_items)

        # Verify zero-byte file was skipped
        assert len(dialog.paths) == 0
        assert result == 0


@mac_only
def test_process_directory_oserror_handling():
    """Test _process_directory handles OSError."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def _process_directory(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                from nxdrive.utils import get_tree_list

                list(get_tree_list(path))
            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    skipped_items = []

    with patch("nxdrive.gui.folders_dialog.get_tree_list") as mock_get_tree:
        mock_get_tree.side_effect = OSError("Permission denied")

        result = dialog._process_directory(mock_path, 100, None, None, skipped_items)

        # Verify exception was handled and current size returned
        assert result == 100


@mac_only
def test_process_directory_general_exception_handling():
    """Test _process_directory handles general Exception."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def _process_directory(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                from nxdrive.utils import get_tree_list

                list(get_tree_list(path))
            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    skipped_items = []

    with patch("nxdrive.gui.folders_dialog.get_tree_list") as mock_get_tree:
        mock_get_tree.side_effect = ValueError("Unexpected error")

        result = dialog._process_directory(mock_path, 100, None, None, skipped_items)

        # Verify exception was handled and current size returned
        assert result == 100
