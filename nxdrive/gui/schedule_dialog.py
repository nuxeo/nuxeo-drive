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


class CustomDateTimeDialog(QDialog):
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
        current_hour = current_datetime.hour % 12
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

        selected_dt = self.get_datetime()
        if not selected_dt.isValid():
            self.error_label.setText(Translator.get("SCHEDULE_INVALID_DATETIME"))
            self.error_label.setVisible(True)
            if ok_button:
                ok_button.setEnabled(False)
            return

        # If today, must be >= 1 min from now
        if selected_dt.date() == QDate.currentDate():
            if selected_dt < QDateTime.currentDateTime().addSecs(60):
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


class ScheduleDialog(QDialog):
    """Dialog for scheduling a transfer later."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.custom_datetime = None

        self.setWindowTitle(Translator.get("SCHEDULE_TRANSFER"))
        self.resize(400, 180)

        layout = QVBoxLayout(self)

        hlayout = QHBoxLayout()

        # Pick custom date button
        btn_vlayout = QVBoxLayout()
        custom_label = QLabel(Translator.get("SCHEDULE_SELECT_CUSTOM_DATETIME"))
        self.pick_datetime_btn = QPushButton(Translator.get("SCHEDULE_PICK_DATETIME"))
        self.pick_datetime_btn.clicked.connect(self._open_custom_picker)
        btn_vlayout.addWidget(custom_label)
        btn_vlayout.addWidget(self.pick_datetime_btn)

        # Condition selection
        cond_vlayout = QVBoxLayout()
        cond_label = QLabel(Translator.get("SCHEDULE_SELECT_CONDITION"))
        self.condition_combo = QComboBox()
        self.condition_combo.addItem(Translator.get("NONE"))
        self.condition_combo.addItems(
            [
                Translator.get("SCHEDULE_AFTER_7PM"),
                Translator.get("SCHEDULE_WEEKENDS"),
            ]
        )
        cond_vlayout.addWidget(cond_label)
        cond_vlayout.addWidget(self.condition_combo)

        hlayout.addLayout(btn_vlayout)
        hlayout.addLayout(cond_vlayout)

        # Mutual exclusion logic
        self.condition_combo.currentIndexChanged.connect(self._on_condition_changed)

        layout.addLayout(hlayout)

        self.custom_display_label = QLabel("")
        self.custom_display_label.hide()
        layout.addWidget(self.custom_display_label)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _open_custom_picker(self) -> None:
        """Open the custom date time picker."""
        dialog = CustomDateTimeDialog(self)
        if dialog.exec():
            self.custom_datetime = dialog.get_datetime()

            self.condition_combo.blockSignals(True)
            self.condition_combo.setCurrentIndex(0)
            self.condition_combo.blockSignals(False)

            # Update display label
            self.custom_display_label.setText(
                Translator.get(
                    "SCHEDULE_CUSTOM_DISPLAY",
                    values=[
                        Translator.format_datetime(self.custom_datetime.toPyDateTime())
                    ],
                )
            )
            self.custom_display_label.show()
        else:
            self.custom_datetime = None

    def _on_condition_changed(self, index: int) -> None:
        """Reset time combo if a condition is selected. Also reset custom datetime."""
        if index > 0:
            self.custom_datetime = None
            self.custom_display_label.hide()

    def get_time(self) -> str | None:
        """Return the selected time value. Or custom date time string."""
        if self.custom_datetime is not None:
            return self.custom_datetime.toString("yyyy-MM-dd HH:mm:ss")

    def get_condition(self) -> str:
        """Return the selected condition value."""
        return self.condition_combo.currentText()

    def accept(self) -> None:
        """Close the dialog."""
        super().accept()
