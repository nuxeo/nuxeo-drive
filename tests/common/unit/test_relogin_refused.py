#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""A refused re-login is shown like an expired login, with its own reason."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.drive.engine.engine import Engine
from nxdrive.drive.gui.application import Application
from nxdrive.drive.gui.view import EngineModel
from nxdrive.drive.notification import Notification, ReloginFailedNotification


def _engine():
    with patch.object(Engine, "__init__", return_value=None):
        engine = Engine.__new__(Engine)
    engine.uid = "engine-1"
    engine._invalid_credentials = True
    engine.authChanged = MagicMock()
    engine.invalidAuthentication = MagicMock()
    return engine


class TestEngineFlag:
    def test_off_by_default(self):
        assert _engine().has_relogin_failed() is False

    def test_set_once_refreshes_the_ui_once(self):
        engine = _engine()

        engine.set_relogin_failed(True)
        engine.set_relogin_failed(True)

        assert engine.has_relogin_failed() is True
        engine.authChanged.emit.assert_called_once_with("engine-1")

    def test_cleared_by_a_successful_relogin(self):
        engine = _engine()
        engine.set_relogin_failed(True)

        engine.set_invalid_credentials(value=False)

        assert engine.has_relogin_failed() is False
        assert engine.has_invalid_credentials() is False

    def test_kept_while_credentials_stay_invalid(self):
        engine = _engine()
        engine.set_relogin_failed(True)

        engine.set_invalid_credentials(value=True)

        assert engine.has_relogin_failed() is True


@patch("nxdrive.drive.notification.Translator")
def test_notification(translator):
    translator.get.side_effect = lambda key, values=None: f"<{key}:{values}>"

    notif = ReloginFailedNotification("engine-1", "tester")

    assert notif.uid == "RELOGIN_FAILED_engine-1"
    assert notif.title == "<RELOGIN_FAILED:None>"
    assert notif.description == "<RELOGIN_FAILED_DESCRIPTION:['tester']>"
    assert notif.level == Notification.LEVEL_ERROR  # Red, like AUTH_EXPIRED.
    assert notif.is_systray() and notif.is_bubble() and notif.is_unique()
    assert notif.action == "web_update_token"
    assert notif.action_args == ("engine-1",)


class TestSystrayBanner:
    def _status(self, *, invalid, refused):
        engine = Mock(spec=Engine, uid="engine-1")
        engine.has_invalid_credentials.return_value = invalid
        engine.has_relogin_failed.return_value = refused
        engine.is_paused.return_value = False
        engine.is_syncing.return_value = False
        root = MagicMock()
        app = SimpleNamespace(
            _current_engine_uid="engine-1",
            manager=SimpleNamespace(restart_needed=False, updater=Mock(status="")),
            refresh_conflicts=Mock(),
            conflicts_model=Mock(count=0),
            errors_model=Mock(count=0),
            systray_window=Mock(),
            _window_root=lambda _: root,
        )
        Application.update_status(app, engine)
        return root.setStatus.emit.call_args.args[1]

    @pytest.mark.parametrize(
        "invalid, refused, expected",
        [
            (True, True, "relogin_failed"),
            (True, False, "auth_expired"),
            (False, False, ""),
        ],
    )
    def test_error_state(self, invalid, refused, expected):
        assert self._status(invalid=invalid, refused=refused) == expected


def test_a_login_change_refreshes_the_systray_banner():
    model = EngineModel.__new__(EngineModel)
    engine = MagicMock()

    with patch.object(EngineModel, "__init__", return_value=None):
        EngineModel._connect_engine(model, engine)

    relayed = [c.args[0] for c in engine.authChanged.connect.call_args_list]
    assert model._relay_engine_events in relayed


@pytest.mark.parametrize("folder", ["nxdrive/data/i18n", "nxdrive/drive/data/i18n"])
def test_translations(folder):
    labels = json.loads(
        (Path(__file__).parents[3] / folder / "i18n.json").read_text(encoding="utf-8")
    )
    assert labels["RELOGIN_FAILED"] == "Incorrect password"
    assert "%1" in labels["RELOGIN_FAILED_DESCRIPTION"]
    assert labels["RELOGIN_RETRY_ACTION"]
    assert labels["RELOGIN_WRONG_PASSWORD"]


@pytest.mark.parametrize(
    "qml, needle",
    [
        ("Systray.qml", 'name: "relogin_failed"'),
        ("EngineAccountItem.qml", "api.has_relogin_failed(uid)"),
    ],
)
def test_the_banners_use_the_new_state(qml, needle):
    path = Path(__file__).parents[3] / "nxdrive" / "drive" / "data" / "qml" / qml
    assert needle in path.read_text(encoding="utf-8")
