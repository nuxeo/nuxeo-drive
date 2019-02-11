# coding: utf-8
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..constants import APP_NAME, LINUX, MAC, WINDOWS
from ..objects import DocPair

if TYPE_CHECKING:
    from ..manager import Manager  # noqa

log = getLogger(__name__)


class AbstractOSIntegration:

    __zoom_factor = 1.0
    nature = "Unknown"

    def __init__(self, manager: Optional["Manager"]) -> None:
        self._manager = manager

    @property
    def zoom_factor(self) -> float:
        return self.__zoom_factor

    def open_local_file(self, file_path: str, select: bool = False) -> None:
        """
        Launch the local OS program on the given file / folder.

        :param file_path: The file URL to open.
        :param select: Hightlight the given file_path. Useful when
                       opening a folder and to select a file.
        """
        pass

    def register_startup(self) -> bool:
        return False

    def unregister_startup(self) -> bool:
        return False

    @staticmethod
    def is_partition_supported(folder: Path) -> bool:
        return True

    def uninstall(self) -> None:
        """
        Actions to perform before uninstalling Drive.
        One action might do nothing depending on its OS-specific
        implementation.
        """
        self.unregister_startup()
        self.unregister_folder_link(Path(APP_NAME))
        self.unregister_contextual_menu()

    def register_protocol_handlers(self) -> None:
        pass

    def watch_folder(self, folder: Path) -> None:
        pass

    def unwatch_folder(self, folder: Path) -> None:
        pass

    def send_sync_status(self, state: DocPair, path: Path) -> None:
        pass

    def send_content_sync_status(self, states: List[DocPair], path: Path) -> None:
        pass

    def register_contextual_menu(self) -> None:
        pass

    def unregister_contextual_menu(self) -> None:
        pass

    def register_folder_link(self, path: Path) -> None:
        pass

    def unregister_folder_link(self, path: Path) -> None:
        pass

    def get_system_configuration(self) -> Dict[str, Any]:
        return dict()

    def _init(self) -> None:
        pass

    def _cleanup(self) -> None:
        pass

    @staticmethod
    def get(manager: Optional["Manager"]) -> "AbstractOSIntegration":
        if LINUX:
            from .linux.linux import LinuxIntegration

            return LinuxIntegration(manager)
        elif MAC:
            from .darwin.darwin import DarwinIntegration

            return DarwinIntegration(manager)
        elif WINDOWS:
            from .windows.windows import WindowsIntegration

            return WindowsIntegration(manager)

        import sys

        raise RuntimeError(f"OS not supported: {sys.platform!r}")
