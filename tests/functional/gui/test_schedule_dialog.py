"""Functional tests for nxdrive.gui.schedule_dialog module."""

from unittest.mock import patch

import pytest
from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import QApplication, QPushButton

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


def test_schedule_dialog_future_selection_allows_accept(qapp, translator_patch):
    dialog = ScheduleDialog()

    future = QDateTime.currentDateTime().addDays(1)
    dialog.calendar.setSelectedDate(future.date())
    dialog.hours_input.setText("09")
    dialog.minutes_input.setText("30")
    dialog.seconds_input.setText("15")
    dialog.ampm_combo.setCurrentText("AM")
    dialog._update_ok_button_state()

    ok_button = dialog.button_box.button(dialog.button_box.StandardButton.Ok)
    assert ok_button is not None
    assert ok_button.isEnabled() is True

    ok_button.click()
    assert dialog.result() == dialog.DialogCode.Accepted


def test_resume_popup_cancel_and_start_buttons(qapp, translator_patch):
    popup = ResumeScheduledSessionPopup(scheduled_datetime="2026-01-09T11:50:00")
    buttons = popup.findChildren(QPushButton)

    cancel_button = next(button for button in buttons if button.text() == "CANCEL")
    cancel_button.click()
    assert popup.result() == popup.DialogCode.Rejected

    popup = ResumeScheduledSessionPopup(scheduled_datetime="2026-01-09T11:50:00")
    buttons = popup.findChildren(QPushButton)
    start_button = next(button for button in buttons if button.text() == "START_NOW")
    start_button.click()
    assert popup.result() == popup.DialogCode.Accepted
