"""Integration tests for open_task method - macOS only."""

from unittest.mock import MagicMock, Mock, patch
from urllib.parse import urlparse

import pytest

from nxdrive.engine.engine import Engine
from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestOpenTask:
    """Test suite for open_task method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager

        yield app, manager

        manager.close()

    def test_open_task_opens_browser_with_correct_url(self, mock_application):
        """Test open_task opens webbrowser with correct task URL."""
        app, manager = mock_application

        # Create mock engine
        mock_engine = Mock(spec=Engine)
        mock_engine.server_url = "https://nuxeo.example.com"
        task_id = "task-123-abc"

        with patch("nxdrive.gui.application.webbrowser") as mock_webbrowser:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.open_task.__get__(app, Application)
            bound_method(mock_engine, task_id)

            # Verify webbrowser.open was called with correct URL
            expected_url = "https://nuxeo.example.com/ui/#!/tasks/task-123-abc"
            mock_webbrowser.open.assert_called_once_with(expected_url)

    def test_open_task_constructs_correct_endpoint(self, mock_application):
        """Test open_task uses correct endpoint /ui/#!/tasks/."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.server_url = "https://server.com"
        task_id = "my-task"

        with patch("nxdrive.gui.application.webbrowser") as mock_webbrowser:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.open_task.__get__(app, Application)
            bound_method(mock_engine, task_id)

            # Verify endpoint is /ui/#!/tasks/
            expected_url = "https://server.com/ui/#!/tasks/my-task"
            mock_webbrowser.open.assert_called_once_with(expected_url)

    def test_open_task_with_different_server_urls(self, mock_application):
        """Test open_task with various server URLs."""
        app, manager = mock_application

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.open_task.__get__(app, Application)

        test_cases = [
            ("https://nuxeo1.com", "task-1", "https://nuxeo1.com/ui/#!/tasks/task-1"),
            (
                "http://localhost:8080",
                "task-2",
                "http://localhost:8080/ui/#!/tasks/task-2",
            ),
            (
                "https://demo.nuxeo.com/nuxeo",
                "task-3",
                "https://demo.nuxeo.com/nuxeo/ui/#!/tasks/task-3",
            ),
        ]

        with patch("nxdrive.gui.application.webbrowser") as mock_webbrowser:
            for server_url, task_id, expected_url in test_cases:
                mock_webbrowser.reset_mock()
                mock_engine = Mock(spec=Engine)
                mock_engine.server_url = server_url

                bound_method(mock_engine, task_id)
                mock_webbrowser.open.assert_called_once_with(expected_url)

    def test_open_task_with_different_task_ids(self, mock_application):
        """Test open_task with various task IDs."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.server_url = "https://server.com"

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.open_task.__get__(app, Application)

        test_task_ids = [
            "simple-task",
            "task-with-numbers-123",
            "TASK-UPPERCASE",
            "task_with_underscores",
            "very-long-task-id-with-many-parts-abc-123-xyz",
        ]

        with patch("nxdrive.gui.application.webbrowser") as mock_webbrowser:
            for task_id in test_task_ids:
                mock_webbrowser.reset_mock()
                bound_method(mock_engine, task_id)
                expected_url = f"https://server.com/ui/#!/tasks/{task_id}"
                mock_webbrowser.open.assert_called_once_with(expected_url)

    def test_open_task_url_format(self, mock_application):
        """Test open_task constructs URL in correct format."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.server_url = "https://example.com"
        task_id = "test-task-id"

        with patch("nxdrive.gui.application.webbrowser") as mock_webbrowser:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.open_task.__get__(app, Application)
            bound_method(mock_engine, task_id)

            called_url = mock_webbrowser.open.call_args[0][0]

            # Verify URL format using urlparse
            # Note: #! is treated as fragment by urlparse
            parsed = urlparse(called_url)
            assert parsed.scheme == "https"
            assert parsed.netloc == "example.com"
            assert parsed.path == "/ui/"
            assert parsed.fragment.startswith("!/tasks/")
            assert parsed.fragment.endswith(task_id)
            assert task_id == "test-task-id"

    def test_open_task_with_trailing_slash_in_server_url(self, mock_application):
        """Test open_task handles server URL with trailing slash."""
        app, manager = mock_application

        # Server URL with trailing slash
        mock_engine = Mock(spec=Engine)
        mock_engine.server_url = "https://server.com/"
        task_id = "task-xyz"

        with patch("nxdrive.gui.application.webbrowser") as mock_webbrowser:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.open_task.__get__(app, Application)
            bound_method(mock_engine, task_id)

            # URL might have double slash, but that's the current implementation
            called_url = mock_webbrowser.open.call_args[0][0]

            # Verify URL components using urlparse
            # Note: task_id is in the fragment after #!
            parsed = urlparse(called_url)
            assert parsed.netloc == "server.com"
            assert task_id in parsed.fragment
            assert task_id == "task-xyz"

    def test_open_task_webbrowser_called_once(self, mock_application):
        """Test open_task calls webbrowser.open exactly once."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.server_url = "https://test.com"

        with patch("nxdrive.gui.application.webbrowser") as mock_webbrowser:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.open_task.__get__(app, Application)
            bound_method(mock_engine, "task-abc")

            # Verify called exactly once
            assert mock_webbrowser.open.call_count == 1

    def test_open_task_multiple_calls(self, mock_application):
        """Test open_task can be called multiple times."""
        app, manager = mock_application

        mock_engine = Mock(spec=Engine)
        mock_engine.server_url = "https://multi.com"

        with patch("nxdrive.gui.application.webbrowser") as mock_webbrowser:
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.open_task.__get__(app, Application)

            # Call multiple times
            bound_method(mock_engine, "task-1")
            bound_method(mock_engine, "task-2")
            bound_method(mock_engine, "task-3")

            # Verify called three times
            assert mock_webbrowser.open.call_count == 3

            # Verify different URLs
            calls = mock_webbrowser.open.call_args_list
            assert "task-1" in calls[0][0][0]
            assert "task-2" in calls[1][0][0]
            assert "task-3" in calls[2][0][0]
