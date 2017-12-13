# coding: utf-8
from logging import getLogger

from PyQt4.QtCore import QObject, pyqtSlot

log = getLogger(__name__)


class DriveScript(QObject):
    def __init__(self, manager):
        self._manager = manager
        self.engine_uid = None
        super(DriveScript, self).__init__()

    @pyqtSlot(str)
    def log(self, line):
        log.debug("DriveScript: %s", line)

    @pyqtSlot(result=bool)
    def hasUi(self):
        return False

    def get_engine(self):
        if self.engine_uid is None:
            if len(self._manager.get_engines()) == 0:
                return None
            engine = self._manager.get_engines().itervalues().next()
        else:
            engine = self._manager.get_engines()[self.engine_uid]
        return engine


class DriveUiScript(DriveScript):
    def __init__(self, manager, application):
        self.application = application
        super(DriveUiScript, self).__init__(manager)

    @pyqtSlot(result=bool)
    def hasUi(self):
        return True

    @pyqtSlot(str)
    def showSettings(self, section='Accounts'):
        if not section:
            section = 'Accounts'
        self.application.show_settings(section)

    @pyqtSlot()
    def showConflicts(self):
        engine = self.get_engine()
        if engine is None:
            log.debug("No engine for showConflicts: %s", self.engine_uid)
            return
        self.application.show_conflicts_resolution(engine)

    @pyqtSlot(str)
    def openUrl(self, url):
        self.application.show_dialog(str(url))
