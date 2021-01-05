""" API to access local resources for synchronization. """

import errno
import os
import re
import shutil
import subprocess
import unicodedata
from logging import getLogger
from pathlib import Path
from typing import Union

from send2trash import send2trash

from ...utils import lock_path, unlock_path
from .base import LocalClientMixin

__all__ = ("LocalClient",)

log = getLogger(__name__)


class LocalClient(LocalClientMixin):
    """GNU/Linux client API implementation for the local file system."""

    shared_icons = Path.home() / ".local/share/icons"

    def has_folder_icon(self, ref: Path, /) -> bool:
        """Check if the folder icon is set."""
        emblem = self.shared_icons / "emblem-nuxeo.svg"

        if not emblem.is_file():
            return False

        folder = self.abspath(ref)
        cmd = ["gio", "info", "-a", "metadata", str(folder)]
        try:
            output = subprocess.check_output(cmd, encoding="utf-8")
        except Exception:
            log.warning(f"Could not check the metadata of {folder!r}", exc_info=True)
            return False

        matcher = re.compile(r"metadata::emblems: \[.*emblem-nuxeo.*\]")
        return bool(matcher.findall(output))

    @staticmethod
    def get_path_remote_id(path: Path, /, *, name: str = "ndrive") -> str:
        """Get a given extended attribute from a file/folder."""
        try:
            return (
                os.getxattr(path, f"user.{name}").decode("utf-8", errors="ignore")  # type: ignore
                or ""
            )
        except OSError:
            return ""

    @staticmethod
    def remove_remote_id_impl(path: Path, /, *, name: str = "ndrive") -> None:
        """Remove a given extended attribute."""
        try:
            os.removexattr(path, f"user.{name}")  # type: ignore
        except OSError as exc:
            # EPROTONOSUPPORT: protocol not supported (xattr)
            # ENODATA: no data available
            if exc.errno not in (errno.ENODATA, errno.EPROTONOSUPPORT):
                raise exc

    def set_folder_icon(self, ref: Path, icon: Path, /) -> None:
        """Use commandline to customize the folder icon."""
        folder = self.abspath(ref)

        # Emblems icons must be saved in $XDG_DATA_HOME/icons to be accessible
        emblem = self.shared_icons / "emblem-nuxeo.svg"
        emblem.parent.mkdir(parents=True, exist_ok=True)

        log.debug(f"Setting the folder emblem of {folder!r} using {emblem!r}")

        if not emblem.is_file():
            try:
                shutil.copy(icon, emblem)
            except shutil.Error:
                log.warning(f"Could not copy {icon!r} to {self.shared_icons!r}")
                return

        cmd = [
            "gio",
            "set",
            "-t",
            "stringv",
            str(folder),
            "metadata::emblems",
            "emblem-nuxeo",
        ]
        try:
            subprocess.check_call(cmd)
        except Exception:
            log.warning(f"Could not set the folder emblem on {folder!r}", exc_info=True)

    @staticmethod
    def set_path_remote_id(
        path: Path, remote_id: Union[bytes, str], /, *, name: str = "ndrive"
    ) -> None:
        if not isinstance(remote_id, bytes):
            remote_id = unicodedata.normalize("NFC", remote_id).encode("utf-8")

        locker = unlock_path(path, unlock_parent=False)
        try:
            stat_ = path.stat()
            os.setxattr(path, f"user.{name}", remote_id)  # type: ignore
            os.utime(path, (stat_.st_atime, stat_.st_mtime))
        except FileNotFoundError:
            pass
        finally:
            lock_path(path, locker)

    def trash(self, path: Path, /) -> None:
        """Move a given file or folder to the trash. Untrash is possible then."""
        send2trash(str(path))
