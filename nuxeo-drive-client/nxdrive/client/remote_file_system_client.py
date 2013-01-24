"""API to access a remote file system for synchronization."""

from collections import namedtuple
from nxdrive.logging_config import get_logger
from nxdrive.client.base_automation_client import BaseAutomationClient


log = get_logger(__name__)


# Data transfer objects

BaseRemoteFileInfo = namedtuple('RemoteFileInfo', [
    'name',  # title of the item (not guaranteed to be locally unique)
    'uid',   # id of the item
    'parent_uid',  # id of the parent item
    'folderish',  # True is can host child documents
    'last_modification_time',  # last update time
    'digest',  # digest of the document
])


class RemoteFileInfo(BaseRemoteFileInfo):
    """Data Transfer Object for remote file info"""

    # TODO: backward compatibility, to be removed
    root = '/'
    path = '/'
    repository = 'default'

    def get_digest(self):
        return self.digest


class RemoteFileSystemClient(BaseAutomationClient):
    """File system oriented Automation client

    Uses the FileSystemItem API.
    """

    #
    # API common with the local client API
    #

    def get_info(self, file_id, raise_if_missing=True):
        #TODO
        pass

    def get_content(self, file_id):
        #TODO
        pass

    def get_children_info(self, file_id):
        #TODO
        pass

    def make_folder(self, parent, name):
        # TODO
        pass

    def make_file(self, parent, name, content=None):
        # TODO
        pass

    def update_content(self, file_id, content, name=None):
        #TODO
        pass

    def delete(self, file_id, use_trash=True):
        # TODO
        pass

    def exists(self, file_id, use_trash=True):
        #TODO
        pass

    def check_writable(self, file_id):
        # TODO: which operation can be used to perform a permission check?
        return True
