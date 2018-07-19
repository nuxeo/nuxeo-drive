# coding: utf-8
import os

from PyQt5.QtCore import QSize, QUrl, Qt, pyqtSlot
from PyQt5.QtGui import QColor, QCursor
from PyQt5.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from .dialog import QMLDriveApi
from .view import FileModel, NuxeoView
from ..constants import MAC
from ..options import Options
from ..translator import Translator
from ..updater.constants import (
    UPDATE_STATUS_DOWNGRADE_NEEDED,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_UPDATING,
)
from ..utils import find_resource

from logging import getLogger

log = getLogger(__name__)

__all__ = ("DriveSystrayIcon",)


class SystrayView(NuxeoView):
    def __init__(self, application: "Application", icon: QSystemTrayIcon) -> None:
        super().__init__(application, QMLSystrayApi(application, self))

        self.icon = icon
        self.setColor(QColor.fromRgba64(0, 0, 0, 0))
        self.size = QSize(300, 370)
        self.setMinimumSize(self.size)
        self.setMaximumSize(self.size)

        self.engine_model.statusChanged.connect(self.update_status)
        self.file_model = FileModel()
        self.setFlags(Qt.FramelessWindowHint | Qt.Popup)

        context = self.rootContext()
        context.setContextProperty("Systray", self)
        context.setContextProperty("FileModel", self.file_model)

        self.init()

    def init(self) -> None:
        """
        Resize and move the system tray menu accordingly to
        the system tray icon position.
        """
        super().init()
        self.setSource(QUrl(find_resource("qml", "Systray.qml")))
        self.rootObject().getLastFiles.connect(self.get_last_files)
        self.rootObject().hide.connect(self.hide)

        if self.icon.application.manager.get_engines():
            current_uid = self.engine_model.engines_uid[0]
            self.get_last_files(current_uid)
            self.update_status(self.engine_model.engines[current_uid])

        icon = self.icon.geometry()
        pos_x = max(0, icon.x() + icon.width() - self.size.width())
        pos_y = icon.y() - self.size.height()
        if pos_y < 0:
            pos_y = icon.y() + icon.height()
        self.set_tray_position(pos_x, pos_y)

    @pyqtSlot(str)
    def get_last_files(self, uid: str) -> None:
        files = self.api.get_last_files(uid, 10, "")
        self.file_model.empty()
        self.file_model.addFiles(files)

    def update_status(self, engine: "Engine") -> None:
        state = message = submessage = ""

        update_status = self.application.manager.updater.last_status
        conflicts = engine.get_conflicts()
        errors = engine.get_errors()

        if engine.has_invalid_credentials():
            state = "auth_expired"
        elif update_status[0] == UPDATE_STATUS_DOWNGRADE_NEEDED:
            state = "downgrade"
            message = update_status[1]
            submessage = self.application.manager.updater.nature
        elif update_status[0] == UPDATE_STATUS_UPDATE_AVAILABLE:
            state = "update"
            message = update_status[1]
            submessage = self.application.manager.updater.nature
        elif update_status[0] == UPDATE_STATUS_UPDATING:
            state = "updating"
            message = update_status[1]
            submessage = update_status[2]
        elif engine.is_paused():
            state = "suspended"
        elif engine.is_syncing():
            state = "syncing"
        elif conflicts:
            state = "conflicted"
            message = str(len(conflicts))
        elif errors:
            state = "error"
            message = str(len(errors))
        self.rootObject().setStatus.emit(state, message, submessage)

    def set_tray_position(self, x: int, y: int) -> None:
        self.rootObject().setTrayPosition.emit(x, y)

    @pyqtSlot()
    def popup(self) -> None:
        self.show()
        self.raise_()


class DriveSystrayIcon(QSystemTrayIcon):

    __menu_left = None
    __menu_right = None
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
            self.setContextMenu(self.menu_right)

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
            self.menu_left.popup()
        elif reason == QSystemTrayIcon.MiddleClick:
            # On middle click, open settings.  Yeah, it rocks!
            self.application.show_settings()

    @property
    def menu_left(self) -> SystrayView:
        """
        Create the usual menu with engines and sync files.
        It shows up on left click.
        """

        if not self.__menu_left:
            self.__menu_left = SystrayView(self.application, self)
        return self.__menu_left

    @property
    def menu_right(self) -> QMenu:
        """
        Create the context menu.
        It shows up on left click.

        Note: icons will not be displayed on every GNU/Linux
        distributions, it depends on the graphical environment.
        """

        if not self.__menu_right:
            style = QApplication.style()
            menu = QMenu()
            menu.addAction(
                Translator.get("SETTINGS"),
                self.application.show_settings,
            )
            menu.addSeparator()
            menu.addAction(
                Translator.get("HELP"),
                self.application.open_help,
            )
            menu.addSeparator()
            menu.addAction(
                Translator.get("QUIT"),
                self.application.quit,
            )
            self.__menu_right = menu

        return self.__menu_right


class QMLSystrayApi(QMLDriveApi):

    menu = None

    @pyqtSlot(str)
    def show_settings(self, page: str) -> None:
        self.dialog.hide()
        super().show_settings(page)

    @pyqtSlot(str)
    def show_conflicts_resolution(self, uid: str) -> None:
        self.dialog.hide()
        super().show_conflicts_resolution(uid)

    @pyqtSlot(str, str)
    def show_metadata(self, uid: str, ref: str) -> None:
        self.dialog.hide()
        super().show_metadata(uid, ref)

    @pyqtSlot(str)
    def open_remote(self, uid: str) -> None:
        self.dialog.hide()
        super().open_remote(uid)

    @pyqtSlot(str, str)
    def open_local(self, uid: str, path: str) -> None:
        self.dialog.hide()
        super().open_local(uid, path)

    @pyqtSlot()
    def open_help(self) -> None:
        self.dialog.hide()
        self._manager.open_help()

    @pyqtSlot(str)
    def trigger_notification(self, id_: str) -> None:
        self.dialog.hide()
        super().trigger_notification(id_)

    @pyqtSlot(bool)
    def suspend(self, start: bool) -> None:
        if start:
            self._manager.resume()
        else:
            self._manager.suspend()

    @pyqtSlot(result=bool)
    def is_paused(self) -> bool:
        return self._manager.is_paused()

    @pyqtSlot(result=bool)
    def need_adv_menu(self) -> bool:
        """
        Do we need to display the left click advanced menu?  Yes if:
          - on debug
          - on macOS
          - when the envar USE_OLD_MENU is set
            (for Unity that does not see right click into the systray)
        """
        return Options.debug or MAC or os.environ.get("USE_OLD_MENU", False)

    @pyqtSlot(str, result=int)
    def get_syncing_count(self, uid: str) -> int:
        count = 0
        engine = self._get_engine(uid)
        if engine:
            count = engine.get_dao().get_syncing_count()
        return count

    @pyqtSlot(str, result=int)
    def get_conflicts_count(self, uid: str) -> int:
        return len(self.get_conflicts(uid))

    @pyqtSlot(str, result=int)
    def get_errors_count(self, uid: str) -> int:
        return len(self.get_errors(uid))

    @pyqtSlot()
    def advanced_systray(self) -> None:
        if not self.need_adv_menu():
            return

        if self.menu:
            return self.menu.popup(QCursor.pos())

        self.menu = QMenu()

        if Options.debug:
            self.application.create_debug_menu(self.menu)

        self.menu.addSeparator()
        self.menu.addAction(Translator.get("SETTINGS"), self.application.show_settings)
        self.menu.addSeparator()
        self.menu.addAction(Translator.get("HELP"), self.application.open_help)
        self.menu.addSeparator()
        self.menu.addAction(Translator.get("QUIT"), self.application.quit)

        self.menu.popup(QCursor.pos())
