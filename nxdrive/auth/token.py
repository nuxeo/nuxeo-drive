from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from nuxeo.auth import TokenAuth
from nuxeo.client import NuxeoClient

from ..constants import APP_NAME, TOKEN_PERMISSION
from ..metrics.utils import current_os
from ..options import Options
from .base import Authentication

if TYPE_CHECKING:
    from . import Token


class TokenAuthentication(Authentication):
    """Use the Nuxeo token."""

    def __init__(self, *args: Any, device_id: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.auth = TokenAuth(self.token)
        self._device_id = device_id

    def connect_url(self) -> str:
        params = urlencode(
            {
                "deviceId": self._device_id,
                "applicationName": APP_NAME,
                "permission": TOKEN_PERMISSION,
                "deviceDescription": current_os(full=True),
                "forceAnonymousLogin": "true",
                "useProtocol": "true",
            }
        )

        # Handle URL parameters
        parts = urlsplit(self.url)
        path = f"{parts.path}/{Options.browser_startup_page}".replace("//", "/")

        params = f"{parts.query}&{params}" if parts.query else params
        return urlunsplit((parts.scheme, parts.netloc, path, params, parts.fragment))

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

    def revoke_token(self, **kwargs: Any) -> None:
        self.get_token(client=kwargs["client"], revoke=True)
