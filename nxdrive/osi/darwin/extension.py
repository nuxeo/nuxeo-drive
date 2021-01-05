import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..extension import ExtensionListener

if TYPE_CHECKING:
    from ...manager import Manager  # noqa


class DarwinExtensionListener(ExtensionListener):
    """
    Server listening to the FinderSync extension.

    Currently accepted commands are:
    - "get-status" with the path of the file whose status
      we want to retrieve as parameter.
    - "trigger-watch" to get all the local folders to watch.
    """

    explorer_name = "Finder"

    def __init__(self, manager: "Manager") -> None:
        super().__init__(manager)
        self.handlers["get-status"] = self.handle_status
        self.handlers["trigger-watch"] = self.handle_trigger_watch

    def handle_status(self, path: Any, /) -> None:
        if not isinstance(path, str):
            return None
        path = Path(unicodedata.normalize("NFC", path))
        self.manager.send_sync_status(path)

    def handle_trigger_watch(self, *args: Any) -> None:
        for engine in self.manager.engines.copy().values():
            self.manager.osi.watch_folder(engine.local_folder)
