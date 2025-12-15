"""Integration tests for show_tasks_window method - macOS only."""

from unittest.mock import MagicMock, Mock

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestShowTasksWindow:
    """Test suite for show_tasks_window method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager

        # Mock task_manager_window
        mock_window = Mock()
        mock_root = Mock()
        mock_root.setEngine = Mock()
        mock_root.setEngine.emit = Mock()
        mock_root.setSection = Mock()
        mock_root.setSection.emit = Mock()

        app.task_manager_window = mock_window
        app._window_root = Mock(return_value=mock_root)
        app._center_on_screen = Mock()

        yield app, manager, mock_window, mock_root

        manager.close()

    def test_show_tasks_window_emits_set_engine(self, mock_application):
        """Test show_tasks_window emits setEngine signal with engine_uid."""
        app, manager, mock_window, mock_root = mock_application

        engine_uid = "test-engine-uid-123"

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_tasks_window.__get__(app, Application)
        bound_method(engine_uid)

        # Verify setEngine.emit was called with engine_uid
        mock_root.setEngine.emit.assert_called_once_with(engine_uid)

    def test_show_tasks_window_emits_set_section_zero(self, mock_application):
        """Test show_tasks_window emits setSection signal with 0."""
        app, manager, mock_window, mock_root = mock_application

        engine_uid = "engine-456"

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_tasks_window.__get__(app, Application)
        bound_method(engine_uid)

        # Verify setSection.emit was called with 0
        mock_root.setSection.emit.assert_called_once_with(0)

    def test_show_tasks_window_calls_window_root(self, mock_application):
        """Test show_tasks_window calls _window_root with task_manager_window."""
        app, manager, mock_window, mock_root = mock_application

        engine_uid = "engine-789"

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_tasks_window.__get__(app, Application)
        bound_method(engine_uid)

        # Verify _window_root was called with task_manager_window
        # It's called twice (once for setEngine, once for setSection)
        assert app._window_root.call_count == 2
        app._window_root.assert_called_with(mock_window)

    def test_show_tasks_window_centers_window(self, mock_application):
        """Test show_tasks_window centers the window on screen."""
        app, manager, mock_window, mock_root = mock_application

        engine_uid = "center-test"

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_tasks_window.__get__(app, Application)
        bound_method(engine_uid)

        # Verify _center_on_screen was called with task_manager_window
        app._center_on_screen.assert_called_once_with(mock_window)

    def test_show_tasks_window_with_different_engine_uids(self, mock_application):
        """Test show_tasks_window with various engine_uid values."""
        app, manager, mock_window, mock_root = mock_application

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_tasks_window.__get__(app, Application)

        # Test with different UIDs
        test_uids = ["uid-1", "uid-2", "special-uid-abc-123"]

        for uid in test_uids:
            mock_root.setEngine.emit.reset_mock()
            bound_method(uid)
            mock_root.setEngine.emit.assert_called_once_with(uid)

    def test_show_tasks_window_signal_order(self, mock_application):
        """Test show_tasks_window emits signals in correct order."""
        app, manager, mock_window, mock_root = mock_application

        engine_uid = "order-test"

        # Track call order
        call_order = []
        mock_root.setEngine.emit.side_effect = lambda x: call_order.append(
            ("setEngine", x)
        )
        mock_root.setSection.emit.side_effect = lambda x: call_order.append(
            ("setSection", x)
        )
        app._center_on_screen.side_effect = lambda x: call_order.append("center")

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_tasks_window.__get__(app, Application)
        bound_method(engine_uid)

        # Verify correct order: setEngine, setSection, then center
        assert len(call_order) == 3
        assert call_order[0] == ("setEngine", engine_uid)
        assert call_order[1] == ("setSection", 0)
        assert call_order[2] == "center"

    def test_show_tasks_window_section_always_zero(self, mock_application):
        """Test show_tasks_window always sets section to 0."""
        app, manager, mock_window, mock_root = mock_application

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_tasks_window.__get__(app, Application)

        # Call multiple times with different engine_uids
        for uid in ["uid-a", "uid-b", "uid-c"]:
            mock_root.setSection.emit.reset_mock()
            bound_method(uid)
            # Always 0
            mock_root.setSection.emit.assert_called_once_with(0)
