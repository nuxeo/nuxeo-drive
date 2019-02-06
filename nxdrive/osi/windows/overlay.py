# coding: utf-8
import json
import os
import stat
import unicodedata
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Set, TYPE_CHECKING

from PyQt5.Qt import pyqtSignal
from PyQt5.QtNetwork import QHostAddress, QTcpServer, QTcpSocket

from win32com.shell import shell, shellcon

from . import registry
from ...constants import CONFIG_REGISTRY_KEY
from ...objects import DocPair
from ...utils import force_decode, force_encode

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


def get_filter_folders() -> Set[Path]:
    value = registry.read(OVERLAYS_REGISTRY_KEY)
    if not value:
        return set()
    overlay_conf = json.loads(value)
    if not isinstance(overlay_conf, list):
        return set()
    filters = overlay_conf.get(FILTER_FOLDERS, [])
    return {Path(path) for path in filters}


def set_filter_folders(paths: Set[Path]) -> None:
    filters = json.dumps([str(path) for path in paths])
    registry.write(OVERLAYS_REGISTRY_KEY, {FILTER_FOLDERS: filters})


def refresh_files(paths: List[Path]) -> None:
    for path in paths:
        update_explorer(path)


def update_explorer(path: Path) -> None:
    shell.SHChangeNotify(
        shellcon.SHCNE_UPDATEITEM,
        shellcon.SHCNF_PATH | shellcon.SHCNF_FLUSH,
        force_encode(str(path)),
        None,
    )


class OverlayHandlerListener(QTcpServer):

    listening = pyqtSignal()

    def __init__(self, manager: "Manager", *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.manager = manager
        self.host = "localhost"
        self.port = 10650
        self.newConnection.connect(self.handle_connection)

    def _listen(self):
        self.listen(QHostAddress(self.host), self.port)
        log.debug(f"Listening to Explorer on {self.host}:{self.port}")
        self.listening.emit()

    def handle_connection(self) -> None:
        """ Called when an Explorer instance is connecting. """
        con: QTcpSocket = self.nextPendingConnection()

        if not con or not con.waitForConnected():
            log.error(
                f"Unable to open OverlayHandler server socket: {con.errorString()}"
            )
            return

        if con.waitForReadyRead():
            payload = con.readLine()

            try:
                content = payload.data().replace(b"\0", b"").decode("cp1252")
            except:
                log.debug(f"Unable to decode payload: {payload}")
            else:
                response = self._handle_content(content)
                if response:
                    con.write(force_encode(chr(0).join(response) + chr(0)))

        con.disconnectFromHost()
        del con

    def _handle_content(self, content: str) -> str:
        content = json.loads(content)
        if content.get("command", "") == "getFileIconId":
            state = None
            path = content.get("value")
            if not path:
                return ""
            path = Path(unicodedata.normalize("NFC", force_decode(path)))

            for engine in self.manager._engines.values():
                # Only send status if we picked the right
                # engine and if we're not targeting the root
                if engine.local_folder not in path.parents:
                    return ""

                r_path = path.relative_to(engine.local_folder)
                dao = engine._dao
                state = dao.get_state_from_local(r_path)
                break

            if not state:
                return ""
            return json.dumps(self._formatted_status(state, path))

    def _formatted_status(self, state: DocPair, path: str) -> Dict[str, str]:
        """
        Synced: 1
        Syncing: 2
        Conflicted: 3
        Error: 4
        Locked: 5
        Unsynced: 6
        """
        status = "6"

        readonly = (os.stat(path).st_mode & (stat.S_IWUSR | stat.S_IWGRP)) == 0
        if readonly:
            status = "5"
        elif state:
            if state.error_count > 0:
                status = "4"
            elif state.pair_state == "conflicted":
                status = "3"
            elif state.local_state == "synchronized":
                status = "1"
            elif state.pair_state == "unsynchronized":
                status = "6"
            elif state.processor != 0:
                status = "2"
        return {"value": status}
