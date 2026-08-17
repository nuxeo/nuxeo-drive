"""Deterministic unit tests for the server-agnostic engine base class."""

from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

import nxdrive.drive.engine.engine as engine_module
from nxdrive.drive.constants import ROOT, DelAction, TransferStatus
from nxdrive.drive.engine.engine import Engine, ServerBindingSettings
from nxdrive.drive.exceptions import (
    EngineInitError,
    MissingXattrSupport,
    RootAlreadyBindWithDifferentAccount,
    ThreadInterrupt,
    UnknownDigest,
)
from nxdrive.drive.options import MetaOptions
from nxdrive.drive.server_type import FileSystemID


class FakeSignal:
    """Small signal double that exposes the connected callback to a test."""

    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


class FakeTimer:
    """In-memory QTimer double; callbacks run only when ``fire`` is called."""

    def __init__(self, parent):
        self.parent = parent
        self.timeout = FakeSignal()
        self.properties = {}
        self.intervals = []
        self.single_shot = False
        self.start_count = 0
        self.stopped = False
        self.deleted = False

    def setSingleShot(self, value):
        self.single_shot = value

    def setProperty(self, name, value):
        self.properties[name] = value

    def property(self, name):
        return self.properties.get(name)

    def setInterval(self, value):
        self.intervals.append(value)

    def start(self):
        self.start_count += 1

    def stop(self):
        self.stopped = True

    def deleteLater(self):
        self.deleted = True

    def fire(self):
        assert self.timeout.callback is not None
        self.timeout.callback()


def option_values(**values):
    """Temporarily override dynamic ``Options`` values without callbacks."""
    overrides = {name: (value, "test") for name, value in values.items()}
    return patch.dict(MetaOptions.options, overrides)


@pytest.fixture
def base_engine(tmp_path):
    """Build a base ``Engine`` without running its dependency-heavy init."""
    with patch.object(Engine, "__init__", return_value=None):
        engine = Engine.__new__(Engine)

    local_folder = tmp_path / "sync"
    local_folder.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    engine.uid = "engine-1"
    engine.name = "Shared engine"
    engine.type = "NXDRIVE"
    engine.version = "1.0"
    engine.local_folder = local_folder
    engine.folder = str(local_folder)
    engine.download_dir = ROOT
    engine.csv_dir = home / "csv"
    engine.server_url = "https://server.example/"
    engine.hostname = "server.example"
    engine.remote_user = "alice"
    engine.wui = "web"
    engine.force_ui = ""
    engine._web_authentication = False
    engine._remote_token = "old-token"
    engine._remote_password = ""
    engine._invalid_credentials = False
    engine._stopped = False
    engine._pause = False
    engine._sync_started = False
    engine._offline_state = False
    engine._folder_lock = None
    engine._proc_count = 4
    engine._threads = []
    engine._scheduled_timers = {}
    engine._user_cache = {"cached": "Cached User"}

    engine.manager = MagicMock()
    engine.manager.version = engine.version
    engine.manager.home = home
    engine.dao = MagicMock()
    engine.remote = MagicMock()
    engine.local = MagicMock()
    engine.queue_manager = MagicMock()
    engine._threadpool = MagicMock()
    engine._local_watcher = MagicMock()
    engine._remote_watcher = MagicMock()

    engine.dao.get_conflicts.return_value = []
    engine.dao.get_downloads_with_status.return_value = []
    engine.dao.get_uploads_with_status.return_value = []
    engine.dao.get_dt_uploads_with_status.return_value = []
    engine.dao.get_conflict_count.return_value = 0
    engine.dao.get_error_count.return_value = 0
    engine.dao.get_global_size.return_value = 0
    engine.dao.get_sync_count.return_value = 0
    engine.dao.get_syncing_count.return_value = 0
    engine.dao.get_unsynchronized_count.return_value = 0
    engine.queue_manager.get_errors_count.return_value = 0
    engine.queue_manager.get_overall_size.return_value = 0
    engine.queue_manager.active.return_value = False
    engine.queue_manager.get_metrics.return_value = {}
    engine.local.can_use_trash.return_value = True

    for signal_name in (
        "started",
        "_stop",
        "_scanPair",
        "newError",
        "newQueueItem",
        "newSyncStarted",
        "newSyncEnded",
        "syncStarted",
        "syncCompleted",
        "syncPartialCompleted",
        "syncSuspended",
        "syncResumed",
        "rootDeleted",
        "rootMoved",
        "docDeleted",
        "fileAlreadyExists",
        "uiChanged",
        "authChanged",
        "invalidAuthentication",
        "newConflict",
        "offline",
        "online",
        "cancelTimerSignal",
    ):
        setattr(engine, signal_name, MagicMock())

    return engine


def make_pair(**overrides):
    values = {
        "id": 17,
        "local_path": Path("file.txt"),
        "local_parent_path": ROOT,
        "local_name": "file.txt",
        "local_digest": "local-digest",
        "remote_name": "file.txt",
        "remote_ref": "opaque-ref",
        "remote_parent_path": "/parent",
        "remote_parent_ref": "parent-ref",
        "remote_digest": "remote-digest",
        "remote_state": "synchronized",
        "folderish": False,
        "update_state": MagicMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_constructor_wires_server_agnostic_dependencies(tmp_path):
    local_folder = tmp_path / "account"
    home = tmp_path / "home"
    home.mkdir()
    manager = MagicMock(version="2.0", home=home)
    definition = SimpleNamespace(
        local_folder=local_folder, uid="engine-id", name="Account"
    )
    local = MagicMock()
    local_cls = MagicMock(return_value=local)
    dao = MagicMock()
    remote = MagicMock()
    pool = MagicMock()

    def load_configuration(instance):
        instance.server_url = "https://server.example/"
        instance.hostname = "server.example"
        instance.remote_user = "alice"
        instance._web_authentication = False
        instance.wui = "web"
        instance.force_ui = ""

    with (
        patch.object(engine_module, "EngineDAO", return_value=dao),
        patch.object(engine_module, "QThreadPool") as pool_cls,
        patch.object(engine_module.Feature, "synchronization", True),
        option_values(debug=False, nofscheck=False),
        patch.object(Engine, "_load_configuration", new=load_configuration),
        patch.object(
            Engine, "_set_download_dir", return_value=tmp_path / "downloads"
        ) as set_download,
        patch.object(
            Engine, "_set_csv_dir_or_cleanup", return_value=tmp_path / "csv"
        ) as set_csv,
        patch.object(Engine, "_setup_local_folder") as setup_folder,
        patch.object(Engine, "_check_https") as check_https,
        patch.object(Engine, "init_remote", return_value=remote) as init_remote,
        patch.object(Engine, "_create_queue_manager") as create_queue,
        patch.object(Engine, "_create_remote_watcher") as create_remote_watcher,
        patch.object(Engine, "_create_local_watcher") as create_local_watcher,
        patch.object(Engine, "_set_root_icon") as set_icon,
        patch.object(Engine, "_send_roots_metrics") as send_roots_metrics,
    ):
        pool_cls.return_value.globalInstance.return_value = pool
        engine = Engine(manager, definition, local_cls=local_cls)

    assert engine.local_folder == local_folder
    assert engine.local is local
    assert engine.dao is dao
    assert engine.remote is remote
    assert engine._threadpool is pool
    local_cls.assert_called_once_with(
        local_folder,
        digest_callback=engine.suspend_client,
        download_dir=ROOT,
    )
    setup_folder.assert_called_once_with(True)
    check_https.assert_called_once()
    init_remote.assert_called_once()
    create_queue.assert_called_once()
    create_remote_watcher.assert_called_once()
    create_local_watcher.assert_called_once()
    set_download.assert_called_once()
    set_csv.assert_called_once()
    set_icon.assert_called_once()
    send_roots_metrics.assert_called_once()


def test_constructor_disposes_database_when_binding_fails(tmp_path):
    manager = MagicMock(version="2.0", home=tmp_path)
    definition = SimpleNamespace(
        local_folder=tmp_path / "account", uid="engine-id", name="Account"
    )
    dao = MagicMock()

    with (
        patch.object(engine_module, "EngineDAO", return_value=dao),
        patch.object(Engine, "bind", side_effect=RuntimeError("bind failed")),
        patch.object(Engine, "dispose_db") as dispose,
        pytest.raises(RuntimeError, match="bind failed"),
    ):
        Engine(manager, definition, binder=object(), local_cls=MagicMock())

    dispose.assert_called_once()


def test_constructor_rejects_missing_server_url(tmp_path):
    manager = MagicMock(version="2.0", home=tmp_path)
    definition = SimpleNamespace(
        local_folder=tmp_path / "account", uid="engine-id", name="Account"
    )

    def load_configuration(instance):
        instance.server_url = ""
        instance.remote_user = "alice"

    with (
        patch.object(engine_module, "EngineDAO", return_value=MagicMock()),
        patch.object(Engine, "_load_configuration", new=load_configuration),
        patch.object(Engine, "_set_download_dir", return_value=tmp_path / "tmp"),
        patch.object(Engine, "_set_csv_dir_or_cleanup", return_value=tmp_path / "csv"),
        patch.object(Engine, "_setup_local_folder"),
        pytest.raises(EngineInitError),
    ):
        Engine(manager, definition, local_cls=MagicMock())


def test_repr_and_export_report_lifecycle_state(base_engine):
    base_engine._offline_state = True
    representation = repr(base_engine)
    assert "Shared engine" in representation
    assert "is_offline=True" in representation

    binder = ServerBindingSettings(
        base_engine.server_url,
        False,
        base_engine.remote_user,
        base_engine.local_folder,
        True,
        server_version="2025.0",
        pwd_update_required=True,
    )
    base_engine.get_binder = MagicMock(return_value=binder)
    base_engine.get_metrics = MagicMock(return_value={"syncing": 0})
    base_engine._get_threads = MagicMock(return_value=[{"name": "watcher"}])
    exported = base_engine.export()

    assert exported["uid"] == "engine-1"
    assert exported["offline"] is True
    assert exported["need_password_update"] is True
    assert exported["threads"] == [{"name": "watcher"}]


def test_create_queue_manager_connects_all_signals(base_engine):
    queue_manager = MagicMock()
    with (
        patch.object(engine_module, "QueueManager", return_value=queue_manager) as cls,
        option_values(debug=True),
        patch.object(engine_module.Feature, "synchronization", False),
    ):
        base_engine._create_queue_manager()

    cls.assert_called_once_with(base_engine, base_engine.dao, max_file_processors=2)
    queue_manager.newItem.connect.assert_has_calls(
        [call(base_engine._check_sync_start), call(base_engine.newQueueItem)]
    )
    queue_manager.newErrorGiveUp.connect.assert_called_once_with(base_engine.newError)
    base_engine.started.connect.assert_called_once_with(queue_manager.init_processors)


def test_create_local_watcher_connects_lifecycle_signals(base_engine):
    watcher = MagicMock()
    base_engine.create_thread = MagicMock()
    with patch.object(engine_module, "LocalWatcher", return_value=watcher) as cls:
        base_engine._create_local_watcher()

    cls.assert_called_once_with(base_engine, base_engine.dao)
    base_engine.create_thread.assert_called_once_with(watcher, "LocalWatcher")
    watcher.localScanFinished.connect.assert_called_once_with(
        base_engine._remote_watcher.run
    )
    watcher.rootDeleted.connect.assert_called_once_with(base_engine.rootDeleted)
    watcher.rootMoved.connect.assert_called_once_with(base_engine.rootMoved)
    watcher.docDeleted.connect.assert_called_once_with(base_engine.docDeleted)
    watcher.fileAlreadyExists.connect.assert_called_once_with(
        base_engine.fileAlreadyExists
    )


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("_create_remote_watcher", ()),
        ("init_remote", ()),
        ("bind", (object(),)),
        ("_add_top_level_state", ()),
        ("create_processor", (MagicMock(),)),
    ],
)
def test_base_extension_points_require_an_override(base_engine, method_name, args):
    with pytest.raises(NotImplementedError):
        getattr(base_engine, method_name)(*args)


def test_small_state_helpers_and_metrics(base_engine):
    base_engine._sync_started = True
    base_engine._pause = True
    base_engine._stopped = True
    base_engine._offline_state = True
    base_engine.dao.get_conflict_count.return_value = 1
    base_engine.dao.get_error_count.return_value = 2
    base_engine.dao.get_global_size.return_value = 3
    base_engine.dao.get_sync_count.side_effect = [4, 5]
    base_engine.dao.get_syncing_count.return_value = 6
    base_engine.dao.get_unsynchronized_count.return_value = 7
    conflicts = [object()]
    base_engine.dao.get_conflicts.return_value = conflicts

    assert base_engine.have_folder_upload is True
    assert base_engine.is_syncing() is True
    assert base_engine.is_paused() is True
    assert base_engine.is_started() is False
    assert base_engine.is_stopped() is True
    assert base_engine.is_offline() is True
    assert base_engine.use_trash() is True
    assert base_engine.get_conflicts() is conflicts
    assert base_engine.get_user_full_name("cached") == "Cached User"
    assert base_engine.get_user_full_name("unknown", cache_only=True) == "unknown"
    assert base_engine.get_metrics() == {
        "uid": "engine-1",
        "conflicted_files": 1,
        "error_files": 2,
        "files_size": 3,
        "invalid_credentials": False,
        "sync_files": 4,
        "sync_folders": 5,
        "syncing": 6,
        "unsynchronized_files": 7,
    }


def test_get_threads_exports_each_worker(base_engine):
    first = MagicMock()
    second = MagicMock()
    first.worker.export.return_value = {"name": "first"}
    second.worker.export.return_value = {"name": "second"}
    base_engine._threads = [first, second]

    assert base_engine._get_threads() == [
        {"name": "first"},
        {"name": "second"},
    ]


def test_check_sync_start_emits_only_for_nonempty_queue(base_engine):
    base_engine.queue_manager.get_overall_size.return_value = 3
    base_engine._check_sync_start(row_id="ignored")
    assert base_engine._sync_started is True
    base_engine.syncStarted.emit.assert_called_once_with(3)

    base_engine._check_sync_start()
    base_engine.syncStarted.emit.assert_called_once_with(3)


def test_suspend_client_reflects_pause_and_started_state(base_engine):
    base_engine._pause = False
    base_engine._stopped = False
    base_engine.suspend_client()

    base_engine._pause = True
    with pytest.raises(ThreadInterrupt):
        base_engine.suspend_client()

    base_engine._pause = False
    base_engine._stopped = True
    with pytest.raises(ThreadInterrupt):
        base_engine.suspend_client()


def test_set_download_dir_reuses_existing_directory(base_engine, tmp_path):
    existing = tmp_path / "existing-downloads"
    existing.mkdir()
    base_engine.download_dir = existing

    with patch.object(engine_module, "find_suitable_tmp_dir") as find_tmp:
        assert base_engine._set_download_dir() == existing
    find_tmp.assert_not_called()


def test_set_download_dir_creates_engine_specific_directory(base_engine, tmp_path):
    scratch = tmp_path / "scratch"
    expected = scratch / ".tmp" / base_engine.uid
    base_engine.download_dir = ROOT

    with (
        patch.object(engine_module, "find_suitable_tmp_dir", return_value=scratch),
        patch.object(engine_module, "safe_long_path", side_effect=lambda path: path),
    ):
        result = base_engine._set_download_dir()

    assert result == expected
    assert expected.is_dir()
    assert base_engine.local.download_dir == expected


def test_csv_directory_is_created_and_temporary_files_are_cleaned(
    base_engine, tmp_path
):
    csv_dir = engine_module.safe_long_path(base_engine.manager.home) / "csv"
    assert base_engine._set_csv_dir_or_cleanup() == csv_dir
    assert csv_dir.is_dir()

    temporary = csv_dir / "export.tmp"
    permanent = csv_dir / "export.csv"
    temporary.write_text("temporary")
    permanent.write_text("permanent")
    assert base_engine._set_csv_dir_or_cleanup() == csv_dir
    assert not temporary.exists()
    assert permanent.exists()


def test_set_local_folder_lock_waits_without_sleeping(base_engine, tmp_path):
    path = tmp_path / "locked"
    base_engine.queue_manager.has_file_processors_on.side_effect = [True, True, False]

    with patch.object(engine_module, "sleep") as sleep_mock:
        base_engine.set_local_folder_lock(path)

    assert base_engine._folder_lock == path
    assert sleep_mock.call_count == 2


def test_delete_doc_handles_missing_and_unknown_pairs(base_engine):
    config = SimpleNamespace(fs_item_id_format=FileSystemID.UUID)
    with patch("nxdrive.drive.server_type.get_by_engine_type", return_value=config):
        base_engine.dao.get_state_from_local.return_value = None
        base_engine.delete_doc(Path("missing"))
        base_engine.dao.remove_state.assert_not_called()

        pair = make_pair(remote_state="unknown")
        base_engine.dao.get_state_from_local.return_value = pair
        base_engine.delete_doc(pair.local_path)
        base_engine.dao.remove_state.assert_called_once_with(pair)


def test_delete_doc_uses_configured_server_deletion_behavior(base_engine):
    pair = make_pair()
    base_engine.dao.get_state_from_local.return_value = pair
    base_engine.manager.get_deletion_behavior.return_value = DelAction.DEL_SERVER
    config = SimpleNamespace(fs_item_id_format=FileSystemID.UUID)

    with patch("nxdrive.drive.server_type.get_by_engine_type", return_value=config):
        base_engine.delete_doc(pair.local_path)

    pair.update_state.assert_called_once_with("deleted", "synchronized")
    base_engine.dao.delete_local_state.assert_called_once_with(pair)


def test_delete_doc_unsyncs_opaque_server_items(base_engine):
    pair = make_pair(remote_parent_path="/parent", remote_ref="opaque-ref")
    base_engine.dao.get_state_from_local.return_value = pair
    config = SimpleNamespace(fs_item_id_format=FileSystemID.UUID)

    with patch("nxdrive.drive.server_type.get_by_engine_type", return_value=config):
        base_engine.delete_doc(pair.local_path, mode=DelAction.UNSYNC)

    base_engine.dao.remove_state.assert_called_once_with(pair)
    base_engine.dao.add_filter.assert_called_once_with("/parent/opaque-ref")


def test_delete_doc_unsync_requires_complete_remote_identity(base_engine):
    pair = make_pair(remote_parent_path="", remote_ref="")
    base_engine.dao.get_state_from_local.return_value = pair
    config = SimpleNamespace(fs_item_id_format=FileSystemID.UUID)

    with patch("nxdrive.drive.server_type.get_by_engine_type", return_value=config):
        base_engine.delete_doc(pair.local_path, mode=DelAction.UNSYNC)

    base_engine.dao.remove_state.assert_called_once_with(pair)
    base_engine.dao.add_filter.assert_not_called()


def test_delete_doc_uses_human_server_path_for_filter(base_engine):
    pair = make_pair()
    base_engine.dao.get_state_from_local.return_value = pair
    base_engine.remote.get_fs_info.return_value = SimpleNamespace(
        path="/Company Home/Sites/file.txt"
    )
    config = SimpleNamespace(fs_item_id_format=FileSystemID.HUMANTEXT)

    with patch("nxdrive.drive.server_type.get_by_engine_type", return_value=config):
        base_engine.delete_doc(pair.local_path, mode=DelAction.UNSYNC)

    base_engine.dao.remove_state.assert_called_once_with(pair)
    base_engine.dao.add_filter.assert_called_once_with("/Company Home/Sites/file.txt")


def test_delete_doc_keeps_human_server_pair_when_path_lookup_fails(base_engine):
    pair = make_pair()
    base_engine.dao.get_state_from_local.return_value = pair
    base_engine.remote.get_fs_info.side_effect = RuntimeError("offline")
    config = SimpleNamespace(fs_item_id_format=FileSystemID.HUMANTEXT)

    with patch("nxdrive.drive.server_type.get_by_engine_type", return_value=config):
        base_engine.delete_doc(pair.local_path, mode=DelAction.UNSYNC)

    base_engine.dao.remove_state.assert_not_called()
    base_engine.dao.add_filter.assert_not_called()


def test_resume_suspended_transfers_dispatches_all_transfer_kinds(base_engine):
    base_engine._resume_transfers = MagicMock()
    base_engine._check_sync_start = MagicMock()

    Engine.resume_suspended_transfers(base_engine)

    assert base_engine._resume_transfers.call_count == 3
    first, second, third = base_engine._resume_transfers.call_args_list
    assert first.args[0] == "download"
    assert first.args[1].func == base_engine.dao.get_downloads_with_status
    assert first.args[1].args == (TransferStatus.SUSPENDED,)
    assert second.args[0] == "upload"
    assert second.args[1].func == base_engine.dao.get_uploads_with_status
    assert third.args[1].func == base_engine.dao.get_dt_uploads_with_status
    assert third.kwargs == {"is_direct_transfer": True}
    base_engine._check_sync_start.assert_called_once()


@pytest.mark.parametrize("accepted", [True, False])
def test_resume_scheduled_session_honors_user_choice(base_engine, accepted):
    uid = 42
    base_engine.dao.get_session.return_value = SimpleNamespace(
        scheduled_at="2026-08-05T12:00:00Z"
    )
    base_engine.cancel_scheduled_timer = MagicMock()

    with patch(
        "nxdrive.drive.gui.schedule_dialog.ResumeScheduledSessionPopup"
    ) as popup_cls:
        popup_cls.return_value.exec.return_value = accepted
        base_engine.resume_session(uid)

    popup_cls.assert_called_once_with(
        parent=None, scheduled_datetime="2026-08-05T12:00:00Z"
    )
    if accepted:
        base_engine.cancel_scheduled_timer.assert_called_once_with(uid)
        base_engine.dao.change_session_status.assert_called_once_with(
            uid, TransferStatus.ONGOING
        )
        base_engine.dao.reset_session_schedule.assert_called_once_with(uid)
        base_engine.dao.resume_session.assert_called_once_with(uid)
        base_engine.dao.pause_session.assert_not_called()
    else:
        base_engine.dao.pause_session.assert_called_once_with(uid)
        base_engine.dao.resume_session.assert_not_called()


def test_resume_unscheduled_and_resume_scheduled_session(base_engine):
    uid = 7
    base_engine.dao.get_session.return_value = None
    base_engine.resume_session(uid)
    base_engine.dao.change_session_status.assert_called_once_with(
        uid, TransferStatus.ONGOING
    )
    base_engine.dao.resume_session.assert_called_once_with(uid)

    base_engine.dao.reset_mock()
    base_engine.resume_session = MagicMock()
    Engine.resume_scheduled_session(base_engine, uid)
    base_engine.dao.reset_session_schedule.assert_called_once_with(uid)
    base_engine.resume_session.assert_called_once_with(uid)


def test_scheduled_timer_finishes_without_an_event_loop(base_engine):
    base_engine.resume_scheduled_session = MagicMock()
    with patch.object(engine_module, "QTimer", FakeTimer):
        base_engine.start_scheduled_timer(11, 5)

    timer = base_engine._scheduled_timers[11]
    assert timer.single_shot is True
    assert timer.intervals == [5000]
    assert timer.start_count == 1

    timer.setProperty("remaining_ms", None)
    timer.fire()
    assert 11 not in base_engine._scheduled_timers
    assert timer.stopped is True
    assert timer.deleted is True
    base_engine.resume_scheduled_session.assert_called_once_with(11)


def test_scheduled_timer_chunks_values_above_qt_integer_limit(base_engine):
    max_ms = 2_147_483_647
    delay_seconds = (max_ms * 2 + 1000) // 1000
    base_engine.resume_scheduled_session = MagicMock()

    with patch.object(engine_module, "QTimer", FakeTimer):
        base_engine.start_scheduled_timer(12, delay_seconds)

    timer = base_engine._scheduled_timers[12]
    assert timer.intervals == [max_ms]
    timer.fire()
    assert timer.intervals[-1] == max_ms
    assert 12 in base_engine._scheduled_timers
    timer.fire()
    assert timer.intervals[-1] < max_ms
    assert 12 in base_engine._scheduled_timers
    timer.fire()
    assert 12 not in base_engine._scheduled_timers
    base_engine.resume_scheduled_session.assert_called_once_with(12)


def test_cancel_scheduled_timer_is_idempotent(base_engine):
    timer = FakeTimer(base_engine)
    base_engine._scheduled_timers[3] = timer

    base_engine.cancel_scheduled_timer(3)
    base_engine.cancel_scheduled_timer(3)

    assert timer.stopped is True
    assert timer.deleted is True


@pytest.mark.parametrize("has_crashed", [True, False])
def test_manage_staled_transfers_covers_downloads_and_direct_uploads(
    base_engine, has_crashed
):
    download = SimpleNamespace(
        path=Path("download.bin"),
        status=TransferStatus.ONGOING,
        is_direct_transfer=False,
    )
    upload = SimpleNamespace(
        path=Path("upload.bin"),
        status=TransferStatus.ONGOING,
        is_direct_transfer=True,
    )
    base_engine.dao.get_downloads_with_status.return_value = [download]
    base_engine.dao.get_uploads_with_status.return_value = [upload]

    with patch.object(engine_module.State, "has_crashed", has_crashed):
        base_engine._manage_staled_transfers()

    if has_crashed:
        assert download.status is TransferStatus.SUSPENDED
        assert upload.status is TransferStatus.SUSPENDED
        base_engine.dao.set_transfer_status.assert_has_calls(
            [call("download", download), call("upload", upload)]
        )
    else:
        base_engine.dao.remove_transfer.assert_has_calls(
            [
                call(
                    "download",
                    path=download.path,
                    is_direct_transfer=False,
                ),
                call("upload", path=upload.path, is_direct_transfer=True),
            ]
        )


def test_cancel_session_cancels_timer_and_persisted_schedule(base_engine):
    base_engine.cancel_session(9)

    base_engine.cancelTimerSignal.emit.assert_called_once_with(9)
    base_engine.dao.reset_session_schedule.assert_called_once_with(9)
    base_engine.dao.cancel_session.assert_called_once_with(9)


@pytest.mark.parametrize(
    ("local_empty", "queue_size", "active"),
    [(False, 0, False), (True, 2, False), (True, 0, True)],
)
def test_check_last_sync_waits_for_all_work_to_settle(
    base_engine, local_empty, queue_size, active
):
    base_engine._sync_started = True
    base_engine._local_watcher.empty_events.return_value = local_empty
    base_engine._remote_watcher.empty_polls = 2
    base_engine.queue_manager.get_overall_size.return_value = queue_size
    base_engine.queue_manager.active.return_value = active

    base_engine._check_last_sync()

    assert base_engine._sync_started is True
    base_engine.syncCompleted.emit.assert_not_called()
    base_engine.syncPartialCompleted.emit.assert_not_called()


@pytest.mark.parametrize("errors", [0, 2])
def test_check_last_sync_emits_complete_or_partial(base_engine, errors):
    base_engine._sync_started = True
    base_engine._local_watcher.empty_events.return_value = True
    base_engine._remote_watcher.empty_polls = 2
    base_engine.queue_manager.get_overall_size.return_value = 0
    base_engine.queue_manager.active.return_value = False
    base_engine.queue_manager.get_errors_count.return_value = errors
    finished_at = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)

    clock = nullcontext()
    if not errors:
        clock = patch.object(engine_module, "datetime")

    with clock as datetime_mock:
        if not errors:
            datetime_mock.now.return_value = finished_at
        base_engine._check_last_sync()

    if errors:
        assert base_engine._sync_started is True
        base_engine.syncPartialCompleted.emit.assert_called_once()
        base_engine.syncCompleted.emit.assert_not_called()
    else:
        assert base_engine._sync_started is False
        base_engine.dao.update_config.assert_called_once_with(
            "last_sync_date", finished_at
        )
        base_engine.syncCompleted.emit.assert_called_once()


def test_check_last_sync_returns_when_not_started(base_engine):
    base_engine._sync_started = False
    base_engine._check_last_sync()
    base_engine._local_watcher.empty_events.assert_not_called()


def test_thread_finished_keeps_watcher_threads(base_engine):
    local_thread = base_engine._local_watcher.thread
    remote_thread = base_engine._remote_watcher.thread
    local_thread.isFinished.return_value = True
    remote_thread.isFinished.return_value = True
    other = MagicMock()
    other.isFinished.return_value = False
    base_engine._threads = [local_thread, remote_thread, other]

    base_engine._thread_finished()

    assert base_engine._threads == [local_thread, remote_thread, other]
    local_thread.quit.assert_not_called()
    remote_thread.quit.assert_not_called()


def test_start_runs_lifecycle_in_order_and_resolves_conflicts(base_engine):
    thread = MagicMock()
    conflict = SimpleNamespace(id=81)
    base_engine._threads = [thread]
    base_engine.dao.get_conflicts.return_value = [conflict]
    base_engine._check_root = MagicMock()
    base_engine._manage_staled_transfers = MagicMock()
    base_engine.resume_suspended_transfers = MagicMock()
    base_engine.conflict_resolver = MagicMock()
    base_engine._stopped = True

    Engine.start(base_engine)

    base_engine._check_root.assert_called_once()
    base_engine.manager.server_config_updater.force_poll.assert_called_once()
    base_engine._manage_staled_transfers.assert_called_once()
    base_engine.resume_suspended_transfers.assert_called_once()
    assert base_engine._stopped is False
    thread.start.assert_called_once()
    base_engine.conflict_resolver.assert_called_once_with(81, emit=False)
    base_engine.syncStarted.emit.assert_called_once_with(0)
    base_engine.started.emit.assert_called_once()


def test_stop_terminates_unresponsive_workers_and_waits_for_shutdown(base_engine):
    worker_thread = MagicMock()
    worker_thread.wait.side_effect = [False, True]
    worker_thread.isRunning.return_value = True
    local_thread = MagicMock()
    local_thread.wait.side_effect = [False, True]
    local_thread.isRunning.return_value = False
    remote_thread = MagicMock()
    remote_thread.wait.side_effect = [False, True]
    remote_thread.isRunning.return_value = False
    base_engine._threads = [worker_thread]
    base_engine._local_watcher.thread = local_thread
    base_engine._remote_watcher.thread = remote_thread

    base_engine.stop()

    assert base_engine._stopped is True
    base_engine.dao.suspend_transfers.assert_called_once()
    base_engine.dao.save_backup.assert_called_once()
    base_engine.remote.metrics.force_poll.assert_called_once()
    base_engine._stop.emit.assert_called_once()
    worker_thread.terminate.assert_called_once()
    local_thread.terminate.assert_called_once()
    remote_thread.terminate.assert_called_once()
    assert worker_thread.wait.call_count == 2
    assert local_thread.wait.call_count == 2
    assert remote_thread.wait.call_count == 2


def test_update_token_same_user_updates_remote_and_restarts_engine(base_engine):
    token = {"access_token": "new"}
    base_engine._load_configuration = MagicMock()
    base_engine._save_token = MagicMock()
    base_engine.set_invalid_credentials = MagicMock()
    base_engine.start = MagicMock()

    Engine.update_token(base_engine, token, "alice")

    assert base_engine._remote_token == token
    base_engine.remote.update_token.assert_called_once_with(token)
    base_engine.set_invalid_credentials.assert_called_once_with(value=False)
    base_engine._save_token.assert_called_once_with(token)
    base_engine.start.assert_called_once()
    base_engine.manager.restartNeeded.emit.assert_not_called()


def test_update_token_changed_user_persists_user_before_token(base_engine):
    token = {"access_token": "new"}
    base_engine._load_configuration = MagicMock()
    base_engine._save_token = MagicMock()
    base_engine.set_invalid_credentials = MagicMock()
    base_engine.start = MagicMock()

    Engine.update_token(base_engine, token, "bob")

    assert base_engine.remote_user == "bob"
    base_engine.dao.update_config.assert_called_once_with("remote_user", "bob")
    base_engine._save_token.assert_called_once_with(token)
    base_engine.manager.restartNeeded.emit.assert_called_once()
    base_engine.start.assert_not_called()


def test_setup_local_folder_creates_and_checks_only_requested_path(
    base_engine, tmp_path
):
    folder = tmp_path / "new-sync"
    base_engine.local_folder = folder
    base_engine._check_fs = MagicMock()

    with patch.object(engine_module.Feature, "synchronization", True):
        base_engine._setup_local_folder(True)

    assert folder.is_dir()
    base_engine._check_fs.assert_called_once_with(folder)


def test_setup_local_folder_rolls_back_new_folder_without_xattrs(base_engine, tmp_path):
    folder = tmp_path / "unsupported-sync"
    base_engine.local_folder = folder
    error = MissingXattrSupport(folder)
    base_engine._check_fs = MagicMock(side_effect=error)

    with (
        patch.object(engine_module.Feature, "synchronization", True),
        pytest.raises(MissingXattrSupport) as raised,
    ):
        base_engine._setup_local_folder(True)

    assert raised.value is error
    base_engine.local.unset_readonly.assert_called_once_with(folder)
    assert not folder.exists()


def test_check_root_is_disabled_with_synchronization(base_engine):
    with patch.object(engine_module.Feature, "synchronization", False):
        base_engine._check_root()
    base_engine.dao.get_state_from_local.assert_not_called()


@pytest.mark.parametrize("folder_exists", [True, False])
def test_check_root_creates_local_and_persisted_root(base_engine, folder_exists):
    if not folder_exists:
        base_engine.local_folder.rmdir()
    base_engine.dao.get_state_from_local.return_value = None
    base_engine._add_top_level_state = MagicMock()
    base_engine._set_root_icon = MagicMock()

    with (
        patch.object(engine_module.Feature, "synchronization", True),
        patch.object(engine_module, "unset_path_readonly") as unset_readonly,
        patch.object(engine_module, "set_path_readonly") as set_readonly,
    ):
        Engine._check_root(base_engine)

    assert base_engine.local_folder.is_dir()
    if folder_exists:
        unset_readonly.assert_called_once_with(base_engine.local_folder)
    else:
        unset_readonly.assert_not_called()
    base_engine._add_top_level_state.assert_called_once()
    base_engine._set_root_icon.assert_called_once()
    base_engine.manager.osi.register_folder_link.assert_called_once_with(
        base_engine.local_folder
    )
    set_readonly.assert_called_once_with(base_engine.local_folder)


def test_check_root_leaves_existing_state_untouched(base_engine):
    base_engine.dao.get_state_from_local.return_value = object()
    base_engine._add_top_level_state = MagicMock()
    with patch.object(engine_module.Feature, "synchronization", True):
        Engine._check_root(base_engine)
    base_engine._add_top_level_state.assert_not_called()


def test_check_filesystem_requires_marker_support(base_engine):
    base_engine.check_fs_marker = MagicMock(return_value=False)
    with pytest.raises(MissingXattrSupport) as raised:
        base_engine._check_fs(base_engine.local_folder)
    assert raised.value.path == base_engine.local_folder


def test_check_filesystem_accepts_matching_root_binding(base_engine):
    base_engine.check_fs_marker = MagicMock(return_value=True)
    base_engine.local.get_root_id.return_value = (
        "https://server.example/|alice|device-id"
    )
    base_engine._check_fs(base_engine.local_folder)


def test_check_filesystem_rejects_another_account_binding(base_engine):
    base_engine.check_fs_marker = MagicMock(return_value=True)
    base_engine.local.get_root_id.return_value = (
        "https://other.example/|mallory|device-id"
    )

    with pytest.raises(RootAlreadyBindWithDifferentAccount):
        base_engine._check_fs(base_engine.local_folder)


def test_check_fs_marker_handles_missing_mismatch_and_success(base_engine, tmp_path):
    base_engine.local_folder = tmp_path / "missing"
    assert base_engine.check_fs_marker() is False
    base_engine.rootDeleted.emit.assert_called_once()

    base_engine.local_folder.mkdir()
    base_engine.local.get_remote_id.return_value = "wrong"
    assert base_engine.check_fs_marker() is False
    base_engine.local.remove_remote_id.assert_not_called()

    base_engine.local.get_remote_id.return_value = "NXDRIVE_VERIFICATION"
    assert base_engine.check_fs_marker() is True
    base_engine.local.set_remote_id.assert_called_with(
        ROOT, "NXDRIVE_VERIFICATION", name="drive-fs-test"
    )
    base_engine.local.remove_remote_id.assert_called_once_with(
        ROOT, name="drive-fs-test"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://server.example", "https://server.example/"),
        ("https://x/", "https://x/"),
    ],
)
def test_normalize_url(value, expected):
    assert Engine._normalize_url(value) == expected


def test_load_token_decrypts_json_and_migrates_clear_text(base_engine):
    base_engine.dao.get_config.return_value = "ciphertext"
    with patch.object(
        engine_module, "decrypt", return_value=b'{"access_token": "abc"}'
    ):
        assert base_engine._load_token() == {"access_token": "abc"}

    base_engine._save_token = MagicMock()
    base_engine.dao.get_config.return_value = "plain-token"
    decode_error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
    with patch.object(engine_module, "decrypt", side_effect=decode_error):
        assert Engine._load_token(base_engine) == "plain-token"
    base_engine._save_token.assert_called_once_with("plain-token")


def test_save_token_encrypts_strings_and_dictionaries(base_engine):
    with patch.object(engine_module, "encrypt", return_value=b"encrypted") as encrypt:
        base_engine._save_token({"access_token": "abc"})
    encrypt.assert_called_once_with(
        '{"access_token": "abc"}', "alicehttps://server.example/"
    )
    base_engine.dao.update_config.assert_called_once_with("remote_token", "encrypted")

    base_engine.dao.reset_mock()
    base_engine._save_token(None)
    base_engine.dao.update_config.assert_not_called()


def test_load_configuration_populates_fields_and_flags_missing_token(base_engine):
    values = {
        "server_url": "https://configured.example/",
        "ui": "jsf",
        "force_ui": "web",
        "remote_user": "configured-user",
    }
    base_engine.dao.get_bool.return_value = True
    base_engine.dao.get_config.side_effect = lambda key, default=None: values.get(
        key, default
    )
    base_engine._load_token = MagicMock(return_value=None)
    base_engine.set_invalid_credentials = MagicMock()

    Engine._load_configuration(base_engine)

    assert base_engine._web_authentication is True
    assert base_engine.server_url == "https://configured.example/"
    assert base_engine.hostname == "configured.example"
    assert base_engine.wui == "jsf"
    assert base_engine.force_ui == "web"
    assert base_engine.remote_user == "configured-user"
    base_engine.set_invalid_credentials.assert_called_once_with(
        reason="found no token in engine configuration"
    )


def test_database_file_binder_and_credential_state(base_engine, tmp_path):
    database = tmp_path / "engine.db"
    base_engine.manager.get_engine_db.return_value = database
    assert base_engine._get_db_file() == database
    base_engine.manager.get_engine_db.assert_called_once_with(
        base_engine.uid, base_engine.type
    )

    base_engine._web_authentication = True
    base_engine._invalid_credentials = True
    binder = base_engine.get_binder()
    assert binder == ServerBindingSettings(
        base_engine.server_url,
        True,
        "alice",
        base_engine.local_folder,
        True,
        pwd_update_required=True,
    )
    assert base_engine.has_invalid_credentials() is True

    base_engine._invalid_credentials = False
    base_engine.set_invalid_credentials(reason="expired")
    assert base_engine.has_invalid_credentials() is True
    base_engine.invalidAuthentication.emit.assert_called_once()
    base_engine.authChanged.emit.assert_called_once_with(base_engine.uid)

    base_engine.set_invalid_credentials(reason="duplicate")
    base_engine.invalidAuthentication.emit.assert_called_once()
    base_engine.authChanged.emit.assert_called_once_with(base_engine.uid)

    base_engine.set_invalid_credentials(value=False)
    assert base_engine.has_invalid_credentials() is False
    assert base_engine.authChanged.emit.call_count == 2


def test_local_rollback_rejects_non_boolean_values():
    assert Engine.local_rollback(force="yes") is False


def test_create_thread_builds_default_worker(base_engine):
    worker = MagicMock()
    worker.thread = MagicMock()
    with patch.object(engine_module, "Worker", return_value=worker) as worker_cls:
        thread = base_engine.create_thread(None, "PollWorker")

    worker_cls.assert_called_once_with(base_engine, name="PollWorker")
    assert thread is worker.thread
    worker.thread.started.connect.assert_called_once_with(worker.run)
    base_engine._stop.connect.assert_called_once_with(worker.quit)
    worker.thread.finished.connect.assert_called_once_with(base_engine._thread_finished)


def test_create_thread_relays_processor_pair_signals(base_engine):
    class ProcessorDouble:
        def __init__(self):
            self.thread = MagicMock()
            self.run = MagicMock()
            self.quit = MagicMock()
            self.pairSyncStarted = MagicMock()
            self.pairSyncEnded = MagicMock()

    worker = ProcessorDouble()
    with patch.object(engine_module, "Processor", ProcessorDouble):
        base_engine.create_thread(worker, "Processor")

    worker.pairSyncStarted.connect.assert_called_once_with(base_engine.newSyncStarted)
    worker.pairSyncEnded.connect.assert_called_once_with(base_engine.newSyncEnded)


def test_conflict_resolver_synchronizes_equivalent_pair(base_engine):
    pair = make_pair()
    base_engine.dao.get_state_from_id.return_value = pair
    base_engine.local.get_remote_id.return_value = pair.remote_parent_ref
    base_engine.local.is_equal_digests.return_value = True

    base_engine.conflict_resolver(pair.id)

    base_engine.dao.synchronize_state.assert_called_once_with(pair)
    base_engine.newConflict.emit.assert_not_called()


def test_conflict_resolver_emits_meaningful_conflict(base_engine):
    pair = make_pair(remote_name="remote.txt")
    base_engine.dao.get_state_from_id.return_value = pair
    base_engine.local.get_remote_id.return_value = "another-parent"
    base_engine.local.is_equal_digests.return_value = False
    base_engine.local.abspath.return_value = base_engine.local_folder / "file.txt"

    base_engine.conflict_resolver(pair.id)

    base_engine.newConflict.emit.assert_called_once_with(pair.id)
    base_engine.manager.osi.send_sync_status.assert_called_once_with(
        pair, base_engine.local.abspath.return_value
    )


def test_conflict_resolver_skips_missing_pair_and_suppresses_expected_errors(
    base_engine,
):
    base_engine.dao.get_state_from_id.return_value = None
    base_engine.conflict_resolver(404)
    base_engine.newConflict.emit.assert_not_called()

    pair = make_pair()
    base_engine.dao.get_state_from_id.return_value = pair
    for error in (
        ThreadInterrupt(),
        UnknownDigest("sha-unknown"),
        RuntimeError("broken digest"),
    ):
        base_engine.local.get_remote_id.side_effect = error
        base_engine.conflict_resolver(pair.id)
    base_engine.newConflict.emit.assert_not_called()


def test_check_https_keeps_https_server(base_engine):
    with option_values(is_frozen=True):
        base_engine._check_https()
    base_engine.manager.proxy.settings.assert_not_called()


def test_check_https_upgrades_http_when_probe_succeeds(base_engine):
    base_engine.server_url = "http://server.example/"
    base_engine.hostname = "server.example"
    base_engine.manager.proxy.settings.return_value = {"https": "proxy"}

    with (
        option_values(is_frozen=True),
        patch.object(engine_module.requests, "get") as request,
    ):
        base_engine._check_https()

    request.assert_called_once_with(
        "https://server.example/", proxies={"https": "proxy"}
    )
    assert base_engine.server_url == "https://server.example/"
    base_engine.dao.update_config.assert_called_once_with(
        "server_url", "https://server.example/"
    )


def test_check_https_keeps_http_when_probe_fails(base_engine):
    base_engine.server_url = "http://production.example/"
    base_engine.hostname = "production.example"

    with (
        option_values(is_frozen=True),
        patch.object(
            engine_module.requests, "get", side_effect=RuntimeError("TLS failed")
        ),
    ):
        base_engine._check_https()

    assert base_engine.server_url == "http://production.example/"
    base_engine.dao.update_config.assert_not_called()


def test_cancel_action_on_ignores_nonprocessors_and_stops_matching_worker(base_engine):
    pair = SimpleNamespace(id=31)
    no_pair_worker = SimpleNamespace(
        get_current_pair=MagicMock(return_value=None), quit=MagicMock()
    )
    other_worker = SimpleNamespace(
        get_current_pair=MagicMock(return_value=SimpleNamespace(id=32)),
        quit=MagicMock(),
    )
    matching_worker = SimpleNamespace(
        get_current_pair=MagicMock(return_value=pair), quit=MagicMock()
    )
    base_engine._threads = [
        object(),
        SimpleNamespace(worker=object()),
        SimpleNamespace(worker=no_pair_worker),
        SimpleNamespace(worker=other_worker),
        SimpleNamespace(worker=matching_worker),
    ]

    base_engine.cancel_action_on(pair.id)

    no_pair_worker.quit.assert_not_called()
    other_worker.quit.assert_not_called()
    matching_worker.quit.assert_called_once()


@pytest.mark.parametrize(
    ("linux", "mac", "icon_name"),
    [
        (True, False, "emblem.svg"),
        (False, True, "folder_mac.dat"),
        (False, False, "folder_windows.ico"),
    ],
)
def test_set_root_icon_uses_platform_asset(
    base_engine, tmp_path, linux, mac, icon_name
):
    icon = tmp_path / icon_name
    base_engine.local.has_folder_icon.return_value = False
    base_engine.local.unlock_ref.return_value = "locker"

    with (
        option_values(is_frozen=True),
        patch.object(engine_module, "LINUX", linux),
        patch.object(engine_module, "MAC", mac),
        patch.object(engine_module, "find_icon", return_value=icon) as find_icon,
    ):
        base_engine._set_root_icon()

    find_icon.assert_called_once_with(icon_name)
    base_engine.local.set_folder_icon.assert_called_once_with(ROOT, icon)
    base_engine.local.lock_ref.assert_called_once_with(ROOT, "locker")


def test_set_root_icon_handles_existing_missing_and_failed_icon(base_engine):
    with option_values(is_frozen=True):
        base_engine.local.has_folder_icon.return_value = True
        base_engine._set_root_icon()
    base_engine.local.unlock_ref.assert_not_called()

    base_engine.local.has_folder_icon.return_value = False
    with (
        option_values(is_frozen=True),
        patch.object(engine_module, "LINUX", True),
        patch.object(engine_module, "find_icon", return_value=None),
    ):
        base_engine._set_root_icon()
    base_engine.local.unlock_ref.assert_not_called()

    base_engine.local.unlock_ref.return_value = "locker"
    base_engine.local.set_folder_icon.side_effect = OSError("read only")
    with (
        option_values(is_frozen=True),
        patch.object(engine_module, "LINUX", True),
        patch.object(engine_module, "find_icon", return_value=Path("icon.svg")),
    ):
        base_engine._set_root_icon()
    base_engine.local.lock_ref.assert_called_once_with(ROOT, "locker")


@pytest.mark.parametrize("error", [FileNotFoundError(), OSError("busy")])
def test_unbind_tolerates_download_directory_cleanup_errors(base_engine, error):
    base_engine.stop = MagicMock()
    base_engine.dispose_db = MagicMock()
    with patch.object(engine_module.shutil, "rmtree", side_effect=error):
        base_engine.unbind()

    base_engine.stop.assert_called_once()
    base_engine.manager.osi.unwatch_folder.assert_called_once_with(
        base_engine.local_folder
    )
    base_engine.manager.osi.unregister_folder_link.assert_called_once_with(
        base_engine.local_folder
    )
    base_engine.dispose_db.assert_called_once()
    base_engine.manager.remove_engine_dbs.assert_called_once_with(base_engine.uid)
    base_engine.remote.revoke_token.assert_called_once()


def test_dispose_db_handles_present_and_missing_dao(base_engine):
    base_engine.dispose_db()
    base_engine.dao.dispose.assert_called_once()

    base_engine.dao = None
    base_engine.dispose_db()
