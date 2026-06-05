from typing import Any, Dict, Union

from .alfresco_oauth2 import AlfrescoOAuthentication
from .oauth2 import OAuthentication
from .token import TokenAuthentication

# Authentication token
#   - dict for OAuth2
#   - str for Nuxeo token
Token = Union[Dict[str, Any], str]


def get_auth(
    host: str, token: Token, **kwargs: Any
) -> Union[AlfrescoOAuthentication, OAuthentication, TokenAuthentication]:
    """Proxy to instantiate the appropriate authentication class based on the given *token*.

    When *server_type* is ``"ALFRESCO"`` and *token* is a dict (OAuth2),
    an ``AlfrescoOAuthentication`` is returned so that the username is
    resolved via the Alfresco People API instead of the Nuxeo Users API.
    """
    server_type = kwargs.pop("server_type", None)
    if isinstance(token, dict):
        if server_type == "ALFRESCO":
            return AlfrescoOAuthentication(host, token=token, **kwargs)
        return OAuthentication(host, token=token, **kwargs)
    return TokenAuthentication(host, token=token, **kwargs)


__all__ = (
    "AlfrescoOAuthentication",
    "OAuthentication",
    "Token",
    "TokenAuthentication",
    "get_auth",
)
