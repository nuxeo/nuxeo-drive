"""Integration tests for _wrong_channel method - macOS only."""

from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestWrongChannel:
    """Test suite for _wrong_channel method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        manager.prompted_wrong_channel = False

        # Mock manager.version as a property using PropertyMock
        type(manager).version = PropertyMock(return_value="5.0.0")

        # Mock manager methods to avoid real calls
        manager.set_update_channel = Mock()
        manager.updater.update = Mock()

        yield app, manager

        manager.close()

    def test_wrong_channel_switch_channel(self, mock_application):
        """Test wrong channel dialog when user chooses to switch channel."""
        app, manager = mock_application

        downgrade_version = "4.5.0"
        version_channel = "release"
        current_channel = "beta"

        manager.updater.version = downgrade_version
        manager.updater.available_version = None
        manager.updater.get_version_channel = Mock(return_value=version_channel)
        manager.get_update_channel = Mock(return_value=current_channel)

        with patch("nxdrive.gui.application.Translator") as mock_translator:

            mock_translator.get.side_effect = lambda key, values=None: f"{key}_{values}"

            # Mock the question dialog
            mock_dialog = Mock()
            mock_dialog.exec = Mock()

            # Create button mocks
            switch_button = Mock()
            downgrade_button = Mock()

            def add_button_side_effect(text, role):
                if "USE_CHANNEL" in text or text.startswith("USE_CHANNEL"):
                    return switch_button
                elif "DOWNGRADE_TO" in text or text.startswith("DOWNGRADE_TO"):
                    return downgrade_button
                return Mock()

            mock_dialog.addButton = Mock(side_effect=add_button_side_effect)
            mock_dialog.clickedButton.return_value = switch_button

            app.question.return_value = mock_dialog

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._wrong_channel.__get__(app, Application)
            bound_method()

            # Verify dialog was shown
            app.question.assert_called_once()
            mock_dialog.exec.assert_called_once()

            # Verify channel switch was triggered
            manager.set_update_channel.assert_called_once_with(version_channel)

            # Verify update was NOT triggered
            manager.updater.update.assert_not_called()

            # Verify flag was set
            assert manager.prompted_wrong_channel is True

    def test_wrong_channel_downgrade(self, mock_application):
        """Test wrong channel dialog when user chooses to downgrade."""
        app, manager = mock_application

        downgrade_version = "4.5.0"
        version_channel = "release"
        current_channel = "beta"

        manager.updater.version = downgrade_version
        manager.updater.available_version = None
        manager.updater.get_version_channel = Mock(return_value=version_channel)
        manager.get_update_channel = Mock(return_value=current_channel)

        with patch("nxdrive.gui.application.Translator") as mock_translator:

            mock_translator.get.side_effect = lambda key, values=None: f"{key}_{values}"

            # Mock the question dialog
            mock_dialog = Mock()
            mock_dialog.exec = Mock()

            # Create button mocks
            switch_button = Mock()
            downgrade_button = Mock()

            def add_button_side_effect(text, role):
                if "USE_CHANNEL" in text or text.startswith("USE_CHANNEL"):
                    return switch_button
                elif "DOWNGRADE_TO" in text or text.startswith("DOWNGRADE_TO"):
                    return downgrade_button
                return Mock()

            mock_dialog.addButton = Mock(side_effect=add_button_side_effect)
            mock_dialog.clickedButton.return_value = downgrade_button

            app.question.return_value = mock_dialog

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._wrong_channel.__get__(app, Application)
            bound_method()

            # Verify dialog was shown
            app.question.assert_called_once()
            mock_dialog.exec.assert_called_once()

            # Verify update was triggered
            manager.updater.update.assert_called_once_with(downgrade_version)

            # Verify channel switch was NOT triggered
            manager.set_update_channel.assert_not_called()

            # Verify flag was set
            assert manager.prompted_wrong_channel is True

    def test_wrong_channel_already_prompted(self, mock_application):
        """Test that dialog is not shown if already prompted."""
        app, manager = mock_application

        # Set flag to True
        manager.prompted_wrong_channel = True

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp._wrong_channel.__get__(app, Application)
        bound_method()

        # Verify dialog was NOT shown
        app.question.assert_not_called()

    def test_wrong_channel_no_action_taken(self, mock_application):
        """Test wrong channel dialog when user clicks neither button."""
        app, manager = mock_application

        downgrade_version = "4.5.0"
        version_channel = "release"
        current_channel = "beta"

        manager.updater.version = downgrade_version
        manager.updater.available_version = None
        manager.updater.get_version_channel = Mock(return_value=version_channel)
        manager.get_update_channel = Mock(return_value=current_channel)

        with patch("nxdrive.gui.application.Translator") as mock_translator:

            mock_translator.get.side_effect = lambda key, values=None: f"{key}_{values}"

            # Mock the question dialog
            mock_dialog = Mock()
            mock_dialog.exec = Mock()

            # Create button mocks
            switch_button = Mock()
            downgrade_button = Mock()
            other_button = Mock()

            def add_button_side_effect(text, role):
                if "USE_CHANNEL" in text or text.startswith("USE_CHANNEL"):
                    return switch_button
                elif "DOWNGRADE_TO" in text or text.startswith("DOWNGRADE_TO"):
                    return downgrade_button
                return Mock()

            mock_dialog.addButton = Mock(side_effect=add_button_side_effect)
            mock_dialog.clickedButton.return_value = other_button

            app.question.return_value = mock_dialog

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._wrong_channel.__get__(app, Application)
            bound_method()

            # Verify dialog was shown
            app.question.assert_called_once()
            mock_dialog.exec.assert_called_once()

            # Verify neither action was triggered
            manager.set_update_channel.assert_not_called()
            manager.updater.update.assert_not_called()

    def test_wrong_channel_uses_available_version_fallback(self, mock_application):
        """Test that available_version is used when version is None."""
        app, manager = mock_application

        available_version = "4.3.0"
        version_channel = "release"
        current_channel = "beta"

        manager.updater.version = None
        manager.updater.available_version = available_version
        manager.updater.get_version_channel = Mock(return_value=version_channel)
        manager.get_update_channel = Mock(return_value=current_channel)

        with patch("nxdrive.gui.application.Translator") as mock_translator:

            mock_translator.get.side_effect = lambda key, values=None: f"{key}_{values}"

            mock_dialog = Mock()
            mock_dialog.exec = Mock()
            downgrade_button = Mock()

            def add_button_side_effect(text, role):
                if "DOWNGRADE_TO" in text or text.startswith("DOWNGRADE_TO"):
                    return downgrade_button
                return Mock()

            mock_dialog.addButton = Mock(side_effect=add_button_side_effect)
            mock_dialog.clickedButton.return_value = downgrade_button

            app.question.return_value = mock_dialog

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._wrong_channel.__get__(app, Application)
            bound_method()

            # Verify update was triggered with available_version
            manager.updater.update.assert_called_once_with(available_version)
