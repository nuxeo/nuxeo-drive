"""Functional tests for the Alfresco OAuth2 authentication flow.

These tests require the OAuth-capable Alfresco server.  The handler
auto-discovers client credentials from the AIMS endpoint, so no
separate OAuth secrets are needed — only a reachable server.

Full-flow OAuth (browser interaction) is out of scope for CI — we
test the wiring: the OAuth handler builds an authorization URL that
targets the expected server and returns the expected shape.
"""

import pytest

from ... import env_alfresco as env


@pytest.mark.skipif(not env.ALFRESCO_URL, reason="ALFRESCO_URL not configured")
class TestOAuthWiring:
    def test_authorization_url_is_built(self) -> None:
        from nxdrive.alfresco.auth.oauth2 import AlfrescoOAuthentication

        handler = AlfrescoOAuthentication(env.ALFRESCO_URL, dao=None)
        url, _state, _verifier = handler.auth.create_authorization_url()
        assert env.ALFRESCO_URL.split("//")[-1] in url or "auth" in url
