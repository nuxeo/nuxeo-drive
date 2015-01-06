'''
@author: Remi Cattiau
'''
from nxdrive.logging_config import get_logger
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
import sys
import os
from time import time
from nxdrive.engine.dao.model import LastKnownState
log = get_logger(__name__)

conflicted_changes = []


class LocalWatcher(object):
    '''
    classdocs
    '''
    def __init__(self, dao, local_folder, controller):
        '''
        Constructor
        '''
        self.unhandle_fs_event = False
        self.local_full_scan = dict()
        self.dao = dao
        self.controller = controller
        self.client = self.controller.get_local_client(local_folder)

    def scan(self):
        info = self.client.get_info(u'/')
        self._scan_recursive(info)
        self.dao.commit()

    def _scan_recursive(self, info):
        # Load all children from FS
        # detect recently deleted children
        try:
            fs_children_info = self.client.get_children_info(info.path)
        except OSError:
            # The folder has been deleted in the mean time
            return
        db_children = self.dao.get_local_children(info.path)
        # Create a list of all children by their name
        children = dict()
        for child in db_children:
            children[child.local_name] = child

        # recursively update children
        for child_info in fs_children_info:
            child_name = os.path.basename(child_info.path)
            if not child_name in children:
                log.debug("Found new file %s", child_info.path)
                child_pair = self.dao.insert_local_state(child_info)
            else:
                child_pair = children.pop(child_name)
                self.dao.update_local_state(child_pair, child_info)
            if child_info.folderish:
                self._scan_recursive(child_info)

        for deleted in children.values():
            log.debug("Found deleted file %s", child_info.path)
            self.dao.delete_state(deleted)

    def scan_local(self, server_binding_or_local_path, from_state=None,
                   session=None):
        """Recursively scan the bound local folder looking for updates"""
        session = self.get_session() if session is None else session

        if isinstance(server_binding_or_local_path, basestring):
            local_path = server_binding_or_local_path
            state = self._controller.get_state_for_local_path(local_path)
            server_binding = state.server_binding
            from_state = state
        else:
            server_binding = server_binding_or_local_path

        if from_state is None:
            from_state = session.query(LastKnownState).filter_by(
                local_path='/',
                local_folder=server_binding.local_folder).filter(
                    LastKnownState.pair_state != 'unsynchronized').one()

        client = self.get_local_client(from_state.local_folder)
        info = client.get_info('/')
        # recursive update
        self._scan_local_recursive(session, client, from_state, info)
        session.commit()

    def _scan_local_recursive(self, session, client, doc_pair, local_info):
        self.check_suspended('Local recursive scan')
        if doc_pair.pair_state == 'unsynchronized':
            log.trace("Ignoring %s as marked unsynchronized",
                      doc_pair.local_path)
            return
        if local_info is None:
            raise ValueError("Cannot bind %r to missing local info" %
                             doc_pair)

        # Update the pair state from the collected local info
        doc_pair.update_local(local_info)

        if not local_info.folderish:
            # No children to align, early stop.
            return

        # Load all children from db
        db_children = session.query(LastKnownState).filter_by(
                local_folder=doc_pair.local_folder,
                local_parent_path=doc_pair.local_path)
        # Create a list of all children by their name
        children = dict()
        for child in db_children:
            children[child.local_name] = child
        # Load all children from FS
        # detect recently deleted children
        try:
            fs_children_info = client.get_children_info(local_info.path)
        except OSError:
            # The folder has been deleted in the mean time
            return

        # recursively update children
        for child_info in fs_children_info:
            child_name = os.path.basename(child_info.path)
            if not child_name in children:
                child_pair = self._scan_local_new_file(session, child_name,
                                            child_info, doc_pair)
            else:
                child_pair = children.pop(child_name)
            if child_info.folderish:
                self._scan_local_recursive(session, client, child_pair,
                                       child_info)
            else:
                child_pair.update_local(local_info)

        for deleted in children.values():
            self._mark_deleted_local_recursive(session, deleted)

    def watchdog_local(self, server_binding):
        # Local scan is done, handle changes registered by watchdog
        if server_binding.local_folder in self.local_full_scan:
            if self.unhandle_fs_event:
                # Force a scan unhandle fs event has been found
                log.warn('Scan local as unhandled fs event')
                # Reset the local changes
                del self.local_changes[:]
                self.unhandle_fs_event = False
                # Remove to enable move detection
                self.local_full_scan.remove(
                                    server_binding.local_folder)
                self.scan_local(server_binding)
                # Add it again
                self.local_full_scan.append(
                                        server_binding.local_folder)
            else:
                self.handle_local_changes(server_binding)
        else:
            watcher_installed = False
            try:
                '''
                 Setup the FS notify before scanning
                 as we may create new file during the scan
                '''
                self.setup_local_watchdog(server_binding)
                watcher_installed = True
            except OSError:
                log.error("Cannot setup watchdog to monitor local"
                            " changes since inotify instance limit has"
                          " been reached. Please try increasing it,"
                          " typically under Linux by changing"
                          " /proc/sys/fs/inotify/max_user_instances",
                        exc_info=True)
            # Scan local folders to detect changes
            self.scan_local(server_binding)
            # Put the local_full_scan after to keep move detection
            if watcher_installed:
                self.local_full_scan.append(
                                        server_binding.local_folder)

    def setup_local_watchdog(self, server_binding):
        from watchdog.observers import Observer
        event_handler = DriveFSEventHandler(self.local_changes)
        observer = Observer()
        log.info("Watching FS modification on : %s",
                    server_binding.local_folder)
        observer.schedule(event_handler, server_binding.local_folder,
                          recursive=True)
        observer.start()
        self.observers.append(observer)

    def stop_observers(self, raise_on_error=True):
        log.info("Stopping all FS Observers thread")
        # Send the stop command
        for observer in self.observers:
            try:
                observer.stop()
            except:
                if raise_on_error:
                    raise
                else:
                    pass
        # Wait for all observers to stop
        for observer in self.observers:
            try:
                observer.join()
            except:
                if raise_on_error:
                    raise
                else:
                    pass
        # Delete all observers
        for observer in self.observers:
            del observer
        # Reinitialize list of observers
        self.observers = []


class DriveFSEventHandler(FileSystemEventHandler):
    def __init__(self, queue):
        super(DriveFSEventHandler, self).__init__()
        self.queue = queue
        self.counter = 0

    def on_any_event(self, event):
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
