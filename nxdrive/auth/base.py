from typing import TYPE_CHECKING, Any

from nuxeo.auth.base import AuthBase

if TYPE_CHECKING:
    from . import Token


class Authentication:
    def __init__(self, url: str, /, *, token: "Token" = None, **kwargs: Any) -> None:
        self.auth: AuthBase = None
        self.token = token
        self.url = url

    def connect_url(self) -> str:
        """Get the URL to use to open the browser to and let the user continue the authentication."""

    def get_token(self, **kwargs: Any) -> "Token":
        """Request a token."""

    def revoke_token(self, **kwargs: Any) -> None:
        """Revoke a token."""

    def set_token(self, token: "Token") -> None:
        """Update the current token."""
        self.token = token
        self.auth.set_token(token)
