# coding: utf-8
import subprocess
from logging import getLogger

from .. import AbstractOSIntegration
from ...utils import force_decode

__all__ = ("LinuxIntegration",)

log = getLogger(__name__)


class LinuxIntegration(AbstractOSIntegration):

    nature = "GNU/Linux"

    @staticmethod
    def cb_get() -> str:
        """Get the text data from the clipboard. The xclip tool needs to be installed."""
        data = subprocess.check_output("xclip -selection clipboard -o".split())
        # data = '"blablabla"\n' -> remove useless characters
        data = data.rstrip()[1:-1]
        return force_decode(data)

    @staticmethod
    def cb_set(text: str) -> None:
        """Copy some *text* into the clipboard. The xclip tool needs to be installed."""
        with subprocess.Popen(["echo", f'"{text}"'], stdout=subprocess.PIPE) as ps:
            subprocess.check_call(["xclip", "-selection", "c"], stdin=ps.stdout)
            ps.wait()

    def open_local_file(self, file_path: str, select: bool = False) -> None:
        """Note that this function must _not_ block the execution."""
        if select:
            log.info(
                "The Select/Highlight feature is not yet implemented, please vote "
                "https://jira.nuxeo.com/browse/NXDRIVE-848 to show your interest"
            )

        # xdg-open should be supported by recent Gnome, KDE, Xfce
        subprocess.Popen(["xdg-open", file_path])
