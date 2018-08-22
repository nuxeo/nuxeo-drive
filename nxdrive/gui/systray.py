# coding: utf-8
import os
from logging import getLogger

from PyQt5.QtCore import QEvent
from PyQt5.QtQuick import QQuickView
from PyQt5.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from ..constants import MAC
from ..translator import Translator

log = getLogger(__name__)

__all__ = ("DriveSystrayIcon",)


class DriveSystrayIcon(QSystemTrayIcon):

    __context_menu = None
    use_old_menu = MAC or os.environ.get("USE_OLD_MENU", False)

    def __init__(self, application: "Application"):
        super().__init__(application)
        self.application = application
        self.messageClicked.connect(self.application.message_clicked)
        self.activated.connect(self.handle_mouse_click)

        # Windows bug: the systray icon is still visible
        self.application.aboutToQuit.connect(self.hide)

        if not self.use_old_menu:
            # On macOS, only the left click is detected, so the context
            # menu is useless.  It is better to not define it else it
            # will show up every click on the systray icon.
            self.setContextMenu(self.context_menu)

    def handle_mouse_click(self, reason: int) -> None:
        """
        Handle any mouse click on the systray icon.
        It is not needed to handle the right click as it
        is the native behavior and will open the context
        menu (right click menu).

        Note: only the left click is detected on macOS.
        """
        if reason == QSystemTrayIcon.Trigger:
            # On left click, open the usual menu with engines and sync files
            # If it is already open, we close it
            if self.application.systray_window.isVisible():
                self.application.hide_systray()
            else:
                self.application.show_systray()
        elif reason == QSystemTrayIcon.MiddleClick:
            # On middle click, open settings.  Yeah, it rocks!
            self.application.show_settings()

    @property
    def context_menu(self) -> QMenu:
        """
        Create the context menu.
        It shows up on left click.

        Note: icons will not be displayed on every GNU/Linux
        distributions, it depends on the graphical environment.
        """

        if not self.__context_menu:
            style = QApplication.style()
            menu = QMenu()
            menu.addAction(
                style.standardIcon(QStyle.SP_FileDialogInfoView),
                Translator.get("SETTINGS"),
                self.application.show_settings,
            )
            menu.addSeparator()
            menu.addAction(
                style.standardIcon(QStyle.SP_MessageBoxQuestion),
                Translator.get("HELP"),
                self.application.open_help,
            )
            menu.addSeparator()
            menu.addAction(
                style.standardIcon(QStyle.SP_DialogCloseButton),
                Translator.get("QUIT"),
                self.application.quit,
            )
            self.__context_menu = menu

        return self.__context_menu


class SystrayWindow(QQuickView):
    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.FocusOut or (
            event.type() == QEvent.MouseButtonPress
            and not self.geometry().contains(event.screenPos().toPoint())
        ):
            # The click was outside of the systray
            self.hide()
        return super().event(event)
