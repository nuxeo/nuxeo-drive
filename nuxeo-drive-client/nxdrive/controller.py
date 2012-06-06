"""Main API to perform Nuxeo Drive operations"""

import os.path
from nxdrive.model import get_session
from nxdrive.model import ServerBinding
from nxdrive.model import RootBinding

from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound


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

    def bind_server(self, local_folder, server_url, username, password):
        """Bind a local folder to a remote nuxeo server"""
        try:
            server_binding = self.session.query(ServerBinding).filter(
                ServerBinding.local_folder == local_folder).one()
            raise RuntimeError(
                "%s is already bound to '%s' with user '%s'" % (
                    local_folder, server_binding.remote_host,
                    server_binding.remote_user))
        except NoResultFound:
            # this is expected in most cases
            pass
        except MultipleResultsFound:
            raise RuntimeError('There is more than one server binding for ' +
                               local_folder)

        self.session.add(ServerBinding(local_folder, server_url, username,
                                       password))
        self.session.commit()

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
        server_binding = None
        try:
            server_binding = self.session.query(ServerBinding).filter(
                ServerBinding.local_folder == local_folder).one()
        except NoResultFound:
            raise RuntimeError(
                ('Could not bind %s as a root as parent folder is not bound'
                 ' to any Nuxeo server') % local_root)
        except MultipleResultsFound:
            raise RuntimeError('There is more than one server binding for ' +
                               local_folder)

        # Check the remote root exists and is an editable folder by current
        # user.
        client = self.nuxeo_client_factory(server_binding.remote_host,
                                           server_binding.remote_user,
                                           server_binding.remote_password)
        if not client.is_valid_root(remote_repo, remote_root):
            raise RuntimeError(
                'No folder at "%s/%s" editable by "%s" on server "%s"'
                % (remote_repo, remote_root, server_binding.remote_user,
                   server_binding.remote_password))

        # Ensure that the local folder exists
        if os.path.exists(local_root):
            if not os.path.isdir(local_root):
                raise RuntimeError('%s is not a folder' % local_root)
        else:
            os.makedirs(local_root)

        # Check that remote_root exists on the matching server
        self.session.add(RootBinding(local_root, remote_repo, remote_root))
        self.session.commit()
