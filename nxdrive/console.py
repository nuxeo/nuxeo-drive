# coding: utf-8
""" Console mode application. """

from logging import getLogger

from PyQt5.QtCore import QCoreApplication

__all__ = ('ConsoleApplication',)

log = getLogger(__name__)


class ConsoleApplication(QCoreApplication):
    """Console mode Nuxeo Drive application"""

    def __init__(self, manager, argv=()):
        super().__init__(list(argv))
        self.manager = manager

        # Make sure manager is stopped before quitting
        self.aboutToQuit.connect(self.manager.stop)

        log.info('Starting console mode application')
        self.manager.start()
