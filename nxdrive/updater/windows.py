# coding: utf-8
import subprocess
from logging import getLogger

from .base import BaseUpdater

__all__ = ('Updater',)

log = getLogger(__name__)


class Updater(BaseUpdater):
    """ Windows updater. """

    ext = 'exe'
    release_file = 'nuxeo-drive-{version}.exe'

    def install(self, filename: str) -> None:
        """
        The installer will automagically:
            - stop Drive
            - install the new version
            - start Drive

        So, a big thank you to Inno Setup!
        """

        log.debug('Calling %r /verysilent /start=auto', filename)
        subprocess.Popen([filename, '/verysilent', '/start=auto'],
                         close_fds=True)
