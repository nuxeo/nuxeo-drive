"""API to access local resources for synchronization."""

import unicodedata
from datetime import datetime
import hashlib
import os
import shutil
import re
import sys
from nxdrive.client.common import BaseClient

from nxdrive.logging_config import get_logger
from nxdrive.client.common import safe_filename
from nxdrive.client.common import NotFound
from nxdrive.client.common import DEFAULT_IGNORED_PREFIXES
from nxdrive.client.common import DEFAULT_IGNORED_SUFFIXES
from nxdrive.utils import normalized_path
from nxdrive.utils import safe_long_path
from nxdrive.client.common import FILE_BUFFER_SIZE
from send2trash import send2trash


log = get_logger(__name__)


DEDUPED_BASENAME_PATTERN = ur'^(.*)__(\d{1,3})$'


# Data transfer objects

class FileInfo(object):
    """Data Transfer Object for file info on the Local FS"""

    def __init__(self, root, path, folderish, last_modification_time,
                 digest_func='md5', check_suspended=None, remote_ref=None):

        # Function to check during long-running processing like digest
        # computation if the synchronization thread needs to be suspended
        self.check_suspended = check_suspended

        root = unicodedata.normalize('NFC', root)
        path = unicodedata.normalize('NFC', path)
        self.root = root  # the sync root folder local path
        self.path = path  # the truncated path (under the root)
        self.folderish = folderish  # True if a Folder
        self.remote_ref = remote_ref

        # Last OS modification date of the file
        self.last_modification_time = last_modification_time

        # Function to use
        self._digest_func = digest_func.lower()

        # Precompute base name once and for all are it's often useful in
        # practice
        self.name = os.path.basename(path)

        self.filepath = os.path.join(
            root, path[1:].replace(u'/', os.path.sep))

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
                # Check if synchronization thread was suspended
                if self.check_suspended is not None:
                    self.check_suspended('Digest computation: %s'
                                         % self.filepath)
                buffer_ = f.read(FILE_BUFFER_SIZE)
                if buffer_ == '':
                    break
                h.update(buffer_)
        return h.hexdigest()


class LocalClient(BaseClient):
    """Client API implementation for the local file system"""

    # TODO: initialize the prefixes and suffix with a dedicated Nuxeo
    # Automation operations fetched at controller init time.

    def __init__(self, base_folder, digest_func='md5', ignored_prefixes=None,
                 ignored_suffixes=None, check_suspended=None):
        self._case_sensitive = None
        # Function to check during long-running processing like digest
        # computation if the synchronization thread needs to be suspended
        self.check_suspended = check_suspended

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

    def is_case_sensitive(self):
        if self._case_sensitive is None:
            path = os.tempnam(self.base_folder, '.caseTest_')
            os.mkdir(path)
            if os.path.exists(path.upper()):
                self._case_sensitive = False
            else:
                self._case_sensitive = True
            os.rmdir(path)
        return self._case_sensitive

    def set_readonly(self, ref):
        path = self._abspath(ref)
        self.set_path_readonly(path)

    def unset_readonly(self, ref):
        path = self._abspath(ref)
        self.unset_path_readonly(path)

    def remove_remote_id(self, ref):
     # Can be move to another class
        path = self._abspath(ref)
        if sys.platform == 'win32':
            path = path + ":ndrive"
            with open(path, "w") as f:
                f.write("")
            pass
        else:
            import xattr
            xattr.removexattr(path, 'ndrive')

    def set_remote_id(self, ref, remote_id):
        # Can be move to another class
        path = self._abspath(ref)
        if sys.platform == 'win32':
            locker = self.unlock_path(path, False)
            pathAlt = path + ":ndrive"
            try:
                with open(pathAlt, "w") as f:
                    f.write(remote_id)
            except IOError as e:
                if e.errno == os.errno.EACCES:
                    self.unset_path_readonly(path)
                    with open(pathAlt, "w") as f:
                        f.write(remote_id)
                    self.set_path_readonly(path)
            finally:
                self.lock_path(path, locker)
        else:
            import xattr
            xattr.setxattr(path, 'ndrive', remote_id)

    def get_remote_id(self, ref):
        # Can be move to another class
        path = self._abspath(ref)
        if sys.platform == 'win32':
            path = path + ":ndrive"
            try:
                with open(path, "r") as f:
                    return f.read()
            except:
                return None
        else:
            import xattr
            try:
                return xattr.getxattr(path, 'ndrive')
            except:
                return None

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
        mtime = datetime.utcfromtimestamp(stat_info.st_mtime)
        path = u'/' + os_path[len(safe_long_path(self.base_folder)) + 1:]
        path = path.replace(os.path.sep, u'/')  # unix style path
        remote_ref = self.get_remote_id(ref)
        # On unix we could use the inode for file move detection but that won't
        # work on Windows. To reduce complexity of the code and the possibility
        # to have Windows specific bugs, let's not use the unix inode at all.
        # uid = str(stat_info.st_ino)
        return FileInfo(self.base_folder, path, folderish, mtime,
                        digest_func=self._digest_func,
                        check_suspended=self.check_suspended,
                        remote_ref=remote_ref)

    def get_content(self, ref):
        return open(self._abspath(ref), "rb").read()

    def is_ignored(self, ref, child_name):
        ignore = False
        for suffix in self.ignored_suffixes:
            if child_name.endswith(suffix):
                ignore = True
                break
        for prefix in self.ignored_prefixes:
            if child_name.startswith(prefix):
                ignore = True
                break
        return ignore

    def get_children_ref(self, parent_ref, name):
        if parent_ref == u'/':
            return parent_ref + name
        else:
            return parent_ref + u'/' + name

    def get_children_info(self, ref):
        os_path = self._abspath(ref)
        result = []
        children = os.listdir(os_path)
        children.sort()
        for child_name in children:

            if not self.is_ignored(ref, child_name):
                child_ref = self.get_children_ref(ref, child_name)
                try:
                    result.append(self.get_info(child_ref))
                except (OSError, NotFound):
                    # the child file has been deleted in the mean time or while
                    # reading some of its attributes
                    pass

        return result

    def get_parent_ref(self, ref):
        if ref == '/':
            return None
        parent = ref.rsplit(u'/', 1)[0]
        if parent is None:
            parent = '/'
        return parent

    def unlock_ref(self, ref, unlock_parent=True):
        path = self._abspath(ref)
        return self.unlock_path(path, unlock_parent)

    def lock_ref(self, ref, locker):
        path = self._abspath(ref)
        return self.lock_path(path, locker)

    def make_folder(self, parent, name):
        locker = self.unlock_ref(parent, False)
        os_path, name = self._abspath_deduped(parent, name)
        try:
            os.mkdir(os_path)
            if parent == u"/":
                return u"/" + name
            return parent + u"/" + name
        finally:
            self.lock_ref(parent, locker)

    def make_file(self, parent, name, content=None):
        locker = self.unlock_ref(parent, False)
        os_path, name = self._abspath_deduped(parent, name)
        try:
            with open(os_path, "wb") as f:
                if content:
                    f.write(content)
            if parent == u"/":
                return u"/" + name
            return parent + u"/" + name
        finally:
            self.lock_ref(parent, locker)

    def get_new_file(self, parent, name):
        os_path, name = self._abspath_deduped(parent, name)
        if parent == u"/":
            path = u"/" + name
        else:
            path = parent + u"/" + name
        return path, os_path, name

    def update_content(self, ref, content):
        with open(self._abspath(ref), "wb") as f:
            f.write(content)

    def delete(self, ref):
        locker = self.unlock_ref(ref)
        os_path = self._abspath(ref)
        if not self.exists(ref):
            return
        # Remove the \\?\ for SHFileOperation on win
        if os_path[:4] == '\\\\?\\':
            # http://msdn.microsoft.com/en-us/library/cc249520.aspx
            # SHFileOperation don't handle \\?\ paths
            if len(os_path) > 260:
                # Rename to the drive root
                info = self.move(ref, '/')
                new_ref = info.path
                try:
                    send2trash(self._abspath(new_ref)[4:])
                except:
                    log.debug('Cant use trash for ' + os_path
                                 + ', delete it')
                    self.delete_final(new_ref)
                return
            else:
                os_path = os_path[4:]
        log.trace('Send ' + os_path + ' to trash')
        try:
            send2trash(os_path)
        except:
            log.debug('Cant use trash for ' + os_path
                                 + ', delete it')
            self.delete_final(ref)
        finally:
            # Dont want to unlock the current deleted
            self.lock_ref(ref, locker & 2)

    def delete_final(self, ref):
        self.unset_readonly(ref)
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
        source_os_path = self._abspath(ref)
        parent = ref.rsplit(u'/', 1)[0]
        old_name = ref.rsplit(u'/', 1)[1]
        parent = u'/' if parent == '' else parent
        locker = self.unlock_ref(ref)
        try:
            # Check if only case renaming
            if (old_name != new_name and old_name.lower() == new_name.lower()
                and not self.is_case_sensitive()):
                # Must use a temp rename as FS is not case sensitive
                temp_path = os.tempnam(self._abspath(parent),
                                       '.ren_' + old_name + '_')
                if sys.platform == 'win32':
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(
                                                unicode(temp_path), 2)
                shutil.move(source_os_path, temp_path)
                source_os_path = temp_path
                # Try the os rename part
                target_os_path = self._abspath(os.path.join(parent, new_name))
            else:
                target_os_path, new_name = self._abspath_deduped(parent,
                                                                new_name, old_name)
            if old_name != new_name:
                shutil.move(source_os_path, target_os_path)
            if sys.platform == 'win32':
                import ctypes
                # See http://msdn.microsoft.com/en-us/library/aa365535%28v=vs.85%29.aspx
                ctypes.windll.kernel32.SetFileAttributesW(
                                            unicode(target_os_path), 128)
            new_ref = self.get_children_ref(parent, new_name)
            return self.get_info(new_ref)
        finally:
            self.lock_ref(ref, locker & 2)

    def move(self, ref, new_parent_ref):
        """Move a local file or folder into another folder

        Return the actualized info object.

        """
        if ref == u'/':
            raise ValueError("Cannot move the toplevel folder.")
        locker = self.unlock_ref(ref)
        new_locker = self.unlock_ref(new_parent_ref, False)
        source_os_path = self._abspath(ref)
        name = ref.rsplit(u'/', 1)[1]
        target_os_path, new_name = self._abspath_deduped(new_parent_ref, name)
        try:
            shutil.move(source_os_path, target_os_path)
            new_ref = self.get_children_ref(new_parent_ref, new_name)
            return self.get_info(new_ref)
        finally:
            self.lock_ref(ref, locker & 2)
            self.lock_ref(new_parent_ref, locker & 1 | new_locker)

    def get_path(self, abspath):
        """Relative path to the local client from an absolute OS path"""
        path = abspath.split(self.base_folder, 1)[1]
        return path.replace(os.path.sep, '/')

    def _abspath(self, ref):
        """Absolute path on the operating system"""
        if not ref.startswith(u'/'):
            raise ValueError("LocalClient expects ref starting with '/'")
        path_suffix = ref[1:].replace('/', os.path.sep)
        path = normalized_path(os.path.join(self.base_folder, path_suffix))
        return safe_long_path(path)

    def _abspath_safe(self, parent, orig_name):
        """Absolute path on the operating system with deduplicated names"""
        # make name safe by removing invalid chars
        name = safe_filename(orig_name)

        # decompose the name into actionable components
        name, suffix = os.path.splitext(name)
        os_path = self._abspath(os.path.join(parent, name + suffix))
        return os_path

    def _abspath_deduped(self, parent, orig_name, old_name=None):
        """Absolute path on the operating system with deduplicated names"""
        # make name safe by removing invalid chars
        name = safe_filename(orig_name)

        # decompose the name into actionable components
        name, suffix = os.path.splitext(name)

        for _ in range(1000):
            os_path = self._abspath(os.path.join(parent, name + suffix))
            if old_name == (name + suffix):
                return os_path, name + suffix
            if not os.path.exists(os_path):
                return os_path, name + suffix

            # the is a duplicated file, try to come with a new name
            m = re.match(DEDUPED_BASENAME_PATTERN, name)
            if m:
                short_name, increment = m.groups()
                name = u"%s__%d" % (short_name, int(increment) + 1)
            else:
                name = name + u'__1'

        raise ValueError("Failed to de-duplicate '%s' under '%s'" % (
            orig_name, parent))
