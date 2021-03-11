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
from AppKit import NSWorkspace, NSWorkspaceRecycleOperation

from ...utils import lock_path, unlock_path
from .base import LocalClientMixin

__all__ = ("LocalClient",)

log = getLogger(__name__)


class LocalClient(LocalClientMixin):
    """macOS Client API implementation."""

    def change_created_time(self, filepath: Path, d_ctime: datetime, /) -> None:
        """Change the created time of a given file."""
        cmd = ["touch", "-mt", d_ctime.strftime("%Y%m%d%H%M.%S"), str(filepath)]
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
            # Note: This is mostly due to the new Apple security layer asking for permissions.
            # Note: Passing "exc_info=True" is useless as there will be no useful details.
            log.warning(f"Cannot change the created time of {filepath!r}")

    def has_folder_icon(self, ref: Path, /) -> bool:
        """Check if the folder icon is set."""
        return (self.abspath(ref) / "Icon\r").is_file()

    @staticmethod
    def get_path_remote_id(path: Path, /, *, name: str = "ndrive") -> str:
        """Get a given extended attribute from a file/folder."""
        try:
            return (
                xattr.getxattr(str(path), name).decode("utf-8", errors="ignore") or ""
            )
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

    def remove_remote_id_impl(self, path: Path, /, *, name: str = "ndrive") -> None:
        """Remove a given extended attribute."""
        try:
            xattr.removexattr(str(path), name)
        except OSError as exc:
            # EPROTONOSUPPORT: protocol not supported (xattr)
            # ENODATA: no data available
            if exc.errno not in (errno.ENODATA, errno.EPROTONOSUPPORT):
                raise exc

    def set_folder_icon(self, ref: Path, icon: Path, /) -> None:
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
        meta_file.unlink(missing_ok=True)
        meta_file.touch()

        # Configure 'com.apple.FinderInfo' for the Icon file
        xattr.setxattr(str(meta_file), xattr.XATTR_FINDERINFO_NAME, has_icon_xdata)

        # Configure 'com.apple.ResourceFork' for the Icon file
        info = icon.read_bytes()
        xattr.setxattr(str(meta_file), xattr.XATTR_RESOURCEFORK_NAME, info)
        os.chflags(meta_file, stat.UF_HIDDEN)  # type: ignore

    @staticmethod
    def set_path_remote_id(
        path: Path, remote_id: Union[bytes, str], /, *, name: str = "ndrive"
    ) -> None:
        if not isinstance(remote_id, bytes):
            remote_id = unicodedata.normalize("NFC", remote_id).encode("utf-8")

        locker = unlock_path(path, unlock_parent=False)
        try:
            stat_ = path.stat()
            xattr.setxattr(str(path), name, remote_id)
            os.utime(path, (stat_.st_atime, stat_.st_mtime))
        except FileNotFoundError:
            pass
        finally:
            lock_path(path, locker)

    def trash(self, path: Path, /) -> None:
        """Move a given file or folder to the trash. Untrash is possible then."""
        # Using deprecated APIs that still works on Mojave.
        # See next commented code when it will no more work.
        parent, files = str(path.parent), [path.name]
        ws = NSWorkspace.sharedWorkspace()
        ws.performFileOperation_source_destination_files_tag_(
            NSWorkspaceRecycleOperation, parent, "", files, None
        )

        """
        # Code kept for future usage, when Apple will remove those deprecated APIs (or PyObjC)
        # will need to define:
        #       self.mac_ver = ...
        if version_lt(self.mac_ver, "10.14"):
            # Before Mojave (that code actually works on Mojave though, but APIs are deprecated)
            parent, files = str(path.parent),  [path.name]
            ws = NSWorkspace.sharedWorkspace()
            ws.performFileOperation_source_destination_files_tag_(
                NSWorkspaceRecycleOperation, parent, "", files, None
            )
        else:
            # Mojave and newer
            from AppKit import NSURL
            from ScriptingBridge import SBApplication

            targetfile = NSURL.fileURLWithPath_(str(path))
            finder = SBApplication.applicationWithBundleIdentifier_("com.apple.Finder")
            items = finder.items().objectAtLocation_(targetfile)
            items.delete()
            del finder
        """
