"""Tests for nxdrive/drive/auth/__init__.py — get_auth() and __getattr__."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_module_cache():
    """Ensure fresh imports for each test."""
    import sys

    keys_to_remove = [
        k for k in sys.modules if k.startswith("nxdrive.drive.auth") and k != "nxdrive.drive.auth.base"
    ]
    for k in keys_to_remove:
        sys.modules.pop(k, None)
    yield


# --------------------------------------------------------------------------
# get_auth tests
# --------------------------------------------------------------------------


def test_get_auth_uses_auth_factory_from_config():
    """Line 28: config.auth_factory is truthy → calls it."""
    mock_factory = MagicMock(return_value="factory_result")
    mock_config = MagicMock(auth_factory=mock_factory)

    with patch("nxdrive.drive.server_type.get_default_key", return_value="NUXEO"), \
         patch("nxdrive.drive.server_type.get", return_value=mock_config):
        from nxdrive.drive.auth import get_auth

        result = get_auth("http://host", {"access_token": "abc"}, extra="val")

    mock_factory.assert_called_once_with("http://host", {"access_token": "abc"}, extra="val")
    assert result == "factory_result"


def test_get_auth_fallback_to_token_authentication():
    """Line 30: config.auth_factory is None → falls back to TokenAuthentication."""
    mock_config = MagicMock(auth_factory=None)
    mock_token_auth_cls = MagicMock(return_value="token_auth_instance")

    with patch("nxdrive.drive.server_type.get_default_key", return_value="NUXEO"), \
         patch("nxdrive.drive.server_type.get", return_value=mock_config), \
         patch("nxdrive.drive.auth.token.TokenAuthentication", mock_token_auth_cls):
        from nxdrive.drive.auth import get_auth

        result = get_auth("http://host", "my_token")

    mock_token_auth_cls.assert_called_once_with("http://host", token="my_token")
    assert result == "token_auth_instance"


def test_get_auth_explicit_server_type_kwarg():
    """Line 22: server_type kwarg is popped and used as key."""
    mock_factory = MagicMock(return_value="ok")
    mock_config = MagicMock(auth_factory=mock_factory)

    with patch("nxdrive.drive.server_type.get", return_value=mock_config) as mock_get:
        from nxdrive.drive.auth import get_auth

        get_auth("http://host", "tok", server_type="ALFRESCO")

    mock_get.assert_called_once_with("ALFRESCO")


# --------------------------------------------------------------------------
# __getattr__ tests
# --------------------------------------------------------------------------


def test_getattr_raises_for_unknown_name():
    """Line 47-48: name != 'OAuthentication' → AttributeError."""
    from nxdrive.drive import auth

    with pytest.raises(AttributeError, match="UnknownName"):
        _ = auth.__getattr__("UnknownName")


def test_getattr_oauthentication_returns_loaded_class():
    """Lines 50, 52-53: resolves OAuthentication through server-type registry."""
    mock_klass = MagicMock()
    mock_config = MagicMock(oauth2_class_path="some.module.OAuthClass")

    with patch("nxdrive.drive.server_type.get_default_key", return_value="NUXEO"), \
         patch("nxdrive.drive.server_type.get", return_value=mock_config), \
         patch("nxdrive.drive.server_type.load_class", return_value=mock_klass):
        from nxdrive.drive import auth

        result = auth.__getattr__("OAuthentication")

    assert result is mock_klass


def test_getattr_oauthentication_fallback_to_base():
    """Line 54: load_class returns None → fallback to OAuthenticationBase."""
    mock_config = MagicMock(oauth2_class_path="")

    with patch("nxdrive.drive.server_type.get_default_key", return_value="NUXEO"), \
         patch("nxdrive.drive.server_type.get", return_value=mock_config), \
         patch("nxdrive.drive.server_type.load_class", return_value=None):
        from nxdrive.drive import auth

        result = auth.__getattr__("OAuthentication")

    assert result.__name__ == "OAuthenticationBase"
