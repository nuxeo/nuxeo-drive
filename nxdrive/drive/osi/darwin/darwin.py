import os
import re
import subprocess
import sys
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from CoreServices import (
    CFURLCreateWithString,
    LSSetDefaultHandlerForURLScheme,
    LSSharedFileListCopySnapshot,
    LSSharedFileListCreate,
    LSSharedFileListInsertItemURL,
    LSSharedFileListItemCopyDisplayName,
    LSSharedFileListItemRef,
    LSSharedFileListItemRemove,
    NSBundle,
    NSDistributedNotificationCenter,
    NSUserDefaults,
    kLSSharedFileListFavoriteItems,
    kLSSharedFileListItemBeforeFirst,
)

from ...constants import BUNDLE_IDENTIFIER, NXDRIVE_SCHEME
from ...objects import DocPair
from ...options import Options
from ...translator import Translator
from ...utils import if_frozen
from .. import AbstractOSIntegration
from ..extension import get_formatted_status
from .darwin_config import get_agent_template, get_findersync_ids
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

    # Used to know when the FinderSync extension is loaded
    # to prevent errors when it failed to start or when
    # trying to stop it twice from the auto-updater.
    _finder_sync_loaded = False

    @property
    def NDRIVE_AGENT_TEMPLATE(self) -> str:
        """Get the launch agent plist template for the current server type."""
        return get_agent_template()

    @property
    def FINDERSYNC_ID(self) -> str:
        """Get the FinderSync bundle ID for the current server type."""
        suffix, _ = get_findersync_ids()
        return f"{BUNDLE_IDENTIFIER}.{suffix}"

    @property
    def FINDERSYNC_PATH(self) -> str:
        """Get the FinderSync app extension path for the current server type."""
        _, appex_name = get_findersync_ids()
        return f"{_get_app()}/Contents/PlugIns/{appex_name}/"

    @if_frozen
    def init(self) -> None:
        if self._finder_sync_loaded:
            return

        log.info("Telling plugInKit to use the FinderSync")
        cmd_use_plugin = ["pluginkit", "-e", "use", "-i", self.FINDERSYNC_ID]
        cmd_add_plugin_location = ["pluginkit", "-a", self.FINDERSYNC_PATH]
        try:
            subprocess.check_call(cmd_use_plugin)
            subprocess.check_call(cmd_add_plugin_location)
            self._finder_sync_loaded = True
        except subprocess.CalledProcessError:
            log.exception("Error while starting FinderSync")

    @if_frozen
    def cleanup(self) -> None:
        if not self._finder_sync_loaded:
            return

        log.info("Telling plugInKit to ignore the FinderSync")
        cmd_ignore_plugin = ["pluginkit", "-e", "ignore", "-i", self.FINDERSYNC_ID]
        try:
            subprocess.check_call(cmd_ignore_plugin)
            self._finder_sync_loaded = False
        except subprocess.CalledProcessError:
            log.warning("Error while stopping FinderSync", exc_info=True)

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
    def cb_set(text: str, /) -> None:
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
    def startup_enabled(self) -> bool:
        agent = self._get_agent_file()
        return agent.is_file()

    @if_frozen
    def register_startup(self) -> None:
        """
        Register the Nuxeo Drive.app as a user Launch Agent.
        http://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html
        """
        if self.startup_enabled():
            return

        agent = self._get_agent_file()
        parent = agent.parent
        if not parent.exists():
            log.info(f"Making launch agent folder {parent!r}")
            parent.mkdir(parents=True)

        exe = os.path.realpath(sys.executable)
        log.info(f"Registering {exe!r} for startup in {agent!r}")
        agent.write_text(self.NDRIVE_AGENT_TEMPLATE % exe, encoding="utf-8")

    @if_frozen
    def unregister_startup(self) -> None:
        if not self.startup_enabled():
            return

        agent = self._get_agent_file()
        log.info(f"Unregistering startup agent {agent!r}")
        agent.unlink()

    @if_frozen
    def _prune_competing_url_handlers(self) -> None:
        """
        Detach leftover Nuxeo Drive install DMGs and prune their stale
        LaunchServices registrations.

        macOS routes ``nxdrive://`` URLs via LaunchServices. If two
        bundles claim ``org.nuxeo.drive`` at the same time (typically
        ``/Applications/Nuxeo Drive.app`` AND ``/Volumes/Nuxeo Drive/
        Nuxeo Drive.app`` because the user forgot to eject the install
        DMG), routing becomes ambiguous and URLs are silently dropped
        — the running app never receives the ``QFileOpenEvent``. This
        method removes those competing claimants so the canonical
        ``/Applications`` install is the only handler.

        Only touches paths under ``/Volumes/Nuxeo Drive*``. Never the
        running app's own bundle path. Best-effort: failures are logged
        and ignored.
        """
        canonical = _get_app()
        lsregister = (
            "/System/Library/Frameworks/CoreServices.framework/Versions/A"
            "/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
        )

        try:
            volumes = sorted(Path("/Volumes").glob("Nuxeo Drive*"))
        except Exception:
            log.exception("Failed to enumerate /Volumes for Nuxeo Drive mounts")
            return

        for vol in volumes:
            vol_str = str(vol)
            # Never detach the volume the app itself is running from.
            if canonical == vol_str or canonical.startswith(vol_str + "/"):
                continue
            if not vol.is_dir():
                continue
            try:
                subprocess.run(
                    ["/usr/bin/hdiutil", "detach", vol_str, "-force"],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
                log.info(f"Detached competing Nuxeo Drive volume {vol_str!r}")
            except Exception:
                log.exception(f"Failed to detach {vol_str!r}")

            # Drop any stale LSDB entry that pointed at the just-detached
            # mount; otherwise LaunchServices may keep routing to it.
            try:
                subprocess.run(
                    [lsregister, "-u", str(vol / "Nuxeo Drive.app")],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                pass  # lsregister cleanup is purely best-effort

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
        # Remove competing /Volumes/Nuxeo Drive* claimants before we
        # declare ourselves the default handler; see method docstring.
        self._prune_competing_url_handlers()
        LSSetDefaultHandlerForURLScheme(NXDRIVE_SCHEME, bundle_id)
        log.info(f"Registered bundle {bundle_id!r} for URL scheme {NXDRIVE_SCHEME!r}")

    def _send_notification(self, name: str, content: Dict[str, Any], /) -> None:
        """
        Send a notification through the macOS notification center
        to the FinderSync app extension.

        :param name: name of the notification
        :param content: content to send
        """
        nc = NSDistributedNotificationCenter.defaultCenter()
        nc.postNotificationName_object_userInfo_(name, None, content)

    def _set_monitoring(self, operation: str, path: Path, /) -> None:
        """
        Set the monitoring of a folder by the FinderSync.

        :param operation: 'watch' or 'unwatch'
        :param path: path to the folder
        """
        name = f"{BUNDLE_IDENTIFIER}.watchFolder"
        self._send_notification(name, {"operation": operation, "path": str(path)})

    @if_frozen
    def watch_folder(self, folder: Path, /) -> None:
        log.info(f"FinderSync now watching {folder!r}")
        self._set_monitoring("watch", folder)

    @if_frozen
    def unwatch_folder(self, folder: Path, /) -> None:
        log.info(f"FinderSync now ignoring {folder!r}")
        self._set_monitoring("unwatch", folder)

    @if_frozen
    def send_sync_status(self, state: DocPair, path: Path, /) -> None:
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
    def send_content_sync_status(self, states: List[DocPair], path: Path, /) -> None:
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

        entries = [Translator.get(f"CONTEXT_MENU_{i}") for i in range(1, 5)]
        log.debug(f"Sending menu to FinderSync: {entries}")
        self._send_notification(name, {"entries": entries})

    @if_frozen
    def register_folder_link(self, path: Path, /) -> None:
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
    def unregister_folder_link(self, path: Path, /) -> None:
        favorites = self._get_favorite_list()
        if not favorites:
            log.warning("Could not fetch Finder favorites")
            return

        item = self._find_item_in_list(favorites, path.name)
        if not item:
            log.info(f"Favorite {path!r} not found in Finder favorites")
            return

        try:
            LSSharedFileListItemRemove(favorites, item)
        except Exception:
            log.exception(f"Cannot remove {path!r} from Finder favorites")
        else:
            log.info(f"Favorite {path!r} removed from Finder favorites")

    @staticmethod
    def _get_favorite_list() -> List[str]:
        favorites: List[str] = LSSharedFileListCreate(
            None, kLSSharedFileListFavoriteItems, None
        )
        return favorites

    @staticmethod
    def _find_item_in_list(
        lst: List[str], name: str, /
    ) -> Optional[LSSharedFileListItemRef]:
        for item in LSSharedFileListCopySnapshot(lst, None)[0]:
            item_name = LSSharedFileListItemCopyDisplayName(item)
            if name == item_name:
                return item
        return None

    def get_extension_listener(self) -> DarwinExtensionListener:
        assert self._manager
        return DarwinExtensionListener(self._manager)
