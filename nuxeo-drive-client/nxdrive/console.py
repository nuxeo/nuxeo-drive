"""Console mode application"""

from nxdrive.logging_config import get_logger

log = get_logger(__name__)

# Keep Qt an optional dependency for now
QCoreApplication, QObject = object, object
try:
    from PyQt4 import QtCore
    QCoreApplication = QtCore.QCoreApplication
    QObject = QtCore.QObject
    log.debug("Qt / PyQt4 successfully imported")
except ImportError:
    log.warning("Qt / PyQt4 is not installed: GUI is disabled")
    pass


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

        log.info('Starting console mode application')
        self.manager.start()
