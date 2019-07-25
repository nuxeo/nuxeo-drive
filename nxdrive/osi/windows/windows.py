# coding: utf-8
import os
import sys
import subprocess
from contextlib import suppress
from ctypes import windll  # type: ignore
from logging import getLogger
from pathlib import Path
from typing import Any, Dict

import win32api
import win32file
from PyQt5.QtCore import pyqtSlot
from win32com.client import Dispatch
from win32com.shell import shell, shellcon
from win32con import LOGPIXELSX

from . import registry
from .extension import (
    disable_overlay,
    enable_overlay,
    set_filter_folders,
    WindowsExtensionListener,
)
from .. import AbstractOSIntegration
from ...constants import APP_NAME, CONFIG_REGISTRY_KEY
from ...objects import DocPair
from ...options import Options
from ...translator import Translator
from ...utils import force_encode, get_value, if_frozen

__all__ = ("WindowsIntegration",)

log = getLogger(__name__)


class WindowsIntegration(AbstractOSIntegration):

    nature = "Windows"

    @if_frozen
    def _init(self) -> None:
        if self._manager:
            watched_folders = {
                engine.local_folder for engine in self._manager._engine_definitions
            }
            if watched_folders:
                set_filter_folders(watched_folders)
                enable_overlay()

    @if_frozen
    def _cleanup(self) -> None:
        disable_overlay()

    @property
    def zoom_factor(self) -> float:
        if not self.__zoom_factor:
            try:
                # Enable DPI detection
                windll.user32.SetProcessDPIAware()
                display = windll.user32.GetDC(None)
                dpi = windll.gdi32.GetDeviceCaps(display, LOGPIXELSX)
                windll.user32.ReleaseDC(None, display)
                # See https://technet.microsoft.com/en-us/library/dn528846.aspx
                self.__zoom_factor = dpi / 96.0
            except:
                log.info("Cannot get zoom factor (using default 1.0)", exc_info=True)
                self.__zoom_factor = 1.0
        return self.__zoom_factor

    @pyqtSlot(result=bool)
    def addons_installed(self) -> bool:
        """Check if add-ons are installed or not."""
        if (
            Options.system_wide
            or (Path(sys.executable).parent / "addons-installed.txt").is_file()
        ):
            return True
        return False

    @staticmethod
    def cb_get() -> str:
        """Get the text data from the clipboard.
        Emulate: CTRL + V
        """
        import win32clipboard

        win32clipboard.OpenClipboard()
        text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return text

    @staticmethod
    def cb_set(text: str) -> None:
        """Copy some *text* into the clipboard.
        Emulate: CTRL + C
        """
        import win32clipboard

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()

    @pyqtSlot(result=bool)
    def install_addons(self, setup: str = "nuxeo-drive-addons.exe") -> bool:
        """Install addons using the installer shipped within the main installer."""
        installer = Path(sys.executable).parent / setup
        if not installer.is_file():
            log.warning(f"Addons installer {installer!r} not found.")
            return False

        log.info(f"Installing addons from {installer!r} ...")
        try:
            subprocess.run([str(installer)])
        except Exception:
            log.exception(f"Unknown error while trying to install addons")
        else:
            return self.addons_installed()
        return False

    @staticmethod
    def is_partition_supported(path: Path) -> bool:
        """
        Only NTFS is supported on Windows.
        FAT and FAT32 do not support extended attributes.
        """
        folder = str(path)
        if folder[-1] != os.path.sep:
            folder += os.path.sep
        if win32file.GetDriveType(folder) != win32file.DRIVE_FIXED:
            return False
        volume = win32file.GetVolumePathName(folder)
        return win32api.GetVolumeInformation(volume)[-1] == "NTFS"

    def get_system_configuration(self) -> Dict[str, Any]:
        if not registry.exists(CONFIG_REGISTRY_KEY):
            return {}

        config = registry.read(CONFIG_REGISTRY_KEY) or {}
        return {
            key.replace("-", "_").lower(): get_value(value)
            for key, value in config.items()
        }

    def open_local_file(self, file_path: str, select: bool = False) -> None:
        """Note that this function must _not_ block the execution."""
        if select:
            win32api.ShellExecute(
                None, "open", "explorer.exe", f"/select,{file_path}", None, 1
            )
        else:
            # startfile() returns as soon as the associated application is launched.
            os.startfile(file_path)  # type: ignore

    @if_frozen
    def register_contextual_menu(self) -> None:
        log.info("Registering contextual menu")

        # Register a submenu for both files (*) and folders (directory)
        for item in ("*", "directory"):
            registry.write(
                f"Software\\Classes\\{item}\\shell\\{APP_NAME}",
                {
                    "Icon": f'"{sys.executable}",0',
                    "MUIVerb": APP_NAME,
                    "ExtendedSubCommandsKey": f"*\\shell\\{APP_NAME}\\",
                },
            )

        self.register_contextual_menu_entry(
            Translator.get("CONTEXT_MENU_1"),
            'access-online --file "%1"',
            "shell32.dll,17",
            1,
        )
        self.register_contextual_menu_entry(
            Translator.get("CONTEXT_MENU_2"),
            'copy-share-link --file "%1"',
            "shell32.dll,134",
            2,
        )
        self.register_contextual_menu_entry(
            Translator.get("CONTEXT_MENU_3"),
            'edit-metadata --file "%1"',
            "shell32.dll,269",
            3,
        )

    @if_frozen
    def register_contextual_menu_entry(
        self, name: str, command: str, icon: str, n: int
    ) -> None:
        registry.write(
            f"Software\\Classes\\*\\shell\\{APP_NAME}\\shell\\item{n}",
            {"MUIVerb": name, "Icon": icon},
        )
        registry.write(
            f"Software\\Classes\\*\\shell\\{APP_NAME}\\shell\\item{n}\\command",
            f'"{sys.executable}" {command}',
        )

    @if_frozen
    def unregister_contextual_menu(self) -> None:
        log.info("Unregistering contextual menu")

        for item in ("*", "directory"):
            registry.delete(f"Software\\Classes\\{item}\\shell\\{APP_NAME}")

    @if_frozen
    def register_folder_link(self, path: Path) -> None:
        favorite = self._get_folder_link(path.name)
        if not favorite.is_file():
            self._create_shortcut(favorite, path)

    @if_frozen
    def unregister_folder_link(self, path: Path) -> None:
        with suppress(OSError):
            self._get_folder_link(path.name).unlink()

    @if_frozen
    def register_startup(self) -> bool:
        return registry.write(
            "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            {APP_NAME: sys.executable},
        )

    @if_frozen
    def unregister_startup(self) -> bool:
        return registry.delete_value(
            "Software\\Microsoft\\Windows\\CurrentVersion\\Run", APP_NAME
        )

    def _create_shortcut(self, favorite: Path, path: Path) -> None:
        try:
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(str(favorite))
            shortcut.Targetpath = str(path)
            shortcut.WorkingDirectory = str(path.parent)
            shortcut.IconLocation = str(path)
            shortcut.save()
        except Exception:
            log.warning(f"Could not create the favorite for {path!r}", exc_info=True)
        else:
            log.info(f"Registered new favorite in Explorer for {path!r}")

    def _get_folder_link(self, name: str = None) -> Path:
        return Options.home / "Links" / f"{name or APP_NAME}.lnk"

    @if_frozen
    def send_sync_status(self, state: DocPair, path: Path) -> None:
        shell.SHChangeNotify(
            shellcon.SHCNE_UPDATEITEM,
            shellcon.SHCNF_PATH | shellcon.SHCNF_FLUSH,
            force_encode(str(path)),
            None,
        )

    def _watch_or_ignore(self, folder: Path, action: str) -> None:

        if not self._manager:
            return

        log.debug(f"Making Explorer {action} {folder!r}")
        paths = {e.local_folder for e in self._manager.engines.values()}

        if action == "watch":
            paths.add(folder)
        else:
            paths.discard(folder)

        set_filter_folders(paths)
        log.info(f"{folder!r} is now in Explorer {action} list")

    @if_frozen
    def watch_folder(self, folder: Path) -> None:
        self._watch_or_ignore(folder, "watch")

    @if_frozen
    def unwatch_folder(self, folder: Path) -> None:
        self._watch_or_ignore(folder, "ignore")

    def get_extension_listener(self) -> WindowsExtensionListener:
        return WindowsExtensionListener(self._manager)
