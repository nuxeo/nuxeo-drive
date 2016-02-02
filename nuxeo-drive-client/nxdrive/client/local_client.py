"""API to access local resources for synchronization."""

import unicodedata
from datetime import datetime
import hashlib
import os
import shutil
import re
import tempfile
from nxdrive.client.common import BaseClient, UNACCESSIBLE_HASH
from nxdrive.osi import AbstractOSIntegration

from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_PREFIX
from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_SUFFIX
from nxdrive.logging_config import get_logger
from nxdrive.client.common import safe_filename
from nxdrive.client.common import NotFound
from nxdrive.client.common import DEFAULT_IGNORED_PREFIXES
from nxdrive.client.common import DEFAULT_IGNORED_SUFFIXES
from nxdrive.utils import normalized_path
from nxdrive.utils import safe_long_path
from nxdrive.utils import guess_digest_algorithm
from nxdrive.client.common import FILE_BUFFER_SIZE
from send2trash import send2trash


log = get_logger(__name__)


DEDUPED_BASENAME_PATTERN = ur'^(.*)__(\d{1,3})$'


# Data transfer objects

class FileInfo(object):
    """Data Transfer Object for file info on the Local FS"""

    def __init__(self, root, path, folderish, last_modification_time, size=0,
                 digest_func='md5', check_suspended=None, remote_ref=None):

        # Function to check during long-running processing like digest
        # computation if the synchronization thread needs to be suspended
        self.check_suspended = check_suspended
        self.size = size
        filepath = os.path.join(root, path[1:].replace(u'/', os.path.sep))
        root = unicodedata.normalize('NFC', root)
        path = unicodedata.normalize('NFC', path)
        normalized_filepath = os.path.join(root, path[1:].replace(u'/', os.path.sep))
        self.filepath = normalized_filepath

        # Normalize name on the file system if not normalized
        # See https://jira.nuxeo.com/browse/NXDRIVE-188
        if os.path.exists(filepath) and normalized_filepath != filepath and not AbstractOSIntegration.is_mac():
            log.debug('Forcing normalization of %r to %r', filepath, normalized_filepath)
            os.rename(filepath, normalized_filepath)

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

    def __repr__(self):
        return self.__unicode__().encode('ascii', 'ignore')

    def __unicode__(self):
        return u"FileInfo[%s, remote_ref=%s]" % (self.filepath, self.remote_ref)

    def get_digest(self, digest_func=None):
        """Lazy computation of the digest"""
        if self.folderish:
            return None
        digest_func = digest_func if digest_func is not None else self._digest_func
        digester = getattr(hashlib, digest_func, None)
        if digester is None:
            raise ValueError('Unknow digest method: ' + digest_func)

        h = digester()
        try:
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
        except IOError:
            return UNACCESSIBLE_HASH
        return h.hexdigest()


class LocalClient(BaseClient):
    """Client API implementation for the local file system"""

    # TODO: initialize the prefixes and suffix with a dedicated Nuxeo
    # Automation operations fetched at manager init time.

    def __init__(self, base_folder, digest_func='md5', ignored_prefixes=None,
                    ignored_suffixes=None, check_suspended=None, case_sensitive=None, disable_duplication=False):
        self._case_sensitive = case_sensitive
        self._disable_duplication = disable_duplication
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
            lock = self.unlock_path(self.base_folder, unlock_parent=False)
            path = tempfile.mkdtemp(prefix='.caseTest_', dir=self.base_folder)
            if os.path.exists(path.upper()):
                self._case_sensitive = False
            else:
                self._case_sensitive = True
            os.rmdir(path)
            self.lock_path(self.base_folder, lock)
        return self._case_sensitive

    def is_temp_file(self, filename):
        return (filename.startswith(DOWNLOAD_TMP_FILE_PREFIX) and
                            filename.endswith(DOWNLOAD_TMP_FILE_SUFFIX))

    def set_readonly(self, ref):
        path = self._abspath(ref)
        self.set_path_readonly(path)

    def unset_readonly(self, ref):
        path = self._abspath(ref)
        self.unset_path_readonly(path)

    def clean_xattr_root(self):
        self.unlock_ref(u'/', unlock_parent=False)
        try:
            self.remove_root_id()
        except Exception as e:
            pass
        finally:
            pass
        self.clean_xattr_folder_recursive(u'/')

    def clean_xattr_folder_recursive(self, path):
        for child in self.get_children_info(path):
            locker = self.unlock_ref(child.path, unlock_parent=False)
            if child.remote_ref is not None:
                self.remove_remote_id(child.path)
            self.lock_ref(child.path, locker)
            if child.folderish:
                self.clean_xattr_folder_recursive(child.path)

    def remove_root_id(self):
        self.remove_remote_id('/', name='ndriveroot')

    def set_root_id(self, value):
        self.set_remote_id('/', value, name="ndriveroot")

    def get_root_id(self):
        return self.get_remote_id('/', name="ndriveroot")

    def remove_remote_id(self, ref, name='ndrive'):
        # Can be move to another class
        path = self._abspath(ref)
        log.trace('Removing xattr %s from %s', name, path)
        locker = self.unlock_path(path, False)
        if AbstractOSIntegration.is_windows():
            pathAlt = path + ":" + name
            try:
                if os.path.exists(pathAlt):
                    os.remove(pathAlt)
            except WindowsError as e:
                if e.errno == os.errno.EACCES:
                    self.unset_path_readonly(path)
                    os.remove(pathAlt)
                    self.set_path_readonly(path)
                else:
                    raise e
            finally:
                self.lock_path(path, locker)
        else:
            try:
                import xattr
                if AbstractOSIntegration.is_mac():
                    xattr.removexattr(path, name)
                else:
                    xattr.removexattr(path, 'user.' + name)
            except IOError as e:
                # Ignore IOError: [Errno 93] Attribute not found ( Mac )
                # IOError: [Errno 61] No data available ( Linux )
                if e.errno == 93 or e.errno == 61:
                    pass
                else:
                    raise
            finally:
                self.lock_path(path, locker)

    def unset_folder_icon(self, ref):
        '''
            Unset the red icon
        '''
        if AbstractOSIntegration.is_windows():
            # TODO Clean version
            desktop_ini_file_path = os.path.join(self._abspath(ref), "desktop.ini")
        if AbstractOSIntegration.is_mac():
            desktop_ini_file_path = os.path.join(self._abspath(ref), "Icon\r")
        if os.path.exists(desktop_ini_file_path):
            os.remove(desktop_ini_file_path)

    def has_folder_icon(self, ref):
        target_folder = self._abspath(ref)
        if AbstractOSIntegration.is_mac():
            meta_file = os.path.join(target_folder, "Icon\r")
            return os.path.exists(meta_file)
        if AbstractOSIntegration.is_windows():
            meta_file = os.path.join(target_folder, "desktop.ini")
            return os.path.exists(meta_file)
        return False

    def set_folder_icon(self, ref, icon):
        if AbstractOSIntegration.is_windows():
            self.set_folder_icon_win32(ref, icon)
        elif AbstractOSIntegration.is_mac():
            self.set_folder_icon_darwin(ref, icon)

    def set_folder_icon_win32(self, ref, icon):
        import win32con
        import win32api
        '''
            Configure red color icon for a folder Windows / Mac
        '''
        # Desktop.ini file content for Windows 7 and later.
        ini_file_content = """
        [.ShellClassInfo]
        IconResource=icon_file_path,0
        [ViewState]
        Mode=
        Vid=
        FolderType=Generic
        """
        # Desktop.ini file content for Windows XP.
        ini_file_content_xp = """
        [.ShellClassInfo]
        IconFile=icon_file_path
        IconIndex=0
        """
        if AbstractOSIntegration.os_version_below("5.2"):
            desktop_ini_content = ini_file_content_xp.replace("icon_file_path", icon)
        else:
            desktop_ini_content = ini_file_content.replace("icon_file_path", icon)

        # Create the desktop.ini file inside the ReadOnly shared folder.
        created_ini_file_path = os.path.join(self._abspath(ref), 'desktop.ini')
        attrib_command_path = self._abspath(ref)
        if not os.path.exists(created_ini_file_path):
            try:
                create_file = open(created_ini_file_path,'w')
                create_file.write(desktop_ini_content)
                create_file.close()
                win32api.SetFileAttributes(created_ini_file_path, win32con.FILE_ATTRIBUTE_SYSTEM)
                win32api.SetFileAttributes(created_ini_file_path, win32con.FILE_ATTRIBUTE_HIDDEN)
            except Exception as e:
                log.error("Exception when setting folder icon : %r", e)
        else:
            win32api.SetFileAttributes(created_ini_file_path, win32con.FILE_ATTRIBUTE_SYSTEM)
            win32api.SetFileAttributes(created_ini_file_path, win32con.FILE_ATTRIBUTE_HIDDEN)
        # Windows folder use READ_ONLY flag as a customization flag ...
        # https://support.microsoft.com/en-us/kb/326549
        win32api.SetFileAttributes(attrib_command_path, win32con.FILE_ATTRIBUTE_READONLY)

    def _read_data(self, file_path):
        '''The data file contains the mac icons'''
        dat = open(file_path, 'rb')
        info = dat.read()
        dat.close()
        return info

    def _get_icon_xdata(self):
        OSX_FINDER_INFO_ENTRY_SIZE = 32
        OSX_FINDER_INFO_ICON_FLAG_INDEX = 8
        OSX_FINDER_INFO_ICON_FLAG_VALUE = 4
        result = (OSX_FINDER_INFO_ENTRY_SIZE)*[0]
        result[OSX_FINDER_INFO_ICON_FLAG_INDEX] = OSX_FINDER_INFO_ICON_FLAG_VALUE
        return result

    def set_folder_icon_darwin(self, ref, icon):
        ''' Mac: Configure a folder with a given custom icon
            1. Read the com.apple.ResourceFork extended attribute from the icon file
            2. Set the com.apple.FinderInfo extended attribute with folder icon flag
            3. Create a Icon file (name: Icon\r) inside the target folder
            4. Set extended attributes com.apple.FinderInfo & com.apple.ResourceFork for icon file (name: Icon\r)
            5. Hide the icon file (name: Icon\r)
        '''
        try:
            import xattr
            import stat
            target_folder = self._abspath(ref)
            # Generate the value for 'com.apple.FinderInfo'
            has_icon_xdata = bytes(bytearray(self._get_icon_xdata()))
            # Configure 'com.apple.FinderInfo' for the folder
            xattr.setxattr(target_folder, xattr.XATTR_FINDERINFO_NAME, has_icon_xdata)
            # Create the 'Icon\r' file
            meta_file = os.path.join(target_folder, "Icon\r")
            if os.path.exists(meta_file):
                os.remove(meta_file)
            open(meta_file, "w").close()
            # Configure 'com.apple.FinderInfo' for the Icon file
            xattr.setxattr(meta_file, xattr.XATTR_FINDERINFO_NAME, has_icon_xdata)
            # Configure 'com.apple.ResourceFork' for the Icon file
            info = self._read_data(icon)
            xattr.setxattr(meta_file, xattr.XATTR_RESOURCEFORK_NAME, info)
            os.chflags(meta_file, stat.UF_HIDDEN)

        except Exception as e:
            log.error("Exception when setting folder icon : %s", e)

    def set_remote_id(self, ref, remote_id, name='ndrive'):
        if type(remote_id).__name__ == "unicode":
            remote_id = unicodedata.normalize('NFC', remote_id).encode('utf-8')
        # Can be move to another class
        path = self._abspath(ref)
        log.trace('Setting xattr %s with value %r on %r', name, remote_id, path)
        locker = self.unlock_path(path, False)
        if AbstractOSIntegration.is_windows():
            pathAlt = path + ":" + name
            try:
                if not os.path.exists(path):
                    raise NotFound()
                stat = os.stat(path)
                with open(pathAlt, "w") as f:
                    f.write(remote_id)
                # Avoid time modified change
                os.utime(path, (stat.st_atime, stat.st_mtime))
            except IOError as e:
                # Should not happen
                if e.errno == os.errno.EACCES:
                    self.unset_path_readonly(path)
                    with open(pathAlt, "w") as f:
                        f.write(remote_id)
                    self.set_path_readonly(path)
                else:
                    raise e
            finally:
                self.lock_path(path, locker)
        else:
            try:
                import xattr
                stat = os.stat(path)
                if AbstractOSIntegration.is_mac():
                    xattr.setxattr(path, name, remote_id)
                else:
                    xattr.setxattr(path, 'user.' + name, remote_id)
                os.utime(path, (stat.st_atime, stat.st_mtime))
            finally:
                self.lock_path(path, locker)

    def get_remote_id(self, ref, name="ndrive"):
        # Can be move to another class
        path = self._abspath(ref)
        return LocalClient.get_path_remote_id(path, name)

    @staticmethod
    def get_path_remote_id(path, name="ndrive"):
        if AbstractOSIntegration.is_windows():
            path = path + ":" + name
            try:
                with open(path, "r") as f:
                    return unicode(f.read(), 'utf-8')
            except:
                return None
        else:
            import xattr
            try:
                if AbstractOSIntegration.is_mac():
                    value = xattr.getxattr(path, name)
                else:
                    value = xattr.getxattr(path, 'user.' + name)
                return unicode(value, 'utf-8')
            except:
                return None

    # Getters
    def get_info(self, ref, raise_if_missing=True):
        if isinstance(ref, str):
            ref = unicode(ref)
        os_path = self._abspath(ref)
        if not os.path.exists(os_path):
            if raise_if_missing:
                raise NotFound("Could not found file '%s' under '%s'" % (
                ref, self.base_folder))
            else:
                return None
        folderish = os.path.isdir(os_path)
        stat_info = os.stat(os_path)
        if folderish:
            size = 0
        else:
            size = stat_info.st_size
        mtime = datetime.utcfromtimestamp(stat_info.st_mtime)
        # TODO Do we need to load it everytime ?
        remote_ref = self.get_remote_id(ref)
        # On unix we could use the inode for file move detection but that won't
        # work on Windows. To reduce complexity of the code and the possibility
        # to have Windows specific bugs, let's not use the unix inode at all.
        # uid = str(stat_info.st_ino)
        return FileInfo(self.base_folder, ref, folderish, mtime,
                        digest_func=self._digest_func,
                        check_suspended=self.check_suspended,
                        remote_ref=remote_ref, size=size)

    def is_equal_digests(self, local_digest, remote_digest, local_path, remote_digest_algorithm=None):
        if local_digest == remote_digest:
            return True
        if remote_digest_algorithm is None:
            remote_digest_algorithm = guess_digest_algorithm(remote_digest)
        if remote_digest_algorithm == self._digest_func:
            return False
        else:
            return self.get_info(local_path).get_digest(digest_func=remote_digest_algorithm) == remote_digest

    def get_content(self, ref):
        return open(self._abspath(ref), "rb").read()

    def is_osxbundle(self, ref):
        '''
        This is not reliable yet
        '''
        if not AbstractOSIntegration.is_mac():
            return False
        if (os.path.isfile(self._abspath(ref))):
            return False
        # Dont want to synchornize app - when copy paste this file might not has been created yet
        if os.path.isfile(os.path.join(ref, "Contents", "Info.plist")):
            return True
        attrs = self.get_remote_id(ref, "com.apple.FinderInfo")
        if attrs is None:
            return False
        return bool(ord(attrs[8]) & 0x20)

    def is_ignored(self, parent_ref, file_name):
        # Add parent_ref to be able to filter on size if needed
        ignore = False
        # Office temp file
        # http://support.microsoft.com/kb/211632
        if file_name.startswith("~") and file_name.endswith(".tmp"):
            return True
        # Emacs auto save file
        # http://www.emacswiki.org/emacs/AutoSave
        if file_name.startswith("#") and file_name.endswith("#") and len(file_name) > 2:
            return True
        for suffix in self.ignored_suffixes:
            if file_name.endswith(suffix):
                ignore = True
                break
        for prefix in self.ignored_prefixes:
            if file_name.startswith(prefix):
                ignore = True
                break
        if ignore:
            return True
        if AbstractOSIntegration.is_windows():
            # NXDRIVE-465
            ref = self.get_children_ref(parent_ref, file_name)
            path = self._abspath(ref)
            if not os.path.exists(path):
                return False
            import win32con
            import win32api
            attrs = win32api.GetFileAttributes(path)
            if attrs & win32con.FILE_ATTRIBUTE_SYSTEM == win32con.FILE_ATTRIBUTE_SYSTEM:
                return True
            if attrs & win32con.FILE_ATTRIBUTE_HIDDEN == win32con.FILE_ATTRIBUTE_HIDDEN:
                return True
        return False

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

            if not (self.is_ignored(ref, child_name) or self.is_temp_file(child_name)):
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

    def duplicate_file(self, ref):
        parent = os.path.dirname(ref)
        name = os.path.basename(ref)
        locker = self.unlock_ref(parent, False)
        os_path, name = self._abspath_deduped(parent, name)
        try:
            shutil.copy(self._abspath(ref), os_path)
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

    def update_content(self, ref, content, xattr_names=['ndrive']):
        xattrs = {}
        for name in xattr_names:
            xattrs[name] = self.get_remote_id(ref, name=name)
        with open(self._abspath(ref), "wb") as f:
            f.write(content)
        for name in xattr_names:
            if xattrs[name] is not None:
                self.set_remote_id(ref, xattrs[name], name=name)

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
        locker = 0
        parent_ref = None
        try:
            if ref is not '/':
                parent_ref = os.path.dirname(ref)
                locker = self.unlock_ref(parent_ref, False)
            self.unset_readonly(ref)
            os_path = self._abspath(ref)
            if os.path.isfile(os_path):
                os.unlink(os_path)
            elif os.path.isdir(os_path):
                shutil.rmtree(os_path)
        finally:
            if parent_ref is not None:
                self.lock_ref(parent_ref, locker)

    def exists(self, ref):
        os_path = self._abspath(ref)
        return os.path.exists(os_path)

    def check_writable(self, ref):
        os_path = self._abspath(ref)
        return os.access(os_path, os.W_OK)

    def rename(self, ref, to_name):
        """Rename a local file or folder

        Return the actualized info object.

        """
        new_name = safe_filename(to_name)
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
                if AbstractOSIntegration.is_windows():
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(
                                                unicode(temp_path), 2)
                os.rename(source_os_path, temp_path)
                source_os_path = temp_path
                # Try the os rename part
                target_os_path = self._abspath(os.path.join(parent, new_name))
            else:
                target_os_path, new_name = self._abspath_deduped(parent,
                                                                new_name, old_name)
            if old_name != new_name:
                os.rename(source_os_path, target_os_path)
            if AbstractOSIntegration.is_windows():
                import ctypes
                # See http://msdn.microsoft.com/en-us/library/aa365535%28v=vs.85%29.aspx
                ctypes.windll.kernel32.SetFileAttributesW(
                                            unicode(target_os_path), 128)
            new_ref = self.get_children_ref(parent, new_name)
            return self.get_info(new_ref)
        finally:
            self.lock_ref(ref, locker & 2)

    def move(self, ref, new_parent_ref, name=None):
        """Move a local file or folder into another folder

        Return the actualized info object.

        """
        if ref == u'/':
            raise ValueError("Cannot move the toplevel folder.")
        locker = self.unlock_ref(ref)
        new_locker = self.unlock_ref(new_parent_ref, False)
        source_os_path = self._abspath(ref)
        name = name if name is not None else ref.rsplit(u'/', 1)[1]
        target_os_path, new_name = self._abspath_deduped(new_parent_ref, name)
        try:
            shutil.move(source_os_path, target_os_path)
            new_ref = self.get_children_ref(new_parent_ref, new_name)
            return self.get_info(new_ref)
        finally:
            self.lock_ref(ref, locker & 2)
            self.lock_ref(new_parent_ref, locker & 1 | new_locker)

    def is_inside(self, abspath):
        return abspath.startswith(self.base_folder)

    def get_path(self, abspath):
        """Relative path to the local client from an absolute OS path"""
        path = abspath.split(self.base_folder, 1)[1]
        rel_path = path.replace(os.path.sep, '/')
        if rel_path == '':
            rel_path = u'/'
        return rel_path

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
            if self._disable_duplication:
                raise ValueError("De-duplication is disabled")
            # the is a duplicated file, try to come with a new name
            log.trace("dedup: %s exist try next", os_path)
            m = re.match(DEDUPED_BASENAME_PATTERN, name)
            if m:
                short_name, increment = m.groups()
                name = u"%s__%d" % (short_name, int(increment) + 1)
            else:
                name = name + u'__1'
            log.trace("Deduplicate a name: %s", name, exc_info=True)
        raise ValueError("Failed to de-duplicate '%s' under '%s'" % (
            orig_name, parent))
