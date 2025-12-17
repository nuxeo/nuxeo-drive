"""Integration tests for event method - macOS only."""

from unittest.mock import MagicMock, Mock, patch
from urllib.parse import quote_plus

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from nxdrive.qt.imports import QEvent
from tests.markers import mac_only


@mac_only
class TestEvent:
    """Test suite for event method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager

        yield app, manager

        manager.close()

    def test_event_with_url_event(self, mock_application):
        """Test event method handles URL scheme events."""
        app, manager = mock_application

        test_url = "nxdrive://token/test_token/test_user"

        # Create a mock QEvent with url attribute
        mock_event = Mock(spec=QEvent)
        mock_url = Mock()
        mock_url.toString.return_value = test_url
        # Set url as an attribute that returns the mock_url
        type(mock_event).url = Mock(return_value=mock_url)

        with patch.object(
            app, "_handle_nxdrive_url", return_value=True
        ) as mock_handle_url:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.event.__get__(app, Application)
            result = bound_method(mock_event)

            # Verify _handle_nxdrive_url was called with decoded URL
            mock_handle_url.assert_called_once_with(test_url)

            # Should return True when URL was handled successfully
            assert result is True

    def test_event_with_encoded_url(self, mock_application):
        """Test event method handles URL-encoded events."""
        app, manager = mock_application

        original_url = "nxdrive://edit/server_url/doc_id/user name/download_url"
        encoded_url = quote_plus(original_url)

        # Create a mock QEvent with url attribute
        mock_event = Mock(spec=QEvent)
        mock_url = Mock()
        mock_url.toString.return_value = encoded_url
        mock_event.url = Mock(return_value=mock_url)

        with patch.object(
            app, "_handle_nxdrive_url", return_value=True
        ) as mock_handle_url:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.event.__get__(app, Application)
            result = bound_method(mock_event)

            # Verify _handle_nxdrive_url was called with decoded URL
            called_url = mock_handle_url.call_args[0][0]
            assert "user name" in called_url  # Should be decoded

            assert result is True

    def test_event_without_url_attribute(self, mock_application):
        """Test event method passes through events without url attribute."""
        app, manager = mock_application

        # Create a mock QEvent without url attribute
        mock_event = Mock(spec=QEvent)
        # Remove url attribute
        delattr(mock_event, "url")

        # Mock the super().event() call
        with patch(
            "nxdrive.gui.application.QApplication.event", return_value=False
        ) as mock_super_event:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.event.__get__(app, Application)
            result = bound_method(mock_event)

            # Should call super().event() for non-URL events
            mock_super_event.assert_called_once_with(mock_event)

            # Should return the result from super().event()
            assert result is False

    def test_event_with_exception_handling(self, mock_application):
        """Test event method handles exceptions gracefully."""
        app, manager = mock_application

        test_url = "nxdrive://invalid/url"

        # Create a mock QEvent with url attribute
        mock_event = Mock(spec=QEvent)
        mock_url = Mock()
        mock_url.toString.return_value = test_url
        mock_event.url = Mock(return_value=mock_url)

        # Make _handle_nxdrive_url raise an exception
        with patch.object(
            app, "_handle_nxdrive_url", side_effect=Exception("Test error")
        ), patch("nxdrive.gui.application.log") as mock_log:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.event.__get__(app, Application)
            result = bound_method(mock_event)

            # Verify exception was logged
            mock_log.exception.assert_called_once()
            log_message = mock_log.exception.call_args[0][0]
            assert test_url in log_message
            assert "Error handling URL event" in log_message

            # Should return False when exception occurs
            assert result is False

    def test_event_with_various_url_schemes(self, mock_application):
        """Test event method with various URL scheme patterns."""
        app, manager = mock_application

        test_urls = [
            "nxdrive://token/abc123/user1",
            "nxdrive://edit/http://server/doc123/user/http://download",
            "nxdrive://access-online/filepath=/path/to/file",
            "nxdrive://copy-share-link/filepath=/another/path",
            "nxdrive://direct-transfer/filepath=/transfer/path",
        ]

        for test_url in test_urls:
            # Create a mock QEvent with url attribute
            mock_event = Mock(spec=QEvent)
            mock_url = Mock()
            mock_url.toString.return_value = test_url
            mock_event.url = Mock(return_value=mock_url)

            with patch.object(
                app, "_handle_nxdrive_url", return_value=True
            ) as mock_handle_url:
                from nxdrive.gui.application import Application as RealApp

                bound_method = RealApp.event.__get__(app, Application)
                result = bound_method(mock_event)

                # Verify _handle_nxdrive_url was called
                mock_handle_url.assert_called_once_with(test_url)
                assert result is True

    def test_event_returns_false_when_handler_fails(self, mock_application):
        """Test event method returns False when URL handler returns False."""
        app, manager = mock_application

        test_url = "nxdrive://unknown/command"

        # Create a mock QEvent with url attribute
        mock_event = Mock(spec=QEvent)
        mock_url = Mock()
        mock_url.toString.return_value = test_url
        mock_event.url = Mock(return_value=mock_url)

        with patch.object(
            app, "_handle_nxdrive_url", return_value=False
        ) as mock_handle_url:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.event.__get__(app, Application)
            result = bound_method(mock_event)

            # Verify _handle_nxdrive_url was called
            mock_handle_url.assert_called_once_with(test_url)

            # Should return False when handler returns False
            assert result is False
