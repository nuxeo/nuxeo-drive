# coding: utf-8
from requests import Request

from .base import AuthBase


class JWTAuth(AuthBase):
    """ Attaches JSON Web Token Authentication to the given Request object. """

    __slots__ = ("token",)

    AUTHORIZATION = "Authorization".encode("utf-8")

    def __init__(self, token):
        # type: (str) -> None
        self.token = token

    def __eq__(self, other):
        # type: (object) -> bool
        return self.token == getattr(other, "token", None)

    def __ne__(self, other):
        # type: (object) -> bool
        return not self == other

    def __call__(self, r):
        # type: (Request) -> Request
        r.headers[self.AUTHORIZATION] = "Bearer " + self.token
        return r
