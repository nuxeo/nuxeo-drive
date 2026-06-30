from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from nxdrive.drive.auth.base import Authentication
from nxdrive.drive.constants import APP_NAME, TOKEN_PERMISSION
from nxdrive.drive.metrics.utils import current_os
from nxdrive.drive.options import Options

if TYPE_CHECKING:
    from nxdrive.drive.auth import Token


class TokenAuthentication(Authentication):
    """Token-based authentication.

    Subclasses must implement ``_create_auth_handler()`` and
    ``_request_token()`` to provide server-type-specific behaviour.
    """

    def __init__(self, *args: Any, device_id: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.auth = self._create_auth_handler(self.token)
        self._device_id = device_id

    def _create_auth_handler(self, token: "Token") -> Any:
        """Create the underlying auth handler object.  Must be overridden."""
        raise NotImplementedError

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

        from nxdrive.drive import server_type as st

        config = st.detect_by_url(self.url)
        browser_startup_page = config.browser_startup_page or Options.browser_startup_page

        # Handle URL parameters
        parts = urlsplit(self.url)
        path = f"{parts.path}/{browser_startup_page}".replace("//", "/")

        params = f"{parts.query}&{params}" if parts.query else params
        return urlunsplit((parts.scheme, parts.netloc, path, params, parts.fragment))

    def get_token(self, **kwargs: Any) -> "Token":  # type: ignore[empty-body]
        """Request a token.  Must be overridden by server-type subclasses."""
        raise NotImplementedError

    def revoke_token(self, **kwargs: Any) -> None:
        self.get_token(client=kwargs["client"], revoke=True)
