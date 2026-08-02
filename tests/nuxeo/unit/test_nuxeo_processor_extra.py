"""Extra unit tests for nxdrive.nuxeo.engine.processor — methods not yet covered."""

import errno
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.drive.constants import DigestStatus, TransferStatus
from nxdrive.drive.exceptions import (
    NotFound,
    PairInterrupt,
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
        state = _mock_doc_pair(id=7, pair_state="locally_modified", remote_can_rename=True)
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
        pair = _mock_doc_pair(pair_state="locally_created", local_path=Path("ws/file.txt"))

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
        pair = _mock_doc_pair(pair_state="locally_created", local_path=Path("ws/file.txt"))
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
        pair = _mock_doc_pair(local_path=Path("f.txt"), local_name="f.txt", local_digest="d1")
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
