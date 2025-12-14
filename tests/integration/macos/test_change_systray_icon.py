"""Integration tests for Application.change_systray_icon method."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from nxdrive.updater.constants import UPDATE_STATUS_UP_TO_DATE
from tests.markers import mac_only


@mac_only
class TestChangeSystrayIcon:
    """Tests for Application.change_systray_icon."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock application with manager."""
        manager = Manager(tmp())

        # Create mocked Application
        app = MagicMock(spec=Application)
        app.manager = manager
        app.set_icon_state = Mock()

        yield app, manager

    def test_change_systray_icon_update_state(self, mock_application):
        """Test icon changes to update state when update is available."""
        app, manager = mock_application
        manager.updater.status = "update_available"

        with patch("nxdrive.gui.application.Translator") as mock_translator:
            mock_translator.get.return_value = "Mocked text"

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.change_systray_icon.__get__(app, Application)

            bound_method()

            app.set_icon_state.assert_called_once_with("update")

    def test_change_systray_icon_offline(self, mock_application):
        """Test icon changes to error state when all engines are offline."""
        app, manager = mock_application
        manager.updater.status = UPDATE_STATUS_UP_TO_DATE

        engine = Mock()
        engine.is_syncing.return_value = False
        engine.has_invalid_credentials.return_value = False
        engine.is_paused.return_value = False
        engine.is_offline.return_value = True
        engine.get_conflicts.return_value = []

        manager.engines = {"engine1": engine}

        with patch("nxdrive.gui.application.Action") as mock_action, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator:
            mock_translator.get.return_value = "OFFLINE"

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.change_systray_icon.__get__(app, Application)

            bound_method()

            app.set_icon_state.assert_called_once_with("error")
            mock_action.assert_called_once_with("OFFLINE")

    def test_change_systray_icon_invalid_credentials(self, mock_application):
        """Test icon changes to error state when all engines have invalid credentials."""
        app, manager = mock_application
        manager.updater.status = UPDATE_STATUS_UP_TO_DATE

        engine = Mock()
        engine.is_syncing.return_value = False
        engine.has_invalid_credentials.return_value = True
        engine.is_paused.return_value = False
        engine.is_offline.return_value = False
        engine.get_conflicts.return_value = []

        manager.engines = {"engine1": engine}

        with patch("nxdrive.gui.application.Action") as mock_action, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator:
            mock_translator.get.return_value = "AUTH_EXPIRED"

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.change_systray_icon.__get__(app, Application)

            bound_method()

            app.set_icon_state.assert_called_once_with("error")
            mock_action.assert_called_once_with("AUTH_EXPIRED")

    def test_change_systray_icon_no_engines(self, mock_application):
        """Test icon changes to error when no engines (offline flag stays True)."""
        app, manager = mock_application
        manager.engines = {}
        manager.updater.status = UPDATE_STATUS_UP_TO_DATE

        with patch("nxdrive.gui.application.Action") as mock_action, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator:
            mock_translator.get.return_value = "Mocked text"

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.change_systray_icon.__get__(app, Application)

            bound_method()

            # With no engines, offline=True stays True, so state becomes "error"
            app.set_icon_state.assert_called_once_with("error")
            # Action is instantiated (not finish_action) when offline
            mock_action.assert_called_once_with("Mocked text")

    def test_change_systray_icon_paused(self, mock_application):
        """Test icon changes to paused state when all engines are paused."""
        app, manager = mock_application
        manager.updater.status = UPDATE_STATUS_UP_TO_DATE

        engine = Mock()
        engine.is_syncing.return_value = False
        engine.has_invalid_credentials.return_value = False
        engine.is_paused.return_value = True
        engine.is_offline.return_value = False
        engine.get_conflicts.return_value = []

        manager.engines = {"engine1": engine}

        with patch("nxdrive.gui.application.Action") as mock_action:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.change_systray_icon.__get__(app, Application)

            bound_method()

            app.set_icon_state.assert_called_once_with("paused")
            mock_action.finish_action.assert_called_once()

    def test_change_systray_icon_syncing(self, mock_application):
        """Test icon changes to syncing state when engine is syncing."""
        app, manager = mock_application
        manager.updater.status = UPDATE_STATUS_UP_TO_DATE

        engine = Mock()
        engine.is_syncing.return_value = True
        engine.has_invalid_credentials.return_value = False
        engine.is_paused.return_value = False
        engine.is_offline.return_value = False
        engine.get_conflicts.return_value = []

        manager.engines = {"engine1": engine}

        with patch("nxdrive.gui.application.Action"):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.change_systray_icon.__get__(app, Application)

            bound_method()

            app.set_icon_state.assert_called_once_with("syncing")

    def test_change_systray_icon_conflict(self, mock_application):
        """Test icon changes to conflict state when engine has conflicts."""
        app, manager = mock_application
        manager.updater.status = UPDATE_STATUS_UP_TO_DATE

        engine = Mock()
        engine.is_syncing.return_value = False
        engine.has_invalid_credentials.return_value = False
        engine.is_paused.return_value = False
        engine.is_offline.return_value = False
        engine.get_conflicts.return_value = [Mock()]

        manager.engines = {"engine1": engine}

        with patch("nxdrive.gui.application.Action"):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.change_systray_icon.__get__(app, Application)

            bound_method()

            app.set_icon_state.assert_called_once_with("conflict")

    def test_change_systray_icon_idle(self, mock_application):
        """Test icon changes to idle state when engine is idle."""
        app, manager = mock_application
        manager.updater.status = UPDATE_STATUS_UP_TO_DATE

        engine = Mock()
        engine.is_syncing.return_value = False
        engine.has_invalid_credentials.return_value = False
        engine.is_paused.return_value = False
        engine.is_offline.return_value = False
        engine.get_conflicts.return_value = []

        manager.engines = {"engine1": engine}

        with patch("nxdrive.gui.application.Action") as mock_action:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.change_systray_icon.__get__(app, Application)

            bound_method()

            app.set_icon_state.assert_called_once_with("idle")
            mock_action.finish_action.assert_called_once()
