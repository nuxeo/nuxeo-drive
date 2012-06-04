"""Main API to perform Nuxeo Drive operations"""

import os.path
from nxdrive.model import get_session
from nxdrive.model import ServerBinding
from nxdrive.model import RootBinding


class Controller(object):
    """Manage configuration and perform Nuxeo Drive Operations"""

    def __init__(self, config_folder, nuxeo_client_factory=None):
        self.config_folder = os.path.expanduser(config_folder)
        if not os.path.exists(self.config_folder):
            os.makedirs(self.config_folder)

        self.session = get_session(self.config_folder)
        # make it possible to pass an arbitrary nuxeo client factory
        # for testing
        self.nuxeo_client_factory = nuxeo_client_factory

    def start(self):
        """Start the Nuxeo Drive daemon"""
        # TODO

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

    def bind_server(self, local_folder, nuxeo_url, username, password):
        """Bind a local folder to a remote nuxeo server"""
        # TODO

    def bind_root(self, local_root, remote_root):
        """Bind local root to a remote root (folderish document in Nuxeo).

        local_root must be a direct sub-folder of a local_folder already
        bound to an existing Nuxeo server. If it does not exists, the local
        folder will be created.

        remote_root must be the IdRef or PathRef of an existing folderish
        document on the remote server bound to the local folder. The
        user account must have write access to that folder, otherwise
        a RuntimeError will be raised.
        """
