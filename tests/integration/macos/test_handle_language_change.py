"""Integration tests for _handle_language_change method - macOS only."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestHandleLanguageChange:
    """Test suite for _handle_language_change method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app.tray_icon = Mock()
        app.osi = Mock()

        yield app, manager

        manager.close()

    def test_handle_language_change_sets_locale(self, mock_application):
        """Test that _handle_language_change sets the locale in manager config."""
        app, manager = mock_application

        test_locale = "fr"

        with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
            "nxdrive.gui.application.MAC", False
        ):
            mock_translator.locale.return_value = test_locale

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_language_change.__get__(app, Application)
            bound_method()

            # Verify locale was set in manager config
            assert manager.get_config("locale") == test_locale

    def test_handle_language_change_updates_context_menu_non_mac(
        self, mock_application
    ):
        """Test that context menu is updated on non-macOS platforms."""
        app, manager = mock_application

        test_locale = "en"
        mock_context_menu = Mock()

        with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
            "nxdrive.gui.application.MAC", False
        ):
            mock_translator.locale.return_value = test_locale
            app.tray_icon.get_context_menu.return_value = mock_context_menu

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_language_change.__get__(app, Application)
            bound_method()

            # Verify context menu was updated
            app.tray_icon.get_context_menu.assert_called_once()
            app.tray_icon.setContextMenu.assert_called_once_with(mock_context_menu)

    def test_handle_language_change_skips_context_menu_on_mac(self, mock_application):
        """Test that context menu update is skipped on macOS."""
        app, manager = mock_application

        test_locale = "de"

        with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
            "nxdrive.gui.application.MAC", True
        ):
            mock_translator.locale.return_value = test_locale

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_language_change.__get__(app, Application)
            bound_method()

            # Verify context menu was NOT updated on macOS
            app.tray_icon.get_context_menu.assert_not_called()
            app.tray_icon.setContextMenu.assert_not_called()

    def test_handle_language_change_registers_contextual_menu(self, mock_application):
        """Test that OSI contextual menu is registered."""
        app, manager = mock_application

        test_locale = "es"

        with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
            "nxdrive.gui.application.MAC", False
        ):
            mock_translator.locale.return_value = test_locale
            app.tray_icon.get_context_menu.return_value = Mock()

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_language_change.__get__(app, Application)
            bound_method()

            # Verify OSI contextual menu registration was called
            app.osi.register_contextual_menu.assert_called_once()

    def test_handle_language_change_various_locales(self, mock_application):
        """Test _handle_language_change with various locale values."""
        app, manager = mock_application

        locales_to_test = ["en", "fr", "de", "es", "ja", "zh_CN"]

        for test_locale in locales_to_test:
            with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
                "nxdrive.gui.application.MAC", True
            ):
                mock_translator.locale.return_value = test_locale

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp._handle_language_change.__get__(app, Application)
                bound_method()

                # Verify OSI registration was called
                app.osi.register_contextual_menu.assert_called()

                # Reset mocks for next iteration
                app.osi.register_contextual_menu.reset_mock()

        # Verify the final locale was set correctly
        final_locale = manager.get_config("locale")
        assert (
            final_locale == locales_to_test[-1]
        ), f"Expected {locales_to_test[-1]}, got {final_locale}"
