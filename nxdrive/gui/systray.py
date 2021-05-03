from logging import getLogger
from typing import TYPE_CHECKING

from ..constants import MAC
from ..qt import constants as qt
from ..qt.imports import QApplication, QEvent, QMenu, QQuickView, QSystemTrayIcon
from ..translator import Translator

if TYPE_CHECKING:
    from .application import Application  # noqa

log = getLogger(__name__)

__all__ = ("DriveSystrayIcon",)


class DriveSystrayIcon(QSystemTrayIcon):
    def __init__(self, application: "Application", /) -> None:
        super().__init__(application)
        self.application = application
        self.messageClicked.connect(self.application.message_clicked)
        self.activated.connect(self.handle_mouse_click)

        # Windows bug: the systray icon is still visible
        self.application.aboutToQuit.connect(self.hide)

        if not MAC:
            # On macOS, only the left click is detected, so the context
            # menu is useless.  It is better to not define it else it
            # will show up every click on the systray icon.
            self.setContextMenu(self.get_context_menu())

    def handle_mouse_click(self, reason: int, /) -> None:
        """
        Handle any mouse click on the systray icon.
        It is not needed to handle the right click as it
        is the default behavior and will open the context
        menu (right click menu).

        Note: only the left click is detected on macOS.
        """
        if reason == qt.Trigger:
            # On left click, open the usual menu with engines and sync files
            # If it is already open, we close it
            if self.application.systray_window.isVisible():
                self.application.hide_systray()
            else:
                self.application.show_systray()
        elif reason == qt.MiddleClick:
            # On middle click, open settings.  Yeah, it rocks!
            self._open_settings()

    def _open_settings(self) -> None:
        """Open the settings window."""
        self.application.show_settings("Advanced")

    def get_context_menu(self) -> QMenu:
        """
        Create the context menu.
        It shows up on left click.

        Note: icons will not be displayed on every GNU/Linux
        distributions, it depends on the graphical environment.
        """

        style = QApplication.style()
        menu = QMenu()
        menu.addAction(
            style.standardIcon(qt.SP_FileDialogInfoView),
            Translator.get("SETTINGS"),
            self._open_settings,
        )
        menu.addSeparator()
        menu.addAction(
            style.standardIcon(qt.SP_MessageBoxQuestion),
            Translator.get("HELP"),
            self.application.open_help,
        )
        menu.addSeparator()
        menu.addAction(
            style.standardIcon(qt.SP_DialogCloseButton),
            Translator.get("QUIT"),
            self.application.exit_app,
        )

        return menu


class SystrayWindow(QQuickView):
    def event(self, event: QEvent, /) -> bool:
        if event.type() == qt.FocusOut or (
            event.type() == qt.MouseButtonPress
            and not self.geometry().contains(event.screenPos().toPoint())
        ):
            # The click was outside of the systray
            self.hide()
        return super().event(event)
