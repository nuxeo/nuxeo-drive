# coding: utf-8
import subprocess
from logging import getLogger

from .base import BaseUpdater
from ..options import Options

__all__ = ("Updater",)

log = getLogger(__name__)


class Updater(BaseUpdater):
    """ Windows updater. """

    ext = "exe-admin" if Options.system_wide else "exe"
    release_file = (
        "nuxeo-drive-{version}-admin.exe"
        if Options.system_wide
        else "nuxeo-drive-{version}.exe"
    )

    def install(self, filename: str) -> None:
        """
        The installer will automagically:
            - try to stop Drive, if not already done
            - install the new version
            - start Drive

        So, a big thank you to Inno Setup!
        """

        # Using ping instead of timeout to wait 5 seconds (see NXDRIVE-1890)
        cmd = f'ping 127.0.0.1 -n 6 > nul && "{filename}" /verysilent /start=auto'
        log.info("Launching the auto-updater in 5 seconds ...")
        subprocess.Popen(cmd, shell=True, close_fds=True)

        # Trigger the application exit
        self.appUpdated.emit()
