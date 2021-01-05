import json
import unicodedata
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from win32com.shell import shell, shellcon

from ...constants import CONFIG_REGISTRY_KEY
from ...utils import force_encode
from ..extension import ExtensionListener, get_formatted_status
from . import registry

if TYPE_CHECKING:
    from ...manager import Manager  # noqa

log = getLogger(__name__)

OVERLAYS_REGISTRY_KEY = f"{CONFIG_REGISTRY_KEY}\\Overlays"
FILTER_FOLDERS = "FilterFolders"
ENABLE_OVERLAY = "EnableOverlay"


def enable_overlay() -> None:
    registry.write(OVERLAYS_REGISTRY_KEY, {ENABLE_OVERLAY: "1"})


def disable_overlay() -> None:
    registry.write(OVERLAYS_REGISTRY_KEY, {ENABLE_OVERLAY: "0"})


def set_filter_folders(paths: Set[Path], /) -> None:
    filters = json.dumps([str(path) for path in paths])
    registry.write(OVERLAYS_REGISTRY_KEY, {FILTER_FOLDERS: filters})


def refresh_files(paths: List[Path], /) -> None:
    for path in paths:
        update_explorer(path)


def update_explorer(path: Path, /) -> None:
    shell.SHChangeNotify(
        shellcon.SHCNE_UPDATEITEM,
        shellcon.SHCNF_PATH | shellcon.SHCNF_FLUSH,
        force_encode(str(path)),
        None,
    )


class WindowsExtensionListener(ExtensionListener):
    """
    Server listening to the Explorer DLLs.

    Currently accepted commands are:
    - "getFileIconId" with the path of the file whose status
      we want to retrieve as parameter.
    """

    explorer_name = "Explorer"

    def __init__(self, manager: "Manager") -> None:
        super().__init__(manager)
        self.handlers["getFileIconId"] = self.handle_status

    def _parse_payload(self, payload: bytes, /) -> str:
        return payload.replace(b"\0", b"").decode("cp1252")

    def _format_response(self, response: str, /) -> bytes:
        return force_encode(chr(0).join(response) + chr(0))

    def handle_status(self, path: Any, /) -> Optional[Dict[str, str]]:
        if not isinstance(path, str):
            return None
        path = Path(unicodedata.normalize("NFC", path))

        engine = self.get_engine(path)
        if not engine:
            return None

        r_path = path.relative_to(engine.local_folder)
        state = engine.dao.get_state_from_local(r_path)

        if not state:
            return None
        return get_formatted_status(state, path)
