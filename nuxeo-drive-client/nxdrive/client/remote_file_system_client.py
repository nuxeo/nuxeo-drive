"""API to access a remote file system for synchronization."""

from collections import namedtuple
from datetime import datetime
import urllib2
from nxdrive.logging_config import get_logger
from nxdrive.client.common import NotFound
from nxdrive.client.common import BUFFER_SIZE
from nxdrive.client.base_automation_client import Unauthorized
from nxdrive.client.base_automation_client import BaseAutomationClient


log = get_logger(__name__)


# Data transfer objects

BaseRemoteFileInfo = namedtuple('RemoteFileInfo', [
    'name',  # title of the file (not guaranteed to be locally unique)
    'uid',   # id of the file
    'parent_uid',  # id of the parent file
    'folderish',  # True is can host children
    'last_modification_time',  # last update time
    'digest',  # digest of the file
    'digest_algorithm',  # digest algorithm of the file
    'download_url', # download URL of the file
])


class RemoteFileInfo(BaseRemoteFileInfo):
    """Data Transfer Object for remote file info"""

    # TODO: backward compatibility, to be removed
    root = '/'
    path = '/'
    repository = 'default'

    # Consistency with the local client API
    def get_digest(self):
        return self.digest


class RemoteFileSystemClient(BaseAutomationClient):
    """File system oriented Automation client

    Uses the FileSystemItem API.
    """

    #
    # API common with the local client API
    #

    def get_info(self, fs_item_id, raise_if_missing=True):
        fs_item = self.get_fs_item(fs_item_id)
        if fs_item is None:
            if raise_if_missing:
                raise NotFound("Could not find '%s' on '%s'" % (
                    fs_item_id, self.server_url))
            return None
        return self._file_to_info(fs_item)

    def get_content(self, fs_item_id, file_out=None):
        """Downloads the binary content of a file system item

        Raises NotFound if file system item with id fs_item_id
        cannot be found
        """

        fs_item_info = self.get_info(fs_item_id)
        download_url = self.server_url + fs_item_info.download_url
        return self._do_get(download_url, file_out=file_out)

    def get_children_info(self, fs_item_id):
        #TODO
        pass

    def make_folder(self, parent_id, name):
        fs_item = self.execute("NuxeoDrive.CreateFolder",
            id=parent_id, name=name)
        return fs_item['id']

    def make_file(self, parent_id, name, content):
        fs_item = self.execute_with_blob("NuxeoDrive.CreateFile",
            content, name, id=parent_id)
        return fs_item['id']

    def update_content(self, fs_item_id, content, name=None):
        #TODO
        pass

    def delete(self, fs_item_id):
        # TODO
        pass

    def exists(self, fs_item_id):
        return self.execute("NuxeoDrive.FileSystemItemExists", id=fs_item_id)

    # TODO: probably to be replaced by
    # can_rename, can_update, can_delete, can_create_child
    def check_writable(self, fs_item_id):
        # TODO
        pass

    def _file_to_info(self, fs_item):
        """Convert Automation file system item description to RemoteFileInfo"""
        folderish = fs_item['folder']
        # TODO: fix: lastModificationDate is a long value
#        try:
#            last_update = datetime.strptime(fs_item['lastModificationDate'],
#                                            "%Y-%m-%dT%H:%M:%S.%fZ")
#        except ValueError:
#            # no millisecond?
#            last_update = datetime.strptime(fs_item['lastModificationDate'],
#                                            "%Y-%m-%dT%H:%M:%SZ")
        last_update = datetime.now()

        if folderish:
            digest = None
            digest_algorithm = None
            download_url = None
        else:
            digest = fs_item['digest']
            digest_algorithm = fs_item['digestAlgorithm']
            download_url = fs_item['downloadURL']

        return RemoteFileInfo(
            fs_item['name'], fs_item['id'], fs_item['parentId'],
            folderish, last_update, digest, digest_algorithm, download_url)

    def _do_get(self, url, file_out=None):
        if self._error is not None:
            # Simulate a configurable (e.g. network or server) error for the
            # tests
            raise self._error

        headers = self._get_common_headers()
        base_error_message = (
            "Failed to connect to Nuxeo server %r with user %r"
        ) % (self.server_url, self.user_id)
        try:
            log.trace("Calling '%s' with headers: %r", url, headers)
            req = urllib2.Request(url, headers=headers)
            response = self.opener.open(req)
            if hasattr(file_out, "write"):
                while True:
                    buffer_ = response.read(BUFFER_SIZE)
                    if buffer_ == '':
                        break
                    file_out.write(buffer_)
            else:
                return response.read()
        except urllib2.HTTPError as e:
            if e.code == 401 or e.code == 403:
                raise Unauthorized(self.server_url, self.user_id, e.code)
            else:
                e.msg = base_error_message + ": HTTP error %d" % e.code
                raise e
        except Exception as e:
            if hasattr(e, 'msg'):
                e.msg = base_error_message + ": " + e.msg
            raise

    #
    # API specific to the remote file system client
    #

    def get_fs_item(self, fs_item_id):
        return self.execute("NuxeoDrive.GetFileSystemItem", id=fs_item_id)
