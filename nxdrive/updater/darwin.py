# coding: utf-8
import re
import shutil
import subprocess
import sys
from contextlib import suppress
from logging import getLogger
from pathlib import Path

from ..constants import APP_NAME
from ..utils import force_decode
from .base import BaseUpdater

__all__ = ("Updater",)

log = getLogger(__name__)


class Updater(BaseUpdater):
    """macOS updater.

    The updater is path agnostic: it will update the application
    whatever the current location of the application. Ideally it
    will be /Applications, but it can also be $HOME/Applications
    for testing or users having less rights.
    """

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
        self.manager.osi.cleanup()

        exe_path = sys.executable
        m = re.match(r"(.*\.app).*", exe_path)
        self.final_app = Path(m.group(1) if m else exe_path)

        log.info(f"Mounting {filename!r}")
        mount_info = subprocess.check_output(["hdiutil", "mount", filename])
        lines = mount_info.splitlines()
        mount_dir = force_decode(lines[-1].split(b"\t")[-1])
        log.info(f"Mounted in {mount_dir!r}")

        self._backup()
        self._set_progress(70)

        try:
            self._copy(mount_dir)
            self._set_progress(80)
        except Exception:
            log.exception("Content copy error")
            self._backup(restore=True)
        finally:
            self._cleanup(filename)
            self._set_progress(90)
            log.info(f"Unmounting {mount_dir!r}")
            try:
                subprocess.check_call(["hdiutil", "unmount", mount_dir, "-force"])
            except subprocess.CalledProcessError:
                log.warning(
                    f"Unmount failed, you will have to do it manually (Catalina feature).",
                    exc_info=True,
                )

        # Check if the new application exists
        if not self.final_app.is_dir():
            log.error(f"{self.final_app!r} does not exist, auto-update failed")
            return

        # Trigger the application exit + restart
        self._set_progress(100)
        self._restart()
        self.appUpdated.emit()

    def _backup(self, restore: bool = False) -> None:
        """ Backup or restore the current application. """

        src = self.final_app
        dst = src.with_suffix(f"{src.suffix}.old")

        if restore:
            src, dst = dst, src

        if not src.is_dir():
            return

        # Delete eventual obsolete backup
        with suppress(FileNotFoundError):
            shutil.rmtree(dst)

        log.info(f"Moving {src!r} -> {dst!r}")
        shutil.move(src, dst)

    def _cleanup(self, filename: str) -> None:
        """ Remove some files. """

        paths = (f"{self.final_app}.old", filename)
        for path in paths:
            with suppress(OSError):
                shutil.rmtree(path)
                log.info(f"Deleted {path!r}")

    def _copy(self, mount_dir: str) -> None:
        """ Copy the new application content to /Applications. """

        src = f"{mount_dir}/{APP_NAME}.app"
        log.info(f"Copying {src!r} -> {self.final_app!r}")
        shutil.copytree(src, self.final_app)

    def _restart(self) -> None:
        """
        Restart the current application to take into account the new version.
        """

        cmd = f'sleep 5 ; open "{self.final_app}"'
        log.info(f"Launching the new {APP_NAME} version in 5 seconds ...")
        subprocess.Popen(cmd, shell=True, close_fds=True)
