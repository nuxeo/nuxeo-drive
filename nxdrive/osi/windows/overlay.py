# coding: utf-8
import json
import os
import stat
import unicodedata
from ctypes import windll
from logging import getLogger
from typing import Any, Dict, List, TYPE_CHECKING

from PyQt5.QtNetwork import QHostAddress, QTcpServer, QTcpSocket

from . import registry
from ...objects import DocPair
from ...utils import force_decode, force_encode

if TYPE_CHECKING:
    from ...manager import Manager  # noqa

log = getLogger(__name__)

WINDOWS_UTIL_DLL_PATH = (
    "C:\\development\\liferay-nativity\\windows\\LiferayNativityShellExtensions"
    "\\Release\\x64\\LiferayNativityUtil_x64.dll"
)
NATIVITY_REGISTRY_KEY = "SOFTWARE\\Liferay Inc\\Liferay Nativity"
FILTER_FOLDERS_REGISTRY_NAME = "FilterFolders"


class NativityControl:
    def __init__(self, manager: "Manager") -> None:
        self.manager = manager
        self._loaded = False
        self._connected = False
        self._listener = None
        self._win_dll = None

    def load(self) -> bool:
        if not self._loaded:
            try:
                self._win_dll = windll.LoadLibrary(WINDOWS_UTIL_DLL_PATH)
            except OSError:
                log.exception("Unable to load DLL.")
            else:
                self._loaded = bool(self._win_dll)
        return self._loaded

    def connect(self) -> bool:
        if self._connected:
            return True

        if not self.load():
            return False
        log.info("Loaded DLL.")

        if not self._listener:
            self._listener = OverlayHandlerListener(
                self.manager, host="localhost", port=33001
            )

        if not self._listener.isListening():
            self._listener._listen()

        return True

    def disconnect(self):
        if not self._connected:
            return True

        self._listener.close()
        self._connected = False

        return True

    def set_filter_folder(self, path: str) -> None:
        self.set_filter_folders([path])

    def set_filter_folders(self, paths: List[str]) -> None:
        registry.write(
            NATIVITY_REGISTRY_KEY, {FILTER_FOLDERS_REGISTRY_NAME: json.dumps(paths)}
        )

        for path in paths:
            self.refresh_explorer(path)

    def refresh_files(self, paths: List[str]) -> None:
        if not paths or not self._loaded:
            return

        for path in paths:
            self.update_explorer(path)

    # Native function bridges
    def refresh_explorer(self, path: str) -> None:
        if self._loaded:
            self._win_dll.RefreshExplorer(path)

    def update_explorer(self, path: str) -> None:
        if self._loaded:
            self._win_dll.UpdateExplorer(path)

    def set_system_folder(self, path: str) -> None:
        if self._loaded:
            self._win_dll.SetSystemFolder(path)


class OverlayHandlerListener(QTcpServer):
    def __init__(
        self,
        manager: "Manager",
        *args: Any,
        host: str = None,
        port: int = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.host = host
        self.port = port
        self.manager = manager
        self.newConnection.connect(self.handle_connection)

    def _listen(self):
        self.listen(QHostAddress(self.host), self.port)
        log.debug(f"Listening to Explorer on {self.host}:{self.port}")

    def handle_connection(self) -> None:
        """ Called when an Explorer instance is connecting. """
        con: QTcpSocket = self.nextPendingConnection()
        print("getting connection")
        if not con or not con.waitForConnected():
            log.error(
                f"Unable to open OverlayHandler server socket: {con.errorString()}"
            )
            return

        if con.waitForReadyRead():
            payload = con.readAll()
            print(payload)
            content = force_decode(payload.data()).replace(chr(0), "")
            log.trace(f"OverlayHandler request: {content}")

            response = self._handle_content(content)
            if response:
                log.trace(response)
                con.write(force_encode(chr(0).join(response) + chr(0)))
                con.waitForBytesWritten()

            con.disconnectFromHost()
            con.waitForDisconnected()
            del con

    def _handle_content(self, content: str) -> str:
        content = json.loads(content)
        if content.get("command", "") == "getFileIconId":
            state = None
            path = content.get("value")
            if not path:
                return ""
            path = unicodedata.normalize("NFC", force_decode(path))

            for engine in self.manager._engines.values():
                # Only send status if we picked the right
                # engine and if we're not targeting the root
                if path == engine.local_folder:
                    r_path = "/"
                elif path.startswith(engine.local_folder_bs):
                    r_path = path.replace(engine.local_folder, "").replace("\\", "/")
                else:
                    continue

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
