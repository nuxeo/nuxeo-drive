"""Handle synchronization logic."""
import re
import os
import os.path
from time import time
from time import sleep
import urllib2
import socket
import httplib

from sqlalchemy import not_
import psutil

from nxdrive.client import DEDUPED_BASENAME_PATTERN
from nxdrive.client import safe_filename
from nxdrive.client import NotFound
from nxdrive.client import Unauthorized
from nxdrive.model import ServerBinding
from nxdrive.model import RootBinding
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

    def __init__(self, controller):
        self._controller = controller

    def get_session(self):
        return self._controller.get_session()

    def scan_local(self, local_root, session=None):
        """Recursively scan the bound local folder looking for updates"""
        if session is None:
            session = self.get_session()

        root_state = session.query(LastKnownState).filter_by(
            local_root=local_root, path='/').one()

        client = root_state.get_local_client()
        root_info = client.get_info('/')
        # recursive update
        self._scan_local_recursive(local_root, session, client,
                                   root_state, root_info)
        session.commit()

    def _mark_deleted_local_recursive(self, local_root, session, doc_pair):
        """Update the metadata of the descendants of locally deleted doc"""
        # delete descendants first
        children = session.query(LastKnownState).filter_by(
            local_root=local_root, parent_path=doc_pair.path).all()
        for child in children:
            self._mark_deleted_local_recursive(local_root, session, child)

        # update the state of the parent it-self
        if doc_pair.remote_ref is None:
            # Unbound child metadata can be removed
            session.delete(doc_pair)
        else:
            # mark it for remote deletion
            doc_pair.update_local(None)

    def _scan_local_recursive(self, local_root, session, client,
                              doc_pair, local_info):
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
            local_root=local_root,
            parent_path=local_info.path,
        )
        if len(children_path) > 0:
            q = q.filter(not_(LastKnownState.path.in_(children_path)))

        for deleted in q.all():
            self._mark_deleted_local_recursive(local_root, session, deleted)

        # recursively update children
        for child_info in children_info:

            # TODO: detect whether this is a __digit suffix name and relax the
            # alignment queries accordingly
            child_name = os.path.basename(child_info.path)
            child_pair = session.query(LastKnownState).filter_by(
                local_root=local_root,
                path=child_info.path).first()

            if child_pair is None and not child_info.folderish:
                # Try to find an existing remote doc that has not yet been
                # bound to any local file that would align with both name
                # and digest
                try:
                    child_digest = child_info.get_digest()
                    possible_pairs = session.query(LastKnownState).filter_by(
                        local_root=local_root,
                        path=None,
                        remote_parent_ref=doc_pair.remote_ref,
                        folderish=child_info.folderish,
                        remote_digest=child_digest,
                    ).all()
                    child_pair = find_first_name_match(
                        child_name, possible_pairs)
                except (IOError, WindowsError):
                    # The file is currently being accessed and we cannot
                    # compute the digest
                    log.debug("Cannot perform alignment of %r using"
                              " digest info due to concurrent file"
                              " access", local_info.filepath)

            if child_pair is None:
                # Previous attempt has failed: relax the digest constraint
                possible_pairs = session.query(LastKnownState).filter_by(
                    local_root=local_root,
                    path=None,
                    remote_parent_ref=doc_pair.remote_ref,
                    folderish=child_info.folderish,
                ).all()
                child_pair = find_first_name_match(child_name, possible_pairs)

            if child_pair is None:
                # Could not find any pair state to align to, create one
                child_pair = LastKnownState(local_root, local_info=child_info)
                session.add(child_pair)

            self._scan_local_recursive(local_root, session, client,
                                       child_pair, child_info)

    def scan_remote(self, local_root, session=None):
        """Recursively scan the bound remote folder looking for updates"""
        if session is None:
            session = self.get_session()

        root_state = session.query(LastKnownState).filter_by(
            local_root=local_root, path='/').one()

        try:
            client = self.get_remote_client_from_docpair(root_state)
            root_info = client.get_info(root_state.remote_ref,
                                        fetch_parent_uid=False)
        except NotFound:
            # remote folder has been deleted, remote the binding
            log.debug("Unbinding %r because of remote deletion.",
                      local_root)
            self.unbind_root(local_root, session=session)
            return

        # recursive update
        self._scan_remote_recursive(local_root, session, client,
                                    root_state, root_info)
        session.commit()

    def _mark_deleted_remote_recursive(self, local_root, session, doc_pair):
        """Update the metadata of the descendants of remotely deleted doc"""
        # delete descendants first
        children = session.query(LastKnownState).filter_by(
            local_root=local_root,
            remote_parent_ref=doc_pair.remote_ref).all()
        for child in children:
            self._mark_deleted_remote_recursive(local_root, session, child)

        # update the state of the parent it-self
        if doc_pair.path is None:
            # Unbound child metadata can be removed
            session.delete(doc_pair)
        else:
            # schedule it for local deletion
            doc_pair.update_remote(None)

    def _scan_remote_recursive(self, local_root, session, client,
                               doc_pair, remote_info):
        """Recursively scan the bound remote folder looking for updates"""
        if remote_info is None:
            raise ValueError("Cannot bind %r to missing remote info" %
                             doc_pair)

        # Update the pair state from the collected remote info
        doc_pair.update_remote(remote_info)

        if not remote_info.folderish:
            # No children to align, early stop.
            return

        # detect recently deleted children
        children_info = client.get_children_info(remote_info.uid)
        children_refs = set(c.uid for c in children_info)

        q = session.query(LastKnownState).filter_by(
            local_root=local_root,
            remote_parent_ref=remote_info.uid,
        )
        if len(children_refs) > 0:
            q = q.filter(not_(LastKnownState.remote_ref.in_(children_refs)))

        for deleted in q.all():
            self._mark_deleted_remote_recursive(local_root, session, deleted)

        # recursively update children
        for child_info in children_info:

            # TODO: detect whether this is a __digit suffix name and relax the
            # alignment queries accordingly
            child_name = child_info.name
            child_pair = session.query(LastKnownState).filter_by(
                local_root=local_root,
                remote_ref=child_info.uid).first()

            if child_pair is None and not child_info.folderish:
                # Try to find an existing local doc that has not yet been
                # bound to any remote file that would align with both name
                # and digest
                possible_pairs = session.query(LastKnownState).filter_by(
                    local_root=local_root,
                    remote_ref=None,
                    parent_path=doc_pair.path,
                    folderish=child_info.folderish,
                    local_digest=child_info.get_digest(),
                ).all()
                child_pair = find_first_name_match(child_name, possible_pairs)

            if child_pair is None:
                # Previous attempt has failed: relax the digest constraint
                possible_pairs = session.query(LastKnownState).filter_by(
                    local_root=local_root,
                    remote_ref=None,
                    parent_path=doc_pair.path,
                    folderish=child_info.folderish,
                ).all()
                child_pair = find_first_name_match(child_name, possible_pairs)

            if child_pair is None:
                # Could not find any pair state to align to, create one
                child_pair = LastKnownState(
                    local_root, remote_info=child_info)
                session.add(child_pair)

            self._scan_remote_recursive(local_root, session, client,
                                        child_pair, child_info)

    def update_roots(self, session=None, server_binding=None,
                     repository=None, frontend=None):
        """Ensure that the list of bound roots match server-side info

        If a server is not responding it is skipped.
        """
        if session is None:
            session = self.get_session()
        if server_binding is not None:
            server_bindings = [server_binding]
        else:
            server_bindings = session.query(ServerBinding).all()
        for sb in server_bindings:
            if sb.has_invalid_credentials():
                # Skip servers with missing credentials
                continue
            try:
                nxclient = self.get_remote_client(sb)
                if not nxclient.is_addon_installed():
                    continue
                if repository is not None:
                    repositories = [repository]
                else:
                    repositories = nxclient.get_repository_names()
                for repo in repositories:
                    nxclient = self.get_remote_client(sb, repository=repo)
                    remote_roots = nxclient.get_roots()
                    local_roots = [r for r in sb.roots
                                   if r.remote_repo == repo]
                    self._controller.update_server_roots(
                        sb, session, local_roots, remote_roots, repo)
            except POSSIBLE_NETWORK_ERROR_TYPES as e:
                # Ignore expected possible network related errors
                _log_offline(e, "update roots")
                log.trace("Traceback of ignored network error:",
                        exc_info=True)
                if frontend is not None:
                    frontend.notify_offline(sb.local_folder, e)
                self._controller.invalidate_client_cache(sb.server_url)

        if frontend is not None:
            local_folders = [sb.local_folder
                    for sb in session.query(ServerBinding).all()]
            frontend.notify_local_folders(local_folders)

    def refresh_remote_folders_from_log(root_binding):
        """Query the remote server audit log looking for state updates."""
        # TODO
        raise NotImplementedError()

    def get_remote_client_from_docpair(self, doc_pair):
        """Fetch a client from the cache or create a new instance"""
        rb = doc_pair.root_binding
        sb = rb.server_binding
        return self.get_remote_client(sb, base_folder=rb.remote_root,
                                      repository=rb.remote_repo)

    # TODO: move the synchronization related methods in a dedicated class

    def synchronize_one(self, doc_pair, session=None):
        """Refresh state a perform network transfer for a pair of documents."""
        if session is None:
            session = self.get_session()
        # Find a cached remote client for the server binding of the file to
        # synchronize
        remote_client = self.get_remote_client_from_docpair(doc_pair)
        # local clients are cheap
        local_client = doc_pair.get_local_client()

        # Update the status the collected info of this file to make sure
        # we won't perfom inconsistent operations

        if doc_pair.path is not None:
            doc_pair.refresh_local(local_client)
        if doc_pair.remote_ref is not None:
            remote_info = doc_pair.refresh_remote(remote_client)

        # Detect creation
        if (doc_pair.local_state != 'deleted'
            and doc_pair.remote_state != 'deleted'):
            if doc_pair.remote_ref is None and doc_pair.path is not None:
                doc_pair.update_state(local_state='created')
            if doc_pair.remote_ref is not None and doc_pair.path is None:
                doc_pair.update_state(remote_state='created')

        if len(session.dirty):
            # Make refreshed state immediately available to other
            # processes as file transfer can take a long time
            session.commit()

        # TODO: refactor blob access API to avoid loading content in memory
        # as python strings

        if doc_pair.pair_state == 'locally_modified':
            # TODO: handle smart versionning policy here (or maybe delegate to
            # a dedicated server-side operation)
            if doc_pair.remote_digest != doc_pair.local_digest:
                log.debug("Updating remote document '%s'.",
                          doc_pair.remote_name)
                remote_client.update_content(
                    doc_pair.remote_ref,
                    local_client.get_content(doc_pair.path),
                    name=doc_pair.remote_name,
                )
                doc_pair.refresh_remote(remote_client)
            doc_pair.update_state('synchronized', 'synchronized')

        elif doc_pair.pair_state == 'remotely_modified':
            if doc_pair.remote_digest != doc_pair.local_digest != None:
                log.debug("Updating local file '%s'.",
                          doc_pair.get_local_abspath())
                content = remote_client.get_content(doc_pair.remote_ref)
                try:
                    local_client.update_content(doc_pair.path, content)
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

        elif doc_pair.pair_state == 'locally_created':
            name = os.path.basename(doc_pair.path)
            # Find the parent pair to find the ref of the remote folder to
            # create the document
            parent_pair = session.query(LastKnownState).filter_by(
                local_root=doc_pair.local_root, path=doc_pair.parent_path
            ).first()
            if parent_pair is None or parent_pair.remote_ref is None:
                log.warning(
                    "Parent folder of %r/%r is not bound to a remote folder",
                    doc_pair.local_root, doc_pair.path)
                # Inconsistent state: delete and let the next scan redetect for
                # now
                # TODO: how to handle this case in incremental mode?
                session.delete(doc_pair)
                session.commit()
                return
            parent_ref = parent_pair.remote_ref
            if doc_pair.folderish:
                log.debug("Creating remote folder '%s' in folder '%s'",
                          name, parent_pair.remote_name)
                remote_ref = remote_client.make_folder(parent_ref, name)
            else:
                remote_ref = remote_client.make_file(
                    parent_ref, name,
                    content=local_client.get_content(doc_pair.path))
                log.debug("Creating remote document '%s' in folder '%s'",
                          name, parent_pair.remote_name)
            doc_pair.update_remote(remote_client.get_info(remote_ref))
            doc_pair.update_state('synchronized', 'synchronized')

        elif doc_pair.pair_state == 'remotely_created':
            name = remote_info.name
            # Find the parent pair to find the path of the local folder to
            # create the document into
            parent_pair = session.query(LastKnownState).filter_by(
                local_root=doc_pair.local_root,
                remote_ref=remote_info.parent_uid,
            ).first()
            if parent_pair is None or parent_pair.path is None:
                log.warning(
                    "Parent folder of doc %r (%r:%r) is not bound to a local"
                    " folder",
                    name, doc_pair.root_binding.remote_repo, doc_pair.remote_ref)
                # Inconsistent state: delete and let the next scan redetect for
                # now
                # TODO: how to handle this case in incremental mode?
                session.delete(doc_pair)
                session.commit()
                return
            parent_path = parent_pair.path
            if doc_pair.folderish:
                path = local_client.make_folder(parent_path, name)
                log.debug("Creating local folder '%s' in '%s'", name,
                          parent_pair.get_local_abspath())
            else:
                path = local_client.make_file(
                    parent_path, name,
                    content=remote_client.get_content(doc_pair.remote_ref))
                log.debug("Creating local document '%s' in '%s'", name,
                          parent_pair.get_local_abspath())
            doc_pair.update_local(local_client.get_info(path))
            doc_pair.update_state('synchronized', 'synchronized')

        elif doc_pair.pair_state == 'locally_deleted':
            if doc_pair.path == '/':
                log.debug("Unbinding local root '%s'", doc_pair.local_root)
                # Special case: unbind root instead of performing deletion
                self.unbind_root(doc_pair.local_root, session=session)
            else:
                if doc_pair.remote_ref is not None:
                    # TODO: handle trash management with a dedicated server
                    # side operations?
                    log.debug("Deleting remote doc '%s' (%s)",
                              doc_pair.remote_name, doc_pair.remote_ref)
                    remote_client.delete(doc_pair.remote_ref)
                # XXX: shall we also delete all the subcontent / folder at
                # once in the medata table?
                session.delete(doc_pair)

        elif doc_pair.pair_state == 'remotely_deleted':
            if doc_pair.path is not None:
                try:
                    # TODO: handle OS-specific trash management?
                    log.debug("Deleting local doc '%s'",
                              doc_pair.get_local_abspath())
                    local_client.delete(doc_pair.path)
                    session.delete(doc_pair)
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
                session.delete(doc_pair)

        elif doc_pair.pair_state == 'deleted':
            # No need to store this information any further
            session.delete(doc_pair)
            session.commit()

        elif doc_pair.pair_state == 'conflicted':
            if doc_pair.local_digest == doc_pair.remote_digest != None:
                # Automated conflict resolution based on digest content:
                doc_pair.update_state('synchronized', 'synchronized')
        else:
            log.warning("Unhandled pair_state: %r for %r",
                          doc_pair.pair_state, doc_pair)

        # TODO: handle other cases such as moves and lock updates

        # Ensure that concurrent process can monitor the synchronization
        # progress
        if len(session.dirty) != 0 or len(session.deleted) != 0:
            session.commit()

    def synchronize(self, limit=None, local_root=None, fault_tolerant=False):
        """Synchronize one file at a time from the pending list.

        Fault tolerant mode is meant to be skip problematic documents while not
        preventing the rest of the synchronization loop to work on documents
        that work as expected.

        This mode will probably hide real Nuxeo Drive bugs in the
        logs. It should thus not be enabled when running tests for the
        synchronization code but might be useful when running Nuxeo
        Drive in daemon mode.
        """
        synchronized = 0
        session = self.get_session()
        doc_pair = self._controller.next_pending(local_root=local_root,
                                                 session=session)
        while doc_pair is not None and (limit is None or synchronized < limit):
            if fault_tolerant:
                try:
                    self.synchronize_one(doc_pair, session=session)
                    synchronized += 1
                except Exception as e:
                    log.error("Failed to synchronize %r: %r",
                              doc_pair, e, exc_info=True)
                    # TODO: flag pending and all descendant as failed with a
                    # time stamp and make next_pending ignore recently (e.g.
                    # up to 30s) failed synchronized pairs
                    raise NotImplementedError(
                        'Fault tolerant synchronization not implemented yet.')
            else:
                self.synchronize_one(doc_pair, session=session)
                synchronized += 1

            doc_pair = self._controller.next_pending(local_root=local_root,
                                                     session=session)
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

    def loop(self, full_local_scan=True, full_remote_scan=True, delay=10,
             max_sync_step=50, max_loops=None, fault_tolerant=True,
             frontend=None, limit_pending=100):
        """Forever loop to scan / refresh states and perform synchronization

        delay is an delay in seconds that ensures that two consecutive
        scans won't happen too closely from one another.
        """
        if frontend is not None:
            frontend.notify_sync_started()
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
        if not full_local_scan:
            # TODO: ensure that the watchdog thread for incremental state
            # update is started thread is started (and make sure it's able to
            # detect new bindings while running)
            raise NotImplementedError()

        previous_time = time()
        first_pass = True
        session = self.get_session()
        loop_count = 0
        try:
            while True:
                if self.should_stop_synchronization():
                    log.info("Stopping synchronization (pid=%d)", pid)
                    break
                if (max_loops is not None and loop_count > max_loops):
                    log.info("Stopping synchronization after %d loops",
                             loop_count)
                    break
                self.update_roots(session, frontend=frontend)

                bindings = session.query(RootBinding).all()
                for rb in bindings:
                    try:
                        # the alternative to local full scan is the watchdog
                        # thread
                        if full_local_scan or first_pass:
                            self.scan_local(rb.local_root, session)

                        if rb.server_binding.has_invalid_credentials():
                            # Skip roots for servers with missing credentials
                            continue

                        if full_remote_scan or first_pass:
                            self.scan_remote(rb.local_root, session)
                        else:
                            self.refresh_remote_from_log(rb.remote_ref)
                        if frontend is not None:
                            n_pending = len(self._controller.list_pending(
                                limit=limit_pending))
                            reached_limit = n_pending == limit_pending
                            frontend.notify_pending(rb.local_folder, n_pending,
                                    or_more=reached_limit)

                        self.synchronize(limit=max_sync_step,
                                         local_root=rb.local_root,
                                         fault_tolerant=fault_tolerant)
                    except POSSIBLE_NETWORK_ERROR_TYPES as e:
                        # Ignore expected possible network related errors
                        _log_offline(e, "synchronization loop")
                        log.trace("Traceback of ignored network error:",
                                exc_info=True)
                        if frontend is not None:
                            frontend.notify_offline(rb.local_folder, e)

                        # TODO: add a special handling for the invalid
                        # credentials case and mark the server binding
                        # with a special flag in the DB to be skipped by
                        # the synchronization loop until the user decides
                        # to reenable it in the systray menu with a dedicated
                        # action instead
                        self._controller.invalidate_client_cache(
                            rb.server_binding.server_url)

                # safety net to ensure that Nuxe Drive won't eat all the CPU,
                # disk and network resources of the machine scanning over an
                # over the bound folders too often.
                current_time = time()
                spent = current_time - previous_time
                if spent < delay:
                    sleep(delay - spent)
                previous_time = current_time
                first_pass = False
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
                    " for stopped process %d: %r",
                    pid_filepath, pid, e)

        # Notify UI frontend to take synchronization stop into account and
        # potentially quit the app
        if frontend is not None:
            frontend.notify_sync_stopped()

    def get_remote_client(self, server_binding, base_folder=None,
                          repository='default'):
        return self._controller.get_remote_client(
            server_binding, base_folder=base_folder, repository='default')
