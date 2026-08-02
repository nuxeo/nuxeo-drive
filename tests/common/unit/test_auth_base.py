"""Tests for nxdrive/drive/auth/base.py — Authentication and AuthHandler."""

from unittest.mock import MagicMock

from nxdrive.drive.auth.base import AuthHandler, Authentication

# --------------------------------------------------------------------------
# AuthHandler protocol tests (line 4 — TYPE_CHECKING import is not runtime)
# --------------------------------------------------------------------------


def test_auth_handler_protocol_isinstance_check():
    """Verify runtime_checkable protocol works with conforming objects."""

    class MyHandler:
        def __call__(self, r):
            return r

        def set_token(self, token):
            pass

    handler = MyHandler()
    assert isinstance(handler, AuthHandler)


def test_auth_handler_protocol_non_conforming():
    """Objects missing required methods should not pass isinstance check."""

    class BadHandler:
        def __call__(self, r):
            return r

        # Missing set_token

    assert not isinstance(BadHandler(), AuthHandler)


# --------------------------------------------------------------------------
# Authentication tests
# --------------------------------------------------------------------------


def test_authentication_init():
    """Basic construction stores url and token."""
    auth = Authentication("http://server.com", token="tok123")
    assert auth.url == "http://server.com"
    assert auth.token == "tok123"
    assert auth.auth is None


def test_authentication_revoke_token_is_noop():
    """revoke_token() exists and does nothing by default."""
    auth = Authentication("http://server.com")
    # Should not raise
    auth.revoke_token()


def test_authentication_set_token():
    """Lines 33-34: set_token updates self.token and calls self.auth.set_token."""
    mock_auth_handler = MagicMock()
    auth = Authentication("http://server.com", token="old")
    auth.auth = mock_auth_handler

    auth.set_token("new_token")

    assert auth.token == "new_token"
    mock_auth_handler.set_token.assert_called_once_with("new_token")


def test_authentication_set_token_with_dict():
    """set_token with a dict OAuth2 token."""
    mock_auth_handler = MagicMock()
    auth = Authentication("http://server.com")
    auth.auth = mock_auth_handler

    token = {"access_token": "abc", "refresh_token": "def"}
    auth.set_token(token)

    assert auth.token == token
    mock_auth_handler.set_token.assert_called_once_with(token)
