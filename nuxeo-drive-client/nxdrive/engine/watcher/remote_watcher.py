'''
Created on 8 janv. 2015

@author: Remi Cattiau
'''
from nxdrive.logging_config import get_logger
from nxdrive.engine.workers import EngineWorker
from nxdrive.utils import current_milli_time
from nxdrive.client import NotFound
from time import sleep
from datetime import datetime
from nxdrive.client.common import COLLECTION_SYNC_ROOT_FACTORY_NAME
from nxdrive.client.remote_file_system_client import RemoteFileInfo
from nxdrive.engine.activity import Action
from nxdrive.client.common import safe_filename
from nxdrive.client.base_automation_client import Unauthorized
from nxdrive.utils import path_join
from httplib import BadStatusLine
from urllib2 import HTTPError, URLError
import os
import socket
log = get_logger(__name__)
from PyQt4.QtCore import pyqtSignal, pyqtSlot
from nxdrive.engine.workers import ThreadInterrupt


class RemoteWatcher(EngineWorker):
    initiate = pyqtSignal()
    updated = pyqtSignal()
    remoteScanFinished = pyqtSignal()
    changesFound = pyqtSignal(int)
    noChangesFound = pyqtSignal()
    remoteWatcherStopped = pyqtSignal()

    def __init__(self, engine, dao, delay):
        super(RemoteWatcher, self).__init__(engine, dao)
        self.server_interval = delay
        # Review to delete
        self._init()
        self._current_interval = 0

    def _init(self):
        self.unhandle_fs_event = False
        self.local_full_scan = dict()
        self._full_scan_mode = False
        self._last_sync_date = self._dao.get_config('remote_last_sync_date')
        self._last_event_log_id = self._dao.get_config('remote_last_event_log_id')
        self._last_root_definitions = self._dao.get_config('remote_last_root_definitions')
        self._last_remote_full_scan = self._dao.get_config('remote_last_full_scan')
        self._client = None
        self._local_client = self._engine.get_local_client()
        self._metrics = dict()
        self._metrics['last_remote_scan_time'] = -1
        self._metrics['last_remote_update_time'] = -1
        self._metrics['empty_polls'] = 0

    def get_engine(self):
        return self._engine

    def get_metrics(self):
        metrics = super(RemoteWatcher, self).get_metrics()
        metrics['last_remote_sync_date'] = self._last_sync_date
        metrics['last_event_log_id'] = self._last_event_log_id
        metrics['last_root_definitions'] = self._last_root_definitions
        metrics['last_remote_full_scan'] = self._last_remote_full_scan
        metrics['next_polling'] = self._current_interval
        return dict(metrics.items() + self._metrics.items())

    @pyqtSlot()
    def _reset_clients(self):
        self._client = None

    def _execute(self):
        first_pass = True
        try:
            self._init()
            while (1):
                self._interact()
                if self._current_interval == 0:
                    #
                    self._current_interval = self.server_interval * 100
                    if self._handle_changes(first_pass):
                        first_pass = False
                else:
                    self._current_interval = self._current_interval - 1
                sleep(0.01)
        except ThreadInterrupt:
            self.remoteWatcherStopped.emit()
            raise

    def _scan_remote(self, from_state=None):
        """Recursively scan the bound remote folder looking for updates"""
        start_ms = current_milli_time()
        try:
            if from_state is None:
                from_state = self._dao.get_state_from_local('/')
            self._client = self._engine.get_remote_client()
            remote_info = self._client.get_info(from_state.remote_ref)
            self._dao.update_remote_state(from_state, remote_info, remote_parent_path=from_state.remote_parent_path)
        except NotFound:
            log.debug("Marking %r as remotely deleted.", from_state)
            # Should unbind ?
            # from_state.update_remote(None)
            self._dao.commit()
            self._metrics['last_remote_scan_time'] = current_milli_time() - start_ms
            return
        self._get_changes()
        self._save_changes_state()
        # recursive update
        self._scan_remote_recursive(from_state, remote_info)
        self._last_remote_full_scan = datetime.utcnow()
        self._dao.update_config('remote_last_full_scan', self._last_remote_full_scan)
        self._dao.clean_scanned()
        self._dao.commit()
        self._metrics['last_remote_scan_time'] = current_milli_time() - start_ms
        log.debug("Remote scan finished in %dms", self._metrics['last_remote_scan_time'])
        self.remoteScanFinished.emit()

    @pyqtSlot(str)
    def scan_pair(self, remote_path):
        self._dao.add_path_to_scan(str(remote_path))
        self._current_interval = 0

    def _scan_pair(self, remote_path):
        if remote_path is None:
            return
        remote_path = str(remote_path)
        if self._dao.is_filter(remote_path):
            # Skip if filter
            return
        if remote_path[-1:] == '/':
            remote_path = remote_path[0:-1]
        remote_ref = os.path.basename(remote_path)
        parent_path = os.path.dirname(remote_path)
        if parent_path == '/':
            parent_path = ''
        # If pair is present already
        try:
            child_info = self._client.get_info(remote_ref)
        except NotFound:
            # The folder has been deleted
            return
        doc_pair = self._dao.get_state_from_remote_with_path(remote_ref, parent_path)
        if doc_pair is not None:
            log.debug("Remote scan_pair: %s", doc_pair.local_path)
            self._scan_remote_recursive(doc_pair, child_info)
            log.debug("Remote scan_pair ended: %s", doc_pair.local_path)
            return
        log.debug("parent_path: '%s'\t'%s'\t'%s'", parent_path, os.path.basename(parent_path),
                  os.path.dirname(parent_path))
        parent_pair = self._dao.get_state_from_remote_with_path(os.path.basename(parent_path),
                                                                os.path.dirname(parent_path))
        log.debug("scan_pair: parent_pair: %r", parent_pair)
        if parent_pair is None:
            return
        local_path = path_join(parent_pair.local_path, safe_filename(child_info.name))
        remote_parent_path = parent_pair.remote_parent_path + '/' + parent_pair.remote_ref
        row_id = self._dao.insert_remote_state(child_info, remote_parent_path, local_path, parent_pair.local_path)
        doc_pair = self._dao.get_state_from_id(row_id, from_write=True)
        if child_info.folderish:
            log.debug("Remote scan_pair: %s", doc_pair.local_path)
            self._scan_remote_recursive(doc_pair, child_info)
            log.debug("Remote scan_pair ended: %s", doc_pair.local_path)

    def _check_modified(self, child_pair, child_info):
        if child_pair.remote_can_delete != child_info.can_delete:
            return True
        if child_pair.remote_can_rename != child_info.can_rename:
            return True
        if child_pair.remote_can_update != child_info.can_update:
            return True
        if child_pair.remote_can_create_child != child_info.can_create_child:
            return True
        if child_pair.remote_digest != child_info.digest:
            return True
        return False

    def _scan_remote_recursive(self, doc_pair, remote_info,
                               force_recursion=True, mark_unknown=True):
        """Recursively scan the bound remote folder looking for updates

        If force_recursion is True, recursion is done even on
        non newly created children.
        """
        if not remote_info.folderish:
            # No children to align, early stop.
            return
        # Check if synchronization thread was suspended
        self._interact()
        remote_parent_path = doc_pair.remote_parent_path + '/' + remote_info.uid
        if self._dao.is_path_scanned(remote_parent_path):
            log.trace("Skip already remote scanned: %s", doc_pair.local_path)
            return
        if doc_pair.local_path is not None:
            self._action = Action("Remote scanning : " + doc_pair.local_path)
            log.debug("Remote scanning: %s", doc_pair.local_path)

        if remote_info is None:
            raise ValueError("Cannot bind %r to missing remote info" %
                             doc_pair)

        # If a folderish pair state has been remotely updated,
        # recursively unmark its local descendants as 'unsynchronized'
        # by marking them as 'unknown'.
        # This is needed to synchronize unsynchronized items back.
        if mark_unknown:
            # TODO Should be DAO method
            pass

        # Detect recently deleted children
        db_children = self._dao.get_remote_children(doc_pair.remote_ref)
        children_info = self._client.get_children_info(remote_info.uid)
        children = dict()
        to_scan = []
        for child in db_children:
            children[child.remote_ref] = child

        for child_info in children_info:
            log.trace('Scanning remote child: %r', child_info)
            child_pair = None
            new_pair = False
            if child_info.uid in children:
                child_pair = children.pop(child_info.uid)
                if self._check_modified(child_pair, child_info):
                    child_pair.remote_state = 'modified'
                self._dao.update_remote_state(child_pair, child_info, remote_parent_path=remote_parent_path)
            else:
                child_pair, new_pair = self._find_remote_child_match_or_create(doc_pair, child_info)
            if ((new_pair or force_recursion) and remote_info.folderish):
                    to_scan.append((child_pair, child_info))
        # Delete remaining
        for deleted in children.values():
            # TODO Should be DAO
            # self._dao.mark_descendants_remotely_deleted(deleted)
            self._dao.delete_remote_state(deleted)

        for folder in to_scan:
            # TODO Optimize by multithreading this too ?
            self._scan_remote_recursive(folder[0], folder[1],
                                        mark_unknown=False, force_recursion=force_recursion)
        self._dao.add_path_scanned(remote_parent_path)

    def _find_remote_child_match_or_create(self, parent_pair, child_info):
        local_path = path_join(parent_pair.local_path, safe_filename(child_info.name))
        remote_parent_path = parent_pair.remote_parent_path + '/' + parent_pair.remote_ref
        # Try to get the local definition if not linked
        child_pair = self._dao.get_state_from_local(local_path)
        # Case of duplication: the file can exists in with a __x
        if child_pair is None and parent_pair is not None and self._local_client.exists(parent_pair.local_path):
            for child in self._local_client.get_children_info(parent_pair.local_path):
                # Skip any file without __ as it cannot be a deduplicate
                if '__' not in child.name:
                    continue
                if self._local_client.get_remote_id(child.path) == child_info.uid:
                    log.debug("Found a deduplication case: %r on %s", child_info, child.path)
                    child_pair = self._dao.get_state_from_local(child.path)
                    break
        if child_pair is not None:
            if child_pair.remote_ref is not None:
                child_pair = None
            else:
                if (child_pair.folderish == child_info.folderish
                        and self._local_client.is_equal_digests(child_pair.local_digest, child_info.digest,
                                                                child_pair.local_path,
                                                                remote_digest_algorithm=child_info.digest_algorithm)):
                    self._dao.update_remote_state(child_pair, child_info, remote_parent_path=remote_parent_path)
                    # Use version+1 as we just update the remote info
                    synced = self._dao.synchronize_state(child_pair, version=child_pair.version + 1)
                    if not synced:
                        # Try again, might happen that it has been modified locally and remotely
                        child_pair = self._dao.get_state_from_id(child_pair.id)
                        if (child_pair.folderish == child_info.folderish
                                and self._local_client.is_equal_digests(
                                    child_pair.local_digest, child_info.digest,
                                    child_pair.local_path,
                                    remote_digest_algorithm=child_info.digest_algorithm)):
                            self._dao.synchronize_state(child_pair)
                            child_pair = self._dao.get_state_from_id(child_pair.id)
                            synced = child_pair.pair_state == 'synchronized'
                    # Can be updated in previous call
                    if synced:
                        self._engine.stop_processor_on(child_pair.local_path)
                    # Push the remote_Id
                    self._local_client.set_remote_id(local_path, child_info.uid)
                    if child_pair.folderish:
                        self._dao.queue_children(child_pair)
                else:
                    child_pair.remote_state = 'modified'
                    self._dao.update_remote_state(child_pair, child_info, remote_parent_path=remote_parent_path)
                child_pair = self._dao.get_state_from_id(child_pair.id, from_write=True)
                return child_pair, False
        row_id = self._dao.insert_remote_state(child_info, remote_parent_path, local_path, parent_pair.local_path)
        child_pair = self._dao.get_state_from_id(row_id, from_write=True)
        return child_pair, True

    def _partial_full_scan(self, path):
        log.debug("Continue full scan of %s", path)
        if path == '/':
            self._scan_remote()
        else:
            self._scan_pair(path)
        self._dao.delete_path_to_scan(path)
        self._dao.delete_config('remote_need_full_scan')
        self._dao.clean_scanned()

    def _check_offline(self):
        try:
            self._client = self._engine.get_remote_client()
        except HTTPError as e:
            if e.code == 401 or e.code == 403:
                if not self._engine.has_invalid_credentials():
                    self._engine.set_invalid_credentials(reason='got HTTPError %d while checking if offline' % e.code,
                                                         exception=e)
        except Unauthorized as e:
            if not self._engine.has_invalid_credentials():
                self._engine.set_invalid_credentials(reason='got Unauthorized with code %s while checking if offline'
                                                     % e.code if hasattr(e, 'code') and e.code else 'None',
                                                     exception=e)
        except:
            pass
        if self._client is None:
            if not self._engine.is_offline():
                self._engine.set_offline()
            return None
        if self._engine.is_offline():
            try:
                # Try to get the api
                self._client.fetch_api()
                # if retrieved
                self._engine.set_offline(False)
                return self._client
            except ThreadInterrupt as e:
                raise e
            except:
                return None
        return self._client

    def _handle_changes(self, first_pass=False):
        log.debug("Handle remote changes, first_pass=%r", first_pass)
        self._client = self._check_offline()
        if self._client is None:
            return False
        try:
            if self._last_remote_full_scan is None:
                log.debug("Remote full scan")
                self._action = Action("Remote scanning")
                self._scan_remote()
                self._end_action()
                # Might need to handle the changes now
                if first_pass:
                    self.initiate.emit()
                return True
            full_scan = self._dao.get_config('remote_need_full_scan', None)
            if full_scan is not None:
                self._partial_full_scan(full_scan)
                return
            else:
                paths = self._dao.get_paths_to_scan()
                while len(paths) > 0:
                    remote_ref = paths[0].path
                    self._dao.update_config('remote_need_full_scan', remote_ref)
                    self._partial_full_scan(remote_ref)
                    paths = self._dao.get_paths_to_scan()
            self._action = Action("Handle remote changes")
            self._update_remote_states()
            self._save_changes_state()
            if first_pass:
                self.initiate.emit()
            else:
                self.updated.emit()
            return True
        except HTTPError as e:
            if e.code == 401 or e.code == 403:
                self._engine.set_invalid_credentials(reason='got HTTPError %d while trying to handle remote changes'
                                                     % e.code, exception=e)
            else:
                log.exception(e)
            self._engine.set_offline()
        except (BadStatusLine, URLError, socket.error) as e:
            # Pause the rest of the engine
            log.exception(e)
            self._engine.set_offline()
        except ThreadInterrupt as e:
            raise e
        except Exception as e:
            log.exception(e)
        finally:
            self._end_action()
        return False

    def _save_changes_state(self):
        self._dao.update_config('remote_last_sync_date', self._last_sync_date)
        self._dao.update_config('remote_last_event_log_id', self._last_event_log_id)
        self._dao.update_config('remote_last_root_definitions', self._last_root_definitions)

    def _get_changes(self):
        """Fetch incremental change summary from the server"""
        summary = self._client.get_changes(self._last_root_definitions, self._last_event_log_id, self._last_sync_date)

        self._last_root_definitions = summary['activeSynchronizationRootDefinitions']
        self._last_sync_date = summary['syncDate']
        if self._client.is_event_log_id_available():
            # If available, read 'upperBound' key as last event log id
            # according to the new implementation of the audit change finder,
            # see https://jira.nuxeo.com/browse/NXP-14826.
            self._last_event_log_id = summary['upperBound']
        else:
            self._last_event_log_id = None
        return summary

    def _force_scan_recursive(self, doc_pair, remote_info, remote_path=None, force_recursion=True):
        if remote_path is None:
            remote_path = remote_info.path
        self._dao.update_config('remote_need_full_scan', remote_path)
        self._scan_remote_recursive(doc_pair, remote_info, force_recursion)
        self._dao.delete_config('remote_need_full_scan')
        self._dao.clean_scanned()

    def _update_remote_states(self):
        """Incrementally update the state of documents from a change summary"""
        summary = self._get_changes()
        if summary['hasTooManyChanges']:
            log.debug("Forced full scan by server")
            remote_path = '/'
            self._dao.add_path_to_scan(remote_path)
            self._dao.update_config('remote_need_full_scan', remote_path)
            return
        # Fetch all events and consider the most recent first
        sorted_changes = sorted(summary['fileSystemChanges'],
                                key=lambda x: x['eventDate'], reverse=True)
        n_changes = len(sorted_changes)
        if n_changes > 0:
            log.debug("%d remote changes detected", n_changes)
            self._metrics['last_changes'] = n_changes
            self._metrics['empty_polls'] = 0
            self.changesFound.emit(n_changes)
        else:
            self._metrics['empty_polls'] = self._metrics['empty_polls'] + 1
            self.noChangesFound.emit()

        # Scan events and update the related pair states
        refreshed = set()
        delete_queue = []
        for change in sorted_changes:

            # Check if synchronization thread was suspended
            # TODO In case of pause or stop: save the last event id
            log.trace("Interacting...")
            self._interact()
            log.trace("Interacting finished...")

            eventId = change.get('eventId')
            remote_ref = change['fileSystemItemId']
            processed = False
            for refreshed_ref in refreshed:
                if refreshed_ref.endswith(remote_ref):
                    processed = True
                    break
            if processed:
                # A more recent version was already processed
                continue
            fs_item = change.get('fileSystemItem')
            new_info = self._client.file_to_info(fs_item) if fs_item else None
            log.trace("Processing event: %r", change)
            # Possibly fetch multiple doc pairs as the same doc can be synchronized at 2 places,
            # typically if under a sync root and locally edited.
            # See https://jira.nuxeo.com/browse/NXDRIVE-125
            doc_pairs = self._dao.get_states_from_remote(remote_ref)
            if not doc_pairs:
                # Relax constraint on factory name in FileSystemItem id to
                # match 'deleted' or 'securityUpdated' events.
                # See https://jira.nuxeo.com/browse/NXDRIVE-167
                doc_pair = self._dao.get_first_state_from_partial_remote(remote_ref)
                if doc_pair is not None:
                    doc_pairs = [doc_pair]

            updated = False
            if doc_pairs:
                for doc_pair in doc_pairs:
                    doc_pair_repr = doc_pair.local_path if doc_pair.local_path is not None else doc_pair.remote_name
                    if eventId == 'deleted':
                        if fs_item is None:
                            log.debug("Push doc_pair '%s' in delete queue",
                                      doc_pair_repr)
                            delete_queue.append(doc_pair)
                        else:
                            log.debug("Ignore delete on doc_pair '%s' as a fsItem is attached", doc_pair_repr)
                            # To ignore completely put updated to true
                            updated = True
                            break
                    elif fs_item is None:
                        if eventId == 'securityUpdated':
                            log.debug("Security has been updated for"
                                      " doc_pair '%s' denying Read access,"
                                      " marking it as deleted",
                                      doc_pair_repr)
                            self._dao.delete_remote_state(doc_pair)
                        else:
                            log.debug("Unknow event: '%s'", eventId)
                    else:
                        remote_parent_factory = doc_pair.remote_parent_ref.split('#', 1)[0]
                        new_info_parent_factory = new_info.parent_uid.split('#', 1)[0]
                        # Specific cases of a move on a locally edited doc
                        if (eventId == 'documentMoved' and remote_parent_factory == COLLECTION_SYNC_ROOT_FACTORY_NAME):
                                # If moved from a non sync root to a sync root, break to creation case
                                # (updated is False).
                                # If moved from a sync root to a non sync root, break to noop
                                # (updated is True).
                                break
                        elif (eventId == 'documentMoved'
                              and new_info_parent_factory == COLLECTION_SYNC_ROOT_FACTORY_NAME):
                            # If moved from a sync root to a non sync root, delete from local sync root
                            log.debug("Marking doc_pair '%s' as deleted", doc_pair_repr)
                            self._dao.delete_remote_state(doc_pair)
                        else:
                            # Make new_info consistent with actual doc pair parent path for a doc member of a
                            # collection (typically the Locally Edited one) that is also under a sync root.
                            # Indeed, in this case, when adapted as a FileSystemItem, its parent path will be the one
                            # of the sync root because it takes precedence over the collection,
                            # see AbstractDocumentBackedFileSystemItem constructor.
                            consistent_new_info = new_info
                            if remote_parent_factory == COLLECTION_SYNC_ROOT_FACTORY_NAME:
                                new_info_parent_uid = doc_pair.remote_parent_ref
                                new_info_path = (doc_pair.remote_parent_path + '/' + remote_ref)
                                consistent_new_info = RemoteFileInfo(new_info.name, new_info.uid, new_info_parent_uid,
                                                                     new_info_path, new_info.folderish,
                                                                     new_info.last_modification_time,
                                                                     new_info.last_contributor, new_info.digest,
                                                                     new_info.digest_algorithm, new_info.download_url,
                                                                     new_info.can_rename, new_info.can_delete,
                                                                     new_info.can_update, new_info.can_create_child)
                            # Perform a regular document update on a document
                            # that has been updated, renamed or moved
                            log.debug("Refreshing remote state info"
                                      " for doc_pair '%s', eventId = %s (force_recursion:%d)", doc_pair_repr, eventId,
                                      (eventId == "securityUpdated"))
                            remote_parent_path = doc_pair.remote_parent_path
                            # if (new_info.digest != doc_pair.local_digest or
                            #     safe_filename(new_info.name) != doc_pair.local_name
                            #     or new_info.parent_uid != doc_pair.remote_parent_ref):
                            if doc_pair.remote_state != 'created':
                                doc_pair.remote_state = 'modified'
                                remote_parent_path = os.path.dirname(new_info.path)
                            else:
                                remote_parent_path = os.path.dirname(new_info.path)
                                # TODO Add modify local_path and local_parent_path if needed
                            # Force remote state update in case of a locked / unlocked event since lock info is not
                            # persisted, so not part of the dirty check
                            force_update = eventId == 'documentLocked' or eventId == 'documentUnlocked'
                            self._dao.update_remote_state(doc_pair, new_info, remote_parent_path=remote_parent_path,
                                                          force_update=force_update)
                            self._force_scan_recursive(doc_pair, consistent_new_info, remote_path=new_info.path,
                                                       force_recursion=(eventId == "securityUpdated"))

                    updated = True
                    refreshed.add(remote_ref)

            if new_info and not updated:
                # Handle new document creations
                created = False
                parent_pairs = self._dao.get_states_from_remote(new_info.parent_uid)
                for parent_pair in parent_pairs:

                    child_pair, new_pair = (self._find_remote_child_match_or_create(parent_pair, new_info))
                    if new_pair:
                        log.debug("Marked doc_pair '%s' as remote creation",
                                  child_pair.remote_name)

                    if child_pair.folderish and new_pair:
                        log.debug('Remote recursive scan of the content of %s',
                                  child_pair.remote_name)
                        remote_path = child_pair.remote_parent_path + "/" + new_info.uid
                        self._force_scan_recursive(child_pair, new_info, remote_path)

                    created = True
                    refreshed.add(remote_ref)
                    break

                if not created:
                    log.debug("Could not match changed document to a bound local folder: %r", new_info)

        # Sort by path the deletion to only mark parent
        sorted_deleted = sorted(delete_queue,
                                key=lambda x: x.local_path, reverse=False)
        delete_processed = []
        for delete_pair in sorted_deleted:
            # Mark as deleted
            skip = False
            for processed in delete_processed:
                path = processed.local_path
                if path[-1] != "/":
                    path = path + "/"
                if delete_pair.local_path.startswith(path):
                    skip = True
                    break
            if skip:
                continue
            # Verify the file is really deleted
            if self._client.get_fs_item(delete_pair.remote_ref) is not None:
                continue
            delete_processed.append(delete_pair)
            log.debug("Marking doc_pair '%r' as deleted", delete_pair)
            self._dao.delete_remote_state(delete_pair)
