"""Integration tests for show_hide_refresh_button method - macOS only."""

from unittest.mock import MagicMock, Mock

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestShowHideRefreshButton:
    """Test suite for show_hide_refresh_button method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager

        yield app, manager

        manager.close()

    def test_show_hide_refresh_button_sets_height_property(self, mock_application):
        """Test show_hide_refresh_button sets height property on refresh button."""
        app, manager = mock_application

        # Mock task_manager_window with refresh button
        mock_window = Mock()
        mock_refresh_button = Mock()
        mock_window.findChild.return_value = mock_refresh_button
        app.task_manager_window = mock_window

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_hide_refresh_button.__get__(app, Application)
        height = 50
        bound_method(height)

        # Verify setProperty was called with "height" and the value
        mock_refresh_button.setProperty.assert_called_once_with("height", height)

    def test_show_hide_refresh_button_finds_refresh_child(self, mock_application):
        """Test show_hide_refresh_button finds child with name 'refresh'."""
        app, manager = mock_application

        # Mock task_manager_window
        mock_window = Mock()
        mock_refresh_button = Mock()
        mock_window.findChild.return_value = mock_refresh_button
        app.task_manager_window = mock_window

        from PyQt5.QtCore import QObject

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_hide_refresh_button.__get__(app, Application)
        bound_method(100)

        # Verify findChild was called with QObject and "refresh"
        mock_window.findChild.assert_called_once_with(QObject, "refresh")

    def test_show_hide_refresh_button_with_zero_height(self, mock_application):
        """Test show_hide_refresh_button with height 0 (hide button)."""
        app, manager = mock_application

        mock_window = Mock()
        mock_refresh_button = Mock()
        mock_window.findChild.return_value = mock_refresh_button
        app.task_manager_window = mock_window

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_hide_refresh_button.__get__(app, Application)
        bound_method(0)

        # Verify height was set to 0
        mock_refresh_button.setProperty.assert_called_once_with("height", 0)

    def test_show_hide_refresh_button_with_positive_height(self, mock_application):
        """Test show_hide_refresh_button with positive height (show button)."""
        app, manager = mock_application

        mock_window = Mock()
        mock_refresh_button = Mock()
        mock_window.findChild.return_value = mock_refresh_button
        app.task_manager_window = mock_window

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_hide_refresh_button.__get__(app, Application)
        height = 75
        bound_method(height)

        # Verify height was set correctly
        mock_refresh_button.setProperty.assert_called_once_with("height", height)

    def test_show_hide_refresh_button_with_various_heights(self, mock_application):
        """Test show_hide_refresh_button with various height values."""
        app, manager = mock_application

        mock_window = Mock()
        mock_refresh_button = Mock()
        mock_window.findChild.return_value = mock_refresh_button
        app.task_manager_window = mock_window

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_hide_refresh_button.__get__(app, Application)

        # Test with different heights
        test_heights = [0, 25, 50, 100, 200]
        for height in test_heights:
            mock_refresh_button.setProperty.reset_mock()
            bound_method(height)
            mock_refresh_button.setProperty.assert_called_once_with("height", height)

    def test_show_hide_refresh_button_when_window_is_none(self, mock_application):
        """Test show_hide_refresh_button when task_manager_window is None."""
        app, manager = mock_application

        # No window
        app.task_manager_window = None

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_hide_refresh_button.__get__(app, Application)

        # Should not raise an error, just do nothing
        try:
            bound_method(50)
        except AttributeError:
            pytest.fail("Method should handle None window gracefully")

    def test_show_hide_refresh_button_window_exists_check(self, mock_application):
        """Test show_hide_refresh_button only operates when window exists."""
        app, manager = mock_application

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_hide_refresh_button.__get__(app, Application)

        # Test with None window
        app.task_manager_window = None
        bound_method(50)  # Should not crash

        # Test with actual window
        mock_window = Mock()
        mock_refresh_button = Mock()
        mock_window.findChild.return_value = mock_refresh_button
        app.task_manager_window = mock_window

        bound_method(75)
        # Should work normally
        mock_refresh_button.setProperty.assert_called_once_with("height", 75)

    def test_show_hide_refresh_button_multiple_calls(self, mock_application):
        """Test show_hide_refresh_button can be called multiple times."""
        app, manager = mock_application

        mock_window = Mock()
        mock_refresh_button = Mock()
        mock_window.findChild.return_value = mock_refresh_button
        app.task_manager_window = mock_window

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.show_hide_refresh_button.__get__(app, Application)

        # Call multiple times with different heights
        bound_method(0)
        bound_method(100)
        bound_method(50)

        # Verify all three calls
        assert mock_refresh_button.setProperty.call_count == 3
        calls = mock_refresh_button.setProperty.call_args_list
        assert calls[0][0] == ("height", 0)
        assert calls[1][0] == ("height", 100)
        assert calls[2][0] == ("height", 50)
