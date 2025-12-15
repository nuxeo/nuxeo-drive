"""Integration tests for refresh_files method - macOS only."""

from time import monotonic
from unittest.mock import MagicMock, Mock

import pytest

from nxdrive.engine.engine import Engine
from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestRefreshFiles:
    """Test suite for refresh_files method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app._last_refresh_view = 0.0

        yield app, manager

        manager.close()

    def test_refresh_files_throttled_within_one_second(self, mock_application):
        """Test refresh_files is throttled when called within 1 second."""
        app, manager = mock_application

        # Set recent timestamp (less than 1 second ago)
        app._last_refresh_view = monotonic() - 0.5

        # Create mock engine as sender
        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test-engine-uid"

        # Create mock for get_last_files
        mock_get_last_files = Mock()
        app.get_last_files = mock_get_last_files
        app.sender = Mock(return_value=mock_engine)

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_files.__get__(app, Application)
        bound_method({})

        # Verify get_last_files was NOT called (throttled)
        mock_get_last_files.assert_not_called()

    def test_refresh_files_not_throttled_after_one_second(self, mock_application):
        """Test refresh_files executes when more than 1 second elapsed."""
        app, manager = mock_application

        # Set old timestamp (more than 1 second ago)
        app._last_refresh_view = monotonic() - 2.0

        # Create mock engine as sender
        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test-engine-uid"

        # Create mock for get_last_files
        mock_get_last_files = Mock()
        app.get_last_files = mock_get_last_files
        app.sender = Mock(return_value=mock_engine)

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_files.__get__(app, Application)

        old_timestamp = app._last_refresh_view
        bound_method({})

        # Verify get_last_files was called with engine.uid
        mock_get_last_files.assert_called_once_with(mock_engine.uid)
        # Verify timestamp was updated
        assert app._last_refresh_view > old_timestamp

    def test_refresh_files_initial_call_zero_timestamp(self, mock_application):
        """Test refresh_files executes on first call (timestamp = 0.0)."""
        app, manager = mock_application

        # Initial timestamp is 0.0
        app._last_refresh_view = 0.0

        # Create mock engine as sender
        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "engine-123"

        # Create mock for get_last_files
        mock_get_last_files = Mock()
        app.get_last_files = mock_get_last_files
        app.sender = Mock(return_value=mock_engine)

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_files.__get__(app, Application)
        bound_method({})

        # Verify get_last_files was called
        mock_get_last_files.assert_called_once_with("engine-123")
        # Verify timestamp was updated
        assert app._last_refresh_view > 0.0

    def test_refresh_files_updates_timestamp(self, mock_application):
        """Test refresh_files updates _last_refresh_view after execution."""
        app, manager = mock_application

        app._last_refresh_view = 0.0

        # Create mock engine
        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test-uid"

        app.get_last_files = Mock()
        app.sender = Mock(return_value=mock_engine)

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_files.__get__(app, Application)

        before_call = monotonic()
        bound_method({})
        after_call = monotonic()

        # Verify timestamp is between before and after the call
        assert before_call <= app._last_refresh_view <= after_call

    def test_refresh_files_calls_sender_to_get_engine(self, mock_application):
        """Test refresh_files calls sender() to get the engine."""
        app, manager = mock_application

        app._last_refresh_view = 0.0

        # Create mock engine
        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "sender-engine"

        mock_sender = Mock(return_value=mock_engine)
        app.sender = mock_sender
        app.get_last_files = Mock()

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_files.__get__(app, Application)
        bound_method({})

        # Verify sender was called
        mock_sender.assert_called_once()

    def test_refresh_files_passes_engine_uid_to_get_last_files(self, mock_application):
        """Test refresh_files passes correct engine.uid to get_last_files."""
        app, manager = mock_application

        app._last_refresh_view = 0.0

        # Create mock engine with specific uid
        mock_engine = Mock(spec=Engine)
        test_uid = "unique-engine-uid-789"
        mock_engine.uid = test_uid

        app.sender = Mock(return_value=mock_engine)
        mock_get_last_files = Mock()
        app.get_last_files = mock_get_last_files

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_files.__get__(app, Application)
        bound_method({})

        # Verify get_last_files received the correct uid
        mock_get_last_files.assert_called_once_with(test_uid)

    def test_refresh_files_exact_one_second_boundary(self, mock_application):
        """Test refresh_files behavior at exactly 1 second boundary."""
        app, manager = mock_application

        # Set timestamp to exactly 1 second ago
        app._last_refresh_view = monotonic() - 1.0

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "boundary-test"

        app.sender = Mock(return_value=mock_engine)
        mock_get_last_files = Mock()
        app.get_last_files = mock_get_last_files

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_files.__get__(app, Application)
        bound_method({})

        # At exactly 1.0 second, should execute (> 1.0 check)
        # Due to execution time, it will be slightly more than 1.0
        mock_get_last_files.assert_called_once()

    def test_refresh_files_with_metrics_parameter(self, mock_application):
        """Test refresh_files accepts metrics dict parameter (position-only)."""
        app, manager = mock_application

        app._last_refresh_view = 0.0

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "metrics-test"

        app.sender = Mock(return_value=mock_engine)
        app.get_last_files = Mock()

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_files.__get__(app, Application)

        # Pass metrics dict (though it's not used in the method)
        metrics = {"uploads": 5, "downloads": 3}
        bound_method(metrics)

        # Method should still execute normally
        app.get_last_files.assert_called_once()
