from contextlib import suppress
from copy import deepcopy
from logging import getLogger
from pathlib import Path
from time import sleep  # time was added here
from typing import TYPE_CHECKING, Dict, Iterable, Iterator

import psutil

from .constants import LINUX, MAC, WINDOWS
from .engine.workers import PollWorker
from .exceptions import ThreadInterrupt
from .objects import Item, Items
from .options import Options
from .qt.imports import QTimer, pyqtSignal

if TYPE_CHECKING:
    from .direct_edit import DirectEdit  # noqa
    from .manager import Manager  # noqa

if LINUX:
    from .osi.linux.files import get_other_opened_files
elif MAC:
    from .osi.darwin.files import get_other_opened_files
elif WINDOWS:
    from .osi.windows.files import get_other_opened_files

__all__ = ("ProcessAutoLockerWorker",)

log = getLogger(__name__)

# Define which processes to INCLUDE for monitoring file operations
# Only these applications will be monitored for document editing
# Process names should be without extensions (e.g., "winword" not "winword.exe")
MONITORED_PROCESSES = {
    # Microsoft Office Suite
    "winword",  # Microsoft Word
    "excel",  # Microsoft Excel
    "powerpnt",  # Microsoft PowerPoint
    "outlook",  # Microsoft Outlook
    "onenote",  # Microsoft OneNote
    # Adobe Creative Suite
    "photoshop",  # Adobe Photoshop
    "illustrator",  # Adobe Illustrator
    "indesign",  # Adobe InDesign
    "acrobat",  # Adobe Acrobat
    "acroread",  # Adobe Acrobat Reader
    "aftereffects",  # Adobe After Effects
    "premiere",  # Adobe Premiere Pro
    "dreamweaver",  # Adobe Dreamweaver
    "flash",  # Adobe Flash (legacy)
    "lightroom",  # Adobe Lightroom
    "bridge",  # Adobe Bridge
    "audition",  # Adobe Audition
    "animate",  # Adobe Animate
    "xd",  # Adobe XD
    "dimension",  # Adobe Dimension
    # OpenOffice
    "soffice",  # Entire office suite
    "scalc",  # OpenOffice Calc
    "swriter",  # OpenOffice Writer
    "simpress",  # OpenOffice Impress
    "sdraw",  # OpenOffice Draw
    "sbase",  # OpenOffice Base
    "smath",  # OpenOffice Math
}

# Add processes from Options.include_process to the monitored processes
if Options.include_process:
    MONITORED_PROCESSES.update(Options.include_process)
    log.info(f"Added processes to include from user config: {Options.include_process}")


class ProcessAutoLockerWorker(PollWorker):
    orphanLocks = pyqtSignal(object)
    concurrentAlreadyLocked = pyqtSignal(str, str)
    documentLocked = pyqtSignal(str)
    documentUnlocked = pyqtSignal(str)

    def __init__(
        self, check_interval: int, manager: "Manager", folder: Path, /
    ) -> None:
        super().__init__(check_interval, "AutoLocker")
        self.dao = manager.dao
        self._folder = folder

        self._autolocked: Dict[Path, int] = {}
        self._lockers: Dict[Path, "DirectEdit"] = {}
        self._to_lock: Items = []
        self._first = True

        # Notification signals
        self.concurrentAlreadyLocked.connect(
            manager.notification_service._concurrentLocked
        )
        self.documentLocked.connect(manager.notification_service._lockDocument)
        self.documentUnlocked.connect(manager.notification_service._unlockDocument)

    def set_autolock(self, filepath: Path, locker: "DirectEdit", /) -> None:
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
                locks = self.dao.get_locked_paths()
                self.orphanLocks.emit(locks)
                self._first = False
            self._process()
            return True
        except ThreadInterrupt:
            raise
        except Exception:
            log.exception("Unhandled error")
        return False

    def orphan_unlocked(self, path: Path, /) -> None:
        """Unlock old documents, or documents from an old Direct Edit session."""
        self.dao.unlock_path(path)

    def _process(self) -> None:
        current_locks = deepcopy(self._autolocked)

        for pid, path in get_open_files():
            log.info(f"Inside for loop _process method: {pid}, {path}")
            # Filter out files depending on configured ignored patterns
            if path.name.startswith(Options.ignored_prefixes) or path.name.endswith(
                Options.ignored_suffixes
            ):
                continue

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
        log.info("Sleeping for 10 seconds after for loop")
        sleep(10)
        log.info("Sleep completed")

        # Lock new documents
        if self._to_lock:
            self._lock_files(self._to_lock)

        # If there are remaining documents, it means they are no more being edited
        # and therefore we need to unlock them.
        if current_locks:
            self._unlock_files(current_locks)

    def _lock_files(self, items: Items, /) -> None:
        """Schedule locks for the given documents."""
        for item in items:
            self._lock_file(item)

    def _unlock_files(self, files: Iterable[Path], /) -> None:
        """Schedule unlocks for the given documents."""
        for path in files:
            self._unlock_file(path)

    def _lock_file(self, item: Item, /) -> None:
        """Lock a given document."""
        pid, path = item
        log.info(f"Locking file {path!r} (PID={pid!r})")
        if path in self._lockers:
            locker = self._lockers[path]
            locker.autolock_lock(path)
        self.dao.lock_path(path, pid, "")
        self._to_lock.remove(item)

    def _unlock_file(self, path: Path, /) -> None:
        """Unlock a given document."""
        log.info(f"Unlocking file {path!r}")
        if path in self._lockers:
            locker = self._lockers[path]
            locker.autolock_unlock(path)
        del self._autolocked[path]
        del self._lockers[path]
        self.dao.unlock_path(path)


def get_open_files() -> Iterator[Item]:
    """
    Get all opened files on the OS, filtered to include only specific applications.
    Only processes in MONITORED_PROCESSES will be monitored for file operations.

    :return: Generator of (PID, file path).
    """
    import traceback

    # Let's skip all errors at the top the the code.
    # It would be an endless fight to catch specific errors only.
    # Here, it is typically MemoryError's.
    if WINDOWS:
        log.debug(f"All processes to be monitored: {sorted(MONITORED_PROCESSES)}")
        try:
            psutil.process_iter.cache_clear()
            for proc in psutil.process_iter(attrs=["pid", "name", "username"]):
                try:
                    process_name_raw = proc.name().lower() if proc.name() else ""
                    # Remove extension from process name for comparison (e.g., "winword.exe" -> "winword")
                    process_name = (
                        process_name_raw.rsplit(".", 1)[0]
                        if "." in process_name_raw
                        else process_name_raw
                    )

                    # Only monitor processes that are in our inclusion list
                    if process_name not in MONITORED_PROCESSES:
                        continue

                    log.debug(
                        f"Monitoring process: {process_name_raw} -> {process_name} (PID: {proc.pid}) \
                        (User: {proc.info.get('username')})"
                    )

                    # But we also want to filter out errors by processor to be able to retrieve some data from others
                    for handler in proc.open_files():
                        # And so for errors happening at the processes level (typically PermissisonError's)
                        log.debug("Inside proc.open_files inner loop")
                        log.debug(f"pid : {proc.pid}, handler.path : {handler.path}")
                        yield proc.pid, Path(handler.path)
                except psutil.NoSuchProcess:
                    # Process might have terminated while we were checking it
                    log.error(
                        f"psutil.NoSuchProcess for process: {process_name_raw} (PID: {proc.pid})"
                    )
                    continue
                except psutil.AccessDenied:
                    # We don't have access to this process
                    log.error(
                        f"psutil.AccessDenied for process: {process_name_raw} (PID: {proc.pid})"
                    )
                    continue
                except Exception as ex:
                    log.error(
                        f"Exception {type(ex).__name__} for process: {process_name_raw} (PID: {proc.pid})"
                    )
                    log.debug(traceback.format_exc())
        except Exception as ex:
            log.error(f"autolocker exception >>>>>>>> {ex}")
            log.error("Cannot get opened files", exc_info=True)
    else:
        try:
            for proc in psutil.process_iter(attrs=["pid"]):
                # But we also want to filter out errors by processor to be able to retrieve some data from others
                with suppress(Exception):
                    for handler in proc.open_files():
                        # And so for errors happening at the processes level (typically PermissisonError's)
                        with suppress(Exception):
                            yield proc.pid, Path(handler.path)
        except Exception:
            log.warning("Cannot get opened files", exc_info=True)

    yield from get_other_opened_files()
