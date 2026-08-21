"""
OAuth2 / AIMS authentication for Alfresco Content Services.

Uses ``alfresco.OAuth2`` (an OpenID Connect / authlib wrapper that
supports PKCE) and resolves the authenticated username via the
Alfresco People API.

The AIMS/Keycloak endpoints are auto-discovered from the Alfresco
server via the ``syncServiceConfiguration`` API so the user only
needs to enter the server URL.
"""

from logging import getLogger
from typing import TYPE_CHECKING, Any, Dict, Optional

import requests
from alfresco.exceptions import OAuth2Error

from nxdrive.drive.auth.oauth2 import OAuthenticationBase
from nxdrive.drive.exceptions import RemoteOAuth2Error

if TYPE_CHECKING:
    from nxdrive.drive.auth import Token
    from nxdrive.drive.dao.base import BaseDAO

__all__ = ("AlfrescoOAuthentication", "discover_aims_config", "probe_capabilities")

log = getLogger(__name__)

# Default AIMS / Keycloak client identifier used by Alfresco deployments.
_DEFAULT_CLIENT_ID = "alfresco"


class _NoAuth(requests.auth.AuthBase):
    """No-op ``requests`` auth handler.

    The Alfresco Device Sync ``/config`` webscript is intentionally
    unauthenticated so that a fresh installer can discover the AIMS
    endpoints before the user logs in. The Alfresco Python client
    still requires *some* ``auth`` object though — this is the
    zero-credential shim we hand it.
    """

    def __call__(
        self, r: "requests.PreparedRequest", /
    ) -> "requests.PreparedRequest":  # pragma: no cover - trivial
        return r


def discover_aims_config(server_url: str, /, *, verify: bool = True) -> Dict[str, Any]:
    """Discover AIMS/Keycloak configuration from an Alfresco server.

    Tries the following in order and returns the first that yields a
    usable OpenID configuration URL:

    0. ``/alfresco/service/devicesync/config`` — Alfresco Device Sync
       ``IdentityServiceConfig`` (available since ACS with the Device
       Sync webscript; unauthenticated). This is the preferred source
       because it also carries the ``audience`` / ``publicClient`` /
       ``enablePkce`` / ``enableBasicAuth`` capability flags that
       Alfresco Drive 1.0 relies on.
    1. ``syncServiceConfiguration`` — standard Alfresco Sync Service
       ``identityServiceConfig`` block (returns ``authServerUrl`` /
       ``realm`` / ``resource``).
    2. ``/app.config.json`` and ``/assets/app.config.json`` — Alfresco
       Digital Workspace config (``oauth2.host`` / ``oauth2.clientId``).
    3. Well-known Keycloak heuristic — ``<server>/auth/realms/alfresco``.

    Returns a dict with keys ``openid_configuration_url``, ``client_id``,
    and — when the source knows them — ``client_secret``, ``audience``,
    ``public_client`` (bool), ``enable_pkce`` (bool) and
    ``enable_basic_auth`` (bool).  Returns an empty dict on failure.
    """
    from urllib.parse import urlparse as _urlparse

    base = server_url.rstrip("/")
    parsed = _urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    # 0) Device Sync /config (v0.0.3+ Alfresco Python client)
    try:
        from alfresco import Alfresco

        client = Alfresco(url=base, auth=_NoAuth())
        try:
            if not verify:
                try:
                    client.session.verify = False
                except Exception:  # pragma: no cover - defensive
                    log.debug("Could not disable TLS verification on probe client")
            isc = client.device_sync.get_identity_service_config()
        finally:
            try:
                client.close()
            except Exception:  # pragma: no cover - defensive
                pass
        openid_url = isc.openid_configuration_url()
        if openid_url:
            client_id = isc.client_id or _DEFAULT_CLIENT_ID
            # Extract all values from the ISC object before logging
            # to avoid CodeQL taint propagation from client_secret.
            safe_openid_url = str(openid_url)
            safe_client_id = str(client_id)
            audience = isc.audience or ""
            public_client = bool(isc.public_client)
            enable_pkce = bool(isc.enable_pkce)
            enable_basic_auth = bool(isc.enable_basic_auth)
            has_secret = bool(isc.client_secret)
            # Do not log values returned by discovery endpoints: those
            # payloads may contain credentials and are treated as sensitive
            # by CodeQL's clear-text logging analysis.
            log.info(
                "Discovered AIMS OpenID config via "
                "/alfresco/service/devicesync/config"
            )
            result: Dict[str, Any] = {
                "openid_configuration_url": safe_openid_url,
                "client_id": safe_client_id,
                "audience": audience,
                "public_client": public_client,
                "enable_pkce": enable_pkce,
                "enable_basic_auth": enable_basic_auth,
            }
            if has_secret:
                result["client_secret"] = isc.client_secret
            return result
    except Exception:
        log.warning(
            "Device Sync /config bootstrap failed, falling back to legacy discovery",
            exc_info=True,
        )

    # 1) syncServiceConfiguration
    # ACS mounts its REST API under ``/alfresco/api/…``. The user-supplied
    # URL is the site root, so the ``/alfresco`` context prefix must be
    # added explicitly. If the user already supplied a URL ending in
    # ``/alfresco``, avoid doubling it.
    sync_base = base if base.endswith("/alfresco") else base + "/alfresco"
    sync_url = (
        sync_base
        + "/api/-default-/private/alfresco/versions/1/config/syncServiceConfiguration"
    )
    try:
        resp = requests.get(sync_url, timeout=10, verify=verify)
        if resp.ok:
            data = resp.json()
            isc = data.get("identityServiceConfig") or data.get("entry", {}).get(
                "identityServiceConfig", {}
            )
            auth_server = (isc.get("authServerUrl") or "").rstrip("/")
            if auth_server:
                realm = str(isc.get("realm", "alfresco"))
                client_id = str(isc.get("resource", _DEFAULT_CLIENT_ID))
                openid_url = (
                    f"{auth_server}/realms/{realm}/.well-known/openid-configuration"
                )
                log.info("Discovered AIMS OpenID config via syncServiceConfiguration")
                legacy_result: Dict[str, Any] = {
                    "openid_configuration_url": openid_url,
                    "client_id": client_id,
                    # Legacy sources don't expose these; assume permissive
                    # defaults matching pre-1.0 Alfresco Drive behaviour.
                    "audience": "",
                    "public_client": True,
                    "enable_pkce": True,
                    "enable_basic_auth": True,
                }
                secret = isc.get("credentialsSecret")
                if secret:
                    legacy_result["client_secret"] = secret
                return legacy_result
    except Exception:
        log.debug(
            f"Could not fetch syncServiceConfiguration from {sync_url}",
            exc_info=True,
        )

    # 2) app.config.json (ADW / Digital Workspace)
    for config_path in ("/app.config.json", "/assets/app.config.json"):
        try:
            resp = requests.get(origin + config_path, timeout=10, verify=verify)
            if not resp.ok:
                continue
            data = resp.json()
            oauth2 = data.get("oauth2") or {}
            host = (oauth2.get("host") or "").rstrip("/")
            if not host:
                continue
            client_id = oauth2.get("clientId", _DEFAULT_CLIENT_ID)
            openid_url = host + "/.well-known/openid-configuration"
            # Extract values as plain ``str`` before logging to prevent CodeQL
            # taint propagation from any sensitive fields the JSON payload
            # might also contain (e.g. ``oauth2.secret``, ``password``).
            safe_openid_url = str(openid_url)
            safe_client_id = str(client_id)
            log.info("Discovered AIMS OpenID config via app.config.json")
            return {
                "openid_configuration_url": safe_openid_url,
                "client_id": safe_client_id,
                "audience": "",
                "public_client": True,
                "enable_pkce": True,
                "enable_basic_auth": True,
            }
        except Exception:
            log.debug(f"Failed to discover from {config_path}", exc_info=True)

    # 3) Well-known Keycloak heuristic
    heuristic_url = origin + "/auth/realms/alfresco/.well-known/openid-configuration"
    try:
        resp = requests.get(heuristic_url, timeout=10, verify=verify)
        if resp.ok and resp.json().get("authorization_endpoint"):
            safe_heuristic_url = str(heuristic_url)
            safe_default_client_id = str(_DEFAULT_CLIENT_ID)
            log.info("Discovered AIMS OpenID config via well-known heuristic")
            return {
                "openid_configuration_url": safe_heuristic_url,
                "client_id": safe_default_client_id,
                "audience": "",
                "public_client": True,
                "enable_pkce": True,
                "enable_basic_auth": True,
            }
    except Exception:
        log.debug(f"Well-known heuristic failed for {heuristic_url}", exc_info=True)

    log.warning(
        "Could not discover AIMS/Keycloak configuration. Tried Device Sync "
        "/config, syncServiceConfiguration, app.config.json and the well-known "
        "Keycloak path. Configure oauth2_openid_configuration_url manually or "
        "ensure the server exposes one of these endpoints."
    )
    return {}


def probe_capabilities(server_url: str, /, *, verify: bool = True) -> Dict[str, Any]:
    """Return the Alfresco Drive auth capabilities advertised by ``server_url``.

    Thin wrapper around :func:`discover_aims_config` that keeps only
    the auth-capability keys the UI cares about. When discovery fails
    entirely, falls back to permissive defaults (basic auth allowed,
    PKCE allowed) so the existing legacy popup stays functional.
    """
    aims = discover_aims_config(server_url, verify=verify)
    return {
        "discovered": bool(aims),
        "enable_basic_auth": bool(aims.get("enable_basic_auth", True)),
        "enable_pkce": bool(aims.get("enable_pkce", True)),
        "public_client": bool(aims.get("public_client", True)),
        "audience": aims.get("audience", ""),
        "client_id": aims.get("client_id", _DEFAULT_CLIENT_ID),
        "openid_configuration_url": aims.get("openid_configuration_url", ""),
    }


def _release_loopback_state(api: Any) -> None:
    """Shut down and forget the loopback state pinned to ``api``.

    ``api._alfresco_loopback_state`` is a ``(bridge, server)`` tuple set
    by :meth:`AlfrescoOAuthentication._start_loopback_flow`. Called when
    a new auth attempt starts or when the current one completes.
    Safe to call when nothing is pinned.
    """
    state = getattr(api, "_alfresco_loopback_state", None)
    if state is None:
        return
    _bridge, server = state
    try:
        server.shutdown()
    except Exception:
        log.exception("Loopback: shutdown failed")
    try:
        api._alfresco_loopback_state = None
    except Exception:
        log.exception("Loopback: clearing api state failed")


class AlfrescoOAuthentication(OAuthenticationBase):
    """OAuth2 / AIMS authentication for Alfresco servers.

    Uses ``alfresco.OAuth2`` (PKCE) for the browser flow and fetches
    the current user's identity via
    ``/alfresco/api/-default-/public/alfresco/versions/1/people/-me-``.
    """

    def __init__(self, *args: Any, dao: "BaseDAO" = None, **kwargs: Any) -> None:
        super().__init__(*args, dao=dao, **kwargs)

        # AIMS capability flags surfaced by Device Sync /config. Legacy
        # (pre-1.0) Alfresco servers don't expose these, so default to
        # the historic permissive values.
        self._oauth2_audience: str = ""
        self._oauth2_public_client: bool = True
        self._oauth2_enable_pkce: bool = True
        self._oauth2_enable_basic_auth: bool = True

        # Auto-discover AIMS/Keycloak endpoints from the Alfresco server
        # if no explicit OpenID configuration URL has been provided.
        if not self._oauth2_openid_configuration_url:
            aims = discover_aims_config(self.url, verify=self.verification_needed)
            if aims:
                self._apply_aims_discovery(aims)

        self._build_oauth2()

    def _apply_aims_discovery(self, aims: Dict[str, Any], /) -> None:
        """Copy fields from a :func:`discover_aims_config` result onto self."""
        self._oauth2_openid_configuration_url = aims["openid_configuration_url"]
        self._oauth2_client_id = aims.get("client_id", _DEFAULT_CLIENT_ID)
        self._oauth2_client_secret = (
            aims.get("client_secret") or self._oauth2_client_secret
        )
        self._oauth2_audience = aims.get("audience", "") or ""
        self._oauth2_public_client = bool(aims.get("public_client", True))
        self._oauth2_enable_pkce = bool(aims.get("enable_pkce", True))
        self._oauth2_enable_basic_auth = bool(aims.get("enable_basic_auth", True))

    def _build_oauth2(self, *, redirect_uri_override: Optional[str] = None) -> None:
        """Construct the ``alfresco.OAuth2`` auth object for Alfresco.

        When called a second time (e.g. to swap in a loopback
        ``redirect_uri``), the previously-discovered authorization and
        token endpoints are reused so we don't re-hit the OpenID
        ``.well-known`` document.
        """
        from alfresco import OAuth2

        from nxdrive.drive.options import Options

        existing = getattr(self, "auth", None)
        authz_ep = (
            getattr(existing, "authorization_endpoint", None)
            or Options.oauth2_authorization_endpoint
        )
        token_ep = (
            getattr(existing, "token_endpoint", None) or Options.oauth2_token_endpoint
        )
        # Skip re-discovery if we already have both endpoints.
        openid_url = (
            None if (authz_ep and token_ep) else self._oauth2_openid_configuration_url
        )
        effective_redirect = redirect_uri_override or Options.oauth2_redirect_uri

        self.auth = OAuth2(
            self.url,
            client_id=self._oauth2_client_id,
            client_secret=self._oauth2_client_secret,
            authorization_endpoint=authz_ep,
            openid_configuration_url=openid_url,
            redirect_uri=effective_redirect,
            token_endpoint=token_ep,
            token=self.token,
            subclient_kwargs=self._subclient_kwargs,
        )

    def connect_url(self) -> str:
        """Build the IdP authorization URL for the PKCE browser flow.

        Starts a short-lived loopback HTTP server on ``127.0.0.1`` to
        catch the IdP redirect (Keycloak / AIMS does not accept the
        ``nxdrive://`` custom scheme), rebuilds :attr:`auth` so both the
        authorize hop and the token exchange use the loopback URL, then
        generates a fresh ``state`` and ``code_verifier`` via
        ``alfresco.OAuth2.create_authorization_url()``. The verifier
        and state are persisted in the DAO so that
        ``QMLDriveApi.continue_oauth2_flow()`` can validate the
        callback and swap the code for a token.
        """
        from nxdrive.drive.options import Options

        # If discovery failed at __init__ time (server unreachable at that
        # point, network flap, etc.) retry now so the user gets a fresh
        # attempt instead of a stale None.
        if not self.auth.authorization_endpoint:
            aims = discover_aims_config(self.url, verify=self.verification_needed)
            if aims:
                self._apply_aims_discovery(aims)
                self._build_oauth2()
            if not self.auth.authorization_endpoint:
                raise OAuth2Error(
                    "Could not discover the Alfresco AIMS/Keycloak configuration "
                    f"for {self.url!r}. Verify the server URL is correct and that "
                    "AIMS is enabled, or set 'oauth2_openid_configuration_url' "
                    "manually."
                )

        # Bring up the loopback listener + Qt bridge, then rebuild self.auth
        # so both the authorize URL and the subsequent token exchange use
        # the same loopback redirect_uri (Keycloak requires exact match).
        loopback_uri = self._start_loopback_flow()
        self._build_oauth2(redirect_uri_override=loopback_uri)

        scope = Options.oauth2_scope or "openid"
        # AIMS/Keycloak requires the ``audience`` request parameter when
        # the client is configured with an explicit audience mapper.
        extra: Dict[str, Any] = {}
        if self._oauth2_audience:
            extra["audience"] = self._oauth2_audience
        uri, state, code_verifier = self.auth.create_authorization_url(
            scope=scope, **extra
        )

        if self._dao:
            self._dao.update_config("tmp_oauth2_url", self.url)
            self._dao.update_config("tmp_oauth2_code_verifier", code_verifier)
            self._dao.update_config("tmp_oauth2_state", state)
            # Persist the loopback redirect_uri: the token exchange in
            # ``get_token()`` must use the exact same value (Keycloak
            # enforces RFC 6749 §4.1.3 redirect_uri match).
            self._dao.update_config("tmp_oauth2_redirect_uri", loopback_uri)

        return uri

    # ------------------------------------------------------------------
    # Loopback callback plumbing
    # ------------------------------------------------------------------

    def _start_loopback_flow(self) -> str:
        """Boot the loopback HTTP server and wire it to Qt.

        Creates a lightweight :class:`QObject` bridge on the Qt main
        thread and connects its ``Signal(dict)`` to
        ``QMLDriveApi.continue_oauth2_flow``. The signal is emitted
        from the loopback server's worker thread — Qt's automatic
        connection upgrades this to a queued call so the OAuth2 flow
        finalises on the GUI thread.

        The bridge and server are pinned to the ``QMLDriveApi``
        instance (a long-lived ``QObject``) so they survive after
        ``connect_url()`` returns and this ``AlfrescoOAuthentication``
        instance is garbage-collected — otherwise the loopback thread
        would later emit on a freed ``QObject`` and crash the process.

        Returns the ``http://127.0.0.1:<port>/callback`` URL to hand
        to the IdP as ``redirect_uri``.
        """
        from PySide6.QtCore import QObject, Signal

        from nxdrive.alfresco.auth.loopback import LoopbackAuthServer
        from nxdrive.drive.qt.imports import QApplication

        app = QApplication.instance()
        api = getattr(app, "api", None) if app is not None else None
        if api is None:
            raise OAuth2Error(
                "Qt application is not initialised; cannot start the loopback "
                "OAuth2 callback server."
            )

        # Tear down any previous attempt (user cancelled + retried).
        _release_loopback_state(api)

        class _CallbackBridge(QObject):
            callback_received = Signal(dict)

        bridge = _CallbackBridge()
        # AutoConnection → QueuedConnection at emit time because the
        # signal will be emitted from the HTTP server's worker thread
        # while the receiver (api) lives on the Qt main thread.
        bridge.callback_received.connect(api.continue_oauth2_flow)

        def _emit_from_thread(query: Dict[str, str]) -> None:
            try:
                bridge.callback_received.emit(query)
            except Exception:
                raise

        server = LoopbackAuthServer()
        try:
            redirect_uri = server.start(on_callback=_emit_from_thread)
        except RuntimeError as exc:
            raise OAuth2Error(str(exc)) from exc

        # Pin to the API instance so both objects outlive `self`.
        api._alfresco_loopback_state = (bridge, server)
        return redirect_uri

    def get_token(self, **kwargs: Any) -> "Token":
        # The token exchange must use the exact ``redirect_uri`` that
        # was sent on the authorize hop (Keycloak enforces RFC 6749
        # §4.1.3). ``connect_url()`` stashed it in the DAO; rebuild
        # ``self.auth`` with it before delegating to the base class.
        stored_uri = (
            self._dao.get_config("tmp_oauth2_redirect_uri") if self._dao else None
        )
        if stored_uri:
            self._build_oauth2(redirect_uri_override=stored_uri)
        # Some AIMS/Keycloak deployments enforce that the ``audience``
        # request parameter sent on the authorize hop is echoed back on
        # the token exchange (RFC 8707-style resource-audience binding).
        if self._oauth2_audience and "audience" not in kwargs:
            kwargs["audience"] = self._oauth2_audience
        try:
            result = super().get_token(**kwargs)
            # Enrich the token dict with the metadata ``AlfrescoRemote`` needs
            # to rebuild an ``OAuth2Auth`` capable of proactive/reactive
            # refresh. ``super().get_token()`` only returns the raw fields
            # from the token endpoint (``access_token``, ``refresh_token``,
            # ``expires_at``, ...) — the caller (``continue_oauth2_flow``)
            # persists this exact dict, so we must attach ``token_url`` and
            # ``client_id`` here or refresh will fail later with
            # "token_url not configured".
            if isinstance(result, dict):
                token_endpoint = getattr(self.auth, "token_endpoint", None)
                if token_endpoint and "token_url" not in result:
                    result["token_url"] = str(token_endpoint)
                client_id = getattr(self.auth, "client_id", None)
                if client_id and "client_id" not in result:
                    result["client_id"] = client_id
                # Persist ``client_secret`` when the AIMS client is
                # configured as *confidential*. Keycloak rejects the
                # refresh POST with ``invalid_client`` if the secret is
                # missing, so we must round-trip it through the DAO.
                # For public / PKCE clients this attribute is ``None``
                # and we intentionally leave the key absent.
                client_secret = getattr(self.auth, "client_secret", None)
                if client_secret and "client_secret" not in result:
                    result["client_secret"] = client_secret
            return result
        except OAuth2Error as exc:
            raise RemoteOAuth2Error(message=getattr(exc, "message", str(exc))) from exc
        except Exception:
            raise
        finally:
            # Release the pinned loopback state and the extra DAO key.
            # Nothing else needs the server once the code has been
            # exchanged (or the exchange has failed).
            try:
                from nxdrive.drive.qt.imports import QApplication

                app = QApplication.instance()
                api = getattr(app, "api", None) if app is not None else None
                if api is not None:
                    _release_loopback_state(api)
            except Exception:
                log.exception("Loopback: release failed")
            if self._dao:
                self._dao.delete_config("tmp_oauth2_redirect_uri")

    def get_username(self) -> str:
        """Resolve the authenticated user's ID via the Alfresco People API."""
        token = self.auth.token
        if not token:
            return ""

        access_token = (
            token.get("access_token", "") if isinstance(token, dict) else token
        )
        # ACS mounts its REST API under ``/alfresco/api/…``. The user-supplied
        # URL is the site root (e.g. ``https://host/``), so the ``/alfresco``
        # context prefix must be added explicitly. If the user already
        # supplied a URL ending in ``/alfresco``, avoid doubling it.
        base = self.url.rstrip("/")
        if not base.endswith("/alfresco"):
            base += "/alfresco"
        url = base + "/api/-default-/public/alfresco/versions/1/people/-me-"
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            verify=self.verification_needed,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        username: str = data.get("entry", {}).get("id", "")
        return username

    def get_token_dict(self) -> Optional[Dict[str, Any]]:
        """Return the full token dict for storage.

        Includes ``access_token``, ``refresh_token``, ``expires_at``,
        ``token_url``, ``client_id``, and (when configured)
        ``client_secret`` so that ``AlfrescoRemote`` can recreate an
        ``OAuth2Auth`` with proactive-refresh capability. ``expires_at``
        is a POSIX timestamp (float, seconds since epoch), matching
        authlib's convention.
        """
        token = self.auth.token
        if not token or not isinstance(token, dict):
            return None
        result: Dict[str, Any] = {
            "access_token": token.get("access_token", ""),
            "refresh_token": token.get("refresh_token"),
            "expires_at": token.get("expires_at"),
            "token_url": str(self.auth.token_endpoint),
            "client_id": self.auth.client_id,
        }
        # Confidential clients only; ``None`` for public / PKCE clients.
        client_secret = getattr(self.auth, "client_secret", None)
        if client_secret:
            result["client_secret"] = client_secret
        return result
