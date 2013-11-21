"""API to access a remote file system for synchronization."""

import unicodedata
from collections import namedtuple
from datetime import datetime
import urllib2
import os
from nxdrive.logging_config import get_logger
from nxdrive.client.common import NotFound
from nxdrive.client.common import FILE_BUFFER_SIZE
from nxdrive.client.base_automation_client import Unauthorized
from nxdrive.client.base_automation_client import BaseAutomationClient


log = get_logger(__name__)

DOWNLOAD_TMP_FILE_PREFIX = '.'
DOWNLOAD_TMP_FILE_SUFFIX = '.part'

# Data transfer objects

BaseRemoteFileInfo = namedtuple('RemoteFileInfo', [
    'name',  # title of the file (not guaranteed to be locally unique)
    'uid',   # id of the file
    'parent_uid',  # id of the parent file
    'path',  # abstract file system path: useful for ordering folder trees
    'folderish',  # True is can host children
    'last_modification_time',  # last update time
    'digest',  # digest of the file
    'digest_algorithm',  # digest algorithm of the file
    'download_url',  # download URL of the file
    'can_rename',  # True is can rename
    'can_delete',  # True is can delete
    'can_update',  # True is can update content
    'can_create_child',  # True is can create child
])


class RemoteFileInfo(BaseRemoteFileInfo):
    """Data Transfer Object for remote file info"""

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
        return self.file_to_info(fs_item)

    def get_filesystem_root_info(self):
        toplevel_folder = self.execute("NuxeoDrive.GetTopLevelFolder")
        return self.file_to_info(toplevel_folder)

    def get_content(self, fs_item_id):
        """Download and return the binary content of a file system item

        Beware that the content is loaded in memory.

        Raises NotFound if file system item with id fs_item_id
        cannot be found
        """
        fs_item_info = self.get_info(fs_item_id)
        download_url = self.server_url + fs_item_info.download_url
        content, _ = self._do_get(download_url)
        return content

    def stream_content(self, fs_item_id, file_path):
        """Stream the binary content of a file system item to a tmp file

        Raises NotFound if file system item with id fs_item_id
        cannot be found
        """
        fs_item_info = self.get_info(fs_item_id)
        download_url = self.server_url + fs_item_info.download_url
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        file_out = os.path.join(file_dir, DOWNLOAD_TMP_FILE_PREFIX + file_name
                                + DOWNLOAD_TMP_FILE_SUFFIX)
        _, tmp_file = self._do_get(download_url, file_out=file_out)
        return tmp_file

    def get_children_info(self, fs_item_id):
        children = self.execute("NuxeoDrive.GetChildren", id=fs_item_id)
        return [self.file_to_info(fs_item) for fs_item in children]

    def make_folder(self, parent_id, name):
        fs_item = self.execute("NuxeoDrive.CreateFolder",
            parentId=parent_id, name=name)
        return fs_item['id']

    def make_file(self, parent_id, name, content):
        """Create a document with the given name and content

        Creates a temporary file from the content then streams it.
        """
        file_path = self.make_tmp_file(content)
        fs_item = self.execute_with_blob_streaming("NuxeoDrive.CreateFile",
            file_path, filename=name, parentId=parent_id)
        return fs_item['id']

    def stream_file(self, parent_id, file_path, filename=None, mime_type=None):
        """Create a document by streaming the file with the given path"""
        fs_item = self.execute_with_blob_streaming("NuxeoDrive.CreateFile",
            file_path, filename=filename, mime_type=mime_type,
            parentId=parent_id)
        return fs_item['id']

    def update_content(self, fs_item_id, content, filename=None, mime_type=None):
        """Update a document with the given content

        Creates a temporary file from the content then streams it.
        """
        file_path = self.make_tmp_file(content)
        if filename is None:
            filename = self.get_info(fs_item_id).name
        self.execute_with_blob_streaming('NuxeoDrive.UpdateFile',
            file_path, filename=filename, mime_type=mime_type,
            id=fs_item_id)

    def stream_update(self, fs_item_id, file_path, filename=None):
        """Update a document by streaming the file with the given path"""
        self.execute_with_blob_streaming('NuxeoDrive.UpdateFile',
            file_path, filename=filename, id=fs_item_id)

    def delete(self, fs_item_id):
        self.execute("NuxeoDrive.Delete", id=fs_item_id)

    def exists(self, fs_item_id):
        return self.execute("NuxeoDrive.FileSystemItemExists", id=fs_item_id)

    # TODO
    def check_writable(self, fs_item_id):
        pass

    def rename(self, fs_item_id, new_name):
        return self.file_to_info(self.execute("NuxeoDrive.Rename",
            id=fs_item_id, name=new_name))

    def move(self, fs_item_id, new_parent_id):
        return self.file_to_info(self.execute("NuxeoDrive.Move",
            srcId=fs_item_id, destId=new_parent_id))

    def can_move(self, fs_item_id, new_parent_id):
        return self.execute("NuxeoDrive.CanMove", srcId=fs_item_id,
            destId=new_parent_id)

    def conflicted_name(self, original_name):
        """Generate a new name suitable for conflict deduplication."""
        return self.execute("NuxeoDrive.GenerateConflictedItemName",
            name=original_name)

    def file_to_info(self, fs_item):
        """Convert Automation file system item description to RemoteFileInfo"""
        folderish = fs_item['folder']
        milliseconds = fs_item['lastModificationDate']
        last_update = datetime.fromtimestamp(milliseconds // 1000)

        if folderish:
            digest = None
            digest_algorithm = None
            download_url = None
            can_update = False
            can_create_child = fs_item['canCreateChild']
        else:
            digest = fs_item['digest']
            digest_algorithm = fs_item['digestAlgorithm']
            download_url = fs_item['downloadURL']
            can_update = fs_item['canUpdate']
            can_create_child = False

        # Normalize using NFKC to make the tests more intuitive
        name = fs_item['name']
        if name is not None:
            name = unicodedata.normalize('NFKC', name)
        return RemoteFileInfo(
            name, fs_item['id'], fs_item['parentId'],
            fs_item['path'], folderish, last_update, digest, digest_algorithm,
            download_url, fs_item['canRename'], fs_item['canDelete'],
            can_update, can_create_child)

    def _do_get(self, url, file_out=None):
        headers = self._get_common_headers()
        base_error_message = (
            "Failed to connect to Nuxeo server %r with user %r"
        ) % (self.server_url, self.user_id)
        try:
            log.trace("Calling '%s' with headers: %r", url, headers)
            req = urllib2.Request(url, headers=headers)
            response = self.opener.open(req, timeout=self.blob_timeout)

            if file_out is not None:
                with open(file_out, "wb") as f:
                    while True:
                        # Check if synchronization thread was suspended
                        if self.check_suspended is not None:
                            self.check_suspended('File download: %s'
                                                 % file_out)
                        buffer_ = response.read(FILE_BUFFER_SIZE)
                        if buffer_ == '':
                            break
                        f.write(buffer_)
                    if self._remote_error is not None:
                        # Simulate a configurable remote (e.g. network or
                        # server) error for the tests
                        raise self._remote_error
                    if self._local_error is not None:
                        # Simulate a configurable local error (e.g. "No space
                        # left on device") for the tests
                        raise self._local_error
                return None, file_out
            else:
                return response.read(), None
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

    def get_top_level_children(self):
        return self.execute("NuxeoDrive.GetTopLevelChildren")

    def get_changes(self, last_sync_date=None, last_root_definitions=None):
        return self.execute(
            'NuxeoDrive.GetChangeSummary',
            lastSyncDate=last_sync_date,
            lastSyncActiveRootDefinitions=last_root_definitions)
