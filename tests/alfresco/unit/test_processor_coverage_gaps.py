"""Targeted coverage tests for Alfresco processor edge branches."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.alfresco.engine.processor import AlfrescoProcessor
from nxdrive.drive.constants import UNACCESSIBLE_HASH
from nxdrive.drive.exceptions import ParentNotSynced


@pytest.fixture
def processor(tmp_path):
    engine = MagicMock()
    engine.uid = "alfresco-coverage-engine"
    engine.dao = MagicMock()
    engine.local = MagicMock()
    engine.remote = MagicMock()
    engine.manager = MagicMock()
    engine.queue_manager = MagicMock()
    engine.queue_manager.get_error_threshold.return_value = 3
    engine.download_dir = tmp_path / "downloads"

    result = AlfrescoProcessor(engine, MagicMock(return_value=None))
    result.dao = engine.dao
    result.local = engine.local
    result.remote = engine.remote
    result.pairSyncStarted = MagicMock()
    result.pairSyncEnded = MagicMock()
    result._current_metrics = {}
    result.dao.get_filters.return_value = []
    return result


def test_finder_owned_file_is_postponed(processor):
    pair = MagicMock()
    pair.id = 1
    pair.local_path = Path("sync/document.txt")
    pair.local_parent_path = None
    pair.error_count = 0
    processor.local.get_remote_id.return_value = "prefix-brokMACS-suffix"

    with patch("nxdrive.alfresco.engine.processor.MAC", True):
        processor._handle_doc_pair_sync(pair, MagicMock())

    processor.engine.queue_manager.push_error.assert_called_once_with(
        pair, exception=None, interval=3
    )


def test_remote_create_stops_when_parent_xattr_does_not_match(processor):
    pair = MagicMock()
    pair.remote_name = "document.txt"
    pair.remote_ref = "document-id"
    pair.remote_parent_ref = "parent-id"
    pair.local_path = Path("sync/document.txt")
    pair.folderish = False
    parent = MagicMock()
    parent.local_path = Path("sync")
    parent.remote_ref = "parent-id"
    processor._get_normal_state_from_remote_ref = MagicMock(return_value=parent)
    processor.local.exists.return_value = False
    processor.local.get_remote_id.return_value = "different-parent-id"
    processor._create_remotely = MagicMock()

    processor._synchronize_remotely_created(pair)

    processor._create_remotely.assert_not_called()
    processor.local.set_remote_id.assert_not_called()


def test_remote_folder_create_records_actual_safe_path(processor):
    pair = MagicMock()
    pair.remote_name = "folder"
    pair.remote_ref = "folder-id"
    pair.remote_parent_ref = "parent-id"
    pair.local_path = Path("sync/folder")
    pair.folderish = True
    pair.is_readonly.return_value = False
    parent = MagicMock()
    parent.local_path = Path("sync")
    parent.remote_ref = "parent-id"
    processor._get_normal_state_from_remote_ref = MagicMock(return_value=parent)
    processor.local.exists.return_value = False
    processor.local.get_remote_id.return_value = "parent-id"
    actual_path = Path("sync/folder-safe")
    processor._create_remotely = MagicMock(return_value=actual_path)
    local_info = MagicMock()
    local_info.get_digest.return_value = "folder-digest"
    processor.local.get_info.return_value = local_info

    processor._synchronize_remotely_created(pair)

    processor._create_remotely.assert_called_once_with(pair, parent, "folder")
    processor.local.set_remote_id.assert_called_once_with(actual_path, "folder-id")
    processor.dao.update_local_parent_path.assert_called_once_with(
        pair, "folder-safe", Path("sync")
    )
    assert pair.local_digest == "folder-digest"
    processor.dao.synchronize_state.assert_called_once_with(pair)


def test_remote_create_chooses_safe_name_when_path_has_another_xattr(processor):
    pair = MagicMock()
    pair.remote_name = "document.txt"
    pair.remote_ref = "document-id"
    pair.remote_parent_ref = "parent-id"
    pair.local_path = Path("sync/document.txt")
    pair.folderish = False
    pair.is_readonly.return_value = False
    parent = MagicMock()
    parent.local_path = Path("sync")
    parent.remote_ref = "parent-id"
    processor._get_normal_state_from_remote_ref = MagicMock(return_value=parent)
    processor.local.exists.return_value = True
    processor.local.get_remote_id.return_value = "occupied-id"
    actual_path = Path("sync/document-1.txt")
    processor._create_remotely = MagicMock(return_value=actual_path)
    local_info = MagicMock()
    local_info.get_digest.return_value = "downloaded-digest"
    processor.local.get_info.return_value = local_info

    processor._synchronize_remotely_created(pair)

    processor._create_remotely.assert_called_once_with(pair, parent, "document.txt")
    processor.local.set_remote_id.assert_called_once_with(actual_path, "document-id")
    processor.dao.synchronize_state.assert_called_once_with(pair)


def test_remote_modify_postpones_until_parent_is_synchronized(processor):
    pair = MagicMock()
    pair.folderish = False
    pair.local_digest = None
    pair.remote_name = "document.txt"
    pair.local_name = "document.txt"
    pair.remote_parent_path = "/Company Home/missing"
    pair.error_count = 0
    processor._is_remote_move = MagicMock(return_value=(False, None))
    processor.remote.is_filtered.return_value = False

    processor._synchronize_remotely_modified(pair)

    processor.engine.queue_manager.push_error.assert_called_once_with(
        pair, exception=None, interval=None
    )


def test_remote_move_with_already_matching_target_synchronizes(processor):
    pair = MagicMock()
    pair.folderish = False
    pair.local_digest = None
    pair.local_name = "document.txt"
    pair.remote_name = "document.txt"
    pair.local_path = Path("sync/new-parent/document.txt")
    pair.remote_parent_path = "/Company Home/new-parent"
    pair.is_readonly.return_value = False
    parent = MagicMock()
    parent.local_path = Path("sync/new-parent")
    processor._is_remote_move = MagicMock(return_value=(True, parent))
    processor.remote.is_filtered.return_value = False

    processor._synchronize_remotely_modified(pair)

    assert processor.dao.synchronize_state.call_count == 2
    processor.local.move.assert_not_called()


def test_remote_update_renames_download_and_preserves_remote_xattr(processor, tmp_path):
    pair = MagicMock()
    pair.id = 9
    pair.local_path = Path("sync/old-name.txt")
    pair.local_parent_path = Path("sync")
    pair.remote_name = "new-name.txt"
    pair.remote_ref = "document-id"
    pair.last_remote_updated = "2026-08-01 12:00:00"
    old_os_path = tmp_path / "old-name.txt"
    temporary_path = tmp_path / "transfer" / "new-name.txt"
    processor.local.abspath.return_value = old_os_path
    processor._download_content = MagicMock(return_value=temporary_path)
    processor.local.get_remote_id.return_value = "document-id"
    updated_info = MagicMock()
    updated_info.filepath = tmp_path / "new-name.txt"
    updated_info.get_digest.return_value = "new-digest"
    processor.local.move.return_value = updated_info
    processor.remote.get_fs_info.return_value = MagicMock()

    processor._update_remotely(pair, True)

    processor._download_content.assert_called_once_with(pair, tmp_path / "new-name.txt")
    processor.local.set_remote_id.assert_called_once_with(temporary_path, "document-id")
    assert pair.local_digest == "new-digest"


def test_remote_folder_delete_balances_folder_lock(processor):
    pair = MagicMock()
    pair.local_path = Path("sync/old-folder")
    pair.remote_ref = "folder-id"
    pair.local_state = "synchronized"
    pair.folderish = True
    processor.local.get_remote_id.return_value = "folder-id"
    processor.engine.use_trash.return_value = False

    processor._synchronize_remotely_deleted(pair)

    processor.engine.set_local_folder_lock.assert_called_once_with(pair.local_path)
    processor.local.delete_final.assert_called_once_with(pair.local_path)
    processor.engine.release_folder_lock.assert_called_once_with()


@pytest.mark.parametrize(
    "tmp_result, expected_error",
    [
        pytest.param((True, False), False, id="ignore-immediately"),
        pytest.param((True, True), True, id="delay-on-first-pass"),
    ],
)
def test_generated_local_file_is_ignored_or_delayed(
    processor, tmp_result, expected_error
):
    pair = MagicMock()
    pair.local_path = Path("sync/generated.tmp")
    pair.folderish = False
    pair.error_count = 0

    with patch(
        "nxdrive.alfresco.engine.processor.is_generated_tmp_file",
        return_value=tmp_result,
    ):
        processor._synchronize_locally_created(pair)

    if expected_error:
        processor.dao.increase_error.assert_called_once_with(
            pair, "Can be a temporary file", details=None
        )
    else:
        processor.dao.increase_error.assert_not_called()
    processor.dao.get_state_from_local.assert_not_called()


def test_local_folder_create_recovers_parent_from_xattr(processor):
    pair = MagicMock()
    pair.id = 11
    pair.local_path = Path("sync/new-folder")
    pair.local_parent_path = Path("sync")
    pair.local_name = "new-folder"
    pair.folderish = True
    parent = MagicMock()
    parent.remote_ref = "parent-id"
    parent.remote_can_create_child = True
    parent.remote_name = "Company Home"
    parent.remote_parent_path = ""
    processor.dao.get_state_from_local.return_value = None
    processor.local.exists.return_value = True
    processor.local.get_remote_id.return_value = "parent-id"
    processor._get_normal_state_from_remote_ref = MagicMock(return_value=parent)
    processor.remote.get_fs_info.return_value = MagicMock(path="/Company Home")
    remote_info = MagicMock(uid="new-folder-id", digest=None)
    processor.remote.make_folder.return_value = remote_info

    processor._synchronize_locally_created(pair)

    processor._get_normal_state_from_remote_ref.assert_called_once_with("parent-id")
    processor.remote.make_folder.assert_called_once_with("parent-id", "new-folder")
    processor.dao.synchronize_state.assert_called_once_with(pair)


def test_local_create_postpones_when_digest_remains_inaccessible(processor):
    pair = MagicMock()
    pair.local_path = Path("sync/document.txt")
    pair.local_parent_path = Path("sync")
    pair.local_name = "document.txt"
    pair.local_digest = UNACCESSIBLE_HASH
    pair.folderish = False
    pair.error_count = 0
    parent = MagicMock()
    parent.remote_ref = "parent-id"
    parent.remote_can_create_child = True
    parent.remote_name = "Company Home"
    parent.remote_parent_path = ""
    processor.dao.get_state_from_local.return_value = parent
    local_info = MagicMock()
    local_info.get_digest.return_value = UNACCESSIBLE_HASH
    processor.local.get_info.return_value = local_info

    processor._synchronize_locally_created(pair)

    processor.dao.update_local_state.assert_called_once_with(
        pair, local_info, versioned=False, queue=False
    )
    processor.engine.queue_manager.push_error.assert_called_once_with(
        pair, exception=None, interval=None
    )
    processor.remote.stream_file.assert_not_called()


@pytest.mark.parametrize("digest", [UNACCESSIBLE_HASH, "readable-digest"])
def test_local_modify_refreshes_an_inaccessible_digest(processor, digest):
    pair = MagicMock()
    pair.id = 12
    pair.local_path = Path("sync/document.txt")
    pair.local_name = "document.txt"
    pair.local_digest = UNACCESSIBLE_HASH
    pair.remote_digest = "readable-digest"
    pair.remote_ref = "document-id"
    pair.remote_name = "document.txt"
    pair.remote_can_update = True
    pair.error_count = 0
    local_info = MagicMock()
    local_info.get_digest.return_value = digest
    processor.local.get_info.return_value = local_info
    processor.local.is_equal_digests.return_value = True
    processor.remote.get_fs_info.return_value = MagicMock()

    processor._synchronize_locally_modified(pair)

    if digest == UNACCESSIBLE_HASH:
        processor.engine.queue_manager.push_error.assert_called_once_with(
            pair, exception=None, interval=None
        )
        processor.dao.update_local_state.assert_not_called()
    else:
        processor.dao.update_local_state.assert_called_once_with(
            pair, local_info, versioned=False, queue=False
        )
        processor.dao.synchronize_state.assert_called_once_with(pair)


def test_readonly_local_delete_retries_when_remote_path_lookup_fails(processor):
    pair = MagicMock()
    pair.remote_ref = "document-id"
    pair.remote_can_delete = False
    pair.local_path = Path("sync/document.txt")
    processor.remote.get_fs_info.side_effect = RuntimeError("temporary failure")

    processor._synchronize_locally_deleted(pair)

    processor.dao.remove_state.assert_not_called()
    processor.dao.add_filter.assert_not_called()


def test_local_move_without_known_parent_raises_parent_not_synced(processor):
    pair = MagicMock()
    pair.local_path = Path("sync/missing/document.txt")
    pair.local_parent_path = Path("sync/missing")
    processor.local.get_remote_id.return_value = None
    processor.dao.get_state_from_local.return_value = None

    with pytest.raises(ParentNotSynced):
        processor._synchronize_locally_moved(pair)
