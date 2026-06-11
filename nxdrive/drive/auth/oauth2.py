"""Base class for OAuth2-based authentication across server types."""

from typing import TYPE_CHECKING, Any

from nuxeo.auth import OAuth2

from nxdrive.drive.auth.base import Authentication
from nxdrive.drive.options import Options
from nxdrive.drive.utils import get_verify

if TYPE_CHECKING:
    from nxdrive.drive.auth import Token
    from nxdrive.drive.dao.base import BaseDAO


class OAuthenticationBase(Authentication):
    """Shared OAuth2 authentication logic.

    Handles the common initialisation (SSL verification, DAO reference,
    subclient kwargs) and the ``get_token()`` exchange that is identical
    for every server type.  Subclasses must implement ``connect_url()``
    and ``get_username()``.
    """

    def __init__(self, *args: Any, dao: "BaseDAO" = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.verification_needed = get_verify()
        self._dao = dao
        subclient_kwargs = kwargs.get("subclient_kwargs", {})
        subclient_kwargs["verify"] = self.verification_needed

        # Subclasses may override these before calling _build_oauth2()
        self._oauth2_client_id = Options.oauth2_client_id
        self._oauth2_client_secret = Options.oauth2_client_secret
        self._oauth2_openid_configuration_url = Options.oauth2_openid_configuration_url
        self._subclient_kwargs = subclient_kwargs

    def _build_oauth2(self) -> None:
        """Construct the ``OAuth2`` auth object from current settings.

        Called at the end of ``__init__`` (or by a subclass after
        overriding discovery attributes).
        """
        self.auth = OAuth2(
            self.url,
            client_id=self._oauth2_client_id,
            client_secret=self._oauth2_client_secret,
            authorization_endpoint=Options.oauth2_authorization_endpoint,
            openid_configuration_url=self._oauth2_openid_configuration_url,
            redirect_uri=Options.oauth2_redirect_uri,
            token_endpoint=Options.oauth2_token_endpoint,
            token=self.token,
            subclient_kwargs=self._subclient_kwargs,
        )

    def get_token(self, **kwargs: Any) -> "Token":
        token: str = self.auth.request_token(
            code_verifier=kwargs["code_verifier"],
            code=kwargs["code"],
            state=kwargs["state"],
        )
        self.token = token
        return token

    def get_username(self) -> str:  # type: ignore[empty-body]
        """Resolve the authenticated user's identity.  Server-type specific."""
