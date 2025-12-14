"""Integration tests for _handle_notification_action method - macOS only."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestHandleNotificationAction:
    """Test suite for _handle_notification_action method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app.api = Mock()

        yield app, manager

        manager.close()

    def test_handle_notification_action_success(self, mock_application):
        """Test successful notification action handling."""
        app, manager = mock_application

        action = "test_action"
        action_args = ("arg1", "arg2", 123)

        # Mock the action method on api
        mock_action_func = Mock()
        app.api.test_action = mock_action_func

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._handle_notification_action.__get__(app, Application)
        bound_method(action, action_args)

        # Verify the action was called with correct args
        mock_action_func.assert_called_once_with("arg1", "arg2", 123)

    def test_handle_notification_action_no_args(self, mock_application):
        """Test notification action with no arguments."""
        app, manager = mock_application

        action = "simple_action"
        action_args = ()

        mock_action_func = Mock()
        app.api.simple_action = mock_action_func

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._handle_notification_action.__get__(app, Application)
        bound_method(action, action_args)

        # Verify the action was called with no args
        mock_action_func.assert_called_once_with()

    def test_handle_notification_action_not_found(self, mock_application):
        """Test notification action when action doesn't exist."""
        app, manager = mock_application

        action = "nonexistent_action"
        action_args = ()

        # Don't add this action to api
        app.api.nonexistent_action = None

        with patch("nxdrive.gui.application.log") as mock_log:

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_notification_action.__get__(app, Application)
            bound_method(action, action_args)

            # Verify error was logged
            mock_log.error.assert_called_once()
            error_msg = mock_log.error.call_args[0][0]
            assert "nonexistent_action" in error_msg
            assert "not defined" in error_msg

    def test_handle_notification_action_with_multiple_args(self, mock_application):
        """Test notification action with multiple complex arguments."""
        app, manager = mock_application

        action = "complex_action"
        action_args = ("string", 42, {"key": "value"}, ["list", "items"])

        mock_action_func = Mock()
        app.api.complex_action = mock_action_func

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._handle_notification_action.__get__(app, Application)
        bound_method(action, action_args)

        # Verify the action was called with all args
        mock_action_func.assert_called_once_with(
            "string", 42, {"key": "value"}, ["list", "items"]
        )

    def test_handle_notification_action_exception_in_action(self, mock_application):
        """Test notification action when the action raises an exception."""
        app, manager = mock_application

        action = "failing_action"
        action_args = ("test",)

        mock_action_func = Mock(side_effect=Exception("Action failed"))
        app.api.failing_action = mock_action_func

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._handle_notification_action.__get__(app, Application)

        # The exception should propagate
        with pytest.raises(Exception, match="Action failed"):
            bound_method(action, action_args)

    def test_handle_notification_action_attribute_not_callable(self, mock_application):
        """Test notification action when attribute exists but is not callable."""
        app, manager = mock_application

        action = "not_callable"
        action_args = ()

        # Set a non-callable attribute
        app.api.not_callable = "I am not a function"

        with patch("nxdrive.gui.application.log") as mock_log:
            mock_log.return_value = None

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_notification_action.__get__(app, Application)

            # This should fail when trying to call it
            with pytest.raises(TypeError):
                bound_method(action, action_args)
