"""Unit tests for nxdrive.alfresco.engine.engine — targets uncovered lines."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.alfresco.engine.engine import AlfrescoEngine


def _make_engine():
    """Create a mock AlfrescoEngine bypassing QObject __init__."""
    with patch.object(AlfrescoEngine, "__init__", return_value=None):
        engine = AlfrescoEngine.__new__(AlfrescoEngine)
    engine.dao = MagicMock()
    engine.remote = MagicMock()
    engine.manager = MagicMock()
    engine.local = MagicMock()
    engine._name = "test"
    engine.uid = "test-uid"
    engine.hostname = "localhost"
    engine.remote_user = "admin"
    engine.server_url = "https://acs.example.com/"
    engine._remote_token = None
    engine._remote_password = "secret"
    engine._web_authentication = False
    engine._alfresco_ticket = ""
    engine._stopped = False
    engine._threads = []
    engine.local_folder = Path("/tmp/alfresco-test")
    engine.queue_manager = MagicMock()
    engine.invalidAuthentication = MagicMock()
    engine.version = "1.0.0"
    engine.timeout = 30
    engine.remote_cls = MagicMock()
    return engine


class TestBindTicketExtraction:
    """Tests for the ticket extraction path in AlfrescoEngine.bind()."""

    def test_no_ticket_found_logs_warning(self):
        """When auth succeeds but no ticket is found on remote.auth or
        remote.client.session.auth, a warning is logged and the password
        is NOT cleared."""
        engine = _make_engine()
        engine._remote_password = "secret"
        engine._remote_token = None

        # The remote has auth, but ticket is None (not set)
        engine.remote.auth = MagicMock(spec=[])  # no 'ticket' attribute
        engine.remote.client = MagicMock()
        engine.remote.client.session.auth = MagicMock(spec=[])  # no 'ticket'

        # Mock all the methods bind() calls
        engine._normalize_url = MagicMock(side_effect=lambda u: u)
        engine._setup_local_folder = MagicMock()
        engine.init_remote = MagicMock(return_value=engine.remote)
        engine.remote.check_credentials = MagicMock()  # succeeds
        engine._save_ticket = MagicMock()
        engine._save_token = MagicMock()
        engine._fetch_discovery_info = MagicMock()
        engine._check_root = MagicMock()

        from nxdrive.drive.objects import Binder

        binder = Binder(
            url="https://acs.example.com/",
            username="admin",
            password="secret",
            token=None,
            no_check=False,
            no_fscheck=True,
        )

        engine.bind(binder)

        # Password should NOT be cleared since no ticket was found
        assert engine._remote_password == "secret"
        # _save_ticket should NOT be called
        engine._save_ticket.assert_not_called()

    def test_ticket_found_on_auth(self):
        """When a ticket is present on remote.auth, it gets persisted
        and the password is cleared."""
        engine = _make_engine()
        engine._remote_password = "secret"
        engine._remote_token = None

        engine.remote.auth = MagicMock()
        engine.remote.auth.ticket = "TICKET-12345"

        engine._normalize_url = MagicMock(side_effect=lambda u: u)
        engine._setup_local_folder = MagicMock()
        engine.init_remote = MagicMock(return_value=engine.remote)
        engine.remote.check_credentials = MagicMock()
        engine._save_ticket = MagicMock()
        engine._save_token = MagicMock()
        engine._fetch_discovery_info = MagicMock()
        engine._check_root = MagicMock()

        from nxdrive.drive.objects import Binder

        binder = Binder(
            url="https://acs.example.com/",
            username="admin",
            password="secret",
            token=None,
            no_check=False,
            no_fscheck=True,
        )

        engine.bind(binder)

        # Password should be cleared and ticket saved
        assert engine._remote_password == ""
        assert engine._alfresco_ticket == "TICKET-12345"
        engine._save_ticket.assert_called_once_with("TICKET-12345")
