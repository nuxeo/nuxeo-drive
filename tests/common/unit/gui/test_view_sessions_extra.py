"""Focused tests for the shared session list models."""

from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from unittest.mock import Mock, call, patch

import pytest

from nxdrive.drive.constants import TransferStatus
from nxdrive.drive.gui.view import ActiveSessionModel, CompletedSessionModel


@pytest.fixture
def translate():
    """Return translations together with their interpolation values."""
    return Mock(side_effect=lambda key, values=None: (key, values))


def make_active_session(**overrides):
    session = {
        "uid": 42,
        "status": TransferStatus.DONE,
        "remote_ref": "remote-ref",
        "remote_path": Path("/shared/folder"),
        "uploaded": 12_345,
        "total": 67_890,
        "engine": "engine-id",
        "created_on": "created",
        "completed_on": "completed",
        "description": "Shared transfer",
        "scheduled_at": 0,
    }
    session.update(overrides)
    return session


def make_completed_session(**overrides):
    session = {
        "uid": 84,
        "status": TransferStatus.DONE,
        "remote_ref": "remote-ref",
        "remote_path": Path("/shared/completed"),
        "uploaded": 12_345,
        "total": 67_890,
        "planned_items": 67_890,
        "engine": "engine-id",
        "created_on": "created",
        "completed_on": "completed",
        "description": "Completed transfer",
        "csv_path": "/tmp/result.csv",
        "scheduled_at": "schedule-value",
    }
    session.update(overrides)
    return session


def model_index(model, session):
    model.sessions = [session]
    return model.index(0, 0)


def test_active_session_scalar_roles(app, translate):
    model = ActiveSessionModel(translate)
    row = make_active_session(shadow=True)
    index = model_index(model, row)

    assert model.data(index, model.REMOTE_PATH) == "/shared/folder"
    assert model.data(index, model.STATUS) == "COMPLETED"
    assert model.data(index, model.DESCRIPTION) == "Shared transfer"
    assert model.data(index, model.PROGRESS) == "[12,345 / 67,890]"
    assert model.data(index, model.SHADOW) is True
    assert model.data(index, model.UID) == 42

    row["status"] = TransferStatus.CANCELLED
    row["description"] = ""
    row.pop("shadow")
    assert model.data(index, model.STATUS) == "CANCELLED"
    assert model.data(index, model.DESCRIPTION) == "Session 42"
    assert model.data(index, model.SHADOW) is False


def test_session_remote_paths_use_posix_separators(app, translate):
    active = ActiveSessionModel(translate)
    active_index = model_index(
        active,
        make_active_session(remote_path=PureWindowsPath("/shared/folder")),
    )
    completed = CompletedSessionModel(translate)
    completed_index = model_index(
        completed,
        make_completed_session(remote_path=PureWindowsPath("/shared/completed")),
    )

    assert active.data(active_index, active.REMOTE_PATH) == "/shared/folder"
    assert completed.data(completed_index, completed.REMOTE_PATH) == "/shared/completed"


@pytest.mark.parametrize("offset", [timedelta(hours=2), None])
def test_active_session_date_roles(app, translate, offset):
    instant = datetime(2026, 8, 5, 9, 30)
    zone = Mock()
    zone.utcoffset.return_value = offset
    model = ActiveSessionModel(translate)
    index = model_index(model, make_active_session())

    with patch(
        "nxdrive.drive.gui.view.get_date_from_sqlite", return_value=instant
    ) as get_date, patch("nxdrive.drive.gui.view.tzlocal", return_value=zone), patch(
        "nxdrive.drive.gui.view.Translator.format_datetime",
        return_value="formatted-date",
    ) as format_datetime:
        assert model.data(index, model.CREATED_ON) == (
            "STARTED_ON",
            ["formatted-date"],
        )
        assert model.data(index, model.COMPLETED_ON) == (
            "COMPLETED_ON",
            ["formatted-date"],
        )

    adjusted = instant + offset if offset else instant
    assert get_date.call_args_list == [call("created"), call("completed")]
    assert format_datetime.call_args_list == [call(adjusted), call(adjusted)]


def test_active_session_date_roles_without_dates(app, translate):
    model = ActiveSessionModel(translate)
    index = model_index(
        model,
        make_active_session(
            status=TransferStatus.CANCELLED,
            created_on=None,
            completed_on=None,
        ),
    )

    with patch("nxdrive.drive.gui.view.get_date_from_sqlite", return_value=None):
        assert model.data(index, model.CREATED_ON) == ("STARTED", [])
        assert model.data(index, model.COMPLETED_ON) == ("CANCELLED", [])


def test_active_session_valid_schedule(app, translate):
    parsed = Mock()
    localized = Mock()
    localized.strftime.return_value = "05 Aug 2026, 11:45:00"
    parsed.astimezone.return_value = localized
    zone = Mock()
    model = ActiveSessionModel(translate)
    index = model_index(
        model, make_active_session(scheduled_at="2026-08-05T09:45:00+00:00")
    )

    with patch(
        "nxdrive.drive.gui.view.parser.isoparse", return_value=parsed
    ) as isoparse, patch("nxdrive.drive.gui.view.tzlocal", return_value=zone):
        result = model.data(index, model.SCHEDULED_AT)

    assert result == ("SCHEDULED_ON", ["05 Aug 2026, 11:45:00"])
    isoparse.assert_called_once_with("2026-08-05T09:45:00+00:00")
    parsed.astimezone.assert_called_once_with(zone)
    localized.strftime.assert_called_once_with("%d %b %Y, %H:%M:%S")


def test_active_session_invalid_schedule_uses_raw_value(app, translate):
    model = ActiveSessionModel(translate)
    index = model_index(model, make_active_session(scheduled_at="not-a-date"))

    with patch(
        "nxdrive.drive.gui.view.parser.isoparse", side_effect=ValueError("invalid")
    ):
        assert model.data(index, model.SCHEDULED_AT) == (
            "SCHEDULED_ON",
            ["not-a-date"],
        )


@pytest.mark.parametrize("scheduled_at", [0, "0", None])
def test_active_session_empty_schedule(app, translate, scheduled_at):
    model = ActiveSessionModel(translate)
    index = model_index(model, make_active_session(scheduled_at=scheduled_at))

    assert model.data(index, model.SCHEDULED_AT) == ""


def test_completed_session_scalar_roles(app, translate):
    model = CompletedSessionModel(translate)
    row = make_completed_session()
    index = model_index(model, row)

    assert model.data(index, model.REMOTE_PATH) == "/shared/completed"
    assert model.data(index, model.STATUS) == "COMPLETED"
    assert model.data(index, model.DESCRIPTION) == "Completed transfer"
    assert model.data(index, model.PROGRESS) == "[12,345 / 67,890]"
    assert model.data(index, model.SHADOW) is False
    assert model.data(index, model.UID) == 84
    assert model.data(index, model.CSV_PATH) == "/tmp/result.csv"
    assert model.data(index, model.SCHEDULED_AT) == "schedule-value"

    row["status"] = TransferStatus.CANCELLED
    row["description"] = ""
    assert model.data(index, model.STATUS) == "CANCELLED"
    assert model.data(index, model.DESCRIPTION) == "Session 84"


@pytest.mark.parametrize(
    "status, completed_label",
    [
        (TransferStatus.DONE, "COMPLETED_ON"),
        (TransferStatus.CANCELLED, "CANCELLED_ON"),
    ],
)
def test_completed_session_date_roles(app, translate, status, completed_label):
    instant = datetime(2026, 8, 5, 9, 30)
    offset = timedelta(hours=-3)
    zone = Mock()
    zone.utcoffset.return_value = offset
    model = CompletedSessionModel(translate)
    index = model_index(model, make_completed_session(status=status))

    with patch(
        "nxdrive.drive.gui.view.get_date_from_sqlite", return_value=instant
    ), patch("nxdrive.drive.gui.view.tzlocal", return_value=zone), patch(
        "nxdrive.drive.gui.view.Translator.format_datetime",
        return_value="formatted-date",
    ) as format_datetime:
        assert model.data(index, model.CREATED_ON) == (
            "STARTED_ON",
            ["formatted-date"],
        )
        assert model.data(index, model.COMPLETED_ON) == (
            completed_label,
            ["formatted-date"],
        )

    adjusted = instant + offset
    assert format_datetime.call_args_list == [call(adjusted), call(adjusted)]


def test_completed_session_date_roles_without_dates(app, translate):
    model = CompletedSessionModel(translate)
    index = model_index(
        model,
        make_completed_session(
            status=TransferStatus.CANCELLED,
            created_on=None,
            completed_on=None,
        ),
    )

    with patch("nxdrive.drive.gui.view.get_date_from_sqlite", return_value=None):
        assert model.data(index, model.CREATED_ON) == ("STARTED", [])
        assert model.data(index, model.COMPLETED_ON) == ("CANCELLED", [])
