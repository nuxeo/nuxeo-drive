# coding: utf-8
""" API to access local resources for synchronization. """

import errno
import hashlib
import os
import shutil
import sys
import tempfile
import unicodedata
import uuid
from datetime import datetime
from logging import getLogger
from time import mktime, strptime

from send2trash import send2trash

from .base_automation_client import (DOWNLOAD_TMP_FILE_PREFIX,
                                     DOWNLOAD_TMP_FILE_SUFFIX)
from .common import (BaseClient, DuplicationDisabledError,
                     FILE_BUFFER_SIZE, NotFound,
                     UNACCESSIBLE_HASH, safe_filename)
from ..options import Options
from ..utils import (guess_digest_algorithm, force_decode, normalized_path,
                     safe_long_path)

# from typing import List, Optional, Text, Tuple, Union

if sys.platform == 'win32':
    import ctypes
    import win32api
    import win32con
    import win32file
else:
    import stat
    import xattr

log = getLogger(__name__)


# Data transfer objects

class FileInfo(object):
    """ Data Transfer Object for file info on the Local FS. """

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
                and not sys.platform == 'darwin'):
            log.debug('Forcing normalization of %r to %r',
                      filepath, normalized_filepath)
            os.rename(filepath, normalized_filepath)

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
        # type: (Optional[callable]) -> Union[Text, None]
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
    """ Client API implementation for the local file system. """

    CASE_RENAME_PREFIX = 'driveCaseRename_'

    def __init__(self, base_folder, **kwargs):
        self._case_sensitive = kwargs.pop('case_sensitive', None)

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
                ' is_case_sensitive={cls._case_sensitive!r}'
                '>'
                ).format(name=type(self).__name__, cls=self)

    def is_case_sensitive(self):
        # type: () -> bool

        if self._case_sensitive is None:
            path = tempfile.mkdtemp(prefix='.caseTest_')
            self._case_sensitive = not os.path.exists(path.upper())
            os.rmdir(path)
        return self._case_sensitive

    @staticmethod
    def is_temp_file(filename):
        # type: () -> bool

        return (filename.startswith(DOWNLOAD_TMP_FILE_PREFIX) and
                filename.endswith(DOWNLOAD_TMP_FILE_SUFFIX))

    def set_readonly(self, ref):
        # type: (Text) -> None

        path = self.abspath(ref)
        self.set_path_readonly(path)

    def unset_readonly(self, ref):
        # type: (Text) -> None

        path = self.abspath(ref)
        if os.path.exists(path):
            self.unset_path_readonly(path)

    def clean_xattr_root(self):
        # type: () -> None

        self.unlock_ref(u'/', unlock_parent=False)
        try:
            self.remove_root_id()
        except IOError:
            pass
        self.clean_xattr_folder_recursive(u'/')

    def clean_xattr_folder_recursive(self, path):
        # type: (Text) -> None

        for child in self.get_children_info(path):
            locker = self.unlock_ref(child.path, unlock_parent=False)
            if child.remote_ref is not None:
                self.remove_remote_id(child.path)
            self.lock_ref(child.path, locker)
            if child.folderish:
                self.clean_xattr_folder_recursive(child.path)

    def remove_root_id(self):
        # type: () -> None

        self.remove_remote_id('/', name='ndriveroot')

    def set_root_id(self, value):
        # type: (Text) -> None

        self.set_remote_id('/', value, name="ndriveroot")

    def get_root_id(self):
        # type: () -> Text

        return self.get_remote_id('/', name='ndriveroot')

    def _remove_remote_id_windows(self, path, name='ndrive'):
        # type: (Text, Text) -> None

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
        # type: (Text, Text) -> None

        if sys.platform == 'linux2':
            name = 'user.' + name
        try:
            xattr.removexattr(path, name)
        except IOError as exc:
            # EPROTONOSUPPORT: protocol not supported (xattr)
            # ENODATA: no data available
            if exc.errno not in (errno.ENODATA, errno.EPROTONOSUPPORT):
                raise exc

    def remove_remote_id(self, ref, name='ndrive'):
        # type: (Text, Text) -> None

        path = self.abspath(ref)
        log.trace('Removing xattr %r from %r', name, path)
        locker = self.unlock_path(path, False)
        func = (self._remove_remote_id_windows
                if sys.platform == 'win32'
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

    def has_folder_icon(self, ref):
        # type: (Text) -> bool
        """ Check if the folder icon is set. """

        if sys.platform == 'darwin':
            meta_file = os.path.join(self.abspath(ref), 'Icon\r')
        elif sys.platform == 'win32':
            meta_file = os.path.join(self.abspath(ref), 'desktop.ini')
        else:
            return False

        return os.path.exists(meta_file)

    def set_folder_icon(self, ref, icon):
        if icon is None:
            return

        if sys.platform == 'darwin':
            self.set_folder_icon_darwin(ref, icon)
        elif sys.platform == 'win32':
            self.set_folder_icon_win32(ref, icon)

    def set_folder_icon_win32(self, ref, icon):
        """ Configure red color icon for a folder Windows. """

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
        os_path = self.abspath(ref)
        created_ini_file_path = os.path.join(os_path, 'desktop.ini')
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
        win32api.SetFileAttributes(os_path, win32con.FILE_ATTRIBUTE_READONLY)

    @staticmethod
    def _read_data(file_path):
        # type: (Text) -> bytes
        """ The data file contains macOS icons. """

        with open(file_path, 'rb') as dat:
            return dat.read()

    @staticmethod
    def _get_icon_xdata():
        # type: () -> List[int]

        entry_size = 32
        icon_flag_index = 8
        icon_flag_value = 4
        result = [0] * entry_size
        result[icon_flag_index] = icon_flag_value
        return result

    def set_folder_icon_darwin(self, ref, icon):
        # type: (Text, Text) -> None
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
        except:
            log.exception('Impossible to set the folder icon')

    def set_remote_id(self, ref, remote_id, name='ndrive'):
        # type: (Text, Text, Text) -> None

        if not isinstance(remote_id, bytes):
            remote_id = unicodedata.normalize('NFC', remote_id).encode('utf-8')

        path = self.abspath(ref)
        log.trace('Setting xattr %s with value %r on %r', name, remote_id, path)
        locker = self.unlock_path(path, False)
        if sys.platform == 'win32':
            path_alt = path + ':' + name
            try:
                if not os.path.exists(path):
                    raise NotFound()

                stat_ = os.stat(path)
                with open(path_alt, 'w') as f:
                    f.write(remote_id)

                # Avoid time modified change
                os.utime(path, (stat_.st_atime, stat_.st_mtime))
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
            return

        if sys.platform == 'linux2':
            name = 'user.' + name
        try:
            stat_ = os.stat(path)
            xattr.setxattr(path, name, remote_id)
            os.utime(path, (stat_.st_atime, stat_.st_mtime))
        finally:
            self.lock_path(path, locker)

    def get_remote_id(self, ref, name='ndrive'):
        # type: (Text, Text) -> Union[Text, None]

        return self.get_path_remote_id(self.abspath(ref), name)

    @staticmethod
    def get_path_remote_id(path, name='ndrive'):
        # type: (Text, Text) -> Union[Text, None]

        if sys.platform == 'win32':
            path += ':' + name
            try:
                with open(path) as f:
                    return unicode(f.read(), 'utf-8')
            except (IOError, OSError):
                return None

        if sys.platform == 'linux2':
            name = 'user.' + name
        try:
            value = xattr.getxattr(path, name)
            return unicode(value, 'utf-8')
        except:
            return None

    def get_info(self, ref, raise_if_missing=True):
        # type: (Text, bool) -> Union[FileInfo, None]

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
            mtime = datetime.utcfromtimestamp(stat_info.st_mtime)
        except ValueError, e:
            log.error(str(e) + "file path: %s. st_mtime value: %s" % (str(os_path), str(stat_info.st_mtime)))
            mtime = datetime.utcfromtimestamp(0)

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
        # type: (Text, Text, Text, Optional[Text]) -> bool
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
        # type: (Text) -> bytes

        with open(self.abspath(ref), 'rb') as f:
            return f.read()

    def is_ignored(self, parent_ref, file_name):
        # type: (Text, Text) -> bool
        """ Note: added parent_ref to be able to filter on size if needed. """

        file_name = force_decode(file_name.lower())

        if (file_name.endswith(Options.ignored_suffixes)
                or file_name.startswith(Options.ignored_prefixes)):
            return True

        if sys.platform == 'win32':
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
        # type: (Text, Text) -> Text

        if parent_ref == u'/':
            return parent_ref + name
        return parent_ref + u'/' + name

    def get_children_info(self, ref):
        # type: (Text) -> List[FileInfo]

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

    def unlock_ref(self, ref, unlock_parent=True, is_abs=False):
        # type: (Text, bool, bool) -> int

        path = ref if is_abs else self.abspath(ref)
        return self.unlock_path(path, unlock_parent)

    def lock_ref(self, ref, locker, is_abs=False):
        # type: (Text, int, bool) -> int

        path = ref if is_abs else self.abspath(ref)
        return self.lock_path(path, locker)

    def make_folder(self, parent, name):
        # type: (Text, Text) -> Text

        os_path, name = self._abspath_deduped(parent, name)
        locker = self.unlock_ref(parent, unlock_parent=False)
        try:
            os.mkdir(os_path)
        finally:
            self.lock_ref(parent, locker)

        # Name should be the actual name of the folder created locally
        name = os.path.basename(os_path)
        if parent == u'/':
            return u'/' + name
        return parent + u'/' + name

    def make_file(self, parent, name, content=None):
        # type: (Text, Text, Optional[bytes]) -> Text

        os_path, name = self._abspath_deduped(parent, name)
        locker = self.unlock_ref(parent, unlock_parent=False)
        try:
            with open(os_path, 'wb') as f:
                if content:
                    f.write(content)
            if parent == u"/":
                return u"/" + name
            return parent + u"/" + name
        finally:
            self.lock_ref(parent, locker)

    def get_new_file(self, parent, name):
        # type: (Text, Text) -> Tuple[Text, Text, Text]

        os_path, name = self._abspath_deduped(parent, name)
        if parent == u"/":
            path = u"/" + name
        else:
            path = parent + u"/" + name
        return path, os_path, name

    def update_content(self, ref, content, xattr_names=('ndrive',)):
        # type: (Text, bytes, Tuple[Text]) -> None

        xattrs = {name: self.get_remote_id(ref, name=name)
                  for name in xattr_names}

        with open(self.abspath(ref), 'wb') as f:
            f.write(content)

        for name, value in xattrs.iteritems():
            if value is not None:
                self.set_remote_id(ref, value, name=name)

    def delete(self, ref):
        # type: (Text) -> None

        os_path = self.abspath(ref)
        if not os.path.exists(os_path):
            return

        if sys.platform == 'win32':
            # Send2Trash uses a SHFileOperation on Windows, which fails on
            # any path prefixed with "\\?\" (from official documentation).
            # So removing that prefix.
            os_path = os_path.lstrip('\\\\?\\')

        log.trace('Trashing %r', os_path)

        # Send2Trash needs bytes
        if not isinstance(os_path, bytes):
            os_path = os_path.encode(sys.getfilesystemencoding() or 'utf-8')

        locker = self.unlock_ref(os_path, is_abs=True)
        try:
            send2trash(os_path)
        except OSError as exc:
            log.exception('Cannot trash %r', os_path)
            try:
                # WindowsError(None, None, path, retcode)
                _, _, _, retcode = exc.args
            except:
                pass
            else:
                exc.winerror = retcode
            exc.trash_issue = True
            raise exc
        finally:
            # Don't want to unlock the current deleted
            self.lock_ref(os_path, locker & 2, is_abs=True)

    def delete_final(self, ref):
        # type: (Text) -> None

        global error
        error = None

        def onerror(func, path, exc_info):
            """ Assign the error only once. """
            global error
            if not error:
                error = exc_info[1]

        locker = 0
        parent_ref = None
        try:
            if ref != '/':
                parent_ref = os.path.dirname(ref)
                locker = self.unlock_ref(parent_ref, unlock_parent=False)
            self.unset_readonly(ref)
            os_path = self.abspath(ref)
            if os.path.isfile(os_path):
                os.unlink(os_path)
            elif os.path.isdir(os_path):
                # Override `onerror` to catch the 1st exception and let other
                # documents to be deleted.
                shutil.rmtree(os_path, onerror=onerror)
                if error:
                    raise error
        finally:
            if parent_ref is not None:
                self.lock_ref(parent_ref, locker)

    def exists(self, ref):
        # type: (Text) -> bool

        return os.path.exists(self.abspath(ref))

    def rename(self, ref, to_name):
        # type: (Text, Text) -> FileInfo
        """ Rename a local file or folder. """

        new_name = safe_filename(to_name)
        source_os_path = self.abspath(ref)
        parent = ref.rsplit(u'/', 1)[0]
        old_name = ref.rsplit(u'/', 1)[1]
        parent = u'/' if parent == '' else parent
        locker = self.unlock_ref(source_os_path, is_abs=True)
        try:
            # Check if only case renaming
            if (old_name != new_name
                    and old_name.lower() == new_name.lower()
                    and not self.is_case_sensitive()):
                # Must use a temp rename as FS is not case sensitive
                temp_path = os.path.join(tempfile.gettempdir(),
                                         unicode(uuid.uuid4()))
                os.rename(source_os_path, temp_path)
                source_os_path = temp_path
                # Try the os rename part
                target_os_path = self.abspath(os.path.join(parent, new_name))
            else:
                target_os_path, new_name = self._abspath_deduped(
                    parent, new_name, old_name)
            if old_name != new_name:
                os.rename(source_os_path, target_os_path)
            if sys.platform == 'win32':
                # See http://msdn.microsoft.com/en-us/library/aa365535%28v=vs.85%29.aspx
                ctypes.windll.kernel32.SetFileAttributesW(
                    unicode(target_os_path), 128)
            new_ref = self.get_children_ref(parent, new_name)
            return self.get_info(new_ref)
        finally:
            self.lock_ref(source_os_path, locker & 2, is_abs=True)

    def move(self, ref, new_parent_ref, name=None):
        # type: (Text, Text, Optional[Text]) -> FileInfo
        """ Move a local file or folder into another folder. """

        if ref == u'/':
            raise ValueError('Cannot move the toplevel folder.')

        name = name if name is not None else ref.rsplit(u'/', 1)[1]
        filename = self.abspath(ref)
        target_os_path, new_name = self._abspath_deduped(new_parent_ref, name)
        locker = self.unlock_ref(filename, is_abs=True)
        parent = os.path.dirname(target_os_path)
        new_locker = self.unlock_ref(parent, unlock_parent=False, is_abs=True)
        try:
            os.rename(filename, target_os_path)
            new_ref = self.get_children_ref(new_parent_ref, new_name)
            return self.get_info(new_ref)
        finally:
            self.lock_ref(filename, locker & 2, is_abs=True)
            self.lock_ref(parent, locker & 1 | new_locker, is_abs=True)

    def change_file_date(self, filename, mtime=None, ctime=None):
        # type: (Text, Optional[Text], Optional[Text]) -> None
        """
        Change the FS modification and creation dates of a file.

        Since there is no creation time on GNU/Linux, the ctime
        will not be taken into account if running on this platform.

        :param filename: The file to modify
        :param mtime: The modification time
        :param ctime: The creation time
        """

        log.trace('Setting file dates for %r (ctime=%r, mtime=%r)',
                  filename, ctime, mtime)
        if mtime:
            try:
                mtime = int(mtime)
            except ValueError:
                mtime = mktime(strptime(mtime, '%Y-%m-%d %H:%M:%S'))
            os.utime(filename, (mtime, mtime))

        if ctime:
            try:
                ctime = datetime.fromtimestamp(ctime)
            except TypeError:
                ctime = datetime.strptime(ctime, '%Y-%m-%d %H:%M:%S')

            if sys.platform == 'darwin':
                if isinstance(filename, unicode):
                    filename = filename.encode('utf8')
                os.system('SetFile -d "{}" "{}"'.format(
                    ctime.strftime('%m/%d/%Y %H:%M:%S'), filename))
            elif sys.platform == 'win32':
                winfile = win32file.CreateFile(
                    filename,
                    win32con.GENERIC_WRITE,
                    (win32con.FILE_SHARE_READ
                     | win32con.FILE_SHARE_WRITE
                     | win32con.FILE_SHARE_DELETE),
                    None,
                    win32con.OPEN_EXISTING,
                    win32con.FILE_ATTRIBUTE_NORMAL,
                    None)
                win32file.SetFileTime(winfile, ctime)

    def is_inside(self, abspath):
        # type: (Text) -> bool

        return abspath.startswith(self.base_folder)

    def get_path(self, abspath):
        # type: (Text) -> Text
        """ Relative path to the local client from an absolute OS path. """

        if isinstance(abspath, bytes):
            abspath = abspath.decode(sys.getfilesystemencoding() or 'utf-8')

        _, _, path = abspath.partition(self.base_folder)
        if not path:
            return '/'
        return path.replace(os.path.sep, '/')

    def abspath(self, ref):
        # type: (Text) -> Text
        """ Absolute path on the operating system. """

        if not ref.startswith(u'/'):
            raise ValueError(
                'LocalClient expects ref starting with "/"', locals())

        path_suffix = ref[1:].replace('/', os.path.sep)
        path = normalized_path(os.path.join(self.base_folder, path_suffix))
        return safe_long_path(path)

    def _abspath_deduped(self, parent, orig_name, old_name=None):
        # type: (Text, Text, Optional[Text]) -> Tuple[Text, Text]
        """ Absolute path on the operating system with deduplicated names. """

        # Make name safe by removing invalid chars
        name = safe_filename(orig_name)

        # Decompose the name into actionable components
        name, suffix = os.path.splitext(name)

        os_path = self.abspath(os.path.join(parent, name + suffix))
        if old_name == (name + suffix):
            return os_path, name + suffix
        if not os.path.exists(os_path):
            return os_path, name + suffix
        raise DuplicationDisabledError('De-duplication is disabled')
