"""Integration tests for Application._update_notification method."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from nxdrive.options import Options
from nxdrive.updater.constants import UPDATE_STATUS_INCOMPATIBLE_SERVER
from tests.markers import mac_only


@mac_only
class TestUpdateNotification:
    """Tests for Application._update_notification."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock application with manager."""
        manager = Manager(tmp())

        # Create mocked Application
        app = MagicMock(spec=Application)
        app.manager = manager
        app.change_systray_icon = Mock()

        # Setup notification service
        manager.notification_service = Mock()
        manager.notification_service.send_notification = Mock()

        yield app, manager

    def test_update_notification_upgrade(self, mock_application):
        """Test update notification for upgrade scenario."""
        app, manager = mock_application
        manager.updater.status = "update_available"
        manager.updater.version = "1.2.3"

        # Enable frozen mode for this test
        original_frozen = Options.is_frozen
        Options.is_frozen = True

        try:
            with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
                "nxdrive.gui.application.Notification"
            ) as mock_notification_class, patch(
                "nxdrive.gui.application.log"
            ) as mock_log:

                mock_translator.get.return_value = "Update available"
                mock_notification = Mock()
                mock_notification_class.return_value = mock_notification

                # Call the method
                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp._update_notification.__get__(app, Application)

                bound_method()

                # Verify change_systray_icon called
                app.change_systray_icon.assert_called_once()

                # Verify log.warning called
                mock_log.warning.assert_called_once()

                # Verify notification sent
                manager.notification_service.send_notification.assert_called_once()
        finally:
            Options.is_frozen = original_frozen

    def test_update_notification_downgrade(self, mock_application):
        """Test update notification for downgrade scenario."""
        app, manager = mock_application
        manager.updater.status = UPDATE_STATUS_INCOMPATIBLE_SERVER
        manager.updater.version = "1.0.0"

        original_frozen = Options.is_frozen
        Options.is_frozen = True

        try:
            with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
                "nxdrive.gui.application.Notification"
            ) as mock_notification_class, patch(
                "nxdrive.gui.application.log"
            ) as mock_log:

                mock_translator.get.return_value = "Downgrade required"
                mock_notification = Mock()
                mock_notification_class.return_value = mock_notification

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp._update_notification.__get__(app, Application)

                bound_method()

                # Verify change_systray_icon called
                app.change_systray_icon.assert_called_once()

                # Verify log.warning called
                mock_log.warning.assert_called_once()

                # Verify Translator.get was called with AUTOUPDATE_DOWNGRADE
                assert any(
                    call[0][0] == "AUTOUPDATE_DOWNGRADE"
                    for call in mock_translator.get.call_args_list
                )
        finally:
            Options.is_frozen = original_frozen

    def test_update_notification_flags(self, mock_application):
        """Test update notification uses correct flags."""
        app, manager = mock_application
        manager.updater.status = "update_available"
        manager.updater.version = "1.2.3"

        original_frozen = Options.is_frozen
        Options.is_frozen = True

        try:
            with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
                "nxdrive.gui.application.Notification"
            ) as mock_notification_class, patch("nxdrive.gui.application.log"):

                mock_translator.get.return_value = "Update available"
                # Mock FLAG constants as integers
                mock_notification_class.FLAG_BUBBLE = 32
                mock_notification_class.FLAG_UNIQUE = 2

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp._update_notification.__get__(app, Application)

                bound_method()

                # Verify Notification constructor called with correct flags
                notification_call = mock_notification_class.call_args
                assert notification_call is not None

                # Check flags (32 | 2 = 34)
                expected_flags = 32 | 2  # FLAG_BUBBLE | FLAG_UNIQUE
                assert notification_call[1]["flags"] == expected_flags
        finally:
            Options.is_frozen = original_frozen

    def test_update_notification_logs_warning(self, mock_application):
        """Test update notification logs warning message."""
        app, manager = mock_application
        manager.updater.status = "update_available"
        manager.updater.version = "1.2.3"

        original_frozen = Options.is_frozen
        Options.is_frozen = True

        try:
            with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
                "nxdrive.gui.application.Notification"
            ), patch("nxdrive.gui.application.log") as mock_log:

                description = "Update available to version 1.2.3"
                mock_translator.get.return_value = description

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp._update_notification.__get__(app, Application)

                bound_method()

                # Verify log.warning called with description
                mock_log.warning.assert_called_once_with(description)
        finally:
            Options.is_frozen = original_frozen

    def test_update_notification_uses_correct_version(self, mock_application):
        """Test update notification uses correct version from updater."""
        app, manager = mock_application
        test_version = "2.5.1"
        manager.updater.status = "update_available"
        manager.updater.version = test_version

        original_frozen = Options.is_frozen
        Options.is_frozen = True

        try:
            with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
                "nxdrive.gui.application.Notification"
            ), patch("nxdrive.gui.application.log"):

                mock_translator.get.return_value = f"Update to {test_version}"

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp._update_notification.__get__(app, Application)

                bound_method()

                # Verify Translator.get called with version values
                assert any(
                    call[1].get("values") == [test_version]
                    for call in mock_translator.get.call_args_list
                )
        finally:
            Options.is_frozen = original_frozen
