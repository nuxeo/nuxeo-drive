
'''
@author: Remi Cattiau
'''
from nxdrive.logging_config import get_logger
from watchdog.events import FileSystemEventHandler
from nxdrive.engine.workers import EngineWorker, ThreadInterrupt
from nxdrive.utils import current_milli_time
from nxdrive.engine.activity import Action
from Queue import Queue
import sys
import os
from time import sleep, time
from threading import Lock
from PyQt4.QtCore import pyqtSignal, pyqtSlot
log = get_logger(__name__)

# Windows 2s between resolution of delete event
WIN_MOVE_RESOLUTION_PERIOD = 2000


class LocalWatcher(EngineWorker):
    localScanFinished = pyqtSignal()
    rootMoved = pyqtSignal(str)
    rootDeleted = pyqtSignal()
    '''
    classdocs
    '''
    def __init__(self, engine, dao):
        '''
        Constructor
        '''
        super(LocalWatcher, self).__init__(engine, dao)
        self.unhandle_fs_event = False
        self._event_handler = None
        self._windows = (sys.platform == 'win32')
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
            # Check windows dequeue only every 100 loops ( every 1s )
            self._win_delete_interval = int(round(time() * 1000))
            while (1):
                self._interact()
                sleep(0.01)
                if trigger_local_scan:
                    self._action = Action("Full local scan")
                    self._scan()
                    trigger_local_scan = False
                    self._end_action()
                while (not self._watchdog_queue.empty()):
                    # Dont retest if already local scan
                    if not trigger_local_scan and self._watchdog_queue.qsize() > 50:
                        trigger_local_scan = True
                    evt = self._watchdog_queue.get()
                    self.handle_watchdog_event(evt)
                    self._win_delete_check()
                self._win_delete_check()

        except ThreadInterrupt:
            raise
        finally:
            self._stop_watchdog()

    def win_queue_empty(self):
        return len(self._delete_events) == 0

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
        except Exception as e:
            log.exception(e)
        finally:
            self._win_lock.release()

    def _scan(self):
        log.debug("Full scan started")
        start_ms = current_milli_time()
        self._delete_files = dict()
        self._protected_files = dict()

        info = self.client.get_info(u'/')
        self._scan_recursive(info)
        for deleted in self._delete_files:
            if deleted in self._protected_files:
                continue
            self._dao.delete_local_state(self._delete_files[deleted])
        self._metrics['last_local_scan_time'] = current_milli_time() - start_ms
        log.debug("Full scan finished in %dms", self._metrics['last_local_scan_time'])
        self._local_scan_finished = True
        self.localScanFinished.emit()

    def get_metrics(self):
        metrics = super(LocalWatcher, self).get_metrics()
        if self._event_handler is not None:
            metrics['fs_events'] = self._event_handler.counter
        return dict(metrics.items() + self._metrics.items())

    @pyqtSlot(str)
    def scan_pair(self, local_path):
        info = self.client.get_info(local_path)
        self._scan_recursive(info, recursive=False)

    def empty_events(self):
        return self._watchdog_queue.empty()

    def _scan_recursive(self, info, recursive=True):
        self._interact()
        # Load all children from FS
        # detect recently deleted children
        try:
            fs_children_info = self.client.get_children_info(info.path)
        except OSError:
            # The folder has been deleted in the mean time
            return
        db_children = self._dao.get_local_children(info.path)
        # Create a list of all children by their name
        children = dict()
        to_scan = []
        to_scan_new = []
        for child in db_children:
            children[child.local_name] = child

        # recursively update children
        for child_info in fs_children_info:
            child_name = os.path.basename(child_info.path)
            child_type = 'folder' if child_info.folderish else 'file'
            if child_name not in children:
                try:
                    remote_id = self.client.get_remote_id(child_info.path)
                    if remote_id is None:
                        log.debug("Found new %s %s", child_type, child_info.path)
                        self._metrics['new_files'] = self._metrics['new_files'] + 1
                        self._dao.insert_local_state(child_info, info.path)
                    else:
                        log.debug("Found potential moved file %s[%s]", child_info.path, remote_id)
                        doc_pair = self._dao.get_normal_state_from_remote(remote_id)
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
                        elif not self.client.exists(doc_pair.local_path):
                            log.debug("Found a moved file")
                            doc_pair.local_state = 'moved'
                            self._dao.update_local_state(doc_pair, child_info)
                            self._protected_files[doc_pair.remote_ref] = True
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
                                log.debug("Moved and renamed")
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
                except Exception as e:
                    log.error('Error during recursive scan of %r, ignoring until next full scan', child_info.path,
                              exc_info=True)
                    continue
            else:
                child_pair = children.pop(child_name)
                try:
                    if (unicode(child_info.last_modification_time.strftime("%Y-%m-%d %H:%M:%S"))
                            != child_pair.last_local_updated and child_pair.processor == 0):
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
                            log.warn("Detected file substitution: %s (%s/%s)", child_pair.local_path, remote_ref,
                                     child_pair.remote_ref)
                            if remote_ref is None and not child_info.folderish:
                                # Alternative stream or xattr can have been removed by external software or user
                                digest = child_info.get_digest()
                                if child_pair.local_digest != digest:
                                    child_pair.local_digest = digest
                                    child_pair.local_state = 'modified'
                                self.client.set_remote_id(child_pair.local_path, child_pair.remote_ref)
                                self._dao.update_local_state(child_pair, child_info)
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
                    log.exception(e)
                    self.increase_error(child_pair, "SCAN RECURSIVE", exception=e)
                    continue

        for deleted in children.values():
            if deleted.pair_state == "remotely_created":
                continue
            log.debug("Found deleted file %s", deleted.local_path)
            # May need to count the children to be ok
            self._metrics['delete_files'] = self._metrics['delete_files'] + 1
            if deleted.remote_ref is None:
                self._dao.remove_state(deleted)
            else:
                self._delete_files[deleted.remote_ref] = deleted

        for child_info in to_scan_new:
            self._scan_recursive(child_info)

        if not recursive:
            return

        for child_info in to_scan:
            self._scan_recursive(child_info)

    def _setup_watchdog(self):
        from watchdog.observers import Observer
        log.debug("Watching FS modification on : %s", self.client.base_folder)
        self._event_handler = DriveFSEventHandler(self)
        self._root_event_handler = DriveFSRootEventHandler(self, os.path.basename(self.client.base_folder))
        self._observer = Observer()
        self._observer.schedule(self._event_handler, self.client.base_folder, recursive=True)
        self._observer.start()
        # Be sure to have at least one watchdog event
        timeout = 30
        lock = self.client.unlock_ref('/', False)
        try:
            fname = self.client._abspath('/.watchdog_setup')
            while (self._watchdog_queue.empty()):
                with open(fname, 'a'):
                    os.utime(fname, None)
                sleep(1)
                timeout = timeout - 1
                if timeout < 0:
                    log.debug("Can't have watchdog setup. Fallback to full scan mode ?")
                    os.remove(fname)
                    raise Exception
                os.remove(fname)
            if os.path.exists(fname):
                os.remove(fname)
        finally:
            self.client.lock_ref('/', lock)
        self._root_observer = Observer()
        self._root_observer.schedule(self._root_event_handler, os.path.dirname(self.client.base_folder), recursive=False)
        self._root_observer.start()

    def _stop_watchdog(self, raise_on_error=True):
        if self._observer is not None:
            log.info("Stopping FS Observer thread")
            try:
                self._observer.stop()
            except Exception as e:
                log.warn("Can't stop FS observer : %r", e)
            # Wait for all observers to stop
            try:
                self._observer.join()
            except Exception as e:
                log.warn("Can't join FS observer : %r", e)
            # Delete all observers
            self._observer = None
        if self._root_observer is not None:
            log.info("Stopping FS root Observer thread")
            try:
                self._root_observer.stop()
            except Exception as e:
                log.warn("Can't stop FS root observer : %r", e)
            # Wait for all observers to stop
            try:
                self._root_observer.join()
            except Exception as e:
                log.warn("Can't join FS root observer : %r", e)
            # Delete all observers
            self._root_observer = None

    def _handle_watchdog_delete(self, doc_pair):
        doc_pair.update_state('deleted', doc_pair.remote_state)
        if doc_pair.remote_state == 'unknown':
            self._dao.remove_state(doc_pair)
        else:
            self._dao.delete_local_state(doc_pair)

    def _handle_watchdog_event_on_known_pair(self, doc_pair, evt, rel_path):
        if (evt.event_type == 'moved'):
            # Ignore move to Office tmp file
            dest_filename = os.path.basename(evt.dest_path)
            if dest_filename.startswith('~') and dest_filename.endswith('.tmp'):
                log.debug('Ignoring Office tmp file: %r', evt.dest_path)
                return
            # Ignore normalization of the filename on the file system
            # See https://jira.nuxeo.com/browse/NXDRIVE-188
            if evt.dest_path == normalize_event_filename(evt.src_path):
                log.debug('Ignoring move from %r to normalized name: %r', evt.src_path, evt.dest_path)
                return
            src_path = normalize_event_filename(evt.dest_path)
            rel_path = self.client.get_path(src_path)
            local_info = self.client.get_info(rel_path, raise_if_missing=False)
            if local_info is not None:
                rel_parent_path = self.client.get_path(os.path.dirname(src_path))
                if rel_parent_path == '':
                    rel_parent_path = '/'
                # Ignore inner movement
                remote_parent_ref = self.client.get_remote_id(rel_parent_path)
                if (doc_pair.remote_name == local_info.name and
                        doc_pair.remote_parent_ref == remote_parent_ref):
                        # The pair was moved but it has been canceled manually
                        doc_pair.local_state = 'synchronized'
                elif not (local_info.name == doc_pair.local_name and
                        doc_pair.remote_parent_ref == remote_parent_ref):
                    log.debug("Detect move for %r (%r)", local_info.name, doc_pair)
                    if doc_pair.local_state != 'created':
                        doc_pair.local_state = 'moved'
                self._dao.update_local_state(doc_pair, local_info, versionned=False)
            return
        if doc_pair.processor > 0:
            log.trace("Don't update as in process %r", doc_pair)
            return
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
        if local_info is not None:
            if doc_pair.local_state == 'synchronized':
                digest = local_info.get_digest()
                # Drop event if digest hasn't changed, can be the case if only file permissions have been updated
                if not doc_pair.folderish and doc_pair.local_digest == digest:
                    log.debug('Dropping watchdog event [%s] as digest has not changed for %s',
                              evt.event_type, rel_path)
                    return
                doc_pair.local_digest = digest
                doc_pair.local_state = 'modified'
            queue = not (evt.event_type == 'modified' and doc_pair.folderish and doc_pair.local_state == 'modified')
            # No need to change anything on sync folder
            if (evt.event_type == 'modified' and doc_pair.folderish and doc_pair.local_state == 'modified'):
                doc_pair.local_state = 'synchronized'
            self._dao.update_local_state(doc_pair, local_info, queue=queue)

    def handle_watchdog_root_event(self, evt):
        if evt.event_type == 'modified' or evt.event_type == 'created':
            pass
        if evt.event_type == 'moved':
            log.warn("Root has been moved to ")
            self.rootMoved.emit(evt.dest_path)
        if evt.event_type == 'deleted':
            log.warn("Root has been deleted")
            self.rootDeleted.emit()

    def handle_watchdog_event(self, evt):
        log.trace("watchdog event: %r", evt)
        self._metrics['last_event'] = current_milli_time()
        self._action = Action("Handle watchdog event")
        if evt.event_type == 'moved':
            log.debug("Handling watchdog event [%s] on %s to %s", evt.event_type, evt.src_path, evt.dest_path)
        else:
            log.debug("Handling watchdog event [%s] on %r", evt.event_type, evt.src_path)
        try:
            src_path = normalize_event_filename(evt.src_path)
            rel_path = self.client.get_path(src_path)
            if len(rel_path) == 0 or rel_path == '/':
                self.handle_watchdog_root_event(evt)
                return
            file_name = os.path.basename(src_path)
            parent_path = os.path.dirname(src_path)
            parent_rel_path = self.client.get_path(parent_path)
            doc_pair = self._dao.get_state_from_local(rel_path)
            # Dont care about ignored file, unless it is moved
            if (self.client.is_ignored(parent_rel_path, file_name) and evt.event_type != 'moved'):
                return
            if self.client.is_temp_file(file_name):
                return
            if doc_pair is not None:
                if doc_pair.pair_state == 'unsynchronized':
                    log.debug("Ignoring %s as marked unsynchronized", doc_pair.local_path)
                    if evt.event_type == 'deleted' or evt.event_type == 'moved':
                        self._dao.remove_state(doc_pair)
                    return
                self._handle_watchdog_event_on_known_pair(doc_pair, evt, rel_path)
                return
            if evt.event_type == 'deleted':
                log.debug('Unknown pair deleted: %s', rel_path)
                return
            if (evt.event_type == 'moved'):
                dest_filename = os.path.basename(evt.dest_path)
                if (self.client.is_ignored(parent_rel_path, dest_filename)):
                    return
                # Ignore normalization of the filename on the file system
                # See https://jira.nuxeo.com/browse/NXDRIVE-188
                if evt.dest_path == normalize_event_filename(evt.src_path):
                    log.debug('Ignoring move from %r to normalized name: %r', evt.src_path, evt.dest_path)
                    return
                src_path = normalize_event_filename(evt.dest_path)
                rel_path = self.client.get_path(src_path)
                local_info = self.client.get_info(rel_path, raise_if_missing=False)
                doc_pair = self._dao.get_state_from_local(rel_path)
                # If the file exsit but not the pair
                if local_info is not None and doc_pair is None:
                    rel_parent_path = self.client.get_path(os.path.dirname(src_path))
                    if rel_parent_path == '':
                        rel_parent_path = '/'
                    self._dao.insert_local_state(local_info, rel_parent_path)
                    # An event can be missed inside a new created folder as
                    # watchdog will put listener after it
                    if local_info.folderish:
                        self._scan_recursive(local_info)
                return
            # if the pair is modified and not known consider as created
            if evt.event_type == 'created' or evt.event_type == 'modified':
                # If doc_pair is not None mean
                # the creation has been catched by scan
                # As Windows send a delete / create event for reparent
                # Ignore .*.nxpart ?
                '''
                for deleted in deleted_files:
                    if deleted.local_digest == digest:
                        # Move detected
                        log.info('Detected a file movement %r', deleted)
                        deleted.update_state('moved', deleted.remote_state)
                        deleted.update_local(self.client.get_info(
                                                                rel_path))
                        continue
                '''
                local_info = self.client.get_info(rel_path)
                # This might be a move but Windows don't emit this event...
                if local_info.remote_ref is not None:
                    from_pair = self._dao.get_normal_state_from_remote(local_info.remote_ref)
                    if from_pair is not None and (from_pair.processor > 0 or from_pair.local_path == rel_path):
                        # First condition is in process
                        # Second condition is a race condition
                        log.trace("Ignore creation or modification as the coming pair is being processed")
                        return
                    if self._windows:
                        self._win_lock.acquire()
                        try:
                            if local_info.remote_ref in self._delete_events:
                                log.debug('Found creation in delete event, handle move instead')
                                doc_pair = self._delete_events[local_info.remote_ref][1]
                                doc_pair.local_state = 'moved'
                                self._dao.update_local_state(doc_pair, self.client.get_info(rel_path))
                                del self._delete_events[local_info.remote_ref]
                                return
                        finally:
                            self._win_lock.release()
                self._dao.insert_local_state(local_info, parent_rel_path)
                # An event can be missed inside a new created folder as
                # watchdog will put listener after it
                if local_info.folderish:
                    self._scan_recursive(local_info)
                return
            log.debug('Unhandled case: %r %s %s', evt, rel_path, file_name)
        except Exception:
            log.error('Watchdog exception', exc_info=True)
        finally:
            self._end_action()


class DriveFSEventHandler(FileSystemEventHandler):
    def __init__(self, watcher):
        super(DriveFSEventHandler, self).__init__()
        self.counter = 0
        self.watcher = watcher

    def on_any_event(self, event):
        self.counter = self.counter + 1
        log.trace("Queueing watchdog: %r", event)
        self.watcher._watchdog_queue.put(event)


class DriveFSRootEventHandler(FileSystemEventHandler):
    def __init__(self, watcher, name):
        super(DriveFSRootEventHandler, self).__init__()
        self.name = name
        self.counter = 0
        self.watcher = watcher

    def on_any_event(self, event):
        log.trace("DriveFSROOT: %s : need: %s",os.path.basename(event.src_path), self.name)
        if os.path.basename(event.src_path) != self.name:
            return
        self.counter = self.counter + 1
        self.watcher.handle_watchdog_root_event(event)


def normalize_event_filename(filename):
    import unicodedata
    if sys.platform == 'darwin':
        normalized_filename = unicodedata.normalize('NFC', unicode(filename, 'utf-8'))
    else:
        normalized_filename = unicodedata.normalize('NFC', unicode(filename))
    # Normalize name on the file system if not normalized
    # See https://jira.nuxeo.com/browse/NXDRIVE-188
    if os.path.exists(filename) and normalized_filename != filename:
        log.debug('Forcing normalization of %r to %r', filename, normalized_filename)
        os.rename(filename, normalized_filename)
    return normalized_filename
