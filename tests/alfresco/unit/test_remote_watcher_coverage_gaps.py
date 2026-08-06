"""Targeted coverage tests for Alfresco remote watcher edge branches."""

from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.alfresco.engine.watcher.remote_watcher import AlfrescoRemoteWatcher
from nxdrive.drive.constants import ROOT
from nxdrive.drive.exceptions import ThreadInterrupt


def _watcher():
    engine = MagicMock()
    dao = MagicMock()
    dao.get_config.return_value = None
    with patch.object(AlfrescoRemoteWatcher, "__init__", return_value=None):
        watcher = AlfrescoRemoteWatcher(engine, dao)
    watcher.engine = engine
    watcher.dao = dao
    watcher._next_check = 0
    watcher._last_remote_full_scan = None
    watcher._interact = MagicMock()
    watcher.remoteScanFinished = MagicMock()
    watcher.remoteWatcherStopped = MagicMock()
    watcher.updated = MagicMock()
    watcher.initiate = MagicMock()
    watcher.empty_polls = 0
    return watcher


def _pair(name, path, **overrides):
    pair = MagicMock()
    pair.local_name = name
    pair.local_path = PurePosixPath(path)
    pair.remote_ref = overrides.get("remote_ref", f"remote-{name}")
    pair.remote_parent_path = overrides.get("remote_parent_path", "")
    pair.pair_state = overrides.get("pair_state", "synchronized")
    pair.processor = overrides.get("processor", 0)
    pair.local_digest = overrides.get("local_digest", "old-digest")
    pair.last_remote_updated = overrides.get(
        "last_remote_updated", "2026-08-01 10:00:00"
    )
    return pair


def _local_info(path, *, folderish=False, digest="new-digest"):
    info = MagicMock()
    info.path = PurePosixPath(path)
    info.folderish = folderish
    info.get_digest.return_value = digest
    return info


def test_execute_completes_poll_then_interacts_before_interrupting():
    watcher = _watcher()
    watcher._next_check = 0
    watcher._handle_changes = MagicMock()
    watcher._interact = MagicMock(side_effect=ThreadInterrupt())

    with patch(
        "nxdrive.alfresco.engine.watcher.remote_watcher.monotonic",
        return_value=10.0,
    ), patch("nxdrive.alfresco.engine.watcher.remote_watcher.Options") as options:
        options.delay = 7
        with pytest.raises(ThreadInterrupt):
            watcher._execute()

    watcher._handle_changes.assert_called_once_with(True)
    assert watcher._next_check == 17.0
    watcher._interact.assert_called_once_with()
    watcher.remoteWatcherStopped.emit.assert_called_once_with()


def test_scan_remote_handles_unexpected_root_fetch_error():
    watcher = _watcher()
    watcher.engine.download_dir = PurePosixPath("/")
    root = _pair("root", "/", remote_ref="root-id")
    watcher.dao.get_state_from_local.return_value = root
    watcher.engine.remote.get_node.side_effect = ValueError("bad payload")

    watcher.scan_remote()

    watcher.remoteScanFinished.emit.assert_not_called()
    watcher.dao.update_config.assert_not_called()


def test_handle_changes_ignores_local_scan_failure_and_finishes_poll():
    watcher = _watcher()
    watcher.engine.remote = MagicMock()
    watcher.engine.queue_manager.get_overall_size.return_value = 0
    watcher.scan_remote = MagicMock()
    watcher._scan_local_changes = MagicMock(side_effect=OSError("unreadable"))

    watcher._handle_changes(first_pass=False)

    watcher.updated.emit.assert_called_once_with()
    watcher.engine._check_last_sync.assert_called_once_with()


def test_remote_recursive_formats_string_timestamp():
    watcher = _watcher()
    remote = MagicMock()
    watcher.engine.remote = remote
    node = MagicMock()
    remote.client.nodes.iter_children.return_value = [node]
    child_info = MagicMock()
    child_info.uid = "child-id"
    child_info.name = "document.txt"
    child_info.path = "/Company Home/document.txt"
    child_info.folderish = False
    child_info.last_modification_time = "2026-08-02 12:34:56.123+00:00"
    remote._node_to_remote_file_info.return_value = child_info
    existing = _pair(
        "document.txt",
        "/document.txt",
        remote_ref="child-id",
        last_remote_updated="2026-08-01 10:00:00",
    )
    watcher.dao.get_remote_children.return_value = [existing]
    watcher.dao.is_filter.return_value = False
    parent = _pair("root", "/", remote_ref="root-id")
    parent_info = MagicMock(folderish=True, uid="root-id")

    watcher._scan_remote_recursive(parent, parent_info)

    watcher.dao.force_remote.assert_called_once_with(existing)


def test_existing_remote_folder_is_recursed_into():
    watcher = _watcher()
    remote = MagicMock()
    watcher.engine.remote = remote
    node = MagicMock()
    remote.client.nodes.iter_children.return_value = [node]
    child_info = MagicMock()
    child_info.uid = "folder-id"
    child_info.name = "folder"
    child_info.path = "/Company Home/folder"
    child_info.folderish = True
    child_info.last_modification_time = "2026-08-01 10:00:00"
    remote._node_to_remote_file_info.return_value = child_info
    existing = _pair("folder", "/folder", remote_ref="folder-id")
    watcher.dao.get_remote_children.return_value = [existing]
    watcher.dao.is_filter.return_value = False
    parent = _pair("root", "/", remote_ref="root-id")
    parent_info = MagicMock(folderish=True, uid="root-id")
    original = AlfrescoRemoteWatcher._scan_remote_recursive

    with patch.object(watcher, "_scan_remote_recursive") as recurse:
        recurse.side_effect = lambda pair, info: original(watcher, pair, info)
        remote.client.nodes.iter_children.side_effect = [[node], []]
        watcher.dao.get_remote_children.side_effect = [[existing], []]
        watcher._scan_remote_recursive(parent, parent_info)

    assert recurse.call_count == 2
    recurse.assert_any_call(existing, child_info)


def test_queued_folder_is_still_scanned_recursively():
    watcher = _watcher()
    local = MagicMock()
    dao = MagicMock()
    folder_info = _local_info("/queued", folderish=True)
    local.get_children_info.side_effect = [[folder_info], []]
    local.is_ignored.return_value = False
    local.get_remote_id.return_value = "folder-id"
    queued = _pair("queued", "/queued", pair_state="locally_modified")
    dao.get_local_children.side_effect = [[queued], []]

    watcher._scan_local_recursive(ROOT, local, dao, set(), [])

    assert local.get_children_info.call_count == 2
    dao.update_local_state.assert_not_called()


def test_processing_folder_is_still_scanned_recursively():
    watcher = _watcher()
    local = MagicMock()
    dao = MagicMock()
    folder_info = _local_info("/processing", folderish=True)
    local.get_children_info.side_effect = [[folder_info], []]
    local.is_ignored.return_value = False
    local.get_remote_id.return_value = "folder-id"
    processing = _pair("processing", "/processing", processor=5)
    dao.get_local_children.side_effect = [[processing], []]

    watcher._scan_local_recursive(ROOT, local, dao, set(), [])

    assert local.get_children_info.call_count == 2
    dao.update_local_state.assert_not_called()


def test_digest_failure_skips_update_and_continues_with_next_file():
    watcher = _watcher()
    local = MagicMock()
    dao = MagicMock()
    bad_info = _local_info("/bad.txt")
    bad_info.get_digest.side_effect = PermissionError("locked")
    good_info = _local_info("/good.txt", digest="new-good")
    local.get_children_info.return_value = [bad_info, good_info]
    local.is_ignored.return_value = False
    local.get_remote_id.side_effect = ["bad-id", "good-id"]
    bad_pair = _pair("bad.txt", "/bad.txt", local_digest="old-bad")
    good_pair = _pair("good.txt", "/good.txt", local_digest="old-good")
    dao.get_local_children.return_value = [bad_pair, good_pair]

    watcher._scan_local_recursive(ROOT, local, dao, set(), [])

    dao.update_local_state.assert_called_once_with(good_pair, good_info)
    assert good_pair.local_digest == "new-good"


def test_synchronized_folder_is_scanned_recursively():
    watcher = _watcher()
    local = MagicMock()
    dao = MagicMock()
    folder_info = _local_info("/folder", folderish=True)
    nested_info = _local_info("/folder/nested.txt")
    local.get_children_info.side_effect = [[folder_info], [nested_info]]
    local.is_ignored.return_value = False
    local.get_remote_id.side_effect = ["folder-id", None]
    folder_pair = _pair("folder", "/folder")
    dao.get_local_children.side_effect = [[folder_pair], []]

    watcher._scan_local_recursive(ROOT, local, dao, set(), [])

    dao.insert_local_state.assert_called_once_with(
        nested_info, PurePosixPath("/folder")
    )


def test_new_folder_is_inserted_and_scanned_recursively():
    watcher = _watcher()
    local = MagicMock()
    dao = MagicMock()
    folder_info = _local_info("/new-folder", folderish=True)
    nested_info = _local_info("/new-folder/nested.txt")
    local.get_children_info.side_effect = [[folder_info], [nested_info]]
    local.is_ignored.return_value = False
    local.get_remote_id.return_value = None
    dao.get_local_children.return_value = []

    watcher._scan_local_recursive(ROOT, local, dao, set(), [])

    assert dao.insert_local_state.call_count == 2
    dao.insert_local_state.assert_any_call(folder_info, ROOT)
    dao.insert_local_state.assert_any_call(nested_info, PurePosixPath("/new-folder"))
