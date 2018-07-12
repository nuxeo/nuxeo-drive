# coding: utf-8
import subprocess
from logging import getLogger

from .base import BaseUpdater

__all__ = ("Updater",)

log = getLogger(__name__)


class Updater(BaseUpdater):
    """ Windows updater. """

    ext = "exe"
    release_file = "nuxeo-drive-{version}.exe"

    def install(self, filename: str) -> None:
        """
        The installer will automagically:
            - try to stop Drive, if not already done
            - install the new version
            - start Drive

        So, a big thank you to Inno Setup!
        """

        cmd = 'timeout /t 5 /nobreak > nul && "{}" /verysilent /start=auto'.format(
            filename
        )
        log.debug("Launching the auto-updater in 5 seconds ...")
        subprocess.Popen(cmd, shell=True, close_fds=True)

        # Trigger the application exit
        self.appUpdated.emit()
