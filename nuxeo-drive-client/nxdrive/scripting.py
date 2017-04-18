# coding: utf-8
from PyQt4.QtCore import QObject, pyqtSlot

from nxdrive.logging_config import get_logger

log = get_logger(__name__)


class DriveScript(QObject):
    def __init__(self, manager):
        self._manager = manager
        self._engine_uid = None
        super(DriveScript, self).__init__()

    def set_engine_uid(self, engine_uid):
        self._engine_uid = engine_uid

    @pyqtSlot(str)
    def log(self, line):
        log.debug("DriveScript: %s", line)

    @pyqtSlot(result=bool)
    def hasUi(self):
        return False

    def get_engine(self):
        if self._engine_uid is None:
            if len(self._manager.get_engines()) == 0:
                return None
            engine = self._manager.get_engines().itervalues().next()
        else:
            engine = self._manager.get_engines()[self._engine_uid]
        return engine


class DriveUiScript(DriveScript):
    def __init__(self, manager, application):
        self._application = application
        super(DriveUiScript, self).__init__(manager)

    @pyqtSlot(result=bool)
    def hasUi(self):
        return True

    @pyqtSlot(str)
    def showSettings(self, section=""):
        if section == "":
            section = "Accounts"
        self._application.show_settings(section)

    @pyqtSlot()
    def showConflicts(self):
        engine = self.get_engine()
        if engine is None:
            log.debug("No engine for showConflicts: %s", self._engine_uid)
            return
        self._application.show_conflicts_resolution(engine)

    @pyqtSlot(str)
    def openUrl(self, url):
        self._application.show_dialog(str(url))
