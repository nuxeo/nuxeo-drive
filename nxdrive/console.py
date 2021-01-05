""" Console mode application. """

from logging import getLogger
from typing import TYPE_CHECKING, Any

from .constants import APP_NAME, COMPANY
from .qt.imports import QCoreApplication, QTimer

if TYPE_CHECKING:
    from .manager import Manager  # noqa

__all__ = ("ConsoleApplication",)

log = getLogger(__name__)


class ConsoleApplication(QCoreApplication):
    """Console mode Nuxeo Drive application"""

    def __init__(self, manager: "Manager", *args: Any) -> None:
        # Little fix here! See Application.__init__() for details.
        QCoreApplication.setOrganizationName(COMPANY)

        super().__init__(list(*args))

        # Little trick here! See Application.__init__() for details.
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: None)
        self.timer.start(100)

        self.manager = manager

        # Used by SyncAndQuitWorker
        self.manager.application = self

        # Application update
        self.manager.updater.appUpdated.connect(self.quit)

        # Connect this slot last so the other slots connected
        # to self.aboutToQuit can run beforehand.
        self.aboutToQuit.connect(self.manager.stop)

        log.info(f"Starting {APP_NAME} in console mode")
        self.manager.start()
