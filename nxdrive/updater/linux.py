# coding: utf-8
import shutil
import subprocess
from logging import getLogger
from pathlib import Path

from .base import BaseUpdater
from ..constants import APP_NAME
from ..options import Options

__all__ = ("Updater",)

log = getLogger(__name__)


class Updater(BaseUpdater):
    """ GNU/Linux updater. """

    ext = "appimage"
    release_file = "nuxeo-drive-{version}-x86_64.AppImage"

    def install(self, filename: str) -> None:
        """
        Steps:
            - move the new executable into the $HOME folder
            - restart Drive

        Note 1: on any error, nothing will be handled.
        Note 2: the old version executable will still be present on the disk after the restart.
        """

        # Destination file (removing the salt from the file name)
        file = str(Options.home / Path(filename).name[33:])

        # We cannot guess the actual location of the original executable as the AppImage
        # is mounted into a temporary folder. So we just move the new executable in the
        # $HOME folder.
        log.debug(f"Moving {filename!r} -> {file!r}")
        shutil.move(filename, file)

        log.debug(f"Adjusting execution rights on {file!r}")
        subprocess.check_call(["chmod", "a+x", file])

        self._restart(file)

    def _restart(self, executable: str) -> None:
        """
        Restart the current application to take into account the new version.
        """
        cmd = f'sleep 5 ; "{executable}"&'
        log.info(f"Launching the new {APP_NAME} version in 5 seconds ...")
        subprocess.Popen(cmd, shell=True, close_fds=True)

        # Trigger the application exit
        self.appUpdated.emit()
