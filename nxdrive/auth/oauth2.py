from typing import TYPE_CHECKING, Any, Tuple

from nuxeo.auth import OAuth2
from nuxeo.client import Nuxeo

from ..options import Options
from .base import Authentication

if TYPE_CHECKING:
    from ..dao.base import BaseDAO
    from . import Token


class OAuthentication(Authentication):
    """Use the OAuth2 mechanism."""

    def __init__(self, *args: Any, dao: "BaseDAO" = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self._dao = dao
        self.auth = OAuth2(
            self.url,
            client_id=Options.oauth2_client_id,
            client_secret=Options.oauth2_client_secret,
            authorization_endpoint=Options.oauth2_authorization_endpoint,
            openid_configuration_url=Options.oauth2_openid_configuration_url,
            redirect_uri=Options.oauth2_redirect_uri,
            token_endpoint=Options.oauth2_token_endpoint,
            token=self.token,
        )

    def connect_url(self) -> str:
        kw = {"scope": Options.oauth2_scope} if Options.oauth2_scope else {}
        auth_details: Tuple[str, str, str] = self.auth.create_authorization_url(**kw)
        uri, state, code_verifier = auth_details

        # Save them for later
        if self._dao:
            self._dao.update_config("tmp_oauth2_url", self.url)
            self._dao.update_config("tmp_oauth2_code_verifier", code_verifier)
            self._dao.update_config("tmp_oauth2_state", state)

        return uri

    def get_token(self, **kwargs: Any) -> "Token":
        token: str = self.auth.request_token(
            code_verifier=kwargs["code_verifier"],
            code=kwargs["code"],
            state=kwargs["state"],
        )
        self.token = token
        return token

    def get_username(self) -> str:
        client = Nuxeo(host=self.url, auth=self.auth)
        user = client.users.current_user()
        username: str = user.uid
        return username
