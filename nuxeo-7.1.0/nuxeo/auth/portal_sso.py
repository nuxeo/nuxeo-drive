# coding: utf-8
from random import randint
from time import time
from typing import Optional

from requests import Request

from .base import AuthBase
from .utils import make_portal_sso_token


class PortalSSOAuth(AuthBase):
    """Attaches required HTTP headers for SSO with Portals.
    See https://doc.nuxeo.com/nxdoc/using-sso-portals/ for details.
    """

    __slots__ = ("digest_algorithm", "secret", "username")

    NX_USER = "NX_USER".encode("utf-8")
    NX_TOKEN = "NX_TOKEN".encode("utf-8")
    NX_RD = "NX_RD".encode("utf-8")
    NX_TS = "NX_TS".encode("utf-8")

    def __init__(self, username, secret, digest_algorithm="md5"):
        # type: (str, str, Optional[str]) -> None
        self.username = username
        self.secret = secret
        self.digest_algorithm = digest_algorithm.lower()

    def __eq__(self, other):
        # type: (object) -> bool
        return all(
            [
                self.username == getattr(other, "username", None),
                self.secret == getattr(other, "secret", None),
                self.digest_algorithm == getattr(other, "digest_algorithm", None),
            ]
        )

    def __ne__(self, other):
        # type: (object) -> bool
        return not self == other

    def __call__(self, r):
        # type: (Request) -> Request
        timestamp = int(time() * 1000)
        random = str(randint(0, timestamp))
        token = make_portal_sso_token(
            timestamp,
            random,
            self.secret,
            self.username,
            digest_algorithm=self.digest_algorithm,
        )

        r.headers[self.NX_TS] = str(timestamp)
        r.headers[self.NX_RD] = random
        r.headers[self.NX_TOKEN] = token
        r.headers[self.NX_USER] = self.username
        return r
