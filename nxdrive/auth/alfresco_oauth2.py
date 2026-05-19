"""
OAuth2 / AIMS authentication for Alfresco Content Services.

Re-uses the ``nuxeo.auth.OAuth2`` class (which is an OpenID Connect /
authlib wrapper that supports PKCE) but resolves the authenticated
username via the Alfresco People API instead of the Nuxeo Users API.
"""

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

        # Use the same Options as the Nuxeo OAuth2 flow.
        # For Alfresco AIMS (Keycloak), the admin should configure:
        #   oauth2_openid_configuration_url →
        #     https://<aims>/auth/realms/alfresco/.well-known/openid-configuration
        #   oauth2_client_id → "alfresco" (default Keycloak client)
        self.auth = OAuth2(
            self.url,
            client_id=Options.oauth2_client_id,
            client_secret=Options.oauth2_client_secret,
            authorization_endpoint=Options.oauth2_authorization_endpoint,
            openid_configuration_url=Options.oauth2_openid_configuration_url,
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
            "client_id": Options.oauth2_client_id,
        }
