"""API to access local resources for synchronization."""

from datetime import datetime
import hashlib
import os
import shutil
import re
from nxdrive.logging_config import get_logger
from nxdrive.client.common import NotFound
from nxdrive.client.common import DEFAULT_IGNORED_PREFIXES
from nxdrive.client.common import DEFAULT_IGNORED_SUFFIXES
from nxdrive.utils import normalized_path
from nxdrive.utils import safe_long_path
from nxdrive.client.common import BUFFER_SIZE


log = get_logger(__name__)


DEDUPED_BASENAME_PATTERN = r'^(.*)__(\d{1,3})$'


def safe_filename(name, replacement='-'):
    """Replace invalid character in candidate filename"""
    return re.sub(r'(/|\\|\*|:)', replacement, name)


# Data transfer objects

class FileInfo(object):
    """Data Transfer Object for file info on the Local FS"""

    def __init__(self, root, path, folderish, last_modification_time,
                 digest_func='md5'):
        self.root = root  # the sync root folder local path
        self.path = path  # the truncated path (under the root)
        self.folderish = folderish  # True if a Folder

        # Last OS modification date of the file
        self.last_modification_time = last_modification_time

        # Function to use
        self._digest_func = digest_func.lower()

        # Precompute base name once and for all are it's often useful in
        # practice
        self.name = os.path.basename(path)

        self.filepath = os.path.join(
            root, path[1:].replace('/', os.path.sep))

    def get_digest(self):
        """Lazy computation of the digest"""
        if self.folderish:
            return None
        digester = getattr(hashlib, self._digest_func, None)
        if digester is None:
            raise ValueError('Unknow digest method: ' + self.digest_func)

        h = digester()
        with open(safe_long_path(self.filepath), 'rb') as f:
            while True:
                buffer = f.read(BUFFER_SIZE)
                if buffer == '':
                    break
                h.update(buffer)
        return h.hexdigest()


class LocalClient(object):
    """Client API implementation for the local file system"""

    # TODO: initialize the prefixes and suffix with a dedicated Nuxeo
    # Automation operations fetched at controller init time.

    def __init__(self, base_folder, digest_func='md5', ignored_prefixes=None,
                 ignored_suffixes=None):
        if ignored_prefixes is not None:
            self.ignored_prefixes = ignored_prefixes
        else:
            self.ignored_prefixes = DEFAULT_IGNORED_PREFIXES

        if ignored_suffixes is not None:
            self.ignored_suffixes = ignored_suffixes
        else:
            self.ignored_suffixes = DEFAULT_IGNORED_SUFFIXES

        while len(base_folder) > 1 and base_folder.endswith(os.path.sep):
            base_folder = base_folder[:-1]
        self.base_folder = base_folder
        self._digest_func = digest_func

    # Getters
    def get_info(self, ref, raise_if_missing=True):
        os_path = self._abspath(ref)
        if not os.path.exists(os_path):
            if raise_if_missing:
                raise NotFound("Could not found file '%s' under '%s'" % (
                ref, self.base_folder))
            else:
                return None
        folderish = os.path.isdir(os_path)
        stat_info = os.stat(os_path)
        mtime = datetime.fromtimestamp(stat_info.st_mtime)
        path = '/' + os_path[len(safe_long_path(self.base_folder)) + 1:]
        path = path.replace(os.path.sep, '/')  # unix style path
        # On unix we could use the inode for file move detection but that won't
        # work on Windows. To reduce complexity of the code and the possibility
        # to have Windows specific bugs, let's not use the unix inode at all.
        # uid = str(stat_info.st_ino)
        return FileInfo(self.base_folder, path, folderish, mtime,
                        digest_func=self._digest_func)

    def get_content(self, ref):
        return open(self._abspath(ref), "rb").read()

    def get_children_info(self, ref):
        os_path = self._abspath(ref)
        result = []
        children = os.listdir(os_path)
        children.sort()
        for child_name in children:
            ignore = False

            for suffix in self.ignored_suffixes:
                if child_name.endswith(suffix):
                    ignore = True
                    break

            for prefix in self.ignored_prefixes:
                if child_name.startswith(prefix):
                    ignore = True
                    break

            if not ignore:
                if ref == '/':
                    child_ref = ref + child_name
                else:
                    child_ref = ref + '/' + child_name
                try:
                    result.append(self.get_info(child_ref))
                except (OSError, NotFound):
                    # the child file has been deleted in the mean time or while
                    # reading some of its attributes
                    pass

        return result

    def make_folder(self, parent, name):
        os_path, name = self._abspath_deduped(parent, name)
        os.mkdir(os_path)
        if parent == "/":
            return "/" + name
        return parent + "/" + name

    def make_file(self, parent, name, content=None):
        os_path, name = self._abspath_deduped(parent, name)
        with open(os_path, "wb") as f:
            if content:
                f.write(content)
        if parent == "/":
            return "/" + name
        return parent + "/" + name

    def update_content(self, ref, content):
        with open(self._abspath(ref), "wb") as f:
            f.write(content)

    def delete(self, ref):
        # TODO: add support the OS trash?
        os_path = self._abspath(ref)
        if os.path.isfile(os_path):
            os.unlink(os_path)
        elif os.path.isdir(os_path):
            shutil.rmtree(os_path)

    def exists(self, ref):
        os_path = self._abspath(ref)
        return os.path.exists(os_path)

    def check_writable(self, ref):
        os_path = self._abspath(ref)
        return os.access(os_path, os.W_OK)

    def rename(self, ref, new_name):
        """Rename a local file or folder

        Return the actualized info object.

        """
        if ref == '/':
            raise ValueError("Cannot rename the toplevel folder.")
        source_os_path = self._abspath(ref)
        parent = ref.rsplit('/', 1)[0]
        parent = '/' if parent == '' else parent
        target_os_path, new_name = self._abspath_deduped(parent, new_name)
        shutil.move(source_os_path, target_os_path)
        if parent == '/':
            new_ref = '/' + new_name
        else:
            new_ref = parent + "/" + new_name
        return self.get_info(new_ref)

    def move(self, ref, new_parent_ref):
        """Move a local file or folder into another folder

        Return the actualized info object.

        """
        if ref == '/':
            raise ValueError("Cannot move the toplevel folder.")
        source_os_path = self._abspath(ref)
        name = ref.rsplit('/', 1)[1]
        target_os_path, new_name = self._abspath_deduped(new_parent_ref, name)
        shutil.move(source_os_path, target_os_path)
        if new_parent_ref == '/':
            new_ref = '/' + new_name
        else:
            new_ref = new_parent_ref + "/" + new_name
        return self.get_info(new_ref)

    def _abspath(self, ref):
        """Absolute path on the operating system"""
        if not ref.startswith('/'):
            raise ValueError("LocalClient expects ref starting with '/'")
        path_suffix = ref[1:].replace('/', os.path.sep)
        path = normalized_path(os.path.join(self.base_folder, path_suffix))
        return safe_long_path(path)

    def _abspath_deduped(self, parent, orig_name):
        """Absolute path on the operating system with deduplicated names"""
        # make name safe by removing invalid chars
        name = safe_filename(orig_name)

        # decompose the name into actionable components
        name, suffix = os.path.splitext(name)

        for _ in range(1000):
            os_path = self._abspath(os.path.join(parent, name + suffix))
            if not os.path.exists(os_path):
                return os_path, name + suffix

            # the is a duplicated file, try to come with a new name
            m = re.match(DEDUPED_BASENAME_PATTERN, name)
            if m:
                short_name, increment = m.groups()
                name = "%s__%d" % (short_name, int(increment) + 1)
            else:
                name = name + '__1'

        raise ValueError("Failed to de-duplicate '%s' under '%s'" % (
            orig_name, parent))
