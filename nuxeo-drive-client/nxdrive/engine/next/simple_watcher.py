__author__ = 'loopingz'
from nxdrive.engine.watcher.local_watcher import LocalWatcher, DriveFSRootEventHandler, normalize_event_filename
from time import sleep, time, mktime
from nxdrive.utils import current_milli_time
import os
import sqlite3
import copy
from Queue import Queue
from watchdog.events import FileSystemEventHandler, DirModifiedEvent
from nxdrive.engine.workers import ThreadInterrupt
from nxdrive.engine.activity import Action
from nxdrive.logging_config import get_logger
from nxdrive.client.local_client import FileInfo
log = get_logger(__name__)
'''
Only handle modified event in this class
As we cannot rely on DELETE/CREATE etc just using the modification with a folder check should do the trick
'''

class SimpleWatcher(LocalWatcher):
    def __init__(self, engine, dao):
        super(SimpleWatcher, self).__init__(engine, dao)
        self._scan_delay = 1
        self._to_scan = dict()
        self._last_scan = dict()

    def _push_to_scan(self, info):
        if isinstance(info, FileInfo):
            ref = info.path
            super(SimpleWatcher, self)._push_to_scan(info)
            return
        else:
            ref = info
        log.warn("should scan: %s", ref)
        self._to_scan[ref] = current_milli_time()

    def empty_events(self):
        return self._watchdog_queue.empty() and len(self._to_scan) == 0

    def get_scan_delay(self):
        return self._scan_delay

    def is_pending_scan(self, ref):
        return ref in self._to_scan

    def handle_watchdog_move(self, evt, src_path, rel_path):
        # Dest
        dst_path = normalize_event_filename(evt.dest_path)
        if self.client.is_temp_file(os.path.basename(dst_path)):
            return
        log.warn("handle watchdog move: %r", evt)
        dst_rel_path = self.client.get_path(dst_path)
        doc_pair = self._dao.get_state_from_local(rel_path)
        # Add for security src_path and dest_path parent - not sure it is needed
        self._push_to_scan(os.path.dirname(rel_path))
        if self.client.is_inside(dst_path):
            dst_rel_path = self.client.get_path(dst_path)
            self._push_to_scan(os.path.dirname(dst_rel_path))
        if (doc_pair is None):
            # Scan new parent
            log.warn("NO PAIR")
            return
        # It is not yet created no need to move it
        if doc_pair.local_state != 'created':
            doc_pair.local_state = 'moved'
        old_local_path = doc_pair.local_path
        local_info = self.client.get_info(dst_rel_path, raise_if_missing=False)
        if local_info is None:
            log.warn("Should not disapear")
            return
        self._dao.update_local_state(doc_pair, local_info, versionned=True)
        log.warn("has update with moved status")

    def handle_watchdog_event(self, evt):
        self._metrics['last_event'] = current_milli_time()
        # For creation and deletion just update the parent folder
        src_path = normalize_event_filename(evt.src_path)
        rel_path = self.client.get_path(src_path)
        file_name = os.path.basename(src_path)
        if self.client.is_temp_file(file_name) or rel_path == '/.partials':
            return
        if evt.event_type == 'moved':
            self.handle_watchdog_move(evt, src_path, rel_path)
            return
        # Dont care about ignored file, unless it is moved
        if self.client.is_ignored(os.path.dirname(rel_path), file_name):
            return
        log.warn("Got evt: %r", evt)
        if len(rel_path) == 0 or rel_path == '/':
            self._push_to_scan('/')
            return
        # If not modified then we will scan the parent folder later
        if evt.event_type != 'modified':
            log.warn(rel_path)
            parent_rel_path = os.path.dirname(rel_path)
            if parent_rel_path == "":
                parent_rel_path = '/'
            self._push_to_scan(parent_rel_path)
            return
        file_name = os.path.basename(src_path)
        doc_pair = self._dao.get_state_from_local(rel_path)
        if not os.path.exists(src_path):
            log.warn("Event on a disappeared file: %r %s %s", evt, rel_path, file_name)
            return
        if doc_pair is not None and doc_pair.processor > 0:
            log.warn("Don't update as in process %r", doc_pair)
            return
        if isinstance(evt, DirModifiedEvent):
            self._push_to_scan(rel_path)
        else:
            local_info = self.client.get_info(rel_path, raise_if_missing=False)
            if local_info is None or doc_pair is None:
                # Suspicious
                return
            digest = local_info.get_digest()
            if doc_pair.local_state != 'created':
                if doc_pair.local_digest != digest:
                    doc_pair.local_state = 'modified'
            doc_pair.local_digest = digest
            log.warn("file is updated: %r", doc_pair)
            self._dao.update_local_state(doc_pair, local_info, versionned=True)

    def _execute(self):
        try:
            trigger_local_scan = False
            self._init()
            if not self.client.exists('/'):
                self.rootDeleted.emit()
                return
            self._action = Action("Setup watchdog")
            self._watchdog_queue = Queue()
            self._setup_watchdog()
            log.debug("Watchdog setup finished")
            self._action = Action("Full local scan")
            self._scan()
            self._end_action()
            # Check windows dequeue and folder scan only every 100 loops ( every 1s )
            current_time_millis = int(round(time() * 1000))
            self._win_delete_interval = current_time_millis
            self._win_folder_scan_interval = current_time_millis
            i = 0
            while (1):
                self._interact()
                sleep(0.01)
                while (not self._watchdog_queue.empty()):
                    # Dont retest if already local scan
                    evt = self._watchdog_queue.get()
                    self.handle_watchdog_event(evt)
                # Check to scan
                i += 1
                if i % 100 != 0:
                    continue
                i = 0
                threshold_time = current_milli_time() - 1000 * self._scan_delay
                # Need to create a list of to scan as the dictionary cannot grow while iterating
                local_scan = []
                for path, last_event_time in self._to_scan.iteritems():
                    if last_event_time < threshold_time:
                        local_scan.append(path)
                for path in local_scan:
                    self._scan_path(path)
                    # Dont delete if the time has changed since last scan
                    if self._to_scan[path] < threshold_time:
                        del self._to_scan[path]
                if (len(self._delete_files)):
                    # Enforce scan of all others folders to not loose track of moved file
                    self._scan_handle_deleted_files()
        except ThreadInterrupt:
            raise
        finally:
            self._stop_watchdog()

    def _scan_handle_deleted_files(self):
        log.warn("delete files are: %r", self._delete_files)
        # Need to check for the current file
        to_deletes = copy.copy(self._delete_files)
        # Enforce the scan of all folders to check if the file hasnt moved there
        for path, last_event_time in self._to_scan.iteritems():
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

    def _scan_path(self, path):
        if self.client.exists(path):
            log.warn("Scan delayed folder: %s:%d", path, len(self.client.get_children_info(path)))
            local_info = self.client.get_info(path, raise_if_missing=False)
            if local_info is not None:
                self._scan_recursive(local_info, False)
                log.warn("scan delayed done")
        else:
            log.warn("Cannot scan delayed deleted folder: %s", path)
