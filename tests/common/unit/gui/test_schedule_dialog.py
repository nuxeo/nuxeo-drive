"""Deterministic unit tests for the scheduling dialogs."""

from datetime import datetime as PythonDateTime
from unittest.mock import Mock, call

import pytest

from nxdrive.drive.gui import schedule_dialog as schedule_dialog_module
from nxdrive.drive.qt.imports import (
    QCoreApplication,
    QDate,
    QDateTime,
    QDialog,
    QDialogButtonBox,
    QEvent,
    QIntValidator,
    QLabel,
    QPushButton,
    Qt,
    QTime,
)

TODAY = QDate(2035, 5, 10)
NOW = QDateTime(TODAY, QTime(10, 20, 30))
PYTHON_NOW = PythonDateTime(2035, 5, 10, 10, 20, 30)

TRANSLATIONS = {
    "SCHEDULE_PICK_DATETIME": "Schedule date and time",
    "SCHEDULE_HOURS": "Hours",
    "SCHEDULE_MINUTES": "Minutes",
    "SCHEDULE_SECONDS": "Seconds",
    "SCHEDULE_INVALID_HOURS": "Invalid hours",
    "SCHEDULE_INVALID_MINUTES": "Invalid minutes",
    "SCHEDULE_INVALID_SECONDS": "Invalid seconds",
    "SCHEDULE_INVALID_DATETIME": "Invalid date and time",
    "SCHEDULE_TIME_FUTURE": "Choose a time at least one minute ahead",
    "RESUMING_SCHEDULED_SESSION_TITLE": "Resume scheduled session",
    "RESUMING_SCHEDULED_SESSION_MSG": "Resume the session scheduled for %1.",
    "CANCEL": "Cancel",
    "START_NOW": "Start now",
}


class FrozenDateTime(PythonDateTime):
    """Provide a stable clock while retaining the real ISO parser."""

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return PYTHON_NOW
        return PYTHON_NOW.replace(tzinfo=tz)

    @classmethod
    def fromisoformat(cls, date_string):
        return PythonDateTime.fromisoformat(date_string)


def _translate(label, *, values=None):
    """Return deterministic translations with Qt-style value substitution."""
    translated = TRANSLATIONS.get(label, label)
    for index, value in enumerate(values or [], start=1):
        translated = translated.replace(f"%{index}", str(value))
    return translated


@pytest.fixture(autouse=True)
def deterministic_dependencies(monkeypatch):
    """Freeze all time sources and replace translation lookup for every test."""
    translator_get = Mock(side_effect=_translate)
    monkeypatch.setattr(
        schedule_dialog_module.Translator,
        "get",
        staticmethod(translator_get),
    )
    monkeypatch.setattr(schedule_dialog_module, "datetime", FrozenDateTime)

    qdate_api = Mock(spec=QDate)
    qdate_api.currentDate.return_value = TODAY
    monkeypatch.setattr(schedule_dialog_module, "QDate", qdate_api)

    qdatetime_api = Mock(
        spec=QDateTime,
        side_effect=lambda *args, **kwargs: QDateTime(*args, **kwargs),
    )
    qdatetime_api.currentDateTime.return_value = NOW
    monkeypatch.setattr(schedule_dialog_module, "QDateTime", qdatetime_api)

    return translator_get


@pytest.fixture
def keep_widget(qapp):
    """Track widgets and dispose of them before the QApplication is torn down."""
    widgets = []

    def keep(widget):
        widgets.append(widget)
        return widget

    yield keep

    for widget in reversed(widgets):
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


@pytest.fixture
def dialog(keep_widget):
    """Create a ScheduleDialog backed by the shared QApplication."""
    return keep_widget(schedule_dialog_module.ScheduleDialog())


def _ok_button(dialog):
    button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
    assert button is not None
    return button


def _set_valid_selection(
    dialog,
    *,
    date=None,
    hour=9,
    minute=15,
    second=45,
    ampm="AM",
):
    dialog.calendar.setSelectedDate(date or TODAY.addDays(1))
    dialog.hours_input.setText(f"{hour:02d}")
    dialog.minutes_input.setText(f"{minute:02d}")
    dialog.seconds_input.setText(f"{second:02d}")
    dialog.ampm_combo.setCurrentText(ampm)
    dialog._update_ok_button_state()


def _assert_validation_error(dialog, expected_message):
    assert dialog.error_label.text() == expected_message
    assert not dialog.error_label.isHidden()
    assert not _ok_button(dialog).isEnabled()


def _popup_message(popup):
    labels = popup.findChildren(QLabel)
    assert len(labels) == 1
    return labels[0]


def _popup_buttons(popup):
    return {button.text(): button for button in popup.findChildren(QPushButton)}


def test_schedule_dialog_init_builds_deterministic_valid_form(
    dialog, deterministic_dependencies
):
    assert dialog.windowModality() == Qt.WindowModality.WindowModal
    assert dialog.windowTitle() == TRANSLATIONS["SCHEDULE_PICK_DATETIME"]
    assert dialog.selected_dt == QDateTime(TODAY, QTime(10, 22, 30))

    assert dialog.calendar.minimumDate() == TODAY
    assert dialog.calendar.maximumDate() == TODAY.addMonths(1)
    assert dialog.calendar.selectedDate() == TODAY

    assert dialog.hours_input.text() == "10"
    assert dialog.minutes_input.text() == "22"
    assert dialog.seconds_input.text() == "30"
    assert dialog.ampm_combo.currentText() == "AM"
    assert [dialog.ampm_combo.itemText(index) for index in range(2)] == ["AM", "PM"]

    expected_inputs = (
        (dialog.hours_input, "HH", 12),
        (dialog.minutes_input, "MM", 59),
        (dialog.seconds_input, "SS", 59),
    )
    for line_edit, placeholder, maximum in expected_inputs:
        validator = line_edit.validator()
        assert isinstance(validator, QIntValidator)
        assert validator.bottom() == 0
        assert validator.top() == maximum
        assert line_edit.placeholderText() == placeholder
        assert line_edit.maxLength() == 2
        assert line_edit.minimumWidth() == 30
        assert line_edit.maximumWidth() == 30

    label_texts = {label.text() for label in dialog.findChildren(QLabel)}
    assert {"Hours", "Minutes", "Seconds"}.issubset(label_texts)
    assert dialog.error_label.text() == ""
    assert dialog.error_label.isHidden()
    assert _ok_button(dialog).isEnabled()

    deterministic_dependencies.assert_any_call("SCHEDULE_PICK_DATETIME")
    deterministic_dependencies.assert_any_call("SCHEDULE_HOURS")
    deterministic_dependencies.assert_any_call("SCHEDULE_MINUTES")
    deterministic_dependencies.assert_any_call("SCHEDULE_SECONDS")


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "translation_key"),
    [
        ("hours_input", "", "SCHEDULE_INVALID_HOURS"),
        ("hours_input", "x", "SCHEDULE_INVALID_HOURS"),
        ("hours_input", "-1", "SCHEDULE_INVALID_HOURS"),
        ("hours_input", "13", "SCHEDULE_INVALID_HOURS"),
        ("minutes_input", "", "SCHEDULE_INVALID_MINUTES"),
        ("minutes_input", "x", "SCHEDULE_INVALID_MINUTES"),
        ("minutes_input", "-1", "SCHEDULE_INVALID_MINUTES"),
        ("minutes_input", "60", "SCHEDULE_INVALID_MINUTES"),
        ("seconds_input", "", "SCHEDULE_INVALID_SECONDS"),
        ("seconds_input", "x", "SCHEDULE_INVALID_SECONDS"),
        ("seconds_input", "-1", "SCHEDULE_INVALID_SECONDS"),
        ("seconds_input", "60", "SCHEDULE_INVALID_SECONDS"),
    ],
    ids=[
        "empty-hours",
        "non-numeric-hours",
        "hours-below-range",
        "hours-above-range",
        "empty-minutes",
        "non-numeric-minutes",
        "minutes-below-range",
        "minutes-above-range",
        "empty-seconds",
        "non-numeric-seconds",
        "seconds-below-range",
        "seconds-above-range",
    ],
)
def test_update_ok_button_state_rejects_invalid_time_fields(
    dialog, field_name, invalid_value, translation_key
):
    _set_valid_selection(dialog)
    field = getattr(dialog, field_name)
    field.setText(invalid_value)
    assert field.text() == invalid_value

    dialog._update_ok_button_state()

    _assert_validation_error(dialog, TRANSLATIONS[translation_key])


def test_update_ok_button_state_rejects_invalid_datetime(dialog, monkeypatch):
    _set_valid_selection(dialog)
    invalid_datetime = QDateTime()
    monkeypatch.setattr(
        dialog,
        "get_datetime",
        Mock(return_value=invalid_datetime),
    )

    dialog._update_ok_button_state()

    assert dialog.selected_dt is invalid_datetime
    _assert_validation_error(dialog, TRANSLATIONS["SCHEDULE_INVALID_DATETIME"])


@pytest.mark.parametrize(
    ("hour", "minute", "second"),
    [(10, 20, 29), (10, 21, 29)],
    ids=["past", "future-but-too-soon"],
)
def test_update_ok_button_state_rejects_today_before_minimum_delay(
    dialog, hour, minute, second
):
    _set_valid_selection(
        dialog,
        date=TODAY,
        hour=hour,
        minute=minute,
        second=second,
        ampm="AM",
    )

    _assert_validation_error(dialog, TRANSLATIONS["SCHEDULE_TIME_FUTURE"])


def test_update_ok_button_state_accepts_exact_minimum_delay(dialog):
    _set_valid_selection(
        dialog,
        date=TODAY,
        hour=10,
        minute=21,
        second=30,
        ampm="AM",
    )

    assert dialog.selected_dt == NOW.addSecs(60)
    assert dialog.error_label.text() == ""
    assert dialog.error_label.isHidden()
    assert _ok_button(dialog).isEnabled()


def test_update_ok_button_state_accepts_valid_future_date(dialog):
    future_date = TODAY.addDays(1)
    _set_valid_selection(
        dialog,
        date=future_date,
        hour=12,
        minute=5,
        second=6,
        ampm="PM",
    )

    assert dialog.selected_dt == QDateTime(future_date, QTime(12, 5, 6))
    assert dialog.error_label.text() == ""
    assert dialog.error_label.isHidden()
    assert _ok_button(dialog).isEnabled()


@pytest.mark.parametrize(
    ("hour", "ampm", "expected_hour"),
    [
        (1, "AM", 1),
        (1, "PM", 13),
        (12, "AM", 0),
        (12, "PM", 12),
    ],
    ids=["am", "pm", "midnight-12am", "noon-12pm"],
)
def test_get_datetime_converts_am_and_pm(dialog, hour, ampm, expected_hour):
    selected_date = TODAY.addDays(1)
    _set_valid_selection(
        dialog,
        date=selected_date,
        hour=hour,
        minute=34,
        second=56,
        ampm=ampm,
    )

    result = dialog.get_datetime()

    assert result.date() == selected_date
    assert result.time() == QTime(expected_hour, 34, 56)


def test_get_time_returns_none_without_a_selection(dialog):
    dialog.selected_dt = None

    assert dialog.get_time() is None


def test_get_time_returns_selected_datetime(dialog):
    selected_datetime = QDateTime(TODAY.addDays(1), QTime(16, 17, 18))
    dialog.selected_dt = selected_datetime

    assert dialog.get_time() is selected_datetime


def test_accept_marks_dialog_as_accepted(dialog):
    dialog.setResult(42)

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted.value


def test_schedule_dialog_button_box_connections(keep_widget):
    accepted_dialog = keep_widget(schedule_dialog_module.ScheduleDialog())
    _set_valid_selection(accepted_dialog)
    _ok_button(accepted_dialog).click()
    assert accepted_dialog.result() == QDialog.DialogCode.Accepted.value

    rejected_dialog = keep_widget(schedule_dialog_module.ScheduleDialog())
    rejected_dialog.accept()
    cancel_button = rejected_dialog.button_box.button(
        QDialogButtonBox.StandardButton.Cancel
    )
    assert cancel_button is not None
    cancel_button.click()
    assert rejected_dialog.result() == QDialog.DialogCode.Rejected.value


def test_resume_popup_without_datetime(keep_widget, deterministic_dependencies):
    popup = keep_widget(schedule_dialog_module.ResumeScheduledSessionPopup())
    message = _popup_message(popup)

    assert popup.windowModality() == Qt.WindowModality.WindowModal
    assert popup.windowTitle() == TRANSLATIONS["RESUMING_SCHEDULED_SESSION_TITLE"]
    assert message.textFormat() == Qt.TextFormat.RichText
    assert message.text() == (
        "<p style='line-height: 150%;'>Resume the session scheduled for .</p>"
    )
    assert set(_popup_buttons(popup)) == {"Cancel", "Start now"}
    assert (
        call("RESUMING_SCHEDULED_SESSION_MSG", values=[""])
        in deterministic_dependencies.call_args_list
    )


def test_resume_popup_formats_valid_iso_datetime(
    keep_widget, deterministic_dependencies
):
    popup = keep_widget(
        schedule_dialog_module.ResumeScheduledSessionPopup(
            scheduled_datetime="2035-06-01T14:15:16"
        )
    )

    assert "2035-06-01 14:15:16" in _popup_message(popup).text()
    deterministic_dependencies.assert_any_call(
        "RESUMING_SCHEDULED_SESSION_MSG",
        values=["2035-06-01 14:15:16"],
    )


def test_resume_popup_falls_back_to_invalid_datetime(
    keep_widget, deterministic_dependencies
):
    invalid_datetime = "not-an-iso-datetime"
    popup = keep_widget(
        schedule_dialog_module.ResumeScheduledSessionPopup(
            scheduled_datetime=invalid_datetime
        )
    )

    assert invalid_datetime in _popup_message(popup).text()
    deterministic_dependencies.assert_any_call(
        "RESUMING_SCHEDULED_SESSION_MSG",
        values=[invalid_datetime],
    )


def test_resume_popup_escapes_datetime_before_translation(
    keep_widget, deterministic_dependencies
):
    unsafe_datetime = '<b>now</b> & "later"'
    escaped_datetime = "&lt;b&gt;now&lt;/b&gt; &amp; &quot;later&quot;"
    popup = keep_widget(
        schedule_dialog_module.ResumeScheduledSessionPopup(
            scheduled_datetime=unsafe_datetime
        )
    )
    message_text = _popup_message(popup).text()

    assert unsafe_datetime not in message_text
    assert escaped_datetime in message_text
    deterministic_dependencies.assert_any_call(
        "RESUMING_SCHEDULED_SESSION_MSG",
        values=[escaped_datetime],
    )


def test_resume_popup_button_connections(keep_widget):
    accepted_popup = keep_widget(
        schedule_dialog_module.ResumeScheduledSessionPopup(
            scheduled_datetime="2035-06-01T14:15:16"
        )
    )
    _popup_buttons(accepted_popup)["Start now"].click()
    assert accepted_popup.result() == QDialog.DialogCode.Accepted.value

    rejected_popup = keep_widget(schedule_dialog_module.ResumeScheduledSessionPopup())
    rejected_popup.accept()
    _popup_buttons(rejected_popup)["Cancel"].click()
    assert rejected_popup.result() == QDialog.DialogCode.Rejected.value
