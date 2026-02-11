"""Integration tests for _select_account method - macOS only."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.engine.engine import Engine
from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from nxdrive.qt import constants as qt
from tests.markers import mac_only


@mac_only
class TestSelectAccount:
    """Test suite for _select_account method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app.icon = Mock()

        yield app, manager

        manager.close()

    def test_select_account_user_accepts(self, mock_application):
        """Test _select_account when user selects an account and accepts."""
        app, manager = mock_application

        # Create mock engines
        mock_engine1 = Mock(spec=Engine)
        mock_engine1.get_user_full_name.return_value = "John Doe"
        mock_engine1.remote_user = "jdoe"
        mock_engine1.server_url = "https://server1.example.com"

        mock_engine2 = Mock(spec=Engine)
        mock_engine2.get_user_full_name.return_value = "Jane Smith"
        mock_engine2.remote_user = "jsmith"
        mock_engine2.server_url = "https://server2.example.com"

        engines = [mock_engine1, mock_engine2]

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QComboBox"
        ) as mock_combo_class, patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttons_class, patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_translator.get.return_value = "Select Account"

            # Setup dialog mock
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Setup combo box mock
            mock_combo = Mock()
            mock_combo_class.return_value = mock_combo
            mock_combo.currentData.return_value = mock_engine1

            # Setup buttons mock
            mock_buttons = Mock()
            mock_buttons_class.return_value = mock_buttons

            # Simulate user accepting
            def exec_side_effect():
                # Simulate clicking OK button by triggering accepted signal
                if mock_buttons.accepted.connect.called:
                    accept_callback = mock_buttons.accepted.connect.call_args[0][0]
                    accept_callback()
                return 1  # QDialog.Accepted

            mock_dialog.exec.side_effect = exec_side_effect

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._select_account.__get__(app, Application)
            result = bound_method(engines)

            # Verify the selected engine is returned
            assert result == mock_engine1

            # Verify combo box was populated with engines
            assert mock_combo.addItem.call_count == 2
            mock_combo.addItem.assert_any_call(
                "John Doe • https://server1.example.com", mock_engine1
            )
            mock_combo.addItem.assert_any_call(
                "Jane Smith • https://server2.example.com", mock_engine2
            )

    def test_select_account_user_cancels(self, mock_application):
        """Test _select_account when user cancels the dialog."""
        app, manager = mock_application

        # Create mock engines
        mock_engine1 = Mock(spec=Engine)
        mock_engine1.get_user_full_name.return_value = "John Doe"
        mock_engine1.remote_user = "jdoe"
        mock_engine1.server_url = "https://server.example.com"

        engines = [mock_engine1]

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QComboBox"
        ) as mock_combo_class, patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttons_class, patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_translator.get.return_value = "Select Account"

            # Setup dialog mock
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Setup combo box mock
            mock_combo = Mock()
            mock_combo_class.return_value = mock_combo

            # Setup buttons mock
            mock_buttons = Mock()
            mock_buttons_class.return_value = mock_buttons

            # Simulate user rejecting
            def exec_side_effect():
                # Simulate clicking Cancel button by triggering rejected signal
                if mock_buttons.rejected.connect.called:
                    close_callback = mock_buttons.rejected.connect.call_args[0][0]
                    close_callback()
                return 0  # QDialog.Rejected

            mock_dialog.exec.side_effect = exec_side_effect

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._select_account.__get__(app, Application)
            result = bound_method(engines)

            # Verify None is returned when user cancels
            assert result is None

    def test_select_account_single_engine(self, mock_application):
        """Test _select_account with single engine in list."""
        app, manager = mock_application

        # Create mock engine
        mock_engine = Mock(spec=Engine)
        mock_engine.get_user_full_name.return_value = "Test User"
        mock_engine.remote_user = "testuser"
        mock_engine.server_url = "https://test.example.com"

        engines = [mock_engine]

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QComboBox"
        ) as mock_combo_class, patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttons_class, patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_translator.get.return_value = "Select Account"

            # Setup dialog mock
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Setup combo box mock
            mock_combo = Mock()
            mock_combo_class.return_value = mock_combo
            mock_combo.currentData.return_value = mock_engine

            # Setup buttons mock
            mock_buttons = Mock()
            mock_buttons_class.return_value = mock_buttons

            # Simulate user accepting
            def exec_side_effect():
                if mock_buttons.accepted.connect.called:
                    accept_callback = mock_buttons.accepted.connect.call_args[0][0]
                    accept_callback()
                return 1

            mock_dialog.exec.side_effect = exec_side_effect

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._select_account.__get__(app, Application)
            result = bound_method(engines)

            # Verify the selected engine is returned
            assert result == mock_engine

            # Verify combo box was populated with single engine
            mock_combo.addItem.assert_called_once_with(
                "Test User • https://test.example.com", mock_engine
            )

    def test_select_account_activated_callback(self, mock_application):
        """Test _select_account activated signal triggers account_selected callback."""
        app, manager = mock_application

        # Create mock engines
        mock_engine1 = Mock(spec=Engine)
        mock_engine1.get_user_full_name.return_value = "User One"
        mock_engine1.remote_user = "user1"
        mock_engine1.server_url = "https://server1.example.com"

        mock_engine2 = Mock(spec=Engine)
        mock_engine2.get_user_full_name.return_value = "User Two"
        mock_engine2.remote_user = "user2"
        mock_engine2.server_url = "https://server2.example.com"

        engines = [mock_engine1, mock_engine2]

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QComboBox"
        ) as mock_combo_class, patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttons_class, patch(
            "nxdrive.gui.application.QVBoxLayout"
        ), patch(
            "nxdrive.gui.application.log"
        ) as mock_log:
            mock_translator.get.return_value = "Select Account"

            # Setup dialog mock
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Setup combo box mock
            mock_combo = Mock()
            mock_combo_class.return_value = mock_combo
            mock_combo.itemData.return_value = mock_engine2
            mock_combo.itemText.return_value = "User Two • https://server2.example.com"
            mock_combo.currentData.return_value = mock_engine2

            # Setup buttons mock
            mock_buttons = Mock()
            mock_buttons_class.return_value = mock_buttons

            # Simulate activated signal and user accepting
            def exec_side_effect():
                # Simulate selecting second item
                if mock_combo.activated.connect.called:
                    activated_callback = mock_combo.activated.connect.call_args[0][0]
                    activated_callback(1)  # Select index 1
                # Simulate clicking OK
                if mock_buttons.accepted.connect.called:
                    accept_callback = mock_buttons.accepted.connect.call_args[0][0]
                    accept_callback()
                return 1

            mock_dialog.exec.side_effect = exec_side_effect

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._select_account.__get__(app, Application)
            result = bound_method(engines)

            # Verify the selected engine is returned
            assert result == mock_engine2

            # Verify logging occurred
            mock_log.debug.assert_called()

    def test_select_account_dialog_title_and_icon(self, mock_application):
        """Test _select_account sets correct dialog title and icon."""
        app, manager = mock_application

        # Create mock engine
        mock_engine = Mock(spec=Engine)
        mock_engine.get_user_full_name.return_value = "Test User"
        mock_engine.remote_user = "testuser"
        mock_engine.server_url = "https://test.example.com"

        engines = [mock_engine]

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QComboBox"
        ) as mock_combo_class, patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttons_class, patch(
            "nxdrive.gui.application.QVBoxLayout"
        ), patch(
            "nxdrive.gui.application.APP_NAME", "TestApp"
        ):
            mock_translator.get.side_effect = (
                lambda key, values=None: f"Translated: {key}"
            )

            # Setup dialog mock
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Setup combo box mock
            mock_combo = Mock()
            mock_combo_class.return_value = mock_combo
            mock_combo.currentData.return_value = mock_engine

            # Setup buttons mock
            mock_buttons = Mock()
            mock_buttons_class.return_value = mock_buttons

            # Simulate user accepting
            def exec_side_effect():
                if mock_buttons.accepted.connect.called:
                    accept_callback = mock_buttons.accepted.connect.call_args[0][0]
                    accept_callback()
                return 1

            mock_dialog.exec.side_effect = exec_side_effect

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._select_account.__get__(app, Application)
            bound_method(engines)

            # Verify dialog title was set
            mock_dialog.setWindowTitle.assert_called_once()
            # Verify dialog icon was set
            mock_dialog.setWindowIcon.assert_called_once_with(app.icon)

    def test_select_account_button_configuration(self, mock_application):
        """Test _select_account configures buttons correctly."""
        app, manager = mock_application

        # Create mock engine
        mock_engine = Mock(spec=Engine)
        mock_engine.get_user_full_name.return_value = "Test User"
        mock_engine.remote_user = "testuser"
        mock_engine.server_url = "https://test.example.com"

        engines = [mock_engine]

        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator, patch("nxdrive.gui.application.QLabel"), patch(
            "nxdrive.gui.application.QComboBox"
        ) as mock_combo_class, patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttons_class, patch(
            "nxdrive.gui.application.QVBoxLayout"
        ):
            mock_translator.get.return_value = "Select Account"

            # Setup dialog mock
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Setup combo box mock
            mock_combo = Mock()
            mock_combo_class.return_value = mock_combo
            mock_combo.currentData.return_value = mock_engine

            # Setup buttons mock
            mock_buttons = Mock()
            mock_buttons_class.return_value = mock_buttons

            # Simulate user accepting
            def exec_side_effect():
                if mock_buttons.accepted.connect.called:
                    accept_callback = mock_buttons.accepted.connect.call_args[0][0]
                    accept_callback()
                return 1

            mock_dialog.exec.side_effect = exec_side_effect

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._select_account.__get__(app, Application)
            bound_method(engines)

            # Verify buttons were configured with OK and Cancel
            mock_buttons.setStandardButtons.assert_called_once_with(qt.Ok | qt.Cancel)
            # Verify accepted and rejected signals were connected
            mock_buttons.accepted.connect.assert_called_once()
            mock_buttons.rejected.connect.assert_called_once()
