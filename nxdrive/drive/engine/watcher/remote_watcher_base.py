"""Base class for remote watchers.

Provides the shared polling loop (``_execute``), common signals
(``initiate``, ``updated``, ``remoteScanFinished``,
``remoteWatcherStopped``), and initialization attributes
(``empty_polls``, ``_next_check``) used by both
``RemoteWatcher`` (Nuxeo) and ``AlfrescoRemoteWatcher``.
"""

from time import monotonic, sleep
from typing import TYPE_CHECKING

from nxdrive.drive.engine.workers import EngineWorker
from nxdrive.drive.exceptions import ThreadInterrupt
from nxdrive.drive.options import Options
from nxdrive.drive.qt.imports import pyqtSignal

if TYPE_CHECKING:
    from nxdrive.drive.dao.engine import EngineDAO

__all__ = ("RemoteWatcherBase",)


class RemoteWatcherBase(EngineWorker):
    """Shared base for remote watchers across all server types."""

    initiate = pyqtSignal()
    updated = pyqtSignal()
    remoteScanFinished = pyqtSignal()
    remoteWatcherStopped = pyqtSignal()

    def __init__(self, engine: "EngineWorker", dao: "EngineDAO", name: str, /) -> None:
        super().__init__(engine, dao, name)

        self.empty_polls = 0
        self._next_check = 0.0

    def _execute(self) -> None:
        first_pass = True
        now = monotonic
        handle_changes = self._handle_changes
        interact = self._interact

        try:
            while "working":
                if now() > self._next_check:
                    if handle_changes(first_pass):
                        first_pass = False

                    self._next_check = now() + Options.delay

                interact()
                sleep(0.5)
        except ThreadInterrupt:
            self.remoteWatcherStopped.emit()
            raise
