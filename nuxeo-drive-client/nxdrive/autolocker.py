# coding: utf-8
from copy import deepcopy
from logging import getLogger

import psutil
from PyQt4 import QtCore

from nxdrive.engine.workers import PollWorker, ThreadInterrupt
from nxdrive.utils import force_decode

log = getLogger(__name__)


class ProcessAutoLockerWorker(PollWorker):

    orphanLocks = QtCore.pyqtSignal(object)
    documentLocked = QtCore.pyqtSignal(str)
    documentUnlocked = QtCore.pyqtSignal(str)

    def __init__(self, check_interval, dao, folder):
        super(ProcessAutoLockerWorker, self).__init__(check_interval)
        self._dao = dao
        self._folder = force_decode(folder)

        self._autolocked = {}
        self._lockers = {}
        self._to_lock = []
        self._first = True

    def set_autolock(self, filepath, locker):
        if self._autolocked.get(filepath):
            # Already locked
            return

        self._autolocked[filepath] = 0
        self._lockers[filepath] = locker
        QtCore.QTimer.singleShot(2000, self.force_poll)

    def _poll(self):
        try:
            if self._first:
                # Cannot guess the locker of orphans so emit a signal
                locks = self._dao.get_locked_paths()
                self.orphanLocks.emit(locks)
                self._first = False
            self._process()
        except ThreadInterrupt:
            raise
        except:
            log.trace('Unhandled error', exc_info=True)

    def orphan_unlocked(self, path):
        self._dao.unlock_path(path)

    def _process(self):
        to_unlock = deepcopy(self._autolocked)
        for pid, path in get_open_files():
            if path.startswith(self._folder):
                log.trace('Found in watched folder: %r (PID=%r)', path, pid)
            elif path in self._autolocked:
                log.trace('Found in auto-locked: %r (PID=%r)', path, pid)
            else:
                continue

            item = (pid, path)
            if path in to_unlock:
                if not self._autolocked[path]:
                    self._to_lock.append(item)
                self._autolocked[path] = pid
                del to_unlock[path]

        self._lock_files(self._to_lock)
        self._unlock_files(to_unlock)

    def _lock_files(self, items):
        for item in items:
            self._lock_file(item)

    def _unlock_files(self, files):
        for path in files:
            self._unlock_file(path)

    def _lock_file(self, item):
        pid, path = item
        log.trace('Locking file %r (PID=%r)', path, pid)
        if path in self._lockers:
            locker = self._lockers[path]
            locker.autolock_lock(path)
        self._dao.lock_path(path, pid, '')
        self._to_lock.remove(item)

    def _unlock_file(self, path):
        log.trace('Unlocking file %r', path)
        if path in self._lockers:
            locker = self._lockers[path]
            locker.autolock_unlock(path)
        del self._autolocked[path]
        del self._lockers[path]
        self._dao.unlock_path(path)


def get_open_files():
    # type () -> generator(int, str)
    """
    Get all opened files on the OS.

    :return: Generator of (PID, file path).
    """

    for proc in psutil.process_iter():
        try:
            for handler in proc.open_files():
                yield proc.pid, force_decode(handler.path)
        except psutil.Error:
            pass
