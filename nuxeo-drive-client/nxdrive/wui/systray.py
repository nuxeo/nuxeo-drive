# coding: utf-8
'''
Created on 27 janv. 2015

@author: Remi Cattiau
'''
from PyQt4.QtCore import QRect, Qt, pyqtSlot
from PyQt4.QtGui import QAction, QApplication, QCursor, QMenu, QSystemTrayIcon

from nxdrive.logging_config import get_logger
from nxdrive.osi import AbstractOSIntegration
from nxdrive.wui.dialog import WebDialog, WebDriveApi
from nxdrive.wui.translator import Translator

try:
    from nxdrive.osi.darwin.pyNotificationCenter import notify
except ImportError:
    pass

log = get_logger(__name__)


class DriveSystrayIcon(QSystemTrayIcon):

    def __init__(self):
        super(DriveSystrayIcon, self).__init__()
        self.activated.connect(self._show_popup)

    def showMessage(self, title, message, icon=QSystemTrayIcon.Information, timeout=10000):
        if AbstractOSIntegration.is_mac() and AbstractOSIntegration.os_version_above('10.8'):
            # Use notification center
            return notify(title, None, message)
        return QSystemTrayIcon.showMessage(self, title, message, icon, timeout)

    def _show_popup(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.contextMenu().popup(QCursor.pos())


class WebSystrayApi(WebDriveApi):

    menu = None

    @pyqtSlot(str)
    def show_settings(self, page):
        self.get_dialog().hide()
        super(WebSystrayApi, self).show_settings(page)

    @pyqtSlot(str)
    def show_conflicts_resolution(self, uid):
        self.get_dialog().hide()
        super(WebSystrayApi, self).show_conflicts_resolution(uid)

    @pyqtSlot(str, str)
    def show_metadata(self, uid, ref):
        self.get_dialog().hide()
        super(WebSystrayApi, self).show_metadata(uid, ref)

    @pyqtSlot(str, result=str)
    def open_remote(self, uid):
        self.get_dialog().hide()
        return super(WebSystrayApi, self).open_remote(uid)

    @pyqtSlot(str, str, result=str)
    def open_local(self, uid, path):
        self.get_dialog().hide()
        return super(WebSystrayApi, self).open_local(uid, path)

    @pyqtSlot()
    def open_help(self):
        self.get_dialog().hide()
        self._manager.open_help()

    @pyqtSlot(str)
    def trigger_notification(self, id_):
        self.get_dialog().hide()
        super(WebSystrayApi, self).trigger_notification(id_)

    @pyqtSlot()
    def open_about(self):
        self.get_dialog().hide()
        self._application.show_settings(section='About')

    @pyqtSlot()
    def suspend(self):
        self.get_dialog().close()
        self._manager.suspend()

    @pyqtSlot(str, result=int)
    def get_syncing_items(self, uid):
        engine = self._get_engine(uid)
        if engine:
            return engine.get_dao().get_syncing_count()
        return 0

    @pyqtSlot()
    def resume(self):
        self.get_dialog().close()
        self._manager.resume()

    def _create_advanced_menu(self):
        menu = QMenu()
        if self._manager.is_paused():
            menu.addAction(Translator.get('RESUME'), self.resume)
        else:
            menu.addAction(Translator.get('SUSPEND'), self.suspend)
        menu.addSeparator()
        menu.addAction(Translator.get('SETTINGS'), self._application.show_settings)
        menu.addSeparator()
        menu.addAction(Translator.get('HELP'), self.open_help)
        if self._manager.is_debug():
            menu.addSeparator()
            menu_debug = self._application.create_debug_menu(menu)
            debug_action = QAction(Translator.get('DEBUG'), self)
            debug_action.setMenu(menu_debug)
            menu.addAction(debug_action)
        menu.addSeparator()
        menu.addAction(Translator.get('QUIT'), self._application.quit)
        return menu

    @pyqtSlot()
    def advanced_systray(self):
        if not self.menu:
            self.menu = self._create_advanced_menu()
        self.menu.popup(QCursor.pos())


class WebSystrayView(WebDialog):

    default_width = 300
    default_height = 370

    def __init__(self, application, icon):

        super(WebSystrayView, self).__init__(application, 'systray.html', api=WebSystrayApi(application, self))
        self._icon = icon
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Popup)
        self.move_and_replace()
        # TODO center systray icon into the notification zone

    def move_and_replace(self):
        ''' Resize and move the sysem tray menu accordingly to the system tray icon position. '''

        self.resize(self.default_width,
                    self.default_height)  # TODO can we use these args on init?

        rect = self._icon.geometry()
        log.trace('Systray icon: %r', self._icon)
        log.trace('Systray icon geometry: %r', rect)

        # Calculate coordinates of the box that will contain the systray menu
        pos_x = max(0, rect.x() + rect.width() - self.width())
        pos_y = rect.y() - self.height()
        if pos_y < 0:
            pos_y = rect.y() + rect.height()
        log.trace('Move systray menu to (%d, %d)', pos_x, pos_y)
        self.move(pos_x, pos_y)
        log.trace('Systray menu geometry: %r', self.geometry())


class WebSystray(QMenu):

    def __init__(self, application, systray_icon):
        super(WebSystray, self).__init__()
        self.aboutToShow.connect(self.on_show)
        self.aboutToHide.connect(self.on_hide)
        self._application = application
        self._systray_icon = systray_icon
        self.__dialog = None

    @property
    def dialog(self):
        if not self.__dialog:
            self.__dialog = WebSystrayView(self._application, self._systray_icon)
            self.__dialog.destroyed.connect(self.on_delete)
            self.__dialog._icon = self._systray_icon

            # Close systray when app is quitting
            self._application.aboutToQuit.connect(self.__dialog.close)
        return self.__dialog

    @pyqtSlot()
    def on_delete(self):
        self.__dialog = None

    @pyqtSlot()
    def on_hide(self):
        if not self.dialog.geometry().contains(QCursor.pos()):
            log.trace('Hide systray menu')
            self.dialog.hide()

    @pyqtSlot()
    def on_show(self):
        log.trace('Show systray menu')
        self.dialog.show()
