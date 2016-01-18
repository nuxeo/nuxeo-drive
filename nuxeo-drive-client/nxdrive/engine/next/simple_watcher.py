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
            if local_info is None:
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

    def _scan_recursive(self, info, recursive=True):
        log.debug('Starting recursive local scan of %r', info.path)
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
        # recursively update children
        for child_info in fs_children_info:
            child_name = os.path.basename(child_info.path)
            child_type = 'folder' if child_info.folderish else 'file'
            if child_name == 'Test file.odt':
                print child_info
            if child_name not in children:
                # New item found on FS
                try:
                    remote_id = self.client.get_remote_id(child_info.path)
                    if remote_id is None:
                        if child_info.path == '/Nuxeo Drive Test Workspace':
                            log.warn("children: %r", children)
                            log.warn("fschildren: %r", fs_children_info)
                        log.debug("Found new %s %s", child_type, child_info.path)
                        try:
                            self._dao.insert_local_state(child_info, info.path)
                            self._metrics['new_files'] = self._metrics['new_files'] + 1
                            if child_info.folderish:
                                to_scan_new.append(child_info)
                        except sqlite3.IntegrityError:
                            log.debug("New item %s %s was already in database", child_type, child_info.path)
                        continue
                    log.debug("Found potential moved file %s[%s]", child_info.path, remote_id)
                    doc_pair = self._dao.get_normal_state_from_remote(remote_id)
                    if doc_pair is None:
                        log.debug("Can't find reference for %s in database, put it in locally_created state",
                                  child_info.path)
                        self._metrics['new_files'] = self._metrics['new_files'] + 1
                        self._dao.insert_local_state(child_info, info.path)
                        # TODO Why adding in protected ?
                        #self._protected_files[remote_id] = True
                        continue
                    if doc_pair.processor > 0:
                        log.debug('Skip pair as it is being processed: %r', doc_pair)
                        continue
                    if doc_pair.local_path == child_info.path:
                        log.debug('Skip pair as it is not a real move: %r', doc_pair)
                        continue
                    if not self.client.exists(doc_pair.local_path):
                        # Found a moved file
                        log.debug("Found moved file")
                        doc_pair.local_state = 'moved'
                        self._dao.update_local_state(doc_pair, child_info)
                        # TODO Why adding to protected
                        #self._protected_files[doc_pair.remote_ref] = True
                        continue
                    # possible move-then-copy case, NXDRIVE-471
                    child_full_path = self.client._abspath(child_info.path)
                    child_creation_time = self.get_creation_time(child_full_path)
                    doc_full_path = self.client._abspath(doc_pair.local_path)
                    doc_creation_time = self.get_creation_time(doc_full_path)
                    log.trace('child_cre_time=%f, doc_cre_time=%f', child_creation_time, doc_creation_time)
                    if child_creation_time < doc_creation_time:
                        # If file exists at old location, and the file at the original location is newer,
                        #   it is moved to the new location earlier then copied back
                        log.debug("Found moved file")
                        doc_pair.local_state = 'moved'
                        self._dao.update_local_state(doc_pair, child_info)
                        self._protected_files[doc_pair.remote_ref] = True
                        # Need to put back the new created - need to check maybe if already there
                        log.trace("Found a moved file that has been copy/paste back: %s", doc_pair.local_path)
                        self.client.remove_remote_id(doc_pair.local_path)
                        self._dao.insert_local_state(self.client.get_info(doc_pair.local_path), os.path.dirname(doc_pair.local_path))
                        continue
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
                except Exception as e:
                    log.error('Error during recursive scan of %r, ignoring until next full scan', child_info.path,
                              exc_info=True)
                    continue
            else:
                # Known FS item
                child_pair = children.pop(child_name)
                if (child_pair.processor != 0 or child_pair.pair_state == 'remotely_created' or
                    (unicode(child_info.last_modification_time.strftime("%Y-%m-%d %H:%M:%S"))
                        == child_pair.last_local_updated.split(".")[0])):
                    continue
                try:
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
            self._push_to_scan(child_info)

        if not recursive:
            log.debug('Ended recursive local scan of %r', info.path)
            return

        for child_info in to_scan:
            self._push_to_scan(child_info)

        log.debug('Ended recursive local scan of %r', info.path)

    def _scan_path(self, path):
        if self.client.exists(path):
            log.warn("Scan delayed folder: %s:%d", path, len(self.client.get_children_info(path)))
            local_info = self.client.get_info(path, raise_if_missing=False)
            if local_info is not None:
                self._scan_recursive(local_info, False)
                log.warn("scan delayed done")
        else:
            log.warn("Cannot scan delayed deleted folder: %s", path)
