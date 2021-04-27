import os
import shutil
import stat
import subprocess
from logging import getLogger
from pathlib import Path

from ..constants import APP_NAME
from .base import BaseUpdater

__all__ = ("Updater",)

log = getLogger(__name__)


class Updater(BaseUpdater):
    """GNU/Linux updater."""

    ext = "appimage"
    release_file = "nuxeo-drive-{version}-x86_64.AppImage"

    def install(self, filename: str, /) -> None:
        """
        Steps:
            - move the new executable next to the current running AppImage file
            - restart Drive

        Note 1: on any error, nothing will be handled.
        Note 2: the old executable will still be present on the disk after the restart.
        """
        # Destination file (removing the salt from the file name)
        original_executable = Path(os.getenv("APPIMAGE", ""))  # Set by AppImage
        new_executable = str(original_executable.parent / Path(filename).name[33:])
        log.debug(f"Moving {filename!r} -> {new_executable!r}")
        shutil.move(filename, new_executable)

        log.debug(f"Adjusting execution rights on {new_executable!r}")
        os.chmod(new_executable, os.stat(new_executable).st_mode | stat.S_IXUSR)

        self._restart(new_executable)

    def _restart(self, executable: str, /) -> None:
        """
        Restart the current application to take into account the new version.
        """

        cmd = f'sleep 5 ; "{executable}"&'
        log.info(f"Launching the new {APP_NAME} version in 5 seconds ...")
        log.debug(f"Full command line: {cmd}")
        subprocess.Popen(cmd, shell=True, close_fds=True)

        # Trigger the application exit
        self.appUpdated.emit()
