"""Nuxeo token authentication — concrete implementation."""

from typing import TYPE_CHECKING, Any

from nuxeo.auth import TokenAuth
from nuxeo.client import NuxeoClient

from nxdrive.drive.auth.token import TokenAuthentication as _TokenAuthenticationBase
from nxdrive.drive.constants import APP_NAME, TOKEN_PERMISSION
from nxdrive.drive.metrics.utils import current_os

if TYPE_CHECKING:
    from nxdrive.drive.auth import Token


class TokenAuthentication(_TokenAuthenticationBase):
    """Nuxeo token-based authentication."""

    def _create_auth_handler(self, token: "Token") -> TokenAuth:
        return TokenAuth(token)

    def get_token(self, **kwargs: Any) -> "Token":
        client: NuxeoClient = kwargs["client"]
        token: str = self.auth.request_token(
            client,
            client.headers["X-Device-Id"],
            TOKEN_PERMISSION,
            app_name=APP_NAME,
            device=current_os(full=True),
            revoke=kwargs.get("revoke", False),
        )
        token = "" if "\n" in token else token
        self.token = self.auth.token = token
        return token
