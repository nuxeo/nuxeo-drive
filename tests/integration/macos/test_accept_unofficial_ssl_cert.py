"""Integration tests for accept_unofficial_ssl_cert method - macOS only."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from nxdrive.qt import constants as qt
from tests.markers import mac_only


@mac_only
class TestAcceptUnofficialSslCert:
    """Test suite for accept_unofficial_ssl_cert method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app.icon = Mock()

        yield app, manager

        manager.close()

    def test_accept_unofficial_ssl_cert_no_certificate(self, mock_application):
        """Test accept_unofficial_ssl_cert when certificate cannot be retrieved."""
        app, manager = mock_application

        hostname = "example.com"

        with patch("nxdrive.utils.get_certificate_details") as mock_get_cert:
            mock_get_cert.return_value = None

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.accept_unofficial_ssl_cert.__get__(app, Application)
            result = bound_method(hostname)

            # Verify certificate retrieval was attempted
            mock_get_cert.assert_called_once_with(hostname=hostname)

            # Should return False when no certificate
            assert result is False

    def test_accept_unofficial_ssl_cert_user_accepts(self, mock_application):
        """Test accept_unofficial_ssl_cert when user accepts the certificate."""
        app, manager = mock_application

        hostname = "example.com"
        mock_cert = {
            "subject": [[("CN", "example.com"), ("O", "Example Org")]],
            "issuer": [[("CN", "Example CA"), ("O", "Example CA Org")]],
            "serialNumber": "0F4019D1E6C52EF9A3A929B6D5613816",
            "notBefore": "2024-01-01",
            "notAfter": "2025-12-31",
            "caIssuers": ["http://ca.example.com/cert"],
        }

        with patch("nxdrive.utils.get_certificate_details") as mock_get_cert, patch(
            "nxdrive.gui.application.QDialog"
        ) as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator:
            mock_get_cert.return_value = mock_cert
            mock_translator.get.return_value = "Test Message"

            # Create mock dialog instance
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Mock dialog components
            mock_text_edit = Mock()
            mock_buttons = Mock()
            mock_ok_button = Mock()
            mock_checkbox = Mock()

            # Simulate user accepting
            def exec_side_effect():
                # Get the callback that was connected to stateChanged
                if mock_checkbox.stateChanged.connect.called:
                    state_changed_callback = (
                        mock_checkbox.stateChanged.connect.call_args[0][0]
                    )
                    # Simulate checkbox being checked
                    state_changed_callback(2)  # Qt.Checked = 2
                # Simulate clicking OK button by triggering accepted signal
                if mock_buttons.accepted.connect.called:
                    accept_callback = mock_buttons.accepted.connect.call_args[0][0]
                    accept_callback()
                return 1  # QDialog.Accepted

            mock_dialog.exec_.side_effect = exec_side_effect

            with patch(
                "nxdrive.gui.application.QTextEdit", return_value=mock_text_edit
            ), patch(
                "nxdrive.gui.application.QDialogButtonBox", return_value=mock_buttons
            ), patch(
                "nxdrive.gui.application.QCheckBox", return_value=mock_checkbox
            ), patch(
                "nxdrive.gui.application.QVBoxLayout"
            ):
                mock_buttons.button.return_value = mock_ok_button
                mock_buttons.standardButtons.return_value = qt.Ok | qt.Cancel

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp.accept_unofficial_ssl_cert.__get__(
                    app, Application
                )
                result = bound_method(hostname)

                # Verify dialog was created and shown
                mock_dialog_class.assert_called_once()
                mock_dialog.exec_.assert_called_once()

                # Should return True when user accepts
                assert result is True

    def test_accept_unofficial_ssl_cert_user_rejects(self, mock_application):
        """Test accept_unofficial_ssl_cert when user rejects the certificate."""
        app, manager = mock_application

        hostname = "example.com"
        mock_cert = {
            "subject": [[("CN", "example.com")]],
            "issuer": [[("CN", "Example CA")]],
            "serialNumber": "ABC123",
            "notBefore": "2024-01-01",
            "notAfter": "2025-12-31",
            "caIssuers": [],
        }

        with patch("nxdrive.utils.get_certificate_details") as mock_get_cert, patch(
            "nxdrive.gui.application.QDialog"
        ) as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator:
            mock_get_cert.return_value = mock_cert
            mock_translator.get.return_value = "Test Message"

            # Create mock dialog instance
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Mock dialog components
            mock_text_edit = Mock()
            mock_buttons = Mock()
            mock_ok_button = Mock()
            mock_checkbox = Mock()

            # Simulate user rejecting (clicking Cancel)
            def exec_side_effect():
                mock_buttons.rejected.emit()
                return 0  # QDialog.Rejected

            mock_dialog.exec_.return_value = 0
            mock_dialog.exec_.side_effect = exec_side_effect

            with patch(
                "nxdrive.gui.application.QTextEdit", return_value=mock_text_edit
            ), patch(
                "nxdrive.gui.application.QDialogButtonBox", return_value=mock_buttons
            ), patch(
                "nxdrive.gui.application.QCheckBox", return_value=mock_checkbox
            ), patch(
                "nxdrive.gui.application.QVBoxLayout"
            ):
                mock_buttons.button.return_value = mock_ok_button

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp.accept_unofficial_ssl_cert.__get__(
                    app, Application
                )
                result = bound_method(hostname)

                # Should return False when user rejects
                assert result is False

    def test_accept_unofficial_ssl_cert_checkbox_enables_button(self, mock_application):
        """Test that checkbox state change enables/disables OK button."""
        app, manager = mock_application

        hostname = "example.com"
        mock_cert = {
            "subject": [[("CN", "example.com")]],
            "issuer": [[("CN", "Example CA")]],
            "serialNumber": "123456",
            "notBefore": "2024-01-01",
            "notAfter": "2025-12-31",
            "caIssuers": ["http://ca.example.com"],
        }

        with patch("nxdrive.utils.get_certificate_details") as mock_get_cert, patch(
            "nxdrive.gui.application.QDialog"
        ) as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator:
            mock_get_cert.return_value = mock_cert
            mock_translator.get.return_value = "Test Message"

            # Create mock dialog instance
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Mock dialog components
            mock_text_edit = Mock()
            mock_buttons = Mock()
            mock_ok_button = Mock()
            mock_checkbox = Mock()

            # Track the stateChanged callback
            state_changed_callback = None

            def connect_state_changed(callback):
                nonlocal state_changed_callback
                state_changed_callback = callback

            mock_checkbox.stateChanged.connect = connect_state_changed

            with patch(
                "nxdrive.gui.application.QTextEdit", return_value=mock_text_edit
            ), patch(
                "nxdrive.gui.application.QDialogButtonBox", return_value=mock_buttons
            ), patch(
                "nxdrive.gui.application.QCheckBox", return_value=mock_checkbox
            ), patch(
                "nxdrive.gui.application.QVBoxLayout"
            ):
                mock_buttons.button.return_value = mock_ok_button

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp.accept_unofficial_ssl_cert.__get__(
                    app, Application
                )

                # Execute but don't wait for dialog
                mock_dialog.exec_.return_value = 0

                bound_method(hostname)

                # Verify OK button was initially disabled
                mock_ok_button.setEnabled.assert_any_call(False)

                # Verify stateChanged was connected
                assert state_changed_callback is not None

                # Simulate checkbox being checked
                state_changed_callback(2)  # Qt.Checked = 2
                mock_ok_button.setEnabled.assert_called_with(True)

                # Simulate checkbox being unchecked
                state_changed_callback(0)  # Qt.Unchecked = 0
                mock_ok_button.setEnabled.assert_called_with(False)

    def test_accept_unofficial_ssl_cert_certificate_formatting(self, mock_application):
        """Test certificate details are properly formatted in the dialog."""
        app, manager = mock_application

        hostname = "test.example.com"
        mock_cert = {
            "subject": [
                [("CN", "test.example.com")],
                [("O", "Test Organization")],
                [("L", "Test City")],
            ],
            "issuer": [
                [("CN", "Test CA")],
                [("O", "Test CA Organization")],
            ],
            "serialNumber": "0F4019D1E6C52EF9A3A929B6D5613816",
            "notBefore": "Jan 1 00:00:00 2024 GMT",
            "notAfter": "Dec 31 23:59:59 2025 GMT",
            "caIssuers": [
                "http://ca.example.com/cert1",
                "http://ca.example.com/cert2",
            ],
        }

        with patch("nxdrive.utils.get_certificate_details") as mock_get_cert, patch(
            "nxdrive.gui.application.QDialog"
        ) as mock_dialog_class, patch(
            "nxdrive.gui.application.Translator"
        ) as mock_translator:
            mock_get_cert.return_value = mock_cert
            mock_translator.get.return_value = "Test Message"

            # Create mock dialog instance
            mock_dialog = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Mock dialog components
            mock_text_edit = Mock()
            mock_buttons = Mock()
            mock_ok_button = Mock()
            mock_checkbox = Mock()

            mock_dialog.exec_.return_value = 0

            with patch(
                "nxdrive.gui.application.QTextEdit", return_value=mock_text_edit
            ), patch(
                "nxdrive.gui.application.QDialogButtonBox", return_value=mock_buttons
            ), patch(
                "nxdrive.gui.application.QCheckBox", return_value=mock_checkbox
            ), patch(
                "nxdrive.gui.application.QVBoxLayout"
            ):
                mock_buttons.button.return_value = mock_ok_button

                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp.accept_unofficial_ssl_cert.__get__(
                    app, Application
                )
                bound_method(hostname)

                # Verify HTML was set with formatted data
                mock_text_edit.setHtml.assert_called_once()
                html_content = mock_text_edit.setHtml.call_args[0][0]

                # Check that serial number is formatted with colons
                assert (
                    "0f:40:19:d1:e6:c5:2e:f9:a3:a9:29:b6:d5:61:38:16"
                    in html_content.lower()
                )

                # Check that certificate fields are present
                assert "test.example.com" in html_content
                assert "Test Organization" in html_content
                assert "Test CA" in html_content
