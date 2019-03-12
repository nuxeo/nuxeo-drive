# coding: utf-8
from contextlib import suppress
from copy import deepcopy
from logging import getLogger
from pathlib import Path
from typing import Dict, Iterable, Iterator, TYPE_CHECKING

import psutil
from PyQt5.QtCore import QTimer, pyqtSignal

from .constants import LINUX, MAC, WINDOWS
from .engine.workers import PollWorker
from .exceptions import ThreadInterrupt
from .objects import Item, Items

if TYPE_CHECKING:
    from .direct_edit import DirectEdit  # noqa
    from .engine.dao.sqlite import ManagerDAO  # noqa

if LINUX:
    from .osi.linux.files import get_other_opened_files
elif MAC:
    from .osi.darwin.files import get_other_opened_files
elif WINDOWS:
    from .osi.windows.files import get_other_opened_files

__all__ = ("ProcessAutoLockerWorker",)

log = getLogger(__name__)


class ProcessAutoLockerWorker(PollWorker):

    orphanLocks = pyqtSignal(object)
    documentLocked = pyqtSignal(str)
    documentUnlocked = pyqtSignal(str)

    def __init__(self, check_interval: int, dao: "ManagerDAO", folder: Path) -> None:
        super().__init__(check_interval)
        self._dao = dao
        self._folder = folder

        self._autolocked: Dict[Path, int] = {}
        self._lockers: Dict[Path, "DirectEdit"] = {}
        self._to_lock: Items = []
        self._first = True

    def set_autolock(self, filepath: Path, locker: "DirectEdit") -> None:
        """Schedule the document lock."""

        if self._autolocked.get(filepath):
            # Already locked
            return

        self._autolocked[filepath] = 0
        self._lockers[filepath] = locker
        QTimer.singleShot(2000, self.force_poll)

    def _poll(self) -> bool:
        try:
            if self._first:
                # Cannot guess the locker of orphans so emit a signal
                locks = self._dao.get_locked_paths()
                self.orphanLocks.emit(locks)
                self._first = False
            self._process()
            return True
        except ThreadInterrupt:
            raise
        except:
            log.exception("Unhandled error")
        return False

    def orphan_unlocked(self, path: Path) -> None:
        """Unlock old documents, or documents from an old DirectEdit session."""
        self._dao.unlock_path(path)

    def _process(self) -> None:
        current_locks = deepcopy(self._autolocked)

        for pid, path in get_open_files():
            found_in_watched_folder = False
            if self._folder in path.parents:
                log.info(f"Found in watched folder: {path!r} (PID={pid})")
                found_in_watched_folder = True
            elif path in self._autolocked:
                log.info(f"Found in auto-locked: {path!r} (PID={pid})")
            else:
                # All documents are not interesting!
                continue

            item: Item = (pid, path)

            if path in current_locks:
                # If the doc has been detected but not yet locked ...
                if self._autolocked[path] == 0:
                    self._to_lock.append(item)  # ... schedule the lock

                # Prevent re-locking the next time, set the PID as a flag (always != 0)
                self._autolocked[path] = pid

                # Remove the doc, else it will be unlocked just after
                del current_locks[path]
            elif found_in_watched_folder:
                # The document has been found but not locked, this is the case when the application
                # that opens the document does not use identifiable temporary files.
                # Such as Photoshop and Illustrator.
                self.set_autolock(path, self.direct_edit)

        # Lock new documents
        if self._to_lock:
            self._lock_files(self._to_lock)

        # If there are remaining documents, it means they are no more being edited
        # and therefore we need to unlock them.
        if current_locks:
            self._unlock_files(current_locks)

    def _lock_files(self, items: Items) -> None:
        """Schedule locks for the given documents."""
        for item in items:
            self._lock_file(item)

    def _unlock_files(self, files: Iterable[Path]) -> None:
        """Schedule unlocks for the given documents."""
        for path in files:
            self._unlock_file(path)

    def _lock_file(self, item: Item) -> None:
        """Lock a given document."""
        pid, path = item
        log.info(f"Locking file {path!r} (PID={pid!r})")
        if path in self._lockers:
            locker = self._lockers[path]
            locker.autolock_lock(path)
        self._dao.lock_path(path, pid, "")
        self._to_lock.remove(item)

    def _unlock_file(self, path: Path) -> None:
        """Unlock a given document."""
        log.info(f"Unlocking file {path!r}")
        if path in self._lockers:
            locker = self._lockers[path]
            locker.autolock_unlock(path)
        del self._autolocked[path]
        del self._lockers[path]
        self._dao.unlock_path(path)


def get_open_files() -> Iterator[Item]:
    """
    Get all opened files on the OS.

    :return: Generator of (PID, file path).
    """

    for proc in psutil.process_iter():
        with suppress(psutil.Error, OSError, MemoryError):
            for handler in proc.open_files():
                with suppress(PermissionError):
                    yield proc.pid, Path(handler.path)

    yield from get_other_opened_files()
