"""Cross-platform coverage tests for shared OS integration helpers."""

import importlib
import json
import sys
import typing
import unicodedata
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock, call

import pytest

from nxdrive.drive import constants
from nxdrive.drive.options import MetaOptions

ROOT = Path(__file__).parents[3]
OSI_ROOT = ROOT / "nxdrive" / "drive" / "osi"


def _load_source(
    monkeypatch,
    relative_path: str,
    module_name: str,
    package: str,
    *,
    type_checking: bool = False,
):
    """Load a source file under an isolated name while preserving relative imports."""
    path = OSI_ROOT / relative_path
    module = ModuleType(module_name)
    module.__file__ = str(path)
    module.__package__ = package
    monkeypatch.setitem(sys.modules, module_name, module)

    original_type_checking = typing.TYPE_CHECKING
    typing.TYPE_CHECKING = type_checking
    try:
        code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
        exec(code, module.__dict__)
    finally:
        typing.TYPE_CHECKING = original_type_checking
    return module


@pytest.fixture
def frozen_app(monkeypatch):
    """Run methods guarded by if_frozen and restore the exact previous option."""
    monkeypatch.setitem(MetaOptions.options, "is_frozen", (True, "manual"))


@pytest.fixture
def shared_modules(monkeypatch):
    extension = _load_source(
        monkeypatch,
        "extension.py",
        "nxdrive.drive.osi._coverage_extension",
        "nxdrive.drive.osi",
        type_checking=True,
    )
    abstract = _load_source(
        monkeypatch,
        "__init__.py",
        "nxdrive.drive.osi._coverage_init",
        "nxdrive.drive.osi",
        type_checking=True,
    )
    return SimpleNamespace(abstract=abstract, extension=extension)


def test_abstract_osi_defaults_and_uninstall(shared_modules, tmp_path):
    integration = shared_modules.abstract.AbstractOSIntegration(None)
    local_path = tmp_path / "document.txt"

    integration.open_local_file(str(local_path), select=True)
    assert integration.startup_enabled() is False
    integration.register_startup()
    integration.unregister_startup()
    assert integration.addons_installed() is False
    assert integration.install_addons() is False
    integration.register_protocol_handlers()
    integration.watch_folder(tmp_path)
    integration.unwatch_folder(tmp_path)
    integration.send_sync_status(None, local_path)
    integration.send_content_sync_status([], tmp_path)
    assert integration.get_extension_listener() is None
    integration.register_contextual_menu()
    integration.unregister_contextual_menu()
    integration.register_folder_link(tmp_path)
    integration.unregister_folder_link(tmp_path)
    assert integration.get_system_configuration() == {}
    assert integration.cb_get() == ""
    integration.cb_set("clipboard text")
    integration.init()
    integration.cleanup()

    integration.uninstall()


def test_abstract_osi_rejects_an_unsupported_platform(shared_modules, monkeypatch):
    module = shared_modules.abstract
    monkeypatch.setattr(module, "LINUX", False)
    monkeypatch.setattr(module, "MAC", False)
    monkeypatch.setattr(module, "WINDOWS", False)

    with pytest.raises(RuntimeError, match="OS not supported"):
        module.AbstractOSIntegration.get(None)


def test_extension_listener_address_start_and_engine_lookup(shared_modules, tmp_path):
    module = shared_modules.extension
    server_address = SimpleNamespace(toString=Mock(return_value="127.0.0.1"))
    address_source = SimpleNamespace(
        serverAddress=Mock(return_value=server_address),
        serverPort=Mock(return_value=10650),
    )
    assert module.ExtensionListener.address.fget(address_source) == "127.0.0.1:10650"

    start_listener = SimpleNamespace(
        host="localhost",
        port=10650,
        explorer_name="Test Explorer",
        address="127.0.0.1:10650",
        host_to_addr=Mock(return_value="resolved-address"),
        listen=Mock(),
        listening=SimpleNamespace(emit=Mock()),
    )
    module.ExtensionListener.start_listening(start_listener)
    start_listener.listen.assert_called_once_with("resolved-address", 10650)
    start_listener.listening.emit.assert_called_once_with()

    sync_root = tmp_path / "sync"
    engine = SimpleNamespace(local_folder=sync_root)
    manager = SimpleNamespace(engines={"engine": engine})
    engine_listener = SimpleNamespace(manager=manager)
    synced_file = sync_root / "folder" / "document.txt"
    other_file = tmp_path / "other" / "document.txt"

    assert module.ExtensionListener.get_engine(engine_listener, synced_file) is engine
    assert module.ExtensionListener.get_engine(engine_listener, other_file) is None


class _Volume:
    def __init__(self, path: PurePosixPath, *, directory: bool = True):
        self.path = path
        self.directory = directory

    def __str__(self):
        return str(self.path)

    def __truediv__(self, name):
        return self.path / name

    def is_dir(self):
        return self.directory


@pytest.fixture
def darwin_modules(monkeypatch):
    core_services = ModuleType("CoreServices")
    for name in (
        "CFURLCreateWithString",
        "LSSetDefaultHandlerForURLScheme",
        "LSSharedFileListCopySnapshot",
        "LSSharedFileListCreate",
        "LSSharedFileListInsertItemURL",
        "LSSharedFileListItemCopyDisplayName",
        "LSSharedFileListItemRemove",
        "NSBundle",
        "NSDistributedNotificationCenter",
        "NSUserDefaults",
        "NSUserNotification",
        "NSUserNotificationCenter",
    ):
        setattr(core_services, name, Mock(name=name))
    core_services.LSSharedFileListItemRef = object
    core_services.NSMutableDictionary = dict
    core_services.NSObject = object
    core_services.kLSSharedFileListFavoriteItems = object()
    core_services.kLSSharedFileListItemBeforeFirst = object()
    monkeypatch.setitem(sys.modules, "CoreServices", core_services)

    appkit = ModuleType("AppKit")
    appkit.NSWorkspace = Mock(name="NSWorkspace")
    monkeypatch.setitem(sys.modules, "AppKit", appkit)

    scripting_bridge = ModuleType("ScriptingBridge")
    scripting_bridge.SBApplication = Mock(name="SBApplication")
    monkeypatch.setitem(sys.modules, "ScriptingBridge", scripting_bridge)

    darwin = _load_source(
        monkeypatch,
        "darwin/darwin.py",
        "nxdrive.drive.osi.darwin._coverage_darwin",
        "nxdrive.drive.osi.darwin",
    )
    notifications = _load_source(
        monkeypatch,
        "darwin/pyNotificationCenter.py",
        "nxdrive.drive.osi.darwin._coverage_notifications",
        "nxdrive.drive.osi.darwin",
        type_checking=True,
    )
    files = _load_source(
        monkeypatch,
        "darwin/files.py",
        "nxdrive.drive.osi.darwin._coverage_files",
        "nxdrive.drive.osi.darwin",
    )
    extension = _load_source(
        monkeypatch,
        "darwin/extension.py",
        "nxdrive.drive.osi.darwin._coverage_extension",
        "nxdrive.drive.osi.darwin",
        type_checking=True,
    )
    return SimpleNamespace(
        core=core_services,
        darwin=darwin,
        extension=extension,
        files=files,
        notifications=notifications,
    )


def test_darwin_init_falls_back_to_legacy_identifiers(
    darwin_modules, frozen_app, monkeypatch
):
    module = darwin_modules.darwin
    app_bundle = (
        PurePosixPath("/") / "Applications" / f"{module._constants.APP_NAME}.app"
    )
    monkeypatch.setitem(MetaOptions.options, "server_type", ("nuxeo", "manual"))
    monkeypatch.setattr(module, "_get_app", Mock(return_value=str(app_bundle)))
    check_call = Mock()
    monkeypatch.setattr(module.subprocess, "check_call", check_call)

    class BrokenFinderSyncConfiguration:
        _finder_sync_loaded = False

        @property
        def FINDERSYNC_ID(self):
            raise RuntimeError("registry unavailable")

    integration = BrokenFinderSyncConfiguration()
    module.DarwinIntegration.init(integration)

    expected_id = "org.nuxeo.drive.NuxeoFinderSync"
    expected_path = f"{app_bundle}/Contents/PlugIns/NuxeoFinderSync.appex/"
    assert check_call.call_args_list == [
        call(["pluginkit", "-e", "use", "-i", expected_id]),
        call(["pluginkit", "-a", expected_path]),
    ]
    assert integration._finder_sync_loaded is True


def test_darwin_agent_path_and_non_nuxeo_context_menu(
    darwin_modules, frozen_app, monkeypatch
):
    module = darwin_modules.darwin
    agent = module.DarwinIntegration._get_agent_file(SimpleNamespace())
    assert agent.name == f"{module.BUNDLE_IDENTIFIER}.plist"
    assert agent.parent.name == "LaunchAgents"

    log = Mock()
    monkeypatch.setattr(module, "log", log)
    monkeypatch.setattr(constants, "APP_SERVER", "ALFRESCO")
    module.DarwinIntegration.register_contextual_menu(SimpleNamespace())
    log.info.assert_called_once_with("Contextual menu is not available at this time")


def test_darwin_prune_handles_volume_enumeration_failure(
    darwin_modules, frozen_app, monkeypatch
):
    module = darwin_modules.darwin
    volumes_root = Mock()
    volumes_root.glob.side_effect = OSError("volume service unavailable")
    monkeypatch.setattr(module, "Path", Mock(return_value=volumes_root))
    log = Mock()
    monkeypatch.setattr(module, "log", log)

    module.DarwinIntegration._prune_competing_url_handlers(SimpleNamespace())

    log.exception.assert_called_once()


def test_darwin_prune_filters_and_cleans_competing_volumes(
    darwin_modules, frozen_app, monkeypatch
):
    module = darwin_modules.darwin
    app_name = module._constants.APP_NAME
    volume_path = PurePosixPath("/") / "Volumes" / f"{app_name} Installer"
    canonical = PurePosixPath("/") / "Applications" / f"{app_name}.app"
    volume = _Volume(volume_path)
    volumes_root = Mock()
    volumes_root.glob.return_value = [volume]
    monkeypatch.setattr(module, "Path", Mock(return_value=volumes_root))
    get_app = Mock(return_value=str(volume_path))
    monkeypatch.setattr(module, "_get_app", get_app)
    run = Mock()
    monkeypatch.setattr(module.subprocess, "run", run)
    log = Mock()
    monkeypatch.setattr(module, "log", log)

    module.DarwinIntegration._prune_competing_url_handlers(SimpleNamespace())
    run.assert_not_called()

    get_app.return_value = str(canonical)
    volume.directory = False
    module.DarwinIntegration._prune_competing_url_handlers(SimpleNamespace())
    run.assert_not_called()

    volume.directory = True
    module.DarwinIntegration._prune_competing_url_handlers(SimpleNamespace())
    assert run.call_count == 2
    assert str(volume_path) in run.call_args_list[0].args[0]
    assert str(volume_path / f"{app_name}.app") in run.call_args_list[1].args[0]

    run.reset_mock(side_effect=True)
    run.side_effect = [OSError("detach failed"), OSError("cleanup failed")]
    module.DarwinIntegration._prune_competing_url_handlers(SimpleNamespace())
    assert run.call_count == 2
    log.exception.assert_called_once_with(f"Failed to detach {str(volume_path)!r}")


def test_notification_delegator_callbacks(darwin_modules):
    module = darwin_modules.notifications
    info_dictionary = {}
    module.NSBundle.mainBundle().infoDictionary.return_value = info_dictionary
    delegator = module.NotificationDelegator()
    assert info_dictionary["CFBundleIdentifier"] == module.BUNDLE_IDENTIFIER

    service = Mock()
    delegator.manager = SimpleNamespace(notification_service=service)
    center = Mock()
    notification = Mock()

    notification.userInfo.return_value = {"kind": "without-uuid"}
    delegator.userNotificationCenter_didActivateNotification_(center, notification)
    service.get_notifications.assert_not_called()

    notification.userInfo.return_value = {"uuid": "missing"}
    service.get_notifications.return_value = {}
    delegator.userNotificationCenter_didActivateNotification_(center, notification)
    center.removeDeliveredNotification_.assert_called_once_with(notification)
    service.trigger_notification.assert_called_once_with("missing")

    center.removeDeliveredNotification_.reset_mock()
    service.trigger_notification.reset_mock()
    saved_notification = Mock()
    saved_notification.is_discard_on_trigger.return_value = False
    notification.userInfo.return_value = {"uuid": "saved"}
    service.get_notifications.return_value = {"saved": saved_notification}
    delegator.userNotificationCenter_didActivateNotification_(center, notification)
    center.removeDeliveredNotification_.assert_not_called()
    service.trigger_notification.assert_called_once_with("saved")

    saved_notification.is_discard_on_trigger.return_value = True
    delegator.userNotificationCenter_didActivateNotification_(center, notification)
    center.removeDeliveredNotification_.assert_called_once_with(notification)
    assert delegator.userNotificationCenter_shouldPresentNotification_(None, None)


def test_notification_setup_and_delivery(darwin_modules):
    module = darwin_modules.notifications
    center = Mock()
    module.NSUserNotificationCenter.defaultUserNotificationCenter.return_value = center
    delegator = Mock()
    module.setup_delegator(delegator)
    center.setDelegate_.assert_called_once_with(delegator)

    notification = Mock()
    module.NSUserNotification.alloc().init.return_value = notification
    module.notify(
        "Title",
        "Subtitle",
        "Information",
        delay=2,
        sound=True,
        user_info=None,
    )
    notification.setTitle_.assert_called_once_with("Title")
    notification.setSubtitle_.assert_called_once_with("Subtitle")
    notification.setInformativeText_.assert_called_once_with("Information")
    notification.setUserInfo_.assert_called_once_with({})
    notification.setSoundName_.assert_called_once_with(
        "NSUserNotificationDefaultSoundName"
    )
    center.deliverNotification_.assert_called_once_with(notification)

    module.NSUserNotificationCenter.defaultUserNotificationCenter.return_value = None
    module.notify("Silent", "", "No center", sound=False, user_info={"uuid": "id"})


def test_darwin_opened_adobe_files_branches(darwin_modules, monkeypatch, tmp_path):
    module = darwin_modules.files
    compute_pid = Mock(return_value=1234)
    monkeypatch.setattr(module, "compute_fake_pid_from_path", compute_pid)
    module.NSWorkspace.sharedWorkspace.return_value = None
    assert module._is_running("com.example.Editor") is False

    workspace = Mock()
    module.NSWorkspace.sharedWorkspace.return_value = workspace
    workspace.runningApplications.return_value = []
    assert module._is_running("com.example.Editor") is False

    running_application = Mock()
    running_application.bundleIdentifier.return_value = "com.example.Editor"
    workspace.runningApplications.return_value = [running_application]
    assert module._is_running("com.example.Editor") is True

    is_running = Mock(return_value=False)
    monkeypatch.setattr(module, "_is_running", is_running)
    assert list(module._get_opened_files_adobe_cc("com.example.Editor")) == []

    is_running.return_value = True
    module.SBApplication.applicationWithBundleIdentifier_.return_value = None
    assert list(module._get_opened_files_adobe_cc("com.example.Editor")) == []

    adobe_app = Mock()
    module.SBApplication.applicationWithBundleIdentifier_.return_value = adobe_app
    adobe_app.isRunning.return_value = False
    assert list(module._get_opened_files_adobe_cc("com.example.Editor")) == []

    adobe_app.isRunning.return_value = True
    adobe_app.documents.side_effect = AttributeError("documents unavailable")
    assert list(module._get_opened_files_adobe_cc("com.example.Editor")) == []

    adobe_app.documents.side_effect = None
    adobe_app.documents.return_value = []
    assert list(module._get_opened_files_adobe_cc("com.example.Editor")) == []

    unsaved = Mock()
    unsaved.filePath.return_value = None
    saved = Mock()
    file_path = Mock()
    raw_path = str(tmp_path / "design.psd")
    file_path.path.return_value = raw_path
    saved.filePath.return_value = file_path
    adobe_app.documents.return_value = [unsaved, saved]

    assert list(module._get_opened_files_adobe_cc("com.example.Editor")) == [
        (1234, module.Path(raw_path))
    ]
    compute_pid.assert_called_once_with(raw_path)


def test_darwin_extension_status_and_watch_handlers(darwin_modules, tmp_path):
    module = darwin_modules.extension
    manager = Mock()
    listener = SimpleNamespace(manager=manager)

    assert module.DarwinExtensionListener.handle_status(listener, object()) is None
    decomposed_path = unicodedata.normalize("NFD", str(tmp_path / "café.txt"))
    module.DarwinExtensionListener.handle_status(listener, decomposed_path)
    expected_path = module.Path(unicodedata.normalize("NFC", decomposed_path))
    manager.send_sync_status.assert_called_once_with(expected_path)

    first = SimpleNamespace(local_folder=tmp_path / "first")
    second = SimpleNamespace(local_folder=tmp_path / "second")
    manager.engines = {"first": first, "second": second}
    manager.osi.watch_folder.reset_mock()
    module.DarwinExtensionListener.handle_trigger_watch(listener)
    assert manager.osi.watch_folder.call_args_list == [
        call(first.local_folder),
        call(second.local_folder),
    ]


@pytest.fixture
def windows_modules(monkeypatch):
    winreg = ModuleType("winreg")
    winreg.HKEY_CURRENT_USER = object()
    winreg.KEY_ALL_ACCESS = 1
    winreg.KEY_SET_VALUE = 2
    winreg.KEY_READ = 4
    winreg.REG_SZ = 1
    for name in (
        "CreateKey",
        "CreateKeyEx",
        "DeleteKey",
        "DeleteValue",
        "EnumKey",
        "EnumValue",
        "OpenKey",
        "QueryInfoKey",
        "SetValueEx",
    ):
        setattr(winreg, name, MagicMock(name=name))
    monkeypatch.setitem(sys.modules, "winreg", winreg)

    win32api = ModuleType("win32api")
    win32api.ShellExecute = Mock()
    monkeypatch.setitem(sys.modules, "win32api", win32api)

    client = ModuleType("win32com.client")
    client.Dispatch = Mock()
    client.GetActiveObject = Mock()
    shell = SimpleNamespace(SHChangeNotify=Mock())
    shellcon = SimpleNamespace(SHCNE_UPDATEITEM=1, SHCNF_PATH=2, SHCNF_FLUSH=4)
    shell_package = ModuleType("win32com.shell")
    shell_package.shell = shell
    shell_package.shellcon = shellcon
    win32com = ModuleType("win32com")
    win32com.__path__ = []
    win32com.client = client
    win32com.shell = shell_package
    for name, fake_module in (
        ("win32com", win32com),
        ("win32com.client", client),
        ("win32com.shell", shell_package),
    ):
        monkeypatch.setitem(sys.modules, name, fake_module)

    package = importlib.import_module("nxdrive.drive.osi.windows")
    registry = _load_source(
        monkeypatch,
        "windows/registry.py",
        "nxdrive.drive.osi.windows._coverage_registry",
        "nxdrive.drive.osi.windows",
    )
    monkeypatch.setattr(package, "registry", registry, raising=False)
    monkeypatch.setitem(sys.modules, "nxdrive.drive.osi.windows.registry", registry)

    extension = _load_source(
        monkeypatch,
        "windows/extension.py",
        "nxdrive.drive.osi.windows._coverage_extension",
        "nxdrive.drive.osi.windows",
        type_checking=True,
    )
    monkeypatch.setattr(package, "extension", extension, raising=False)
    monkeypatch.setitem(sys.modules, "nxdrive.drive.osi.windows.extension", extension)

    windows_config = _load_source(
        monkeypatch,
        "windows/windows_config.py",
        "nxdrive.drive.osi.windows._coverage_config",
        "nxdrive.drive.osi.windows",
    )
    monkeypatch.setattr(package, "windows_config", windows_config, raising=False)
    monkeypatch.setitem(
        sys.modules, "nxdrive.drive.osi.windows.windows_config", windows_config
    )

    files = _load_source(
        monkeypatch,
        "windows/files.py",
        "nxdrive.drive.osi.windows._coverage_files",
        "nxdrive.drive.osi.windows",
    )
    windows = _load_source(
        monkeypatch,
        "windows/windows.py",
        "nxdrive.drive.osi.windows._coverage_windows",
        "nxdrive.drive.osi.windows",
    )
    return SimpleNamespace(
        client=client,
        extension=extension,
        files=files,
        registry=registry,
        shell=shell,
        win32api=win32api,
        windows=windows,
        windows_config=windows_config,
        winreg=winreg,
    )


def test_windows_registry_success_and_recursive_delete(windows_modules):
    registry = windows_modules.registry
    winreg = windows_modules.winreg
    key = r"Software\Classes\Drive"

    assert registry.create(key) is True
    assert registry.write(key, "default value") is True
    write_handle = winreg.CreateKeyEx.return_value.__enter__.return_value
    winreg.SetValueEx.assert_called_once_with(
        write_handle, None, 0, winreg.REG_SZ, "default value"
    )

    assert registry.delete_value(key, "Obsolete") is True
    delete_handle = winreg.OpenKey.return_value.__enter__.return_value
    winreg.DeleteValue.assert_called_once_with(delete_handle, "Obsolete")

    winreg.EnumKey.side_effect = ["Child", OSError("no child"), OSError("no child")]
    assert registry.delete(key) is True
    assert winreg.DeleteKey.call_args_list == [
        call(winreg.HKEY_CURRENT_USER, rf"{key}\Child"),
        call(winreg.HKEY_CURRENT_USER, key),
    ]


def test_windows_registry_error_paths(windows_modules):
    registry = windows_modules.registry
    winreg = windows_modules.winreg
    key = r"Software\Classes\Drive"

    winreg.CreateKey.side_effect = OSError("access denied")
    assert registry.create(key) is False

    winreg.OpenKey.side_effect = PermissionError("access denied")
    assert registry.delete(key) is False
    assert registry.delete_value(key, "Obsolete") is False

    winreg.CreateKeyEx.side_effect = OSError("access denied")
    assert registry.write(key, {"Enabled": "1"}) is False


def test_windows_extension_helpers_and_codecs(windows_modules, monkeypatch, tmp_path):
    module = windows_modules.extension
    registry_write = Mock()
    monkeypatch.setattr(module.registry, "write", registry_write)
    first = tmp_path / "first"
    second = tmp_path / "second"

    module.enable_overlay()
    module.disable_overlay()
    module.set_filter_folders({first, second})
    assert registry_write.call_args_list[:2] == [
        call(module.OVERLAYS_REGISTRY_KEY, {module.ENABLE_OVERLAY: "1"}),
        call(module.OVERLAYS_REGISTRY_KEY, {module.ENABLE_OVERLAY: "0"}),
    ]
    filters = json.loads(
        registry_write.call_args_list[2].args[1][module.FILTER_FOLDERS]
    )
    assert set(filters) == {str(first), str(second)}

    module.refresh_files([first, second])
    assert module.shell.SHChangeNotify.call_count == 2

    listener_type = module.WindowsExtensionListener
    payload = "café".encode("latin-1") + b"\0"
    assert listener_type._parse_payload(None, payload) == "café"
    assert listener_type._format_response(None, "42") == b"4\x002\x00"


def test_windows_extension_handle_status_branches(
    windows_modules, monkeypatch, tmp_path
):
    module = windows_modules.extension
    listener_type = module.WindowsExtensionListener
    listener = SimpleNamespace(get_engine=Mock(return_value=None))

    assert listener_type.handle_status(listener, object()) is None
    assert listener_type.handle_status(listener, str(tmp_path / "outside.txt")) is None

    sync_root = tmp_path / "sync"
    target = sync_root / "café.txt"
    decomposed_target = unicodedata.normalize("NFD", str(target))
    expected_target = module.Path(unicodedata.normalize("NFC", decomposed_target))
    engine = SimpleNamespace(local_folder=sync_root, dao=Mock())
    listener.get_engine.return_value = engine
    engine.dao.get_state_from_local.return_value = None
    assert listener_type.handle_status(listener, decomposed_target) is None
    engine.dao.get_state_from_local.assert_called_once_with(
        expected_target.relative_to(sync_root)
    )

    state = object()
    engine.dao.get_state_from_local.return_value = state
    formatted_status = {"path": str(expected_target), "value": "1"}
    get_formatted_status = Mock(return_value=formatted_status)
    monkeypatch.setattr(module, "get_formatted_status", get_formatted_status)
    assert listener_type.handle_status(listener, decomposed_target) == formatted_status
    get_formatted_status.assert_called_once_with(state, expected_target)


def test_windows_integration_init_shell_status_and_unwatch(
    windows_modules, frozen_app, monkeypatch
):
    module = windows_modules.windows
    first = PureWindowsPath("C:/Sync/First")
    second = PureWindowsPath("D:/Sync/Second")
    manager = SimpleNamespace(
        engines={
            "first": SimpleNamespace(local_folder=first),
            "second": SimpleNamespace(local_folder=second),
        }
    )
    set_filter_folders = Mock()
    enable_overlay = Mock()
    monkeypatch.setattr(module, "set_filter_folders", set_filter_folders)
    monkeypatch.setattr(module, "enable_overlay", enable_overlay)

    module.WindowsIntegration.init(SimpleNamespace(_manager=manager))
    set_filter_folders.assert_called_once_with({first, second})
    enable_overlay.assert_called_once_with()

    selected = PureWindowsPath("C:/Sync/report.docx")
    module.WindowsIntegration.open_local_file(
        SimpleNamespace(), str(selected), select=True
    )
    module.win32api.ShellExecute.assert_called_once_with(
        None, "open", "explorer.exe", f"/select,{selected}", None, 1
    )

    module.WindowsIntegration.send_sync_status(SimpleNamespace(), None, selected)
    module.shell.SHChangeNotify.assert_called_once()

    watch_or_ignore = Mock()
    module.WindowsIntegration.unwatch_folder(
        SimpleNamespace(_watch_or_ignore=watch_or_ignore), second
    )
    watch_or_ignore.assert_called_once_with(second, "ignore")


def test_windows_integration_context_startup_and_folder_link(
    windows_modules, frozen_app, monkeypatch, tmp_path
):
    module = windows_modules.windows
    registry_delete = Mock()
    registry_delete_value = Mock()
    registry_read = Mock()
    registry_write = Mock()
    monkeypatch.setattr(module.registry, "delete", registry_delete)
    monkeypatch.setattr(module.registry, "delete_value", registry_delete_value)
    monkeypatch.setattr(module.registry, "read", registry_read)
    monkeypatch.setattr(module.registry, "write", registry_write)

    module.WindowsIntegration.unregister_contextual_menu(SimpleNamespace())
    assert registry_delete.call_count == 2

    shortcut = tmp_path / "Drive.lnk"
    shortcut.touch()
    folder_link = SimpleNamespace(_get_folder_link=Mock(return_value=shortcut))
    module.WindowsIntegration.unregister_folder_link(folder_link, tmp_path / "sync")
    assert not shortcut.exists()

    registry_read.return_value = {module.APP_NAME: "drive.exe"}
    assert module.WindowsIntegration.startup_enabled(SimpleNamespace()) is True
    registry_read.return_value = {}
    assert module.WindowsIntegration.startup_enabled(SimpleNamespace()) is False

    startup = SimpleNamespace(startup_enabled=Mock(return_value=True))
    module.WindowsIntegration.register_startup(startup)
    registry_write.assert_not_called()
    startup.startup_enabled.return_value = False
    module.WindowsIntegration.register_startup(startup)
    registry_write.assert_called_once()

    startup.startup_enabled.return_value = False
    module.WindowsIntegration.unregister_startup(startup)
    registry_delete_value.assert_not_called()
    startup.startup_enabled.return_value = True
    module.WindowsIntegration.unregister_startup(startup)
    registry_delete_value.assert_called_once()


def test_windows_opened_adobe_files(windows_modules, monkeypatch, tmp_path):
    module = windows_modules.files
    first_path = str(tmp_path / "first.psd")
    second_path = str(tmp_path / "second.ai")
    compute_pid = Mock(side_effect=[101, 202])
    monkeypatch.setattr(module, "compute_fake_pid_from_path", compute_pid)
    app = SimpleNamespace(
        Application=SimpleNamespace(
            Documents=[
                SimpleNamespace(fullName=first_path),
                SimpleNamespace(fullName=second_path),
            ]
        )
    )
    get_active_object = Mock(return_value=app)
    monkeypatch.setattr(module, "GetActiveObject", get_active_object)

    assert list(module._get_opened_files_adobe_cc("Adobe.Application")) == [
        (101, module.Path(first_path)),
        (202, module.Path(second_path)),
    ]
    assert compute_pid.call_args_list == [call(first_path), call(second_path)]
    get_active_object.assert_called_once_with("Adobe.Application")

    get_active_object.side_effect = RuntimeError("COM object unavailable")
    assert list(module._get_opened_files_adobe_cc("Missing.Application")) == []


def test_windows_addon_installer_name(windows_modules, monkeypatch):
    module = windows_modules.windows_config
    monkeypatch.setattr(module.st, "get_default_key", Mock(return_value="TEST"))
    get_config = Mock(
        return_value=SimpleNamespace(addon_installer_name="custom-addons.exe")
    )
    monkeypatch.setattr(module.st, "get", get_config)

    assert module.get_addon_installer_name() == "custom-addons.exe"
    get_config.return_value = SimpleNamespace(addon_installer_name="")
    assert module.get_addon_installer_name() == "drive-addons.exe"


@pytest.fixture
def linux_module(monkeypatch):
    importlib.import_module("nxdrive.drive.osi.linux")
    return _load_source(
        monkeypatch,
        "linux/linux.py",
        "nxdrive.drive.osi.linux._coverage_linux",
        "nxdrive.drive.osi.linux",
        type_checking=True,
    )


def test_linux_init_without_gio(linux_module, monkeypatch):
    icons_to_emblems = Mock()
    monkeypatch.setattr(
        linux_module.LinuxIntegration, "_icons_to_emblems", icons_to_emblems
    )
    monkeypatch.setattr(linux_module.shutil, "which", Mock(return_value=None))
    log = Mock()
    monkeypatch.setattr(linux_module, "log", log)

    integration = linux_module.LinuxIntegration(None)

    icons_to_emblems.assert_called_once_with()
    assert integration._gio_path is None
    assert integration._last_emblem == {}
    log.debug.assert_called_once_with(
        "`gio` not found on PATH; folder emblems will be disabled"
    )


def test_linux_open_local_file_selects_and_launches(linux_module, monkeypatch):
    environment = {"DISPLAY": ":test"}
    host_env = Mock(return_value=environment)
    popen = Mock()
    log = Mock()
    monkeypatch.setattr(linux_module, "host_env", host_env)
    monkeypatch.setattr(linux_module.subprocess, "Popen", popen)
    monkeypatch.setattr(linux_module, "log", log)
    local_file = PurePosixPath("sync") / "document.txt"

    linux_module.LinuxIntegration.open_local_file(
        SimpleNamespace(), str(local_file), select=True
    )

    log.info.assert_called_once()
    popen.assert_called_once_with(["xdg-open", str(local_file)], env=environment)


def test_linux_send_sync_status_success_and_error(
    linux_module, frozen_app, monkeypatch
):
    local_file = PurePosixPath("sync") / "document.txt"
    status = {"path": str(local_file), "value": "1"}
    get_formatted_status = Mock(return_value=status)
    monkeypatch.setattr(linux_module, "get_formatted_status", get_formatted_status)
    set_icon = Mock()
    integration = SimpleNamespace(_set_icon=set_icon)

    linux_module.LinuxIntegration.send_sync_status(integration, object(), local_file)
    set_icon.assert_called_once_with(status)

    get_formatted_status.side_effect = RuntimeError("stat failed")
    log = Mock()
    monkeypatch.setattr(linux_module, "log", log)
    linux_module.LinuxIntegration.send_sync_status(integration, object(), local_file)
    log.exception.assert_called_once_with(
        "Error while setting the status to {path!r}", exc_info=True
    )


def test_linux_icons_skip_identical_emblems(linux_module, monkeypatch, tmp_path):
    path_factory = SimpleNamespace(home=Mock(return_value=tmp_path))
    monkeypatch.setattr(linux_module, "Path", path_factory)
    monkeypatch.setattr(
        linux_module, "find_icon", Mock(return_value=tmp_path / "icons")
    )
    compare = Mock(return_value=True)
    copy = Mock()
    monkeypatch.setattr(linux_module.filecmp, "cmp", compare)
    monkeypatch.setattr(linux_module.shutil, "copy", copy)

    linux_module.LinuxIntegration._icons_to_emblems(SimpleNamespace())

    assert compare.call_count == 6
    copy.assert_not_called()
