"""Unit tests for nxdrive.alfresco.auth.oauth2 discovery functions."""

from unittest.mock import MagicMock, patch

from nxdrive.alfresco.auth.oauth2 import (
    _release_loopback_state,
    discover_aims_config,
    probe_capabilities,
)


class TestDiscoverAimsConfigDeviceSync:
    """Strategy 0: Device Sync /config endpoint."""

    def test_success_returns_full_config(self):
        isc = MagicMock()
        isc.openid_configuration_url.return_value = (
            "https://idp/realms/alfresco/.well-known/openid-configuration"
        )
        isc.client_id = "drive"
        isc.audience = "acs-api"
        isc.public_client = True
        isc.enable_pkce = True
        isc.enable_basic_auth = False
        isc.client_secret = "s3cret"

        mock_client = MagicMock()
        mock_client.device_sync.get_identity_service_config.return_value = isc

        with patch("alfresco.Alfresco", return_value=mock_client):
            result = discover_aims_config("https://acs.example.com")

        assert (
            result["openid_configuration_url"]
            == "https://idp/realms/alfresco/.well-known/openid-configuration"
        )
        assert result["client_id"] == "drive"
        assert result["audience"] == "acs-api"
        assert result["public_client"] is True
        assert result["enable_pkce"] is True
        assert result["enable_basic_auth"] is False
        assert result["client_secret"] == "s3cret"

    def test_no_client_secret_omits_key(self):
        isc = MagicMock()
        isc.openid_configuration_url.return_value = (
            "https://idp/.well-known/openid-configuration"
        )
        isc.client_id = "alfresco"
        isc.audience = ""
        isc.public_client = True
        isc.enable_pkce = True
        isc.enable_basic_auth = True
        isc.client_secret = None

        mock_client = MagicMock()
        mock_client.device_sync.get_identity_service_config.return_value = isc

        with patch("alfresco.Alfresco", return_value=mock_client):
            result = discover_aims_config("https://server")

        assert "client_secret" not in result

    def test_device_sync_exception_falls_through(self):
        """When Device Sync fails, the function falls through to next strategy."""
        with patch(
            "alfresco.Alfresco",
            side_effect=ImportError("no alfresco"),
        ):
            with patch("nxdrive.alfresco.auth.oauth2.requests.get") as mock_get:
                mock_get.return_value = MagicMock(ok=False)
                result = discover_aims_config("https://server")
        assert result == {}


class TestDiscoverAimsConfigSyncService:
    """Strategy 1: syncServiceConfiguration endpoint."""

    def _mock_response(self, json_data, ok=True):
        resp = MagicMock()
        resp.ok = ok
        resp.json.return_value = json_data
        return resp

    def test_success_via_identity_service_config(self):
        json_data = {
            "identityServiceConfig": {
                "authServerUrl": "https://keycloak.example.com/auth",
                "realm": "myco",
                "resource": "drive-client",
                "credentialsSecret": "client-secret",
            }
        }
        with patch("alfresco.Alfresco", side_effect=Exception):
            with patch(
                "nxdrive.alfresco.auth.oauth2.requests.get",
                return_value=self._mock_response(json_data),
            ):
                result = discover_aims_config("https://acs.example.com")

        assert (
            result["openid_configuration_url"]
            == "https://keycloak.example.com/auth/realms/myco/.well-known/openid-configuration"
        )
        assert result["client_id"] == "drive-client"
        assert result["client_secret"] == "client-secret"
        assert result["public_client"] is True
        assert result["enable_pkce"] is True

    def test_url_ending_in_alfresco_not_doubled(self):
        json_data = {
            "identityServiceConfig": {
                "authServerUrl": "https://kc/auth",
                "realm": "alfresco",
                "resource": "alfresco",
            }
        }
        with patch("alfresco.Alfresco", side_effect=Exception):
            with patch(
                "nxdrive.alfresco.auth.oauth2.requests.get",
                return_value=self._mock_response(json_data),
            ) as mock_get:
                discover_aims_config("https://acs.example.com/alfresco")
        # The URL should NOT be doubled
        call_url = mock_get.call_args_list[0][0][0]
        assert "/alfresco/alfresco/" not in call_url


class TestDiscoverAimsConfigAppConfig:
    """Strategy 2: app.config.json discovery."""

    def test_success_via_app_config_json(self):
        sync_resp = MagicMock(ok=False)
        app_resp = MagicMock(ok=True)
        app_resp.json.return_value = {
            "oauth2": {
                "host": "https://idp.example.com/realms/alfresco",
                "clientId": "custom_client",
            }
        }

        def side_effect(url, **kwargs):
            if "syncServiceConfiguration" in url:
                return sync_resp
            return app_resp

        with patch("alfresco.Alfresco", side_effect=Exception):
            with patch(
                "nxdrive.alfresco.auth.oauth2.requests.get", side_effect=side_effect
            ):
                result = discover_aims_config("https://server.example.com")

        assert (
            result["openid_configuration_url"]
            == "https://idp.example.com/realms/alfresco/.well-known/openid-configuration"
        )
        assert result["client_id"] == "custom_client"


class TestDiscoverAimsConfigKeycloakHeuristic:
    """Strategy 3: well-known Keycloak heuristic."""

    def test_success_via_keycloak_well_known(self):
        fail_resp = MagicMock(ok=False)
        kc_resp = MagicMock(ok=True)
        kc_resp.json.return_value = {
            "authorization_endpoint": "https://kc/auth/realms/alfresco/protocol/openid-connect/auth"
        }

        def side_effect(url, **kwargs):
            if "well-known/openid-configuration" in url:
                return kc_resp
            return fail_resp

        with patch("alfresco.Alfresco", side_effect=Exception):
            with patch(
                "nxdrive.alfresco.auth.oauth2.requests.get", side_effect=side_effect
            ):
                result = discover_aims_config("https://server.example.com")

        assert "openid-configuration" in result["openid_configuration_url"]
        assert result["client_id"] == "alfresco"


class TestDiscoverAimsConfigAllFail:
    """All strategies fail → returns empty dict."""

    def test_returns_empty_dict(self):
        with patch("alfresco.Alfresco", side_effect=Exception):
            with patch(
                "nxdrive.alfresco.auth.oauth2.requests.get",
                side_effect=Exception("network"),
            ):
                result = discover_aims_config("https://unreachable.com")
        assert result == {}


class TestProbeCapabilities:
    """Tests for the probe_capabilities wrapper."""

    def test_delegates_to_discover(self):
        aims = {
            "openid_configuration_url": "https://idp/.well-known/openid-configuration",
            "client_id": "drive",
            "audience": "acs-api",
            "public_client": True,
            "enable_pkce": True,
            "enable_basic_auth": False,
        }
        with patch(
            "nxdrive.alfresco.auth.oauth2.discover_aims_config", return_value=aims
        ):
            result = probe_capabilities("https://acs.example.com")

        assert result["discovered"] is True
        assert result["client_id"] == "drive"
        assert result["enable_basic_auth"] is False
        assert result["enable_pkce"] is True
        assert result["audience"] == "acs-api"

    def test_permissive_defaults_when_discovery_fails(self):
        with patch(
            "nxdrive.alfresco.auth.oauth2.discover_aims_config", return_value={}
        ):
            result = probe_capabilities("https://unreachable.com")

        assert result["discovered"] is False
        assert result["enable_basic_auth"] is True
        assert result["enable_pkce"] is True
        assert result["public_client"] is True
        assert result["client_id"] == "alfresco"
        assert result["openid_configuration_url"] == ""


class TestReleaseLoopbackState:
    """Tests for the _release_loopback_state helper."""

    def test_no_state_is_noop(self):
        api = MagicMock(spec=[])  # no _alfresco_loopback_state attribute
        _release_loopback_state(api)  # should not raise

    def test_shutdown_called_and_state_cleared(self):
        server = MagicMock()
        bridge = MagicMock()
        api = MagicMock()
        api._alfresco_loopback_state = (bridge, server)

        _release_loopback_state(api)

        server.shutdown.assert_called_once()
        assert api._alfresco_loopback_state is None

    def test_shutdown_exception_does_not_propagate(self):
        server = MagicMock()
        server.shutdown.side_effect = OSError("already closed")
        api = MagicMock()
        api._alfresco_loopback_state = (MagicMock(), server)

        # Should NOT raise
        _release_loopback_state(api)
