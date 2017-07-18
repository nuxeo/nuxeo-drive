"""Common utilities for local and remote clients."""

import re
import os
import stat


class BaseClient(object):
    @staticmethod
    def set_path_readonly(path):
        current = os.stat(path).st_mode
        if os.path.isdir(path):
            # Need to add
            right = (stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IRUSR)
            if current & ~right == 0:
                return
            os.chmod(path, right)
        else:
            # Already in read only
            right = (stat.S_IRGRP | stat.S_IRUSR)
            if current & ~right == 0:
                return
            os.chmod(path, right)

    @staticmethod
    def unset_path_readonly(path):
        current = os.stat(path).st_mode
        if os.path.isdir(path):
            right = (stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP |
                                stat.S_IRUSR | stat.S_IWGRP | stat.S_IWUSR)
            if current & right == right:
                return
            os.chmod(path, right)
        else:
            right = (stat.S_IRGRP | stat.S_IRUSR |
                             stat.S_IWGRP | stat.S_IWUSR)
            if current & right == right:
                return
            os.chmod(path, right)

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


class DuplicationDisabledError(ValueError):
    """
    Exception raised when de-duplication is disabled and there is a
    file collision.
    """
    pass


class DuplicationError(IOError):
    """ Exception raised when a de-duplication fails. """
    pass


DEFAULT_BETA_SITE_URL = 'http://community.nuxeo.com/static/drive-tests/'
DEFAULT_REPOSITORY_NAME = 'default'

DEFAULT_IGNORED_PREFIXES = tuple({
    '.',  # hidden Unix files
    'Icon\r',  # macOS icon
    'Thumbs.db',  # Windows Thumbnails files
    'desktop.ini',  # Windows icon
    '~$',  # Windows lock files
})

DEFAULT_IGNORED_SUFFIXES = tuple({
    '.LOCK',  # other locks
    '.bak',  # temporary backup files
    '.crdownload',  # partially downloaded files by browsers
    '.lock',  # some process use file locks
    '.part',  # partially downloaded files by browsers
    '.partial',  # partially downloaded files by browsers
    '.swp',  # vim swap files
    '.tmp',  # temporary files (MS Office and others)
    '~',  # editor buffers
})

# Default buffer size for file upload / download and digest computation
FILE_BUFFER_SIZE = 1024 ** 2

# Name of the folder holding the files locally edited from Nuxeo
LOCALLY_EDITED_FOLDER_NAME = 'Locally Edited'

COLLECTION_SYNC_ROOT_FACTORY_NAME = 'collectionSyncRootFolderItemFactory'

UNACCESSIBLE_HASH = "TO_COMPUTE"

def safe_filename(name, replacement=u'-'):
    """Replace invalid character in candidate filename"""
    return re.sub(ur'(/|\\|\*|:|\||"|<|>|\?)', replacement, name)
