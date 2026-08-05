import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

CONSOLE_PATH = Path(__file__).parents[3] / "nxdrive" / "drive" / "console.py"
CONSOLE_MODULE = "nxdrive.drive._tested_console"


class FakeSignal:
    def __init__(self):
        self.connect = Mock()


class FakeCoreApplication:
    organization_name = None

    @classmethod
    def setOrganizationName(cls, name):
        cls.organization_name = name

    def __init__(self, arguments):
        self.arguments = arguments
        self.aboutToQuit = FakeSignal()
        self.quit = Mock()


class FakeTimer:
    def __init__(self):
        self.timeout = FakeSignal()
        self.start = Mock()


@pytest.fixture
def console_module(monkeypatch):
    qt_imports = ModuleType("nxdrive.drive.qt.imports")
    qt_imports.QCoreApplication = FakeCoreApplication
    qt_imports.QTimer = FakeTimer
    monkeypatch.setitem(sys.modules, "nxdrive.drive.qt.imports", qt_imports)

    spec = importlib.util.spec_from_file_location(CONSOLE_MODULE, CONSOLE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, CONSOLE_MODULE, module)
    spec.loader.exec_module(module)
    return module


def test_console_application_initializes_manager_and_timer(console_module):
    manager = Mock()

    application = console_module.ConsoleApplication(manager, ["ndrive", "console"])

    assert FakeCoreApplication.organization_name == console_module.COMPANY
    assert application.arguments == ["ndrive", "console"]
    application.timer.start.assert_called_once_with(100)
    timeout_callback = application.timer.timeout.connect.call_args.args[0]
    assert timeout_callback() is None
    assert manager.application is application
    manager.updater.appUpdated.connect.assert_called_once_with(application.quit)
    application.aboutToQuit.connect.assert_called_once_with(manager.stop)
    manager.start.assert_called_once_with()
