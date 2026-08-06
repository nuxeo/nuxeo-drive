"""Coverage for shared workers, translation, registry, and value helpers."""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

from nxdrive.drive import autolocker, commandline, digest, objects, poll_workers
from nxdrive.drive import server_type, version
from nxdrive.drive import translator as translator_module
from nxdrive.drive.engine import workers
from nxdrive.drive.exceptions import (
    EngineInitError,
    ThreadInterrupt,
    UnknownDigest,
    UnknownPairState,
)
from nxdrive.drive.objects import Upload
from nxdrive.drive.server_type import ServerTypeConfig
from nxdrive.drive.translator import Translator


def test_worker_interaction_processes_a_pause_cycle(monkeypatch):
    worker = SimpleNamespace(_pause=True, _continue=True)

    def release_pause(_delay):
        worker._pause = False

    process_events = Mock()
    monkeypatch.setattr(workers.QCoreApplication, "processEvents", process_events)
    monkeypatch.setattr(workers, "sleep", release_pause)

    workers.Worker._interact(worker)

    assert process_events.call_count == 2


def test_base_worker_execute_loops_until_interrupted(monkeypatch):
    worker = SimpleNamespace(
        _interact=Mock(side_effect=[None, ThreadInterrupt()]),
    )
    sleep = Mock()
    monkeypatch.setattr(workers, "sleep", sleep)

    with pytest.raises(ThreadInterrupt):
        workers.Worker._execute(worker)

    sleep.assert_called_once_with(0.01)


def test_poll_worker_execute_records_successful_poll(monkeypatch):
    worker = SimpleNamespace(
        _interact=Mock(side_effect=[None, ThreadInterrupt()]),
        get_next_poll=Mock(return_value=0),
        enable=True,
        _poll=Mock(return_value=True),
        _metrics={"last_poll": 0},
        _next_check=0,
        _check_interval=60,
    )
    monkeypatch.setattr(workers, "time", Mock(return_value=100))
    monkeypatch.setattr(workers, "sleep", Mock())

    with pytest.raises(ThreadInterrupt):
        workers.PollWorker._execute(worker)

    assert worker._metrics["last_poll"] == 100
    assert worker._next_check == 160


@pytest.fixture(autouse=True)
def restore_translator_state():
    singleton = Translator.singleton
    language = Translator.current_language
    cache = dict(translator_module._CACHE)
    yield
    Translator.singleton = singleton
    Translator.current_language = language
    translator_module._CACHE.clear()
    translator_module._CACHE.update(cache)


def test_translator_copies_compatibility_resources_to_missing_i18n_path(tmp_path):
    target = tmp_path / "generated" / "i18n"

    translator = Translator(target)

    assert translator.current_language == "en"
    assert (target / "i18n.json").is_file()


def test_translator_falls_back_to_compatibility_path_when_copy_fails(tmp_path):
    target = tmp_path / "i18n"
    with patch.object(Path, "mkdir", side_effect=OSError("read only")):
        translator = Translator(target)

    assert translator.current_language == "en"


@pytest.mark.parametrize(
    "operation",
    [
        lambda: Translator.on_change(Mock()),
        lambda: Translator.set("en"),
        Translator.locale,
        Translator.languages,
    ],
)
def test_translator_static_operations_require_initialization(operation):
    Translator.singleton = None
    with pytest.raises(RuntimeError, match="not initialized"):
        operation()


def test_translator_formats_datetime_through_active_labels():
    Translator.singleton = SimpleNamespace(
        get_translation=Mock(return_value="%Y/%m/%d")
    )
    value = datetime(2026, 8, 6)

    assert Translator.format_datetime(value) == "2026/08/06"


def test_server_options_normalizes_home_and_requests_restart(monkeypatch, tmp_path):
    config = {"nxdrive_home": "$HOME/Shared"}
    engine = SimpleNamespace(
        remote=SimpleNamespace(get_server_configuration=Mock(return_value=config)),
        set_ui=Mock(),
    )
    restart = SimpleNamespace(emit=Mock())
    manager = SimpleNamespace(
        engines={"engine": engine},
        restartNeeded=restart,
        set_feature_state=Mock(),
    )
    updater = SimpleNamespace(manager=manager, first_run=False)
    options = SimpleNamespace(feature_synchronization=False)

    def update(_config, **_kwargs):
        options.feature_synchronization = True

    options.update = Mock(side_effect=update)
    monkeypatch.setattr(poll_workers, "Options", options)
    normalize = Mock(return_value=tmp_path / "Shared")
    monkeypatch.setattr(poll_workers, "normalize_and_expand_path", normalize)

    assert poll_workers.ServerOptionsUpdater._poll(updater) is True
    normalize.assert_called_once_with("$HOME/Shared")
    restart.emit.assert_called_once_with()


def test_sync_and_quit_skips_its_first_check():
    worker = SimpleNamespace(_first_check=True)
    assert poll_workers.SyncAndQuitWorker._poll(worker) is True
    assert worker._first_check is False


def test_sync_and_quit_exits_after_idle_sync(monkeypatch):
    application = SimpleNamespace(quit=Mock())
    manager = SimpleNamespace(
        is_started=Mock(return_value=True),
        is_syncing=Mock(return_value=False),
        updater=SimpleNamespace(status="idle"),
        application=application,
    )
    worker = SimpleNamespace(_first_check=False, manager=manager)
    monkeypatch.setattr(poll_workers, "Options", SimpleNamespace(sync_and_quit=True))

    assert poll_workers.SyncAndQuitWorker._poll(worker) is True
    application.quit.assert_called_once_with()


def test_workflow_worker_accepts_an_unregistered_workflow(monkeypatch):
    application = SimpleNamespace(workflow=None)
    manager = SimpleNamespace(engines={"engine": object()}, application=application)
    worker = SimpleNamespace(
        manager=manager,
        _first_workflow_check=False,
    )
    monkeypatch.setattr(poll_workers, "Feature", SimpleNamespace(tasks_management=True))

    assert poll_workers.WorkflowWorker._poll(worker) is True


def _config(key, **overrides):
    values = {
        "key": key,
        "home_dir": f".{key.lower()}",
        "log_file": f"{key.lower()}.log",
        "db_prefix": f"{key.lower()}_",
        "engine_type": f"{key}_ENGINE",
    }
    values.update(overrides)
    return ServerTypeConfig(**values)


def test_registry_home_directories_and_engine_fallback(monkeypatch):
    primary = _config("PRIMARY")
    secondary = _config("SECONDARY")
    monkeypatch.setattr(
        server_type, "_registry", {primary.key: primary, secondary.key: secondary}
    )
    monkeypatch.setattr(server_type, "_default_key", primary.key)

    assert server_type.all_home_dirs() == (".primary", ".secondary")
    assert server_type.get_by_engine_type("missing") is primary


def test_load_class_handles_empty_and_invalid_paths():
    assert server_type.load_class("") is None
    assert server_type.load_class("missing.module.Class") is None


def test_first_class_path_scans_non_default_configs(monkeypatch):
    primary = _config("PRIMARY")
    secondary = _config("SECONDARY", workflow_class_path="builtins.str")
    monkeypatch.setattr(
        server_type, "_registry", {primary.key: primary, secondary.key: secondary}
    )
    monkeypatch.setattr(server_type, "_default_key", primary.key)

    assert server_type.first_class_path("workflow_class_path") == "builtins.str"
    assert server_type.first_class_path("document_info_class_path") == ""


def test_to_date_returns_none_for_platform_timestamp_errors(monkeypatch):
    broken_datetime = SimpleNamespace(
        fromtimestamp=Mock(side_effect=OSError("out of range"))
    )
    monkeypatch.setattr(objects, "datetime", broken_datetime)

    assert objects._to_date(1_000) is None


def test_doc_pair_readonly_handles_folder_and_file_permissions():
    folder = SimpleNamespace(folderish=True, remote_can_create_child=0)
    file_ = SimpleNamespace(
        folderish=False,
        remote_can_delete=1,
        remote_can_rename=1,
        remote_can_update=0,
    )

    assert objects.DocPair.is_readonly(folder) is True
    assert objects.DocPair.is_readonly(file_) is True


def test_upload_token_callback_marks_transfer_dirty():
    upload = SimpleNamespace(batch={}, is_dirty=False)
    batch = SimpleNamespace(as_dict=Mock(return_value={"id": "batch"}))

    Upload.token_callback(upload, batch, {})

    assert upload.batch == {"id": "batch"}
    assert upload.is_dirty is True


def test_version_comparison_zero_none_and_instance_suffixes():
    version.version_compare_client.cache_clear()
    assert version._cmp("0", "1") == -1
    assert version._cmp("1", "0") == 1
    assert version.version_compare_client(None, None) == 0
    assert version.version_compare_client("1.0-I1", "2.0-I2") == -1


def test_digest_snapshot_shorter_and_fallback_versions():
    digest.version_compare.cache_clear()
    digest.version_compare_client.cache_clear()

    assert digest.version_compare("2", "2-SNAPSHOT") == 1
    assert digest.version_compare("1", "1.1") == -1
    assert digest.version_compare_client("1.0-HF1", "1.0") == 1


def test_shared_exception_string_representations():
    engine = object()
    assert str(EngineInitError(engine)) == f"Engine initialization error for {engine!r}"
    assert str(UnknownDigest("bad")) == "Unknown digest 'bad'"
    assert str(UnknownPairState("local", "remote")) == (
        "Unknown pair state for 'local' and 'remote'"
    )


def test_autolocker_recognizes_tracked_and_uninteresting_files(monkeypatch, tmp_path):
    watched = tmp_path / "watched"
    tracked = tmp_path / "external.txt"
    unrelated = tmp_path / "unrelated.txt"
    worker = SimpleNamespace(
        _folder=watched,
        _autolocked={tracked: 7},
        _to_lock=[],
        _lock_files=Mock(),
        _unlock_files=Mock(),
        direct_edit=None,
    )
    monkeypatch.setattr(autolocker, "WINDOWS", False)
    monkeypatch.setattr(
        autolocker,
        "Options",
        SimpleNamespace(ignored_prefixes=("~",), ignored_suffixes=(".tmp",)),
    )
    monkeypatch.setattr(
        autolocker, "get_open_files", Mock(return_value=[(8, tracked), (9, unrelated)])
    )
    monkeypatch.setattr(autolocker, "sleep", Mock())

    autolocker.ProcessAutoLockerWorker._process(worker)

    assert worker._autolocked[tracked] == 8
    worker._lock_files.assert_not_called()
    worker._unlock_files.assert_not_called()


def test_commandline_supported_keys_fall_back_to_registry(monkeypatch):
    monkeypatch.setattr(Path, "read_text", Mock(side_effect=OSError("missing")))
    monkeypatch.setattr(server_type, "all_keys", Mock(return_value=("PRIMARY",)))

    assert commandline.CliHandler._load_supported_server_keys() == ["PRIMARY"]
    server_type.all_keys.assert_has_calls([call(), call()])
