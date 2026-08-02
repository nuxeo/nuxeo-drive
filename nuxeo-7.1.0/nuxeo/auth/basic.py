# coding: utf-8
import base64
from requests import Request

from .base import AuthBase


class BasicAuth(AuthBase):
    """ Attaches a simple Basic Authentication to the given Request object. """

    __slots__ = ("username", "password", "_token_header")

    AUTHORIZATION = "Authorization".encode("utf-8")

    def __init__(self, username, password):
        # type: (str, str) -> None
        self.username = username
        self.password = password
        self.set_token(password)

    def set_token(self, token):
        # type: (str) -> None
        """Apply the given *token*."""
        self.password = token
        payload = f"{self.username}:{self.password}".encode("utf-8")
        self._token_header = f"Basic {base64.b64encode(payload).decode('utf-8')}"

    def __eq__(self, other):
        # type: (object) -> bool
        return all(
            [
                self.username == getattr(other, "username", None),
                self.password == getattr(other, "password", None),
            ]
        )

    def __ne__(self, other):
        # type: (object) -> bool
        return not self == other

    def __call__(self, r):
        # type: (Request) -> Request
        r.headers[self.AUTHORIZATION] = self._token_header
        return r
