"""Focused tests for the backend-neutral updater control flow."""

import errno
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest
from requests.exceptions import ConnectionError

from nxdrive.drive.updater import UpdateError, UpdateIntegrityError
from nxdrive.drive.updater import base as updater_base
from nxdrive.drive.updater.constants import (
    UPDATE_STATUS_INCOMPATIBLE_SERVER,
    UPDATE_STATUS_UNAVAILABLE_SITE,
    UPDATE_STATUS_UP_TO_DATE,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_UPDATING,
    UPDATE_STATUS_WRONG_CHANNEL,
    Login,
)


def make_signal():
    return SimpleNamespace(emit=Mock())


def make_manager():
    return SimpleNamespace(
        engines={},
        version="1.0",
        get_server_login_type=Mock(return_value=Login.NONE),
        get_update_channel=Mock(return_value="release"),
        restartNeeded=make_signal(),
    )


def make_updater(**overrides):
    updater = SimpleNamespace(
        manager=make_manager(),
        status=UPDATE_STATUS_UP_TO_DATE,
        version="",
        available_version="",
        versions={},
        ext="dmg",
        enable=True,
        can_update=True,
        server_ver="2025.1",
        _fetch_versions=Mock(),
        _set_status=Mock(),
        _download=Mock(return_value="installer.dmg"),
        _install=Mock(),
        update=Mock(),
        updateAvailable=make_signal(),
        wrongChannel=make_signal(),
        serverIncompatible=make_signal(),
        noSpaceLeftOnDevice=make_signal(),
    )
    for name, value in overrides.items():
        setattr(updater, name, value)
    return updater


def test_update_downloads_and_installs_requested_version():
    updater = make_updater()

    updater_base.BaseUpdater.update(updater, "2.0")

    updater._set_status.assert_called_once_with(
        UPDATE_STATUS_UPDATING, version="2.0", progress=10
    )
    updater._download.assert_called_once_with("2.0")
    updater._install.assert_called_once_with("2.0", "installer.dmg")


def test_update_swallows_connection_errors():
    updater = make_updater()
    updater._download.side_effect = ConnectionError("offline")

    updater_base.BaseUpdater.update(updater, "2.0")

    updater._set_status.assert_called_once_with(
        UPDATE_STATUS_UPDATING, version="2.0", progress=10
    )
    updater._install.assert_not_called()


def test_update_reports_no_space_and_restores_available_status():
    updater = make_updater()
    updater._download.side_effect = OSError(errno.ENOSPC, "full")

    updater_base.BaseUpdater.update(updater, "2.0")

    assert updater._set_status.call_args_list == [
        call(UPDATE_STATUS_UPDATING, version="2.0", progress=10),
        call(UPDATE_STATUS_UPDATE_AVAILABLE, version="2.0"),
    ]
    updater.noSpaceLeftOnDevice.emit.assert_called_once_with()


def test_update_reraises_other_os_errors_after_restoring_status():
    updater = make_updater()
    updater._download.side_effect = OSError(errno.EACCES, "denied")

    with pytest.raises(OSError) as exc_info:
        updater_base.BaseUpdater.update(updater, "2.0")

    assert exc_info.value.errno == errno.EACCES
    assert updater._set_status.call_args_list[-1] == call(
        UPDATE_STATUS_UPDATE_AVAILABLE, version="2.0"
    )
    updater.noSpaceLeftOnDevice.emit.assert_not_called()


def test_update_swallows_integrity_errors():
    updater = make_updater()
    updater._download.side_effect = UpdateIntegrityError(
        "installer.dmg", "sha256", "expected", "actual"
    )

    updater_base.BaseUpdater.update(updater, "2.0")

    updater._set_status.assert_called_once_with(
        UPDATE_STATUS_UPDATING, version="2.0", progress=10
    )
    updater._install.assert_not_called()


def test_update_swallows_unexpected_errors_and_restores_status():
    updater = make_updater()
    updater._install.side_effect = RuntimeError("installation failed")

    updater_base.BaseUpdater.update(updater, "2.0")

    assert updater._set_status.call_args_list == [
        call(UPDATE_STATUS_UPDATING, version="2.0", progress=10),
        call(UPDATE_STATUS_UPDATE_AVAILABLE, version="2.0"),
    ]


def test_get_update_status_marks_unavailable_site_after_fetch_error(monkeypatch):
    monkeypatch.delenv("FORCE_USE_LATEST_VERSION", raising=False)
    updater = make_updater()
    updater._fetch_versions.side_effect = UpdateError("offline")

    updater_base.BaseUpdater._get_update_status(updater)

    assert updater.status == UPDATE_STATUS_UNAVAILABLE_SITE
    assert updater.version == ""
    updater._set_status.assert_not_called()


def test_get_update_status_force_latest_selects_newer_version(monkeypatch):
    monkeypatch.setenv("FORCE_USE_LATEST_VERSION", "1")
    updater = make_updater(versions={"1.0": {}, "2.0": {}})

    updater_base.BaseUpdater._get_update_status(updater)

    updater._set_status.assert_called_once_with(
        UPDATE_STATUS_UPDATE_AVAILABLE, version="2.0"
    )


def test_get_update_status_force_latest_ignores_older_version(monkeypatch):
    monkeypatch.setenv("FORCE_USE_LATEST_VERSION", "1")
    updater = make_updater(versions={"1.0": {}, "2.0": {}})
    updater.manager.version = "3.0"

    updater_base.BaseUpdater._get_update_status(updater)

    updater._set_status.assert_not_called()
    assert updater.status == UPDATE_STATUS_UP_TO_DATE


def test_get_update_status_aggregates_logins_and_sets_available_update(monkeypatch):
    monkeypatch.delenv("FORCE_USE_LATEST_VERSION", raising=False)
    updater = make_updater(versions={"2.0": {"checksum": {"dmg": "ABCDEF"}}})
    updater.manager.engines = {
        "first": SimpleNamespace(server_url="https://one.invalid"),
        "second": SimpleNamespace(server_url="https://two.invalid"),
    }
    updater.manager.get_server_login_type.side_effect = [Login.OLD, Login.NEW]

    with patch.object(
        updater_base,
        "get_update_status",
        return_value=(UPDATE_STATUS_UPDATE_AVAILABLE, "2.0"),
    ) as get_status:
        updater_base.BaseUpdater._get_update_status(updater)

    assert updater.manager.get_server_login_type.call_args_list == [
        call("https://one.invalid", _raise=False),
        call("https://two.invalid", _raise=False),
    ]
    get_status.assert_called_once_with(
        "1.0",
        updater.versions,
        "release",
        "2025.1",
        Login.OLD | Login.NEW,
    )
    assert updater.available_version == "2.0"
    updater._set_status.assert_called_once_with(
        UPDATE_STATUS_UPDATE_AVAILABLE, version="2.0"
    )


def test_get_update_status_stops_when_platform_checksum_is_missing(monkeypatch):
    monkeypatch.delenv("FORCE_USE_LATEST_VERSION", raising=False)
    updater = make_updater(versions={"2.0": {"checksum": {"exe": "ABCDEF"}}})

    with patch.object(
        updater_base,
        "get_update_status",
        return_value=(UPDATE_STATUS_UPDATE_AVAILABLE, "2.0"),
    ):
        updater_base.BaseUpdater._get_update_status(updater)

    assert updater.available_version == "2.0"
    assert updater.status == UPDATE_STATUS_UP_TO_DATE
    updater._set_status.assert_not_called()


@pytest.mark.parametrize("enable, can_update", [(False, True), (True, False)])
def test_get_update_status_records_status_when_update_is_not_allowed(
    monkeypatch, enable, can_update
):
    monkeypatch.delenv("FORCE_USE_LATEST_VERSION", raising=False)
    updater = make_updater(
        versions={"2.0": {"checksum": {"dmg": "ABCDEF"}}},
        enable=enable,
        can_update=can_update,
    )

    with patch.object(
        updater_base,
        "get_update_status",
        return_value=(UPDATE_STATUS_UPDATE_AVAILABLE, "2.0"),
    ):
        updater_base.BaseUpdater._get_update_status(updater)

    assert updater.status == UPDATE_STATUS_UPDATE_AVAILABLE
    assert updater.version == ""
    updater._set_status.assert_not_called()


def test_get_update_status_records_status_without_candidate(monkeypatch):
    monkeypatch.delenv("FORCE_USE_LATEST_VERSION", raising=False)
    updater = make_updater(versions={})

    with patch.object(
        updater_base,
        "get_update_status",
        return_value=(UPDATE_STATUS_UP_TO_DATE, ""),
    ):
        updater_base.BaseUpdater._get_update_status(updater)

    assert updater.status == UPDATE_STATUS_UP_TO_DATE
    assert updater.version == ""
    updater._set_status.assert_not_called()


def test_force_downgrade_marks_site_unavailable_and_notifies():
    updater = make_updater()
    updater._fetch_versions.side_effect = UpdateError("offline")

    updater_base.BaseUpdater.force_downgrade(updater)

    updater._set_status.assert_called_once_with(UPDATE_STATUS_UNAVAILABLE_SITE)
    updater.serverIncompatible.emit.assert_called_once_with()


def test_force_downgrade_selects_latest_pre_v4_release_or_channel_version():
    updater = make_updater(
        versions={
            "2.9": {"type": "alpha"},
            "3.1": {"type": "BETA"},
            "3.2": {"type": "release"},
            "4.0": {"type": "release"},
        }
    )
    updater.manager.get_update_channel.return_value = "beta"

    updater_base.BaseUpdater.force_downgrade(updater)

    updater._set_status.assert_called_once_with(
        UPDATE_STATUS_INCOMPATIBLE_SERVER, version="3.2"
    )
    updater.serverIncompatible.emit.assert_called_once_with()


def test_force_downgrade_only_notifies_when_no_candidate_exists():
    updater = make_updater(
        versions={
            "3.9": {"type": "alpha"},
            "4.0": {"type": "release"},
        }
    )

    updater_base.BaseUpdater.force_downgrade(updater)

    updater._set_status.assert_not_called()
    updater.serverIncompatible.emit.assert_called_once_with()


@pytest.mark.parametrize(
    "status", [UPDATE_STATUS_UNAVAILABLE_SITE, UPDATE_STATUS_UP_TO_DATE]
)
def test_handle_status_returns_for_non_actionable_statuses(status):
    updater = make_updater(status=status, version="2.0")

    updater_base.BaseUpdater._handle_status(updater)

    updater.updateAvailable.emit.assert_not_called()
    updater.update.assert_not_called()


def test_handle_status_emits_wrong_channel_only():
    updater = make_updater(status=UPDATE_STATUS_WRONG_CHANNEL, version="2.0")

    updater_base.BaseUpdater._handle_status(updater)

    updater.wrongChannel.emit.assert_called_once_with()
    updater.updateAvailable.emit.assert_not_called()
    updater.update.assert_not_called()


def test_handle_status_ignores_actionable_status_without_version():
    updater = make_updater(status=UPDATE_STATUS_UPDATE_AVAILABLE, version="")

    updater_base.BaseUpdater._handle_status(updater)

    updater.updateAvailable.emit.assert_not_called()
    updater.update.assert_not_called()


@pytest.mark.parametrize("can_update", [False, True])
def test_handle_available_update_respects_update_permission(can_update):
    updater = make_updater(
        status=UPDATE_STATUS_UPDATE_AVAILABLE,
        version="2.0",
        can_update=can_update,
    )

    updater_base.BaseUpdater._handle_status(updater)

    updater.updateAvailable.emit.assert_called_once_with()
    if can_update:
        updater.update.assert_called_once_with("2.0")
    else:
        updater.update.assert_not_called()


def test_handle_incompatible_server_requests_restart_and_notifies():
    updater = make_updater(
        status=UPDATE_STATUS_INCOMPATIBLE_SERVER,
        version="3.2",
    )

    updater_base.BaseUpdater._handle_status(updater)

    updater.updateAvailable.emit.assert_called_once_with()
    updater.manager.restartNeeded.emit.assert_called_once_with()
    updater.serverIncompatible.emit.assert_called_once_with()
    updater.update.assert_not_called()
