# coding: utf-8
import msilib
import os
import subprocess
from logging import getLogger

from .base import BaseUpdater

log = getLogger(__name__)


class Updater(BaseUpdater):
    """ Windows updater. """

    ext = 'exe'
    release_file = 'nuxeo-drive-{version}.exe'

    def install(self, filename):
        # type: (unicode) -> None
        """
        The installer will automagically:
            - stop Drive
            - install the new version
            - start Drive

        So, a big thank you to Inno Setup!
        """

        try:
            self.manager.osi.uninstall()
        except:
            pass

        uninst_cmd = ' && '
        try:
            uninst_cmd += self.uninstall()
        except:
            log.error('Uninstallation failed. Installing the new version.')

        cmd = 'timeout /t 5 /nobreak > NUL %s && "%s" /verysilent /start=auto'
        cmd = cmd % (uninst_cmd, filename)
        log.debug('Calling %r', cmd)
        subprocess.Popen(cmd, shell=True, close_fds=True)

        # Trigger the application exit
        self.appUpdated.emit()

    def uninstall(self):
        uninstaller = None
        path = os.path.join(os.environ.get('WINDIR', 'C:\Windows'), 'Installer')
        for filename in os.listdir(path):
            if not filename.endswith('.msi'):
                continue

            full_path = os.path.join(path, filename)
            app = self.get_msi_app(full_path)
            if app.lower().startswith('nuxeo-driv'):
                uninstaller = full_path
                break

        if not uninstaller:
            log.error('No uninstaller found')
            return ''

        return 'msiexec /x {} /quiet /qb'.format(uninstaller)

    def get_msi_app(self, path):
        try:
            db = msilib.OpenDatabase(path, msilib.MSIDBOPEN_READONLY)
            info = db.GetSummaryInformation(1)
            return info.GetProperty(msilib.PID_SUBJECT)
        except:
            return ''
