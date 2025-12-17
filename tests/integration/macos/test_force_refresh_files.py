"""Integration tests for force_refresh_files method - macOS only."""

from unittest.mock import MagicMock, Mock

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestForceRefreshFiles:
    """Test suite for force_refresh_files method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app._last_refresh_view = 10.0  # Set initial value

        yield app, manager

        manager.close()

    def test_force_refresh_files_resets_timestamp(self, mock_application):
        """Test force_refresh_files resets _last_refresh_view to 0.0."""
        app, manager = mock_application

        # Set initial timestamp
        app._last_refresh_view = 123.456

        from nxdrive.gui.application import Application as RealApp

        # Create mock for refresh_files
        mock_refresh = Mock()
        app.refresh_files = mock_refresh

        bound_method = RealApp.force_refresh_files.__get__(app, Application)
        bound_method()

        # Verify timestamp was reset
        assert app._last_refresh_view == 0.0
        # Verify refresh_files was called with empty dict
        mock_refresh.assert_called_once_with({})

    def test_force_refresh_files_calls_refresh_files(self, mock_application):
        """Test force_refresh_files calls refresh_files with empty dict."""
        app, manager = mock_application

        from nxdrive.gui.application import Application as RealApp

        # Create mock for refresh_files
        mock_refresh = Mock()
        app.refresh_files = mock_refresh

        bound_method = RealApp.force_refresh_files.__get__(app, Application)
        bound_method()

        # Verify refresh_files was called exactly once with {}
        mock_refresh.assert_called_once_with({})

    def test_force_refresh_files_from_nonzero_timestamp(self, mock_application):
        """Test force_refresh_files from non-zero initial timestamp."""
        app, manager = mock_application

        # Set large timestamp
        app._last_refresh_view = 999999.999

        from nxdrive.gui.application import Application as RealApp

        mock_refresh = Mock()
        app.refresh_files = mock_refresh

        bound_method = RealApp.force_refresh_files.__get__(app, Application)
        bound_method()

        # Verify reset happened
        assert app._last_refresh_view == 0.0
        mock_refresh.assert_called_once()
