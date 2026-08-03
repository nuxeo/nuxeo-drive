"""Extra unit tests for nxdrive.nuxeo.engine.processor — methods not yet covered."""

import errno
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.drive.constants import TransferStatus
from nxdrive.drive.exceptions import (
    NotFound,
    UploadCancelled,
    UploadPaused,
)


def _make_processor():
    from nxdrive.nuxeo.engine.processor import Processor

    with patch.object(Processor, "__init__", return_value=None):
        p = Processor.__new__(Processor)
    p.engine = MagicMock()
    p.engine.uid = "eng-1"
    p.dao = MagicMock()
    p.local = MagicMock()
    p.remote = MagicMock()
    p.thread_id = 1
    p._current_doc_pair = None
    p._current_metrics = {}
    # Reset class-level state
    Processor = type(p)
    Processor.soft_locks = {}
    Processor.readonly_locks = {}
    return p


def _mock_doc_pair(**kwargs):
    pair = Mock()
    defaults = dict(
        id=1,
        pair_state="locally_modified",
        local_state="synchronized",
        remote_state="modified",
        remote_ref="ref-123",
        local_path=Path("folder/file.txt"),
        local_parent_path=Path("folder"),
        remote_parent_ref="parent-ref",
        remote_parent_path="/default-domain",
        folderish=False,
        remote_digest="abc123",
        local_digest="abc123",
        remote_name="file.txt",
        local_name="file.txt",
        remote_can_rename=True,
        remote_can_update=True,
        error_count=0,
        version=1,
        session=0,
        size=1024,
        last_error=None,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(pair, k, v)
    return pair


# ---------------------------------------------------------------------------
# _handle_doc_pair_dt
# ---------------------------------------------------------------------------


def _handler(side_effect=None):
    """Create a Mock with __name__ set (required by processor logging)."""
    h = Mock(side_effect=side_effect)
    h.__name__ = "test_handler"
    return h


class TestHandleDocPairDt:
    def test_calls_sync_handler(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        handler = _handler()

        proc._handle_doc_pair_dt(pair, handler)

        handler.assert_called_once_with(pair)

    def test_not_found_cancels_transfer(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        handler = _handler(side_effect=NotFound("gone"))

        with pytest.raises(NotFound):
            proc._handle_doc_pair_dt(pair, handler)

        proc._direct_transfer_cancel = Mock()
        # Re-test with the mock to verify cancel is called
        proc2 = _make_processor()
        proc2._direct_transfer_cancel = Mock()
        proc2._postpone_pair = Mock()
        with pytest.raises(NotFound):
            proc2._handle_doc_pair_dt(pair, _handler(side_effect=NotFound("gone")))
        proc2._direct_transfer_cancel.assert_called_once_with(pair)

    def test_http_error_404_postpones(self):
        from nuxeo.exceptions import HTTPError

        proc = _make_processor()
        proc._postpone_pair = Mock()
        pair = _mock_doc_pair()
        handler = _handler(side_effect=HTTPError(status=404, message="not found"))

        proc._handle_doc_pair_dt(pair, handler)

        proc._postpone_pair.assert_called_once_with(pair, "Parent not yet synced")

    def test_http_error_non_404_raises(self):
        from nuxeo.exceptions import HTTPError

        proc = _make_processor()
        pair = _mock_doc_pair()
        handler = _handler(side_effect=HTTPError(status=500, message="server error"))

        with pytest.raises(HTTPError):
            proc._handle_doc_pair_dt(pair, handler)

    def test_upload_cancelled_handles_gracefully(self):
        proc = _make_processor()
        proc._direct_transfer_cancel = Mock()
        pair = _mock_doc_pair()
        upload_mock = Mock()
        upload_mock.doc_pair = pair.id
        upload_mock.batch = {"batchId": "b1"}
        proc.engine.dao.get_dt_upload.return_value = upload_mock
        proc.engine.dao.get_state_from_id.return_value = pair

        handler = _handler(side_effect=UploadCancelled(42))
        proc._handle_doc_pair_dt(pair, handler)

        proc.remote.cancel_batch.assert_called_once_with(upload_mock.batch)
        proc._direct_transfer_cancel.assert_called_once_with(pair)

    def test_upload_cancelled_no_upload_returns(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        proc.engine.dao.get_dt_upload.return_value = None

        handler = _handler(side_effect=UploadCancelled(42))
        proc._handle_doc_pair_dt(pair, handler)
        # Should not raise

    def test_upload_paused_reraises(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        handler = _handler(side_effect=UploadPaused(99))

        with pytest.raises(UploadPaused):
            proc._handle_doc_pair_dt(pair, handler)

    def test_generic_exception_emits_error_signal(self):
        proc = _make_processor()
        pair = _mock_doc_pair(local_path=Path("folder/file.txt"))
        handler = _handler(side_effect=ValueError("boom"))

        with patch("nxdrive.nuxeo.engine.processor.WINDOWS", False):
            with pytest.raises(ValueError):
                proc._handle_doc_pair_dt(pair, handler)

        proc.engine.directTranferError.emit.assert_called_once()


# ---------------------------------------------------------------------------
# _get_next_doc_pair
# ---------------------------------------------------------------------------


class TestGetNextDocPair:
    def test_success(self):
        proc = _make_processor()
        item = _mock_doc_pair(id=5)
        proc.dao.acquire_state.return_value = _mock_doc_pair(id=5)

        result = proc._get_next_doc_pair(item)

        proc.dao.acquire_state.assert_called_once_with(proc.thread_id, 5)
        assert result is not None

    def test_operational_error_windows_locally_moved_no_rename(self):
        proc = _make_processor()
        proc._postpone_pair = Mock()
        item = _mock_doc_pair(id=7)
        proc.dao.acquire_state.side_effect = sqlite3.OperationalError("locked")
        state = _mock_doc_pair(
            id=7, pair_state="locally_moved", remote_can_rename=False
        )
        proc.dao.get_state_from_id.return_value = state

        with patch("nxdrive.nuxeo.engine.processor.WINDOWS", True):
            result = proc._get_next_doc_pair(item)

        assert result is None
        # Should NOT postpone for this special Windows case
        proc._postpone_pair.assert_not_called()

    def test_operational_error_generic_postpones(self):
        proc = _make_processor()
        proc._postpone_pair = Mock()
        item = _mock_doc_pair(id=7)
        proc.dao.acquire_state.side_effect = sqlite3.OperationalError("locked")
        state = _mock_doc_pair(
            id=7, pair_state="locally_modified", remote_can_rename=True
        )
        proc.dao.get_state_from_id.return_value = state

        with patch("nxdrive.nuxeo.engine.processor.WINDOWS", False):
            result = proc._get_next_doc_pair(item)

        assert result is None
        proc._postpone_pair.assert_called_once()

    def test_operational_error_no_state(self):
        proc = _make_processor()
        item = _mock_doc_pair(id=7)
        proc.dao.acquire_state.side_effect = sqlite3.OperationalError("locked")
        proc.dao.get_state_from_id.return_value = None

        result = proc._get_next_doc_pair(item)
        assert result is None


# ---------------------------------------------------------------------------
# _check_exists_on_the_server
# ---------------------------------------------------------------------------


class TestCheckExistsOnTheServer:
    def test_non_locally_created_postpones(self):
        proc = _make_processor()
        proc._postpone_pair = Mock()
        pair = _mock_doc_pair(pair_state="locally_modified")

        proc._check_exists_on_the_server(pair)

        proc._postpone_pair.assert_called_once_with(pair, "Server unavailable")

    def test_locally_created_doc_found_syncs(self):
        proc = _make_processor()
        proc._postpone_pair = Mock()
        proc._refresh_remote = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncEnded = MagicMock()
        pair = _mock_doc_pair(
            pair_state="locally_created", local_path=Path("ws/file.txt")
        )

        remote_info = Mock()
        remote_info.path = "default#default/defaultFileSystemItemFactory#default#uid123"
        remote_info.name = "file.txt"

        proc.remote.fetch.return_value = {"uid": "uid123"}
        proc.remote.get_fs_info.return_value = remote_info

        with patch("nxdrive.nuxeo.engine.processor.WINDOWS", False):
            proc._check_exists_on_the_server(pair)

        proc.dao.synchronize_state.assert_called_once_with(pair)
        proc.dao.update_last_transfer.assert_called_once()
        proc.remove_void_transfers.assert_called_once_with(pair)

    def test_locally_created_fetch_error_no_action(self):
        proc = _make_processor()
        proc._postpone_pair = Mock()
        pair = _mock_doc_pair(
            pair_state="locally_created", local_path=Path("ws/file.txt")
        )
        proc.remote.fetch.side_effect = Exception("network error")

        with patch("nxdrive.nuxeo.engine.processor.WINDOWS", False):
            proc._check_exists_on_the_server(pair)

        # No sync, no postpone (for locally_created)
        proc.dao.synchronize_state.assert_not_called()
        proc._postpone_pair.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_pair_handler_exception
# ---------------------------------------------------------------------------


class TestHandlePairHandlerException:
    def test_os_error_no_space(self):
        proc = _make_processor()
        proc.increase_error = Mock()
        pair = _mock_doc_pair()
        exc = OSError(errno.ENOSPC, "No space left")

        proc._handle_pair_handler_exception(pair, "handler", exc)

        proc.engine.suspend.assert_called_once()
        proc.increase_error.assert_called_once_with(pair, "NO_SPACE_LEFT_ON_DEVICE")
        proc.engine.noSpaceLeftOnDevice.emit.assert_called_once()

    def test_generic_exception_increases_error(self):
        proc = _make_processor()
        proc.increase_error = Mock()
        pair = _mock_doc_pair()
        exc = RuntimeError("unknown")

        proc._handle_pair_handler_exception(pair, "my_handler", exc)

        proc.increase_error.assert_called_once_with(
            pair, "SYNC_HANDLER_my_handler", exception=exc
        )


# ---------------------------------------------------------------------------
# _synchronize_direct_transfer
# ---------------------------------------------------------------------------


class TestSynchronizeDirectTransfer:
    def test_session_paused_skips(self):
        proc = _make_processor()
        pair = _mock_doc_pair(session=1)
        session = Mock()
        session.status = TransferStatus.PAUSED
        proc.dao.get_session.return_value = session

        proc._synchronize_direct_transfer(pair)

        proc.remote.upload.assert_not_called()

    def test_path_not_exists_with_session_pauses(self):
        proc = _make_processor()
        proc._direct_transfer_cancel = Mock()
        pair = _mock_doc_pair(session=1, local_path=Path("missing/file.txt"))
        session = Mock()
        session.status = TransferStatus.ONGOING
        session.uid = 1
        proc.dao.get_session.return_value = session

        with patch("nxdrive.nuxeo.engine.processor.WINDOWS", False):
            with patch.object(Path, "exists", return_value=False):
                proc._synchronize_direct_transfer(pair)

        proc.dao.pause_session.assert_called_once_with(1)
        proc.remote.upload.assert_not_called()

    def test_path_not_exists_no_session_cancels(self):
        proc = _make_processor()
        proc._direct_transfer_cancel = Mock()
        pair = _mock_doc_pair(session=0, local_path=Path("missing/file.txt"))
        proc.dao.get_session.return_value = None

        with patch("nxdrive.nuxeo.engine.processor.WINDOWS", False):
            with patch.object(Path, "exists", return_value=False):
                proc._synchronize_direct_transfer(pair)

        proc._direct_transfer_cancel.assert_called_once_with(pair)

    def test_success_uploads_and_ends(self):
        proc = _make_processor()
        proc._direct_transfer_end = Mock()
        pair = _mock_doc_pair(session=1, local_path=Path("folder/file.txt"))
        session = Mock()
        session.status = TransferStatus.ONGOING
        proc.dao.get_session.return_value = session

        with patch("nxdrive.nuxeo.engine.processor.WINDOWS", False):
            with patch.object(Path, "exists", return_value=True):
                proc._synchronize_direct_transfer(pair)

        proc.remote.upload.assert_called_once()
        proc._direct_transfer_end.assert_called_once_with(pair, False)


# ---------------------------------------------------------------------------
# _direct_transfer_end
# ---------------------------------------------------------------------------


class TestDirectTransferEnd:
    def test_not_cancelled_updates_session(self):
        proc = _make_processor()
        pair = _mock_doc_pair(session=5, folderish=False, size=1024)
        session = Mock()
        session.status = TransferStatus.ONGOING
        proc.dao.get_session.return_value = session
        proc.dao.update_session.return_value = session
        proc.engine.handle_session_status = Mock()

        proc._direct_transfer_end(pair, False)

        proc.dao.remove_transfer.assert_called_once_with(
            "upload", doc_pair=pair.id, is_direct_transfer=True
        )
        proc.dao.remove_state.assert_called_once_with(pair, recursive=False)
        proc.dao.update_session.assert_called_once_with(5)
        proc.engine.handle_session_status.assert_called_once_with(session)

    def test_cancelled_decreases_session_counts(self):
        proc = _make_processor()
        pair = _mock_doc_pair(session=5, folderish=True, size=2048)
        session = Mock()
        session.status = TransferStatus.ONGOING
        proc.dao.get_session.return_value = session
        proc.dao.decrease_session_counts.return_value = session
        proc.engine.handle_session_status = Mock()

        proc._direct_transfer_end(pair, True)

        proc.dao.decrease_session_counts.assert_called_once_with(5)
        proc.engine.handle_session_status.assert_called_once_with(session)

    def test_no_session(self):
        proc = _make_processor()
        pair = _mock_doc_pair(session=0, folderish=False, size=512)
        proc.dao.get_session.return_value = None
        proc.engine.handle_session_status = Mock()

        proc._direct_transfer_end(pair, False)

        proc.dao.remove_transfer.assert_called_once()
        proc.dao.remove_state.assert_called_once()
        proc.engine.handle_session_status.assert_not_called()


# ---------------------------------------------------------------------------
# _synchronize_conflicted
# ---------------------------------------------------------------------------


class TestSynchronizeConflicted:
    def test_moved_and_moved_sets_conflict(self):
        proc = _make_processor()
        pair = _mock_doc_pair(local_state="moved", remote_state="moved")

        proc._synchronize_conflicted(pair)

        proc.dao.set_conflict_state.assert_called_once_with(pair)

    def test_moved_and_unknown_sets_conflict(self):
        proc = _make_processor()
        pair = _mock_doc_pair(local_state="moved", remote_state="unknown")

        proc._synchronize_conflicted(pair)

        proc.dao.set_conflict_state.assert_called_once_with(pair)

    def test_file_same_digest_auto_resolves(self):
        proc = _make_processor()
        pair = _mock_doc_pair(
            local_state="modified",
            remote_state="modified",
            folderish=False,
            local_digest="aaa",
            remote_digest="aaa",
            local_path=Path("folder/file.txt"),
        )
        proc.local.is_equal_digests.return_value = True

        proc._synchronize_conflicted(pair)

        proc.dao.synchronize_state.assert_called_once_with(pair)

    def test_file_different_digest_no_resolve(self):
        proc = _make_processor()
        pair = _mock_doc_pair(
            local_state="modified",
            remote_state="modified",
            folderish=False,
            local_digest="aaa",
            remote_digest="bbb",
            local_path=Path("folder/file.txt"),
        )
        proc.local.is_equal_digests.return_value = False

        proc._synchronize_conflicted(pair)

        proc.dao.synchronize_state.assert_not_called()
        proc.dao.set_conflict_state.assert_not_called()

    def test_folder_same_remote_uid_auto_resolves(self):
        proc = _make_processor()
        pair = _mock_doc_pair(
            local_state="modified",
            remote_state="modified",
            folderish=True,
            remote_ref="uid-123",
            local_path=Path("folder"),
        )
        proc.local.get_remote_id.return_value = "uid-123"

        proc._synchronize_conflicted(pair)

        proc.dao.synchronize_state.assert_called_once_with(pair)

    def test_folder_different_remote_uid_no_resolve(self):
        proc = _make_processor()
        pair = _mock_doc_pair(
            local_state="modified",
            remote_state="modified",
            folderish=True,
            remote_ref="uid-123",
            local_path=Path("folder"),
        )
        proc.local.get_remote_id.return_value = "uid-456"

        proc._synchronize_conflicted(pair)

        proc.dao.synchronize_state.assert_not_called()


# ---------------------------------------------------------------------------
# _synchronize_if_not_remotely_dirty
# ---------------------------------------------------------------------------


class TestSynchronizeIfNotRemotelyDirty:
    def test_remote_info_name_differs_forces_modified(self):
        proc = _make_processor()
        proc._synchronize_remotely_modified = Mock()
        pair = _mock_doc_pair(
            local_path=Path("f.txt"), local_name="f.txt", local_digest="d1"
        )
        remote_info = Mock(name="other.txt", digest="d1")
        # Mock name attribute explicitly
        remote_info.name = "other.txt"
        remote_info.digest = "d1"
        modified = _mock_doc_pair()
        proc.dao.get_state_from_local.return_value = modified

        proc._synchronize_if_not_remotely_dirty(pair, remote_info=remote_info)

        proc._synchronize_remotely_modified.assert_called_once_with(modified)

    def test_remote_info_none_synchronizes(self):
        proc = _make_processor()
        pair = _mock_doc_pair(folderish=True, local_path=Path("folder"))

        proc._synchronize_if_not_remotely_dirty(pair, remote_info=None)

        proc.dao.synchronize_state.assert_called_once()

    def test_folderish_synchronizes_directly(self):
        proc = _make_processor()
        pair = _mock_doc_pair(
            folderish=True,
            local_path=Path("folder"),
            remote_digest=None,
        )

        proc._synchronize_if_not_remotely_dirty(pair, remote_info=None)

        proc.dao.synchronize_state.assert_called_once_with(pair, dynamic_states=False)


# ---------------------------------------------------------------------------
# _direct_transfer_cancel
# ---------------------------------------------------------------------------


class TestDirectTransferCancel:
    def test_calls_end_with_cancelled_and_recursive(self):
        proc = _make_processor()
        proc._direct_transfer_end = Mock()
        pair = _mock_doc_pair()

        proc._direct_transfer_cancel(pair)

        proc._direct_transfer_end.assert_called_once_with(pair, True, recursive=True)


# ---------------------------------------------------------------------------
# _unlock_readonly / _lock_readonly
# ---------------------------------------------------------------------------


class TestReadonlyLocks:
    def test_unlock_readonly_new_lock(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = _make_processor()
        Processor.readonly_locks = {}
        proc.local.unlock_ref.return_value = 0o644

        proc._unlock_readonly(Path("/tmp/file.txt"))

        assert proc.engine.uid in Processor.readonly_locks
        assert Path("/tmp/file.txt") in Processor.readonly_locks[proc.engine.uid]
        assert Processor.readonly_locks[proc.engine.uid][Path("/tmp/file.txt")] == [
            1,
            0o644,
        ]

    def test_unlock_readonly_increment_count(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = _make_processor()
        Processor.readonly_locks = {proc.engine.uid: {Path("/tmp/file.txt"): [1, 0o644]}}

        proc._unlock_readonly(Path("/tmp/file.txt"))

        assert Processor.readonly_locks[proc.engine.uid][Path("/tmp/file.txt")][0] == 2

    def test_lock_readonly_relocks(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = _make_processor()
        Processor.readonly_locks = {proc.engine.uid: {Path("/tmp/file.txt"): [1, 0o644]}}

        proc._lock_readonly(Path("/tmp/file.txt"))

        # Count decremented to 0, should relock and remove entry
        proc.local.lock_ref.assert_called_once_with(Path("/tmp/file.txt"), 0o644)
        assert Path("/tmp/file.txt") not in Processor.readonly_locks[proc.engine.uid]

    def test_lock_readonly_decrements_count(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = _make_processor()
        Processor.readonly_locks = {proc.engine.uid: {Path("/tmp/file.txt"): [2, 0o644]}}

        proc._lock_readonly(Path("/tmp/file.txt"))

        # Count should be 1, not relocked yet
        assert Processor.readonly_locks[proc.engine.uid][Path("/tmp/file.txt")][0] == 1
        proc.local.lock_ref.assert_not_called()

    def test_lock_readonly_not_found(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = _make_processor()
        Processor.readonly_locks = {}

        # Should not raise
        proc._lock_readonly(Path("/tmp/missing.txt"))


# ---------------------------------------------------------------------------
# _lock_soft_path
# ---------------------------------------------------------------------------


class TestLockSoftPath:
    def test_lock_and_unlock(self):
        from nxdrive.nuxeo.engine.processor import Processor

        proc = _make_processor()
        Processor.soft_locks = {}

        result = proc._lock_soft_path(Path("/TMP/File.txt"))
        assert result == Path("/tmp/file.txt")

        proc._unlock_soft_path(Path("/TMP/File.txt"))
        assert Path("/tmp/file.txt") not in Processor.soft_locks.get(
            proc.engine.uid, {}
        )

    def test_double_lock_raises(self):
        from nxdrive.drive.exceptions import PairInterrupt
        from nxdrive.nuxeo.engine.processor import Processor

        proc = _make_processor()
        Processor.soft_locks = {}

        proc._lock_soft_path(Path("/tmp/file.txt"))
        with pytest.raises(PairInterrupt):
            proc._lock_soft_path(Path("/tmp/file.txt"))


# ---------------------------------------------------------------------------
# _execute exception branches
# ---------------------------------------------------------------------------


class TestExecuteExceptionBranches:
    """Cover the many exception handlers in _execute()."""

    def _setup_execute(self, proc, pair, exc_class, **exc_kwargs):
        """Set up a processor for _execute testing with a given exception."""
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.pairSyncEnded = MagicMock()
        proc.increase_error = Mock()
        proc.giveup_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_pair_handler_exception = Mock()
        proc._handle_doc_pair_sync = Mock(side_effect=exc_class(**exc_kwargs))
        proc._handle_doc_pair_dt = Mock()
        return proc

    def test_unauthorized_gives_up(self):
        from nuxeo.exceptions import Unauthorized

        proc = _make_processor()
        pair = _mock_doc_pair()
        self._setup_execute(proc, pair, Unauthorized)
        proc._execute()
        proc.giveup_error.assert_called_once_with(pair, "INVALID_CREDENTIALS")

    def test_forbidden_logs_warning(self):
        from nuxeo.exceptions import Forbidden

        proc = _make_processor()
        pair = _mock_doc_pair()
        self._setup_execute(proc, pair, Forbidden)
        proc._execute()
        # Should not raise, just log

    def test_pair_interrupt_requeues(self):
        from nxdrive.drive.exceptions import PairInterrupt

        proc = _make_processor()
        pair = _mock_doc_pair()
        self._setup_execute(proc, pair, PairInterrupt)
        with patch("nxdrive.nuxeo.engine.processor.sleep"):
            proc._execute()
        proc.engine.queue_manager.push.assert_called_once_with(pair)

    def test_parent_not_synced_requeues(self):
        from nxdrive.drive.exceptions import ParentNotSynced

        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(
            side_effect=ParentNotSynced("child", "parent")
        )
        with patch("nxdrive.nuxeo.engine.processor.sleep"):
            proc._execute()
        proc.engine.queue_manager.push.assert_called_once_with(pair)

    def test_connection_error_postpones(self):
        from requests.exceptions import ConnectionError as RequestsConnectionError

        proc = _make_processor()
        pair = _mock_doc_pair()
        self._setup_execute(proc, pair, RequestsConnectionError)
        proc._execute()
        proc._postpone_pair.assert_called_once_with(pair, "CONNECTION_ERROR")

    def test_max_retry_error_postpones(self):
        from urllib3.exceptions import MaxRetryError

        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(
            side_effect=MaxRetryError(None, None, "max retries")
        )
        proc._execute()
        proc._postpone_pair.assert_called_once_with(pair, "MAX_RETRY_ERROR")

    def test_conflict_postpones(self):
        from nuxeo.exceptions import Conflict

        proc = _make_processor()
        pair = _mock_doc_pair()
        self._setup_execute(proc, pair, Conflict)
        proc._execute()
        proc._postpone_pair.assert_called_once_with(pair, "Conflict")

    def test_http_error_404_removes_state(self):
        from nuxeo.exceptions import HTTPError

        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(
            side_effect=HTTPError(status=404, message="not found")
        )
        proc._execute()
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_http_error_416_cleans_temp(self):
        import shutil

        from nuxeo.exceptions import HTTPError

        proc = _make_processor()
        proc.engine.download_dir = Path("/tmp/downloads")
        pair = _mock_doc_pair(remote_ref="default#abc123")
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(
            side_effect=HTTPError(status=416, message="range")
        )
        with patch("nxdrive.nuxeo.engine.processor.shutil.rmtree"):
            proc._execute()
        proc._postpone_pair.assert_called_once()

    def test_http_error_500_increases_error(self):
        from nuxeo.exceptions import HTTPError

        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(
            side_effect=HTTPError(status=500, message="server error")
        )
        proc._execute()
        proc.increase_error.assert_called_once()

    def test_http_error_503_checks_server(self):
        from nuxeo.exceptions import HTTPError

        proc = _make_processor()
        proc._check_exists_on_the_server = Mock()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(
            side_effect=HTTPError(status=503, message="unavailable")
        )
        proc._execute()
        proc._check_exists_on_the_server.assert_called_once_with(pair)

    def test_upload_error_postpones(self):
        from nuxeo.exceptions import UploadError

        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        exc = UploadError("file.txt", info="some error info")
        proc._handle_doc_pair_sync = Mock(side_effect=exc)
        proc._execute()
        proc._postpone_pair.assert_called_once()

    def test_upload_error_expired_token_removes_upload(self):
        from nuxeo.exceptions import UploadError

        proc = _make_processor()
        pair = _mock_doc_pair(local_state="direct")
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        exc = UploadError("file.txt", info="ExpiredToken blah")
        proc._handle_doc_pair_sync = Mock(side_effect=exc)
        proc._handle_doc_pair_dt = Mock(side_effect=exc)
        proc._execute()
        proc.dao.remove_transfer.assert_called_once()

    def test_download_paused_sets_transfer_doc(self):
        from nxdrive.drive.exceptions import DownloadPaused

        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(side_effect=DownloadPaused(42))
        proc._execute()
        proc.engine.dao.set_transfer_doc.assert_called_once_with(
            "download", 42, proc.engine.uid, pair.id
        )

    def test_upload_paused_sets_transfer_doc(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(side_effect=UploadPaused(99))
        proc._execute()
        proc.engine.dao.set_transfer_doc.assert_called_once_with(
            "upload", 99, proc.engine.uid, pair.id
        )

    def test_duplication_disabled_gives_up(self):
        from nxdrive.drive.exceptions import DuplicationDisabledError

        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc.giveup_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(side_effect=DuplicationDisabledError())
        proc._execute()
        proc.giveup_error.assert_called_once_with(pair, "DEDUP")

    def test_corrupted_file_increases_error(self):
        from nuxeo.exceptions import CorruptedFile

        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        exc = CorruptedFile("file.txt", "bad hash", "expected hash")
        proc._handle_doc_pair_sync = Mock(side_effect=exc)
        proc._execute()
        proc.increase_error.assert_called_once()

    def test_unknown_digest_unsynchronizes(self):
        from nxdrive.drive.exceptions import UnknownDigest

        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(side_effect=UnknownDigest("weird-hash"))
        proc._execute()
        proc.dao.unsynchronize_state.assert_called_once()

    def test_permission_error_postpones(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(side_effect=PermissionError("locked"))
        proc._execute()
        proc.engine.errorOpenedFile.emit.assert_called_once()
        proc._postpone_pair.assert_called_once()

    def test_os_error_enoent_removes_state(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(
            side_effect=OSError(errno.ENOENT, "not found")
        )
        proc._execute()
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_os_error_trash_issue_postpones(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        exc = OSError(42, "trash issue")
        exc.trash_issue = True
        proc._handle_doc_pair_sync = Mock(side_effect=exc)
        proc._execute()
        proc.engine.errorOpenedFile.emit.assert_called_once()
        proc._postpone_pair.assert_called_once()

    def test_runtime_error_expired_creds_removes_upload(self):
        proc = _make_processor()
        pair = _mock_doc_pair(local_state="direct")
        exc = RuntimeError(
            "but the refreshed credentials are still expired"
        )
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(side_effect=exc)
        proc._handle_doc_pair_dt = Mock(side_effect=exc)
        proc._execute()
        proc.dao.remove_transfer.assert_called_once()

    def test_runtime_error_other_reraises(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(
            side_effect=RuntimeError("something else")
        )
        with pytest.raises(RuntimeError, match="something else"):
            proc._execute()

    def test_ongoing_request_error_postpones(self):
        from nuxeo.exceptions import OngoingRequestError

        proc = _make_processor()
        pair = _mock_doc_pair()
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc.increase_error = Mock()
        proc._postpone_pair = Mock()
        proc._handle_doc_pair_sync = Mock(side_effect=OngoingRequestError("req-1"))
        proc._execute()
        proc._postpone_pair.assert_called_once()

    def test_no_sync_handler_increases_error(self):
        proc = _make_processor()
        pair = _mock_doc_pair(pair_state="bizarre_state")
        # Pre-set the attribute to None so getattr() doesn't trigger
        # Qt metaclass checks on the uninitialised QObject.
        proc._synchronize_bizarre_state = None
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.increase_error = Mock()
        proc._execute()
        proc.increase_error.assert_called_once_with(pair, "ILLEGAL_STATE")

    def test_direct_state_calls_dt_handler(self):
        proc = _make_processor()
        pair = _mock_doc_pair(
            pair_state="locally_modified", local_state="direct"
        )
        proc._get_item = Mock(side_effect=[pair, None])
        proc._get_next_doc_pair = Mock(return_value=pair)
        proc._interact = Mock()
        proc.remove_void_transfers = Mock()
        proc.pairSyncStarted = MagicMock()
        proc._handle_doc_pair_dt = Mock()
        proc._handle_doc_pair_sync = Mock()
        proc._current_metrics = {}
        proc._execute()
        proc._handle_doc_pair_dt.assert_called_once()
        proc._handle_doc_pair_sync.assert_not_called()


# ---------------------------------------------------------------------------
# _synchronize_locally_deleted
# ---------------------------------------------------------------------------


class TestSynchronizeLocallyDeleted:
    def test_no_remote_ref_removes_and_searches(self):
        proc = _make_processor()
        proc._search_for_dedup = Mock()
        proc.remove_void_transfers = Mock()
        pair = _mock_doc_pair(remote_ref="")

        proc._synchronize_locally_deleted(pair)

        proc.dao.remove_state.assert_called_once_with(pair)
        proc._search_for_dedup.assert_called_once_with(pair)

    def test_server_deletion_disabled_filters(self):
        from nxdrive.drive.behavior import Behavior

        proc = _make_processor()
        proc._search_for_dedup = Mock()
        proc.remove_void_transfers = Mock()
        pair = _mock_doc_pair(
            remote_ref="ref-1",
            remote_parent_path="/domain",
        )

        with patch.object(Behavior, "server_deletion", False):
            proc._synchronize_locally_deleted(pair)

        proc.dao.remove_state.assert_called_once_with(pair)
        proc.dao.add_filter.assert_called_once_with("/domain/ref-1")

    def test_can_delete_remotely(self):
        proc = _make_processor()
        proc._search_for_dedup = Mock()
        proc.remove_void_transfers = Mock()
        pair = _mock_doc_pair(
            remote_ref="ref-1",
            remote_state="modified",
            remote_can_delete=True,
            remote_name="file.txt",
            remote_parent_ref="parent-ref",
        )

        proc._synchronize_locally_deleted(pair)

        proc.remote.delete.assert_called_once_with(
            "ref-1", parent_fs_item_id="parent-ref"
        )
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_already_deleted_remotely_skips_delete(self):
        proc = _make_processor()
        proc._search_for_dedup = Mock()
        proc.remove_void_transfers = Mock()
        pair = _mock_doc_pair(
            remote_ref="ref-1",
            remote_state="deleted",
            remote_can_delete=True,
            remote_name="file.txt",
        )

        proc._synchronize_locally_deleted(pair)

        proc.remote.delete.assert_not_called()
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_cannot_delete_readonly(self):
        proc = _make_processor()
        proc._search_for_dedup = Mock()
        proc.remove_void_transfers = Mock()
        pair = _mock_doc_pair(
            remote_ref="ref-1",
            remote_state="modified",
            remote_can_delete=False,
            remote_name="file.txt",
            remote_parent_path="/domain",
        )

        proc._synchronize_locally_deleted(pair)

        proc.remote.delete.assert_not_called()
        proc.dao.add_filter.assert_called_once()
        proc.engine.deleteReadonly.emit.assert_called_once()


# ---------------------------------------------------------------------------
# _synchronize_deleted_unknown
# ---------------------------------------------------------------------------


class TestSynchronizeDeletedUnknown:
    def test_removes_state(self):
        proc = _make_processor()
        pair = _mock_doc_pair()

        proc._synchronize_deleted_unknown(pair)

        proc.dao.remove_state.assert_called_once_with(pair)


# ---------------------------------------------------------------------------
# _postpone_pair
# ---------------------------------------------------------------------------


class TestPostponePair:
    def test_sets_error_count_and_pushes(self):
        proc = _make_processor()
        pair = _mock_doc_pair()

        proc._postpone_pair(pair, "test_reason")

        assert pair.error_count == 1
        proc.engine.queue_manager.push_error.assert_called_once_with(
            pair, exception=None, interval=None
        )

    def test_with_exception_and_interval(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        exc = RuntimeError("test")

        proc._postpone_pair(pair, "test_reason", exception=exc, interval=5)

        proc.engine.queue_manager.push_error.assert_called_once_with(
            pair, exception=exc, interval=5
        )


# ---------------------------------------------------------------------------
# _synchronize_locally_resolved
# ---------------------------------------------------------------------------


class TestSynchronizeLocallyResolved:
    def test_delegates_to_locally_created_with_overwrite(self):
        proc = _make_processor()
        proc._synchronize_locally_created = Mock()
        pair = _mock_doc_pair()

        proc._synchronize_locally_resolved(pair)

        proc._synchronize_locally_created.assert_called_once_with(pair, overwrite=True)


# ---------------------------------------------------------------------------
# _refresh_remote / _refresh_local_state
# ---------------------------------------------------------------------------


class TestRefreshRemote:
    def test_fetches_info_when_none(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        remote_info = Mock()
        proc.remote.get_fs_info.return_value = remote_info

        proc._refresh_remote(pair, None)

        proc.remote.get_fs_info.assert_called_once_with(pair.remote_ref)
        proc.dao.update_remote_state.assert_called_once()

    def test_uses_provided_info(self):
        proc = _make_processor()
        pair = _mock_doc_pair()
        remote_info = Mock()

        proc._refresh_remote(pair, remote_info)

        proc.remote.get_fs_info.assert_not_called()
        proc.dao.update_remote_state.assert_called_once()


class TestRefreshLocalState:
    def test_computes_digest_for_non_folderish(self):
        proc = _make_processor()
        pair = _mock_doc_pair(local_digest=None, folderish=False)
        local_info = Mock()
        local_info.get_digest.return_value = "abc123"
        local_info.path = Path("folder/file.txt")
        local_info.last_modification_time = Mock()
        local_info.last_modification_time.strftime.return_value = "2024-01-01 00:00:00"

        proc._refresh_local_state(pair, local_info)

        assert pair.local_digest == "abc123"
        proc.dao.update_local_state.assert_called_once()

    def test_skips_digest_for_folderish(self):
        proc = _make_processor()
        pair = _mock_doc_pair(local_digest=None, folderish=True)
        local_info = Mock()
        local_info.path = Path("folder")
        local_info.last_modification_time = Mock()
        local_info.last_modification_time.strftime.return_value = "2024-01-01 00:00:00"

        proc._refresh_local_state(pair, local_info)

        assert pair.local_digest is None


# ---------------------------------------------------------------------------
# _is_remote_move
# ---------------------------------------------------------------------------


class TestIsRemoteMove:
    def test_same_parent_no_move(self):
        proc = _make_processor()
        pair = _mock_doc_pair(
            local_parent_path=Path("folder"),
            remote_parent_ref="parent-ref",
        )
        parent = Mock()
        parent.id = 10
        proc.dao.get_state_from_local.return_value = parent
        proc._get_normal_state_from_remote_ref = Mock(return_value=parent)

        is_move, remote_parent = proc._is_remote_move(pair)

        assert is_move is False

    def test_different_parent_is_move(self):
        proc = _make_processor()
        pair = _mock_doc_pair(
            local_parent_path=Path("folder"),
            remote_parent_ref="parent-ref",
        )
        local_parent = Mock()
        local_parent.id = 10
        remote_parent = Mock()
        remote_parent.id = 20
        proc.dao.get_state_from_local.return_value = local_parent
        proc._get_normal_state_from_remote_ref = Mock(return_value=remote_parent)

        is_move, rp = proc._is_remote_move(pair)

        assert is_move is True
        assert rp is remote_parent


# ---------------------------------------------------------------------------
# _handle_failed_remote_rename
# ---------------------------------------------------------------------------


class TestHandleFailedRemoteRename:
    def test_no_rollback_returns_false(self):
        proc = _make_processor()
        proc.engine.local_rollback.return_value = False
        pair = _mock_doc_pair()

        result = proc._handle_failed_remote_rename(pair, pair)

        assert result is False

    def test_no_remote_name_returns_false(self):
        proc = _make_processor()
        proc.engine.local_rollback.return_value = True
        pair = _mock_doc_pair(remote_name=None)

        result = proc._handle_failed_remote_rename(pair, pair)

        assert result is False

    def test_successful_rollback(self):
        proc = _make_processor()
        proc.engine.local_rollback.return_value = True
        pair = _mock_doc_pair(
            remote_name="original.txt",
            local_name="renamed.txt",
            local_path=Path("folder/renamed.txt"),
        )
        proc.local.rename.return_value = Mock()

        result = proc._handle_failed_remote_rename(pair, pair)

        assert result is True
        proc.dao.synchronize_state.assert_called_once()


# ---------------------------------------------------------------------------
# _handle_readonly
# ---------------------------------------------------------------------------


class TestHandleReadonly:
    def test_readonly_sets_readonly(self):
        proc = _make_processor()
        pair = _mock_doc_pair(folderish=False, local_path=Path("file.txt"))
        pair.is_readonly.return_value = True

        with patch("nxdrive.nuxeo.engine.processor.WINDOWS", False):
            proc._handle_readonly(pair)

        proc.local.set_readonly.assert_called_once()

    def test_not_readonly_unsets(self):
        proc = _make_processor()
        pair = _mock_doc_pair(folderish=False, local_path=Path("file.txt"))
        pair.is_readonly.return_value = False

        with patch("nxdrive.nuxeo.engine.processor.WINDOWS", False):
            proc._handle_readonly(pair)

        proc.local.unset_readonly.assert_called_once()

    def test_folderish_on_windows_returns(self):
        proc = _make_processor()
        pair = _mock_doc_pair(folderish=True, local_path=Path("folder"))

        with patch("nxdrive.nuxeo.engine.processor.WINDOWS", True):
            proc._handle_readonly(pair)

        proc.local.set_readonly.assert_not_called()
        proc.local.unset_readonly.assert_not_called()
