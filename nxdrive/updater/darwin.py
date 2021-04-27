import plistlib
import re
import shutil
import subprocess
import sys
from contextlib import suppress
from logging import getLogger
from pathlib import Path

from ..constants import APP_NAME
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

    def install(self, filename: str, /) -> None:
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
        self._relocate_in_home()

        self._fix_notarization(filename)
        mount_point = self._mount(filename)

        try:
            self._backup()
            self._set_progress(70)
            self._copy(mount_point)
            self._set_progress(80)
        except Exception:
            log.exception("Content copy error")
            self._backup(restore=True)
        finally:
            self._unmount(mount_point)
            self._cleanup(filename)
            self._set_progress(90)

        # Check if the new application exists
        if not self.final_app.is_dir():
            log.error(f"{self.final_app!r} does not exist, auto-update failed")
            return

        # Trigger the application exit + restart
        self._set_progress(100)
        self._restart()

    def _relocate_in_home(self) -> None:
        """Ensure the app is located into $HOME/Applications."""
        if str(self.final_app.parent) != "/Applications":
            # Likely already at the good location
            return

        new_location = Path().home() / "Applications" / self.final_app.name

        # Delete eventual obsolete version
        with suppress(FileNotFoundError):
            shutil.rmtree(new_location)

        log.info(f"Relocating {self.final_app!r} -> {new_location!r}")
        shutil.move(self.final_app, new_location)
        self.final_app = new_location

    def _mount(self, filename: str, /) -> str:
        """Mount the DMG and return the mount point."""
        cmd = ["hdiutil", "mount", "-plist", filename]
        log.info(f"Mounting file {filename!r}")
        log.debug(f"Full command line: {cmd}")
        output = subprocess.check_output(cmd)

        entities = plistlib.loads(output)["system-entities"]
        entity = next(se for se in entities if se["potentially-mountable"])
        dev_entry = entity["dev-entry"]
        mount_point: str = entity["mount-point"]
        log.info(f"Mounted {dev_entry!r} into {mount_point!r}")
        return mount_point

    def _unmount(self, mount_point: str, /) -> None:
        """Unmount the DMG."""
        cmd = ["hdiutil", "unmount", "-force", mount_point]
        log.info(f"Unmounting {mount_point!r}")
        log.debug(f"Full command line: {cmd}")
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
            log.warning(
                "Unmount failed, you will have to do it manually.",
                exc_info=True,
            )

    def _backup(self, *, restore: bool = False) -> None:
        """Backup or restore the current application."""

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

    def _cleanup(self, filename: str, /) -> None:
        """Remove some files."""

        paths = (f"{self.final_app}.old", filename)
        for path in paths:
            with suppress(OSError):
                shutil.rmtree(path)
                log.info(f"Deleted {path!r}")

    def _copy(self, mount_dir: str, /) -> None:
        """Copy the new application content to /Applications."""

        src = f"{mount_dir}/{APP_NAME}.app"
        log.info(f"Copying {src!r} -> {self.final_app!r}")
        shutil.copytree(src, self.final_app)

    def _fix_notarization(self, path: str, /) -> None:
        """Fix the notarization (enforced security since February 2020)"""
        with suppress(subprocess.CalledProcessError):
            subprocess.check_call(["xattr", "-d", "com.apple.quarantine", path])
            log.info(f"Fixed the notarization on {path!r}")

    def _restart(self) -> None:
        """
        Restart the current application to take into account the new version.
        """

        cmd = f'sleep 5 ; open "{self.final_app}"'
        log.info(f"Launching the new {APP_NAME} version in 5 seconds ...")
        log.debug(f"Full command line: {cmd}")
        subprocess.Popen(cmd, shell=True, close_fds=True)

        # Trigger the application exit
        self.appUpdated.emit()
