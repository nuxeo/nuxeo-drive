"""Handle synchronization logic."""
import re
import os.path
from time import time
from time import sleep
from datetime import datetime
import urllib2
import socket
import httplib

from sqlalchemy import not_, or_
import psutil

from nxdrive.client import DEDUPED_BASENAME_PATTERN
from nxdrive.client import safe_filename
from nxdrive.client import NotFound
from nxdrive.client import Unauthorized
from nxdrive.model import ServerBinding
from nxdrive.model import LastKnownState
from nxdrive.logging_config import get_logger

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

log = get_logger(__name__)


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


def find_first_name_match(name, possible_pairs):
    """Select the first pair that can match the provided name"""

    for pair in possible_pairs:
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


class Synchronizer(object):
    """Handle synchronization operations between the client FS and Nuxeo"""

    # delay in seconds that ensures that two consecutive scans won't happen
    # too closely from one another.
    # TODO: make this a value returned by the server so that it can tell the
    # client to slow down when the server cannot keep up with the load
    delay = 10

    # Number of consecutive sync operations to perform without refreshing
    # the internal state DB
    max_sync_step = 10

    # Limit number of pending items to retrieve when computing the list of
    # operations to perform (useful to display activity stats in the
    # frontend)
    limit_pending = 100

    # Log sync error date and skip document pairs in error while syncing up
    # to a fixed cooldown period
    error_skip_period = 300  # 5 minutes

    def __init__(self, controller):
        self._controller = controller
        self._frontend = None

    def register_frontend(self, frontend):
        self._frontend = frontend

    def get_session(self):
        return self._controller.get_session()

    def _delete_with_descendant_states(self, session, doc_pair):
        """Delete the metadata of the descendants of deleted doc"""
        # delete local and remote descendants first
        if doc_pair.local_path is not None:
            local_children = session.query(LastKnownState).filter_by(
                local_folder=doc_pair.local_folder,
                local_parent_path=doc_pair.local_path).all()
            for child in local_children:
                self._delete_with_descendant_states(session, child)

        if doc_pair.remote_ref is not None:
            remote_children = session.query(LastKnownState).filter_by(
                local_folder=doc_pair.local_folder,
                remote_parent_ref=doc_pair.remote_ref).all()
            for child in remote_children:
                self._delete_with_descendant_states(session, child)

        # delete parent folder in the end
        session.delete(doc_pair)

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
                local_folder=server_binding.local_folder).one()

        client = from_state.get_local_client()
        info = client.get_info('/')
        # recursive update
        self._scan_local_recursive(session, client, from_state, info)
        session.commit()

    def _mark_deleted_local_recursive(self, session, doc_pair):
        """Update the metadata of the descendants of locally deleted doc"""
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

    def _scan_local_recursive(self, session, client, doc_pair, local_info):
        """Recursively scan the bound local folder looking for updates"""
        if local_info is None:
            raise ValueError("Cannot bind %r to missing local info" %
                             doc_pair)

        # Update the pair state from the collected local info
        doc_pair.update_local(local_info)

        if not local_info.folderish:
            # No children to align, early stop.
            return

        # detect recently deleted children
        try:
            children_info = client.get_children_info(local_info.path)
        except OSError:
            # The folder has been deleted in the mean time
            return

        children_path = set(c.path for c in children_info)

        q = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder,
            local_parent_path=local_info.path,
        )
        if len(children_path) > 0:
            q = q.filter(not_(LastKnownState.local_path.in_(children_path)))

        for deleted in q.all():
            self._mark_deleted_local_recursive(session, deleted)

        # recursively update children
        for child_info in children_info:

            # TODO: detect whether this is a __digit suffix name and relax the
            # alignment queries accordingly
            child_name = os.path.basename(child_info.path)
            child_pair = session.query(LastKnownState).filter_by(
                local_folder=doc_pair.local_folder,
                local_path=child_info.path).first()

            if child_pair is None and not child_info.folderish:
                # Try to find an existing remote doc that has not yet been
                # bound to any local file that would align with both name
                # and digest
                try:
                    child_digest = child_info.get_digest()
                    possible_pairs = session.query(LastKnownState).filter_by(
                        local_folder=doc_pair.local_folder,
                        local_path=None,
                        remote_parent_ref=doc_pair.remote_ref,
                        folderish=child_info.folderish,
                        remote_digest=child_digest,
                    ).all()
                    child_pair = find_first_name_match(
                        child_name, possible_pairs)
                    if child_pair is not None:
                        log.debug("Matched local %s with remote %s with digest",
                                  child_info.path, child_pair.remote_name)

                except (IOError, WindowsError):
                    # The file is currently being accessed and we cannot
                    # compute the digest
                    log.debug("Cannot perform alignment of %r using"
                              " digest info due to concurrent file"
                              " access", local_info.filepath)

            if child_pair is None:
                # Previous attempt has failed: relax the digest constraint
                possible_pairs = session.query(LastKnownState).filter_by(
                    local_folder=doc_pair.local_folder,
                    local_path=None,
                    remote_parent_ref=doc_pair.remote_ref,
                    folderish=child_info.folderish,
                ).all()
                child_pair = find_first_name_match(child_name, possible_pairs)
                if child_pair is not None:
                    log.debug("Matched local %s with remote %s by name only",
                              child_info.path, child_pair.remote_name)

            if child_pair is None:
                # Could not find any pair state to align to, create one
                child_pair = LastKnownState(doc_pair.local_folder,
                    local_info=child_info)
                session.add(child_pair)
                log.debug("Detected a new non-alignable local file at %s",
                          child_pair.local_path)


            self._scan_local_recursive(session, client, child_pair,
                                       child_info)

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
            log.debug("Mark %r as remotely deleted.", from_state)
            from_state.update_remote(None)
            session.commit()
            return

        # recursive update
        self._scan_remote_recursive(session, client, from_state, remote_info)
        session.commit()

    def _mark_deleted_remote_recursive(self, session, doc_pair):
        """Update the metadata of the descendants of remotely deleted doc"""
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

    def _scan_remote_recursive(self, session, client, doc_pair, remote_info):
        """Recursively scan the bound remote folder looking for updates"""
        if remote_info is None:
            raise ValueError("Cannot bind %r to missing remote info" %
                             doc_pair)

        # Update the pair state from the collected remote info
        doc_pair.update_remote(remote_info)

        if not remote_info.folderish:
            # No children to align, early stop.
            return

        # Detect recently deleted children
        children_info = client.get_children_info(remote_info.uid)
        children_refs = set(c.uid for c in children_info)

        q = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder,
            remote_parent_ref=remote_info.uid,
        )
        if len(children_refs) > 0:
            q = q.filter(not_(LastKnownState.remote_ref.in_(children_refs)))

        for deleted in q.all():
            self._mark_deleted_remote_recursive(session, deleted)

        # Recursively update children
        for child_info in children_info:

            # TODO: detect whether this is a __digit suffix name and relax the
            # alignment queries accordingly
            child_pair = session.query(LastKnownState).filter_by(
                local_folder=doc_pair.local_folder,
                remote_ref=child_info.uid).first()

            if child_pair is None:
                child_pair, _ = self._find_remote_child_match_or_create(
                    doc_pair, child_info, session=session)

            self._scan_remote_recursive(session, client, child_pair,
                                        child_info)

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
            child_pair = find_first_name_match(child_name, possible_pairs)
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
        child_pair = find_first_name_match(child_name, possible_pairs)
        if child_pair is not None:
            log.debug("Matched remote %s with local %s by name only",
                      child_info.name, child_pair.local_path)
            return child_pair, False

        # Could not find any pair state to align to, create one
        child_pair = LastKnownState(parent_pair.local_folder,
            remote_info=child_info)
        session.add(child_pair)
        return child_pair, True

    def synchronize_one(self, doc_pair, session=None):
        """Refresh state and perform network transfer for a pair of documents."""
        session = self.get_session() if session is None else session
        # Find a cached remote client for the server binding of the file to
        # synchronize
        remote_client = self.get_remote_fs_client(doc_pair.server_binding)
        # local clients are cheap
        local_client = doc_pair.get_local_client()

        # Update the status the collected info of this file to make sure
        # we won't perfom inconsistent operations

        local_info = remote_info = None
        if doc_pair.local_path is not None:
            local_info = doc_pair.refresh_local(local_client)
        if doc_pair.remote_ref is not None:
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

        # TODO: refactor blob access API to avoid loading content in memory
        # as python strings

        handler_name = '_synchronize_' + doc_pair.pair_state
        sync_handler = getattr(self, handler_name, None)

        if sync_handler is None:
            raise RuntimeError("Unhandled pair_state: %r for %r",
                               doc_pair.pair_state, doc_pair)
        else:
            sync_handler(doc_pair, session, local_client, remote_client,
                         local_info, remote_info)

        # Ensure that concurrent process can monitor the synchronization
        # progress
        if len(session.dirty) != 0 or len(session.deleted) != 0:
            session.commit()

    def _synchronize_locally_modified(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        if doc_pair.remote_digest != doc_pair.local_digest:
            log.debug("Updating remote document '%s'.",
                      doc_pair.remote_name)
            remote_client.update_content(
                doc_pair.remote_ref,
                local_client.get_content(doc_pair.local_path),
                name=doc_pair.remote_name,
            )
            doc_pair.refresh_remote(remote_client)
        doc_pair.update_state('synchronized', 'synchronized')

    def _synchronize_remotely_modified(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        if doc_pair.remote_digest != doc_pair.local_digest != None:
            log.debug("Updating local file '%s'.",
                      doc_pair.get_local_abspath())
            content = remote_client.get_content(doc_pair.remote_ref)
            try:
                local_client.update_content(doc_pair.local_path, content)
                doc_pair.refresh_local(local_client)
                doc_pair.update_state('synchronized', 'synchronized')
            except (IOError, WindowsError):
                log.debug("Delaying update for remotely modified "
                          "content %r due to concurrent file access.",
                          doc_pair)
        else:
            # digest agree, no need to transfer additional bytes over the
            # network
            doc_pair.update_state('synchronized', 'synchronized')

    def _synchronize_locally_created(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        if self._detect_resolve_local_move(doc_pair, session,
            local_client, remote_client, local_info, remote_info):
            return
        name = os.path.basename(doc_pair.local_path)
        # Find the parent pair to find the ref of the remote folder to
        # create the document
        parent_pair = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder,
            local_path=doc_pair.local_parent_path
        ).first()
        if parent_pair is None or parent_pair.remote_ref is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            session.commit()
            raise ValueError(
                "Parent folder of %s is not bound to a remote folder"
                % doc_pair.get_local_abspath())
        parent_ref = parent_pair.remote_ref
        if doc_pair.folderish:
            log.debug("Creating remote folder '%s' in folder '%s'",
                      name, parent_pair.remote_name)
            remote_ref = remote_client.make_folder(parent_ref, name)
        else:
            remote_ref = remote_client.make_file(
                parent_ref, name,
                content=local_client.get_content(doc_pair.local_path))
            log.debug("Creating remote document '%s' in folder '%s'",
                      name, parent_pair.remote_name)
        doc_pair.update_remote(remote_client.get_info(remote_ref))
        doc_pair.update_state('synchronized', 'synchronized')

    def _synchronize_remotely_created(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
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
        local_parent_path = parent_pair.local_path
        if doc_pair.folderish:
            path = local_client.make_folder(local_parent_path, name)
            log.debug("Creating local folder '%s' in '%s'", name,
                      parent_pair.get_local_abspath())
        else:
            path = local_client.make_file(
                local_parent_path, name,
                content=remote_client.get_content(doc_pair.remote_ref))
            log.debug("Creating local document '%s' in '%s'", name,
                      parent_pair.get_local_abspath())
        doc_pair.update_local(local_client.get_info(path))
        doc_pair.update_state('synchronized', 'synchronized')

    def _synchronize_locally_deleted(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        if self._detect_resolve_local_move(doc_pair, session,
            local_client, remote_client, local_info, remote_info):
            return
        if doc_pair.remote_ref is not None:
            log.debug("Deleting remote doc '%s' (%s)",
                      doc_pair.remote_name, doc_pair.remote_ref)
            remote_client.delete(doc_pair.remote_ref)
        self._delete_with_descendant_states(session, doc_pair)

    def _synchronize_remotely_deleted(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        if doc_pair.local_path is not None:
            try:
                # TODO: handle OS-specific trash management?
                log.debug("Deleting local doc '%s'",
                          doc_pair.get_local_abspath())
                local_client.delete(doc_pair.local_path)
                self._delete_with_descendant_states(session, doc_pair)
                # XXX: shall we also delete all the subcontent / folder at
                # once in the medata table?
            except (IOError, WindowsError):
                # Under Windows deletion can be impossible while another
                # process is accessing the same file (e.g. word processor)
                # TODO: be more specific as detecting this case:
                # shall we restrict to the case e.errno == 13 ?
                log.debug(
                    "Deletion of '%s' delayed due to concurrent"
                    "editing of this file by another process.",
                    doc_pair.get_local_abspath())
        else:
            self._delete_with_descendant_states(session, doc_pair)

    def _synchronize_deleted(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        # No need to store this information any further
        log.debug('Deleting doc pair %s deleted on both sides' %
                  doc_pair.get_local_abspath())
        self._delete_with_descendant_states(session, doc_pair)

    def _synchronize_conflicted(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        if doc_pair.local_digest == doc_pair.remote_digest != None:
            log.debug('Automated conflict resolution using digest for %s',
                doc_pair.get_local_abspath())
            doc_pair.update_state('synchronized', 'synchronized')
        else:
            raise RuntimeError('Conflict detected for %s' %
                               doc_pair.local_path)

    def _detect_resolve_local_move(self, doc_pair, session,
        local_client, remote_client, local_info, remote_info):
        """Handle local move / renaming if doc_pair is detected as involved

        Detection is based on digest for files and content for folders.
        Resolution perform the matching remote action and update the local
        state DB.

        If the doc_pair is not detected as being involved in a rename
        / move operation
        """
        # Detection step

        if doc_pair.pair_state == 'locally_deleted':
            source_doc_pair = doc_pair
            target_doc_pair = None
            wanted_local_state = 'created'
            if doc_pair.folderish:
                # TODO: implement me!
                return False
            else:
                # The creation detection might not have occurred yet for the
                # other pair state
                candidates = session.query(LastKnownState).filter_by(
                    local_folder=doc_pair.local_folder,
                    folderish=0,
                    local_digest=doc_pair.local_digest,
                    remote_ref=None).filter(
                    or_(LastKnownState.local_state == 'created',
                        LastKnownState.local_state == 'unknown')).all()
        elif doc_pair.pair_state == 'locally_created':
            source_doc_pair = None
            target_doc_pair = doc_pair
            wanted_local_state = 'deleted'
            if doc_pair.folderish:
                # TODO: implement me!
                return False
            else:
                candidates = session.query(LastKnownState).filter_by(
                    local_folder=doc_pair.local_folder,
                    folderish=0,
                    local_digest=doc_pair.local_digest,
                    local_state='deleted').all()
        else:
            # Nothing to do
            return False

        if doc_pair.folderish:
            # TODO: implement me!
            return False
        else:
            # Find a locally_created document with matching digest
            if len(candidates) == 0:
                # Shall we try to detect move + update sequences based
                # on same name in another folder?
                return False
            if len(candidates) > 1:
                # TODO: rerank the candidates according to some closeness scores:
                # name unchanged + very code score
                # parent id unchanged + good score
                log.debug("Found %d renaming / move candidates for %s",
                          len(candidates), doc_pair)
            if doc_pair.pair_state == 'locally_deleted':
                target_doc_pair = candidates[0]
            else:
                source_doc_pair = candidates[0]

        if source_doc_pair is None or target_doc_pair is None:
            # No candidate found
            return False

        # Resolution step

        moved_or_renamed = False
        remote_ref = source_doc_pair.remote_ref

        # check that the target still exists
        if not remote_client.exists(remote_ref):
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
                log.debug("Detected and resolving local move event on %s to %s",
                    source_doc_pair, parent_doc_pair)
                remote_info = remote_client.move(remote_ref,
                    parent_doc_pair.remote_ref)
                target_doc_pair.update_remote(remote_info)

        if target_doc_pair.local_name != source_doc_pair.local_name:
            # This is a (also?) a rename operation
            moved_or_renamed = True
            new_name = target_doc_pair.local_name
            log.debug("Detected and resolving local rename event on %s to %s",
                      source_doc_pair, new_name)
            remote_info = remote_client.rename(remote_ref, new_name)
            target_doc_pair.update_remote(remote_info)

        if moved_or_renamed:
            target_doc_pair.update_state('synchronized', 'synchronized')
            session.delete(source_doc_pair)
            session.commit()

        return moved_or_renamed

    def synchronize(self, local_folder=None, limit=None):
        """Synchronize one file at a time from the pending list."""
        synchronized = 0
        session = self.get_session()

        while (limit is None or synchronized < limit):

            pending = self._controller.list_pending(
                local_folder=local_folder, limit=self.limit_pending,
                session=session, ignore_in_error=self.error_skip_period)

            or_more = len(pending) == self.limit_pending
            if self._frontend is not None:
                self._frontend.notify_pending(
                    local_folder, len(pending), or_more=or_more)

            if len(pending) == 0:
                break

            # TODO: make it possible to catch unexpected exceptions here so as
            # to black list the pair of document and ignore it for a while
            # using a TTL for the blacklist token in the state DB
            pair_state = pending[0]
            try:
                self.synchronize_one(pair_state, session=session)
                synchronized += 1
            except POSSIBLE_NETWORK_ERROR_TYPES as e:
                # This is expected and should interrupt the sync process for
                # this local_folder and should be dealt with in the main loop
                if getattr(e, 'code', None) == 500:
                    log.error("Failed to sync %r", pair_state, exc_info=True)
                    pair_state.last_sync_error_date = datetime.utcnow()
                    session.commit()
                else:
                    raise e
            except Exception as e:
                # Unexpected exception
                log.error("Failed to sync %r", pair_state, exc_info=True)
                pair_state.last_sync_error_date = datetime.utcnow()
                session.commit()

        return synchronized

    def _get_sync_pid_filepath(self, process_name="sync"):
        return os.path.join(self._controller.config_folder,
                            'nxdrive_%s.pid' % process_name)

    def check_running(self, process_name="sync"):
        """Check whether another sync process is already runnning

        If nxdrive.pid file already exists and the pid points to a running
        nxdrive program then return the pid. Return None otherwise.

        """
        pid_filepath = self._get_sync_pid_filepath(process_name=process_name)
        if os.path.exists(pid_filepath):
            with open(pid_filepath, 'rb') as f:
                pid = int(f.read().strip())
                try:
                    p = psutil.Process(pid)
                    # Check that this is a nxdrive process by looking at the
                    # process name and commandline
                    # TODO: be more specific using the p.exe attribute
                    if 'ndrive' in p.name:
                        return pid
                    if 'Nuxeo Drive' in p.name:
                        return pid
                    for component in p.cmdline:
                        if 'ndrive' in component:
                            return pid
                        if 'nxdrive' in component:
                            return pid
                except psutil.NoSuchProcess:
                    pass
                # This is a pid file pointing to either a stopped process
                # or a non-nxdrive process: let's delete it if possible
                try:
                    os.unlink(pid_filepath)
                    log.info("Removed old pid file: %s for"
                            " stopped process %d", pid_filepath, pid)
                except Exception, e:
                    log.warning("Failed to remove stalled pid file: %s"
                            " for stopped process %d: %r",
                            pid_filepath, pid, e)
                return None
        return None

    def should_stop_synchronization(self):
        """Check whether another process has told the synchronizer to stop"""
        stop_file = os.path.join(self._controller.config_folder,
                                 "stop_%d" % os.getpid())
        if os.path.exists(stop_file):
            os.unlink(stop_file)
            return True
        return False

    def loop(self, max_loops=None, delay=None):
        """Forever loop to scan / refresh states and perform sync"""

        delay = delay if delay is not None else self.delay

        if self._frontend is not None:
            self._frontend.notify_sync_started()
        pid = self.check_running(process_name="sync")
        if pid is not None:
            log.warning(
                    "Synchronization process with pid %d already running.",
                    pid)
            return

        # Write the pid of this process
        pid_filepath = self._get_sync_pid_filepath(process_name="sync")
        pid = os.getpid()
        with open(pid_filepath, 'wb') as f:
            f.write(str(pid))

        log.info("Starting synchronization (pid=%d)", pid)
        self.continue_synchronization = True

        previous_time = time()
        session = self.get_session()
        loop_count = 0
        try:
            while True:
                n_synchronized = 0
                if self.should_stop_synchronization():
                    log.info("Stopping synchronization (pid=%d)", pid)
                    break
                if (max_loops is not None and loop_count > max_loops):
                    log.info("Stopping synchronization after %d loops",
                             loop_count)
                    break

                bindings = session.query(ServerBinding).all()
                if self._frontend is not None:
                    local_folders = [sb.local_folder for sb in bindings]
                    self._frontend.notify_local_folders(local_folders)

                for sb in bindings:
                    if not sb.has_invalid_credentials():
                        n_synchronized += self.update_synchronize_server(
                            sb, session=session)

                # safety net to ensure that Nuxeo Drive won't eat all the CPU,
                # disk and network resources of the machine scanning over an
                # over the bound folders too often.
                current_time = time()
                spent = current_time - previous_time
                sleep_time = delay - spent
                if sleep_time > 0 and n_synchronized == 0:
                    log.debug("Sleeping %0.3fs", sleep_time)
                    sleep(sleep_time)
                previous_time = time()
                loop_count += 1

        except KeyboardInterrupt:
            self.get_session().rollback()
            log.info("Interrupted synchronization on user's request.")
        except:
            self.get_session().rollback()
            raise

        # Clean pid file
        pid_filepath = self._get_sync_pid_filepath()
        try:
            os.unlink(pid_filepath)
        except Exception, e:
            log.warning("Failed to remove stalled pid file: %s"
                        " for stopped process %d: %r", pid_filepath, pid, e)

        # Notify UI frontend to take synchronization stop into account and
        # potentially quit the app
        if self._frontend is not None:
            self._frontend.notify_sync_stopped()

    def _get_remote_changes(self, server_binding, session=None):
        """Fetch incremental change summary from the server"""
        session = self.get_session() if session is None else session
        remote_client = self.get_remote_fs_client(server_binding)

        summary = remote_client.get_changes(
            last_sync_date=server_binding.last_sync_date,
            last_root_definitions=server_binding.last_root_definitions)

        root_definitions = summary['activeSynchronizationRootDefinitions']
        sync_date = summary['syncDate']
        checkpoint_data = (sync_date, root_definitions)

        return summary, checkpoint_data

    def _checkpoint(self, server_binding, checkpoint_data, session=None):
        """Save the incremental change data for the next iteration"""
        session = self.get_session() if session is None else session
        sync_date, root_definitions = checkpoint_data
        server_binding.last_sync_date = sync_date
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

        # Scan events and update the inter
        refreshed = set()
        moved = []
        for change in sorted_changes:
            remote_ref = change['fileSystemItemId']
            if remote_ref in refreshed:
                # A more recent version was already processed
                continue
            doc_pairs = session.query(LastKnownState).filter_by(
                remote_ref=remote_ref).all()
            updated = False
            for doc_pair in doc_pairs:
                if doc_pair.server_binding.server_url == s_url:
                    old_remote_parent_ref = doc_pair.remote_parent_ref
                    new_info = client.get_info(
                        remote_ref, raise_if_missing=False)
                    if new_info is None:
                        log.debug("Mark doc_pair '%s' as deleted",
                                  doc_pair.remote_name)
                        doc_pair.update_state(remote_state='deleted')

                    elif (old_remote_parent_ref is None
                          or new_info.parent_uid == old_remote_parent_ref):
                        # Perform a regular document update
                        log.debug("Refreshing remote state info for doc_pair '%s'",
                                  doc_pair.remote_name)
                        doc_pair.update_remote(new_info)

                    else:
                        # This document has been moved: make the
                        # existing doc pair as remotely deleted and schedule a
                        # rescan on the new parent to detect the creation
                        log.debug("Mark doc_pair '%s' as deleted (moved)",
                                  doc_pair.remote_name)
                        doc_pair.update_state(remote_state='deleted')
                        moved.append(new_info)

                    session.commit()
                    updated = True
                    refreshed.add(remote_ref)

            if not updated:
                child_info = client.get_info(
                    remote_ref, raise_if_missing=False)
                if child_info is None:
                    # Document must have been deleted since: nothing to do
                    continue

                created = False
                parent_pairs = session.query(LastKnownState).filter_by(
                    remote_ref=child_info.parent_uid).all()
                for parent_pair in parent_pairs:
                    if (parent_pair.server_binding.server_url != s_url):
                        continue

                    child_pair, new_pair = self._find_remote_child_match_or_create(
                        parent_pair, child_info, session=session)
                    if new_pair:
                        log.debug("Marked doc_pair '%s' as creation",
                                  child_pair.remote_name)

                    if child_pair.folderish and new_pair:
                        log.debug('Remote recursive scan of the content of %s',
                                  child_pair.remote_name)
                        self._scan_remote_recursive(
                            session, client, child_pair, child_info)

                    elif not new_pair:
                        child_pair.update_remote(child_info)

                    created = True
                    refreshed.add(remote_ref)
                    break

                if not created:
                    log.warning("Could not match changed document to a "
                                "bound local folder: %r", child_info)

        # TODO: implement the detection of moved documents here
        # Sort the moved documents by path to start with the creation of parent
        # folders if needed
        # moved = sorted(moved, key=lambda m: m.path)

    def update_synchronize_server(self, server_binding, session=None,
                                  full_scan=False):
        """Do one pass of synchronization for given server binding."""
        session = self.get_session() if session is None else session
        local_scan_is_done = False
        try:
            tick = time()
            first_pass = server_binding.last_sync_date is None
            summary, checkpoint = self._get_remote_changes(
                server_binding, session=session)

            # Apparently we are online, otherwise an network related exception
            # would have been raised and caught below
            if self._frontend is not None:
                self._frontend.notify_online(server_binding.local_folder)

            if full_scan or summary['hasTooManyChanges'] or first_pass:
                # Force remote full scan
                log.debug("Remote full scan of %s. Reasons: "
                          "forced: %r, too many changes: %r, first pass: %r",
                          server_binding.local_folder, full_scan,
                          summary['hasTooManyChanges'], first_pass)
                self.scan_remote(server_binding, session=session)
            else:
                # Only update recently changed documents
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

            # Scan local folders to detect changes
            # XXX: OPTIM: use file system monitoring instead
            self.scan_local(server_binding, session=session)

            local_scan_is_done = True
            local_refresh_duration = time() - tick

            tick = time()
            # The DB is updated we, can update the UI with the number of
            # pending tasks
            n_pending = self._notify_pending(server_binding)

            n_synchronized = self.synchronize(limit=self.max_sync_step,
                local_folder=server_binding.local_folder)
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
                # if the netwrok is done so that the UI (e.g. windows shell
                # extension can still be right)
                self.scan_local(server_binding, session=session)
            return 0

    def _notify_refreshing(self, server_binding):
        """Notify the frontend that a remote scan is happening"""
        if self._frontend is not None:
            # XXX: this is broken: list pending should be able to count
            # pending operations on a per-server basis!
            self._frontend.notify_pending(server_binding.local_folder, -1)

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
                server_binding.local_folder, n_pending,
                or_more=reached_limit)
        return n_pending

    def _handle_network_error(self, server_binding, e):
        _log_offline(e, "synchronization loop")
        log.trace("Traceback of ignored network error:",
                  exc_info=True)
        if self._frontend is not None:
            self._frontend.notify_offline(
                server_binding.local_folder, e)

        self._controller.invalidate_client_cache(
            server_binding.server_url)

    def get_remote_fs_client(self, server_binding):
        return self._controller.get_remote_fs_client(server_binding)
