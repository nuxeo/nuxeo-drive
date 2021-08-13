from typing import Optional

from ..constants import WINDOWS
from ..qt import constants as qt
from ..qt.imports import QKeyEvent, QQuickView, QQuickWindow, QWindow

inherited_base_class = QQuickView if WINDOWS else QQuickWindow


class CustomWindow(inherited_base_class):  # type: ignore
    def __init__(self, parent: Optional[QWindow] = None) -> None:
        super().__init__(parent=parent)
        self.visibilityChanged.connect(self._handle_visibility_change)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Did the user press the Escape key?
        if event.key() == qt.Key_Escape:
            self.showNormal()
        else:
            super().keyPressEvent(event)

    def _handle_visibility_change(self, visibility: QWindow.Visibility) -> None:
        if visibility == QWindow.Visibility.FullScreen:
            self.showMaximized()
