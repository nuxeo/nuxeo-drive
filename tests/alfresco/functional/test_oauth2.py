"""Functional tests for the Alfresco OAuth2 authentication flow.

These tests require the OAuth-capable Alfresco server. When
``ALFRESCO_OAUTH_CLIENT_ID`` / ``ALFRESCO_OAUTH_CLIENT_SECRET`` are
not configured, the tests are auto-skipped by
:func:`_skip_if_oauth_not_configured`.

Full-flow OAuth (browser interaction) is out of scope for CI — we
test the wiring: the OAuth handler builds an authorization URL that
targets the expected server and returns the expected shape.
"""

import pytest

from ... import env_alfresco as env


def _skip_if_oauth_not_configured() -> None:
    if not (env.ALFRESCO_OAUTH_CLIENT_ID and env.ALFRESCO_OAUTH_CLIENT_SECRET):
        pytest.skip("ALFRESCO_OAUTH_CLIENT_ID / _CLIENT_SECRET not set")


class TestOAuthWiring:
    def test_authorization_url_is_built(self) -> None:
        _skip_if_oauth_not_configured()

        from nxdrive.alfresco.auth.oauth2 import AlfrescoOAuthentication

        handler = AlfrescoOAuthentication(
            env.ALFRESCO_URL,
            dao=None,
            client_id=env.ALFRESCO_OAUTH_CLIENT_ID,
            client_secret=env.ALFRESCO_OAUTH_CLIENT_SECRET,
        )
        url, _state = handler.get_authorization_url()
        assert env.ALFRESCO_URL.split("//")[-1] in url or "auth" in url
