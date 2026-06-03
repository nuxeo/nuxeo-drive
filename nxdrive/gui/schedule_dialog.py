from ..qt.imports import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)
from ..translator import Translator


class ScheduleDialog(QDialog):
    """Dialog for scheduling a transfer later."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle(Translator.get("SCHEDULE_TRANSFER"))
        self.resize(400, 180)

        layout = QVBoxLayout(self)

        hlayout = QHBoxLayout()

        # Time selection
        time_vlayout = QVBoxLayout()
        time_label = QLabel(Translator.get("SCHEDULE_SELECT_TIME"))
        self.time_combo = QComboBox()
        self.time_combo.addItem(Translator.get("NONE"))
        self.time_combo.addItems(
            [
                Translator.get("SCHEDULE_1_MIN"),
                Translator.get("SCHEDULE_5_MIN"),
                Translator.get("SCHEDULE_1_HOUR"),
                Translator.get("SCHEDULE_2_HOURS"),
                Translator.get("SCHEDULE_5_HOURS"),
                Translator.get("SCHEDULE_12_HOURS"),
                Translator.get("SCHEDULE_1_DAY"),
                Translator.get("SCHEDULE_1_WEEK"),
            ]
        )
        time_vlayout.addWidget(time_label)
        time_vlayout.addWidget(self.time_combo)

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

        hlayout.addLayout(time_vlayout)
        hlayout.addLayout(cond_vlayout)

        # Mutual exclusion logic
        self.time_combo.currentIndexChanged.connect(self._on_time_changed)
        self.condition_combo.currentIndexChanged.connect(self._on_condition_changed)

        layout.addLayout(hlayout)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _on_time_changed(self, index: int) -> None:
        """Reset condition combo if a time is selected."""
        if index > 0:
            self.condition_combo.blockSignals(True)
            self.condition_combo.setCurrentIndex(0)
            self.condition_combo.blockSignals(False)

    def _on_condition_changed(self, index: int) -> None:
        """Reset time combo if a condition is selected."""
        if index > 0:
            self.time_combo.blockSignals(True)
            self.time_combo.setCurrentIndex(0)
            self.time_combo.blockSignals(False)

    def get_time(self) -> str:
        """Return the selected time value."""
        return self.time_combo.currentText()

    def get_time_index(self) -> int:
        """Return the selected time index."""
        return self.time_combo.currentIndex()

    def get_condition(self) -> str:
        """Return the selected condition value."""
        return self.condition_combo.currentText()

    def accept(self) -> None:
        """Close the dialog."""
        super().accept()
