#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""A re-login with another user is shown like an expired login, with its own reason."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.drive.engine.engine import Engine


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
        assert _engine().has_relogin_wrong_user() is False

    def test_set_once_refreshes_the_ui_once(self):
        engine = _engine()

        engine.set_relogin_wrong_user(True)
        engine.set_relogin_wrong_user(True)

        assert engine.has_relogin_wrong_user() is True
        engine.authChanged.emit.assert_called_once_with("engine-1")

    def test_cleared_by_a_successful_relogin(self):
        engine = _engine()
        engine.set_relogin_wrong_user(True)

        engine.set_invalid_credentials(value=False)

        assert engine.has_relogin_wrong_user() is False
        assert engine.has_invalid_credentials() is False

    def test_kept_while_credentials_stay_invalid(self):
        engine = _engine()
        engine.set_relogin_wrong_user(True)

        engine.set_invalid_credentials(value=True)

        assert engine.has_relogin_wrong_user() is True


@pytest.mark.parametrize(
    "needle",
    [
        "api.has_relogin_wrong_user(uid)",
        'qsTr("RELOGIN_WRONG_USER")',
    ],
)
def test_the_account_card_uses_the_new_state(needle):
    path = (
        Path(__file__).parents[3]
        / "nxdrive"
        / "drive"
        / "data"
        / "qml"
        / "EngineAccountItem.qml"
    )
    assert needle in path.read_text(encoding="utf-8")
