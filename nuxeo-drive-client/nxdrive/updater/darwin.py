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
            log.exception('Content copy error')
            self._backup(restore=True)
        finally:
            self._cleanup(filename)
            log.debug('Unmounting %r', mount_dir)
            subprocess.check_call(['hdiutil', 'unmount', mount_dir])

        # Check if the new application exists
        app = '/Applications/{}.app'.format(self.manager.app_name)
        if not os.path.isdir(app):
            log.error('%r does not exist, auto-update failed')
            return

        # Trigger the application exit + restart
        self._restart()
        self.appUpdated.emit()

    def _backup(self, restore=False):
        # type: (Optional[bool]) -> None
        """ Backup or restore the current application. """

        src = '/Applications/{}.app'.format(self.manager.app_name)
        dst = src + '.old'

        if restore:
            src, dst = dst, src

        if not os.path.isdir(src):
            return

        log.debug('Moving %r -> %r', src, dst)
        os.rename(src, dst)

    def _cleanup(self, filename):
        # type: (unicode) -> None
        """ Remove some files. """

        # The backup
        path = '/Applications/{}.app.old'.format(self.manager.app_name)
        try:
            shutil.rmtree(path)
            log.debug('Deleted %r', path)
        except OSError:
            pass

        # The temporary DMG
        try:
            os.remove(filename)
            log.debug('Deleted %r', filename)
        except OSError:
            pass

    def _copy(self, mount_dir):
        # type: (unicode) -> None
        """ Copy the new application content to /Applications. """

        src = '{}/{}.app'.format(mount_dir, self.manager.app_name)
        dst = '/Applications/{}.app'.format(self.manager.app_name)
        log.debug('Copying %r -> %r', src, dst)
        shutil.copytree(src, dst)

    def _restart(self):
        # type: () -> None
        """
        Restart the current application to take into account the new version.
        """

        cmd = 'sleep 5 ; open "/Applications/{}.app"'.format(self.manager.app_name)
        log.debug('Launching the new %s version in 5 secondes ...', self.manager.app_name)
        subprocess.Popen(cmd, shell=True, close_fds=True)
