# coding: utf-8
import subprocess
from logging import getLogger

from .. import AbstractOSIntegration

__all__ = ("LinuxIntegration",)

log = getLogger(__name__)


class LinuxIntegration(AbstractOSIntegration):

    nature = "GNU/Linux"

    def open_local_file(self, file_path: str, select: bool = False) -> None:
        """Note that this function must _not_ block the execution."""
        if select:
            log.info(
                "The Select/Highlight feature is not yet implemented, please vote "
                "https://jira.nuxeo.com/browse/NXDRIVE-848 to show your interest"
            )

        # xdg-open should be supported by recent Gnome, KDE, Xfce
        subprocess.Popen(["xdg-open", file_path])
