"""Integration tests for show_metrics_acceptance method - macOS only."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from nxdrive.options import Options
from nxdrive.qt import constants as qt
from tests.markers import mac_only


@mac_only
class TestShowMetricsAcceptance:
    """Test suite for show_metrics_acceptance method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app.icon = Mock()

        yield app, manager

        manager.close()

    def test_show_metrics_acceptance_dialog_displayed(self, mock_application):
        """Test show_metrics_acceptance displays dialog."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QCheckBox"
        ), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ), patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get = Mock(return_value="Test String")

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_metrics_acceptance.__get__(app, Application)
            bound_method()

            # Verify dialog was shown and executed
            mock_dialog.show.assert_called_once()
            mock_dialog.exec_.assert_called_once()

    def test_show_metrics_acceptance_creates_metrics_state_file(self, mock_application):
        """Test show_metrics_acceptance creates metrics.state file."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QCheckBox"
        ), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ), patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get = Mock(return_value="Test")

            # Reset options
            Options.use_analytics = False
            Options.use_sentry = False

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_metrics_acceptance.__get__(app, Application)
            bound_method()

            # Verify metrics.state file was created
            metrics_file = Options.nxdrive_home / "metrics.state"
            assert metrics_file.exists()

    def test_show_metrics_acceptance_analytics_enabled(self, mock_application):
        """Test show_metrics_acceptance with analytics enabled."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QCheckBox"
        ) as mock_checkbox_class, patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ), patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get = Mock(return_value="Test")

            # Mock checkboxes
            mock_analytics_cb = Mock()
            mock_sentry_cb = Mock()
            mock_checkbox_class.side_effect = [mock_sentry_cb, mock_analytics_cb]

            # Simulate user checking analytics
            Options.use_analytics = True
            Options.use_sentry = False

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_metrics_acceptance.__get__(app, Application)
            bound_method()

            # Verify metrics.state contains analytics
            metrics_file = Options.nxdrive_home / "metrics.state"
            content = metrics_file.read_text(encoding="utf-8")
            assert "analytics" in content

    def test_show_metrics_acceptance_sentry_enabled(self, mock_application):
        """Test show_metrics_acceptance with sentry enabled."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QCheckBox"
        ), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ), patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get = Mock(return_value="Test")

            # Simulate user checking sentry
            Options.use_analytics = False
            Options.use_sentry = True

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_metrics_acceptance.__get__(app, Application)
            bound_method()

            # Verify metrics.state contains sentry
            metrics_file = Options.nxdrive_home / "metrics.state"
            content = metrics_file.read_text(encoding="utf-8")
            assert "sentry" in content

    def test_show_metrics_acceptance_both_enabled(self, mock_application):
        """Test show_metrics_acceptance with both analytics and sentry enabled."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QCheckBox"
        ), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ), patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get = Mock(return_value="Test")

            # Enable both options
            Options.use_analytics = True
            Options.use_sentry = True

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_metrics_acceptance.__get__(app, Application)
            bound_method()

            # Verify metrics.state contains both
            metrics_file = Options.nxdrive_home / "metrics.state"
            content = metrics_file.read_text(encoding="utf-8")
            assert "analytics" in content
            assert "sentry" in content

    def test_show_metrics_acceptance_both_disabled(self, mock_application):
        """Test show_metrics_acceptance with both options disabled."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QCheckBox"
        ), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ), patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get = Mock(return_value="Test")

            # Disable both options (note: use_sentry may be forcibly enabled in dev)
            Options.use_analytics = False
            Options.use_sentry = False

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_metrics_acceptance.__get__(app, Application)
            bound_method()

            # Verify metrics.state file content
            metrics_file = Options.nxdrive_home / "metrics.state"
            content = metrics_file.read_text(encoding="utf-8")

            # In dev, sentry is forcibly enabled, so file may contain "sentry"
            # In production with both disabled, file should be empty or just newline
            assert content in ("", "\n", "sentry", "sentry\n")

    def test_show_metrics_acceptance_dialog_title_set(self, mock_application):
        """Test show_metrics_acceptance sets dialog title."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QCheckBox"
        ), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ), patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get = Mock(return_value="Share Metrics")

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_metrics_acceptance.__get__(app, Application)
            bound_method()

            # Verify setWindowTitle was called
            mock_dialog.setWindowTitle.assert_called_once()
            # Verify setWindowIcon was called with app.icon
            mock_dialog.setWindowIcon.assert_called_once_with(app.icon)

    def test_show_metrics_acceptance_dialog_resized(self, mock_application):
        """Test show_metrics_acceptance resizes dialog to 400x200."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QCheckBox"
        ), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ), patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get = Mock(return_value="Test")

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_metrics_acceptance.__get__(app, Application)
            bound_method()

            # Verify resize was called with 400, 200
            mock_dialog.resize.assert_called_once_with(400, 200)

    def test_show_metrics_acceptance_checkboxes_created(self, mock_application):
        """Test show_metrics_acceptance creates checkboxes for analytics and sentry."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QCheckBox"
        ) as mock_checkbox_class, patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ), patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get = Mock(return_value="Test")

            mock_checkbox1 = Mock()
            mock_checkbox2 = Mock()
            mock_checkbox_class.side_effect = [mock_checkbox1, mock_checkbox2]

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_metrics_acceptance.__get__(app, Application)
            bound_method()

            # Verify two checkboxes were created
            assert mock_checkbox_class.call_count == 2
            # Verify stateChanged signals were connected
            mock_checkbox1.stateChanged.connect.assert_called_once()
            mock_checkbox2.stateChanged.connect.assert_called_once()

    def test_show_metrics_acceptance_layout_set(self, mock_application):
        """Test show_metrics_acceptance sets layout on dialog."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QCheckBox"
        ), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ), patch(
            "nxdrive.gui.application.QVBoxLayout"
        ) as mock_layout_class:
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get = Mock(return_value="Test")
            mock_layout = Mock()
            mock_layout_class.return_value = mock_layout

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_metrics_acceptance.__get__(app, Application)
            bound_method()

            # Verify setLayout was called with the layout
            mock_dialog.setLayout.assert_called_once_with(mock_layout)

    def test_show_metrics_acceptance_button_box_created(self, mock_application):
        """Test show_metrics_acceptance creates dialog button box with Apply button."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QCheckBox"
        ), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttonbox_class, patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get = Mock(return_value="Test")
            mock_buttons = Mock()
            mock_buttonbox_class.return_value = mock_buttons

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.show_metrics_acceptance.__get__(app, Application)
            bound_method()

            # Verify button box was created and configured
            mock_buttonbox_class.assert_called_once()
            mock_buttons.setStandardButtons.assert_called_once_with(qt.Apply)
            mock_buttons.clicked.connect.assert_called_once_with(mock_dialog.close)
