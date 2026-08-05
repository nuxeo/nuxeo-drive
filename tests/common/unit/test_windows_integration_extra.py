import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, call

import pytest

from nxdrive.drive import constants
from nxdrive.drive.options import Options

WINDOWS_PATH = (
    Path(__file__).parents[3] / "nxdrive" / "drive" / "osi" / "windows" / "windows.py"
)
WINDOWS_MODULE = "nxdrive.drive.osi.windows._tested_windows"


@pytest.fixture
def frozen_app():
    original = Options.is_frozen
    Options.set("is_frozen", True, setter="manual")
    yield
    Options.set("is_frozen", original, setter="manual")


@pytest.fixture
def windows_module(monkeypatch):
    win32api = ModuleType("win32api")
    win32api.ShellExecute = Mock()

    client = ModuleType("win32com.client")
    client.Dispatch = Mock()
    shell = SimpleNamespace(SHChangeNotify=Mock())
    shellcon = SimpleNamespace(
        SHCNE_UPDATEITEM=1,
        SHCNF_PATH=2,
        SHCNF_FLUSH=4,
    )
    shell_package = ModuleType("win32com.shell")
    shell_package.shell = shell
    shell_package.shellcon = shellcon
    win32com = ModuleType("win32com")
    win32com.__path__ = []
    win32com.client = client
    win32com.shell = shell_package

    registry = ModuleType("nxdrive.drive.osi.windows.registry")
    registry.delete = Mock()
    registry.delete_value = Mock()
    registry.exists = Mock()
    registry.read = Mock()
    registry.write = Mock()

    extension = ModuleType("nxdrive.drive.osi.windows.extension")
    extension.WindowsExtensionListener = type("WindowsExtensionListener", (), {})
    extension.disable_overlay = Mock()
    extension.enable_overlay = Mock()
    extension.set_filter_folders = Mock()

    windows_package = importlib.import_module("nxdrive.drive.osi.windows")
    monkeypatch.setattr(windows_package, "registry", registry, raising=False)
    for name, module in (
        ("win32api", win32api),
        ("win32com", win32com),
        ("win32com.client", client),
        ("win32com.shell", shell_package),
        ("nxdrive.drive.osi.windows.registry", registry),
        ("nxdrive.drive.osi.windows.extension", extension),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(WINDOWS_MODULE, WINDOWS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, WINDOWS_MODULE, module)
    spec.loader.exec_module(module)
    return SimpleNamespace(module=module, registry=registry, extension=extension)


@pytest.fixture
def integration(windows_module):
    integration_type = windows_module.module.WindowsIntegration
    instance = integration_type.__new__(integration_type)
    instance._manager = None
    return instance


def test_install_addons_handles_missing_success_and_error(
    windows_module, integration, monkeypatch, tmp_path
):
    module = windows_module.module
    module.sys = SimpleNamespace(executable=str(tmp_path / "drive.exe"))
    windows_config = importlib.import_module("nxdrive.drive.osi.windows.windows_config")
    monkeypatch.setattr(
        windows_config, "get_addon_installer_name", Mock(return_value="addons.exe")
    )
    run = Mock()
    monkeypatch.setattr(module.subprocess, "run", run)

    assert integration.install_addons() is False
    run.assert_not_called()

    installer = tmp_path / "addons.exe"
    installer.touch()
    addons_installed = Mock(return_value=True)
    monkeypatch.setattr(integration, "addons_installed", addons_installed)

    assert integration.install_addons() is True
    run.assert_called_once_with([str(installer)])
    addons_installed.assert_called_once_with()

    run.reset_mock(side_effect=True)
    run.side_effect = RuntimeError("installer failed")
    assert integration.install_addons(setup="addons.exe") is False


def test_register_contextual_menu_skips_unsupported_server(
    windows_module, integration, frozen_app, monkeypatch
):
    monkeypatch.setattr(constants, "APP_SERVER", "ALFRESCO")

    integration.register_contextual_menu()

    windows_module.registry.write.assert_not_called()


def test_register_contextual_menu_writes_submenus_and_entries(
    windows_module, integration, frozen_app, monkeypatch
):
    module = windows_module.module
    monkeypatch.setattr(constants, "APP_SERVER", "NUXEO")
    module.sys = SimpleNamespace(executable="C:\\Drive\\drive.exe")
    translate = Mock(side_effect=lambda key: f"translated-{key}")
    monkeypatch.setattr(module.Translator, "get", translate)

    integration.register_contextual_menu()

    assert windows_module.registry.write.call_count == 10
    assert windows_module.registry.write.call_args_list[:2] == [
        call(
            f"Software\\Classes\\*\\shell\\{module.APP_NAME}",
            {
                "Icon": '"C:\\Drive\\drive.exe",0',
                "MUIVerb": module.APP_NAME,
                "ExtendedSubCommandsKey": f"*\\shell\\{module.APP_NAME}\\",
            },
        ),
        call(
            f"Software\\Classes\\directory\\shell\\{module.APP_NAME}",
            {
                "Icon": '"C:\\Drive\\drive.exe",0',
                "MUIVerb": module.APP_NAME,
                "ExtendedSubCommandsKey": f"*\\shell\\{module.APP_NAME}\\",
            },
        ),
    ]
    assert translate.call_args_list == [
        call("CONTEXT_MENU_1"),
        call("CONTEXT_MENU_2"),
        call("CONTEXT_MENU_3"),
        call("CONTEXT_MENU_4"),
    ]
    command_values = [
        args[1]
        for args, _kwargs in (
            registry_call
            for registry_call in windows_module.registry.write.call_args_list
            if registry_call.args[0].endswith("\\command")
        )
    ]
    assert command_values == [
        '"C:\\Drive\\drive.exe" access-online --file "%1"',
        '"C:\\Drive\\drive.exe" copy-share-link --file "%1"',
        '"C:\\Drive\\drive.exe" edit-metadata --file "%1"',
        '"C:\\Drive\\drive.exe" direct-transfer --file "%1"',
    ]


def test_create_shortcut_populates_windows_shortcut(
    windows_module, integration, tmp_path
):
    module = windows_module.module
    shortcut = Mock()
    shell = Mock()
    shell.CreateShortCut.return_value = shortcut
    module.Dispatch.return_value = shell
    favorite = tmp_path / "Drive.lnk"
    folder = tmp_path / "sync" / "folder"

    integration._create_shortcut(favorite, folder)

    module.Dispatch.assert_called_once_with("WScript.Shell")
    shell.CreateShortCut.assert_called_once_with(str(favorite))
    assert shortcut.Targetpath == str(folder)
    assert shortcut.WorkingDirectory == str(folder.parent)
    assert shortcut.IconLocation == str(folder)
    shortcut.save.assert_called_once_with()


def test_create_shortcut_logs_dispatch_error(
    windows_module, integration, monkeypatch, tmp_path
):
    module = windows_module.module
    module.Dispatch.side_effect = RuntimeError("COM unavailable")
    log = Mock()
    monkeypatch.setattr(module, "log", log)
    folder = tmp_path / "sync"

    integration._create_shortcut(tmp_path / "Drive.lnk", folder)

    log.warning.assert_called_once_with(
        f"Could not create the favorite for {folder!r}", exc_info=True
    )


def test_watch_or_ignore_updates_filter_paths(windows_module, integration, tmp_path):
    set_filter_folders = windows_module.extension.set_filter_folders
    existing = tmp_path / "existing"
    other = tmp_path / "other"
    added = tmp_path / "added"

    integration._watch_or_ignore(added, "watch")
    set_filter_folders.assert_not_called()

    integration._manager = SimpleNamespace(
        engines={
            "first": SimpleNamespace(local_folder=existing),
            "second": SimpleNamespace(local_folder=other),
        }
    )
    integration._watch_or_ignore(added, "watch")
    set_filter_folders.assert_called_once_with({existing, other, added})

    set_filter_folders.reset_mock()
    integration._watch_or_ignore(existing, "ignore")
    set_filter_folders.assert_called_once_with({other})
