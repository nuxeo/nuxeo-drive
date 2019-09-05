# coding: utf-8
import os
import subprocess
from logging import getLogger
from pathlib import Path

from .. import AbstractOSIntegration
from ...constants import APP_NAME, NXDRIVE_SCHEME
from ...utils import if_frozen

__all__ = ("LinuxIntegration",)

log = getLogger(__name__)


class LinuxIntegration(AbstractOSIntegration):

    nature = "GNU/Linux"

    @staticmethod
    def cb_get() -> str:
        """Get the text data from the clipboard. The xclip tool needs to be installed.
        Emulate: xclip -selection c -o
        """
        data = subprocess.check_output(["xclip", "-selection", "c", "-o"])
        return data.decode("utf-8")

    @staticmethod
    def cb_set(text: str) -> None:
        """Copy some *text* into the clipboard. The xclip tool needs to be installed.
        Emulate: echo "blablabla" | xclip -selection c
        """
        with subprocess.Popen(["xclip", "-selection", "c"], stdin=subprocess.PIPE) as p:
            p.stdin.write(text.encode("utf-8"))
            p.stdin.close()
            p.wait()

    def open_local_file(self, file_path: str, select: bool = False) -> None:
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
