"""Integration tests for update_status method - macOS only."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.engine.engine import Engine
from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestUpdateStatus:
    """Test suite for update_status method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager and models."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app.conflicts_model = Mock()
        app.conflicts_model.count = 0
        app.errors_model = Mock()
        app.errors_model.count = 0
        app.systray_window = Mock()
        app.refresh_conflicts = Mock()

        yield app, manager

        manager.close()

    def test_update_status_with_invalid_engine(self, mock_application):
        """Test update_status logs error when passed non-Engine object."""
        app, manager = mock_application

        not_an_engine = "not_an_engine"

        with patch("nxdrive.gui.application.log") as mock_log, patch.object(
            app, "_window_root", return_value=app.systray_window
        ):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(not_an_engine)

            # Verify error was logged
            mock_log.error.assert_called_once()
            log_message = mock_log.error.call_args[0][0]
            assert "Need an Engine" in log_message

    def test_update_status_restart_needed(self, mock_application):
        """Test update_status sets restart state when restart is needed."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = False
        mock_engine.is_syncing.return_value = False
        mock_engine.has_invalid_credentials.return_value = False

        manager.restart_needed = True
        manager.updater = Mock()
        manager.updater.status = ""

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify setStatus was called with restart state
            app.systray_window.setStatus.emit.assert_called_once()
            call_args = app.systray_window.setStatus.emit.call_args[0]
            assert call_args[0] == "restart"  # sync_state

    def test_update_status_suspended(self, mock_application):
        """Test update_status sets suspended state when engine is paused."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = True
        mock_engine.is_syncing.return_value = False
        mock_engine.has_invalid_credentials.return_value = False

        manager.restart_needed = False
        manager.updater = Mock()
        manager.updater.status = ""

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify setStatus was called with suspended state
            app.systray_window.setStatus.emit.assert_called_once()
            call_args = app.systray_window.setStatus.emit.call_args[0]
            assert call_args[0] == "suspended"  # sync_state

    def test_update_status_syncing(self, mock_application):
        """Test update_status sets syncing state when engine is syncing."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = False
        mock_engine.is_syncing.return_value = True
        mock_engine.has_invalid_credentials.return_value = False

        manager.restart_needed = False
        manager.updater = Mock()
        manager.updater.status = ""

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify setStatus was called with syncing state
            app.systray_window.setStatus.emit.assert_called_once()
            call_args = app.systray_window.setStatus.emit.call_args[0]
            assert call_args[0] == "syncing"  # sync_state

    def test_update_status_auth_expired(self, mock_application):
        """Test update_status sets auth_expired error state."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = False
        mock_engine.is_syncing.return_value = False
        mock_engine.has_invalid_credentials.return_value = True

        manager.restart_needed = False
        manager.updater = Mock()
        manager.updater.status = ""

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify setStatus was called with auth_expired error state
            app.systray_window.setStatus.emit.assert_called_once()
            call_args = app.systray_window.setStatus.emit.call_args[0]
            assert call_args[1] == "auth_expired"  # error_state

    def test_update_status_conflicted(self, mock_application):
        """Test update_status sets conflicted error state."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = False
        mock_engine.is_syncing.return_value = False
        mock_engine.has_invalid_credentials.return_value = False

        manager.restart_needed = False
        manager.updater = Mock()
        manager.updater.status = ""

        # Set conflicts count
        app.conflicts_model.count = 5

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify setStatus was called with conflicted error state
            app.systray_window.setStatus.emit.assert_called_once()
            call_args = app.systray_window.setStatus.emit.call_args[0]
            assert call_args[1] == "conflicted"  # error_state

    def test_update_status_error(self, mock_application):
        """Test update_status sets error state when errors exist."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = False
        mock_engine.is_syncing.return_value = False
        mock_engine.has_invalid_credentials.return_value = False

        manager.restart_needed = False
        manager.updater = Mock()
        manager.updater.status = ""

        # Set errors count (no conflicts)
        app.conflicts_model.count = 0
        app.errors_model.count = 3

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify setStatus was called with error state
            app.systray_window.setStatus.emit.assert_called_once()
            call_args = app.systray_window.setStatus.emit.call_args[0]
            assert call_args[1] == "error"  # error_state

    def test_update_status_with_update_available(self, mock_application):
        """Test update_status includes update state."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = False
        mock_engine.is_syncing.return_value = False
        mock_engine.has_invalid_credentials.return_value = False

        manager.restart_needed = False
        manager.updater = Mock()
        manager.updater.status = "update_available"

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify setStatus was called with update state
            app.systray_window.setStatus.emit.assert_called_once()
            call_args = app.systray_window.setStatus.emit.call_args[0]
            assert call_args[2] == "update_available"  # update_state

    def test_update_status_calls_refresh_conflicts(self, mock_application):
        """Test update_status calls refresh_conflicts before checking counts."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = False
        mock_engine.is_syncing.return_value = False
        mock_engine.has_invalid_credentials.return_value = False

        manager.restart_needed = False
        manager.updater = Mock()
        manager.updater.status = ""

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify refresh_conflicts was called
            app.refresh_conflicts.assert_called_once_with(mock_engine.uid)

    def test_update_status_empty_states(self, mock_application):
        """Test update_status with no special states."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = False
        mock_engine.is_syncing.return_value = False
        mock_engine.has_invalid_credentials.return_value = False

        manager.restart_needed = False
        manager.updater = Mock()
        manager.updater.status = ""

        # No conflicts or errors
        app.conflicts_model.count = 0
        app.errors_model.count = 0

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify setStatus was called with empty states
            app.systray_window.setStatus.emit.assert_called_once()
            call_args = app.systray_window.setStatus.emit.call_args[0]
            assert call_args[0] == ""  # sync_state
            assert call_args[1] == ""  # error_state
            assert call_args[2] == ""  # update_state

    def test_update_status_priority_restart_over_paused(self, mock_application):
        """Test update_status prioritizes restart over paused state."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = True
        mock_engine.is_syncing.return_value = False
        mock_engine.has_invalid_credentials.return_value = False

        manager.restart_needed = True
        manager.updater = Mock()
        manager.updater.status = ""

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify restart takes priority
            app.systray_window.setStatus.emit.assert_called_once()
            call_args = app.systray_window.setStatus.emit.call_args[0]
            assert call_args[0] == "restart"  # sync_state

    def test_update_status_priority_auth_over_conflicts(self, mock_application):
        """Test update_status prioritizes auth_expired over conflicts."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = False
        mock_engine.is_syncing.return_value = False
        mock_engine.has_invalid_credentials.return_value = True

        manager.restart_needed = False
        manager.updater = Mock()
        manager.updater.status = ""

        # Set conflicts count
        app.conflicts_model.count = 5
        app.errors_model.count = 0

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify auth_expired takes priority
            app.systray_window.setStatus.emit.assert_called_once()
            call_args = app.systray_window.setStatus.emit.call_args[0]
            assert call_args[1] == "auth_expired"  # error_state

    def test_update_status_priority_conflicts_over_errors(self, mock_application):
        """Test update_status prioritizes conflicts over errors."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.is_paused.return_value = False
        mock_engine.is_syncing.return_value = False
        mock_engine.has_invalid_credentials.return_value = False

        manager.restart_needed = False
        manager.updater = Mock()
        manager.updater.status = ""

        # Set both conflicts and errors
        app.conflicts_model.count = 2
        app.errors_model.count = 3

        with patch.object(app, "_window_root", return_value=app.systray_window):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.update_status.__get__(app, Application)
            bound_method(mock_engine)

            # Verify conflicts take priority
            app.systray_window.setStatus.emit.assert_called_once()
            call_args = app.systray_window.setStatus.emit.call_args[0]
            assert call_args[1] == "conflicted"  # error_state
