"""Unit tests for nxdrive.alfresco.auth.oauth2 discovery functions."""

import sys
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from nxdrive.alfresco.auth.oauth2 import (
    _release_loopback_state,
    discover_aims_config,
    probe_capabilities,
)


@contextmanager
def _mock_loopback_dependencies(app, *, start_result=None, start_error=None):
    """Mock Qt and the loopback server imported by ``_start_loopback_flow``."""
    from nxdrive.drive.qt import imports as qt_imports

    signal = MagicMock()
    qt_core = ModuleType("PyQt6.QtCore")

    class QObject:
        pass

    qt_core.QObject = QObject
    qt_core.pyqtSignal = MagicMock(return_value=signal)
    pyqt6 = ModuleType("PyQt6")
    pyqt6.QtCore = qt_core

    qapplication = MagicMock()
    qapplication.instance.return_value = app
    server = MagicMock()
    if start_error is not None:
        server.start.side_effect = start_error
    else:
        server.start.return_value = start_result or "http://127.0.0.1:43123/callback"

    with patch.dict(
        sys.modules, {"PyQt6": pyqt6, "PyQt6.QtCore": qt_core}
    ), patch.object(qt_imports, "QApplication", qapplication), patch(
        "nxdrive.alfresco.auth.loopback.LoopbackAuthServer", return_value=server
    ):
        yield SimpleNamespace(
            qapplication=qapplication,
            server=server,
            signal=signal,
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


# --- NEW TESTS BELOW ---


class TestProbeCapabilitiesExtended:
    """Additional edge-case tests for probe_capabilities."""

    def test_returns_discovered_true_when_aims_found(self):
        aims = {
            "openid_configuration_url": "https://idp/.well-known/openid-configuration",
            "client_id": "custom",
            "audience": "my-api",
            "public_client": False,
            "enable_pkce": False,
            "enable_basic_auth": True,
        }
        with patch(
            "nxdrive.alfresco.auth.oauth2.discover_aims_config", return_value=aims
        ):
            result = probe_capabilities("https://server")
        assert result["discovered"] is True
        assert result["public_client"] is False
        assert result["enable_pkce"] is False
        assert result["audience"] == "my-api"

    def test_returns_discovered_false_when_empty(self):
        with patch(
            "nxdrive.alfresco.auth.oauth2.discover_aims_config", return_value={}
        ):
            result = probe_capabilities("https://server")
        assert result["discovered"] is False
        assert result["openid_configuration_url"] == ""


class TestReleaseLoopbackStateExtended:
    """Additional edge-case tests for _release_loopback_state."""

    def test_state_is_none_explicit(self):
        api = MagicMock()
        api._alfresco_loopback_state = None
        # Should not raise, should not call shutdown
        _release_loopback_state(api)

    def test_clearing_state_fails_does_not_propagate(self):
        """When setting api._alfresco_loopback_state = None raises."""
        server = MagicMock()
        bridge = MagicMock()

        class _StubApi:
            _alfresco_loopback_state = (bridge, server)

            def __setattr__(self, key, value):
                if key == "_alfresco_loopback_state" and value is None:
                    raise AttributeError("read-only")
                super().__setattr__(key, value)

        api = _StubApi()
        # Should not propagate
        _release_loopback_state(api)
        server.shutdown.assert_called_once()


class TestAlfrescoOAuthApplyAimsDiscovery:
    """Tests for AlfrescoOAuthentication._apply_aims_discovery."""

    def _make_auth(self):
        """Create an AlfrescoOAuthentication with mocked internals."""
        with patch(
            "nxdrive.alfresco.auth.oauth2.discover_aims_config", return_value={}
        ), patch("nxdrive.alfresco.auth.oauth2.AlfrescoOAuthentication._build_oauth2"):
            from nxdrive.alfresco.auth.oauth2 import AlfrescoOAuthentication

            auth = AlfrescoOAuthentication.__new__(AlfrescoOAuthentication)
            auth.url = "https://acs.example.com"
            auth.verification_needed = True
            auth._oauth2_openid_configuration_url = ""
            auth._oauth2_client_id = "alfresco"
            auth._oauth2_client_secret = ""
            auth._oauth2_audience = ""
            auth._oauth2_public_client = True
            auth._oauth2_enable_pkce = True
            auth._oauth2_enable_basic_auth = True
            auth._dao = None
            auth.token = None
            auth._subclient_kwargs = {}
            return auth

    def test_copies_all_fields(self):
        auth = self._make_auth()
        aims = {
            "openid_configuration_url": "https://idp/.well-known/openid-configuration",
            "client_id": "my-client",
            "client_secret": "s3cret",
            "audience": "acs",
            "public_client": False,
            "enable_pkce": True,
            "enable_basic_auth": False,
        }
        auth._apply_aims_discovery(aims)
        assert (
            auth._oauth2_openid_configuration_url
            == "https://idp/.well-known/openid-configuration"
        )
        assert auth._oauth2_client_id == "my-client"
        assert auth._oauth2_client_secret == "s3cret"
        assert auth._oauth2_audience == "acs"
        assert auth._oauth2_public_client is False
        assert auth._oauth2_enable_pkce is True
        assert auth._oauth2_enable_basic_auth is False

    def test_missing_secret_preserves_existing(self):
        auth = self._make_auth()
        auth._oauth2_client_secret = "old-secret"
        aims = {
            "openid_configuration_url": "https://idp/.wk",
            "client_id": "x",
        }
        auth._apply_aims_discovery(aims)
        assert auth._oauth2_client_secret == "old-secret"

    def test_defaults_for_missing_keys(self):
        auth = self._make_auth()
        aims = {
            "openid_configuration_url": "https://idp/.wk",
        }
        auth._apply_aims_discovery(aims)
        assert auth._oauth2_client_id == "alfresco"
        assert auth._oauth2_audience == ""
        assert auth._oauth2_public_client is True
        assert auth._oauth2_enable_pkce is True
        assert auth._oauth2_enable_basic_auth is True


class TestAlfrescoOAuthConnectUrl:
    """Tests for the browser authorization URL preparation."""

    def _make_auth(self, *, has_endpoint=True, dao=True):
        from nxdrive.alfresco.auth.oauth2 import AlfrescoOAuthentication

        auth = AlfrescoOAuthentication.__new__(AlfrescoOAuthentication)
        auth.url = "https://acs.example.com"
        auth.verification_needed = False
        auth._oauth2_audience = ""
        auth._dao = MagicMock() if dao else None
        auth.auth = MagicMock()
        auth.auth.authorization_endpoint = (
            "https://idp.example.com/authorize" if has_endpoint else None
        )
        auth.auth.create_authorization_url.return_value = (
            "https://idp.example.com/login",
            "generated-state",
            "generated-verifier",
        )
        return auth

    def test_builds_url_with_audience_and_persists_flow_state(self):
        auth = self._make_auth()
        auth._oauth2_audience = "acs-api"
        loopback_uri = "http://127.0.0.1:43123/callback"

        with patch(
            "nxdrive.drive.options.Options",
            SimpleNamespace(oauth2_scope="openid profile"),
        ), patch.object(
            auth, "_start_loopback_flow", return_value=loopback_uri
        ) as start, patch.object(
            auth, "_build_oauth2"
        ) as build:
            result = auth.connect_url()

        assert result == "https://idp.example.com/login"
        start.assert_called_once_with()
        build.assert_called_once_with(redirect_uri_override=loopback_uri)
        auth.auth.create_authorization_url.assert_called_once_with(
            scope="openid profile", audience="acs-api"
        )
        assert auth._dao.update_config.call_args_list == [
            call("tmp_oauth2_url", "https://acs.example.com"),
            call("tmp_oauth2_code_verifier", "generated-verifier"),
            call("tmp_oauth2_state", "generated-state"),
            call("tmp_oauth2_redirect_uri", loopback_uri),
        ]

    def test_uses_openid_default_without_audience_or_dao(self):
        auth = self._make_auth(dao=False)

        with patch(
            "nxdrive.drive.options.Options", SimpleNamespace(oauth2_scope="")
        ), patch.object(
            auth,
            "_start_loopback_flow",
            return_value="http://127.0.0.1:43123/callback",
        ), patch.object(
            auth, "_build_oauth2"
        ):
            result = auth.connect_url()

        assert result == "https://idp.example.com/login"
        auth.auth.create_authorization_url.assert_called_once_with(scope="openid")

    def test_retries_discovery_before_starting_loopback(self):
        auth = self._make_auth(has_endpoint=False)
        aims = {
            "openid_configuration_url": "https://idp.example.com/.well-known",
            "client_id": "drive",
        }
        loopback_uri = "http://127.0.0.1:43123/callback"

        def apply_discovery(discovered):
            assert discovered is aims
            auth.auth.authorization_endpoint = "https://idp.example.com/authorize"

        with patch(
            "nxdrive.alfresco.auth.oauth2.discover_aims_config", return_value=aims
        ) as discover, patch.object(
            auth, "_apply_aims_discovery", side_effect=apply_discovery
        ) as apply, patch.object(
            auth, "_build_oauth2"
        ) as build, patch.object(
            auth, "_start_loopback_flow", return_value=loopback_uri
        ):
            result = auth.connect_url()

        assert result == "https://idp.example.com/login"
        discover.assert_called_once_with("https://acs.example.com", verify=False)
        apply.assert_called_once_with(aims)
        assert build.call_args_list == [
            call(),
            call(redirect_uri_override=loopback_uri),
        ]

    def test_raises_when_discovery_still_has_no_authorization_endpoint(self):
        from alfresco.exceptions import OAuth2Error

        auth = self._make_auth(has_endpoint=False)

        with patch(
            "nxdrive.alfresco.auth.oauth2.discover_aims_config", return_value={}
        ) as discover, patch.object(auth, "_start_loopback_flow") as start:
            with pytest.raises(OAuth2Error, match="Could not discover.*AIMS"):
                auth.connect_url()

        discover.assert_called_once_with("https://acs.example.com", verify=False)
        start.assert_not_called()


class TestAlfrescoOAuthStartLoopbackFlow:
    """Tests for the Qt bridge without creating UI, sockets, or threads."""

    def _make_auth(self):
        from nxdrive.alfresco.auth.oauth2 import AlfrescoOAuthentication

        return AlfrescoOAuthentication.__new__(AlfrescoOAuthentication)

    @pytest.mark.parametrize(
        "app", [None, SimpleNamespace()], ids=["no-application", "no-api"]
    )
    def test_requires_qt_api(self, app):
        from alfresco.exceptions import OAuth2Error

        auth = self._make_auth()
        with _mock_loopback_dependencies(app) as mocked:
            with pytest.raises(OAuth2Error, match="Qt application is not initialised"):
                auth._start_loopback_flow()

        mocked.server.start.assert_not_called()

    def test_connects_bridge_emits_callback_and_pins_state(self):
        auth = self._make_auth()
        api = SimpleNamespace(
            continue_oauth2_flow=MagicMock(),
            _alfresco_loopback_state=("old-bridge", "old-server"),
        )
        query = {"code": "authorization-code", "state": "expected-state"}

        with _mock_loopback_dependencies(api_app := SimpleNamespace(api=api)) as mocked:
            assert api_app.api is api
            with patch(
                "nxdrive.alfresco.auth.oauth2._release_loopback_state"
            ) as release:
                result = auth._start_loopback_flow()
                callback = mocked.server.start.call_args.kwargs["on_callback"]
                callback(query)

        assert result == "http://127.0.0.1:43123/callback"
        release.assert_called_once_with(api)
        mocked.signal.connect.assert_called_once_with(api.continue_oauth2_flow)
        mocked.signal.emit.assert_called_once_with(query)
        bridge, pinned_server = api._alfresco_loopback_state
        assert bridge.callback_received is mocked.signal
        assert pinned_server is mocked.server

    def test_server_start_error_is_converted_to_oauth_error(self):
        from alfresco.exceptions import OAuth2Error

        auth = self._make_auth()
        previous_state = object()
        api = SimpleNamespace(
            continue_oauth2_flow=MagicMock(),
            _alfresco_loopback_state=previous_state,
        )

        with _mock_loopback_dependencies(
            SimpleNamespace(api=api), start_error=RuntimeError("bind denied")
        ) as mocked, patch(
            "nxdrive.alfresco.auth.oauth2._release_loopback_state"
        ) as release:
            with pytest.raises(OAuth2Error, match="bind denied"):
                auth._start_loopback_flow()

        release.assert_called_once_with(api)
        mocked.server.start.assert_called_once()
        assert api._alfresco_loopback_state is previous_state

    def test_bridge_reraises_signal_emit_failure(self):
        auth = self._make_auth()
        api = SimpleNamespace(
            continue_oauth2_flow=MagicMock(), _alfresco_loopback_state=None
        )

        with _mock_loopback_dependencies(SimpleNamespace(api=api)) as mocked, patch(
            "nxdrive.alfresco.auth.oauth2._release_loopback_state"
        ):
            auth._start_loopback_flow()
            callback = mocked.server.start.call_args.kwargs["on_callback"]
            mocked.signal.emit.side_effect = RuntimeError("receiver deleted")
            with pytest.raises(RuntimeError, match="receiver deleted"):
                callback({"code": "code", "state": "state"})


class TestAlfrescoOAuthGetUsername:
    """Tests for AlfrescoOAuthentication.get_username (People API)."""

    def _make_auth_with_token(self, token):
        from nxdrive.alfresco.auth.oauth2 import AlfrescoOAuthentication

        auth = AlfrescoOAuthentication.__new__(AlfrescoOAuthentication)
        auth.url = "https://acs.example.com"
        auth.verification_needed = True
        auth.auth = MagicMock()
        auth.auth.token = token
        return auth

    def test_returns_username_from_people_api(self):
        auth = self._make_auth_with_token(
            {"access_token": "tok123", "refresh_token": "r"}
        )
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"entry": {"id": "jdoe"}}
        with patch("nxdrive.alfresco.auth.oauth2.requests.get", return_value=resp) as m:
            result = auth.get_username()
        assert result == "jdoe"
        call_url = m.call_args[0][0]
        assert (
            "/alfresco/api/-default-/public/alfresco/versions/1/people/-me-" in call_url
        )

    def test_returns_empty_when_no_token(self):
        auth = self._make_auth_with_token(None)
        assert auth.get_username() == ""

    def test_url_already_ending_in_alfresco(self):
        auth = self._make_auth_with_token({"access_token": "tok"})
        auth.url = "https://acs.example.com/alfresco"
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"entry": {"id": "admin"}}
        with patch("nxdrive.alfresco.auth.oauth2.requests.get", return_value=resp) as m:
            result = auth.get_username()
        assert result == "admin"
        call_url = m.call_args[0][0]
        assert "/alfresco/alfresco/" not in call_url

    def test_string_token_used_as_bearer(self):
        auth = self._make_auth_with_token("raw-token-string")
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"entry": {"id": "user1"}}
        with patch("nxdrive.alfresco.auth.oauth2.requests.get", return_value=resp) as m:
            result = auth.get_username()
        assert result == "user1"
        headers = m.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer raw-token-string"


class TestAlfrescoOAuthGetTokenDict:
    """Tests for AlfrescoOAuthentication.get_token_dict."""

    def _make_auth(self, token, *, client_secret=None):
        from nxdrive.alfresco.auth.oauth2 import AlfrescoOAuthentication

        auth = AlfrescoOAuthentication.__new__(AlfrescoOAuthentication)
        auth.auth = MagicMock()
        auth.auth.token = token
        auth.auth.token_endpoint = "https://idp/token"
        auth.auth.client_id = "drive"
        if client_secret:
            auth.auth.client_secret = client_secret
        else:
            auth.auth.client_secret = None
        return auth

    def test_returns_full_dict(self):
        token = {
            "access_token": "acc",
            "refresh_token": "ref",
            "expires_at": 1234567890,
        }
        auth = self._make_auth(token)
        result = auth.get_token_dict()
        assert result["access_token"] == "acc"
        assert result["refresh_token"] == "ref"
        assert result["expires_at"] == 1234567890
        assert result["token_url"] == "https://idp/token"
        assert result["client_id"] == "drive"
        assert "client_secret" not in result

    def test_includes_client_secret_when_set(self):
        token = {"access_token": "acc", "refresh_token": "ref", "expires_at": 0}
        auth = self._make_auth(token, client_secret="s3cret")
        result = auth.get_token_dict()
        assert result["client_secret"] == "s3cret"

    def test_returns_none_when_no_token(self):
        auth = self._make_auth(None)
        assert auth.get_token_dict() is None

    def test_returns_none_when_token_is_string(self):
        auth = self._make_auth("just-a-string")
        assert auth.get_token_dict() is None


class TestAlfrescoOAuthGetToken:
    """Tests for AlfrescoOAuthentication.get_token overrides."""

    def _make_auth(self):
        from nxdrive.alfresco.auth.oauth2 import AlfrescoOAuthentication

        auth = AlfrescoOAuthentication.__new__(AlfrescoOAuthentication)
        auth.url = "https://acs.example.com"
        auth.verification_needed = True
        auth._oauth2_audience = ""
        auth._dao = MagicMock()
        auth._dao.get_config.return_value = None
        auth.auth = MagicMock()
        auth.auth.token_endpoint = "https://idp/token"
        auth.auth.client_id = "drive"
        auth.auth.client_secret = None
        auth.token = None
        return auth

    def test_redirect_uri_restored_from_dao(self):
        auth = self._make_auth()
        auth._dao.get_config.return_value = "http://127.0.0.1:12345/callback"
        auth.auth.request_token.return_value = {
            "access_token": "a",
            "refresh_token": "r",
        }

        with patch.object(auth, "_build_oauth2") as build:
            with patch("nxdrive.drive.qt.imports.QApplication") as mock_app:
                mock_app.instance.return_value = None
                auth.get_token(code_verifier="v", code="c", state="s")
        build.assert_called_once_with(
            redirect_uri_override="http://127.0.0.1:12345/callback"
        )

    def test_audience_injected_when_set(self):
        from nxdrive.drive.auth.oauth2 import OAuthenticationBase

        auth = self._make_auth()
        auth._oauth2_audience = "acs-api"
        auth._dao.get_config.return_value = None

        with patch.object(
            OAuthenticationBase, "get_token", return_value={"access_token": "a"}
        ) as get_token, patch("nxdrive.drive.qt.imports.QApplication") as mock_app:
            mock_app.instance.return_value = None
            result = auth.get_token(code_verifier="v", code="c", state="s")

        assert isinstance(result, dict)
        get_token.assert_called_once_with(
            code_verifier="v", code="c", state="s", audience="acs-api"
        )

    def test_oauth2error_wrapped_as_remote_oauth2_error(self):
        from alfresco.exceptions import OAuth2Error

        from nxdrive.drive.exceptions import RemoteOAuth2Error

        auth = self._make_auth()
        auth._dao.get_config.return_value = None
        auth.auth.request_token.side_effect = OAuth2Error("bad code")

        with patch("nxdrive.drive.qt.imports.QApplication") as mock_app:
            mock_app.instance.return_value = None
            with pytest.raises(RemoteOAuth2Error):
                auth.get_token(code_verifier="v", code="c", state="s")

    def test_dao_key_deleted_in_finally(self):
        auth = self._make_auth()
        auth._dao.get_config.return_value = None
        auth.auth.request_token.return_value = {"access_token": "a"}

        with patch("nxdrive.drive.qt.imports.QApplication") as mock_app:
            mock_app.instance.return_value = None
            auth.get_token(code_verifier="v", code="c", state="s")
        auth._dao.delete_config.assert_called_with("tmp_oauth2_redirect_uri")

    def test_token_enriched_with_endpoint_metadata(self):
        auth = self._make_auth()
        auth._dao.get_config.return_value = None
        auth.auth.request_token.return_value = {
            "access_token": "a",
            "refresh_token": "r",
            "expires_at": 9999,
        }

        with patch("nxdrive.drive.qt.imports.QApplication") as mock_app:
            mock_app.instance.return_value = None
            result = auth.get_token(code_verifier="v", code="c", state="s")
        assert result["token_url"] == "https://idp/token"
        assert result["client_id"] == "drive"

    def test_token_enriched_with_confidential_client_secret(self):
        auth = self._make_auth()
        auth._dao.get_config.return_value = None
        auth.auth.client_secret = "confidential-secret"
        auth.auth.request_token.return_value = {"access_token": "a"}

        with patch("nxdrive.drive.qt.imports.QApplication") as mock_app:
            mock_app.instance.return_value = None
            result = auth.get_token(code_verifier="v", code="c", state="s")

        assert result["client_secret"] == "confidential-secret"

    def test_generic_token_error_is_reraised_and_dao_key_is_deleted(self):
        auth = self._make_auth()
        auth._dao.get_config.return_value = None
        error = ValueError("malformed token response")
        auth.auth.request_token.side_effect = error

        with patch("nxdrive.drive.qt.imports.QApplication") as mock_app:
            mock_app.instance.return_value = None
            with pytest.raises(ValueError) as exc_info:
                auth.get_token(code_verifier="v", code="c", state="s")

        assert exc_info.value is error
        auth._dao.delete_config.assert_called_once_with("tmp_oauth2_redirect_uri")

    def test_success_releases_loopback_state_from_qt_api(self):
        auth = self._make_auth()
        auth.auth.request_token.return_value = {"access_token": "a"}
        api = MagicMock()

        with patch("nxdrive.drive.qt.imports.QApplication") as mock_app, patch(
            "nxdrive.alfresco.auth.oauth2._release_loopback_state"
        ) as release:
            mock_app.instance.return_value = SimpleNamespace(api=api)
            auth.get_token(code_verifier="v", code="c", state="s")

        release.assert_called_once_with(api)
        auth._dao.delete_config.assert_called_once_with("tmp_oauth2_redirect_uri")

    def test_loopback_release_error_is_logged_without_masking_result(self):
        auth = self._make_auth()
        auth.auth.request_token.return_value = {"access_token": "a"}
        api = MagicMock()

        with patch("nxdrive.drive.qt.imports.QApplication") as mock_app, patch(
            "nxdrive.alfresco.auth.oauth2._release_loopback_state",
            side_effect=RuntimeError("shutdown failed"),
        ), patch("nxdrive.alfresco.auth.oauth2.log.debug") as debug:
            mock_app.instance.return_value = SimpleNamespace(api=api)
            result = auth.get_token(code_verifier="v", code="c", state="s")

        assert result["access_token"] == "a"
        debug.assert_called_once_with("Loopback: release failed", exc_info=True)
        auth._dao.delete_config.assert_called_once_with("tmp_oauth2_redirect_uri")
