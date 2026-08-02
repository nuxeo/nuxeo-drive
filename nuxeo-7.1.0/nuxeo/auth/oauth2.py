# coding: utf-8
from time import time
from typing import Any, Callable, Dict, Optional, Tuple

import requests
from authlib.common.security import generate_token
from authlib.integrations.base_client.errors import AuthlibBaseError
from authlib.integrations.requests_client import OAuth2Session
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from jwt import JWT, jwk_from_dict
from jwt.exceptions import JWTDecodeError

from ..exceptions import OAuth2Error
from ..utils import log_response
from .base import AuthBase

Token = Dict[str, Any]
DEFAULT_AUTHORIZATION_ENDPOINT = "oauth2/authorize"
DEFAULT_TOKEN_ENDPOINT = "oauth2/token"


class OAuth2(AuthBase):
    """OAuth2 mechanism."""

    __slots__ = (
        "token",
        "verify",
        "_authorization_endpoint",
        "_client",
        "_host",
        "_openid_conf",
        "_token_endpoint",
        "_token_header",
    )

    AUTHORIZATION = "Authorization".encode("utf-8")
    GRANT_AUTHORIZATION_CODE = "authorization_code"

    def __init__(
        self,
        host,  # type: str
        client_secret=None,  # type: Optional[str]
        client_id=None,  # type: Optional[str]
        token=None,  # type: Optional[str]
        authorization_endpoint=None,  # type: Optional[str]
        token_endpoint=None,  # type: Optional[str]
        redirect_uri=None,  # type: Optional[str]
        openid_configuration_url=None,  # type: Optional[str]
        subclient_kwargs=None,  # Type: Optional[Dict[str, Any]]
    ):
        # type: (...) -> None
        if not host.endswith("/"):
            host += "/"
        self._host = host
        self._openid_conf = {}
        self._token_header = ""
        self.token = {}  # type: Token
        self.verify = None
        if token:
            self.set_token(token)
        if subclient_kwargs and "verify" in subclient_kwargs:
            self.verify = subclient_kwargs["verify"]
        # Allow to pass custom endpoints
        if openid_configuration_url:
            # OpenID Connect Discovery
            subclient_kwargs = subclient_kwargs or {}
            with requests.get(openid_configuration_url, **subclient_kwargs) as req:
                self._openid_conf = req.json()
            auth_endpoint = self._openid_conf["authorization_endpoint"]
            token_endpoint = self._openid_conf["token_endpoint"]
            with requests.get(self._openid_conf["jwks_uri"], **subclient_kwargs) as req:
                self._openid_conf["signing_keys"] = req.json()["keys"]
        else:
            auth_endpoint = authorization_endpoint or DEFAULT_AUTHORIZATION_ENDPOINT
            token_endpoint = token_endpoint or DEFAULT_TOKEN_ENDPOINT
            if not auth_endpoint.startswith("https://"):
                auth_endpoint = self._host + auth_endpoint
            if not token_endpoint.startswith("https://"):
                token_endpoint = self._host + token_endpoint

        self._client = OAuth2Session(
            client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri
        )
        self._client.session.hooks["response"] = [log_response]

        self._authorization_endpoint = auth_endpoint
        self._token_endpoint = token_endpoint

    def _request(self, method, *args, **kwargs):
        # type: (Callable, Any, Any) -> Any
        """Make a request with the OAuthlib client and shadow exceptions."""
        try:
            return method(*args, **kwargs)
        except AuthlibBaseError as exc:
            raise OAuth2Error(exc.description) from None

    def token_is_expired(self):
        # type: () -> bool
        """Check whenever the current token is expired or not."""
        token = self.token
        if not token:
            return False

        return token["expires_at"] < time()

    def create_authorization_url(self, **kwargs):
        # type: (Any) -> Tuple[str, str, str]
        """Create the authorization URL.
        Additionnal *kwargs* are passed to the underlying level.
        """
        code_verifier = generate_token(48)
        code_challenge = create_s256_code_challenge(code_verifier)
        uri, state = self._request(
            self._client.create_authorization_url,
            self._authorization_endpoint,
            code_challenge=code_challenge,
            code_challenge_method="S256",
            **kwargs,
        )
        return uri, state, code_verifier

    def request_token(self, **kwargs):
        # type: (Any) -> Token
        """Do request for a token.
        The *code_verifier* kwarg is required in any cases.
        Other kwargs can be a combination of either:
            1. *authorization_response* or;
            2. *code* and *state*.
        """
        kwargs = kwargs or {}
        if self.verify is not None and "verify" not in kwargs:
            kwargs["verify"] = self.verify
        token = self._request(
            self._client.fetch_token,
            self._token_endpoint,
            grant_type=self.GRANT_AUTHORIZATION_CODE,
            **kwargs,
        )
        self.set_token(token)
        return token

    def refresh_token(self, **kwargs):
        # type: (dict) -> Token
        """Do refresh the current token using the *refresh_token*."""

        token = self._request(
            self._client.refresh_token,
            self._token_endpoint,
            self.token["refresh_token"],
            **kwargs,
        )
        self.set_token(token)

        return token

    def set_token(self, token):
        # type: (Token) -> None
        """Apply the given *token*."""
        self.token = token
        self._token_header = "Bearer " + token["access_token"]

    def validate_access_token(self):
        error = ""
        instance = JWT()
        for key in self._openid_conf["signing_keys"]:
            try:
                # Validate token and return claims
                verifying_key = jwk_from_dict(key)
                return instance.decode(
                    self.token["access_token"], verifying_key, do_time_check=True
                )
            except JWTDecodeError as exc:
                error = str(exc)
        raise OAuth2Error(error)

    def __eq__(self, other):
        # type: (object) -> bool
        return self.token == getattr(other, "token", None)

    def __ne__(self, other):
        # type: (object) -> bool
        return not self == other

    def __call__(self, r):
        # type: (requests.Request) -> requests.Request
        if self.token_is_expired():
            if self.verify is not None:
                self.refresh_token(verify=self.verify)
            else:
                self.refresh_token()
        r.headers[self.AUTHORIZATION] = self._token_header
        return r
