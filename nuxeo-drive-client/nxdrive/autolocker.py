# coding: utf-8
from copy import deepcopy
from logging import getLogger

from PyQt4 import QtCore

from engine.workers import PollWorker
from nxdrive.engine.workers import ThreadInterrupt

log = getLogger(__name__)


class ProcessAutoLockerWorker(PollWorker):

    orphanLocks = QtCore.pyqtSignal(object)
    documentLocked = QtCore.pyqtSignal(str)
    documentUnlocked = QtCore.pyqtSignal(str)

    def __init__(self, check_interval, manager, watched_folders=None):
        super(ProcessAutoLockerWorker, self).__init__(check_interval)
        self._manager = manager
        self._osi = manager.osi
        self._dao = manager.get_dao()
        self._autolocked = dict()
        self._lockers = dict()
        if watched_folders is None:
            watched_folders = []
        self._watched_folders = watched_folders
        self._opened_files = dict()
        self._to_lock = []
        self._first = True

    def set_autolock(self, filepath, locker):
        self._autolocked[filepath] = 0
        self._lockers[filepath] = locker
        QtCore.QTimer.singleShot(2000, self.force_poll)

    def get_open_files(self):
        return self._opened_files

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
        except Exception as e:
            log.trace("Exception occured: %r", e)

    def orphan_unlocked(self, path):
        self._dao.unlock_path(path)

    def _process(self):
        opened_files = []
        # Restrict to pid
        pids = None
        if len(self._watched_folders) == 0:
            if len(self._autolocked) == 0:
                # Nothing to watch
                return
            pids = []
            # Can only restricted to pid if no watched folders
            for file_path in self._autolocked:
                if self._autolocked[file_path] == 0:
                    pids = None
                    break
                pids.append(self._autolocked[file_path])
        log.trace("get_open_files restricted to %r", pids)
        to_unlock = deepcopy(self._autolocked)
        files = self._osi.get_open_files(pids=pids)
        if files is None:
            log.debug("no opened files")
            return
        for file_path in files:
            found = False
            for folder in self._watched_folders:
                if file_path[1].startswith(folder):
                    log.trace("found in watched_folder: %r", file_path)
                    found = True
                    break
            if file_path[1] in self._autolocked:
                log.trace("found in autolocked: %r", file_path)
                found = True
            if not found:
                continue
            if file_path[1] in to_unlock:
                if self._autolocked[file_path[1]] == 0:
                    self._to_lock.append(file_path)
                self._autolocked[file_path[1]] = file_path[0]
                del to_unlock[file_path[1]]
            opened_files.append(file_path)
        self._opened_files = opened_files
        self._lock_files(self._to_lock)
        self._unlock_files(to_unlock)

    def _lock_files(self, files):
        for file_path in files:
            self._lock_file(file_path)

    def _unlock_files(self, files):
        for file_path in files:
            pid = self._autolocked[file_path]
            if pid == 0:
                continue
            # No process recorded so never been locked
            self._unlock_file(file_path)

    def _lock_file(self, file_path):
        log.trace("lock file: %s", file_path)
        if file_path[1] in self._lockers:
            locker = self._lockers[file_path[1]]
            locker.autolock_lock(file_path[1])
        self._dao.lock_path(file_path[1], file_path[0], '')
        self._to_lock.remove(file_path)

    def _unlock_file(self, file_path):
        log.trace("unlocking file: %s", file_path)
        if file_path in self._lockers:
            locker = self._lockers[file_path]
            locker.autolock_unlock(file_path)
        del self._autolocked[file_path]
        del self._lockers[file_path]
        self._dao.unlock_path(file_path)
