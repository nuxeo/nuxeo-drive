# coding: utf-8
import os
import re
import stat
import subprocess
import sys
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
import xattr
from CoreServices import (
    CFURLCreateWithString,
    LSSetDefaultHandlerForURLScheme,
    LSSharedFileListCopySnapshot,
    LSSharedFileListCreate,
    LSSharedFileListInsertItemURL,
    LSSharedFileListItemCopyDisplayName,
    LSSharedFileListItemRemove,
    NSBundle,
    NSDistributedNotificationCenter,
    NSUserDefaults,
    kLSSharedFileListFavoriteItems,
    kLSSharedFileListItemBeforeFirst,
)
from nuxeo.compat import quote

from ...constants import BUNDLE_IDENTIFIER, NXDRIVE_SCHEME
from ...objects import DocPair
from ...options import Options
from ...translator import Translator
from ...utils import if_frozen
from .. import AbstractOSIntegration
from ..extension import get_formatted_status
from .extension import DarwinExtensionListener

__all__ = ("DarwinIntegration",)

log = getLogger(__name__)


def _get_app() -> str:
    """Return the path to the application, when bundled."""
    exe_path = sys.executable
    m = re.match(r"(.*\.app).*", exe_path)
    return m.group(1) if m else exe_path


class DarwinIntegration(AbstractOSIntegration):

    nature = "macOS"

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
    FINDERSYNC_ID = f"{BUNDLE_IDENTIFIER}.NuxeoFinderSync"
    FINDERSYNC_PATH = f"{_get_app()}/Contents/PlugIns/NuxeoFinderSync.appex/"

    @if_frozen
    def init(self) -> None:
        log.info("Telling plugInKit to use the FinderSync")
        try:
            subprocess.run(
                ["pluginkit", "-e", "use", "-i", self.FINDERSYNC_ID], check=True
            )
            subprocess.run(["pluginkit", "-a", self.FINDERSYNC_PATH], check=True)
            for p in psutil.process_iter(attrs=["name", "pid"]):
                if p.info["name"] == "NuxeoFinderSync":
                    log.info(f"FinderSync is running with pid {p.info['pid']}")
        except subprocess.CalledProcessError:
            log.exception("Error while starting FinderSync")

    @if_frozen
    def cleanup(self) -> None:
        log.info("Telling plugInKit to ignore the FinderSync")
        try:
            subprocess.run(
                ["pluginkit", "-e", "ignore", "-i", self.FINDERSYNC_ID], check=True
            )
        except subprocess.CalledProcessError:
            log.exception("Error while stopping FinderSync")

    def _get_agent_file(self) -> Path:
        return Path(f"~/Library/LaunchAgents/{BUNDLE_IDENTIFIER}.plist").expanduser()

    @staticmethod
    def cb_get() -> str:
        """Get the text data from the clipboard.
        Emulate: pbpaste r
        """
        data = subprocess.check_output(["pbpaste", "r"])
        return data.decode("utf-8")

    @staticmethod
    def cb_set(text: str) -> None:
        """Copy some *text* into the clipboard.
        Emulate: echo "blablabla" | pbcopy w
        """
        with subprocess.Popen(["pbcopy", "w"], stdin=subprocess.PIPE) as p:
            # See https://github.com/python/typeshed/pull/3652#issuecomment-598122198
            # if this "if" is still needed
            if p.stdin:
                p.stdin.write(text.encode("utf-8"))
                p.stdin.close()
                p.wait()

    @staticmethod
    def current_them() -> str:
        """Get the current OS them."""
        try:
            theme: str = NSUserDefaults.standardUserDefaults().stringForKey_(
                "AppleInterfaceStyle"
            )
            return theme.lower()
        except Exception:
            return ""

    def dark_mode_in_use(self) -> bool:
        """Does the user has the Dark mode set?"""
        return self.current_them() == "dark"

    def open_local_file(self, file_path: str, select: bool = False) -> None:
        """Note that this function must _not_ block the execution."""
        args = ["open"]
        if select:
            args += ["-R"]
        args += [file_path]
        subprocess.Popen(args)

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
            log.info(f"Making launch agent folder {parent!r}")
            parent.mkdir(parents=True)

        exe = os.path.realpath(sys.executable)
        log.info(f"Registering {exe!r} for startup in {agent!r}")
        agent.write_text(self.NDRIVE_AGENT_TEMPLATE % exe, encoding="utf-8")
        return True

    @if_frozen
    def unregister_startup(self) -> bool:
        agent = self._get_agent_file()
        if agent.is_file():
            log.info(f"Unregistering startup agent {agent!r}")
            agent.unlink()
            return True
        return False

    @if_frozen
    def register_protocol_handlers(self) -> None:
        """Register the URL scheme listener using PyObjC"""
        bundle_id = NSBundle.mainBundle().bundleIdentifier()
        if bundle_id == "org.python.python":
            log.info(
                "Skipping URL scheme registration as this program "
                " was launched from the Python OSX app bundle"
            )
            return
        LSSetDefaultHandlerForURLScheme(NXDRIVE_SCHEME, bundle_id)
        log.info(f"Registered bundle {bundle_id!r} for URL scheme {NXDRIVE_SCHEME!r}")

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
        log.info(f"FinderSync now watching {folder!r}")
        self._set_monitoring("watch", folder)

    @if_frozen
    def unwatch_folder(self, folder: Path) -> None:
        log.info(f"FinderSync now ignoring {folder!r}")
        self._set_monitoring("unwatch", folder)

    @if_frozen
    def send_sync_status(self, state: DocPair, path: Path) -> None:
        """
        Send the sync status of a file to the FinderSync.

        :param state: current local state of the file
        :param path: full path of the file
        """
        name = f"{BUNDLE_IDENTIFIER}.syncStatus"
        try:
            status = get_formatted_status(state, path)
            if status:
                log.debug(f"Sending status to FinderSync for {path!r}: {status}")
                self._send_notification(name, {"statuses": [status]})
        except Exception:
            log.exception("Error while trying to send status to FinderSync")

    @if_frozen
    def send_content_sync_status(self, states: List[DocPair], path: Path) -> None:
        """
        Send the sync status of the content of a folder to the FinderSync.

        :param states: current local states of the children of the folder
        :param path: full path of the folder
        """
        name = f"{BUNDLE_IDENTIFIER}.syncStatus"
        try:
            # We send the statuses of the children by batch in case
            # the notification center doesn't allow notifications
            # with a heavy payload.
            # 50 seems like a good balance between payload size
            # and number of notifications.
            batch_size = Options.findersync_batch_size
            for i in range(0, len(states), batch_size):
                states_batch = states[i : i + batch_size]
                statuses = []
                for state in states_batch:
                    status = get_formatted_status(state, path / state.local_name)
                    if status:
                        statuses.append(status)
                log.debug(
                    f"Sending statuses to FinderSync for children of {path!r} "
                    f"(items {i}-{i + len(states_batch) - 1})"
                )
                log.debug(statuses)
                self._send_notification(name, {"statuses": statuses})
        except FileNotFoundError:
            pass
        except Exception:
            log.exception("Error while trying to send status to FinderSync")

    @if_frozen
    def register_contextual_menu(self) -> None:
        name = f"{BUNDLE_IDENTIFIER}.setConfig"

        log.debug("Sending menu to FinderSync")
        entries = [Translator.get(f"CONTEXT_MENU_{i}") for i in range(1, 5)]
        self._send_notification(name, {"entries": entries})

    @if_frozen
    def register_folder_link(self, path: Path) -> None:
        favorites = self._get_favorite_list() or []
        if not favorites:
            log.warning("Could not fetch the Finder favorite list.")
            return

        if self._find_item_in_list(favorites, path.name):
            return

        url = CFURLCreateWithString(None, f"file://{quote(str(path))}", None)
        if not url:
            log.warning(f"Could not generate valid favorite URL for: {path!r}")
            return

        # Register the folder as favorite if not already there
        item = LSSharedFileListInsertItemURL(
            favorites, kLSSharedFileListItemBeforeFirst, path.name, None, url, {}, []
        )
        if item:
            log.info(f"Registered new favorite in Finder for: {path!r}")

    @if_frozen
    def unregister_folder_link(self, path: Path) -> None:
        favorites = self._get_favorite_list()
        if not favorites:
            log.warning("Could not fetch the Finder favorite list.")
            return

        item = self._find_item_in_list(favorites, path.name)
        if not item:
            return

        LSSharedFileListItemRemove(favorites, item)

    @staticmethod
    def _get_favorite_list() -> List[str]:
        favorites: List[str] = LSSharedFileListCreate(
            None, kLSSharedFileListFavoriteItems, None
        )
        return favorites

    @staticmethod
    def _find_item_in_list(lst: List[str], name: str) -> Optional[str]:
        for item in LSSharedFileListCopySnapshot(lst, None)[0]:
            item_name = LSSharedFileListItemCopyDisplayName(item)
            if name == item_name:
                return str(item)
        return None

    def get_extension_listener(self) -> DarwinExtensionListener:
        return DarwinExtensionListener(self._manager)
