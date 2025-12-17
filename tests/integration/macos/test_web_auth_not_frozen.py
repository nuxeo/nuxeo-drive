"""Integration tests for _web_auth_not_frozen method - macOS only."""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest
from nuxeo.client import Nuxeo

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestWebAuthNotFrozen:
    """Test suite for _web_auth_not_frozen method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp, nuxeo_url):
        """Create a mock Application with manager."""
        # Create a minimal Manager without engine
        manager = Manager(tmp())

        # Create a minimal Application mock
        app = MagicMock(spec=Application)
        app.manager = manager
        app.icon = Mock()

        # Mock the API
        app.api = Mock()
        app.api.handle_token = Mock()

        # Setup translate method
        def translate(message, **kwargs):
            return message

        app.translate = translate

        yield app, manager, nuxeo_url

        manager.close()

    def test_web_auth_not_frozen_successful_authentication(self, mock_application):
        """Test successful authentication flow."""
        app, manager, nuxeo_url = mock_application

        test_user = "test_user"
        test_password = "test_password"
        test_token = "test_auth_token_12345"

        # Mock all Qt components and Nuxeo before calling the method
        # QDialog, QVBoxLayout, QDialogButtonBox are imported at module level in application.py
        # QLineEdit is imported locally in the method, so patch it at qt.imports level
        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.qt.imports.QLineEdit"
        ) as mock_lineedit_class, patch(
            "nxdrive.gui.application.QVBoxLayout"
        ) as mock_layout_class, patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttonbox_class, patch(
            "nuxeo.client.Nuxeo"
        ) as mock_nuxeo_class:

            # Setup dialog mock with exec_
            mock_dialog = Mock()
            mock_dialog.exec_ = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Setup line edit mocks for username and password
            username_widget = Mock()
            username_widget.text.return_value = test_user
            password_widget = Mock()
            password_widget.text.return_value = test_password

            mock_lineedit_class.side_effect = [username_widget, password_widget]

            # Setup layout and button box mocks
            mock_layout = Mock()
            mock_layout_class.return_value = mock_layout
            mock_buttonbox = Mock()
            mock_buttonbox_class.return_value = mock_buttonbox

            # Capture the auth callback
            auth_callback = None

            def capture_accepted_connect(callback):
                nonlocal auth_callback
                auth_callback = callback

            mock_buttonbox.accepted.connect = capture_accepted_connect
            mock_buttonbox.rejected.connect = Mock()

            # Setup Nuxeo client mock
            mock_nuxeo_instance = Mock(spec=Nuxeo)
            mock_client = Mock()
            mock_client.request_auth_token = Mock(return_value=test_token)
            mock_nuxeo_instance.client = mock_client
            mock_nuxeo_class.return_value = mock_nuxeo_instance

            # Bind and call the actual method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._web_auth_not_frozen.__get__(app, Application)
            bound_method(nuxeo_url)

            # Verify dialog setup
            mock_dialog_class.assert_called_once()
            mock_dialog.setWindowTitle.assert_called_once()
            assert mock_lineedit_class.call_count == 2

            # Simulate clicking OK button
            assert auth_callback is not None
            auth_callback()

            # Verify Nuxeo client and token handling
            mock_nuxeo_class.assert_called_once()
            mock_client.request_auth_token.assert_called_once()
            app.api.handle_token.assert_called_once_with(test_token, test_user)
            mock_dialog.close.assert_called_once()

    def test_web_auth_not_frozen_authentication_failure(self, mock_application):
        """Test authentication flow when token request fails."""
        app, manager, nuxeo_url = mock_application

        test_user = "test_user"
        test_password = "wrong_password"

        # Mock all components
        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.qt.imports.QLineEdit"
        ) as mock_lineedit_class, patch("nxdrive.gui.application.QVBoxLayout"), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttonbox_class, patch(
            "nuxeo.client.Nuxeo"
        ) as mock_nuxeo_class:

            # Setup dialog mock
            mock_dialog = Mock()
            mock_dialog.exec_ = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Setup line edits
            username_widget = Mock()
            username_widget.text.return_value = test_user
            password_widget = Mock()
            password_widget.text.return_value = test_password
            mock_lineedit_class.side_effect = [username_widget, password_widget]

            # Setup button box
            mock_buttonbox = Mock()
            mock_buttonbox_class.return_value = mock_buttonbox
            auth_callback = None

            def capture_accepted_connect(callback):
                nonlocal auth_callback
                auth_callback = callback

            mock_buttonbox.accepted.connect = capture_accepted_connect
            mock_buttonbox.rejected.connect = Mock()

            # Setup Nuxeo to fail
            mock_nuxeo_instance = Mock(spec=Nuxeo)
            mock_client = Mock()
            mock_client.request_auth_token = Mock(side_effect=Exception("Auth failed"))
            mock_nuxeo_instance.client = mock_client
            mock_nuxeo_class.return_value = mock_nuxeo_instance

            # Call the method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._web_auth_not_frozen.__get__(app, Application)
            bound_method(nuxeo_url)

            # Trigger auth
            auth_callback()

            # Verify empty token was handled
            app.api.handle_token.assert_called_once_with("", test_user)
            mock_dialog.close.assert_called_once()

    def test_web_auth_not_frozen_cancel_authentication(self, mock_application):
        """Test canceling the authentication dialog."""
        app, manager, nuxeo_url = mock_application

        # Mock all components
        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.qt.imports.QLineEdit"
        ) as mock_lineedit_class, patch("nxdrive.gui.application.QVBoxLayout"), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttonbox_class:

            mock_dialog = Mock()
            mock_dialog.exec_ = Mock()
            mock_dialog_class.return_value = mock_dialog

            username_widget = Mock()
            password_widget = Mock()
            mock_lineedit_class.side_effect = [username_widget, password_widget]

            mock_buttonbox = Mock()
            mock_buttonbox_class.return_value = mock_buttonbox

            # Capture cancel callback
            cancel_callback = None

            def capture_rejected_connect(callback):
                nonlocal cancel_callback
                cancel_callback = callback

            mock_buttonbox.accepted.connect = Mock()
            mock_buttonbox.rejected.connect = capture_rejected_connect

            # Call the method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._web_auth_not_frozen.__get__(app, Application)
            bound_method(nuxeo_url)

            # Simulate clicking Cancel
            cancel_callback()

            # Verify no token was handled
            app.api.handle_token.assert_not_called()
            mock_dialog.close.assert_called_once()

    def test_web_auth_not_frozen_uses_environment_defaults(self, mock_application):
        """Test that default credentials come from environment variables."""
        app, manager, nuxeo_url = mock_application

        test_env_user = "EnvUser"
        test_env_password = "EnvPassword"

        # Set environment variables
        with patch.dict(
            os.environ,
            {
                "NXDRIVE_TEST_USERNAME": test_env_user,
                "NXDRIVE_TEST_PASSWORD": test_env_password,
            },
        ):
            # Mock all components
            with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
                "nxdrive.qt.imports.QLineEdit"
            ) as mock_lineedit_class, patch(
                "nxdrive.gui.application.QVBoxLayout"
            ), patch(
                "nxdrive.gui.application.QDialogButtonBox"
            ):

                mock_dialog = Mock()
                mock_dialog.exec_ = Mock()
                mock_dialog_class.return_value = mock_dialog

                username_widget = Mock()
                password_widget = Mock()
                mock_lineedit_class.side_effect = [username_widget, password_widget]

                # Call the method
                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp._web_auth_not_frozen.__get__(app, Application)
                bound_method(nuxeo_url)

                # Verify username field was created with environment default
                calls = mock_lineedit_class.call_args_list
                assert len(calls) == 2
                assert calls[0][0][0] == test_env_user  # username
                assert calls[1][0][0] == test_env_password  # password

    def test_web_auth_not_frozen_proxy_and_ssl_settings(self, mock_application):
        """Test that proxy and SSL settings are correctly passed to Nuxeo client."""
        app, manager, nuxeo_url = mock_application

        test_user = "test_user"
        test_password = "test_password"
        test_token = "test_token"
        test_proxies = {"http": "http://proxy.example.com:8080"}

        # Setup proxy settings
        manager.proxy.settings = Mock(return_value=test_proxies)

        # Mock all components
        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.qt.imports.QLineEdit"
        ) as mock_lineedit_class, patch("nxdrive.gui.application.QVBoxLayout"), patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttonbox_class, patch(
            "nuxeo.client.Nuxeo"
        ) as mock_nuxeo_class, patch(
            "nxdrive.gui.application.get_verify"
        ) as mock_get_verify, patch(
            "nxdrive.gui.application.client_certificate"
        ) as mock_client_cert:

            mock_get_verify.return_value = True
            mock_client_cert.return_value = "/path/to/cert.pem"

            # Setup dialog and inputs
            mock_dialog = Mock()
            mock_dialog.exec_ = Mock()
            mock_dialog_class.return_value = mock_dialog

            username_widget = Mock()
            username_widget.text.return_value = test_user
            password_widget = Mock()
            password_widget.text.return_value = test_password
            mock_lineedit_class.side_effect = [username_widget, password_widget]

            # Setup button box
            mock_buttonbox = Mock()
            mock_buttonbox_class.return_value = mock_buttonbox
            auth_callback = None

            def capture_accepted_connect(callback):
                nonlocal auth_callback
                auth_callback = callback

            mock_buttonbox.accepted.connect = capture_accepted_connect
            mock_buttonbox.rejected.connect = Mock()

            # Setup Nuxeo
            mock_nuxeo_instance = Mock(spec=Nuxeo)
            mock_client = Mock()
            mock_client.request_auth_token = Mock(return_value=test_token)
            mock_nuxeo_instance.client = mock_client
            mock_nuxeo_class.return_value = mock_nuxeo_instance

            # Call the method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._web_auth_not_frozen.__get__(app, Application)
            bound_method(nuxeo_url)

            # Trigger authentication
            auth_callback()

            # Verify Nuxeo client was created with correct settings
            call_kwargs = mock_nuxeo_class.call_args[1]
            assert call_kwargs["proxies"] == test_proxies
            assert call_kwargs["verify"] is True
            assert call_kwargs["cert"] == "/path/to/cert.pem"
            manager.proxy.settings.assert_called_once_with(url=nuxeo_url)

    def test_web_auth_not_frozen_dialog_ui_elements(self, mock_application):
        """Test that all UI elements are properly created and configured."""
        app, manager, nuxeo_url = mock_application

        # Mock all Qt components
        with patch("nxdrive.gui.application.QDialog") as mock_dialog_class, patch(
            "nxdrive.qt.imports.QLineEdit"
        ) as mock_lineedit_class, patch(
            "nxdrive.gui.application.QVBoxLayout"
        ) as mock_layout_class, patch(
            "nxdrive.gui.application.QDialogButtonBox"
        ) as mock_buttonbox_class:

            mock_dialog = Mock()
            mock_dialog.exec_ = Mock()
            mock_dialog_class.return_value = mock_dialog

            username_widget = Mock()
            password_widget = Mock()
            mock_lineedit_class.side_effect = [username_widget, password_widget]

            mock_layout = Mock()
            mock_layout_class.return_value = mock_layout

            mock_buttonbox = Mock()
            mock_buttonbox_class.return_value = mock_buttonbox
            mock_buttonbox.accepted.connect = Mock()
            mock_buttonbox.rejected.connect = Mock()

            # Call the method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._web_auth_not_frozen.__get__(app, Application)
            bound_method(nuxeo_url)

            # Verify dialog setup
            mock_dialog.setWindowTitle.assert_called_once()
            mock_dialog.setWindowIcon.assert_called_once_with(app.icon)
            mock_dialog.resize.assert_called_once_with(250, 100)

            # Verify password field has echo mode set
            password_widget.setEchoMode.assert_called_once()

            # Verify layout was populated
            assert mock_layout.addWidget.call_count >= 3  # username, password, buttons

            # Verify button box was configured
            mock_buttonbox.setStandardButtons.assert_called_once()
            mock_buttonbox.accepted.connect.assert_called_once()
            mock_buttonbox.rejected.connect.assert_called_once()

            # Verify exec_ was called
            mock_dialog.exec_.assert_called_once()
