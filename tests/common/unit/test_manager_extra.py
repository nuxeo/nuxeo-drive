import sqlite3
from copy import deepcopy
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call
from urllib.parse import urlsplit

import pytest

import nxdrive.drive.constants as constants
import nxdrive.drive.feature as feature_module
import nxdrive.drive.manager as manager_module
from nxdrive.drive import server_type as st
from nxdrive.drive.constants import DelAction
from nxdrive.drive.exceptions import (
    AddonForbiddenError,
    EngineInitError,
    EngineTypeMissing,
    FolderAlreadyUsed,
    MissingXattrSupport,
    NoAssociatedSoftware,
    StartupPageConnectionError,
)
from nxdrive.drive.feature import DisabledFeatures, Feature
from nxdrive.drive.manager import Manager
from nxdrive.drive.objects import Binder
from nxdrive.drive.options import DEFAULT_LOG_LEVEL_FILE, MetaOptions, Options
from nxdrive.drive.qt.imports import QObject
from nxdrive.drive.updater.constants import Login


class StubResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


def make_dao(config=None, *, migration_success=True):
    values = dict(config or {})
    dao = MagicMock()
    dao.migration_success = migration_success

    def get_config(key, *, default=None):
        return values.get(key, default)

    def update_config(key, value):
        values[key] = value

    def delete_config(key):
        values.pop(key, None)

    def get_bool(key, *, default=False):
        return bool(values.get(key, default))

    def store_bool(key, value):
        values[key] = value

    dao.get_config.side_effect = get_config
    dao.update_config.side_effect = update_config
    dao.delete_config.side_effect = delete_config
    dao.get_bool.side_effect = get_bool
    dao.store_bool.side_effect = store_bool
    dao.values = values
    return dao


@pytest.fixture(autouse=True)
def isolate_manager_globals():
    option_state = deepcopy(MetaOptions.options)
    callback_state = MetaOptions.callbacks.copy()
    feature_state = vars(Feature).copy()
    disabled_state = list(DisabledFeatures)
    beta_state = list(feature_module.Beta)
    registry_state = dict(st._registry)
    default_server_type = st._default_key
    instance_state = dict(Manager._instances)
    device_id = Manager._Manager__device_id
    branding = {
        name: getattr(constants, name)
        for name in (
            "APP_NAME",
            "COMPANY",
            "BUNDLE_IDENTIFIER",
            "NXDRIVE_SCHEME",
            "CONFIG_REGISTRY_KEY",
        )
    }

    try:
        yield
    finally:
        MetaOptions.options = option_state
        MetaOptions.callbacks = callback_state
        vars(Feature).clear()
        vars(Feature).update(feature_state)
        DisabledFeatures[:] = disabled_state
        feature_module.Beta[:] = beta_state
        st._registry.clear()
        st._registry.update(registry_state)
        st._default_key = default_server_type
        Manager._instances.clear()
        Manager._instances.update(instance_state)
        Manager._Manager__device_id = device_id
        for name, value in branding.items():
            setattr(constants, name, value)


@pytest.fixture
def manager_obj(app, tmp_path):
    manager = Manager.__new__(Manager)
    QObject.__init__(manager)
    manager.home = tmp_path
    manager.dao = make_dao()
    manager.osi = MagicMock()
    manager.proxy = MagicMock()
    manager.tracker = MagicMock()
    manager.updater = MagicMock()
    manager.server_config_updater = MagicMock(first_run=False)
    manager.db_backup_worker = None
    manager.direct_download = None
    manager.engines = {}
    manager._engine_definitions = []
    manager._engine_types = {}
    manager.delete_users_from_tasks_cache = [str]
    manager.is_paused = False
    manager._started = False
    return manager


def patch_constructor_dependencies(monkeypatch, dao):
    server_config_updater = MagicMock(first_run=True)
    application_updater = MagicMock()
    notification_service = MagicMock()
    osi = MagicMock()
    osi.nature = "mock"
    proxy = MagicMock(name="proxy")
    tracker = MagicMock()
    db_backup_worker = MagicMock()
    sync_and_quit_worker = SimpleNamespace(thread=MagicMock())
    autolock = MagicMock()
    direct_edit = MagicMock()
    direct_download = MagicMock()
    guess_sync = Mock()
    apply_server_config = Mock()
    load = Mock()
    extension_listener = Mock()
    workflow = Mock()

    def create_dao(self):
        self.dao = dao

    def create_db_backup(self):
        self.db_backup_worker = db_backup_worker

    monkeypatch.setattr(Manager, "_create_dao", create_dao)
    monkeypatch.setattr(
        Manager,
        "_create_server_config_updater",
        lambda self: server_config_updater,
    )
    monkeypatch.setattr(Manager, "_create_updater", lambda self: application_updater)
    monkeypatch.setattr(
        Manager,
        "_build_engine_types",
        staticmethod(lambda: {"NXDRIVE": Mock()}),
    )
    monkeypatch.setattr(Manager, "_save_or_load_proxy", lambda self: proxy)
    monkeypatch.setattr(Manager, "get_log_level", lambda self: "INFO")
    monkeypatch.setattr(Manager, "_guess_synchronization_state", guess_sync)
    monkeypatch.setattr(Manager, "check_metrics_preferences", Mock())
    monkeypatch.setattr(Manager, "_apply_server_type_config", apply_server_config)
    monkeypatch.setattr(Manager, "_create_db_backup_worker", create_db_backup)
    monkeypatch.setattr(Manager, "create_tracker", lambda self: tracker)
    monkeypatch.setattr(Manager, "_create_extension_listener", extension_listener)
    monkeypatch.setattr(Manager, "load", load)
    monkeypatch.setattr(Manager, "_create_autolock_service", lambda self: autolock)
    monkeypatch.setattr(Manager, "_create_direct_edit", lambda self: direct_edit)
    monkeypatch.setattr(
        Manager, "_create_direct_download", lambda self: direct_download
    )
    monkeypatch.setattr(Manager, "_create_workflow_worker", workflow)
    monkeypatch.setattr(
        manager_module,
        "DefaultNotificationService",
        Mock(return_value=notification_service),
    )
    monkeypatch.setattr(
        manager_module.AbstractOSIntegration, "get", Mock(return_value=osi)
    )
    monkeypatch.setattr(
        manager_module,
        "find_suitable_direct_edit_dir",
        lambda path: path,
    )
    monkeypatch.setattr(
        manager_module,
        "SyncAndQuitWorker",
        Mock(return_value=sync_and_quit_worker),
    )

    return SimpleNamespace(
        server_config_updater=server_config_updater,
        updater=application_updater,
        notification=notification_service,
        osi=osi,
        proxy=proxy,
        tracker=tracker,
        db_backup_worker=db_backup_worker,
        sync_and_quit_worker=sync_and_quit_worker,
        autolock=autolock,
        direct_edit=direct_edit,
        direct_download=direct_download,
        guess_sync=guess_sync,
        apply_server_config=apply_server_config,
        load=load,
        extension_listener=extension_listener,
        workflow=workflow,
    )


def test_constructor_initializes_non_frozen_manager(app, tmp_path, monkeypatch):
    Options.is_frozen = False
    Options.force_locale = "fr"
    dao = make_dao(
        {
            "client_version": "6.0",
            "deletion_behavior": "delete_server",
            "server_type": "NUXEO",
        }
    )
    deps = patch_constructor_dependencies(monkeypatch, dao)

    manager = Manager(tmp_path / "home")

    assert manager.home.is_dir()
    assert Manager._instances[manager.home].home == manager.home
    assert manager.old_version is None
    assert manager.proxy is deps.proxy
    assert manager.osi is deps.osi
    assert manager.tracker is deps.tracker
    assert manager.db_backup_worker is deps.db_backup_worker
    assert manager.autolock_service is deps.autolock
    assert manager.direct_edit is deps.direct_edit
    assert manager.direct_download is deps.direct_download
    assert manager.delete_users_from_tasks_cache == [str]
    assert manager.is_paused is Options.debug
    assert not manager.is_started()
    assert Options.locale == "fr"
    assert Options.deletion_behavior == "delete_server"
    deps.guess_sync.assert_called_once_with()
    deps.apply_server_config.assert_called_once_with()
    deps.load.assert_called_once_with()
    deps.notification.init_signals.assert_called_once_with()
    deps.extension_listener.assert_called_once_with()
    deps.workflow.assert_called_once_with()


def test_constructor_runs_frozen_migrations(app, tmp_path, monkeypatch):
    Options.is_frozen = True
    Options.force_locale = None
    Options.nxdrive_home = tmp_path
    dao = make_dao(
        {
            "client_version": "1.0",
            "locale": "de",
            "beta_channel": True,
            "channel": "beta",
            "original_version": None,
            "direct_edit_auto_lock": None,
            "deletion_behavior": None,
        }
    )
    patch_constructor_dependencies(monkeypatch, dao)

    manager = Manager(tmp_path / "home")

    assert Options.locale == "de"
    assert Options.channel == "beta"
    assert "beta_channel" not in dao.values
    assert dao.values["original_version"] == manager.version
    assert dao.values["client_version"] == manager.version
    assert dao.values["direct_edit_auto_lock"] is True
    assert Options.deletion_behavior == "unsync"
    assert manager.old_version == "1.0"
    assert (tmp_path / "VERSION").read_text(encoding="utf-8") == (
        f"{manager.version}\n"
    )


def test_constructor_exits_after_failed_dao_migration(app, tmp_path, monkeypatch):
    dao = make_dao(migration_success=False)
    set_feature_state = Mock()

    def create_dao(self):
        self.dao = dao

    monkeypatch.setattr(Manager, "_create_dao", create_dao)
    monkeypatch.setattr(
        Manager, "_create_server_config_updater", lambda self: MagicMock()
    )
    monkeypatch.setattr(Manager, "_create_updater", lambda self: MagicMock())
    monkeypatch.setattr(Manager, "set_feature_state", set_feature_state)

    with pytest.raises(SystemExit) as exc_info:
        Manager(tmp_path / "broken")

    assert exc_info.value.code == 0
    assert dao.values["xxx_broken_update"] == manager_module.APP_VERSION
    set_feature_state.assert_called_once_with("auto_update", False)


def test_save_or_load_proxy(manager_obj, monkeypatch):
    manual_proxy = Mock()
    monkeypatch.setattr(manager_module, "get_proxy", Mock(return_value=manual_proxy))
    save = Mock()
    load = Mock(return_value=Mock())
    monkeypatch.setattr(manager_module, "save_proxy", save)
    monkeypatch.setattr(manager_module, "load_proxy", load)
    Manager._Manager__device_id = "device"

    Options.proxy_server = "http://proxy:3128"
    assert manager_obj._save_or_load_proxy() is manual_proxy
    manager_module.get_proxy.assert_called_once_with("Manual", url="http://proxy:3128")
    save.assert_called_once_with(manual_proxy, manager_obj.dao, token="device")
    load.assert_not_called()

    MetaOptions.options["proxy_server"] = (None, "manual")
    loaded = manager_obj._save_or_load_proxy()
    assert loaded is load.return_value
    load.assert_called_once_with(manager_obj.dao)


def test_build_engine_types_uses_registry_and_skips_bad_classes(monkeypatch):
    nuxeo_engine = type("NuxeoEngine", (), {})
    alfresco_engine = type("AlfrescoEngine", (), {})
    configs = {
        "NUXEO": SimpleNamespace(
            engine_type="NXDRIVE", engine_class_path="nuxeo.module.NuxeoEngine"
        ),
        "ALFRESCO": SimpleNamespace(
            engine_type="ALFRESCO",
            engine_class_path="alfresco.module.AlfrescoEngine",
        ),
        "BROKEN": SimpleNamespace(
            engine_type="BROKEN", engine_class_path="missing.module.Engine"
        ),
        "NO_CLASS": SimpleNamespace(
            engine_type="NO_CLASS", engine_class_path="nuxeo.module.Missing"
        ),
    }

    def import_module(name):
        if name == "nuxeo.module":
            return SimpleNamespace(NuxeoEngine=nuxeo_engine)
        if name == "alfresco.module":
            return SimpleNamespace(AlfrescoEngine=alfresco_engine)
        raise ImportError(name)

    monkeypatch.setattr(st, "all_configs", lambda: configs)
    monkeypatch.setattr("importlib.import_module", import_module)

    assert Manager._build_engine_types() == {
        "NXDRIVE": nuxeo_engine,
        "ALFRESCO": alfresco_engine,
    }


def test_context_repr_close_and_runtime_cleanup(manager_obj):
    manager_obj.home = Path("/tmp/manager-home")
    Manager._instances[manager_obj.home] = manager_obj
    assert repr(manager_obj) == (f"<Manager home={manager_obj.home!r}>")
    assert manager_obj.__enter__() is manager_obj

    manager_obj.stop = Mock(side_effect=RuntimeError("Qt object deleted"))
    manager_obj.__exit__(None, None, None)

    manager_obj.stop.assert_called_once_with()
    assert manager_obj.home not in Manager._instances


def test_guess_synchronization_state_legacy_option(manager_obj):
    manager_obj.get_config = Mock(
        side_effect=lambda key: {"synchronization_enabled": "1"}.get(key)
    )
    manager_obj.set_feature_state = Mock()

    manager_obj._guess_synchronization_state()

    manager_obj.set_feature_state.assert_called_once_with("synchronization", True)
    manager_obj.dao.delete_config.assert_called_once_with("synchronization_enabled")

    manager_obj.get_config = Mock(return_value="0")
    manager_obj.set_feature_state.reset_mock()
    manager_obj.dao.delete_config.reset_mock()
    manager_obj._guess_synchronization_state()
    manager_obj.set_feature_state.assert_not_called()
    manager_obj.dao.delete_config.assert_called_once_with("synchronization_enabled")


def test_guess_synchronization_state_only_migrates_old_nuxeo(manager_obj):
    manager_obj.get_config = Mock(
        side_effect=lambda key: None if key == "synchronization_enabled" else "5.2.0"
    )
    manager_obj.set_feature_state = Mock()

    Options.server_type = "ALFRESCO"
    manager_obj._guess_synchronization_state()
    manager_obj.set_feature_state.assert_not_called()

    Options.server_type = "NUXEO"
    manager_obj._guess_synchronization_state()
    manager_obj.set_feature_state.assert_called_once_with("synchronization", True)

    manager_obj.set_feature_state.reset_mock()
    manager_obj.get_config = Mock(
        side_effect=lambda key: None if key == "synchronization_enabled" else None
    )
    manager_obj._guess_synchronization_state()
    manager_obj.set_feature_state.assert_not_called()


def test_metrics_restart_help_and_preferences(manager_obj, tmp_path, monkeypatch):
    manager_obj.tracker.uid = "tracker"
    manager_obj.get_auto_start = Mock(return_value=True)
    manager_obj.get_auto_update = Mock(return_value=True)
    manager_obj.get_update_channel = Mock(return_value="beta")
    manager_obj.open_local_file = Mock()
    monkeypatch.setattr(manager_module, "current_os", Mock(return_value="Test OS"))
    monkeypatch.setattr(manager_module, "machine", Mock(return_value="arm64"))
    Feature.auto_update = True
    Options.use_analytics = True
    Options.use_sentry = False

    metrics = manager_obj.get_metrics()

    assert metrics["auto_start"] is True
    assert metrics["auto_update"] is True
    assert metrics["tracker_id"] == "tracker"
    assert metrics["os"] == "Test OS"
    assert metrics["machine"] == "arm64"
    assert (
        metrics["python_client_version"] == st.get(st.get_default_key()).client_version
    )

    manager_obj._restart_needed()
    assert manager_obj.restart_needed is True
    manager_obj.open_help()
    manager_obj.open_local_file.assert_called_once_with(
        "https://doc.nuxeo.com/nxdoc/nuxeo-drive/"
    )

    Options.nxdrive_home = tmp_path
    manager_obj.preferences_metrics_chosen = False
    manager_obj.check_metrics_preferences()
    assert manager_obj.preferences_metrics_chosen is False

    (tmp_path / "metrics.state").write_text("sentry\nanalytics\n", encoding="utf-8")
    manager_obj.check_metrics_preferences()
    assert manager_obj.preferences_metrics_chosen is True
    assert Options.use_sentry is True
    assert Options.use_analytics is True


def test_apply_server_type_config_from_database(manager_obj, monkeypatch):
    restrict = Mock()
    refresh = Mock()
    monkeypatch.setattr(feature_module, "apply_server_type_restrictions", restrict)
    monkeypatch.setattr(constants, "refresh_branding", refresh)
    manager_obj.get_config = Mock(return_value="ALFRESCO")

    manager_obj._apply_server_type_config()

    assert Options.server_type == "ALFRESCO"
    restrict.assert_called_once_with("ALFRESCO")
    refresh.assert_called_once_with("ALFRESCO")


def test_apply_server_type_config_persists_first_launch_choice(manager_obj):
    manager_obj.get_config = Mock(return_value=None)
    manager_obj.set_config = Mock()
    Options.server_type = "NUXEO"

    manager_obj._apply_server_type_config()
    manager_obj.set_config.assert_called_once_with("server_type", "NUXEO")

    manager_obj.set_config.reset_mock()
    MetaOptions.options["server_type"] = (None, "manual")
    manager_obj._apply_server_type_config()
    manager_obj.set_config.assert_not_called()


def test_os_database_and_tracker_factories(manager_obj, tmp_path, monkeypatch):
    Options.is_frozen = True
    manager_obj._handle_os()
    manager_obj.osi.register_protocol_handlers.assert_called_once_with()
    assert manager_obj._get_db() == tmp_path / "manager.db"

    fake_dao = Mock()
    dao_factory = Mock(return_value=fake_dao)
    monkeypatch.setattr(manager_module, "ManagerDAO", dao_factory)
    manager_obj._create_dao()
    assert manager_obj.dao is fake_dao
    dao_factory.assert_called_once_with(tmp_path / "manager.db")

    tracker = MagicMock()
    monkeypatch.setattr(manager_module, "Tracker", Mock(return_value=tracker))
    created = manager_obj.create_tracker()
    assert created is tracker
    manager_obj.started.emit()
    tracker.thread.start.assert_called_once_with()
    manager_obj.directTransferStats.emit(True, 12)
    tracker.send_direct_transfer.assert_called_once_with(True, 12)


def test_worker_factories(manager_obj, tmp_path, monkeypatch):
    server_worker = MagicMock()
    monkeypatch.setattr(
        manager_module, "ServerOptionsUpdater", Mock(return_value=server_worker)
    )
    assert manager_obj._create_server_config_updater() is server_worker
    manager_module.ServerOptionsUpdater.assert_called_once_with(manager_obj)
    server_worker.firstRunCompleted.connect.assert_called_once_with(
        manager_obj.start_engines
    )

    manager_obj.server_config_updater = server_worker
    autolock = MagicMock()
    monkeypatch.setattr(
        manager_module, "ProcessAutoLockerWorker", Mock(return_value=autolock)
    )
    manager_obj.direct_edit_folder = tmp_path / "edit"
    assert manager_obj._create_autolock_service() is autolock
    manager_module.ProcessAutoLockerWorker.assert_called_once_with(
        30, manager_obj, manager_obj.direct_edit_folder
    )
    server_worker.firstRunCompleted.connect.assert_any_call(autolock.thread.start)

    db_worker = MagicMock()
    monkeypatch.setattr(
        manager_module, "DatabaseBackupWorker", Mock(return_value=db_worker)
    )
    manager_obj._create_db_backup_worker()
    assert manager_obj.db_backup_worker is db_worker
    manager_obj.started.emit()
    db_worker.thread.start.assert_called_once_with()


def test_direct_edit_factory_respects_feature_and_registry(
    manager_obj, tmp_path, monkeypatch
):
    manager_obj.direct_edit_folder = tmp_path / "edit"
    manager_obj.autolock_service = MagicMock()
    manager_obj.server_config_updater = MagicMock()
    manager_obj.tracker = MagicMock()
    loader = Mock()
    monkeypatch.setattr(st, "load_class", loader)
    monkeypatch.setattr(st, "first_class_path", Mock(return_value="worker.Path"))

    Feature.direct_edit = False
    assert manager_obj._create_direct_edit() is None
    loader.assert_not_called()

    Feature.direct_edit = True
    loader.return_value = None
    assert manager_obj._create_direct_edit() is None

    worker = MagicMock()
    worker_class = Mock(return_value=worker)
    loader.return_value = worker_class
    assert manager_obj._create_direct_edit() is worker
    worker_class.assert_called_once_with(manager_obj, manager_obj.direct_edit_folder)
    assert manager_obj.autolock_service.direct_edit is worker
    manager_obj.server_config_updater.firstRunCompleted.connect.assert_called_with(
        worker.thread.start
    )
    worker.openDocument.connect.assert_called_once_with(
        manager_obj.tracker.send_directedit_open
    )
    worker.editDocument.connect.assert_called_once_with(
        manager_obj.tracker.send_directedit_edit
    )


def test_direct_download_factory_handles_missing_and_present_worker(
    manager_obj, tmp_path, monkeypatch
):
    manager_obj.direct_download_folder = tmp_path / "download"
    manager_obj.server_config_updater = MagicMock()
    loader = Mock(return_value=None)
    monkeypatch.setattr(st, "load_class", loader)
    monkeypatch.setattr(st, "first_class_path", Mock(return_value=""))

    assert manager_obj._create_direct_download() is None

    worker = MagicMock()
    worker_class = Mock(return_value=worker)
    loader.return_value = worker_class
    assert manager_obj._create_direct_download() is worker
    assert manager_obj.direct_download_folder.is_dir()
    worker_class.assert_called_once_with(
        manager_obj, manager_obj.direct_download_folder
    )
    manager_obj.server_config_updater.firstRunCompleted.connect.assert_called_once_with(
        worker.thread.start
    )


def test_updater_factory_connects_expected_start_policy(manager_obj, monkeypatch):
    worker = MagicMock()
    manager_obj.server_config_updater = MagicMock()
    monkeypatch.setattr(manager_module, "updater", Mock(return_value=worker))
    monkeypatch.delenv("FORCE_USE_LATEST_VERSION", raising=False)

    assert manager_obj._create_updater() is worker
    assert manager_obj.prompted_wrong_channel is False
    manager_obj.server_config_updater.firstRunCompleted.connect.assert_any_call(
        worker.thread.start
    )
    manager_obj.server_config_updater.firstRunCompleted.connect.assert_any_call(
        worker.refresh_status
    )

    forced_worker = MagicMock()
    manager_module.updater.return_value = forced_worker
    manager_obj.server_config_updater.reset_mock()
    monkeypatch.setenv("FORCE_USE_LATEST_VERSION", "1")
    assert manager_obj._create_updater() is forced_worker
    manager_obj.started.emit()
    forced_worker.thread.start.assert_called_once_with()
    manager_obj.server_config_updater.firstRunCompleted.connect.assert_called_once_with(
        forced_worker.refresh_status
    )


def test_workflow_and_extension_listener_factories(manager_obj, monkeypatch):
    Feature.tasks_management = False
    manager_obj._create_workflow_worker()
    assert not hasattr(manager_obj, "workflow_worker")

    Feature.tasks_management = True
    worker = MagicMock()
    worker.thread.isRunning.return_value = False
    monkeypatch.setattr(manager_module, "WorkflowWorker", Mock(return_value=worker))
    manager_obj._create_workflow_worker()
    assert manager_obj.workflow_worker is worker
    assert manager_obj.workflow_thread is worker.thread
    worker.start.assert_called_once_with()
    manager_obj.stop_workflow_worker()
    worker.quit.assert_called_once_with()

    Options.is_frozen = True
    manager_obj.osi.get_extension_listener.return_value = None
    manager_obj._create_extension_listener()
    assert manager_obj._extension_listener is None

    listener = MagicMock()
    manager_obj.osi.get_extension_listener.return_value = listener
    manager_obj._create_extension_listener()
    listener.listening.connect.assert_called_once_with(manager_obj.osi.init)


def test_suspend_and_resume_lifecycle(manager_obj):
    first = Mock()
    second = Mock()
    manager_obj.engines = {"first": first, "second": second}
    resumed = []
    suspended = []
    manager_obj.resumed.connect(lambda: resumed.append(True))
    manager_obj.suspended.connect(lambda: suspended.append(True))

    manager_obj.resume()
    assert resumed == []
    first.resume.assert_not_called()

    manager_obj.suspend()
    assert manager_obj.is_paused is True
    first.suspend.assert_called_once_with()
    second.suspend.assert_called_once_with()
    assert suspended == [True]

    manager_obj.suspend()
    assert suspended == [True]

    manager_obj.resume()
    assert manager_obj.is_paused is False
    first.resume.assert_called_once_with()
    second.resume.assert_called_once_with()
    assert resumed == [True]


def test_stop_cleans_started_engines_downloads_and_os(manager_obj):
    started = Mock()
    started.is_started.return_value = True
    stopped = Mock()
    stopped.is_started.return_value = False
    manager_obj.engines = {"started": started, "stopped": stopped}
    manager_obj.direct_download = Mock()
    seen = []
    manager_obj.stopped.connect(lambda: seen.append(True))

    manager_obj.stop()

    manager_obj.dao.save_backup.assert_called_once_with()
    started.stop.assert_called_once_with()
    stopped.stop.assert_not_called()
    manager_obj.direct_download.stop.assert_called_once_with()
    manager_obj.direct_download.cleanup.assert_called_once_with()
    manager_obj.osi.cleanup.assert_called_once_with()
    manager_obj.dao.dispose.assert_called_once_with()
    assert seen == [True]


def test_start_engines_isolates_failures_and_resumes_transfers(manager_obj):
    good = Mock()
    missing_xattr = Mock()
    missing_xattr.start.side_effect = MissingXattrSupport(Path("/sync"))
    broken = Mock()
    broken.start.side_effect = RuntimeError("broken")
    manager_obj.engines = {
        "good": good,
        "missing": missing_xattr,
        "broken": broken,
    }
    manager_obj.direct_download = Mock()
    manager_obj._init_direct_transfer_resumption = Mock()
    Feature.direct_transfer = True

    manager_obj.start_engines()

    good.start.assert_called_once_with()
    missing_xattr.start.assert_called_once_with()
    broken.start.assert_called_once_with()
    manager_obj.direct_download.resume_persisted_downloads.assert_called_once_with()
    manager_obj._init_direct_transfer_resumption.assert_called_once_with()

    for engine in manager_obj.engines.values():
        engine.start.reset_mock()
    manager_obj.is_paused = True
    Feature.direct_transfer = False
    manager_obj._init_direct_transfer_resumption.reset_mock()
    manager_obj.start_engines()
    for engine in manager_obj.engines.values():
        engine.start.assert_not_called()
    manager_obj._init_direct_transfer_resumption.assert_not_called()


def test_start_sets_state_and_handles_server_config_policy(manager_obj):
    manager_obj._handle_os = Mock()
    manager_obj.start_engines = Mock()
    started = []
    manager_obj.started.connect(lambda: started.append(True))

    manager_obj.server_config_updater.first_run = True
    manager_obj.start()
    manager_obj.start_engines.assert_not_called()
    assert manager_obj.is_started() is True

    manager_obj.server_config_updater.first_run = False
    manager_obj.start()
    manager_obj.start_engines.assert_called_once_with()
    assert manager_obj._handle_os.call_count == 2
    assert started == [True, True]


def test_direct_transfer_resumption_handles_past_future_and_invalid_sessions(
    manager_obj,
):
    sessions = [
        {"uid": "missing", "scheduled_at": None},
        {"uid": "zero", "scheduled_at": 0},
        {"uid": "zero-string", "scheduled_at": "0"},
        {"uid": "past", "scheduled_at": "2000-01-01T00:00:00+00:00"},
        {"uid": "naive", "scheduled_at": "2000-01-02T00:00:00"},
        {"uid": "future", "scheduled_at": "2999-01-01T00:00:00+00:00"},
        {"uid": "invalid", "scheduled_at": "not-a-date"},
    ]
    engine = MagicMock()
    engine.dao.get_active_sessions_raw.return_value = sessions
    manager_obj.engines = {"engine": engine}

    manager_obj._init_direct_transfer_resumption()

    assert engine.resume_scheduled_session.call_args_list == [
        call("past"),
        call("naive"),
    ]
    uid, delay = engine.startTimerSignal.emit.call_args.args
    assert uid == "future"
    assert delay > 0


def test_load_selects_registered_nuxeo_and_alfresco_factories(manager_obj, tmp_path):
    unknown = SimpleNamespace(
        uid="unknown", engine="REMOVED", local_folder=tmp_path / "unknown"
    )
    missing = SimpleNamespace(
        uid="missing", engine="NXDRIVE", local_folder=tmp_path / "missing"
    )
    nuxeo_def = SimpleNamespace(
        uid="nuxeo", engine="NXDRIVE", local_folder=tmp_path / "nuxeo"
    )
    alfresco_def = SimpleNamespace(
        uid="alfresco", engine="ALFRESCO", local_folder=tmp_path / "alfresco"
    )
    broken_def = SimpleNamespace(
        uid="broken", engine="NXDRIVE", local_folder=tmp_path / "broken"
    )
    definitions = [unknown, missing, nuxeo_def, alfresco_def, broken_def]
    manager_obj.dao.get_engines.return_value = definitions

    for definition in (nuxeo_def, alfresco_def, broken_def):
        manager_obj._get_engine_db_file(
            definition.uid, engine_type=definition.engine
        ).touch()

    nuxeo_engine = MagicMock()
    alfresco_engine = MagicMock()

    def make_nuxeo(manager, definition):
        if definition.uid == "broken":
            raise EngineInitError(definition)
        return nuxeo_engine

    nuxeo_factory = Mock(side_effect=make_nuxeo)
    alfresco_factory = Mock(return_value=alfresco_engine)
    manager_obj._engine_types = {
        "NXDRIVE": nuxeo_factory,
        "ALFRESCO": alfresco_factory,
    }
    initialized = []
    manager_obj.initEngine.connect(initialized.append)

    manager_obj.load()

    assert manager_obj.engines == {
        "nuxeo": nuxeo_engine,
        "alfresco": alfresco_engine,
    }
    assert manager_obj._engine_definitions == [nuxeo_def, alfresco_def]
    nuxeo_factory.assert_has_calls(
        [call(manager_obj, nuxeo_def), call(manager_obj, broken_def)]
    )
    alfresco_factory.assert_called_once_with(manager_obj, alfresco_def)
    nuxeo_engine.online.connect.assert_called_once_with(manager_obj._force_autoupdate)
    alfresco_engine.online.connect.assert_called_once_with(
        manager_obj._force_autoupdate
    )
    assert initialized == [nuxeo_engine, alfresco_engine]
    manager_obj.tracker.send_metric.assert_called_once_with("account", "count", "2")


def test_reload_headers_database_paths_and_force_update(manager_obj, tmp_path):
    reloadable = SimpleNamespace(remote=Mock())
    reloadable.remote.reload_global_headers = Mock()
    manager_obj.engines = {
        "none": SimpleNamespace(remote=None),
        "plain": SimpleNamespace(remote=SimpleNamespace()),
        "reloadable": reloadable,
    }
    manager_obj.reload_client_global_headers()
    reloadable.remote.reload_global_headers.assert_called_once_with()

    assert manager_obj._get_engine_db_file("one", engine_type="NXDRIVE") == (
        tmp_path / "ndrive_one.db"
    )
    assert manager_obj._get_engine_db_file("two", engine_type="ALFRESCO") == (
        tmp_path / "adrive_two.db"
    )

    manager_obj.updater.get_next_poll.return_value = 61
    manager_obj.updater.get_last_poll.return_value = 1801
    manager_obj._force_autoupdate()
    manager_obj.updater.force_poll.assert_called_once_with()

    manager_obj.updater.force_poll.reset_mock()
    manager_obj.updater.get_next_poll.return_value = 60
    manager_obj._force_autoupdate()
    manager_obj.updater.force_poll.assert_not_called()


def test_open_local_file_success_and_errors(manager_obj, monkeypatch):
    manager_obj.open_local_file("document.txt", select=True)
    manager_obj.osi.open_local_file.assert_called_once_with("document.txt", select=True)

    no_space = OSError(next(iter(manager_module.NO_SPACE_ERRORS)), "full")
    manager_obj.osi.open_local_file.side_effect = no_space
    with pytest.raises(OSError) as exc_info:
        manager_obj.open_local_file("full.txt")
    assert exc_info.value is no_space

    no_application = OSError(1155, "missing association")
    no_application.winerror = 1155
    monkeypatch.setattr(manager_module, "WINDOWS", True)
    manager_obj.osi.open_local_file.side_effect = no_application
    with pytest.raises(NoAssociatedSoftware):
        manager_obj.open_local_file("unknown.extension")

    monkeypatch.setattr(manager_module, "WINDOWS", False)
    manager_obj.osi.open_local_file.side_effect = OSError(2, "missing")
    manager_obj.open_local_file("missing.txt")

    manager_obj.osi.open_local_file.side_effect = RuntimeError("launcher failed")
    manager_obj.open_local_file("broken.txt")


def test_device_id_and_config_accessors(manager_obj, monkeypatch):
    Manager._Manager__device_id = None
    manager_obj.dao.values["device_id"] = "stored-device"
    assert manager_obj.device_id == "stored-device"
    assert manager_obj.device_id == "stored-device"
    manager_obj.dao.get_config.assert_called_once_with("device_id")

    manager_obj._Manager__device_id = None
    manager_obj.dao.values.pop("device_id")
    generated = SimpleNamespace(hex="generated-device")
    monkeypatch.setattr(manager_module.uuid, "uuid1", Mock(return_value=generated))
    assert manager_obj.device_id == "generated-device"
    assert manager_obj.dao.values["device_id"] == "generated-device"

    manager_obj.dao.values["setting"] = "value"
    assert manager_obj.get_config("setting", default="fallback") == "value"

    manager_obj.dao.update_config.reset_mock()
    manager_obj.set_config("locale", "es")
    assert Options.locale == "es"
    manager_obj.dao.update_config.assert_called_once_with("locale", "es")
    manager_obj.set_config("locale", "es")
    manager_obj.dao.update_config.assert_called_once_with("locale", "es")


def test_boolean_feature_and_update_settings(manager_obj, monkeypatch):
    manager_obj.dao.values["direct_edit_auto_lock"] = False
    assert manager_obj.get_direct_edit_auto_lock() is False
    manager_obj.set_direct_edit_auto_lock(True)
    assert manager_obj.dao.values["direct_edit_auto_lock"] is True

    Feature.direct_edit = True
    assert manager_obj.get_feature_state("direct_edit") is True
    save_config = Mock()
    monkeypatch.setattr(manager_module, "save_config", save_config)
    updates = []
    manager_obj.featureUpdate.connect(lambda name, value: updates.append((name, value)))
    manager_obj.set_feature_state("direct_edit", False, setter="manual")
    assert Feature.direct_edit is False
    assert save_config.call_args.args[0]["feature_direct_edit"] is False
    assert updates == [("direct_edit", False)]

    Options.update_check_delay = 3600
    Options.is_frozen = True
    manager_obj.dao.values["auto_update"] = True
    assert manager_obj.get_auto_update() is True
    Options.update_check_delay = 0
    assert manager_obj.get_auto_update() is False
    manager_obj.set_auto_update(False)
    assert manager_obj.dao.values["auto_update"] is False


def test_generate_report_and_csv_dispatch(manager_obj, tmp_path, monkeypatch):
    engine = MagicMock()
    manager_obj.engines = {"engine": engine}
    manager_obj.get_metrics = Mock(return_value={"manager": True})
    report_path = tmp_path / "report.zip"
    report = MagicMock()
    report.get_path.return_value = report_path
    report_factory = Mock(return_value=report)
    import nxdrive.drive.report as report_module

    monkeypatch.setattr(report_module, "Report", report_factory)
    assert manager_obj.generate_report(path=report_path) == report_path
    engine.get_metrics.assert_called_once_with()
    report_factory.assert_called_once_with(manager_obj, report_path=report_path)
    report.generate.assert_called_once_with()

    session = SimpleNamespace(uid=7)
    engine.dao.get_session.return_value = None
    assert manager_obj.generate_csv(7, engine) is False

    engine.dao.get_session.return_value = session
    runner = Mock()
    runner_factory = Mock(return_value=runner)
    monkeypatch.setattr(manager_module, "Runner", runner_factory)
    engine._threadpool = MagicMock()
    assert manager_obj.generate_csv(7, engine) is True
    runner_factory.assert_called_once_with(
        manager_obj._generate_csv_async, engine, session
    )
    engine._threadpool.start.assert_called_once_with(runner)

    engine._threadpool = None
    assert manager_obj.generate_csv(7, engine) is False


def test_generate_csv_async_success_and_failure(manager_obj, tmp_path, monkeypatch):
    created = []

    class FakeSessionCsv:
        fail = False

        def __init__(self, manager, session):
            self.output_file = tmp_path / f"{session.uid}.csv"
            self.output_tmp = tmp_path / f"{session.uid}.tmp"
            created.append(self)

        def create_tmp(self):
            self.output_tmp.write_text("temporary", encoding="utf-8")

        def store_data(self, items):
            if self.fail:
                raise RuntimeError("CSV failure")
            self.output_file.write_text(str(items), encoding="utf-8")

    import nxdrive.drive.session_csv as csv_module

    monkeypatch.setattr(csv_module, "SessionCsv", FakeSessionCsv)
    engine = MagicMock()
    engine.dao.get_session_items.return_value = ["item"]
    session = SimpleNamespace(uid=1)

    manager_obj._generate_csv_async(engine, session)
    assert created[-1].output_file.read_text(encoding="utf-8") == "['item']"
    assert engine.dao.sessionUpdated.emit.call_args_list == [call(False), call(True)]

    engine.dao.sessionUpdated.emit.reset_mock()
    FakeSessionCsv.fail = True
    failed_session = SimpleNamespace(uid=2)
    manager_obj._generate_csv_async(engine, failed_session)
    assert not created[-1].output_tmp.exists()
    assert engine.dao.sessionUpdated.emit.call_args_list == [call(False), call(True)]


def test_auto_start_icons_sentry_channels_and_log_levels(manager_obj):
    manager_obj.osi.startup_enabled.return_value = True
    assert manager_obj.get_auto_start() is True
    manager_obj.osi.startup_enabled.side_effect = OSError("unavailable")
    assert manager_obj.get_auto_start() is False
    manager_obj.osi.startup_enabled.side_effect = None

    manager_obj.set_auto_start(True)
    manager_obj.osi.register_startup.assert_called_once_with()
    manager_obj.set_auto_start(False)
    manager_obj.osi.unregister_startup.assert_called_once_with()
    manager_obj.osi.register_startup.side_effect = OSError("denied")
    manager_obj.set_auto_start(True)

    manager_obj.dao.values["light_icons"] = True
    assert manager_obj.use_light_icons() is True
    manager_obj.set_config = Mock()
    icon_updates = []
    manager_obj.reloadIconsSet.connect(icon_updates.append)
    manager_obj.set_light_icons(False)
    manager_obj.set_config.assert_called_once_with("light_icons", False)
    assert icon_updates == [False]

    manager_obj.dao.values["use_sentry"] = False
    assert manager_obj.use_sentry() is False
    manager_obj.set_sentry(True)
    manager_obj.set_config.assert_called_with("use_sentry", True)

    manager_obj.dao.values["channel"] = "beta"
    assert manager_obj.get_update_channel() == "beta"
    manager_obj.prompted_wrong_channel = True
    manager_obj.set_update_channel("stable")
    manager_obj.set_config.assert_called_with("channel", "stable")
    assert manager_obj.prompted_wrong_channel is False
    manager_obj.updater.refresh_status.assert_called_once_with()

    Options.is_frozen = False
    assert manager_obj.get_log_level() == DEFAULT_LOG_LEVEL_FILE
    Options.is_frozen = True
    Options.is_alpha = True
    assert manager_obj.get_log_level() == DEFAULT_LOG_LEVEL_FILE
    Options.is_alpha = False
    manager_obj.dao.values["log_level_file"] = "DEBUG"
    assert manager_obj.get_log_level() == "DEBUG"
    manager_obj.set_log_level("WARNING")
    manager_obj.set_config.assert_called_with("log_level_file", "WARNING")


def test_proxy_and_deletion_settings(manager_obj, monkeypatch):
    first = SimpleNamespace(server_url="https://first", remote=Mock())
    second = SimpleNamespace(server_url="https://second", remote=Mock())
    manager_obj.engines = {"first": first, "second": second}
    new_proxy = Mock()
    validate = Mock(side_effect=[True, False])
    save = Mock()
    monkeypatch.setattr(manager_module, "validate_proxy", validate)
    monkeypatch.setattr(manager_module, "save_proxy", save)

    assert manager_obj.set_proxy(new_proxy) == "PROXY_INVALID"
    first.remote.set_proxy.assert_called_once_with(new_proxy)
    second.remote.set_proxy.assert_not_called()
    save.assert_not_called()

    validate.side_effect = None
    validate.return_value = True
    first.remote.set_proxy.reset_mock()
    assert manager_obj.set_proxy(new_proxy) == ""
    first.remote.set_proxy.assert_called_once_with(new_proxy)
    second.remote.set_proxy.assert_called_once_with(new_proxy)
    save.assert_called_once_with(new_proxy, manager_obj.dao)
    assert manager_obj.proxy is new_proxy

    Options.deletion_behavior = "delete_server"
    assert manager_obj.get_deletion_behavior() is DelAction.DEL_SERVER
    manager_obj.set_config = Mock()
    manager_obj.set_deletion_behavior(DelAction.UNSYNC)
    manager_obj.set_config.assert_called_once_with("deletion_behavior", "unsync")


def test_login_type_without_browser_page_never_contacts_server(
    manager_obj, monkeypatch
):
    monkeypatch.setattr(
        st,
        "detect_by_url",
        Mock(return_value=SimpleNamespace(browser_startup_page="")),
    )
    request = Mock()
    monkeypatch.setattr(manager_module.requests, "get", request)
    assert manager_obj.get_server_login_type("https://alfresco.example") is Login.OLD
    request.assert_not_called()


@pytest.mark.parametrize(
    "status, modern, expected",
    [
        (200, False, Login.NEW),
        (401, False, Login.NEW),
        (404, True, Login.NEW),
        (404, False, Login.OLD),
        (500, False, Login.UNKNOWN),
    ],
)
def test_login_type_status_handling(manager_obj, monkeypatch, status, modern, expected):
    monkeypatch.setattr(
        st,
        "detect_by_url",
        Mock(
            return_value=SimpleNamespace(browser_startup_page="drive_browser_login.jsp")
        ),
    )
    request = Mock(return_value=StubResponse(status))
    monkeypatch.setattr(manager_module.requests, "get", request)
    manager_obj._is_modern_server = Mock(return_value=modern)
    manager_obj.proxy.settings.return_value = {"https": "proxy"}
    Manager._Manager__device_id = "device"

    result = manager_obj.get_server_login_type(
        "https://server.example/nuxeo/?answer=42#fragment"
    )

    assert result is expected
    requested_url = request.call_args.args[0]
    assert requested_url == (
        "https://server.example/nuxeo/drive_browser_login.jsp?answer=42#fragment"
    )
    assert request.call_args.kwargs["timeout"] == (
        manager_module.STARTUP_PAGE_CONNECTION_TIMEOUT
    )
    if status == 404:
        manager_obj._is_modern_server.assert_called_once()
    else:
        manager_obj._is_modern_server.assert_not_called()


def test_login_type_connection_error_policy(manager_obj, monkeypatch):
    monkeypatch.setattr(
        st,
        "detect_by_url",
        Mock(return_value=SimpleNamespace(browser_startup_page="login.jsp")),
    )
    monkeypatch.setattr(
        manager_module.requests, "get", Mock(side_effect=OSError("offline"))
    )

    with pytest.raises(StartupPageConnectionError):
        manager_obj.get_server_login_type("https://server/nuxeo")
    assert (
        manager_obj.get_server_login_type("https://server/nuxeo", _raise=False)
        is Login.UNKNOWN
    )


@pytest.mark.parametrize("status, expected", [(200, True), (403, True), (500, False)])
def test_modern_server_probe(manager_obj, monkeypatch, status, expected):
    request = Mock(return_value=StubResponse(status))
    monkeypatch.setattr(manager_module.requests, "get", request)
    parts = urlsplit("https://server/nuxeo?x=1#fragment")

    assert manager_obj._is_modern_server(parts, {"Header": "value"}) is expected
    assert request.call_args.args[0] == ("https://server/nuxeo/api/v1/me?x=1#fragment")

    request.side_effect = OSError("offline")
    assert manager_obj._is_modern_server(parts, {}) is False


def test_bind_server_detects_type_and_builds_binder(manager_obj, tmp_path):
    manager_obj._detect_server_type = Mock(return_value="ALFRESCO")
    manager_obj.bind_engine = Mock(return_value="engine")

    result = manager_obj.bind_server(
        tmp_path / "sync",
        "https://server/alfresco",
        "user",
        password="secret",
        token="token",
        check_credentials=False,
        start_engine=False,
    )

    assert result == "engine"
    engine_type, local_folder, name, binder = manager_obj.bind_engine.call_args.args
    assert engine_type == "ALFRESCO"
    assert local_folder == tmp_path / "sync"
    assert name == "server"
    assert binder == Binder(
        username="user",
        password="secret",
        token="token",
        no_check=True,
        no_fscheck=False,
        url="https://server/alfresco",
    )
    assert manager_obj.bind_engine.call_args.kwargs == {"starts": False}


def test_server_detection_name_and_local_folder_availability(
    manager_obj, tmp_path, monkeypatch
):
    config = SimpleNamespace(engine_type="ALFRESCO")
    monkeypatch.setattr(st, "detect_by_url", Mock(return_value=config))
    assert Manager._detect_server_type("https://server/alfresco") == "ALFRESCO"
    assert manager_obj._get_engine_name("https://example.test:8443/nuxeo") == (
        "example.test"
    )

    manager_obj._engine_definitions = []
    assert manager_obj.check_local_folder_available(tmp_path / "anywhere") is True
    root = tmp_path / "sync"
    manager_obj._engine_definitions = [SimpleNamespace(local_folder=root)]
    assert manager_obj.check_local_folder_available(root) is False
    assert manager_obj.check_local_folder_available(root / "child") is False
    assert manager_obj.check_local_folder_available(tmp_path) is False
    assert manager_obj.check_local_folder_available(tmp_path / "other") is True


def test_update_engine_path_updates_watchers_and_storage(manager_obj, tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    engine = SimpleNamespace(local_folder=old)
    manager_obj.engines = {"uid": engine}

    manager_obj.update_engine_path("uid", new)

    manager_obj.osi.unwatch_folder.assert_called_once_with(old)
    assert engine.local_folder == new
    manager_obj.osi.watch_folder.assert_called_once_with(new)
    manager_obj.dao.update_engine_path.assert_called_once_with("uid", new)

    manager_obj.osi.reset_mock()
    manager_obj.update_engine_path("missing", tmp_path / "other")
    manager_obj.osi.unwatch_folder.assert_not_called()
    manager_obj.osi.watch_folder.assert_called_once_with(tmp_path / "other")


def test_bind_engine_selects_fragment_type_and_updates_lifecycle(
    manager_obj, tmp_path, monkeypatch
):
    local_folder = tmp_path / "sync"
    definition = SimpleNamespace(
        uid="uid", engine="ALFRESCO", local_folder=local_folder, name="server"
    )
    manager_obj.dao.add_engine.return_value = definition
    engine = MagicMock()
    factory = Mock(return_value=engine)
    manager_obj._engine_types = {"ALFRESCO": factory}
    manager_obj.engines = {"existing": Mock()}
    manager_obj.updater = Mock()
    manager_obj.db_backup_worker = Mock()
    manager_obj.is_paused = True
    monkeypatch.setattr(
        manager_module.uuid, "uuid1", Mock(return_value=SimpleNamespace(hex="uid"))
    )
    emitted = []
    manager_obj.newEngine.connect(emitted.append)
    binder = Binder(
        username="user",
        password="password",
        token=None,
        url="https://server/nuxeo#ALFRESCO",
        no_check=False,
        no_fscheck=False,
    )

    result = manager_obj.bind_engine("NXDRIVE", local_folder, None, binder, starts=True)

    assert result is engine
    manager_obj.dao.add_engine.assert_called_once_with(
        "ALFRESCO", local_folder, "uid", "server"
    )
    factory.assert_called_once_with(
        manager_obj,
        definition,
        binder=binder._replace(url="https://server/nuxeo"),
    )
    assert manager_obj.engines["uid"] is engine
    assert manager_obj._engine_definitions == [definition]
    manager_obj.updater.refresh_status.assert_called_once_with()
    engine.start.assert_called_once_with()
    manager_obj.osi.watch_folder.assert_called_once_with(local_folder)
    assert emitted == [engine]
    assert manager_obj.is_paused is False
    manager_obj.db_backup_worker.force_poll.assert_called_once_with()


def test_bind_engine_uses_default_folder_and_can_skip_start(
    manager_obj, tmp_path, monkeypatch
):
    default_folder = tmp_path / "default"
    definition = SimpleNamespace(uid="uid", engine="NXDRIVE")
    manager_obj.dao.add_engine.return_value = definition
    engine = MagicMock()
    manager_obj._engine_types = {"NXDRIVE": Mock(return_value=engine)}
    manager_obj.load = Mock()
    manager_obj.updater = Mock()
    monkeypatch.setattr(
        manager_module, "get_default_local_folder", lambda: default_folder
    )
    monkeypatch.setattr(
        manager_module.uuid, "uuid1", Mock(return_value=SimpleNamespace(hex="uid"))
    )
    binder = Binder("user", "password", None, "https://server/nuxeo", False, False)

    assert (
        manager_obj.bind_engine("NXDRIVE", None, "name", binder, starts=False) is engine
    )
    manager_obj.load.assert_called_once_with()
    engine.start.assert_not_called()
    manager_obj.osi.watch_folder.assert_called_once_with(default_folder)


def test_bind_engine_validates_type_folder_and_unique_storage(manager_obj, tmp_path):
    binder = Binder("user", "password", None, "https://server/nuxeo", False, False)
    manager_obj._engine_types = {"NXDRIVE": Mock()}
    manager_obj.engines = {"existing": Mock()}

    with pytest.raises(EngineTypeMissing):
        manager_obj.bind_engine("REMOVED", tmp_path / "sync", "name", binder)

    with pytest.raises(FolderAlreadyUsed):
        manager_obj.bind_engine("NXDRIVE", manager_obj.home, "name", binder)

    manager_obj.check_local_folder_available = Mock(return_value=False)
    with pytest.raises(FolderAlreadyUsed):
        manager_obj.bind_engine("NXDRIVE", tmp_path / "nested", "name", binder)

    manager_obj.check_local_folder_available.return_value = True
    manager_obj.dao.add_engine.side_effect = sqlite3.IntegrityError("duplicate")
    with pytest.raises(FolderAlreadyUsed):
        manager_obj.bind_engine("NXDRIVE", tmp_path / "duplicate", "name", binder)


def test_bind_engine_failure_rolls_back_definition_and_databases(
    manager_obj, tmp_path, monkeypatch
):
    definition = SimpleNamespace(uid="uid", engine="NXDRIVE")
    manager_obj.dao.add_engine.return_value = definition
    manager_obj._engine_types = {"NXDRIVE": Mock(side_effect=ValueError("bad bind"))}
    manager_obj.engines = {"existing": Mock()}
    manager_obj.remove_engine_dbs = Mock()
    monkeypatch.setattr(
        manager_module.uuid, "uuid1", Mock(return_value=SimpleNamespace(hex="uid"))
    )
    binder = Binder("user", "password", None, "https://server/nuxeo", False, False)

    with pytest.raises(ValueError, match="bad bind"):
        manager_obj.bind_engine("NXDRIVE", tmp_path / "sync", "name", binder)

    assert "uid" not in manager_obj.engines
    manager_obj.dao.delete_engine.assert_called_once_with("uid")
    manager_obj.remove_engine_dbs.assert_called_once_with("uid", "NXDRIVE")

    manager_obj.dao.reset_mock()
    manager_obj._engine_types["NXDRIVE"].side_effect = AddonForbiddenError()
    with pytest.raises(AddonForbiddenError):
        manager_obj.bind_engine("NXDRIVE", tmp_path / "other", "name", binder)


def test_unbind_engine_updates_state_and_can_purge(manager_obj, tmp_path):
    local_folder = tmp_path / "sync"
    local_folder.mkdir()
    (local_folder / "document.txt").write_text("data", encoding="utf-8")
    engine = MagicMock()
    engine.remote.user_id = "user-id"
    engine.local_folder = local_folder
    manager_obj.engines = {"uid": engine}
    remaining = [SimpleNamespace(uid="other")]
    manager_obj.dao.get_engines.return_value = remaining
    manager_obj.db_backup_worker = Mock()
    dropped = []
    manager_obj.dropEngine.connect(dropped.append)

    manager_obj.unbind_engine("uid", purge=True)

    assert manager_obj.delete_users_from_tasks_cache[-1] == "user-id"
    engine.unbind.assert_called_once_with()
    manager_obj.dao.delete_engine.assert_called_once_with("uid")
    engine.local.unset_readonly.assert_called_once_with(local_folder)
    assert not local_folder.exists()
    assert dropped == ["uid"]
    assert manager_obj._engine_definitions == remaining
    manager_obj.db_backup_worker.force_poll.assert_called_once_with()


def test_unbind_engine_missing_and_purge_errors(manager_obj, tmp_path, monkeypatch):
    manager_obj.load = Mock()
    manager_obj.unbind_engine("missing")
    manager_obj.load.assert_called_once_with()

    engine = MagicMock()
    engine.remote = None
    engine.local_folder = tmp_path / "already-missing"
    manager_obj.engines = {"uid": engine}
    manager_obj.unbind_engine("uid", purge=True)
    assert manager_obj.delete_users_from_tasks_cache == [str]

    engine = MagicMock()
    engine.remote = None
    engine.local_folder = tmp_path / "cannot-remove"
    manager_obj.engines = {"uid": engine}
    monkeypatch.setattr(
        manager_module.shutil, "rmtree", Mock(side_effect=OSError("busy"))
    )
    manager_obj.unbind_engine("uid", purge=True)
    manager_module.shutil.rmtree.assert_called_once_with(engine.local_folder)


def test_engine_database_helpers_and_state(manager_obj, tmp_path):
    manager_obj._engine_definitions = [
        SimpleNamespace(uid="alfresco", engine="ALFRESCO")
    ]
    assert manager_obj.get_engine_db("alfresco") == tmp_path / "adrive_alfresco.db"
    assert manager_obj.get_engine_db("nuxeo", "NXDRIVE") == tmp_path / "ndrive_nuxeo.db"

    main = manager_obj.get_engine_db("nuxeo", "NXDRIVE")
    files = [main, main.with_suffix(".db-shm"), main.with_suffix(".db-wal")]
    for file in files:
        file.write_text("db", encoding="utf-8")
    manager_obj.remove_engine_dbs("nuxeo", "NXDRIVE")
    assert not any(file.exists() for file in files)

    manager_obj.dispose_db()
    manager_obj.dao.dispose.assert_called_once_with()
    manager_obj.dao = None
    manager_obj.dispose_db()

    manager_obj._started = True
    assert manager_obj.is_started() is True
    manager_obj.engines = {
        "idle": SimpleNamespace(is_syncing=Mock(return_value=False)),
        "active": SimpleNamespace(is_syncing=Mock(return_value=True)),
    }
    assert manager_obj.is_syncing() is True
    manager_obj.engines["active"].is_syncing.return_value = False
    assert manager_obj.is_syncing() is False


def test_root_and_metadata_engine_lookup(manager_obj, tmp_path, monkeypatch):
    root = tmp_path / "sync"
    child = root / "folder" / "document.txt"

    def root_id(path, *, name=""):
        if name == "ndriveroot" and path == root:
            return "provider|repo|root|engine-id"
        return None

    monkeypatch.setattr(
        manager_module.LocalClient, "get_path_remote_id", Mock(side_effect=root_id)
    )
    assert manager_obj.get_root_id(child) == "provider|repo|root|engine-id"
    assert manager_obj.get_root_id(Path("/")) == ""

    engine = Mock()
    manager_obj.engines = {"engine-id": engine}

    def metadata_id(path, *, name=""):
        if name == "ndriveroot":
            return "provider|repo|root|engine-id"
        return "remote-ref"

    manager_module.LocalClient.get_path_remote_id.side_effect = metadata_id
    engine.get_metadata_url.return_value = "https://server/document"
    assert manager_obj.get_metadata_infos(child, edit=True) == (
        "https://server/document"
    )
    engine.get_metadata_url.assert_called_once_with("remote-ref", edit=True)

    manager_module.LocalClient.get_path_remote_id.side_effect = (
        lambda path, **kwargs: None
    )
    with pytest.raises(ValueError, match="Could not find file"):
        manager_obj.get_metadata_infos(child)

    manager_module.LocalClient.get_path_remote_id.side_effect = metadata_id
    manager_obj.engines = {}
    with pytest.raises(ValueError, match="Unknown engine"):
        manager_obj.get_metadata_infos(child)


def test_contextual_menu_methods_handle_success_and_unknown_paths(
    manager_obj, tmp_path
):
    path = tmp_path / "document.txt"
    manager_obj.get_metadata_infos = Mock(return_value="https://server/document")
    manager_obj.open_local_file = Mock()

    manager_obj.ctx_access_online(path)
    manager_obj.open_local_file.assert_called_once_with("https://server/document")

    manager_obj.ctx_copy_share_link(path)
    manager_obj.osi.cb_set.assert_called_once_with("https://server/document")
    assert manager_obj.ctx_copy_share_link(path) == "https://server/document"

    manager_obj.ctx_edit_metadata(path)
    manager_obj.get_metadata_infos.assert_called_with(path, edit=True)

    manager_obj.get_metadata_infos.side_effect = ValueError("unmanaged")
    manager_obj.open_local_file.reset_mock()
    manager_obj.osi.cb_set.reset_mock()
    manager_obj.ctx_access_online(path)
    assert manager_obj.ctx_copy_share_link(path) == ""
    manager_obj.ctx_edit_metadata(path)
    manager_obj.open_local_file.assert_not_called()
    manager_obj.osi.cb_set.assert_not_called()


def test_send_sync_status_only_uses_matching_engine(manager_obj, tmp_path):
    first = SimpleNamespace(local_folder=tmp_path / "first", dao=Mock())
    second = SimpleNamespace(local_folder=tmp_path / "second", dao=Mock())
    manager_obj.engines = {"first": first, "second": second}
    nested = second.local_folder / "folder"
    states = ["state"]
    second.dao.get_local_children.return_value = states

    manager_obj.send_sync_status(nested)

    first.dao.get_local_children.assert_not_called()
    second.dao.get_local_children.assert_called_once_with(Path("folder"))
    manager_obj.osi.send_content_sync_status.assert_called_once_with(states, nested)

    manager_obj.osi.send_content_sync_status.reset_mock()
    manager_obj.send_sync_status(tmp_path / "outside")
    manager_obj.osi.send_content_sync_status.assert_not_called()


def test_send_sync_status_supports_windows_paths(manager_obj):
    local_folder = PureWindowsPath(r"C:\Users\test\Drive")
    engine = SimpleNamespace(local_folder=local_folder, dao=Mock())
    manager_obj.engines = {"windows": engine}
    path = local_folder / "folder"
    states = ["state"]
    engine.dao.get_local_children.return_value = states

    manager_obj.send_sync_status(path)

    engine.dao.get_local_children.assert_called_once_with(PureWindowsPath("folder"))
    manager_obj.osi.send_content_sync_status.assert_called_once_with(states, path)


def test_wait_for_server_config_success_and_timeout(manager_obj, monkeypatch):
    manager_obj.server_config_updater.first_run = False
    assert manager_obj.wait_for_server_config(timeout=3) is True
    manager_obj.server_config_updater.force_poll.assert_not_called()

    manager_obj.server_config_updater.first_run = True
    sleeps = []

    def finish_after_two(_):
        sleeps.append(True)
        if len(sleeps) == 2:
            manager_obj.server_config_updater.first_run = False

    monkeypatch.setattr(manager_module, "sleep", finish_after_two)
    assert manager_obj.wait_for_server_config(timeout=3) is True
    assert len(sleeps) == 2
    manager_obj.server_config_updater.force_poll.assert_called_once_with()

    manager_obj.server_config_updater.first_run = True
    monkeypatch.setattr(manager_module, "sleep", Mock())
    assert manager_obj.wait_for_server_config(timeout=2) is False


def test_write_version_file_success_and_missing_parent(manager_obj, tmp_path):
    Options.is_frozen = True
    Options.nxdrive_home = tmp_path
    manager_obj._write_version_file()
    assert (tmp_path / "VERSION").read_text(encoding="utf-8") == (
        f"{manager_obj.version}\n"
    )

    Options.nxdrive_home = tmp_path / "missing" / "nested"
    manager_obj._write_version_file()
    assert not (Options.nxdrive_home / "VERSION").exists()
