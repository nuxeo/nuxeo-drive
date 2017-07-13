# coding: utf-8
import errno
import os
import re
import sqlite3
import unicodedata
from Queue import Queue
from threading import Lock
from time import mktime, sleep, time

from PyQt4.QtCore import pyqtSignal, pyqtSlot
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_SUFFIX
from nxdrive.client.local_client import LocalClient
from nxdrive.engine.activity import Action
from nxdrive.engine.workers import EngineWorker, ThreadInterrupt
from nxdrive.logging_config import get_logger
from nxdrive.osi import AbstractOSIntegration
from nxdrive.utils import current_milli_time, is_office_temp_file

log = get_logger(__name__)

# Windows 2s between resolution of delete event
WIN_MOVE_RESOLUTION_PERIOD = 2000

TEXT_EDIT_TMP_FILE_PATTERN = ur'.*\.rtf\.sb\-(\w)+\-(\w)+$'

if AbstractOSIntegration.is_windows():
    import win32api


def is_office_file(_):
    # Don't filter for now
    return True


def is_text_edit_tmp_file(name):
    return re.match(TEXT_EDIT_TMP_FILE_PATTERN, name)


class LocalWatcher(EngineWorker):
    localScanFinished = pyqtSignal()
    rootMoved = pyqtSignal(str)
    rootDeleted = pyqtSignal()

    def __init__(self, engine, dao):
        super(LocalWatcher, self).__init__(engine, dao)
        self.unhandle_fs_event = False
        self._event_handler = None
        self._windows_queue_threshold = 50
        # Delay for the scheduled recursive scans of a created / modified / moved folder under Windows
        self._windows_folder_scan_delay = 10000  # 10 seconds
        self._windows_watchdog_event_buffer = 8192
        self._windows = AbstractOSIntegration.is_windows()
        if self._windows:
            log.debug('Windows detected so delete event will be delayed by %dms', WIN_MOVE_RESOLUTION_PERIOD)
        # TODO Review to delete
        self._init()

    def _init(self):
        self.local_full_scan = dict()
        self._local_scan_finished = False
        self.client = self._engine.get_local_client()
        self._metrics = dict()
        self._metrics['last_local_scan_time'] = -1
        self._metrics['new_files'] = 0
        self._metrics['update_files'] = 0
        self._metrics['delete_files'] = 0
        self._metrics['last_event'] = 0
        self._observer = None
        self._root_observer = None
        self._win_lock = Lock()
        self._delete_events = dict()
        self._folder_scan_events = dict()

    def set_windows_queue_threshold(self, size):
        self._windows_queue_threshold = size

    def get_windows_queue_threshold(self):
        return self._windows_queue_threshold

    def set_windows_folder_scan_delay(self, size):
        self._windows_folder_scan_delay = size

    def get_windows_folder_scan_delay(self):
        return self._windows_folder_scan_delay

    def set_windows_watchdog_event_buffer(self, size):
        self._windows_watchdog_event_buffer = size

    def get_windows_watchdog_event_buffer(self):
        return self._windows_watchdog_event_buffer

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
            while True:
                self._interact()
                sleep(0.01)
                if trigger_local_scan:
                    self._action = Action("Full local scan")
                    self._scan()
                    trigger_local_scan = False
                    self._end_action()
                while not self._watchdog_queue.empty():
                    # Don't retest if already local scan
                    if not trigger_local_scan and self._watchdog_queue.qsize() > self._windows_queue_threshold:
                        log.debug('Windows queue threshold exceeded, will trigger local scan: %d events', self._watchdog_queue.qsize())
                        trigger_local_scan = True
                        self._delete_events.clear()
                        self._folder_scan_events.clear()
                        self._watchdog_queue = Queue()
                        break
                    evt = self._watchdog_queue.get()
                    self.handle_watchdog_event(evt)
                    self._win_delete_check()
                    self._win_folder_scan_check()
                self._win_delete_check()
                self._win_folder_scan_check()

        except ThreadInterrupt:
            raise
        finally:
            self._stop_watchdog()

    def win_queue_empty(self):
        return not self._delete_events

    def get_win_queue_size(self):
        return len(self._delete_events)

    def _win_delete_check(self):
        if self._windows and self._win_delete_interval < int(round(time() * 1000)) - WIN_MOVE_RESOLUTION_PERIOD:
            self._action = Action("Dequeue delete")
            self._win_dequeue_delete()
            self._end_action()
            self._win_delete_interval = int(round(time() * 1000))

    def _win_dequeue_delete(self):
        self._win_lock.acquire()
        try:
            delete_events = self._delete_events
            for evt in delete_events.values():
                evt_time = evt[0]
                evt_pair = evt[1]
                if current_milli_time() - evt_time < WIN_MOVE_RESOLUTION_PERIOD:
                    log.debug("Win: ignoring delete event as waiting for move resolution period expiration: %r", evt)
                    continue
                if not self.client.exists(evt_pair.local_path):
                    log.debug("Win: handling watchdog delete for event: %r", evt)
                    self._handle_watchdog_delete(evt_pair)
                else:
                    remote_id = self.client.get_remote_id(evt_pair.local_path)
                    if remote_id == evt_pair.remote_ref or remote_id is None:
                        log.debug("Win: ignoring delete event as file still exists: %r", evt)
                    else:
                        log.debug("Win: handling watchdog delete for event: %r", evt)
                        self._handle_watchdog_delete(evt_pair)
                log.debug("Win: dequeuing delete event: %r", evt)
                del self._delete_events[evt_pair.remote_ref]
        except ThreadInterrupt:
            raise
        except:
            log.exception('Win: dequeuing deletion error')
        finally:
            self._win_lock.release()

    def win_folder_scan_empty(self):
        return not self._folder_scan_events

    def get_win_folder_scan_size(self):
        return len(self._folder_scan_events)

    def _win_folder_scan_check(self):
        if (self._windows and self._win_folder_scan_interval > 0 and self._windows_folder_scan_delay > 0
            and self._win_folder_scan_interval < int(round(time() * 1000)) - self._windows_folder_scan_delay):
            self._action = Action("Dequeue folder scan")
            self._win_dequeue_folder_scan()
            self._end_action()
            self._win_folder_scan_interval = int(round(time() * 1000))

    def _win_dequeue_folder_scan(self):
        self._win_lock.acquire()
        try:
            folder_scan_events = self._folder_scan_events.values()
            for evt in folder_scan_events:
                evt_time = evt[0]
                evt_pair = evt[1]
                local_path = evt_pair.local_path
                if current_milli_time() - evt_time < self._windows_folder_scan_delay:
                    log.debug("Win: ignoring folder to scan as waiting for folder scan delay expiration: %r",
                              local_path)
                    continue
                if not self.client.exists(local_path):
                    if local_path in self._folder_scan_events:
                        log.debug("Win: dequeuing folder scan event as folder doesn't exist: %r", local_path)
                        del self._folder_scan_events[local_path]
                    continue
                local_info = self.client.get_info(local_path, raise_if_missing=False)
                if local_info is None:
                    log.trace("Win: dequeuing folder scan event as folder doesn't exist: %r", local_path)
                    del self._folder_scan_events[local_path]
                    continue
                log.debug("Win: handling folder to scan: %r", local_path)
                self.scan_pair(local_path)
                local_info = self.client.get_info(local_path, raise_if_missing=False)
                if local_info is not None and mktime(local_info.last_modification_time.timetuple()) > evt_time:
                    # Re-schedule scan as the folder has been modified since last check
                    self._folder_scan_events[local_path] = (mktime(local_info.last_modification_time.timetuple()),
                                                            evt_pair)
                else:
                    log.debug("Win: dequeuing folder scan event: %r", evt)
                    del self._folder_scan_events[local_path]
        except ThreadInterrupt:
            raise
        except:
            log.exception('Win: dequeuing folder scan error')
        finally:
            self._win_lock.release()

    def _scan(self):
        log.debug("Full scan started")
        start_ms = current_milli_time()
        to_pause = not self._engine.get_queue_manager().is_paused()
        if to_pause:
            self._suspend_queue()
        self._delete_files = dict()
        self._protected_files = dict()

        info = self.client.get_info(u'/')
        self._scan_recursive(info)
        self._scan_handle_deleted_files()
        self._metrics['last_local_scan_time'] = current_milli_time() - start_ms
        log.debug("Full scan finished in %dms", self._metrics['last_local_scan_time'])
        self._local_scan_finished = True
        if to_pause:
            self._engine.get_queue_manager().resume()
        self.localScanFinished.emit()

    def _scan_handle_deleted_files(self):
        for deleted in self._delete_files:
            if deleted in self._protected_files:
                continue
            self._dao.delete_local_state(self._delete_files[deleted])
        self._delete_files = dict()

    def get_metrics(self):
        metrics = super(LocalWatcher, self).get_metrics()
        if self._event_handler is not None:
            metrics['fs_events'] = self._event_handler.counter
        return dict(metrics.items() + self._metrics.items())

    def _suspend_queue(self):
        self._engine.get_queue_manager().suspend()
        for processor in self._engine.get_queue_manager().get_processors_on('/', exact_match=False):
            processor.stop()

    @pyqtSlot(str)
    def scan_pair(self, local_path):
        info = self.client.get_info(local_path)
        to_pause = not self._engine.get_queue_manager().is_paused()
        if to_pause:
            self._suspend_queue()
        self._scan_recursive(info, recursive=False)
        self._scan_handle_deleted_files()
        if to_pause:
            self._engine.get_queue_manager().resume()

    def empty_events(self):
        return self._watchdog_queue.empty() and (not AbstractOSIntegration.is_windows() or
                    self.win_queue_empty() and self.win_folder_scan_empty())

    def get_watchdog_queue_size(self):
        return self._watchdog_queue.qsize()

    def get_creation_time(self, child_full_path):
        if self._windows:
            return os.path.getctime(child_full_path)
        else:
            stat = os.stat(child_full_path)
            # Try inode number as on HFS seems to be increasing
            if AbstractOSIntegration.is_mac() and hasattr(stat, "st_ino"):
                return stat.st_ino
            if hasattr(stat, "st_birthtime"):
                return stat.st_birthtime
            return 0

    def _scan_recursive(self, info, recursive=True):
        log.trace('Starting to get DB local children for %r', info.path)
        if recursive:
            # Don't interact if only one level
            self._interact()

        # Load all children from DB
        log.trace('Starting to get DB local children for %r', info.path)
        db_children = self._dao.get_local_children(info.path)
        log.trace('Fetched DB local children for %r', info.path)

        # Create a list of all children by their name
        children = dict()
        to_scan = []
        to_scan_new = []
        for child in db_children:
            children[child.local_name] = child

        # Load all children from FS
        # detect recently deleted children
        log.trace('Starting to get FS children info for %r', info.path)
        try:
            fs_children_info = self.client.get_children_info(info.path)
        except OSError:
            # The folder has been deleted in the mean time
            return
        log.trace('Fetched FS children info for %r', info.path)

        # Get remote children to be able to check if a local child found during the scan is really a new item
        # or if it is just the result of a remote creation performed on the file system but not yet updated in the DB
        # as for its local information
        remote_children = []
        parent_remote_id = self.client.get_remote_id(info.path)
        if parent_remote_id is not None:
            remote_children_pairs = self._dao.get_new_remote_children(parent_remote_id)
            for remote_child_pair in remote_children_pairs:
                remote_children.append(remote_child_pair.remote_name)

        # recursively update children
        for child_info in fs_children_info:
            child_name = os.path.basename(child_info.path)
            child_type = 'folder' if child_info.folderish else 'file'
            if child_name not in children:
                try:
                    remote_id = self.client.get_remote_id(child_info.path)
                    if remote_id is None:
                        # Avoid IntegrityError: do not insert a new pair state if item is already referenced in the DB
                        if remote_children and child_name in remote_children:
                            log.debug('Skip potential new %s as it is the result of a remote creation: %r',
                                      child_type, child_info.path)
                            continue
                        log.debug("Found new %s %s", child_type, child_info.path)
                        self._metrics['new_files'] = self._metrics['new_files'] + 1
                        self._dao.insert_local_state(child_info, info.path)
                    else:
                        log.debug("Found potential moved file %s[%s]", child_info.path, remote_id)
                        doc_pair = self._dao.get_normal_state_from_remote(remote_id)
                        if doc_pair is not None and self.client.exists(doc_pair.local_path):
                            if (not self.client.is_case_sensitive()
                                    and doc_pair.local_path.lower() == child_info.path.lower()):
                                log.debug('Case renaming on a case insensitive filesystem, update info and ignore: %r',
                                                doc_pair)
                                if doc_pair.local_name in children:
                                    del children[doc_pair.local_name]
                                doc_pair.local_state = 'moved'
                                self._dao.update_local_state(doc_pair, child_info)
                                continue
                            # possible move-then-copy case, NXDRIVE-471
                            child_full_path = self.client.abspath(child_info.path)
                            child_creation_time = self.get_creation_time(child_full_path)
                            doc_full_path = self.client.abspath(doc_pair.local_path)
                            doc_creation_time = self.get_creation_time(doc_full_path)
                            log.trace('child_cre_time=%f, doc_cre_time=%f', child_creation_time, doc_creation_time)
                        if doc_pair is None:
                            log.debug("Can't find reference for %s in database, put it in locally_created state",
                                      child_info.path)
                            self._metrics['new_files'] = self._metrics['new_files'] + 1
                            self._dao.insert_local_state(child_info, info.path)
                            self._protected_files[remote_id] = True
                        elif doc_pair.processor > 0:
                            log.debug('Skip pair as it is being processed: %r', doc_pair)
                            continue
                        elif doc_pair.local_path == child_info.path:
                            log.debug('Skip pair as it is not a real move: %r', doc_pair)
                            continue
                        elif not self.client.exists(doc_pair.local_path) or \
                                ( self.client.exists(doc_pair.local_path) and child_creation_time < doc_creation_time):
                                # If file exists at old location, and the file at the original location is newer,
                                #   it is moved to the new location earlier then copied back
                            log.debug("Found moved file")
                            doc_pair.local_state = 'moved'
                            self._dao.update_local_state(doc_pair, child_info)
                            self._protected_files[doc_pair.remote_ref] = True
                            if self.client.exists(doc_pair.local_path) and child_creation_time < doc_creation_time:
                                # Need to put back the new created - need to check maybe if already there
                                log.trace("Found a moved file that has been copy/paste back: %s", doc_pair.local_path)
                                self.client.remove_remote_id(doc_pair.local_path)
                                self._dao.insert_local_state(self.client.get_info(doc_pair.local_path), os.path.dirname(doc_pair.local_path))
                        else:
                            # File still exists - must check the remote_id
                            old_remote_id = self.client.get_remote_id(doc_pair.local_path)
                            if old_remote_id == remote_id:
                                # Local copy paste
                                log.debug("Found a copy-paste of document")
                                self.client.remove_remote_id(child_info.path)
                                self._dao.insert_local_state(child_info, info.path)
                            else:
                                # Moved and renamed
                                log.debug("Moved and renamed: %r", doc_pair)
                                old_pair = self._dao.get_normal_state_from_remote(old_remote_id)
                                if old_pair is not None:
                                    old_pair.local_state = 'moved'
                                    # Check digest also
                                    digest = child_info.get_digest()
                                    if old_pair.local_digest != digest:
                                        old_pair.local_digest = digest
                                    self._dao.update_local_state(old_pair, self.client.get_info(doc_pair.local_path))
                                    self._protected_files[old_pair.remote_ref] = True
                                doc_pair.local_state = 'moved'
                                # Check digest also
                                digest = child_info.get_digest()
                                if doc_pair.local_digest != digest:
                                    doc_pair.local_digest = digest
                                self._dao.update_local_state(doc_pair, child_info)
                                self._protected_files[doc_pair.remote_ref] = True
                    if child_info.folderish:
                        to_scan_new.append(child_info)
                except:
                    log.exception('Error during recursive scan of %r,'
                                  ' ignoring until next full scan',
                                  child_info.path)
                    continue
            else:
                child_pair = children.pop(child_name)
                try:
                    if (child_pair.last_local_updated is not None and
                                unicode(child_info.last_modification_time.strftime("%Y-%m-%d %H:%M:%S"))
                            != child_pair.last_local_updated.split(".")[0] and child_pair.processor == 0):
                        log.trace("Update file %s", child_info.path)
                        remote_ref = self.client.get_remote_id(child_pair.local_path)
                        if remote_ref is not None and child_pair.remote_ref is None:
                            log.debug("Possible race condition between remote and local scan, let's refresh pair: %r",
                                      child_pair)
                            child_pair = self._dao.get_state_from_id(child_pair.id)
                            if child_pair.remote_ref is None:
                                log.debug("Pair not yet handled by remote scan (remote_ref is None) but existing"
                                          " remote_id xattr, let's set it to None: %r", child_pair)
                                self.client.remove_remote_id(child_pair.local_path)
                                remote_ref = None
                        if remote_ref != child_pair.remote_ref:
                            # TO_REVIEW
                            # Load correct doc_pair | Put the others one back to children
                            log.warning(
                                'Detected file substitution: %s (%s/%s)',
                                child_pair.local_path, remote_ref, child_pair.remote_ref)
                            if remote_ref is None:
                                if not child_info.folderish:
                                    # Alternative stream or xattr can have been removed by external software or user
                                    digest = child_info.get_digest()
                                    if child_pair.local_digest != digest:
                                        child_pair.local_digest = digest
                                        child_pair.local_state = 'modified'
                                # NXDRIVE-668: Here we might be in the case of a new folder/file
                                # with the same name as the old name of a renamed folder/file, typically:
                                # - initial state: subfolder01
                                # - rename subfolder01 to subfolder02
                                # - create subfolder01
                                # => substitution will be detected when scanning subfolder01, so we need to
                                # set the remote id and update the local state to avoid performing a wrong
                                # locally_created operation leading to an IntegrityError.
                                # This is true for folders and files.
                                self.client.set_remote_id(child_pair.local_path, child_pair.remote_ref)
                                self._dao.update_local_state(child_pair, child_info)
                                if child_info.folderish:
                                    to_scan.append(child_info)
                                continue
                            old_pair = self._dao.get_normal_state_from_remote(remote_ref)
                            if old_pair is None:
                                self._dao.insert_local_state(child_info, info.path)
                            else:
                                old_pair.local_state = 'moved'
                                # Check digest also
                                digest = child_info.get_digest()
                                if old_pair.local_digest != digest:
                                    old_pair.local_digest = digest
                                self._dao.update_local_state(old_pair, child_info)
                                self._protected_files[old_pair.remote_ref] = True
                            self._delete_files[child_pair.remote_ref] = child_pair
                        if not child_info.folderish:
                            digest = child_info.get_digest()
                            if child_pair.local_digest != digest:
                                child_pair.local_digest = digest
                                child_pair.local_state = 'modified'
                        self._metrics['update_files'] = self._metrics['update_files'] + 1
                        self._dao.update_local_state(child_pair, child_info)
                    if child_info.folderish:
                        to_scan.append(child_info)
                except Exception as e:
                    log.exception('Error with pair %r, increasing error',
                                  child_pair)
                    self.increase_error(child_pair, "SCAN RECURSIVE", exception=e)
                    continue

        for deleted in children.values():
            if deleted.pair_state == "remotely_created" or deleted.remote_state == "created":
                continue
            log.debug("Found deleted file %s", deleted.local_path)
            # May need to count the children to be ok
            self._metrics['delete_files'] += 1
            if deleted.remote_ref is None:
                self._dao.remove_state(deleted)
            else:
                self._delete_files[deleted.remote_ref] = deleted

        for child_info in to_scan_new:
            self._push_to_scan(child_info)

        if not recursive:
            log.trace('Ended recursive local scan of %r', info.path)
            return

        for child_info in to_scan:
            self._push_to_scan(child_info)

        log.trace('Ended recursive local scan of %r', info.path)

    def _push_to_scan(self, info):
        self._scan_recursive(info)

    def _setup_watchdog(self):
        """
        Monkey-patch Watchdog to:
            - Set the Windows hack delay to 0 in WindowsApiEmitter,
              otherwise we might miss some events
            - Increase the ReadDirectoryChangesW buffer size for Windows
        """

        if self._windows:
            try:
                import watchdog.observers as ob
                ob.read_directory_changes.WATCHDOG_TRAVERSE_MOVED_DIR_DELAY = 0
                ob.winapi.BUFFER_SIZE = self._windows_watchdog_event_buffer
            except ImportError:
                log.exception('Cannot import read_directory_changes')
        log.debug('Watching FS modification on : %s', self.client.base_folder)

        # Filter out all ignored suffixes. It will handle custom ones too.
        ignore_patterns = list(['*' + DOWNLOAD_TMP_FILE_SUFFIX])
        ignore_patterns.extend('*' + p for p in self.client.ignored_suffixes)

        self._event_handler = DriveFSEventHandler(
            self, ignore_patterns=ignore_patterns)
        self._root_event_handler = DriveFSRootEventHandler(
            self, os.path.basename(self.client.base_folder),
            ignore_patterns=ignore_patterns)
        self._observer = Observer()
        self._observer.schedule(self._event_handler, self.client.base_folder, 
                                recursive=True)
        self._observer.start()
        self._root_observer = Observer()
        self._root_observer.schedule(self._root_event_handler, 
                                     os.path.dirname(self.client.base_folder))
        self._root_observer.start()

    def _stop_watchdog(self):
        if self._observer is not None:
            log.info('Stopping FS Observer thread')
            try:
                self._observer.stop()
            except StandardError as e:
                log.warning('Cannot stop FS observer : %r', e)

            # Wait for all observers to stop
            try:
                self._observer.join()
            except StandardError as e:
                log.warning('Cannot join FS observer : %r', e)

            # Delete all observers
            self._observer = None

        if self._root_observer is not None:
            log.info('Stopping FS root Observer thread')
            try:
                self._root_observer.stop()
            except StandardError as e:
                log.warning('Cannot stop FS root observer : %r', e)

            # Wait for all observers to stop
            try:
                self._root_observer.join()
            except StandardError as e:
                log.warning('Cannot join FS root observer : %r', e)

            # Delete all observers
            self._root_observer = None

    def _handle_watchdog_delete(self, doc_pair):
        doc_pair.update_state('deleted', doc_pair.remote_state)
        if doc_pair.remote_state == 'unknown':
            self._dao.remove_state(doc_pair)
        else:
            self._dao.delete_local_state(doc_pair)

    def _handle_watchdog_event_on_known_pair(self, doc_pair, evt, rel_path):
        log.trace("watchdog event %r on known pair: %r", evt, doc_pair)
        if evt.event_type == 'moved':
            # Ignore move to Office tmp file
            dest_filename = os.path.basename(evt.dest_path)
            if dest_filename.startswith(LocalClient.CASE_RENAME_PREFIX) or \
                    os.path.basename(rel_path).startswith(LocalClient.CASE_RENAME_PREFIX):
                log.debug('Ignoring case rename %s to %s', evt.src_path, evt.dest_path)
                return
            if is_office_temp_file(dest_filename):
                log.debug('Ignoring Office tmp file: %r', evt.dest_path)
                return
            src_path = normalize_event_filename(evt.dest_path)
            rel_path = self.client.get_path(src_path)
            # Office weird replacement handling
            if is_office_file(dest_filename):
                pair = self._dao.get_state_from_local(rel_path)
                remote_ref = self.client.get_remote_id(rel_path)
                if pair is not None and pair.remote_ref == remote_ref:
                    local_info = self.client.get_info(rel_path, raise_if_missing=False)
                    if local_info is not None:
                        digest = local_info.get_digest()
                        # Drop event if digest hasn't changed, can be the case
                        # if only file permissions have been updated
                        if not doc_pair.folderish and pair.local_digest == digest:
                            log.trace('Dropping watchdog event [%s] as digest has not changed for %s',
                              evt.event_type, rel_path)
                            # If pair are the same dont drop it. It can happen
                            # in case of server rename on a document.
                            if doc_pair.id != pair.id:
                                self._dao.remove_state(doc_pair)
                            return
                        pair.local_digest = digest
                        pair.local_state = 'modified'
                        self._dao.update_local_state(pair, local_info)
                        self._dao.remove_state(doc_pair)
                        log.debug("Office substitution file: remove pair(%r) mark(%r) as modified", doc_pair, pair)
                        return
            local_info = self.client.get_info(rel_path, raise_if_missing=False)
            if local_info is not None:
                if is_text_edit_tmp_file(local_info.name):
                    log.debug('Ignoring move to TextEdit tmp file %r for %r',
                              local_info.name, doc_pair)
                    return
                old_local_path = None
                rel_parent_path = self.client.get_path(os.path.dirname(src_path))
                if rel_parent_path == '':
                    rel_parent_path = '/'
                # Ignore inner movement
                remote_parent_ref = self.client.get_remote_id(rel_parent_path)
                if (doc_pair.remote_name == local_info.name and
                        doc_pair.remote_parent_ref == remote_parent_ref):
                        # The pair was moved but it has been canceled manually
                        log.debug("The pair was moved but it has been canceled manually,"
                                  " setting state to 'synchronized': %r", doc_pair)
                        doc_pair.local_state = 'synchronized'
                elif not (local_info.name == doc_pair.local_name and
                        doc_pair.remote_parent_ref == remote_parent_ref):
                    log.debug("Detect move for %r (%r)",
                              local_info.name, doc_pair)
                    if doc_pair.local_state != 'created':
                        doc_pair.local_state = 'moved'
                        old_local_path = doc_pair.local_path
                        self._dao.update_local_state(doc_pair, local_info,
                                                     versionned=True)
                self._dao.update_local_state(doc_pair, local_info,
                                             versionned=False)
                if self._windows and old_local_path is not None and self._windows_folder_scan_delay > 0:
                    self._win_lock.acquire()
                    try:
                        if old_local_path in self._folder_scan_events:
                            log.debug('Update queue of folders to scan: move from %r to %r', old_local_path, rel_path)
                            del self._folder_scan_events[old_local_path]
                            self._folder_scan_events[rel_path] = (
                                mktime(local_info.last_modification_time.timetuple()), doc_pair)
                    finally:
                        self._win_lock.release()
            return
        acquired_pair = None
        try:
            acquired_pair = self._dao.acquire_state(self._thread_id, doc_pair.id)
            if acquired_pair is not None:
                self._handle_watchdog_event_on_known_acquired_pair(acquired_pair, evt, rel_path)
            else:
                log.trace("Don't update as in process %r", doc_pair)
        except sqlite3.OperationalError:
            log.trace("Don't update as cannot acquire %r", doc_pair)
        finally:
            self._dao.release_state(self._thread_id)
            if acquired_pair is not None:
                refreshed_pair = self._dao.get_state_from_id(acquired_pair.id)
                if refreshed_pair is not None:
                    log.trace("Re-queuing acquired, released and refreshed state %r", refreshed_pair)
                    self._dao._queue_pair_state(refreshed_pair.id,
                                                refreshed_pair.folderish,
                                                refreshed_pair.pair_state,
                                                pair=refreshed_pair)

    def _handle_watchdog_event_on_known_acquired_pair(self, doc_pair, evt, rel_path):
        if evt.event_type == 'deleted':
            # Delay on Windows the delete event
            if self._windows:
                self._win_lock.acquire()
                log.debug('Add pair to delete events: %r', doc_pair)
                try:
                    self._delete_events[doc_pair.remote_ref] = (current_milli_time(), doc_pair)
                finally:
                    self._win_lock.release()
            else:
                # In case of case sensitive can be an issue
                if self.client.exists(doc_pair.local_path):
                    remote_id = self.client.get_remote_id(doc_pair.local_path)
                    if remote_id == doc_pair.remote_ref or remote_id is None:
                        # This happens on update don't do anything
                        return
                self._handle_watchdog_delete(doc_pair)
            return
        local_info = self.client.get_info(rel_path, raise_if_missing=False)
        if evt.event_type == 'created':
            # NXDRIVE-471 case maybe
            remote_ref = self.client.get_remote_id(rel_path)
            if remote_ref is None:
                log.debug("Created event on a known pair with no remote_ref,"
                          " this should only happen in case of a quick move and copy-paste: %r", doc_pair)
                if local_info is None or local_info.get_digest() == doc_pair.local_digest:
                    return
                else:
                    log.debug("Created event on a known pair with no remote_ref but with different digest: %r" , doc_pair)
            else:
                # NXDRIVE-509
                log.debug("Created event on a known pair with a remote_ref: %r", doc_pair)
        if local_info is not None:
            # Unchanged folder
            if doc_pair.folderish:
                log.debug('Unchanged folder %s (watchdog event [%s]), only update last_local_updated',
                          rel_path, evt.event_type)
                self._dao.update_local_modification_time(doc_pair, local_info)
                return
            if doc_pair.local_state == 'synchronized':
                digest = local_info.get_digest()
                # Unchanged digest, can be the case if only the last modification time or file permissions
                # have been updated
                if doc_pair.local_digest == digest:
                    log.debug('Digest has not changed for %s (watchdog event [%s]), only update last_local_updated',
                              rel_path, evt.event_type)
                    if local_info.remote_ref is None:
                        self.client.set_remote_id(rel_path, doc_pair.remote_ref)
                    self._dao.update_local_modification_time(doc_pair, local_info)
                    return
                doc_pair.local_digest = digest
                doc_pair.local_state = 'modified'
            if evt.event_type == 'modified' and doc_pair.remote_ref is not None and doc_pair.remote_ref != local_info.remote_ref:
                original_pair = self._dao.get_normal_state_from_remote(local_info.remote_ref)
                original_info = None
                if original_pair is not None:
                    original_info = self.client.get_info(original_pair.local_path, raise_if_missing=False)
                if AbstractOSIntegration.is_mac() and original_info is not None and original_info.remote_ref == local_info.remote_ref:
                    log.debug("MacOSX has postponed overwriting of xattr, need to reset remote_ref for %r", doc_pair)
                    # We are in a copy/paste situation with OS overriding the xattribute
                    self.client.set_remote_id(doc_pair.local_path, doc_pair.remote_ref)
                # This happens on overwrite through Windows Explorer
                if original_info is None:
                    self.client.set_remote_id(doc_pair.local_path, doc_pair.remote_ref)
            self._dao.update_local_state(doc_pair, local_info)

    def handle_watchdog_root_event(self, evt):
        if evt.event_type == 'moved':
            log.warning('Root has been moved to %r', evt.dest_path)
            self.rootMoved.emit(evt.dest_path)
        elif evt.event_type == 'deleted':
            log.warning('Root has been deleted')
            self.rootDeleted.emit()

    def handle_watchdog_event(self, evt):
        # Ignore *.nxpart
        if evt.src_path.endswith(DOWNLOAD_TMP_FILE_SUFFIX):
            return
        try:
            if evt.dest_path.endswith(DOWNLOAD_TMP_FILE_SUFFIX):
                return
        except AttributeError:
            pass

        self._metrics['last_event'] = current_milli_time()
        self._action = Action("Handle watchdog event")
        if evt.event_type == 'moved':
            log.debug("Handling watchdog event [%s] on %s to %s", evt.event_type, evt.src_path, evt.dest_path)
            # Ignore normalization of the filename on the file system
            # See https://jira.nuxeo.com/browse/NXDRIVE-188
            if evt.dest_path == normalize_event_filename(evt.src_path, action=False) or evt.dest_path == evt.src_path.strip():
                log.debug('Ignoring move from %r to normalized name: %r', evt.src_path, evt.dest_path)
                return
        else:
            log.debug("Handling watchdog event [%s] on %r", evt.event_type, evt.src_path)
        try:
            src_path = normalize_event_filename(evt.src_path)
            rel_path = self.client.get_path(src_path)
            if not rel_path or rel_path == '/':
                self.handle_watchdog_root_event(evt)
                return

            file_name = os.path.basename(src_path)
            parent_path = os.path.dirname(src_path)
            parent_rel_path = self.client.get_path(parent_path)
            # Don't care about ignored file, unless it is moved
            if evt.event_type != 'moved' and self.client.is_ignored(parent_rel_path, file_name):
                return
            if self.client.is_temp_file(file_name):
                return

            doc_pair = self._dao.get_state_from_local(rel_path)
            if doc_pair is not None:
                if doc_pair.pair_state == 'unsynchronized':
                    log.debug("Ignoring %s as marked unsynchronized", doc_pair.local_path)
                    if (evt.event_type == 'deleted'
                        or evt.event_type == 'moved' and not is_office_temp_file(os.path.basename(evt.dest_path))):
                        log.debug('Removing pair state for deleted or moved event: %r', doc_pair)
                        self._dao.remove_state(doc_pair)
                    return
                self._handle_watchdog_event_on_known_pair(doc_pair, evt, rel_path)
                return
            if evt.event_type == 'deleted':
                log.debug('Unknown pair deleted: %s', rel_path)
                return
            if evt.event_type == 'moved':
                dest_filename = os.path.basename(evt.dest_path)
                if self.client.is_ignored(parent_rel_path, dest_filename):
                    return
                src_path = normalize_event_filename(evt.dest_path)
                rel_path = self.client.get_path(src_path)
                local_info = self.client.get_info(rel_path, raise_if_missing=False)
                doc_pair = self._dao.get_state_from_local(rel_path)
                # If the file exists but not the pair
                if local_info is not None and doc_pair is None:
                    # Check if it is a pair that we loose track of
                    if local_info.remote_ref is not None:
                        doc_pair = self._dao.get_normal_state_from_remote(local_info.remote_ref)
                        if doc_pair is not None and not self.client.exists(doc_pair.local_path):
                            log.debug("Pair re-moved detected for %r", doc_pair)
                            # Can be a move inside a folder that has also moved
                            self._handle_watchdog_event_on_known_pair(doc_pair, evt, rel_path)
                            return
                    rel_parent_path = self.client.get_path(os.path.dirname(src_path))
                    if rel_parent_path == '':
                        rel_parent_path = '/'
                    self._dao.insert_local_state(local_info, rel_parent_path)
                    # An event can be missed inside a new created folder as
                    # watchdog will put listener after it
                    if local_info.folderish:
                        self.scan_pair(rel_path)
                        doc_pair = self._dao.get_state_from_local(rel_path)
                        self._schedule_win_folder_scan(doc_pair)
                return
            # if the pair is modified and not known consider as created
            if evt.event_type == 'created' or evt.event_type == 'modified':
                # If doc_pair is not None mean
                # the creation has been catched by scan
                # As Windows send a delete / create event for reparent
                local_info = self.client.get_info(rel_path, raise_if_missing=False)
                if local_info is None:
                    log.trace("Event on a disappeared file: %r %s %s", evt, rel_path, file_name)
                    return
                # This might be a move but Windows don't emit this event...
                if local_info.remote_ref is not None:
                    moved = False
                    from_pair = self._dao.get_normal_state_from_remote(local_info.remote_ref)
                    if from_pair is not None:
                        if from_pair.processor > 0 or from_pair.local_path == rel_path:
                            # First condition is in process
                            # Second condition is a race condition
                            log.trace("Ignore creation or modification as the coming pair is being processed: %r",
                                      rel_path)
                            return
                        # If it is not at the origin anymore, magic teleportation, only on Windows ?
                        if not self.client.exists(from_pair.local_path):
                            log.debug('Move from %r to %r', from_pair.local_path, rel_path)
                            from_pair.local_state = 'moved'
                            self._dao.update_local_state(from_pair, self.client.get_info(rel_path))
                            moved = True
                        else:
                            # possible move-then-copy case, NXDRIVE-471
                            doc_pair_full_path = self.client.abspath(rel_path)
                            doc_pair_creation_time = self.get_creation_time(doc_pair_full_path)
                            from_pair_full_path = self.client.abspath(from_pair.local_path)
                            from_pair_creation_time = self.get_creation_time(from_pair_full_path)
                            log.trace('doc_pair_full_path=%s, doc_pair_creation_time=%s, from_pair_full_path=%s, version=%d', doc_pair_full_path, doc_pair_creation_time, from_pair_full_path, from_pair.version)
                            # If file at the original location is newer,
                            #   it is moved to the new location earlier then copied back (what else can it be?)
                            if (not from_pair_creation_time <= doc_pair_creation_time) and evt.event_type == 'created':
                                log.trace("Found moved file: from_pair: %f doc_pair:%f for %s", from_pair_creation_time, doc_pair_creation_time, doc_pair_full_path)
                                log.trace("Creation time are: from: %f | new: %f : boolean: %d", from_pair_creation_time, doc_pair_creation_time, from_pair_creation_time >= doc_pair_creation_time)
                                from_pair.local_state = 'moved'
                                self._dao.update_local_state(from_pair, self.client.get_info(rel_path))
                                self._dao.insert_local_state(self.client.get_info(from_pair.local_path), os.path.dirname(from_pair.local_path))
                                self.client.remove_remote_id(from_pair.local_path)
                                moved = True
                    if self._windows:
                        self._win_lock.acquire()
                        try:
                            if local_info.remote_ref in self._delete_events:
                                log.debug('Found creation in delete event, handle move instead')
                                # Should be cleaned
                                if not moved:
                                    doc_pair = self._delete_events[local_info.remote_ref][1]
                                    doc_pair.local_state = 'moved'
                                    self._dao.update_local_state(doc_pair, self.client.get_info(rel_path))
                                del self._delete_events[local_info.remote_ref]
                                return
                        finally:
                            self._win_lock.release()
                    if from_pair is not None:
                        if moved:
                            # Stop the process here
                            return
                        log.debug('Copy paste from %r to %r', from_pair.local_path, rel_path)
                        self.client.remove_remote_id(rel_path)
                self._dao.insert_local_state(local_info, parent_rel_path)
                # An event can be missed inside a new created folder as
                # watchdog will put listener after it
                if local_info.folderish:
                    self.scan_pair(rel_path)
                    doc_pair = self._dao.get_state_from_local(rel_path)
                    self._schedule_win_folder_scan(doc_pair)
                return
            log.debug('Unhandled case: %r %s %s', evt, rel_path, file_name)
        except:
            log.exception('Watchdog exception')
        finally:
            self._end_action()

    def _schedule_win_folder_scan(self, doc_pair):
        if not doc_pair:
            return

        # On Windows schedule another recursive scan to make sure I/O is completed,
        # ex: copy/paste, move
        if self._windows and self._win_folder_scan_interval > 0 and self._windows_folder_scan_delay > 0:
            self._win_lock.acquire()
            try:
                log.debug('Add pair to folder scan events: %r', doc_pair)
                local_info = self.client.get_info(doc_pair.local_path, raise_if_missing=False)
                if local_info is not None:
                    self._folder_scan_events[doc_pair.local_path] = (
                        mktime(local_info.last_modification_time.timetuple()), doc_pair)
            finally:
                self._win_lock.release()


class DriveFSEventHandler(PatternMatchingEventHandler):
    def __init__(self, watcher, **kwargs):
        super(DriveFSEventHandler, self).__init__(**kwargs)
        self.counter = 0
        self.watcher = watcher

    def __repr__(self):
        return ('<{name}'
                ' patterns={cls.patterns!r},'
                ' ignore_patterns={cls.ignore_patterns!r},'
                ' ignore_directories={cls.ignore_directories!s},'
                ' case_sensitive={cls.case_sensitive!s}'
                '>'
                ).format(name=type(self).__name__, cls=self)

    def on_any_event(self, event):
        self.counter += 1
        log.trace('Queueing watchdog: %r', event)
        self.watcher._watchdog_queue.put(event)


class DriveFSRootEventHandler(PatternMatchingEventHandler):
    def __init__(self, watcher, name, **kwargs):
        super(DriveFSRootEventHandler, self).__init__(**kwargs)
        self.name = name
        self.counter = 0
        self.watcher = watcher

    def __repr__(self):
        return ('<{name}'
                ' patterns={cls.patterns!r},'
                ' ignore_patterns={cls.ignore_patterns!r},'
                ' ignore_directories={cls.ignore_directories!s},'
                ' case_sensitive={cls.case_sensitive!s}'
                '>'
                ).format(name=type(self).__name__, cls=self)

    def on_any_event(self, event):
        if os.path.basename(event.src_path) != self.name:
            return
        self.counter += 1
        self.watcher.handle_watchdog_root_event(event)


def normalize_event_filename(filename, action=True):
    """
    Normalize a file name.

    :param unicode filename: The file name to normalize.
    :param bool action: Apply changes on the file system.
    :return unicode: The normalized file name.
    """

    # NXDRIVE-688: Ensure the name is stripped for a file
    stripped = filename.strip()
    if AbstractOSIntegration.is_windows():
        # Windows does not allow files/folders ending with space(s)
        filename = stripped
    elif (action
            and filename != stripped
            and os.path.exists(filename)
            and not os.path.isdir(filename)):
        # We can have folders ending with spaces
        log.debug('Forcing space normalization: %r -> %r', filename, stripped)
        os.rename(filename, stripped)
        filename = stripped

    # NXDRIVE-188: Normalize name on the file system, if needed
    try:
        normalized = unicodedata.normalize('NFC', unicode(filename, 'utf-8'))
    except TypeError:
        normalized = unicodedata.normalize('NFC', unicode(filename))

    if AbstractOSIntegration.is_mac():
        return normalized
    elif AbstractOSIntegration.is_windows() and os.path.exists(filename):
        """
        If `filename` exists, and as Windows is case insensitive,
        the result of Get(Full|Long|Short)PathName() could be unexpected
        because it will return the path of the existant `filename`.

        Check this simplified code session (the file "ABC.txt" exists):

            >>> win32api.GetLongPathName('abc.txt')
            'ABC.txt'
            >>> win32api.GetLongPathName('ABC.TXT')
            'ABC.txt'
            >>> win32api.GetLongPathName('ABC.txt')
            'ABC.txt'

        So, to counter that behavior, we save the actual file name
        and restore it in the full path.
        """
        long_path = win32api.GetLongPathNameW(filename)
        filename = os.path.join(os.path.dirname(long_path),
                                os.path.basename(filename))

    if action and filename != normalized and os.path.exists(filename):
        log.debug('Forcing normalization: %r -> %r', filename, normalized)
        os.rename(filename, normalized)

    return normalized
