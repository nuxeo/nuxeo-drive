"""Cross-platform coverage for backend-neutral updater error and install paths."""

import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, patch

import pytest
import yaml
from requests.exceptions import ConnectionError as RequestsConnectionError

from nxdrive.drive.updater import UpdateError
from nxdrive.drive.updater import base as updater_base
from nxdrive.drive.updater import utils as updater_utils
from nxdrive.drive.updater.constants import AutoUpdateState, Login
from nxdrive.drive.updater.darwin import Updater as DarwinUpdater
from nxdrive.drive.updater.linux import Updater as LinuxUpdater
from nxdrive.drive.updater.windows import Updater as WindowsUpdater


def _signal() -> SimpleNamespace:
    return SimpleNamespace(emit=Mock())


def _base_updater(**overrides):
    instance = SimpleNamespace(
        update_site="https://updates.invalid",
        release_file="drive-{}.bin",
        versions={"2.0": {"type": "release"}},
        chunk_size=8,
        progress=0,
        _set_progress=Mock(),
        _update_in_progress=False,
        status="up_to_date",
    )
    for name, value in overrides.items():
        setattr(instance, name, value)
    return instance


def test_can_update_forced_and_disabled_and_server_version(monkeypatch):
    manager = SimpleNamespace(
        server_config_updater=SimpleNamespace(first_run=False),
        engines={},
        get_auto_update=Mock(return_value=True),
    )
    instance = SimpleNamespace(manager=manager)

    monkeypatch.setenv("FORCE_USE_LATEST_VERSION", "1")
    assert updater_base.BaseUpdater.can_update.fget(instance) is True

    monkeypatch.delenv("FORCE_USE_LATEST_VERSION")
    monkeypatch.setattr(
        updater_base, "auto_updates_state", lambda: AutoUpdateState.DISABLED
    )
    assert updater_base.BaseUpdater.can_update.fget(instance) is False
    assert updater_base.BaseUpdater.server_ver.fget(instance) is None


def test_base_install_is_abstract():
    with pytest.raises(NotImplementedError):
        updater_base.BaseUpdater.install(SimpleNamespace(), "installer.bin")


def test_download_reraises_connection_errors(monkeypatch):
    instance = _base_updater()
    error = RequestsConnectionError("offline")
    monkeypatch.setattr(updater_base.requests, "get", Mock(side_effect=error))

    with pytest.raises(RequestsConnectionError) as exc_info:
        updater_base.BaseUpdater._download(instance, "2.0")

    assert exc_info.value is error


def test_download_wraps_non_connection_errors(monkeypatch):
    instance = _base_updater()
    monkeypatch.setattr(
        updater_base.requests, "get", Mock(side_effect=ValueError("bad response"))
    )

    with pytest.raises(UpdateError, match="Impossible to get"):
        updater_base.BaseUpdater._download(instance, "2.0")


def _response(text: str) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value = response
    response.text = text
    return response


def test_fetch_versions_wraps_request_errors(monkeypatch):
    instance = _base_updater()
    monkeypatch.setattr(
        updater_base.requests, "get", Mock(side_effect=RuntimeError("offline"))
    )

    with pytest.raises(UpdateError, match="Impossible to get"):
        updater_base.BaseUpdater._fetch_versions(instance)


def test_fetch_versions_wraps_yaml_errors(monkeypatch):
    instance = _base_updater()
    monkeypatch.setattr(updater_base.requests, "get", Mock(return_value=_response("!")))
    monkeypatch.setattr(
        updater_base.yaml,
        "safe_load",
        Mock(side_effect=yaml.YAMLError("invalid document")),
    )

    with pytest.raises(UpdateError, match="Parsing error"):
        updater_base.BaseUpdater._fetch_versions(instance)


def test_fetch_versions_normalizes_non_mapping_documents(monkeypatch):
    instance = _base_updater()
    monkeypatch.setattr(
        updater_base.requests, "get", Mock(return_value=_response("- one\n- two"))
    )

    updater_base.BaseUpdater._fetch_versions(instance)

    assert instance.versions == {}


@pytest.mark.parametrize(
    "versions, version, expected",
    [
        ({"2.0": {"type": "beta"}}, "2.0", "beta"),
        ({"2.0": {"type": None}}, "2.0", ""),
        ({}, "missing", ""),
    ],
)
def test_get_version_channel(versions, version, expected):
    instance = SimpleNamespace(versions=versions)
    assert updater_base.BaseUpdater.get_version_channel(instance, version) == expected


def test_poll_stops_when_feature_is_disabled(monkeypatch):
    instance = _base_updater()
    monkeypatch.setattr(updater_base.Feature, "auto_update", False)

    assert updater_base.BaseUpdater._poll(instance) is False
    assert instance._update_in_progress is False


def test_poll_stops_when_an_update_is_already_running(monkeypatch):
    instance = _base_updater(_update_in_progress=True)
    monkeypatch.setattr(updater_base.Feature, "auto_update", True)

    assert updater_base.BaseUpdater._poll(instance) is False
    assert instance._update_in_progress is True


def test_darwin_install_restarts_when_copied_bundle_exists(monkeypatch, tmp_path):
    app = tmp_path / "Current.app"
    app.mkdir()
    executable = app / "Contents" / "MacOS" / "drive"
    instance = SimpleNamespace(
        manager=SimpleNamespace(osi=SimpleNamespace(cleanup=Mock())),
        _relocate_in_home=Mock(),
        _fix_notarization=Mock(),
        _mount=Mock(return_value=str(tmp_path / "mount")),
        _backup=Mock(),
        _copy=Mock(),
        _unmount=Mock(),
        _cleanup=Mock(),
        _set_progress=Mock(),
        _restart=Mock(),
    )
    with patch("nxdrive.drive.updater.darwin.sys.executable", str(executable)):
        DarwinUpdater.install(instance, "installer.dmg")

    assert instance._set_progress.call_args_list == [
        call(70),
        call(80),
        call(90),
        call(100),
    ]
    instance._restart.assert_called_once_with()


def test_darwin_relocation_returns_when_not_in_system_applications(tmp_path):
    instance = SimpleNamespace(final_app=tmp_path / "Drive.app")
    DarwinUpdater._relocate_in_home(instance)
    assert instance.final_app == tmp_path / "Drive.app"


def test_darwin_relocation_moves_to_user_applications(tmp_path):
    instance = SimpleNamespace(final_app=Path("/Applications/Drive.app"))
    with patch.object(Path, "home", return_value=tmp_path), patch(
        "nxdrive.drive.updater.darwin.shutil.rmtree"
    ) as remove, patch("nxdrive.drive.updater.darwin.shutil.move") as move:
        DarwinUpdater._relocate_in_home(instance)

    destination = tmp_path / "Applications" / "Drive.app"
    remove.assert_called_once_with(destination)
    move.assert_called_once_with(Path("/Applications/Drive.app"), destination)
    assert instance.final_app == destination


def test_darwin_backup_ignores_missing_source(tmp_path):
    instance = SimpleNamespace(final_app=tmp_path / "missing.app")
    with patch("nxdrive.drive.updater.darwin.shutil.move") as move:
        DarwinUpdater._backup(instance)
    move.assert_not_called()


def test_darwin_copy_checks_legacy_location(monkeypatch, tmp_path):
    instance = SimpleNamespace(final_app=tmp_path / "final.app")
    check_call = Mock()
    monkeypatch.setattr(subprocess, "check_call", check_call)

    with patch.object(Path, "exists", side_effect=[False, True]):
        DarwinUpdater._copy(instance, str(tmp_path / "mounted"))

    check_call.assert_called_once()


def test_darwin_notarization_success_is_logged(monkeypatch):
    check_call = Mock()
    monkeypatch.setattr(subprocess, "check_call", check_call)

    DarwinUpdater._fix_notarization(SimpleNamespace(), "installer.dmg")

    check_call.assert_called_once_with(
        ["xattr", "-d", "com.apple.quarantine", "installer.dmg"]
    )


def test_linux_install_moves_marks_executable_and_restarts(monkeypatch, tmp_path):
    salted = tmp_path / ("a" * 33 + "drive.AppImage")
    salted.write_bytes(b"app")
    monkeypatch.setenv("APPIMAGE", str(tmp_path / "old.AppImage"))
    instance = SimpleNamespace(_restart=Mock())

    LinuxUpdater.install(instance, str(salted))

    installed = tmp_path / "drive.AppImage"
    assert installed.read_bytes() == b"app"
    assert installed.stat().st_mode & stat.S_IXUSR
    instance._restart.assert_called_once_with(str(installed))


def test_linux_restart_launches_and_emits(monkeypatch):
    popen = Mock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    instance = SimpleNamespace(appUpdated=_signal())

    LinuxUpdater._restart(instance, "/tmp/drive.AppImage")

    popen.assert_called_once_with(
        'sleep 5 ; "/tmp/drive.AppImage"&', shell=True, close_fds=True
    )
    instance.appUpdated.emit.assert_called_once_with()


def test_windows_install_launches_and_emits(monkeypatch, tmp_path):
    popen = Mock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    instance = SimpleNamespace(appUpdated=_signal())
    installer = str(tmp_path / "drive.exe")

    WindowsUpdater.install(instance, installer)

    command = popen.call_args.args[0]
    assert installer in command
    popen.assert_called_once_with(command, shell=True, close_fds=True)
    instance.appUpdated.emit.assert_called_once_with()


def test_auto_update_state_final_disabled_branch(monkeypatch):
    monkeypatch.setattr(
        updater_utils,
        "Feature",
        SimpleNamespace(auto_update=True),
    )
    monkeypatch.setattr(
        updater_utils,
        "Options",
        SimpleNamespace(
            is_frozen=True,
            update_check_delay=0,
            channel="release",
            client_version=None,
        ),
    )

    assert updater_utils.auto_updates_state() is AutoUpdateState.DISABLED


def test_version_requiring_browser_login_is_incompatible():
    assert (
        updater_utils.is_version_compatible("4.0", {"min": "1.0"}, "2.0", False)
        is False
    )


def test_unknown_login_compatibility_returns_no_update():
    versions = {"1.0": {"type": "release", "min": "1.0"}}
    assert updater_utils.get_update_status(
        "1.0", versions, "release", "1.0", Login.UNKNOWN
    ) == ("", "")
