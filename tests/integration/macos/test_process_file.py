"""Integration tests for FoldersDialog._process_file method - macOS only."""

from logging import getLogger
from unittest.mock import Mock

from ...markers import mac_only

log = getLogger(__name__)


@mac_only
def test_process_file_basic():
    """Test _process_file with valid file."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def get_size(self, path):
            return 100

        def _process_file(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            """Process a file with size checks."""
            try:
                file_size = self.get_size(path)

                if file_size == 0:
                    return current_total_size

                if file_limit and file_size > file_limit:
                    skipped_items.append(path.name)
                    return current_total_size

                if folder_limit and (current_total_size + file_size) > folder_limit:
                    skipped_items.append(path.name)
                    return current_total_size

                self.paths[path] = file_size
                current_total_size += file_size

            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    mock_path.name = "file.txt"
    skipped_items = []

    result = dialog._process_file(mock_path, 0, None, None, skipped_items)

    # Verify file was processed
    assert dialog.paths[mock_path] == 100
    assert result == 100
    assert len(skipped_items) == 0


@mac_only
def test_process_file_zero_byte():
    """Test _process_file skips zero-byte files (NXDRIVE-2925)."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def get_size(self, path):
            return 0

        def _process_file(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                file_size = self.get_size(path)

                if file_size == 0:
                    return current_total_size

                self.paths[path] = file_size
                current_total_size += file_size

            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    skipped_items = []

    result = dialog._process_file(mock_path, 50, None, None, skipped_items)

    # Verify zero-byte file was skipped
    assert len(dialog.paths) == 0
    assert result == 50  # Unchanged


@mac_only
def test_process_file_exceeds_file_limit():
    """Test _process_file skips file exceeding file_limit."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def get_size(self, path):
            return 600

        def _process_file(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                file_size = self.get_size(path)

                if file_size == 0:
                    return current_total_size

                if file_limit and file_size > file_limit:
                    skipped_items.append(path.name)
                    return current_total_size

                self.paths[path] = file_size
                current_total_size += file_size

            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    mock_path.name = "large.txt"
    skipped_items = []

    result = dialog._process_file(mock_path, 0, 500, None, skipped_items)

    # Verify file was skipped
    assert len(dialog.paths) == 0
    assert "large.txt" in skipped_items
    assert result == 0


@mac_only
def test_process_file_exceeds_folder_limit():
    """Test _process_file skips file when total exceeds folder_limit."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def get_size(self, path):
            return 300

        def _process_file(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                file_size = self.get_size(path)

                if file_size == 0:
                    return current_total_size

                if file_limit and file_size > file_limit:
                    skipped_items.append(path.name)
                    return current_total_size

                if folder_limit and (current_total_size + file_size) > folder_limit:
                    skipped_items.append(path.name)
                    return current_total_size

                self.paths[path] = file_size
                current_total_size += file_size

            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    mock_path.name = "file.txt"
    skipped_items = []

    result = dialog._process_file(mock_path, 300, None, 500, skipped_items)

    # Verify file was skipped (300 + 300 > 500)
    assert len(dialog.paths) == 0
    assert "file.txt" in skipped_items
    assert result == 300  # Unchanged


@mac_only
def test_process_file_oserror_handling():
    """Test _process_file handles OSError."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def get_size(self, path):
            raise OSError("Permission denied")

        def _process_file(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                file_size = self.get_size(path)
                self.paths[path] = file_size
                current_total_size += file_size
            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    skipped_items = []

    result = dialog._process_file(mock_path, 100, None, None, skipped_items)

    # Verify exception was handled
    assert len(dialog.paths) == 0
    assert result == 100  # Unchanged


@mac_only
def test_process_file_general_exception_handling():
    """Test _process_file handles general Exception."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def get_size(self, path):
            raise ValueError("Unexpected error")

        def _process_file(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                file_size = self.get_size(path)
                self.paths[path] = file_size
                current_total_size += file_size
            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    skipped_items = []

    result = dialog._process_file(mock_path, 100, None, None, skipped_items)

    # Verify exception was handled
    assert len(dialog.paths) == 0
    assert result == 100  # Unchanged


@mac_only
def test_process_file_paths_dictionary_update():
    """Test _process_file updates paths dictionary correctly."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def get_size(self, path):
            sizes = {"file1": 100, "file2": 200}
            return sizes.get(path.name, 0)

        def _process_file(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                file_size = self.get_size(path)

                if file_size == 0:
                    return current_total_size

                self.paths[path] = file_size
                current_total_size += file_size

            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    skipped_items = []

    # Process multiple files
    path1 = Mock()
    path1.name = "file1"
    result1 = dialog._process_file(path1, 0, None, None, skipped_items)

    path2 = Mock()
    path2.name = "file2"
    result2 = dialog._process_file(path2, result1, None, None, skipped_items)

    # Verify paths dictionary and total size
    assert len(dialog.paths) == 2
    assert dialog.paths[path1] == 100
    assert dialog.paths[path2] == 200
    assert result2 == 300


@mac_only
def test_process_file_file_limit_at_boundary():
    """Test _process_file with file size exactly at limit."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def get_size(self, path):
            return 500

        def _process_file(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                file_size = self.get_size(path)

                if file_size == 0:
                    return current_total_size

                if file_limit and file_size > file_limit:
                    skipped_items.append(path.name)
                    return current_total_size

                self.paths[path] = file_size
                current_total_size += file_size

            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    mock_path.name = "file.txt"
    skipped_items = []

    # File size equals limit (should be accepted)
    result = dialog._process_file(mock_path, 0, 500, None, skipped_items)

    # Verify file was processed (not skipped)
    assert dialog.paths[mock_path] == 500
    assert result == 500
    assert len(skipped_items) == 0


@mac_only
def test_process_file_folder_limit_at_boundary():
    """Test _process_file with total size exactly at limit."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def get_size(self, path):
            return 200

        def _process_file(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                file_size = self.get_size(path)

                if file_size == 0:
                    return current_total_size

                if folder_limit and (current_total_size + file_size) > folder_limit:
                    skipped_items.append(path.name)
                    return current_total_size

                self.paths[path] = file_size
                current_total_size += file_size

            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    mock_path.name = "file.txt"
    skipped_items = []

    # Total size equals limit (should be accepted)
    result = dialog._process_file(mock_path, 300, None, 500, skipped_items)

    # Verify file was processed
    assert dialog.paths[mock_path] == 200
    assert result == 500
    assert len(skipped_items) == 0


@mac_only
def test_process_file_with_all_checks():
    """Test _process_file with all checks (zero-byte, file_limit, folder_limit)."""

    class MockFoldersDialog:
        def __init__(self):
            self.paths = {}

        def get_size(self, path):
            return 300

        def _process_file(
            self, path, current_total_size, file_limit, folder_limit, skipped_items
        ):
            try:
                file_size = self.get_size(path)

                if file_size == 0:
                    return current_total_size

                if file_limit and file_size > file_limit:
                    skipped_items.append(path.name)
                    return current_total_size

                if folder_limit and (current_total_size + file_size) > folder_limit:
                    skipped_items.append(path.name)
                    return current_total_size

                self.paths[path] = file_size
                current_total_size += file_size

            except OSError as e:
                log.error(f"OSError : {e}")
            except Exception as e:
                log.error(f"Exception : {e}")

            return current_total_size

    dialog = MockFoldersDialog()
    mock_path = Mock()
    mock_path.name = "file.txt"
    skipped_items = []

    # File passes all checks
    result = dialog._process_file(mock_path, 100, 400, 500, skipped_items)

    # Verify file was processed
    assert dialog.paths[mock_path] == 300
    assert result == 400
    assert len(skipped_items) == 0
