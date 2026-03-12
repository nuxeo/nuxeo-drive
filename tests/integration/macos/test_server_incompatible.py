"""Integration tests for _server_incompatible method - macOS only."""

from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestServerIncompatible:
    """Test suite for _server_incompatible method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager

        # Mock manager.version as a property using PropertyMock
        type(manager).version = PropertyMock(return_value="5.0.0")

        # Mock manager methods to avoid real calls
        manager.set_update_channel = Mock()
        manager.updater.update = Mock()

        yield app, manager

        manager.close()

    def test_server_incompatible_with_downgrade_version_accept(self, mock_application):
        """Test server incompatible dialog when downgrade version exists and user accepts."""
        app, manager = mock_application

        downgrade_version = "4.5.0"
        manager.updater.version = downgrade_version
        manager.updater.available_version = None

        with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
            "nxdrive.gui.application.APP_NAME", "TestApp"
        ):

            mock_translator.get.side_effect = lambda key, values=None: f"{key}_{values}"

            # Mock the question dialog
            mock_dialog = Mock()
            mock_dialog.exec = Mock()

            # Create button mocks
            reject_button = Mock()
            accept_button = Mock()

            def add_button_side_effect(text, role):
                if "CONTINUE_USING" in text or text.startswith("CONTINUE_USING"):
                    return reject_button
                elif "DOWNGRADE_TO" in text or text.startswith("DOWNGRADE_TO"):
                    return accept_button
                return Mock()

            mock_dialog.addButton = Mock(side_effect=add_button_side_effect)
            mock_dialog.clickedButton.return_value = accept_button

            app.question.return_value = mock_dialog

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._server_incompatible.__get__(app, Application)
            bound_method()

            # Verify dialog was shown
            app.question.assert_called_once()
            mock_dialog.exec.assert_called_once()

            # Verify update was triggered
            manager.updater.update.assert_called_once_with(downgrade_version)

            # Verify update was triggered
            manager.updater.update.assert_called_once_with(downgrade_version)

    def test_server_incompatible_with_downgrade_version_reject(self, mock_application):
        """Test server incompatible dialog when downgrade version exists and user rejects."""
        app, manager = mock_application

        downgrade_version = "4.5.0"
        manager.updater.version = downgrade_version
        manager.updater.available_version = None

        with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
            "nxdrive.gui.application.APP_NAME", "TestApp"
        ):

            mock_translator.get.side_effect = lambda key, values=None: f"{key}_{values}"

            # Mock the question dialog
            mock_dialog = Mock()
            mock_dialog.exec = Mock()

            # Create button mocks
            reject_button = Mock()
            accept_button = Mock()

            def add_button_side_effect(text, role):
                if "CONTINUE_USING" in text or text.startswith("CONTINUE_USING"):
                    return reject_button
                elif "DOWNGRADE_TO" in text or text.startswith("DOWNGRADE_TO"):
                    return accept_button
                return Mock()

            mock_dialog.addButton = Mock(side_effect=add_button_side_effect)
            mock_dialog.clickedButton.return_value = reject_button

            app.question.return_value = mock_dialog

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._server_incompatible.__get__(app, Application)
            bound_method()

            # Verify dialog was shown
            app.question.assert_called_once()
            mock_dialog.exec.assert_called_once()

            # Verify update was NOT triggered
            manager.updater.update.assert_not_called()

    def test_server_incompatible_without_downgrade_version(self, mock_application):
        """Test server incompatible dialog when no downgrade version is available."""
        app, manager = mock_application

        manager.updater.version = None
        manager.updater.available_version = None

        with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
            "nxdrive.gui.application.APP_NAME", "TestApp"
        ):

            mock_translator.get.side_effect = lambda key, values=None: f"{key}_{values}"

            # Mock the question dialog
            mock_dialog = Mock()
            mock_dialog.exec = Mock()

            continue_button = Mock()
            mock_dialog.addButton = Mock(return_value=continue_button)

            app.question.return_value = mock_dialog

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._server_incompatible.__get__(app, Application)
            bound_method()

            # Verify dialog was shown
            app.question.assert_called_once()
            mock_dialog.exec.assert_called_once()

            # Verify only one button (CONTINUE) was added
            assert mock_dialog.addButton.call_count == 1

            # Verify update was NOT triggered
            manager.updater.update.assert_not_called()

    def test_server_incompatible_uses_available_version_fallback(
        self, mock_application
    ):
        """Test that available_version is used when version is None."""
        app, manager = mock_application

        available_version = "4.3.0"
        manager.updater.version = None
        manager.updater.available_version = available_version

        with patch("nxdrive.gui.application.Translator") as mock_translator, patch(
            "nxdrive.gui.application.APP_NAME", "TestApp"
        ):

            mock_translator.get.side_effect = lambda key, values=None: f"{key}_{values}"

            mock_dialog = Mock()
            mock_dialog.exec = Mock()
            accept_button = Mock()
            mock_dialog.addButton = Mock(return_value=accept_button)
            mock_dialog.clickedButton.return_value = accept_button

            app.question.return_value = mock_dialog

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._server_incompatible.__get__(app, Application)
            bound_method()

            # Verify update was triggered with available_version
            manager.updater.update.assert_called_once_with(available_version)
