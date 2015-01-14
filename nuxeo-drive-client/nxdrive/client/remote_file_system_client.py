"""API to access a remote file system for synchronization."""

import unicodedata
from collections import namedtuple
from datetime import datetime
import os
from nxdrive.logging_config import get_logger
from nxdrive.client.common import NotFound
from nxdrive.client.base_automation_client import BaseAutomationClient
from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_PREFIX
from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_SUFFIX
from nxdrive.engine.activity import FileAction


log = get_logger(__name__)

# Data transfer objects

BaseRemoteFileInfo = namedtuple('RemoteFileInfo', [
    'name',  # title of the file (not guaranteed to be locally unique)
    'uid',   # id of the file
    'parent_uid',  # id of the parent file
    'path',  # abstract file system path: useful for ordering folder trees
    'folderish',  # True is can host children
    'last_modification_time',  # last update time
    'last_contributor',  # last contributor
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

    def get_info(self, fs_item_id, parent_fs_item_id=None,
                 raise_if_missing=True):
        fs_item = self.get_fs_item(fs_item_id,
                                   parent_fs_item_id=parent_fs_item_id)
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
        self.current_action = FileAction("Download", None,
                                        fs_item_info.name, 0)
        content, _ = self.do_get(download_url)
        self.end_action()
        return content

    def stream_content(self, fs_item_id, file_path, parent_fs_item_id=None):
        """Stream the binary content of a file system item to a tmp file

        Raises NotFound if file system item with id fs_item_id
        cannot be found
        """
        fs_item_info = self.get_info(fs_item_id,
                                     parent_fs_item_id=parent_fs_item_id)
        download_url = self.server_url + fs_item_info.download_url
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        file_out = os.path.join(file_dir, DOWNLOAD_TMP_FILE_PREFIX + file_name
                                + DOWNLOAD_TMP_FILE_SUFFIX)
        self.current_action = FileAction("Download", file_out, file_name, 0)
        _, tmp_file = self.do_get(download_url, file_out=file_out)
        self.end_action()
        return tmp_file

    def get_children_info(self, fs_item_id):
        children = self.execute("NuxeoDrive.GetChildren", id=fs_item_id)
        return [self.file_to_info(fs_item) for fs_item in children]

    def is_filtered(self, path):
        return False

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

    def update_content(self, fs_item_id, content, filename=None,
                       mime_type=None):
        """Update a document with the given content

        Creates a temporary file from the content then streams it.
        """
        file_path = self.make_tmp_file(content)
        if filename is None:
            filename = self.get_info(fs_item_id).name
        self.execute_with_blob_streaming('NuxeoDrive.UpdateFile',
            file_path, filename=filename, mime_type=mime_type,
            id=fs_item_id)

    def stream_update(self, fs_item_id, file_path, parent_fs_item_id=None,
                      filename=None):
        """Update a document by streaming the file with the given path"""
        self.execute_with_blob_streaming('NuxeoDrive.UpdateFile',
            file_path, filename=filename, id=fs_item_id,
            parentId=parent_fs_item_id)

    def delete(self, fs_item_id, parent_fs_item_id=None):
        self.execute("NuxeoDrive.Delete", id=fs_item_id,
                     parentId=parent_fs_item_id)

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
        last_contributor = fs_item.get('lastContributor')

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

        # Normalize using NFC to make the tests more intuitive
        name = fs_item['name']
        if name is not None:
            name = unicodedata.normalize('NFC', name)
        return RemoteFileInfo(
            name, fs_item['id'], fs_item['parentId'],
            fs_item['path'], folderish, last_update, last_contributor, digest, digest_algorithm,
            download_url, fs_item['canRename'], fs_item['canDelete'],
            can_update, can_create_child)

    #
    # API specific to the remote file system client
    #

    def get_fs_item(self, fs_item_id, parent_fs_item_id=None):
        return self.execute("NuxeoDrive.GetFileSystemItem", id=fs_item_id,
                            parentId=parent_fs_item_id)

    def get_top_level_children(self):
        return self.execute("NuxeoDrive.GetTopLevelChildren")

    def get_changes(self, last_root_definitions,
                        log_id=None, last_sync_date=None):
        if log_id:
            # If available, use last event log id as 'lowerBound' parameter
            # according to the new implementation of the audit change finder,
            # see https://jira.nuxeo.com/browse/NXP-14826.
            return self.execute('NuxeoDrive.GetChangeSummary',
                                lowerBound=log_id,
                                lastSyncActiveRootDefinitions=(
                                        last_root_definitions))
        else:
            # Use last sync date as 'lastSyncDate' parameter according to the
            # old implementation of the audit change finder.
            return self.execute('NuxeoDrive.GetChangeSummary',
                                lastSyncDate=last_sync_date,
                                lastSyncActiveRootDefinitions=(
                                                last_root_definitions))
