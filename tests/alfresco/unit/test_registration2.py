"""Unit tests for nxdrive.alfresco.registration."""

from unittest.mock import MagicMock, Mock, patch

import pytest


class TestAlfrescoAuthFactory:
    def test_dict_token_returns_oauth_auth(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_auth_factory

        token = {"access_token": "abc", "token_url": "https://idp/token"}
        with patch(
            "nxdrive.alfresco.auth.oauth2.AlfrescoOAuthentication"
        ) as mock_cls:
            mock_cls.return_value = "oauth-instance"
            result = _alfresco_auth_factory("https://server", token)
        assert result == "oauth-instance"

    def test_string_token_returns_token_auth(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_auth_factory

        with patch(
            "nxdrive.drive.auth.token.TokenAuthentication"
        ) as mock_cls:
            mock_cls.return_value = "token-instance"
            result = _alfresco_auth_factory("https://server", "bearer-token")
        assert result == "token-instance"

    def test_none_token_returns_token_auth(self) -> None:
        from nxdrive.alfresco.registration import _alfresco_auth_factory

        with patch(
            "nxdrive.drive.auth.token.TokenAuthentication"
        ) as mock_cls:
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
        engine.dao.update_config.assert_called_once_with(
            "remote_need_full_scan", "1"
        )

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
