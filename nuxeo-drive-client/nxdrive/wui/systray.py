'''
Created on 27 janv. 2015

@author: Remi Cattiau
'''
from PyQt4 import QtGui, QtCore
from nxdrive.logging_config import get_logger
from nxdrive.wui.dialog import WebDialog, WebDriveApi
from nxdrive.wui.translator import Translator

log = get_logger(__name__)


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
    '''
    classdocs
    '''
    def __init__(self, application, icon):
        '''
        Constructor
        '''
        super(WebSystrayView, self).__init__(application, "systray.html", api=WebSystrayApi(application, self))
        self._icon = icon
        self._view.setFocusProxy(self)
        self.resize(300, 370)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint);

    def replace(self):
        log.trace("Icon is %r", self._icon)
        rect = self._icon.geometry()
        if rect.x() < 100:
            x = rect.x() + rect.width()
            y = rect.y() - self.height() + rect.height()
        elif rect.y() < 100:
            x = rect.x() + rect.width() - self.width()
            y = rect.y() + rect.height()
        else:
            x = rect.x() + rect.width() - self.width()
            y = rect.y() - self.height()
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
        if not (self.underMouse() or self._icon.geometry().contains(QtGui.QCursor.pos())):
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
