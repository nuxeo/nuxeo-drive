"""Unit tests for :mod:`nxdrive.alfresco.gui.auth` and
:mod:`nxdrive.alfresco.gui.darwin_config`.

These modules are small enough to test as pure functions / constants.
"""

from unittest.mock import Mock

from nxdrive.alfresco.gui.auth import basic_auth
from nxdrive.alfresco.gui.darwin_config import (
    ALFRESCO_AGENT_TEMPLATE,
    ALFRESCO_FINDERSYNC_APPEX,
    ALFRESCO_FINDERSYNC_ID_SUFFIX,
)


class TestBasicAuth:
    def test_delegates_to_api_bind_server(self) -> None:
        api = Mock()
        basic_auth(
            api,
            "/tmp/local",
            "https://alfresco.example.com/alfresco",
            "admin",
            "secret",
        )
        api.bind_server.assert_called_once_with(
            "/tmp/local",
            "https://alfresco.example.com/alfresco",
            "admin",
            password="secret",
        )


class TestDarwinConfigConstants:
    def test_agent_template_is_valid_plist(self) -> None:
        assert ALFRESCO_AGENT_TEMPLATE.startswith("<?xml")
        assert "<plist" in ALFRESCO_AGENT_TEMPLATE
        assert "%s" in ALFRESCO_AGENT_TEMPLATE  # Program placeholder
        assert "org.alfresco.drive.agentlauncher" in ALFRESCO_AGENT_TEMPLATE

    def test_findersync_identifiers(self) -> None:
        assert ALFRESCO_FINDERSYNC_ID_SUFFIX == "AlfrescoFinderSync"
        assert ALFRESCO_FINDERSYNC_APPEX == "AlfrescoFinderSync.appex"
