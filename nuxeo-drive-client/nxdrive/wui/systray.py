# coding: utf-8
from PyQt4.QtCore import Qt, pyqtSlot
from PyQt4.QtGui import QApplication, QCursor, QMenu, QStyle, QSystemTrayIcon

from nxdrive.osi import AbstractOSIntegration
from nxdrive.wui.dialog import WebDialog, WebDriveApi
from nxdrive.wui.translator import Translator


class DriveSystrayIcon(QSystemTrayIcon):

    __menu_left = None
    __menu_right = None

    def __init__(self, application):
        super(DriveSystrayIcon, self).__init__(application)
        self.application = application
        self.messageClicked.connect(self.application.message_clicked)
        self.activated.connect(self.handle_mouse_click)

        # Windows bug: the systray icon is still visible
        self.application.aboutToQuit.connect(self.hide)

        if not AbstractOSIntegration.is_mac():
            # On macOS, only the left click is detected, so the context
            # menu is useless.  It is better to not define it else it
            # will show up every click on the systray icon.
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

    @pyqtSlot()
    def suspend(self):
        self._manager.suspend()
        self.dialog.view.reload()

    @pyqtSlot()
    def resume(self):
        self._manager.resume()
        self.dialog.view.reload()

    @pyqtSlot(result=bool)
    def is_paused(self):
        return self._manager.is_paused()

    @pyqtSlot(result=bool)
    def need_adv_menu(self):
        """
        Do we need to display the left click advanced menu?  Yes if:
          - on debug
          - on macOS
        """
        return self._manager.debug or AbstractOSIntegration.is_mac()

    @pyqtSlot(str, result=int)
    def get_syncing_items(self, uid):
        count = 0
        engine = self._get_engine(str(uid))
        if engine:
            count = engine.get_dao().get_syncing_count()
        return count

    @pyqtSlot()
    def advanced_systray(self):
        if not self.need_adv_menu():
            return

        self.menu = QMenu()

        if self._manager.debug:
            self.application.create_debug_menu(self.menu)

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
            self.menu.addAction(Translator.get('QUIT'), self.application.quit)

        self.menu.popup(QCursor.pos())


class WebSystrayView(WebDialog):

    default_width = 300
    default_height = 370

    __geometry = None

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

        height = self.default_height
        if not self.icon.application.manager.get_engines():
            height = 280
        self.resize(self.default_width, height)

        geometry = self.icon.geometry()
        if geometry != self.__geometry:
            pos_x = max(0, geometry.x() + geometry.width() - self.width())
            pos_y = geometry.y() - self.height()
            if pos_y < 0:
                pos_y = geometry.y() + geometry.height()
            self.move(pos_x, pos_y)
            self.__geometry = geometry


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
            self.__dialog = WebSystrayView(self.application, self.systray_icon)
            self.__dialog.icon = self.systray_icon
        return self.__dialog

    @pyqtSlot()
    def popup(self, _):
        self.dialog.resize_and_move()
        self.dialog.show()

        # macOs bug: if you click on the advanced menu and then elsewhere
        # when you will re-click on the menu, nothing will appeares.
        self.dialog.raise_()
