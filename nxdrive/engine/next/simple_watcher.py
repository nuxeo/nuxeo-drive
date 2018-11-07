# coding: utf-8
import copy
import os
from logging import getLogger
from queue import Queue
from time import sleep, time
from typing import Union

from watchdog.events import DirModifiedEvent, FileSystemEvent

from ...client.local_client import FileInfo
from ...engine.watcher.local_watcher import LocalWatcher
from ...exceptions import ThreadInterrupt
from ...utils import current_milli_time, normalize_event_filename

__all__ = ("SimpleWatcher",)

log = getLogger(__name__)


class SimpleWatcher(LocalWatcher):
    """
    Only handle modified event in this class. As we cannot
    rely on DELETE/CREATE etc just using the modification
    with a folder check should do the trick.
    """

    def __init__(self, engine: "Engine", dao: "EngineDAO") -> None:
        super().__init__(engine, dao)
        self._scan_delay = 1
        self._to_scan = dict()

    def _push_to_scan(self, info: Union[FileInfo, str]) -> None:
        if isinstance(info, FileInfo):
            super()._scan_recursive(info)
            return

        log.warning(f"should scan: {info}")
        self._to_scan[info] = current_milli_time()

    def empty_events(self) -> bool:
        return self.watchdog_queue.empty() and len(self._to_scan) == 0

    def get_scan_delay(self) -> int:
        return self._scan_delay

    def is_inside(self, abspath: str) -> bool:
        return abspath.startswith(self.local.base_folder)

    def is_pending_scan(self, ref: str) -> bool:
        return ref in self._to_scan

    def handle_watchdog_move(self, evt: FileSystemEvent, _, rel_path: str) -> None:
        # Dest
        dst_path = normalize_event_filename(evt.dest_path)
        if self.local.is_temp_file(os.path.basename(dst_path)):
            return
        log.warning(f"handle watchdog move: {evt!r}")
        dst_rel_path = self.local.get_path(dst_path)
        doc_pair = self._dao.get_state_from_local(rel_path)
        # Add for security src_path and dest_path parent - not sure it is needed
        self._push_to_scan(os.path.dirname(rel_path))
        if self.is_inside(dst_path):
            dst_rel_path = self.local.get_path(dst_path)
            self._push_to_scan(os.path.dirname(dst_rel_path))
        if not doc_pair:
            # Scan new parent
            log.warning("NO PAIR")
            return
        # It is not yet created no need to move it
        if doc_pair.local_state != "created":
            doc_pair.local_state = "moved"
        local_info = self.local.get_info(dst_rel_path, raise_if_missing=False)
        if local_info is None:
            log.warning("Should not disapear")
            return
        self._dao.update_local_state(doc_pair, local_info, versioned=True)
        log.warning("has update with moved status")

    def handle_watchdog_event(self, evt: FileSystemEvent) -> None:
        self._metrics["last_event"] = current_milli_time()
        # For creation and deletion just update the parent folder
        src_path = normalize_event_filename(evt.src_path)
        rel_path = self.local.get_path(src_path)
        file_name = os.path.basename(src_path)
        if self.local.is_temp_file(file_name) or rel_path == "/.partials":
            return
        if evt.event_type == "moved":
            self.handle_watchdog_move(evt, src_path, rel_path)
            return
        # Dont care about ignored file, unless it is moved
        if self.local.is_ignored(os.path.dirname(rel_path), file_name):
            return
        log.warning(f"Got evt: {evt!r}")
        if len(rel_path) == 0 or rel_path == "/":
            self._push_to_scan("/")
            return
        # If not modified then we will scan the parent folder later
        if evt.event_type != "modified":
            log.warning(rel_path)
            parent_rel_path = os.path.dirname(rel_path)
            if parent_rel_path == "":
                parent_rel_path = "/"
            self._push_to_scan(parent_rel_path)
            return
        file_name = os.path.basename(src_path)
        doc_pair = self._dao.get_state_from_local(rel_path)
        if not os.path.exists(src_path):
            log.warning(f"Event on a disappeared file: {evt!r} {rel_path} {file_name}")
            return
        if doc_pair is not None and doc_pair.processor > 0:
            log.warning(f"Don't update as in process {doc_pair!r}")
            return
        if isinstance(evt, DirModifiedEvent):
            self._push_to_scan(rel_path)
        else:
            local_info = self.local.get_info(rel_path, raise_if_missing=False)
            if local_info is None or doc_pair is None:
                # Suspicious
                return
            digest = local_info.get_digest()
            if doc_pair.local_state != "created":
                if doc_pair.local_digest != digest:
                    doc_pair.local_state = "modified"
            doc_pair.local_digest = digest
            log.warning(f"file is updated: {doc_pair!r}")
            self._dao.update_local_state(doc_pair, local_info, versioned=True)

    def _execute(self) -> None:
        try:
            self._init()
            if not self.local.exists("/"):
                self.rootDeleted.emit()
                return
            self.watchdog_queue = Queue()
            self._setup_watchdog()
            log.debug("Watchdog setup finished")
            self._scan()

            # Check windows de-queue and folder scan
            # only every 100 loops (every 1s)
            current_time_millis = int(round(time() * 1000))
            self._win_delete_interval = current_time_millis
            self._win_folder_scan_interval = current_time_millis
            i = 0
            while True:
                self._interact()
                sleep(0.01)
                while not self.watchdog_queue.empty():
                    # Dont retest if already local scan
                    evt = self.watchdog_queue.get()
                    self.handle_watchdog_event(evt)
                # Check to scan
                i += 1
                if i % 100 != 0:
                    continue
                i = 0
                threshold_time = current_milli_time() - 1000 * self._scan_delay
                # Need to create a list of to scan as
                # the dictionary cannot grow while iterating
                local_scan = []
                for path, last_event_time in self._to_scan.items():
                    if last_event_time < threshold_time:
                        local_scan.append(path)
                for path in local_scan:
                    self._scan_path(path)
                    # Dont delete if the time has changed since last scan
                    if self._to_scan[path] < threshold_time:
                        del self._to_scan[path]
                if len(self._delete_files):
                    # Enforce scan of all others folders
                    # to not loose track of moved file
                    self._scan_handle_deleted_files()
        except ThreadInterrupt:
            raise
        finally:
            self._stop_watchdog()

    def _scan_handle_deleted_files(self) -> None:
        log.warning(f"delete files are: {self._delete_files!r}")
        # Need to check for the current file
        to_deletes = copy.copy(self._delete_files)
        # Enforce the scan of all folders
        # to check if the file hasn't moved there
        for path, _ in self._to_scan.items():
            self._scan_path(path)
        for deleted in to_deletes:
            if deleted not in self._delete_files:
                continue
            if deleted not in self._protected_files:
                self._dao.delete_local_state(self._delete_files[deleted])
            else:
                del self._protected_files[deleted]
            # Really delete file then
            del self._delete_files[deleted]

    def _scan_path(self, path: str) -> None:
        if self.local.exists(path):
            log.warning(
                f"Scan delayed folder: {path}:{len(self.local.get_children_info(path))}"
            )
            local_info = self.local.get_info(path, raise_if_missing=False)
            if local_info is not None:
                self._scan_recursive(local_info, False)
                log.warning("scan delayed done")
        else:
            log.warning(f"Cannot scan delayed deleted folder: {path}")
