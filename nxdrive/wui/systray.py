# coding: utf-8
import os
import sys

from PyQt5.QtCore import Qt, QUrl, pyqtSlot
from PyQt5.QtGui import QColor, QCursor
from PyQt5.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from ..constants import MAC
from ..options import Options
from ..updater.constants import (UPDATE_STATUS_DOWNGRADE_NEEDED,
                                 UPDATE_STATUS_UPDATE_AVAILABLE)
from .dialog import WebDriveApi
from .translator import Translator
from .view import FileModel, NuxeoView


class DriveSystrayIcon(QSystemTrayIcon):

    __menu_left = None
    __menu_right = None
    use_old_menu = MAC or os.environ.get('USE_OLD_MENU', False)

    def __init__(self, application):
        super(DriveSystrayIcon, self).__init__(application)
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

    def handle_mouse_click(self, reason):
        """
        Handle any mouse click on the systray icon.
        It is not needed to handle the right click as it
        is the native behavior and will open the context
        menu (right click menu).

        Note: only the left click is detected on macOS.
        """

        if reason == QSystemTrayIcon.Trigger:
            # On left click, open the usual menu with engines and sync files
            self.menu_left.popup(QCursor.pos())
        elif reason == QSystemTrayIcon.MiddleClick:
            # On middle click, open settings.  Yeah, it rocks!
            self.application.show_settings()

    @property
    def menu_left(self):
        """
        Create the usual menu with engines and sync files.
        It shows up on left click.
        """

        if not self.__menu_left:
            self.__menu_left = WebSystray(self, self.application)
        return self.__menu_left

    @property
    def menu_right(self):
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
                style.standardIcon(QStyle.SP_FileDialogInfoView),
                Translator.get('SETTINGS'),
                self.application.show_settings,
            )
            menu.addSeparator()
            menu.addAction(
                style.standardIcon(QStyle.SP_MessageBoxQuestion),
                Translator.get('HELP'),
                self.application.open_help)
            menu.addSeparator()
            menu.addAction(
                style.standardIcon(QStyle.SP_DialogCloseButton),
                Translator.get('QUIT'),
                self.application.quit)
            self.__menu_right = menu

        return self.__menu_right


class WebSystrayApi(WebDriveApi):

    menu = None

    @pyqtSlot(str)
    def show_settings(self, page):
        self.dialog.hide()
        super(WebSystrayApi, self).show_settings(page)

    @pyqtSlot(str)
    def show_conflicts_resolution(self, uid):
        self.dialog.hide()
        super(WebSystrayApi, self).show_conflicts_resolution(uid)

    @pyqtSlot(str, str)
    def show_metadata(self, uid, ref):
        self.dialog.hide()
        super(WebSystrayApi, self).show_metadata(uid, ref)

    @pyqtSlot(str)
    def open_remote(self, uid):
        self.dialog.hide()
        super(WebSystrayApi, self).open_remote(uid)

    @pyqtSlot(str, str)
    def open_local(self, uid, path):
        self.dialog.hide()
        super(WebSystrayApi, self).open_local(uid, path)

    @pyqtSlot()
    def open_help(self):
        self.dialog.hide()
        self._manager.open_help()

    @pyqtSlot(str)
    def trigger_notification(self, id_):
        self.dialog.hide()
        super(WebSystrayApi, self).trigger_notification(id_)

    @pyqtSlot(bool)
    def suspend(self, start):
        if start:
            self._manager.resume()
        else:
            self._manager.suspend()

    @pyqtSlot(result=bool)
    def is_paused(self):
        return self._manager.is_paused()

    @pyqtSlot(result=bool)
    def need_adv_menu(self):
        """
        Do we need to display the left click advanced menu?  Yes if:
          - on debug
          - on macOS
          - when the envar USE_OLD_MENU is set
            (for Unity that does not see right click into the systray)
        """
        return Options.debug or MAC or os.environ.get('USE_OLD_MENU', False)

    @pyqtSlot(str, result=int)
    def get_syncing_count(self, uid):
        count = 0
        engine = self._get_engine(str(uid))
        if engine:
            count = engine.get_dao().get_syncing_count()
        return count

    @pyqtSlot(str, result=int)
    def get_conflicts_count(self, uid):
        return len(self.get_conflicts(uid))

    @pyqtSlot(str, result=int)
    def get_errors_count(self, uid):
        return len(self.get_errors(uid))

    @pyqtSlot()
    def advanced_systray(self):
        if not self.need_adv_menu():
            return

        if self.menu:
            return self.menu.popup(QCursor.pos())

        self.menu = QMenu()

        if Options.debug:
            self.application.create_debug_menu(self.menu)

        self.menu.addSeparator()
        self.menu.addAction(Translator.get('SETTINGS'),
                            self.application.show_settings)
        self.menu.addSeparator()
        self.menu.addAction(Translator.get('HELP'),
                            self.application.open_help)
        self.menu.addSeparator()
        self.menu.addAction(Translator.get('QUIT'), self.application.quit)

        self.menu.popup(QCursor.pos())


class WebSystray(QMenu):
    """ Left-click menu, also the entire menu on macOS. """

    __dialog = None

    def __init__(self, systray_icon, application):
        super(WebSystray, self).__init__()
        self.application = application
        self.systray_icon = systray_icon

    @property
    def dialog(self):
        if not self.__dialog:
            self.__dialog = SystrayView(self.application, self.systray_icon)
            self.__dialog.icon = self.systray_icon
        return self.__dialog

    @pyqtSlot()
    def popup(self, _):
        # Not the best, but works for now

        self.dialog.reload()
        self.dialog.show()

        # macOs bug: if you click on the advanced menu and then elsewhere
        # when you will re-click on the menu, nothing will appear.
        self.dialog.raise_()


class SystrayView(NuxeoView):

    def __init__(self, application, icon):
        super(SystrayView, self).__init__(
            application, WebSystrayApi(application, self))

        self.icon = icon
        self.setColor(QColor.fromRgba64(0, 0, 0, 0))

        self.file_model = FileModel()
        self.setFlags(Qt.FramelessWindowHint | Qt.Popup)

        context = self.rootContext()
        context.setContextProperty('Systray', self)
        context.setContextProperty('FileModel', self.file_model)

        self.application.manager.updater.updateAvailable.connect(
            self.update_info)
        self.init()

    def get_last_files(self, uid):
        files = self.api.get_last_files(uid, 10, '')
        self.file_model.empty()
        self.file_model.addFiles(files)

    def update_info(self, in_context=False):
        status = self.application.manager.updater.last_status
        channel = self.application.manager.updater.nature
        update_version = status[1]

        if status[0] == UPDATE_STATUS_DOWNGRADE_NEEDED:
            update_type = 'downgrade'
            update_message = Translator.get('NOTIF_UPDATE_DOWNGRADE',
                                            {'version': update_version})
        elif status[0] == UPDATE_STATUS_UPDATE_AVAILABLE:
            update_type = 'upgrade'
            update_message = Translator.get('UPGRADE_AVAILABLE',
                                            {'version': update_version})
        if not update_version:
            update_confirm = update_type = update_message = ""
        else:
            update_confirm = Translator.get('CONFIRM_UPDATE_MESSAGE',
                                            {'version': update_version,
                                             'update_channel': channel})
        if in_context:
            context = self.rootContext()
            context.setContextProperty('updateMessage', update_message)
            context.setContextProperty('updateConfirm', update_confirm)
            context.setContextProperty('updateType', update_type)
            context.setContextProperty('updateVersion', update_version)
            context.setContextProperty(
                'autoUpdateValue', self.application.manager.get_auto_update())
        else:
            self.rootObject().updateInfo.emit(
                update_message, update_confirm, update_type, update_version)

    def set_engine(self, uid):
        self.get_last_files(uid)

    def set_tray_position(self, x, y):
        self.rootObject().setTrayPosition.emit(x, y)

    def init(self):
        """
        Resize and move the system tray menu accordingly to
        the system tray icon position.
        """
        super(SystrayView, self).init()
        if not self.icon.application.manager.get_engines():
            height = 280
            self.setSource(QUrl('nxdrive/data/qml/NoEngineSystray.qml'))
        else:
            height = 370
            self.update_info(in_context=True)
            self.setSource(QUrl('nxdrive/data/qml/Systray.qml'))
            # Connect signals for systray
            self.rootObject().setEngine.connect(self.set_engine)
            self.application.manager.updater.updateAvailable.connect(
                self.update_info)
            self.get_last_files(self.engine_model.engines[0].uid)
        self.rootObject().hide.connect(self.hide)

        geometry = self.geometry()
        icon = self.icon.geometry()

        pos_x = max(0, icon.x() + icon.width() - 300)
        pos_y = icon.y() - height
        if pos_y < 0:
            pos_y = icon.y() + icon.height()
        self.set_tray_position(pos_x, pos_y)
