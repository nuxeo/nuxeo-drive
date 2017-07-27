# coding: utf-8
from PyQt4.QtCore import Qt, pyqtSlot
from PyQt4.QtGui import QAction, QApplication, QCursor, QMenu, QStyle, \
    QSystemTrayIcon

from nxdrive.osi import AbstractOSIntegration
from nxdrive.wui.dialog import WebDialog, WebDriveApi
from nxdrive.wui.translator import Translator


class DriveSystrayIcon(QSystemTrayIcon):

    def __init__(self, application):
        super(DriveSystrayIcon, self).__init__(application)
        self.application = application
        self.menu_left = self.create_menu_left()
        self.messageClicked.connect(self.application.message_clicked)
        self.activated.connect(self.handle_mouse_click)

        if not AbstractOSIntegration.is_mac():
            # On macOS, only the left click is detected, so the context
            # menu is useless.  It is better to not define it else it
            # will show up every click on the systray icon.
            self.menu_right = self.create_menu_right()
            self.setContextMenu(self.menu_right)

    def handle_mouse_click(self, reason):
        """
        Handle any mouse click on the systray icon.
        It is not needed to handle the right click as it
        is the native bahevior and will open the context
        menu (right click menu).

        Note: only the left click is detected on macOS.
        """

        if reason == QSystemTrayIcon.Trigger:
            # On left click, open the usual menu with engines and sync files
            self.menu_left.popup(QCursor.pos())
        elif reason == QSystemTrayIcon.MiddleClick:
            # On middle click, open settings.  Yeah, it rocks!
            self.application.show_settings()

    def create_menu_left(self):
        """
        Create the usual menu with engines and sync files.
        It shows up on left click.
        """
        return WebSystray(self, self.application)

    def create_menu_right(self):
        """
        Create the context menu.
        It shows up on left click.

        Note: icons will not be displayed on every GNU/Linux
        distributions, it depends on the graphical environment.
        """

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
        return menu


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

    @pyqtSlot()
    def suspend(self):
        self.dialog.hide()
        self.menu = None  # Force advanced menu regeneration to keep up-to-date
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
        self.dialog.hide()
        self.menu = None  # Force advanced menu regeneration to keep up-to-date
        self._manager.resume()

    @pyqtSlot()
    def advanced_systray(self):
        if not self.menu:
            self.menu = QMenu()
            if self._manager.is_paused():
                self.menu.addAction(Translator.get('RESUME'), self.resume)
            else:
                self.menu.addAction(Translator.get('SUSPEND'), self.suspend)

            if self._manager.debug:
                self.menu.addSeparator()
                debug_menu = self.application.create_debug_menu(self.menu)
                debug_action = QAction(Translator.get('DEBUG'), self)
                debug_action.setMenu(debug_menu)
                self.menu.addAction(debug_action)

            if AbstractOSIntegration.is_mac():
                # Still need to include context menu items as macOS does not
                # see anything but left clicks.
                self.menu.addSeparator()
                self.menu.addAction(Translator.get('SETTINGS'),
                                    self.application.show_settings)
                self.menu.addSeparator()
                self.menu.addAction(Translator.get('HELP'),
                                    self.application.open_help)
                self.menu.addSeparator()
                self.menu.addAction(Translator.get('QUIT'),
                                    self.application.quit)

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

    def resize_and_move(self):
        """
        Resize and move the system tray menu accordingly to
        the system tray icon position.
        """

        if not self.__resized:
            self.resize(self.default_width, self.default_height)
            self.__resized = True

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
    __geometry = None

    def __init__(self, systray_icon, application):
        super(WebSystray, self).__init__()
        self.aboutToShow.connect(self.onShow)
        self.aboutToHide.connect(self.onHide)
        self.application = application
        self.systray_icon = systray_icon

    @property
    def dialog(self):
        if not self.__dialog:
            self.__dialog = WebSystrayView(self.application,
                                           self.systray_icon)
            self.__dialog.destroyed.connect(self.onDelete)
            self.__dialog.icon = self.systray_icon
            self.__geometry = self.__dialog.geometry()
            self.application.aboutToQuit.connect(self.__dialog.close)
        return self.__dialog

    @pyqtSlot()
    def popup(self, pos):
        self.dialog.resize_and_move()
        self.dialog.show()

    @pyqtSlot()
    def onDelete(self):
        self.__dialog = None

    @pyqtSlot()
    def onHide(self):
        """
        This is not triggered on macOS, but keep it for other platforms.
        """
        if not self.__geometry.contains(QCursor.pos()):
            self.dialog.hide()

    @pyqtSlot()
    def onShow(self):
        self.dialog.resize_and_move()
        self.dialog.show()
