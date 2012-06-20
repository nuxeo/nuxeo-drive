"""Main API to perform Nuxeo Drive operations"""

import os.path
from nxdrive.client import NuxeoClient
from nxdrive.client import LocalClient
from nxdrive.model import get_session
from nxdrive.model import ServerBinding
from nxdrive.model import RootBinding
from nxdrive.model import LastKnownState

from sqlalchemy.orm.exc import NoResultFound


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

    def start(self):
        """Start the Nuxeo Drive daemon if not already started"""
        # TODO, see:
        # https://github.com/mozilla-services/circus/blob/master/circus/
        # circusd.py#L34

    def stop(self):
        """Stop the Nuxeo Drive daemon"""
        # TODO

    def status(self, files=()):
        """Fetch the status of some files

        If the list of files is empty, the status of the synchronization
        roots is returned.
        """
        # TODO
        return ()

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

    def bind_root(self, local_root, remote_repo, remote_root):
        """Bind local root to a remote root (folderish document in Nuxeo).

        local_root must be a direct sub-folder of a local_folder already
        bound to an existing Nuxeo server. If it does not exists, the local
        folder will be created.

        remote_root must be the IdRef or PathRef of an existing folderish
        document on the remote server bound to the local folder. The
        user account must have write access to that folder, otherwise
        a RuntimeError will be raised.
        """
        # Check that local_root is a subfolder of bound folder
        local_folder = os.path.abspath(os.path.join(local_root, '..'))
        server_binding = self.get_server_binding(local_folder,
                                                 raise_if_missing=True)

        # Check the remote root exists and is an editable folder by current
        # user.
        nxclient = self.nuxeo_client_factory(server_binding.server_url,
                                             server_binding.remote_user,
                                             server_binding.remote_password,
                                             repository=remote_repo,
                                             base_folder=remote_root)
        remote_info = nxclient.get_info(remote_root)
        if remote_info is None or not remote_info.folderish:
            raise RuntimeError(
                'No folder at "%s/%s" visible by "%s" on server "%s"'
                % (remote_repo, remote_root, server_binding.remote_user,
                   server_binding.server_url))

        if nxclient.check_writable(remote_root):
            raise RuntimeError(
                'Folder at "%s/%s" is not editable by "%s" on server "%s"'
                % (remote_repo, remote_root, server_binding.remote_user,
                   server_binding.remote_password))

        # Check that this workspace does not already exist locally
        if os.path.exists(local_root):
            raise RuntimeError(
                'Cannot initialize binding to existing local folder: %s'
                % local_root)

        os.makedirs(local_root)
        lcclient = LocalClient(local_root)
        local_info = lcclient.get_info('/')

        # Register the binding itself
        self.session.add(RootBinding(local_root, remote_repo, remote_root))

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
            state.local_state = 'synchronized'
            state.remote_state = 'synchronized'
        else:
            # Mark remote as updated to trigger a download of the binary
            # attachment during the next synchro
            state.remote_state = 'updated'

        self.session.add(state)

        if folderish:
            # TODO: how to handle the too many children case properly?
            # Shall we introduce some pagination or shall we raise an
            # exception if a folder contains too many children?
            children = remote_client.get_children_info(remote_info.uid)
            for child_remote_info in children:
                if child_remote_info.folderish:
                    child_local_path = local_client.make_folder(
                        local_info.path, child_remote_info.title)

                    child_local_info = local_client.get_info(child_local_path)
                else:
                    child_local_path = local_client.make_file(
                        local_client.path, child_remote_info.title)
                self._recursive_init(local_client, child_local_info,
                                     remote_client, child_local_info)

    def unbind_root(self, local_root):
        """Remove binding on a root folder"""
        binding = self.get_root_binding(local_root, raise_if_missing=True)
        self.session.delete(binding)
        self.session.commit()
