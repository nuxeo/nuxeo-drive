"""Tests for nxdrive/drive/engine/queue_manager.py"""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.drive.engine.queue_manager import QueueItem, QueueManager

# ─── QueueItem Tests ─────────────────────────────────────────────────────────


class TestQueueItem:
    def test_construction(self):
        item = QueueItem(42, True, "locally_created")
        assert item.id == 42
        assert item.folderish is True
        assert item.pair_state == "locally_created"

    def test_construction_non_folderish(self):
        item = QueueItem(7, False, "remotely_modified")
        assert item.id == 7
        assert item.folderish is False
        assert item.pair_state == "remotely_modified"

    def test_repr(self):
        item = QueueItem(10, True, "locally_created")
        r = repr(item)
        assert "QueueItem[10]" in r
        assert "folderish=True" in r
        assert "state='locally_created'" in r

    def test_repr_non_folderish(self):
        item = QueueItem(99, False, "remotely_deleted")
        r = repr(item)
        assert "QueueItem[99]" in r
        assert "folderish=False" in r
        assert "state='remotely_deleted'" in r


# ─── QueueManager Fixture ────────────────────────────────────────────────────


@pytest.fixture
def qm():
    with patch("nxdrive.drive.engine.queue_manager.QObject.__init__"):
        with patch("nxdrive.drive.engine.queue_manager.QTimer") as MockTimer:
            timer_inst = MagicMock()
            MockTimer.return_value = timer_inst
            # Signals must be mocked at class level before __init__ uses .connect()
            with patch.object(QueueManager, "newItem", Mock()), patch.object(
                QueueManager, "newError", Mock()
            ), patch.object(QueueManager, "newErrorGiveUp", Mock()), patch.object(
                QueueManager, "queueProcessing", Mock()
            ), patch.object(
                QueueManager, "queueFinishedProcessing", Mock()
            ):
                engine = Mock()
                dao = Mock()
                inst = QueueManager(engine, dao)
                # Replace with fresh mocks on the instance for assertion isolation
                inst.newItem = Mock()
                inst.newError = Mock()
                inst.newErrorGiveUp = Mock()
                inst.queueProcessing = Mock()
                inst.queueFinishedProcessing = Mock()
                return inst


# ─── QueueManager Construction ───────────────────────────────────────────────


class TestQueueManagerConstruction:
    def test_init_attributes(self, qm):
        assert qm.dao is not None
        assert qm._engine is not None
        assert qm._local_folder_enable is True
        assert qm._local_file_enable is True
        assert qm._remote_folder_enable is True
        assert qm._remote_file_enable is True
        assert qm._local_folder_thread is None
        assert qm._local_file_thread is None
        assert qm._remote_folder_thread is None
        assert qm._remote_file_thread is None
        assert qm._error_interval == 60
        assert qm._processors_pool == []

    def test_init_queues_empty(self, qm):
        assert qm._local_folder_queue.empty()
        assert qm._local_file_queue.empty()
        assert qm._remote_file_queue.empty()
        assert qm._remote_folder_queue.empty()

    def test_dao_register_called(self, qm):
        qm.dao.register_queue_manager.assert_called_once_with(qm)

    def test_default_max_processors(self, qm):
        # default max_file_processors=5, so _max_processors = 5 - 2 = 3
        assert qm._max_processors == 3


# ─── push() Tests ────────────────────────────────────────────────────────────


class TestPush:
    def test_push_locally_created_file(self, qm):
        item = QueueItem(1, False, "locally_created")
        qm.push(item)
        assert qm._local_file_queue.qsize() == 1
        assert qm._local_folder_queue.empty()
        qm.newItem.emit.assert_called_once_with(1)

    def test_push_locally_created_folder(self, qm):
        item = QueueItem(2, True, "locally_created")
        qm.push(item)
        assert qm._local_folder_queue.qsize() == 1
        assert qm._local_file_queue.empty()
        qm.newItem.emit.assert_called_once_with(2)

    def test_push_remotely_created_file(self, qm):
        item = QueueItem(3, False, "remotely_created")
        qm.push(item)
        assert qm._remote_file_queue.qsize() == 1
        assert qm._remote_folder_queue.empty()
        qm.newItem.emit.assert_called_once_with(3)

    def test_push_remotely_created_folder(self, qm):
        item = QueueItem(4, True, "remotely_created")
        qm.push(item)
        assert qm._remote_folder_queue.qsize() == 1
        assert qm._remote_file_queue.empty()
        qm.newItem.emit.assert_called_once_with(4)

    def test_push_parent_remotely_folder(self, qm):
        item = QueueItem(5, True, "parent_remotely_created")
        qm.push(item)
        assert qm._remote_folder_queue.qsize() == 1
        qm.newItem.emit.assert_called_once_with(5)

    def test_push_parent_remotely_file(self, qm):
        item = QueueItem(6, False, "parent_remotely_created")
        qm.push(item)
        assert qm._remote_file_queue.qsize() == 1

    def test_push_none_pair_state(self, qm):
        item = QueueItem(7, False, None)
        item.pair_state = None
        qm.push(item)
        # Should be skipped, no queues populated
        assert qm._local_file_queue.empty()
        assert qm._local_folder_queue.empty()
        assert qm._remote_file_queue.empty()
        assert qm._remote_folder_queue.empty()
        qm.newItem.emit.assert_not_called()

    def test_push_deleted_pair_local(self, qm):
        """Locally deleted file should cancel action and go to local file queue."""
        item = QueueItem(8, False, "locally_deleted")
        qm.push(item)
        assert qm._local_file_queue.qsize() == 1
        qm._engine.cancel_action_on.assert_called_once_with(8)
        qm.newItem.emit.assert_called_once_with(8)

    def test_push_deleted_pair_remote(self, qm):
        """Remotely deleted file should cancel action and go to remote file queue."""
        item = QueueItem(9, False, "remotely_deleted")
        qm.push(item)
        assert qm._remote_file_queue.qsize() == 1
        qm._engine.cancel_action_on.assert_called_once_with(9)

    def test_push_deleted_folder_local(self, qm):
        """Locally deleted folder goes to local folder queue, no cancel_action_on."""
        item = QueueItem(10, True, "locally_deleted")
        qm.push(item)
        assert qm._local_folder_queue.qsize() == 1
        qm._engine.cancel_action_on.assert_not_called()

    def test_push_conflicted_pair(self, qm):
        """Conflicted state goes to else branch — not processable."""
        item = QueueItem(11, False, "conflicted")
        qm.push(item)
        assert qm._local_file_queue.empty()
        assert qm._remote_file_queue.empty()
        qm.newItem.emit.assert_not_called()

    def test_push_direct_transfer_file(self, qm):
        """direct_transfer states should go to local file queue."""
        item = QueueItem(12, False, "direct_transfer_replace")
        qm.push(item)
        assert qm._local_file_queue.qsize() == 1
        qm.newItem.emit.assert_called_once_with(12)

    def test_push_direct_transfer_folder(self, qm):
        """direct_transfer states with folderish should go to local folder queue."""
        item = QueueItem(13, True, "direct_transfer_replace")
        qm.push(item)
        assert qm._local_folder_queue.qsize() == 1


# ─── push_ref() Tests ────────────────────────────────────────────────────────


class TestPushRef:
    def test_push_ref_locally_created(self, qm):
        qm.push_ref(20, False, "locally_created")
        assert qm._local_file_queue.qsize() == 1
        qm.newItem.emit.assert_called_once_with(20)

    def test_push_ref_remotely_created_folder(self, qm):
        qm.push_ref(21, True, "remotely_created")
        assert qm._remote_folder_queue.qsize() == 1


# ─── set_max_processors Tests ────────────────────────────────────────────────


class TestSetMaxProcessors:
    def test_normal_value(self, qm):
        qm.set_max_processors(10)
        assert qm._max_processors == 8

    def test_minimum_value(self, qm):
        qm.set_max_processors(1)
        assert qm._max_processors == 0  # min(2) - 2

    def test_exactly_two(self, qm):
        qm.set_max_processors(2)
        assert qm._max_processors == 0

    def test_zero_clamped_to_two(self, qm):
        qm.set_max_processors(0)
        assert qm._max_processors == 0

    def test_negative_clamped_to_two(self, qm):
        qm.set_max_processors(-5)
        assert qm._max_processors == 0


# ─── resume / suspend / is_paused ────────────────────────────────────────────


class TestResumeSuspendPaused:
    def test_initial_not_paused(self, qm):
        assert qm.is_paused() is False

    def test_suspend_pauses(self, qm):
        qm.suspend()
        assert qm.is_paused() is True
        assert qm._local_file_enable is False
        assert qm._local_folder_enable is False
        assert qm._remote_file_enable is False
        assert qm._remote_folder_enable is False

    def test_resume_unpauses(self, qm):
        qm.suspend()
        assert qm.is_paused() is True
        qm.resume()
        assert qm.is_paused() is False
        assert qm._local_file_enable is True
        assert qm._local_folder_enable is True
        assert qm._remote_file_enable is True
        assert qm._remote_folder_enable is True
        qm.queueProcessing.emit.assert_called()

    def test_suspend_quits_running_threads(self, qm):
        qm._local_file_thread = Mock()
        qm._local_folder_thread = Mock()
        qm._remote_file_thread = Mock()
        qm._remote_folder_thread = Mock()
        qm.suspend()
        qm._local_file_thread.quit.assert_called_once()
        qm._local_folder_thread.quit.assert_called_once()
        qm._remote_file_thread.quit.assert_called_once()
        qm._remote_folder_thread.quit.assert_called_once()


# ─── enable_*_queue Tests ────────────────────────────────────────────────────


class TestEnableQueues:
    def test_enable_local_file_queue_true(self, qm):
        qm._local_file_enable = False
        qm.enable_local_file_queue(True)
        assert qm._local_file_enable is True
        qm.queueProcessing.emit.assert_called()

    def test_enable_local_file_queue_false(self, qm):
        qm.enable_local_file_queue(False)
        assert qm._local_file_enable is False

    def test_enable_local_file_queue_false_quits_thread(self, qm):
        qm._local_file_thread = Mock()
        qm.enable_local_file_queue(False)
        qm._local_file_thread.quit.assert_called_once()

    def test_enable_local_file_queue_true_no_emit(self, qm):
        qm.enable_local_file_queue(True, emit=False)
        assert qm._local_file_enable is True
        qm.queueProcessing.emit.assert_not_called()

    def test_enable_local_folder_queue_true(self, qm):
        qm.enable_local_folder_queue(True)
        assert qm._local_folder_enable is True
        qm.queueProcessing.emit.assert_called()

    def test_enable_local_folder_queue_false_quits_thread(self, qm):
        qm._local_folder_thread = Mock()
        qm.enable_local_folder_queue(False)
        qm._local_folder_thread.quit.assert_called_once()

    def test_enable_remote_file_queue_true(self, qm):
        qm.enable_remote_file_queue(True)
        assert qm._remote_file_enable is True
        qm.queueProcessing.emit.assert_called()

    def test_enable_remote_file_queue_false_quits_thread(self, qm):
        qm._remote_file_thread = Mock()
        qm.enable_remote_file_queue(False)
        qm._remote_file_thread.quit.assert_called_once()

    def test_enable_remote_folder_queue_true(self, qm):
        qm.enable_remote_folder_queue(True)
        assert qm._remote_folder_enable is True
        qm.queueProcessing.emit.assert_called()

    def test_enable_remote_folder_queue_false_quits_thread(self, qm):
        qm._remote_folder_thread = Mock()
        qm.enable_remote_folder_queue(False)
        qm._remote_folder_thread.quit.assert_called_once()


# ─── get_metrics / get_overall_size ──────────────────────────────────────────


class TestMetrics:
    def test_get_metrics_empty(self, qm):
        metrics = qm.get_metrics()
        assert metrics["local_folder_queue"] == 0
        assert metrics["local_file_queue"] == 0
        assert metrics["remote_folder_queue"] == 0
        assert metrics["remote_file_queue"] == 0
        assert metrics["total_queue"] == 0
        assert metrics["error_queue"] == 0
        assert metrics["is_paused"] is False
        assert metrics["local_file_thread"] is False
        assert metrics["local_folder_thread"] is False
        assert metrics["remote_file_thread"] is False
        assert metrics["remote_folder_thread"] is False
        assert metrics["additional_processors"] == 0

    def test_get_metrics_with_items(self, qm):
        qm._local_file_queue.put(QueueItem(1, False, "locally_created"))
        qm._remote_folder_queue.put(QueueItem(2, True, "remotely_created"))
        metrics = qm.get_metrics()
        assert metrics["local_file_queue"] == 1
        assert metrics["remote_folder_queue"] == 1
        assert metrics["total_queue"] == 2

    def test_get_metrics_with_threads(self, qm):
        qm._local_file_thread = Mock()
        metrics = qm.get_metrics()
        assert metrics["local_file_thread"] is True

    def test_get_overall_size_empty(self, qm):
        assert qm.get_overall_size() == 0

    def test_get_overall_size_with_items(self, qm):
        qm._local_file_queue.put(QueueItem(1, False, "locally_created"))
        qm._local_folder_queue.put(QueueItem(2, True, "locally_created"))
        qm._remote_file_queue.put(QueueItem(3, False, "remotely_created"))
        qm._remote_folder_queue.put(QueueItem(4, True, "remotely_created"))
        assert qm.get_overall_size() == 4


# ─── push_error Tests ────────────────────────────────────────────────────────


def _make_doc_pair(
    row_id=1,
    error_count=1,
    pair_state="locally_created",
    folderish=False,
    error_next_try=0,
):
    """Create a mock DocPair with the necessary attributes."""
    doc = Mock()
    doc.id = row_id
    doc.error_count = error_count
    doc.pair_state = pair_state
    doc.folderish = folderish
    doc.error_next_try = error_next_try
    return doc


class TestPushError:
    def test_push_error_normal(self, qm):
        doc = _make_doc_pair(row_id=100, error_count=1)
        qm.push_error(doc)
        assert 100 in qm._on_error_queue
        assert qm._on_error_queue[100] is doc
        qm.newError.emit.assert_called_once_with(100)

    def test_push_error_sets_error_next_try(self, qm):
        doc = _make_doc_pair(row_id=101, error_count=2)
        before = int(time.time())
        qm.push_error(doc)
        after = int(time.time())
        # interval = 60 * error_count = 120
        assert doc.error_next_try >= before + 120
        assert doc.error_next_try <= after + 120

    def test_push_error_exceeded_threshold_gives_up(self, qm):
        doc = _make_doc_pair(row_id=102, error_count=qm._error_threshold + 1)
        qm.push_error(doc)
        qm.newErrorGiveUp.emit.assert_called_once_with(102)
        assert 102 not in qm._on_error_queue

    def test_push_error_at_threshold_not_gives_up(self, qm):
        doc = _make_doc_pair(row_id=103, error_count=qm._error_threshold)
        qm.push_error(doc)
        qm.newErrorGiveUp.emit.assert_not_called()
        assert 103 in qm._on_error_queue

    @patch("nxdrive.drive.engine.queue_manager.WINDOWS", True)
    def test_push_error_windows_permission_error(self, qm):
        doc = _make_doc_pair(row_id=104, error_count=5)
        exc = PermissionError("access denied")
        exc.winerror = 32
        exc.strerror = "The process cannot access the file"
        qm.push_error(doc, exception=exc)
        # error_count is overridden to 1 for Windows PermissionError
        # so interval = 60 * 1 = 60
        assert 104 in qm._on_error_queue

    def test_push_error_interval_override(self, qm):
        doc = _make_doc_pair(row_id=105, error_count=1)
        before = int(time.time())
        qm.push_error(doc, interval=30)
        assert doc.error_next_try >= before + 30
        assert doc.error_next_try <= int(time.time()) + 30

    def test_push_error_duplicate_no_double_emit(self, qm):
        """Second push_error for the same doc_pair.id should not emit newError."""
        doc = _make_doc_pair(row_id=106, error_count=1)
        qm._on_error_queue[106] = doc
        qm.push_error(doc)
        qm.newError.emit.assert_not_called()

    def test_push_error_remote_ongoing_request(self, qm):
        """RemoteOngoingRequestError should not emit newError signal."""
        from nxdrive.drive.exceptions import RemoteOngoingRequestError

        doc = _make_doc_pair(row_id=107, error_count=1)
        exc = RemoteOngoingRequestError()
        qm.push_error(doc, exception=exc)
        # emit_sig is set to False, so newError should not be called
        qm.newError.emit.assert_not_called()


# ─── _is_on_error Tests ──────────────────────────────────────────────────────


class TestIsOnError:
    def test_not_on_error(self, qm):
        assert qm._is_on_error(999) is False

    def test_on_error(self, qm):
        doc = _make_doc_pair(row_id=200)
        qm._on_error_queue[200] = doc
        assert qm._is_on_error(200) is True


# ─── get_errors_count / get_error_threshold ──────────────────────────────────


class TestErrorCounts:
    def test_get_errors_count_empty(self, qm):
        assert qm.get_errors_count() == 0

    def test_get_errors_count_with_errors(self, qm):
        qm._on_error_queue[1] = _make_doc_pair(row_id=1)
        qm._on_error_queue[2] = _make_doc_pair(row_id=2)
        assert qm.get_errors_count() == 2

    def test_get_error_threshold(self, qm):
        assert qm.get_error_threshold() == qm._error_threshold


# ─── _get_file Tests ─────────────────────────────────────────────────────────


class TestGetFile:
    def test_get_file_empty_queues(self, qm):
        assert qm._get_file() is None

    def test_get_file_remote_bigger(self, qm):
        # Put 2 items in remote, 1 in local
        remote_item = QueueItem(10, False, "remotely_created")
        qm._remote_file_queue.put(remote_item)
        qm._remote_file_queue.put(QueueItem(11, False, "remotely_modified"))
        qm._local_file_queue.put(QueueItem(20, False, "locally_created"))
        result = qm._get_file()
        assert result is not None
        assert result.id == 10  # remote was bigger, so remote file taken

    def test_get_file_local_bigger(self, qm):
        # Put 2 items in local, 1 in remote
        qm._local_file_queue.put(QueueItem(20, False, "locally_created"))
        qm._local_file_queue.put(QueueItem(21, False, "locally_modified"))
        qm._remote_file_queue.put(QueueItem(10, False, "remotely_created"))
        result = qm._get_file()
        assert result is not None
        assert result.id == 20  # local was bigger, so local file taken

    def test_get_file_equal_sizes_returns_local(self, qm):
        # Equal sizes — local is returned (not strictly greater for remote)
        qm._local_file_queue.put(QueueItem(20, False, "locally_created"))
        qm._remote_file_queue.put(QueueItem(10, False, "remotely_created"))
        result = qm._get_file()
        assert result is not None
        assert result.id == 20

    def test_get_file_skips_on_error(self, qm):
        """Items on error should be skipped."""
        item = QueueItem(30, False, "locally_created")
        qm._local_file_queue.put(item)
        qm._on_error_queue[30] = _make_doc_pair(row_id=30)
        # Only one item, and it's on error, should recurse and return None
        result = qm._get_file()
        assert result is None

    def test_get_file_only_remote(self, qm):
        qm._remote_file_queue.put(QueueItem(40, False, "remotely_created"))
        result = qm._get_file()
        assert result is not None
        assert result.id == 40

    def test_get_file_only_local(self, qm):
        qm._local_file_queue.put(QueueItem(50, False, "locally_created"))
        result = qm._get_file()
        assert result is not None
        assert result.id == 50
