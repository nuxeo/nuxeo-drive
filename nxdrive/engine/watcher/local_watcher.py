# coding: utf-8
import os
import re
import sqlite3
import sys
from Queue import Queue
from logging import getLogger
from os.path import basename, dirname, getctime
from threading import Lock
from time import mktime, sleep, time

from PyQt4.QtCore import pyqtSignal, pyqtSlot
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

from ..activity import tooltip
from ..workers import EngineWorker, ThreadInterrupt
from ...client.base_automation_client import DOWNLOAD_TMP_FILE_SUFFIX
from ...client.local_client import LocalClient
from ...options import Options
from ...utils import (current_milli_time, force_decode, is_generated_tmp_file,
                      normalize_event_filename as normalize)

log = getLogger(__name__)

# Windows 2s between resolution of delete event
WIN_MOVE_RESOLUTION_PERIOD = 2000

TEXT_EDIT_TMP_FILE_PATTERN = ur'.*\.rtf\.sb\-(\w)+\-(\w)+$'


def is_text_edit_tmp_file(name):
    return re.match(TEXT_EDIT_TMP_FILE_PATTERN, name)


class LocalWatcher(EngineWorker):
    localScanFinished = pyqtSignal()
    rootMoved = pyqtSignal(str)
    rootDeleted = pyqtSignal()

    # Windows lock
    lock = Lock()

    def __init__(self, engine, dao):
        super(LocalWatcher, self).__init__(engine, dao)
        self._event_handler = None
        # Delay for the scheduled recursive scans of
        # a created / modified / moved folder under Windows
        self._windows_folder_scan_delay = 10000  # 10 seconds
        self._windows_watchdog_event_buffer = 8192
        self._windows = sys.platform == 'win32'
        if self._windows:
            log.debug('Windows detected so delete event will be '
                      'delayed by %dms', WIN_MOVE_RESOLUTION_PERIOD)
        # TODO Review to delete
        self._init()

    def _init(self):
        self.client = self._engine.get_local_client()
        self._metrics = {
            'last_local_scan_time': -1,
            'new_files': 0,
            'update_files': 0,
            'delete_files': 0,
            'last_event': 0,
        }
        self._observer = None
        self._root_observer = None
        self._delete_events = dict()
        self._folder_scan_events = dict()

    def _execute(self):
        try:
            self._init()
            if not self.client.exists('/'):
                self.rootDeleted.emit()
                return

            self.watchdog_queue = Queue()
            self._setup_watchdog()
            self._scan()

            if self._windows:
                # Check dequeue and folder scan only every 100 loops (1s)
                self._win_delete_interval = self._win_folder_scan_interval = \
                    int(round(time() * 1000))

            while 'working':
                self._interact()
                sleep(0.01)

                while not self.watchdog_queue.empty():
                    self.handle_watchdog_event(self.watchdog_queue.get())

                    if self._windows:
                        self._win_delete_check()
                        self._win_folder_scan_check()

                if self._windows:
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
        elapsed = int(round(time() * 1000)) - WIN_MOVE_RESOLUTION_PERIOD
        if self._win_delete_interval >= elapsed:
            return

        with self.lock:
            self._win_dequeue_delete()
        self._win_delete_interval = int(round(time() * 1000))

    @tooltip('Dequeue delete')
    def _win_dequeue_delete(self):
        try:
            delete_events = self._delete_events
            for evt in delete_events.values():
                evt_time, evt_pair = evt
                if (current_milli_time() - evt_time
                        < WIN_MOVE_RESOLUTION_PERIOD):
                    log.debug('Win: ignoring delete event as waiting for '
                              'move resolution period expiration: %r', evt)
                    continue
                if not self.client.exists(evt_pair.local_path):
                    log.debug('Win: handling watchdog delete '
                              'for event: %r', evt)
                    self._handle_watchdog_delete(evt_pair)
                else:
                    remote_id = self.client.get_remote_id(evt_pair.local_path)
                    if remote_id == evt_pair.remote_ref or remote_id is None:
                        log.debug('Win: ignoring delete event as '
                                  'file still exists: %r', evt)
                    else:
                        log.debug('Win: handling watchdog delete '
                                  'for event: %r', evt)
                        self._handle_watchdog_delete(evt_pair)
                log.debug('Win: dequeuing delete event: %r', evt)
                del self._delete_events[evt_pair.remote_ref]
        except ThreadInterrupt:
            raise
        except:
            log.exception('Win: dequeuing deletion error')

    def win_folder_scan_empty(self):
        return not self._folder_scan_events

    def get_win_folder_scan_size(self):
        return len(self._folder_scan_events)

    def _win_folder_scan_check(self):
        elapsed = int(round(time() * 1000)) - self._windows_folder_scan_delay
        if self._win_folder_scan_interval >= elapsed:
            return

        with self.lock:
            self._win_dequeue_folder_scan()
        self._win_folder_scan_interval = int(round(time() * 1000))

    @tooltip('Dequeue folder scan')
    def _win_dequeue_folder_scan(self):
        try:
            folder_scan_events = self._folder_scan_events.values()
            for evt in folder_scan_events:
                evt_time, evt_pair = evt
                local_path = evt_pair.local_path
                delay = current_milli_time() - evt_time

                if delay < self._windows_folder_scan_delay:
                    log.debug('Win: ignoring folder to scan as waiting for '
                              'folder scan delay expiration: %r', local_path)
                    continue
                if not self.client.exists(local_path):
                    if local_path in self._folder_scan_events:
                        log.debug('Win: dequeuing folder scan event as '
                                  'folder doesn\'t exist: %r', local_path)
                        del self._folder_scan_events[local_path]
                    continue
                local_info = self.client.get_info(local_path,
                                                  raise_if_missing=False)
                if local_info is None:
                    log.trace('Win: dequeuing folder scan event as '
                              'folder doesn\'t exist: %r', local_path)
                    del self._folder_scan_events[local_path]
                    continue
                log.debug('Win: handling folder to scan: %r', local_path)
                self.scan_pair(local_path)
                local_info = self.client.get_info(local_path,
                                                  raise_if_missing=False)

                mtime = mktime(local_info.last_modification_time.timetuple())
                if local_info is not None and mtime > evt_time:
                    # Re-schedule scan as the folder
                    # has been modified since last check
                    self._folder_scan_events[local_path] = (mtime, evt_pair)
                else:
                    log.debug('Win: dequeuing folder scan event: %r', evt)
                    del self._folder_scan_events[local_path]
        except ThreadInterrupt:
            raise
        except:
            log.exception('Win: dequeuing folder scan error')

    @tooltip('Full local scan')
    def _scan(self):
        log.debug('Full scan started')
        start_ms = current_milli_time()
        to_pause = not self._engine.get_queue_manager().is_paused()
        if to_pause:
            self._suspend_queue()
        self._delete_files = dict()
        self._protected_files = dict()

        info = self.client.get_info('/')
        self._scan_recursive(info)
        self._scan_handle_deleted_files()
        self._metrics['last_local_scan_time'] = current_milli_time() - start_ms
        log.debug('Full scan finished in %dms',
                  self._metrics['last_local_scan_time'])
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
        if self._event_handler:
            metrics['fs_events'] = self._event_handler.counter
        metrics.update(self._metrics)
        return metrics

    def _suspend_queue(self):
        queue = self._engine.get_queue_manager()
        queue.suspend()
        for processor in queue.get_processors_on('/', exact_match=False):
            processor.stop()

    @pyqtSlot(str)
    def scan_pair(self, local_path):
        to_pause = not self._engine.get_queue_manager().is_paused()
        if to_pause:
            self._suspend_queue()

        info = self.client.get_info(local_path)
        self._scan_recursive(info, recursive=False)
        self._scan_handle_deleted_files()

        if to_pause:
            self._engine.get_queue_manager().resume()

    def empty_events(self):
        return self.watchdog_queue.empty() and (
            not sys.platform == 'win32' or self.win_queue_empty()
            and self.win_folder_scan_empty())

    def get_creation_time(self, child_full_path):
        if self._windows:
            return getctime(child_full_path)

        stat = os.stat(child_full_path)
        # Try inode number as on HFS seems to be increasing
        if sys.platform == 'darwin' and hasattr(stat, 'st_ino'):
            return stat.st_ino
        if hasattr(stat, 'st_birthtime'):
            return stat.st_birthtime
        return 0

    def _scan_recursive(self, info, recursive=True):
        if recursive:
            # Don't interact if only one level
            self._interact()

        dao, client = self._dao, self.client
        # Load all children from DB
        log.trace('Fetching DB local children of %r', info.path)
        db_children = dao.get_local_children(info.path)

        # Create a list of all children by their name
        to_scan = []
        to_scan_new = []
        children = {child.local_name: child for child in db_children}

        # Load all children from FS
        # detect recently deleted children
        log.trace('Fetching FS children info of %r', info.path)
        try:
            fs_children_info = client.get_children_info(info.path)
        except OSError:
            # The folder has been deleted in the mean time
            return

        # Get remote children to be able to check if a local child found
        # during the scan is really a new item or if it is just the result
        # of a remote creation performed on the file system but not yet
        # updated in the DB as for its local information.
        remote_children = set()
        parent_remote_id = client.get_remote_id(info.path)
        if parent_remote_id is not None:
            pairs_ = dao.get_new_remote_children(parent_remote_id)
            remote_children = {pair.remote_name for pair in pairs_}

        # recursively update children
        for child_info in fs_children_info:
            child_name = basename(child_info.path)
            child_type = 'folder' if child_info.folderish else 'file'
            if child_name not in children:
                try:
                    remote_id = client.get_remote_id(child_info.path)
                    if remote_id is None:
                        # Avoid IntegrityError: do not insert a new pair state
                        # if item is already referenced in the DB
                        if child_name in remote_children:
                            log.debug('Skip potential new %s as it is the '
                                      'result of a remote creation: %r',
                                      child_type, child_info.path)
                            continue
                        log.debug('Found new %s %r',
                                  child_type, child_info.path)
                        self._metrics['new_files'] += 1
                        dao.insert_local_state(child_info, info.path)
                    else:
                        log.debug('Found potential moved file %r[%s]',
                                  child_info.path, remote_id)
                        doc_pair = dao.get_normal_state_from_remote(remote_id)

                        if doc_pair and client.exists(doc_pair.local_path):
                            if (not client.is_case_sensitive()
                                    and doc_pair.local_path.lower()
                                    == child_info.path.lower()):
                                log.debug('Case renaming on a case '
                                          'insensitive filesystem, update '
                                          'info and ignore: %r', doc_pair)
                                if doc_pair.local_name in children:
                                    del children[doc_pair.local_name]
                                doc_pair.local_state = 'moved'
                                dao.update_local_state(doc_pair, child_info)
                                continue
                            # possible move-then-copy case, NXDRIVE-471
                            child_full_path = client.abspath(child_info.path)
                            child_creation_time = self.get_creation_time(
                                child_full_path)
                            doc_full_path = client.abspath(
                                doc_pair.local_path)
                            doc_creation_time = self.get_creation_time(
                                doc_full_path)
                            log.trace('child_cre_time=%f, doc_cre_time=%f',
                                child_creation_time, doc_creation_time)
                        if not doc_pair:
                            log.debug('Cannot find reference for %r in '
                                      'database, put it in locally_created '
                                      'state', child_info.path)
                            self._metrics['new_files'] += 1
                            dao.insert_local_state(child_info, info.path)
                            self._protected_files[remote_id] = True
                        elif doc_pair.processor > 0:
                            log.debug('Skip pair as it is being processed: %r',
                                      doc_pair)
                            continue
                        elif doc_pair.local_path == child_info.path:
                            log.debug('Skip pair as it is not a real move: %r',
                                      doc_pair)
                            continue
                        elif (not client.exists(doc_pair.local_path)
                              or (client.exists(doc_pair.local_path) and
                                  child_creation_time < doc_creation_time)):
                            # If file exists at old location, and the file
                            # at the original location is newer, it is
                            # moved to the new location earlier then copied
                            # back
                            log.debug('Found moved file')
                            doc_pair.local_state = 'moved'
                            dao.update_local_state(doc_pair, child_info)
                            self._protected_files[doc_pair.remote_ref] = True
                            if (client.exists(doc_pair.local_path)
                                    and child_creation_time
                                    < doc_creation_time):
                                # Need to put back the new created - need to
                                # check maybe if already there
                                log.trace('Found a moved file that has been '
                                          'copy/paste back: %r',
                                          doc_pair.local_path)
                                client.remove_remote_id(doc_pair.local_path)
                                dao.insert_local_state(
                                    client.get_info(doc_pair.local_path),
                                    os.path.dirname(doc_pair.local_path))
                        else:
                            # File still exists - must check the remote_id
                            old_remote_id = client.get_remote_id(
                                doc_pair.local_path)
                            if old_remote_id == remote_id:
                                # Local copy paste
                                log.debug('Found a copy-paste of document')
                                client.remove_remote_id(child_info.path)
                                dao.insert_local_state(child_info, info.path)
                            else:
                                # Moved and renamed
                                log.debug('Moved and renamed: %r', doc_pair)
                                old_pair = dao.get_normal_state_from_remote(
                                    old_remote_id)
                                if old_pair is not None:
                                    old_pair.local_state = 'moved'
                                    # Check digest also
                                    digest = child_info.get_digest()
                                    if old_pair.local_digest != digest:
                                        old_pair.local_digest = digest
                                    dao.update_local_state(
                                        old_pair,
                                        client.get_info(doc_pair.local_path))
                                    self._protected_files[
                                        old_pair.remote_ref] = True
                                doc_pair.local_state = 'moved'
                                # Check digest also
                                digest = child_info.get_digest()
                                if doc_pair.local_digest != digest:
                                    doc_pair.local_digest = digest
                                dao.update_local_state(doc_pair, child_info)
                                self._protected_files[
                                    doc_pair.remote_ref] = True
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
                    last_mtime = unicode(
                        child_info.last_modification_time.strftime(
                            '%Y-%m-%d %H:%M:%S'))
                    if (child_pair.processor == 0
                            and child_pair.last_local_updated is not None
                            and last_mtime
                            != child_pair.last_local_updated.split('.')[0]):
                        log.trace('Update file %r', child_info.path)
                        remote_ref = client.get_remote_id(
                            child_pair.local_path)
                        if (remote_ref is not None
                                and child_pair.remote_ref is None):
                            log.debug('Possible race condition between '
                                      'remote and local scan, let\'s '
                                      'refresh pair: %r', child_pair)
                            child_pair = dao.get_state_from_id(child_pair.id)
                            if child_pair.remote_ref is None:
                                log.debug('Pair not yet handled by remote '
                                          'scan (remote_ref is None) but '
                                          'existing remote_id xattr, let\'s '
                                          'set it to None: %r', child_pair)
                                client.remove_remote_id(child_pair.local_path)
                                remote_ref = None
                        if remote_ref != child_pair.remote_ref:
                            # Load correct doc_pair | Put the others one back
                            # to children
                            log.warning('Detected file substitution: %r '
                                        '(%s/%s)', child_pair.local_path,
                                        remote_ref, child_pair.remote_ref)
                            if remote_ref is None:
                                if not child_info.folderish:
                                    # Alternative stream or xattr can have
                                    # been removed by external software or user
                                    digest = child_info.get_digest()
                                    if child_pair.local_digest != digest:
                                        child_pair.local_digest = digest
                                        child_pair.local_state = 'modified'

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
                                client.set_remote_id(child_pair.local_path,
                                                     child_pair.remote_ref)
                                dao.update_local_state(child_pair, child_info)
                                if child_info.folderish:
                                    to_scan.append(child_info)
                                continue

                            old_pair = dao.get_normal_state_from_remote(
                                remote_ref)
                            if old_pair is None:
                                dao.insert_local_state(child_info, info.path)
                            else:
                                old_pair.local_state = 'moved'
                                # Check digest also
                                digest = child_info.get_digest()
                                if old_pair.local_digest != digest:
                                    old_pair.local_digest = digest
                                dao.update_local_state(old_pair, child_info)
                                self._protected_files[
                                    old_pair.remote_ref] = True
                            self._delete_files[
                                child_pair.remote_ref] = child_pair
                        if not child_info.folderish:
                            digest = child_info.get_digest()
                            if child_pair.local_digest != digest:
                                child_pair.local_digest = digest
                                child_pair.local_state = 'modified'
                        self._metrics['update_files'] += 1
                        dao.update_local_state(child_pair, child_info)
                    if child_info.folderish:
                        to_scan.append(child_info)
                except Exception as e:
                    log.exception('Error with pair %r, increasing error',
                                  child_pair)
                    self.increase_error(child_pair, 'SCAN RECURSIVE',
                                        exception=e)
                    continue

        for deleted in children.values():
            if (deleted.pair_state == 'remotely_created'
                    or deleted.remote_state == 'created'):
                continue
            log.debug('Found deleted file %r', deleted.local_path)
            # May need to count the children to be ok
            self._metrics['delete_files'] += 1
            if deleted.remote_ref is None:
                dao.remove_state(deleted)
            else:
                self._delete_files[deleted.remote_ref] = deleted

        for child_info in to_scan_new:
            self._scan_recursive(child_info)

        if not recursive:
            return

        for child_info in to_scan:
            self._scan_recursive(child_info)

    @tooltip('Setup watchdog')
    def _setup_watchdog(self):
        """
        Monkey-patch Watchdog to:
            - Set the Windows hack delay to 0 in WindowsApiEmitter,
              otherwise we might miss some events
            - Increase the ReadDirectoryChangesW buffer size for Windows
        """
        base = self.client.base_folder

        if self._windows:
            try:
                import watchdog.observers as ob
                ob.read_directory_changes.WATCHDOG_TRAVERSE_MOVED_DIR_DELAY = 0
                ob.winapi.BUFFER_SIZE = self._windows_watchdog_event_buffer
            except ImportError:
                log.exception('Cannot import read_directory_changes')
        log.debug('Watching FS modification on : %r', base)

        # Filter out all ignored suffixes. It will handle custom ones too.
        ignore_patterns = list('*' + suffix
                               for suffix in Options.ignored_suffixes)

        self._event_handler = DriveFSEventHandler(
            self, ignore_patterns=ignore_patterns)
        self._root_event_handler = DriveFSRootEventHandler(
            self, basename(base), ignore_patterns=ignore_patterns)
        self._observer = Observer()
        self._observer.schedule(self._event_handler, base, recursive=True)
        self._observer.start()
        self._root_observer = Observer()
        self._root_observer.schedule(self._root_event_handler, dirname(base))
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
        log.trace('Watchdog event %r on known pair %r', evt, doc_pair)
        dao, client = self._dao, self.client

        if evt.event_type == 'moved':
            # Ignore move to Office tmp file
            dest_filename = basename(evt.dest_path)
            prefix = LocalClient.CASE_RENAME_PREFIX

            if (dest_filename.startswith(prefix)
                    or basename(rel_path).startswith(prefix)):
                log.debug('Ignoring case rename %r to %r',
                          evt.src_path, evt.dest_path)
                return

            ignore, _ = is_generated_tmp_file(dest_filename)
            if ignore:
                log.debug('Ignoring generated temporary file: %r',
                          evt.dest_path)
                return

            src_path = normalize(evt.dest_path)
            rel_path = client.get_path(src_path)

            pair = dao.get_state_from_local(rel_path)
            remote_ref = client.get_remote_id(rel_path)
            if pair is not None and pair.remote_ref == remote_ref:
                local_info = client.get_info(rel_path,
                                             raise_if_missing=False)
                if local_info:
                    digest = local_info.get_digest()
                    # Drop event if digest hasn't changed, can be the case
                    # if only file permissions have been updated
                    if not doc_pair.folderish and pair.local_digest == digest:
                        log.trace('Dropping watchdog event [%s] as '
                                  'digest has not changed for %r',
                                  evt.event_type, rel_path)
                        # If pair are the same don't drop it.  It can happen
                        # in case of server rename on a document.
                        if doc_pair.id != pair.id:
                            dao.remove_state(doc_pair)
                        return

                    pair.local_digest = digest
                    pair.local_state = 'modified'
                    dao.update_local_state(pair, local_info)
                    dao.remove_state(doc_pair)
                    log.debug('Substitution file: remove pair(%r) mark(%r) '
                              'as modified', doc_pair, pair)
                    return

            local_info = client.get_info(rel_path, raise_if_missing=False)
            if not local_info:
                return

            if is_text_edit_tmp_file(local_info.name):
                log.debug('Ignoring move to TextEdit tmp file %r for %r',
                          local_info.name, doc_pair)
                return

            old_local_path = None
            rel_parent_path = client.get_path(dirname(src_path)) or '/'

            # Ignore inner movement
            remote_parent_ref = client.get_remote_id(rel_parent_path)
            parent_path = dirname(doc_pair.local_path)
            if (doc_pair.remote_name == local_info.name
                    and doc_pair.remote_parent_ref == remote_parent_ref
                    and rel_parent_path == parent_path):
                log.debug('The pair was moved but it has been canceled '
                          'manually, setting state to synchronized: %r',
                          doc_pair)
                doc_pair.local_state = 'synchronized'
            else:
                log.debug('Detect move for %r (%r)', local_info.name, doc_pair)
                if doc_pair.local_state != 'created':
                    doc_pair.local_state = 'moved'
                    old_local_path = doc_pair.local_path
                    dao.update_local_state(doc_pair, local_info)

            dao.update_local_state(doc_pair, local_info, versioned=False)

            if (self._windows
                    and old_local_path is not None
                    and self._windows_folder_scan_delay > 0):
                with self.lock:
                    if old_local_path in self._folder_scan_events:
                        log.debug('Update folders to scan queue: move '
                                  'from %r to %r', old_local_path, rel_path)
                        del self._folder_scan_events[old_local_path]
                        t = mktime(
                            local_info.last_modification_time.timetuple())
                        self._folder_scan_events[rel_path] = t, doc_pair
            return

        acquired_pair = None
        try:
            acquired_pair = dao.acquire_state(self._thread_id, doc_pair.id)
            if acquired_pair is not None:
                self._handle_watchdog_event_on_known_acquired_pair(
                    acquired_pair, evt, rel_path)
            else:
                log.trace('Don\'t update as in process %r', doc_pair)
        except sqlite3.OperationalError:
            log.trace('Don\'t update as cannot acquire %r', doc_pair)
        finally:
            dao.release_state(self._thread_id)
            if acquired_pair is not None:
                refreshed_pair = dao.get_state_from_id(acquired_pair.id)
                if refreshed_pair is not None:
                    log.trace('Re-queuing acquired, released and '
                              'refreshed state %r', refreshed_pair)
                    dao._queue_pair_state(refreshed_pair.id,
                                          refreshed_pair.folderish,
                                          refreshed_pair.pair_state,
                                          pair=refreshed_pair)

    def _handle_watchdog_event_on_known_acquired_pair(self, doc_pair, evt,
                                                      rel_path):
        dao, client = self._dao, self.client

        if evt.event_type == 'deleted':
            if self._windows:
                # Delay on Windows the delete event
                log.debug('Add pair to delete events: %r', doc_pair)
                with self.lock:
                    self._delete_events[
                        doc_pair.remote_ref] = current_milli_time(), doc_pair
                return

            # In case of case sensitive can be an issue
            if client.exists(doc_pair.local_path):
                remote_id = client.get_remote_id(doc_pair.local_path)
                if remote_id == doc_pair.remote_ref or remote_id is None:
                    # This happens on update, don't do anything
                    return
            self._handle_watchdog_delete(doc_pair)
            return

        local_info = client.get_info(rel_path, raise_if_missing=False)
        if evt.event_type == 'created':
            # NXDRIVE-471 case maybe
            remote_ref = client.get_remote_id(rel_path)
            if remote_ref is None:
                log.debug('Created event on a known pair with no remote_ref,'
                          ' this should only happen in case of a quick move '
                          'and copy-paste: %r', doc_pair)
                if (not local_info
                        or local_info.get_digest() == doc_pair.local_digest):
                    return
                else:
                    log.debug('Created event on a known pair with no '
                              'remote_ref but with different digest: %r',
                              doc_pair)
            else:
                # NXDRIVE-509
                log.debug('Created event on a known pair with '
                          'a remote_ref: %r', doc_pair)

        if local_info:
            # Unchanged folder
            if doc_pair.folderish:
                # Unchanged folder, only update last_local_updated
                dao.update_local_modification_time(doc_pair, local_info)
                return

            if doc_pair.local_state == 'synchronized':
                digest = local_info.get_digest()
                # Unchanged digest, can be the case if only the last
                # modification time or file permissions have been updated
                if doc_pair.local_digest == digest:
                    log.debug('Digest has not changed for %r (watchdog event '
                              '[%s]), only update last_local_updated',
                              rel_path, evt.event_type)
                    if local_info.remote_ref is None:
                        client.set_remote_id(rel_path, doc_pair.remote_ref)
                    dao.update_local_modification_time(doc_pair, local_info)
                    return

                doc_pair.local_digest = digest
                doc_pair.local_state = 'modified'
            if (evt.event_type == 'modified'
                    and doc_pair.remote_ref is not None
                    and doc_pair.remote_ref != local_info.remote_ref):
                original_pair = dao.get_normal_state_from_remote(
                    local_info.remote_ref)
                original_info = None
                if original_pair:
                    original_info = client.get_info(
                        original_pair.local_path, raise_if_missing=False)
                if (sys.platform == 'darwin'
                        and original_info
                        and original_info.remote_ref == local_info.remote_ref):
                    log.debug('MacOS has postponed overwriting of xattr, '
                              'need to reset remote_ref for %r', doc_pair)
                    # We are in a copy/paste situation with OS overriding
                    # the xattribute
                    client.set_remote_id(doc_pair.local_path,
                                         doc_pair.remote_ref)
                # This happens on overwrite through Windows Explorer
                if not original_info:
                    client.set_remote_id(doc_pair.local_path,
                                         doc_pair.remote_ref)
            dao.update_local_state(doc_pair, local_info)

    def handle_watchdog_root_event(self, evt):
        if evt.event_type == 'moved':
            log.warning('Root has been moved to %r', evt.dest_path)
            self.rootMoved.emit(evt.dest_path)
        elif evt.event_type == 'deleted':
            log.warning('Root has been deleted')
            self.rootDeleted.emit()

    @tooltip('Handle watchdog event')
    def handle_watchdog_event(self, evt):
        dao, client = self._dao, self.client

        # Ignore *.nxpart
        dst_path = getattr(evt, 'dest_path', '')
        if (evt.src_path.endswith(DOWNLOAD_TMP_FILE_SUFFIX)
                or dst_path.endswith(DOWNLOAD_TMP_FILE_SUFFIX)):
            return

        self._metrics['last_event'] = current_milli_time()
        if evt.event_type == 'moved':
            log.debug('Handling watchdog event [%s] on %r to %r',
                      evt.event_type, evt.src_path, dst_path)
            # Ignore normalization of the filename on the file system
            # See https://jira.nuxeo.com/browse/NXDRIVE-188
            filename = normalize(evt.src_path, action=False)

            if force_decode(dst_path) in (
                    filename, force_decode(evt.src_path.strip())):
                log.debug('Ignoring move from %r to normalized %r',
                          evt.src_path, dst_path)
                return
        else:
            log.debug('Handling watchdog event [%s] on %r',
                      evt.event_type, evt.src_path)

        try:
            src_path = normalize(evt.src_path)
            rel_path = client.get_path(src_path)
            if not rel_path or rel_path == '/':
                self.handle_watchdog_root_event(evt)
                return

            file_name = basename(src_path)
            parent_path = dirname(src_path)
            parent_rel_path = client.get_path(parent_path)
            # Don't care about ignored file, unless it is moved
            if (evt.event_type != 'moved'
                    and client.is_ignored(parent_rel_path, file_name)):
                log.debug('Ignoring action on banned file: %r', evt)
                return

            if client.is_temp_file(file_name):
                log.debug('Ignoring temporary file: %r', evt)
                return

            doc_pair = dao.get_state_from_local(rel_path)
            self._engine._manager.osi.send_sync_status(doc_pair, src_path)
            if doc_pair is not None:
                if doc_pair.pair_state == 'unsynchronized':
                    log.debug('Ignoring %r as marked unsynchronized',
                              doc_pair.local_path)

                    if evt.event_type in ('deleted', 'moved'):
                        path = (evt.dest_path
                                if evt.event_type == 'moved'
                                else evt.src_path)
                        ignore, _ = is_generated_tmp_file(basename(path))
                        if not ignore:
                            log.debug('Removing pair state for %s event: %r',
                                      evt.event_type, doc_pair)
                            dao.remove_state(doc_pair)
                    return
                if (evt.event_type == 'created'
                        and doc_pair.local_state == 'deleted'
                        and doc_pair.pair_state == 'locally_deleted'):
                    log.debug('File has been deleted/created quickly, '
                              'it must be a replace.')
                    doc_pair.local_state = 'modified'
                    doc_pair.remote_state = 'unknown'
                    dao.update_local_state(doc_pair, client.get_info(rel_path))

                self._handle_watchdog_event_on_known_pair(doc_pair, evt,
                                                          rel_path)
                return

            if evt.event_type == 'deleted':
                log.debug('Unknown pair deleted: %r', rel_path)
                return

            if evt.event_type == 'moved':
                dest_filename = basename(evt.dest_path)
                if client.is_ignored(parent_rel_path, dest_filename):
                    log.debug('Ignoring move on banned file: %r', evt)
                    return

                src_path = normalize(evt.dest_path)
                rel_path = client.get_path(src_path)
                local_info = client.get_info(rel_path, raise_if_missing=False)
                doc_pair = dao.get_state_from_local(rel_path)

                # If the file exists but not the pair
                if local_info is not None and doc_pair is None:
                    # Check if it is a pair that we loose track of
                    if local_info.remote_ref is not None:
                        doc_pair = dao.get_normal_state_from_remote(
                            local_info.remote_ref)
                        if (doc_pair is not None
                                and not client.exists(doc_pair.local_path)):
                            log.debug('Pair re-moved detected for %r',
                                      doc_pair)

                            # Can be a move inside a folder that has also moved
                            self._handle_watchdog_event_on_known_pair(
                                doc_pair, evt, rel_path)
                            return

                    rel_parent_path = client.get_path(dirname(src_path))
                    if rel_parent_path == '':
                        rel_parent_path = '/'
                    dao.insert_local_state(local_info, rel_parent_path)

                    # An event can be missed inside a new created folder as
                    # watchdog will put listener after it
                    if local_info.folderish:
                        self.scan_pair(rel_path)
                        if self._windows:
                            doc_pair = dao.get_state_from_local(rel_path)
                            if doc_pair:
                                self._schedule_win_folder_scan(doc_pair)
                return

            # if the pair is modified and not known consider as created
            if evt.event_type not in ('created', 'modified'):
                log.debug('Unhandled case: %r %r %r', evt, rel_path, file_name)
                return

            # If doc_pair is not None mean
            # the creation has been catched by scan
            # As Windows send a delete / create event for reparent
            local_info = client.get_info(rel_path, raise_if_missing=False)
            if local_info is None:
                log.trace('Event on a disappeared file: %r %r %r',
                          evt, rel_path, file_name)
                return

            # This might be a move but Windows don't emit this event...
            if local_info.remote_ref is not None:
                moved = False
                from_pair = dao.get_normal_state_from_remote(
                    local_info.remote_ref)
                if from_pair is not None:
                    if (from_pair.processor > 0
                            or from_pair.local_path == rel_path):
                        # First condition is in process
                        # Second condition is a race condition
                        log.trace('Ignore creation or modification as '
                                  'the coming pair is being processed: %r',
                                  rel_path)
                        return

                    # If it is not at the origin anymore, magic teleportation?
                    # Maybe an event crafted from a
                    # delete/create => move on Windows
                    if not client.exists(from_pair.local_path):
                        # Check if the destination is writable
                        dst_parent = dao.get_state_from_local(
                            dirname(rel_path))
                        if (dst_parent
                                and not dst_parent.remote_can_create_child):
                            log.debug('Moving to a read-only folder: %r -> %r',
                                      from_pair, dst_parent)
                            dao.unsynchronize_state(from_pair, 'READONLY')
                            self._engine.newReadonly.emit(
                                from_pair.local_name, dst_parent.remote_name)
                            return

                        # Check if the source is read-only, in that case we
                        # convert the move to a creation
                        src_parent = dao.get_state_from_local(
                            dirname(from_pair.local_path))
                        if (src_parent
                                and not src_parent.remote_can_create_child):
                            self._engine.newReadonly.emit(
                                from_pair.local_name, dst_parent.remote_name)
                            log.debug('Converting the move to a create '
                                      'for %r -> %r', from_pair, src_path)
                            from_pair.local_path = rel_path
                            from_pair.local_state = 'created'
                            from_pair.remote_state = 'unknown'
                            client.remove_remote_id(rel_path)
                        else:
                            log.debug('Move from %r to %r',
                                      from_pair.local_path, rel_path)
                            from_pair.local_state = 'moved'
                        dao.update_local_state(from_pair,
                                               client.get_info(rel_path))
                        moved = True
                    else:
                        # NXDRIVE-471: Possible move-then-copy case
                        doc_pair_full_path = client.abspath(rel_path)
                        doc_pair_ctime = self.get_creation_time(
                            doc_pair_full_path)
                        from_pair_full_path = client.abspath(
                            from_pair.local_path)
                        from_pair_ctime = self.get_creation_time(
                            from_pair_full_path)
                        log.trace('doc_pair_full_path=%r, doc_pair_ctime=%s, '
                                  'from_pair_full_path=%r, version=%d',
                                  doc_pair_full_path, doc_pair_ctime,
                                  from_pair_full_path, from_pair.version)

                        # If file at the original location is newer, it is
                        # moved to the new location earlier then copied back
                        # (what else can it be?)
                        if (evt.event_type == 'created'
                                and from_pair_ctime > doc_pair_ctime):
                            log.trace('Found moved file %r (times: from=%f, '
                                      'to=%f)', doc_pair_full_path,
                                      from_pair_ctime, doc_pair_ctime)
                            from_pair.local_state = 'moved'
                            dao.update_local_state(
                                from_pair, client.get_info(rel_path))
                            dao.insert_local_state(
                                client.get_info(from_pair.local_path),
                                dirname(from_pair.local_path))
                            client.remove_remote_id(from_pair.local_path)
                            moved = True

                if self._windows:
                    with self.lock:
                        if local_info.remote_ref in self._delete_events:
                            log.debug('Found creation in delete event, '
                                      'handle move instead')
                            # Should be cleaned
                            if not moved:
                                doc_pair = self._delete_events[
                                    local_info.remote_ref][1]
                                doc_pair.local_state = 'moved'
                                dao.update_local_state(
                                    doc_pair, client.get_info(rel_path))
                            del self._delete_events[local_info.remote_ref]
                            return

                if from_pair is not None:
                    if moved:
                        # Stop the process here
                        return
                    log.debug('Copy paste from %r to %r',
                              from_pair.local_path, rel_path)
                    client.remove_remote_id(rel_path)
            dao.insert_local_state(local_info, parent_rel_path)
            # An event can be missed inside a new created folder as
            # watchdog will put listener after it
            if local_info.folderish:
                self.scan_pair(rel_path)
                if self._windows:
                    doc_pair = dao.get_state_from_local(rel_path)
                    if doc_pair:
                        self._schedule_win_folder_scan(doc_pair)
            return
        except ThreadInterrupt:
            raise
        except:
            log.exception('Watchdog exception')

    def _schedule_win_folder_scan(self, doc_pair):
        # On Windows schedule another recursive scan to make sure I/Os finished
        # ex: copy/paste, move
        if (self._win_folder_scan_interval > 0
                and self._windows_folder_scan_delay > 0):
            log.debug('Add pair to folder scan events: %r', doc_pair)
            with self.lock:
                local_info = self.client.get_info(doc_pair.local_path,
                                                  raise_if_missing=False)
                if local_info is not None:
                    self._folder_scan_events[doc_pair.local_path] = (
                        mktime(local_info.last_modification_time.timetuple()),
                        doc_pair)


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
        self.watcher.watchdog_queue.put(event)


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
        if basename(event.src_path) != self.name:
            return
        self.counter += 1
        self.watcher.handle_watchdog_root_event(event)
