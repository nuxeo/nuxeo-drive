from typing import TYPE_CHECKING, Any, Tuple

from nuxeo.client import Nuxeo

from nxdrive.drive.auth.oauth2 import OAuthenticationBase
from nxdrive.drive.options import Options
from nxdrive.drive.utils import get_verify

if TYPE_CHECKING:
    from nxdrive.drive.dao.base import BaseDAO


class OAuthentication(OAuthenticationBase):
    """Use the OAuth2 mechanism."""

    def __init__(self, *args: Any, dao: "BaseDAO" = None, **kwargs: Any) -> None:
        super().__init__(*args, dao=dao, **kwargs)
        self._build_oauth2()

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

    def get_username(self) -> str:
        verification_needed = get_verify()
        client = Nuxeo(host=self.url, auth=self.auth, verify=verification_needed)
        user = client.users.current_user(verification_needed)
        username: str = user.uid
        return username
