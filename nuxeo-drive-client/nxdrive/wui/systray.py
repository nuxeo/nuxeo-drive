# coding: utf-8
from PyQt4.QtCore import Qt, pyqtSlot
from PyQt4.QtGui import QAction, QCursor, QMenu, QSystemTrayIcon

from nxdrive.wui.dialog import WebDialog, WebDriveApi
from nxdrive.wui.translator import Translator


class DriveSystrayIcon(QSystemTrayIcon):

    def __init__(self, application):
        super(DriveSystrayIcon, self).__init__(application)
        self.application = application
        self.setContextMenu(WebSystray(self, application))
        self.messageClicked.connect(self.application.message_clicked)


class WebSystrayApi(WebDriveApi):

    menu = None

    @pyqtSlot(str)
    def show_settings(self, page):
        self.dialog.hide()
        super(WebSystrayApi, self).show_settings(str(page))

    @pyqtSlot(str)
    def show_conflicts_resolution(self, uid):
        self.dialog.hide()
        super(WebSystrayApi, self).show_conflicts_resolution(str(uid))

    @pyqtSlot(str, str)
    def show_metadata(self, uid, ref):
        self.dialog.hide()
        super(WebSystrayApi, self).show_metadata(str(uid), str(ref))

    @pyqtSlot(str)
    def open_remote(self, uid):
        self.dialog.hide()
        super(WebSystrayApi, self).open_remote(str(uid))

    @pyqtSlot(str, str)
    def open_local(self, uid, path):
        self.dialog.hide()
        super(WebSystrayApi, self).open_local(str(uid), str(path))

    @pyqtSlot()
    def open_help(self):
        self.dialog.hide()
        self._manager.open_help()

    @pyqtSlot(str)
    def trigger_notification(self, id_):
        self.dialog.hide()
        super(WebSystrayApi, self).trigger_notification(str(id_))

    @pyqtSlot()
    def open_about(self):
        self.dialog.hide()
        self.application.show_settings(section='About')

    @pyqtSlot()
    def suspend(self):
        self.dialog.close()
        self._manager.suspend()

    @pyqtSlot(str, result=int)
    def get_syncing_items(self, uid):
        count = 0
        engine = self._get_engine(str(uid))
        if engine:
            count = engine.get_dao().get_syncing_count()
        return count

    @pyqtSlot()
    def resume(self):
        self.dialog.close()
        self._manager.resume()

    @pyqtSlot()
    def advanced_systray(self):
        if not self.menu:
            self.menu = QMenu()
            if self._manager.is_paused():
                self.menu.addAction(Translator.get('RESUME'), self.resume)
            else:
                self.menu.addAction(Translator.get('SUSPEND'), self.suspend)
            self.menu.addSeparator()
            self.menu.addAction(Translator.get('SETTINGS'),
                                self.application.show_settings)
            self.menu.addSeparator()
            self.menu.addAction(Translator.get('HELP'), self.open_help)
            if self._manager.is_debug():
                self.menu.addSeparator()
                debug_menu = self.application.create_debug_menu(self.menu)
                debug_action = QAction(Translator.get('DEBUG'), self)
                debug_action.setMenu(debug_menu)
                self.menu.addAction(debug_action)
            self.menu.addSeparator()
            self.menu.addAction(Translator.get('QUIT'), self.application.quit)

        self.menu.popup(QCursor.pos())


class WebSystrayView(WebDialog):

    default_width = 300
    default_height = 370

    __geometry = None
    __resized = False

    def __init__(self, application, icon):
        super(WebSystrayView, self).__init__(
            application,
            'systray.html',
            api=WebSystrayApi(application, self),
        )
        self.icon = icon
        self.setWindowFlags(Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint
                            | Qt.Popup)

    def move_and_replace(self):
        """
        Resize and move the sysem tray menu accordingly to
        the system tray icon position.
        """

        if not self.__resized:
            self.resize(self.default_width, self.default_height)
            self.__resized = True

        # Calculate coordinates of the box that will contain the systray menu
        geometry = self.icon.geometry()
        if self.__geometry != geometry:
            pos_x = max(0, geometry.x() + geometry.width() - self.width())
            pos_y = geometry.y() - self.height()
            if pos_y < 0:
                pos_y = geometry.y() + geometry.height()
            self.move(pos_x, pos_y)
            self.__geometry = geometry


class WebSystray(QMenu):

    __dialog = None

    def __init__(self, parent, application):
        super(WebSystray, self).__init__()
        self.aboutToShow.connect(self.onShow)
        self.application = application
        self.systray_icon = parent

    @property
    def dialog(self):
        if not self.__dialog:
            self.__dialog = WebSystrayView(self.application,
                                           self.systray_icon)
            self.__dialog.destroyed.connect(self.onDelete)
            self.__dialog.icon = self.systray_icon
            self.application.aboutToQuit.connect(self.__dialog.close)
        return self.__dialog

    @pyqtSlot()
    def onDelete(self):
        self.__dialog = None

    @pyqtSlot()
    def onShow(self):
        self.dialog.move_and_replace()
        self.dialog.show()
