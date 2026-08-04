"""Focused branch tests for the local filesystem watcher.

The legacy local watcher test module exercises broad happy paths.  These tests
keep each remaining edge case isolated so no observer thread or timing delay is
needed.
"""

import errno
import sqlite3
from datetime import datetime
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest
from watchdog.events import FileCreatedEvent, FileDeletedEvent

from nxdrive.drive.constants import ROOT, UNACCESSIBLE_HASH
from nxdrive.drive.engine.watcher import local_watcher as local_watcher_module
from nxdrive.drive.engine.watcher.local_watcher import (
    DriveFSEventHandler,
    LocalWatcher,
)
from nxdrive.drive.exceptions import ThreadInterrupt


NOW = datetime(2024, 1, 2, 3, 4, 5)


def make_pair(**overrides):
    values = {
        "id": 1,
        "processor": 0,
        "local_path": Path("file.txt"),
        "local_name": "file.txt",
        "remote_ref": "remote-id",
        "remote_name": "file.txt",
        "remote_parent_ref": "parent-id",
        "local_state": "synchronized",
        "remote_state": "synchronized",
        "pair_state": "synchronized",
        "folderish": False,
        "local_digest": "old-digest",
        "last_local_updated": "2024-01-01 00:00:00.000",
        "size": 10,
        "version": 1,
        "remote_can_create_child": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_info(path="file.txt", **overrides):
    path = Path(path)
    digest = overrides.pop("digest", "new-digest")
    values = {
        "path": path,
        "name": path.name,
        "folderish": False,
        "remote_ref": "",
        "last_modification_time": NOW,
        "size": 10,
        "get_digest": Mock(return_value=digest),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_event(event_type, src_path="/sync/file.txt", dest_path=""):
    return SimpleNamespace(
        event_type=event_type,
        src_path=src_path,
        dest_path=dest_path,
        is_directory=False,
    )


@pytest.fixture
def watcher():
    engine = Mock()
    engine.local = Mock()
    engine.manager = Mock()
    engine.manager.osi = Mock()
    engine.queue_manager = Mock()
    engine.queue_manager.is_paused.return_value = True
    engine.newReadonly = Mock()
    engine.remote = Mock()

    dao = Mock()
    instance = LocalWatcher(engine, dao)
    instance.local = engine.local
    instance.dao = dao
    instance.thread_id = 73
    instance._interact = Mock()
    instance.remove_void_transfers = Mock()
    instance.increase_error = Mock()
    instance._delete_files = {}
    instance._protected_files = {}
    return instance


def prepare_event_router(watcher):
    """Set safe defaults for direct calls to ``handle_watchdog_event``."""

    def get_path(path):
        path = Path(path)
        if path == Path("/sync"):
            return ROOT
        try:
            return path.relative_to("/sync")
        except ValueError:
            return path

    watcher.local.get_path.side_effect = get_path
    watcher.local.is_ignored.return_value = False
    watcher.local.is_temp_file.return_value = False
    watcher.local.try_get_info.return_value = None
    watcher.local.exists.return_value = True
    watcher.dao.get_state_from_local.return_value = None


def dispatch(watcher, event, *, windows=False, mac=False, normalizer=None):
    normalizer = normalizer or (lambda value, action=True: Path(value))
    with patch.object(local_watcher_module, "WINDOWS", windows), patch.object(
        local_watcher_module, "MAC", mac
    ), patch.object(local_watcher_module, "normalize", side_effect=normalizer):
        watcher.handle_watchdog_event(event)


# _execute and observer lifecycle -------------------------------------------------


def test_execute_drains_one_event_and_always_stops_observer(watcher):
    event = make_event("modified")
    watcher.local.exists.return_value = True
    watcher.watchdog_queue.put(event)
    watcher._setup_watchdog = Mock()
    watcher._scan = Mock()
    watcher._stop_watchdog = Mock()
    watcher.handle_watchdog_event = Mock()
    watcher._interact.side_effect = [None, ThreadInterrupt()]

    with patch.object(local_watcher_module, "LINUX", False), patch.object(
        local_watcher_module, "WINDOWS", False
    ), patch.object(local_watcher_module, "sleep") as sleep_mock:
        with pytest.raises(ThreadInterrupt):
            watcher._execute()

    watcher._setup_watchdog.assert_called_once_with()
    watcher._scan.assert_called_once_with()
    watcher.handle_watchdog_event.assert_called_once_with(event)
    sleep_mock.assert_called_once_with(1)
    watcher._stop_watchdog.assert_called_once_with()


@pytest.mark.parametrize("failure", [PermissionError("denied"), RuntimeError("scan")])
def test_execute_stops_observer_when_startup_fails(watcher, failure):
    watcher.local.exists.return_value = True
    watcher._setup_watchdog = Mock()
    watcher._scan = Mock()
    watcher._stop_watchdog = Mock()
    if isinstance(failure, PermissionError):
        watcher._setup_watchdog.side_effect = failure
    else:
        watcher._scan.side_effect = failure

    with pytest.raises(type(failure), match=str(failure)):
        watcher._execute()

    watcher._stop_watchdog.assert_called_once_with()


def test_execute_missing_root_emits_and_still_cleans_up(watcher):
    watcher.local.exists.return_value = False
    watcher.rootDeleted = Mock()
    watcher._stop_watchdog = Mock()

    watcher._execute()

    watcher.rootDeleted.emit.assert_called_once_with()
    watcher._stop_watchdog.assert_called_once_with()


def test_scan_when_synchronization_is_disabled_only_emits(watcher):
    watcher.localScanFinished = Mock()

    with patch.object(local_watcher_module.Feature, "synchronization", False):
        watcher._scan()

    watcher.localScanFinished.emit.assert_called_once_with()
    watcher.local.get_info.assert_not_called()


def test_stop_watchdog_swallows_observer_shutdown_error(watcher):
    observer = Mock()
    observer.stop.side_effect = RuntimeError("observer failed")
    watcher._observer = observer

    with patch.object(local_watcher_module.Feature, "synchronization", True):
        watcher._stop_watchdog()

    observer.stop.assert_called_once_with()
    assert not hasattr(watcher, "_observer")


def test_stop_watchdog_without_observer_is_a_noop(watcher):
    watcher._observer = None

    with patch.object(local_watcher_module.Feature, "synchronization", True):
        watcher._stop_watchdog()

    assert watcher._observer is None


def test_windows_constructor_initializes_without_starting_observer():
    engine = Mock(local=Mock())
    with patch.object(local_watcher_module, "WINDOWS", True):
        watcher = LocalWatcher(engine, Mock())

    assert watcher._windows_folder_scan_delay == 10000
    assert watcher._observer is None


# _scan_recursive ----------------------------------------------------------------


def test_scan_recursive_handles_case_only_rename(watcher):
    parent = make_info("folder", folderish=True)
    child = make_info("folder/file.txt")
    pair = make_pair(
        local_path=Path("folder/File.txt"),
        local_name="File.txt",
        remote_ref="case-ref",
    )
    watcher.dao.get_local_children.return_value = [pair]
    watcher.local.get_children_info.return_value = [child]
    watcher.local.get_remote_id.side_effect = lambda path: (
        "case-ref" if Path(path) == child.path else None
    )
    watcher.dao.get_normal_state_from_remote.return_value = pair
    watcher.local.exists.return_value = True
    watcher.local.is_case_sensitive.return_value = False

    watcher._scan_recursive(parent, recursive=False)

    assert pair.local_state == "moved"
    watcher.dao.update_local_state.assert_called_once_with(pair, child)
    assert watcher._delete_files == {}


@pytest.mark.parametrize("reason", ["processing", "same-path"])
def test_scan_recursive_skips_non_moves(watcher, reason):
    parent = make_info("folder", folderish=True)
    child = make_info("folder/file.txt")
    pair = make_pair(
        processor=1 if reason == "processing" else 0,
        local_path=(
            Path("folder/old.txt") if reason == "processing" else child.path
        ),
        remote_ref="tracked-ref",
    )
    watcher.dao.get_local_children.return_value = []
    watcher.local.get_children_info.return_value = [child]
    watcher.local.get_remote_id.side_effect = lambda path: (
        "tracked-ref" if Path(path) == child.path else None
    )
    watcher.dao.get_normal_state_from_remote.return_value = pair
    watcher.local.exists.return_value = True
    watcher.local.is_case_sensitive.return_value = True
    watcher.get_creation_time = Mock(side_effect=[2, 1])

    watcher._scan_recursive(parent, recursive=False)

    watcher.dao.update_local_state.assert_not_called()
    watcher.dao.insert_local_state.assert_not_called()


def test_scan_recursive_detects_move_then_copy_back(watcher):
    parent = make_info("folder", folderish=True)
    child = make_info("folder/new.txt")
    old_info = make_info("folder/old.txt")
    pair = make_pair(
        local_path=old_info.path,
        local_name="old.txt",
        remote_ref="move-ref",
    )
    watcher.dao.get_local_children.return_value = []
    watcher.local.get_children_info.return_value = [child]
    watcher.local.get_remote_id.side_effect = lambda path: (
        "move-ref" if Path(path) == child.path else None
    )
    watcher.dao.get_normal_state_from_remote.return_value = pair
    watcher.local.exists.return_value = True
    watcher.local.is_case_sensitive.return_value = True
    watcher.local.abspath.side_effect = lambda path: Path("/sync") / path
    watcher.local.get_info.return_value = old_info
    watcher.get_creation_time = Mock(side_effect=[1, 2])

    watcher._scan_recursive(parent, recursive=False)

    assert pair.local_state == "moved"
    assert watcher._protected_files == {"move-ref": True}
    watcher.local.remove_remote_id.assert_called_once_with(old_info.path)
    watcher.dao.insert_local_state.assert_called_once_with(
        old_info, old_info.path.parent
    )


@pytest.mark.parametrize("moved_and_renamed", [False, True])
def test_scan_recursive_distinguishes_copy_paste_and_rename(
    watcher, moved_and_renamed
):
    parent = make_info("folder", folderish=True)
    child = make_info("folder/new.txt", digest="fresh")
    pair = make_pair(
        id=2,
        local_path=Path("folder/old.txt"),
        local_name="old.txt",
        remote_ref="new-ref",
        local_digest="stale-new",
    )
    old_pair = make_pair(
        id=3,
        local_path=Path("folder/other.txt"),
        remote_ref="old-ref",
        local_digest="stale-old",
    )
    watcher.dao.get_local_children.return_value = []
    watcher.local.get_children_info.return_value = [child]

    def remote_id(path):
        path = Path(path)
        if path == child.path:
            return "new-ref"
        if path == pair.local_path:
            return "old-ref" if moved_and_renamed else "new-ref"
        return None

    watcher.local.get_remote_id.side_effect = remote_id
    watcher.dao.get_normal_state_from_remote.side_effect = lambda ref: {
        "new-ref": pair,
        "old-ref": old_pair,
    }.get(ref)
    watcher.local.exists.return_value = True
    watcher.local.is_case_sensitive.return_value = True
    watcher.local.abspath.side_effect = lambda path: Path("/sync") / path
    watcher.get_creation_time = Mock(side_effect=[2, 1])

    watcher._scan_recursive(parent, recursive=False)

    if moved_and_renamed:
        assert pair.local_state == "moved"
        assert pair.local_digest == "fresh"
        assert old_pair.local_state == "moved"
        assert old_pair.local_digest == "fresh"
        assert watcher._protected_files == {
            "old-ref": True,
            "new-ref": True,
        }
        assert watcher.dao.update_local_state.call_args_list == [
            call(old_pair, watcher.local.get_info.return_value),
            call(pair, child),
        ]
    else:
        watcher.local.remove_remote_id.assert_called_once_with(child.path)
        watcher.dao.insert_local_state.assert_called_once_with(child, parent.path)


def test_scan_recursive_refreshes_racy_pair_and_recurses_into_folder(watcher):
    parent = make_info("folder", folderish=True)
    child = make_info("folder/child", folderish=True)
    stale = make_pair(
        id=8,
        local_path=child.path,
        local_name="child",
        remote_ref=None,
        folderish=True,
    )
    refreshed = make_pair(
        id=8,
        local_path=child.path,
        local_name="child",
        remote_ref=None,
        folderish=True,
    )
    watcher.dao.get_local_children.side_effect = lambda path: (
        [stale] if Path(path) == parent.path else []
    )
    watcher.local.get_children_info.side_effect = lambda path: (
        [child] if Path(path) == parent.path else []
    )
    watcher.local.get_remote_id.side_effect = lambda path: (
        None if Path(path) == parent.path else "xattr-ref"
    )
    watcher.dao.get_new_remote_children.return_value = []
    watcher.dao.get_state_from_id.return_value = refreshed

    watcher._scan_recursive(parent)

    watcher.local.remove_remote_id.assert_called_once_with(child.path)
    watcher.local.set_remote_id.assert_called_once_with(child.path, None)
    assert watcher.dao.get_local_children.call_args_list == [
        call(parent.path),
        call(child.path),
    ]


@pytest.mark.parametrize("replacement_exists", [False, True])
def test_scan_recursive_handles_file_substitution(watcher, replacement_exists):
    parent = make_info("folder", folderish=True)
    child = make_info("folder/file.txt", digest="replacement-digest")
    tracked = make_pair(
        id=4,
        local_path=child.path,
        local_name=child.name,
        remote_ref="tracked-ref",
        local_digest="tracked-digest",
    )
    replacement = make_pair(
        id=5,
        local_path=Path("elsewhere.txt"),
        remote_ref="replacement-ref",
        local_digest="old-replacement-digest",
    )
    watcher.dao.get_local_children.return_value = [tracked]
    watcher.local.get_children_info.return_value = [child]
    watcher.local.get_remote_id.side_effect = lambda path: (
        "replacement-ref" if Path(path) == child.path else None
    )
    watcher.dao.get_normal_state_from_remote.return_value = (
        replacement if replacement_exists else None
    )

    watcher._scan_recursive(parent, recursive=False)

    assert watcher._delete_files == {"tracked-ref": tracked}
    if replacement_exists:
        assert replacement.local_state == "moved"
        assert replacement.local_digest == "replacement-digest"
        assert watcher._protected_files == {"replacement-ref": True}
        watcher.dao.update_local_state.assert_any_call(replacement, child)
    else:
        watcher.dao.insert_local_state.assert_called_once_with(child, parent.path)


def test_scan_recursive_records_existing_pair_error_and_continues(watcher):
    parent = make_info("folder", folderish=True)
    child = make_info("folder/file.txt", last_modification_time=None)
    pair = make_pair(local_path=child.path, local_name=child.name)
    watcher.dao.get_local_children.return_value = [pair]
    watcher.local.get_children_info.return_value = [child]
    watcher.local.get_remote_id.return_value = None

    watcher._scan_recursive(parent, recursive=False)

    watcher.increase_error.assert_called_once()
    args, kwargs = watcher.increase_error.call_args
    assert args == (pair, "SCAN RECURSIVE")
    assert isinstance(kwargs["exception"], AttributeError)


def test_scan_recursive_removes_unbound_deletion_but_protects_remote_creation(
    watcher,
):
    parent = make_info("folder", folderish=True)
    remote_creation = make_pair(
        local_name="remote.txt",
        local_path=Path("folder/remote.txt"),
        pair_state="remotely_created",
    )
    local_only = make_pair(
        local_name="local.txt",
        local_path=Path("folder/local.txt"),
        remote_ref="",
    )
    watcher.dao.get_local_children.return_value = [remote_creation, local_only]
    watcher.local.get_children_info.return_value = []
    watcher.local.get_remote_id.return_value = None

    watcher._scan_recursive(parent, recursive=False)

    watcher.dao.remove_state.assert_called_once_with(local_only)
    watcher.remove_void_transfers.assert_called_once_with(local_only)
    assert watcher._metrics["delete_files"] == 1


def test_scan_recursive_propagates_thread_interrupt(watcher):
    parent = make_info("folder", folderish=True)
    child = make_info("folder/file.txt")
    watcher.dao.get_local_children.return_value = []
    watcher.local.get_children_info.return_value = [child]
    watcher.local.get_remote_id.side_effect = lambda path: (
        None
        if Path(path) == parent.path
        else (_ for _ in ()).throw(ThreadInterrupt())
    )

    with pytest.raises(ThreadInterrupt):
        watcher._scan_recursive(parent, recursive=False)


# Known-pair event handling -------------------------------------------------------


def test_known_pair_operational_error_releases_state(watcher):
    pair = make_pair()
    event = make_event("modified")
    watcher.dao.acquire_state.side_effect = sqlite3.OperationalError("busy")

    watcher._handle_watchdog_event_on_known_pair(pair, event, pair.local_path)

    watcher.dao.release_state.assert_called_once_with(watcher.thread_id)


def test_known_pair_windows_requeues_nonterminal_state(watcher):
    pair = make_pair()
    acquired = make_pair(id=pair.id)
    refreshed = make_pair(id=pair.id, pair_state="locally_modified")
    event = make_event("modified")
    watcher.dao.acquire_state.return_value = acquired
    watcher.dao.get_state_from_id.return_value = refreshed
    watcher._handle_watchdog_event_on_known_acquired_pair = Mock()

    with patch.object(local_watcher_module, "WINDOWS", True):
        watcher._handle_watchdog_event_on_known_pair(
            pair, event, pair.local_path
        )

    watcher.dao._queue_pair_state.assert_called_once_with(
        refreshed.id,
        refreshed.folderish,
        refreshed.pair_state,
        pair=refreshed,
    )
    watcher.engine.send_metric.assert_called_once_with(
        "sync", "error", "WINDOWS_RO_FOLDER"
    )


@pytest.mark.parametrize(
    ("remote_ref", "digest", "returns_early"),
    [("", "same", True), ("", "different", False), ("remote-id", "same", False)],
)
def test_created_event_on_acquired_pair_remote_id_cases(
    watcher, remote_ref, digest, returns_early
):
    pair = make_pair(local_digest="same", pair_state="locally_created")
    info = make_info(pair.local_path, digest=digest)
    watcher.local.try_get_info.return_value = info
    watcher.local.get_remote_id.return_value = remote_ref
    event = make_event("created")

    with patch.object(local_watcher_module, "is_large_file", return_value=True):
        watcher._handle_watchdog_event_on_known_acquired_pair(
            pair, event, pair.local_path
        )

    if returns_early:
        watcher.dao.update_local_state.assert_not_called()
    else:
        watcher.remove_void_transfers.assert_called_once_with(pair)
        watcher.dao.update_local_state.assert_called_once_with(pair, info)


@pytest.mark.parametrize("set_remote_id_fails", [False, True])
def test_acquired_modified_event_tracks_ongoing_copy(
    watcher, set_remote_id_fails
):
    pair = make_pair(
        pair_state="locally_created",
        size=100,
        local_digest="old",
        remote_ref="remote-id",
    )
    info = make_info(pair.local_path, size=25, remote_ref="")
    watcher.local.try_get_info.return_value = info
    if set_remote_id_fails:
        watcher.local.set_remote_id.side_effect = OSError("xattrs denied")
    event = make_event("modified")

    watcher._handle_watchdog_event_on_known_acquired_pair(
        pair, event, pair.local_path
    )

    assert pair.local_digest == UNACCESSIBLE_HASH
    watcher.local.set_remote_id.assert_called_once_with(
        pair.local_path, pair.remote_ref
    )
    watcher.remove_void_transfers.assert_called_once_with(pair)
    watcher.dao.update_local_state.assert_not_called()


def test_acquired_modified_event_keeps_unaccessible_hash_until_copy_finishes(
    watcher,
):
    pair = make_pair(
        pair_state="locally_created",
        size=10,
        local_digest=UNACCESSIBLE_HASH,
        remote_ref="",
    )
    info = make_info(pair.local_path, size=10, remote_ref="")
    watcher.local.try_get_info.return_value = info

    watcher._handle_watchdog_event_on_known_acquired_pair(
        pair, make_event("modified"), pair.local_path
    )

    watcher.remove_void_transfers.assert_called_once_with(pair)
    watcher.dao.update_local_state.assert_not_called()


@pytest.mark.parametrize("mac_delayed_xattr", [False, True])
def test_acquired_modified_event_repairs_substituted_xattr(
    watcher, mac_delayed_xattr
):
    pair = make_pair(
        pair_state="locally_created",
        remote_ref="expected-ref",
        local_digest="digest",
    )
    info = make_info(pair.local_path, remote_ref="other-ref")
    original = make_pair(local_path=Path("original.txt"), remote_ref="other-ref")
    original_info = (
        make_info(original.local_path, remote_ref="other-ref")
        if mac_delayed_xattr
        else None
    )
    watcher.local.try_get_info.side_effect = lambda path: (
        info if Path(path) == pair.local_path else original_info
    )
    watcher.dao.get_normal_state_from_remote.return_value = original

    with patch.object(local_watcher_module, "MAC", mac_delayed_xattr):
        watcher._handle_watchdog_event_on_known_acquired_pair(
            pair, make_event("modified"), pair.local_path
        )

    watcher.local.set_remote_id.assert_called_once_with(
        pair.local_path, pair.remote_ref
    )
    watcher.dao.update_local_state.assert_called_once_with(pair, info)


# Moves on known pairs -----------------------------------------------------------


def configure_direct_move(watcher, destination="/sync/new.txt"):
    destination = Path(destination)
    watcher.local.get_path.side_effect = lambda path: Path(path).relative_to(
        "/sync"
    )
    watcher.dao.get_state_from_local.return_value = None
    watcher.local.get_remote_id.return_value = "different-parent"
    return patch.object(
        local_watcher_module, "normalize", side_effect=lambda path: Path(path)
    )


def test_known_move_drops_same_digest_substitution(watcher):
    old = make_pair(id=1, local_path=Path("old.txt"), local_digest="same")
    destination_pair = make_pair(
        id=2, local_path=Path("new.txt"), remote_ref="destination-ref", local_digest="same"
    )
    info = make_info("new.txt", digest="same")
    event = make_event("moved", "/sync/old.txt", "/sync/new.txt")
    watcher.dao.get_state_from_local.return_value = destination_pair
    watcher.local.get_remote_id.return_value = destination_pair.remote_ref
    watcher.local.try_get_info.return_value = info
    watcher.local.get_path.return_value = info.path

    with patch.object(local_watcher_module, "is_generated_tmp_file", return_value=(False, None)), patch.object(
        local_watcher_module, "normalize", return_value=Path(event.dest_path)
    ):
        watcher._handle_move_on_known_pair(old, event, old.local_path)

    watcher.dao.remove_state.assert_called_once_with(old)
    watcher.dao.update_local_state.assert_not_called()


@pytest.mark.parametrize("text_edit_temporary", [False, True])
def test_known_move_ignores_missing_and_textedit_destinations(
    watcher, text_edit_temporary
):
    pair = make_pair(local_path=Path("old.txt"))
    destination = (
        "/sync/note.rtf.sb-a-b" if text_edit_temporary else "/sync/missing.txt"
    )
    event = make_event("moved", "/sync/old.txt", destination)
    info = make_info(Path(destination).relative_to("/sync"))
    watcher.local.get_path.side_effect = lambda path: Path(path).relative_to(
        "/sync"
    )
    watcher.dao.get_state_from_local.return_value = None
    watcher.local.try_get_info.return_value = info if text_edit_temporary else None

    with patch.object(local_watcher_module, "is_generated_tmp_file", return_value=(False, None)), patch.object(
        local_watcher_module, "normalize", return_value=Path(destination)
    ):
        watcher._handle_move_on_known_pair(pair, event, pair.local_path)

    watcher.dao.update_local_state.assert_not_called()


def test_known_move_cancelled_by_user_restores_synchronized_state(watcher):
    pair = make_pair(
        local_path=Path("folder/file.txt"),
        remote_name="file.txt",
        remote_parent_ref="parent-ref",
        local_state="moved",
    )
    info = make_info("folder/file.txt")
    event = make_event("moved", "/sync/elsewhere.txt", "/sync/folder/file.txt")
    watcher.local.get_path.side_effect = lambda path: Path(path).relative_to(
        "/sync"
    )
    watcher.dao.get_state_from_local.return_value = None
    watcher.local.try_get_info.return_value = info
    watcher.local.get_remote_id.return_value = "parent-ref"

    with patch.object(local_watcher_module, "is_generated_tmp_file", return_value=(False, None)), patch.object(
        local_watcher_module, "normalize", return_value=Path(event.dest_path)
    ):
        watcher._handle_move_on_known_pair(pair, event, pair.local_path)

    assert pair.local_state == "synchronized"
    watcher.dao.update_local_state.assert_called_once_with(pair, info, versioned=False)


def test_known_folder_move_on_linux_does_not_replace_child_paths(watcher):
    pair = make_pair(
        local_path=Path("old-folder"),
        local_state="synchronized",
        folderish=True,
    )
    info = make_info("new-folder", folderish=True)
    event = make_event("moved", "/sync/old-folder", "/sync/new-folder")
    watcher.local.get_path.side_effect = lambda path: Path(path).relative_to(
        "/sync"
    )
    watcher.dao.get_state_from_local.return_value = None
    watcher.local.try_get_info.return_value = info

    with patch.object(local_watcher_module, "is_generated_tmp_file", return_value=(False, None)), patch.object(
        local_watcher_module, "normalize", return_value=Path(event.dest_path)
    ), patch.object(local_watcher_module, "LINUX", True):
        watcher._handle_move_on_known_pair(pair, event, pair.local_path)

    assert pair.local_state == "moved"
    watcher.dao.replace_local_paths.assert_not_called()


def test_known_folder_move_replaces_paths_and_migrates_windows_scan(watcher):
    old_path = Path("old-folder")
    new_path = Path("new-folder")
    pair = make_pair(
        local_path=old_path,
        local_state="synchronized",
        folderish=True,
    )
    info = make_info(new_path, folderish=True)
    event = make_event("moved", "/sync/old-folder", "/sync/new-folder")
    watcher.local.get_path.side_effect = lambda path: Path(path).relative_to(
        "/sync"
    )
    watcher.dao.get_state_from_local.return_value = None
    watcher.local.try_get_info.return_value = info
    watcher._folder_scan_events = {old_path: (1, pair)}

    with patch.object(local_watcher_module, "is_generated_tmp_file", return_value=(False, None)), patch.object(
        local_watcher_module, "normalize", return_value=Path(event.dest_path)
    ), patch.object(local_watcher_module, "LINUX", False), patch.object(
        local_watcher_module, "WINDOWS", True
    ), patch.object(local_watcher_module, "mktime", return_value=123):
        watcher._handle_move_on_known_pair(pair, event, pair.local_path)

    watcher.dao.replace_local_paths.assert_called_once_with(old_path, new_path)
    assert old_path not in watcher._folder_scan_events
    assert watcher._folder_scan_events[new_path] == (123, pair)


# Top-level watchdog event router ------------------------------------------------


def test_event_router_skips_windows_stream(watcher):
    prepare_event_router(watcher)

    dispatch(
        watcher,
        make_event("modified", "/sync/file.txt:nxdrive"),
        windows=True,
    )

    watcher.dao.get_state_from_local.assert_not_called()


def test_event_router_skips_normalization_only_move(watcher):
    prepare_event_router(watcher)
    event = make_event("moved", "/sync/file.txt", "/sync/file.txt")

    dispatch(watcher, event)

    watcher.dao.get_state_from_local.assert_not_called()


def test_event_router_skips_temporary_file(watcher):
    prepare_event_router(watcher)
    watcher.local.is_temp_file.return_value = True

    dispatch(watcher, make_event("created"))

    watcher.dao.get_state_from_local.assert_not_called()


@pytest.mark.parametrize("event_type", ["deleted", "moved"])
def test_event_router_removes_unsynchronized_pair_after_delete_or_move(
    watcher, event_type
):
    prepare_event_router(watcher)
    pair = make_pair(pair_state="unsynchronized")
    watcher.dao.get_state_from_local.return_value = pair
    event = make_event(
        event_type,
        "/sync/file.txt",
        "/sync/renamed.txt" if event_type == "moved" else "",
    )

    dispatch(watcher, event)

    watcher.dao.remove_state.assert_called_once_with(pair)


def test_event_router_turns_quick_recreation_into_modification(watcher):
    prepare_event_router(watcher)
    pair = make_pair(local_state="deleted", pair_state="locally_deleted")
    info = make_info(pair.local_path)
    watcher.dao.get_state_from_local.return_value = pair
    watcher.local.get_info.return_value = info
    watcher._handle_watchdog_event_on_known_pair = Mock()

    dispatch(watcher, make_event("created"))

    assert pair.local_state == "modified"
    assert pair.remote_state == "unknown"
    watcher.dao.update_local_state.assert_called_once_with(pair, info)
    watcher._handle_watchdog_event_on_known_pair.assert_called_once()


def test_event_router_sends_known_move_to_move_handler(watcher):
    prepare_event_router(watcher)
    pair = make_pair()
    watcher.dao.get_state_from_local.return_value = pair
    watcher._handle_move_on_known_pair = Mock()
    event = make_event("moved", "/sync/file.txt", "/sync/renamed.txt")

    dispatch(watcher, event)

    watcher._handle_move_on_known_pair.assert_called_once_with(
        pair, event, pair.local_path
    )


def test_event_router_ignores_move_to_banned_name(watcher):
    prepare_event_router(watcher)
    watcher.local.is_ignored.return_value = True

    dispatch(
        watcher,
        make_event("moved", "/sync/old.txt", "/sync/ignored.tmp"),
    )

    watcher.local.try_get_info.assert_not_called()


def test_event_router_detects_pair_that_was_moved_twice(watcher):
    prepare_event_router(watcher)
    destination = Path("new.txt")
    info = make_info(destination, remote_ref="remote-id")
    tracked = make_pair(local_path=Path("original.txt"), remote_ref="remote-id")
    watcher.local.try_get_info.return_value = info
    watcher.dao.get_normal_state_from_remote.return_value = tracked
    watcher.local.exists.return_value = False
    watcher._handle_move_on_known_pair = Mock()
    event = make_event("moved", "/sync/old.txt", "/sync/new.txt")

    dispatch(watcher, event)

    watcher._handle_move_on_known_pair.assert_called_once_with(
        tracked, event, destination
    )


def test_event_router_inserts_unknown_moved_folder_and_schedules_scan(watcher):
    prepare_event_router(watcher)
    folder = make_info("new-folder", folderish=True)
    scheduled_pair = make_pair(local_path=folder.path, folderish=True)
    watcher.local.try_get_info.return_value = folder
    watcher.dao.get_state_from_local.side_effect = [None, None, scheduled_pair]
    watcher.local.get_path.side_effect = lambda path: (
        None if Path(path) == Path("/sync") else Path(path).relative_to("/sync")
    )
    watcher.scan_pair = Mock()
    watcher._schedule_win_folder_scan = Mock()

    dispatch(
        watcher,
        make_event("moved", "/sync/old-folder", "/sync/new-folder"),
        windows=True,
    )

    watcher.dao.insert_local_state.assert_called_once_with(folder, ROOT)
    watcher.scan_pair.assert_called_once_with(folder.path)
    watcher._schedule_win_folder_scan.assert_called_once_with(scheduled_pair)


def test_event_router_returns_for_unknown_unhandled_event(watcher):
    prepare_event_router(watcher)

    dispatch(watcher, make_event("metadata"))

    watcher.local.try_get_info.assert_not_called()


def test_event_router_returns_when_modified_file_disappeared(watcher):
    prepare_event_router(watcher)

    dispatch(watcher, make_event("modified"))

    watcher.dao.insert_local_state.assert_not_called()


def test_event_router_ignores_remote_pair_in_process(watcher):
    prepare_event_router(watcher)
    info = make_info("file.txt", remote_ref="remote-id")
    source = make_pair(processor=1, local_path=Path("old.txt"))
    watcher.local.try_get_info.return_value = info
    watcher.dao.get_normal_state_from_remote.return_value = source

    dispatch(watcher, make_event("created"))

    watcher.dao.update_local_state.assert_not_called()
    watcher.dao.insert_local_state.assert_not_called()


def test_event_router_rejects_move_into_readonly_folder(watcher):
    prepare_event_router(watcher)
    info = make_info("folder/file.txt", remote_ref="remote-id")
    source = make_pair(local_path=Path("old/file.txt"), remote_ref="remote-id")
    destination_parent = make_pair(
        local_path=Path("folder"),
        remote_name="Read only",
        remote_can_create_child=False,
        folderish=True,
    )
    watcher.local.try_get_info.return_value = info
    watcher.dao.get_normal_state_from_remote.return_value = source
    watcher.local.exists.return_value = False
    watcher.dao.get_state_from_local.side_effect = lambda path: (
        destination_parent if Path(path) == info.path.parent else None
    )

    dispatch(watcher, make_event("created", "/sync/folder/file.txt"))

    watcher.dao.unsynchronize_state.assert_called_once_with(source, "READONLY")
    watcher.engine.newReadonly.emit.assert_called_once_with(
        source.local_name, destination_parent.remote_name
    )


def test_event_router_converts_move_from_readonly_folder_to_creation(watcher):
    prepare_event_router(watcher)
    info = make_info("new/file.txt", remote_ref="remote-id")
    source = make_pair(local_path=Path("readonly/file.txt"), remote_ref="remote-id")
    source_parent = make_pair(
        local_path=source.local_path.parent,
        remote_can_create_child=False,
        folderish=True,
    )
    watcher.local.try_get_info.return_value = info
    watcher.local.get_info.return_value = info
    watcher.dao.get_normal_state_from_remote.return_value = source
    watcher.local.exists.return_value = False
    watcher.dao.get_state_from_local.side_effect = lambda path: (
        source_parent if Path(path) == source.local_path.parent else None
    )

    dispatch(watcher, make_event("created", "/sync/new/file.txt"))

    assert source.local_path == info.path
    assert source.local_state == "created"
    assert source.remote_state == "unknown"
    watcher.local.remove_remote_id.assert_called_once_with(info.path)
    watcher.dao.update_local_state.assert_called_once_with(source, info)


def test_event_router_tracks_regular_move_detected_as_creation(watcher):
    prepare_event_router(watcher)
    info = make_info("new/file.txt", remote_ref="remote-id")
    source = make_pair(local_path=Path("old/file.txt"), remote_ref="remote-id")
    watcher.local.try_get_info.return_value = info
    watcher.local.get_info.return_value = info
    watcher.dao.get_normal_state_from_remote.return_value = source
    watcher.local.exists.return_value = False
    watcher.dao.get_state_from_local.return_value = None

    dispatch(watcher, make_event("created", "/sync/new/file.txt"))

    assert source.local_state == "moved"
    watcher.dao.update_local_state.assert_called_once_with(source, info)


def test_event_router_handles_move_then_copy_back_by_creation_time(watcher):
    prepare_event_router(watcher)
    info = make_info("new.txt", remote_ref="remote-id")
    old_info = make_info("old.txt", remote_ref="remote-id")
    source = make_pair(local_path=old_info.path, remote_ref="remote-id")
    watcher.local.try_get_info.return_value = info
    watcher.local.get_info.side_effect = lambda path: (
        info if Path(path) == info.path else old_info
    )
    watcher.dao.get_normal_state_from_remote.return_value = source
    watcher.local.exists.return_value = True
    watcher.local.abspath.side_effect = lambda path: Path("/sync") / path
    watcher.get_creation_time = Mock(side_effect=[1, 2])

    dispatch(watcher, make_event("created", "/sync/new.txt"))

    assert source.local_state == "moved"
    watcher.dao.update_local_state.assert_called_once_with(source, info)
    watcher.dao.insert_local_state.assert_called_once_with(
        old_info, old_info.path.parent
    )
    watcher.local.remove_remote_id.assert_called_once_with(old_info.path)


def test_event_router_handles_windows_copy_paste_then_rename(watcher):
    prepare_event_router(watcher)
    info = make_info("new.txt", remote_ref="remote-id")
    source = make_pair(local_path=Path("old.txt"), remote_ref="remote-id")
    watcher.local.try_get_info.return_value = info
    watcher.dao.get_normal_state_from_remote.return_value = source
    watcher.local.exists.return_value = True
    watcher.local.abspath.side_effect = lambda path: Path("/sync") / path
    watcher.local.is_equal_digests.return_value = True
    watcher.get_creation_time = Mock(side_effect=[2, 1])

    dispatch(
        watcher,
        make_event("created", "/sync/new.txt"),
        windows=True,
    )

    watcher.local.remove_remote_id.assert_called_once_with(source.local_path)
    watcher.dao.insert_local_state.assert_not_called()


def test_event_router_resolves_windows_delete_create_as_move(watcher):
    prepare_event_router(watcher)
    info = make_info("new.txt", remote_ref="remote-id")
    deleted_pair = make_pair(local_path=Path("old.txt"), remote_ref="remote-id")
    watcher.local.try_get_info.return_value = info
    watcher.local.get_info.return_value = info
    watcher.dao.get_normal_state_from_remote.return_value = None
    watcher._delete_events = {"remote-id": (1, deleted_pair)}

    dispatch(
        watcher,
        make_event("created", "/sync/new.txt"),
        windows=True,
    )

    assert deleted_pair.local_state == "moved"
    watcher.dao.update_local_state.assert_called_once_with(deleted_pair, info)
    assert watcher._delete_events == {}


def test_event_router_treats_existing_remote_id_as_copy_paste(watcher):
    prepare_event_router(watcher)
    info = make_info("copy.txt", remote_ref="remote-id")
    source = make_pair(local_path=Path("original.txt"), remote_ref="remote-id")
    watcher.local.try_get_info.return_value = info
    watcher.dao.get_normal_state_from_remote.return_value = source
    watcher.local.exists.return_value = True
    watcher.local.abspath.side_effect = lambda path: Path("/sync") / path
    watcher.get_creation_time = Mock(side_effect=[1, 2])

    dispatch(watcher, make_event("modified", "/sync/copy.txt"))

    watcher.local.remove_remote_id.assert_called_once_with(info.path)
    watcher.dao.insert_local_state.assert_called_once_with(info, ROOT)


def test_event_router_scans_new_folder_and_schedules_windows_followup(watcher):
    prepare_event_router(watcher)
    folder = make_info("folder", folderish=True)
    scheduled_pair = make_pair(local_path=folder.path, folderish=True)
    watcher.local.try_get_info.return_value = folder
    watcher.dao.get_state_from_local.side_effect = [None, scheduled_pair]
    watcher.scan_pair = Mock()
    watcher._schedule_win_folder_scan = Mock()

    dispatch(
        watcher,
        make_event("created", "/sync/folder"),
        windows=True,
    )

    watcher.dao.insert_local_state.assert_called_once_with(folder, ROOT)
    watcher.scan_pair.assert_called_once_with(folder.path)
    watcher._schedule_win_folder_scan.assert_called_once_with(scheduled_pair)


def test_event_router_propagates_thread_interrupt(watcher):
    prepare_event_router(watcher)

    with pytest.raises(ThreadInterrupt):
        dispatch(
            watcher,
            make_event("modified"),
            normalizer=Mock(side_effect=ThreadInterrupt()),
        )


@pytest.mark.parametrize("event_type", ["created", "modified"])
def test_event_router_handles_eexist_on_source(
    watcher, tmp_path, event_type
):
    prepare_event_router(watcher)
    existing = tmp_path / "normalized.txt"
    existing.write_text("existing", encoding="utf-8")
    watcher.fileAlreadyExists = Mock()
    error = OSError(errno.EEXIST, "already exists")
    normalizer = (
        Mock(side_effect=error)
        if event_type == "created"
        else Mock(side_effect=[error, existing])
    )

    dispatch(
        watcher,
        make_event(event_type, str(tmp_path / "source.txt")),
        normalizer=normalizer,
    )

    if event_type == "created":
        watcher.fileAlreadyExists.emit.assert_not_called()
    else:
        watcher.fileAlreadyExists.emit.assert_called_once_with(
            existing, tmp_path / "source.txt"
        )


def test_event_router_handles_eexist_on_destination(watcher, tmp_path):
    prepare_event_router(watcher)
    missing = tmp_path / "missing.txt"
    existing = tmp_path / "destination.txt"
    existing.write_text("existing", encoding="utf-8")
    watcher.fileAlreadyExists = Mock()
    error = OSError(errno.EEXIST, "already exists")

    dispatch(
        watcher,
        make_event("moved", str(missing), str(existing)),
        normalizer=Mock(side_effect=[error, missing, existing]),
    )

    watcher.fileAlreadyExists.emit.assert_called_once_with(existing, existing)


def test_event_router_swallows_other_os_errors(watcher):
    prepare_event_router(watcher)

    dispatch(
        watcher,
        make_event("modified"),
        normalizer=Mock(side_effect=OSError(errno.EACCES, "denied")),
    )


def test_event_router_forwards_unexpected_exception(watcher):
    prepare_event_router(watcher)

    with patch.object(local_watcher_module.sys, "excepthook") as excepthook:
        dispatch(
            watcher,
            make_event("modified"),
            normalizer=Mock(side_effect=ValueError("bad event")),
        )

    excepthook.assert_called_once()
    assert excepthook.call_args.args[0] is ValueError


# DriveFSEventHandler ------------------------------------------------------------


def test_fs_event_handler_skips_read_only_backend_events():
    worker = Mock(watchdog_queue=Queue())
    handler = DriveFSEventHandler(worker)
    event = SimpleNamespace(event_type="opened")

    handler.on_any_event(event)

    assert handler.counter == 0
    assert worker.watchdog_queue.empty()


@pytest.mark.parametrize(
    ("kind", "locked", "expected_signal"),
    [
        ("office-created", True, "concurrentAlreadyLocked"),
        ("office-created", False, "documentLocked"),
        ("office-deleted", True, "documentUnlocked"),
        ("libreoffice-created", False, "documentLocked"),
    ],
)
def test_fs_event_handler_locks_and_unlocks_office_documents(
    kind, locked, expected_signal
):
    worker = Mock(watchdog_queue=Queue())
    engine = Mock()
    engine.manager.get_metadata_infos.return_value = "https://server/doc-id"
    engine.remote.documents.fetch_lock_status.return_value = locked
    handler = DriveFSEventHandler(worker, engine=engine)
    if kind == "office-deleted":
        event = FileDeletedEvent("/sync/~$report.docx")
    elif kind == "libreoffice-created":
        event = FileCreatedEvent("/sync/.~lock.report.odt#")
    else:
        event = FileCreatedEvent("/sync/~$report.docx")

    office_result = ("/sync/report.docx", "report.docx")
    with patch.object(
        local_watcher_module,
        "find_real_office_file",
        return_value=office_result,
    ), patch.object(
        local_watcher_module,
        "find_real_libreoffice_file",
        return_value=office_result,
    ):
        handler.on_any_event(event)

    autolock = engine.manager.autolock_service
    getattr(autolock, expected_signal).emit.assert_called_once_with("report.docx")
    if expected_signal == "documentLocked":
        engine.remote.lock.assert_called_once_with("doc-id")
    elif expected_signal == "documentUnlocked":
        engine.remote.unlock.assert_called_once_with("doc-id")
    else:
        engine.remote.lock.assert_not_called()
    assert worker.watchdog_queue.get_nowait() is event


# Deferred Windows queues --------------------------------------------------------


def test_windows_delete_queue_keeps_event_when_filesystem_check_fails(watcher):
    pair = make_pair(remote_ref="queued-ref")
    watcher._delete_events = {"queued-ref": (0, pair)}
    watcher.local.exists.side_effect = PermissionError("denied")

    with patch.object(
        local_watcher_module, "current_milli_time", return_value=10000
    ):
        watcher._win_dequeue_delete()

    assert watcher._delete_events == {"queued-ref": (0, pair)}


def test_windows_folder_queue_keeps_event_when_scan_fails(watcher):
    pair = make_pair(local_path=Path("folder"), folderish=True)
    watcher._windows_folder_scan_delay = 10
    watcher._folder_scan_events = {pair.local_path: (0, pair)}
    watcher.scan_pair = Mock(side_effect=PermissionError("denied"))

    with patch.object(
        local_watcher_module, "current_milli_time", return_value=100
    ):
        watcher._win_dequeue_folder_scan()

    assert watcher._folder_scan_events == {pair.local_path: (0, pair)}
