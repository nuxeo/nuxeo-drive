"""Unit tests for nxdrive.nuxeo.registration module."""

from unittest.mock import Mock, patch


class TestNuxeoAuthFactory:
    def test_dict_token_returns_oauth(self):
        from nxdrive.nuxeo.registration import _nuxeo_auth_factory

        token = {"access_token": "abc", "token_url": "https://idp/token"}
        with patch("nxdrive.nuxeo.auth.oauth2.OAuthentication") as mock_cls:
            mock_cls.return_value = "oauth-inst"
            result = _nuxeo_auth_factory("https://server/nuxeo", token)
        assert result == "oauth-inst"
        mock_cls.assert_called_once_with("https://server/nuxeo", token=token)

    def test_string_token_returns_token_auth(self):
        from nxdrive.nuxeo.registration import _nuxeo_auth_factory

        with patch("nxdrive.nuxeo.auth.token.TokenAuthentication") as mock_cls:
            mock_cls.return_value = "token-inst"
            result = _nuxeo_auth_factory("https://server/nuxeo", "my-token")
        assert result == "token-inst"
        mock_cls.assert_called_once_with("https://server/nuxeo", token="my-token")


class TestNuxeoDebugInit:
    def test_enables_check_params(self):
        from nxdrive.nuxeo.registration import _nuxeo_debug_init

        with patch("nuxeo.constants") as mock_const:
            _nuxeo_debug_init()
        assert mock_const.CHECK_PARAMS is True


class TestNuxeoProtocolHelpers:
    def test_parse_direct_transfer_remote_path(self):
        from nxdrive.nuxeo.registration import (
            _nuxeo_parse_direct_transfer_remote_path,
        )

        result = _nuxeo_parse_direct_transfer_remote_path("https://s.com/nuxeo/path/ws")
        assert result == "/path/ws"

    def test_normalize_download_server_path(self):
        from nxdrive.nuxeo.registration import (
            _nuxeo_normalize_download_server_path,
        )

        assert _nuxeo_normalize_download_server_path("s.com") == "s.com/nuxeo"

    def test_normalize_protocol_url(self):
        from nxdrive.nuxeo.registration import _nuxeo_normalize_protocol_url

        assert (
            _nuxeo_normalize_protocol_url("nxdrive:token/edit")
            == "nxdrive://token/edit"
        )

    def test_protocol_token_pattern(self):
        from nxdrive.nuxeo.registration import _nuxeo_protocol_token_pattern

        assert _nuxeo_protocol_token_pattern() == "[^/]+"

    def test_get_test_server_url_default(self):
        from nxdrive.nuxeo.registration import _nuxeo_get_test_server_url

        with patch.dict("os.environ", {}, clear=True):
            result = _nuxeo_get_test_server_url()
        assert result == ""

    def test_get_test_server_url_from_env(self):
        from nxdrive.nuxeo.registration import _nuxeo_get_test_server_url

        with patch.dict(
            "os.environ", {"NXDRIVE_TEST_NUXEO_URL": "http://localhost:8080/nuxeo"}
        ):
            result = _nuxeo_get_test_server_url()
        assert result == "http://localhost:8080/nuxeo"


class TestNuxeoCallbackParamHooks:
    def test_save_delegates(self):
        from nxdrive.nuxeo.registration import _nuxeo_save_auth_callback_params

        api = Mock()
        params = {"code": "abc"}
        _nuxeo_save_auth_callback_params(api, params)
        api._manager.dao.update_config.assert_called_once()

    def test_load_returns_dict(self):
        from nxdrive.nuxeo.registration import _nuxeo_load_auth_callback_params

        import json

        api = Mock()
        api._manager.dao.get_config.return_value = json.dumps({"k": "v"})
        result = _nuxeo_load_auth_callback_params(api)
        assert result == {"k": "v"}

    def test_clear_delegates(self):
        from nxdrive.nuxeo.registration import _nuxeo_clear_auth_callback_params

        api = Mock()
        _nuxeo_clear_auth_callback_params(api)
        api._manager.dao.delete_config.assert_called_once()


class TestServerTypeRegistration:
    def test_nuxeo_config_registered(self):
        from nxdrive.drive.server_type import _registry

        config = _registry.get("NUXEO")
        assert config is not None
        assert config.key == "NUXEO"
        assert config.engine_type == "NXDRIVE"
        assert config.app_name == "Nuxeo Drive"
        assert config.company == "Hyland"
        assert config.home_dir == ".nuxeo-drive"
        assert config.local_folder_name == "Nuxeo Drive"
        assert config.url_scheme == "nxdrive"
