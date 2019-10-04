# coding: utf-8
""" API to access local resources for synchronization. """

import errno
import os
import stat
import subprocess
import unicodedata
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import List, Union

import xattr

from .base import LocalClientMixin
from ...utils import lock_path, unlock_path

__all__ = ("LocalClient",)

log = getLogger(__name__)


class LocalClient(LocalClientMixin):
    """macOS Client API implementation."""

    def change_created_time(self, filepath: Path, d_ctime: datetime) -> None:
        """Change the created time of a given file."""
        cmd = ["touch", "-mt", d_ctime.strftime("%Y%m%d%H%M.%S"), str(filepath)]
        subprocess.check_call(cmd)

    def has_folder_icon(self, ref: Path) -> bool:
        """Check if the folder icon is set."""
        return (self.abspath(ref) / "Icon\r").is_file()

    @staticmethod
    def get_path_remote_id(path: Path, name: str = "ndrive") -> str:
        """Get a given extended attribute from a file/folder."""
        try:
            return xattr.getxattr(str(path), name).decode("utf-8", errors="ignore")
        except OSError:
            return ""

    @staticmethod
    def _get_icon_xdata() -> List[int]:
        entry_size = 32
        icon_flag_index = 8
        icon_flag_value = 4
        result = [0] * entry_size
        result[icon_flag_index] = icon_flag_value
        return result

    def remove_remote_id_impl(self, path: Path, name: str = "ndrive") -> None:
        """Remove a given extended attribute."""
        try:
            xattr.removexattr(str(path), name)
        except OSError as exc:
            # EPROTONOSUPPORT: protocol not supported (xattr)
            # ENODATA: no data available
            if exc.errno not in (errno.ENODATA, errno.EPROTONOSUPPORT):
                raise exc

    def set_folder_icon(self, ref: Path, icon: Path) -> None:
        """Create a special file to customize the folder icon.
            1. Read the com.apple.ResourceFork extended attribute from the icon file
            2. Set the com.apple.FinderInfo extended attribute with folder icon flag
            3. Create a Icon file (name: Icon\r) inside the target folder
            4. Set extended attributes com.apple.FinderInfo & com.apple.ResourceFork for icon file (name: Icon\r)
            5. Hide the icon file (name: Icon\r)
        """
        log.debug(f"Setting the folder icon of {ref!r} using {icon!r}")

        target_folder = self.abspath(ref)

        # Generate the value for 'com.apple.FinderInfo'
        has_icon_xdata = bytes(bytearray(self._get_icon_xdata()))

        # Configure 'com.apple.FinderInfo' for the folder
        xattr.setxattr(str(target_folder), xattr.XATTR_FINDERINFO_NAME, has_icon_xdata)

        # Create the 'Icon\r' file
        meta_file = target_folder / "Icon\r"
        if meta_file.is_file():
            meta_file.unlink()
        meta_file.touch()

        # Configure 'com.apple.FinderInfo' for the Icon file
        xattr.setxattr(str(meta_file), xattr.XATTR_FINDERINFO_NAME, has_icon_xdata)

        # Configure 'com.apple.ResourceFork' for the Icon file
        info = icon.read_bytes()
        xattr.setxattr(str(meta_file), xattr.XATTR_RESOURCEFORK_NAME, info)
        os.chflags(meta_file, stat.UF_HIDDEN)  # type: ignore

    @staticmethod
    def set_path_remote_id(
        path: Path, remote_id: Union[bytes, str], name: str = "ndrive"
    ) -> None:
        if not isinstance(remote_id, bytes):
            remote_id = unicodedata.normalize("NFC", remote_id).encode("utf-8")

        locker = unlock_path(path, False)
        try:
            stat_ = path.stat()
            xattr.setxattr(str(path), name, remote_id)
            os.utime(path, (stat_.st_atime, stat_.st_mtime))
        except FileNotFoundError:
            pass
        finally:
            lock_path(path, locker)
