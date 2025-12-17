"""Integration tests for _handle_nxdrive_url method - macOS only."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestHandleNxdriveUrl:
    """Test suite for _handle_nxdrive_url method - macOS only."""

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
        manager.wait_for_server_config = Mock(return_value=True)
        manager.restart_needed = False

        yield app, manager

        manager.close()

    def test_handle_nxdrive_url_invalid_url(self, mock_application):
        """Test _handle_nxdrive_url with invalid URL returns False."""
        app, manager = mock_application

        invalid_url = "not-a-valid-nxdrive-url"

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse:
            mock_parse.return_value = None

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(invalid_url)

            # Verify parsing was attempted
            mock_parse.assert_called_once_with(invalid_url)

            # Should return False for invalid URL
            assert result is False

    def test_handle_nxdrive_url_access_online(self, mock_application):
        """Test _handle_nxdrive_url with access-online command."""
        app, manager = mock_application

        test_url = "nxdrive://access-online/filepath=/path/to/file"
        test_path = "/path/to/file"

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path", return_value=test_path
        ), patch("nxdrive.gui.application.log"):
            mock_parse.return_value = {
                "command": "access-online",
                "filepath": "file:///path/to/file",
            }

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify ctx_access_online was called with the path
            manager.ctx_access_online.assert_called_once_with(test_path)

            # Should return True
            assert result is True

    def test_handle_nxdrive_url_copy_share_link(self, mock_application):
        """Test _handle_nxdrive_url with copy-share-link command."""
        app, manager = mock_application

        test_url = "nxdrive://copy-share-link/filepath=/shared/file"
        test_path = "/shared/file"

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path", return_value=test_path
        ), patch("nxdrive.gui.application.log"):
            mock_parse.return_value = {
                "command": "copy-share-link",
                "filepath": "file:///shared/file",
            }

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify ctx_copy_share_link was called
            manager.ctx_copy_share_link.assert_called_once_with(test_path)

            assert result is True

    def test_handle_nxdrive_url_direct_transfer(self, mock_application):
        """Test _handle_nxdrive_url with direct-transfer command."""
        app, manager = mock_application

        test_url = "nxdrive://direct-transfer/filepath=/transfer/file"
        test_path = "/transfer/file"

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path", return_value=test_path
        ), patch("nxdrive.gui.application.log"):
            mock_parse.return_value = {
                "command": "direct-transfer",
                "filepath": "file:///transfer/file",
            }

            app.ctx_direct_transfer = Mock()

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify ctx_direct_transfer was called
            app.ctx_direct_transfer.assert_called_once_with(test_path)

            assert result is True

    def test_handle_nxdrive_url_edit_metadata(self, mock_application):
        """Test _handle_nxdrive_url with edit-metadata command."""
        app, manager = mock_application

        test_url = "nxdrive://edit-metadata/filepath=/metadata/file"
        test_path = "/metadata/file"

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path", return_value=test_path
        ), patch("nxdrive.gui.application.log"):
            mock_parse.return_value = {
                "command": "edit-metadata",
                "filepath": "file:///metadata/file",
            }

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify ctx_edit_metadata was called
            manager.ctx_edit_metadata.assert_called_once_with(test_path)

            assert result is True

    def test_handle_nxdrive_url_with_remote_path(self, mock_application):
        """Test _handle_nxdrive_url with remote_path parameter."""
        app, manager = mock_application

        test_url = "nxdrive://access-online/remote_path=/remote/doc"
        remote_path = "/remote/doc"

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path"
        ), patch("nxdrive.gui.application.log"):
            mock_parse.return_value = {
                "command": "access-online",
                "remote_path": remote_path,
            }

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify ctx_access_online was called with remote_path args
            manager.ctx_access_online.assert_called_once_with(None, remote_path, True)

            assert result is True

    def test_handle_nxdrive_url_edit_command(self, mock_application):
        """Test _handle_nxdrive_url with edit command."""
        app, manager = mock_application

        test_url = "nxdrive://edit/server/doc123/user/download"

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path"
        ), patch("nxdrive.gui.application.log"):
            mock_parse.return_value = {
                "command": "edit",
                "server_url": "http://server.com",
                "doc_id": "doc123",
                "user": "testuser",
                "download_url": "http://download.url",
            }

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify directEdit.emit was called with correct args
            manager.directEdit.emit.assert_called_once_with(
                "http://server.com",
                "doc123",
                "testuser",
                "http://download.url",
            )

            assert result is True

    def test_handle_nxdrive_url_edit_server_not_configured(self, mock_application):
        """Test _handle_nxdrive_url with edit command when server not configured."""
        app, manager = mock_application

        test_url = "nxdrive://edit/server/doc123/user/download"

        manager.wait_for_server_config = Mock(return_value=False)

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path"
        ), patch("nxdrive.gui.application.log"), patch(
            "nxdrive.gui.application.APP_NAME", "TestApp"
        ):
            mock_parse.return_value = {
                "command": "edit",
                "server_url": "http://server.com",
                "doc_id": "doc123",
                "user": "testuser",
                "download_url": "http://download.url",
            }

            app.display_warning = Mock()

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify warning was displayed
            app.display_warning.assert_called_once()

            # directEdit should not be called
            manager.directEdit.emit.assert_not_called()

            # Should return False
            assert result is False

    def test_handle_nxdrive_url_edit_restart_needed(self, mock_application):
        """Test _handle_nxdrive_url with edit command when restart is needed."""
        app, manager = mock_application

        test_url = "nxdrive://edit/server/doc123/user/download"

        manager.restart_needed = True

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path"
        ), patch("nxdrive.gui.application.log"):
            mock_parse.return_value = {
                "command": "edit",
                "server_url": "http://server.com",
                "doc_id": "doc123",
                "user": "testuser",
                "download_url": "http://download.url",
            }

            app.show_msgbox_restart_needed = Mock()

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify restart message was shown
            app.show_msgbox_restart_needed.assert_called_once()

            # directEdit should not be called
            manager.directEdit.emit.assert_not_called()

            # Should return False
            assert result is False

    def test_handle_nxdrive_url_authorize_command(self, mock_application):
        """Test _handle_nxdrive_url with authorize command."""
        app, manager = mock_application

        test_url = "nxdrive://authorize/code=ABC123&state=xyz"

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path"
        ), patch("nxdrive.gui.application.log"):
            mock_parse.return_value = {
                "command": "authorize",
                "code": "ABC123",
                "state": "xyz",
            }

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify continue_oauth2_flow was called with correct args
            app.api.continue_oauth2_flow.assert_called_once_with(
                {"code": "ABC123", "state": "xyz"}
            )

            assert result is True

    def test_handle_nxdrive_url_token_command(self, mock_application):
        """Test _handle_nxdrive_url with token command."""
        app, manager = mock_application

        test_url = "nxdrive://token/mytoken123/myusername"

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path"
        ), patch("nxdrive.gui.application.log"):
            mock_parse.return_value = {
                "command": "token",
                "token": "mytoken123",
                "username": "myusername",
            }

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify handle_token was called
            app.api.handle_token.assert_called_once_with("mytoken123", "myusername")

            assert result is True

    def test_handle_nxdrive_url_unknown_command(self, mock_application):
        """Test _handle_nxdrive_url with unknown command."""
        app, manager = mock_application

        test_url = "nxdrive://unknown-command/param1/param2"

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path"
        ), patch("nxdrive.gui.application.log") as mock_log:
            mock_parse.return_value = {
                "command": "unknown-command",
                "param1": "value1",
            }

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify warning was logged
            mock_log.warning.assert_called_once()
            warning_msg = mock_log.warning.call_args[0][0]
            assert "Unknown event URL" in warning_msg
            assert test_url in warning_msg

            # Should return False
            assert result is False

    def test_handle_nxdrive_url_filepath_decoding(self, mock_application):
        """Test _handle_nxdrive_url properly decodes filepath."""
        app, manager = mock_application

        test_url = (
            "nxdrive://access-online/filepath=file:///path%20with%20spaces/file.txt"
        )
        decoded_path = "/path with spaces/file.txt"

        with patch("nxdrive.gui.application.parse_protocol_url") as mock_parse, patch(
            "nxdrive.gui.application.normalized_path", return_value=decoded_path
        ), patch("nxdrive.gui.application.unquote_plus") as mock_unquote, patch(
            "nxdrive.gui.application.log"
        ):
            mock_parse.return_value = {
                "command": "access-online",
                "filepath": "file:///path%20with%20spaces/file.txt",
            }
            mock_unquote.return_value = "/path with spaces/file.txt"

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_nxdrive_url.__get__(app, Application)
            result = bound_method(test_url)

            # Verify unquote_plus was used for decoding
            mock_unquote.assert_called()

            # Verify the decoded path was used
            manager.ctx_access_online.assert_called_once_with(decoded_path)

            assert result is True
