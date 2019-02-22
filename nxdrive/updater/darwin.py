# coding: utf-8
import os
import shutil
import subprocess
from contextlib import suppress
from logging import getLogger

from .base import BaseUpdater
from ..constants import APP_NAME
from ..utils import force_decode

__all__ = ("Updater",)

log = getLogger(__name__)


class Updater(BaseUpdater):
    """ macOS updater. """

    ext = "dmg"
    release_file = "nuxeo-drive-{version}.dmg"

    def install(self, filename: str) -> None:
        """
        Steps:
            - mount the.dmg
            - backup the current .app
            - copy content
            - restart Drive

        On any error, the backup will be reverted.
        """
        # Unload the Finder Sync extension
        self.manager.osi._cleanup()

        log.debug(f"Mounting {filename!r}")
        mount_info = subprocess.check_output(["hdiutil", "mount", filename])
        lines = mount_info.splitlines()
        mount_dir = force_decode(lines[-1].split(b"\t")[-1])
        log.debug(f"Mounted in {mount_dir!r}")

        self._backup()
        self._set_progress(70)

        try:
            self._copy(mount_dir)
            self._set_progress(80)
        except:
            log.exception("Content copy error")
            self._backup(restore=True)
        finally:
            self._cleanup(filename)
            self._set_progress(90)
            log.debug(f"Unmounting {mount_dir!r}")
            subprocess.check_call(["hdiutil", "unmount", mount_dir])

        # Check if the new application exists
        app = f"/Applications/{APP_NAME}.app"
        if not os.path.isdir(app):
            log.error(f"{app!r} does not exist, auto-update failed")
            return

        # Trigger the application exit + restart
        self._set_progress(100)
        self._restart()
        self.appUpdated.emit()

    def _backup(self, restore: bool = False) -> None:
        """ Backup or restore the current application. """

        src = f"/Applications/{APP_NAME}.app"
        dst = src + ".old"

        if restore:
            src, dst = dst, src

        if not os.path.isdir(src):
            return

        log.debug(f"Moving {src!r} -> {dst!r}")
        shutil.move(src, dst)

    def _cleanup(self, filename: str) -> None:
        """ Remove some files. """

        # The backup
        path = f"/Applications/{APP_NAME}.app.old"
        with suppress(OSError):
            shutil.rmtree(path)
            log.debug(f"Deleted {path!r}")

        # The temporary DMG
        with suppress(OSError):
            os.remove(filename)
            log.debug(f"Deleted {filename!r}")

    def _copy(self, mount_dir: str) -> None:
        """ Copy the new application content to /Applications. """

        src = f"{mount_dir}/{APP_NAME}.app"
        dst = f"/Applications/{APP_NAME}.app"
        log.debug(f"Copying {src!r} -> {dst!r}")
        shutil.copytree(src, dst)

    def _restart(self) -> None:
        """
        Restart the current application to take into account the new version.
        """

        cmd = f'sleep 5 ; open "/Applications/{APP_NAME}.app"'
        log.debug(f"Launching the new {APP_NAME} version in 5 seconds ...")
        subprocess.Popen(cmd, shell=True, close_fds=True)
