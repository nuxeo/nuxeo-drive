"""Integration tests for _show_release_notes method - macOS only."""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from nxdrive.options import Options
from tests.markers import mac_only


@mac_only
class TestShowReleaseNotes:
    """Test suite for _show_release_notes method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager

        yield app, manager

        manager.close()

    def test_show_release_notes_success(self, mock_application):
        """Test successful display of release notes."""
        app, manager = mock_application

        previous_version = "5.0.0"
        current_version = "5.1.0"
        channel = "release"

        manager.get_update_channel = Mock(return_value=channel)

        # Ensure we're not in CI and not alpha
        original_is_alpha = Options.is_alpha
        original_is_frozen = Options.is_frozen
        Options.is_alpha = False
        Options.is_frozen = True  # Required for @if_frozen decorator

        try:
            with patch.dict(os.environ, {}, clear=True), patch(
                "nxdrive.gui.application.Translator"
            ) as mock_translator, patch(
                "nxdrive.gui.application.APP_NAME", "TestApp"
            ), patch(
                "nxdrive.gui.application.log"
            ) as mock_log:

                mock_translator.get.side_effect = lambda key, values=None: f"{key}"

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp._show_release_notes.__get__(app, Application)
                bound_method(previous_version, current_version)

                # Verify display_info was called
                app.display_info.assert_called_once()
                call_args = app.display_info.call_args[0]
                assert "RELEASE_NOTES_TITLE" in call_args[0]
                assert call_args[1] == "RELEASE_NOTES_MSG"
                assert "TestApp" in call_args[2]
                assert current_version in call_args[2]

                # Verify logging
                mock_log.info.assert_called_once()
                log_msg = mock_log.info.call_args[0][0]
                assert previous_version in log_msg
                assert current_version in log_msg
                assert channel in log_msg

        finally:
            Options.is_alpha = original_is_alpha
            Options.is_frozen = original_is_frozen

    def test_show_release_notes_in_ci(self, mock_application):
        """Test that release notes are not shown in CI environment."""
        app, manager = mock_application

        previous_version = "5.0.0"
        current_version = "5.1.0"

        # Set CI environment variable
        with patch.dict(os.environ, {"CI": "true"}):

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._show_release_notes.__get__(app, Application)
            bound_method(previous_version, current_version)

            # Verify display_info was NOT called
            app.display_info.assert_not_called()

    def test_show_release_notes_is_alpha(self, mock_application):
        """Test that release notes are not shown for alpha versions."""
        app, manager = mock_application

        previous_version = "5.0.0"
        current_version = "5.1.0"

        # Set is_alpha to True
        original_is_alpha = Options.is_alpha
        Options.is_alpha = True

        try:
            with patch.dict(os.environ, {}, clear=True):

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp._show_release_notes.__get__(app, Application)
                bound_method(previous_version, current_version)

                # Verify display_info was NOT called
                app.display_info.assert_not_called()

        finally:
            Options.is_alpha = original_is_alpha

    def test_show_release_notes_different_channels(self, mock_application):
        """Test release notes with different update channels."""
        app, manager = mock_application

        previous_version = "5.0.0"
        current_version = "5.1.0"

        test_channels = ["release", "beta", "centralized", "alpha"]

        original_is_alpha = Options.is_alpha
        original_is_frozen = Options.is_frozen
        Options.is_alpha = False
        Options.is_frozen = True

        try:
            for channel in test_channels:
                manager.get_update_channel = Mock(return_value=channel)

                with patch.dict(os.environ, {}, clear=True), patch(
                    "nxdrive.gui.application.Translator"
                ) as mock_translator, patch(
                    "nxdrive.gui.application.APP_NAME", "TestApp"
                ), patch(
                    "nxdrive.gui.application.log"
                ) as mock_log:

                    mock_translator.get.side_effect = lambda key, values=None: f"{key}"

                    from nxdrive.gui.application import Application as RealApp

                    bound_method = RealApp._show_release_notes.__get__(app, Application)
                    bound_method(previous_version, current_version)

                    # Verify logging includes the channel
                    mock_log.info.assert_called_once()
                    log_msg = mock_log.info.call_args[0][0]
                    assert channel in log_msg

                    # Reset for next iteration
                    app.display_info.reset_mock()

        finally:
            Options.is_alpha = original_is_alpha
            Options.is_frozen = original_is_frozen

    def test_show_release_notes_version_format(self, mock_application):
        """Test release notes with various version formats."""
        app, manager = mock_application

        test_cases = [
            ("1.0.0", "2.0.0"),
            ("5.2.3", "5.3.0"),
            ("2023.1.0", "2023.2.0"),
        ]

        manager.get_update_channel = Mock(return_value="release")

        original_is_alpha = Options.is_alpha
        original_is_frozen = Options.is_frozen
        Options.is_alpha = False
        Options.is_frozen = True

        try:
            for previous, current in test_cases:
                with patch.dict(os.environ, {}, clear=True), patch(
                    "nxdrive.gui.application.Translator"
                ) as mock_translator, patch(
                    "nxdrive.gui.application.APP_NAME", "TestApp"
                ), patch(
                    "nxdrive.gui.application.log"
                ):

                    mock_translator.get.side_effect = lambda key, values=None: f"{key}"

                    from nxdrive.gui.application import Application as RealApp

                    bound_method = RealApp._show_release_notes.__get__(app, Application)
                    bound_method(previous, current)

                    # Verify display_info was called with current version
                    app.display_info.assert_called_once()
                    call_args = app.display_info.call_args[0]
                    assert current in call_args[2]

                    # Reset for next iteration
                    app.display_info.reset_mock()

        finally:
            Options.is_alpha = original_is_alpha
            Options.is_frozen = original_is_frozen

    def test_show_release_notes_ci_various_values(self, mock_application):
        """Test that any CI environment variable value prevents showing notes."""
        app, manager = mock_application

        previous_version = "5.0.0"
        current_version = "5.1.0"

        ci_values = ["true", "1", "yes", "TRUE", "True"]

        for ci_value in ci_values:
            with patch.dict(os.environ, {"CI": ci_value}):

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp._show_release_notes.__get__(app, Application)
                bound_method(previous_version, current_version)

                # Verify display_info was NOT called
                app.display_info.assert_not_called()

                # Reset for next iteration
                app.display_info.reset_mock()
