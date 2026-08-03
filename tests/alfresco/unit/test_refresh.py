"""Unit tests for nxdrive.alfresco.auth.refresh."""

from unittest.mock import MagicMock, patch

import pytest
from alfresco.exceptions import AuthenticationError

from nxdrive.alfresco.auth.refresh import RefreshingOAuth2Auth


class TestFromToken:
    """Tests for the factory classmethod."""

    def test_creates_instance_with_callback(self):
        callback = MagicMock()
        with patch.object(
            RefreshingOAuth2Auth.__bases__[0],
            "from_token",
            return_value=RefreshingOAuth2Auth.__new__(RefreshingOAuth2Auth),
        ):
            inst = RefreshingOAuth2Auth.from_token(
                "access_tok", on_refresh=callback, refresh_token="ref_tok"
            )
            assert inst._on_refresh is callback

    def test_creates_instance_without_callback(self):
        with patch.object(
            RefreshingOAuth2Auth.__bases__[0],
            "from_token",
            return_value=RefreshingOAuth2Auth.__new__(RefreshingOAuth2Auth),
        ):
            inst = RefreshingOAuth2Auth.from_token("access_tok")
            assert inst._on_refresh is None


class TestTokenRequest:
    """Tests for _token_request persistence hook."""

    def test_callback_invoked_with_token_snapshot(self):
        callback = MagicMock()
        inst = RefreshingOAuth2Auth.__new__(RefreshingOAuth2Auth)
        inst._on_refresh = callback
        inst._access_token = "old_access"
        inst._refresh_token = "old_refresh"
        inst._expires_at = 9999
        inst.token_url = "https://idp/token"
        inst.client_id = "my_client"
        inst.client_secret = ""

        with patch.object(
            RefreshingOAuth2Auth.__bases__[0],
            "_token_request",
            return_value="new_access",
        ):
            # After super() call, attrs are updated
            inst._access_token = "new_access"
            inst._refresh_token = "new_refresh"
            inst._expires_at = 10000

            result = RefreshingOAuth2Auth._token_request(
                inst, {"grant_type": "refresh_token"}
            )

        assert result == "new_access"
        callback.assert_called_once()
        snapshot = callback.call_args[0][0]
        assert snapshot["access_token"] == "new_access"
        assert snapshot["refresh_token"] == "new_refresh"
        assert snapshot["expires_at"] == 10000
        assert snapshot["token_url"] == "https://idp/token"
        assert snapshot["client_id"] == "my_client"

    def test_callback_exception_does_not_propagate(self):
        callback = MagicMock(side_effect=RuntimeError("DAO write failed"))
        inst = RefreshingOAuth2Auth.__new__(RefreshingOAuth2Auth)
        inst._on_refresh = callback
        inst._access_token = "acc"
        inst._refresh_token = "ref"
        inst._expires_at = 100
        inst.token_url = ""
        inst.client_id = ""
        inst.client_secret = ""

        with patch.object(
            RefreshingOAuth2Auth.__bases__[0],
            "_token_request",
            return_value="acc",
        ):
            # Should NOT raise
            result = RefreshingOAuth2Auth._token_request(inst, {})
        assert result == "acc"

    def test_no_callback_still_works(self):
        inst = RefreshingOAuth2Auth.__new__(RefreshingOAuth2Auth)
        inst._on_refresh = None
        inst._access_token = "acc"
        inst._refresh_token = "ref"
        inst._expires_at = 100
        inst.token_url = ""
        inst.client_id = ""
        inst.client_secret = ""

        with patch.object(
            RefreshingOAuth2Auth.__bases__[0],
            "_token_request",
            return_value="acc",
        ):
            result = RefreshingOAuth2Auth._token_request(inst, {})
        assert result == "acc"


class TestInvalidate:
    """Tests for the invalidate override."""

    def test_refresh_succeeds_does_not_raise(self):
        inst = RefreshingOAuth2Auth.__new__(RefreshingOAuth2Auth)
        inst._refresh_token = "valid_refresh"
        inst.refresh = MagicMock()

        # Should NOT raise — refresh succeeded
        inst.invalidate()
        inst.refresh.assert_called_once()

    def test_refresh_fails_raises_authentication_error(self):
        inst = RefreshingOAuth2Auth.__new__(RefreshingOAuth2Auth)
        inst._refresh_token = "valid_refresh"
        inst.refresh = MagicMock(side_effect=RuntimeError("expired"))

        with patch.object(
            RefreshingOAuth2Auth.__bases__[0], "invalidate"
        ) as mock_super_inv:
            with pytest.raises(AuthenticationError, match="re-authentication required"):
                inst.invalidate()
            mock_super_inv.assert_called_once()

    def test_no_refresh_token_raises_authentication_error(self):
        inst = RefreshingOAuth2Auth.__new__(RefreshingOAuth2Auth)
        inst._refresh_token = None

        with patch.object(
            RefreshingOAuth2Auth.__bases__[0], "invalidate"
        ) as mock_super_inv:
            with pytest.raises(AuthenticationError):
                inst.invalidate()
            mock_super_inv.assert_called_once()


class TestRefresh:
    """Tests for the refresh override."""

    def test_success_returns_token(self):
        inst = RefreshingOAuth2Auth.__new__(RefreshingOAuth2Auth)
        with patch.object(
            RefreshingOAuth2Auth.__bases__[0],
            "refresh",
            return_value="new_token",
        ):
            assert RefreshingOAuth2Auth.refresh(inst) == "new_token"

    def test_runtime_error_becomes_authentication_error(self):
        inst = RefreshingOAuth2Auth.__new__(RefreshingOAuth2Auth)
        with patch.object(
            RefreshingOAuth2Auth.__bases__[0],
            "refresh",
            side_effect=RuntimeError("grant_type not configured"),
        ):
            with pytest.raises(AuthenticationError, match="grant_type not configured"):
                RefreshingOAuth2Auth.refresh(inst)


class TestExpirySKew:
    """Verify class constant."""

    def test_expiry_skew_is_60(self):
        assert RefreshingOAuth2Auth._EXPIRY_SKEW == 60
