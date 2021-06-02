import errno
import re
import sqlite3
import sys
from logging import getLogger
from os.path import basename, splitext
from pathlib import Path
from queue import Queue
from threading import Lock
from time import mktime, sleep
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from watchdog.events import FileSystemEvent, PatternMatchingEventHandler
from watchdog.observers import Observer

from ...client.local import FileInfo
from ...constants import LINUX, MAC, ROOT, UNACCESSIBLE_HASH, WINDOWS
from ...exceptions import ThreadInterrupt
from ...feature import Feature
from ...objects import DocPair, Metrics
from ...options import Options
from ...qt.imports import pyqtSignal
from ...utils import current_milli_time, force_decode, is_generated_tmp_file
from ...utils import normalize_event_filename as normalize
from ..activity import tooltip
from ..workers import EngineWorker, Worker

if WINDOWS:
    import watchdog.observers as ob

    # Monkey-patch Watchdog to:
    #   - Set the Windows hack delay to 0 in WindowsApiEmitter,
    #     otherwise we might miss some events
    #   - Increase the ReadDirectoryChangesW buffer size
    ob.read_directory_changes.WATCHDOG_TRAVERSE_MOVED_DIR_DELAY = 0
    ob.winapi.BUFFER_SIZE = 8192

if TYPE_CHECKING:
    from ...dao.engine import EngineDAO  # noqa
    from ..engine import Engine  # noqa

__all__ = ("DriveFSEventHandler", "LocalWatcher", "WIN_MOVE_RESOLUTION_PERIOD")

log = getLogger(__name__)

# Windows 2s between resolution of delete event
WIN_MOVE_RESOLUTION_PERIOD = 2000

TEXT_EDIT_TMP_FILE_PATTERN = r".*\.rtf\.sb\-(\w)+\-(\w)+$"


def is_text_edit_tmp_file(name: str, /) -> bool:
    return bool(re.match(TEXT_EDIT_TMP_FILE_PATTERN, name))


class LocalWatcher(EngineWorker):
    localScanFinished = pyqtSignal()
    rootMoved = pyqtSignal(Path)
    rootDeleted = pyqtSignal()
    docDeleted = pyqtSignal(Path)
    fileAlreadyExists = pyqtSignal(Path, Path)

    def __init__(self, engine: "Engine", dao: "EngineDAO", /) -> None:
        super().__init__(engine, dao, "LocalWatcher")

        self.local = self.engine.local
        self.lock = Lock()
        self.watchdog_queue: Queue = Queue()

        # Delay for the scheduled recursive scans of
        # a created / modified / moved folder under Windows
        self._windows_folder_scan_delay = 10000  # 10 seconds
        if WINDOWS:
            log.info(
                "Windows detected so delete event will be delayed "
                f"by {WIN_MOVE_RESOLUTION_PERIOD} ms"
            )

        self._metrics = {
            "last_local_scan_time": -1,
            "new_files": 0,
            "update_files": 0,
            "delete_files": 0,
            "last_event": 0,
        }

        self._event_handler: Optional[DriveFSEventHandler] = None
        self._observer: Optional[Observer] = None
        self._delete_events: Dict[str, Tuple[int, DocPair]] = {}
        self._folder_scan_events: Dict[Path, Tuple[float, DocPair]] = {}

    def _execute(self) -> None:
        try:
            if not self.local.exists(ROOT):
                self.rootDeleted.emit()
                return

            self._setup_watchdog()
            self._scan()

            if LINUX:
                self._update_local_status()

            if WINDOWS:
                # Check dequeue and folder scan only every 100 loops (1s)
                now = current_milli_time()
                self._win_delete_interval = self._win_folder_scan_interval = now

            while "working":
                self._interact()
                sleep(1)

                while not self.watchdog_queue.empty():
                    self.handle_watchdog_event(self.watchdog_queue.get())

                    if WINDOWS:
                        self._win_delete_check()
                        self._win_folder_scan_check()

                    # If there are a _lot_ of FS events, it is better to let Qt handling
                    # some app events. Else the GUI will not be responsive enough.
                    self._interact()

                if WINDOWS:
                    self._win_delete_check()
                    self._win_folder_scan_check()

        except ThreadInterrupt:
            raise
        finally:
            with self.lock:
                self._stop_watchdog()

    def _update_local_status(self) -> None:
        """Fetch State of each local file then update sync status."""
        local = self.local
        send_sync_status = self.engine.manager.osi.send_sync_status
        doc_pairs = self.dao.get_states_from_partial_local(ROOT)

        # Skip the first as it is the ROOT
        for doc_pair in doc_pairs[1:]:
            abs_path = local.abspath(doc_pair.local_path)
            send_sync_status(doc_pair, abs_path)

    def win_queue_empty(self) -> bool:
        return not self._delete_events

    def get_win_queue_size(self) -> int:
        return len(self._delete_events)

    def _win_delete_check(self) -> None:
        elapsed = current_milli_time() - WIN_MOVE_RESOLUTION_PERIOD
        if self._win_delete_interval >= elapsed:
            return

        with self.lock:
            self._win_dequeue_delete()
        self._win_delete_interval = current_milli_time()

    @tooltip("Dequeue delete")
    def _win_dequeue_delete(self) -> None:
        try:
            for evt in self._delete_events.copy().values():
                evt_time, evt_pair = evt
                if current_milli_time() - evt_time < WIN_MOVE_RESOLUTION_PERIOD:
                    log.info(
                        "Win: ignoring delete event as waiting for move resolution "
                        f"period expiration: {evt!r}"
                    )
                    continue
                if not self.local.exists(evt_pair.local_path):
                    log.info(f"Win: handling watchdog delete for event: {evt!r}")
                    self._handle_watchdog_delete(evt_pair)
                else:
                    remote_id = self.local.get_remote_id(evt_pair.local_path)
                    if not remote_id or remote_id == evt_pair.remote_ref:
                        log.info(
                            f"Win: ignoring delete event as file still exists: {evt!r}"
                        )
                    else:
                        log.info(f"Win: handling watchdog delete for event: {evt!r}")
                        self._handle_watchdog_delete(evt_pair)
                log.info(f"Win: dequeuing delete event: {evt!r}")
                del self._delete_events[evt_pair.remote_ref]
        except ThreadInterrupt:
            raise
        except Exception:
            log.exception("Win: dequeuing deletion error")

    def win_folder_scan_empty(self) -> bool:
        return not self._folder_scan_events

    def get_win_folder_scan_size(self) -> int:
        return len(self._folder_scan_events)

    def _win_folder_scan_check(self) -> None:
        elapsed = current_milli_time() - self._windows_folder_scan_delay
        if self._win_folder_scan_interval >= elapsed:
            return

        with self.lock:
            self._win_dequeue_folder_scan()
        self._win_folder_scan_interval = current_milli_time()

    @tooltip("Dequeue folder scan")
    def _win_dequeue_folder_scan(self) -> None:
        try:
            events = self._folder_scan_events.copy().items()
            for local_path, (evt_time, evt_pair) in events:
                delay = current_milli_time() - evt_time

                if delay < self._windows_folder_scan_delay:
                    log.info(
                        "Win: ignoring folder to scan as waiting for folder scan "
                        f"delay expiration: {local_path!r}"
                    )
                    continue

                if not self.local.exists(local_path):
                    log.info(
                        "Win: dequeuing folder scan event as folder "
                        f"doesn't exist: {local_path!r}"
                    )
                    self._folder_scan_events.pop(local_path, None)
                    continue

                local_info = self.local.try_get_info(local_path)
                if not local_info:
                    log.debug(
                        "Win: dequeuing folder scan event as folder "
                        f"doesn't exist: {local_path!r}"
                    )
                    self._folder_scan_events.pop(local_path, None)
                    continue

                log.info(f"Win: handling folder to scan: {local_path!r}")
                self.scan_pair(local_path)
                local_info = self.local.try_get_info(local_path)
                mtime = (
                    mktime(local_info.last_modification_time.timetuple())
                    if local_info
                    else 0
                )
                if mtime > evt_time:
                    log.info(
                        f"Re-schedule scan as the folder has been modified since last check: {evt_pair}"
                    )
                    self._folder_scan_events[local_path] = (mtime, evt_pair)
                else:
                    log.info(f"Win: dequeuing folder scan event: {evt_pair!r}")
                    self._folder_scan_events.pop(local_path, None)
        except ThreadInterrupt:
            raise
        except Exception:
            log.exception("Win: dequeuing folder scan error")

    @tooltip("Full local scan")
    def _scan(self) -> None:
        # If synchronization features are disabled, we just need to emit that specific
        # signal to let the Remote Watcher start its own thread and the Queue Manager.
        if not Feature.synchronization:
            self.localScanFinished.emit()
            return

        log.info("Full scan started")
        start_ms = current_milli_time()
        to_pause = not self.engine.queue_manager.is_paused()
        if to_pause:
            self._suspend_queue()
        self._delete_files: Dict[str, DocPair] = {}
        self._protected_files: Dict[str, bool] = {}

        info = self.local.get_info(ROOT)
        self._scan_recursive(info)
        self._scan_handle_deleted_files()
        self._metrics["last_local_scan_time"] = current_milli_time() - start_ms
        log.info(f"Full scan finished in {self._metrics['last_local_scan_time']}ms")
        if to_pause:
            self.engine.queue_manager.resume()
        self.localScanFinished.emit()

    def _scan_handle_deleted_files(self) -> None:
        for remote_ref, doc_pair in self._delete_files.copy().items():
            if remote_ref in self._protected_files:
                continue
            self.engine.delete_doc(doc_pair.local_path)
        self._delete_files = {}

    def get_metrics(self) -> Metrics:
        metrics = super().get_metrics()
        if self._event_handler:
            metrics["fs_events"] = self._event_handler.counter
        return {**metrics, **self._metrics}

    def _suspend_queue(self) -> None:
        queue = self.engine.queue_manager
        queue.suspend()
        for processor in queue.get_processors_on(ROOT, exact_match=False):
            processor.stop()

    def scan_pair(self, local_path: Path, /) -> None:
        to_pause = not self.engine.queue_manager.is_paused()
        if to_pause:
            self._suspend_queue()

        info = self.local.get_info(local_path)
        self._scan_recursive(info, recursive=False)
        self._scan_handle_deleted_files()

        if to_pause:
            self.engine.queue_manager.resume()

    def empty_events(self) -> bool:
        ret = self.watchdog_queue.empty()
        if WINDOWS:
            ret &= self.win_queue_empty()
            ret &= self.win_folder_scan_empty()
        return ret

    def get_creation_time(self, child_full_path: Path, /) -> int:
        if WINDOWS:
            return int(child_full_path.stat().st_ctime)

        stat = child_full_path.stat()
        # Try inode number as on HFS seems to be increasing
        if MAC and hasattr(stat, "st_ino"):
            return stat.st_ino
        if hasattr(stat, "st_birthtime"):
            return stat.st_birthtime
        return 0

    def _scan_recursive(self, info: FileInfo, /, *, recursive: bool = True) -> None:
        if recursive:
            # Don't interact if only one level
            self._interact()

        dao, client = self.dao, self.local
        # Load all children from DB
        log.debug(f"Fetching DB local children of {info.path!r}")
        db_children = dao.get_local_children(info.path)

        # Create a list of all children by their name
        to_scan = []
        to_scan_new = []
        children = {child.local_name: child for child in db_children}

        # Load all children from FS
        # detect recently deleted children
        log.debug(f"Fetching FS children info of {info.path!r}")
        try:
            fs_children_info = client.get_children_info(info.path)
        except OSError:
            # The folder has been deleted in the mean time
            return

        # Get remote children to be able to check if a local child found
        # during the scan is really a new item or if it is just the result
        # of a remote creation performed on the file system but not yet
        # updated in the DB as for its local information.
        remote_children: Set[str] = set()
        parent_remote_id = client.get_remote_id(info.path)
        if parent_remote_id:
            pairs_ = dao.get_new_remote_children(parent_remote_id)
            remote_children = {pair.remote_name for pair in pairs_}

        # recursively update children
        for child_info in fs_children_info:
            child_name = child_info.path.name
            child_type = "folder" if child_info.folderish else "file"
            if child_name not in children:
                try:
                    remote_id = client.get_remote_id(child_info.path)
                    if not remote_id:
                        # Avoid IntegrityError: do not insert a new pair state
                        # if item is already referenced in the DB
                        if child_name in remote_children:
                            log.info(
                                f"Skip potential new {child_type} as it is the "
                                f"result of a remote creation: {child_info.path!r}"
                            )
                            continue
                        log.info(f"Found new {child_type} {child_info.path!r}")
                        self._metrics["new_files"] += 1
                        dao.insert_local_state(child_info, info.path)
                    else:
                        log.info(
                            "Found potential moved file "
                            f"{child_info.path!r}[{remote_id}]"
                        )
                        doc_pair = dao.get_normal_state_from_remote(remote_id)

                        if doc_pair and client.exists(doc_pair.local_path):
                            if (
                                not client.is_case_sensitive()
                                and str(doc_pair.local_path).lower()
                                == str(child_info.path).lower()
                            ):
                                log.info(
                                    "Case renaming on a case insensitive filesystem, "
                                    f"update info and ignore: {doc_pair!r}"
                                )
                                if doc_pair.local_name in children:
                                    del children[doc_pair.local_name]
                                doc_pair.local_state = "moved"
                                dao.update_local_state(doc_pair, child_info)
                                continue
                            # possible move-then-copy case, NXDRIVE-471
                            child_full_path = client.abspath(child_info.path)
                            child_creation_time = self.get_creation_time(
                                child_full_path
                            )
                            doc_full_path = client.abspath(doc_pair.local_path)
                            doc_creation_time = self.get_creation_time(doc_full_path)
                            log.debug(
                                f"child_cre_time={child_creation_time}, "
                                f"doc_cre_time={doc_creation_time}"
                            )
                        if not doc_pair:
                            log.info(
                                f"Cannot find reference for {child_info.path!r} in "
                                "database, put it in locally_created state"
                            )
                            self._metrics["new_files"] += 1
                            dao.insert_local_state(child_info, info.path)
                            self._protected_files[remote_id] = True
                        elif doc_pair.processor > 0:
                            log.info(
                                f"Skip pair as it is being processed: {doc_pair!r}"
                            )
                            continue
                        elif doc_pair.local_path == child_info.path:
                            log.info(
                                f"Skip pair as it is not a real move: {doc_pair!r}"
                            )
                            continue
                        elif not client.exists(doc_pair.local_path) or (
                            client.exists(doc_pair.local_path)
                            and child_creation_time < doc_creation_time
                        ):
                            # If file exists at old location, and the file
                            # at the original location is newer, it is
                            # moved to the new location earlier then copied
                            # back
                            log.info("Found moved file")
                            doc_pair.local_state = "moved"
                            dao.update_local_state(doc_pair, child_info)
                            self._protected_files[doc_pair.remote_ref] = True
                            if (
                                client.exists(doc_pair.local_path)
                                and child_creation_time < doc_creation_time
                            ):
                                # Need to put back the new created - need to
                                # check maybe if already there
                                log.debug(
                                    "Found a moved file that has been copy/pasted "
                                    f"back: {doc_pair.local_path!r}"
                                )
                                client.remove_remote_id(doc_pair.local_path)
                                dao.insert_local_state(
                                    client.get_info(doc_pair.local_path),
                                    doc_pair.local_path.parent,
                                )
                        else:
                            # File still exists - must check the remote_id
                            old_remote_id = client.get_remote_id(doc_pair.local_path)
                            if old_remote_id == remote_id:
                                # Local copy paste
                                log.info("Found a copy-paste of document")
                                client.remove_remote_id(child_info.path)
                                dao.insert_local_state(child_info, info.path)
                            else:
                                # Moved and renamed
                                log.info(f"Moved and renamed: {doc_pair!r}")
                                old_pair = dao.get_normal_state_from_remote(
                                    old_remote_id
                                )
                                if old_pair is not None:
                                    old_pair.local_state = "moved"
                                    # Check digest also
                                    digest = child_info.get_digest()
                                    if old_pair.local_digest != digest:
                                        old_pair.local_digest = digest
                                    dao.update_local_state(
                                        old_pair, client.get_info(doc_pair.local_path)
                                    )
                                    self._protected_files[old_pair.remote_ref] = True
                                doc_pair.local_state = "moved"
                                # Check digest also
                                digest = child_info.get_digest()
                                if doc_pair.local_digest != digest:
                                    doc_pair.local_digest = digest
                                dao.update_local_state(doc_pair, child_info)
                                self._protected_files[doc_pair.remote_ref] = True
                    if child_info.folderish:
                        to_scan_new.append(child_info)
                except ThreadInterrupt:
                    raise
                except Exception:
                    log.exception(
                        f"Error during recursive scan of {child_info.path!r}, "
                        "ignoring until next full scan"
                    )
                    continue
            else:
                child_pair = children.pop(child_name)
                try:
                    last_mtime = child_info.last_modification_time.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if (
                        child_pair.processor == 0
                        and child_pair.last_local_updated is not None
                        and last_mtime != child_pair.last_local_updated.split(".")[0]
                    ):
                        log.debug(f"Update file {child_info.path!r}")
                        remote_ref = client.get_remote_id(child_pair.local_path)
                        if remote_ref and not child_pair.remote_ref:
                            log.info(
                                "Possible race condition between remote and local "
                                f"scan, let's refresh pair: {child_pair!r}"
                            )
                            refreshed = dao.get_state_from_id(child_pair.id)
                            if refreshed:
                                child_pair = refreshed
                                if not child_pair.remote_ref:
                                    log.info(
                                        "Pair not yet handled by remote scan "
                                        "(remote_ref is None) but existing remote_id "
                                        f"xattr, let's set it to None: {child_pair!r}"
                                    )
                                    client.remove_remote_id(child_pair.local_path)
                                    remote_ref = ""
                        if remote_ref != child_pair.remote_ref:
                            # Load correct doc_pair | Put the others one back
                            # to children
                            log.warning(
                                "Detected file substitution: "
                                f"{child_pair.local_path!r} "
                                f"({remote_ref}/{child_pair.remote_ref})"
                            )
                            if not remote_ref:
                                if not child_info.folderish:
                                    # Alternative stream or xattr can have
                                    # been removed by external software or user
                                    digest = child_info.get_digest()
                                    if child_pair.local_digest != digest:
                                        child_pair.local_digest = digest
                                        child_pair.local_state = "modified"

                                """
                                NXDRIVE-668: Here we might be in the case
                                of a new folder/file with the same name
                                as the old name of a renamed folder/file,
                                typically:
                                  - initial state: subfolder01
                                  - rename subfolder01 to subfolder02
                                  - create subfolder01
                                => substitution will be detected when scanning
                                subfolder01, so we need to set the remote ID
                                and update the local state to avoid performing
                                a wrong locally_created operation leading to
                                an IntegrityError.  This is true for folders
                                and files.
                                """
                                client.set_remote_id(
                                    child_pair.local_path, child_pair.remote_ref
                                )
                                dao.update_local_state(child_pair, child_info)
                                if child_info.folderish:
                                    to_scan.append(child_info)
                                continue

                            old_pair = dao.get_normal_state_from_remote(remote_ref)
                            if old_pair is None:
                                dao.insert_local_state(child_info, info.path)
                            else:
                                old_pair.local_state = "moved"
                                # Check digest also
                                digest = child_info.get_digest()
                                if old_pair.local_digest != digest:
                                    old_pair.local_digest = digest
                                dao.update_local_state(old_pair, child_info)
                                self._protected_files[old_pair.remote_ref] = True
                            self._delete_files[child_pair.remote_ref] = child_pair
                        if not child_info.folderish:
                            digest = child_info.get_digest()
                            if child_pair.local_digest != digest:
                                child_pair.local_digest = digest
                                child_pair.local_state = "modified"
                        self._metrics["update_files"] += 1
                        dao.update_local_state(child_pair, child_info)
                    if child_info.folderish:
                        to_scan.append(child_info)
                except Exception as e:
                    log.exception(f"Error with pair {child_pair!r}, increasing error")
                    self.increase_error(child_pair, "SCAN RECURSIVE", exception=e)
                    continue

        for deleted in children.values():
            if (
                deleted.pair_state == "remotely_created"
                or deleted.remote_state == "created"
            ):
                continue
            log.info(f"Found deleted file {deleted.local_path!r}")
            # May need to count the children to be ok
            self._metrics["delete_files"] += 1
            if not deleted.remote_ref:
                dao.remove_state(deleted)
            else:
                self._delete_files[deleted.remote_ref] = deleted
            self.remove_void_transfers(deleted)

        for child_info in to_scan_new:
            self._scan_recursive(child_info)

        if not recursive:
            return

        for child_info in to_scan:
            self._scan_recursive(child_info)

    @tooltip("Setup watchdog")
    def _setup_watchdog(self) -> None:
        base: Path = self.local.base_folder
        log.info(f"Watching FS modification on {base!r}")

        # Filter out all ignored suffixes. It will handle custom ones too.
        ignore_patterns = [f"*{suffix}" for suffix in Options.ignored_suffixes]

        # The contents of the local folder
        self._observer = Observer()
        self._event_handler = DriveFSEventHandler(self, ignore_patterns=ignore_patterns)
        self._observer.schedule(self._event_handler, base, recursive=True)

        if Feature.synchronization:
            self._observer.start()

    def _stop_watchdog(self) -> None:
        if not Feature.synchronization:
            return

        if self._observer:
            log.info("Stopping the FS Observer thread")
            try:
                self._observer.stop()
                self._observer.join()
            except Exception:
                log.warning("Cannot stop the FS observer")
            finally:
                del self._observer
        else:
            log.info("No existing FS observer reference")

    def _handle_watchdog_delete(self, doc_pair: DocPair, /) -> None:
        self.remove_void_transfers(doc_pair)

        # Ask for deletion confirmation if needed
        abspath = self.local.abspath(doc_pair.local_path)
        if not abspath.parent.exists():
            log.debug(f"Deleted event on inexistent file: {abspath!r}")
            return

        log.debug(f"Deleting file: {abspath!r}")
        if self.engine.manager.dao.get_bool("show_deletion_prompt", default=True):
            self.docDeleted.emit(doc_pair.local_path)
        else:
            self.engine.delete_doc(doc_pair.local_path)

    def _handle_delete_on_known_pair(self, doc_pair: DocPair, /) -> None:
        """Handle watchdog deleted event on a known doc pair."""
        if WINDOWS:
            # Delay on Windows the delete event
            log.info(f"Add pair to delete events: {doc_pair!r}")
            with self.lock:
                self._delete_events[doc_pair.remote_ref] = (
                    current_milli_time(),
                    doc_pair,
                )
            return

        # In case of case sensitive can be an issue
        if self.local.exists(doc_pair.local_path):
            remote_id = self.local.get_remote_id(doc_pair.local_path)
            if not remote_id or remote_id == doc_pair.remote_ref:
                # This happens on update, don't do anything
                return

        self._handle_watchdog_delete(doc_pair)

    def _handle_move_on_known_pair(
        self, doc_pair: DocPair, evt: FileSystemEvent, rel_path: Path, /
    ) -> None:
        """Handle a watchdog move event on a known doc pair."""

        # Ignore move to Office tmp file
        dest_filename = basename(evt.dest_path)

        ignore, _ = is_generated_tmp_file(dest_filename)
        if ignore:
            log.info(f"Ignoring file: {evt.dest_path!r}")
            return

        dao, client = self.dao, self.local
        src_path = normalize(evt.dest_path)
        rel_path = client.get_path(src_path)

        pair = dao.get_state_from_local(rel_path)
        remote_ref = client.get_remote_id(rel_path)
        if pair and pair.remote_ref == remote_ref:
            local_info = client.try_get_info(rel_path)
            if local_info:
                digest = local_info.get_digest()
                # Drop event if digest hasn't changed, can be the case
                # if only file permissions have been updated
                if not doc_pair.folderish and pair.local_digest == digest:
                    log.debug(
                        f"Dropping watchdog event [{evt.event_type}] as digest "
                        f"has not changed for {rel_path!r}"
                    )
                    # If pair are the same don't drop it.  It can happen
                    # in case of server rename on a document.
                    if doc_pair.id != pair.id:
                        dao.remove_state(doc_pair)
                    return

                pair.local_digest = digest
                pair.local_state = "modified"
                dao.update_local_state(pair, local_info)
                dao.remove_state(doc_pair)
                log.info(
                    f"Substitution file: remove pair({doc_pair!r}) "
                    f"mark({pair!r}) as modified"
                )
                return

        local_info = client.try_get_info(rel_path)
        if not local_info:
            return

        if is_text_edit_tmp_file(local_info.name):
            log.info(
                f"Ignoring move to TextEdit tmp file {local_info.name!r} "
                f"for {doc_pair!r}"
            )
            return

        old_local_path = None
        rel_parent_path = client.get_path(src_path.parent)

        # Ignore inner movement
        versioned = False
        remote_parent_ref = client.get_remote_id(rel_parent_path)
        if (
            doc_pair.remote_name == local_info.name
            and doc_pair.remote_parent_ref == remote_parent_ref
            and rel_parent_path == doc_pair.local_path.parent
        ):
            log.info(
                "The pair was moved but it has been canceled manually, "
                f"setting state to synchronized: {doc_pair!r}"
            )
            doc_pair.local_state = "synchronized"
        else:
            log.info(f"Detect move for {local_info.name!r} ({doc_pair!r})")
            if doc_pair.local_state != "created":
                doc_pair.local_state = "moved"
                old_local_path = doc_pair.local_path
                versioned = True

        self.remove_void_transfers(doc_pair)

        dao.update_local_state(doc_pair, local_info, versioned=versioned)

        # Reflect local path changes of all impacted children in the database
        if doc_pair.folderish:
            if LINUX:
                # This does not make it on GNU/Linux, and it would break
                # test_move_and_copy_paste_folder_original_location_from_child_stopped().
                # The call to dao.replace_local_paths() is revelant on macOS and Windows only.
                # See NXDRIVE-1690 for more information.
                return

            dao.replace_local_paths(doc_pair.local_path, local_info.path)

        if (
            WINDOWS
            and old_local_path is not None
            and self._windows_folder_scan_delay > 0
            and old_local_path in self._folder_scan_events
        ):
            with self.lock:
                log.info(
                    "Update folders to scan queue: move "
                    f"from {old_local_path!r} to {rel_path!r}"
                )
                self._folder_scan_events.pop(old_local_path, None)
                t = mktime(local_info.last_modification_time.timetuple())
                self._folder_scan_events[rel_path] = t, doc_pair

    def _handle_watchdog_event_on_known_pair(
        self, doc_pair: DocPair, evt: FileSystemEvent, rel_path: Path, /
    ) -> None:
        log.debug(f"Watchdog event {evt!r} on known pair {doc_pair!r}")
        dao = self.dao
        acquired_pair = None

        try:
            acquired_pair = dao.acquire_state(self.thread_id, doc_pair.id)
            if acquired_pair:
                if evt.event_type == "deleted":
                    self._handle_delete_on_known_pair(doc_pair)
                else:
                    self._handle_watchdog_event_on_known_acquired_pair(
                        acquired_pair, evt, rel_path
                    )
            else:
                log.debug(f"Don't update as in process {doc_pair!r}")
        except sqlite3.OperationalError:
            log.debug(f"Don't update as cannot acquire {doc_pair!r}")
        finally:
            dao.release_state(self.thread_id)

            # TODO: This piece of code is only useful on Windows when creating a file inside a read-only folder.
            # TODO: Remove everything with NXDRIVE-1095.
            if WINDOWS and acquired_pair:
                refreshed_pair = dao.get_state_from_id(acquired_pair.id)
                if refreshed_pair and refreshed_pair.pair_state not in (
                    "synchronized",
                    "unsynchronized",
                ):
                    log.debug(
                        "Re-queuing acquired, released and refreshed "
                        f"state {refreshed_pair!r}"
                    )
                    dao._queue_pair_state(
                        refreshed_pair.id,
                        refreshed_pair.folderish,
                        refreshed_pair.pair_state,
                        pair=refreshed_pair,
                    )
                    self.engine.send_metric("sync", "error", "WINDOWS_RO_FOLDER")

    def _handle_watchdog_event_on_known_acquired_pair(
        self, doc_pair: DocPair, evt: FileSystemEvent, rel_path: Path, /
    ) -> None:
        client = self.local
        dao = self.dao
        local_info = client.try_get_info(rel_path)

        if not local_info:
            return

        if evt.event_type == "created":
            # NXDRIVE-471 case maybe
            remote_ref = client.get_remote_id(rel_path)
            if not remote_ref:
                log.info(
                    "Created event on a known pair with no remote_ref, this should "
                    f"only happen in case of a quick move and copy-paste: {doc_pair!r}"
                )
                if local_info.get_digest() == doc_pair.local_digest:
                    return

                log.info(
                    "Created event on a known pair with no remote_ref "
                    f"but with different digest: {doc_pair!r}"
                )
            else:
                # NXDRIVE-509
                log.info(
                    f"Created event on a known pair with a remote_ref: {doc_pair!r}"
                )

        # Unchanged folder
        if doc_pair.folderish:
            # Unchanged folder, only update last_local_updated
            dao.update_local_modification_time(doc_pair, local_info)
            return

        # We can't allow this branch to be taken for big files
        # because computing their digest will explode everything.
        # This code is taken _a lot_ when copying big files, so it
        # makes sens to bypass this check.
        if (
            local_info.size < Options.big_file * 1024 * 1024
            and doc_pair.pair_state == "synchronized"
        ):
            digest = local_info.get_digest()
            # Unchanged digest, can be the case if only the last
            # modification time or file permissions have been updated
            if doc_pair.local_digest == digest:
                log.info(
                    f"Digest has not changed for {rel_path!r} (watchdog event "
                    f"[{evt.event_type}]), only update last_local_updated"
                )
                if not local_info.remote_ref and doc_pair.remote_ref:
                    client.set_remote_id(rel_path, doc_pair.remote_ref)
                dao.update_local_modification_time(doc_pair, local_info)
                return

            doc_pair.local_digest = digest
            doc_pair.local_state = "modified"

        if evt.event_type == "modified":
            # Handle files that take some time to be fully copied
            ongoing_copy = False
            if local_info.size != doc_pair.size:
                # Check the pair state as:
                #  - a synced document can be modified and we need to handle it
                #  - a conflicted file can be manually resolved using the local version and we need to handle it too
                if doc_pair.pair_state not in ("synchronized", "locally_resolved"):
                    log.debug("Size has changed (copy must still be running)")
                    doc_pair.local_digest = UNACCESSIBLE_HASH
                    ongoing_copy = True
            elif doc_pair.local_digest == UNACCESSIBLE_HASH:
                log.debug("Unaccessible hash (copy must still be running)")
                ongoing_copy = True
            if ongoing_copy:
                if not local_info.remote_ref and doc_pair.remote_ref:
                    try:
                        client.set_remote_id(rel_path, doc_pair.remote_ref)
                        local_info.remote_ref = doc_pair.remote_ref
                    except OSError:
                        log.warning("Cannot set the remote ID", exc_info=True)
                self.remove_void_transfers(doc_pair)
                return

            if doc_pair.remote_ref and doc_pair.remote_ref != local_info.remote_ref:
                original_pair = dao.get_normal_state_from_remote(local_info.remote_ref)
                original_info = None
                if original_pair:
                    original_info = client.try_get_info(original_pair.local_path)

                if (
                    MAC
                    and original_info
                    and original_info.remote_ref == local_info.remote_ref
                ):
                    log.info(
                        "macOS has postponed overwriting of xattr, "
                        f"need to reset remote_ref for {doc_pair!r}"
                    )
                    # We are in a copy/paste situation with OS overriding
                    # the xattribute
                    client.set_remote_id(doc_pair.local_path, doc_pair.remote_ref)

                # This happens on overwrite through Windows Explorer
                if not original_info:
                    client.set_remote_id(doc_pair.local_path, doc_pair.remote_ref)

        self.remove_void_transfers(doc_pair)

        # Update state
        dao.update_local_state(doc_pair, local_info)

    def handle_watchdog_root_event(self, evt: FileSystemEvent, /) -> None:
        if evt.event_type == "deleted":
            log.warning("Root has been deleted")
            self.rootDeleted.emit()
        elif evt.event_type == "moved":
            dst = normalize(evt.dest_path)
            log.warning(f"Root has been moved to {dst!r}")
            self.rootMoved.emit(dst)

    @tooltip("Handle watchdog event")
    def handle_watchdog_event(self, evt: FileSystemEvent, /) -> None:
        self._metrics["last_event"] = current_milli_time()

        if not evt.src_path:
            log.warning(f"Skipping event without a source path: {evt!r}")
            return

        if WINDOWS and ":" in splitext(evt.src_path)[1]:
            # An event on the NTFS stream ("c:\folder\file.ext:nxdrive"), it should not happen.
            # The cause is not yet known, need more data to understand how it happens.
            log.warning(f"Skipping event on the NTFS stream: {evt!r}")
            return

        dao, client = self.dao, self.local
        dst_path = getattr(evt, "dest_path", "")

        evt_log = f"Handling watchdog event [{evt.event_type}] on {evt.src_path!r}"
        if dst_path:
            evt_log += f" to {dst_path!r}"
        log.info(evt_log)

        try:
            # Set action=False to avoid forced normalization before
            # checking for banned files
            src_path = normalize(evt.src_path, action=False)

            if evt.event_type == "moved":
                # Ignore normalization of the filename on the file system
                # See https://jira.nuxeo.com/browse/NXDRIVE-188

                if force_decode(dst_path) in (
                    str(src_path),
                    force_decode(evt.src_path.strip()),
                ):
                    log.info(
                        f"Ignoring move from {evt.src_path!r} to normalized {dst_path!r}"
                    )
                    return

            if client.get_path(src_path) == ROOT:
                self.handle_watchdog_root_event(evt)
                return

            parent_rel_path = client.get_path(src_path.parent)
            # Don't care about ignored file, unless it is moved
            if evt.event_type != "moved" and client.is_ignored(
                parent_rel_path, src_path.name
            ):
                log.info(f"Ignoring action on banned file: {evt!r}")
                return

            if client.is_temp_file(src_path):
                log.info(f"Ignoring temporary file: {evt!r}")
                return

            # This time, let action=True to force normalization
            # and refresh all the variables
            src_path = normalize(evt.src_path)
            rel_path = client.get_path(src_path)
            parent_rel_path = client.get_path(src_path.parent)

            doc_pair = dao.get_state_from_local(rel_path)
            if doc_pair:
                self.engine.manager.osi.send_sync_status(doc_pair, src_path)
                if doc_pair.pair_state == "unsynchronized":
                    log.info(
                        f"Ignoring {doc_pair.local_path!r} as marked unsynchronized"
                    )

                    if evt.event_type in ("deleted", "moved"):
                        path = (
                            evt.dest_path if evt.event_type == "moved" else evt.src_path
                        )
                        ignore, _ = is_generated_tmp_file(basename(path))
                        if not ignore:
                            log.info(
                                f"Removing pair state for {evt.event_type} event: "
                                f"{doc_pair!r}"
                            )
                            dao.remove_state(doc_pair)
                    return
                if (
                    evt.event_type == "created"
                    and doc_pair.local_state == "deleted"
                    and doc_pair.pair_state == "locally_deleted"
                ):
                    log.info(
                        "File has been deleted/created quickly, "
                        "it must be a replace."
                    )
                    doc_pair.local_state = "modified"
                    doc_pair.remote_state = "unknown"
                    dao.update_local_state(doc_pair, client.get_info(rel_path))

                if evt.event_type == "moved":
                    self._handle_move_on_known_pair(doc_pair, evt, rel_path)
                else:
                    self._handle_watchdog_event_on_known_pair(doc_pair, evt, rel_path)
                return

            if evt.event_type == "deleted":
                log.info(f"Unknown pair deleted: {rel_path!r}")
                return

            if evt.event_type == "moved":
                dest_filename = basename(evt.dest_path)
                if client.is_ignored(parent_rel_path, dest_filename):
                    log.info(f"Ignoring move on banned file: {evt!r}")
                    return

                src_path = normalize(evt.dest_path)
                rel_path = client.get_path(src_path)
                local_info = client.try_get_info(rel_path)
                doc_pair = dao.get_state_from_local(rel_path)

                # If the file exists but not the pair
                if local_info is not None and doc_pair is None:
                    # Check if it is a pair that we loose track of
                    if local_info.remote_ref:
                        doc_pair = dao.get_normal_state_from_remote(
                            local_info.remote_ref
                        )
                        if doc_pair is not None and not client.exists(
                            doc_pair.local_path
                        ):
                            log.info(f"Pair re-moved detected for {doc_pair!r}")

                            # Can be a move inside a folder that has also moved
                            self._handle_move_on_known_pair(doc_pair, evt, rel_path)
                            return

                    rel_parent_path = client.get_path(src_path.parent)
                    if not rel_parent_path:
                        rel_parent_path = ROOT
                    dao.insert_local_state(local_info, rel_parent_path)

                    # An event can be missed inside a new created folder as
                    # watchdog will put listener after it
                    if local_info.folderish:
                        self.scan_pair(rel_path)
                        if WINDOWS:
                            doc_pair = dao.get_state_from_local(rel_path)
                            if doc_pair:
                                self._schedule_win_folder_scan(doc_pair)
                return

            # if the pair is modified and not known consider as created
            if evt.event_type not in ("created", "modified"):
                log.info(f"Unhandled case: {evt!r} {rel_path!r} {src_path.name!r}")
                return

            # If doc_pair is not None mean
            # the creation has been caught by scan
            # As Windows send a delete / create event for reparent
            local_info = client.try_get_info(rel_path)
            if not local_info:
                log.debug(f"Event on a disappeared file: {evt!r}")
                return

            # This might be a move but Windows don't emit this event...
            if local_info.remote_ref:
                moved = False
                from_pair = dao.get_normal_state_from_remote(local_info.remote_ref)
                if from_pair:
                    if from_pair.processor > 0 or str(from_pair.local_path) == str(
                        rel_path
                    ):
                        # First condition is in process
                        # Second condition is a race condition
                        log.debug(
                            "Ignore creation or modification as the coming pair "
                            f"is being processed: {rel_path!r}"
                        )
                        return

                    # If it is not at the origin anymore, magic teleportation?
                    # Maybe an event crafted from a
                    # delete/create => move on Windows
                    if not client.exists(from_pair.local_path):
                        # Check if the destination is writable
                        dst_parent = dao.get_state_from_local(rel_path.parent)
                        if dst_parent and not dst_parent.remote_can_create_child:
                            log.info(
                                "Moving to a read-only folder: "
                                f"{from_pair!r} -> {dst_parent!r}"
                            )
                            dao.unsynchronize_state(from_pair, "READONLY")
                            self.engine.newReadonly.emit(
                                from_pair.local_name, dst_parent.remote_name
                            )
                            return

                        # Check if the source is read-only, in that case we
                        # convert the move to a creation
                        src_parent = dao.get_state_from_local(
                            from_pair.local_path.parent
                        )
                        if src_parent and not src_parent.remote_can_create_child:
                            self.engine.newReadonly.emit(
                                from_pair.local_name,
                                dst_parent.remote_name if dst_parent else None,
                            )
                            log.info(
                                "Converting the move to a create for "
                                f"{from_pair!r} -> {src_path!r}"
                            )
                            from_pair.local_path = rel_path
                            from_pair.local_state = "created"
                            from_pair.remote_state = "unknown"
                            client.remove_remote_id(rel_path)
                        else:
                            log.info(
                                f"Move from {from_pair.local_path!r} to {rel_path!r}"
                            )
                            from_pair.local_state = "moved"
                        dao.update_local_state(from_pair, client.get_info(rel_path))
                        moved = True
                    else:
                        # NXDRIVE-471: Possible move-then-copy case
                        doc_pair_full_path = client.abspath(rel_path)
                        doc_pair_ctime = self.get_creation_time(doc_pair_full_path)
                        from_pair_full_path = client.abspath(from_pair.local_path)
                        from_pair_ctime = self.get_creation_time(from_pair_full_path)
                        log.debug(
                            f"doc_pair_full_path={doc_pair_full_path!r}, "
                            f"doc_pair_ctime={doc_pair_ctime}, "
                            f"from_pair_full_path={from_pair_full_path!r}, "
                            f"version={from_pair.version}"
                        )

                        # If file at the original location is newer, it is
                        # moved to the new location earlier then copied back
                        # (what else can it be?)
                        if (
                            evt.event_type == "created"
                            and from_pair_ctime > doc_pair_ctime
                        ):
                            log.debug(
                                f"Found moved file {doc_pair_full_path!r} "
                                f"(times: from={from_pair_ctime}, to={doc_pair_ctime})"
                            )
                            from_pair.local_state = "moved"
                            dao.update_local_state(from_pair, client.get_info(rel_path))
                            dao.insert_local_state(
                                client.get_info(from_pair.local_path),
                                from_pair.local_path.parent,
                            )
                            client.remove_remote_id(from_pair.local_path)
                            moved = True
                        elif (
                            WINDOWS
                            and evt.event_type == "created"
                            and client.is_equal_digests(
                                None, from_pair.local_digest, rel_path
                            )
                        ):
                            # Note: set 1st argument of is_equal_digests() to None
                            # to force digest computation.
                            # This code is needed and tested by test_copy_paste_normal() on Windows.
                            log.debug(
                                f"Copy-paste then rename case for {doc_pair_full_path!r} (same digests)"
                            )
                            client.remove_remote_id(from_pair.local_path)
                            moved = True

                if WINDOWS:
                    with self.lock:
                        if local_info.remote_ref in self._delete_events:
                            log.info(
                                "Found creation in delete event, handle move instead"
                            )
                            # Should be cleaned
                            if not moved:
                                doc_pair = self._delete_events[local_info.remote_ref][1]
                                doc_pair.local_state = "moved"
                                dao.update_local_state(
                                    doc_pair, client.get_info(rel_path)
                                )
                            del self._delete_events[local_info.remote_ref]
                            return

                if from_pair is not None:
                    if moved:
                        # Stop the process here
                        return
                    log.info(
                        f"Copy paste from {from_pair.local_path!r} to {rel_path!r}"
                    )
                    client.remove_remote_id(rel_path)
            dao.insert_local_state(local_info, parent_rel_path)

            # An event can be missed inside a new created folder as
            # watchdog will put listener after it
            if local_info.folderish:
                self.scan_pair(rel_path)
                if WINDOWS:
                    doc_pair = dao.get_state_from_local(rel_path)
                    if doc_pair:
                        self._schedule_win_folder_scan(doc_pair)
        except ThreadInterrupt:
            raise
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                # FileExistsError, this is probably a normalization renaming gone wrong.
                if evt.event_type == "created":
                    # Creations generate both a modified event and a created event,
                    # we don't want to display two messages.
                    return
                log.warning(f"Cannot synchronize both files with same name: {exc}")
                normpath = normalize(evt.src_path, action=False)
                if normpath.exists():
                    self.fileAlreadyExists.emit(normpath, Path(evt.src_path))
                    return
                dst_path = getattr(evt, "dest_path")
                if not dst_path:
                    return
                normpath = normalize(dst_path, action=False)
                if normpath.exists():
                    self.fileAlreadyExists.emit(normpath, Path(dst_path))
                    return
            log.exception("Watchdog OS exception")
        except Exception:
            # Workaround to forward unhandled exceptions to sys.excepthook between all Qthreads
            sys.excepthook(*sys.exc_info())
            log.exception("Watchdog exception")

    def _schedule_win_folder_scan(self, doc_pair: DocPair, /) -> None:
        # On Windows schedule another recursive scan to make sure I/Os finished
        # ex: copy/paste, move
        if self._win_folder_scan_interval <= 0 or self._windows_folder_scan_delay <= 0:
            return

        with self.lock:
            local_info = self.local.try_get_info(doc_pair.local_path)
            if local_info:
                log.info(f"Add pair to folder scan events: {doc_pair!r}")
                self._folder_scan_events[doc_pair.local_path] = (
                    mktime(local_info.last_modification_time.timetuple()),
                    doc_pair,
                )


class DriveFSEventHandler(PatternMatchingEventHandler):
    def __init__(
        self, watcher: Worker, /, *, ignore_patterns: List[str] = None
    ) -> None:
        super().__init__(ignore_patterns=ignore_patterns)
        self.counter = 0
        self.watcher = watcher

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__}"
            f" patterns={self.patterns!r},"
            f" ignore_patterns={self.ignore_patterns!r},"
            f" ignore_directories={self.ignore_directories},"
            f" case_sensitive={self.case_sensitive}"
            ">"
        )

    def on_any_event(self, event: FileSystemEvent, /) -> None:
        self.counter += 1
        log.debug(f"Queueing watchdog: {event!r}")
        self.watcher.watchdog_queue.put(event)
