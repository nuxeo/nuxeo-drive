from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..constants import APP_NAME, LINUX, MAC, WINDOWS
from ..objects import DocPair
from ..qt.imports import QObject, pyqtSlot
from .extension import ExtensionListener

if TYPE_CHECKING:
    from ..manager import Manager  # noqa

log = getLogger(__name__)


class AbstractOSIntegration(QObject):

    nature = "Unknown"

    def __init__(self, manager: Optional["Manager"], /) -> None:
        super().__init__()
        self._manager = manager

    def open_local_file(self, file_path: str, /, *, select: bool = False) -> None:
        """
        Launch the local OS program on the given file / folder.

        Note that this function must _not_ block the execution.

        :param file_path: The file URL to open.
        :param select: Highlight the given file_path. Useful when
                       opening a folder and to select a file.
        """
        pass

    def startup_enabled(self) -> bool:
        """Return True if the application is registered to boot at machine startup."""
        return False

    def register_startup(self) -> None:
        pass

    def unregister_startup(self) -> None:
        pass

    @pyqtSlot(result=bool)
    def addons_installed(self) -> bool:
        return False

    @pyqtSlot(result=bool)
    def install_addons(self) -> bool:
        return False

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

    def watch_folder(self, folder: Path, /) -> None:
        pass

    def unwatch_folder(self, folder: Path, /) -> None:
        pass

    def send_sync_status(self, state: DocPair, path: Path, /) -> None:
        pass

    def send_content_sync_status(self, states: List[DocPair], path: Path, /) -> None:
        pass

    def get_extension_listener(self) -> Optional[ExtensionListener]:
        return None

    def register_contextual_menu(self) -> None:
        pass

    def unregister_contextual_menu(self) -> None:
        pass

    def register_folder_link(self, path: Path, /) -> None:
        pass

    def unregister_folder_link(self, path: Path, /) -> None:
        pass

    def get_system_configuration(self) -> Dict[str, Any]:
        return {}

    @staticmethod
    def cb_get() -> str:
        """Get the text data from the clipboard."""
        return ""

    @staticmethod
    def cb_set(text: str, /) -> None:
        """Copy some *text* into the clipboard."""
        pass

    def init(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    @staticmethod
    def get(manager: Optional["Manager"], /) -> "AbstractOSIntegration":
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
