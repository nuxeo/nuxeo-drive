"""Common utilities for local and remote clients."""

import re
import os
import stat


class BaseClient(object):
    @staticmethod
    def set_path_readonly(path):
        if os.path.isdir(path):
            os.chmod(path, stat.S_IXUSR | stat.S_IRGRP |
                    stat.S_IXGRP | stat.S_IRUSR)
        else:
            os.chmod(path, stat.S_IRGRP | stat.S_IRUSR)

    @staticmethod
    def unset_path_readonly(path):
        if os.path.isdir(path):
            os.chmod(path, stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP |
                                stat.S_IRUSR | stat.S_IWGRP | stat.S_IWUSR)
        else:
            os.chmod(path, stat.S_IRGRP | stat.S_IRUSR |
                             stat.S_IWGRP | stat.S_IWUSR)

    def unlock_path(self, path, unlock_parent=True):
        result = 0
        if unlock_parent:
            parent_path = os.path.dirname(path)
            if (os.path.exists(parent_path) and
                not os.access(parent_path, os.W_OK)):
                self.unset_path_readonly(parent_path)
                result |= 2
        if os.path.exists(path) and not os.access(path, os.W_OK):
            self.unset_path_readonly(path)
            result |= 1
        return result

    def lock_path(self, path, locker):
        if locker == 0:
            return
        if locker & 1 == 1:
            self.set_path_readonly(path)
        if locker & 2 == 2:
            parent = os.path.dirname(path)
            self.set_path_readonly(parent)


class NotFound(Exception):
    pass

DEFAULT_REPOSITORY_NAME = 'default'

DEFAULT_IGNORED_PREFIXES = [
    '.',  # hidden Unix files
    '~$',  # Windows lock files
    'Thumbs.db',  # Thumbnails files
]

DEFAULT_IGNORED_SUFFIXES = [
    '~',  # editor buffers
    '.swp',  # vim swap files
    '.lock',  # some process use file locks
    '.LOCK',  # other locks
    '.part',  # partially downloaded files
]

# Default buffer size for file upload / download and digest computation
FILE_BUFFER_SIZE = 4096

# Name of the folder holding the files locally edited from Nuxeo
LOCALLY_EDITED_FOLDER_NAME = 'Locally Edited'

COLLECTION_SYNC_ROOT_FACTORY_NAME = 'collectionSyncRootFolderItemFactory'


def safe_filename(name, replacement=u'-'):
    """Replace invalid character in candidate filename"""
    return re.sub(ur'(/|\\|\*|:|\||"|<|>|\?)', replacement, name)
