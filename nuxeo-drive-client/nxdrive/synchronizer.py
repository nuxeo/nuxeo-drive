"""Handle synchronization logic."""
import re
import os.path
from time import time
from time import sleep
from datetime import datetime
from threading import Thread
from threading import Condition
import urllib2
import socket
import httplib

from sqlalchemy import or_
from sqlalchemy import and_

from nxdrive.client import DEDUPED_BASENAME_PATTERN
from nxdrive.client import safe_filename
from nxdrive.client import NotFound
from nxdrive.client import Unauthorized
from nxdrive.client.common import COLLECTION_SYNC_ROOT_FACTORY_NAME
from nxdrive.client.common import LOCALLY_EDITED_FOLDER_NAME
from nxdrive.client.remote_file_system_client import RemoteFileInfo
from nxdrive.model import ServerBinding
from nxdrive.activity import Action
from nxdrive.model import LastKnownState
from nxdrive.logging_config import get_logger
from nxdrive.utils import PidLockFile
import sys

WindowsError = None
try:
    from exceptions import WindowsError
except ImportError:
    pass  # this will never be raised under unix

POSSIBLE_NETWORK_ERROR_TYPES = (
    Unauthorized,
    urllib2.URLError,
    urllib2.HTTPError,
    httplib.HTTPException,
    socket.error,
)

UNEXPECTED_HTTP_STATUS = (
    500,
    403
)

log = get_logger(__name__)
conflicted_changes = []


def _log_offline(exception, context):
    if isinstance(exception, urllib2.HTTPError):
        msg = ("Client offline in %s: HTTP error with code %d"
                % (context, exception.code))
    else:
        msg = "Client offline in %s: %s" % (context, exception)
    log.trace(msg)


def name_match(local_name, remote_name):
    """Return true if local_name is a possible match with remote_name"""
    # Nuxeo document titles can have unsafe characters:
    remote_name = safe_filename(remote_name)

    local_base, local_ext = os.path.splitext(local_name)
    remote_base, remote_ext = os.path.splitext(remote_name)
    if remote_ext != local_ext:
        return False

    m = re.match(DEDUPED_BASENAME_PATTERN, local_base)
    if m:
        # The local file name seems to result from a deduplication, let's
        # ignore the increment data and just consider the base local name
        local_base, _ = m.groups()
    return local_base == remote_base


def jaccard_index(set_1, set_2):
    """Compute a normalized overlap similarity between 2 sets

    set_1 must be a set instance. set_2 can be any collection.

    1.0 means perfect identity
    0.0 means that one set is empty and the other is not.

    """
    if len(set_1) == len(set_2) == 0:
        return 1.0
    return float(len(set_1.intersection(set_2))) / len(set_1.union(set_2))


def _local_children_names(doc_pair, session):
    return set([child.local_name
            for child in session.query(LastKnownState).filter_by(
                local_parent_path=doc_pair.local_path).all()])


def rerank_local_rename_or_move_candidates(doc_pair, candidates, session,
                                           check_suspended=None):
    """Find the most suitable rename or move candidate

    If doc_pair is a folder, then the similarity (Jaccard Index) of the
    children names is the most important criterion to reorder the candidates.

    Otherwise, candidates with same name (move) are favored over candidates
    with same parent path (inplace rename) over candidates with no common
    attribute (move + rename at once).

    Folders without any children names overlap are pruned out of the candidate
    list.

    """
    relatednesses = []
    if doc_pair.folderish:
        children_names = _local_children_names(doc_pair, session)

    for c in candidates:

        # Check if synchronization thread was suspended
        if check_suspended is not None:
            check_suspended("Re-rank local rename or move candidates")

        if doc_pair.folderish:
            # Measure the jackard index on direct children names of
            # folders to finger print them
            candidate_children_names = _local_children_names(c, session)
            ji = jaccard_index(children_names, candidate_children_names)
        else:
            ji = 1.0

        if ji == 0.0:
            # prune folder that have no child in common
            continue

        same_name = doc_pair.local_name == c.local_name
        same_parent = doc_pair.local_parent_path == c.local_parent_path
        relatednesses.append(((ji, same_name, same_parent), c))

    relatednesses.sort(reverse=True)
    return [candidate for _, candidate in relatednesses]


def find_first_name_match(name, possible_pairs, check_suspended=None):
    """Select the first pair that can match the provided name"""

    for pair in possible_pairs:

        # Check if synchronization thread was suspended
        if check_suspended is not None:
            check_suspended("Find first name match")

        if pair.local_name is not None and pair.remote_name is not None:
            # This pair already links a non null local and remote resource
            log.warning("Possible pair %r has both local and remote info",
                        pair)
            continue
        if pair.local_name is not None:
            if name_match(pair.local_name, name):
                return pair
        elif pair.remote_name is not None:
            if name_match(name, pair.remote_name):
                return pair
    return None


class SyncThreadStopped(Exception):
    pass


class SyncThreadSuspended(Exception):
    pass


class SynchronizerThread(Thread):
    """Wrapper thread running the synchronization loop"""

    def __init__(self, controller, kwargs=None):
        Thread.__init__(self)
        self.controller = controller
        if kwargs is None:
            kwargs = {}
        self.kwargs = kwargs
        # Lock condition for suspend/resume
        self.suspend_condition = Condition()
        self.suspended = False
        # Lock condition for stop
        self.stop_condition = Condition()
        self.stopped = False

    def run(self):
        # Check sync is running
        lock = PidLockFile(self.controller.config_folder, "sync")
        pid = lock.lock()
        if pid is not None:
            log.warning('Another synchronization thread is running %d', pid)
            return
        shouldRun = True
        while shouldRun:
            # Log uncaught exceptions in the synchronization loop and continue
            try:
                log.debug('Start synchronization thread %r', self)
                self.controller.synchronizer.loop(sync_thread=self,
                                                  **self.kwargs)
                shouldRun = False
            except Exception, e:
                log.error("Error in synchronization thread: %s", e,
                                    exc_info=True)
        self.controller.sync_thread = None
        lock.unlock()

    def stop(self):
        with self.stop_condition:
            log.debug('Marking synchronization thread %r as stopped', self)
            self.stopped = True

    def suspend(self):
        with self.suspend_condition:
            log.debug('Marking synchronization thread %r as suspended', self)
            self.suspended = True

    def resume(self):
        with self.suspend_condition:
            log.debug('Notifying synchronization thread %r', self)
            self.suspended = False
            self.suspend_condition.notify()


class Synchronizer(object):
    """Handle synchronization operations between the client FS and Nuxeo"""

    # Default delay in seconds that ensures that two consecutive scans
    # won't happen too closely from one another.
    # TODO: make this a value returned by the server so that it can tell the
    # client to slow down when the server cannot keep up with the load
    delay = 5

    # Test delay for FS notify
    test_delay = 0

    # Default number of consecutive sync operations to perform
    # without refreshing the internal state DB.
    max_sync_step = 10

    # Limit number of pending items to retrieve when computing the list of
    # operations to perform (useful to display activity stats in the
    # frontend)
    limit_pending = 100

    # Log sync error date and skip document pairs in error while syncing up
    # to a fixed cooldown period
    error_skip_period = 300  # 5 minutes

    # Default page size for deleted items detection query in DB
    default_page_size = 100

    # Application update check delay
    update_check_delay = 3600

    def __init__(self, controller, page_size=None):
        self.current_action = None
        self.local_full_scan = []
        self.local_changes = []
        self.observers = []
        self._controller = controller
        self.previous_time = None
        self._frontend = None
        self.page_size = (page_size if page_size is not None
                          else self.default_page_size)
        self.unhandle_fs_event = False

    def register_frontend(self, frontend):
        self._frontend = frontend

    def get_session(self):
        return self._controller.get_session()

    def _delete_with_descendant_states(self, session, doc_pair, local_client,
        keep_root=False, io_delete=True):
        """Recursive delete the descendants of a deleted doc

        If the file or folder has been modified since its last
        synchronization date, keep it on the file system and mark
        its pair state as 'unsynchronized', else delete it and
        its pair state.
        """

        # Check if synchronization thread was suspended
        self.check_suspended('Delete recursively the descendants of a locally'
                             ' deleted item or a remotely deleted document')

        # Delete first the parent as we use the trash
        # and we want to keep hierarchy
        if self._controller.trash_modified_file() and io_delete:
            local_client.delete(doc_pair.local_path)

        locally_modified = False
        # Handle local and remote descendants first
        if doc_pair.local_path is not None:
            local_children = session.query(LastKnownState).filter_by(
                local_folder=doc_pair.local_folder,
                local_parent_path=doc_pair.local_path).all()
            for child in local_children:
                if self._delete_with_descendant_states(session, child,
                                                       local_client,
                                                       io_delete=io_delete):
                    locally_modified = True

        if doc_pair.remote_ref is not None:
            remote_children = session.query(LastKnownState).filter_by(
                local_folder=doc_pair.local_folder,
                remote_parent_ref=doc_pair.remote_ref).all()
            for child in remote_children:
                if self._delete_with_descendant_states(session, child,
                                                       local_client,
                                                       io_delete=io_delete):
                    locally_modified = True

        if not locally_modified:
            # Compare last local update date and last synchronization date
            # to detect local modification
            log.trace("Handling %s for deletion: last_local_updated = %s,"
                      " last_sync_date = %s",
                    (doc_pair.remote_name if doc_pair.remote_name
                     else doc_pair.local_path),
                    (doc_pair.last_local_updated.strftime('%Y-%m-%d %H:%M:%S')
                     if doc_pair.last_local_updated else 'None'),
                    (doc_pair.last_sync_date.strftime('%Y-%m-%d %H:%M:%S')
                     if doc_pair.last_sync_date else 'None'))
            locally_modified = (doc_pair.last_sync_date is None
                    or doc_pair.last_local_updated and (
                        doc_pair.last_local_updated.replace(microsecond=0) >
                            doc_pair.last_sync_date.replace(microsecond=0)))

        # Handle current pair state in the end
        file_or_folder = 'folder' if doc_pair.folderish else 'file'
        if not locally_modified or self._controller.trash_modified_file():
            # We now use the trash feature so we delete in this case
            if not keep_root:
                # Not modified since last synchronization, delete
                # file/folder and its pair state
                if (doc_pair.local_path is not None
                    and local_client.exists(doc_pair.local_path)):
                    log.debug("Deleting local %s '%s'",
                              file_or_folder, doc_pair.get_local_abspath())
                    if io_delete:
                        local_client.delete(doc_pair.local_path)
                session.delete(doc_pair)
        else:
            log.debug("Marking local %s '%s' as unsynchronized as it has been"
                      " remotely deleted but locally modified"
                      " (keeping local changes)",
                      file_or_folder, doc_pair.local_path
                          if doc_pair.local_path else doc_pair.remote_name)
            # Modified since last synchronization, mark pair state
            # as unsynchronized
            doc_pair.pair_state = 'unsynchronized'
            doc_pair.remote_state = 'unknown'
        return locally_modified

    def _mark_descendant_states_remotely_created(self, session, doc_pair,
        keep_root=None):
        """Mark the descendant states as remotely created"""

        # Check if synchronization thread was suspended
        self.check_suspended('Mark recursively the descendant states of a'
                             ' remotely created document')

        # mark local descendant states first
        if doc_pair.local_path is not None:
            local_children = session.query(LastKnownState).filter_by(
                local_folder=doc_pair.local_folder,
                local_parent_path=doc_pair.local_path).all()
            for child in local_children:
                self._mark_descendant_states_remotely_created(session, child)

        # mark parent folder state in the end
        if not keep_root:
            doc_pair.reset_local()
            doc_pair.update_state('unknown', 'created')

    def _local_rename_with_descendant_states(self, session, client, doc_pair,
        previous_local_path, updated_path):
        """Update the metadata of the descendants of a renamed doc"""

        # Check if synchronization thread was suspended
        self.check_suspended('Update recursively the descendant states of a'
                             ' remotely renamed document')

        # rename local descendants first
        if doc_pair.local_path is None:
            raise ValueError("Cannot apply renaming to %r due to"
                             "missing local path" %
                doc_pair)
        local_children = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder,
            local_parent_path=previous_local_path).all()
        for child in local_children:
            child_path = updated_path + '/' + child.local_name
            self._local_rename_with_descendant_states(session, client, child,
                child.local_path, child_path)
        doc_pair.update_state(local_state='synchronized')
        doc_pair.refresh_local(client=client, local_path=updated_path)

    def _update_remote_parent_path_recursive(self, session, doc_pair,
        updated_path):
        """Update the remote parent path of the descendants of a moved doc"""

        # Check if synchronization thread was suspended
        self.check_suspended('Update recursively the remote parent path of the'
                             ' descendant states of a remotely moved document')

        # update local descendants first
        if doc_pair.remote_ref is None:
            raise ValueError("Cannot apply parent path update to %r "
                             "due to missing remote_ref" % doc_pair)
        local_children = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder,
            remote_parent_ref=doc_pair.remote_ref).all()
        for child in local_children:
            child_path = updated_path + '/' + child.remote_ref
            self._update_remote_parent_path_recursive(session, child,
                child_path)

        doc_pair.remote_parent_path = updated_path

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

    def _mark_deleted_local_recursive(self, session, doc_pair):
        """Update the metadata of the descendants of locally deleted doc"""

        # Check if synchronization thread was suspended
        self.check_suspended('Mark recursively the descendant states of a'
                             ' locally deleted item')

        log.trace("Marking %r as locally deleted", doc_pair.remote_ref)
        # delete descendants first
        children = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder,
            local_parent_path=doc_pair.local_path).all()
        for child in children:
            self._mark_deleted_local_recursive(session, child)

        # update the state of the parent it-self
        if doc_pair.remote_ref is None:
            # Unbound child metadata can be removed
            session.delete(doc_pair)
        else:
            # mark it for remote deletion
            doc_pair.update_local(None)

    def _mark_unknown_local_recursive(self, session, doc_pair):
        """Recursively mark local unsynchronized pair state as 'unknown'"""

        # Check if synchronization thread was suspended
        self.check_suspended("Mark recursively as 'unknown' the descendant"
                             " states of an unsynchronized pair state")

        if doc_pair.local_path is not None:
            # Delete descendants first
            session.query(LastKnownState).filter(
                            and_(LastKnownState.pair_state == "unsynchronized",
                            LastKnownState.local_parent_path.like(
                            doc_pair.local_path + '%'))).update(
                            {'pair_state': 'unknown'},
                            synchronize_session=False)

    def _scan_local_new_file(self, session, child_name, child_info,
                             parent_pair):
        if not child_info.folderish:
            # Try to find an existing remote doc that has not yet been
            # bound to any local file that would align with both name
            # and digest
            try:
                child_digest = child_info.get_digest()
                possible_pairs = session.query(LastKnownState).filter_by(
                        local_folder=parent_pair.local_folder,
                        local_path=None,
                        remote_parent_ref=parent_pair.remote_ref,
                        folderish=child_info.folderish,
                        remote_digest=child_digest,
                    ).all()
                child_pair = find_first_name_match(
                        child_name, possible_pairs, self.check_suspended)
                if child_pair is not None:
                    child_pair.update_state(local_state='created')
                    log.debug("Matched local %s with remote %s "
                                "with digest",
                              child_info.path, child_pair.remote_name)
                    return child_pair
            except (IOError, WindowsError):
                    # The file is currently being accessed and we cannot
                    # compute the digest
                    log.debug("Cannot perform alignment of %r using"
                              " digest info due to concurrent file"
                              " access", child_info.filepath)

            # Previous attempt has failed: relax the digest constraint
        possible_pairs = session.query(LastKnownState).filter_by(
            local_folder=parent_pair.local_folder,
            local_path=None,
            remote_parent_ref=parent_pair.remote_ref,
            folderish=child_info.folderish,
        ).all()
        child_pair = find_first_name_match(child_name, possible_pairs,
                                                       self.check_suspended)
        if child_pair is not None:
            log.debug("Matched local %s with remote %s by name only",
                                child_info.path, child_pair.remote_name)
            child_pair.update_state(local_state='created')
            return child_pair

        # Could not find any pair state to align to, create one
        # XXX Should be tagged as locally created
        child_pair = LastKnownState(parent_pair.local_folder,
                local_info=child_info)
        session.add(child_pair)
        log.debug("Detected a new non-alignable local file at %s",
                          child_pair.local_path)
        return child_pair

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
            self._scan_local_recursive(session, client, child_pair,
                                       child_info)

        for deleted in children.values():
            self._mark_deleted_local_recursive(session, deleted)

    def scan_remote(self, server_binding_or_local_path, from_state=None,
                    session=None):
        """Recursively scan the bound remote folder looking for updates"""
        if session is None:
            session = self.get_session()

        if isinstance(server_binding_or_local_path, basestring):
            local_path = server_binding_or_local_path
            state = self._controller.get_state_for_local_path(local_path)
            server_binding = state.server_binding
            from_state = state
        else:
            server_binding = server_binding_or_local_path

        # This operation is likely to be long, let's notify the user that
        # update is ongoing
        self._notify_refreshing(server_binding)

        if from_state is None:
            from_state = session.query(LastKnownState).filter_by(
                local_path='/', local_folder=server_binding.local_folder).one()

        try:
            client = self.get_remote_fs_client(from_state.server_binding)
            remote_info = client.get_info(from_state.remote_ref)
        except NotFound:
            log.debug("Marking %r as remotely deleted.", from_state)
            from_state.update_remote(None)
            session.commit()
            return

        # recursive update
        self._scan_remote_recursive(session, client, from_state, remote_info)
        session.commit()

    def _mark_deleted_remote_recursive(self, session, doc_pair):
        """Update the metadata of the descendants of remotely deleted doc"""

        # Check if synchronization thread was suspended
        self.check_suspended('Mark recursively the descendant states of a'
                             ' remotely deleted document')

        # delete descendants first
        children = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder,
            remote_parent_ref=doc_pair.remote_ref).all()
        for child in children:
            self._mark_deleted_remote_recursive(session, child)

        # update the state of the parent it-self
        if doc_pair.local_path is None:
            # Unbound child metadata can be removed
            session.delete(doc_pair)
        else:
            # schedule it for local deletion
            doc_pair.update_remote(None)

    def _scan_remote_recursive(self, session, client, doc_pair, remote_info,
        force_recursion=True, mark_unknown=True):
        """Recursively scan the bound remote folder looking for updates

        If force_recursion is True, recursion is done even on
        non newly created children.
        """

        # Check if synchronization thread was suspended
        self.check_suspended('Remote recursive scan')

        if remote_info is None:
            raise ValueError("Cannot bind %r to missing remote info" %
                             doc_pair)

        # Update the pair state from the collected remote info
        doc_pair.update_remote(remote_info)

        if not remote_info.folderish:
            # No children to align, early stop.
            return

        # If a folderish pair state has been remotely updated,
        # recursively unmark its local descendants as 'unsynchronized'
        # by marking them as 'unknown'.
        # This is needed to synchronize unsynchronized items back.
        if mark_unknown:
            self._mark_unknown_local_recursive(session, doc_pair)

        # Detect recently deleted children
        children_info = client.get_children_info(remote_info.uid)

        db_children = session.query(LastKnownState).filter_by(
                local_folder=doc_pair.local_folder,
                remote_parent_ref=doc_pair.remote_ref)
        children = dict()
        for child in db_children:
            children[child.remote_ref] = child

        for child_info in children_info:
            child_pair = None
            if child_info.uid in children:
                child_pair = children.pop(child_info.uid)
            new_pair = False
            if child_pair is None:
                child_pair, new_pair = self._find_remote_child_match_or_create(
                    doc_pair, child_info, session=session)

            if new_pair or force_recursion:
                self._scan_remote_recursive(session, client, child_pair,
                                        child_info, mark_unknown=False)
        # Delete remaining
        for deleted in children.values():
            self._mark_deleted_remote_recursive(session, deleted)

    def _find_remote_child_match_or_create(self, parent_pair, child_info,
                                           session=None):
        """Find a pair_state that can match child_info by name.

        Return a tuple (child_pair, created) where created is a boolean marker
        that tells that no match was found and that child_pair is newly created
        from the provided child_info.

        """
        session = self.get_session() if session is None else session
        child_name = child_info.name
        if not child_info.folderish:
            # Try to find an existing local doc that has not yet been
            # bound to any remote file that would align with both name
            # and digest
            possible_pairs = session.query(LastKnownState).filter_by(
                local_folder=parent_pair.local_folder,
                remote_ref=None,
                local_parent_path=parent_pair.local_path,
                folderish=child_info.folderish,
                local_digest=child_info.get_digest(),
            ).all()
            child_pair = find_first_name_match(child_name, possible_pairs,
                                               self.check_suspended)
            if child_pair is not None:
                log.debug("Matched remote %s with local %s with digest",
                          child_info.name, child_pair.local_path)
                return child_pair, False

        # Previous attempt has failed: relax the digest constraint
        possible_pairs = session.query(LastKnownState).filter_by(
            local_folder=parent_pair.local_folder,
            remote_ref=None,
            local_parent_path=parent_pair.local_path,
            folderish=child_info.folderish,
        ).all()
        child_pair = find_first_name_match(child_name, possible_pairs,
                                           self.check_suspended)
        if child_pair is not None:
            log.debug("Matched remote %s with local %s by name only",
                      child_info.name, child_pair.local_path)
            return child_pair, False

        # Could not find any pair state to align to, create one
        child_pair = LastKnownState(parent_pair.local_folder,
                                    remote_info=child_info)
        log.trace("Created new pair %r", child_pair)
        session.add(child_pair)
        return child_pair, True

    def synchronize_one(self, doc_pair, session=None):
        """Refresh state and perform network transfer for a doc pair."""
        log.trace("Synchronizing doc pair %r", doc_pair)
        session = self.get_session() if session is None else session
        # Find a cached remote client for the server binding of the file to
        # synchronize
        remote_client = self.get_remote_fs_client(doc_pair.server_binding)
        # local clients are cheap
        local_client = self.get_local_client(doc_pair.local_folder)

        # Update the status of the collected info of this file to make sure
        # we won't perform inconsistent operations
        local_info = remote_info = None
        if doc_pair.local_path is not None:
            local_info = doc_pair.refresh_local(local_client)
        if (doc_pair.remote_ref is not None
            and doc_pair.remote_state != 'deleted'):
            remote_info = doc_pair.refresh_remote(remote_client)

        # Detect creation
        if (doc_pair.local_state != 'deleted'
            and doc_pair.remote_state != 'deleted'):
            if (doc_pair.remote_ref is None
                and doc_pair.local_path is not None):
                doc_pair.update_state(local_state='created')
            if (doc_pair.remote_ref is not None
                and doc_pair.local_path is None):
                doc_pair.update_state(remote_state='created')

        if len(session.dirty):
            # Make refreshed state immediately available to other
            # processes as file transfer can take a long time
            session.commit()

        old_state = doc_pair.pair_state
        handler_name = '_synchronize_' + doc_pair.pair_state
        sync_handler = getattr(self, handler_name, None)

        if sync_handler is None:
            raise RuntimeError("Unhandled pair_state: %r for %r",
                               doc_pair.pair_state, doc_pair)
        else:
            log.trace("Calling %s on doc pair %r", sync_handler, doc_pair)
            sync_handler(doc_pair, session, local_client, remote_client,
                         local_info, remote_info)

        # Update last synchronization date
        doc_pair.update_last_sync_date()
        # Reset the error counter
        doc_pair.error_count = 0

        # Ensure that concurrent process can monitor the synchronization
        # progress
        if len(session.dirty) != 0 or len(session.deleted) != 0:
            session.commit()

        # Update recently modified items
        # Avoid specific case like not known file
        if not old_state in ['unknown_deleted']:
            self._controller.update_recently_modified(doc_pair)

        if self._frontend is not None:
            try:
                # Try to refresh object if possible
                # Deletion will throw except
                session.add(doc_pair)
                session.refresh(doc_pair)
                session.expunge(doc_pair)
            except:
                pass
            self._frontend.notify_change(doc_pair, old_state)

    def _synchronize_locally_modified(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        if doc_pair.remote_digest != doc_pair.local_digest:
            if doc_pair.remote_can_update:
                log.debug("Updating remote document '%s'.",
                          doc_pair.remote_name)
                remote_client.stream_update(
                    doc_pair.remote_ref,
                    doc_pair.get_local_abspath(),
                    parent_fs_item_id=doc_pair.remote_parent_ref,
                    filename=doc_pair.remote_name,
                )
                doc_pair.refresh_remote(remote_client)
            else:
                log.debug("Skip update of remote document '%s'"\
                             " as it is readonly.",
                          doc_pair.remote_name)
                if self._controller.local_rollback():
                    local_client.delete(doc_pair.local_path)
                    doc_pair.update_state('unknown', 'created')
                else:
                    doc_pair.pair_state = 'unsynchronized'
                return
        doc_pair.update_state('synchronized', 'synchronized')

    def _synchronize_remotely_modified(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        try:
            is_renaming = doc_pair.remote_name != doc_pair.local_name
            if doc_pair.remote_digest != doc_pair.local_digest != None:
                os_path = doc_pair.get_local_abspath()
                if is_renaming:
                    new_os_path = os.path.join(os.path.dirname(os_path),
                                               doc_pair.remote_name)
                    log.debug("Replacing local file '%s' by '%s'.",
                              os_path, new_os_path)
                else:
                    new_os_path = os_path
                    log.debug("Updating content of local file '%s'.",
                              os_path)
                tmp_file = remote_client.stream_content(
                                doc_pair.remote_ref, new_os_path,
                                parent_fs_item_id=doc_pair.remote_parent_ref)
                # Ignore the next delete event
                log.trace("Ignore next deleteEvent on %s", os_path)
                conflicted_changes.append(os_path)
                # Delete original file and rename tmp file
                local_client.delete(doc_pair.local_path)
                updated_info = local_client.rename(
                                            local_client.get_path(tmp_file),
                                            doc_pair.remote_name)
                doc_pair.refresh_local(local_client,
                                       local_path=updated_info.path)
            else:
                # digest agree so this might be a renaming and/or a move,
                # and no need to transfer additional bytes over the network
                is_move, new_parent_pair = self._is_remote_move(
                    doc_pair, session)
                if remote_client.is_filtered(doc_pair.remote_parent_path):
                    # A move to a filtered parent ( treat it as deletion )
                    self._synchronize_remotely_deleted(doc_pair, session,
                                            local_client, remote_client,
                                            local_info, remote_info)
                    return
                if not is_move and not is_renaming:
                    log.debug("No local impact of metadata update on"
                              " document '%s'.", remote_info.name)
                else:
                    file_or_folder = 'folder' if doc_pair.folderish else 'file'
                    previous_local_path = doc_pair.local_path
                    if is_move:
                        # move
                        log.debug("Moving local %s '%s' to '%s'.",
                            file_or_folder, doc_pair.get_local_abspath(),
                            new_parent_pair.get_local_abspath())
                        self._update_remote_parent_path_recursive(session,
                            doc_pair, doc_pair.remote_parent_path)
                        updated_info = local_client.move(doc_pair.local_path,
                                          new_parent_pair.local_path)
                        # refresh doc pair for the case of a
                        # simultaneous move and renaming
                        doc_pair.refresh_local(client=local_client,
                            local_path=updated_info.path)
                    if is_renaming:
                        # renaming
                        log.debug("Renaming local %s '%s' to '%s'.",
                            file_or_folder, doc_pair.get_local_abspath(),
                            remote_info.name)
                        updated_info = local_client.rename(
                            doc_pair.local_path, remote_info.name)
                    if is_move or is_renaming:
                        self._local_rename_with_descendant_states(session,
                            local_client, doc_pair, previous_local_path,
                            updated_info.path)
            self.handle_readonly(local_client, doc_pair)
            doc_pair.update_state('synchronized', 'synchronized')
        except (IOError, WindowsError) as e:
            log.warning(
                "Delaying local update of remotely modified content %r due to"
                " concurrent file access (probably opened by another"
                " process).",
                doc_pair)
            raise e

    def _is_remote_move(self, doc_pair, session):
        local_parent_pair = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder,
            local_path=doc_pair.local_parent_path
        ).first()
        remote_parent_pair = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder,
            remote_ref=doc_pair.remote_parent_ref
        ).first()
        return (local_parent_pair is not None
                and remote_parent_pair is not None
                and local_parent_pair.id != remote_parent_pair.id,
                remote_parent_pair)

    def _synchronize_locally_created(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        # Dont detect move if events is on
        if (not doc_pair.local_folder in self.local_full_scan and
            self._detect_resolve_local_move(doc_pair, session,
            local_client, remote_client, local_info)):
            return
        name = os.path.basename(doc_pair.local_path)
        # Find the parent pair to find the ref of the remote folder to
        # create the document
        parent_pair = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder,
            local_path=doc_pair.local_parent_path
        ).first()
        if parent_pair is None or (parent_pair.remote_can_create_child
                                   and parent_pair.remote_ref is None):
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            session.commit()
            raise ValueError(
                "Parent folder of %s is not bound to a remote folder"
                % doc_pair.get_local_abspath())
        parent_ref = parent_pair.remote_ref
        if parent_pair.remote_can_create_child:
            if doc_pair.folderish:
                log.debug("Creating remote folder '%s' in folder '%s'",
                          name, parent_pair.remote_name)
                remote_ref = remote_client.make_folder(parent_ref, name)
            else:
                log.debug("Creating remote document '%s' in folder '%s'",
                          name, parent_pair.remote_name)
                remote_ref = remote_client.stream_file(
                    parent_ref, doc_pair.get_local_abspath(), filename=name)
            doc_pair.update_remote(remote_client.get_info(remote_ref))
            doc_pair.update_state('synchronized', 'synchronized')
        else:
            child_type = 'folder' if doc_pair.folderish else 'file'
            log.warning("Won't synchronize %s '%s' created in"
                        " local folder '%s' since it is readonly",
                child_type, local_info.name, parent_pair.local_name)
            if doc_pair.folderish:
                doc_pair.remote_can_create_child = False
            if self._controller.local_rollback():
                local_client.delete(doc_pair.local_path)
                session.delete(doc_pair)
            else:
                doc_pair.pair_state = 'unsynchronized'

    def _synchronize_remotely_created(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        if (doc_pair.local_state == 'deleted' and
            doc_pair.remote_state == 'modified' and
            self._detect_resolve_local_move(doc_pair, session,
            local_client, remote_client, local_info)):
            return
        name = remote_info.name
        # Find the parent pair to find the path of the local folder to
        # create the document into
        parent_pair = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder,
            remote_ref=remote_info.parent_uid,
        ).first()
        if parent_pair is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ValueError(
                "Could not find parent folder of doc %r (%r)"
                " folder" % (name, doc_pair.remote_ref))
        if parent_pair.local_path is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ValueError(
                "Parent folder of doc %r (%r) is not bound to a local"
                " folder" % (name, doc_pair.remote_ref))
        path = doc_pair.remote_parent_path + '/' + doc_pair.remote_ref
        if remote_client.is_filtered(path):
            # It is filtered so skip and remove from the LastKnownState
            session.delete(doc_pair)
            return
        local_parent_path = parent_pair.local_path
        if doc_pair.folderish:
            log.debug("Creating local folder '%s' in '%s'", name,
                      parent_pair.get_local_abspath())
            path = local_client.make_folder(local_parent_path, name)
            log.debug('Remote recursive scan of the content of %s', name)
            self._scan_remote_recursive(session, remote_client, doc_pair,
                                        remote_info, force_recursion=False)
        else:
            path, os_path, name = local_client.get_new_file(local_parent_path,
                                                            name)
            log.debug("Creating local file '%s' in '%s'", name,
                      parent_pair.get_local_abspath())
            tmp_file = remote_client.stream_content(
                                doc_pair.remote_ref, os_path,
                                parent_fs_item_id=doc_pair.remote_parent_ref)
            # Rename tmp file
            local_client.rename(local_client.get_path(tmp_file), name)
        doc_pair.update_local(local_client.get_info(path))
        self.handle_readonly(local_client, doc_pair)
        doc_pair.update_state('synchronized', 'synchronized')

    def handle_readonly(self, local_client, doc_pair):
        # Don't use readonly on folder for win32 and on Locally Edited
        if (doc_pair.folderish and os.sys.platform == 'win32'
            or self.is_locally_edited_folder(doc_pair)):
            return
        if doc_pair.is_readonly():
            local_client.set_readonly(doc_pair.local_path)
        else:
            local_client.unset_readonly(doc_pair.local_path)

    def _synchronize_locally_deleted(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        if (not doc_pair.local_folder in self.local_full_scan and
            self._detect_resolve_local_move(doc_pair, session,
            local_client, remote_client, local_info)):
            return
        if doc_pair.remote_ref is not None:
            if remote_info.can_delete:
                log.debug("Deleting or unregistering remote document"
                          " '%s' (%s)",
                          doc_pair.remote_name, doc_pair.remote_ref)
                remote_client.delete(doc_pair.remote_ref,
                                parent_fs_item_id=doc_pair.remote_parent_ref)
                self._delete_with_descendant_states(session, doc_pair,
                    local_client)
            else:
                log.debug("Marking %s as remotely created since remote"
                          " document '%s' (%s) can not be deleted: either"
                          " it is readonly or it is a virtual folder that"
                          " doesn't exist in the server hierarchy",
                          doc_pair, doc_pair.remote_name, doc_pair.remote_ref)
                self._mark_descendant_states_remotely_created(session,
                    doc_pair)

    def _synchronize_remotely_deleted(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        try:
            self._delete_with_descendant_states(session, doc_pair,
                                                local_client)
            # XXX: shall we also delete all the subcontent / folder at
            # once in the metadata table?
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

    def _synchronize_deleted(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        # No need to store this information any further
        log.debug('Deleting doc pair %s deleted on both sides' %
                  doc_pair.get_local_abspath())
        self._delete_with_descendant_states(session, doc_pair, local_client)

    def _synchronize_conflicted(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        if doc_pair.local_digest == doc_pair.remote_digest:
            # Note: this also handles folders
            if doc_pair.folderish:
                log.debug('Automated conflict resolution using name for %s',
                          doc_pair.get_local_abspath())
            else:
                log.debug('Automated conflict resolution using digest for %s',
                          doc_pair.get_local_abspath())
            doc_pair.update_state('synchronized', 'synchronized')
        else:
            new_local_name = remote_client.conflicted_name(
                doc_pair.local_name)
            path = doc_pair.get_local_abspath()
            # Ignore the next move event on this file (replace it by creation)
            conflicted_changes.append(os.path.join(os.path.dirname(path),
                                                        new_local_name))
            log.debug('Conflict being handled by renaming local "%s" to "%s"',
                      doc_pair.local_name, new_local_name)

            # Let's rename the file
            # The new local item will be detected as a creation and
            # synchronized by the next iteration of the sync loop
            local_client.rename(doc_pair.local_path, new_local_name)

            # Let the remote win as if doing a regular creation
            self._synchronize_remotely_created(doc_pair, session,
                local_client, remote_client, local_info, remote_info)

    def _synchronize_unknown_deleted(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
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
        session.delete(doc_pair)
        if doc_pair.local_path is not None:
            log.debug("Since the local path is not None: %s, the synchronizer"
                      " will probably consider this as a local creation at"
                      " next iteration and create the file or folder remotely",
                      doc_pair.local_path)
        else:
            log.debug("Since the local path is None the synchronizer will"
                      " probably do nothing at next iteration")

    def _synchronize_locally_moved_created(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        doc_pair.remote_ref = None
        self._synchronize_locally_created(doc_pair, session, local_client,
                                        remote_client, local_info, remote_info)

    def handle_failed_remote_rename(self, source_pair, target_pair, session):
        # An error occurs return false
        log.error("Renaming from %s to %s canceled",
                            target_pair.remote_name, target_pair.local_name)
        if self._controller.local_rollback():
            try:
                local_client = self._controller.get_local_client(
                                                    target_pair.local_folder)
                info = local_client.rename(target_pair.local_path,
                                            target_pair.remote_name)
                source_pair.update_local(info)
                if source_pair != target_pair:
                    if target_pair.folderish:
                        # Remove "new" created tree
                        pairs = session.query(LastKnownState).filter(
                                LastKnownState.local_path.like(
                                target_pair.local_path + '%')).all()
                        [session.delete(pair) for pair in pairs]
                        pairs = session.query(LastKnownState).filter(
                                LastKnownState.local_path.like(
                                source_pair.local_path + '%')).all()
                        for pair in pairs:
                            pair.update_state('synchronized', 'synchronized')
                    else:
                        session.delete(target_pair)
                    # Mark all local as unknown
                    #self._mark_unknown_local_recursive(session, source_pair)
                source_pair.update_state('synchronized', 'synchronized')
                return True
            except Exception, e:
                log.error("Can't rollback local modification")
                log.debug(e)
        return False

    def handle_missing_root(self, server_binding, session):
        log.info("[%s] - [%s]: unbinding server because local folder"
                    " doesn't exist anymore",
                     server_binding.local_folder,
                     server_binding.server_url)
        # LastKnownState table will be deleted on cascade
        session.delete(server_binding)
        session.commit()
        if self._controller.local_rollback():
            old = server_binding
            new_binding = ServerBinding(old.local_folder, old.server_url,
                                           old.remote_user,
                                           old.remote_password,
                                           old.remote_token)
            new_binding.last_event_log_id = None
            new_binding.last_sync_date = None
            new_binding.last_ended_sync_date = None
            session.add(new_binding)
            # Create back the folder
            self._controller._make_local_folder(new_binding.local_folder)
            # Add the root folder back in lastknownstate
            self._controller._add_top_level_state(new_binding, session)
            # Remove from watchdog registered
            if server_binding.local_folder in self.local_full_scan:
                self.local_full_scan.remove(new_binding.local_folder)
            # Reinit the date to force remote scan
            session.commit()

    def _synchronize_locally_moved(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        # A file has been moved locally, and an error occurs when tried to
        # move on the server
        if doc_pair.local_name != doc_pair.remote_name:
            try:
                log.debug('Renaming remote file according to local : %r',
                                                    doc_pair)
                doc_pair.update_remote(remote_client.rename(
                                                        doc_pair.remote_ref,
                                                        doc_pair.local_name))
            except:
                    self.handle_failed_remote_rename(doc_pair, doc_pair,
                                                     session)
                    return
        parent_pair = session.query(LastKnownState).filter_by(
                local_folder=local_client.base_folder,
                local_path=doc_pair.local_parent_path).first()
        if (parent_pair is not None
            and parent_pair.remote_ref != doc_pair.remote_parent_ref):
            log.debug('Moving remote file according to local : %r', doc_pair)
            # Bug if move in a parent with no rights / partial move
            # if rename at the same time
            doc_pair.update_remote(remote_client.move(doc_pair.remote_ref,
                        parent_pair.remote_ref))
        doc_pair.update_state('synchronized', 'synchronized')

    def _synchronize_deleted_unknown(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
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
        session.delete(doc_pair)

    def _detect_local_move_or_rename(self, doc_pair, session,
        local_client, local_info):
        """Find local move or renaming events by introspecting the states

        In case of detection return (source_doc_pair, target_doc_pair).
        Otherwise, return (None, None)

        """
        filters = [
            LastKnownState.local_folder == doc_pair.local_folder,
            LastKnownState.folderish == doc_pair.folderish,
        ]
        if doc_pair.folderish:
            # Detect either renaming or move but not both at the same time
            # for folder to reduce the potential cost of re-ranking that
            # needs to fetch the children of all potential candidates.
            filters.append(or_(
                LastKnownState.local_name == doc_pair.local_name,
                LastKnownState.local_parent_path == doc_pair.local_parent_path
            ))
        else:
            # File match is based on digest hence we can efficiently detect
            # move and rename events or both at the same time.
            filters.append(
                LastKnownState.local_digest == doc_pair.local_digest)

        if (doc_pair.pair_state == 'locally_deleted'
            or doc_pair.pair_state == 'remotely_created'):
            source_doc_pair = doc_pair
            target_doc_pair = None
            # The creation detection might not have occurred yet for the
            # other pair state: let consider both pairs in states 'created'
            # and 'unknown'.
            filters.extend((
                LastKnownState.remote_ref == None,
                or_(LastKnownState.local_state == 'created',
                    LastKnownState.local_state == 'unknown'),
            ))
        elif doc_pair.pair_state == 'locally_created':
            source_doc_pair = None
            target_doc_pair = doc_pair
            filters.append(LastKnownState.local_state == 'deleted')
        else:
            # Nothing to do
            return None, None

        candidates = session.query(LastKnownState).filter(*filters).all()
        if len(candidates) == 0:
            # No match found
            return None, None

        if len(candidates) > 1 or doc_pair.folderish:
            # Re-ranking is always required for folders as it also prunes false
            # positives:
            candidates = rerank_local_rename_or_move_candidates(
                doc_pair, candidates, session,
                check_suspended=self.check_suspended)
            log.trace("Reranked candidates for %s: %s", doc_pair, candidates)

            if len(candidates) == 0:
                # Potentially matches have been pruned by the reranking
                return None, None

        if len(candidates) > 1:
            log.debug("Found %d renaming / move candidates for %s",
                      len(candidates), doc_pair)

        best_candidate = candidates[0]
        if doc_pair.pair_state == 'locally_created':
            source_doc_pair = best_candidate
        else:
            target_doc_pair = best_candidate
        return source_doc_pair, target_doc_pair

    def _detect_resolve_local_move(self, doc_pair, session,
        local_client, remote_client, local_info):
        """Handle local move / renaming if doc_pair is detected as involved

        Detection is based on digest for files and content for folders.
        Resolution perform the matching remote action and update the local
        state DB.

        If the doc_pair is not detected as being involved in a rename
        / move operation
        """
        # Detection step
        source_doc_pair, target_doc_pair = self._detect_local_move_or_rename(
            doc_pair, session, local_client, local_info)

        if source_doc_pair is None or target_doc_pair is None:
            # No candidate found
            return False

        # Resolution step
        moved_or_renamed = False
        remote_ref = source_doc_pair.remote_ref

        remote_info = remote_client.get_info(remote_ref,
                                             raise_if_missing=False)
        # check that the target still exists
        if remote_info is None:
            # Nothing to do: the regular deleted / created handling will
            # work in this case.
            return False

        if (target_doc_pair.local_parent_path
            != source_doc_pair.local_parent_path):
            # This is (at least?) a move operation

            # Find the matching target parent folder, assuming it has already
            # been refreshed and matched in the past
            parent_doc_pair = session.query(LastKnownState).filter_by(
                local_folder=doc_pair.local_folder,
                local_path=target_doc_pair.local_parent_path,
            ).first()

            if (parent_doc_pair is not None  and
                parent_doc_pair.remote_ref is not None):
                # Detect any concurrent deletion of the target remote folder
                # that would prevent the move
                parent_doc_pair.refresh_remote(remote_client)
            if (parent_doc_pair is not None and
                parent_doc_pair.remote_ref is not None):
                # Target has not be concurrently deleted, let's perform the
                # move
                moved_or_renamed = True
                log.debug("Detected and resolving local move event "
                          "on %s to %s",
                    source_doc_pair, parent_doc_pair)
                target_ref = parent_doc_pair.remote_ref
                if not remote_client.can_move(remote_ref, target_ref):
                    log.debug("Move operation unauthorized: fallback to"
                              " default create / delete behavior if possible")
                    return False
                remote_info = remote_client.move(remote_ref, target_ref)
                target_doc_pair.update_remote(remote_info)

        if target_doc_pair.local_name != source_doc_pair.local_name:
            # This is a (also?) a rename operation
            moved_or_renamed = True
            new_name = target_doc_pair.local_name
            log.debug("Detected and resolving local rename event on %s to %s",
                      source_doc_pair, new_name)
            if remote_info.can_rename:
                remote_info = remote_client.rename(remote_ref, new_name)
                target_doc_pair.update_remote(remote_info)
            else:
                log.debug("Marking %s as synchronized since remote document"
                          " can not be renamed: either it is readonly or it is"
                          " a virtual folder that doesn't exist"
                          " in the server hierarchy",
                          target_doc_pair)
                # Put the previous remote name to allow rename
                target_doc_pair.remote_name = source_doc_pair.local_name
                if self.handle_failed_remote_rename(source_doc_pair,
                                                 target_doc_pair, session):
                    return True

        if moved_or_renamed:
            #target_doc_pair.update_state('synchronized', 'synchronized')
            # Set last synchronization date for new pair
            #target_doc_pair.update_last_sync_date()
            new_path = target_doc_pair.local_path
            # Delete the new tree info that is now deprecated
            filters = [
                LastKnownState.local_folder == target_doc_pair.local_folder,
                LastKnownState.local_path.like(
                                            target_doc_pair.local_path + '/%'),
                LastKnownState.remote_ref == None
            ]
            session.query(LastKnownState).filter(*filters).delete(
                                                synchronize_session='fetch')
            session.delete(target_doc_pair)
            # Change the old tree with new path
            self._local_rename_with_descendant_states(session, local_client,
                                    source_doc_pair,
                                    source_doc_pair.local_path, new_path)
            source_doc_pair.update_remote(remote_info)
            source_doc_pair.update_state('synchronized', 'synchronized')
            session.commit()

        return moved_or_renamed

    def synchronize(self, server_binding=None, limit=None):
        """Synchronize one file at a time from the pending list."""
        local_folder = (server_binding.local_folder
                        if server_binding is not None else None)
        synchronized = 0
        session = self.get_session()

        # NDRIVE-107: Remove inconsistents pair
        LastKnownState.remove_inconsistents(session)

        while (limit is None or synchronized < limit):

            # Check if synchronization thread was suspended
            self.check_suspended('Synchronization of pending items')

            pending = self._controller.list_pending(
                local_folder=local_folder,
                limit=self.limit_pending,
                session=session, ignore_in_error=self.error_skip_period)
            nb_pending = len(pending)

            or_more = nb_pending == self.limit_pending
            if self._frontend is not None:
                self._frontend.notify_pending(
                    server_binding, nb_pending, or_more=or_more)

            if nb_pending == 0:
                break
            if not or_more:
                log.debug("Found %d pending item(s)", nb_pending)
            log.trace("Pending items: %r", pending)

            # Look first for a pending pair state with local_path not None,
            # fall back on first one. This is needed in the case where a
            # document is remotely deleted then created with the same name
            # in the same folder within the same change summary: deletion
            # (local_path not None) needs to be handled before creation
            # (local_path None), otherwise the deduplication suffix will
            # be added. See https://jira.nuxeo.com/browse/NXP-11517
            pending_iterator = 0
            while ((pending[pending_iterator].local_path is None
                    or pending[pending_iterator].remote_ref is None)
                   and nb_pending > pending_iterator + 1):
                pending_iterator += 1
            if ((pending[pending_iterator].local_path is None
                 or pending[pending_iterator].remote_ref is None)
                and nb_pending == pending_iterator + 1):
                pending_iterator = 0
            pair_state = pending[pending_iterator]

            try:
                self.synchronize_one(pair_state, session=session)
                synchronized += 1
            except POSSIBLE_NETWORK_ERROR_TYPES as e:
                if getattr(e, 'code', None) in UNEXPECTED_HTTP_STATUS:
                    # This is an unexpected: blacklist doc_pair for
                    # a cooldown period
                    log.error("Failed to sync %r, blacklisting doc pair "
                              "for %d seconds",
                        pair_state, self.error_skip_period, exc_info=True)
                    pair_state.last_sync_error_date = datetime.utcnow()
                    pair_state.error_count += 1
                    session.commit()
                else:
                    # This is expected and should interrupt the sync process
                    # for this local_folder and should be dealt with
                    # in the main loop
                    raise e
            except SyncThreadSuspended as e:
                raise e
            except SyncThreadStopped as e:
                raise e
            except WindowsError as e:
                log.error("Failed to sync %r, blacklisting doc pair "
                          "for %d seconds",
                    pair_state, self.error_skip_period, exc_info=True)
                # Another process is using it, dont update the error count
                pair_state.last_sync_error_date = datetime.utcnow()
                if e.errno == 32:
                    log.error("Another process is using it")
                else:
                    pair_state.error_count += 1
                session.commit()
            except Exception as e:
                # Unexpected exception: blacklist for a cooldown period
                log.error("Failed to sync %r, blacklisting doc pair "
                          "for %d seconds",
                    pair_state, self.error_skip_period, exc_info=True)
                pair_state.last_sync_error_date = datetime.utcnow()
                pair_state.error_count += 1
                session.commit()

        return synchronized

    def should_stop_synchronization(self):
        """Check whether another process has told the synchronizer to stop"""
        stop_file = os.path.join(self._controller.config_folder,
                                 "stop_%d" % os.getpid())
        if os.path.exists(stop_file):
            os.unlink(stop_file)
            return True
        return False

    def loop(self, max_loops=None, delay=None, max_sync_step=None,
             sync_thread=None, no_event_init=False):
        """Forever loop to scan / refresh states and perform sync"""

        # Reinit the full scan for unit test
        if not no_event_init:
            self.local_full_scan = []
            self.local_changes = []
            self.conflicted_changes = []
            self.observers = []
        self.sync_thread = sync_thread
        delay = delay if delay is not None else self.delay

        if self._frontend is not None:
            self._frontend.notify_sync_started()
        pid = os.getpid()
        log.info("Starting synchronization loop (pid=%d)", pid)
        self.continue_synchronization = True

        # Initialize recently modified items
        self._controller.init_recently_modified()

        update_check_time = time()
        session = self.get_session()
        loop_count = 0
        try:
            while True:
                try:
                    n_synchronized = 0
                    # Safety net to ensure that Nuxeo Drive won't eat all the
                    # CPU, disk and network resources of the machine scanning
                    # over an over the bound folders too often.
                    current_time = time()
                    if self.previous_time is not None:
                        spent = current_time - self.previous_time
                        sleep_time = delay - spent
                        if sleep_time > 0 and n_synchronized == 0:
                            log.debug("Sleeping %0.3fs", sleep_time)
                            if self._frontend is not None:
                                self._frontend.notify_sync_asleep()
                            while (sleep_time > 0):
                                if sleep_time < 1:
                                    sleep(sleep_time)
                                else:
                                    sleep(1)
                                sleep_time -= 1
                                self.check_suspended("Suspend during pause")
                            if self._frontend is not None:
                                self._frontend.notify_sync_woken_up()
                    self.previous_time = time()

                    # Check if synchronization thread was suspended
                    self.check_suspended('Main synchronization loop')
                    # Check if synchronization thread was asked to stop
                    if self.should_stop_synchronization():
                        log.info("Stopping synchronization loop (pid=%d)", pid)
                        break
                    if (max_loops is not None and loop_count >= max_loops):
                        log.info("Stopping synchronization loop after %d"
                                 " loops", loop_count)
                        break

                    bindings = session.query(ServerBinding).all()
                    if self._frontend is not None:
                        self._frontend.notify_local_folders(bindings)

                    for sb in bindings:
                        if not sb.has_invalid_credentials():
                            n_synchronized += self.update_synchronize_server(
                                sb, session=session,
                                max_sync_step=max_sync_step)

                    loop_count += 1

                    # Force a commit here to refresh the visibility of any
                    # concurrent change in the database for instance if the
                    # user has updated the connection credentials for a server
                    # binding.
                    session.commit()

                except SyncThreadSuspended as e:
                    session.rollback()
                    self._suspend_sync_thread(e)
                    Action.finish_action()
                # Check for application update
                expired = time() - update_check_time
                if expired > self.update_check_delay:
                    log.debug("Delay for application update check (%ds) has"
                              " expired",
                              self.update_check_delay)
                    if self._frontend is not None:
                        self._frontend.notify_check_update()
                    update_check_time = time()
        except SyncThreadStopped as e:
            self.get_session().rollback()
            log.info("Stopping synchronization loop (pid=%d)", pid)
        except KeyboardInterrupt:
            self.get_session().rollback()
            log.info("Interrupted synchronization on user's request.")
        except:
            self.get_session().rollback()
            raise
        finally:
            # Close thread-local Session
            log.debug("Calling Controller.dispose() from Synchronizer to close"
                      " thread-local Session")
            self._controller.dispose()
            Action.finish_action()

        # Stop all observers
        if not no_event_init:
            self.stop_observers()
        # Notify UI front end to take synchronization stop into account and
        # quit the application
        if self._frontend is not None:
            self._frontend.notify_sync_stopped()

    def _get_remote_changes(self, server_binding, session=None):
        """Fetch incremental change summary from the server"""
        session = self.get_session() if session is None else session
        remote_client = self.get_remote_fs_client(server_binding)

        summary = remote_client.get_changes(server_binding)

        root_definitions = summary['activeSynchronizationRootDefinitions']
        sync_date = summary['syncDate']
        if remote_client.is_event_log_id_available():
            # If available, read 'upperBound' key as last event log id
            # according to the new implementation of the audit change finder,
            # see https://jira.nuxeo.com/browse/NXP-14826.
            last_event_log_id = summary['upperBound']
        else:
            last_event_log_id = None
        checkpoint_data = (sync_date, last_event_log_id, root_definitions)

        return summary, checkpoint_data

    def _checkpoint(self, server_binding, checkpoint_data, session=None):
        """Save the incremental change data for the next iteration"""
        session = self.get_session() if session is None else session
        sync_date, last_event_log_id, root_definitions = checkpoint_data
        server_binding.last_sync_date = sync_date
        if last_event_log_id is not None:
            server_binding.last_event_log_id = last_event_log_id
        server_binding.last_root_definitions = root_definitions
        session.commit()

    def _update_remote_states(self, server_binding, summary, session=None):
        """Incrementally update the state of documents from a change summary"""
        session = self.get_session() if session is None else session
        s_url = server_binding.server_url

        # Fetch all events and consider the most recent first
        sorted_changes = sorted(summary['fileSystemChanges'],
                                key=lambda x: x['eventDate'], reverse=True)
        n_changes = len(sorted_changes)
        if n_changes > 0:
            log.debug("%d remote changes detected on %s",
                    n_changes, server_binding.server_url)

        client = self.get_remote_fs_client(server_binding)

        # Scan events and update the related pair states
        refreshed = set()
        for change in sorted_changes:

            # Check if synchronization thread was suspended
            self.check_suspended('Remote states update')

            eventId = change.get('eventId')
            remote_ref = change['fileSystemItemId']
            if remote_ref in refreshed:
                # A more recent version was already processed
                continue
            fs_item = change.get('fileSystemItem')
            new_info = client.file_to_info(fs_item) if fs_item else None

            # Possibly fetch multiple doc pairs as the same doc can be synchronized at 2 places,
            # typically if under a sync root and locally edited.
            # See https://jira.nuxeo.com/browse/NXDRIVE-125
            doc_pairs = session.query(LastKnownState).filter_by(
                local_folder=server_binding.local_folder,
                remote_ref=remote_ref).all()
            if not doc_pairs:
                # Relax constraint on factory name in FileSystemItem id to
                # match 'deleted' or 'securityUpdated' events.
                # See https://jira.nuxeo.com/browse/NXDRIVE-167
                doc_pairs = session.query(LastKnownState).filter(
                    LastKnownState.local_folder == server_binding.local_folder,
                    LastKnownState.remote_ref.endswith(remote_ref)).all()

            updated = False
            if doc_pairs:
                for doc_pair in (
                        pair for pair in doc_pairs
                            if pair.server_binding.server_url == s_url):
                    doc_pair_repr = doc_pair.local_path if doc_pair.local_path is not None else doc_pair.remote_name
                    # This change has no fileSystemItem, it can be either
                    # a "deleted" event or a "securityUpdated" event
                    if fs_item is None:
                        if eventId == 'deleted':
                            log.debug("Marking doc_pair '%s' as deleted",
                                      doc_pair_repr)
                            doc_pair.update_state(remote_state='deleted')
                        elif eventId == 'securityUpdated':
                            log.debug("Security has been updated for"
                                      " doc_pair '%s' denying Read access,"
                                      " marking it as deleted",
                                      doc_pair_repr)
                            doc_pair.update_state(remote_state='deleted')
                        else:
                            log.debug("Unknow event: '%s'", eventId)
                    else:
                        remote_parent_factory = doc_pair.remote_parent_ref.split('#', 1)[0]
                        new_info_parent_factory = new_info.parent_uid.split('#', 1)[0]
                        # Specific cases of a move on a locally edited doc
                        if (eventId == 'documentMoved'
                            and remote_parent_factory == COLLECTION_SYNC_ROOT_FACTORY_NAME):
                                # If moved from a non sync root to a sync root, break to creation case
                                # (updated is False).
                                # If moved from a sync root to a non sync root, break to noop
                                # (updated is True).
                                break
                        elif (eventId == 'documentMoved'
                              and new_info_parent_factory == COLLECTION_SYNC_ROOT_FACTORY_NAME):
                            # If moved from a sync root to a non sync root, delete from local sync root
                            log.debug("Marking doc_pair '%s' as deleted", doc_pair_repr)
                            doc_pair.update_state(remote_state='deleted')
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
                                consistent_new_info = RemoteFileInfo(new_info.name, new_info.uid,
                                                            new_info_parent_uid, new_info_path, new_info.folderish,
                                                            new_info.last_modification_time,
                                                            new_info.digest, new_info.digest_algorithm,
                                                            new_info.download_url, new_info.can_rename,
                                                            new_info.can_delete, new_info.can_update,
                                                            new_info.can_create_child)
                            # Perform a regular document update on a document
                            # that has been updated, renamed or moved
                            log.debug("Refreshing remote state info"
                                      " for doc_pair '%s'", doc_pair_repr)
                            eventId = change.get('eventId')
                            self._scan_remote_recursive(session, client,
                                doc_pair, consistent_new_info,
                                force_recursion=(eventId == "securityUpdated"))

                    session.commit()
                    updated = True
                    refreshed.add(remote_ref)

            if new_info and not updated:
                # Handle new document creations
                created = False
                parent_pairs = session.query(LastKnownState).filter_by(
                    remote_ref=new_info.parent_uid).all()
                for parent_pair in parent_pairs:
                    if (parent_pair.server_binding.server_url != s_url):
                        continue

                    child_pair, new_pair = (self
                        ._find_remote_child_match_or_create(
                        parent_pair, new_info, session=session))
                    if new_pair:
                        log.debug("Marked doc_pair '%s' as remote creation",
                                  child_pair.remote_name)

                    if child_pair.folderish and new_pair:
                        log.debug('Remote recursive scan of the content of %s',
                                  child_pair.remote_name)
                        self._scan_remote_recursive(
                            session, client, child_pair, new_info)

                    elif not new_pair:
                        child_pair.update_remote(new_info)
                        log.debug("Updated doc_pair '%s' from remote info",
                                  child_pair.remote_name)

                    created = True
                    refreshed.add(remote_ref)
                    break

                if not created:
                    log.debug("Could not match changed document to a "
                                "bound local folder: %r", new_info)

    def watchdog_local(self, server_binding, session):
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
                self.scan_local(server_binding, session=session)
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
            self.scan_local(server_binding, session=session)
            # Put the local_full_scan after to keep move detection
            if watcher_installed:
                self.local_full_scan.append(
                                        server_binding.local_folder)

    def update_synchronize_server(self, server_binding, session=None,
                                  full_scan=False, max_sync_step=None):
        """Do one pass of synchronization for given server binding."""
        session = self.get_session() if session is None else session
        max_sync_step = (max_sync_step if max_sync_step is not None
                          else self.max_sync_step)
        local_scan_is_done = False
        try:
            tick = time()
            is_event_log_id = (self.get_remote_fs_client(server_binding)
                               .is_event_log_id_available())
            first_pass = (is_event_log_id
                          and server_binding.last_event_log_id is None
                          or server_binding.last_sync_date is None)
            log.trace("Fetching remote change summary")
            summary, checkpoint = self._get_remote_changes(
                server_binding, session=session)

            # Apparently we are online, otherwise an network related exception
            # would have been raised and caught below
            if self._frontend is not None:
                self._frontend.notify_online(server_binding)

            self.current_action = Action("Remote scan")
            if full_scan or summary['hasTooManyChanges'] or first_pass:
                # Force remote full scan
                log.debug("Remote full scan of %s. Reasons: "
                          "forced: %r, too many changes: %r, first pass: %r",
                          server_binding.local_folder, full_scan,
                          summary['hasTooManyChanges'], first_pass)
                self.scan_remote(server_binding, session=session)
            else:
                # Only update recently changed documents
                log.trace("Updating remote states")
                self._update_remote_states(server_binding, summary,
                                           session=session)
                self._notify_pending(server_binding)

            remote_refresh_duration = time() - tick
            tick = time()

            # If we reach this point it means the the internal DB was
            # successfully refreshed (no network disruption while collecting
            # the change data): we can save the new time stamp to start again
            # from this point next time
            self._checkpoint(server_binding, checkpoint, session=session)
            self.current_action = Action("Local scan")
            try:
                if not self._controller.use_watchdog():
                    log.trace("Processing local scan to detect local changes")
                    self.scan_local(server_binding, session=session)
                else:
                    log.trace("Using Watchdog to detect local changes")
                    self.watchdog_local(server_binding, session)
            except NotFound:
                # The top level folder has been locally deleted, renamed
                # or moved, unbind the server
                self.handle_missing_root(server_binding, session)
                return 1

            local_scan_is_done = True
            local_refresh_duration = time() - tick
            Action.finish_action()
            tick = time()
            # The DB is updated we, can update the UI with the number of
            # pending tasks
            n_pending = self._notify_pending(server_binding)

            n_synchronized = self.synchronize(limit=max_sync_step,
                server_binding=server_binding)
            synchronization_duration = time() - tick
            log.debug("[%s] - [%s]: synchronized: %d, pending: %d, "
                      "local: %0.3fs, remote: %0.3fs sync: %0.3fs",
                      server_binding.local_folder,
                      server_binding.server_url,
                      n_synchronized, n_pending,
                      local_refresh_duration,
                      remote_refresh_duration,
                      synchronization_duration)
            return n_synchronized

        except POSSIBLE_NETWORK_ERROR_TYPES as e:
            # Do not fail when expecting possible network related errors
            self._handle_network_error(server_binding, e)
            if not local_scan_is_done:
                # Scan the local folders now to update the local DB even
                # if the network is done so that the UI (e.g. windows shell
                # extension) can still be right
                self.scan_local(server_binding, session=session)
            return 0

    def _notify_refreshing(self, server_binding):
        """Notify the frontend that a remote scan is happening"""
        if self._frontend is not None:
            # XXX: this is broken: list pending should be able to count
            # pending operations on a per-server basis!
            self._frontend.notify_pending(server_binding, -1)

    def _notify_pending(self, server_binding):
        """Update the statistics of the frontend"""
        n_pending = len(self._controller.list_pending(
                        local_folder=server_binding.local_folder,
                        limit=self.limit_pending))

        reached_limit = n_pending == self.limit_pending
        if self._frontend is not None:
            # XXX: this is broken: list pending should be able to count
            # pending operations on a per-server basis!
            self._frontend.notify_pending(
                server_binding, n_pending,
                or_more=reached_limit)
        return n_pending

    def _handle_network_error(self, server_binding, e):
        _log_offline(e, "synchronization loop")
        msg = "Traceback of ignored network error: "
        if hasattr(e, 'msg'):
            msg = msg + e.msg
        log.error(msg,
                  exc_info=True)
        if self._frontend is not None:
            self._frontend.notify_offline(
                server_binding, e)

        self._controller.invalidate_client_cache(
            server_binding.server_url)

    def check_suspended(self, msg):
        if hasattr(self, 'sync_thread') and self.sync_thread is not None:
            with self.sync_thread.suspend_condition:
                if self.sync_thread.suspended:
                    raise SyncThreadSuspended(msg)
        if hasattr(self, 'sync_thread') and self.sync_thread is not None:
            with self.sync_thread.stop_condition:
                if self.sync_thread.stopped:
                    raise SyncThreadStopped(msg)

    def _suspend_sync_thread(self, exception):
        if hasattr(self, 'sync_thread') and self.sync_thread is not None:
            with self.sync_thread.suspend_condition:
                log.info("Suspending synchronization thread %r during [%s]",
                         self.sync_thread, exception.message)
                # Notify UI front end to take synchronization
                # suspension into account
                if self._frontend is not None:
                    self._frontend.notify_sync_suspended()
                # Block thread until notified
                self.sync_thread.suspend_condition.wait()

    def get_remote_fs_client(self, server_binding):
        return self._controller.get_remote_fs_client(server_binding)

    def get_local_client(self, local_folder):
        return self._controller.get_local_client(local_folder)

    def handle_local_changes(self, server_binding):
        local_folder = server_binding.local_folder
        session = self.get_session()
        # If the local folder dont even exists unbind
        if not os.path.exists(local_folder):
            raise NotFound
        if self.test_delay > 0:
            sleep(self.test_delay)
        local_client = self.get_local_client(local_folder)
        sorted_evts = []
        deleted_files = []
        # Use the thread_safe pop() to extract events
        while (len(self.local_changes)):
            evt = self.local_changes.pop()
            sorted_evts.append(evt)
        sorted_evts = sorted(sorted_evts, key=lambda evt: evt.time)
        log.debug('Sorted events: %r', sorted_evts)
        for evt in sorted_evts:
            try:
                src_path = normalize_event_filename(evt.src_path)
                rel_path = local_client.get_path(src_path)
                if len(rel_path) == 0:
                    rel_path = '/'
                file_name = os.path.basename(src_path)
                doc_pair = session.query(LastKnownState).filter_by(
                    local_folder=local_folder, local_path=rel_path).first()
                # Ignore unsynchronized doc pairs
                if (doc_pair is not None
                    and doc_pair.pair_state == 'unsynchronized'):
                    log.debug("Ignoring %s as marked unsynchronized",
                              doc_pair.local_path)
                    continue
                if (doc_pair is not None and
                        local_client.is_ignored(doc_pair.local_parent_path,
                                                    file_name)
                      and evt.event_type != 'moved'):
                    continue
                if (evt.event_type == 'created'
                        and doc_pair is None):
                    # If doc_pair is not None mean
                    # the creation has been catched by scan
                    # As Windows send a delete / create event for reparent
                    local_info = local_client.get_info(rel_path)
                    digest = local_info.get_digest()
                    for deleted in deleted_files:
                        if deleted.local_digest == digest:
                            # Move detected
                            log.info('Detected a file movement %r', deleted)
                            deleted.update_state('moved', deleted.remote_state)
                            deleted.update_local(local_client.get_info(
                                                                    rel_path))
                            continue
                    fragments = rel_path.rsplit('/', 1)
                    name = fragments[1]
                    parent_path = fragments[0]
                    # Handle creation of "Locally Edited" folder and its
                    # children
                    if name == LOCALLY_EDITED_FOLDER_NAME:
                        root_pair = session.query(LastKnownState).filter_by(
                            local_path='/', local_folder=local_folder).one()
                        doc_pair = self._scan_local_new_file(session, name,
                                                    local_info, root_pair)
                    elif parent_path.endswith(LOCALLY_EDITED_FOLDER_NAME):
                        parent_pair = session.query(LastKnownState).filter_by(
                            local_path=parent_path,
                            local_folder=local_folder).one()
                        doc_pair = self._scan_local_new_file(session, name,
                                                    local_info, parent_pair)
                    else:
                        doc_pair = LastKnownState(local_folder,
                            local_info=local_info)
                        doc_pair.local_state = 'created'
                        session.add(doc_pair)
                    # An event can be missed inside a new created folder as
                    # watchdog will put listener after it
                    self._scan_local_recursive(session, local_client, doc_pair,
                                                local_info)
                elif doc_pair is not None:
                    if (evt.event_type == 'moved'):
                        remote_client = self.get_remote_fs_client(
                                                                server_binding)
                        self.handle_move(local_client, remote_client,
                                         doc_pair, src_path,
                                    normalize_event_filename(evt.dest_path))
                        session.commit()
                        continue
                    if evt.event_type == 'deleted':
                        doc_pair.update_state('deleted', doc_pair.remote_state)
                        deleted_files.append(doc_pair)
                        continue
                    if evt.event_type == 'modified' and doc_pair.folderish:
                        continue
                    doc_pair.update_local(local_client.get_info(rel_path))
                else:
                    # Event is the reflection of remote deletion
                    if evt.event_type == 'deleted':
                        continue
                    # As you receive an event for every children move also
                    if evt.event_type == 'moved':
                        # Try to see if it is a move from update
                        # No previous pair as it was hidden file
                        # Existing pair (may want to check the pair state)
                        dst_rel_path = local_client.get_path(
                                        normalize_event_filename(
                                                                evt.dest_path))
                        dst_pair = session.query(LastKnownState).filter_by(
                                        local_folder=local_folder,
                                        local_path=dst_rel_path).first()
                        # No pair so it must be a filed moved to this folder
                        if dst_pair is None:
                            local_info = local_client.get_info(dst_rel_path)
                            fragments = dst_rel_path.rsplit('/', 1)
                            name = fragments[1]
                            parent_path = fragments[0]
                            if (parent_path
                                .endswith(LOCALLY_EDITED_FOLDER_NAME)):
                                parent_pair = (session.query(LastKnownState)
                                               .filter_by(
                                                    local_path=parent_path,
                                                    local_folder=local_folder)
                                               .one())
                                doc_pair = self._scan_local_new_file(session,
                                                                name,
                                                                local_info,
                                                                parent_pair)
                                doc_pair.update_local(local_info)
                            else:
                                # It can be consider as a creation
                                doc_pair = LastKnownState(local_folder,
                                        local_info=local_client.get_info(
                                                                dst_rel_path))
                                session.add(doc_pair)
                        else:
                            # Must come from a modification
                            dst_pair.update_local(
                                        local_client.get_info(dst_rel_path))
                        continue
                    log.trace('Unhandled case: %r %s %s', evt, rel_path,
                             file_name)
                    self.unhandle_fs_event = True
            except Exception as e:
                if e.args and len(e.args) == 1 and e.args[0]:
                    e.args = tuple([e.args[0].encode('utf-8')])
                log.trace(e)
        session.commit()

    def handle_rename(self, local_client, remote_client, doc_pair, dest_path):
        new_name = os.path.basename(dest_path)
        state = 'moved'
        rel_path = local_client.get_path(dest_path)
        if len(rel_path) == 0:
                rel_path = '/'
        try:
            doc_pair.update_local(local_client.get_info(rel_path))
        except NotFound:
            # In case of Windows with several move in a row
            # Still need to update path
            doc_pair.local_name = new_name
            doc_pair.local_path = rel_path
        doc_pair.update_state(state, 'synchronized')

    def handle_move(self, local_client, remote_client, doc_pair, src_path,
                        dest_path):
        log.info("Move from %s to %s", src_path, dest_path)
        previous_local_path = doc_pair.local_path
        # Just a rename
        if os.path.basename(dest_path) != os.path.basename(src_path):
            self.handle_rename(local_client, remote_client, doc_pair,
                                    dest_path)
        if os.path.dirname(src_path) != os.path.dirname(dest_path):
            # reparent
            new_parent = os.path.dirname(dest_path)
            rel_path = local_client.get_path(new_parent)
            if len(rel_path) == 0:
                rel_path = '/'
            parent_pair = self.get_session().query(LastKnownState).filter_by(
                local_folder=local_client.base_folder,
                local_path=rel_path).first()
            state = 'synchronized'
            if parent_pair is None:
                log.warn("Cant find parent for %s, %s", rel_path, new_parent)
            else:
                state = 'moved'
            doc_pair.update_state(state, 'synchronized')
            rel_path = local_client.get_path(dest_path)
            if len(rel_path) == 0:
                rel_path = '/'
            doc_pair.update_local(local_client.get_info(rel_path))
        # recursive change
        # all /folder/ must be rename to /folderRenamed/
        self._local_rename_with_descendant_states(self.get_session(),
                                local_client, doc_pair,
                                previous_local_path, doc_pair.local_path)

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

    def is_locally_edited_folder(self, doc_pair):
        return doc_pair.local_path.endswith(LOCALLY_EDITED_FOLDER_NAME)

from watchdog.events import FileSystemEventHandler, FileCreatedEvent


def normalize_event_filename(filename):
    import unicodedata
    if sys.platform == 'darwin':
        return unicodedata.normalize('NFC', unicode(filename, 'utf-8'))
    else:
        return unicodedata.normalize('NFC', unicode(filename))


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
