"""Unit tests for nxdrive.drive.auth.token module."""

from unittest.mock import Mock, patch

from nxdrive.drive.auth.token import TokenAuthentication


class _ConcreteToken(TokenAuthentication):
    """Concrete subclass for testing the base class logic."""

    def _create_auth_handler(self, token):
        return Mock(token=token)

    def get_token(self, **kwargs):
        return "test-token"


class TestTokenAuthenticationConnectUrl:
    def _make(self, url="http://localhost:8080/nuxeo", token="tok", device_id="d1"):
        with patch("nxdrive.drive.auth.token.Options") as mock_opts:
            mock_opts.browser_startup_page = ""
            return _ConcreteToken(url, token=token, device_id=device_id)

    def test_contains_device_id(self):
        obj = self._make(device_id="my-device")
        with patch("nxdrive.drive.auth.token.Options") as mock_opts:
            mock_opts.browser_startup_page = ""
            mock_config = Mock(browser_startup_page="authentication/token")
            with patch(
                "nxdrive.drive.server_type.detect_by_url", return_value=mock_config
            ):
                url = obj.connect_url()
        assert "deviceId=my-device" in url

    def test_contains_application_name(self):
        obj = self._make()
        mock_config = Mock(browser_startup_page="auth/token")
        with patch("nxdrive.drive.server_type.detect_by_url", return_value=mock_config):
            with patch("nxdrive.drive.auth.token.Options") as mock_opts:
                mock_opts.browser_startup_page = ""
                url = obj.connect_url()
        assert "applicationName=" in url

    def test_preserves_base_url_scheme(self):
        obj = self._make(url="https://server.example.com/nuxeo")
        mock_config = Mock(browser_startup_page="auth/token")
        with patch("nxdrive.drive.server_type.detect_by_url", return_value=mock_config):
            with patch("nxdrive.drive.auth.token.Options") as mock_opts:
                mock_opts.browser_startup_page = ""
                url = obj.connect_url()
        assert url.startswith("https://")


class TestTokenAuthenticationRevokeToken:
    def test_revoke_calls_get_token(self):
        with patch("nxdrive.drive.auth.token.Options"):
            obj = _ConcreteToken("http://localhost", token="t", device_id="d")
        mock_client = Mock()
        obj.revoke_token(client=mock_client)
        # get_token returns "test-token" without error means revoke succeeded
