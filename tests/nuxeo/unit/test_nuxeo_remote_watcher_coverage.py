"""Deterministic unit coverage for the Nuxeo remote watcher."""

from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, patch

import pytest
from nuxeo.exceptions import BadQuery, HTTPError, Unauthorized

from nxdrive.drive.constants import ROOT, WORKSPACE_ROOT
from nxdrive.drive.engine.watcher.remote_watcher_base import RemoteWatcherBase
from nxdrive.drive.exceptions import NotFound, ScrollDescendantsError, ThreadInterrupt
from nxdrive.drive.feature import Feature
from nxdrive.drive.objects import RemoteFileInfo
from nxdrive.drive.utils import safe_filename
from nxdrive.nuxeo.engine.watcher.constants import (
    DELETED_EVENT,
    DOCUMENT_LOCKED,
    DOCUMENT_MOVED,
    ROOT_REGISTERED,
    SECURITY_UPDATED_EVENT,
)
from nxdrive.nuxeo.engine.watcher.remote_watcher import (
    COLLECTION_SYNC_ROOT_FACTORY_NAME,
    RemoteWatcher,
)

MODULE = "nxdrive.nuxeo.engine.watcher.remote_watcher"


def _signal() -> MagicMock:
    signal = MagicMock()
    signal.emit = Mock()
    return signal


def _pair(**overrides):
    values = {
        "id": 1,
        "local_path": Path("/sync/folder"),
        "local_parent_path": Path("/sync"),
        "local_digest": "digest",
        "local_state": "synchronized",
        "remote_ref": "uid-1",
        "remote_parent_ref": "parent-uid",
        "remote_parent_path": "/root",
        "remote_name": "folder",
        "remote_digest": "digest",
        "remote_can_delete": True,
        "remote_can_rename": True,
        "remote_can_update": True,
        "remote_can_create_child": True,
        "remote_state": "synchronized",
        "pair_state": "synchronized",
        "folderish": True,
        "last_error": None,
        "last_remote_updated": None,
        "version": 3,
        "readonly": False,
    }
    values.update(overrides)
    pair = SimpleNamespace(**values)
    pair.is_readonly = Mock(side_effect=lambda: pair.readonly)
    return pair


def _info(**overrides) -> RemoteFileInfo:
    values = {
        "name": "folder",
        "uid": "uid-1",
        "parent_uid": "parent-uid",
        "path": "/root/uid-1",
        "folderish": True,
        "last_modification_time": None,
        "creation_time": None,
        "last_contributor": "user",
        "digest": "digest",
        "digest_algorithm": "md5",
        "download_url": None,
        "can_rename": True,
        "can_delete": True,
        "can_update": True,
        "can_create_child": True,
        "lock_owner": None,
        "lock_created": None,
        "can_scroll_descendants": True,
    }
    values.update(overrides)
    return RemoteFileInfo(**values)


def _watcher() -> RemoteWatcher:
    watcher = RemoteWatcher.__new__(RemoteWatcher)
    watcher.dao = MagicMock()
    watcher.dao.get_states_from_remote.return_value = []
    watcher.dao.get_first_state_from_partial_remote.return_value = None
    watcher.dao.get_state_from_id.return_value = None
    watcher.dao.is_filter.return_value = False
    watcher.dao.is_path_scanned.return_value = False

    remote = MagicMock()
    remote.is_sync_root.return_value = False
    local = MagicMock()
    local.exists.return_value = False
    local.is_ignored.return_value = False
    local.abspath.side_effect = lambda path: Path("/absolute") / Path(path).name
    osi = MagicMock()
    engine = SimpleNamespace(
        remote=remote,
        local=local,
        manager=SimpleNamespace(osi=osi),
        local_folder=Path("/sync"),
        send_metric=Mock(),
        stop_processor_on=Mock(),
        is_offline=Mock(return_value=False),
        set_offline=Mock(),
        set_invalid_credentials=Mock(),
    )
    watcher.engine = engine

    watcher._last_sync_date = 0
    watcher._last_event_log_id = 0
    watcher._last_root_definitions = ""
    watcher._last_remote_full_scan = None
    watcher._next_check = 30
    watcher._metrics = {}
    watcher.empty_polls = 0
    watcher._interact = Mock()
    watcher.remove_void_transfers = Mock()
    watcher.initiate = _signal()
    watcher.updated = _signal()
    watcher.remoteScanFinished = _signal()
    watcher.changesFound = _signal()
    watcher.noChangesFound = _signal()
    return watcher


def test_init_and_metrics_restore_persisted_state():
    dao = MagicMock()
    dao.get_int.side_effect = [123, 456]
    full_scan = datetime(2026, 1, 2, tzinfo=timezone.utc)
    dao.get_config.side_effect = ["root-definitions", full_scan]
    engine = MagicMock()

    watcher = RemoteWatcher(engine, dao)
    assert watcher._last_sync_date == 123
    assert watcher._last_event_log_id == 456
    assert watcher._last_root_definitions == "root-definitions"
    assert watcher._last_remote_full_scan == full_scan

    watcher._next_check = 9
    with patch.object(RemoteWatcherBase, "get_metrics", return_value={"polls": 2}):
        metrics = watcher.get_metrics()

    assert metrics == {
        "polls": 2,
        "last_remote_sync_date": 123,
        "last_event_log_id": 456,
        "last_root_definitions": "root-definitions",
        "last_remote_full_scan": full_scan,
        "next_polling": 9,
    }


def test_scan_remote_persists_completion_and_removes_void_transfers():
    watcher = _watcher()
    root_pair = _pair(remote_ref="root", remote_parent_path="")
    remote_info = _info(uid="root", path="/root")
    watcher.dao.get_state_from_local.return_value = root_pair
    watcher.engine.remote.get_fs_info.return_value = remote_info
    watcher.dao.update_remote_state.return_value = True
    watcher._get_changes = Mock()
    watcher._do_scan_remote = Mock()

    watcher.scan_remote()

    watcher.dao.get_state_from_local.assert_called_once_with(ROOT)
    watcher.dao.update_remote_state.assert_called_once_with(
        root_pair, remote_info, remote_parent_path=""
    )
    watcher.remove_void_transfers.assert_called_once_with(root_pair)
    watcher._get_changes.assert_called_once_with()
    watcher._do_scan_remote.assert_called_once_with(root_pair, remote_info)
    assert watcher._last_remote_full_scan.tzinfo == timezone.utc
    watcher.dao.update_config.assert_called_once_with(
        "remote_last_full_scan", watcher._last_remote_full_scan
    )
    watcher.dao.clean_scanned.assert_called_once_with()
    watcher.remoteScanFinished.emit.assert_called_once_with()


def test_scan_remote_stops_without_root_or_when_remote_is_missing():
    watcher = _watcher()
    watcher.dao.get_state_from_local.return_value = None
    watcher.scan_remote()
    watcher.engine.remote.get_fs_info.assert_not_called()

    root_pair = _pair()
    watcher.engine.remote.get_fs_info.side_effect = NotFound("gone")
    watcher.scan_remote(from_state=root_pair)
    watcher.dao.clean_scanned.assert_not_called()


def test_scan_pair_enqueues_path_and_internal_scan_handles_early_returns():
    watcher = _watcher()
    watcher.scan_pair("/parent/child")
    watcher.dao.add_path_to_scan.assert_called_once_with("/parent/child")
    assert watcher._next_check == 0

    watcher._scan_pair(None)
    watcher.dao.is_filter.return_value = True
    watcher._scan_pair("/parent/child")
    watcher.engine.remote.get_fs_info.assert_not_called()

    watcher.dao.is_filter.return_value = False
    watcher.engine.remote.get_fs_info.side_effect = NotFound("deleted")
    watcher._scan_pair("/parent/child")


def test_scan_pair_normalizes_windows_remote_path():
    watcher = _watcher()

    watcher.scan_pair(PureWindowsPath("/parent/child"))

    watcher.dao.add_path_to_scan.assert_called_once_with("/parent/child")


def test_internal_scan_pair_updates_existing_or_inserts_new_folder():
    watcher = _watcher()
    child_info = _info(uid="child", path="/parent/child")
    watcher.engine.remote.get_fs_info.return_value = child_info
    existing = _pair(remote_ref="child")
    watcher.dao.get_state_from_remote_with_path.return_value = existing
    watcher._do_scan_remote = Mock()

    watcher._scan_pair("/parent/child/")
    watcher._do_scan_remote.assert_called_once_with(existing, child_info)

    watcher.dao.reset_mock()
    watcher._do_scan_remote.reset_mock()
    watcher.engine.remote.get_fs_info.return_value = child_info
    parent = _pair(
        local_path=Path("/sync/parent"),
        remote_ref="parent",
        remote_parent_path="",
    )
    created = _pair(remote_ref="child")
    watcher.dao.get_state_from_remote_with_path.side_effect = [None, parent]
    watcher.dao.insert_remote_state.return_value = 99
    watcher.dao.get_state_from_id.return_value = created
    watcher._do_scan_remote = Mock()

    watcher._scan_pair("/parent/child")

    watcher.dao.insert_remote_state.assert_called_once_with(
        child_info,
        "/parent",
        Path("/sync/parent/folder"),
        Path("/sync/parent"),
    )
    watcher.dao.get_state_from_id.assert_called_once_with(99, from_write=True)
    watcher._do_scan_remote.assert_called_once_with(created, child_info)


def test_internal_scan_pair_handles_missing_parent_and_wrong_remote_path():
    watcher = _watcher()
    child_info = _info(uid="child", path="/elsewhere/child")
    watcher.engine.remote.get_fs_info.return_value = child_info
    watcher.dao.get_state_from_remote_with_path.side_effect = [None, None]
    watcher._scan_pair("/parent/child")
    watcher.dao.insert_remote_state.assert_not_called()

    watcher.dao.get_state_from_remote_with_path.side_effect = [None, _pair()]
    watcher.scan_remote = Mock()
    watcher._scan_pair("/parent/child")
    watcher.scan_remote.assert_called_once_with()


def test_check_modified_and_scan_strategy_routing():
    pair = _pair()
    unchanged = _info()
    assert RemoteWatcher._check_modified(pair, unchanged) is False
    assert RemoteWatcher._check_modified(pair, _info(name="renamed")) is True

    watcher = _watcher()
    watcher._scan_remote_scroll = Mock()
    watcher._scan_remote_recursive = Mock()
    watcher._do_scan_remote(pair, _info(can_scroll_descendants=True), moved=True)
    watcher._scan_remote_scroll.assert_called_once_with(
        pair, _info(can_scroll_descendants=True), moved=True
    )

    non_scroll = _info(can_scroll_descendants=False)
    watcher._do_scan_remote(pair, non_scroll, force_recursion=False)
    watcher._scan_remote_recursive.assert_called_once_with(
        pair, non_scroll, force_recursion=False
    )


def test_scroll_scan_updates_creates_postpones_filters_and_deletes():
    watcher = _watcher()
    root_pair = _pair(remote_ref="root")
    root_info = _info(uid="root", name="root")
    existing = _pair(id=2, remote_ref="existing", remote_name="old")
    stale = _pair(id=3, remote_ref="stale", local_path=Path("/sync/stale"))
    parent = _pair(id=4, remote_ref="parent")
    watcher._init_scan_remote = Mock(return_value="/root")
    watcher.dao.get_remote_descendants.return_value = [existing, stale]
    watcher.dao.update_remote_state.return_value = True
    watcher._check_modified = Mock(return_value=True)
    watcher._find_remote_child_match_or_create = Mock()

    banned = _info(uid="banned", name="banned", path="/root/banned")
    filtered = _info(uid="filtered", name="filtered", path="/root/filtered")
    no_binary = _info(
        uid="no-binary",
        name="no-binary",
        path="/root/no-binary",
        digest="notInBinaryStore",
        folderish=False,
    )
    existing_info = _info(
        uid="existing", name="existing", path="/root/existing", folderish=False
    )
    created = _info(
        uid="created", name="created", path="/root/created", parent_uid="parent"
    )
    late = _info(uid="late", name="late", path="/root/late", parent_uid="late-parent")
    missing = _info(
        uid="missing", name="missing", path="/root/missing", parent_uid="missing-parent"
    )
    watcher.filtered = Mock(side_effect=lambda item: item.uid == "banned")
    watcher.dao.is_filter.side_effect = lambda path: path.endswith("/filtered")

    parent_lookups = {"late-parent": 0}

    def get_parent(uid):
        if uid == "parent":
            return parent
        if uid == "late-parent":
            parent_lookups[uid] += 1
            return None if parent_lookups[uid] == 1 else parent
        return None

    watcher.dao.get_normal_state_from_remote.side_effect = get_parent
    watcher.engine.remote.scroll_descendants.side_effect = [
        {
            "descendants": [
                missing,
                existing_info,
                filtered,
                late,
                no_binary,
                created,
                banned,
            ],
            "scroll_id": "next",
        },
        {"descendants": [], "scroll_id": "next"},
    ]

    watcher._scan_remote_scroll(root_pair, root_info)

    assert existing.remote_state == "modified"
    watcher.dao.update_remote_state.assert_called_once_with(existing, existing_info)
    watcher.remove_void_transfers.assert_any_call(existing)
    watcher.engine.send_metric.assert_called_once_with(
        "sync", "skip", "notInBinaryStore"
    )
    assert watcher._find_remote_child_match_or_create.call_args_list == [
        call(parent, created),
        call(parent, late),
    ]
    watcher.dao.delete_remote_state.assert_called_once_with(stale)
    watcher.remove_void_transfers.assert_any_call(stale)
    watcher._interact.assert_called_once_with()


def test_scroll_scan_uses_moved_descendants_and_stops_when_unscannable():
    watcher = _watcher()
    pair = _pair(remote_ref="root")
    info = _info(uid="root")
    watcher._init_scan_remote = Mock(return_value=None)
    watcher._scan_remote_scroll(pair, info, moved=True)
    watcher.dao.get_remote_descendants_from_ref.assert_not_called()

    watcher._init_scan_remote.return_value = "/root"
    watcher.dao.get_remote_descendants_from_ref.return_value = []
    watcher.engine.remote.scroll_descendants.return_value = {
        "descendants": [],
        "scroll_id": None,
    }
    watcher._scan_remote_scroll(pair, info, moved=True)
    watcher.dao.get_remote_descendants_from_ref.assert_called_once_with("root")


def test_recursive_scan_aligns_children_recurses_and_deletes_stale_pairs():
    watcher = _watcher()
    root_pair = _pair(remote_ref="root")
    root_info = _info(uid="root")
    existing_uid = f"{WORKSPACE_ROOT}#existing"
    existing = _pair(id=2, remote_ref=existing_uid, remote_name="old")
    stale = _pair(id=3, remote_ref="stale", local_path=Path("/sync/stale"))
    existing_info = _info(
        uid=existing_uid, name="existing", path=f"/root/{existing_uid}"
    )
    expanded_info = _info(
        uid=existing_uid, name="expanded", path=f"/root/{existing_uid}"
    )
    new_info = _info(uid="new-folder", name="new", path="/root/new-folder")
    new_pair = _pair(id=4, remote_ref="new-folder")
    orphan = _info(uid="orphan", name="orphan", path="/root/orphan")
    banned = _info(uid="banned", name="banned", path="/root/banned")
    no_binary = _info(
        uid="no-binary",
        name="no-binary",
        path="/root/no-binary",
        folderish=False,
        digest="notInBinaryStore",
    )

    watcher._init_scan_remote = Mock(return_value="/root")
    watcher.dao.get_remote_children.return_value = [existing, stale]
    watcher.engine.remote.get_fs_children.return_value = [
        banned,
        no_binary,
        existing_info,
        new_info,
        orphan,
    ]
    watcher.filtered = Mock(side_effect=lambda item: item.uid == "banned")
    watcher.engine.remote.expand_sync_root_name.return_value = expanded_info
    watcher._check_modified = Mock(return_value=True)
    watcher.dao.update_remote_state.return_value = True
    watcher._find_remote_child_match_or_create = Mock(
        side_effect=[(new_pair, True), None]
    )
    watcher._do_scan_remote = Mock()

    watcher._scan_remote_recursive(root_pair, root_info, force_recursion=True)

    watcher._interact.assert_called_once_with()
    watcher.engine.remote.expand_sync_root_name.assert_called_once_with(existing_info)
    assert existing.remote_state == "modified"
    watcher.dao.update_remote_state.assert_called_once_with(
        existing, expanded_info, remote_parent_path="/root"
    )
    watcher.remove_void_transfers.assert_any_call(existing)
    watcher.dao.delete_remote_state.assert_called_once_with(stale)
    watcher.remove_void_transfers.assert_any_call(stale)
    assert watcher._do_scan_remote.call_args_list == [
        call(existing, expanded_info, force_recursion=True),
        call(new_pair, new_info, force_recursion=True),
    ]
    watcher.dao.add_path_scanned.assert_called_once_with("/root")


def test_recursive_scan_stops_when_initialization_declines():
    watcher = _watcher()
    watcher._init_scan_remote = Mock(return_value=None)
    watcher._scan_remote_recursive(_pair(), _info())
    watcher._interact.assert_not_called()


def test_init_scan_remote_validates_folder_and_scan_state():
    watcher = _watcher()
    pair = _pair(remote_parent_path="/parent", local_path=Path("/sync/folder"))
    with pytest.raises(ValueError, match="missing remote info"):
        watcher._init_scan_remote(pair, None)
    assert watcher._init_scan_remote(pair, _info(folderish=False)) is None

    watcher.dao.is_path_scanned.return_value = True
    assert watcher._init_scan_remote(pair, _info(uid="folder")) is None

    watcher.dao.is_path_scanned.return_value = False
    assert watcher._init_scan_remote(pair, _info(uid="folder")) == "/parent/folder"


def test_find_child_rejects_duplicate_parent_and_existing_remote_pair():
    watcher = _watcher()
    child_info = _info(uid="child")
    assert (
        watcher._find_remote_child_match_or_create(
            _pair(last_error="DEDUP"), child_info
        )
        is None
    )

    watcher.dao.get_normal_state_from_remote.return_value = _pair()
    assert watcher._find_remote_child_match_or_create(_pair(), child_info) is None


def test_find_child_creates_new_remote_state_and_persists_parent_paths():
    watcher = _watcher()
    parent = _pair(
        local_path=Path("/sync/parent"),
        remote_parent_path="/roots",
        remote_ref="parent",
    )
    child_info = _info(uid="child", name="unsafe:name")
    created = _pair(id=77, remote_ref="child")
    watcher.dao.get_normal_state_from_remote.return_value = None
    watcher.dao.get_state_from_local.return_value = None
    watcher.engine.local.exists.return_value = False
    watcher.dao.insert_remote_state.return_value = 77
    watcher.dao.get_state_from_id.return_value = created

    result = watcher._find_remote_child_match_or_create(parent, child_info)

    assert result == (created, True)
    watcher.dao.insert_remote_state.assert_called_once_with(
        child_info,
        "/roots/parent",
        Path("/sync/parent") / safe_filename("unsafe:name"),
        Path("/sync/parent"),
    )
    watcher.dao.get_state_from_id.assert_called_once_with(77, from_write=True)


def test_find_child_detects_local_rename_and_updates_both_states():
    watcher = _watcher()
    parent = _pair(local_path=Path("/sync/parent"), remote_ref="parent")
    child_info = _info(
        uid="child", name="new.txt", folderish=False, digest="same", path="/root/child"
    )
    old_path = Path("/sync/parent/old.txt")
    child_pair = _pair(
        id=22,
        local_path=old_path,
        remote_ref="child",
        folderish=False,
        local_digest="same",
    )
    refreshed = _pair(id=22, local_path=old_path, remote_ref="child", folderish=False)
    watcher.dao.get_normal_state_from_remote.return_value = None
    watcher.dao.get_state_from_local.side_effect = [None, child_pair]
    watcher.engine.local.exists.return_value = True
    watcher.engine.local.get_children_info.return_value = [
        SimpleNamespace(path=old_path)
    ]
    watcher.engine.local.get_remote_id.return_value = "child"
    watcher.engine.local.is_equal_digests.return_value = True
    local_info = SimpleNamespace(path=old_path)
    watcher.engine.local.get_info.return_value = local_info
    watcher.dao.get_state_from_id.return_value = refreshed

    result = watcher._find_remote_child_match_or_create(parent, child_info)

    assert result == (refreshed, False)
    assert child_pair.local_state == "moved"
    assert child_pair.remote_state == "unknown"
    watcher.remove_void_transfers.assert_called_once_with(child_pair)
    watcher.dao.update_local_state.assert_called_once_with(child_pair, local_info)
    watcher.dao.update_remote_state.assert_called_once_with(
        child_pair, child_info, remote_parent_path="/root/parent"
    )


def test_find_child_synchronizes_equal_local_file_and_queues_folder_children():
    watcher = _watcher()
    parent = _pair(local_path=Path("/sync/parent"), remote_ref="parent")
    child_info = _info(uid="child", name="child", folderish=True)
    local_path = Path("/sync/parent/child")
    child_pair = _pair(id=8, local_path=local_path, remote_ref="child", folderish=True)
    refreshed = _pair(id=8, local_path=local_path, remote_ref="child", folderish=True)
    watcher.dao.get_normal_state_from_remote.return_value = None
    watcher.dao.get_state_from_local.return_value = child_pair
    watcher.engine.local.is_equal_digests.return_value = True
    watcher.dao.synchronize_state.return_value = True
    watcher.dao.get_state_from_id.return_value = refreshed

    assert watcher._find_remote_child_match_or_create(parent, child_info) == (
        refreshed,
        False,
    )

    watcher.dao.update_remote_state.assert_called_once_with(
        child_pair, child_info, remote_parent_path="/root/parent"
    )
    watcher.dao.synchronize_state.assert_called_once_with(child_pair, version=4)
    watcher.engine.stop_processor_on.assert_called_once_with(local_path)
    watcher.engine.local.set_remote_id.assert_called_once_with(local_path, "child")
    watcher.dao.queue_children.assert_called_once_with(child_pair)


def test_find_child_rechecks_failed_synchronization_before_marking_synced():
    watcher = _watcher()
    parent = _pair(local_path=Path("/sync/parent"), remote_ref="parent")
    child_info = _info(uid="child", name="child.txt", folderish=False, digest="same")
    local_path = Path("/sync/parent/child.txt")
    child_pair = _pair(
        id=8,
        local_path=local_path,
        remote_ref="child",
        folderish=False,
        local_digest="same",
    )
    first_refresh = _pair(
        id=8,
        local_path=local_path,
        remote_ref="child",
        folderish=False,
        local_digest="same",
        pair_state="unsynchronized",
    )
    synchronized = _pair(
        id=8,
        local_path=local_path,
        remote_ref="child",
        folderish=False,
        pair_state="synchronized",
    )
    returned = _pair(id=8, local_path=local_path, remote_ref="child", folderish=False)
    watcher.dao.get_normal_state_from_remote.return_value = None
    watcher.dao.get_state_from_local.return_value = child_pair
    watcher.engine.local.is_equal_digests.return_value = True
    watcher.dao.synchronize_state.side_effect = [False, None]
    watcher.dao.get_state_from_id.side_effect = [first_refresh, synchronized, returned]

    assert watcher._find_remote_child_match_or_create(parent, child_info) == (
        returned,
        False,
    )
    assert watcher.dao.synchronize_state.call_args_list == [
        call(child_pair, version=4),
        call(first_refresh),
    ]
    watcher.engine.stop_processor_on.assert_called_once_with(local_path)


def test_find_child_marks_digest_conflict_modified_and_handles_different_remote_id():
    watcher = _watcher()
    parent = _pair(local_path=Path("/sync/parent"), remote_ref="parent")
    child_info = _info(uid="child", name="child.txt", folderish=False, digest="new")
    local_path = Path("/sync/parent/child.txt")
    conflict = _pair(
        id=8,
        local_path=local_path,
        remote_ref="child",
        folderish=False,
        local_digest="old",
    )
    refreshed = _pair(id=8, local_path=local_path, remote_ref="child", folderish=False)
    watcher.dao.get_normal_state_from_remote.return_value = None
    watcher.dao.get_state_from_local.return_value = conflict
    watcher.engine.local.is_equal_digests.return_value = False
    watcher.dao.update_remote_state.return_value = True
    watcher.dao.get_state_from_id.return_value = refreshed

    assert watcher._find_remote_child_match_or_create(parent, child_info) == (
        refreshed,
        False,
    )
    assert conflict.remote_state == "modified"
    watcher.remove_void_transfers.assert_called_once_with(conflict)

    different = _pair(local_path=local_path, remote_ref="other")
    created = _pair(id=9, remote_ref="child")
    watcher.dao.reset_mock()
    watcher.dao.get_normal_state_from_remote.return_value = None
    watcher.dao.get_state_from_local.return_value = different
    watcher.dao.insert_remote_state.return_value = 9
    watcher.dao.get_state_from_id.return_value = created
    assert watcher._find_remote_child_match_or_create(parent, child_info) == (
        created,
        True,
    )


def test_readonly_partial_scan_and_offline_state_transitions(monkeypatch):
    watcher = _watcher()
    folder = _pair(folderish=True)
    monkeypatch.setattr(f"{MODULE}.WINDOWS", True)
    watcher._handle_readonly(folder)
    watcher.engine.local.set_readonly.assert_not_called()

    monkeypatch.setattr(f"{MODULE}.WINDOWS", False)
    readonly = _pair(folderish=False, readonly=True)
    watcher._handle_readonly(readonly)
    watcher.engine.local.set_readonly.assert_called_once_with(readonly.local_path)
    writable = _pair(folderish=False, readonly=False)
    watcher._handle_readonly(writable)
    watcher.engine.local.unset_readonly.assert_called_once_with(writable.local_path)

    watcher.scan_remote = Mock()
    watcher._scan_pair = Mock()
    watcher._partial_full_scan("/")
    watcher._partial_full_scan("/root/folder")
    watcher.scan_remote.assert_called_once_with()
    watcher._scan_pair.assert_called_once_with("/root/folder")
    assert watcher.dao.delete_path_to_scan.call_count == 2
    assert watcher.dao.delete_config.call_count == 2
    assert watcher.dao.clean_scanned.call_count == 2

    assert watcher._check_offline() is False
    watcher.engine.is_offline.return_value = True
    watcher.engine.remote.client.is_reachable.return_value = True
    assert watcher._check_offline() is False
    watcher.engine.set_offline.assert_called_once_with(value=False)
    watcher.engine.remote.client.is_reachable.return_value = False
    assert watcher._check_offline() is True


def test_handle_changes_disabled_offline_initial_and_queued_paths(monkeypatch):
    watcher = _watcher()
    monkeypatch.setattr(Feature, "synchronization", False)
    assert watcher._handle_changes(True) is True
    assert watcher._handle_changes(False) is False
    watcher.initiate.emit.assert_called_once_with()
    watcher.updated.emit.assert_called_once_with()

    monkeypatch.setattr(Feature, "synchronization", True)
    watcher._check_offline = Mock(return_value=True)
    assert watcher._handle_changes(False) is False

    watcher._check_offline.return_value = False
    watcher.scan_remote = Mock()
    watcher._last_remote_full_scan = None
    with patch(f"{MODULE}.Action.finish_action") as finish:
        assert watcher._handle_changes(True) is True
    watcher.scan_remote.assert_called_once_with()
    watcher.initiate.emit.assert_called()
    finish.assert_called_once_with()

    watcher._last_remote_full_scan = datetime.now(tz=timezone.utc)
    watcher.dao.get_config.return_value = None
    watcher.dao.get_paths_to_scan.side_effect = [["/one"], []]
    watcher._partial_full_scan = Mock()
    watcher._update_remote_states = Mock()
    with patch(f"{MODULE}.Action.finish_action"):
        assert watcher._handle_changes(False) is True
    watcher._partial_full_scan.assert_called_once_with("/one")
    watcher.dao.update_config.assert_called_with("remote_need_full_scan", "/one")
    watcher._update_remote_states.assert_called_once_with()
    watcher.updated.emit.assert_called()


def test_handle_changes_resumes_pending_full_scan(monkeypatch):
    monkeypatch.setattr(Feature, "synchronization", True)
    watcher = _watcher()
    watcher._last_remote_full_scan = datetime.now(tz=timezone.utc)
    watcher._check_offline = Mock(return_value=False)
    watcher.dao.get_config.return_value = "/pending"
    watcher._partial_full_scan = Mock()
    with patch(f"{MODULE}.Action.finish_action"):
        assert watcher._handle_changes(False) is False
    watcher._partial_full_scan.assert_called_once_with("/pending")


@pytest.mark.parametrize(
    ("error", "credential_error"),
    [
        (ScrollDescendantsError("scroll failed"), False),
        (Unauthorized(), True),
        (HTTPError(status=504, message="gateway"), False),
        (HTTPError(status=500, message="server"), False),
        (OSError("offline"), False),
        (RuntimeError("unexpected"), False),
    ],
)
def test_handle_changes_converts_expected_errors_to_failed_poll(
    monkeypatch, error, credential_error
):
    monkeypatch.setattr(Feature, "synchronization", True)
    watcher = _watcher()
    watcher._check_offline = Mock(return_value=False)
    watcher.scan_remote = Mock(side_effect=error)
    with patch(f"{MODULE}.Action.finish_action") as finish:
        assert watcher._handle_changes(False) is False
    finish.assert_called_once_with()
    if credential_error:
        watcher.engine.set_invalid_credentials.assert_called_once_with()
        watcher.engine.set_offline.assert_called_once_with()


@pytest.mark.parametrize("error", [BadQuery("bad query"), ThreadInterrupt("stop")])
def test_handle_changes_reraises_programming_and_thread_interrupts(monkeypatch, error):
    monkeypatch.setattr(Feature, "synchronization", True)
    watcher = _watcher()
    watcher._check_offline = Mock(return_value=False)
    watcher.scan_remote = Mock(side_effect=error)
    with patch(f"{MODULE}.Action.finish_action"):
        with pytest.raises(type(error)):
            watcher._handle_changes(False)


def test_get_changes_measures_call_and_persists_cursor():
    watcher = _watcher()
    summary = {
        "activeSynchronizationRootDefinitions": "roots",
        "syncDate": "123",
        "upperBound": "456",
        "fileSystemChanges": [],
    }
    watcher.engine.remote.get_changes.return_value = summary
    with patch(f"{MODULE}.monotonic", side_effect=[10.2, 12.0]):
        assert watcher._call_and_measure_gcs() == summary
    watcher.engine.remote.get_changes.assert_called_once_with("", log_id=0)
    watcher.engine.send_metric.assert_called_once_with(
        "operation", "NuxeoDrive.GetChangesSummary", "2"
    )

    watcher._call_and_measure_gcs = Mock(return_value=summary)
    assert watcher._get_changes() == summary
    assert watcher._last_root_definitions == "roots"
    assert watcher._last_sync_date == 123
    assert watcher._last_event_log_id == 456
    assert watcher.dao.store_int.call_args_list == [
        call("remote_last_sync_date", 123),
        call("remote_last_event_log_id", 456),
    ]
    watcher.dao.update_config.assert_called_once_with(
        "remote_last_root_definitions", "roots"
    )


def test_get_changes_rejects_invalid_payloads():
    watcher = _watcher()
    watcher._call_and_measure_gcs = Mock(return_value=[])
    assert watcher._get_changes() is None
    watcher._call_and_measure_gcs.return_value = {
        "activeSynchronizationRootDefinitions": None
    }
    assert watcher._get_changes() is None
    watcher.dao.store_int.assert_not_called()


def test_force_remote_scan_enqueues_or_scans_immediately():
    watcher = _watcher()
    pair = _pair()
    info = _info(path="/remote/path")
    watcher._do_scan_remote = Mock()
    watcher._force_remote_scan(pair, info)
    watcher.dao.add_path_to_scan.assert_called_once_with("/remote/path")

    watcher._force_remote_scan(
        pair,
        info,
        remote_path="/provided",
        force_recursion=False,
        moved=True,
    )
    watcher._do_scan_remote.assert_called_once_with(
        pair, info, force_recursion=False, moved=True
    )


def test_update_remote_states_handles_empty_and_full_scan_summaries():
    watcher = _watcher()
    watcher._get_changes = Mock(return_value=None)
    watcher._update_remote_states()
    watcher.changesFound.emit.assert_not_called()

    watcher._get_changes.return_value = {"hasTooManyChanges": True}
    watcher._update_remote_states()
    watcher.dao.add_path_to_scan.assert_called_once_with("/")
    watcher.dao.update_config.assert_called_once_with("remote_need_full_scan", "/")

    watcher.empty_polls = 4
    watcher._get_changes.return_value = {"fileSystemChanges": []}
    watcher._update_remote_states()
    assert watcher.empty_polls == 5
    watcher.noChangesFound.emit.assert_called_once_with()


def test_update_remote_states_deletes_only_confirmed_top_level_pairs():
    watcher = _watcher()
    dedup = _pair(
        id=1, remote_ref="dedup", local_path=Path("/sync/dup"), last_error="DEDUP"
    )
    parent = _pair(id=2, remote_ref="parent", local_path=Path("/sync/folder"))
    child = _pair(id=3, remote_ref="child", local_path=Path("/sync/folder/child"))
    still_exists = _pair(id=4, remote_ref="still", local_path=Path("/sync/still"))
    security = _pair(id=5, remote_ref="security", local_path=Path("/sync/security"))
    unknown = _pair(id=6, remote_ref="unknown", local_path=Path("/sync/unknown"))
    partial = _pair(id=7, remote_ref="partial", local_path=Path("/sync/partial"))
    pairs = {
        "dedup": [None, dedup],
        "parent": [parent],
        "child": [child],
        "still": [still_exists],
        "security": [security],
        "unknown": [unknown],
        "partial": [],
    }
    events = [
        {"eventDate": 70, "eventId": DELETED_EVENT, "fileSystemItemId": "dedup"},
        {"eventDate": 60, "eventId": DELETED_EVENT, "fileSystemItemId": "parent"},
        {"eventDate": 50, "eventId": DELETED_EVENT, "fileSystemItemId": "child"},
        {"eventDate": 40, "eventId": DELETED_EVENT, "fileSystemItemId": "still"},
        {
            "eventDate": 30,
            "eventId": SECURITY_UPDATED_EVENT,
            "fileSystemItemId": "security",
        },
        {"eventDate": 20, "eventId": "mystery", "fileSystemItemId": "unknown"},
        {"eventDate": 10, "eventId": DELETED_EVENT, "fileSystemItemId": "partial"},
    ]
    watcher._get_changes = Mock(return_value={"fileSystemChanges": events})
    watcher.dao.get_states_from_remote.side_effect = lambda ref: pairs[ref]
    watcher.dao.get_first_state_from_partial_remote.side_effect = lambda ref: (
        partial if ref == "partial" else None
    )
    watcher.dao.get_state_from_id.side_effect = lambda pair_id: next(
        pair
        for pair in [dedup, parent, child, still_exists, security, unknown, partial]
        if pair.id == pair_id
    )
    watcher.engine.remote.get_fs_item.side_effect = lambda ref: (
        object() if ref == "still" else None
    )

    watcher._update_remote_states()

    watcher.dao.remove_state.assert_called_once_with(dedup, remote_recursion=True)
    watcher.dao.delete_remote_state.assert_any_call(security)
    watcher.dao.delete_remote_state.assert_any_call(parent)
    watcher.dao.delete_remote_state.assert_any_call(partial)
    assert call(child) not in watcher.dao.delete_remote_state.call_args_list
    assert call(still_exists) not in watcher.dao.delete_remote_state.call_args_list
    watcher.remove_void_transfers.assert_any_call(dedup)
    watcher.remove_void_transfers.assert_any_call(security)
    assert watcher.engine.manager.osi.send_sync_status.call_count >= 3


def test_update_remote_states_refreshes_security_and_duplicate_rename(monkeypatch):
    watcher = _watcher()
    pair = _pair(
        id=10,
        local_path=Path("/sync/old-name"),
        remote_ref="doc",
        remote_name="old-name",
        remote_digest="old",
        remote_can_create_child=False,
        pair_state="remotely_created",
        folderish=True,
    )
    new_info = _info(
        uid="doc",
        name="new:name",
        parent_uid="parent-uid",
        path="/root/doc",
        digest="new",
        folderish=True,
        can_create_child=True,
    )
    event = {
        "eventDate": 1,
        "eventId": SECURITY_UPDATED_EVENT,
        "fileSystemItemId": "doc",
        "fileSystemItem": {"kind": "security"},
    }
    watcher._get_changes = Mock(return_value={"fileSystemChanges": [event]})
    watcher.dao.get_states_from_remote.return_value = [pair]
    watcher.dao.update_remote_state.return_value = True
    watcher.dao.get_state_from_id.return_value = pair
    watcher._force_remote_scan = Mock()
    monkeypatch.setattr(Path, "exists", lambda self: False)

    with patch.object(RemoteFileInfo, "from_dict", return_value=new_info):
        watcher._update_remote_states()

    assert pair.remote_state == "modified"
    local_update = watcher.dao.update_local_state.call_args
    assert local_update.args[0] is pair
    assert local_update.args[1].path == Path("/sync") / safe_filename("new:name")
    assert local_update.kwargs == {"versioned": False}
    watcher.dao.update_remote_state.assert_called_once_with(
        pair,
        new_info,
        remote_parent_path="/root",
        force_update=False,
    )
    watcher.remove_void_transfers.assert_called_once_with(pair)
    watcher.dao.unset_unsychronised.assert_called_once_with(pair)
    watcher._force_remote_scan.assert_called_once_with(
        pair,
        new_info,
        remote_path="/root/doc",
        force_recursion=True,
        moved=False,
    )
    watcher.engine.manager.osi.send_sync_status.assert_called_once_with(
        pair, Path("/absolute/old-name")
    )


def test_update_remote_states_builds_collection_info_and_handles_lock_error():
    watcher = _watcher()
    pair = _pair(
        id=11,
        remote_ref="doc",
        remote_parent_ref=f"{COLLECTION_SYNC_ROOT_FACTORY_NAME}#collection",
        remote_parent_path="/collection",
        remote_name="doc",
        folderish=True,
    )
    new_info = _info(
        uid="doc",
        name="doc",
        parent_uid="normalFactory#parent",
        path="/normal/doc",
        folderish=True,
    )
    event = {
        "eventDate": 1,
        "eventId": DOCUMENT_LOCKED,
        "fileSystemItemId": "doc",
        "fileSystemItem": {"kind": "lock"},
    }
    watcher._get_changes = Mock(return_value={"fileSystemChanges": [event]})
    watcher.dao.get_states_from_remote.return_value = [pair]
    watcher.dao.update_remote_state.return_value = True
    locked = _pair(id=11, local_path=pair.local_path)
    status = _pair(id=11, local_path=pair.local_path)
    watcher.dao.get_state_from_id.side_effect = [locked, status]
    watcher._force_remote_scan = Mock()
    watcher._handle_readonly = Mock(side_effect=OSError("readonly failed"))

    with patch.object(RemoteFileInfo, "from_dict", return_value=new_info):
        watcher._update_remote_states()

    watcher.dao.update_remote_state.assert_called_once_with(
        pair,
        new_info,
        remote_parent_path="/normal",
        force_update=True,
    )
    force_args = watcher._force_remote_scan.call_args
    consistent_info = force_args.args[1]
    assert consistent_info.parent_uid == pair.remote_parent_ref
    assert consistent_info.path == "/collection/doc"
    assert force_args.args[0] is pair
    assert force_args.kwargs == {
        "remote_path": "/normal/doc",
        "force_recursion": False,
        "moved": False,
    }
    watcher._handle_readonly.assert_called_once_with(locked)


@pytest.mark.parametrize(
    ("pair_parent", "new_parent", "expected_delete"),
    [
        (f"{COLLECTION_SYNC_ROOT_FACTORY_NAME}#old", "normal#parent", False),
        ("normal#old", f"{COLLECTION_SYNC_ROOT_FACTORY_NAME}#parent", True),
    ],
)
def test_update_remote_states_handles_collection_move_edges(
    pair_parent, new_parent, expected_delete
):
    watcher = _watcher()
    pair = _pair(id=20, remote_ref="doc", remote_parent_ref=pair_parent)
    new_info = _info(uid="doc", parent_uid=new_parent, path="/new/doc")
    event = {
        "eventDate": 1,
        "eventId": DOCUMENT_MOVED,
        "fileSystemItemId": "doc",
        "fileSystemItem": {"kind": "move"},
    }
    watcher._get_changes = Mock(return_value={"fileSystemChanges": [event]})

    def states(ref):
        return [pair] if ref == "doc" else []

    watcher.dao.get_states_from_remote.side_effect = states
    watcher.dao.get_state_from_id.return_value = pair
    with patch.object(RemoteFileInfo, "from_dict", return_value=new_info):
        watcher._update_remote_states()

    if expected_delete:
        watcher.dao.delete_remote_state.assert_called_once_with(pair)
        watcher.remove_void_transfers.assert_called_once_with(pair)
    else:
        watcher.dao.delete_remote_state.assert_not_called()
        watcher.dao.update_remote_state.assert_not_called()


def test_update_remote_states_creates_expanded_children_and_skips_noise():
    watcher = _watcher()
    parent = _pair(id=30, remote_ref="parent")
    folder_info = _info(
        uid=f"{WORKSPACE_ROOT}#folder",
        name="folder",
        parent_uid="folder-parent",
        path=f"/root/{WORKSPACE_ROOT}#folder",
        folderish=True,
    )
    file_info = _info(
        uid="prefix#file",
        name="file.txt",
        parent_uid="file-parent",
        path="/root/prefix#file",
        folderish=False,
    )
    sync_root_info = _info(
        uid="sync-root",
        name="sync-root",
        parent_uid="missing-parent",
        path="/root/sync-root",
    )
    ignored_info = _info(
        uid="ignored",
        name="ignored.tmp",
        parent_uid="folder-parent",
        path="/root/ignored",
        folderish=False,
    )
    info_by_kind = {
        "folder": folder_info,
        "file": file_info,
        "sync-root": sync_root_info,
        "ignored": ignored_info,
    }
    events = [
        {
            "eventDate": 100,
            "eventId": "updated",
            "fileSystemItemId": "no-binary",
            "fileSystemItem": {"digest": "notInBinaryStore"},
        },
        {
            "eventDate": 90,
            "eventId": "created",
            "fileSystemItemId": "ignored",
            "fileSystemItem": {"kind": "ignored"},
        },
        {
            "eventDate": 80,
            "eventId": "created",
            "fileSystemItemId": folder_info.uid,
            "fileSystemItem": {"kind": "folder"},
        },
        {
            "eventDate": 70,
            "eventId": ROOT_REGISTERED,
            "fileSystemItemId": file_info.uid,
            "fileSystemItem": {"kind": "file"},
        },
        {
            "eventDate": 60,
            "eventId": "created",
            "fileSystemItemId": sync_root_info.uid,
            "fileSystemItem": {"kind": "sync-root"},
        },
        {
            "eventDate": 50,
            "eventId": "older",
            "fileSystemItemId": "file",
            "fileSystemItem": {"kind": "ignored"},
        },
    ]
    watcher._get_changes = Mock(return_value={"fileSystemChanges": events})
    watcher.engine.remote.is_sync_root.side_effect = (
        lambda item: item.uid == "sync-root"
    )
    watcher.engine.remote.expand_sync_root_name.side_effect = lambda item: item
    watcher.engine.local.is_ignored.side_effect = (
        lambda root, name: name == "ignored.tmp"
    )

    child_ids = {folder_info.uid, file_info.uid, sync_root_info.uid}

    def states(ref):
        if ref in child_ids or ref == "ignored":
            return []
        if ref in {"folder-parent", "file-parent"}:
            return [parent]
        return []

    watcher.dao.get_states_from_remote.side_effect = states
    folder_pair = _pair(id=31, remote_ref=folder_info.uid, folderish=True)
    file_pair = _pair(id=32, remote_ref=file_info.uid, folderish=False)

    def match(_parent, info):
        return (folder_pair, True) if info.folderish else (file_pair, True)

    watcher._find_remote_child_match_or_create = Mock(side_effect=match)
    watcher._force_remote_scan = Mock()

    with patch.object(
        RemoteFileInfo,
        "from_dict",
        side_effect=lambda item: info_by_kind[item["kind"]],
    ):
        watcher._update_remote_states()

    watcher.engine.send_metric.assert_called_once_with(
        "sync", "skip", "notInBinaryStore"
    )
    assert watcher.engine.remote.expand_sync_root_name.call_count == 3
    assert watcher._find_remote_child_match_or_create.call_args_list == [
        call(parent, folder_info),
        call(parent, file_info),
    ]
    watcher._force_remote_scan.assert_called_once_with(
        folder_pair,
        folder_info,
        remote_path=f"{folder_pair.remote_parent_path}/{folder_info.uid}",
    )
    watcher.changesFound.emit.assert_called_once_with(len(events))
    assert watcher.empty_polls == 0


def test_update_remote_states_ignores_delete_event_with_attached_item():
    watcher = _watcher()
    pair = _pair(id=40, remote_ref="doc")
    info = _info(uid="doc")
    event = {
        "eventDate": 1,
        "eventId": DELETED_EVENT,
        "fileSystemItemId": "doc",
        "fileSystemItem": {"kind": "doc"},
    }
    watcher._get_changes = Mock(return_value={"fileSystemChanges": [event]})
    watcher.dao.get_states_from_remote.return_value = [pair]
    with patch.object(RemoteFileInfo, "from_dict", return_value=info):
        watcher._update_remote_states()
    watcher.dao.delete_remote_state.assert_not_called()
    watcher.dao.update_remote_state.assert_not_called()


def test_filtered_only_ignores_non_folder_items_selected_by_local_rules():
    watcher = _watcher()
    watcher.engine.local.is_ignored.side_effect = lambda root, name: name.endswith(
        ".tmp"
    )
    assert watcher.filtered(None) is False
    assert watcher.filtered(_info(name="folder.tmp", folderish=True)) is False
    assert watcher.filtered(_info(name="file.txt", folderish=False)) is False
    assert watcher.filtered(_info(name="file.tmp", folderish=False)) is True
    watcher.engine.local.is_ignored.assert_called_with(ROOT, "file.tmp")
