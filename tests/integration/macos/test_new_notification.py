"""Integration tests for _new_notification method - macOS only."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from nxdrive.notification import Notification
from tests.markers import mac_only


@mac_only
class TestNewNotification:
    """Test suite for _new_notification method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app.tray_icon = Mock()
        app.current_notification = None
        app._delegator = None

        yield app, manager

        manager.close()

    def test_new_notification_not_bubble(self, mock_application):
        """Test that non-bubble notifications are ignored."""
        app, manager = mock_application

        # Create notification without FLAG_BUBBLE
        notif = Notification(
            uid="test1",
            title="Test Title",
            description="Test Description",
            flags=Notification.FLAG_PERSISTENT,
        )

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._new_notification.__get__(app, Application)
        bound_method(notif)

        # Verify no notification was shown
        app.tray_icon.showMessage.assert_not_called()

    def test_new_notification_with_delegator(self, mock_application):
        """Test notification with macOS notification center delegator."""
        app, manager = mock_application

        # Set up delegator
        app._delegator = Mock()

        notif = Notification(
            uid="test1",
            title="Test Title",
            description="Test Description",
            flags=Notification.FLAG_BUBBLE | Notification.FLAG_UNIQUE,
        )

        with patch(
            "nxdrive.osi.darwin.pyNotificationCenter.notify"
        ) as mock_notify:  # Patching at the module level

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._new_notification.__get__(app, Application)
            bound_method(notif)

            # Verify notification center was used
            mock_notify.assert_called_once_with(
                "Test Title",
                "",
                "Test Description",
                user_info={"uuid": "test1"},
            )

            # Verify tray icon was not used
            app.tray_icon.showMessage.assert_not_called()

    def test_new_notification_with_delegator_no_uid(self, mock_application):
        """Test notification with delegator but no uid."""
        app, manager = mock_application

        # Set up delegator
        app._delegator = Mock()

        notif = Notification(
            title="Test Title",
            description="Test Description",
            flags=Notification.FLAG_BUBBLE,
        )

        with patch("nxdrive.osi.darwin.pyNotificationCenter.notify") as mock_notify:

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._new_notification.__get__(app, Application)
            bound_method(notif)

            # Verify notification center was used with None user_info
            mock_notify.assert_called_once_with(
                "Test Title",
                "",
                "Test Description",
                user_info=None,
            )

    def test_new_notification_warning_level(self, mock_application):
        """Test notification with warning level shows warning icon."""
        app, manager = mock_application

        notif = Notification(
            title="Warning Title",
            description="Warning Description",
            level=Notification.LEVEL_WARNING,
            flags=Notification.FLAG_BUBBLE,
        )

        with patch("nxdrive.gui.application.qt") as mock_qt:
            mock_qt.ST_Warning = "ST_Warning_Icon"

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._new_notification.__get__(app, Application)
            bound_method(notif)

            # Verify tray icon was used with warning icon
            app.tray_icon.showMessage.assert_called_once_with(
                "Warning Title",
                "Warning Description",
                "ST_Warning_Icon",
                10000,
            )

            # Verify current_notification was set
            assert app.current_notification == notif

    def test_new_notification_error_level(self, mock_application):
        """Test notification with error level shows critical icon."""
        app, manager = mock_application

        notif = Notification(
            title="Error Title",
            description="Error Description",
            level=Notification.LEVEL_ERROR,
            flags=Notification.FLAG_BUBBLE,
        )

        with patch("nxdrive.gui.application.qt") as mock_qt:
            mock_qt.ST_Critical = "ST_Critical_Icon"

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._new_notification.__get__(app, Application)
            bound_method(notif)

            # Verify tray icon was used with critical icon
            app.tray_icon.showMessage.assert_called_once_with(
                "Error Title",
                "Error Description",
                "ST_Critical_Icon",
                10000,
            )

            # Verify current_notification was set
            assert app.current_notification == notif

    def test_new_notification_info_level(self, mock_application):
        """Test notification with info level shows information icon."""
        app, manager = mock_application

        notif = Notification(
            title="Info Title",
            description="Info Description",
            level=Notification.LEVEL_INFO,
            flags=Notification.FLAG_BUBBLE,
        )

        with patch("nxdrive.gui.application.qt") as mock_qt:
            mock_qt.ST_Information = "ST_Information_Icon"

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._new_notification.__get__(app, Application)
            bound_method(notif)

            # Verify tray icon was used with information icon
            app.tray_icon.showMessage.assert_called_once_with(
                "Info Title",
                "Info Description",
                "ST_Information_Icon",
                10000,
            )

            # Verify current_notification was set
            assert app.current_notification == notif

    def test_new_notification_default_level(self, mock_application):
        """Test notification with default/unknown level shows information icon."""
        app, manager = mock_application

        notif = Notification(
            title="Default Title",
            description="Default Description",
            level="unknown",
            flags=Notification.FLAG_BUBBLE,
        )

        with patch("nxdrive.gui.application.qt") as mock_qt:
            mock_qt.ST_Information = "ST_Information_Icon"

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._new_notification.__get__(app, Application)
            bound_method(notif)

            # Verify tray icon was used with information icon (default)
            app.tray_icon.showMessage.assert_called_once_with(
                "Default Title",
                "Default Description",
                "ST_Information_Icon",
                10000,
            )

    def test_new_notification_timeout(self, mock_application):
        """Test notification shows for 10 seconds."""
        app, manager = mock_application

        notif = Notification(
            title="Timeout Test",
            description="Testing timeout",
            flags=Notification.FLAG_BUBBLE,
        )

        with patch("nxdrive.gui.application.qt"):

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._new_notification.__get__(app, Application)
            bound_method(notif)

            # Verify timeout is 10000 ms (10 seconds)
            call_args = app.tray_icon.showMessage.call_args
            assert call_args[0][3] == 10000
