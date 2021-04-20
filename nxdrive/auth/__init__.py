from typing import Any, Dict, Union

from .oauth2 import OAuthentication
from .token import TokenAuthentication

# Authentication token
#   - dict for OAuth2
#   - str for Nuxeo token
Token = Union[Dict[str, Any], str]


def get_auth(
    host: str, token: Token, **kwargs: Any
) -> Union[OAuthentication, TokenAuthentication]:
    """Proxy to instantiate the appropriate authentication class based on the given *token*."""
    if isinstance(token, dict):
        return OAuthentication(host, token=token, **kwargs)
    return TokenAuthentication(host, token=token, **kwargs)


__all__ = ("OAuthentication", "Token", "TokenAuthentication", "get_auth")
