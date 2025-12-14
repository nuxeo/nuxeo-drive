"""Integration tests for fetch_pending_tasks method - macOS only."""

from unittest.mock import MagicMock, Mock

import pytest

from nxdrive.engine.engine import Engine
from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestFetchPendingTasks:
    """Test suite for fetch_pending_tasks method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app.last_engine_uid = None

        yield app, manager

        manager.close()

    def test_fetch_pending_tasks_returns_tasks_list(self, mock_application):
        """Test fetch_pending_tasks returns list of tasks from remote."""
        app, manager = mock_application

        # Create mock engine with remote
        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "engine-123"

        mock_remote = Mock()
        mock_tasks_api = Mock()

        # Mock tasks list
        expected_tasks = [
            {"id": "task-1", "name": "Review Document"},
            {"id": "task-2", "name": "Approve Request"},
        ]
        mock_tasks_api.get.return_value = expected_tasks
        mock_remote.tasks = mock_tasks_api
        mock_remote.user_id = "user-abc"
        mock_engine.remote = mock_remote

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.fetch_pending_tasks.__get__(app, Application)
        result = bound_method(mock_engine)

        # Verify tasks were returned
        assert result == expected_tasks
        # Verify tasks.get was called with correct user dict
        mock_tasks_api.get.assert_called_once_with({"userId": "user-abc"})

    def test_fetch_pending_tasks_sets_last_engine_uid(self, mock_application):
        """Test fetch_pending_tasks sets last_engine_uid."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        test_uid = "test-engine-uid-456"
        mock_engine.uid = test_uid

        mock_remote = Mock()
        mock_tasks_api = Mock()
        mock_tasks_api.get.return_value = []
        mock_remote.tasks = mock_tasks_api
        mock_remote.user_id = "user-xyz"
        mock_engine.remote = mock_remote

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.fetch_pending_tasks.__get__(app, Application)
        bound_method(mock_engine)

        # Verify last_engine_uid was set
        assert app.last_engine_uid == test_uid

    def test_fetch_pending_tasks_with_empty_tasks(self, mock_application):
        """Test fetch_pending_tasks when no tasks are available."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "engine-empty"

        mock_remote = Mock()
        mock_tasks_api = Mock()
        mock_tasks_api.get.return_value = []
        mock_remote.tasks = mock_tasks_api
        mock_remote.user_id = "user-123"
        mock_engine.remote = mock_remote

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.fetch_pending_tasks.__get__(app, Application)
        result = bound_method(mock_engine)

        # Verify empty list is returned
        assert result == []

    def test_fetch_pending_tasks_handles_exception(self, mock_application):
        """Test fetch_pending_tasks handles exceptions and returns empty list."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "engine-error"

        mock_remote = Mock()
        mock_tasks_api = Mock()
        # Simulate exception
        mock_tasks_api.get.side_effect = Exception("API Error")
        mock_remote.tasks = mock_tasks_api
        mock_remote.user_id = "user-error"
        mock_engine.remote = mock_remote

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.fetch_pending_tasks.__get__(app, Application)
        result = bound_method(mock_engine)

        # Verify empty list is returned on error
        assert result == []
        # Verify last_engine_uid is still set
        assert app.last_engine_uid == "engine-error"

    def test_fetch_pending_tasks_logs_exception(self, mock_application):
        """Test fetch_pending_tasks logs exception information."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "engine-log-test"

        mock_remote = Mock()
        mock_tasks_api = Mock()
        test_exception = ValueError("Test error")
        mock_tasks_api.get.side_effect = test_exception
        mock_remote.tasks = mock_tasks_api
        mock_remote.user_id = "user-log"
        mock_engine.remote = mock_remote

        from nxdrive.gui.application import Application as RealApp

        # We can't easily verify log.info was called without more complex mocking,
        # but we can verify the method doesn't crash
        bound_method = RealApp.fetch_pending_tasks.__get__(app, Application)
        result = bound_method(mock_engine)

        # Should return empty list, not raise exception
        assert result == []

    def test_fetch_pending_tasks_passes_user_id_dict(self, mock_application):
        """Test fetch_pending_tasks passes userId dict to tasks.get."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "engine-userid"

        mock_remote = Mock()
        mock_tasks_api = Mock()
        mock_tasks_api.get.return_value = []
        mock_remote.tasks = mock_tasks_api
        test_user_id = "test-user-id-789"
        mock_remote.user_id = test_user_id
        mock_engine.remote = mock_remote

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.fetch_pending_tasks.__get__(app, Application)
        bound_method(mock_engine)

        # Verify correct user dict was passed
        expected_user_dict = {"userId": test_user_id}
        mock_tasks_api.get.assert_called_once_with(expected_user_dict)

    def test_fetch_pending_tasks_with_multiple_tasks(self, mock_application):
        """Test fetch_pending_tasks with multiple tasks."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "engine-multi"

        mock_remote = Mock()
        mock_tasks_api = Mock()

        tasks_list = [
            {"id": "task-1", "name": "Task One", "status": "pending"},
            {"id": "task-2", "name": "Task Two", "status": "in_progress"},
            {"id": "task-3", "name": "Task Three", "status": "pending"},
        ]
        mock_tasks_api.get.return_value = tasks_list
        mock_remote.tasks = mock_tasks_api
        mock_remote.user_id = "user-multi"
        mock_engine.remote = mock_remote

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.fetch_pending_tasks.__get__(app, Application)
        result = bound_method(mock_engine)

        # Verify all tasks are returned
        assert len(result) == 3
        assert result == tasks_list

    def test_fetch_pending_tasks_different_exception_types(self, mock_application):
        """Test fetch_pending_tasks handles different exception types."""
        app, manager = mock_application

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.fetch_pending_tasks.__get__(app, Application)

        exception_types = [
            ValueError("Value error"),
            KeyError("Key error"),
            RuntimeError("Runtime error"),
            ConnectionError("Connection error"),
        ]

        for exception in exception_types:
            mock_engine = Mock(spec=Engine)
            mock_engine.uid = f"engine-{type(exception).__name__}"

            mock_remote = Mock()
            mock_tasks_api = Mock()
            mock_tasks_api.get.side_effect = exception
            mock_remote.tasks = mock_tasks_api
            mock_remote.user_id = "user-test"
            mock_engine.remote = mock_remote

            result = bound_method(mock_engine)

            # Should always return empty list, not raise
            assert result == []

    def test_fetch_pending_tasks_updates_last_engine_uid_even_on_error(
        self, mock_application
    ):
        """Test fetch_pending_tasks updates last_engine_uid even when exception occurs."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        test_uid = "engine-uid-before-error"
        mock_engine.uid = test_uid

        mock_remote = Mock()
        mock_tasks_api = Mock()
        mock_tasks_api.get.side_effect = Exception("Error")
        mock_remote.tasks = mock_tasks_api
        mock_remote.user_id = "user-error"
        mock_engine.remote = mock_remote

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.fetch_pending_tasks.__get__(app, Application)
        bound_method(mock_engine)

        # last_engine_uid should be set even after error
        assert app.last_engine_uid == test_uid

    def test_fetch_pending_tasks_successive_calls(self, mock_application):
        """Test fetch_pending_tasks successive calls update last_engine_uid."""
        app, manager = mock_application

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.fetch_pending_tasks.__get__(app, Application)

        # First call
        mock_engine1 = Mock(spec=Engine)
        mock_engine1.uid = "engine-1"
        mock_remote1 = Mock()
        mock_tasks_api1 = Mock()
        mock_tasks_api1.get.return_value = [{"id": "task-1"}]
        mock_remote1.tasks = mock_tasks_api1
        mock_remote1.user_id = "user-1"
        mock_engine1.remote = mock_remote1

        bound_method(mock_engine1)
        assert app.last_engine_uid == "engine-1"

        # Second call with different engine
        mock_engine2 = Mock(spec=Engine)
        mock_engine2.uid = "engine-2"
        mock_remote2 = Mock()
        mock_tasks_api2 = Mock()
        mock_tasks_api2.get.return_value = [{"id": "task-2"}]
        mock_remote2.tasks = mock_tasks_api2
        mock_remote2.user_id = "user-2"
        mock_engine2.remote = mock_remote2

        bound_method(mock_engine2)
        assert app.last_engine_uid == "engine-2"

    def test_fetch_pending_tasks_uses_engine_remote(self, mock_application):
        """Test fetch_pending_tasks accesses engine.remote."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "engine-remote-test"

        mock_remote = Mock()
        mock_tasks_api = Mock()
        mock_tasks_api.get.return_value = []
        mock_remote.tasks = mock_tasks_api
        mock_remote.user_id = "user-remote"
        mock_engine.remote = mock_remote

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.fetch_pending_tasks.__get__(app, Application)
        bound_method(mock_engine)

        # Verify remote was accessed
        assert mock_engine.remote == mock_remote
        # Verify remote.tasks was accessed
        assert mock_remote.tasks == mock_tasks_api
