# coding: utf-8
from requests import Request


class AuthBase(object):
    """Base class that all auth implementations derive from.
    Copied from requests.auth to add __slots__ capability.
    """

    __slots__ = ()

    def __call__(self, r):
        # type: (Request) -> Request
        raise NotImplementedError("Auth hooks must be callable.")
