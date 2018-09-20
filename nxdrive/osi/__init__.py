# coding: utf-8
from logging import getLogger
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..constants import MAC, WINDOWS
from ..objects import DocPair

if TYPE_CHECKING:
    from .manager import Manager  # noqa

log = getLogger(__name__)


class AbstractOSIntegration:

    __zoom_factor = 1.0

    def __init__(self, manager: "Manager") -> None:
        self._manager = manager

    @property
    def zoom_factor(self) -> float:
        return self.__zoom_factor

    def register_startup(self) -> bool:
        return False

    def unregister_startup(self) -> bool:
        return False

    @staticmethod
    def is_partition_supported(folder: str) -> bool:
        return True

    def uninstall(self) -> None:
        """
        Actions to perform before uninstalling Drive.
        One action might do nothing depending on its OS-specific
        implementation.
        """
        self.unregister_startup()
        self.unregister_folder_link(None)

    def register_protocol_handlers(self) -> None:
        pass

    def unregister_protocol_handlers(self) -> None:
        pass

    def watch_folder(self, folder: str) -> None:
        pass

    def unwatch_folder(self, folder: str) -> None:
        pass

    def send_sync_status(self, state: Optional[DocPair], path: str) -> None:
        pass

    def register_folder_link(self, folder_path: str, name: str = None) -> None:
        pass

    def unregister_folder_link(self, name: str = None) -> None:
        pass

    def get_system_configuration(self) -> Dict[str, Any]:
        return dict()

    def _init(self) -> None:
        pass

    def _cleanup(self) -> None:
        pass

    @staticmethod
    def get(manager: object) -> "AbstractOSIntegration":

        integration, nature = AbstractOSIntegration, "None"

        if MAC:
            from .darwin.darwin import DarwinIntegration

            integration, nature = DarwinIntegration, "macOS"
        elif WINDOWS:
            from .windows.windows import WindowsIntegration

            integration, nature = WindowsIntegration, "Windows"

        log.debug(f"OS integration type: {nature}")
        return integration(manager)
