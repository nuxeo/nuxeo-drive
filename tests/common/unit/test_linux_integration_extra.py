import subprocess
from unittest.mock import Mock

import pytest

from nxdrive.drive.options import Options
from nxdrive.drive.osi.extension import Status, icon_status
from nxdrive.drive.osi.linux import linux
from nxdrive.drive.osi.linux.linux import LinuxIntegration


@pytest.fixture
def frozen_app():
    original = Options.is_frozen
    Options.set("is_frozen", True, setter="manual")
    yield
    Options.set("is_frozen", original, setter="manual")


@pytest.fixture
def integration():
    instance = LinuxIntegration.__new__(LinuxIntegration)
    instance._gio_path = "/usr/bin/gio"
    instance._last_emblem = {}
    return instance


def test_register_protocol_handlers_skips_without_appimage(
    integration, frozen_app, monkeypatch
):
    monkeypatch.delenv("APPIMAGE", raising=False)
    check_call = Mock()
    monkeypatch.setattr(linux.subprocess, "check_call", check_call)

    integration.register_protocol_handlers()

    check_call.assert_not_called()


def test_register_protocol_handlers_writes_desktop_file(
    integration, frozen_app, monkeypatch, tmp_path
):
    appimage = "/opt/Drive AppImage"
    monkeypatch.setenv("APPIMAGE", appimage)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    environment = {"DISPLAY": ":test"}
    host_env = Mock(return_value=environment)
    check_call = Mock()
    monkeypatch.setattr(linux, "host_env", host_env)
    monkeypatch.setattr(linux.subprocess, "check_call", check_call)

    integration.register_protocol_handlers()

    desktop_file = (
        tmp_path
        / ".local"
        / "share"
        / "applications"
        / f"{linux.NXDRIVE_SCHEME}.desktop"
    )
    content = desktop_file.read_text(encoding="utf-8")
    assert f'Exec="{appimage}" %u' in content
    assert f"MimeType=x-scheme-handler/{linux.NXDRIVE_SCHEME};" in content
    host_env.assert_called_once_with()
    check_call.assert_called_once_with(
        [
            "xdg-mime",
            "default",
            f"{linux.NXDRIVE_SCHEME}.desktop",
            f"x-scheme-handler/{linux.NXDRIVE_SCHEME}",
        ],
        env=environment,
    )


def test_register_protocol_handlers_logs_registration_failure(
    integration, frozen_app, monkeypatch, tmp_path
):
    monkeypatch.setenv("APPIMAGE", "/opt/drive")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(
        linux.subprocess,
        "check_call",
        Mock(side_effect=subprocess.CalledProcessError(1, ["xdg-mime"])),
    )
    log = Mock()
    monkeypatch.setattr(linux, "log", log)

    integration.register_protocol_handlers()

    log.warning.assert_called_once_with(
        "Error while registering the URL scheme", exc_info=True
    )


def test_set_icon_skips_when_gio_is_unavailable(integration, monkeypatch):
    integration._gio_path = None
    check_call = Mock()
    monkeypatch.setattr(linux.subprocess, "check_call", check_call)

    integration._set_icon({"path": "/sync", "value": str(Status.SYNCED.value)})

    check_call.assert_not_called()


def test_set_icon_invokes_gio_once_and_caches_emblem(integration, monkeypatch):
    environment = {"PATH": "/usr/bin"}
    monkeypatch.setattr(linux, "host_env", Mock(return_value=environment))
    check_call = Mock()
    monkeypatch.setattr(linux.subprocess, "check_call", check_call)
    status = {"path": "/sync/folder", "value": str(Status.CONFLICTED.value)}

    integration._set_icon(status)
    integration._set_icon(status)

    emblem = icon_status[Status.CONFLICTED]
    check_call.assert_called_once_with(
        [
            "/usr/bin/gio",
            "set",
            "-t",
            "stringv",
            "/sync/folder",
            "metadata::emblems",
            emblem,
        ],
        env=environment,
    )
    assert integration._last_emblem == {"/sync/folder": emblem}


def test_set_icon_disables_gio_when_executable_disappears(integration, monkeypatch):
    monkeypatch.setattr(
        linux.subprocess, "check_call", Mock(side_effect=FileNotFoundError)
    )

    integration._set_icon({"path": "/sync", "value": str(Status.ERROR.value)})

    assert integration._gio_path is None
    assert integration._last_emblem == {}


def test_set_icon_ignores_gio_command_failure(integration, monkeypatch):
    monkeypatch.setattr(
        linux.subprocess,
        "check_call",
        Mock(side_effect=subprocess.CalledProcessError(5, ["gio"])),
    )
    log = Mock()
    monkeypatch.setattr(linux, "log", log)

    integration._set_icon({"path": "/sync", "value": str(Status.LOCKED.value)})

    assert integration._last_emblem == {}
    log.exception.assert_called_once()


def test_set_icon_logs_unexpected_failure(integration, monkeypatch):
    monkeypatch.setattr(
        linux.subprocess, "check_call", Mock(side_effect=RuntimeError("boom"))
    )
    log = Mock()
    monkeypatch.setattr(linux, "log", log)

    integration._set_icon({"path": "/sync", "value": str(Status.SYNCING.value)})

    assert integration._last_emblem == {}
    log.warning.assert_called_once()
