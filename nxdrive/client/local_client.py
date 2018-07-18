# coding: utf-8
""" API to access local resources for synchronization. """

import errno
import hashlib
import os
import re
import shutil
import tempfile
import unicodedata
import uuid
from contextlib import suppress
from datetime import datetime
from logging import getLogger
from time import mktime, strptime
from typing import Any, List, Optional, Tuple, Union

from send2trash import send2trash

from ..constants import (
    DOWNLOAD_TMP_FILE_PREFIX,
    DOWNLOAD_TMP_FILE_SUFFIX,
    FILE_BUFFER_SIZE,
    LINUX,
    MAC,
    UNACCESSIBLE_HASH,
    WINDOWS,
)
from ..exceptions import DuplicationDisabledError, NotFound
from ..options import Options
from ..utils import (
    force_decode,
    guess_digest_algorithm,
    lock_path,
    normalized_path,
    safe_filename,
    safe_long_path,
    set_path_readonly,
    unlock_path,
    unset_path_readonly,
)

if WINDOWS:
    import ctypes
    import win32api
    import win32con
    import win32file
else:
    import stat
    import xattr

__all__ = ("FileInfo", "LocalClient")

log = getLogger(__name__)


class FileInfo:
    """ Data Transfer Object for file info on the Local FS. """

    def __init__(
        self,
        root: str,
        path: str,
        folderish: bool,
        last_modification_time: Union[datetime, int],
        **kwargs: Any,
    ) -> None:
        # Function to check during long-running processing like digest
        # computation if the synchronization thread needs to be suspended
        self.check_suspended = kwargs.pop("check_suspended", None)
        self.size = kwargs.pop("size", 0)
        filepath = os.path.join(root, path[1:].replace("/", os.path.sep))
        root = unicodedata.normalize("NFC", root)
        path = unicodedata.normalize("NFC", path)
        normalized_filepath = os.path.join(root, path[1:].replace("/", os.path.sep))
        self.filepath = normalized_filepath

        # NXDRIVE-188: normalize name on the file system if not normalized
        if not MAC and os.path.exists(filepath) and normalized_filepath != filepath:
            log.debug(
                "Forcing normalization of %r to %r", filepath, normalized_filepath
            )
            os.rename(filepath, normalized_filepath)

        self.path = path  # the truncated path (under the root)
        self.folderish = folderish  # True if a Folder
        self.remote_ref = kwargs.pop("remote_ref", None)

        # Last OS modification date of the file
        self.last_modification_time = last_modification_time

        # Function to use
        self._digest_func = kwargs.pop("digest_func", "MD5").lower()

        # Precompute base name once and for all are it's often useful in
        # practice
        self.name = os.path.basename(path)

    def __repr__(self) -> str:
        return "FileInfo<path=%r, remote_ref=%r>" % (self.filepath, self.remote_ref)

    def get_digest(self, digest_func: str = None) -> Optional[str]:
        """ Lazy computation of the digest. """

        if self.folderish:
            return None

        digest_func = digest_func or self._digest_func
        digester = getattr(hashlib, digest_func, None)
        if digester is None:
            raise ValueError("Unknown digest method: " + digest_func)

        h = digester()
        try:
            with open(safe_long_path(self.filepath), "rb") as f:
                while True:
                    # Check if synchronization thread was suspended
                    if self.check_suspended is not None:
                        self.check_suspended("Digest computation: %s" % self.filepath)
                    buf = f.read(FILE_BUFFER_SIZE)
                    if not buf:
                        break
                    h.update(buf)
        except OSError:
            return UNACCESSIBLE_HASH
        return h.hexdigest()


class LocalClient:
    """ Client API implementation for the local file system. """

    CASE_RENAME_PREFIX = "driveCaseRename_"
    _case_sensitive = None

    def __init__(self, base_folder: str, **kwargs: Any) -> None:
        self._digest_func = kwargs.pop("digest_func", "md5")
        # Function to check during long-running processing like digest
        # computation if the synchronization thread needs to be suspended
        self.check_suspended = kwargs.pop("check_suspended", None)

        while len(base_folder) > 1 and base_folder.endswith(os.path.sep):
            base_folder = base_folder[:-1]
        self.base_folder = base_folder

        self.is_case_sensitive()

    def __repr__(self) -> str:
        return (
            "<{name}"
            " base_folder={cls.base_folder!r},"
            " is_case_sensitive={cls._case_sensitive!r}"
            ">"
        ).format(name=type(self).__name__, cls=self)

    def is_case_sensitive(self) -> bool:
        if self._case_sensitive is None:
            path = tempfile.mkdtemp(prefix=".caseTest_")
            self._case_sensitive = not os.path.isdir(path.upper())
            os.rmdir(path)
        return self._case_sensitive

    @staticmethod
    def is_temp_file(filename: str) -> bool:
        return filename.startswith(DOWNLOAD_TMP_FILE_PREFIX) and filename.endswith(
            DOWNLOAD_TMP_FILE_SUFFIX
        )

    def set_readonly(self, ref: str) -> None:
        path = self.abspath(ref)
        set_path_readonly(path)

    def unset_readonly(self, ref: str) -> None:
        path = self.abspath(ref)
        if os.path.exists(path):
            unset_path_readonly(path)

    def clean_xattr_root(self) -> None:
        self.unlock_ref("/", unlock_parent=False)
        with suppress(OSError):
            self.remove_root_id()
        self.clean_xattr_folder_recursive("/")

    def clean_xattr_folder_recursive(self, path: str) -> None:
        for child in self.get_children_info(path):
            locker = self.unlock_ref(child.path, unlock_parent=False)
            if child.remote_ref is not None:
                self.remove_remote_id(child.path)
            self.lock_ref(child.path, locker)
            if child.folderish:
                self.clean_xattr_folder_recursive(child.path)

    def remove_root_id(self) -> None:
        self.remove_remote_id("/", name="ndriveroot")

    def set_root_id(self, value: bytes) -> None:
        self.set_remote_id("/", value, name="ndriveroot")

    def get_root_id(self) -> Optional[str]:
        return self.get_remote_id("/", name="ndriveroot")

    def _remove_remote_id_windows(self, path: str, name: str = "ndrive") -> None:
        path_alt = path + ":" + name
        try:
            os.remove(path_alt)
        except OSError as e:
            if e.errno != errno.EACCES:
                raise e
            unset_path_readonly(path)
            try:
                os.remove(path_alt)
            finally:
                set_path_readonly(path)

    @staticmethod
    def _remove_remote_id_unix(path: str, name: str = "ndrive") -> None:
        if LINUX:
            name = "user." + name
        try:
            xattr.removexattr(path, name)
        except OSError as exc:
            # EPROTONOSUPPORT: protocol not supported (xattr)
            # ENODATA: no data available
            if exc.errno not in {errno.ENODATA, errno.EPROTONOSUPPORT}:
                raise exc

    def remove_remote_id(self, ref: str, name: str = "ndrive") -> None:
        path = self.abspath(ref)
        log.trace("Removing xattr %r from %r", name, path)
        locker = unlock_path(path, False)
        func = (
            self._remove_remote_id_windows if WINDOWS else self._remove_remote_id_unix
        )
        try:
            func(path, name=name)
        except OSError as exc:
            # ENOENT: file does not exist
            # OSError [Errno 93]: Attribute not found
            if exc.errno not in {errno.ENOENT, 93}:
                raise exc
        finally:
            lock_path(path, locker)

    def has_folder_icon(self, ref: str) -> Union[bool, str]:
        """Check if the folder icon is set.
        On Windows, it may return the version number as str for later use in stats."""

        if MAC:
            return os.path.isfile(os.path.join(self.abspath(ref), "Icon\r"))

        if WINDOWS:
            fname = os.path.join(self.abspath(ref), "desktop.ini")
            with suppress(FileNotFoundError):
                with open(fname) as handler:
                    version = re.findall(r"nuxeo-drive-([0-9.]+).win32\\", handler.read())
                    if version:
                        return version[0]
                return True

        return False

    def set_folder_icon(self, ref: str, icon: str) -> None:
        if MAC:
            self.set_folder_icon_darwin(ref, icon)
        elif WINDOWS:
            self.set_folder_icon_win32(ref, icon)

    def set_folder_icon_win32(self, ref: str, icon: str) -> None:
        """ Configure the icon for a folder on Windows. """

        # Desktop.ini file content
        content = f"""
[.ShellClassInfo]
IconResource={icon},0
[ViewState]
Mode=
Vid=
FolderType=Generic
"""
        # Create the desktop.ini file inside the ReadOnly shared folder.
        os_path = self.abspath(ref)
        filename = os.path.join(os_path, "desktop.ini")
        with suppress(FileNotFoundError):
            os.remove(filename)

        with open(filename, "w") as handler:
            handler.write(content)
        win32api.SetFileAttributes(filename, win32con.FILE_ATTRIBUTE_SYSTEM)
        win32api.SetFileAttributes(filename, win32con.FILE_ATTRIBUTE_HIDDEN)

        # Windows folder use READ_ONLY flag as a customization flag ...
        # https://support.microsoft.com/en-us/kb/326549
        win32api.SetFileAttributes(os_path, win32con.FILE_ATTRIBUTE_READONLY)

    @staticmethod
    def _read_data(file_path: str) -> bytes:
        """ The data file contains macOS icons. """

        with open(file_path, "rb") as dat:
            return dat.read()

    @staticmethod
    def _get_icon_xdata() -> List[int]:
        entry_size = 32
        icon_flag_index = 8
        icon_flag_value = 4
        result = [0] * entry_size
        result[icon_flag_index] = icon_flag_value
        return result

    def set_folder_icon_darwin(self, ref: str, icon: str) -> None:
        """
        macOS: configure a folder with a given custom icon
            1. Read the com.apple.ResourceFork extended attribute from the icon file
            2. Set the com.apple.FinderInfo extended attribute with folder icon flag
            3. Create a Icon file (name: Icon\r) inside the target folder
            4. Set extended attributes com.apple.FinderInfo & com.apple.ResourceFork for icon file (name: Icon\r)
            5. Hide the icon file (name: Icon\r)
        """

        target_folder = self.abspath(ref)

        # Generate the value for 'com.apple.FinderInfo'
        has_icon_xdata = bytes(bytearray(self._get_icon_xdata()))

        # Configure 'com.apple.FinderInfo' for the folder
        xattr.setxattr(target_folder, xattr.XATTR_FINDERINFO_NAME, has_icon_xdata)

        # Create the 'Icon\r' file
        meta_file = os.path.join(target_folder, "Icon\r")
        if os.path.isfile(meta_file):
            os.remove(meta_file)
        open(meta_file, "w").close()

        # Configure 'com.apple.FinderInfo' for the Icon file
        xattr.setxattr(meta_file, xattr.XATTR_FINDERINFO_NAME, has_icon_xdata)

        # Configure 'com.apple.ResourceFork' for the Icon file
        info = self._read_data(icon)
        xattr.setxattr(meta_file, xattr.XATTR_RESOURCEFORK_NAME, info)
        os.chflags(meta_file, stat.UF_HIDDEN)

    def set_remote_id(self, ref: str, remote_id: bytes, name: str = "ndrive") -> None:
        path = self.abspath(ref)

        if not isinstance(remote_id, bytes):
            remote_id = unicodedata.normalize("NFC", remote_id).encode()

        log.trace("Setting xattr %r with value %r on %r", name, remote_id, path)
        locker = unlock_path(path, False)
        if WINDOWS:
            path_alt = path + ":" + name
            try:
                if not os.path.exists(path):
                    raise NotFound()

                stat_ = os.stat(path)
                with open(path_alt, "wb") as f:
                    f.write(remote_id)

                # Avoid time modified change
                os.utime(path, (stat_.st_atime, stat_.st_mtime))
            except FileNotFoundError:
                pass
            except OSError as e:
                # Should not happen
                if e.errno != errno.EACCES:
                    raise e
                unset_path_readonly(path)
                with open(path_alt, "wb") as f:
                    f.write(remote_id)
                set_path_readonly(path)
            finally:
                lock_path(path, locker)
            return

        if LINUX:
            name = "user." + name

        try:
            stat_ = os.stat(path)
            xattr.setxattr(path, name, remote_id)
            os.utime(path, (stat_.st_atime, stat_.st_mtime))
        except FileNotFoundError:
            pass
        finally:
            lock_path(path, locker)

    def get_remote_id(self, ref: str, name: str = "ndrive") -> Optional[str]:
        path = self.abspath(ref)
        value = self.get_path_remote_id(path, name)
        log.trace("Getting xattr %r from %r: %r", name, path, value)
        return value

    @staticmethod
    def get_path_remote_id(path: str, name: str = "ndrive") -> Optional[str]:
        if WINDOWS:
            path += ":" + name
            try:
                with open(path, "rb") as f:
                    return f.read().decode()
            except OSError:
                return None

        if LINUX:
            name = "user." + name

        try:
            return xattr.getxattr(path, name).decode()
        except OSError:
            return None

    def get_info(self, ref: str, raise_if_missing: bool = True) -> Optional[FileInfo]:
        if isinstance(ref, bytes):
            ref = ref.decode()

        os_path = self.abspath(ref)
        if not os.path.exists(os_path):
            if raise_if_missing:
                err = "Could not find doc into {!r}: ref={!r}, os_path={!r}"
                raise NotFound(err.format(self.base_folder, ref, os_path))
            return None

        folderish = os.path.isdir(os_path)
        stat_info = os.stat(os_path)
        size = 0 if folderish else stat_info.st_size
        try:
            mtime = datetime.utcfromtimestamp(stat_info.st_mtime)
        except (ValueError, OverflowError, OSError) as e:
            log.error(
                str(e)
                + "file path: %s. st_mtime value: %s" % (os_path, stat_info.st_mtime)
            )
            if WINDOWS:
                # TODO: NXDRIVE-1236 Remove those ugly fixes
                # TODO: when https://bugs.python.org/issue29097 is fixed
                mtime = datetime.utcfromtimestamp(86400)
            else:
                mtime = datetime.utcfromtimestamp(0)

        # TODO Do we need to load it everytime ?
        remote_ref = self.get_remote_id(ref)
        # On unix we could use the inode for file move detection but that won't
        # work on Windows. To reduce complexity of the code and the possibility
        # to have Windows specific bugs, let's not use the unix inode at all.
        # uid = str(stat_info.st_ino)
        return FileInfo(
            self.base_folder,
            ref,
            folderish,
            mtime,
            digest_func=self._digest_func,
            check_suspended=self.check_suspended,
            remote_ref=remote_ref,
            size=size,
        )

    def is_equal_digests(
        self,
        local_digest: str,
        remote_digest: str,
        local_path: str,
        remote_digest_algorithm: str = None,
    ) -> bool:
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

    def is_ignored(self, parent_ref: str, file_name: str) -> bool:
        """ Note: added parent_ref to be able to filter on size if needed. """

        file_name = force_decode(file_name.lower())

        if file_name.endswith(Options.ignored_suffixes) or file_name.startswith(
            Options.ignored_prefixes
        ):
            return True

        if WINDOWS:
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
        if parent_ref != "/":
            file_name = os.path.basename(parent_ref)
            parent_ref = os.path.dirname(parent_ref)
            result = self.is_ignored(parent_ref, file_name)

        return result

    @staticmethod
    def get_children_ref(parent_ref: str, name: str) -> str:
        if parent_ref == "/":
            return parent_ref + name
        return parent_ref + "/" + name

    def get_children_info(self, ref: str) -> List[FileInfo]:
        os_path = self.abspath(ref)
        result = []
        children = os.listdir(os_path)

        for child_name in sorted(children):
            if self.is_ignored(ref, child_name) or self.is_temp_file(child_name):
                log.debug("Ignoring banned file %r in %r", child_name, os_path)
                continue

            child_ref = self.get_children_ref(ref, child_name)
            try:
                info = self.get_info(child_ref)
            except NotFound:
                log.exception(
                    "The child file has been deleted in the mean time"
                    " or while reading some of its attributes"
                )
                continue
            result.append(info)

        return result

    def unlock_ref(
        self, ref: str, unlock_parent: bool = True, is_abs: bool = False
    ) -> int:
        path = ref if is_abs else self.abspath(ref)
        return unlock_path(path, unlock_parent)

    def lock_ref(self, ref: str, locker: int, is_abs: bool = False) -> None:
        path = ref if is_abs else self.abspath(ref)
        lock_path(path, locker)

    def make_file(self, parent: str, name: str, content: bytes = None) -> str:
        os_path, name = self._abspath_deduped(parent, name)
        locker = self.unlock_ref(parent, unlock_parent=False)
        try:
            with open(os_path, "wb") as f:
                if content:
                    f.write(content)
            if parent == "/":
                return "/" + name
            return parent + "/" + name
        finally:
            self.lock_ref(parent, locker)

    def make_folder(self, parent: str, name: str) -> str:
        os_path, name = self._abspath_deduped(parent, name)
        locker = self.unlock_ref(parent, unlock_parent=False)
        try:
            os.mkdir(os_path)
        finally:
            self.lock_ref(parent, locker)

        # Name should be the actual name of the folder created locally
        name = os.path.basename(os_path)
        if parent == "/":
            return "/" + name
        return parent + "/" + name

    def get_new_file(self, parent: str, name: str) -> Tuple[str, str, str]:
        os_path, name = self._abspath_deduped(parent, name)
        if parent == "/":
            path = "/" + name
        else:
            path = parent + "/" + name
        return path, os_path, name

    def delete(self, ref: str) -> None:
        os_path = self.abspath(ref)
        if not os.path.exists(os_path):
            return

        log.trace("Trashing %r", os_path)
        locker = self.unlock_ref(os_path, is_abs=True)
        try:
            send2trash(os_path)
        except OSError as exc:
            log.error("Cannot trash %r", os_path)
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

    def delete_final(self, ref: str) -> None:
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
            if ref != "/":
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

    def exists(self, ref: str) -> bool:
        return os.path.exists(self.abspath(ref))

    def rename(self, ref: str, to_name: str) -> FileInfo:
        """ Rename a local file or folder. """

        new_name = safe_filename(to_name)
        source_os_path = self.abspath(ref)
        parent = ref.rsplit("/", 1)[0]
        old_name = ref.rsplit("/", 1)[1]
        parent = parent or "/"
        locker = self.unlock_ref(source_os_path, is_abs=True)
        try:
            # Check if only case renaming
            if (
                old_name != new_name
                and old_name.lower() == new_name.lower()
                and not self.is_case_sensitive()
            ):
                # Must use a temp rename as FS is not case sensitive
                temp_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
                os.rename(source_os_path, temp_path)
                source_os_path = temp_path
                # Try the os rename part
                target_os_path = self.abspath(os.path.join(parent, new_name))
            else:
                target_os_path, new_name = self._abspath_deduped(
                    parent, new_name, old_name
                )
            if old_name != new_name:
                os.rename(source_os_path, target_os_path)
            if WINDOWS:
                # See http://msdn.microsoft.com/en-us/library/aa365535%28v=vs.85%29.aspx
                ctypes.windll.kernel32.SetFileAttributesW(str(target_os_path), 128)
            new_ref = self.get_children_ref(parent, new_name)
            return self.get_info(new_ref)
        finally:
            self.lock_ref(source_os_path, locker & 2, is_abs=True)

    def move(self, ref: str, new_parent_ref: str, name: str = None) -> FileInfo:
        """ Move a local file or folder into another folder. """

        if ref == "/":
            raise ValueError("Cannot move the toplevel folder.")

        name = name or ref.rsplit("/", 1)[1]
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

    def change_file_date(
        self, filename: str, mtime: str = None, ctime: str = None
    ) -> None:
        """
        Change the FS modification and creation dates of a file.

        Since there is no creation time on GNU/Linux, the ctime
        will not be taken into account if running on this platform.

        :param filename: The file to modify
        :param mtime: The modification time
        :param ctime: The creation time
        """

        log.trace(
            "Setting file dates for %r (ctime=%r, mtime=%r)", filename, ctime, mtime
        )
        if mtime:
            try:
                mtime = int(mtime)
            except ValueError:
                mtime = mktime(strptime(mtime, "%Y-%m-%d %H:%M:%S"))
            os.utime(filename, (mtime, mtime))

        if ctime:
            try:
                ctime = datetime.fromtimestamp(ctime)
            except TypeError:
                ctime = datetime.strptime(ctime, "%Y-%m-%d %H:%M:%S")

            if MAC:
                if isinstance(filename, bytes):
                    filename = filename.decode()
                os.system(
                    'SetFile -d "{}" "{}"'.format(
                        ctime.strftime("%m/%d/%Y %H:%M:%S"), filename
                    )
                )
            elif WINDOWS:
                winfile = win32file.CreateFile(
                    filename,
                    win32con.GENERIC_WRITE,
                    (
                        win32con.FILE_SHARE_READ
                        | win32con.FILE_SHARE_WRITE
                        | win32con.FILE_SHARE_DELETE
                    ),
                    None,
                    win32con.OPEN_EXISTING,
                    win32con.FILE_ATTRIBUTE_NORMAL,
                    None,
                )
                win32file.SetFileTime(winfile, ctime)

    def get_path(self, abspath: str) -> str:
        """ Relative path to the local client from an absolute OS path. """

        if isinstance(abspath, bytes):
            abspath = abspath.decode()

        _, _, path = abspath.partition(self.base_folder)
        if not path:
            return "/"
        return path.replace(os.path.sep, "/")

    def abspath(self, ref: str) -> str:
        """ Absolute path on the operating system. """

        if not ref.startswith("/"):
            raise ValueError('LocalClient expects ref starting with "/"', locals())

        path_suffix = ref[1:].replace("/", os.path.sep)
        path = normalized_path(os.path.join(self.base_folder, path_suffix))
        return safe_long_path(path)

    def _abspath_deduped(
        self, parent: str, orig_name: str, old_name: str = None
    ) -> Tuple[str, str]:
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
        raise DuplicationDisabledError("De-duplication is disabled")
