"""Uniform API to access both local and remote resource for synchronization."""

import shutil
import os
from datetime import datetime


class Info(object):
    """Data transfer object representing the state in one tree"""

    def __init__(self, local_root, path, uid, type, mtime, digest=None):
        self.local_root
        self.path = path
        self.uid = uid
        self.type = type
        self.mtime = mtime
        self.digest = digest

    def __repr__(self):
        return "Info(%r, %r, %r, %r, %r, %r)" % (
            self.local_root, self.path, self.uid, self.type, self.mtime,
            self.digest)

    def is_folderish(self):
        return self.type == 'folder'


# TODO: add support for the move operations

class LocalClient(object):
    """Client API implementation for the local file system"""

    def __init__(self, base_folder):
        self.base_folder = base_folder

    def authenticate(self):
        # TODO
        return True

    # Getters
    def get_state(self, path):
        os_path = os.path.join(self.base_folder, path)
        if not os.path.exists(os_path):
            return None
        if os.path.isdir(os_path):
            type = 'folder'
        else:
            type = 'file'
        stat_info = os.stat(os_path)
        mtime = datetime.fromtimestamp(stat_info.st_mtime)
        # On unix we could use the inode for file move detection but that won't
        # work on Windows. To reduce complexity of the code and the possibility
        # to have Windows specific bugs, let's not use the unixe inode at all.
        # uid = str(stat_info.st_ino)
        return Info(os_path[len(self.base_folder) + 1:], None, type, mtime)

    def get_content(self, path):
        return open(os.path.join(self.base_folder, path), "rb").read()

    def get_descendants(self, path=None):
        if path is None:
            os_path = self.base_folder
        else:
            os_path = os.path.join(self.base_folder, path)
        result = []
        for root, dirs, files in os.walk(os_path):
            for dir in dirs:
                if not dir.startswith('.'):
                    path = os.path.join(os_path, root, dir)
                    result.append(self.get_state(path))
            for file in files:
                if not file.startswith('.'):
                    path = os.path.join(os_path, root, file)
                    result.append(self.get_state(path))
        return result

    # Modifiers
    def mkdir(self, path):
        os.mkdir(os.path.join(self.base_folder, path))

    def mkfile(self, path, content=None):
        with open(os.path.join(self.base_folder, path), "wcb") as f:
            if content:
                f.write(content)

    def update(self, path, content):
        with open(os.path.join(self.base_folder, path), "wb") as f:
            f.write(content)

    def delete(self, path):
        os_path = os.path.join(self.base_folder, path)
        if os.path.isfile(os_path):
            os.unlink(os_path)
        elif os.path.isdir(os_path):
            shutil.rmtree(os_path)


class NuxeoClient(object):
    """Client for the Nuxeo Content Automation HTTP API"""

    def __init__(self, server_url, user_id, password, base_folder='/',
                 repo="default"):
        self.server_url = server_url
        self.user_id = user_id
        self.password = password
        self.base_folder = base_folder
        self.repo = repo

    def authenticate(self):
        # TODO
        return True

    def get_descendants(self, path=""):
        raise NotImplementedError()

    def get_state(self, path):
        raise NotImplementedError()

    def get_content(self, path):
        raise NotImplementedError()

    # Modifiers
    def mkdir(self, path):
        raise NotImplementedError()

    def mkfile(self, path, content=None):
        raise NotImplementedError()

    def update(self, path, content):
        raise NotImplementedError()

    def delete(self, path):
        raise NotImplementedError()

    #
    # Utilities
    #

    def get_full_path(self, path):
        if path != "":
            return self.base_folder + "/" + path
        else:
            return self.base_folder
