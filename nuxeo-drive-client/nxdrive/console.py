# coding: utf-8
""" Console mode application. """

from logging import getLogger

from PyQt4 import QtCore
from PyQt4.QtCore import QCoreApplication

from nxdrive.options import Options

log = getLogger(__name__)


class ConsoleApplication(QCoreApplication):
    """Console mode Nuxeo Drive application"""

    def __init__(self, manager, argv=()):
        super(ConsoleApplication, self).__init__(list(argv))
        self.manager = manager
        self.mainEngine = None
        for engine in self.manager.get_engines().values():
            self.mainEngine = engine
            break
        if self.mainEngine is not None and Options.debug:
            from nxdrive.engine.engine import EngineLogger
            self.engineLogger = EngineLogger(self.mainEngine)

        # Make sure manager is stopped before quitting
        self.aboutToQuit.connect(self.manager.stop)

        self.quit_if_done = Options.quit_if_done
        if self.quit_if_done:
            #  Connect engines to a signal allowing to quit application if synchronization is over
            self.manager.aboutToStart.connect(self.connect_engine_quit)

        self.quit_timeout = Options.quit_timeout
        if self.quit_timeout >= 0:
            # If a quit timeout is passed start a timer
            self.quit_timer = QtCore.QTimer().singleShot(1000 * self.quit_timeout, self.quit_after_timeout)

        log.info('Starting console mode application')
        self.manager.start()

    @QtCore.pyqtSlot(object)
    def connect_engine_quit(self, engine):
        engine.syncCompleted.connect(self.quit_if_sync_completed)

    @QtCore.pyqtSlot()
    def quit_if_sync_completed(self):
        self.sender().stop()
        if self.manager.is_syncing():
            return
        log.debug("All engines completed synchronization")
        self.quit()

    @QtCore.pyqtSlot()
    def quit_after_timeout(self):
        if self.quit_if_done:
            log.error("Maximum uptime [%ds] expired before all engines completed synchronization", self.quit_timeout)
            self.exit(1)
        else:
            log.info("Maximum uptime [%ds] expired", self.quit_timeout)
            self.quit()
