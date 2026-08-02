# coding: utf-8
from typing import Any, Dict, Optional

from requests import Request

from ..constants import DEFAULT_APP_NAME
from .base import AuthBase

Token = Dict[str, Any]


class TokenAuth(AuthBase):
    """Attaches Nuxeo Token Authentication to the given Request object."""

    __slots__ = ("token",)

    HEADER_TOKEN = "X-Authentication-Token".encode("utf-8")

    def __init__(self, token):
        # type: (str) -> None
        self.token = token

    def request_token(
        self,
        client,
        device_id,  # type: str
        permission,  # type: str
        app_name=DEFAULT_APP_NAME,  # type: str
        device=None,  # type: Optional[str]
        revoke=False,  # type: bool
        auth=None,
        ssl_verify=True,  # type: bool
    ):
        # type: (...) -> Token
        """
        Request a token.

        :param device_id: device identifier
        :param permission: read/write permissions
        :param app_name: application name
        :param device: optional device description
        :param revoke: revoke the token
        """

        params = {
            "deviceId": device_id,
            "applicationName": app_name,
            "permission": permission,
            "revoke": str(revoke).lower(),
        }
        if device:
            params["deviceDescription"] = device

        path = "authentication/token"
        token = client.request(
            "GET",
            path,
            params=params,
            auth=auth,
            ssl_verify=ssl_verify,
        ).text
        token = "" if (revoke or "\n" in token) else token
        self.set_token(token)
        return token

    def set_token(self, token):
        # type: (Token) -> None
        """Apply the given *token*."""
        self.token = token

    def __eq__(self, other):
        # type: (object) -> bool
        return self.token == getattr(other, "token", None)

    def __ne__(self, other):
        # type: (object) -> bool
        return not self == other

    def __call__(self, r):
        # type: (Request) -> Request
        r.headers[self.HEADER_TOKEN] = self.token
        return r
