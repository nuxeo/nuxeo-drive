from typing import Any, Dict, Union

from .base import Authentication  # noqa: F401
from .oauth2 import OAuthenticationBase

# Authentication token
#   - dict for OAuth2
#   - str for Nuxeo token
Token = Union[Dict[str, Any], str]


def get_auth(host: str, token: Token, **kwargs: Any) -> Any:
    """Proxy to instantiate the appropriate authentication class based on
    the given *token* and *server_type*.

    The actual authentication class is resolved via the server-type registry
    so that this module has no hard-coded knowledge of any server type.
    """
    from nxdrive.drive import server_type as _st

    server_type_key = kwargs.pop("server_type", None) or _st.get_default_key()
    config = _st.get(server_type_key)

    if config.auth_factory:
        return config.auth_factory(host, token, **kwargs)

    # Fallback for server types without a registered auth factory
    from nxdrive.drive.auth.token import TokenAuthentication

    return TokenAuthentication(host, token=token, **kwargs)


__all__ = (
    "Authentication",
    "OAuthentication",
    "Token",
    "get_auth",
)


def __getattr__(name: str) -> Any:
    """Lazy compatibility exports for legacy imports.

    Keep drive-level imports server-agnostic by resolving classes through
    the server-type registry at runtime.
    """
    if name != "OAuthentication":
        raise AttributeError(name)

    from nxdrive.drive import server_type as _st

    config = _st.get(_st.get_default_key())
    klass = _st.load_class(config.oauth2_class_path)
    return klass or OAuthenticationBase
