'''
Created on 14 janv. 2015

@author: Remi Cattiau
'''
from nxdrive.engine.workers import EngineWorker, ThreadInterrupt, PairInterrupt
from nxdrive.logging_config import get_logger
from nxdrive.client.common import LOCALLY_EDITED_FOLDER_NAME, UNACCESSIBLE_HASH
from nxdrive.client.common import NotFound
from nxdrive.client.common import safe_filename
from nxdrive.engine.activity import Action
from nxdrive.utils import current_milli_time, is_office_temp_file
from PyQt4.QtCore import pyqtSignal
from threading import Lock
import os
log = get_logger(__name__)

WindowsError = None
try:
    from exceptions import WindowsError
except ImportError:
    pass  # this will never be raised under unix


class Processor(EngineWorker):
    '''
    classdocs
    '''
    pairSync = pyqtSignal(object, object)
    path_locks = dict()
    path_locker = Lock()
    soft_locks = dict()
    readonly_locks = dict()
    readonly_locker = Lock()

    def __init__(self, engine, item_getter, name=None):
        '''
        Constructor
        '''
        super(Processor, self).__init__(engine, engine.get_dao(), name=name)
        self._current_item = None
        self._current_doc_pair = None
        self._get_item = item_getter
        self._engine = engine

    def _unlock_soft_path(self, path):
        log.trace("Soft unlocking: %s", path)
        path = path.lower()
        Processor.path_locker.acquire()
        if self._engine.get_uid() not in Processor.soft_locks:
            Processor.soft_locks[self._engine.get_uid()] = dict()
        try:
            del Processor.soft_locks[self._engine.get_uid()][path]
        except Exception as e:
            log.trace(e)
        finally:
            Processor.path_locker.release()

    def _unlock_readonly(self, local_client, path):
        # dict[path]=(count, lock)
        Processor.readonly_locker.acquire()
        if self._engine.get_uid() not in Processor.readonly_locks:
            Processor.readonly_locks[self._engine.get_uid()] = dict()
        try:
            if path in Processor.readonly_locks[self._engine.get_uid()]:
                log.trace("readonly unlock: increase count on %s", path)
                Processor.readonly_locks[self._engine.get_uid()][path][0] = Processor.readonly_locks[self._engine.get_uid()][path][0] + 1
            else:
                lock = local_client.unlock_ref(path)
                log.trace("readonly unlock: unlock on %s with %d", path, lock)
                Processor.readonly_locks[self._engine.get_uid()][path] = [1, lock]
        finally:
            Processor.readonly_locker.release()

    def _lock_readonly(self, local_client, path):
        Processor.readonly_locker.acquire()
        if self._engine.get_uid() not in Processor.readonly_locks:
            Processor.readonly_locks[self._engine.get_uid()] = dict()
        try:
            if path not in Processor.readonly_locks[self._engine.get_uid()]:
                log.debug("readonly lock: can't find reference on %s", path)
                return
            Processor.readonly_locks[self._engine.get_uid()][path][0] = Processor.readonly_locks[self._engine.get_uid()][path][0] - 1
            log.trace("readonly lock: update lock count on %s to %d", path, Processor.readonly_locks[self._engine.get_uid()][path][0])
            if Processor.readonly_locks[self._engine.get_uid()][path][0] <= 0:
                local_client.lock_ref(path, Processor.readonly_locks[self._engine.get_uid()][path][1])
                log.trace("readonly lock: relocked path: %s with %d", path, Processor.readonly_locks[self._engine.get_uid()][path][1])
                del Processor.readonly_locks[self._engine.get_uid()][path]
        finally:
            Processor.readonly_locker.release()

    def _lock_soft_path(self, path):
        log.trace("Soft locking: %s", path)
        path = path.lower()
        Processor.path_locker.acquire()
        if self._engine.get_uid() not in Processor.soft_locks:
            Processor.soft_locks[self._engine.get_uid()] = dict()
        try:
            if path in Processor.soft_locks[self._engine.get_uid()]:
                raise PairInterrupt
            else:
                Processor.soft_locks[self._engine.get_uid()][path] = True
                return path
        finally:
            Processor.path_locker.release()
        return None

    def _lock_path(self, path):
        log.trace("Get lock for '%s'", path)
        lock = None
        Processor.path_locker.acquire()
        if self._engine.get_uid() not in Processor.path_locks:
            Processor.path_locks[self._engine.get_uid()] = dict()
        try:
            if path in Processor.path_locks[self._engine.get_uid()]:
                lock = Processor.path_locks[self._engine.get_uid()][path]
            else:
                lock = Lock()
        finally:
            Processor.path_locker.release()
        log.trace("Locking '%s'", path)
        lock.acquire()
        Processor.path_locks[self._engine.get_uid()][path] = lock

    def _unlock_path(self, path):
        log.trace("Unlocking '%s'", path)
        Processor.path_locker.acquire()
        if self._engine.get_uid() not in Processor.path_locks:
            Processor.path_locks[self._engine.get_uid()] = dict()
        try:
            if path in Processor.path_locks[self._engine.get_uid()]:
                Processor.path_locks[self._engine.get_uid()][path].release()
                del Processor.path_locks[self._engine.get_uid()][path]
        finally:
            Processor.path_locker.release()

    def _clean(self, reason, e=None):
        super(Processor, self)._clean(reason, e)
        if reason == 'exception':
            # Add it back to the queue ? Add the error delay
            if self._current_doc_pair is not None:
                self.increase_error(self._current_doc_pair, "EXCEPTION", exception=e)

    def _execute(self):
        self._current_metrics = dict()
        self._current_item = self._get_item()
        soft_lock = None
        while (self._current_item != None):
            # Take client every time as it is cached in engine
            local_client = self._engine.get_local_client()
            remote_client = self._engine.get_remote_client()
            doc_pair = None
            try:
                doc_pair = self._dao.acquire_state(self._thread_id, self._current_item.id)
            except:
                log.trace("Cannot acquire state for: %r", self._current_item)
                self._engine.get_queue_manager().push(self._current_item)
                self._current_item = self._get_item()
                continue
            try:
                if doc_pair is None:
                    log.trace("Didn't acquire state, dropping %r", self._current_item)
                    self._current_item = self._get_item()
                    continue
                log.debug('Executing processor on %r(%d)', doc_pair, doc_pair.version)
                self._current_doc_pair = doc_pair
                self._current_temp_file = None
                if (doc_pair.pair_state == 'synchronized'
                    or doc_pair.pair_state == 'unsynchronized'
                    or doc_pair.pair_state is None
                    or doc_pair.pair_state.startswith('parent_')):
                    log.trace("Skip as pair is in non-processable state: %r", doc_pair)
                    self._current_item = self._get_item()
                    if doc_pair.pair_state == 'synchronized':
                        self._handle_readonly(local_client, doc_pair)
                    continue
                # TODO Update as the server dont take hash to avoid conflict yet
                if (doc_pair.pair_state.startswith("locally")
                        and doc_pair.remote_ref is not None):
                    try:
                        remote_info = remote_client.get_info(doc_pair.remote_ref)
                        if remote_info.digest != doc_pair.remote_digest:
                            doc_pair.remote_state = 'modified'
                        self._refresh_remote(doc_pair, remote_client, remote_info)
                        # Can run into conflict
                        if doc_pair.pair_state == 'conflicted':
                            self._current_item = self._get_item()
                            continue
                        doc_pair = self._dao.get_state_from_id(doc_pair.id)
                        if doc_pair is None:
                            self._current_item = self._get_item()
                            continue
                    except NotFound:
                        doc_pair.remote_ref = None
                parent_path = doc_pair.local_parent_path
                if (parent_path == ''):
                    parent_path = "/"
                if not local_client.exists(parent_path):
                    if doc_pair.pair_state == "remotely_deleted":
                        self._dao.remove_state(doc_pair)
                        continue
                    self._handle_no_parent(doc_pair, local_client, remote_client)
                    self._current_item = self._get_item()
                    continue
                self._current_metrics = dict()
                handler_name = '_synchronize_' + doc_pair.pair_state
                self._action = Action(handler_name)
                sync_handler = getattr(self, handler_name, None)
                if sync_handler is None:
                    log.debug("Unhandled pair_state: %r for %r",
                                       doc_pair.pair_state, doc_pair)
                    self.increase_error(doc_pair, "ILLEGAL_STATE")
                    self._current_item = self._get_item()
                    continue
                else:
                    self._current_metrics = dict()
                    self._current_metrics["handler"] = doc_pair.pair_state
                    self._current_metrics["start_time"] = current_milli_time()
                    log.trace("Calling %s on doc pair %r", sync_handler, doc_pair)
                    try:
                        soft_lock = self._lock_soft_path(doc_pair.local_path)
                        sync_handler(doc_pair, local_client, remote_client)
                        self._current_metrics["end_time"] = current_milli_time()
                        self.pairSync.emit(doc_pair, self._current_metrics)
                        # TO_REVIEW May have a call to reset_error
                        log.trace("Finish %s on doc pair %r", sync_handler, doc_pair)
                    except ThreadInterrupt:
                        raise
                    except PairInterrupt:
                        from time import sleep
                        # Wait one second to avoid retrying to quickly
                        self._current_doc_pair = None
                        log.debug("PairInterrupt wait 1s and requeue on %r", doc_pair)
                        sleep(1)
                        self._engine.get_queue_manager().push(doc_pair)
                        continue
                    except Exception as e:
                        log.exception(e)
                        self.increase_error(doc_pair, "SYNC HANDLER: %s" % handler_name, exception=e)
                        self._current_item = self._get_item()
                        continue
            except ThreadInterrupt:
                self._engine.get_queue_manager().push(doc_pair)
                raise
            except Exception as e:
                log.exception(e)
                self.increase_error(doc_pair, "EXCEPTION", exception=e)
                raise e
            finally:
                if soft_lock is not None:
                    self._unlock_soft_path(soft_lock)
                self._dao.release_state(self._thread_id)
            self._interact()
            self._current_item = self._get_item()

    def _synchronize_conflicted(self, doc_pair, local_client, remote_client):
        # Auto-resolve conflict
        if not doc_pair.folderish:
            if local_client.is_equal_digests(doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path):
                log.debug("Auto-resolve conflict has digest are the same")
                self._dao.synchronize_state(doc_pair)
        elif local_client.get_remote_id(doc_pair.local_path) == doc_pair.remote_ref:
            log.debug("Auto-resolve conflict has folder has same remote_id")
            self._dao.synchronize_state(doc_pair)

    def _handle_no_parent(self, doc_pair, local_client, remote_client):
        log.trace("Republish as parent doesn't exist : %r", doc_pair)
        parent_pair = self._dao.get_normal_state_from_remote(doc_pair.remote_parent_ref)
        if parent_pair is not None and not doc_pair.local_parent_path == parent_pair.local_path:
            # Need to update the pair
            self._dao.update_local_parent_path(doc_pair, doc_pair.local_name, parent_pair.local_path)
            # Retry with updated path
            raise PairInterrupt
        self.increase_error(doc_pair, "NO_PARENT")

    def _update_speed_metrics(self):
        action = Action.get_last_file_action()
        if action:
            duration = action.end_time - action.start_time
            # Too fast for clock resolution
            if duration <= 0:
                return
            speed = (action.size / duration) * 1000
            log.trace("Transfer speed %d ko/s", speed / 1024)
            self._current_metrics["speed"] = speed

    def _synchronize_if_not_remotely_dirty(self, doc_pair, local_client, remote_client, remote_info=None):
            if remote_info is not None and (remote_info.name != doc_pair.local_name
                                            or remote_info.digest != doc_pair.local_digest):
                doc_pair = self._dao.get_state_from_local(doc_pair.local_path)
                log.debug('Forcing _synchronize_remotely_modified for pair = %r with info = %r', doc_pair, remote_info)
                self._synchronize_remotely_modified(doc_pair, local_client, remote_client)
            else:
                self._dao.synchronize_state(doc_pair)

    def _synchronize_locally_modified(self, doc_pair, local_client, remote_client):
        fs_item_info = None
        if doc_pair.local_digest == UNACCESSIBLE_HASH:
            # Try to update
            info = local_client.get_info(doc_pair.local_path)
            log.trace("Modification of postponed local file: %r", doc_pair)
            doc_pair.local_digest = info.get_digest()
            if doc_pair.local_digest == UNACCESSIBLE_HASH:
                self._postpone_pair(doc_pair, 'Unaccessible hash')
                return
            self._dao.update_local_state(doc_pair, info, versionned=False, queue=False)
        if not local_client.is_equal_digests(doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path):
            if doc_pair.remote_can_update:
                if doc_pair.local_digest == UNACCESSIBLE_HASH:
                    self._postpone_pair(doc_pair, 'Unaccessible hash')
                    return
                log.debug("Updating remote document '%s'.",
                          doc_pair.local_name)
                fs_item_info = remote_client.stream_update(
                    doc_pair.remote_ref,
                    local_client._abspath(doc_pair.local_path),
                    parent_fs_item_id=doc_pair.remote_parent_ref,
                    filename=doc_pair.remote_name,# Use remote name to avoid rename in case of duplicate
                )
                self._dao.update_last_transfer(doc_pair.id, "upload")
                self._update_speed_metrics()
                self._dao.update_remote_state(doc_pair, fs_item_info, versionned=False)
                # TODO refresh_client
            else:
                log.debug("Skip update of remote document '%s'"\
                             " as it is readonly.",
                          doc_pair.local_name)
                if self._engine.local_rollback():
                    local_client.delete(doc_pair.local_path)
                    self._dao.mark_descendants_remotely_created(doc_pair)
                else:
                    log.debug("Set pair unsynchronized: %r", doc_pair)
                    self._dao.unsynchronize_state(doc_pair)
                    info = remote_client.get_info(doc_pair.remote_ref)
                    if info.lock_owner is None:
                        self._engine.newReadonly.emit(doc_pair.local_name, None)
                    else:
                        self._engine.newLocked.emit(doc_pair.local_name, info.lock_owner, info.lock_created)
                    self._handle_unsynchronized(local_client, doc_pair)
                return
        if fs_item_info is None:
            fs_item_info = remote_client.get_info(doc_pair.remote_ref)
            self._dao.update_remote_state(doc_pair, fs_item_info, versionned=False)
        self._synchronize_if_not_remotely_dirty(doc_pair, local_client, remote_client, remote_info=fs_item_info)

    def _get_normal_state_from_remote_ref(self, ref):
        # TODO Select the only states that is not a collection
        return self._dao.get_normal_state_from_remote(ref)

    def _postpone_pair(self, doc_pair, reason=''):
        # Wait 60s for it
        log.trace("Postpone creation of local file(%s): %r", reason, doc_pair)
        doc_pair.error_count = 1
        self._engine.get_queue_manager().push_error(doc_pair, exception=None)

    def _synchronize_locally_created(self, doc_pair, local_client, remote_client):
        name = os.path.basename(doc_pair.local_path)
        if not doc_pair.folderish and is_office_temp_file(name) and doc_pair.error_count == 0:
            # Might be an Office temp file delay it by 60s
            # Save the error_count to not ignore next time
            self.increase_error(doc_pair, 'Can be Office Temp')
            return
        remote_ref = local_client.get_remote_id(doc_pair.local_path)
        # Find the parent pair to find the ref of the remote folder to
        # create the document
        parent_pair = self._dao.get_state_from_local(doc_pair.local_parent_path)
        log.trace('Entered _synchronize_locally_created, parent_pair = %r', parent_pair)
        if parent_pair is None:
            # Try to get it from xattr
            log.trace("Fallback to xattr")
            if local_client.exists(doc_pair.local_parent_path):
                parent_ref = local_client.get_remote_id(doc_pair.local_parent_path)
                parent_pair = self._get_normal_state_from_remote_ref(parent_ref)
        if parent_pair is None or parent_pair.remote_ref is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            if parent_pair is not None and parent_pair.pair_state == 'unsynchronized':
                self._dao.unsynchronize_state(doc_pair)
                self._handle_unsynchronized(local_client, doc_pair)
                return
            raise ValueError(
                "Parent folder of %s, %s is not bound to a remote folder"
                % (doc_pair.local_path, doc_pair.local_parent_path))

        if remote_ref is not None and '#' in remote_ref:
            # TODO Decide what to do
            log.warn("This document %r has remote_ref %s", doc_pair, remote_ref)
            # Get the remote doc
            # Verify it is not already synced elsewhere ( a missed move ? )
            # If same hash dont do anything and reconcile
            remote_doc_client = self._engine.get_remote_doc_client()
            uid = remote_ref.split('#')[-1]
            info = remote_doc_client.get_info(uid, raise_if_missing=False, use_trash=False)
            if info:
                if info.state == 'deleted':
                    log.debug("Untrash from the client: %r", doc_pair)
                    remote_parent_path = parent_pair.remote_parent_path + '/' + parent_pair.remote_ref
                    remote_doc_client.undelete(uid)
                    fs_item_info = remote_client.get_info(remote_ref)
                    if not fs_item_info.path.startswith(remote_parent_path):
                        fs_item_info = remote_client.move(fs_item_info.uid, parent_pair.remote_ref)
                    self._dao.update_remote_state(doc_pair, fs_item_info, remote_parent_path=remote_parent_path,
                                                  versionned=False)
                    self._synchronize_if_not_remotely_dirty(doc_pair, local_client, remote_client, remote_info=fs_item_info)
                    return
                # Document exists on the server
                if info.parent_uid == parent_pair.remote_ref:
                    log.warning("Document is already on the server should not create: %r | %r", doc_pair, info)
                    self._dao.synchronize_state(doc_pair)
                    return

        parent_ref = parent_pair.remote_ref
        if parent_pair.remote_can_create_child:
            fs_item_info = None
            remote_parent_path = parent_pair.remote_parent_path + '/' + parent_pair.remote_ref
            if doc_pair.folderish:
                log.debug("Creating remote folder '%s' in folder '%s'",
                          name, parent_pair.remote_name)
                fs_item_info = remote_client.make_folder(parent_ref, name)
                remote_ref = fs_item_info.uid
            else:
                # TODO Check if the file is already on the server with the good digest
                log.debug("Creating remote document '%s' in folder '%s'",
                          name, parent_pair.remote_name)
                info = local_client.get_info(doc_pair.local_path)
                if info.size != doc_pair.size:
                    # Size has changed ( copy must still be running )
                    doc_pair.local_digest = UNACCESSIBLE_HASH
                    self._dao.update_local_state(doc_pair, info, versionned=False, queue=False)
                    self._postpone_pair(doc_pair, 'Unaccessible hash')
                    return
                if doc_pair.local_digest == UNACCESSIBLE_HASH:
                    doc_pair.local_digest = info.get_digest()
                    log.trace("Creation of postponed local file: %r", doc_pair)
                    self._dao.update_local_state(doc_pair, info, versionned=False, queue=False)
                    if doc_pair.local_digest == UNACCESSIBLE_HASH:
                        self._postpone_pair(doc_pair, 'Unaccessible hash')
                        return
                fs_item_info = remote_client.stream_file(
                    parent_ref, local_client._abspath(doc_pair.local_path), filename=name)
                remote_ref = fs_item_info.uid
                self._dao.update_last_transfer(doc_pair.id, "upload")
                self._update_speed_metrics()
            self._dao.update_remote_state(doc_pair, fs_item_info, remote_parent_path=remote_parent_path,
                                          versionned=False)
            log.trace("Put remote_ref in %s", remote_ref)
            try:
                local_client.set_remote_id(doc_pair.local_path, remote_ref)
            except (NotFound, IOError, OSError):
                new_pair = self._dao.get_state_from_id(doc_pair.id)
                # File has been moved during creation
                if new_pair.local_path != doc_pair.local_path:
                    local_client.set_remote_id(new_pair.local_path, remote_ref)
                    self._synchronize_locally_moved(new_pair, local_client, remote_client, update=False)
                    return
            self._synchronize_if_not_remotely_dirty(doc_pair, local_client, remote_client, remote_info=fs_item_info)
        else:
            child_type = 'folder' if doc_pair.folderish else 'file'
            log.warning("Won't synchronize %s '%s' created in"
                        " local folder '%s' since it is readonly",
                child_type, doc_pair.local_name, parent_pair.local_name)
            if doc_pair.folderish:
                doc_pair.remote_can_create_child = False
            if self._engine.local_rollback():
                local_client.delete(doc_pair.local_path)
                self._dao.remove_state(doc_pair)
            else:
                log.debug("Set pair unsynchronized: %r", doc_pair)
                self._dao.unsynchronize_state(doc_pair)
                self._engine.newReadonly.emit(doc_pair.local_name, parent_pair.remote_name)
                self._handle_unsynchronized(local_client, doc_pair)

    def _synchronize_locally_deleted(self, doc_pair, local_client, remote_client):
        if doc_pair.remote_ref is not None:
            if doc_pair.remote_can_delete:
                log.debug("Deleting or unregistering remote document"
                          " '%s' (%s)",
                          doc_pair.remote_name, doc_pair.remote_ref)
                if doc_pair.remote_state != 'deleted':
                    remote_client.delete(doc_pair.remote_ref,
                                parent_fs_item_id=doc_pair.remote_parent_ref)
                self._dao.remove_state(doc_pair)
            else:
                log.debug("Marking %s as remotely created since remote"
                          " document '%s' (%s) can not be deleted: either"
                          " it is readonly or it is a virtual folder that"
                          " doesn't exist in the server hierarchy",
                          doc_pair, doc_pair.remote_name, doc_pair.remote_ref)
                if doc_pair.remote_state != 'deleted':
                    self._dao.mark_descendants_remotely_created(doc_pair)
        else:
            self._dao.remove_state(doc_pair)

    def _synchronize_locally_moved_remotely_modified(self, doc_pair, local_client, remote_client):
        self._synchronize_locally_moved(doc_pair, local_client, remote_client, update=False)
        self._synchronize_remotely_modified(doc_pair, local_client, remote_client)

    def _synchronize_locally_moved_created(self, doc_pair, local_client, remote_client):
        doc_pair.remote_ref = None
        self._synchronize_locally_created(doc_pair, local_client, remote_client)

    def _synchronize_locally_moved(self, doc_pair, local_client, remote_client, update=True):
        # A file has been moved locally, and an error occurs when tried to
        # move on the server
        remote_info = None
        renamed = False
        moved = False
        if doc_pair.local_name != doc_pair.remote_name:
            try:
                if doc_pair.remote_can_rename:
                    log.debug('Renaming remote document according to local : %r',
                                                        doc_pair)
                    remote_info = remote_client.rename(doc_pair.remote_ref,
                                                            doc_pair.local_name)
                    renamed = True
                    self._refresh_remote(doc_pair, remote_client, remote_info=remote_info)
                else:
                    self._handle_failed_remote_rename(doc_pair, doc_pair)
                    return
            except Exception as e:
                log.debug(e)
                self._handle_failed_remote_rename(doc_pair, doc_pair)
                return
        parent_pair = None
        parent_ref = local_client.get_remote_id(doc_pair.local_parent_path)
        if parent_ref is None:
            parent_pair = self._dao.get_state_from_local(doc_pair.local_parent_path)
            parent_ref = parent_pair.remote_ref
        else:
            parent_pair = self._get_normal_state_from_remote_ref(parent_ref)
        if parent_pair is None:
            raise Exception("Should have a parent pair")
        if parent_ref != doc_pair.remote_parent_ref:
            if doc_pair.remote_can_delete and not parent_pair.pair_state == "unsynchronized":
                log.debug('Moving remote file according to local : %r', doc_pair)
                # Bug if move in a parent with no rights / partial move
                # if rename at the same time
                parent_path = parent_pair.remote_parent_path + "/" + parent_pair.remote_ref
                remote_info = remote_client.move(doc_pair.remote_ref,
                            parent_pair.remote_ref)
                moved = True
                self._dao.update_remote_state(doc_pair, remote_info, remote_parent_path=parent_path, versionned=False)
            else:
                # Move it back
                self._handle_failed_remote_move(doc_pair, doc_pair)
        # Handle modification at the same time if needed
        if update:
            if doc_pair.local_state == 'moved':
                self._synchronize_if_not_remotely_dirty(doc_pair, local_client, remote_client, remote_info=remote_info)
            else:
                self._synchronize_locally_modified(doc_pair, local_client, remote_client)

    def _synchronize_deleted_unknown(self, doc_pair, local_client, remote_client):
        # Somehow a pair can get to an inconsistent state:
        # <local_state=u'deleted', remote_state=u'unknown',
        # pair_state=u'unknown'>
        # Even though we are not able to figure out how this can happen we
        # need to handle this case to put the database back to a consistent
        # state.
        # This is tracked by https://jira.nuxeo.com/browse/NXP-14039
        log.debug("Inconsistency should not happens anymore")
        log.debug("Detected inconsistent doc pair %r, deleting it hoping the"
                  " synchronizer will fix this case at next iteration",
                  doc_pair)
        self._dao.remove_state(doc_pair)

    def _get_temporary_file(self, file_path):
        from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_PREFIX
        from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_SUFFIX
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        file_out = os.path.join(file_dir, DOWNLOAD_TMP_FILE_PREFIX + file_name
                                + DOWNLOAD_TMP_FILE_SUFFIX)
        return file_out

    def _download_content(self, local_client, remote_client, doc_pair, file_path):
        # Check if the file is already on the HD
        pair = self._dao.get_valid_duplicate_file(doc_pair.remote_digest)
        if pair:
            import shutil
            file_out = self._get_temporary_file(file_path)
            locker = local_client.unlock_path(file_out)
            try:
                shutil.copy(local_client._abspath(pair.local_path), file_out)
            finally:
                local_client.lock_path(file_out, locker)
            return file_out
        tmp_file = remote_client.stream_content(
                                doc_pair.remote_ref, file_path,
                                parent_fs_item_id=doc_pair.remote_parent_ref)
        self._update_speed_metrics()
        return tmp_file

    def _update_remotely(self, doc_pair, local_client, remote_client, is_renaming):
        os_path = local_client._abspath(doc_pair.local_path)
        if is_renaming:
            new_os_path = os.path.join(os.path.dirname(os_path), safe_filename(doc_pair.remote_name))
            log.debug("Replacing local file '%s' by '%s'.", os_path, new_os_path)
        else:
            new_os_path = os_path
        log.debug("Updating content of local file '%s'.", os_path)
        self.tmp_file = self._download_content(local_client, remote_client, doc_pair, new_os_path)
        # Delete original file and rename tmp file
        remote_id = local_client.get_remote_id(doc_pair.local_path)
        local_client.delete_final(doc_pair.local_path)
        if remote_id is not None:
            local_client.set_remote_id(local_client.get_path(self.tmp_file), doc_pair.remote_ref)
        updated_info = local_client.rename(local_client.get_path(self.tmp_file), doc_pair.remote_name)
        doc_pair.local_digest = updated_info.get_digest()
        self._dao.update_last_transfer(doc_pair.id, "download")
        self._refresh_local_state(doc_pair, updated_info)

    def _synchronize_remotely_modified(self, doc_pair, local_client, remote_client):
        self.tmp_file = None
        try:
            is_renaming = safe_filename(doc_pair.remote_name) != doc_pair.local_name
            if (not local_client.is_equal_digests(doc_pair.local_digest, doc_pair.remote_digest, doc_pair.local_path)
                    and doc_pair.local_digest is not None):
                self._update_remotely(doc_pair, local_client, remote_client, is_renaming)
            else:
                # digest agree so this might be a renaming and/or a move,
                # and no need to transfer additional bytes over the network
                is_move, new_parent_pair = self._is_remote_move(doc_pair)
                if remote_client.is_filtered(doc_pair.remote_parent_path):
                    # A move to a filtered parent ( treat it as deletion )
                    self._synchronize_remotely_deleted(doc_pair, local_client, remote_client)
                    return
                if not is_move and not is_renaming:
                    log.debug("No local impact of metadata update on"
                              " document '%s'.", doc_pair.remote_name)
                else:
                    file_or_folder = 'folder' if doc_pair.folderish else 'file'
                    if (is_move or is_renaming) and doc_pair.folderish:
                        self._engine.set_local_folder_lock(doc_pair.local_path)
                    if is_move:
                        # move and potential rename
                        moved_name = doc_pair.remote_name if is_renaming else doc_pair.local_name
                        # NXDRIVE-471: log
                        old_path = doc_pair.local_path
                        new_path = new_parent_pair.local_path + '/' + moved_name
                        if old_path == new_path:
                            log.debug("WRONG GUESS FOR MOVE: %r", doc_pair)
                            self._is_remote_move(doc_pair, debug=True)
                            self._dao.synchronize_state(doc_pair)
                        log.debug("DOC_PAIR(%r): old_path[%d][%r]: %s, new_path[%d][%r]: %s",
                            doc_pair, local_client.exists(old_path), local_client.get_remote_id(old_path), old_path,
                            local_client.exists(new_path), local_client.get_remote_id(new_path), new_path)
                        ## end of add log
                        log.debug("Moving local %s '%s' to '%s'.",
                            file_or_folder, local_client._abspath(doc_pair.local_path),
                            local_client._abspath(new_parent_pair.local_path + '/' + moved_name))
                        # May need to add a lock for move
                        updated_info = local_client.move(doc_pair.local_path,
                                          new_parent_pair.local_path, name=moved_name)
                        new_parent_path = new_parent_pair.remote_parent_path + "/" + new_parent_pair.remote_ref
                        self._dao.update_remote_parent_path(doc_pair, new_parent_path)
                    elif is_renaming:
                        # renaming
                        log.debug("Renaming local %s '%s' to '%s'.",
                            file_or_folder, local_client._abspath(doc_pair.local_path),
                            doc_pair.remote_name)
                        updated_info = local_client.rename(
                            doc_pair.local_path, doc_pair.remote_name)
                    if is_move or is_renaming:
                        # Should call a DAO method
                        new_path = os.path.dirname(updated_info.path)
                        self._dao.update_local_parent_path(doc_pair, os.path.basename(updated_info.path), new_path)
                        self._refresh_local_state(doc_pair, updated_info)
            self._handle_readonly(local_client, doc_pair)
            self._dao.synchronize_state(doc_pair)
        except (IOError, WindowsError) as e:
            log.warning(
                "Delaying local update of remotely modified content %r due to"
                " concurrent file access (probably opened by another"
                " process).",
                doc_pair)
            raise e
        finally:
            if self.tmp_file is not None:
                try:
                    if os.path.exists(self.tmp_file):
                        os.remove(self.tmp_file)
                except (IOError, WindowsError):
                    pass
            if doc_pair.folderish:
                # Release folder lock in any case
                self._engine.release_folder_lock()

    def _synchronize_remotely_created(self, doc_pair, local_client, remote_client):
        name = doc_pair.remote_name
        # Find the parent pair to find the path of the local folder to
        # create the document into
        parent_pair = self._get_normal_state_from_remote_ref(doc_pair.remote_parent_ref)
        if parent_pair is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ValueError(
                "Could not find parent folder of doc %r (%r)"
                " folder" % (name, doc_pair.remote_ref))
        if parent_pair.local_path is None:
            if parent_pair.pair_state == 'unsynchronized':
                self._dao.unsynchronize_state(doc_pair)
                self._handle_unsynchronized(local_client, doc_pair)
                return
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ValueError(
                "Parent folder of doc %r (%r) is not bound to a local"
                " folder" % (name, doc_pair.remote_ref))
        path = doc_pair.remote_parent_path + '/' + doc_pair.remote_ref
        if remote_client.is_filtered(path):
            # It is filtered so skip and remove from the LastKnownState
            self._dao.remove_state(doc_pair)
            return
        if not local_client.exists(doc_pair.local_path):
            path = self._create_remotely(local_client, remote_client, doc_pair, parent_pair, name)
        else:
            path = doc_pair.local_path
            remote_ref = local_client.get_remote_id(doc_pair.local_path)
            if remote_ref is not None and remote_ref == doc_pair.remote_ref:
                log.debug('remote_ref (xattr) = %s, doc_pair.remote_ref = %s => setting conflicted state', remote_ref,
                          doc_pair.remote_ref)
                # Set conflict state for now
                # TO_REVIEW May need to overwrite
                self._dao.set_conflict_state(doc_pair)
                return
            elif remote_ref is not None:
                # Case of several documents with same name or case insensitive hard drive
                # TODO dedup
                path = self._create_remotely(local_client, remote_client, doc_pair, parent_pair, name)
        local_client.set_remote_id(path, doc_pair.remote_ref)
        if path != doc_pair.local_path and doc_pair.folderish:
            # Update childs
            self._dao.update_local_parent_path(doc_pair, os.path.basename(path), os.path.dirname(path))
        self._refresh_local_state(doc_pair, local_client.get_info(path))
        self._handle_readonly(local_client, doc_pair)
        if not self._dao.synchronize_state(doc_pair):
            log.debug("Pair is not in synchronized state (version issue): %r", doc_pair)
            # Need to check if this is a remote or local change
            new_pair = self._dao.get_state_from_id(doc_pair.id)
            # Only local 'moved' change that can happen on a pair with processor
            if new_pair.local_state == 'moved':
                self._synchronize_locally_moved(new_pair, local_client, remote_client, update=False)
            else:
                if new_pair.remote_state == 'deleted':
                    self._synchronize_remotely_deleted(new_pair, local_client, remote_client)
                else:
                    self._synchronize_remotely_modified(new_pair, local_client, remote_client)

    def _create_remotely(self, local_client, remote_client, doc_pair, parent_pair, name):
        local_parent_path = parent_pair.local_path
        # TODO Shared this locking system / Can have concurrent lock
        self._unlock_readonly(local_client, local_parent_path)
        tmp_file = None
        try:
            if doc_pair.folderish:
                log.debug("Creating local folder '%s' in '%s'", name,
                          local_client._abspath(parent_pair.local_path))
                path = local_client.make_folder(local_parent_path, name)
            else:
                path, os_path, name = local_client.get_new_file(local_parent_path,
                                                                name)
                log.debug("Creating local file '%s' in '%s'", name,
                          local_client._abspath(parent_pair.local_path))
                tmp_file = self._download_content(local_client, remote_client, doc_pair, os_path)
                tmp_file_path = local_client.get_path(tmp_file)
                # Set remote id on tmp file already
                local_client.set_remote_id(tmp_file_path, doc_pair.remote_ref)
                # Rename tmp file
                local_client.rename(tmp_file_path, name)
                self._dao.update_last_transfer(doc_pair.id, "download")
        finally:
            self._lock_readonly(local_client, local_parent_path)
            # Clean .nxpart if needed
            if tmp_file is not None and os.path.exists(tmp_file):
                os.remove(tmp_file)
        return path

    def _synchronize_remotely_deleted(self, doc_pair, local_client, remote_client):
        try:
            if doc_pair.local_state != 'deleted':
                log.debug("Deleting locally %s", local_client._abspath(doc_pair.local_path))
                if doc_pair.folderish:
                    self._engine.set_local_folder_lock(doc_pair.local_path)
                else:
                    # Check for nxpart to clean up
                    file_out = self._get_temporary_file(local_client._abspath(doc_pair.local_path))
                    if os.path.exists(file_out):
                        os.remove(file_out)
                if self._engine.use_trash():
                    local_client.delete(doc_pair.local_path)
                else:
                    local_client.delete_final(doc_pair.local_path)
            self._dao.remove_state(doc_pair)
        except (IOError, WindowsError) as e:
            # Under Windows deletion can be impossible while another
            # process is accessing the same file (e.g. word processor)
            # TODO: be more specific as detecting this case:
            # shall we restrict to the case e.errno == 13 ?
            log.warning(
                "Delaying local deletion of remotely deleted item %r due to"
                " concurrent file access (probably opened by another"
                " process).", doc_pair)
            raise e
        finally:
            if doc_pair.folderish:
                self._engine.release_folder_lock()

    def _synchronize_unknown_deleted(self, doc_pair, local_client, remote_client):
        # Somehow a pair can get to an inconsistent state:
        # <local_state=u'unknown', remote_state=u'deleted',
        # pair_state=u'unknown'>
        # Even though we are not able to figure out how this can happen we
        # need to handle this case to put the database back to a consistent
        # state.
        # This is tracked by https://jira.nuxeo.com/browse/NXP-13216
        log.debug("Inconsistency should not happens anymore")
        log.debug("Detected inconsistent doc pair %r, deleting it hoping the"
                  " synchronizer will fix this case at next iteration",
                  doc_pair)
        self._dao.remove_state(doc_pair)
        if doc_pair.local_path is not None:
            log.debug("Since the local path is not None: %s, the synchronizer"
                      " will probably consider this as a local creation at"
                      " next iteration and create the file or folder remotely",
                      doc_pair.local_path)
        else:
            log.debug("Since the local path is None the synchronizer will"
                      " probably do nothing at next iteration")

    def _refresh_remote(self, doc_pair, remote_client, remote_info=None):
        if remote_info is None:
            remote_info = None  # Get from remote_client
            remote_info = remote_client.get_info(doc_pair.remote_ref)
        self._dao.update_remote_state(doc_pair, remote_info, versionned=False, queue=False)

    def _refresh_local_state(self, doc_pair, local_info):
        if doc_pair.local_digest is None and not doc_pair.folderish:
            doc_pair.local_digest = local_info.get_digest()
        self._dao.update_local_state(doc_pair, local_info, versionned=False, queue=False)
        doc_pair.local_path = local_info.path
        doc_pair.local_name = os.path.basename(local_info.path)
        doc_pair.last_local_updated = local_info.last_modification_time

    def _is_remote_move(self, doc_pair, debug=False):
        local_parent_pair = self._dao.get_state_from_local(doc_pair.local_parent_path)
        remote_parent_pair = self._get_normal_state_from_remote_ref(doc_pair.remote_parent_ref)
        if debug:
            log.debug("is_remote_move: local:%r remote:%r", local_parent_pair, remote_parent_pair)
        return (local_parent_pair is not None
                and remote_parent_pair is not None
                and local_parent_pair.id != remote_parent_pair.id,
                remote_parent_pair)

    def _handle_failed_remote_move(self, source_pair, target_pair):
        pass

    def _handle_failed_remote_rename(self, source_pair, target_pair):
        # An error occurs return false
        log.error("Renaming from %s to %s canceled",
                            target_pair.remote_name, target_pair.local_name)
        if self._engine.local_rollback():
            try:
                local_client = self._engine.get_local_client()
                info = local_client.rename(target_pair.local_path,
                                            target_pair.remote_name)
                self._dao.update_local_state(source_pair, info, queue=False)
                if source_pair != target_pair:
                    if target_pair.folderish:
                        # Remove "new" created tree
                        pairs = self._dao.get_states_from_partial_local(
                                target_pair.local_path).all()
                        for pair in pairs:
                            self._dao.remove_state(pair)
                        pairs = self._dao.get_states_from_partial_local(
                                source_pair.local_path).all()
                        for pair in pairs:
                            self._dao.synchronize_state(pair)
                    else:
                        self._dao.remove_state(target_pair)
                    # Mark all local as unknown
                    #self._mark_unknown_local_recursive(session, source_pair)
                self._dao.synchronize_state(source_pair)
                return True
            except Exception, e:
                log.error("Can't rollback local modification")
                log.debug(e)
        return False

    def _is_locally_edited_folder(self, doc_pair):
        return doc_pair.local_path.endswith(LOCALLY_EDITED_FOLDER_NAME)

    def _handle_unsynchronized(self, local_client, doc_pair):
        # Used for overwrite
        pass

    def _handle_readonly(self, local_client, doc_pair):
        # Don't use readonly on folder for win32 and on Locally Edited
        if (doc_pair.folderish and os.sys.platform == 'win32'
            or self._is_locally_edited_folder(doc_pair)):
            return
        if doc_pair.is_readonly():
            log.debug('Setting %r as readonly', doc_pair.local_path)
            local_client.set_readonly(doc_pair.local_path)
        else:
            log.debug('Unsetting %r as readonly', doc_pair.local_path)
            local_client.unset_readonly(doc_pair.local_path)
