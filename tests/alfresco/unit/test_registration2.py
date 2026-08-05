"""Unit tests for nxdrive.alfresco.registration."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, patch

import pytest


@contextmanager
def _mock_debug_auth_dialog():
    """Provide a fully mocked Alfresco debug-auth dialog."""
    dialog = MagicMock()
    layout = MagicMock()
    username = MagicMock()
    username.text.return_value = "typed-user"
    password = MagicMock()
    password.text.return_value = "typed-password"
    buttons = MagicMock()
    line_edit = MagicMock(side_effect=[username, password])
    api = MagicMock()

    with patch("nxdrive.drive.qt.imports.QDialog", return_value=dialog), patch(
        "nxdrive.drive.qt.imports.QVBoxLayout", return_value=layout
    ), patch("nxdrive.drive.qt.imports.QLineEdit", line_edit), patch(
        "nxdrive.drive.qt.imports.QDialogButtonBox", return_value=buttons
    ):
        yield SimpleNamespace(
            api=api,
            buttons=buttons,
            dialog=dialog,
            layout=layout,
            line_edit=line_edit,
            password=password,
            username=username,
        )


class TestAlfrescoAuthFactory:
    def test_dict_token_returns_oauth_auth(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_auth_factory

        token = {"access_token": "abc", "token_url": "https://idp/token"}
        with patch("nxdrive.alfresco.auth.oauth2.AlfrescoOAuthentication") as mock_cls:
            mock_cls.return_value = "oauth-instance"
            result = _alfresco_auth_factory("https://server", token)
        assert result == "oauth-instance"

    def test_string_token_returns_token_auth(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_auth_factory

        with patch("nxdrive.drive.auth.token.TokenAuthentication") as mock_cls:
            mock_cls.return_value = "token-instance"
            result = _alfresco_auth_factory("https://server", "bearer-token")
        assert result == "token-instance"

    def test_none_token_returns_token_auth(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_auth_factory

        with patch("nxdrive.drive.auth.token.TokenAuthentication") as mock_cls:
            mock_cls.return_value = "token-instance"
            result = _alfresco_auth_factory("https://server", None)
        assert result == "token-instance"


class TestAlfrescoReloginHandler:
    def test_successful_relogin(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_relogin_handler

        engine = Mock()
        engine.remote_user = "admin"
        engine.server_url = "https://acs.example.com"

        with patch("alfresco.auth.TicketAuth") as mock_ta:
            mock_ta.return_value.authenticate.return_value = "TICKET-123"
            _alfresco_relogin_handler(engine, "password123")

        engine._save_ticket.assert_called_once_with("TICKET-123")
        engine.set_invalid_credentials.assert_called_once_with(value=False)
        engine.stop.assert_called_once()
        engine.start.assert_called_once()
        engine.queue_manager.resume.assert_called_once()
        engine.dao.update_config.assert_called_once_with("remote_need_full_scan", "1")

    def test_no_ticket_raises(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_relogin_handler

        engine = Mock()
        engine.remote_user = "admin"
        engine.server_url = "https://acs.example.com"

        with patch("alfresco.auth.TicketAuth") as mock_ta:
            mock_ta.return_value.authenticate.return_value = None
            with pytest.raises(RuntimeError, match="No ticket"):
                _alfresco_relogin_handler(engine, "badpass")


class TestAlfrescoPasswordAuthHandler:
    def test_delegates_to_basic_auth(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_password_auth_handler

        api = Mock()
        with patch("nxdrive.alfresco.gui.auth.basic_auth") as mock_ba:
            _alfresco_password_auth_handler(
                api, "/local", "https://server", "user", "pass"
            )
        mock_ba.assert_called_once_with(api, "/local", "https://server", "user", "pass")


class TestAlfrescoDebugAuthHandler:
    def test_accept_binds_using_callback_params(self) -> None:
        from nxdrive.drive.qt import constants as qt
        from nxdrive.alfresco.registration import _alfresco_debug_auth_handler

        with patch.dict(
            "os.environ",
            {
                "NXDRIVE_TEST_USERNAME": "default-user",
                "NXDRIVE_TEST_PASSWORD": "default-password",
            },
            clear=True,
        ), _mock_debug_auth_dialog() as mocked:
            mocked.api.callback_params = {
                "local_folder": "/sync-root",
                "server_url": "https://callback.example",
            }

            _alfresco_debug_auth_handler(
                "https://fallback.example", MagicMock(), mocked.api
            )
            accept = mocked.buttons.accepted.connect.call_args.args[0]
            accept()

        mocked.line_edit.assert_has_calls(
            [
                call("default-user", parent=mocked.dialog),
                call("default-password", parent=mocked.dialog),
            ]
        )
        mocked.password.setEchoMode.assert_called_once_with(qt.Password)
        mocked.layout.addWidget.assert_has_calls(
            [call(mocked.username), call(mocked.password), call(mocked.buttons)]
        )
        mocked.buttons.setStandardButtons.assert_called_once_with(qt.Cancel | qt.Ok)
        mocked.api.bind_server.assert_called_once_with(
            "/sync-root",
            "https://callback.example",
            "typed-user",
            password="typed-password",
        )
        mocked.api._load_pending_auth_callback_params.assert_not_called()
        mocked.api._clear_pending_auth_callback_params.assert_called_once_with()
        mocked.api.setMessage.emit.assert_not_called()
        mocked.dialog.setLayout.assert_called_once_with(mocked.layout)
        mocked.dialog.exec.assert_called_once_with()
        mocked.dialog.close.assert_called_once_with()

    def test_accept_loads_pending_params_and_uses_url_fallback(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_debug_auth_handler

        with _mock_debug_auth_dialog() as mocked:
            mocked.api.callback_params = {}
            mocked.api._load_pending_auth_callback_params.return_value = {
                "local_folder": "/pending-root"
            }

            _alfresco_debug_auth_handler(
                "https://fallback.example", MagicMock(), mocked.api
            )
            accept = mocked.buttons.accepted.connect.call_args.args[0]
            accept()

        mocked.api._load_pending_auth_callback_params.assert_called_once_with()
        mocked.api.bind_server.assert_called_once_with(
            "/pending-root",
            "https://fallback.example",
            "typed-user",
            password="typed-password",
        )
        mocked.api._clear_pending_auth_callback_params.assert_called_once_with()
        mocked.dialog.close.assert_called_once_with()

    def test_bind_failure_reports_error_and_cleans_up(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_debug_auth_handler

        logger = MagicMock()
        with _mock_debug_auth_dialog() as mocked, patch(
            "logging.getLogger", return_value=logger
        ):
            mocked.api.callback_params = {
                "local_folder": "/sync-root",
                "server_url": "https://server.example",
            }
            mocked.api.bind_server.side_effect = RuntimeError("invalid credentials")

            _alfresco_debug_auth_handler(
                "https://fallback.example", MagicMock(), mocked.api
            )
            accept = mocked.buttons.accepted.connect.call_args.args[0]
            accept()

        logger.error.assert_called_once_with(
            "Alfresco debug auth failed: invalid credentials"
        )
        mocked.api.setMessage.emit.assert_called_once_with(
            "CONNECTION_REFUSED", "error"
        )
        mocked.api._clear_pending_auth_callback_params.assert_called_once_with()
        mocked.dialog.close.assert_called_once_with()

    def test_cancel_closes_without_binding(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_debug_auth_handler

        with _mock_debug_auth_dialog() as mocked:
            mocked.api.callback_params = {}
            _alfresco_debug_auth_handler(
                "https://fallback.example", MagicMock(), mocked.api
            )
            reject = mocked.buttons.rejected.connect.call_args.args[0]
            reject()

        mocked.dialog.close.assert_called_once_with()
        mocked.api.bind_server.assert_not_called()
        mocked.api._load_pending_auth_callback_params.assert_not_called()
        mocked.api._clear_pending_auth_callback_params.assert_not_called()


class TestAlfrescoCallbackParamsHandlers:
    def test_save_delegates(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_save_auth_callback_params

        api = Mock()
        params = {"code": "xyz"}
        with patch(
            "nxdrive.alfresco.gui.auth_callback_store.save_auth_callback_params"
        ) as mock_save:
            _alfresco_save_auth_callback_params(api, params)
        mock_save.assert_called_once_with(api, params)

    def test_load_delegates(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_load_auth_callback_params

        api = Mock()
        with patch(
            "nxdrive.alfresco.gui.auth_callback_store.load_auth_callback_params",
            return_value={"code": "abc"},
        ) as mock_load:
            result = _alfresco_load_auth_callback_params(api)
        assert result == {"code": "abc"}
        mock_load.assert_called_once_with(api)

    def test_clear_delegates(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_clear_auth_callback_params

        api = Mock()
        with patch(
            "nxdrive.alfresco.gui.auth_callback_store.clear_auth_callback_params"
        ) as mock_clear:
            _alfresco_clear_auth_callback_params(api)
        mock_clear.assert_called_once_with(api)


class TestServerTypeRegistration:
    """Verify the ServerTypeConfig was registered with expected values."""

    def test_alfresco_config_registered(self) -> None:
        from nxdrive.drive.server_type import _registry

        config = _registry.get("ALFRESCO")
        assert config is not None
        assert config.key == "ALFRESCO"
        assert config.engine_type == "ALFRESCO"
        assert config.app_name == "Hyland Drive for Alfresco"
        assert config.company == "Hyland"
        assert "direct_edit" in config.disabled_features
        assert config.home_dir == ".alfresco-drive"
        assert config.local_folder_name == "Alfresco"
