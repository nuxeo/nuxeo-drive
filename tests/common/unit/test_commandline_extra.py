import os
import sys
import threading
from argparse import Namespace
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime as real_datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

import nxdrive.drive.commandline as commandline
import nxdrive.drive.constants as constants
import nxdrive.drive.options as options_module
from nxdrive.drive.commandline import CliHandler, HealthCheck
from nxdrive.drive.feature import DisabledFeatures, Feature
from nxdrive.drive.options import MetaOptions, Options
from nxdrive.drive.state import State


@pytest.fixture(autouse=True)
def restore_commandline_global_state():
    """Keep command-line tests from leaking process-wide application state."""
    saved_options = deepcopy(MetaOptions.options)
    saved_callbacks = MetaOptions.callbacks.copy()
    saved_features = vars(Feature).copy()
    saved_disabled_features = list(DisabledFeatures)
    saved_state = vars(State).copy()
    saved_environment = os.environ.copy()
    saved_retry = commandline.RETRY
    saved_excepthook = sys.excepthook
    saved_threading_excepthook = threading.excepthook
    saved_file_log_level = options_module.DEFAULT_LOG_LEVEL_FILE
    constant_names = (
        "APP_SERVER",
        "APP_VERSION",
        "APP_NAME",
        "COMPANY",
        "BUNDLE_IDENTIFIER",
        "NXDRIVE_SCHEME",
        "CONFIG_REGISTRY_KEY",
    )
    saved_constants = {name: getattr(constants, name) for name in constant_names}

    # Other unit modules exercise crash-reporting paths and may leave this
    # process-wide namespace mutated. Command-line tests must start from the
    # same state as a fresh application process.
    State.about_to_quit = False
    State.crash_details = ""
    State.has_crashed = False

    yield

    MetaOptions.options = saved_options
    MetaOptions.callbacks = saved_callbacks
    vars(Feature).clear()
    vars(Feature).update(saved_features)
    DisabledFeatures[:] = saved_disabled_features
    vars(State).clear()
    vars(State).update(saved_state)
    os.environ.clear()
    os.environ.update(saved_environment)
    commandline.RETRY = saved_retry
    sys.excepthook = saved_excepthook
    threading.excepthook = saved_threading_excepthook
    options_module.DEFAULT_LOG_LEVEL_FILE = saved_file_log_level
    for name, value in saved_constants.items():
        setattr(constants, name, value)


@pytest.fixture
def cli(tmp_path):
    home = tmp_path / "options-home"
    home.mkdir()
    Options.nxdrive_home = home
    Options.server_type = "NUXEO"
    # Protocol callbacks use the lower-priority CLI setter, so preserve a
    # default setter here instead of assigning through the metaclass.
    MetaOptions.options["protocol_url"] = "", "default"
    return CliHandler()


def _write_handle_resources(tmp_path, server_type="NUXEO"):
    supported = tmp_path / "supported_server_list.txt"
    supported.write_text(f"# packaged server\n{server_type}\n", encoding="utf-8")
    downloads = tmp_path / "download_urls.txt"
    downloads.write_text(
        "nuxeo_update_site_url = https://updates.example/nuxeo\n"
        "alfresco_update_site_url = https://updates.example/alfresco\n",
        encoding="utf-8",
    )

    def find_resource(_resource, *, file):
        return {
            "supported_server_list.txt": supported,
            "download_urls.txt": downloads,
        }[file]

    return find_resource


@contextmanager
def _handle_runtime(
    cli,
    tmp_path,
    options,
    *,
    server_type="NUXEO",
    app_version=None,
    qssl_socket=None,
):
    """Replace every external side effect around ``CliHandler.handle``."""
    manager = MagicMock(name="manager")
    find_resource = _write_handle_resources(tmp_path, server_type)
    with ExitStack() as stack:
        runtime = SimpleNamespace()
        runtime.parse_cli = stack.enter_context(
            patch.object(cli, "parse_cli", return_value=options)
        )
        runtime.configure_logger = stack.enter_context(
            patch.object(cli, "_configure_logger")
        )
        runtime.install_faulthandler = stack.enter_context(
            patch.object(cli, "_install_faulthandler")
        )
        runtime.get_manager = stack.enter_context(
            patch.object(cli, "get_manager", return_value=manager)
        )
        runtime.set_app_server = stack.enter_context(
            patch.object(commandline, "set_app_server")
        )
        runtime.set_app_version = stack.enter_context(
            patch.object(commandline, "set_app_version")
        )
        runtime.set_log_level_file = stack.enter_context(
            patch.object(commandline, "set_log_level_file")
        )
        runtime.apply_restrictions = stack.enter_context(
            patch("nxdrive.drive.feature.apply_server_type_restrictions")
        )
        runtime.refresh_branding = stack.enter_context(
            patch("nxdrive.drive.constants.refresh_branding")
        )
        runtime.setup_sentry = stack.enter_context(
            patch("nxdrive.drive.tracing.setup_sentry")
        )
        runtime.find_resource = stack.enter_context(
            patch("nxdrive.drive.utils.find_resource", side_effect=find_resource)
        )
        stack.enter_context(patch.object(Path, "home", return_value=tmp_path))
        stack.enter_context(patch.object(commandline, "QSslSocket", qssl_socket))
        if app_version is not None:
            version_name = (
                "__version__" if server_type == "NUXEO" else "__alfresco_version__"
            )
            stack.enter_context(patch.object(commandline, version_name, app_version))
        runtime.manager = manager
        yield runtime


def _options(tmp_path, command="launch", **kwargs):
    values = {
        "command": command,
        "log_filename": "",
        "log_level_console": "INFO",
        "log_level_file": "DEBUG",
        "nxdrive_home": str(tmp_path / "cli-home"),
    }
    values.update(kwargs)
    return Namespace(**values)


@pytest.mark.parametrize(
    ("server_type", "executable"),
    (("ALFRESCO", "alfresco-drive"), ("UNKNOWN", "drive")),
)
def test_make_cli_parser_for_non_nuxeo_server_types(cli, server_type, executable):
    Options.server_type = server_type

    parser = cli.make_cli_parser(add_subparsers=False)

    assert parser.format_usage().startswith(f"usage: {executable} [command]")
    parsed = parser.parse_args([])
    assert not hasattr(parsed, "locale")


def test_alfresco_parser_exposes_only_common_commands(cli):
    Options.server_type = "ALFRESCO"
    parser = cli.make_cli_parser()

    parsed = parser.parse_args(["bind-server", "user", "https://server.example"])

    assert parsed.command == "bind_server"
    assert parsed.username == "user"
    assert parsed.server_url == "https://server.example"
    with pytest.raises(SystemExit):
        parser.parse_args(["direct-transfer", "--file", "document.txt"])


def test_parse_cli_filters_psn_and_stores_protocol_callback(cli):
    with patch.object(cli, "load_config", return_value={}):
        parsed = cli.parse_cli(["-psn_0_12345", "NXDRIVE://token/secret"])

    assert parsed.version is False
    assert Options.protocol_url == "NXDRIVE://token/secret"


def test_parse_cli_debug_installs_hooks_and_runs_server_debug_initializers(cli):
    debug_hook = MagicMock()
    fake_ipdb = ModuleType("ipdb")
    fake_ipdb.pm = MagicMock()
    configs = {
        "debuggable": SimpleNamespace(debug_init_hook=debug_hook),
        "plain": SimpleNamespace(debug_init_hook=None),
    }

    with patch.object(cli, "load_config", return_value={}), patch(
        "nxdrive.drive.server_type.all_configs", return_value=configs
    ), patch.dict(sys.modules, {"ipdb": fake_ipdb}), patch(
        "traceback.print_exception"
    ) as print_exception:
        parsed = cli.parse_cli(["--debug"])
        try:
            raise ValueError("boom")
        except ValueError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
            threading.excepthook(
                SimpleNamespace(
                    exc_type=type(exc),
                    exc_value=exc,
                    exc_traceback=exc.__traceback__,
                )
            )

    assert parsed.debug is True
    debug_hook.assert_called_once_with()
    assert print_exception.call_count == 2
    assert fake_ipdb.pm.call_count == 2


def test_load_local_config_rejects_scalar_include_process(cli, tmp_path):
    config = tmp_path / "config.ini"
    config.write_text(
        "[DEFAULT]\n"
        "env = TEST\n"
        "[TEST]\n"
        "include-process = python\n"
        "empty-value =\n",
        encoding="utf-8",
    )
    args = {}

    cli._load_local_config((tmp_path / "missing.ini", config), args)

    assert args == {"include_process": ()}
    assert Options.include_process == ()


@pytest.mark.parametrize("filename", ("", "explicit.log"))
def test_configure_logger_uses_expected_file(cli, tmp_path, filename):
    options = Namespace(
        nxdrive_home=tmp_path,
        log_filename=filename,
        log_level_file="ERROR",
        log_level_console="WARNING",
    )

    with patch.object(commandline, "configure") as configure:
        cli._configure_logger("console", options)

    log_folder = tmp_path / "logs"
    assert log_folder.is_dir()
    expected = Path(filename) if filename else log_folder / "nxdrive.log"
    configure.assert_called_once_with(
        log_filename=str(expected),
        file_level="ERROR",
        console_level="WARNING",
        command_name="console",
        force_configure=True,
    )


def test_uninstall_delegates_to_os_integration(cli):
    integration = MagicMock()
    with patch.object(
        commandline.AbstractOSIntegration, "get", return_value=integration
    ) as get_integration:
        assert cli.uninstall(None) is None

    get_integration.assert_called_once_with(None)
    integration.uninstall.assert_called_once_with()


def test_handle_returns_error_when_packaged_server_list_is_empty(cli, tmp_path):
    supported = tmp_path / "supported_server_list.txt"
    supported.write_text("# no enabled server\n\n", encoding="utf-8")

    with patch(
        "nxdrive.drive.utils.find_resource", return_value=supported
    ) as find_resource, patch.object(commandline.log, "error") as log_error:
        result = cli.handle([])

    assert result == 1
    find_resource.assert_called_once_with(
        "server_list", file="supported_server_list.txt"
    )
    log_error.assert_called_once_with(
        "No supported server type found in supported_server_list.txt"
    )


@pytest.mark.parametrize(("windows", "expected"), ((False, "9.8.7\n"), (True, "9.8.7")))
def test_handle_version_short_circuits_before_configuration(
    cli, tmp_path, capsys, windows, expected
):
    options = _options(tmp_path)
    with _handle_runtime(cli, tmp_path, options) as runtime, patch.object(
        commandline, "WINDOWS", windows
    ), patch.object(cli, "get_version", return_value="9.8.7"):
        result = cli.handle(["--version"])

    assert result == 0
    assert capsys.readouterr().out == expected
    runtime.setup_sentry.assert_called_once_with(commandline.__version__)
    runtime.parse_cli.assert_not_called()
    runtime.configure_logger.assert_not_called()
    runtime.get_manager.assert_not_called()
    assert not (tmp_path / ".nuxeo-drive").exists()


def test_handle_configures_nuxeo_and_dispatches_command(cli, tmp_path):
    options = _options(
        tmp_path,
        "clean_folder",
        local_folder=str(tmp_path / "sync-folder"),
    )
    ssl_socket = MagicMock()
    ssl_socket.supportsSsl.return_value = True

    with patch.object(cli, "clean_folder", return_value=27) as command, _handle_runtime(
        cli, tmp_path, options, qssl_socket=ssl_socket
    ) as runtime:
        result = cli.handle(["clean-folder", "--local-folder", options.local_folder])

    assert result == 27
    assert options.local_folder == (tmp_path / "sync-folder").resolve()
    assert options.nxdrive_home == (tmp_path / "cli-home").resolve()
    assert (tmp_path / ".nuxeo-drive").is_dir()
    runtime.set_app_server.assert_called_once_with("NUXEO")
    runtime.set_app_version.assert_called_once_with(commandline.__version__)
    runtime.setup_sentry.assert_called_once_with(commandline.__version__)
    runtime.apply_restrictions.assert_called_once_with("NUXEO")
    runtime.refresh_branding.assert_called_once_with("NUXEO")
    assert runtime.configure_logger.call_count == 2
    early_call, command_call = runtime.configure_logger.call_args_list
    assert early_call.args[0] == "early"
    assert early_call.args[1].nxdrive_home == tmp_path / ".nuxeo-drive"
    assert command_call == call("clean_folder", options)
    runtime.install_faulthandler.assert_called_once_with()
    runtime.get_manager.assert_called_once_with()
    assert cli.manager is runtime.manager
    ssl_socket.supportsSsl.assert_called_once_with()
    command.assert_called_once_with(options)
    assert Options.update_site_url == "https://updates.example/nuxeo"


def test_handle_alfresco_alpha_uninstall_skips_manager(cli, tmp_path):
    options = _options(tmp_path, "uninstall")
    alpha_version = "1.0.0.dev1"

    with patch.object(cli, "uninstall", return_value=0) as uninstall, _handle_runtime(
        cli,
        tmp_path,
        options,
        server_type="ALFRESCO",
        app_version=alpha_version,
    ) as runtime:
        result = cli.handle(["uninstall"])

    assert result == 0
    assert (tmp_path / ".alfresco-drive").is_dir()
    runtime.set_app_server.assert_called_once_with("ALFRESCO")
    runtime.set_app_version.assert_called_once_with(alpha_version)
    runtime.set_log_level_file.assert_called_once_with("DEBUG")
    runtime.setup_sentry.assert_called_once_with(alpha_version)
    runtime.apply_restrictions.assert_called_once_with("ALFRESCO")
    runtime.refresh_branding.assert_called_once_with("ALFRESCO")
    runtime.install_faulthandler.assert_not_called()
    runtime.get_manager.assert_not_called()
    uninstall.assert_called_once_with(options)
    assert Options.is_alpha is True
    assert Options.update_site_url == "https://updates.example/alfresco"


def test_handle_rejects_unknown_command(cli, tmp_path):
    options = _options(tmp_path, "not_implemented")

    with _handle_runtime(cli, tmp_path, options) as runtime, pytest.raises(
        RuntimeError, match="No handler implemented for command not_implemented"
    ):
        cli.handle(["not-implemented"])

    assert runtime.configure_logger.call_count == 1
    runtime.install_faulthandler.assert_not_called()
    runtime.get_manager.assert_not_called()


def test_handle_disables_ssl_validation_when_ssl_is_unavailable(cli, tmp_path):
    options = _options(tmp_path)
    ssl_socket = MagicMock()
    ssl_socket.supportsSsl.return_value = False
    Options.is_frozen = False
    Options.ssl_no_verify = False

    with patch.object(cli, "launch", return_value=4) as launch, _handle_runtime(
        cli, tmp_path, options, qssl_socket=ssl_socket
    ):
        result = cli.handle([])

    assert result == 4
    assert options.cert_file is None
    assert options.cert_key_file is None
    assert options.ssl_no_verify is True
    launch.assert_called_once_with(options)


def test_handle_rejects_frozen_build_without_ssl_support(cli, tmp_path):
    options = _options(tmp_path)
    ssl_socket = MagicMock()
    ssl_socket.supportsSsl.return_value = False
    Options.is_frozen = True
    Options.ssl_no_verify = False

    with _handle_runtime(
        cli, tmp_path, options, qssl_socket=ssl_socket
    ) as runtime, patch.object(commandline, "LINUX", False), pytest.raises(
        RuntimeError, match="No SSL support"
    ):
        cli.handle([])

    runtime.install_faulthandler.assert_not_called()
    runtime.get_manager.assert_not_called()


@pytest.mark.parametrize(
    ("platform", "supported", "chosen", "expected"),
    (
        ("darwin", ["NUXEO", "ALFRESCO"], "ALFRESCO", "ALFRESCO"),
        ("linux", [], None, "NUXEO"),
    ),
)
def test_pick_server_type_configures_selection(
    cli, tmp_path, platform, supported, chosen, expected
):
    picker_name = (
        "_pick_server_type_macos" if platform == "darwin" else "_pick_server_type_qt"
    )
    with patch.object(
        cli, "_load_supported_server_keys", return_value=supported
    ), patch.object(cli, picker_name, return_value=chosen) as picker, patch.object(
        sys, "platform", platform
    ), patch.object(
        Path, "home", return_value=tmp_path
    ), patch(
        "nxdrive.drive.server_type.get_default_key", return_value="NUXEO"
    ), patch(
        "nxdrive.drive.feature.apply_server_type_restrictions"
    ) as apply_restrictions, patch(
        "nxdrive.drive.constants.refresh_branding"
    ) as refresh_branding:
        cli._pick_server_type()

    expected_choices = supported or ["NUXEO"]
    picker.assert_called_once_with(expected_choices)
    assert Options.server_type == expected
    assert Options.nxdrive_home == tmp_path / f".{expected.lower()}-drive"
    assert Options.nxdrive_home.is_dir()
    apply_restrictions.assert_called_once_with(expected)
    refresh_branding.assert_called_once_with(expected)


def test_pick_server_type_macos_returns_none_without_choices(cli):
    with patch("subprocess.run") as run:
        assert cli._pick_server_type_macos([]) is None

    run.assert_not_called()


def test_pick_server_type_macos_runs_osascript_and_returns_valid_choice(cli):
    completed = SimpleNamespace(stdout="ALFRESCO\n")
    with patch("subprocess.run", return_value=completed) as run:
        result = cli._pick_server_type_macos(["NUXEO", "ALFRESCO"])

    assert result == "ALFRESCO"
    args, kwargs = run.call_args
    assert args[0][0:2] == ["/usr/bin/osascript", "-e"]
    script = args[0][2]
    assert 'choose from list {"NUXEO", "ALFRESCO"}' in script
    assert 'default items {"NUXEO"}' in script
    assert 'OK button name "Apply"' in script
    assert kwargs == {"capture_output": True, "text": True, "timeout": 600}


@pytest.mark.parametrize("stdout", ("", "UNSUPPORTED\n"))
def test_pick_server_type_macos_rejects_empty_or_unknown_output(cli, stdout):
    with patch("subprocess.run", return_value=SimpleNamespace(stdout=stdout)):
        assert cli._pick_server_type_macos(["NUXEO", "ALFRESCO"]) is None


def test_pick_server_type_macos_handles_process_error(cli):
    with patch(
        "subprocess.run", side_effect=OSError("osascript unavailable")
    ), patch.object(commandline.log, "exception") as log_exception:
        assert cli._pick_server_type_macos(["NUXEO"]) is None

    log_exception.assert_called_once_with(
        "osascript server-type picker failed to launch"
    )


@pytest.mark.parametrize(
    ("current_data", "expected"), (("ALFRESCO", "ALFRESCO"), (None, None))
)
def test_pick_server_type_qt_builds_dialog_without_showing_real_ui(
    cli, current_data, expected
):
    from nxdrive.drive.qt import constants as qt

    with ExitStack() as stack:
        qapplication = stack.enter_context(
            patch("nxdrive.drive.qt.imports.QApplication")
        )
        combo_class = stack.enter_context(patch("nxdrive.drive.qt.imports.QComboBox"))
        dialog_class = stack.enter_context(patch("nxdrive.drive.qt.imports.QDialog"))
        buttons_class = stack.enter_context(
            patch("nxdrive.drive.qt.imports.QDialogButtonBox")
        )
        row_class = stack.enter_context(patch("nxdrive.drive.qt.imports.QHBoxLayout"))
        label_class = stack.enter_context(patch("nxdrive.drive.qt.imports.QLabel"))
        layout_class = stack.enter_context(
            patch("nxdrive.drive.qt.imports.QVBoxLayout")
        )
        qapplication.instance.return_value = None
        dialog = dialog_class.return_value
        buttons = buttons_class.return_value
        combo = combo_class.return_value
        combo.currentData.return_value = current_data

        result = cli._pick_server_type_qt(["NUXEO", "ALFRESCO"])

    assert result == expected
    qapplication.instance.assert_called_once_with()
    qapplication.assert_called_once_with([])
    dialog.setWindowTitle.assert_called_once_with("Drive — First Run Setup")
    combo.addItem.assert_has_calls(
        [call("NUXEO", "NUXEO"), call("ALFRESCO", "ALFRESCO")]
    )
    row_class.return_value.addWidget.assert_has_calls(
        [call(label_class.return_value), call(combo)]
    )
    layout_class.return_value.addLayout.assert_called_once_with(row_class.return_value)
    buttons.setStandardButtons.assert_called_once_with(qt.Apply)
    buttons.clicked.connect.assert_called_once_with(dialog.accept)
    dialog.setLayout.assert_called_once_with(layout_class.return_value)
    dialog.resize.assert_called_once_with(380, 120)
    dialog.exec.assert_called_once_with()


def test_pick_server_type_qt_falls_back_after_qt_error(cli):
    with patch("nxdrive.drive.qt.imports.QApplication") as qapplication, patch.object(
        commandline.log, "debug"
    ) as log_debug:
        qapplication.instance.side_effect = RuntimeError("Qt unavailable")
        assert cli._pick_server_type_qt(["NUXEO"]) is None

    log_debug.assert_called_once_with(
        "Qt server-type picker failed; falling back to default", exc_info=True
    )


def test_get_manager_uses_current_home(cli, tmp_path):
    manager = MagicMock()
    with patch("nxdrive.drive.manager.Manager", return_value=manager) as manager_class:
        assert cli.get_manager() is manager

    manager_class.assert_called_once_with(tmp_path / "options-home")


def test_get_application_console(cli):
    cli.manager = MagicMock()
    application = MagicMock()
    with patch(
        "nxdrive.drive.console.ConsoleApplication", return_value=application
    ) as application_class:
        assert cli._get_application(console=True) is application

    application_class.assert_called_once_with(cli.manager)


def test_get_application_gui_registers_qml_types(cli):
    cli.manager = MagicMock()
    application = MagicMock()
    with patch(
        "nxdrive.drive.gui.application.Application", return_value=application
    ) as application_class, patch(
        "nxdrive.drive.gui.custom_window.CustomWindow"
    ) as custom_window, patch(
        "nxdrive.drive.gui.systray.SystrayWindow"
    ) as systray_window, patch(
        "nxdrive.drive.qt.imports.qmlRegisterType"
    ) as register_type:
        assert cli._get_application() is application

    register_type.assert_has_calls(
        [
            call(systray_window, "SystrayWindow", 1, 0, "SystrayWindow"),
            call(custom_window, "CustomWindow", 1, 0, "CustomWindow"),
        ]
    )
    application_class.assert_called_once_with(cli.manager)


def test_launch_forwards_protocol_to_existing_instance(cli, tmp_path):
    cli.manager = SimpleNamespace(home=tmp_path)
    lock = MagicMock()
    lock.lock.return_value = 314
    Options.protocol_url = "nxdrive://edit/document"

    with patch(
        "nxdrive.drive.utils.PidLockFile", return_value=lock
    ) as lock_class, patch.object(
        commandline, "force_encode", return_value=b"encoded"
    ) as encode, patch.object(
        cli, "_send_to_running_instance", return_value=True
    ) as send:
        assert cli.launch(None) == 0

    lock_class.assert_called_once_with(tmp_path, "qt")
    encode.assert_called_once_with("nxdrive://edit/document")
    send.assert_called_once_with(b"encoded", 314)
    lock.refresh_lock.assert_not_called()
    lock.unlock.assert_not_called()


def test_launch_retries_failed_protocol_delivery(cli, tmp_path):
    cli.manager = SimpleNamespace(home=tmp_path)
    lock = MagicMock()
    lock.lock.return_value = 314
    Options.protocol_url = "nxdrive://edit/document"
    commandline.RETRY = 0

    with patch("nxdrive.drive.utils.PidLockFile", return_value=lock), patch.object(
        cli, "_send_to_running_instance", return_value=False
    ), patch.object(cli, "launch") as recursive_launch:
        assert CliHandler.launch(cli, None, console=True) == 0

    assert commandline.RETRY == 1
    lock.refresh_lock.assert_called_once_with()
    recursive_launch.assert_called_once_with(None, console=True)


def test_launch_stops_retrying_at_limit(cli, tmp_path):
    cli.manager = SimpleNamespace(home=tmp_path)
    lock = MagicMock()
    lock.lock.return_value = 314
    Options.protocol_url = "nxdrive://edit/document"
    commandline.RETRY = commandline.MAX_RETRIES

    with patch("nxdrive.drive.utils.PidLockFile", return_value=lock), patch.object(
        cli, "_send_to_running_instance", return_value=False
    ), patch.object(cli, "launch") as recursive_launch:
        assert CliHandler.launch(cli, None) == 0

    assert commandline.RETRY == 0
    lock.refresh_lock.assert_not_called()
    recursive_launch.assert_not_called()


def test_launch_runs_application_with_linux_software_rendering(cli, tmp_path):
    cli.manager = SimpleNamespace(home=tmp_path)
    lock = MagicMock()
    lock.lock.return_value = 0
    app = MagicMock()
    app.exec.return_value = 19

    with patch("nxdrive.drive.utils.PidLockFile", return_value=lock), patch.object(
        commandline, "HealthCheck"
    ) as health_check, patch.object(
        cli, "_get_application", return_value=app
    ) as get_application, patch.object(
        commandline, "LINUX", True
    ), patch.object(
        commandline, "WINDOWS", False
    ):
        result = cli.launch(None, console=True)

    assert result == 19
    assert os.environ["QT_QUICK_BACKEND"] == "software"
    assert os.environ["QT_XCB_GL_INTEGRATION"] == "none"
    health_check.assert_called_once_with()
    get_application.assert_called_once_with(console=True)
    app.exec.assert_called_once_with()
    lock.unlock.assert_called_once_with()


@pytest.mark.parametrize("has_clipboard", (True, False))
def test_launch_handles_windows_clipboard(cli, tmp_path, has_clipboard):
    class FakeApplication:
        pass

    cli.manager = SimpleNamespace(home=tmp_path)
    lock = MagicMock()
    lock.lock.return_value = 0
    app = FakeApplication()
    app.exec = MagicMock(return_value=0)
    clipboard = MagicMock() if has_clipboard else None
    app.clipboard = MagicMock(return_value=clipboard)

    with patch("nxdrive.drive.utils.PidLockFile", return_value=lock), patch.object(
        commandline, "HealthCheck"
    ), patch.object(cli, "_get_application", return_value=app), patch(
        "nxdrive.drive.gui.application.Application", FakeApplication
    ), patch.object(
        commandline, "LINUX", False
    ), patch.object(
        commandline, "WINDOWS", True
    ), patch.object(
        commandline.log, "error"
    ) as log_error:
        assert cli.launch(None) == 0

    app.clipboard.assert_called_once_with()
    if clipboard:
        clipboard.blockSignals.assert_called_once_with(True)
        log_error.assert_not_called()
    else:
        log_error.assert_called_once_with("Cannot get clipboard from application")
    lock.unlock.assert_called_once_with()


def test_send_to_running_instance_reports_connection_failure(cli):
    client = MagicMock()
    client.waitForConnected.return_value = False
    client.errorString.return_value = "not listening"

    with patch("nxdrive.drive.qt.imports.QLocalSocket", return_value=client), patch(
        "nxdrive.drive.qt.imports.QByteArray"
    ) as byte_array:
        result = cli._send_to_running_instance(b"payload", 42)

    assert result is False
    client.connectToServer.assert_called_once_with("org.nuxeo.drive.protocol.42")
    client.errorString.assert_called_once_with()
    byte_array.assert_not_called()
    client.write.assert_not_called()


def test_send_to_running_instance_writes_and_disconnects(cli):
    from nxdrive.drive.qt import constants as qt

    client = MagicMock()
    client.waitForConnected.return_value = True
    client.state.return_value = qt.ConnectedState
    encoded = MagicMock(name="qbytearray")

    with patch("nxdrive.drive.qt.imports.QLocalSocket", return_value=client), patch(
        "nxdrive.drive.qt.imports.QByteArray", return_value=encoded
    ) as byte_array:
        result = cli._send_to_running_instance(b"payload", 43)

    assert result is True
    byte_array.assert_called_once_with(b"payload")
    client.write.assert_called_once_with(encoded)
    client.waitForBytesWritten.assert_called_once_with()
    client.disconnectFromServer.assert_called_once_with()
    client.waitForDisconnected.assert_called_once_with()


@pytest.mark.parametrize("local_folder", (None, ""))
def test_clean_folder_requires_folder(cli, capsys, local_folder):
    with patch("nxdrive.drive.client.local.LocalClient") as local_client:
        result = cli.clean_folder(Namespace(local_folder=local_folder))

    assert result == 1
    assert capsys.readouterr().out == "A folder must be specified\n"
    local_client.assert_not_called()


def test_clean_folder_removes_extended_attributes(cli, tmp_path):
    local_folder = tmp_path / "sync"
    client = MagicMock()
    with patch(
        "nxdrive.drive.client.local.LocalClient", return_value=client
    ) as local_client:
        result = cli.clean_folder(Namespace(local_folder=local_folder))

    assert result == 0
    local_client.assert_called_once_with(local_folder)
    client.clean_xattr_root.assert_called_once_with()


def test_console_enables_pydev_and_launches_console_application(cli):
    pydev = ModuleType("pydev")
    pydev.pydevd = MagicMock()
    options = Namespace(debug_pydev=True)

    with patch.dict(sys.modules, {"pydev": pydev}), patch.object(
        cli, "launch", return_value=8
    ) as launch:
        result = cli.console(options)

    assert result == 8
    pydev.pydevd.settrace.assert_called_once_with()
    launch.assert_called_once_with(options, console=True)


@pytest.mark.parametrize(
    ("handler_name", "manager_method"),
    (
        ("ctx_access_online", "ctx_access_online"),
        ("ctx_copy_share_link", "ctx_copy_share_link"),
        ("ctx_edit_metadata", "ctx_edit_metadata"),
    ),
)
def test_context_commands_normalize_file_path(cli, handler_name, manager_method):
    cli.manager = MagicMock()
    normalized = Path("/normalized/document.txt")
    options = Namespace(file="~/document.txt")

    with patch.object(
        commandline, "normalized_path", return_value=normalized
    ) as normalize:
        result = getattr(cli, handler_name)(options)

    assert result is None
    normalize.assert_called_once_with("~/document.txt")
    getattr(cli.manager, manager_method).assert_called_once_with(normalized)


def test_direct_transfer_sets_protocol_url_and_launches(cli):
    options = Namespace(file="/folder/document.txt")
    with patch.object(cli, "launch", return_value=99) as launch:
        result = cli.ctx_direct_transfer(options)

    assert result == 0
    assert Options.protocol_url == "nxdrive://direct-transfer//folder/document.txt"
    launch.assert_called_once_with(options)


def test_download_edit_launches_application(cli):
    options = Namespace(file="document.txt")
    with patch.object(cli, "launch", return_value=99) as launch:
        result = cli.download_edit(options)

    assert result == 0
    launch.assert_called_once_with(options)


@pytest.mark.parametrize(
    (
        "password",
        "local_folder",
        "server_url",
        "nuxeo_url",
        "expected_password",
        "check_credentials",
    ),
    (
        (None, None, None, "https://legacy.example", "", False),
        (
            "secret",
            "/sync",
            "https://server.example",
            "https://legacy.example",
            "secret",
            True,
        ),
    ),
)
def test_bind_server_passes_credentials_and_compatible_url(
    cli,
    password,
    local_folder,
    server_url,
    nuxeo_url,
    expected_password,
    check_credentials,
):
    cli.manager = MagicMock()
    options = Namespace(
        password=password,
        local_folder=local_folder,
        server_url=server_url,
        nuxeo_url=nuxeo_url,
        username="alice",
    )

    result = cli.bind_server(options)

    assert result == 0
    expected_folder = local_folder or commandline.DEFAULT_LOCAL_FOLDER
    assert options.local_folder == expected_folder
    cli.manager.bind_server.assert_called_once_with(
        expected_folder,
        server_url or nuxeo_url,
        "alice",
        password=expected_password,
        start_engine=False,
        check_credentials=check_credentials,
    )


def test_unbind_server_removes_matching_engine(cli):
    matching = SimpleNamespace(local_folder="/sync")
    cli.manager = MagicMock()
    cli.manager.engines = {
        "other": SimpleNamespace(local_folder="/other"),
        "uid": matching,
    }

    assert cli.unbind_server(Namespace(local_folder="/sync")) == 0

    cli.manager.unbind_engine.assert_called_once_with("uid")


def test_unbind_server_reports_missing_engine(cli):
    cli.manager = MagicMock()
    cli.manager.engines = {"uid": SimpleNamespace(local_folder="/other")}

    with patch.object(commandline.log, "warning") as warning:
        result = cli.unbind_server(Namespace(local_folder="/sync"))

    assert result == 1
    cli.manager.unbind_engine.assert_not_called()
    warning.assert_called_once_with("No engine registered for local folder '/sync'")


@pytest.mark.parametrize(
    ("handler_name", "remote_method"),
    (("bind_root", "register_as_root"), ("unbind_root", "unregister_as_root")),
)
def test_root_command_uses_matching_engine(cli, handler_name, remote_method):
    engine = SimpleNamespace(local_folder="/sync", remote=MagicMock())
    cli.manager = MagicMock()
    cli.manager.engines = {"uid": engine}
    options = Namespace(local_folder="/sync", remote_root="remote-id")

    result = getattr(cli, handler_name)(options)

    assert result == 0
    getattr(engine.remote, remote_method).assert_called_once_with("remote-id")


@pytest.mark.parametrize("handler_name", ("bind_root", "unbind_root"))
def test_root_command_reports_missing_engine(cli, handler_name):
    cli.manager = MagicMock()
    cli.manager.engines = {"uid": SimpleNamespace(local_folder="/other")}
    options = Namespace(local_folder="/sync", remote_root="remote-id")

    with patch.object(commandline.log, "warning") as warning:
        result = getattr(cli, handler_name)(options)

    assert result == 1
    warning.assert_called_once_with("No engine registered for local folder '/sync'")


def test_install_faulthandler_writes_timestamped_log(cli, tmp_path):
    logs = tmp_path / "options-home" / "logs"
    logs.mkdir()
    timestamp = real_datetime(2026, 8, 5, 12, 30, 45)

    with patch.object(commandline, "datetime") as datetime, patch.object(
        commandline.faulthandler, "enable"
    ) as enable:
        datetime.now.return_value = timestamp
        cli._install_faulthandler()

    crash_log = logs / "segfault.log"
    assert crash_log.read_text(encoding="utf-8") == f"\n\n\n>>> {timestamp}\n"
    enabled_file = enable.call_args.kwargs["file"]
    assert Path(enabled_file.name) == crash_log
    assert enabled_file.closed


def test_health_check_default_folder_is_resolved_under_mocked_home(tmp_path):
    folder = tmp_path / "resolved-home"
    with patch.object(Path, "home", return_value=tmp_path), patch(
        "nxdrive.drive.options._get_nxdrive_home", return_value=folder
    ) as get_home:
        health = HealthCheck()

    get_home.assert_called_once_with(tmp_path)
    assert health.crash_file == folder / "crash.state"
    assert folder.is_dir()


def test_health_check_creates_and_cleans_crash_marker(tmp_path):
    folder = tmp_path / "health"
    health = HealthCheck(folder)

    with health as entered:
        assert entered is health
        assert health.crash_file.is_file()
        assert State.has_crashed is False

    assert not health.crash_file.exists()


def test_health_check_records_previous_crash_and_cleans_marker(tmp_path):
    folder = tmp_path / "health"
    health = HealthCheck(folder)
    health.crash_file.write_text("previous traceback", encoding="utf-8")

    with health:
        assert State.has_crashed is True
        assert State.crash_details == "previous traceback"

    assert not health.crash_file.exists()


def test_health_check_tolerates_marker_read_error(tmp_path):
    health = HealthCheck(tmp_path / "health")
    health.crash_file = MagicMock()
    health.crash_file.read_text.side_effect = OSError("permission denied")

    with patch.object(commandline.log, "exception") as log_exception:
        assert health.__enter__() is health

    log_exception.assert_called_once_with("Cannot get or create the crash file")


def test_health_check_tolerates_marker_cleanup_error(tmp_path):
    health = HealthCheck(tmp_path / "health")
    health.crash_file = MagicMock()
    health.crash_file.unlink.side_effect = OSError("permission denied")

    with patch.object(commandline.log, "exception") as log_exception:
        assert health.__exit__(None, None, None) is None

    health.crash_file.unlink.assert_called_once_with(missing_ok=True)
    log_exception.assert_called_once_with("Cannot clean-up the crash file")
