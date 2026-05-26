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

from ..options import Options
from ..utils import get_verify
from .base import Authentication

if TYPE_CHECKING:
    from ..dao.base import BaseDAO
    from . import Token

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

    def connect_url(self) -> str:
        """Generate an OAuth2 authorization URL with PKCE."""
        kw: Dict[str, str] = {}
        if Options.oauth2_scope:
            kw["scope"] = Options.oauth2_scope
        auth_details: Tuple[str, str, str] = self.auth.create_authorization_url(**kw)
        uri, state, code_verifier = auth_details

        if self._dao:
            self._dao.update_config("tmp_oauth2_url", self.url)
            self._dao.update_config("tmp_oauth2_code_verifier", code_verifier)
            self._dao.update_config("tmp_oauth2_state", state)

        return uri

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
