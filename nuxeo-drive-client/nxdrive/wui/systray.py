'''
Created on 27 janv. 2015

@author: Remi Cattiau
'''
from PyQt4 import QtGui, QtCore
from nxdrive.logging_config import get_logger
from nxdrive.wui.dialog import WebDialog, WebDriveApi
from nxdrive.wui.translator import Translator
from nxdrive.osi import AbstractOSIntegration
log = get_logger(__name__)


class DriveSystrayIcon(QtGui.QSystemTrayIcon):

    def __init__(self):
        super(DriveSystrayIcon, self).__init__()
        self.activated.connect(self._show_popup)

    def showMessage(self, title, message, icon=QtGui.QSystemTrayIcon.Information, timeout = 10000):
        if AbstractOSIntegration.is_mac():
            if AbstractOSIntegration.os_version_above("10.8"):
                from nxdrive.osi.darwin.pyNotificationCenter import notify
                # Use notification center
                log.trace("Display systray message: %s | %s | %s", QtCore.QCoreApplication.applicationName(), title, message)
                return notify(title, None, message)
        return QtGui.QSystemTrayIcon.showMessage(self, title, message, icon, timeout)

    def _show_popup(self, reason):
        if reason == QtGui.QSystemTrayIcon.Trigger:
            self.contextMenu().popup(QtGui.QCursor.pos())


class WebSystrayApi(WebDriveApi):

    @QtCore.pyqtSlot(str)
    def show_settings(self, page):
        try:
            super(WebSystrayApi, self).show_settings(page)
            self._dialog.close()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def show_conflicts_resolution(self, uid):
        try:
            super(WebSystrayApi, self).show_conflicts_resolution(uid)
            self._dialog.close()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str, str)
    def show_metadata(self, uid, ref):
        try:
            super(WebSystrayApi, self).show_metadata(uid, ref)
            self._dialog.close()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str, result=str)
    def open_remote(self, uid):
        try:
            res = super(WebSystrayApi, self).open_remote(uid)
            self._dialog.close()
            return res
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str, str, result=str)
    def open_local(self, uid, path):
        try:
            res = super(WebSystrayApi, self).open_local(uid, path)
            self._dialog.close()
            return res
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot()
    def open_help(self):
        try:
            self._manager.open_help()
            self._dialog.close()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot()
    def open_about(self):
        try:
            self._application.show_settings(section="About")
            self._dialog.close()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot()
    def suspend(self):
        try:
            self._manager.suspend()
            self._dialog.close()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str, result=int)
    def get_syncing_items(self, uid):
        try:
            engine = self._get_engine(uid)
            return engine.get_dao().get_syncing_count()
        except Exception as e:
            log.exception(e)
            return 0

    @QtCore.pyqtSlot()
    def resume(self):
        try:
            self._manager.resume()
            self._dialog.close()
        except Exception as e:
            log.exception(e)

    def _create_advanced_menu(self):
        menu = QtGui.QMenu()
        menu.setFocusProxy(self._dialog)
        if self._manager.is_paused():
            menu.addAction(Translator.get("RESUME"), self.resume)
        else:
            menu.addAction(Translator.get("SUSPEND"), self.suspend)
        menu.addSeparator()
        menu.addAction(Translator.get("SETTINGS"), self._application.show_settings)
        menu.addSeparator()
        menu.addAction(Translator.get("HELP"), self.open_help)
        if self._manager.is_debug():
            menu.addSeparator()
            menuDebug = self._application.create_debug_menu(menu)
            debugAction = QtGui.QAction(Translator.get("DEBUG"), self)
            debugAction.setMenu(menuDebug)
            menu.addAction(debugAction)
        menu.addSeparator()
        menu.addAction(Translator.get("QUIT"), self._application.quit)
        return menu

    @QtCore.pyqtSlot()
    def advanced_systray(self):
        try:
            menu = self._create_advanced_menu()
            menu.exec_(QtGui.QCursor.pos())
        except Exception as e:
            log.exception(e)


class WebSystrayView(WebDialog):
    DEFAULT_WIDTH = 300
    DEFAULT_HEIGHT = 370
    '''
    classdocs
    '''
    def __init__(self, application, icon):
        '''
        Constructor
        '''
        super(WebSystrayView, self).__init__(application, "systray.html", api=WebSystrayApi(application, self))
        self._icon = icon
        self._icon_geometry = None
        self._view.setFocusProxy(self)
        self.resize(WebSystrayView.DEFAULT_WIDTH, WebSystrayView.DEFAULT_HEIGHT)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Popup | QtCore.Qt.Dialog);

    def replace(self):
        log.trace("Icon is %r", self._icon)
        self._icon_geometry = rect = self._icon.geometry()
        log.trace("IconRect is : %s,%s | %s,%s",rect.x(), rect.y(), rect.width(), rect.height())
        from PyQt4.QtGui import QApplication, QCursor
        from PyQt4.QtCore import QRect
        desktop = QApplication.desktop()
        log.trace("Screen id is %d", desktop.screenNumber(rect.topLeft()))
        screen = desktop.availableGeometry(desktop.screenNumber(rect.topLeft()))
        pos = screen
        log.trace("AvailableRect is : %s,%s | %s,%s",pos.x(), pos.y(), pos.width(), pos.height())
        pos = desktop.screenGeometry(desktop.screenNumber(rect.topLeft()))
        log.trace("ScreenRect is : %s,%s | %s,%s",pos.x(), pos.y(), pos.width(), pos.height())
        pos = QCursor.pos()
        log.trace("Cursor is : %s,%s",pos.x(), pos.y())
        if not rect.contains(pos) or (rect.x() == 0 and rect.y() == 0):
            # Avoid any modulo 0
            if rect.width() == 0 or rect.height() == 0:
                rect = QRect(pos.x(), pos.y(), rect.width(), rect.height())
            else:
                rect = QRect(pos.x()-pos.x()%rect.width(), pos.y()-pos.y()%rect.height(), rect.width(), rect.height())
            log.trace("Adjusting X/Y to %d/%d", rect.x(), rect.y())
            pos = rect
            log.trace("New rect is : %s,%s | %s,%s",pos.x(), pos.y(), pos.width(), pos.height())
        x = rect.x() + rect.width() - self.width()
        y = rect.y() - self.height()
        # Prevent the systray to be hidden
        if y < 0:
            y = rect.y() + rect.height()
        if x < 0:
            x = rect.x()
        log.trace("Move systray menu to %d/%d", x, y)
        self.move(x, y)

    def show(self):
        self.replace()
        super(WebSystrayView, self).show()
        if self.isVisible():
            self.raise_()
            self.activateWindow()
            self.setFocus(QtCore.Qt.ActiveWindowFocusReason)

    def underMouse(self):
        # The original result was different from this simple
        return self.geometry().contains(QtGui.QCursor.pos())

    def shouldHide(self):
        log.trace("Geometry: %r", self.geometry())
        log.trace("Cursor is: %r", QtGui.QCursor.pos())
        log.trace("Icon: %r", self._icon)
        log.trace("Icon geometry: %r", self._icon_geometry)
        if not (self.underMouse() or (self._icon and self._icon.geometry().contains(QtGui.QCursor.pos()))
                or (self._icon_geometry and self._icon_geometry.contains(QtGui.QCursor.pos()))):
            log.trace('will close menu')
            self.close()

    def focusOutEvent(self, event):
        if self._icon is None:
            return
        if not (self.underMouse() or self._icon.geometry().contains(QtGui.QCursor.pos())):
            self.close()
        super(WebSystrayView, self).focusOutEvent(event)

    def resizeEvent(self, event):
        super(WebSystrayView, self).resizeEvent(event)
        self.replace()

    @QtCore.pyqtSlot()
    def close(self):
        self._icon = None
        super(WebSystrayView, self).close()


class WebSystray(QtGui.QMenu):
    '''
    classdocs
    '''
    def __init__(self, application, systray_icon):
        '''
        Constructor
        '''
        super(WebSystray, self).__init__()
        self.aboutToShow.connect(self.onShow)
        self.aboutToHide.connect(self.onHide)
        self._application = application
        self._systray_icon = systray_icon
        self.dlg = None

    @QtCore.pyqtSlot()
    def dialogDeleted(self):
        self.dlg = None

    @QtCore.pyqtSlot()
    def onHide(self):
        if self.dlg:
            self.dlg.shouldHide()

    @QtCore.pyqtSlot()
    def onShow(self):
        log.trace("Show systray menu")
        if self.dlg is None:
            self.dlg = WebSystrayView(self._application, self._systray_icon)
            # Close systray when app is quitting
            self._application.aboutToQuit.connect(self.dlg.close)
            self.dlg.destroyed.connect(self.dialogDeleted)
        self.dlg._icon = self._systray_icon
        self.dlg.show()
