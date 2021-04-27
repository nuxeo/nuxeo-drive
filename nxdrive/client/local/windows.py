""" API to access local resources for synchronization. """

import ctypes
import errno
import os
import unicodedata
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import Union

import win32api
import win32con
import win32file
from send2trash import send2trash

from ...constants import ROOT
from ...options import Options
from ...utils import (
    force_decode,
    lock_path,
    safe_filename,
    set_path_readonly,
    unlock_path,
    unset_path_readonly,
)
from .base import LocalClientMixin

__all__ = ("LocalClient",)

log = getLogger(__name__)


class LocalClient(LocalClientMixin):
    """Windows client API implementation for the local file system."""

    def change_created_time(self, filepath: Path, d_ctime: datetime, /) -> None:
        """Change the created time of a given file."""
        winfile = win32file.CreateFileW(
            str(filepath),
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
        win32file.SetFileTime(winfile, d_ctime)

    @staticmethod
    def get_path_remote_id(path: Path, /, *, name: str = "ndrive") -> str:
        """Get a given extended attribute from a file/folder."""
        try:
            with open(f"{path}:{name}", "rb") as f:
                return f.read().decode("utf-8", errors="ignore")
        except OSError:
            return ""

    def has_folder_icon(self, ref: Path, /) -> bool:
        """Check if the folder icon is set."""
        return (self.abspath(ref) / "desktop.ini").is_file()

    def is_ignored(self, parent_ref: Path, file_name: str, /) -> bool:
        """Note: added parent_ref to be able to filter on size if needed."""

        file_name = safe_filename(force_decode(file_name.lower()))

        if file_name.endswith(Options.ignored_suffixes) or file_name.startswith(
            Options.ignored_prefixes
        ):
            return True

        # NXDRIVE-465: ignore hidden files on Windows
        ref = parent_ref / file_name
        path = self.abspath(ref)
        is_system = win32con.FILE_ATTRIBUTE_SYSTEM
        is_hidden = win32con.FILE_ATTRIBUTE_HIDDEN
        try:
            attrs = win32api.GetFileAttributes(str(path))
        except win32file.error:
            return False
        if attrs & is_system == is_system:
            return True
        if attrs & is_hidden == is_hidden:
            return True

        # NXDRIVE-655: need to check every parent if they are ignored
        result = False
        if parent_ref != ROOT:
            file_name = parent_ref.name
            parent_ref = parent_ref.parent
            result = self.is_ignored(parent_ref, file_name)

        return result

    def remove_remote_id_impl(self, path: Path, /, *, name: str = "ndrive") -> None:
        """Remove a given extended attribute."""
        path_alt = f"{path}:{name}"
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
    def set_file_attribute(path: Path, /) -> None:
        """Set a special attribute (not extended attribute) to a given file."""
        # 128 = FILE_ATTRIBUTE_NORMAL (a file that does not have other attributes set)
        # See http://msdn.microsoft.com/en-us/library/aa365535%28v=vs.85%29.aspx
        ctypes.windll.kernel32.SetFileAttributesW(str(path), 128)

    def set_folder_icon(self, ref: Path, icon: Path) -> None:
        """Create a special file to customize the folder icon."""
        log.debug(f"Setting the folder icon of {ref!r} using {icon!r}")

        # Desktop.ini file content
        content = f"""
[.ShellClassInfo]
IconResource={icon}
[ViewState]
Mode=
Vid=
FolderType=Generic
"""
        # Create the desktop.ini file inside the ReadOnly shared folder.
        os_path = self.abspath(ref)
        filename = os_path / "desktop.ini"
        filename.unlink(missing_ok=True)

        filename.write_text(content, encoding="utf-8")

        win32api.SetFileAttributes(str(filename), win32con.FILE_ATTRIBUTE_SYSTEM)
        win32api.SetFileAttributes(str(filename), win32con.FILE_ATTRIBUTE_HIDDEN)

        # Windows folder use READ_ONLY flag as a customization flag ...
        # https://support.microsoft.com/en-us/kb/326549
        win32api.SetFileAttributes(str(os_path), win32con.FILE_ATTRIBUTE_READONLY)

    @staticmethod
    def set_path_remote_id(
        path: Path, remote_id: Union[bytes, str], /, *, name: str = "ndrive"
    ) -> None:
        if not isinstance(remote_id, bytes):
            remote_id = unicodedata.normalize("NFC", remote_id).encode("utf-8")

        locker = unlock_path(path, unlock_parent=False)
        path_alt = f"{path}:{name}"
        try:
            stat_ = path.stat()
            with open(path_alt, "wb") as f:
                f.write(remote_id)

                # Force write of file to disk
                f.flush()
                os.fsync(f.fileno())

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

                # Force write of file to disk
                f.flush()
                os.fsync(f.fileno())

            set_path_readonly(path)
        finally:
            lock_path(path, locker)

    def trash(self, path: Path, /) -> None:
        """Move a given file or folder to the trash. Untrash is possible then."""
        send2trash(str(path))
