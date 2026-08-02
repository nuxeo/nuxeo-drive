"""Unit tests for nxdrive.drive.auth.oauth2 module."""

from unittest.mock import Mock, patch

from nxdrive.drive.auth.oauth2 import OAuthenticationBase


class _ConcreteOAuth(OAuthenticationBase):
    """Concrete subclass for testing."""

    def _build_oauth2(self):
        self.auth = Mock()

    def connect_url(self):
        return "http://example.com/auth"

    def get_username(self):
        return "testuser"


class TestOAuthenticationBase:
    def _make(self, url="http://localhost:8080/nuxeo", token="tok"):
        with patch("nxdrive.drive.auth.oauth2.get_verify", return_value=True):
            with patch("nxdrive.drive.auth.oauth2.Options") as mock_opts:
                mock_opts.oauth2_client_id = "client-id"
                mock_opts.oauth2_client_secret = "secret"
                mock_opts.oauth2_openid_configuration_url = ""
                return _ConcreteOAuth(url, token=token)

    def test_init_stores_verification(self):
        obj = self._make()
        assert obj.verification_needed is True

    def test_init_stores_dao_none(self):
        obj = self._make()
        assert obj._dao is None

    def test_get_token_delegates_to_auth(self):
        obj = self._make()
        obj.auth = Mock()
        obj.auth.request_token.return_value = "new-token"
        token = obj.get_token(code_verifier="cv", code="code123", state="st")
        assert token == "new-token"
        assert obj.token == "new-token"
        obj.auth.request_token.assert_called_once_with(
            code_verifier="cv", code="code123", state="st"
        )
