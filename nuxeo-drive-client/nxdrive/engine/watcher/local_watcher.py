'''
@author: Remi Cattiau
'''
from nxdrive.logging_config import get_logger
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from nxdrive.engine.engine import Worker, ThreadInterrupt
from nxdrive.utils import current_milli_time
from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_SUFFIX
from nxdrive.engine.activity import Action
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
        self._local_scan_finished = False
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
            self._action = Action("Setup watchdog")
            self._setup_watchdog()
            self._action = Action("Full local scan")
            self._scan()
            self._end_action()
            while (1):
                self._interact()
                sleep(1)
        except ThreadInterrupt:
            self._stop_watchdog()
            raise

    def _scan(self):
        log.debug("Full scan started")
        start_ms = current_milli_time()
        self._delete_files = dict()
        self._protected_files = dict()

        # Use the specific transaction from dao
        # Disable auto-commit
        self._dao.begin_transaction()
        try:
            info = self.client.get_info(u'/')
            self._scan_recursive(info)
            for deleted in self._delete_files:
                if deleted in self._protected_files:
                    continue
                self._dao.delete_local_state(self._delete_files[deleted])
        finally:
            # Dont rollback
            self._dao.end_transaction()
        self._metrics['last_local_scan_time'] = current_milli_time() - start_ms
        log.debug("Full scan finished in %dms",
                    self._metrics['last_local_scan_time'])
        self._local_scan_finished = True
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
        to_scan = []
        for child in db_children:
            children[child.local_name] = child

        # recursively update children
        for child_info in fs_children_info:
            child_name = os.path.basename(child_info.path)
            if not child_name in children:
                remote_id = self.client.get_remote_id(child_info.path)
                if remote_id is None:
                    log.debug("Found new file %s", child_info.path)
                    self._metrics['new_files'] = self._metrics['new_files'] + 1
                    self._dao.insert_local_state(child_info, info.path)
                else:
                    log.debug("Found potential moved file %s[%s]", child_info.path, remote_id)
                    doc_pair = self._dao.get_normal_state_from_remote(remote_id)
                    if doc_pair is None:
                        log.debug("Can't found reference put in locally_created state")
                        self._metrics['new_files'] = self._metrics['new_files'] + 1
                        self._dao.insert_local_state(child_info, info.path)
                        self._protected_files[remote_id]=True
                    elif not self.client.exists(doc_pair.local_path):
                        log.debug("Found a moved file")
                        doc_pair.local_state = 'moved'
                        self._dao.update_local_state(doc_pair, child_info)
                        self._protected_files[doc_pair.remote_ref]=True
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
                            if not old_pair is None:
                                old_pair.local_state = 'moved'
                                # Check digest also
                                digest = child_info.get_digest()
                                if old_pair.local_digest != digest:
                                    old_pair.local_digest = digest
                                self._dao.update_local_state(old_pair, self.client.get_info(doc_pair.local_path))
                                self._protected_files[old_pair.remote_ref]=True
                            doc_pair.local_state = 'moved'
                            # Check digest also
                            digest = child_info.get_digest()
                            if doc_pair.local_digest != digest:
                                doc_pair.local_digest = digest
                            self._dao.update_local_state(doc_pair, child_info)
                            self._protected_files[doc_pair.remote_ref]=True
                    # Dont browse content yet
            else:
                child_pair = children.pop(child_name)
                if (unicode(child_info.last_modification_time.strftime("%Y-%m-%d %H:%M:%S"))
                        != child_pair.last_local_updated):
                    log.trace("Update file %s", child_info.path)
                    remote_ref = self.client.get_remote_id(child_pair.local_path)
                    if remote_ref != child_pair.remote_ref:
                        # TO_REVIEW
                        # Load correct doc_pair | Put the others one back to children
                        log.warn("Detected file substitution")
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
                            self._protected_files[old_pair.remote_ref]=True
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

        for deleted in children.values():
            if deleted.pair_state == "remotely_created":
                continue
            log.debug("Found deleted file %s", deleted.local_path)
            # May need to count the children to be ok
            self._metrics['delete_files'] = self._metrics['delete_files'] + 1
            if deleted.remote_ref is None:
                self._dao.remove_pair(deleted)
            else:
                self._delete_files[deleted.remote_ref] = deleted

        for child_info in to_scan:
            self._scan_recursive(child_info)

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

    def _handle_watchdog_event_on_known_pair(self, doc_pair, evt, rel_path):
        if doc_pair.processor > 0:
            log.trace("Don't update as in process %r", doc_pair)
            return
        if (evt.event_type == 'moved'):
            src_path = normalize_event_filename(evt.dest_path)
            rel_path = self.client.get_path(src_path)
            local_info = self.client.get_info(rel_path)
            # Ignore inner movement
            remote_parent_ref = self.client.get_remote_id(self.client.get_path(
                                                        os.path.dirname(src_path)))
            if not (local_info.name == doc_pair.local_name and
                    doc_pair.remote_parent_ref == remote_parent_ref):
                log.debug("Detect move for %s (%r)", local_info.name, doc_pair)
                doc_pair.local_state = 'moved'
            elif doc_pair.local_state == 'moved':
                # The pair was moved but it has been canceled manually
                doc_pair.local_state = 'synchronized'
            self._dao.update_local_state(doc_pair, local_info)
            return
        if evt.event_type == 'deleted':
            if self.client.exists(doc_pair.local_path):
                # This happens on update dont do anything
                return
            doc_pair.update_state('deleted', doc_pair.remote_state)
            if doc_pair.remote_state == 'unknown':
                self._dao.remove_state(doc_pair)
            else:
                self._dao.delete_local_state(doc_pair)
            return
        local_info = self.client.get_info(rel_path)
        if doc_pair.local_state == 'synchronized':
            # TO_REVIEW Might want run those digester in a separate thread
            doc_pair.local_digest = local_info.get_digest()
            doc_pair.local_state = 'modified'
        queue = not (evt.event_type == 'modified' and doc_pair.folderish
                                and doc_pair.local_state == 'modified')
        self._dao.update_local_state(doc_pair, local_info, queue=queue)
        # No need to change anything on sync folder
        if (not queue):
            self._dao.synchronize_state(doc_pair, doc_pair.version + 1)

    def _handle_watchdog_root_event(self, evt):
        pass

    def handle_watchdog_event(self, evt):
        self._action = Action("Handle watchdog event")
        log.trace("handle_watchdog_event %s on %s", evt.event_type, evt.src_path)
        try:
            src_path = normalize_event_filename(evt.src_path)
            rel_path = self.client.get_path(src_path)
            if len(rel_path) == 0:
                self._handle_watchdog_root_event(evt)
                return
            file_name = os.path.basename(src_path)
            parent_path = os.path.dirname(src_path)
            parent_rel_path = self.client.get_path(parent_path)
            doc_pair = self._dao.get_state_from_local(rel_path)
            # Dont care about ignored file, unless it is moved
            if (self.client.is_ignored(parent_rel_path, file_name)
                  and evt.event_type != 'moved'):
                return
            if self.client.is_temp_file(file_name):
                return
            if doc_pair is not None:
                if doc_pair.pair_state == 'unsynchronized':
                    log.debug("Ignoring %s as marked unsynchronized",
                          doc_pair.local_path)
                    return
                self._handle_watchdog_event_on_known_pair(doc_pair, evt, rel_path)
                return
            if evt.event_type == 'deleted':
                return
            if evt.event_type == 'created':
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
                local_info = self.client.get_info(rel_path)
                # Handle creation of "Locally Edited" folder and its
                # children
                '''
                if file_name == LOCALLY_EDITED_FOLDER_NAME:
                    root_pair = self._controller.get_top_level_state(local_folder, session=session)
                    doc_pair = self._scan_local_new_file(session, name,
                                                local_info, root_pair)
                elif parent_rel_path.endswith(LOCALLY_EDITED_FOLDER_NAME):
                    parent_pair = session.query(LastKnownState).filter_by(
                        local_path=parent_path,
                        local_folder=local_folder).one()
                    doc_pair = self._scan_local_new_file(session, name,
                                                local_info, parent_pair)
                else:
                '''
                self._dao.insert_local_state(local_info, parent_rel_path)
                # An event can be missed inside a new created folder as
                # watchdog will put listener after it
                if local_info.folderish:
                    self._scan_recursive(local_info)
            # As you receive an event for every children move also
            elif evt.event_type == 'moved':
                # Try to see if it is a move from update
                # No previous pair as it was hidden file
                # Existing pair (may want to check the pair state)
                dst_rel_path = self.client.get_path(
                                normalize_event_filename(
                                                        evt.dest_path))
                dst_pair = self._dao.get_state_from_local(dst_rel_path)
                # No pair so it must be a filed moved to this folder
                if dst_pair is None:
                    if self.client.is_ignored(dst_rel_path, os.path.basename(dst_rel_path)):
                        return
                    local_info = self.client.get_info(dst_rel_path)
                    #name = fragments[1]
                    #parent_path = fragments[0]
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
                    self._dao.insert_local_state(local_info, parent_path)
                else:
                    # Must come from a modification
                    if dst_pair.processor == 0:
                        self._dao.update_local_state(dst_pair,
                                self.client.get_info(dst_rel_path))
                log.trace('Unhandled case: %r %s %s', evt, rel_path,
                         file_name)
                self.unhandle_fs_event = True
        except Exception as e:
            log.warn("Watchdog exception : %r" % e)
            log.exception(e)
        finally:
            self._action = None


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
