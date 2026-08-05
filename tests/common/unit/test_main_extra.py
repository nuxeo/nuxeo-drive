import importlib.util
import locale
import signal
import sqlite3
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, call, patch

import pip_system_certs.wrapt_requests
import pytest

from nxdrive.drive import constants, fatal_error
from nxdrive.drive.qt import imports as qt_imports

MAIN_PATH = Path(__file__).parents[3] / "nxdrive" / "__main__.py"
MAIN_MODULE = "nxdrive._tested_main"


def _load_main(monkeypatch, *, windows=False):
    inject_truststore = Mock()
    register_adapter = Mock()
    set_signal = Mock()
    set_locale = Mock()
    exit_ = Mock()

    monkeypatch.setattr(constants, "WINDOWS", windows)
    monkeypatch.setattr(
        pip_system_certs.wrapt_requests, "inject_truststore", inject_truststore
    )
    monkeypatch.setattr(sqlite3, "register_adapter", register_adapter)
    monkeypatch.setattr(signal, "signal", set_signal)
    monkeypatch.setattr(locale, "setlocale", set_locale)
    monkeypatch.setattr(sys, "exit", exit_)
    monkeypatch.setattr(fatal_error, "check_executable_path", Mock(return_value=False))
    monkeypatch.setattr(fatal_error, "check_os_version", Mock(return_value=True))
    monkeypatch.setattr(fatal_error, "show_critical_error", Mock())

    spec = importlib.util.spec_from_file_location(MAIN_MODULE, MAIN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, MAIN_MODULE, module)
    spec.loader.exec_module(module)

    inject_truststore.assert_called_once_with()
    exit_.assert_called_once_with(1)

    for mocked in (
        register_adapter,
        set_signal,
        set_locale,
        module.check_executable_path,
        module.check_os_version,
        module.show_critical_error,
    ):
        mocked.reset_mock()
    return module


@pytest.fixture
def main_module(monkeypatch):
    return _load_main(monkeypatch)


def _set_runtime(module, *, platform="darwin", version=(3, 13, 1)):
    module.sys = SimpleNamespace(
        argv=["ndrive", "console", "--debug"],
        platform=platform,
        stderr=object(),
        stdout=object(),
        version_info=version,
    )


def _set_cli(monkeypatch, *, result=0, side_effect=None):
    handler = Mock()
    handler.handle.return_value = result
    handler.handle.side_effect = side_effect
    handler_type = Mock(return_value=handler)
    commandline = ModuleType("nxdrive.drive.commandline")
    commandline.CliHandler = handler_type
    monkeypatch.setitem(sys.modules, "nxdrive.drive.commandline", commandline)
    return handler_type, handler


def test_main_dispatches_cli_and_registers_runtime_hooks(main_module, monkeypatch):
    _set_runtime(main_module)
    main_module.check_executable_path.return_value = True
    main_module.check_os_version.return_value = True
    handler_type, handler = _set_cli(monkeypatch, result=7)

    assert main_module.main() == 7

    main_module.signal.signal.assert_called_once_with(
        main_module.signal.SIGINT, main_module.signal_handler
    )
    main_module.sqlite3.register_adapter.assert_called_once_with(
        main_module.datetime, main_module.adapt_datetime_iso
    )
    main_module.locale.setlocale.assert_called_once_with(main_module.locale.LC_TIME, "")
    main_module.check_executable_path.assert_called_once_with()
    main_module.check_os_version.assert_called_once_with()
    handler_type.assert_called_once_with()
    handler.handle.assert_called_once_with(["console", "--debug"])
    main_module.show_critical_error.assert_not_called()


def test_main_rejects_unsupported_python(main_module):
    _set_runtime(main_module, version=(3, 13, 0))

    assert main_module.main() == 1

    main_module.locale.setlocale.assert_not_called()
    main_module.check_executable_path.assert_not_called()
    main_module.show_critical_error.assert_called_once_with()


def test_main_continues_after_invalid_locale(main_module, monkeypatch, capsys):
    _set_runtime(main_module)
    main_module.locale.setlocale.side_effect = locale.Error("invalid locale")
    main_module.check_executable_path.return_value = True
    main_module.check_os_version.return_value = True
    _set_cli(monkeypatch, result=0)

    assert main_module.main() == 0

    assert "invalid locale" in capsys.readouterr().out
    main_module.show_critical_error.assert_not_called()


@pytest.mark.parametrize(
    "executable_ok, os_ok, os_check_count",
    [(False, True, 0), (True, False, 1)],
)
def test_main_stops_when_startup_check_fails(
    main_module, executable_ok, os_ok, os_check_count
):
    _set_runtime(main_module)
    main_module.check_executable_path.return_value = executable_ok
    main_module.check_os_version.return_value = os_ok

    assert main_module.main() == 1

    assert main_module.check_os_version.call_count == os_check_count
    main_module.show_critical_error.assert_not_called()


@pytest.mark.parametrize("code", [0, 2])
def test_main_handles_system_exit(main_module, monkeypatch, code):
    _set_runtime(main_module)
    main_module.check_executable_path.return_value = True
    main_module.check_os_version.return_value = True
    _set_cli(monkeypatch, side_effect=SystemExit(code))

    assert main_module.main() == code

    assert main_module.show_critical_error.call_count == (code != 0)


def test_main_reports_unexpected_errors(main_module):
    _set_runtime(main_module)
    main_module.check_executable_path.side_effect = RuntimeError("boom")

    assert main_module.main() == 1

    main_module.show_critical_error.assert_called_once_with()


def test_main_attaches_windows_console(main_module, monkeypatch):
    _set_runtime(main_module, platform="win32")
    main_module.check_executable_path.return_value = False
    attach_console = Mock(return_value=True)
    ctypes = ModuleType("ctypes")
    ctypes.windll = SimpleNamespace(
        kernel32=SimpleNamespace(AttachConsole=attach_console)
    )
    monkeypatch.setitem(sys.modules, "ctypes", ctypes)
    stdout = object()
    stderr = object()
    open_ = Mock(side_effect=[stdout, stderr])

    with patch("builtins.open", open_):
        assert main_module.main() == 1

    attach_console.assert_called_once_with(-1)
    assert open_.call_args_list == [call("CONOUT$", "w"), call("CONOUT$", "w")]
    assert main_module.sys.stdout is stdout
    assert main_module.sys.stderr is stderr


def test_main_logs_windows_console_open_error(main_module, monkeypatch):
    _set_runtime(main_module, platform="win32")
    main_module.check_executable_path.return_value = False
    ctypes = ModuleType("ctypes")
    ctypes.windll = SimpleNamespace(
        kernel32=SimpleNamespace(AttachConsole=Mock(return_value=True))
    )
    monkeypatch.setitem(sys.modules, "ctypes", ctypes)
    logger = Mock()

    with patch("builtins.open", Mock(side_effect=OSError("no console"))), patch(
        "logging.getLogger", return_value=logger
    ):
        assert main_module.main() == 1

    logger.error.assert_called_once_with(
        "Failed to attach console output: %s", logger.error.call_args.args[1]
    )
    assert isinstance(logger.error.call_args.args[1], OSError)


def test_signal_handler_quits_qt_application(main_module, monkeypatch, capsys):
    application = SimpleNamespace(quit=Mock(), processEvents=Mock())
    monkeypatch.setattr(qt_imports, "QApplication", application)

    main_module.signal_handler(signal.SIGTERM, None)

    assert "Caught SIGTERM" in capsys.readouterr().out
    application.quit.assert_called_once_with()
    application.processEvents.assert_called_once_with()


def test_windows_import_sets_default_qt_style(monkeypatch):
    monkeypatch.delenv("QT_QUICK_CONTROLS_STYLE", raising=False)

    _load_main(monkeypatch, windows=True)

    assert "QT_QUICK_CONTROLS_STYLE" in sys.modules["os"].environ
    assert sys.modules["os"].environ["QT_QUICK_CONTROLS_STYLE"] == "Basic"
