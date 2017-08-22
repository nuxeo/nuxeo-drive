# coding: utf-8
""" API to access local resources for synchronization. """

import datetime
import errno
import hashlib
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import warnings

from send2trash import send2trash

from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_PREFIX, \
    DOWNLOAD_TMP_FILE_SUFFIX
from nxdrive.client.common import BaseClient, DEFAULT_IGNORED_PREFIXES, \
    DEFAULT_IGNORED_SUFFIXES, DuplicationDisabledError, DuplicationError, \
    FILE_BUFFER_SIZE, NotFound, UNACCESSIBLE_HASH, safe_filename
from nxdrive.logging_config import get_logger
from nxdrive.osi import AbstractOSIntegration
from nxdrive.utils import guess_digest_algorithm, normalized_path, \
    safe_long_path

if AbstractOSIntegration.is_windows():
    import ctypes
    import win32api
    import win32con
    import win32file
else:
    import stat
    import xattr

log = get_logger(__name__)


DEDUPED_BASENAME_PATTERN = ur'^(.*)__(\d{1,3})$'


# Data transfer objects

class FileInfo(object):
    """Data Transfer Object for file info on the Local FS"""

    def __init__(self, root, path, folderish, last_modification_time, **kwargs):
        # Function to check during long-running processing like digest
        # computation if the synchronization thread needs to be suspended
        self.check_suspended = kwargs.pop('check_suspended', None)
        self.size = kwargs.pop('size', 0)
        filepath = os.path.join(root, path[1:].replace(u'/', os.path.sep))
        root = unicodedata.normalize('NFC', root)
        path = unicodedata.normalize('NFC', path)
        normalized_filepath = os.path.join(
            root, path[1:].replace(u'/', os.path.sep))
        self.filepath = normalized_filepath

        # NXDRIVE-188: normalize name on the file system if not normalized
        if (os.path.exists(filepath)
                and normalized_filepath != filepath
                and not AbstractOSIntegration.is_mac()):
            log.debug('Forcing normalization of %r to %r',
                      filepath, normalized_filepath)
            os.rename(filepath, normalized_filepath)

        self.root = root  # the sync root folder local path
        self.path = path  # the truncated path (under the root)
        self.folderish = folderish  # True if a Folder
        self.remote_ref = kwargs.pop('remote_ref', None)

        # Last OS modification date of the file
        self.last_modification_time = last_modification_time

        # Function to use
        self._digest_func = kwargs.pop('digest_func', 'MD5').lower()

        # Precompute base name once and for all are it's often useful in
        # practice
        self.name = os.path.basename(path)

    def __repr__(self):
        return self.__unicode__().encode('ascii', 'ignore')

    def __unicode__(self):
        return u'FileInfo[%s, remote_ref=%s]' % (self.filepath, self.remote_ref)

    def get_digest(self, digest_func=None):
        """ Lazy computation of the digest. """

        if self.folderish:
            return None
        digest_func = (digest_func
                       if digest_func is not None
                       else self._digest_func)
        digester = getattr(hashlib, digest_func, None)
        if digester is None:
            raise ValueError('Unknown digest method: ' + digest_func)

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

    CASE_RENAME_PREFIX = 'driveCaseRename_'

    def __init__(self, base_folder, **kwargs):
        self._case_sensitive = kwargs.pop('case_sensitive', None)
        self._disable_duplication = kwargs.pop('disable_duplication', True)
        self.ignored_prefixes = (kwargs.pop('ignored_prefixes', None)
                                 or DEFAULT_IGNORED_PREFIXES)
        self.ignored_suffixes = (kwargs.pop('ignored_suffixes', None)
                                 or DEFAULT_IGNORED_SUFFIXES)

        # Function to check during long-running processing like digest
        # computation if the synchronization thread needs to be suspended
        self.check_suspended = kwargs.pop('check_suspended', None)

        while len(base_folder) > 1 and base_folder.endswith(os.path.sep):
            base_folder = base_folder[:-1]
        self.base_folder = base_folder
        self._digest_func = kwargs.pop('digest_func', 'md5')

    def __repr__(self):
        return ('<{name}'
                ' base_folder={cls.base_folder!r},'
                ' duplication_enabled={cls._disable_duplication!r},'
                ' is_case_sensitive={cls._case_sensitive!r},'
                ' ignored_prefixes={cls.ignored_prefixes!r},'
                ' ignored_suffixes={cls.ignored_suffixes!r}'
                '>'
                ).format(name=type(self).__name__, cls=self)

    def duplication_enabled(self):
        """ Check if de-duplication is enable or not. """

        return not self._disable_duplication

    def is_case_sensitive(self):
        if self._case_sensitive is None:
            lock = self.unlock_path(self.base_folder, unlock_parent=False)
            path = tempfile.mkdtemp(prefix='.caseTest_',
                                    dir=safe_long_path(self.base_folder))
            self._case_sensitive = not os.path.exists(path.upper())
            os.rmdir(path)
            self.lock_path(self.base_folder, lock)
        return self._case_sensitive

    @staticmethod
    def is_temp_file(filename):
        return (filename.startswith(DOWNLOAD_TMP_FILE_PREFIX) and
                filename.endswith(DOWNLOAD_TMP_FILE_SUFFIX))

    def set_readonly(self, ref):
        path = self.abspath(ref)
        self.set_path_readonly(path)

    def unset_readonly(self, ref):
        path = self.abspath(ref)
        if os.path.exists(path):
            self.unset_path_readonly(path)

    def clean_xattr_root(self):
        self.unlock_ref(u'/', unlock_parent=False)
        try:
            self.remove_root_id()
        except IOError:
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
        return self.get_remote_id('/', name='ndriveroot')

    def _remove_remote_id_windows(self, path, name='ndrive'):
        path_alt = path + ':' + name
        try:
            os.remove(path_alt)
        except OSError as e:
            if e.errno != errno.EACCES:
                raise e
            self.unset_path_readonly(path)
            try:
                os.remove(path_alt)
            finally:
                self.set_path_readonly(path)

    @staticmethod
    def _remove_remote_id_unix(path, name='ndrive'):
        try:
            if AbstractOSIntegration.is_mac():
                xattr.removexattr(path, name)
            else:
                xattr.removexattr(path, 'user.' + name)
        except IOError as exc:
            # EPROTONOSUPPORT: protocol not supported (xattr)
            # ENODATA: no data available
            if exc.errno not in (errno.ENODATA, errno.EPROTONOSUPPORT):
                raise exc

    def remove_remote_id(self, ref, name='ndrive'):
        path = self.abspath(ref)
        log.trace('Removing xattr %s from %s', name, path)
        locker = self.unlock_path(path, False)
        func = (self._remove_remote_id_windows
                if AbstractOSIntegration.is_windows()
                else self._remove_remote_id_unix)
        try:
            func(path, name=name)
        except (IOError, OSError) as exc:
            # ENOENT: file does not exist
            # IOError [Errno 93]: Attribute not found
            if exc.errno not in (errno.ENOENT, 93):
                raise exc
        finally:
            self.lock_path(path, locker)

    def unset_folder_icon(self, ref):
        """ Unset the red icon. """

        desktop_ini_file_path = os.path.join(self.abspath(ref), "desktop.ini")
        if AbstractOSIntegration.is_mac():
            desktop_ini_file_path = os.path.join(self.abspath(ref), "Icon\r")
        if os.path.exists(desktop_ini_file_path):
            os.remove(desktop_ini_file_path)

    def has_folder_icon(self, ref):
        target_folder = self.abspath(ref)
        if AbstractOSIntegration.is_mac():
            meta_file = os.path.join(target_folder, "Icon\r")
            return os.path.exists(meta_file)
        if AbstractOSIntegration.is_windows():
            meta_file = os.path.join(target_folder, "desktop.ini")
            return os.path.exists(meta_file)
        return False

    def set_folder_icon(self, ref, icon):
        if icon is None:
            return
        if AbstractOSIntegration.is_windows():
            self.set_folder_icon_win32(ref, icon)
        elif AbstractOSIntegration.is_mac():
            self.set_folder_icon_darwin(ref, icon)

    def set_folder_icon_win32(self, ref, icon):
        """ Configure red color icon for a folder Windows / macOS. """

        # Desktop.ini file content for Windows 7+.
        ini_file_content = """
[.ShellClassInfo]
IconResource={icon},0
[ViewState]
Mode=
Vid=
FolderType=Generic
"""
        desktop_ini_content = ini_file_content.format(icon=icon)

        # Create the desktop.ini file inside the ReadOnly shared folder.
        created_ini_file_path = os.path.join(self.abspath(ref), 'desktop.ini')
        attrib_command_path = self.abspath(ref)
        if not os.path.exists(created_ini_file_path):
            try:
                with open(created_ini_file_path, 'w') as create_file:
                    create_file.write(desktop_ini_content)
                win32api.SetFileAttributes(created_ini_file_path,
                                           win32con.FILE_ATTRIBUTE_SYSTEM)
                win32api.SetFileAttributes(created_ini_file_path,
                                           win32con.FILE_ATTRIBUTE_HIDDEN)
            except:
                log.exception('Icon folder cannot be set')
        else:
            win32api.SetFileAttributes(created_ini_file_path,
                                       win32con.FILE_ATTRIBUTE_SYSTEM)
            win32api.SetFileAttributes(created_ini_file_path,
                                       win32con.FILE_ATTRIBUTE_HIDDEN)
        # Windows folder use READ_ONLY flag as a customization flag ...
        # https://support.microsoft.com/en-us/kb/326549
        win32api.SetFileAttributes(attrib_command_path,
                                   win32con.FILE_ATTRIBUTE_READONLY)

    @staticmethod
    def _read_data(file_path):
        """ The data file contains the mac icons. """

        with open(file_path, 'rb') as dat:
            return dat.read()

    @staticmethod
    def _get_icon_xdata():
        entry_size = 32
        icon_flag_index = 8
        icon_flag_value = 4
        result = [0] * entry_size
        result[icon_flag_index] = icon_flag_value
        return result

    def set_folder_icon_darwin(self, ref, icon):
        """
        macOS: configure a folder with a given custom icon
            1. Read the com.apple.ResourceFork extended attribute from the icon file
            2. Set the com.apple.FinderInfo extended attribute with folder icon flag
            3. Create a Icon file (name: Icon\r) inside the target folder
            4. Set extended attributes com.apple.FinderInfo & com.apple.ResourceFork for icon file (name: Icon\r)
            5. Hide the icon file (name: Icon\r)
        """
        try:
            target_folder = self.abspath(ref)
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
        if not isinstance(remote_id, bytes):
            remote_id = unicodedata.normalize('NFC', remote_id).encode('utf-8')
        # Can be move to another class
        path = self.abspath(ref)
        log.trace('Setting xattr %s with value %r on %r', name, remote_id, path)
        locker = self.unlock_path(path, False)
        if AbstractOSIntegration.is_windows():
            path_alt = path + ':' + name
            try:
                if not os.path.exists(path):
                    raise NotFound()
                stat = os.stat(path)
                with open(path_alt, 'w') as f:
                    f.write(remote_id)
                # Avoid time modified change
                os.utime(path, (stat.st_atime, stat.st_mtime))
            except IOError as e:
                # Should not happen
                if e.errno == os.errno.EACCES:
                    self.unset_path_readonly(path)
                    with open(path_alt, 'w') as f:
                        f.write(remote_id)
                    self.set_path_readonly(path)
                else:
                    raise e
            finally:
                self.lock_path(path, locker)
        else:
            try:
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
        path = self.abspath(ref)
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
        if isinstance(ref, bytes):
            ref = unicode(ref)
        os_path = self.abspath(ref)
        if not os.path.exists(os_path):
            if raise_if_missing:
                err = 'Could not find file into {!r}: ref={!r}, os_path={!r}'
                raise NotFound(err.format(self.base_folder, ref, os_path))
            return None
        folderish = os.path.isdir(os_path)
        stat_info = os.stat(os_path)
        size = 0 if folderish else stat_info.st_size
        try:
            mtime = datetime.datetime.utcfromtimestamp(stat_info.st_mtime)
        except ValueError, e:
            log.error(str(e) + "file path: %s. st_mtime value: %s" % (str(os_path), str(stat_info.st_mtime)))
            mtime = datetime.datetime.utcfromtimestamp(0)
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

    def is_equal_digests(
        self,
        local_digest,
        remote_digest,
        local_path,
        remote_digest_algorithm=None,
    ):
        """
        Compare 2 document's digests.

        :param str local_digest: Digest of the local document.
                                 Set to None to force digest computation.
        :param str remote_digest: Digest of the remote document.
        :param str local_path: Local path of the document.
        :param str remote_digest_algorithm: Remote document digest algorithm
        :return bool: Digest are equals.
        """

        if local_digest == remote_digest:
            return True
        if remote_digest_algorithm is None:
            remote_digest_algorithm = guess_digest_algorithm(remote_digest)
        if remote_digest_algorithm == self._digest_func:
            return False

        file_info = self.get_info(local_path)
        digest = file_info.get_digest(digest_func=remote_digest_algorithm)
        return digest == remote_digest

    def get_content(self, ref):
        return open(self.abspath(ref), 'rb').read()

    def is_osxbundle(self, ref):
        '''
        This is not reliable yet
        '''
        if not AbstractOSIntegration.is_mac():
            return False
        if os.path.isfile(self.abspath(ref)):
            return False
        # Don't want to synchornize app - when copy paste this file
        # might not has been created yet
        if os.path.isfile(os.path.join(ref, "Contents", "Info.plist")):
            return True
        attrs = self.get_remote_id(ref, "com.apple.FinderInfo")
        if attrs is None:
            return False
        return bool(ord(attrs[8]) & 0x20)

    def is_ignored(self, parent_ref, file_name):
        # Add parent_ref to be able to filter on size if needed

        # Emacs auto save file
        # http://www.emacswiki.org/emacs/AutoSave
        if (file_name.startswith('#')
                and file_name.endswith('#')
                and len(file_name) > 2):
            return True

        if (file_name.endswith(self.ignored_suffixes)
                or file_name.startswith(self.ignored_prefixes)):
            return True

        if AbstractOSIntegration.is_windows():
            # NXDRIVE-465: ignore hidden files on Windows
            ref = self.get_children_ref(parent_ref, file_name)
            path = self.abspath(ref)
            is_system = win32con.FILE_ATTRIBUTE_SYSTEM
            is_hidden = win32con.FILE_ATTRIBUTE_HIDDEN
            try:
                attrs = win32api.GetFileAttributes(path)
            except win32file.error:
                return False
            if attrs & is_system == is_system:
                return True
            if attrs & is_hidden == is_hidden:
                return True

        # NXDRIVE-655: need to check every parent if they are ignored
        result = False
        if parent_ref != '/':
            file_name = os.path.basename(parent_ref)
            parent_ref = os.path.dirname(parent_ref)
            result = self.is_ignored(parent_ref, file_name)

        return result

    @staticmethod
    def get_children_ref(parent_ref, name):
        if parent_ref == u'/':
            return parent_ref + name
        return parent_ref + u'/' + name

    def get_children_info(self, ref):
        os_path = self.abspath(ref)
        result = []
        children = os.listdir(os_path)

        for child_name in sorted(children):
            if (self.is_ignored(ref, child_name)
                    or self.is_temp_file(child_name)):
                log.debug('Ignoring banned file %r in %r', child_name, os_path)
                continue

            child_ref = self.get_children_ref(ref, child_name)
            try:
                info = self.get_info(child_ref)
            except (OSError, NotFound):
                log.exception('The child file has been deleted in the mean time'
                              ' or while reading some of its attributes')
                continue
            result.append(info)

        return result

    @staticmethod
    def get_parent_ref(ref):
        if ref == '/':
            return None
        parent = ref.rsplit(u'/', 1)[0]
        if parent is None:
            parent = '/'
        return parent

    def unlock_ref(self, ref, unlock_parent=True):
        path = self.abspath(ref)
        return self.unlock_path(path, unlock_parent)

    def lock_ref(self, ref, locker):
        path = self.abspath(ref)
        return self.lock_path(path, locker)

    def make_folder(self, parent, name):
        locker = self.unlock_ref(parent, False)
        os_path, name = self._abspath_deduped(parent, name)
        try:
            os.mkdir(os_path)
            # Name should be the actual name of the folder created locally
            name = os.path.basename(os_path)
            if parent == u"/":
                return u"/" + name
            return parent + u"/" + name
        finally:
            self.lock_ref(parent, locker)

    @staticmethod
    def make_tree(path):
        """
        Recursive directory creation.

        :param str path: The absolute path to create.
        """

        try:
            os.makedirs(path)
        except os.error as exc:
            # EEXIST: path already exists
            if exc.errno != errno.EEXIST:
                raise exc

    def duplicate_file(self, ref):
        parent = os.path.dirname(ref)
        name = os.path.basename(ref)
        locker = self.unlock_ref(parent, False)
        os_path, name = self._abspath_deduped(parent, name)
        if parent == u"/":
            duplicated_file = u"/" + name
        else:
            duplicated_file = parent + u"/" + name
        try:
            shutil.copy(self.abspath(ref), os_path)
            return duplicated_file
        except IOError as e:
            e.duplicated_file = duplicated_file
            raise e
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

    def update_content(self, ref, content, xattr_names=tuple('ndrive')):
        xattrs = {}
        for name in xattr_names:
            xattrs[name] = self.get_remote_id(ref, name=name)
        with open(self.abspath(ref), "wb") as f:
            f.write(content)
        for name in xattr_names:
            if xattrs[name] is not None:
                self.set_remote_id(ref, xattrs[name], name=name)

    def delete(self, ref):
        locker = self.unlock_ref(ref)
        os_path = self.abspath(ref)
        if not self.exists(ref):
            return

        # Remove the \\?\ prefix, specific to Windows
        os_path = os_path.lstrip('\\\\?\\')

        log.trace('Sending to trash ' + os_path)

        # Send2Trash needs bytes
        if not isinstance(os_path, bytes):
            os_path = os_path.encode(sys.getfilesystemencoding() or 'utf-8')

        try:
            send2trash(os_path)
        except OSError:
            log.debug('Cannot use trash, deleting ' + os_path)
            self.delete_final(ref)
        finally:
            # Don't want to unlock the current deleted
            self.lock_ref(ref, locker & 2)

    def delete_final(self, ref):
        locker = 0
        parent_ref = None
        try:
            if ref is not '/':
                parent_ref = os.path.dirname(ref)
                locker = self.unlock_ref(parent_ref, False)
            self.unset_readonly(ref)
            os_path = self.abspath(ref)
            if os.path.isfile(os_path):
                os.unlink(os_path)
            elif os.path.isdir(os_path):
                shutil.rmtree(os_path)
        finally:
            if parent_ref is not None:
                self.lock_ref(parent_ref, locker)

    def exists(self, ref):
        os_path = self.abspath(ref)
        return os.path.exists(os_path)

    def check_writable(self, ref):
        os_path = self.abspath(ref)
        return os.access(os_path, os.W_OK)

    def rename(self, ref, to_name):
        """Rename a local file or folder

        Return the actualized info object.

        """
        new_name = safe_filename(to_name)
        source_os_path = self.abspath(ref)
        parent = ref.rsplit(u'/', 1)[0]
        old_name = ref.rsplit(u'/', 1)[1]
        parent = u'/' if parent == '' else parent
        locker = self.unlock_ref(ref)
        try:
            # Check if only case renaming
            if (old_name != new_name
                    and old_name.lower() == new_name.lower()
                    and not self.is_case_sensitive()):
                # Must use a temp rename as FS is not case sensitive
                with warnings.catch_warnings(UserWarning):
                    temp_path = os.tempnam(
                        self.abspath(parent),
                        LocalClient.CASE_RENAME_PREFIX + old_name + '_')
                if AbstractOSIntegration.is_windows():
                    ctypes.windll.kernel32.SetFileAttributesW(
                        unicode(temp_path), 2)
                os.rename(source_os_path, temp_path)
                source_os_path = temp_path
                # Try the os rename part
                target_os_path = self.abspath(os.path.join(parent, new_name))
            else:
                target_os_path, new_name = self._abspath_deduped(
                    parent, new_name, old_name)
            if old_name != new_name:
                os.rename(source_os_path, target_os_path)
            if AbstractOSIntegration.is_windows():
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
        source_os_path = self.abspath(ref)
        name = name if name is not None else ref.rsplit(u'/', 1)[1]
        target_os_path, new_name = self._abspath_deduped(new_parent_ref, name)
        try:
            os.rename(source_os_path, target_os_path)
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

    def abspath(self, ref):
        """Absolute path on the operating system"""
        if not ref.startswith(u'/'):
            raise ValueError(
                'LocalClient expects ref starting with "/"', locals())
        path_suffix = ref[1:].replace('/', os.path.sep)
        path = normalized_path(os.path.join(self.base_folder, path_suffix))
        return safe_long_path(path)

    def _abspath_safe(self, parent, orig_name):
        """Absolute path on the operating system with deduplicated names"""
        # make name safe by removing invalid chars
        name = safe_filename(orig_name)

        # decompose the name into actionable components
        name, suffix = os.path.splitext(name)
        os_path = self.abspath(os.path.join(parent, name + suffix))
        return os_path

    def _abspath_deduped(self, parent, orig_name, old_name=None):
        """Absolute path on the operating system with deduplicated names"""
        # make name safe by removing invalid chars
        name = safe_filename(orig_name)

        # decompose the name into actionable components
        name, suffix = os.path.splitext(name)

        for _ in range(1000):
            os_path = self.abspath(os.path.join(parent, name + suffix))
            if old_name == (name + suffix):
                return os_path, name + suffix
            if not os.path.exists(os_path):
                return os_path, name + suffix
            if self._disable_duplication:
                raise DuplicationDisabledError('De-duplication is disabled')

            # the is a duplicated file, try to come with a new name
            m = re.match(DEDUPED_BASENAME_PATTERN, name)
            if m:
                short_name, increment = m.groups()
                name = u"%s__%d" % (short_name, int(increment) + 1)
            else:
                name = name + u'__1'
            log.trace("De-duplicate %s to %s", os_path, name)
        raise DuplicationError(
            'Failed to de-duplicate "%s" under "%s"' % (orig_name, parent))
