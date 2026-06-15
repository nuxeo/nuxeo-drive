"""Unit tests for nxdrive.gui.schedule_dialog module."""

from unittest.mock import patch

import pytest
from PyQt6.QtCore import QDate, QDateTime
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from nxdrive.gui.schedule_dialog import ResumeScheduledSessionPopup, ScheduleDialog

from ...markers import not_linux

pytestmark = not_linux(
    reason="Qt GUI tests don't work reliably on Linux",
)


@pytest.fixture(scope="module")
def qapp():
    """Ensure a QApplication instance exists."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def translator_patch():
    def _translate(key, values=None):
        if values:
            return f"{key}:{values[0]}"
        return key

    with patch("nxdrive.gui.schedule_dialog.Translator.get", side_effect=_translate):
        yield


def _ok_button(dialog: ScheduleDialog) -> QPushButton:
    button = dialog.button_box.button(dialog.button_box.StandardButton.Ok)
    assert button is not None
    return button


def test_schedule_dialog_initialization_defaults(qapp, translator_patch):
    dialog = ScheduleDialog()

    assert dialog.windowTitle() == "SCHEDULE_PICK_DATETIME"
    assert dialog.selected_dt is not None
    assert dialog.calendar.minimumDate() == QDate.currentDate()
    assert dialog.calendar.maximumDate() == QDate.currentDate().addDays(365)
    assert dialog.error_label.isVisible() is False
    assert _ok_button(dialog).isEnabled() is True


def test_schedule_dialog_invalid_hours_disables_ok(qapp, translator_patch):
    dialog = ScheduleDialog()

    dialog.hours_input.setText("aa")

    assert dialog.error_label.text() == "SCHEDULE_INVALID_HOURS"
    assert _ok_button(dialog).isEnabled() is False


def test_schedule_dialog_invalid_minutes_disables_ok(qapp, translator_patch):
    dialog = ScheduleDialog()

    dialog.minutes_input.setText("60")

    assert dialog.error_label.text() == "SCHEDULE_INVALID_MINUTES"
    assert _ok_button(dialog).isEnabled() is False


def test_schedule_dialog_invalid_minutes_valueerror_branch(qapp, translator_patch):
    dialog = ScheduleDialog()

    with patch.object(dialog.minutes_input, "text", return_value="xx"):
        dialog._update_ok_button_state()

    assert dialog.error_label.text() == "SCHEDULE_INVALID_MINUTES"
    assert _ok_button(dialog).isEnabled() is False


def test_schedule_dialog_invalid_seconds_disables_ok(qapp, translator_patch):
    dialog = ScheduleDialog()

    dialog.seconds_input.setText("99")

    assert dialog.error_label.text() == "SCHEDULE_INVALID_SECONDS"
    assert _ok_button(dialog).isEnabled() is False


def test_schedule_dialog_invalid_seconds_valueerror_branch(qapp, translator_patch):
    dialog = ScheduleDialog()

    with patch.object(dialog.seconds_input, "text", return_value="xx"):
        dialog._update_ok_button_state()

    assert dialog.error_label.text() == "SCHEDULE_INVALID_SECONDS"
    assert _ok_button(dialog).isEnabled() is False


def test_schedule_dialog_invalid_datetime_disables_ok(qapp, translator_patch):
    dialog = ScheduleDialog()

    with patch.object(dialog.calendar, "selectedDate", return_value=QDate()):
        dialog._update_ok_button_state()

    assert dialog.error_label.text() == "SCHEDULE_INVALID_DATETIME"
    assert _ok_button(dialog).isEnabled() is False


def test_schedule_dialog_today_time_must_be_future(qapp, translator_patch):
    dialog = ScheduleDialog()

    now = QDateTime.currentDateTime()
    hour_24 = now.time().hour()
    hour_12 = (hour_24 - 1) % 12 + 1

    dialog.calendar.setSelectedDate(QDate.currentDate())
    dialog.hours_input.setText(str(hour_12).zfill(2))
    dialog.minutes_input.setText(now.toString("mm"))
    dialog.seconds_input.setText(now.toString("ss"))
    dialog.ampm_combo.setCurrentText("PM" if hour_24 >= 12 else "AM")
    dialog._update_ok_button_state()

    assert dialog.error_label.text() == "SCHEDULE_TIME_FUTURE"
    assert _ok_button(dialog).isEnabled() is False


def test_schedule_dialog_valid_time_enables_ok(qapp, translator_patch):
    dialog = ScheduleDialog()

    future = QDateTime.currentDateTime().addSecs(120)
    future_hour_24 = future.time().hour()
    future_hour_12 = (future_hour_24 - 1) % 12 + 1

    dialog.calendar.setSelectedDate(future.date())
    dialog.hours_input.setText(str(future_hour_12).zfill(2))
    dialog.minutes_input.setText(future.toString("mm"))
    dialog.seconds_input.setText(future.toString("ss"))
    dialog.ampm_combo.setCurrentText("PM" if future_hour_24 >= 12 else "AM")
    dialog._update_ok_button_state()

    assert dialog.error_label.text() == ""
    assert _ok_button(dialog).isEnabled() is True
    assert dialog.get_time() == dialog.selected_dt


def test_schedule_dialog_get_datetime_12h_conversion(qapp, translator_patch):
    dialog = ScheduleDialog()

    dialog.calendar.setSelectedDate(QDate(2026, 1, 1))
    dialog.hours_input.setText("12")
    dialog.minutes_input.setText("30")
    dialog.seconds_input.setText("45")

    dialog.ampm_combo.setCurrentText("AM")
    am_dt = dialog.get_datetime()
    assert am_dt.time().hour() == 0

    dialog.ampm_combo.setCurrentText("PM")
    pm_dt = dialog.get_datetime()
    assert pm_dt.time().hour() == 12

    dialog.hours_input.setText("01")
    dialog.ampm_combo.setCurrentText("PM")
    one_pm_dt = dialog.get_datetime()
    assert one_pm_dt.time().hour() == 13


def test_schedule_dialog_get_time_none_and_accept(qapp, translator_patch):
    dialog = ScheduleDialog()
    dialog.selected_dt = None

    assert dialog.get_time() is None

    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted


def test_resume_scheduled_session_popup_valid_datetime(qapp, translator_patch):
    popup = ResumeScheduledSessionPopup(scheduled_datetime="2026-01-09T11:50:00")

    label = popup.findChild(QLabel)
    assert label is not None
    assert "RESUMING_SCHEDULED_SESSION_MSG:" in label.text()
    assert "2026-01-09" in label.text()

    start_button = next(
        button
        for button in popup.findChildren(QPushButton)
        if button.text() == "START_NOW"
    )
    start_button.click()
    assert popup.result() == popup.DialogCode.Accepted


def test_resume_scheduled_session_popup_invalid_datetime(qapp, translator_patch):
    popup = ResumeScheduledSessionPopup(scheduled_datetime="not-an-iso-date")

    label = popup.findChild(QLabel)
    assert label is not None
    assert "RESUMING_SCHEDULED_SESSION_MSG:not-an-iso-date" in label.text()

    cancel_button = next(
        button
        for button in popup.findChildren(QPushButton)
        if button.text() == "CANCEL"
    )
    cancel_button.click()
    assert popup.result() == popup.DialogCode.Rejected


def test_resume_scheduled_session_popup_without_datetime(qapp, translator_patch):
    popup = ResumeScheduledSessionPopup(scheduled_datetime=None)

    label = popup.findChild(QLabel)
    assert label is not None
    assert "RESUMING_SCHEDULED_SESSION_MSG:" in label.text()


def test_resume_scheduled_session_popup_iso_conversion_exception_branch(
    qapp, translator_patch
):
    with patch("nxdrive.gui.schedule_dialog.datetime") as mocked_datetime:
        mocked_datetime.fromisoformat.side_effect = ValueError("bad format")
        popup = ResumeScheduledSessionPopup(scheduled_datetime="2026-01-09T11:50:00")

    label = popup.findChild(QLabel)
    assert label is not None
    assert "RESUMING_SCHEDULED_SESSION_MSG:2026-01-09T11:50:00" in label.text()
