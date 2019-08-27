# coding: utf-8
""" Console mode application. """

from logging import getLogger
from typing import Any

from PyQt5.QtCore import QCoreApplication, QTimer

__all__ = ("ConsoleApplication",)

log = getLogger(__name__)


class ConsoleApplication(QCoreApplication):
    """Console mode Nuxeo Drive application"""

    def __init__(self, manager, *args: Any):
        super().__init__(list(*args))

        # Little trick here! See Application.__init__() for details.
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: None)
        self.timer.start(100)

        self.manager = manager

        # Used by SyncAndQuitWorker
        self.manager.application = self

        # Make sure manager is stopped before quitting
        self.aboutToQuit.connect(self.manager.stop)

        log.info("Starting console mode application")
        self.manager.start()
