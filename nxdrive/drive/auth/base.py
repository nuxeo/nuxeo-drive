from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from . import Token


@runtime_checkable
class AuthHandler(Protocol):
    """Protocol for objects that sign HTTP requests and manage tokens."""

    def __call__(self, r: Any) -> Any:
        ...

    def set_token(self, token: Any) -> None:
        ...


class Authentication:
    def __init__(self, url: str, /, *, token: "Token" = None, **kwargs: Any) -> None:
        self.auth: Any = None
        self.token = token
        self.url = url

    def connect_url(self) -> str:  # type: ignore[empty-body]
        """Get the URL to use to open the browser to and let the user continue the authentication."""

    def get_token(self, **kwargs: Any) -> "Token":  # type: ignore[empty-body]
        """Request a token."""

    def revoke_token(self, **kwargs: Any) -> None:
        """Revoke a token."""

    def set_token(self, token: "Token") -> None:
        """Update the current token."""
        self.token = token
        self.auth.set_token(token)
