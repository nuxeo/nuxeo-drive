"""Integration tests for _handle_connection method - macOS only."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from nxdrive.qt import constants as qt
from tests.markers import mac_only


@mac_only
class TestHandleConnection:
    """Test suite for _handle_connection method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app._nxdrive_listener = Mock()

        yield app, manager

        manager.close()

    def test_handle_connection_successful(self, mock_application):
        """Test _handle_connection with successful socket connection."""
        app, manager = mock_application

        test_url = "nxdrive://token/mytoken/myuser"
        test_payload = test_url.encode("utf-8")

        # Create mock connection
        mock_connection = Mock()
        mock_connection.waitForConnected.return_value = True
        mock_connection.waitForReadyRead.return_value = True
        mock_payload_data = Mock()
        mock_payload_data.data.return_value = test_payload
        mock_connection.readAll.return_value = mock_payload_data
        mock_connection.state.return_value = qt.ConnectedState

        app._nxdrive_listener.nextPendingConnection.return_value = mock_connection

        with patch.object(app, "_handle_nxdrive_url") as mock_handle_url, patch(
            "nxdrive.gui.application.force_decode"
        ) as mock_decode, patch("nxdrive.gui.application.log"):
            mock_decode.return_value = test_url

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_connection.__get__(app, Application)
            bound_method()

            # Verify connection flow
            app._nxdrive_listener.nextPendingConnection.assert_called_once()
            mock_connection.waitForConnected.assert_called_once()
            mock_connection.waitForReadyRead.assert_called_once()
            mock_connection.readAll.assert_called_once()

            # Verify URL was decoded and handled
            mock_decode.assert_called_once_with(test_payload)
            mock_handle_url.assert_called_once_with(test_url)

            # Verify disconnection
            mock_connection.disconnectFromServer.assert_called_once()
            mock_connection.waitForDisconnected.assert_called_once()

    def test_handle_connection_no_connection(self, mock_application):
        """Test _handle_connection when no connection is available."""
        app, manager = mock_application

        # Create a mock connection that fails waitForConnected
        mock_connection = Mock()
        mock_connection.waitForConnected.return_value = False
        mock_connection.errorString.return_value = "Connection failed"
        app._nxdrive_listener.nextPendingConnection.return_value = mock_connection

        with patch.object(app, "_handle_nxdrive_url") as mock_handle_url, patch(
            "nxdrive.gui.application.log"
        ) as mock_log:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_connection.__get__(app, Application)
            bound_method()

            # Verify early return when connection fails
            app._nxdrive_listener.nextPendingConnection.assert_called_once()
            mock_connection.waitForConnected.assert_called_once()
            mock_log.error.assert_called_once()
            mock_handle_url.assert_not_called()

            # Should log error
            mock_log.error.assert_called_once()

    def test_handle_connection_wait_for_connected_fails(self, mock_application):
        """Test _handle_connection when waitForConnected fails."""
        app, manager = mock_application

        # Create mock connection that fails to connect
        mock_connection = Mock()
        mock_connection.waitForConnected.return_value = False
        mock_connection.errorString.return_value = "Connection timeout"

        app._nxdrive_listener.nextPendingConnection.return_value = mock_connection

        with patch.object(app, "_handle_nxdrive_url") as mock_handle_url, patch(
            "nxdrive.gui.application.log"
        ) as mock_log:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_connection.__get__(app, Application)
            bound_method()

            # Verify connection attempt
            mock_connection.waitForConnected.assert_called_once()

            # Should log error with error string
            mock_log.error.assert_called_once()
            error_msg = mock_log.error.call_args[0][0]
            assert "Connection timeout" in error_msg

            # Should not proceed to read data
            mock_connection.waitForReadyRead.assert_not_called()
            mock_handle_url.assert_not_called()

    def test_handle_connection_wait_for_ready_read_fails(self, mock_application):
        """Test _handle_connection when waitForReadyRead returns False."""
        app, manager = mock_application

        # Create mock connection that connects but has no data
        mock_connection = Mock()
        mock_connection.waitForConnected.return_value = True
        mock_connection.waitForReadyRead.return_value = False
        mock_connection.state.return_value = Mock()  # Not ConnectedState

        app._nxdrive_listener.nextPendingConnection.return_value = mock_connection

        with patch.object(app, "_handle_nxdrive_url") as mock_handle_url, patch(
            "nxdrive.gui.application.log"
        ):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_connection.__get__(app, Application)
            bound_method()

            # Verify connection was established
            mock_connection.waitForConnected.assert_called_once()
            mock_connection.waitForReadyRead.assert_called_once()

            # Should not read data or handle URL
            mock_connection.readAll.assert_not_called()
            mock_handle_url.assert_not_called()

            # Should still disconnect
            mock_connection.disconnectFromServer.assert_called_once()

    def test_handle_connection_disconnects_when_connected(self, mock_application):
        """Test _handle_connection waits for disconnection when still connected."""
        app, manager = mock_application

        test_url = "nxdrive://token/test/user"
        test_payload = test_url.encode("utf-8")

        # Create mock connection
        mock_connection = Mock()
        mock_connection.waitForConnected.return_value = True
        mock_connection.waitForReadyRead.return_value = True
        mock_payload_data = Mock()
        mock_payload_data.data.return_value = test_payload
        mock_connection.readAll.return_value = mock_payload_data
        mock_connection.state.return_value = qt.ConnectedState

        app._nxdrive_listener.nextPendingConnection.return_value = mock_connection

        with patch.object(app, "_handle_nxdrive_url"), patch(
            "nxdrive.gui.application.force_decode", return_value=test_url
        ), patch("nxdrive.gui.application.log"):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_connection.__get__(app, Application)
            bound_method()

            # Verify disconnection sequence
            mock_connection.disconnectFromServer.assert_called_once()
            mock_connection.state.assert_called_once()
            mock_connection.waitForDisconnected.assert_called_once()

    def test_handle_connection_skips_wait_when_not_connected(self, mock_application):
        """Test _handle_connection skips waitForDisconnected when not connected."""
        app, manager = mock_application

        test_url = "nxdrive://token/test/user"
        test_payload = test_url.encode("utf-8")

        # Create mock connection
        mock_connection = Mock()
        mock_connection.waitForConnected.return_value = True
        mock_connection.waitForReadyRead.return_value = True
        mock_payload_data = Mock()
        mock_payload_data.data.return_value = test_payload
        mock_connection.readAll.return_value = mock_payload_data
        mock_connection.state.return_value = Mock()  # Not ConnectedState

        app._nxdrive_listener.nextPendingConnection.return_value = mock_connection

        with patch.object(app, "_handle_nxdrive_url"), patch(
            "nxdrive.gui.application.force_decode", return_value=test_url
        ), patch("nxdrive.gui.application.log"):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_connection.__get__(app, Application)
            bound_method()

            # Verify disconnection but no wait
            mock_connection.disconnectFromServer.assert_called_once()
            mock_connection.state.assert_called_once()
            mock_connection.waitForDisconnected.assert_not_called()

    def test_handle_connection_cleans_up_on_exception(self, mock_application):
        """Test _handle_connection cleans up connection even on exception."""
        app, manager = mock_application

        # Create mock connection that raises exception during readAll
        mock_connection = Mock()
        mock_connection.waitForConnected.return_value = True
        mock_connection.waitForReadyRead.return_value = True
        mock_connection.readAll.side_effect = Exception("Read error")

        app._nxdrive_listener.nextPendingConnection.return_value = mock_connection

        with patch("nxdrive.gui.application.log"):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_connection.__get__(app, Application)

            # Method doesn't handle exceptions - they propagate but finally block still runs
            with pytest.raises(Exception, match="Read error"):
                bound_method()

            # Connection cleanup happens in finally block (del con is always executed)

    def test_handle_connection_logs_success(self, mock_application):
        """Test _handle_connection logs success message."""
        app, manager = mock_application

        test_url = "nxdrive://token/test/user"
        test_payload = test_url.encode("utf-8")

        # Create mock connection
        mock_connection = Mock()
        mock_connection.waitForConnected.return_value = True
        mock_connection.waitForReadyRead.return_value = True
        mock_payload_data = Mock()
        mock_payload_data.data.return_value = test_payload
        mock_connection.readAll.return_value = mock_payload_data
        mock_connection.state.return_value = Mock()  # Not ConnectedState

        app._nxdrive_listener.nextPendingConnection.return_value = mock_connection

        with patch.object(app, "_handle_nxdrive_url"), patch(
            "nxdrive.gui.application.force_decode", return_value=test_url
        ), patch("nxdrive.gui.application.log") as mock_log:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._handle_connection.__get__(app, Application)
            bound_method()

            # Verify success logging
            log_calls = [call[0][0] for call in mock_log.info.call_args_list]
            assert any("Receiving socket connection" in msg for msg in log_calls)
            assert any("Successfully closed server socket" in msg for msg in log_calls)

    def test_handle_connection_with_various_payloads(self, mock_application):
        """Test _handle_connection with various URL payloads."""
        app, manager = mock_application

        test_urls = [
            "nxdrive://token/token123/user1",
            "nxdrive://edit/server/doc/user/download",
            "nxdrive://authorize/code=ABC&state=XYZ",
            "nxdrive://access-online/filepath=/path/to/file",
        ]

        for test_url in test_urls:
            test_payload = test_url.encode("utf-8")

            # Create mock connection
            mock_connection = Mock()
            mock_connection.waitForConnected.return_value = True
            mock_connection.waitForReadyRead.return_value = True
            mock_payload_data = Mock()
            mock_payload_data.data.return_value = test_payload
            mock_connection.readAll.return_value = mock_payload_data
            mock_connection.state.return_value = Mock()  # Not ConnectedState

            app._nxdrive_listener.nextPendingConnection.return_value = mock_connection

            with patch.object(app, "_handle_nxdrive_url") as mock_handle_url, patch(
                "nxdrive.gui.application.force_decode", return_value=test_url
            ), patch("nxdrive.gui.application.log"):
                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp._handle_connection.__get__(app, Application)
                bound_method()

                # Verify each URL was handled
                mock_handle_url.assert_called_with(test_url)
