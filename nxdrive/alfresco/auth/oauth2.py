"""
OAuth2 / AIMS authentication for Alfresco Content Services.

Re-uses the ``nuxeo.auth.OAuth2`` class (which is an OpenID Connect /
authlib wrapper that supports PKCE) but resolves the authenticated
username via the Alfresco People API instead of the Nuxeo Users API.

The AIMS/Keycloak endpoints are auto-discovered from the Alfresco
server via the ``syncServiceConfiguration`` API so the user only
needs to enter the server URL.
"""

from logging import getLogger
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

import requests
from nuxeo.auth import OAuth2

from nxdrive.drive.auth.base import Authentication
from nxdrive.drive.options import Options
from nxdrive.drive.utils import get_verify

if TYPE_CHECKING:
    from nxdrive.drive.auth import Token
    from nxdrive.drive.dao.base import BaseDAO

__all__ = ("AlfrescoOAuthentication",)

log = getLogger(__name__)

# Default AIMS / Keycloak client identifier used by Alfresco deployments.
_DEFAULT_CLIENT_ID = "alfresco"


def discover_aims_config(server_url: str, /, *, verify: bool = True) -> Dict[str, str]:
    """Discover AIMS/Keycloak configuration from an Alfresco server.

    Calls the ``syncServiceConfiguration`` endpoint which returns the
    ``identityServiceConfig`` block containing the Keycloak auth server
    URL, realm name, client id, and optionally client secret.

    Returns a dict with keys ``openid_configuration_url``, ``client_id``,
    and optionally ``client_secret``.  Returns an empty dict on failure.
    """
    url = (
        server_url.rstrip("/")
        + "/api/-default-/private/alfresco/versions/1/config/syncServiceConfiguration"
    )
    try:
        resp = requests.get(url, timeout=10, verify=verify)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        log.debug(f"Could not fetch syncServiceConfiguration from {url}", exc_info=True)
        return {}

    isc = data.get("identityServiceConfig") or data.get("entry", {}).get(
        "identityServiceConfig", {}
    )
    if not isc:
        log.debug("No identityServiceConfig found in syncServiceConfiguration response")
        return {}

    auth_server = isc.get("authServerUrl", "").rstrip("/")
    realm = isc.get("realm", "alfresco")
    client_id = isc.get("resource", _DEFAULT_CLIENT_ID)
    client_secret = isc.get("credentialsSecret")

    if not auth_server:
        log.warning("identityServiceConfig has no authServerUrl")
        return {}

    openid_url = f"{auth_server}/realms/{realm}/.well-known/openid-configuration"
    log.info(f"Discovered AIMS OpenID config: {openid_url} (client_id={client_id})")

    result: Dict[str, str] = {
        "openid_configuration_url": openid_url,
        "client_id": client_id,
    }
    if client_secret:
        result["client_secret"] = client_secret
    return result


def _discover_token_endpoint(
    server_url: str, /, *, verify: bool = True
) -> Tuple[str, str]:
    """Discover the Keycloak token endpoint URL and client ID.

    Tries, in order:
    1. ``syncServiceConfiguration`` (standard Alfresco Sync Service).
    2. ``/app.config.json`` (Alfresco Digital Workspace config).
    3. Well-known Keycloak path heuristic.

    Returns ``(token_url, client_id)`` or ``("", "")`` on failure.
    """
    # 1) Try syncServiceConfiguration
    aims = discover_aims_config(server_url, verify=verify)
    if aims:
        openid_url = aims["openid_configuration_url"]
        client_id = aims.get("client_id", _DEFAULT_CLIENT_ID)
        try:
            resp = requests.get(openid_url, timeout=10, verify=verify)
            resp.raise_for_status()
            token_url = resp.json().get("token_endpoint", "")
            if token_url:
                return token_url, client_id
        except Exception:
            log.debug(
                "Failed to fetch OIDC config from syncServiceConfiguration",
                exc_info=True,
            )

    # 2) Try app.config.json (ADW config)
    from urllib.parse import urlparse as _urlparse

    parsed = _urlparse(server_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    for config_path in ("/app.config.json", "/assets/app.config.json"):
        try:
            resp = requests.get(base + config_path, timeout=10, verify=verify)
            if not resp.ok:
                continue
            data = resp.json()
            oauth2 = data.get("oauth2", {})
            host = oauth2.get("host", "").rstrip("/")
            client_id = oauth2.get("clientId", _DEFAULT_CLIENT_ID)
            if host:
                # Derive token endpoint from the OIDC well-known
                oidc_url = host + "/.well-known/openid-configuration"
                oidc_resp = requests.get(oidc_url, timeout=10, verify=verify)
                oidc_resp.raise_for_status()
                token_url = oidc_resp.json().get("token_endpoint", "")
                if token_url:
                    log.info(
                        f"Discovered token endpoint from {config_path}: {token_url}"
                    )
                    return token_url, client_id
        except Exception:
            log.debug(f"Failed to discover from {config_path}", exc_info=True)

    log.warning(f"Could not discover OAuth2 token endpoint for {server_url}")
    return "", ""


class AlfrescoOAuthentication(Authentication):
    """OAuth2 / AIMS authentication for Alfresco servers.

    Uses the same ``nuxeo.auth.OAuth2`` PKCE flow as the Nuxeo
    ``OAuthentication`` but fetches the current user's identity via
    ``/alfresco/api/-default-/public/alfresco/versions/1/people/-me-``
    instead of the Nuxeo Users API.
    """

    def __init__(self, *args: Any, dao: "BaseDAO" = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.verification_needed = get_verify()
        self._dao = dao
        subclient_kwargs = kwargs.get("subclient_kwargs", {})
        subclient_kwargs["verify"] = self.verification_needed

        # Auto-discover AIMS/Keycloak endpoints from the Alfresco server
        # if no explicit OpenID configuration URL has been provided.
        openid_url = Options.oauth2_openid_configuration_url
        client_id = Options.oauth2_client_id
        client_secret = Options.oauth2_client_secret

        if not openid_url:
            aims = discover_aims_config(self.url, verify=self.verification_needed)
            if aims:
                openid_url = aims["openid_configuration_url"]
                client_id = aims.get("client_id", _DEFAULT_CLIENT_ID)
                client_secret = aims.get("client_secret") or client_secret

        self.auth = OAuth2(
            self.url,
            client_id=client_id,
            client_secret=client_secret,
            authorization_endpoint=Options.oauth2_authorization_endpoint,
            openid_configuration_url=openid_url,
            redirect_uri=Options.oauth2_redirect_uri,
            token_endpoint=Options.oauth2_token_endpoint,
            token=self.token,
            subclient_kwargs=subclient_kwargs,
        )

    def get_token(self, **kwargs: Any) -> "Token":
        """Exchange authorization code + code_verifier for an access token."""
        token: str = self.auth.request_token(
            code_verifier=kwargs["code_verifier"],
            code=kwargs["code"],
            state=kwargs["state"],
        )
        self.token = token
        return token

    def get_username(self) -> str:
        """Resolve the authenticated user's ID via the Alfresco People API."""
        token = self.auth.token
        if not token:
            return ""

        access_token = (
            token.get("access_token", "") if isinstance(token, dict) else token
        )
        url = (
            self.url.rstrip("/")
            + "/api/-default-/public/alfresco/versions/1/people/-me-"
        )
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

        Includes ``access_token``, ``refresh_token``, ``token_url``,
        and ``client_id`` so that ``AlfrescoRemote`` can recreate an
        ``OAuth2Auth`` with refresh capability.
        """
        token = self.auth.token
        if not token or not isinstance(token, dict):
            return None
        return {
            "access_token": token.get("access_token", ""),
            "refresh_token": token.get("refresh_token"),
            "token_url": str(self.auth._token_endpoint),
            "client_id": self.auth._client_id,
        }

    @staticmethod
    def password_grant(
        server_url: str,
        username: str,
        password: str,
        /,
        *,
        verify: bool = True,
    ) -> Dict[str, Any]:
        """Perform an OAuth2 Resource Owner Password Grant against Keycloak.

        Discovers the token endpoint from the server's ``app.config.json``
        or ``syncServiceConfiguration``, then exchanges *username* +
        *password* for an access token via the alfresco-python-client
        ``OAuth2Auth``.

        Returns a dict with ``access_token``, ``refresh_token``,
        ``token_url``, ``client_id``, and ``username`` (resolved via
        the People API).
        """
        from alfresco.auth import OAuth2Auth as AlfrescoOAuth2Auth

        # 1) Discover token endpoint
        token_url, client_id = _discover_token_endpoint(server_url, verify=verify)
        if not token_url:
            raise RuntimeError(
                f"Cannot discover OAuth2 token endpoint for {server_url}. "
                "Ensure the server has AIMS/Keycloak configured."
            )

        # 2) Password grant via alfresco-python-client
        oauth = AlfrescoOAuth2Auth(
            token_url=token_url,
            client_id=client_id,
            username=username,
            password=password,
            scope="openid",
            verify=verify,
        )
        access_token = oauth.fetch_token()
        if not access_token:
            raise RuntimeError("Password grant returned no access token")

        # 3) Resolve username via People API
        # The People API lives under /alfresco/api/... — ensure the prefix
        # is present regardless of whether server_url includes /alfresco.
        base = server_url.rstrip("/")
        if not base.endswith("/alfresco"):
            base += "/alfresco"
        people_url = base + "/api/-default-/public/alfresco/versions/1/people/-me-"
        resp = requests.get(
            people_url,
            headers={"Authorization": f"Bearer {access_token}"},
            verify=verify,
            timeout=30,
        )
        resp.raise_for_status()
        resolved_username: str = resp.json().get("entry", {}).get("id", username)

        # 4) Build the token dict that AlfrescoRemote expects
        return {
            "access_token": access_token,
            "refresh_token": oauth.refresh_token,
            "token_url": token_url,
            "client_id": client_id,
            "username": resolved_username,
        }
