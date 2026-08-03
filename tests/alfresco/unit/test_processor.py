"""Unit tests for :mod:`nxdrive.alfresco.engine.processor`.

The Alfresco processor subclasses the Drive processor and overrides
only a handful of behaviours (readonly handling, remote drift check,
Alfresco-specific rename). We mock the engine + DAO + local/remote
clients so we can exercise the overrides in isolation.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nxdrive.alfresco.engine.processor import AlfrescoProcessor
from nxdrive.drive.constants import TransferStatus


@pytest.fixture
def mock_engine():
    """A mock ``AlfrescoEngine`` sufficient for constructor + method calls."""
    engine = Mock()
    engine.uid = "test-alfresco-uid"
    engine.dao = Mock()
    engine.local = Mock()
    engine.remote = Mock()
    engine.queue_manager = Mock()
    engine.queue_manager.get_error_threshold = Mock(return_value=3)
    engine.get_metadata_url = Mock(return_value="http://alfresco/metadata")
    engine.get_remote_url = Mock(return_value="http://alfresco/remote")
    return engine


@pytest.fixture
def processor(mock_engine) -> AlfrescoProcessor:
    """Construct an AlfrescoProcessor with mocked dependencies."""
    item_getter = Mock(return_value=None)
    return AlfrescoProcessor(mock_engine, item_getter)


class TestConstruction:
    def test_processor_holds_engine_reference(self, processor, mock_engine) -> None:
        assert processor.engine is mock_engine

    def test_processor_class_name(self, processor) -> None:
        assert processor.__class__.__name__ == "AlfrescoProcessor"


class TestGetNormalStateFromRemoteRef:
    def test_delegates_to_dao(self, processor, mock_engine) -> None:
        mock_engine.dao.get_normal_state_from_remote = Mock(return_value="doc-pair")
        got = processor._get_normal_state_from_remote_ref("abc-123")
        assert got == "doc-pair"
        mock_engine.dao.get_normal_state_from_remote.assert_called_once_with("abc-123")


class TestCheckPairState:
    """`check_pair_state` returns True when the pair should be processed."""

    def test_synchronized_pair_is_skipped(self) -> None:
        pair = Mock()
        pair.pair_state = "synchronized"
        assert AlfrescoProcessor.check_pair_state(pair) is False

    def test_unsynchronized_pair_is_skipped(self) -> None:
        pair = Mock()
        pair.pair_state = "unsynchronized"
        assert AlfrescoProcessor.check_pair_state(pair) is False

    def test_parent_prefixed_state_is_skipped(self) -> None:
        pair = Mock()
        pair.pair_state = "parent_updated"
        assert AlfrescoProcessor.check_pair_state(pair) is False

    def test_active_pair_is_processed(self) -> None:
        pair = Mock()
        pair.pair_state = "locally_created"
        assert AlfrescoProcessor.check_pair_state(pair) is True


# ---------------------------------------------------------------------------
# Additional unit tests for uncovered processor methods
# ---------------------------------------------------------------------------


@pytest.fixture
def proc():
    """Construct an AlfrescoProcessor with mocked dependencies."""
    engine = Mock()
    engine.uid = "test-uid"
    engine.dao = Mock()
    engine.local = Mock()
    engine.remote = Mock()
    engine.queue_manager = Mock()
    engine.queue_manager.get_error_threshold = Mock(return_value=3)
    engine.download_dir = Path("/tmp/downloads")
    item_getter = Mock(return_value=None)
    p = AlfrescoProcessor(engine, item_getter)
    p.local = engine.local
    p.remote = engine.remote
    p.dao = engine.dao
    return p


class TestPostponePair:
    def test_sets_error_count_and_pushes(self, proc) -> None:
        pair = Mock()
        pair.error_count = 0
        proc._postpone_pair(pair, "TEST_REASON")
        assert pair.error_count == 1
        proc.engine.queue_manager.push_error.assert_called_once()

    def test_with_interval(self, proc) -> None:
        pair = Mock()
        pair.error_count = 0
        proc._postpone_pair(pair, "DELAYED", interval=5)
        call_kwargs = proc.engine.queue_manager.push_error.call_args.kwargs
        assert call_kwargs["interval"] == 5


class TestIncreaseError:
    def test_increases_and_postpones(self, proc) -> None:
        pair = Mock()
        pair.error_count = 0
        exc = RuntimeError("test")
        proc.increase_error(pair, "SOME_ERROR", exception=exc)
        proc.dao.increase_error.assert_called_once_with(
            pair, "SOME_ERROR", details="test"
        )
        proc.engine.queue_manager.push_error.assert_called_once()


class TestGiveupError:
    def test_incr_exceeds_threshold(self, proc) -> None:
        pair = Mock()
        proc.giveup_error(pair, "FATAL")
        # threshold is 3, so incr = 4
        call_args = proc.dao.increase_error.call_args
        assert call_args.kwargs["incr"] == 4


class TestRemoteHasDrifted:
    def test_no_remote_ref_returns_false(self, proc) -> None:
        pair = Mock()
        pair.remote_ref = ""
        assert proc._remote_has_drifted(pair) is False

    def test_folder_returns_false(self, proc) -> None:
        pair = Mock()
        pair.remote_ref = "abc"
        pair.folderish = True
        pair.last_remote_updated = "2024-01-01 00:00:00"
        remote_info = Mock()
        remote_info.last_modification_time = "2024-06-01 12:00:00"
        proc.remote.get_fs_info.return_value = remote_info
        assert proc._remote_has_drifted(pair) is False

    def test_file_same_timestamp_no_drift(self, proc) -> None:
        from datetime import datetime, timezone

        pair = Mock()
        pair.remote_ref = "abc"
        pair.folderish = False
        pair.last_remote_updated = "2024-01-01 00:00:00"
        remote_info = Mock()
        remote_info.last_modification_time = datetime(
            2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc
        )
        proc.remote.get_fs_info.return_value = remote_info
        assert proc._remote_has_drifted(pair) is False

    def test_file_different_timestamp_drift(self, proc) -> None:
        from datetime import datetime, timezone

        pair = Mock()
        pair.remote_ref = "abc"
        pair.folderish = False
        pair.last_remote_updated = "2024-01-01 00:00:00"
        remote_info = Mock()
        remote_info.last_modification_time = datetime(
            2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc
        )
        proc.remote.get_fs_info.return_value = remote_info
        assert proc._remote_has_drifted(pair) is True

    def test_not_found_returns_false(self, proc) -> None:
        from nxdrive.drive.exceptions import NotFound

        pair = Mock()
        pair.remote_ref = "abc"
        pair.folderish = False
        proc.remote.get_fs_info.side_effect = NotFound("gone")
        assert proc._remote_has_drifted(pair) is False

    def test_network_error_returns_false(self, proc) -> None:
        pair = Mock()
        pair.remote_ref = "abc"
        pair.folderish = False
        proc.remote.get_fs_info.side_effect = OSError("network")
        assert proc._remote_has_drifted(pair) is False


class TestMarkConflicted:
    def test_calls_force_sync(self, proc) -> None:
        pair = Mock()
        pair.local_name = "test.txt"
        pair.remote_ref = "abc"
        proc._mark_conflicted(pair)
        proc.dao._force_sync.assert_called_once_with(
            pair, "modified", "modified", "conflicted"
        )


class TestRemoveVoidTransfers:
    def test_removes_non_ongoing_downloads(self, proc) -> None:
        pair = Mock()
        pair.id = 42
        download = Mock()
        download.status = TransferStatus.PAUSED
        proc.dao.get_download.return_value = download
        upload = Mock()
        upload.status = TransferStatus.PAUSED
        proc.dao.get_upload.return_value = upload

        proc.remove_void_transfers(pair)
        # Both should be removed
        assert proc.dao.remove_transfer.call_count == 2

    def test_ongoing_not_removed(self, proc) -> None:
        pair = Mock()
        pair.id = 42
        download = Mock()
        download.status = TransferStatus.ONGOING
        proc.dao.get_download.return_value = download
        upload = Mock()
        upload.status = TransferStatus.ONGOING
        proc.dao.get_upload.return_value = upload

        proc.remove_void_transfers(pair)
        proc.dao.remove_transfer.assert_not_called()


class TestSynchronizeLocallyDeleted:
    def test_no_remote_ref_removes_state(self, proc) -> None:
        pair = Mock()
        pair.remote_ref = ""
        proc._synchronize_locally_deleted(pair)
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_can_delete_deletes_remotely(self, proc) -> None:
        pair = Mock()
        pair.remote_ref = "node-1"
        pair.remote_can_delete = True
        pair.remote_state = "synchronized"
        pair.remote_parent_ref = "parent-ref"
        proc._synchronize_locally_deleted(pair)
        proc.remote.delete.assert_called_once_with(
            "node-1", parent_fs_item_id="parent-ref"
        )
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_cannot_delete_adds_filter(self, proc) -> None:
        pair = Mock()
        pair.remote_ref = "node-1"
        pair.remote_can_delete = False
        pair.local_path = "/some/path"
        pair.remote_parent_path = "/parent"
        proc._synchronize_locally_deleted(pair)
        proc.dao.remove_state.assert_called()
        proc.dao.add_filter.assert_called_once_with("/parent/node-1")


class TestSynchronizeLocallyMoved:
    def test_rename_calls_remote_rename(self, proc) -> None:
        pair = Mock()
        pair.remote_ref = "node-1"
        pair.local_parent_path = "/parent"
        pair.local_name = "renamed.txt"
        pair.remote_name = "original.txt"
        pair.remote_parent_ref = "parent-ref"

        proc.local.get_remote_id.return_value = "parent-ref"
        parent_pair = Mock()
        parent_pair.remote_ref = "parent-ref"
        parent_pair.remote_parent_path = ""
        proc._get_normal_state_from_remote_ref = Mock(return_value=parent_pair)

        remote_info = Mock()
        proc.remote.rename.return_value = remote_info

        proc._synchronize_locally_moved(pair)
        proc.remote.rename.assert_called_once_with("node-1", "renamed.txt")

    def test_move_calls_remote_move(self, proc) -> None:
        pair = Mock()
        pair.remote_ref = "node-1"
        pair.local_parent_path = "/new-parent"
        pair.local_name = "file.txt"
        pair.remote_name = "file.txt"
        pair.remote_parent_ref = "old-parent-ref"

        proc.local.get_remote_id.return_value = "new-parent-ref"
        new_parent_pair = Mock()
        new_parent_pair.remote_ref = "new-parent-ref"
        new_parent_pair.remote_parent_path = "/root"
        proc._get_normal_state_from_remote_ref = Mock(return_value=new_parent_pair)

        remote_info = Mock()
        proc.remote.move.return_value = remote_info

        proc._synchronize_locally_moved(pair)
        proc.remote.move.assert_called_once_with("node-1", "new-parent-ref")


class TestSynchronizeConflicted:
    def test_both_moved_sets_conflict(self, proc) -> None:
        pair = Mock()
        pair.local_state = "moved"
        pair.remote_state = "moved"
        proc._synchronize_conflicted(pair)
        proc.dao.set_conflict_state.assert_called_once_with(pair)

    def test_file_no_drift_auto_resolves(self, proc) -> None:
        pair = Mock()
        pair.local_state = "modified"
        pair.remote_state = "modified"
        pair.folderish = False
        pair.remote_ref = "abc"
        pair.local_name = "file.txt"
        # No drift
        proc._remote_has_drifted = Mock(return_value=False)

        proc._synchronize_conflicted(pair)
        proc.dao.synchronize_state.assert_called_once_with(pair)

    def test_file_with_drift_sets_conflict(self, proc) -> None:
        pair = Mock()
        pair.local_state = "modified"
        pair.remote_state = "modified"
        pair.folderish = False
        pair.remote_ref = "abc"
        pair.local_name = "file.txt"
        proc._remote_has_drifted = Mock(return_value=True)

        proc._synchronize_conflicted(pair)
        proc.dao.set_conflict_state.assert_called_once_with(pair)

    def test_folder_matching_uid_auto_resolves(self, proc) -> None:
        pair = Mock()
        pair.local_state = "modified"
        pair.remote_state = "modified"
        pair.folderish = True
        pair.remote_ref = "folder-ref"
        pair.local_path = "/path"
        pair.local_name = "folder"
        proc.local.get_remote_id.return_value = "folder-ref"

        proc._synchronize_conflicted(pair)
        proc.dao.synchronize_state.assert_called_once_with(pair)


class TestSynchronizeUnknownDeleted:
    def test_removes_state(self, proc) -> None:
        pair = Mock()
        proc._synchronize_unknown_deleted(pair)
        proc.dao.remove_state.assert_called_once_with(pair)


class TestFmtRemoteTs:
    def test_none_returns_empty(self) -> None:
        from nxdrive.alfresco.engine.processor import _fmt_remote_ts

        assert _fmt_remote_ts(None) == ""

    def test_datetime_formats_correctly(self) -> None:
        from datetime import datetime, timezone

        from nxdrive.alfresco.engine.processor import _fmt_remote_ts

        ts = datetime(2024, 6, 15, 10, 30, 45, tzinfo=timezone.utc)
        assert _fmt_remote_ts(ts) == "2024-06-15 10:30:45"

    def test_string_truncated(self) -> None:
        from nxdrive.alfresco.engine.processor import _fmt_remote_ts

        assert (
            _fmt_remote_ts("2024-06-15 10:30:45.123456+00:00") == "2024-06-15 10:30:45"
        )


class TestRefreshLocalState:
    def test_delegates_to_dao(self, proc) -> None:
        pair = Mock()
        info = Mock()
        proc._refresh_local_state(pair, info)
        proc.dao.update_local_state.assert_called_once_with(
            pair, info, versioned=False, queue=False
        )


class TestRefreshRemote:
    def test_fetches_and_updates(self, proc) -> None:
        pair = Mock()
        pair.remote_ref = "abc"
        remote_info = Mock()
        proc.remote.get_fs_info.return_value = remote_info
        proc._refresh_remote(pair)
        proc.remote.get_fs_info.assert_called_once_with("abc")
        proc.dao.update_remote_state.assert_called_once_with(
            pair, remote_info, versioned=False, queue=False
        )

    def test_uses_provided_info(self, proc) -> None:
        pair = Mock()
        pair.remote_ref = "abc"
        provided_info = Mock()
        proc._refresh_remote(pair, provided_info)
        proc.remote.get_fs_info.assert_not_called()
        proc.dao.update_remote_state.assert_called_once_with(
            pair, provided_info, versioned=False, queue=False
        )

    def test_none_info_no_update(self, proc) -> None:
        pair = Mock()
        pair.remote_ref = "abc"
        proc.remote.get_fs_info.return_value = None
        proc._refresh_remote(pair)
        proc.dao.update_remote_state.assert_not_called()


class TestHandleReadonly:
    def test_readonly_pair_sets_readonly(self, proc) -> None:
        pair = Mock()
        pair.folderish = False
        pair.is_readonly.return_value = True
        pair.local_path = "/file.txt"
        proc._handle_readonly(pair)
        proc.local.set_readonly.assert_called_once_with("/file.txt")

    def test_writable_pair_unsets_readonly(self, proc) -> None:
        pair = Mock()
        pair.folderish = False
        pair.is_readonly.return_value = False
        pair.local_path = "/file.txt"
        proc._handle_readonly(pair)
        proc.local.unset_readonly.assert_called_once_with("/file.txt")


class TestIsRemoteMove:
    def test_different_parents_means_move(self, proc) -> None:
        pair = Mock()
        pair.local_parent_path = "/parent-a"
        pair.remote_parent_ref = "remote-parent-b"

        local_parent = Mock()
        local_parent.id = 1
        remote_parent = Mock()
        remote_parent.id = 2
        proc.dao.get_state_from_local.return_value = local_parent
        proc._get_normal_state_from_remote_ref = Mock(return_value=remote_parent)

        is_move, parent = proc._is_remote_move(pair)
        assert is_move is True
        assert parent is remote_parent

    def test_same_parent_no_move(self, proc) -> None:
        pair = Mock()
        pair.local_parent_path = "/parent"
        pair.remote_parent_ref = "remote-parent"

        same = Mock()
        same.id = 1
        proc.dao.get_state_from_local.return_value = same
        proc._get_normal_state_from_remote_ref = Mock(return_value=same)

        is_move, parent = proc._is_remote_move(pair)
        assert is_move is False


class TestSynchronizeRemotelyCreated:
    def test_parent_not_found_raises(self, proc) -> None:
        from nxdrive.drive.exceptions import ParentNotSynced

        pair = Mock()
        pair.remote_name = "file.txt"
        pair.remote_ref = "abc"
        pair.remote_parent_ref = "parent-ref"
        proc._get_normal_state_from_remote_ref = Mock(return_value=None)

        with pytest.raises(ParentNotSynced):
            proc._synchronize_remotely_created(pair)

    def test_parent_local_path_none_raises(self, proc) -> None:
        from nxdrive.drive.exceptions import ParentNotSynced

        pair = Mock()
        pair.remote_name = "file.txt"
        pair.remote_ref = "abc"
        pair.remote_parent_ref = "parent-ref"
        parent = Mock()
        parent.local_path = None
        proc._get_normal_state_from_remote_ref = Mock(return_value=parent)

        with pytest.raises(ParentNotSynced):
            proc._synchronize_remotely_created(pair)

    def test_existing_same_remote_id_sets_conflict(self, proc) -> None:
        pair = Mock()
        pair.remote_name = "file.txt"
        pair.remote_ref = "abc"
        pair.remote_parent_ref = "parent-ref"
        pair.local_path = Path("/local/file.txt")
        pair.folderish = False

        parent = Mock()
        parent.local_path = Path("/local")
        parent.remote_ref = "parent-ref"
        proc._get_normal_state_from_remote_ref = Mock(return_value=parent)
        proc.local.exists.return_value = True
        proc.local.get_remote_id.return_value = "abc"  # same as pair.remote_ref

        proc._synchronize_remotely_created(pair)
        proc.dao.set_conflict_state.assert_called_once_with(pair)


class TestSynchronizeRemotelyDeleted:
    def test_mismatched_remote_id_aborts(self, proc) -> None:
        pair = Mock()
        pair.local_path = "/path/file.txt"
        pair.remote_ref = "correct-ref"
        pair.local_state = "synchronized"
        proc.local.get_remote_id.return_value = "wrong-ref"

        proc._synchronize_remotely_deleted(pair)
        # Should NOT call remove_state because IDs don't match
        proc.dao.remove_state.assert_not_called()

    def test_already_deleted_state_removes(self, proc) -> None:
        pair = Mock()
        pair.local_path = "/path/file.txt"
        pair.remote_ref = "ref"
        pair.local_state = "deleted"
        pair.folderish = False
        proc.local.get_remote_id.return_value = "ref"

        proc._synchronize_remotely_deleted(pair)
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_unsynchronized_removes_state(self, proc) -> None:
        pair = Mock()
        pair.local_path = "/path/file.txt"
        pair.remote_ref = "ref"
        pair.local_state = "unsynchronized"
        pair.folderish = False
        proc.local.get_remote_id.return_value = "ref"

        proc._synchronize_remotely_deleted(pair)
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_normal_state_deletes_locally(self, proc) -> None:
        pair = Mock()
        pair.local_path = "/path/file.txt"
        pair.remote_ref = "ref"
        pair.local_state = "synchronized"
        pair.folderish = False
        proc.local.get_remote_id.return_value = "ref"
        proc.engine.use_trash.return_value = False

        proc._synchronize_remotely_deleted(pair)
        proc.local.delete_final.assert_called_once_with("/path/file.txt")
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_uses_trash_when_configured(self, proc) -> None:
        pair = Mock()
        pair.local_path = "/path/file.txt"
        pair.remote_ref = "ref"
        pair.local_state = "synchronized"
        pair.folderish = False
        proc.local.get_remote_id.return_value = "ref"
        proc.engine.use_trash.return_value = True

        proc._synchronize_remotely_deleted(pair)
        proc.local.delete.assert_called_once_with("/path/file.txt")


class TestSynchronizeLocallyCreated:
    def test_parent_not_found_raises(self, proc) -> None:
        from nxdrive.drive.exceptions import ParentNotSynced

        pair = Mock()
        pair.local_path = Path("/local/newfile.txt")
        pair.local_parent_path = Path("/local")
        pair.folderish = False
        proc.dao.get_state_from_local.return_value = None
        proc.local.exists.return_value = False

        with pytest.raises(ParentNotSynced):
            proc._synchronize_locally_created(pair)

    def test_readonly_parent_unsynchronizes(self, proc) -> None:
        pair = Mock()
        pair.local_path = Path("/local/newfile.txt")
        pair.local_parent_path = Path("/local")
        pair.local_name = "newfile.txt"
        pair.folderish = False

        parent = Mock()
        parent.remote_ref = "parent-ref"
        parent.remote_can_create_child = False
        parent.remote_name = "LocalFolder"
        parent.remote_parent_path = ""
        proc.dao.get_state_from_local.return_value = parent

        proc._synchronize_locally_created(pair)
        proc.dao.unsynchronize_state.assert_called_once_with(pair, "READONLY")

    def test_folder_creates_remote_folder(self, proc) -> None:
        pair = Mock()
        pair.local_path = Path("/local/NewFolder")
        pair.local_parent_path = Path("/local")
        pair.local_name = "NewFolder"
        pair.folderish = True
        pair.id = 99

        parent = Mock()
        parent.remote_ref = "parent-ref"
        parent.remote_can_create_child = True
        parent.remote_name = "LocalFolder"
        parent.remote_parent_path = "/root"
        proc.dao.get_state_from_local.return_value = parent

        fs_info = Mock()
        fs_info.uid = "new-folder-id"
        fs_info.digest = None
        proc.remote.make_folder.return_value = fs_info

        proc._synchronize_locally_created(pair)
        proc.remote.make_folder.assert_called_once_with("parent-ref", "NewFolder")
        proc.dao.synchronize_state.assert_called_once_with(pair)


class TestSynchronizeLocallyModified:
    def test_digests_differ_uploads(self, proc) -> None:
        pair = Mock()
        pair.local_path = Path("/local/file.txt")
        pair.local_name = "file.txt"
        pair.local_digest = "local_hash"
        pair.remote_digest = "remote_hash"
        pair.remote_ref = "node-1"
        pair.remote_name = "file.txt"
        pair.remote_can_update = True
        pair.id = 1

        proc.local.is_equal_digests.return_value = False
        proc.local.abspath.return_value = Path("/abs/file.txt")

        fs_info = Mock()
        proc.remote.stream_update.return_value = fs_info

        proc._synchronize_locally_modified(pair)
        proc.remote.stream_update.assert_called_once()
        proc.dao.synchronize_state.assert_called_once_with(pair)

    def test_readonly_unsynchronizes(self, proc) -> None:
        pair = Mock()
        pair.local_path = Path("/local/file.txt")
        pair.local_name = "file.txt"
        pair.local_digest = "local_hash"
        pair.remote_digest = "remote_hash"
        pair.remote_ref = "node-1"
        pair.remote_can_update = False
        pair.id = 1

        proc.local.is_equal_digests.return_value = False

        proc._synchronize_locally_modified(pair)
        proc.dao.unsynchronize_state.assert_called_once_with(pair, "READONLY")

    def test_same_digest_just_syncs(self, proc) -> None:
        pair = Mock()
        pair.local_path = Path("/local/file.txt")
        pair.local_digest = "same"
        pair.remote_digest = "same"
        pair.remote_ref = "node-1"
        pair.id = 1

        proc.local.is_equal_digests.return_value = True
        fs_info = Mock()
        proc.remote.get_fs_info.return_value = fs_info

        proc._synchronize_locally_modified(pair)
        proc.remote.stream_update.assert_not_called()
        proc.dao.synchronize_state.assert_called_once_with(pair)


class TestSynchronizeLocallyResolved:
    def test_with_remote_ref_delegates_to_modify(self, proc) -> None:
        pair = Mock()
        pair.local_path = Path("/local/file.txt")
        pair.remote_ref = "node-1"
        pair.local_digest = "hash"
        pair.remote_digest = "hash"
        pair.id = 1

        info = Mock()
        info.get_digest.return_value = "hash"
        proc.local.exists.return_value = True
        proc.local.get_info.return_value = info
        proc.local.is_equal_digests.return_value = True
        fs_info = Mock()
        proc.remote.get_fs_info.return_value = fs_info

        proc._synchronize_locally_resolved(pair)
        proc.dao.synchronize_state.assert_called()

    def test_without_remote_ref_delegates_to_create(self, proc) -> None:
        pair = Mock()
        pair.local_path = Path("/local/file.txt")
        pair.local_parent_path = Path("/local")
        pair.remote_ref = ""
        pair.folderish = False
        pair.local_name = "file.txt"

        info = Mock()
        info.get_digest.return_value = "hash"
        proc.local.exists.return_value = True
        proc.local.get_info.return_value = info

        with patch.object(proc, "_synchronize_locally_created") as mock_create:
            proc._synchronize_locally_resolved(pair)
        mock_create.assert_called_once_with(pair)


class TestDownloadContent:
    def test_streams_from_remote(self, proc, tmp_path) -> None:
        pair = Mock()
        pair.remote_ref = "node-123"
        pair.remote_parent_ref = "parent-ref"
        pair.remote_digest = None
        pair.id = 42

        proc.engine.download_dir = tmp_path
        expected_out = tmp_path / "node-123" / "file.txt"
        proc.remote.stream_content.return_value = expected_out

        result = proc._download_content(pair, Path("file.txt"))
        proc.remote.stream_content.assert_called_once()
        assert result == expected_out

    def test_hash_separator_stripped(self, proc, tmp_path) -> None:
        pair = Mock()
        pair.remote_ref = "workspace#node-456"
        pair.remote_parent_ref = "parent"
        pair.remote_digest = None
        pair.id = 1

        proc.engine.download_dir = tmp_path
        proc.remote.stream_content.return_value = tmp_path / "node-456" / "f.txt"

        proc._download_content(pair, Path("f.txt"))
        # The tmp_folder should use only the part after '#'
        call_args = proc.remote.stream_content.call_args
        assert "node-456" in str(call_args[0][2])


class TestGetNextDocPair:
    def test_acquires_state(self, proc) -> None:
        item = Mock()
        item.id = 10
        acquired = Mock()
        proc.dao.acquire_state.return_value = acquired

        result = proc._get_next_doc_pair(item)
        proc.dao.acquire_state.assert_called_once_with(proc.thread_id, 10)
        assert result is acquired

    def test_operational_error_postpones(self, proc) -> None:
        import sqlite3

        item = Mock()
        item.id = 10
        proc.dao.acquire_state.side_effect = sqlite3.OperationalError("locked")
        proc.dao.get_state_from_id.return_value = Mock()

        result = proc._get_next_doc_pair(item)
        assert result is None
        proc.engine.queue_manager.push_error.assert_called_once()


# ------------------------------------------------------------------ _execute


class TestExecute:
    @pytest.fixture
    def proc(self, mock_engine):
        item_getter = Mock(return_value=None)
        p = AlfrescoProcessor(mock_engine, item_getter)
        p.thread_id = 1
        p.dao = mock_engine.dao
        p.remote = mock_engine.remote
        p.local = mock_engine.local
        p.pairSyncStarted = Mock()
        p.pairSyncEnded = Mock()
        return p

    def test_no_items_returns(self, proc):
        proc._get_item = Mock(return_value=None)
        proc._execute()
        proc.dao.release_state.assert_not_called()

    def test_skips_non_processable(self, proc):
        item = Mock()
        item.pair_state = "synchronized"
        item.id = 1
        proc._get_item = Mock(side_effect=[item, None])
        proc.dao.acquire_state.return_value = item
        proc._execute()
        proc.dao.release_state.assert_called()

    def test_illegal_state_increases_error(self, proc):
        item = Mock()
        item.pair_state = "some_invalid_state"
        item.id = 1
        item.version = 1
        proc._get_item = Mock(side_effect=[item, None])
        proc.dao.acquire_state.return_value = item
        proc.dao.increase_error = Mock()
        proc._execute()
        proc.dao.increase_error.assert_called()

    def test_thread_interrupt_requeues(self, proc):
        from nxdrive.drive.exceptions import ThreadInterrupt

        item = Mock()
        item.pair_state = "locally_created"
        item.id = 1
        item.version = 1
        proc._get_item = Mock(side_effect=[item, None])
        proc.dao.acquire_state.return_value = item
        proc._handle_doc_pair_sync = Mock(side_effect=ThreadInterrupt())
        with pytest.raises(ThreadInterrupt):
            proc._execute()
        proc.engine.queue_manager.push.assert_called_once_with(item)

    def test_not_found_removes_transfers(self, proc):
        from nxdrive.drive.exceptions import NotFound

        item = Mock()
        item.pair_state = "locally_created"
        item.id = 1
        item.version = 1
        proc._get_item = Mock(side_effect=[item, None])
        proc.dao.acquire_state.return_value = item
        proc._handle_doc_pair_sync = Mock(side_effect=NotFound("gone"))
        proc._execute()

    def test_connection_error_postpones(self, proc):
        from requests.exceptions import ConnectionError as ReqConnectionError

        item = Mock()
        item.pair_state = "locally_created"
        item.id = 1
        item.version = 1
        proc._get_item = Mock(side_effect=[item, None])
        proc.dao.acquire_state.return_value = item
        proc._handle_doc_pair_sync = Mock(
            side_effect=ReqConnectionError("connection lost")
        )
        proc._execute()
        proc.engine.queue_manager.push_error.assert_called()

    def test_os_error_no_space(self, proc):
        from nxdrive.drive.exceptions import ThreadInterrupt

        item = Mock()
        item.pair_state = "locally_created"
        item.id = 1
        item.version = 1
        proc._get_item = Mock(side_effect=[item, None])
        proc.dao.acquire_state.return_value = item
        err = OSError(28, "No space left on device")
        proc._handle_doc_pair_sync = Mock(side_effect=err)
        with pytest.raises(ThreadInterrupt):
            proc._execute()
        proc.engine.noSpaceLeftOnDevice.emit.assert_called_once()


# ------------------------------------------------------------------ _synchronize_remotely_deleted


class TestSynchronizeRemotelyDeletedExtra:
    @pytest.fixture
    def proc(self, mock_engine):
        item_getter = Mock(return_value=None)
        p = AlfrescoProcessor(mock_engine, item_getter)
        p.thread_id = 1
        p.dao = mock_engine.dao
        p.remote = mock_engine.remote
        p.local = mock_engine.local
        return p

    def test_mismatched_id_skips(self, proc):
        pair = Mock()
        pair.local_path = "/doc"
        pair.remote_ref = "node-abc"
        proc.local.get_remote_id.return_value = "node-xyz"
        proc._synchronize_remotely_deleted(pair)
        proc.dao.remove_state.assert_not_called()

    def test_already_deleted_removes_state(self, proc):
        pair = Mock()
        pair.local_path = "/doc"
        pair.remote_ref = "node-abc"
        pair.local_state = "deleted"
        pair.folderish = False
        proc.local.get_remote_id.return_value = "node-abc"
        proc._synchronize_remotely_deleted(pair)
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_unsynchronized_removes_state(self, proc):
        pair = Mock()
        pair.local_path = "/doc"
        pair.remote_ref = "node-abc"
        pair.local_state = "unsynchronized"
        pair.folderish = False
        proc.local.get_remote_id.return_value = "node-abc"
        proc._synchronize_remotely_deleted(pair)
        proc.dao.remove_state.assert_called_once_with(pair)


# ------------------------------------------------------------------ _synchronize_locally_deleted


class TestSynchronizeLocallyDeletedExtra:
    @pytest.fixture
    def proc(self, mock_engine):
        item_getter = Mock(return_value=None)
        p = AlfrescoProcessor(mock_engine, item_getter)
        p.thread_id = 1
        p.dao = mock_engine.dao
        p.remote = mock_engine.remote
        p.local = mock_engine.local
        return p

    def test_no_remote_ref_just_removes(self, proc):
        pair = Mock()
        pair.remote_ref = None
        proc._synchronize_locally_deleted(pair)
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_can_delete_removes_remote_and_state(self, proc):
        pair = Mock()
        pair.remote_ref = "node-abc"
        pair.remote_parent_ref = "parent-ref"
        pair.remote_can_delete = True
        pair.remote_state = "synchronized"
        pair.remote_name = "file.txt"
        proc._synchronize_locally_deleted(pair)
        proc.remote.delete.assert_called_once()
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_cannot_delete_adds_filter(self, proc):
        pair = Mock()
        pair.remote_ref = "node-abc"
        pair.remote_parent_ref = "parent-ref"
        pair.remote_parent_path = "/root"
        pair.remote_can_delete = False
        pair.local_path = "/doc"
        proc._synchronize_locally_deleted(pair)
        proc.dao.add_filter.assert_called_once_with("/root/node-abc")


# ------------------------------------------------------------------ _synchronize_conflicted


class TestSynchronizeConflictedExtra:
    @pytest.fixture
    def proc(self, mock_engine):
        item_getter = Mock(return_value=None)
        p = AlfrescoProcessor(mock_engine, item_getter)
        p.thread_id = 1
        p.dao = mock_engine.dao
        p.remote = mock_engine.remote
        p.local = mock_engine.local
        return p

    def test_both_moved_sets_conflict(self, proc):
        pair = Mock()
        pair.local_state = "moved"
        pair.remote_state = "moved"
        proc._synchronize_conflicted(pair)
        proc.dao.set_conflict_state.assert_called_once_with(pair)

    def test_file_remote_unchanged_resolves(self, proc):
        pair = Mock()
        pair.folderish = False
        pair.local_state = "modified"
        pair.remote_state = "modified"
        pair.remote_ref = "node-abc"
        pair.local_name = "file.txt"
        proc._remote_has_drifted = Mock(return_value=False)
        proc._synchronize_conflicted(pair)
        proc.dao.synchronize_state.assert_called_once_with(pair)

    def test_file_remote_drifted_sets_conflict(self, proc):
        pair = Mock()
        pair.folderish = False
        pair.local_state = "modified"
        pair.remote_state = "modified"
        pair.remote_ref = "node-abc"
        pair.local_name = "file.txt"
        proc._remote_has_drifted = Mock(return_value=True)
        proc._synchronize_conflicted(pair)
        proc.dao.set_conflict_state.assert_called_once_with(pair)

    def test_folder_matching_uid_resolves(self, proc):
        pair = Mock()
        pair.folderish = True
        pair.local_state = "modified"
        pair.remote_state = "modified"
        pair.remote_ref = "folder-abc"
        pair.local_path = "/folder"
        pair.local_name = "MyFolder"
        proc.local.get_remote_id.return_value = "folder-abc"
        proc._synchronize_conflicted(pair)
        proc.dao.synchronize_state.assert_called_once_with(pair)

    def test_folder_mismatched_uid_conflicts(self, proc):
        pair = Mock()
        pair.folderish = True
        pair.local_state = "modified"
        pair.remote_state = "modified"
        pair.remote_ref = "folder-abc"
        pair.local_path = "/folder"
        pair.local_name = "MyFolder"
        proc.local.get_remote_id.return_value = "different-id"
        proc._synchronize_conflicted(pair)
        proc.dao.set_conflict_state.assert_called_once_with(pair)


# ------------------------------------------------------------------ _synchronize_unknown_deleted / deleted_unknown


class TestSynchronizeInconsistentPairs:
    @pytest.fixture
    def proc(self, mock_engine):
        item_getter = Mock(return_value=None)
        p = AlfrescoProcessor(mock_engine, item_getter)
        p.thread_id = 1
        p.dao = mock_engine.dao
        return p

    def test_unknown_deleted(self, proc):
        pair = Mock()
        proc._synchronize_unknown_deleted(pair)
        proc.dao.remove_state.assert_called_once_with(pair)

    def test_deleted_unknown(self, proc):
        pair = Mock()
        proc._synchronize_deleted_unknown(pair)
        proc.dao.remove_state.assert_called_once_with(pair)


# ------------------------------------------------------------------ _mark_conflicted


class TestMarkConflictedExtra:
    @pytest.fixture
    def proc(self, mock_engine):
        item_getter = Mock(return_value=None)
        p = AlfrescoProcessor(mock_engine, item_getter)
        p.dao = mock_engine.dao
        return p

    def test_calls_force_sync(self, proc):
        pair = Mock()
        pair.local_name = "file.txt"
        pair.remote_ref = "node-123"
        proc._mark_conflicted(pair)
        proc.dao._force_sync.assert_called_once_with(
            pair, "modified", "modified", "conflicted"
        )


# ------------------------------------------------------------------ _remote_has_drifted


class TestRemoteHasDriftedExtra:
    @pytest.fixture
    def proc(self, mock_engine):
        item_getter = Mock(return_value=None)
        p = AlfrescoProcessor(mock_engine, item_getter)
        p.dao = mock_engine.dao
        p.remote = mock_engine.remote
        return p

    def test_no_remote_ref(self, proc):
        pair = Mock(remote_ref=None)
        assert proc._remote_has_drifted(pair) is False

    def test_not_found_returns_false(self, proc):
        from nxdrive.drive.exceptions import NotFound

        pair = Mock(remote_ref="node-abc", folderish=False)
        proc.remote.get_fs_info.side_effect = NotFound("gone")
        assert proc._remote_has_drifted(pair) is False

    def test_generic_exception_returns_false(self, proc):
        pair = Mock(remote_ref="node-abc", folderish=False)
        proc.remote.get_fs_info.side_effect = RuntimeError("network")
        assert proc._remote_has_drifted(pair) is False

    def test_folder_always_false(self, proc):
        pair = Mock(
            remote_ref="node-abc",
            folderish=True,
            last_remote_updated="2024-01-01 00:00:00",
        )
        remote_info = Mock()
        remote_info.last_modification_time = Mock()
        remote_info.last_modification_time.strftime.return_value = "2024-06-15 12:00:00"
        proc.remote.get_fs_info.return_value = remote_info
        assert proc._remote_has_drifted(pair) is False

    def test_timestamps_match_no_drift(self, proc):
        pair = Mock(
            remote_ref="node-abc",
            folderish=False,
            last_remote_updated="2024-01-01 00:00:00",
        )
        remote_info = Mock()
        remote_info.last_modification_time = Mock()
        remote_info.last_modification_time.strftime.return_value = "2024-01-01 00:00:00"
        proc.remote.get_fs_info.return_value = remote_info
        assert proc._remote_has_drifted(pair) is False

    def test_timestamps_differ_drift(self, proc):
        pair = Mock(
            remote_ref="node-abc",
            folderish=False,
            last_remote_updated="2024-01-01 00:00:00",
        )
        remote_info = Mock()
        remote_info.last_modification_time = Mock()
        remote_info.last_modification_time.strftime.return_value = "2024-06-15 12:00:00"
        proc.remote.get_fs_info.return_value = remote_info
        assert proc._remote_has_drifted(pair) is True
