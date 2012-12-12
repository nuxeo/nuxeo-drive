"""Main API to perform Nuxeo Drive operations"""

import os
import sys
from threading import local
import subprocess

from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import asc
from sqlalchemy import or_

import nxdrive
from nxdrive.client import NuxeoClient
from nxdrive.client import LocalClient
from nxdrive.client import safe_filename
from nxdrive.client import NotFound
from nxdrive.model import init_db
from nxdrive.model import DeviceConfig
from nxdrive.model import ServerBinding
from nxdrive.model import RootBinding
from nxdrive.model import LastKnownState
from nxdrive.synchronizer import Synchronizer
from nxdrive.logging_config import get_logger



log = get_logger(__name__)


def default_nuxeo_drive_folder():
    """Find a reasonable location for the root Nuxeo Drive folder

    This folder is user specific, typically under the home folder.
    """
    if sys.platform == "win32":
        if os.path.exists(os.path.expanduser(r'~\My Documents')):
            # Compat for Windows XP
            return r'~\My Documents\Nuxeo Drive'
        else:
            # Default Documents folder with navigation shortcuts in Windows 7
            # and up.
            return r'~\Documents\Nuxeo Drive'
    else:
        return '~/Nuxeo Drive'


class Controller(object):
    """Manage configuration and perform Nuxeo Drive Operations

    This class is thread safe: instance can be shared by multiple threads
    as DB sessions and Nuxeo clients are thread locals.
    """

    def __init__(self, config_folder, nuxeo_client_factory=None, echo=None,
                 poolclass=None):
        # Log the installation location for debug
        nxdrive_install_folder = os.path.dirname(nxdrive.__file__)
        nxdrive_install_folder = os.path.realpath(nxdrive_install_folder)
        log.debug("nxdrive installed in '%s'", nxdrive_install_folder)

        # Log the configuration location for debug
        config_folder = os.path.expanduser(config_folder)
        self.config_folder = os.path.realpath(config_folder)
        if not os.path.exists(self.config_folder):
            os.makedirs(self.config_folder)
        log.debug("nxdrive configured in '%s'", self.config_folder)

        if echo is None:
            echo = os.environ.get('NX_DRIVE_LOG_SQL', None) is not None

        # Handle connection to the local Nuxeo Drive configuration and
        # metadata sqlite database.
        self._engine, self._session_maker = init_db(
            self.config_folder, echo=echo, poolclass=poolclass)

        # Make it possible to pass an arbitrary nuxeo client factory
        # for testing
        if nuxeo_client_factory is not None:
            self.nuxeo_client_factory = nuxeo_client_factory
        else:
            self.nuxeo_client_factory = NuxeoClient

        self._local = local()
        self._remote_error = None
        self.device_id = self.get_device_config().device_id
        self.synchronizer = Synchronizer(self)

    def get_session(self):
        """Reuse the thread local session for this controller

        Using the controller in several thread should be thread safe as long as
        this method is always called to fetch the session instance.
        """
        return self._session_maker()

    def get_device_config(self, session=None):
        """Fetch the singleton configuration object for this device"""
        if session is None:
            session = self.get_session()
        try:
            return session.query(DeviceConfig).one()
        except NoResultFound:
            device_config = DeviceConfig()  # generate a unique device id
            session.add(device_config)
            session.commit()
            return device_config

    def stop(self):
        """Stop the Nuxeo Drive synchronization thread

        As the process asking the synchronization to stop might not be the as
        the process runnning the synchronization (especially when used from the
        commandline without the graphical user interface and its tray icon
        menu) we use a simple empty marker file a cross platform way to pass
        the stop message between the two.

        """
        pid = self.synchronizer.check_running(process_name="sync")
        if pid is not None:
            # Create a stop file marker for the running synchronization
            # process
            log.info("Telling synchronization process %d to stop." % pid)
            stop_file = os.path.join(self.config_folder, "stop_%d" % pid)
            open(stop_file, 'wb').close()
        else:
            log.info("No running synchronization process to stop.")

    def children_states(self, folder_path, full_states=False):
        """List the status of the children of a folder

        The state of the folder is a summary of their descendant rather
        than their own instric synchronization step which is of little
        use for the end user.

        If full is True the full state object is returned instead of just the
        local path.
        """
        session = self.get_session()
        server_binding = self.get_server_binding(folder_path, session=session)
        if server_binding is not None:
            # TODO: if folder_path is the top level Nuxeo Drive folder, list
            # all the root binding states
            raise NotImplementedError(
                "Children States of a server binding is not yet implemented")

        # Find the root binding for this absolute path
        binding, path = self._binding_path(folder_path, session=session)

        try:
            folder_state = session.query(LastKnownState).filter_by(
                local_root=binding.local_root,
                path=path,
            ).one()
        except NoResultFound:
            return []

        states = self._pair_states_recursive(binding.local_root, session,
                                             folder_state)
        if full_states:
            return [(s, pair_state) for s, pair_state in states
                    if (s.parent_path == path
                        or s.remote_parent_ref == folder_state.remote_ref)]

        return [(s.path, pair_state) for s, pair_state in states
                if s.path is not None and s.parent_path == path]

    def _pair_states_recursive(self, local_root, session, doc_pair):
        """Recursive call to collect pair state under a given location."""
        if not doc_pair.folderish:
            return [(doc_pair, doc_pair.pair_state)]

        if doc_pair.path is not None and doc_pair.remote_ref is not None:
            f = or_(
                LastKnownState.parent_path == doc_pair.path,
                LastKnownState.remote_parent_ref == doc_pair.remote_ref,
            )
        elif doc_pair.path is not None:
            f = LastKnownState.parent_path == doc_pair.path
        elif doc_pair.remote_ref is not None:
            f = LastKnownState.remote_parent_ref == doc_pair.remote_ref
        else:
            raise ValueError("Illegal state %r: at least path or remote_ref"
                             " should be not None." % doc_pair)

        children_states = session.query(LastKnownState).filter_by(
            local_root=local_root).filter(f).order_by(
                asc(LastKnownState.local_name),
                asc(LastKnownState.remote_name),
            ).all()

        results = []
        for child_state in children_states:
            sub_results = self._pair_states_recursive(
                local_root, session, child_state)
            results.extend(sub_results)

        # A folder stays synchronized (or unknown) only if all the descendants
        # are themselfves synchronized.
        pair_state = doc_pair.pair_state
        for _, sub_pair_state in results:
            if sub_pair_state != 'synchronized':
                pair_state = 'children_modified'
            break
        # Pre-pend the folder state to the descendants
        return [(doc_pair, pair_state)] + results

    def _binding_path(self, folder_path, session=None):
        """Find a root binding and relative path for a given FS path"""
        folder_path = os.path.abspath(folder_path)

        # Check exact root binding match
        binding = self.get_root_binding(folder_path, session=session)
        if binding is not None:
            return binding, '/'

        # Check for root bindings that are prefix of folder_path
        session = self.get_session()
        all_root_bindings = session.query(RootBinding).all()
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
        path = path.replace(os.path.sep, '/')
        return binding, path

    def get_server_binding(self, local_folder, raise_if_missing=False,
                           session=None):
        """Find the ServerBinding instance for a given local_folder"""
        if session is None:
            session = self.get_session()
        try:
            return session.query(ServerBinding).filter(
                ServerBinding.local_folder == local_folder).one()
        except NoResultFound:
            if raise_if_missing:
                raise RuntimeError(
                    "Folder '%s' is not bound to any Nuxeo server"
                    % local_folder)
            return None

    def list_server_bindings(self, session=None):
        if session is None:
            session = self.get_session()
        return session.query(ServerBinding).all()

    def bind_server(self, local_folder, server_url, username, password):
        """Bind a local folder to a remote nuxeo server"""
        session = self.get_session()
        local_folder = os.path.abspath(os.path.expanduser(local_folder))

        # check the connection to the server by issuing an authentication
        # request
        server_url = self._normalize_url(server_url)
        nxclient = self.nuxeo_client_factory(server_url, username, self.device_id,
                                             password)
        token = nxclient.request_token()
        if token is not None:
            # The server supports token based identification: do not store the
            # password in the DB
            password = None
        try:
            server_binding = session.query(ServerBinding).filter(
                ServerBinding.local_folder == local_folder).one()
            if (server_binding.remote_user != username
                or server_binding.server_url != server_url):
                raise RuntimeError(
                    "%s is already bound to '%s' with user '%s'" % (
                        local_folder, server_binding.server_url,
                        server_binding.remote_user))

            if token is None and server_binding.remote_password != password:
                # Update password info if required
                server_binding.remote_password = password
                log.info("Updating password for user '%s' on server '%s'",
                        username, server_url)

            if token is not None and server_binding.remote_token != token:
                log.info("Updating token for user '%s' on server '%s'",
                        username, server_url)
                # Update the token info if required
                server_binding.remote_token = token

                # Ensure that the password is not stored in the DB
                if server_binding.remote_password is not None:
                    server_binding.remote_password = None

        except NoResultFound:
            log.info("Binding '%s' to '%s' with account '%s'",
                     local_folder, server_url, username)
            session.add(ServerBinding(local_folder, server_url, username,
                                      remote_password=password,
                                      remote_token=token))

        # Create the local folder to host the synchronized files: this
        # is useless as long as bind_root is not called
        if not os.path.exists(local_folder):
            os.makedirs(local_folder)

        session.commit()

    def unbind_server(self, local_folder):
        """Remove the binding to a Nuxeo server

        Local files are not deleted"""
        session = self.get_session()
        local_folder = os.path.abspath(os.path.expanduser(local_folder))
        binding = self.get_server_binding(local_folder, raise_if_missing=True,
                                          session=session)
        log.info("Unbinding '%s' from '%s' with account '%s'",
                 local_folder, binding.server_url, binding.remote_user)
        session.delete(binding)
        session.commit()

    def get_root_binding(self, local_root, raise_if_missing=False,
                         session=None):
        """Find the RootBinding instance for a given local_root

        It is the responsability of the caller to commit any change in
        the same thread if needed.
        """
        local_root = os.path.abspath(os.path.expanduser(local_root))
        if session is None:
            session = self.get_session()
        try:
            return session.query(RootBinding).filter(
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
        session = self.get_session()
        local_folder = os.path.abspath(os.path.expanduser(local_folder))
        server_binding = self.get_server_binding(local_folder,
                                                 raise_if_missing=True,
                                                 session=session)

        # Check the remote root exists and is an editable folder by current
        # user.
        try:
            nxclient = self.get_remote_client(server_binding,
                                              repository=repository,
                                              base_folder=remote_root)
            remote_info = nxclient.get_info('/', fetch_parent_uid=False)
        except NotFound:
            remote_info = None
        if remote_info is None or not remote_info.folderish:
            raise RuntimeError(
                'No folder at "%s:%s" visible by "%s" on server "%s"'
                % (repository, remote_root, server_binding.remote_user,
                   server_binding.server_url))

        if not nxclient.check_writable(remote_root):
            raise RuntimeError(
                'Folder at "%s:%s" is not editable by "%s" on server "%s"'
                % (repository, remote_root, server_binding.remote_user,
                   server_binding.server_url))


        if nxclient.is_addon_installed():
            # register the root on the server
            nxclient.register_as_root(remote_info.uid)
            self.synchronizer.update_roots(session,
                    server_binding=server_binding,
                    repository=repository)
        else:
            # manual local-only bounding: the server is not aware of any root
            # config
            self._local_bind_root(server_binding, remote_info, nxclient,
                                  session)

    def _local_bind_root(self, server_binding, remote_info, nxclient, session):
        # Check that this workspace does not already exist locally
        # TODO: shall we handle deduplication for root names too?
        local_root = os.path.join(server_binding.local_folder,
                                  safe_filename(remote_info.name))
        repository = nxclient.repository
        if not os.path.exists(local_root):
            os.makedirs(local_root)
        lcclient = LocalClient(local_root)
        local_info = lcclient.get_info('/')

        try:
            existing_binding = session.query(RootBinding).filter_by(
                local_root=local_root,
            ).one()
            if (existing_binding.remote_repo != repository
                or existing_binding.remote_root != remote_info.uid):
                raise RuntimeError(
                    "%r is already bound to %r on repo %r of %r" % (
                        local_root,
                        existing_binding.remote_root,
                        existing_binding.remote_repo,
                        existing_binding.server_binding.server_url))
        except NoResultFound:
            # Register the new binding itself
            log.info("Binding local root '%s' to '%s' (id=%s) on server '%s'",
                 local_root, remote_info.name, remote_info.uid,
                     server_binding.server_url)
            session.add(RootBinding(local_root, repository, remote_info.uid))

            # Initialize the metadata info by recursive walk on the remote
            # folder structure
            self._recursive_init(lcclient, local_info, nxclient, remote_info)
        session.commit()

    def _recursive_init(self, local_client, local_info, remote_client,
                        remote_info):
        """Initialize the metadata table by walking the binding tree"""

        folderish = remote_info.folderish
        state = LastKnownState(local_client.base_folder,
                               local_info=local_info,
                               remote_info=remote_info)
        if folderish:
            # Mark as synchronized as there is nothing to download later
            state.update_state(local_state='synchronized',
                               remote_state='synchronized')
        else:
            # Mark remote as updated to trigger a download of the binary
            # attachment during the next synchro
            state.update_state(local_state='synchronized',
                               remote_state='modified')
        session = self.get_session()
        session.add(state)

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

    def unbind_root(self, local_root, session=None):
        """Remove binding on a root folder"""
        local_root = os.path.abspath(os.path.expanduser(local_root))
        if session is None:
            session = self.get_session()
        binding = self.get_root_binding(local_root, raise_if_missing=True,
                                        session=session)

        nxclient = self.get_remote_client(binding.server_binding,
                                          repository=binding.remote_repo,
                                          base_folder=binding.remote_root)
        if nxclient.is_addon_installed():
            # register the root on the server
            nxclient.unregister_as_root(binding.remote_root)
            self.synchronizer.update_roots(session=session,
                    server_binding=binding.server_binding,
                    repository=binding.remote_repo)
        else:
            # manual bounding: the server is not aware
            self._local_unbind_root(binding, session)

    def _local_unbind_root(self, binding, session):
        log.info("Unbinding local root '%s'.", binding.local_root)
        session.delete(binding)
        session.commit()

    def update_server_roots(self, server_binding, session, local_roots,
            remote_roots, repository):
        """Align the roots for a given server and repository"""
        local_roots_by_id = dict((r.remote_root, r) for r in local_roots)
        local_root_ids = set(local_roots_by_id.keys())

        remote_roots_by_id = dict((r.uid, r) for r in remote_roots)
        remote_root_ids = set(remote_roots_by_id.keys())

        to_remove = local_root_ids - remote_root_ids
        to_add = remote_root_ids - local_root_ids

        for ref in to_remove:
            self._local_unbind_root(local_roots_by_id[ref], session)

        for ref in to_add:
            # get a client with the right base folder
            rc = self.get_remote_client(server_binding,
                                        repository=repository,
                                        base_folder=ref)
            self._local_bind_root(server_binding, remote_roots_by_id[ref],
                                  rc, session)

    def list_pending(self, limit=100, local_root=None, session=None):
        """List pending files to synchronize, ordered by path

        Ordering by path makes it possible to synchronize sub folders content
        only once the parent folders have already been synchronized.
        """
        if session is None:
            session = self.get_session()
        if local_root is not None:
            return session.query(LastKnownState).filter(
                LastKnownState.pair_state != 'synchronized',
                LastKnownState.local_root == local_root
            ).order_by(
                asc(LastKnownState.path),
                asc(LastKnownState.remote_path),
            ).limit(limit).all()
        else:
            return session.query(LastKnownState).filter(
                LastKnownState.pair_state != 'synchronized'
            ).order_by(
                asc(LastKnownState.path),
                asc(LastKnownState.remote_path),
            ).limit(limit).all()

    def next_pending(self, local_root=None, session=None):
        """Return the next pending file to synchronize or None"""
        pending = self.list_pending(limit=1, local_root=local_root,
                                    session=session)
        return pending[0] if len(pending) > 0 else None

    def _get_client_cache(self):
        if not hasattr(self._local, 'remote_clients'):
            self._local.remote_clients = dict()
        return self._local.remote_clients

    def get_remote_client(self, server_binding, base_folder=None,
                          repository='default'):
        cache = self._get_client_cache()
        sb = server_binding
        cache_key = (sb.server_url, sb.remote_user, self.device_id, base_folder,
                     repository)
        remote_client = cache.get(cache_key)

        if remote_client is None:
            remote_client = self.nuxeo_client_factory(
                sb.server_url, sb.remote_user, self.device_id,
                token=sb.remote_token, password=sb.remote_password,
                base_folder=base_folder, repository=repository)
            cache[cache_key] = remote_client
        # Make it possible to have the remote client simulate any kind of
        # failure
        remote_client.make_raise(self._remote_error)
        return remote_client

    def invalidate_client_cache(self, server_url):
        cache = self._get_client_cache()
        for key, client in cache.items():
            if client.server_url == server_url:
                del cache[key]

    def get_state(self, server_url, remote_repo, remote_ref):
        """Find a pair state for the provided remote document identifiers."""
        server_url = self._normalize_url(server_url)
        session = self.get_session()
        try:
            states = session.query(LastKnownState).filter_by(
                remote_ref=remote_ref,
            ).all()
            for state in states:
                rb = state.root_binding
                sb = rb.server_binding
                if (sb.server_url == server_url
                    and rb.remote_repo == remote_repo):
                    return state
        except NoResultFound:
            return None

    def launch_file_editor(self, server_url, remote_repo, remote_ref):
        """Find the local file if any and start OS editor on it."""
        state = self.get_state(server_url, remote_repo, remote_ref)
        if state is None:
            # TODO: synchronize to a dedicated special root for one time edit
            # TODO: find a better exception
            log.warning('Could not find local file for %s/nxdoc/%s/%s'
                    '/view_documents', server_url, remote_repo, remote_ref)
            return

        # TODO: synchronize this state first

        # Find the best editor for the file according to the OS configuration
        file_path = state.get_local_abspath()
        self.open_local_file(file_path)

    def open_local_file(self, file_path):
        """Launch the local operating system program on the given file / folder."""
        log.debug('Launching editor on %s', file_path)
        if sys.platform == 'win32':
            os.startfile(file_path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', file_path])
        else:
            try:
                subprocess.Popen(['xdg-open', file_path])
            except OSError:
                # xdg-open should be supported by recent Gnome, KDE, Xfce
                log.error("Failed to find and editor for: '%s'", file_path)

    def make_remote_raise(self, error):
        """Helper method to simulate network failure for testing"""
        self._remote_error = error

    def dispose(self):
        """Release all database resources"""
        self.get_session().close_all()
        self._engine.pool.dispose()

    def _normalize_url(self, url):
        """Ensure that user provided url always has a trailing '/'"""
        if url is None or not url:
            raise ValueError("Invalid url: %r" % url)
        if not url.endswith('/'):
            return url + '/'
        return url
