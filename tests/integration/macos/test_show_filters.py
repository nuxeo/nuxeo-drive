"""Integration tests for show_filters method - macOS only."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestShowFilters:
    """Test suite for show_filters method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        manager = Manager(tmp())

        engine = Mock()
        engine.uid = "test_engine"

        app = MagicMock(spec=Application)
        app.manager = manager
        app.filters_dlg = None
        app._center_on_screen = Mock()
        app._show_window = Mock()
        app.settings_window = Mock()

        yield app, manager, engine
        manager.close()

    def test_show_filters_new_dialog(self, mock_application):
        """Test showing filters dialog when none exists."""
        app, manager, engine = mock_application

        with patch("nxdrive.gui.application.DocumentsDialog") as mock_dialog_class:
            mock_dialog = Mock()
            mock_dialog.destroyed = Mock()
            mock_dialog.destroyed.connect = Mock()
            mock_dialog_class.return_value = mock_dialog

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_filters.__get__(app, Application)

            bound_method(engine)

            mock_dialog_class.assert_called_once_with(app, engine)
            app._center_on_screen.assert_called_once_with(app.settings_window)
            app._show_window.assert_called_once_with(mock_dialog)
            assert app.filters_dlg == mock_dialog

    def test_show_filters_close_existing(self, mock_application):
        """Test showing filters closes existing dialog first."""
        app, manager, engine = mock_application

        existing_dialog = Mock()
        existing_dialog.close = Mock()
        app.filters_dlg = existing_dialog

        with patch("nxdrive.gui.application.DocumentsDialog") as mock_dialog_class:
            mock_dialog = Mock()
            mock_dialog.destroyed = Mock()
            mock_dialog.destroyed.connect = Mock()
            mock_dialog_class.return_value = mock_dialog

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_filters.__get__(app, Application)

            bound_method(engine)

            existing_dialog.close.assert_called_once()
            assert app.filters_dlg == mock_dialog

    def test_show_filters_close_settings_too(self, mock_application):
        """Test showing filters also closes settings if attribute set."""
        app, manager, engine = mock_application
        app.close_settings_too = True

        with patch("nxdrive.gui.application.DocumentsDialog") as mock_dialog_class:
            mock_dialog = Mock()
            mock_dialog.destroyed = Mock()
            mock_dialog.destroyed.connect = Mock()
            mock_dialog_class.return_value = mock_dialog

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_filters.__get__(app, Application)

            bound_method(engine)

            # Verify settings window close was connected
            assert mock_dialog.destroyed.connect.call_count == 2
            assert not hasattr(app, "close_settings_too")
