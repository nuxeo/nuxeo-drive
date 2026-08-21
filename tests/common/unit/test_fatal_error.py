import platform
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive import fatal_error
from nxdrive.drive.constants import MAC
from nxdrive.drive.options import MetaOptions, Options
from nxdrive.drive.state import State

from ...markers import linux_only, mac_only, windows_only


@pytest.fixture(autouse=True)
def restore_application_state():
    """Prevent crash-reporting tests from leaking process-wide state."""
    saved_state = vars(State).copy()
    saved_options = deepcopy(MetaOptions.options)
    yield
    vars(State).clear()
    vars(State).update(saved_state)
    MetaOptions.options = saved_options


@pytest.fixture()
def fatal_qt_env(monkeypatch):
    """Replace every dialog dependency so fatal_error_qt never creates UI."""
    from nxdrive.drive import osi, report, server_type, translator, utils
    from nxdrive.drive.qt import imports as qt_imports

    app = MagicMock(name="application")
    dialog = MagicMock(name="dialog")
    layout = MagicMock(name="layout")
    buttons = MagicMock(name="buttons")
    update_button = MagicMock(name="update_button")
    send_button = MagicMock(name="send_button")
    copy_button = MagicMock(name="copy_button")
    buttons.addButton.side_effect = [update_button, send_button, copy_button]

    constructors = {
        "QApplication": MagicMock(return_value=app),
        "QDesktopServices": MagicMock(),
        "QDialog": MagicMock(return_value=dialog),
        "QDialogButtonBox": MagicMock(return_value=buttons),
        "QIcon": MagicMock(),
        "QLabel": MagicMock(),
        "QTextEdit": MagicMock(),
        "QUrl": MagicMock(),
        "QVBoxLayout": MagicMock(return_value=layout),
    }
    for name, replacement in constructors.items():
        monkeypatch.setattr(qt_imports, name, replacement)

    translator_type = MagicMock(name="Translator")
    translator_type.get.side_effect = lambda key, values=None: key
    monkeypatch.setattr(translator, "Translator", translator_type)
    monkeypatch.setattr(utils, "find_icon", MagicMock(return_value=Path("icon.svg")))
    monkeypatch.setattr(utils, "find_resource", MagicMock(return_value=Path("i18n")))

    export_logs = MagicMock(return_value=[])
    monkeypatch.setattr(report.Report, "export_logs", export_logs)
    osi_instance = MagicMock(name="osi")
    osi_type = MagicMock(name="AbstractOSIntegration")
    osi_type.get.return_value = osi_instance
    monkeypatch.setattr(osi, "AbstractOSIntegration", osi_type)
    monkeypatch.setattr(sys, "argv", ["drive"])

    return SimpleNamespace(
        app=app,
        buttons=buttons,
        copy_button=copy_button,
        desktop_services=constructors["QDesktopServices"],
        dialog=dialog,
        export_logs=export_logs,
        osi=osi_instance,
        osi_type=osi_type,
        qurl=constructors["QUrl"],
        send_button=send_button,
        server_type=server_type,
        update_button=update_button,
    )


def test_check_os_version(monkeypatch):
    """Check the OS version compatibility for Nuxeo Drive"""
    assert fatal_error.check_os_version()

    if MAC:
        # Test for lower version of MacOS. It will pop-up a Fatal error screen
        def mac_ver():
            return ["10.2.1"]

        monkeypatch.setattr(platform, "mac_ver", mac_ver)

        fatal_error.fatal_error_mac = Mock()
        assert not fatal_error.check_os_version()


@patch("nxdrive.drive.fatal_error.fatal_error_qt")
@patch("traceback.format_exception")
@patch("sys.exc_info")
def test_show_critical_error(mock_exc_info, mock_traceback, mock_fatal_error_qt):
    mock_exc_info.return_value = "dummy_exc_info"
    mock_traceback.return_value = ["dummy_exception1", "dummy_exception2"]
    assert fatal_error.show_critical_error() is None
    mock_fatal_error_qt.assert_called_once_with(
        "dummy_exception1dummy_exception2", exc_info="dummy_exc_info"
    )


@windows_only
@patch("nxdrive.drive.fatal_error.fatal_error_win")
@patch("nxdrive.drive.fatal_error.fatal_error_qt")
@patch("traceback.format_exception")
@patch("sys.exc_info")
def test_show_critical_error_windows(
    mock_exc_info, mock_traceback, mock_fatal_error_qt, mock_fatal_error_win
):
    mock_exc_info.return_value = "dummy_exc_info"
    mock_traceback.return_value = ["dummy_exception1", "dummy_exception2"]
    mock_fatal_error_qt.side_effect = Exception("Dummy Windows Exception")
    assert fatal_error.show_critical_error() is None


@mac_only
@patch("nxdrive.drive.fatal_error.fatal_error_mac")
@patch("nxdrive.drive.fatal_error.fatal_error_qt")
@patch("traceback.format_exception")
@patch("sys.exc_info")
def test_show_critical_error_mac(
    mock_exc_info, mock_traceback, mock_fatal_error_qt, mock_fatal_error_mac
):
    mock_exc_info.return_value = "dummy_exc_info"
    mock_traceback.return_value = ["dummy_exception1", "dummy_exception2"]
    mock_fatal_error_qt.side_effect = Exception("Dummy MacOS Exception")
    assert fatal_error.show_critical_error() is None


@linux_only
@patch("nxdrive.drive.fatal_error.fatal_error_qt")
@patch("traceback.format_exception")
@patch("sys.exc_info")
def test_show_critical_error_linux(mock_exc_info, mock_traceback, mock_fatal_error_qt):
    mock_exc_info.return_value = "dummy_exc_info"
    mock_traceback.return_value = ["dummy_exception1", "dummy_exception2"]
    mock_fatal_error_qt.side_effect = Exception("Dummy Linux Exception")
    assert fatal_error.show_critical_error() is None


def test_accepted_app_names_prefers_registered_shared_configs(monkeypatch):
    from nxdrive.drive import server_type

    configs = {
        "FIRST": SimpleNamespace(app_name="First Drive"),
        "EMPTY": SimpleNamespace(app_name=""),
        "SECOND": SimpleNamespace(app_name="Second Drive"),
    }
    monkeypatch.setattr(server_type, "all_configs", Mock(return_value=configs))

    assert fatal_error._accepted_app_names() == {
        fatal_error.APP_NAME,
        "First Drive",
        "Second Drive",
    }


def test_accepted_app_names_reads_supported_server_file(monkeypatch, tmp_path):
    from nxdrive.drive import server_type

    package_root = tmp_path / "nxdrive"
    source = package_root / "drive" / "fatal_error.py"
    source.parent.mkdir(parents=True)
    source.touch()
    (package_root / "supported_server_list.txt").write_text(
        "\n# supported products\nnuxeo\nalfresco_cloud\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(server_type, "all_configs", Mock(return_value={}))
    monkeypatch.setattr(fatal_error, "__file__", str(source))

    assert fatal_error._accepted_app_names() == {
        fatal_error.APP_NAME,
        "Nuxeo Drive",
        "Alfresco Cloud Drive",
    }


def test_accepted_app_names_discovers_packages_when_file_is_missing(
    monkeypatch, tmp_path
):
    from nxdrive.drive import server_type

    package_root = tmp_path / "nxdrive"
    source = package_root / "drive" / "fatal_error.py"
    source.parent.mkdir(parents=True)
    source.touch()

    valid = package_root / "custom_server"
    valid.mkdir()
    (valid / "__init__.py").touch()
    (valid / "registration.py").touch()

    incomplete = package_root / "incomplete"
    incomplete.mkdir()
    (incomplete / "__init__.py").touch()
    (package_root / "plain_file").touch()

    monkeypatch.setattr(server_type, "all_configs", Mock(return_value={}))
    monkeypatch.setattr(fatal_error, "__file__", str(source))

    assert fatal_error._accepted_app_names() == {
        fatal_error.APP_NAME,
        "Custom Server Drive",
    }


def test_fatal_error_qt_copies_cli_exception_and_logs(fatal_qt_env, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["drive", "--safe", "value"])
    fatal_qt_env.export_logs.return_value = [b"log line", b"invalid: \xff"]

    fatal_error.fatal_error_qt("  failure details  ")

    fatal_qt_env.dialog.show.assert_called_once_with()
    fatal_qt_env.app.exec.assert_called_once_with()
    fatal_qt_env.export_logs.assert_called_once_with(20)

    copy = fatal_qt_env.copy_button.clicked.connect.call_args.args[0]
    copy()
    copied = fatal_qt_env.osi.cb_set.call_args.args[0]
    assert "FATAL_ERROR_CLI_ARGS\n```\n--safe\nvalue\n```" in copied
    assert "FATAL_ERROR_EXCEPTION\n```\nfailure details\n```" in copied
    assert "FATAL_ERROR_LOGS\n```\nlog line\ninvalid: �\n```" in copied
    fatal_qt_env.copy_button.setText.assert_called_once_with(
        "FATAL_ERROR_DETAILS_COPIED"
    )


@pytest.mark.parametrize(
    "windows, mac, filename",
    [
        (True, False, "shared.exe"),
        (False, True, "shared.dmg"),
        (False, False, "shared.AppImage"),
    ],
)
def test_fatal_error_qt_update_button_uses_platform_download(
    fatal_qt_env, monkeypatch, windows, mac, filename
):
    config = SimpleNamespace(
        download_exe="shared.exe",
        download_dmg="shared.dmg",
        download_appimage="shared.AppImage",
    )
    get_config = Mock(return_value=config)
    monkeypatch.setattr(fatal_qt_env.server_type, "get", get_config)
    monkeypatch.setattr(fatal_error, "WINDOWS", windows)
    monkeypatch.setattr(fatal_error, "MAC", mac)
    Options.server_type = "SHARED"
    Options.update_site_url = "https://updates.example.test/client"

    fatal_error.fatal_error_qt("failure")
    open_update_site = fatal_qt_env.update_button.clicked.connect.call_args.args[0]
    open_update_site()

    get_config.assert_called_once_with("SHARED")
    fatal_qt_env.qurl.assert_called_once_with(
        f"https://updates.example.test/client/{filename}"
    )
    fatal_qt_env.desktop_services.openUrl.assert_called_once_with(
        fatal_qt_env.qurl.return_value
    )


def test_fatal_error_qt_sends_error_to_hyland(fatal_qt_env):
    exc = RuntimeError("failure")
    exc_info = (RuntimeError, exc, None)
    fatal_qt_env.export_logs.return_value = [b"first log", b"second log"]

    with patch(
        "nxdrive.drive.tracing.capture_fatal_error", return_value=True
    ) as capture_fatal_error:
        fatal_error.fatal_error_qt("formatted traceback", exc_info=exc_info)
        send_error = fatal_qt_env.send_button.clicked.connect.call_args.args[0]
        send_error()

    capture_fatal_error.assert_called_once_with(
        exc_info, "formatted traceback", ["first log", "second log"]
    )
    fatal_qt_env.send_button.setEnabled.assert_called_once_with(False)
    fatal_qt_env.send_button.setText.assert_called_once_with("FATAL_ERROR_SENT")


def test_fatal_error_qt_reenables_send_button_on_failure(fatal_qt_env):
    with patch("nxdrive.drive.tracing.capture_fatal_error", return_value=False):
        fatal_error.fatal_error_qt("formatted traceback")
        send_error = fatal_qt_env.send_button.clicked.connect.call_args.args[0]
        send_error()

    assert fatal_qt_env.send_button.setEnabled.call_args_list == [
        ((False,), {}),
        ((True,), {}),
    ]
    fatal_qt_env.send_button.setText.assert_called_once_with("FATAL_ERROR_SEND_FAILED")


def test_fatal_error_qt_suppresses_optional_sections(fatal_qt_env):
    fatal_qt_env.export_logs.side_effect = RuntimeError("logs unavailable")
    fatal_qt_env.osi_type.get.side_effect = RuntimeError("clipboard unavailable")
    fatal_qt_env.buttons.addButton.side_effect = [None, None]

    fatal_error.fatal_error_qt("failure")

    fatal_qt_env.dialog.show.assert_called_once_with()
    fatal_qt_env.update_button.setToolTip.assert_not_called()


def test_check_executable_path_accepts_registered_bundle(monkeypatch):
    bundle = Path("/Applications/Shared Drive.app")
    monkeypatch.setattr(fatal_error, "MAC", True)
    monkeypatch.setattr(fatal_error, "_accepted_app_paths", Mock(return_value={bundle}))
    monkeypatch.setattr(fatal_error, "_is_dmg_mount_path", Mock(return_value=False))
    monkeypatch.setattr(sys, "executable", f"{bundle}/Contents/MacOS/drive")
    Options.is_frozen = True

    assert fatal_error.check_executable_path() is True


def test_is_dmg_mount_path_accepts_standard_dmg_layout(monkeypatch):
    monkeypatch.setattr(
        fatal_error,
        "_accepted_app_names",
        Mock(return_value={"Drive", "Nuxeo Drive"}),
    )

    assert fatal_error._is_dmg_mount_path(Path("/Volumes/Nuxeo Drive/Nuxeo Drive.app"))
    assert fatal_error._is_dmg_mount_path(Path("/Volumes/Drive/Drive.app"))
    assert not fatal_error._is_dmg_mount_path(
        Path("/Users/test/Downloads/Nuxeo Drive.app")
    )
    assert not fatal_error._is_dmg_mount_path(
        Path("/Volumes/Nuxeo Drive/Wrong Name.app")
    )


def test_check_executable_path_accepts_dmg_mount(monkeypatch):
    bundle = Path("/Volumes/Nuxeo Drive/Nuxeo Drive.app")
    monkeypatch.setattr(fatal_error, "MAC", True)
    monkeypatch.setattr(fatal_error, "_accepted_app_paths", Mock(return_value=set()))
    monkeypatch.setattr(fatal_error, "_is_dmg_mount_path", Mock(return_value=True))
    monkeypatch.setattr(sys, "executable", f"{bundle}/Contents/MacOS/Nuxeo Drive")
    Options.is_frozen = True

    assert fatal_error.check_executable_path() is True


def test_expected_app_names_label(monkeypatch):
    monkeypatch.setattr(
        fatal_error, "_accepted_app_names", Mock(return_value={"Drive"})
    )
    assert fatal_error._expected_app_names_label() == "Drive.app"

    monkeypatch.setattr(
        fatal_error,
        "_accepted_app_names",
        Mock(return_value={"Drive", "Nuxeo Drive"}),
    )
    label = fatal_error._expected_app_names_label()
    assert '"Drive.app"' in label
    assert '"Nuxeo Drive.app"' in label


def test_check_executable_path_falls_back_without_showing_ui(monkeypatch):
    qt_error = Mock(side_effect=RuntimeError("Qt unavailable"))
    mac_error = Mock()
    monkeypatch.setattr(fatal_error, "MAC", True)
    monkeypatch.setattr(fatal_error, "_accepted_app_paths", Mock(return_value=set()))
    monkeypatch.setattr(fatal_error, "_is_dmg_mount_path", Mock(return_value=False))
    monkeypatch.setattr(fatal_error, "check_executable_path_error_qt", qt_error)
    monkeypatch.setattr(fatal_error, "fatal_error_mac", mac_error)
    monkeypatch.setattr(sys, "executable", "/tmp/Shared Drive.app/Contents/MacOS/drive")
    Options.is_frozen = True

    assert fatal_error.check_executable_path() is False
    qt_error.assert_called_once_with(Path("/tmp/Shared Drive.app"))
    message = mac_error.call_args.args[0]
    assert "entire installation is broken" in message
    assert "Qt unavailable" in message
