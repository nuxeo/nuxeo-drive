"""Integration tests for _add_csv_path_to_session method - macOS only."""

from unittest.mock import MagicMock

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestAddCsvPathToSession:
    """Test suite for _add_csv_path_to_session method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager

        yield app, manager

        manager.close()

    def test_add_csv_path_to_session_no_completed_on(self, mock_application):
        """Test _add_csv_path_to_session when completed_on is None (cancelled)."""
        app, manager = mock_application

        session_data = {
            "uid": "test-session-123",
            "status": "cancelled",
            "completed_on": None,
        }

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._add_csv_path_to_session.__get__(app, Application)
        result = bound_method(session_data)

        # Verify session unchanged when completed_on is None
        assert result == session_data
        assert "csv_path" not in result

    def test_add_csv_path_to_session_with_tmp_file(self, mock_application):
        """Test _add_csv_path_to_session with .tmp file (async_gen state)."""
        app, manager = mock_application

        # Create CSV directory
        csv_dir = manager.home / "csv"
        csv_dir.mkdir(parents=True)

        session_data = {
            "uid": "test-session-456",
            "status": "ongoing",
            "completed_on": "2024-01-15 10:30:00",
        }

        # Create a .tmp file (method uses with_suffix(".tmp") which replaces .csv with .tmp)
        tmp_file = csv_dir / "session_2024-01-15_10-30-00.tmp"
        tmp_file.write_text("id,name,status\n1,file1.txt,success\n")

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._add_csv_path_to_session.__get__(app, Application)
        result = bound_method(session_data)

        # Verify csv_path is "async_gen" for .tmp files
        assert result["csv_path"] == "async_gen"

    def test_add_csv_path_to_session_with_csv_file(self, mock_application):
        """Test _add_csv_path_to_session with completed .csv file."""
        app, manager = mock_application

        # Create CSV directory
        csv_dir = manager.home / "csv"
        csv_dir.mkdir(parents=True)

        session_data = {
            "uid": "test-session-789",
            "status": "completed",
            "completed_on": "2024-01-15 14:45:00",
        }

        # Create a .csv file following the naming convention
        csv_file = csv_dir / "session_2024-01-15_14-45-00.csv"
        csv_file.write_text("id,name,status\n1,file1.txt,success\n")

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._add_csv_path_to_session.__get__(app, Application)
        result = bound_method(session_data)

        # Verify csv_path points to .csv file
        assert result["csv_path"] == str(csv_file)

    def test_add_csv_path_to_session_prioritizes_tmp_over_csv(self, mock_application):
        """Test _add_csv_path_to_session prioritizes .tmp file over .csv file."""
        app, manager = mock_application

        # Create CSV directory
        csv_dir = manager.home / "csv"
        csv_dir.mkdir(parents=True)

        session_data = {
            "uid": "test-session-abc",
            "status": "ongoing",
            "completed_on": "2024-01-15 09:20:00",
        }

        # Create both .tmp and .csv files (with_suffix replaces extension)
        name_base = "session_2024-01-15_09-20-00"
        tmp_file = csv_dir / f"{name_base}.tmp"
        tmp_file.write_text("id,name,status\n1,file1.txt,ongoing\n")

        csv_file = csv_dir / f"{name_base}.csv"
        csv_file.write_text("id,name,status\n1,file1.txt,success\n")

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._add_csv_path_to_session.__get__(app, Application)
        result = bound_method(session_data)

        # Verify csv_path is "async_gen" (.tmp file has priority)
        assert result["csv_path"] == "async_gen"

    def test_add_csv_path_to_session_no_files(self, mock_application):
        """Test _add_csv_path_to_session when no CSV files exist."""
        app, manager = mock_application

        # Create CSV directory but no files
        csv_dir = manager.home / "csv"
        csv_dir.mkdir(parents=True)

        session_data = {
            "uid": "test-session-xyz",
            "status": "completed",
            "completed_on": "2024-01-15 16:00:00",
        }

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._add_csv_path_to_session.__get__(app, Application)
        result = bound_method(session_data)

        # Verify csv_path is empty string when no files exist
        assert result["csv_path"] == ""

    def test_add_csv_path_to_session_csv_dir_not_exist(self, mock_application):
        """Test _add_csv_path_to_session when csv directory doesn't exist."""
        app, manager = mock_application

        session_data = {
            "uid": "test-session-ghi",
            "status": "completed",
            "completed_on": "2024-01-15 12:15:00",
        }

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._add_csv_path_to_session.__get__(app, Application)
        result = bound_method(session_data)

        # Verify csv_path is empty string when directory doesn't exist
        assert result["csv_path"] == ""

    def test_add_csv_path_to_session_date_replacement(self, mock_application):
        """Test _add_csv_path_to_session correctly replaces colons and spaces."""
        app, manager = mock_application

        # Create CSV directory
        csv_dir = manager.home / "csv"
        csv_dir.mkdir(parents=True)

        # Session with date containing colons and spaces
        session_data = {
            "uid": "test-session-date",
            "status": "completed",
            "completed_on": "2024-03-22 18:45:30",
        }

        # Create a .csv file with proper name replacement
        csv_file = csv_dir / "session_2024-03-22_18-45-30.csv"
        csv_file.write_text("id,name,status\n1,file1.txt,success\n")

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._add_csv_path_to_session.__get__(app, Application)
        result = bound_method(session_data)

        # Verify csv_path is correctly set with replaced characters
        assert result["csv_path"] == str(csv_file)

    def test_add_csv_path_to_session_returns_modified_dict(self, mock_application):
        """Test _add_csv_path_to_session returns the modified session dict."""
        app, manager = mock_application

        # Create CSV directory
        csv_dir = manager.home / "csv"
        csv_dir.mkdir(parents=True)

        session_data = {
            "uid": "test-session-jkl",
            "status": "completed",
            "completed_on": "2024-01-15 11:00:00",
            "extra_field": "extra_value",
        }

        # Create a .csv file
        csv_file = csv_dir / "session_2024-01-15_11-00-00.csv"
        csv_file.write_text("id,name,status\n1,file1.txt,success\n")

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._add_csv_path_to_session.__get__(app, Application)
        result = bound_method(session_data)

        # Verify result is the modified session dict
        assert result["uid"] == "test-session-jkl"
        assert result["status"] == "completed"
        assert result["completed_on"] == "2024-01-15 11:00:00"
        assert result["csv_path"] == str(csv_file)
        assert result["extra_field"] == "extra_value"
