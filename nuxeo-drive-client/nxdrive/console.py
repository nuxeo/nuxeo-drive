"""Console mode application"""

from PyQt4 import QtCore
from PyQt4.QtCore import QCoreApplication
from nxdrive.logging_config import get_logger

log = get_logger(__name__)


class ConsoleApplication(QCoreApplication):
    """Console mode Nuxeo Drive application"""

    def __init__(self, controller, options, argv=()):
        super(ConsoleApplication, self).__init__(list(argv))
        self.manager = controller
        self.options = options
        self.mainEngine = None
        for engine in self.manager.get_engines().values():
            self.mainEngine = engine
            break
        if self.mainEngine is not None and options.debug:
            from nxdrive.engine.engine import EngineLogger
            self.engineLogger = EngineLogger(self.mainEngine)

        self.aboutToQuit.connect(self.manager.stop)

        self.quit_timeout = options.quit_timeout
        if self.quit_timeout >= 0:
            # If a quit timeout is passed start a timer and connect engines to a signal allowing to
            # quit application if synchronization is over
            self.quit_timer = QtCore.QTimer().singleShot(1000 * self.quit_timeout, self.quit_after_timeout)
            self.manager.aboutToStart.connect(self.connect_engine_quit)

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
        log.debug("All engines completed synchronization before maximum uptime expiration [%ds]",
                  self.quit_timeout)
        self.quit()

    @QtCore.pyqtSlot()
    def quit_after_timeout(self):
        log.error("Maximum uptime [%ds] expired before all engines completed synchronization", self.quit_timeout)
        self.exit(1)
