"""Base class for OAuth2-based authentication across server types."""

from typing import TYPE_CHECKING, Any

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
    for every server type.  Subclasses must implement ``connect_url()``,
    ``get_username()``, and ``_build_oauth2()``.
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
        """Construct the auth object from current settings.

        Subclasses **must** call this at the end of ``__init__``
        (or after overriding discovery attributes).  The default
        implementation stores an ``OAuth2`` handler into ``self.auth``
        using attributes set by the subclass.
        """
        raise NotImplementedError(
            "Subclasses must implement _build_oauth2() to create self.auth"
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
