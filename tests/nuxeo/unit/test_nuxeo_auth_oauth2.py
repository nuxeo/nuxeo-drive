"""Unit tests for nxdrive.nuxeo.auth.oauth2 module."""

from unittest.mock import Mock, patch

from nxdrive.drive.exceptions import RemoteOAuth2Error


class TestOAuthentication:
    def _make(self, url="http://localhost:8080/nuxeo", token=None, dao=None):
        with patch("nxdrive.nuxeo.auth.oauth2.Options") as mock_opts:
            mock_opts.oauth2_authorization_endpoint = "http://idp/auth"
            mock_opts.oauth2_openid_configuration_url = ""
            mock_opts.oauth2_redirect_uri = "http://localhost/callback"
            mock_opts.oauth2_token_endpoint = "http://idp/token"
            mock_opts.oauth2_scope = ""
            mock_opts.oauth2_client_id = "client-id"
            mock_opts.oauth2_client_secret = "secret"
            with patch("nxdrive.nuxeo.auth.oauth2.get_verify", return_value=True):
                with patch("nuxeo.auth.OAuth2") as mock_oauth2_cls:
                    mock_oauth2_cls.return_value = Mock()
                    from nxdrive.nuxeo.auth.oauth2 import OAuthentication

                    obj = OAuthentication(url, token=token, dao=dao)
        return obj

    def test_init_sets_auth(self):
        obj = self._make()
        assert obj.auth is not None

    def test_init_stores_url(self):
        obj = self._make(url="https://my.server.com/nuxeo")
        assert obj.url == "https://my.server.com/nuxeo"

    def test_connect_url_no_scope(self):
        obj = self._make()
        obj.auth.create_authorization_url.return_value = (
            "http://idp/auth?state=xyz",
            "xyz",
            "verifier123",
        )
        with patch("nxdrive.nuxeo.auth.oauth2.Options") as mock_opts:
            mock_opts.oauth2_scope = ""
            url = obj.connect_url()
        assert url == "http://idp/auth?state=xyz"
        obj.auth.create_authorization_url.assert_called_once_with()

    def test_connect_url_with_scope(self):
        obj = self._make()
        obj.auth.create_authorization_url.return_value = (
            "http://idp/auth?scope=openid",
            "st",
            "cv",
        )
        with patch("nxdrive.nuxeo.auth.oauth2.Options") as mock_opts:
            mock_opts.oauth2_scope = "openid"
            url = obj.connect_url()
        assert url == "http://idp/auth?scope=openid"
        obj.auth.create_authorization_url.assert_called_once_with(scope="openid")

    def test_connect_url_saves_to_dao(self):
        dao = Mock()
        obj = self._make(dao=dao)
        obj.auth.create_authorization_url.return_value = (
            "http://idp/auth",
            "state1",
            "verifier1",
        )
        with patch("nxdrive.nuxeo.auth.oauth2.Options") as mock_opts:
            mock_opts.oauth2_scope = ""
            obj.connect_url()
        dao.update_config.assert_any_call("tmp_oauth2_url", obj.url)
        dao.update_config.assert_any_call("tmp_oauth2_code_verifier", "verifier1")
        dao.update_config.assert_any_call("tmp_oauth2_state", "state1")

    def test_connect_url_no_dao(self):
        obj = self._make(dao=None)
        obj.auth.create_authorization_url.return_value = (
            "http://idp/auth",
            "state1",
            "verifier1",
        )
        with patch("nxdrive.nuxeo.auth.oauth2.Options") as mock_opts:
            mock_opts.oauth2_scope = ""
            # Should not raise
            url = obj.connect_url()
        assert url == "http://idp/auth"

    def test_get_username(self):
        obj = self._make()
        mock_user = Mock()
        mock_user.uid = "jdoe"
        mock_client = Mock()
        mock_client.users.current_user.return_value = mock_user
        with patch("nxdrive.nuxeo.auth.oauth2.Nuxeo", return_value=mock_client):
            with patch("nxdrive.nuxeo.auth.oauth2.get_verify", return_value=True):
                username = obj.get_username()
        assert username == "jdoe"

    def test_get_token_success(self):
        obj = self._make()
        obj.auth.request_token.return_value = "new-tok"
        token = obj.get_token(code_verifier="cv", code="c", state="s")
        assert token == "new-tok"
        assert obj.token == "new-tok"

    def test_get_token_oauth2_error(self):
        from nuxeo.exceptions import OAuth2Error

        obj = self._make()
        obj.auth.request_token.side_effect = OAuth2Error("invalid_grant")
        import pytest

        with pytest.raises(RemoteOAuth2Error):
            obj.get_token(code_verifier="cv", code="c", state="s")
