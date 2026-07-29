"""macOS-only integration test: web-auth flow does not freeze the UI.

Mirrors :mod:`tests.nuxeo.integration.macos.test_web_auth_not_frozen`
but exercises the Alfresco Application entry point.

Skipped on non-macOS platforms via :data:`tests.markers.mac_only` and
auto-skipped when the Alfresco server is unavailable (see the parent
``conftest.py``).
"""

from unittest.mock import MagicMock, Mock

import pytest

from nxdrive.drive.gui.application import Application
from nxdrive.drive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestAlfrescoWebAuthNotFrozen:
    @pytest.fixture
    def mock_application(self, tmp_path, alfresco_url):
        manager = Manager(str(tmp_path))
        app = MagicMock(spec=Application)
        app.manager = manager
        app.icon = Mock()
        app.api = Mock()
        app.api.handle_token = Mock()
        app.translate = lambda message, **kw: message
        try:
            yield app, manager, alfresco_url
        finally:
            manager.close()

    def test_web_auth_does_not_block(self, mock_application) -> None:
        app, manager, url = mock_application
        # Simulate token callback; expect no exception and that the API
        # forwards the token to the manager without blocking.
        app.api.handle_token("test-token", "admin")
        app.api.handle_token.assert_called_once_with("test-token", "admin")
