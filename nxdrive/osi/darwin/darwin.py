# coding: utf-8
import json
import os
import stat
import subprocess
import sys
import unicodedata
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import xattr
from Foundation import NSBundle, NSDistributedNotificationCenter
from LaunchServices import (
    CFURLCreateWithString,
    LSSetDefaultHandlerForURLScheme,
    LSSharedFileListCopySnapshot,
    LSSharedFileListCreate,
    LSSharedFileListInsertItemURL,
    LSSharedFileListItemCopyDisplayName,
    LSSharedFileListItemRemove,
    kLSSharedFileListFavoriteItems,
    kLSSharedFileListItemBeforeFirst,
)
from nuxeo.compat import quote
from PyQt5.Qt import pyqtSignal
from PyQt5.QtNetwork import QHostAddress, QTcpServer, QTcpSocket

from .. import AbstractOSIntegration
from ...constants import APP_NAME, BUNDLE_IDENTIFIER
from ...objects import DocPair
from ...options import Options
from ...translator import Translator
from ...utils import force_decode, if_frozen

if TYPE_CHECKING:
    from ...manager import Manager  # noqa

__all__ = ("DarwinIntegration", "FinderSyncServer")

log = getLogger(__name__)


class DarwinIntegration(AbstractOSIntegration):

    NXDRIVE_SCHEME = "nxdrive"
    NDRIVE_AGENT_TEMPLATE = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"'
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
        '<plist version="1.0">'
        "<dict>"
        "<key>Label</key>"
        "<string>org.nuxeo.drive.agentlauncher</string>"
        "<key>RunAtLoad</key>"
        "<true/>"
        "<key>Program</key>"
        "<string>%s</string>"
        "</dict>"
        "</plist>"
    )
    FINDERSYNC_PATH = (
        f"/Applications/{APP_NAME}.app/Contents/PlugIns/NuxeoFinderSync.appex"
    )

    @if_frozen
    def _init(self) -> None:
        log.debug("Telling plugInKit to use the FinderSync")
        subprocess.call(["pluginkit", "-e", "use", "-i", BUNDLE_IDENTIFIER])
        subprocess.call(["pluginkit", "-a", self.FINDERSYNC_PATH])

    @if_frozen
    def _cleanup(self) -> None:
        log.debug("Telling plugInKit to ignore the FinderSync")
        subprocess.call(["pluginkit", "-r", self.FINDERSYNC_PATH])
        subprocess.call(["pluginkit", "-e", "ignore", "-i", BUNDLE_IDENTIFIER])

    def _get_agent_file(self) -> Path:
        return Path(f"~/Library/LaunchAgents/{BUNDLE_IDENTIFIER}.plist").expanduser()

    @if_frozen
    def register_startup(self) -> bool:
        """
        Register the Nuxeo Drive.app as a user Launch Agent.
        http://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html
        """
        agent = self._get_agent_file()
        if agent.is_file():
            return False

        parent = agent.parent
        if not parent.exists():
            log.debug(f"Making launch agent folder {parent!r}")
            parent.mkdir(parents=True)

        exe = os.path.realpath(sys.executable)
        log.debug(f"Registering {exe!r} for startup in {agent!r}")
        with agent.open(mode="w") as f:
            f.write(self.NDRIVE_AGENT_TEMPLATE % exe)
        return True

    @if_frozen
    def unregister_startup(self) -> bool:
        agent = self._get_agent_file()
        if agent.is_file():
            log.debug(f"Unregistering startup agent {agent!r}")
            agent.unlink()
            return True
        return False

    @if_frozen
    def register_protocol_handlers(self) -> None:
        """Register the URL scheme listener using PyObjC"""
        bundle_id = NSBundle.mainBundle().bundleIdentifier()
        if bundle_id == "org.python.python":
            log.debug(
                "Skipping URL scheme registration as this program "
                " was launched from the Python OSX app bundle"
            )
            return
        LSSetDefaultHandlerForURLScheme(self.NXDRIVE_SCHEME, bundle_id)
        log.debug(
            f"Registered bundle {bundle_id!r} for URL scheme {self.NXDRIVE_SCHEME!r}"
        )

    @staticmethod
    def is_partition_supported(folder: Path) -> bool:
        if folder is None:
            return False
        result = False
        to_delete = not folder.exists()
        try:
            if to_delete:
                folder.mkdir()
            if not os.access(folder, os.W_OK):
                folder.chmod(
                    stat.S_IXUSR
                    | stat.S_IRGRP
                    | stat.S_IXGRP
                    | stat.S_IRUSR
                    | stat.S_IWGRP
                    | stat.S_IWUSR
                )
            key, value = "drive-test", b"drive-test"
            xattr.setxattr(folder, key, value)
            if xattr.getxattr(folder, key) == value:
                result = True
            xattr.removexattr(folder, key)
        finally:
            if to_delete:
                with suppress(OSError):
                    folder.rmdir()
        return result

    def _send_notification(self, name: str, content: Dict[str, Any]) -> None:
        """
        Send a notification through the macOS notification center
        to the FinderSync app extension.

        :param name: name of the notification
        :param content: content to send
        """
        nc = NSDistributedNotificationCenter.defaultCenter()
        nc.postNotificationName_object_userInfo_(name, None, content)

    def _set_monitoring(self, operation: str, path: Path) -> None:
        """
        Set the monitoring of a folder by the FinderSync.

        :param operation: 'watch' or 'unwatch'
        :param path: path to the folder
        """
        name = f"{BUNDLE_IDENTIFIER}.watchFolder"
        self._send_notification(name, {"operation": operation, "path": str(path)})

    @if_frozen
    def watch_folder(self, folder: Path) -> None:
        log.debug(f"FinderSync now watching {folder!r}")
        self._set_monitoring("watch", folder)

    @if_frozen
    def unwatch_folder(self, folder: Path) -> None:
        log.debug(f"FinderSync now ignoring {folder!r}")
        self._set_monitoring("unwatch", folder)

    @if_frozen
    def send_sync_status(self, state: DocPair, path: Path) -> None:
        """
        Send the sync status of a file to the FinderSync.

        :param state: current local state of the file
        :param path: full path of the file
        """
        try:
            if not path.exists():
                return

            name = f"{BUNDLE_IDENTIFIER}.syncStatus"
            status = self._formatted_status(state, path)

            log.trace(f"Sending status to FinderSync for {path!r}: {status}")
            self._send_notification(name, {"statuses": [status]})
        except:
            log.exception("Error while trying to send status to FinderSync")

    @if_frozen
    def send_content_sync_status(self, states: List[DocPair], path: Path) -> None:
        """
        Send the sync status of the content of a folder to the FinderSync.

        :param states: current local states of the children of the folder
        :param path: full path of the folder
        """
        try:
            if not path.exists():
                return

            name = f"{BUNDLE_IDENTIFIER}.syncStatus"

            # We send the statuses of the children by batch in case
            # the notification center doesn't allow notifications
            # with a heavy payload.
            # 50 seems like a good balance between payload size
            # and number of notifications.
            batch_size = Options.findersync_batch_size
            for i in range(0, len(states), batch_size):
                states_batch = states[i : i + batch_size]
                statuses = [
                    self._formatted_status(state, path / state.local_name)
                    for state in states_batch
                ]
                log.trace(
                    f"Sending statuses to FinderSync for children of {path!r} "
                    f"(items {i}-{i + len(states_batch) - 1})"
                )
                self._send_notification(name, {"statuses": statuses})
        except:
            log.exception("Error while trying to send status to FinderSync")

    def _formatted_status(self, state: DocPair, path: Path) -> Dict[str, str]:
        status = "unsynced"

        readonly = (path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP)) == 0
        if readonly:
            status = "locked"
        elif state:
            if state.error_count > 0:
                status = "error"
            elif state.pair_state == "conflicted":
                status = "conflicted"
            elif state.local_state == "synchronized":
                status = "synced"
            elif state.pair_state == "unsynchronized":
                status = "unsynced"
            elif state.processor != 0:
                status = "syncing"
        return {"status": status, "path": str(path)}

    @if_frozen
    def register_contextual_menu(self) -> None:
        name = f"{BUNDLE_IDENTIFIER}.setConfig"

        log.trace(f"Sending menu to FinderSync")
        entries = [Translator.get(f"CONTEXT_MENU_{i}") for i in range(1, 4)]
        self._send_notification(name, {"entries": entries})

    def register_folder_link(self, path: Path, name: str = None) -> None:
        favorites = self._get_favorite_list() or []
        if not favorites:
            log.warning("Could not fetch the Finder favorite list.")
            return

        name = os.path.basename(name) if name else APP_NAME

        if self._find_item_in_list(favorites, name):
            return

        url = CFURLCreateWithString(None, f"file://{quote(str(path))}", None)
        if not url:
            log.warning(f"Could not generate valid favorite URL for: {path!r}")
            return

        # Register the folder as favorite if not already there
        item = LSSharedFileListInsertItemURL(
            favorites, kLSSharedFileListItemBeforeFirst, name, None, url, {}, []
        )
        if item:
            log.debug(f"Registered new favorite in Finder for: {path!r}")

    def unregister_folder_link(self, name: str = None) -> None:
        favorites = self._get_favorite_list()
        if not favorites:
            log.warning("Could not fetch the Finder favorite list.")
            return

        name = os.path.basename(name) if name else APP_NAME

        item = self._find_item_in_list(favorites, name)
        if not item:
            return

        LSSharedFileListItemRemove(favorites, item)

    @staticmethod
    def _get_favorite_list() -> List[str]:
        return LSSharedFileListCreate(None, kLSSharedFileListFavoriteItems, None)

    @staticmethod
    def _find_item_in_list(lst: List[str], name: str) -> Optional[str]:
        for item in LSSharedFileListCopySnapshot(lst, None)[0]:
            item_name = LSSharedFileListItemCopyDisplayName(item)
            if name == item_name:
                return item
        return None


class FinderSyncServer(QTcpServer):
    """
    Server listening to the FinderSync extension.

    This TCP server is instantiated during the Manager.__init__(),
    and starts listening once the signal Manager.started() is emitted.

    It handles requests coming from any FinderSync instance.
    These requests are JSON-formatted and follow this pattern:
    {
        "cmd": "<command>",
        "<key>": "<value>",  # parameters
        ...
    }

    Currently accepted commands are:
    - "get-status" with the parameter "path" to specify which
      file's status to retrieve,
    - "trigger-watch" to get all the local folders to watch.
    """

    listening = pyqtSignal()

    def __init__(self, manager: "Manager", *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.manager = manager
        self.host = "localhost"
        self.port = 50675
        self.newConnection.connect(self.handle_connection)

    def handle_connection(self) -> None:
        """ Called when a FinderSync instance is connecting. """
        con: QTcpSocket = self.nextPendingConnection()
        if not con or not con.waitForConnected():
            log.error(f"Unable to open FinderSync server socket: {con.errorString()}")
            return

        if con.waitForReadyRead():
            content = con.readAll()
            log.trace(f"FinderSync request: {content}")
            self._handle_content(force_decode(content.data()))

            con.disconnectFromHost()
            con.waitForDisconnected()
            del con

    def _listen(self) -> None:
        """
        Called once the Manager.started() is emitted.

        Starts listening and emits a signal so that the extension can be started.
        """
        self.listen(QHostAddress(self.host), self.port)
        log.debug(f"Listening to FinderSync on {self.host}:{self.port}")
        self.listening.emit()

    def _handle_content(self, content: str) -> None:
        """
        If the incoming connection successfully transmitted data,
        run the corresponding commands.
        """
        data = json.loads(content)
        cmd = data.get("cmd", None)

        if cmd == "get-status":
            if "path" in data:
                path = Path(unicodedata.normalize("NFC", force_decode(data["path"])))
                self.manager.send_sync_status(path)
        elif cmd == "trigger-watch":
            for engine in self.manager._engine_definitions:
                self.manager.osi.watch_folder(engine.local_folder)
