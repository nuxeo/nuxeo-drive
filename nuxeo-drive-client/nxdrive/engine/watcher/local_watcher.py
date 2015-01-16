'''
@author: Remi Cattiau
'''
from nxdrive.logging_config import get_logger
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from nxdrive.engine.engine import Worker, ThreadInterrupt
from nxdrive.utils import current_milli_time
import sys
import os
from time import time
from time import sleep
from nxdrive.engine.dao.model import LastKnownState
from PyQt4.QtCore import pyqtSignal
log = get_logger(__name__)

conflicted_changes = []


class LocalWatcher(Worker):
    localScanFinished = pyqtSignal()
    '''
    classdocs
    '''
    def __init__(self, engine, dao):
        '''
        Constructor
        '''
        super(LocalWatcher, self).__init__(engine)
        self.unhandle_fs_event = False
        self.local_full_scan = dict()
        self._dao = dao
        self.client = engine.get_local_client()
        self._metrics = dict()
        self._metrics['last_local_scan_time'] = -1
        self._metrics['new_files'] = 0
        self._metrics['update_files'] = 0
        self._metrics['delete_files'] = 0
        self._observer = None

    def _execute(self):
        try:
            self._setup_watchdog()
            self._scan()
            while (1):
                self._interact()
                sleep(1)
        except ThreadInterrupt:
            self._stop_watchdog()
            raise

    def _scan(self):
        log.debug("Full scan started")
        start_ms = current_milli_time()
        info = self.client.get_info(u'/')
        self._scan_recursive(info)
        self._dao.commit()
        self._metrics['last_local_scan_time'] = current_milli_time() - start_ms
        log.debug("Full scan finished in %dms",
                    self._metrics['last_local_scan_time'])
        self.localScanFinished.emit()

    def get_metrics(self):
        metrics = super(LocalWatcher, self).get_metrics()
        metrics['fs_events'] = self._event_handler.counter
        return dict(metrics.items() + self._metrics.items())

    def _scan_recursive(self, info):
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
        for child in db_children:
            children[child.local_name] = child

        # recursively update children
        for child_info in fs_children_info:
            child_name = os.path.basename(child_info.path)
            if not child_name in children:
                log.debug("Found new file %s", child_info.path)
                self._metrics['new_files'] = self._metrics['new_files'] + 1
                self._dao.insert_local_state(child_info, info.path)
            else:
                child_pair = children.pop(child_name)
                log.trace("Update file %s", child_info.path)
                if (unicode(child_info.last_modification_time.strftime("%Y-%m-%d %H:%M:%S"))
                        != child_pair.last_local_updated):
                    if not child_info.folderish:
                        child_pair.local_digest = child_info.get_digest()
                    self._metrics['update_files'] = self._metrics['update_files']+1
                    self._dao.update_local_state(child_pair, child_info)
            if child_info.folderish:
                self._scan_recursive(child_info)

        for deleted in children.values():
            log.debug("Found deleted file %s", deleted.local_path)
            # May need to count the children to be ok
            self._metrics['delete_files'] = self._metrics['delete_files']+1
            self._dao.delete_state(deleted)

    def _setup_watchdog(self):
        from watchdog.observers import Observer
        log.debug("Watching FS modification on : %s", self.client.base_folder)
        self._event_handler = DriveFSEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(self._event_handler, self.client.base_folder,
                          recursive=True)
        self._observer.start()

    def _stop_watchdog(self, raise_on_error=True):
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
        del self._observer

    def handle_local_changes(self, event):
        sorted_evts = []
        deleted_files = []
        # Use the thread_safe pop() to extract events
        while (len(self.local_changes)):
            evt = self.local_changes.pop()
            sorted_evts.append(evt)
        sorted_evts = sorted(sorted_evts, key=lambda evt: evt.time)
        log.debug('Sorted events: %r', sorted_evts)
        for evt in sorted_evts:
            self.handle_watchdog_event(evt)

    def handle_watchdog_event(self, evt):
        log.debug("handle_watchdog_event")
        try:
            src_path = normalize_event_filename(evt.src_path)
            rel_path = self.client.get_path(src_path)
            if len(rel_path) == 0:
                rel_path = '/'
            file_name = os.path.basename(src_path)
            doc_pair = self._dao.get_state_from_local(rel_path)
            # Ignore unsynchronized doc pairs
            if (doc_pair is not None
                and doc_pair.pair_state == 'unsynchronized'):
                log.debug("Ignoring %s as marked unsynchronized",
                          doc_pair.local_path)
                return
            if (doc_pair is not None and
                    self.client.is_ignored(doc_pair.local_parent_path,
                                                file_name)
                  and evt.event_type != 'moved'):
                return
            if (evt.event_type == 'created'
                    and doc_pair is None):
                # If doc_pair is not None mean
                # the creation has been catched by scan
                # As Windows send a delete / create event for reparent
                # Ignore .*.part ?
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
                fragments = rel_path.rsplit('/', 1)
                name = fragments[1]
                # Skip the .part as it is Nuxeo temporary download
                if name.startswith(".") and name.endswith(".part"):
                    return
                parent_path = fragments[0]
                local_info = self.client.get_info(rel_path)
                digest = local_info.get_digest()
                # Handle creation of "Locally Edited" folder and its
                # children
                '''
                if name == LOCALLY_EDITED_FOLDER_NAME:
                    root_pair = self._controller.get_top_level_state(local_folder, session=session)
                    doc_pair = self._scan_local_new_file(session, name,
                                                local_info, root_pair)
                elif parent_path.endswith(LOCALLY_EDITED_FOLDER_NAME):
                    parent_pair = session.query(LastKnownState).filter_by(
                        local_path=parent_path,
                        local_folder=local_folder).one()
                    doc_pair = self._scan_local_new_file(session, name,
                                                local_info, parent_pair)
                else:
                '''
                self._dao.insert_local_state(local_info, parent_path)
                # An event can be missed inside a new created folder as
                # watchdog will put listener after it
                if local_info.folderish:
                    self._scan_recursive(local_info)
            elif doc_pair is not None:
                if (evt.event_type == 'moved'):
                    #remote_client = self.get_remote_fs_client(
                    #                                        server_binding)
                    #self.handle_move(local_client, remote_client,
                    #                 doc_pair, src_path,
                    #            normalize_event_filename(evt.dest_path))
                    #session.commit()
                    doc_pair.local_state = 'moved'
                    self._dao.update_local_state(doc_pair, local_info)
                    return
                if evt.event_type == 'deleted':
                    doc_pair.update_state('deleted', doc_pair.remote_state)
                    self._dao.delete_local_state(doc_pair)
                    return
                local_info = self.client.get_info(rel_path)
                self._dao.update_local_state(doc_pair, local_info)
                if evt.event_type == 'modified' and doc_pair.folderish:
                    self._dao.synchronize_state(doc_pair, doc_pair.version + 1)
                    return
            else:
                # Event is the reflection of remote deletion
                if evt.event_type == 'deleted':
                    return
                # As you receive an event for every children move also
                if evt.event_type == 'moved':
                    # Try to see if it is a move from update
                    # No previous pair as it was hidden file
                    # Existing pair (may want to check the pair state)
                    dst_rel_path = self.client.get_path(
                                    normalize_event_filename(
                                                            evt.dest_path))
                    dst_pair = self._dao.get_state_from_local(dst_rel_path)
                    # No pair so it must be a filed moved to this folder
                    if dst_pair is None:
                        local_info = self.client.get_info(dst_rel_path)
                        fragments = dst_rel_path.rsplit('/', 1)
                        name = fragments[1]
                        parent_path = fragments[0]
                        # Locally edited patch
                        '''
                        if (parent_path
                            .endswith(LOCALLY_EDITED_FOLDER_NAME)):
                            parent_pair = (session.query(LastKnownState)
                                           .filter_by(
                                                local_path=parent_path,
                                                local_folder=local_folder)
                                           .one())
                            doc_pair = self._scan_local_new_file(
                                                            local_info,
                                                            parent_pair)
                            doc_pair.update_local(local_info)
                        else:
                        '''
                        # It can be consider as a creation
                        # TODO Add 3 argument
                        self._dao.insert_local_state(self.client.get_info(
                                                            dst_rel_path))
                    else:
                        # Must come from a modification
                        self._dao.update_local_state(dst_pair,
                                    self.client.get_info(dst_rel_path))
                    return
                log.trace('Unhandled case: %r %s %s', evt, rel_path,
                         file_name)
                self.unhandle_fs_event = True
        except Exception as e:
            log.warn("Watchdog exception : %r" % e)
            log.exception(e)


class DriveFSEventHandler(FileSystemEventHandler):
    def __init__(self, watcher):
        super(DriveFSEventHandler, self).__init__()
        self.watcher = watcher
        self.counter = 0

    def on_any_event(self, event):
        if self.counter == 0:
            self.watcher.handle_watchdog_event(event)
            return
        if event.event_type == 'moved':
            dest_path = normalize_event_filename(event.dest_path)
            try:
                conflicted_changes.index(dest_path)
                conflicted_changes.remove(dest_path)
                evt = FileCreatedEvent(event.dest_path)
                evt.time = time()
                self.queue.append(evt)
                log.info('Skipping move to %s as it is a conflict resolution',
                            dest_path)
                return
            except ValueError:
                pass
        if event.event_type == 'deleted':
            src_path = normalize_event_filename(event.src_path)
            try:
                conflicted_changes.index(src_path)
                conflicted_changes.remove(src_path)
                log.info('Skipping delete of %s as it is in fact an update',
                            src_path)
                return
            except ValueError:
                pass
        # Use counter instead of time so to be sure to respect the order
        # As 2 events can have the same ms
        self.counter += 1
        event.time = self.counter
        self.queue.append(event)
        log.trace('%d %r', self.counter, event)
        # ERROR_NOTIFY_ENUM_DIR should be sent in specific case


def normalize_event_filename(filename):
    import unicodedata
    if sys.platform == 'darwin':
        return unicodedata.normalize('NFC', unicode(filename, 'utf-8'))
    else:
        return unicodedata.normalize('NFC', unicode(filename))
