from datetime import datetime, timedelta

from ..qt.imports import (
    QCalendarWidget,
    QComboBox,
    QDate,
    QDateTime,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QIntValidator,
    QLabel,
    QLineEdit,
    QPushButton,
    Qt,
    QTime,
    QVBoxLayout,
)
from ..translator import Translator

__all__ = ["ScheduleDialog", "ResumeScheduledSessionPopup"]


class ScheduleDialog(QDialog):
    """Dialog to select a custom date and time."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(Translator.get("SCHEDULE_PICK_DATETIME"))
        self.resize(300, 350)

        layout = QVBoxLayout(self)

        self.calendar = QCalendarWidget()
        self.calendar.setMinimumDate(QDate.currentDate())
        self.calendar.setMaximumDate(QDate.currentDate().addDays(365))
        layout.addWidget(self.calendar)

        # Time input fields
        time_layout = QHBoxLayout()
        current_datetime = datetime.now()
        current_datetime = current_datetime + timedelta(
            minutes=2
        )  # Default to 2 mins in the future
        current_hour = (current_datetime.hour - 1) % 12 + 1
        current_minute = current_datetime.minute
        current_second = current_datetime.second
        current_ampm = "PM" if current_datetime.hour >= 12 else "AM"

        self.hours_input = QLineEdit()
        self.hours_input.setPlaceholderText("HH")
        self.hours_input.setValidator(QIntValidator(0, 12))
        self.hours_input.setText(str(current_hour).zfill(2))
        self.hours_input.setMaxLength(2)
        self.hours_input.setFixedWidth(30)

        self.minutes_input = QLineEdit()
        self.minutes_input.setPlaceholderText("MM")
        self.minutes_input.setValidator(QIntValidator(0, 59))
        self.minutes_input.setText(str(current_minute).zfill(2))
        self.minutes_input.setMaxLength(2)
        self.minutes_input.setFixedWidth(30)

        self.seconds_input = QLineEdit()
        self.seconds_input.setPlaceholderText("SS")
        self.seconds_input.setValidator(QIntValidator(0, 59))
        self.seconds_input.setText(str(current_second).zfill(2))
        self.seconds_input.setMaxLength(2)
        self.seconds_input.setFixedWidth(30)

        self.ampm_combo = QComboBox()
        self.ampm_combo.addItems(["AM", "PM"])
        self.ampm_combo.setCurrentText(current_ampm)

        time_layout.addWidget(self.hours_input)
        time_layout.addWidget(QLabel(Translator.get("SCHEDULE_HOURS")))
        time_layout.addWidget(self.minutes_input)
        time_layout.addWidget(QLabel(Translator.get("SCHEDULE_MINUTES")))
        time_layout.addWidget(self.seconds_input)
        time_layout.addWidget(QLabel(Translator.get("SCHEDULE_SECONDS")))
        time_layout.addWidget(self.ampm_combo)

        layout.addLayout(time_layout)

        # Error label
        self.error_label = QLabel()
        self.error_label.setVisible(False)

        layout.addWidget(self.error_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        # Validation connections
        self.hours_input.textChanged.connect(self._update_ok_button_state)
        self.minutes_input.textChanged.connect(self._update_ok_button_state)
        self.seconds_input.textChanged.connect(self._update_ok_button_state)
        self.ampm_combo.currentIndexChanged.connect(self._update_ok_button_state)
        self.calendar.selectionChanged.connect(self._update_ok_button_state)

        self._update_ok_button_state()

    def _update_ok_button_state(self) -> None:
        """Enable OK button only if time is valid and in the future if today."""
        h_str = self.hours_input.text()
        m_str = self.minutes_input.text()
        s_str = self.seconds_input.text()

        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)

        # Validating hours input
        if h_str and (int(h_str) < 0 or int(h_str) > 12):
            self.error_label.setText(Translator.get("SCHEDULE_INVALID_HOURS"))
            self.error_label.setVisible(True)
            if ok_button:
                ok_button.setEnabled(False)
            return

        # Validating minutes input
        if m_str and (int(m_str) < 0 or int(m_str) > 59):
            self.error_label.setText(Translator.get("SCHEDULE_INVALID_MINUTES"))
            self.error_label.setVisible(True)
            if ok_button:
                ok_button.setEnabled(False)
            return

        # Validating seconds input
        if s_str and (int(s_str) < 0 or int(s_str) > 59):
            self.error_label.setText(Translator.get("SCHEDULE_INVALID_SECONDS"))
            self.error_label.setVisible(True)
            if ok_button:
                ok_button.setEnabled(False)
            return

        self.selected_dt = self.get_datetime()
        if not self.selected_dt.isValid():
            self.error_label.setText(Translator.get("SCHEDULE_INVALID_DATETIME"))
            self.error_label.setVisible(True)
            if ok_button:
                ok_button.setEnabled(False)
            return

        # If today, must be >= 1 min from now
        if self.selected_dt.date() == QDate.currentDate():
            if self.selected_dt < QDateTime.currentDateTime().addSecs(60):
                self.error_label.setText(Translator.get("SCHEDULE_TIME_FUTURE"))
                self.error_label.setVisible(True)
                if ok_button:
                    ok_button.setEnabled(False)
                return

        self.error_label.setText("")
        self.error_label.setVisible(False)

        if ok_button:
            ok_button.setEnabled(True)

    def get_datetime(self) -> QDateTime:
        """Return the selected date and time."""
        date = self.calendar.selectedDate()
        h = int(self.hours_input.text() or 0)
        m = int(self.minutes_input.text() or 0)
        s = int(self.seconds_input.text() or 0)
        is_pm = self.ampm_combo.currentText() == "PM"

        # Convert 12h to 24h
        if is_pm:
            if h < 12:
                h += 12
        elif h == 12:
            h = 0

        return QDateTime(date, QTime(h, m, s))

    def get_time(self) -> QDateTime | None:
        """Return the selected time value. Or custom date time string."""
        if self.selected_dt is not None:
            return self.selected_dt

    def accept(self) -> None:
        """Close the dialog."""
        super().accept()


class ResumeScheduledSessionPopup(QDialog):
    """Popup to ask the user if they want to resume a scheduled session."""

    def __init__(self, parent=None, scheduled_datetime: str | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Resuming Scheduled Session")

        layout = QVBoxLayout(self)

        formatted_dt = ""
        if scheduled_datetime:
            try:
                dt = datetime.fromisoformat(scheduled_datetime)
                formatted_dt = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                formatted_dt = scheduled_datetime

        message = QLabel()
        message.setTextFormat(Qt.TextFormat.RichText)
        message.setText(
            f"<p style='line-height: 150%;'>"
            f"Start transfer now ?<br>"
            f"This transfer is scheduled for {formatted_dt}."
            f"</p>"
        )

        button_layout = QHBoxLayout()

        cancel_button = QPushButton()
        cancel_button.setText("Cancel")
        cancel_button.clicked.connect(self.reject)

        start_button = QPushButton()
        start_button.setText("Start Now")
        start_button.clicked.connect(self.accept)

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(start_button)

        layout.addWidget(message)
        layout.addLayout(button_layout)
