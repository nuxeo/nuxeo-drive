# coding: utf-8
from contextlib import suppress
from copy import deepcopy
from logging import getLogger
from typing import Dict, Iterable, Iterator, List, Tuple, TYPE_CHECKING

import psutil
from PyQt5.QtCore import QTimer, pyqtSignal

from .engine.workers import PollWorker
from .exceptions import ThreadInterrupt
from .utils import force_decode

if TYPE_CHECKING:
    from .direct_edit import DirectEdit  # noqa
    from .engine.dao.sqlite import ManagerDAO  # noqa

__all__ = ("ProcessAutoLockerWorker",)

log = getLogger(__name__)
Item = Tuple[int, str]
Items = List[Item]


class ProcessAutoLockerWorker(PollWorker):

    orphanLocks = pyqtSignal(object)
    documentLocked = pyqtSignal(str)
    documentUnlocked = pyqtSignal(str)

    def __init__(self, check_interval: int, dao: "ManagerDAO", folder: str) -> None:
        super().__init__(check_interval)
        self._dao = dao
        self._folder = force_decode(folder)

        self._autolocked: Dict[str, int] = {}
        self._lockers: Dict[str, "DirectEdit"] = {}
        self._to_lock: Items = []
        self._first = True

    def set_autolock(self, filepath: str, locker: "DirectEdit") -> None:
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

    def orphan_unlocked(self, path: str) -> None:
        self._dao.unlock_path(path)

    def _process(self) -> None:
        to_unlock = deepcopy(self._autolocked)
        for pid, path in get_open_files():
            if path.startswith(self._folder):
                log.debug(f"Found in watched folder: {path!r} (PID={pid})")
            elif path in self._autolocked:
                log.debug(f"Found in auto-locked: {path!r} (PID={pid})")
            else:
                log.trace(f"Skipping file {path!r}")
                continue

            item: Item = (pid, path)
            if path in to_unlock:
                if not self._autolocked[path]:
                    self._to_lock.append(item)
                self._autolocked[path] = pid
                del to_unlock[path]

        self._lock_files(self._to_lock)
        self._unlock_files(to_unlock)

    def _lock_files(self, items: Items) -> None:
        for item in items:
            self._lock_file(item)

    def _unlock_files(self, files: Iterable[str]) -> None:
        for path in files:
            self._unlock_file(path)

    def _lock_file(self, item: Item) -> None:
        pid, path = item
        log.debug(f"Locking file {path!r} (PID={pid!r})")
        if path in self._lockers:
            locker = self._lockers[path]
            locker.autolock_lock(path)
        self._dao.lock_path(path, pid, "")
        self._to_lock.remove(item)

    def _unlock_file(self, path: str) -> None:
        log.debug(f"Unlocking file {path!r}")
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
        with suppress(psutil.Error):
            for handler in proc.open_files():
                yield proc.pid, force_decode(handler.path)
