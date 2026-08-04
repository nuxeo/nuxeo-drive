"""Unit tests for nxdrive.nuxeo.auth.token module."""

from unittest.mock import Mock, patch


class TestNuxeoTokenAuthentication:
    def _make(self, url="http://localhost:8080/nuxeo", token="test-token"):
        with patch("nxdrive.drive.auth.token.Options"):
            with patch(
                "nxdrive.drive.server_type.detect_by_url",
                return_value=Mock(browser_startup_page="drive_browser_login.jsp"),
            ):
                from nxdrive.nuxeo.auth.token import TokenAuthentication

                return TokenAuthentication(url, token=token, device_id="dev-1")

    def test_create_auth_handler_returns_token_auth(self):
        obj = self._make()
        from nuxeo.auth import TokenAuth

        assert isinstance(obj.auth, TokenAuth)

    def test_get_token_success(self):
        obj = self._make()
        mock_client = Mock()
        mock_client.headers = {"X-Device-Id": "dev-1"}
        obj.auth = Mock()
        obj.auth.request_token.return_value = "valid-token"
        token = obj.get_token(client=mock_client)
        assert token == "valid-token"
        assert obj.token == "valid-token"
        assert obj.auth.token == "valid-token"

    def test_get_token_with_newline_returns_empty(self):
        obj = self._make()
        mock_client = Mock()
        mock_client.headers = {"X-Device-Id": "dev-1"}
        obj.auth = Mock()
        obj.auth.request_token.return_value = "bad\ntoken"
        token = obj.get_token(client=mock_client)
        assert token == ""
        assert obj.token == ""

    def test_get_token_with_revoke(self):
        obj = self._make()
        mock_client = Mock()
        mock_client.headers = {"X-Device-Id": "dev-1"}
        obj.auth = Mock()
        obj.auth.request_token.return_value = ""
        obj.get_token(client=mock_client, revoke=True)
        obj.auth.request_token.assert_called_once()
        call_kwargs = obj.auth.request_token.call_args
        assert call_kwargs[1]["revoke"] is True
