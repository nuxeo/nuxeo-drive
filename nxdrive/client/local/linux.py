# coding: utf-8
""" API to access local resources for synchronization. """

import errno
import os
import unicodedata
from logging import getLogger
from pathlib import Path
from typing import Union

import xattr
from send2trash import send2trash

from .base import LocalClientMixin
from ...utils import lock_path, unlock_path

__all__ = ("LocalClient",)

log = getLogger(__name__)


class LocalClient(LocalClientMixin):
    """GNU/Linux client API implementation for the local file system."""

    def has_folder_icon(self, ref: Path) -> bool:
        """Check if the folder icon is set."""
        # To be implementation with https://jira.nuxeo.com/browse/NXDRIVE-1831
        return True

    @staticmethod
    def get_path_remote_id(path: Path, name: str = "ndrive") -> str:
        """Get a given extended attribute from a file/folder."""
        try:
            return xattr.getxattr(str(path), f"user.{name}").decode(
                "utf-8", errors="ignore"
            )
        except OSError:
            return ""

    @staticmethod
    def remove_remote_id_impl(path: Path, name: str = "ndrive") -> None:
        """Remove a given extended attribute."""
        try:
            xattr.removexattr(str(path), f"user.{name}")
        except OSError as exc:
            # EPROTONOSUPPORT: protocol not supported (xattr)
            # ENODATA: no data available
            if exc.errno not in (errno.ENODATA, errno.EPROTONOSUPPORT):
                raise exc

    def set_folder_icon(self, ref: Path, icon: Path) -> None:
        """Create a special file to customize the folder icon."""
        log.debug(f"Setting the folder icon of {ref!r} using {icon!r}")
        # To be implementation with https://jira.nuxeo.com/browse/NXDRIVE-1831
        return

    @staticmethod
    def set_path_remote_id(
        path: Path, remote_id: Union[bytes, str], name: str = "ndrive"
    ) -> None:
        if not isinstance(remote_id, bytes):
            remote_id = unicodedata.normalize("NFC", remote_id).encode("utf-8")

        locker = unlock_path(path, False)
        try:
            stat_ = path.stat()
            xattr.setxattr(str(path), f"user.{name}", remote_id)
            os.utime(path, (stat_.st_atime, stat_.st_mtime))
        except FileNotFoundError:
            pass
        finally:
            lock_path(path, locker)

    def trash(self, path: Path) -> None:
        """Move a given file or folder to the trash. Untrash is possible then."""
        send2trash(str(path))
