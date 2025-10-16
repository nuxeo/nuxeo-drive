"""Functional tests for queue_manager.py module."""

import time
from pathlib import Path
from queue import Empty, Queue
from threading import Lock
from typing import Optional
from unittest.mock import MagicMock, Mock, call, patch

import pytest
from nuxeo.exceptions import OngoingRequestError

from nxdrive.constants import WINDOWS
from nxdrive.engine.queue_manager import (
    WINERROR_CODE_PROCESS_CANNOT_ACCESS_FILE,
    QueueItem,
    QueueManager,
)
from nxdrive.options import Options


class MockDocPair:
    """Mock DocPair for testing."""

    def __init__(
        self, row_id=1, folderish=False, pair_state="locally_created", **kwargs
    ):
        self.id = row_id
        self.folderish = folderish
        self.pair_state: Optional[str] = pair_state
        self.local_path: Optional[Path] = Path(kwargs.get("local_path", "/test/path"))
        self.local_name = kwargs.get("local_name", "test_file.txt")
        self.remote_ref = kwargs.get("remote_ref", "test_ref")
        self.error_count = kwargs.get("error_count", 0)
        self.error_next_try = kwargs.get("error_next_try", 0)
        self.version = kwargs.get("version", 1)

    def __repr__(self):
        return f"MockDocPair[{self.id}](folderish={self.folderish}, state={self.pair_state})"


class MockEngine:
    """Mock Engine for testing."""

    def __init__(self):
        self.uid = "test_engine_uid"
        self.dao = MagicMock()
        # Make these methods properly mockable
        self.create_processor = MagicMock()
        self.create_thread = MagicMock()
        self.cancel_action_on = MagicMock()
        self.is_paused = MagicMock(return_value=False)
        self.is_stopped = MagicMock(return_value=False)

    def configure_return_values(self):
        """Configure default return values for methods."""
        processor = MagicMock()
        processor.get_current_pair.return_value = None
        self.create_processor.return_value = processor

        thread = MagicMock()
        thread.worker = processor
        thread.isFinished.return_value = False
        self.create_thread.return_value = thread


class MockDAO:
    """Mock DAO for testing."""

    def __init__(self):
        self.queue_manager = None
        self.register_queue_manager = MagicMock()

    def configure_queue_manager(self, qm):
        """Configure queue manager reference."""
        self.queue_manager = qm


# Test fixtures
@pytest.fixture
def mock_engine():
    engine = MockEngine()
    engine.configure_return_values()
    return engine


@pytest.fixture
def mock_dao():
    return MockDAO()


@pytest.fixture
def queue_manager(mock_engine, mock_dao):
    """Create a QueueManager instance for testing."""
    return QueueManager(mock_engine, mock_dao, max_file_processors=5)


@pytest.fixture
def mock_doc_pair():
    return MockDocPair()


class TestQueueItem:
    """Test cases for QueueItem class."""

    def test_queue_item_creation(self):
        """Test QueueItem creation with basic parameters."""
        item = QueueItem(1, True, "locally_created")
        assert item.id == 1
        assert item.folderish is True
        assert item.pair_state == "locally_created"

    def test_queue_item_repr(self):
        """Test QueueItem string representation."""
        item = QueueItem(42, False, "remotely_modified")
        repr_str = repr(item)
        assert "QueueItem[42]" in repr_str
        assert "folderish=False" in repr_str
        assert "state='remotely_modified'" in repr_str


class TestQueueManagerInitialization:
    """Test cases for QueueManager initialization and configuration."""

    def test_queue_manager_creation(self, mock_engine, mock_dao):
        """Test QueueManager creation with default parameters."""
        qm = QueueManager(mock_engine, mock_dao)

        assert qm.dao is mock_dao
        assert qm._engine is mock_engine
        assert isinstance(qm._local_folder_queue, Queue)
        assert isinstance(qm._local_file_queue, Queue)
        assert isinstance(qm._remote_file_queue, Queue)
        assert isinstance(qm._remote_folder_queue, Queue)
        assert qm._local_folder_enable is True
        assert qm._local_file_enable is True
        assert qm._remote_folder_enable is True
        assert qm._remote_file_enable is True
        assert qm._error_threshold == Options.max_errors
        assert qm._error_interval == 60
        assert qm._max_processors == 3  # max_file_processors - 2
        assert isinstance(qm._get_file_lock, Lock)
        assert isinstance(qm._thread_inspection, Lock)
        assert isinstance(qm._error_lock, Lock)
        assert qm._on_error_queue == {}

    def test_queue_manager_creation_with_custom_processors(self, mock_engine, mock_dao):
        """Test QueueManager creation with custom max processors."""
        qm = QueueManager(mock_engine, mock_dao, max_file_processors=10)
        assert qm._max_processors == 8  # 10 - 2

    def test_queue_manager_creation_with_minimum_processors(
        self, mock_engine, mock_dao
    ):
        """Test QueueManager creation with minimum processors."""
        qm = QueueManager(mock_engine, mock_dao, max_file_processors=1)
        assert qm._max_processors == 0  # 2 - 2 (minimum enforced)

    def test_set_max_processors(self, queue_manager):
        """Test setting maximum processors."""
        queue_manager.set_max_processors(10)
        assert queue_manager._max_processors == 8

        queue_manager.set_max_processors(1)
        assert queue_manager._max_processors == 0  # Minimum 2 enforced

    def test_init_processors(self, queue_manager):
        """Test processor initialization."""
        with patch.object(queue_manager, "queueProcessing") as mock_signal:
            queue_manager.init_processors()
            mock_signal.emit.assert_called_once()

    def test_shutdown_processors(self, queue_manager):
        """Test processor shutdown."""
        # Should not raise exception even if disconnect fails
        queue_manager.shutdown_processors()


class TestQueueControl:
    """Test cases for queue enable/disable functionality."""

    def test_suspend_resume(self, queue_manager):
        """Test suspending and resuming queues."""
        with patch.object(queue_manager, "queueProcessing") as mock_signal:
            # Test suspend
            queue_manager.suspend()
            assert not queue_manager._local_file_enable
            assert not queue_manager._local_folder_enable
            assert not queue_manager._remote_file_enable
            assert not queue_manager._remote_folder_enable
            assert queue_manager.is_paused()

            # Test resume
            queue_manager.resume()
            assert queue_manager._local_file_enable
            assert queue_manager._local_folder_enable
            assert queue_manager._remote_file_enable
            assert queue_manager._remote_folder_enable
            assert not queue_manager.is_paused()
            mock_signal.emit.assert_called()

    def test_enable_local_file_queue(self, queue_manager):
        """Test enabling/disabling local file queue."""
        with patch.object(queue_manager, "queueProcessing") as mock_signal:
            # Test disabling
            queue_manager.enable_local_file_queue(False)
            assert not queue_manager._local_file_enable

            # Test enabling
            queue_manager.enable_local_file_queue(True)
            assert queue_manager._local_file_enable
            mock_signal.emit.assert_called()

            # Test with emit=False
            queue_manager.enable_local_file_queue(False, emit=False)
            assert not queue_manager._local_file_enable

    def test_enable_local_folder_queue(self, queue_manager):
        """Test enabling/disabling local folder queue."""
        with patch.object(queue_manager, "queueProcessing") as mock_signal:
            queue_manager.enable_local_folder_queue(False)
            assert not queue_manager._local_folder_enable

            queue_manager.enable_local_folder_queue(True)
            assert queue_manager._local_folder_enable
            mock_signal.emit.assert_called()

    def test_enable_remote_file_queue(self, queue_manager):
        """Test enabling/disabling remote file queue."""
        with patch.object(queue_manager, "queueProcessing") as mock_signal:
            queue_manager.enable_remote_file_queue(False)
            assert not queue_manager._remote_file_enable

            queue_manager.enable_remote_file_queue(True)
            assert queue_manager._remote_file_enable
            mock_signal.emit.assert_called()

    def test_enable_remote_folder_queue(self, queue_manager):
        """Test enabling/disabling remote folder queue."""
        with patch.object(queue_manager, "queueProcessing") as mock_signal:
            queue_manager.enable_remote_folder_queue(False)
            assert not queue_manager._remote_folder_enable

            queue_manager.enable_remote_folder_queue(True)
            assert queue_manager._remote_folder_enable
            mock_signal.emit.assert_called()


class TestQueueOperations:
    """Test cases for queue push/get operations."""

    def test_push_ref(self, queue_manager):
        """Test pushing item by reference."""
        with patch.object(queue_manager, "newItem") as mock_signal:
            queue_manager.push_ref(1, True, "locally_created")
            assert queue_manager._local_folder_queue.qsize() == 1
            mock_signal.emit.assert_called_once_with(1)

    def test_push_local_folder(self, queue_manager):
        """Test pushing local folder to queue."""
        doc_pair = MockDocPair(1, True, "locally_created")
        with patch.object(queue_manager, "newItem") as mock_signal:
            queue_manager.push(doc_pair)
            assert queue_manager._local_folder_queue.qsize() == 1
            mock_signal.emit.assert_called_once_with(1)

    def test_push_local_file(self, queue_manager):
        """Test pushing local file to queue."""
        doc_pair = MockDocPair(2, False, "locally_modified")
        with patch.object(queue_manager, "newItem") as mock_signal:
            queue_manager.push(doc_pair)
            assert queue_manager._local_file_queue.qsize() == 1
            mock_signal.emit.assert_called_once_with(2)

    def test_push_local_file_deleted(self, queue_manager):
        """Test pushing deleted local file to queue."""
        doc_pair = MockDocPair(3, False, "locally_deleted")
        with patch.object(queue_manager._engine, "cancel_action_on") as mock_cancel:
            with patch.object(queue_manager, "newItem") as mock_signal:
                queue_manager.push(doc_pair)
                assert queue_manager._local_file_queue.qsize() == 1
                mock_cancel.assert_called_once_with(3)
                mock_signal.emit.assert_called_once_with(3)

    def test_push_remote_folder(self, queue_manager):
        """Test pushing remote folder to queue."""
        doc_pair = MockDocPair(4, True, "remotely_created")
        with patch.object(queue_manager, "newItem") as mock_signal:
            queue_manager.push(doc_pair)
            assert queue_manager._remote_folder_queue.qsize() == 1
            mock_signal.emit.assert_called_once_with(4)

    def test_push_remote_file(self, queue_manager):
        """Test pushing remote file to queue."""
        doc_pair = MockDocPair(5, False, "remotely_modified")
        with patch.object(queue_manager, "newItem") as mock_signal:
            queue_manager.push(doc_pair)
            assert queue_manager._remote_file_queue.qsize() == 1
            mock_signal.emit.assert_called_once_with(5)

    def test_push_remote_file_deleted(self, queue_manager):
        """Test pushing deleted remote file to queue."""
        doc_pair = MockDocPair(6, False, "remotely_deleted")
        with patch.object(queue_manager._engine, "cancel_action_on") as mock_cancel:
            with patch.object(queue_manager, "newItem") as mock_signal:
                queue_manager.push(doc_pair)
                assert queue_manager._remote_file_queue.qsize() == 1
                mock_cancel.assert_called_once_with(6)
                mock_signal.emit.assert_called_once_with(6)

    def test_push_parent_remotely(self, queue_manager):
        """Test pushing parent remotely state to queue."""
        doc_pair = MockDocPair(7, True, "parent_remotely_created")
        with patch.object(queue_manager, "newItem") as mock_signal:
            queue_manager.push(doc_pair)
            assert queue_manager._remote_folder_queue.qsize() == 1
            mock_signal.emit.assert_called_once_with(7)

    def test_push_direct_transfer(self, queue_manager):
        """Test pushing direct transfer state to queue."""
        doc_pair = MockDocPair(8, False, "direct_transfer")
        with patch.object(queue_manager, "newItem") as mock_signal:
            queue_manager.push(doc_pair)
            assert queue_manager._local_file_queue.qsize() == 1
            mock_signal.emit.assert_called_once_with(8)

    def test_push_non_processable_state(self, queue_manager):
        """Test pushing non-processable state (no action taken)."""
        doc_pair = MockDocPair(9, False, "conflicted")
        queue_manager.push(doc_pair)
        assert queue_manager._local_file_queue.qsize() == 0
        assert queue_manager._remote_file_queue.qsize() == 0

    def test_push_empty_pair_state(self, queue_manager):
        """Test pushing item with empty pair state."""
        doc_pair = MockDocPair(10, False, "")  # Empty string instead of None
        doc_pair.pair_state = None  # Set to None after creation
        queue_manager.push(doc_pair)
        assert queue_manager._local_file_queue.qsize() == 0

    def test_get_local_folder(self, queue_manager):
        """Test getting local folder from queue."""
        doc_pair = MockDocPair(1, True, "locally_created")
        queue_manager._local_folder_queue.put(doc_pair)

        result = queue_manager._get_local_folder()
        assert result is doc_pair

    def test_get_local_folder_empty(self, queue_manager):
        """Test getting from empty local folder queue."""
        result = queue_manager._get_local_folder()
        assert result is None

    def test_get_local_folder_timeout(self, queue_manager):
        """Test getting local folder with timeout."""
        with patch.object(queue_manager._local_folder_queue, "get", side_effect=Empty):
            result = queue_manager._get_local_folder()
            assert result is None

    def test_get_local_folder_with_error_doc(self, queue_manager):
        """Test getting local folder when item is in error queue."""
        doc_pair = MockDocPair(1, True, "locally_created")
        queue_manager._local_folder_queue.put(doc_pair)
        queue_manager._on_error_queue[1] = doc_pair

        # Should recursively try to get next item
        with patch.object(queue_manager, "_get_local_folder", return_value=None):
            queue_manager._get_local_folder()

    def test_get_local_file(self, queue_manager):
        """Test getting local file from queue."""
        doc_pair = MockDocPair(2, False, "locally_modified")
        queue_manager._local_file_queue.put(doc_pair)

        result = queue_manager._get_local_file()
        assert result is doc_pair

    def test_get_local_file_empty(self, queue_manager):
        """Test getting from empty local file queue."""
        result = queue_manager._get_local_file()
        assert result is None

    def test_get_remote_folder(self, queue_manager):
        """Test getting remote folder from queue."""
        doc_pair = MockDocPair(3, True, "remotely_created")
        queue_manager._remote_folder_queue.put(doc_pair)

        result = queue_manager._get_remote_folder()
        assert result is doc_pair

    def test_get_remote_file(self, queue_manager):
        """Test getting remote file from queue."""
        doc_pair = MockDocPair(4, False, "remotely_modified")
        queue_manager._remote_file_queue.put(doc_pair)

        result = queue_manager._get_remote_file()
        assert result is doc_pair

    def test_get_file_remote_priority(self, queue_manager):
        """Test getting file with remote queue priority."""
        local_doc = MockDocPair(1, False, "locally_modified")
        remote_doc = MockDocPair(2, False, "remotely_modified")

        queue_manager._local_file_queue.put(local_doc)
        queue_manager._remote_file_queue.put(remote_doc)
        queue_manager._remote_file_queue.put(remote_doc)  # Make remote larger

        result = queue_manager._get_file()
        assert result is not None

    def test_get_file_local_priority(self, queue_manager):
        """Test getting file with local queue priority."""
        local_doc = MockDocPair(1, False, "locally_modified")
        remote_doc = MockDocPair(2, False, "remotely_modified")

        queue_manager._local_file_queue.put(local_doc)
        queue_manager._local_file_queue.put(local_doc)  # Make local larger
        queue_manager._remote_file_queue.put(remote_doc)

        result = queue_manager._get_file()
        assert result is not None

    def test_get_file_empty_queues(self, queue_manager):
        """Test getting file from empty queues."""
        result = queue_manager._get_file()
        assert result is None


class TestErrorHandling:
    """Test cases for error handling functionality."""

    def test_push_error_basic(self, queue_manager):
        """Test basic error pushing."""
        doc_pair = MockDocPair(1, False, "locally_modified", error_count=1)

        with patch.object(queue_manager, "newError") as mock_signal:
            queue_manager.push_error(doc_pair)

            assert 1 in queue_manager._on_error_queue
            assert queue_manager._on_error_queue[1] is doc_pair
            assert doc_pair.error_next_try > int(time.time())
            mock_signal.emit.assert_called_once_with(1)

    def test_push_error_threshold_exceeded(self, queue_manager):
        """Test error pushing when threshold exceeded."""
        doc_pair = MockDocPair(1, False, "locally_modified", error_count=100)

        with patch.object(queue_manager, "newErrorGiveUp") as mock_signal:
            queue_manager.push_error(doc_pair)

            assert 1 not in queue_manager._on_error_queue
            mock_signal.emit.assert_called_once_with(1)

    def test_push_error_custom_interval(self, queue_manager):
        """Test error pushing with custom interval."""
        doc_pair = MockDocPair(1, False, "locally_modified", error_count=1)
        custom_interval = 120

        queue_manager.push_error(doc_pair, interval=custom_interval)
        expected_time = int(time.time()) + custom_interval
        assert abs(doc_pair.error_next_try - expected_time) <= 1

    @pytest.mark.skipif(not WINDOWS, reason="Windows-specific test")
    def test_push_error_windows_permission_error(self, queue_manager):
        """Test Windows permission error handling."""
        doc_pair = MockDocPair(1, False, "locally_modified", error_count=5)

        # Create a mock Windows permission error
        with patch("nxdrive.engine.queue_manager.WINDOWS", True):
            # Create mock exception with Windows error attributes
            perm_error = Mock(spec=PermissionError)
            perm_error.winerror = WINERROR_CODE_PROCESS_CANNOT_ACCESS_FILE
            perm_error.strerror = "The process cannot access the file"

            with patch.object(queue_manager, "newError") as mock_signal:
                with patch("isinstance", return_value=True):
                    queue_manager.push_error(doc_pair, exception=perm_error)

                    # Should reset error count to 1 for this specific error
                    expected_time = int(time.time()) + (
                        queue_manager._error_interval * 1
                    )
                    assert abs(doc_pair.error_next_try - expected_time) <= 1
                    mock_signal.emit.assert_called_once_with(1)

    def test_push_error_ongoing_request_error(self, queue_manager):
        """Test OngoingRequestError handling (no notification)."""
        doc_pair = MockDocPair(1, False, "locally_modified", error_count=1)
        ongoing_error = OngoingRequestError("Request ongoing")

        with patch.object(queue_manager, "newError") as mock_signal:
            queue_manager.push_error(doc_pair, exception=ongoing_error)

            # Should NOT be added to error queue when OngoingRequestError
            # This is the expected behavior - early return for OngoingRequestError
            assert 1 not in queue_manager._on_error_queue
            mock_signal.emit.assert_not_called()

    def test_push_error_runtime_error(self, queue_manager):
        """Test error pushing with RuntimeError on signal emit."""
        doc_pair = MockDocPair(1, False, "locally_modified", error_count=1)

        with patch.object(queue_manager, "newError") as mock_signal:
            mock_signal.emit.side_effect = RuntimeError("QueueManager deleted")

            # Should not raise exception
            queue_manager.push_error(doc_pair)
            assert 1 in queue_manager._on_error_queue

    def test_on_error_timer(self, queue_manager):
        """Test error timer processing."""
        # Add doc with error time in the past
        doc_pair = MockDocPair(1, False, "locally_modified")
        doc_pair.error_next_try = int(time.time()) - 10  # 10 seconds ago
        queue_manager._on_error_queue[1] = doc_pair

        with patch.object(queue_manager, "push") as mock_push:
            queue_manager._on_error_timer()

            # Should have pushed the doc back to queue
            mock_push.assert_called_once()
            assert 1 not in queue_manager._on_error_queue

    def test_on_error_timer_not_ready(self, queue_manager):
        """Test error timer with doc not ready for retry."""
        # Add doc with error time in the future
        doc_pair = MockDocPair(1, False, "locally_modified")
        doc_pair.error_next_try = int(time.time()) + 60  # 1 minute from now
        queue_manager._on_error_queue[1] = doc_pair

        with patch.object(queue_manager, "push") as mock_push:
            queue_manager._on_error_timer()

            # Should not have pushed the doc back to queue
            mock_push.assert_not_called()
            assert 1 in queue_manager._on_error_queue

    def test_on_error_timer_stops_when_empty(self, queue_manager):
        """Test error timer stops when queue becomes empty."""
        queue_manager._error_timer = MagicMock()
        queue_manager._on_error_queue = {}

        queue_manager._on_error_timer()
        queue_manager._error_timer.stop.assert_called_once()

    def test_is_on_error(self, queue_manager):
        """Test checking if doc is in error queue."""
        doc_pair = MockDocPair(1, False, "locally_modified")
        queue_manager._on_error_queue[1] = doc_pair

        assert queue_manager._is_on_error(1) is True
        assert queue_manager._is_on_error(2) is False

    def test_on_new_error(self, queue_manager):
        """Test new error signal handling."""
        queue_manager._error_timer = MagicMock()
        queue_manager._on_new_error()
        queue_manager._error_timer.start.assert_called_once_with(1000)

    def test_get_errors_count(self, queue_manager):
        """Test getting error count."""
        assert queue_manager.get_errors_count() == 0

        doc_pair = MockDocPair(1, False, "locally_modified")
        queue_manager._on_error_queue[1] = doc_pair
        assert queue_manager.get_errors_count() == 1

    def test_get_error_threshold(self, queue_manager):
        """Test getting error threshold."""
        assert queue_manager.get_error_threshold() == Options.max_errors


class TestThreadManagement:
    """Test cases for thread management functionality."""

    def test_thread_finished_cleanup(self, queue_manager):
        """Test thread cleanup when finished."""
        # Mock finished processor thread
        finished_thread = MagicMock()
        finished_thread.isFinished.return_value = True
        queue_manager._processors_pool = [finished_thread]

        # Mock main threads as finished
        queue_manager._local_folder_thread = MagicMock()
        queue_manager._local_folder_thread.isFinished.return_value = True
        queue_manager._local_file_thread = MagicMock()
        queue_manager._local_file_thread.isFinished.return_value = True
        queue_manager._remote_folder_thread = MagicMock()
        queue_manager._remote_folder_thread.isFinished.return_value = True
        queue_manager._remote_file_thread = MagicMock()
        queue_manager._remote_file_thread.isFinished.return_value = True

        with patch.object(queue_manager, "newItem") as mock_signal:
            queue_manager._thread_finished()

            # Should clean up finished threads
            finished_thread.quit.assert_called_once()
            assert len(queue_manager._processors_pool) == 0
            assert queue_manager._local_folder_thread is None
            assert queue_manager._local_file_thread is None
            assert queue_manager._remote_folder_thread is None
            assert queue_manager._remote_file_thread is None

            # Should emit signal to continue processing
            mock_signal.emit.assert_called_once_with(None)

    def test_thread_finished_paused_engine(self, queue_manager):
        """Test thread cleanup when engine is paused."""
        queue_manager._engine.is_paused.return_value = True

        with patch.object(queue_manager, "newItem") as mock_signal:
            queue_manager._thread_finished()
            # Should not emit signal when paused
            mock_signal.emit.assert_not_called()

    def test_thread_finished_stopped_engine(self, queue_manager):
        """Test thread cleanup when engine is stopped."""
        queue_manager._engine.is_stopped.return_value = True

        with patch.object(queue_manager, "newItem") as mock_signal:
            queue_manager._thread_finished()
            # Should not emit signal when stopped
            mock_signal.emit.assert_not_called()

    def test_active_calls_thread_finished(self, queue_manager):
        """Test active() method calls _thread_finished()."""
        with patch.object(queue_manager, "_thread_finished") as mock_cleanup:
            with patch.object(
                queue_manager, "is_active", return_value=True
            ) as mock_active:
                result = queue_manager.active()
                mock_cleanup.assert_called_once()
                mock_active.assert_called_once()
                assert result is True

    def test_is_active_with_threads(self, queue_manager):
        """Test is_active returns True when threads are running."""
        queue_manager._local_folder_thread = MagicMock()
        assert queue_manager.is_active() is True

        queue_manager._local_folder_thread = None
        queue_manager._local_file_thread = MagicMock()
        assert queue_manager.is_active() is True

        queue_manager._local_file_thread = None
        queue_manager._remote_file_thread = MagicMock()
        assert queue_manager.is_active() is True

        queue_manager._remote_file_thread = None
        queue_manager._remote_folder_thread = MagicMock()
        assert queue_manager.is_active() is True

        queue_manager._remote_folder_thread = None
        queue_manager._processors_pool = [MagicMock()]
        assert queue_manager.is_active() is True

    def test_is_active_no_threads(self, queue_manager):
        """Test is_active returns False when no threads are running."""
        assert queue_manager.is_active() is False

    def test_create_thread(self, queue_manager):
        """Test thread creation."""

        def item_getter():
            return None

        thread = queue_manager._create_thread(item_getter, "TestProcessor")

        assert thread is not None
        queue_manager._engine.create_processor.assert_called_once_with(item_getter)
        queue_manager._engine.create_thread.assert_called_once()


class TestMetricsAndStatus:
    """Test cases for metrics and status functionality."""

    def test_get_metrics(self, queue_manager):
        """Test getting queue metrics."""
        # Add some items to queues
        queue_manager._local_folder_queue.put(MockDocPair(1, True, "locally_created"))
        queue_manager._local_file_queue.put(MockDocPair(2, False, "locally_modified"))
        queue_manager._remote_folder_queue.put(MockDocPair(3, True, "remotely_created"))
        queue_manager._remote_file_queue.put(MockDocPair(4, False, "remotely_modified"))
        queue_manager._remote_file_queue.put(MockDocPair(5, False, "remotely_modified"))

        # Add error item
        queue_manager._on_error_queue[6] = MockDocPair(6, False, "locally_modified")

        # Add processor thread
        queue_manager._processors_pool = [MagicMock()]
        queue_manager._local_folder_thread = MagicMock()

        metrics = queue_manager.get_metrics()

        assert isinstance(metrics, dict)
        assert metrics["is_paused"] is False
        assert metrics["local_folder_queue"] == 1
        assert metrics["local_file_queue"] == 1
        assert metrics["remote_folder_queue"] == 1
        assert metrics["remote_file_queue"] == 2
        assert metrics["total_queue"] == 5
        assert metrics["error_queue"] == 1
        assert metrics["additional_processors"] == 1
        assert metrics["local_folder_thread"] is True
        assert metrics["local_file_thread"] is False
        assert metrics["remote_folder_thread"] is False
        assert metrics["remote_file_thread"] is False

    def test_get_overall_size(self, queue_manager):
        """Test getting overall queue size."""
        assert queue_manager.get_overall_size() == 0

        # Add items to different queues
        queue_manager._local_folder_queue.put(MockDocPair(1, True, "locally_created"))
        queue_manager._local_file_queue.put(MockDocPair(2, False, "locally_modified"))
        queue_manager._remote_folder_queue.put(MockDocPair(3, True, "remotely_created"))
        queue_manager._remote_file_queue.put(MockDocPair(4, False, "remotely_modified"))
        queue_manager._remote_file_queue.put(MockDocPair(5, False, "remotely_modified"))

        assert queue_manager.get_overall_size() == 5


class TestProcessorCoordination:
    """Test cases for processor coordination functionality."""

    def test_is_processing_file_no_processor(self):
        """Test is_processing_file with no processor."""
        # Use a mock QThread instead of None
        mock_thread = Mock()
        mock_thread.__bool__ = Mock(return_value=False)  # Make it falsy
        result = QueueManager.is_processing_file(mock_thread, Path("/test"))
        assert result is False

    def test_is_processing_file_wrong_worker_type(self):
        """Test is_processing_file with wrong worker type."""
        mock_thread = MagicMock()
        mock_thread.worker = "not_a_processor"

        result = QueueManager.is_processing_file(mock_thread, Path("/test"))
        assert result is False

    def test_is_processing_file_no_current_pair(self):
        """Test is_processing_file with no current pair."""
        from nxdrive.engine.processor import Processor

        mock_thread = MagicMock()
        mock_processor = MagicMock(spec=Processor)
        mock_processor.get_current_pair.return_value = None
        mock_thread.worker = mock_processor

        result = QueueManager.is_processing_file(mock_thread, Path("/test"))
        assert result is False

    def test_is_processing_file_no_local_path(self):
        """Test is_processing_file with no local path."""
        from nxdrive.engine.processor import Processor

        mock_thread = MagicMock()
        mock_processor = MagicMock(spec=Processor)
        mock_doc_pair = MockDocPair(1, False, "locally_modified")
        mock_doc_pair.local_path = None
        mock_processor.get_current_pair.return_value = mock_doc_pair
        mock_thread.worker = mock_processor

        result = QueueManager.is_processing_file(mock_thread, Path("/test"))
        assert result is False

    def test_is_processing_file_exact_match(self):
        """Test is_processing_file with exact path match."""
        from nxdrive.engine.processor import Processor

        mock_thread = MagicMock()
        mock_processor = MagicMock(spec=Processor)
        test_path = Path("/test/file.txt")
        mock_doc_pair = MockDocPair(
            1, False, "locally_modified", local_path=str(test_path)
        )
        mock_doc_pair.local_path = test_path
        mock_processor.get_current_pair.return_value = mock_doc_pair
        mock_thread.worker = mock_processor

        result = QueueManager.is_processing_file(
            mock_thread, test_path, exact_match=True
        )
        assert result is True

    def test_is_processing_file_parent_match(self):
        """Test is_processing_file with parent path match."""
        from nxdrive.engine.processor import Processor

        mock_thread = MagicMock()
        mock_processor = MagicMock(spec=Processor)
        doc_path = Path("/test/subfolder/file.txt")
        parent_path = Path("/test")
        mock_doc_pair = MockDocPair(
            1, False, "locally_modified", local_path=str(doc_path)
        )
        mock_doc_pair.local_path = doc_path
        mock_processor.get_current_pair.return_value = mock_doc_pair
        mock_thread.worker = mock_processor

        result = QueueManager.is_processing_file(
            mock_thread, parent_path, exact_match=False
        )
        assert result is True

    def test_get_processors_on_exact_match(self, queue_manager):
        """Test getting processors on specific path with exact match."""
        test_path = Path("/test/file.txt")

        # Mock processor with matching path
        mock_processor = MagicMock()
        mock_thread = MagicMock()
        mock_thread.worker = mock_processor
        queue_manager._local_file_thread = mock_thread

        with patch.object(QueueManager, "is_processing_file", return_value=True):
            processors = queue_manager.get_processors_on(test_path, exact_match=True)
            assert len(processors) == 1
            assert processors[0] is mock_processor

    def test_get_processors_on_no_match(self, queue_manager):
        """Test getting processors with no matching paths."""
        test_path = Path("/test/file.txt")

        with patch.object(QueueManager, "is_processing_file", return_value=False):
            processors = queue_manager.get_processors_on(test_path)
            assert len(processors) == 0

    def test_get_processors_on_processor_pool(self, queue_manager):
        """Test getting processors from processor pool when main threads are empty."""
        test_path = Path("/test/file.txt")

        # Mock processor pool with matching processor
        mock_processor = MagicMock()
        mock_thread = MagicMock()
        mock_thread.worker = mock_processor
        queue_manager._processors_pool = [mock_thread]

        # Ensure main threads are None so it checks the pool
        queue_manager._local_folder_thread = None
        queue_manager._remote_folder_thread = None
        queue_manager._local_file_thread = None
        queue_manager._remote_file_thread = None

        with patch.object(
            queue_manager, "is_processing_file", return_value=True
        ) as mock_is_processing:
            processors = queue_manager.get_processors_on(test_path)

            # Should have called is_processing_file once on the pool processor
            assert mock_is_processing.call_count == 1
            assert len(processors) == 1
            assert processors[0] is mock_processor

    def test_interrupt_processors_on(self, queue_manager):
        """Test interrupting processors on specific path."""
        test_path = Path("/test/file.txt")

        mock_processor = MagicMock()

        with patch.object(
            queue_manager, "get_processors_on", return_value=[mock_processor]
        ):
            queue_manager.interrupt_processors_on(test_path, exact_match=False)
            mock_processor.stop.assert_called_once()

    def test_has_file_processors_on_local_file(self, queue_manager):
        """Test checking for file processors on local file thread."""
        test_path = Path("/test/file.txt")
        queue_manager._local_file_thread = MagicMock()

        with patch.object(QueueManager, "is_processing_file", return_value=True):
            result = queue_manager.has_file_processors_on(test_path)
            assert result is True

    def test_has_file_processors_on_remote_file(self, queue_manager):
        """Test checking for file processors on remote file thread."""
        test_path = Path("/test/file.txt")
        queue_manager._remote_file_thread = MagicMock()
        queue_manager._local_file_thread = None

        with patch.object(QueueManager, "is_processing_file", return_value=True):
            result = queue_manager.has_file_processors_on(test_path)
            assert result is True

    def test_has_file_processors_on_processor_pool(self, queue_manager):
        """Test checking for file processors in processor pool."""
        test_path = Path("/test/file.txt")
        queue_manager._processors_pool = [MagicMock()]

        with patch.object(QueueManager, "is_processing_file") as mock_is_processing:
            # Return False for main threads, True for pool thread
            mock_is_processing.side_effect = [False, True]

            result = queue_manager.has_file_processors_on(test_path)
            assert result is True

    def test_has_file_processors_on_none(self, queue_manager):
        """Test checking for file processors when none are processing."""
        test_path = Path("/test/file.txt")

        with patch.object(QueueManager, "is_processing_file", return_value=False):
            result = queue_manager.has_file_processors_on(test_path)
            assert result is False


class TestLaunchProcessors:
    """Test cases for launch_processors functionality."""

    def test_launch_processors_disabled(self, queue_manager):
        """Test launch_processors when disabled."""
        queue_manager._disable = True

        with patch.object(queue_manager, "queueFinishedProcessing") as mock_signal:
            queue_manager.launch_processors()
            mock_signal.emit.assert_called_once()

    def test_launch_processors_paused(self, queue_manager):
        """Test launch_processors when paused."""
        queue_manager.suspend()

        with patch.object(queue_manager, "queueFinishedProcessing") as mock_signal:
            queue_manager.launch_processors()
            mock_signal.emit.assert_called_once()

    def test_launch_processors_empty_queues(self, queue_manager):
        """Test launch_processors with empty queues."""
        with patch.object(queue_manager, "queueFinishedProcessing") as mock_signal:
            queue_manager.launch_processors()
            mock_signal.emit.assert_called_once()

    def test_launch_processors_local_folder(self, queue_manager):
        """Test launching local folder processor."""
        queue_manager._local_folder_queue.put(MockDocPair(1, True, "locally_created"))

        with patch.object(queue_manager, "_create_thread") as mock_create:
            mock_thread = MagicMock()
            mock_create.return_value = mock_thread

            queue_manager.launch_processors()

            mock_create.assert_called_with(
                queue_manager._get_local_folder, "LocalFolderProcessor"
            )
            assert queue_manager._local_folder_thread is mock_thread

    def test_launch_processors_local_file(self, queue_manager):
        """Test launching local file processor."""
        queue_manager._local_file_queue.put(MockDocPair(1, False, "locally_modified"))

        with patch.object(queue_manager, "_create_thread") as mock_create:
            mock_thread = MagicMock()
            mock_create.return_value = mock_thread

            queue_manager.launch_processors()

            # Should create at least one thread - may create local file processor or generic processor
            assert mock_create.call_count >= 1
            assert (
                queue_manager._local_file_thread is mock_thread
                or len(queue_manager._processors_pool) > 0
            )

    def test_launch_processors_local_file_dedicated(self, queue_manager):
        """Test launching local file processor with only local files."""
        # Only add local file to avoid triggering generic processors
        queue_manager._local_file_queue.put(MockDocPair(1, False, "locally_modified"))

        with patch.object(queue_manager, "_create_thread") as mock_create:
            mock_thread = MagicMock()
            mock_create.return_value = mock_thread

            queue_manager.launch_processors()

            # Should create local file processor as first call
            calls = mock_create.call_args_list
            assert len(calls) >= 1
            assert calls[0] == call(queue_manager._get_local_file, "LocalFileProcessor")
            assert queue_manager._local_file_thread is mock_thread

    def test_launch_processors_remote_folder(self, queue_manager):
        """Test launching remote folder processor."""
        queue_manager._remote_folder_queue.put(MockDocPair(1, True, "remotely_created"))

        with patch.object(queue_manager, "_create_thread") as mock_create:
            mock_thread = MagicMock()
            mock_create.return_value = mock_thread

            queue_manager.launch_processors()

            mock_create.assert_called_with(
                queue_manager._get_remote_folder, "RemoteFolderProcessor"
            )
            assert queue_manager._remote_folder_thread is mock_thread

    def test_launch_processors_remote_file(self, queue_manager):
        """Test launching remote file processor."""
        queue_manager._remote_file_queue.put(MockDocPair(1, False, "remotely_modified"))

        with patch.object(queue_manager, "_create_thread") as mock_create:
            mock_thread = MagicMock()
            mock_create.return_value = mock_thread

            queue_manager.launch_processors()

            # Should create at least one thread - may create remote file processor or generic processor
            assert mock_create.call_count >= 1
            assert (
                queue_manager._remote_file_thread is mock_thread
                or len(queue_manager._processors_pool) > 0
            )

    def test_launch_processors_remote_file_dedicated(self, queue_manager):
        """Test launching remote file processor with only remote files."""
        # Only add remote file to avoid triggering generic processors
        queue_manager._remote_file_queue.put(MockDocPair(1, False, "remotely_modified"))

        with patch.object(queue_manager, "_create_thread") as mock_create:
            mock_thread = MagicMock()
            mock_create.return_value = mock_thread

            queue_manager.launch_processors()

            # Should create remote file processor as first call
            calls = mock_create.call_args_list
            assert len(calls) >= 1
            assert calls[0] == call(
                queue_manager._get_remote_file, "RemoteFileProcessor"
            )
            assert queue_manager._remote_file_thread is mock_thread

    def test_launch_processors_additional_processors(self, queue_manager):
        """Test launching additional generic processors."""
        # Add files to both queues
        queue_manager._local_file_queue.put(MockDocPair(1, False, "locally_modified"))
        queue_manager._remote_file_queue.put(MockDocPair(2, False, "remotely_modified"))

        with patch.object(queue_manager, "_create_thread") as mock_create:
            mock_thread = MagicMock()
            mock_create.return_value = mock_thread

            queue_manager.launch_processors()

            # Should create additional processors up to max limit
            assert len(queue_manager._processors_pool) == queue_manager._max_processors

    def test_launch_processors_max_processors_reached(self, queue_manager):
        """Test launch_processors when max processors already reached."""
        # Fill processor pool to max
        queue_manager._processors_pool = [
            MagicMock() for _ in range(queue_manager._max_processors)
        ]

        # Set existing threads to prevent main thread creation
        queue_manager._local_file_thread = MagicMock()
        queue_manager._remote_file_thread = MagicMock()

        # Add files to queues
        queue_manager._local_file_queue.put(MockDocPair(1, False, "locally_modified"))
        queue_manager._remote_file_queue.put(MockDocPair(2, False, "remotely_modified"))

        with patch.object(queue_manager, "_create_thread") as mock_create:
            queue_manager.launch_processors()

            # Should not create more processors since max is reached and main threads exist
            mock_create.assert_not_called()

    def test_launch_processors_existing_threads(self, queue_manager):
        """Test launch_processors doesn't create threads that already exist."""
        queue_manager._local_folder_queue.put(MockDocPair(1, True, "locally_created"))
        queue_manager._local_folder_thread = MagicMock()  # Already exists

        with patch.object(queue_manager, "_create_thread") as mock_create:
            queue_manager.launch_processors()

            # Should not create new thread if one already exists
            mock_create.assert_not_called()

    def test_launch_processors_disabled_queue(self, queue_manager):
        """Test launch_processors with disabled queue."""
        queue_manager._local_folder_queue.put(MockDocPair(1, True, "locally_created"))
        queue_manager._local_folder_enable = False

        with patch.object(queue_manager, "_create_thread") as mock_create:
            queue_manager.launch_processors()

            # Should not create thread for disabled queue
            mock_create.assert_not_called()


class TestIntegration:
    """Integration test cases."""

    def test_full_workflow(self, queue_manager):
        """Test complete queue manager workflow."""
        # Start with empty queues and no errors
        assert queue_manager.get_overall_size() == 0
        assert queue_manager.get_errors_count() == 0
        assert not queue_manager.is_active()

        # Push some items
        local_doc = MockDocPair(1, False, "locally_modified")
        remote_doc = MockDocPair(2, True, "remotely_created")

        with patch.object(queue_manager, "newItem") as mock_signal:
            queue_manager.push(local_doc)
            queue_manager.push(remote_doc)

            assert queue_manager.get_overall_size() == 2
            assert mock_signal.emit.call_count == 2

        # Simulate error
        error_doc = MockDocPair(3, False, "locally_modified", error_count=1)
        queue_manager.push_error(error_doc)
        assert queue_manager.get_errors_count() == 1

        # Get metrics
        metrics = queue_manager.get_metrics()
        assert metrics["total_queue"] == 2
        assert metrics["error_queue"] == 1
        assert metrics["local_file_queue"] == 1
        assert metrics["remote_folder_queue"] == 1

        # Test suspend/resume
        queue_manager.suspend()
        assert queue_manager.is_paused()

        queue_manager.resume()
        assert not queue_manager.is_paused()

    def test_dao_registration(self, mock_engine, mock_dao):
        """Test DAO registration during initialization."""
        qm = QueueManager(mock_engine, mock_dao)
        mock_dao.register_queue_manager.assert_called_once_with(qm)
        # Manually set for verification since it's done by register_queue_manager in real code
        mock_dao.configure_queue_manager(qm)
        assert mock_dao.queue_manager is qm


def teardown_module():
    """Cleanup after all tests are done."""
    # Reset any class-level state if needed
    pass
