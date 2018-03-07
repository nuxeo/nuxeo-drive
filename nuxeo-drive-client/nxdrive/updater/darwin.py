# coding: utf-8
import os
import shutil
import subprocess
from logging import getLogger

from .base import BaseUpdater

log = getLogger(__name__)


class Updater(BaseUpdater):
    """ macOS updater. """

    ext = 'dmg'
    release_file = 'nuxeo-drive-{version}.dmg'

    def install(self, filename):
        # type: (unicode) -> None
        """
        Steps:
            - mount the.dmg
            - backup the current .app
            - copy content
            - restart Drive

        On any error, the backup will be reverted.
        """

        log.debug('Mounting %r', filename)
        mount_info = subprocess.check_output(['hdiutil', 'mount', filename])
        mount_dir = mount_info.splitlines()[-1].split('\t')[-1]
        log.debug('Mounted in %r', mount_dir)

        self._backup()

        try:
            self._copy(mount_dir)
        except:
            self._backup(restore=True)
        finally:
            try:
                self._cleanup(filename)
            except:
                pass

            log.debug('Unmounting %r', mount_dir)
            subprocess.check_output(['hdiutil', 'unmount', mount_dir])

        # Trigger the application excit + restart
        self.manager.stopped.connect(self._restart)
        self.appUpdated.emit()

    def _backup(self, restore=False):
        # type: (Optional[bool]) -> None
        """ Backup the current application. """

        src = '/Applications/{}.app'.format(self.managet.app_name)
        dst = src + '.old'

        if restore:
            src, dst = dst, src
            log.debug('Restoring the old application')
        else:
            log.debug('Backing up the current application')

        os.rename(src, dst)

    def _cleanup(self, filename):
        # type: (unicode) -> None
        """ Remove some files. """

        # The backup
        path = '/Applications/{}.app.old'.format(self.managet.app_name)
        shutil.rmtree(path)

        # The temporary DMG
        os.remove(filename)

    def _copy(self, mount_dir):
        # type: (unicode) -> None
        """ Copy the new application content to /Applications. """

        src = '{}/{}.app'.format(mount_dir, self.managet.app_name)
        log.debug('Copying the new application content')
        shutil.copytree(src, '/Applications')

    def _restart(self):
        # type: () -> None
        """
        Restart the current application to take into account the new version.
        """

        app = '/Applications/{}.app'.format(self.managet.app_name)
        subprocess.Popen(['open', app], close_fds=True)
