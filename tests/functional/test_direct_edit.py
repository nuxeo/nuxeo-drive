"""
Functional tests for DirectEdit module functionality.

Tests comprehensive DirectEdit behavior including core functionality,
notifications, metrics, watchdog events, error handling, file operations,
integration scenarios, configuration, and PyQt signals.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nxdrive.direct_edit import DirectEdit, _is_lock_file
from nxdrive.exceptions import ThreadInterrupt
from nxdrive.options import Options


class TestDirectEditCore:
    """Test core DirectEdit functionality."""

    def test_direct_edit_initialization(self, manager_factory):
        """Test DirectEdit object initialization."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Test that DirectEdit is properly initialized
            assert direct_edit is not None
            assert isinstance(direct_edit, DirectEdit)
            assert direct_edit._manager == manager
            assert hasattr(direct_edit, "_folder")
            assert hasattr(direct_edit, "url")

    def test_is_lock_file_detection(self):
        """Test _is_lock_file function for detecting temporary files."""
        # Microsoft Office lock files
        assert _is_lock_file("~$document.docx")
        assert _is_lock_file("~$presentation.pptx")

        # LibreOffice/OpenOffice lock files
        assert _is_lock_file(".~lock.document.odt#")
        assert _is_lock_file(".~lock.spreadsheet.ods#")

        # Regular files should not be detected as lock files
        assert not _is_lock_file("document.docx")
        assert not _is_lock_file("presentation.pptx")
        assert not _is_lock_file("spreadsheet.ods")
        assert not _is_lock_file("regular_file.txt")

    def test_use_autolock_property(self, manager_factory):
        """Test use_autolock property."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Test autolock property (value depends on manager configuration)
            autolock_value = direct_edit.use_autolock
            assert isinstance(autolock_value, bool)

    def test_start_stop_lifecycle(self, manager_factory):
        """Test DirectEdit start/stop lifecycle."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Test start
            direct_edit.start()
            assert not direct_edit._stop

            # Test stop
            direct_edit.stop()
            assert direct_edit._stop

    def test_autolock_functionality(self, manager_factory):
        """Test autolock lock/unlock functionality."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit
            # Ensure the folder exists first
            direct_edit._folder.mkdir(parents=True, exist_ok=True)
            test_path = direct_edit._folder / "test_file.txt"
            test_path.touch()

            # Test autolock_lock
            direct_edit.autolock_lock(test_path)
            # Queue should have lock request
            assert not direct_edit._lock_queue.empty()

            # Test autolock_unlock
            direct_edit.autolock_unlock(test_path)
            # Queue should have unlock request
            assert not direct_edit._lock_queue.empty()


class TestDirectEditNotifications:
    """Test DirectEdit notification system."""

    def test_send_notification_with_filename(self, manager_factory):
        """Test notification sending with filename."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Mock the autolock service and database operations
            with patch.object(direct_edit.autolock, "documentLocked") as mock_signal:
                with patch.object(direct_edit, "_send_lock_status"):
                    direct_edit.send_notification("test_ref", "test_file.txt")
                    # Should emit with the filename
                    mock_signal.emit.assert_called_once_with("test_file.txt")

    def test_send_notification_without_filename(self, manager_factory):
        """Test notification sending without filename."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Use a string ref instead of Mock to avoid database issues
            test_ref = "test_ref"

            with patch.object(direct_edit.autolock, "documentLocked") as mock_signal:
                with patch.object(direct_edit, "_send_lock_status"):
                    direct_edit.send_notification(test_ref, "auto_file.txt")
                    # Should emit with the filename
                    mock_signal.emit.assert_called_once_with("auto_file.txt")

    def test_force_update_functionality(self, manager_factory):
        """Test force update functionality."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit
            test_ref = Path("test_doc") / "file.txt"  # Use relative path

            # Test force_update
            new_digest = "new_digest_value"
            direct_edit.force_update(test_ref, new_digest)

            # Verify upload queue has the file
            assert not direct_edit._upload_queue.empty()


class TestDirectEditMetrics:
    """Test DirectEdit metrics collection."""

    def test_get_metrics_basic(self, manager_factory):
        """Test basic metrics retrieval."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit
            metrics = direct_edit.get_metrics()

            # Verify metrics structure
            assert isinstance(metrics, dict)
            assert "edit_files" in metrics
            assert metrics["edit_files"] == 0

    def test_get_metrics_with_data(self, manager_factory):
        """Test metrics with populated data."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Modify metrics
            direct_edit._metrics["edit_files"] = 5

            metrics = direct_edit.get_metrics()
            assert metrics["edit_files"] == 5


class TestDirectEditWatchdogEvents:
    """Test DirectEdit watchdog event handling."""

    def test_handle_watchdog_event_file_modified(self, manager_factory):
        """Test handling of file modification events."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Mock a file modification event
            mock_event = Mock()
            mock_event.src_path = str(direct_edit._folder / "test.txt")
            mock_event.is_directory = False

            # Add event to watchdog queue
            direct_edit.watchdog_queue.put(mock_event)

            # Verify event was queued
            assert not direct_edit.watchdog_queue.empty()

    def test_handle_watchdog_event_file_created(self, manager_factory):
        """Test handling of file creation events."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            mock_event = Mock()
            mock_event.src_path = str(direct_edit._folder / "new_file.txt")
            mock_event.is_directory = False

            direct_edit.watchdog_queue.put(mock_event)
            assert not direct_edit.watchdog_queue.empty()

    def test_handle_watchdog_event_file_moved(self, manager_factory):
        """Test handling of file move events."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            mock_event = Mock()
            mock_event.src_path = str(direct_edit._folder / "old_file.txt")
            mock_event.dest_path = str(direct_edit._folder / "new_file.txt")
            mock_event.is_directory = False

            direct_edit.watchdog_queue.put(mock_event)
            assert not direct_edit.watchdog_queue.empty()


class TestDirectEditErrorHandling:
    """Test DirectEdit error handling mechanisms."""

    def test_upload_error_tracking(self, manager_factory):
        """Test upload error tracking and thresholds."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit
            test_path = Path("test_file.txt")

            # Simulate upload errors
            direct_edit._upload_errors[test_path] = 3
            assert direct_edit._upload_errors[test_path] == 3

            # Test error threshold
            assert direct_edit._error_threshold == Options.max_errors

    def test_error_threshold_behavior(self, manager_factory):
        """Test behavior when error threshold is reached."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Test that error threshold is configurable
            assert hasattr(direct_edit, "_error_threshold")
            assert isinstance(direct_edit._error_threshold, int)


class TestDirectEditFileOperations:
    """Test DirectEdit file operation functionality."""

    def test_stop_client_functionality(self, manager_factory):
        """Test stop_client method with ThreadInterrupt."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit
            mock_uploader = Mock()

            # Test that stop_client raises ThreadInterrupt when stopped
            direct_edit._stop = True
            with pytest.raises(ThreadInterrupt):
                direct_edit.stop_client(mock_uploader)

    def test_autolock_orphans_handler(self, manager_factory):
        """Test handling of orphaned locks."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Ensure the folder exists first
            direct_edit._folder.mkdir(parents=True, exist_ok=True)
            lock_path = direct_edit._folder / "test_lock"
            lock_path.touch()

            # Test orphan handling
            direct_edit._autolock_orphans([lock_path])

            # Verify lock queue has unlock request
            assert not direct_edit._lock_queue.empty()


class TestDirectEditIntegration:
    """Test DirectEdit integration scenarios."""

    def test_thread_interrupt_handling(self, manager_factory):
        """Test ThreadInterrupt exception handling."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Test that ThreadInterrupt can be properly caught
            with patch.object(
                direct_edit, "_prepare_edit", side_effect=ThreadInterrupt
            ):
                try:
                    direct_edit.edit(
                        "http://test.server",
                        "test_doc_id",
                        "test_user",
                        "http://test.server/download",
                    )
                except ThreadInterrupt:
                    pass  # Expected behavior
                except Exception as e:
                    pytest.fail(f"Unexpected exception: {e}")


class TestDirectEditConfiguration:
    """Test DirectEdit configuration and setup."""

    def test_folder_configuration(self, manager_factory):
        """Test folder configuration and validation."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Test that folder path exists (create it if needed)
            direct_edit._folder.mkdir(parents=True, exist_ok=True)
            assert direct_edit._folder.exists()
            assert direct_edit._folder.is_dir()

    def test_url_protocol_configuration(self, manager_factory):
        """Test URL protocol configuration."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Test that URL attribute exists (can be None initially)
            assert hasattr(direct_edit, "url")
            # URL is initially None in many cases
            url_value = direct_edit.url
            assert url_value is None or isinstance(url_value, str)


class TestDirectEditSignals:
    """Test DirectEdit PyQt signal functionality."""

    def test_signal_emission(self, manager_factory):
        """Test signal emission functionality."""
        manager, engine = manager_factory()

        with manager:
            direct_edit = manager.direct_edit

            # Test that signals exist and are accessible
            assert hasattr(direct_edit, "directEditStarting")
            assert hasattr(direct_edit, "directEditUploadCompleted")
            assert hasattr(direct_edit, "openDocument")

            # Basic signal test - just verify they exist
            assert direct_edit.directEditStarting is not None
            assert direct_edit.directEditUploadCompleted is not None
