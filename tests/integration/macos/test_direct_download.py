"""Integration tests for direct download feature - macOS only."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestDirectDownloadUrl:
    """Test direct download URL handling - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app.api = Mock()

        # Mock manager methods
        manager.ctx_access_online = Mock()
        manager.ctx_copy_share_link = Mock()
        manager.ctx_edit_metadata = Mock()
        manager.directEdit = Mock()
        manager.directDownload = Mock()
        manager.wait_for_server_config = Mock(return_value=True)
        manager.restart_needed = False

        yield app, manager

        manager.close()

    def test_handle_direct_download_url(self, mock_application):
        """Test _handle_nxdrive_url routes direct download to manager signal."""
        app, manager = mock_application

        url = (
            "nxdrive://direct-download/"
            "https/server.com/11111111-1111-1111-1111-111111111111"
        )

        from nxdrive.gui.application import Application as RealApp

        bound = RealApp._handle_nxdrive_url.__get__(app, Application)
        result = bound(url)

        assert result is True
        manager.directDownload.emit.assert_called_once()
        args = manager.directDownload.emit.call_args[0][0]
        assert len(args) == 1
        assert args[0]["doc_id"] == "11111111-1111-1111-1111-111111111111"

    def test_handle_direct_download_batch_url(self, mock_application):
        """Test batch download URL with multiple documents."""
        app, manager = mock_application

        url = (
            "nxdrive://direct-download/"
            "https/server.com/11111111-1111-1111-1111-111111111111"
            " || 22222222-2222-2222-2222-222222222222"
        )

        from nxdrive.gui.application import Application as RealApp

        bound = RealApp._handle_nxdrive_url.__get__(app, Application)
        result = bound(url)

        assert result is True
        args = manager.directDownload.emit.call_args[0][0]
        assert len(args) == 2

    def test_handle_direct_download_empty_docs(self, mock_application):
        """Test direct download URL with no valid documents returns False."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse:
            mock_parse.return_value = {
                "command": "download_direct",
                "documents": [],
            }

            from nxdrive.gui.application import Application as RealApp

            bound = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound("nxdrive://direct-download/invalid")

            assert result is False
            manager.directDownload.emit.assert_not_called()

    def test_handle_direct_download_restart_needed(self, mock_application):
        """Test direct download when restart is needed shows msgbox."""
        app, manager = mock_application
        manager.restart_needed = True

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse:
            mock_parse.return_value = {
                "command": "download_direct",
                "documents": [{"doc_id": "uuid-1", "server_url": "https://s.com"}],
            }

            from nxdrive.gui.application import Application as RealApp

            bound = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound("nxdrive://direct-download/test")

            assert result is False
            app.show_msgbox_restart_needed.assert_called_once()

    def test_handle_unknown_command(self, mock_application):
        """Test unknown command returns False."""
        app, manager = mock_application

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path", return_value=""
        ), patch("nxdrive.gui.application.log"):
            mock_parse.return_value = {
                "command": "unknown_cmd",
                "filepath": "",
            }

            from nxdrive.gui.application import Application as RealApp

            bound = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound("nxdrive://unknown/test")

            assert result is False


@mac_only
class TestDirectDownloadEndToEnd:
    """End-to-end integration tests for direct download on macOS."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with a real Manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager

        manager.directEdit = Mock()
        manager.directDownload = Mock()
        manager.wait_for_server_config = Mock(return_value=True)
        manager.restart_needed = False

        yield app, manager

        manager.close()

    def test_url_parsing_to_signal_emission(self, mock_application):
        """Test full flow from URL parsing to signal emission."""
        app, manager = mock_application

        url = (
            "nxdrive://direct-download/"
            "https/drive.nuxeocloud.com/"
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            " || ffffffff-1111-2222-3333-444444444444"
        )

        from nxdrive.gui.application import Application as RealApp

        bound = RealApp._handle_nxdrive_url.__get__(app, Application)
        result = bound(url)

        assert result is True
        call_args = manager.directDownload.emit.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0]["server_url"] == "https://drive.nuxeocloud.com/nuxeo/"
        assert call_args[0]["doc_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert call_args[1]["doc_id"] == "ffffffff-1111-2222-3333-444444444444"
        assert call_args[1]["server_url"] == "https://drive.nuxeocloud.com/nuxeo/"
