import filecmp
import os
import shutil
import subprocess
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

from ...constants import APP_NAME, NXDRIVE_SCHEME
from ...objects import DocPair
from ...utils import find_icon, if_frozen
from .. import AbstractOSIntegration
from ..extension import Status, get_formatted_status, icon_status

__all__ = ("LinuxIntegration",)

log = getLogger(__name__)

if TYPE_CHECKING:
    from ...manager import Manager  # noqa


class LinuxIntegration(AbstractOSIntegration):

    nature = "GNU/Linux"

    def __init__(self, manager: Optional["Manager"], /):
        super().__init__(manager)
        self._icons_to_emblems()

    @staticmethod
    def cb_get() -> str:
        """Get the text data from the clipboard. The xclip tool needs to be installed.
        Emulate: xclip -selection c -o
        """
        data = subprocess.check_output(["xclip", "-selection", "c", "-o"])
        return data.decode("utf-8")

    @staticmethod
    def cb_set(text: str, /) -> None:
        """Copy some *text* into the clipboard. The xclip tool needs to be installed.
        Emulate: echo "blablabla" | xclip -selection c
        """
        with subprocess.Popen(["xclip", "-selection", "c"], stdin=subprocess.PIPE) as p:
            # See https://github.com/python/typeshed/pull/3652#issuecomment-598122198
            # if this "if" is still needed
            if p.stdin:
                p.stdin.write(text.encode("utf-8"))
                p.stdin.close()
                p.wait()

    def open_local_file(self, file_path: str, /, *, select: bool = False) -> None:
        """Note that this function must _not_ block the execution."""
        if select:
            log.info(
                "The Select/Highlight feature is not yet implemented, please vote "
                "https://jira.nuxeo.com/browse/NXDRIVE-848 to show your interest"
            )

        # xdg-open should be supported by recent Gnome, KDE, Xfce
        subprocess.Popen(["xdg-open", file_path])

    @if_frozen
    def register_protocol_handlers(self) -> None:
        """Register the URL scheme listener using XDG.
        This works for OSes that are XDG compliant, so most of distribution flavors.

        Note that we recreate the .desktop file each time the application starts
        to handle new versions (as the executable filename may change between
        2 versions).
        """

        original_executable = os.getenv("APPIMAGE", "")  # Set by AppImage
        if not original_executable:
            log.info(
                "Impossible to guess the original file location, "
                "skipping custom protocol URL handler installation."
            )
            return

        desktop_file = Path(
            f"~/.local/share/applications/{NXDRIVE_SCHEME}.desktop"
        ).expanduser()
        desktop_content = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
NoDisplay=true
StartupNotify=false
Terminal=false
Exec="{original_executable}" %u
MimeType=x-scheme-handler/{NXDRIVE_SCHEME};
"""

        try:
            # Create the folder if it does not exist
            desktop_file.parent.mkdir(parents=True, exist_ok=True)

            # Create the .desktop file
            with open(desktop_file, "w") as f:
                f.write(desktop_content)

            # Register the application with the MIME type
            subprocess.check_call(
                [
                    "xdg-mime",
                    "default",
                    f"{NXDRIVE_SCHEME}.desktop",
                    f"x-scheme-handler/{NXDRIVE_SCHEME}",
                ]
            )
        except Exception:
            log.warning("Error while registering the URL scheme", exc_info=True)
        else:
            log.info(
                f"Registered {original_executable!r} for URL scheme {NXDRIVE_SCHEME!r}"
            )

    @if_frozen
    def send_sync_status(self, doc_pair: DocPair, path: Path, /) -> None:
        """
        Set the sync status of a file.

        :param state: current local state of the file
        :param path: full path of the file
        """
        try:
            status = get_formatted_status(doc_pair, path)
            if status:
                log.debug(f"Setting status to {path!r}: {status}")
                self._set_icon(status)
        except Exception:
            log.exception("Error while setting the status to {path!r}", exc_info=True)

    def _set_icon(self, status: Dict[str, str], /) -> None:
        """Call gio command to set folder emblem metadata."""
        value = Status(int(status["value"]))
        path = status["path"]
        emblem = icon_status[value]
        cmd = [
            "gio",
            "set",
            "-t",
            "stringv",
            str(path),
            "metadata::emblems",
            emblem,
        ]
        try:
            subprocess.check_call(cmd)
        except Exception:
            log.warning(f"Could not set the {emblem} emblem on {path!r}", exc_info=True)

    def _icons_to_emblems(self) -> None:
        """
        Copy nuxeo overlay icons to linux local icons folder.
        Previous local icons will be replaced.
        """
        shared_icons = Path.home() / ".local/share/icons"
        shared_icons.mkdir(parents=True, exist_ok=True)

        statuses = ["synced", "syncing", "conflicted", "error", "locked", "unsynced"]
        icons = find_icon("overlay/linux")

        for status in statuses:
            icon = icons / f"badge_{status}.svg"
            emblem = shared_icons / f"emblem-nuxeo_{status}.svg"

            try:
                identical = filecmp.cmp(icon, emblem, shallow=False)
            except OSError:
                # Most likely the *icon* doest not exist yet
                pass
            else:
                if identical:
                    continue

            try:
                shutil.copy(icon, emblem)
            except shutil.Error:
                log.warning(
                    f"Could not copy {icon!r} to {shared_icons!r}", exc_info=True
                )
