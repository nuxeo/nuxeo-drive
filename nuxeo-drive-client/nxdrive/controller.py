"""Main API to perform Nuxeo Drive operations"""

from time import time
from time import sleep
import os.path
import logging
from nxdrive.client import NuxeoClient
from nxdrive.client import LocalClient
from nxdrive.client import safe_filename
from nxdrive.model import get_session
from nxdrive.model import ServerBinding
from nxdrive.model import RootBinding
from nxdrive.model import LastKnownState
from nxdrive.client import NotFound

from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import asc


class Controller(object):
    """Manage configuration and perform Nuxeo Drive Operations"""

    def __init__(self, config_folder, nuxeo_client_factory=None, echo=None):
        if echo is None:
            echo = os.environ.get('NX_DRIVE_LOG_SQL', None) is not None
        self.config_folder = os.path.expanduser(config_folder)
        if not os.path.exists(self.config_folder):
            os.makedirs(self.config_folder)

        self.session = get_session(self.config_folder, echo=echo)
        # make it possible to pass an arbitrary nuxeo client factory
        # for testing
        if nuxeo_client_factory is not None:
            self.nuxeo_client_factory = nuxeo_client_factory
        else:
            self.nuxeo_client_factory = NuxeoClient

        self._cached_remote_clients = {}

    def start(self):
        """Start the Nuxeo Drive main daemon if not already started"""
        # TODO, see:
        # https://github.com/mozilla-services/circus/blob/master/circus/
        # circusd.py#L34

    def stop(self):
        """Stop the Nuxeo Drive daemon"""
        # TODO

    def children_states(self, folder_path):
        """Fetch the status of the children of a folder

        The state of the folder is a summary of their descendant rather
        than their own instric synchronization step which is of little
        use for the end user.

        Warning the current implementation of this method is not very scalable
        as it loads all the descendants info in memory and do some complex
        filtering on them in Python rather than SQL.

        Maybe another data model could be devised to make it possible
        to compute the same filtering in SQL instead, probably by materializing
        the pair state directly in the database.
        """
        server_binding = self.get_server_binding(folder_path)
        if server_binding is not None:
            # TODO: if folder_path is the top level Nuxeo Drive folder, list
            # all the root binding states
            raise NotImplementedError(
                "Children States of a server binding is not yet implemented")

        # Find the root binding for this absolute path
        binding, path = self._binding_path(folder_path)

        # find the python list of all the descendants of path ordered by
        # path and then aggregate state for folderish documents using a OR
        # operation on "to synchronize"
        states = self.session.query(LastKnownState).filter(
            LastKnownState.local_root == binding.local_root
        ).order_by(asc(LastKnownState.path)).all()
        results = []
        candidate_folder_path = None
        candidate_folder_state = None
        for state in states:
            if state.parent_path == path:
                if candidate_folder_path is not None:
                    # we have now collected enough information on the previous
                    # candidate folder
                    results.append(
                        (candidate_folder_path, candidate_folder_state))
                    candidate_folder_path, candidate_folder_state = None, None

                if state.folderish:
                    # need to inspect the following elements (potential
                    # descendants) to know if the folder has any descendant
                    # that needs synchronization
                    candidate_folder_path = state.path
                    candidate_folder_state = 'synchronized'
                    continue
                else:
                    # this is a non-folderish direct child, collect info
                    # directly
                    results.append((state.path, state.pair_state))

            elif candidate_folder_state == 'synchronized':
                if (not state.folderish
                    and state.pair_state != 'synchronized'):
                        # this is a non-synchronized descendant of the current
                        # folder candidate: invalidate it
                        candidate_folder_state = 'children_modified'

        if candidate_folder_state is not None:
            results.append((candidate_folder_path, candidate_folder_state))

        return results

    def _binding_path(self, folder_path):
        """Find a root binding and relative path for a given FS path"""
        folder_path = os.path.abspath(folder_path)

        # Check exact root binding match
        binding = self.get_root_binding(folder_path)
        if binding is not None:
            return binding, '/'

        # Check for root bindings that are prefix of folder_path
        all_root_bindings = self.session.query(RootBinding).all()
        root_bindings = [rb for rb in all_root_bindings
                         if folder_path.startswith(
                             rb.local_root + os.path.sep)]
        if len(root_bindings) == 0:
            raise NotFound("Could not find any root binding for "
                               + folder_path)
        elif len(root_bindings) > 1:
            raise RuntimeError("Found more than one binding for %s: %r" % (
                folder_path, root_bindings))
        binding = root_bindings[0]
        path = folder_path[len(binding.local_root):]
        path.replace(os.path.sep, '/')
        return binding, path

    def get_server_binding(self, local_folder, raise_if_missing=False):
        """Find the ServerBinding instance for a given local_folder"""
        try:
            return self.session.query(ServerBinding).filter(
                ServerBinding.local_folder == local_folder).one()
        except NoResultFound:
            if raise_if_missing:
                raise RuntimeError(
                    "Folder '%s' is not bound to any Nuxeo server"
                    % local_folder)
            return None

    def bind_server(self, local_folder, server_url, username, password):
        """Bind a local folder to a remote nuxeo server"""
        try:
            server_binding = self.session.query(ServerBinding).filter(
                ServerBinding.local_folder == local_folder).one()
            raise RuntimeError(
                "%s is already bound to '%s' with user '%s'" % (
                    local_folder, server_binding.server_url,
                    server_binding.remote_user))
        except NoResultFound:
            # this is expected in most cases
            pass

        # check the connection to the server by issuing an authentication
        # request
        self.nuxeo_client_factory(server_url, username, password)

        self.session.add(ServerBinding(local_folder, server_url, username,
                                       password))
        self.session.commit()

    def unbind_server(self, local_folder):
        """Remove the binding to a Nuxeo server

        Local files are not deleted"""
        binding = self.get_server_binding(local_folder, raise_if_missing=True)
        self.session.delete(binding)
        self.session.commit()

    def get_root_binding(self, local_root, raise_if_missing=False):
        """Find the RootBinding instance for a given local_root"""
        try:
            return self.session.query(RootBinding).filter(
                RootBinding.local_root == local_root).one()
        except NoResultFound:
            if raise_if_missing:
                raise RuntimeError(
                    "Folder '%s' is not bound as a root."
                    % local_root)
            return None

    def bind_root(self, local_folder, remote_root, repository='default'):
        """Bind local root to a remote root (folderish document in Nuxeo).

        local_folder must be already bound to an existing Nuxeo server. A
        new folder will be created under that folder to bind the remote
        root.

        remote_root must be the IdRef or PathRef of an existing folderish
        document on the remote server bound to the local folder. The
        user account must have write access to that folder, otherwise
        a RuntimeError will be raised.
        """
        # Check that local_root is a subfolder of bound folder
        server_binding = self.get_server_binding(local_folder,
                                                 raise_if_missing=True)

        # Check the remote root exists and is an editable folder by current
        # user.
        nxclient = self.nuxeo_client_factory(server_binding.server_url,
                                             server_binding.remote_user,
                                             server_binding.remote_password,
                                             repository=repository,
                                             base_folder=remote_root)
        remote_info = nxclient.get_info(remote_root)
        if remote_info is None or not remote_info.folderish:
            raise RuntimeError(
                'No folder at "%s/%s" visible by "%s" on server "%s"'
                % (repository, remote_root, server_binding.remote_user,
                   server_binding.server_url))

        if not nxclient.check_writable(remote_root):
            raise RuntimeError(
                'Folder at "%s:%s" is not editable by "%s" on server "%s"'
                % (repository, remote_root, server_binding.remote_user,
                   server_binding.server_url))

        # Check that this workspace does not already exist locally
        # TODO: shall we handle deduplication for root names too?
        local_root = os.path.join(local_folder,
                                  safe_filename(remote_info.name))
        if os.path.exists(local_root):
            raise RuntimeError(
                'Cannot initialize binding to existing local folder: %s'
                % local_root)

        os.mkdir(local_root)
        lcclient = LocalClient(local_root)
        local_info = lcclient.get_info('/')

        # Register the binding itself
        self.session.add(RootBinding(local_root, repository, remote_root))

        # Initialize the metadata info by recursive walk on the remote folder
        # structure
        self._recursive_init(lcclient, local_info, nxclient, remote_info)
        self.session.commit()

    def _recursive_init(self, local_client, local_info, remote_client,
                        remote_info):
        """Initialize the metadata table by walking the binding tree"""

        folderish = remote_info.folderish
        state = LastKnownState(
            local_client.base_folder, local_info.path,
            remote_client.repository, remote_info.uid,
            local_info.last_modification_time,
            remote_info.last_modification_time,
            folderish=folderish,
            local_digest=local_info.get_digest(),
            remote_digest=remote_info.get_digest())

        if folderish:
            # Mark as synchronized as there is nothing to download later
            state.update_state(local_state='synchronized',
                               remote_state='synchronized')
        else:
            # Mark remote as updated to trigger a download of the binary
            # attachment during the next synchro
            state.update_state(local_state='synchronized',
                               remote_state='modified')
        self.session.add(state)

        if folderish:
            # TODO: how to handle the too many children case properly?
            # Shall we introduce some pagination or shall we raise an
            # exception if a folder contains too many children?
            children = remote_client.get_children_info(remote_info.uid)
            for child_remote_info in children:
                if child_remote_info.folderish:
                    child_local_path = local_client.make_folder(
                        local_info.path, child_remote_info.name)
                else:
                    child_local_path = local_client.make_file(
                        local_info.path, child_remote_info.name)
                child_local_info = local_client.get_info(child_local_path)
                self._recursive_init(local_client, child_local_info,
                                     remote_client, child_remote_info)

    def unbind_root(self, local_root):
        """Remove binding on a root folder"""
        binding = self.get_root_binding(local_root, raise_if_missing=True)
        self.session.delete(binding)
        self.session.commit()

    def scan_local_folders(self):
        """Recursively scan the bound local folders looking for updates"""
        # TODO
        raise NotImplementedError()

    def scan_remote_folders(self):
        """Recursively scan the bound remote folders looking for updates"""
        # TODO
        raise NotImplementedError()

    def refresh_remote_folders_from_log():
        """Query the remote server audit log looking for state updates."""
        # TODO
        raise NotImplementedError()

    def list_pending(self, limit=100):
        """List pending files to synchronize, ordered by path

        Ordering by path makes it possible to synchronize sub folders content
        only once the parent folders have already been synchronized.
        """
        return self.session.query(LastKnownState).filter(
            LastKnownState.pair_state != 'synchronized'
        ).order_by(asc(LastKnownState.path)).limit(limit).all()

    def next_pending(self):
        """Return the next pending file to synchronize or None"""
        pending = self.list_pending(limit=1)
        return pending[0] if len(pending) > 0 else None

    def get_remote_client(self, doc_pair):
        """Fetch a client from the cache or create a new instance"""
        remote_client = self._cached_remote_clients.get(doc_pair.local_root)
        if remote_client is None:
            remote_client = doc_pair.get_remote_client(
                self.nuxeo_client_factory)
            self._cached_remote_clients[doc_pair.local_root] = remote_client
        return remote_client

    def synchronize_one(self, doc_pair):
        """Refresh state a perform network transfer for a pair of documents."""
        # Find a cached remote client for the server binding of the file to
        # synchronize
        remote_client = self.get_remote_client(doc_pair)
        # local clients are cheap
        local_client = doc_pair.get_local_client()

        # Update the status the collected info of this file to make sure
        # we won't perfom inconsistent operations

        # TODO: how to refresh the state of something that has not been
        # linked to a remote resource (just local path or remote ref)?
        doc_pair.refresh_local(local_client)
        remote_info = doc_pair.refresh_remote(remote_client)
        if len(self.session.dirty):
            # Make refreshed state immediately available to other
            # processes as file transfer can take a long time
            self.session.commit()

        # TODO: refactor blob access API to avoid loading content in memory
        # as python strings

        if doc_pair.pair_state == 'locally_modified':
            if doc_pair.remote_digest != doc_pair.local_digest:
                old_name = None
                if remote_info is not None:
                    old_name = remote_info.name
                remote_client.update_content(
                    doc_pair.remote_ref,
                    local_client.get_content(doc_pair.path),
                    name=old_name,
                )
                doc_pair.refresh_remote(remote_client)
            doc_pair.update_state('synchronized', 'synchronized')

        elif doc_pair.pair_state == 'remotely_modified':
            if doc_pair.remote_digest != doc_pair.local_digest:
                local_client.update_content(
                    doc_pair.path,
                    remote_client.get_content(doc_pair.remote_ref),
                )
                doc_pair.refresh_local(local_client)
            doc_pair.update_state('synchronized', 'synchronized')

        elif doc_pair.pair_state == 'locally_created':
            name = os.path.basename(doc_pair.path)
            # Find the parent pair to find the ref of the remote folder to
            # create the document
            parent_pair = self.session.query(LastKnownState).filter_by(
                local_root=doc_pair.local_root, path=doc_pair.parent_path
            ).one()
            parent_ref = parent_pair.remote_ref
            if parent_ref is None:
                logging.warn(
                    "Parent folder of %r/%r is not bound to a remote folder",
                    doc_pair.local_root, doc_pair.path)
            if doc_pair.folderish:
                remote_ref = remote_client.make_folder(parent_ref, name)
            else:
                remote_ref = remote_client.make_file(
                    parent_ref, name,
                    content=local_client.get_content(doc_pair.path))
            doc_pair.remote_ref = remote_ref
            doc_pair.refresh_remote(remote_client)

        elif doc_pair.pair_state == 'remotely_created':
            # TODO: implement me
            pass

        elif doc_pair.pair_state == 'locally_deleted':
            # TODO: implement me
            pass

        elif doc_pair.pair_state == 'remotely_deleted':
            # TODO: implement me
            pass

        # TODO: handle other cases such as moves and lock updates

        # TODO: wrap the individual state synchronization in a dedicated
        # method call wrapped with a try catch logic to be able to skip to
        # the next

        # Ensure that concurrent process can monitor the synchronization
        # progress
        if len(self.session.dirty) != 0:
            self.session.commit()

    def synchronize(self, limit=None):
        """Synchronize one file at a time from the pending list."""
        synchronized = 0
        pending = self.next_pending()
        while pending is not None and (limit is None or synchronized < limit):
            self.synchronize_one(pending)
            synchronized += 1
            pending = self.next_pending()
        return synchronized

    def loop(self, full_local_scan=True, full_remote_scan=True, delta=5,
             max_sync_step=10):
        """Forever loop to scan / refresh states and perform synchronization

        delta is an delay in seconds that ensures that two consecutive
        scans won't happen too closely from one another.
        """
        # Instance flag to allow for another thread to interrupt the
        # synchronization loop cleanly
        self.continue_synchronization = True
        if not full_local_scan:
            # TODO: ensure that the watchdog thread for incremental state
            # update is started thread is started (and make sure it's able to
            # detect new bindings while running)
            pass

        previous_time = time()
        first_pass = True
        while self.continue_synchronization:
            try:
                # the alternative is the watchdog thread
                if full_local_scan or first_pass:
                    self.scan_local_folders()

                if full_remote_scan or first_pass:
                    self.scan_remote_folders()
                else:
                    self.refresh_remote_from_log()

                self.synchronize(limit=max_sync_step)
            except Exception as e:
                # TODO: catch network related errors and log them at debug
                # level instead as we expect the daemon to work even in offline
                # mode without crashing
                logging.error(e)

            # safety net to ensure that Nuxe Drive won't eat all the CPU, disk
            # and network resources of the machine scanning over an over the
            # bound folders too often.
            current_time = time()
            spent = current_time - previous_time
            if spent < delta:
                sleep(delta - spent)
            previous_time = current_time
            first_pass = False
