"""Unit tests for :mod:`nxdrive.alfresco.gui.auth` and
:mod:`nxdrive.alfresco.gui.darwin_config`.

These modules are small enough to test as pure functions / constants.
"""

import json
from unittest.mock import Mock, patch

import requests

from nxdrive.alfresco.gui.auth import basic_auth
from nxdrive.alfresco.gui.darwin_config import (
    ALFRESCO_AGENT_TEMPLATE,
    ALFRESCO_FINDERSYNC_APPEX,
    ALFRESCO_FINDERSYNC_ID_SUFFIX,
)
from nxdrive.drive.gui.api import QMLDriveApi


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


class TestAlfrescoCapabilities:
    @staticmethod
    def _make_api() -> QMLDriveApi:
        application = Mock()
        application.manager = Mock()
        return QMLDriveApi(application)

    def test_empty_server_url_returns_defaults(self) -> None:
        api = self._make_api()
        assert json.loads(api.alfresco_probe_capabilities("   ")) == {
            "discovered": False,
            "enable_basic_auth": True,
            "enable_pkce": True,
            "public_client": True,
            "audience": "",
        }

    def test_discovered_capabilities_are_normalized(self) -> None:
        api = self._make_api()
        capabilities = {
            "discovered": 1,
            "enable_basic_auth": 0,
            "enable_pkce": 1,
            "public_client": 0,
            "audience": "repository",
            "ignored": "value",
        }
        with patch(
            "nxdrive.alfresco.auth.oauth2.probe_capabilities",
            return_value=capabilities,
        ) as probe:
            result = api.alfresco_probe_capabilities("  https://alfresco.test/  ")

        assert json.loads(result) == {
            "discovered": True,
            "enable_basic_auth": False,
            "enable_pkce": True,
            "public_client": False,
            "audience": "repository",
        }
        probe.assert_called_once_with("https://alfresco.test/", verify=True)

    def test_probe_failure_returns_defaults(self) -> None:
        api = self._make_api()
        with patch(
            "nxdrive.alfresco.auth.oauth2.probe_capabilities",
            side_effect=requests.RequestException("offline"),
        ):
            result = api.alfresco_probe_capabilities("https://offline.test")

        assert json.loads(result) == {
            "discovered": False,
            "enable_basic_auth": True,
            "enable_pkce": True,
            "public_client": True,
            "audience": "",
        }
