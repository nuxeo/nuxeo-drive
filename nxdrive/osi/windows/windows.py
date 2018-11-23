# coding: utf-8
import os
import sys
from contextlib import suppress
from ctypes import windll  # type: ignore
from logging import getLogger
from typing import Any, Dict

import win32api
import win32file
from win32com.client import Dispatch
from win32con import LOGPIXELSX

from . import registry
from .. import AbstractOSIntegration
from ...constants import APP_NAME
from ...options import Options
from ...translator import Translator
from ...utils import if_frozen

__all__ = ("WindowsIntegration",)

log = getLogger(__name__)


class WindowsIntegration(AbstractOSIntegration):
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
                log.debug("Cannot get zoom factor (using default 1.0)", exc_info=True)
                self.__zoom_factor = 1.0
        return self.__zoom_factor

    @staticmethod
    def is_partition_supported(folder: str) -> bool:
        if folder[-1] != os.path.sep:
            folder = folder + os.path.sep
        if win32file.GetDriveType(folder) != win32file.DRIVE_FIXED:
            return False
        volume = win32file.GetVolumePathName(folder)
        t = win32api.GetVolumeInformation(volume)
        return t[-1] == "NTFS"

    def get_system_configuration(self) -> Dict[str, Any]:
        config = registry.read("Software\\Nuxeo\\Drive") or {}
        return {key.replace("-", "_").lower(): value for key, value in config.items()}

    @if_frozen
    def register_contextual_menu(self) -> None:
        log.debug("Registering contextual menu")

        # Register a submenu for both files (*) and folders (directory)
        for item in ("*", "directory"):
            registry.write(
                f"Software\\Classes\\{item}\\shell\\{APP_NAME}",
                {
                    "Icon": f"{sys.executable},0",
                    "MUIVerb": APP_NAME,
                    "ExtendedSubCommandsKey": f"*\\shell\\{APP_NAME}\\",
                },
            )

        self.register_contextual_menu_entry(
            Translator.get("CONTEXT_MENU_1"),
            'access-online --file %1"',
            "shell32.dll,17",
            1,
        )
        self.register_contextual_menu_entry(
            Translator.get("CONTEXT_MENU_2"),
            'copy-share-link --file %1"',
            "shell32.dll,134",
            2,
        )
        self.register_contextual_menu_entry(
            Translator.get("CONTEXT_MENU_3"),
            'edit-metadata --file %1"',
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
            f"{sys.executable} {command}",
        )

    @if_frozen
    def unregister_contextual_menu(self) -> None:
        log.debug("Unregistering contextual menu")

        for item in ("*", "directory"):
            registry.delete(f"Software\\Classes\\{item}\\shell\\{APP_NAME}")

    @if_frozen
    def register_folder_link(self, folder_path: str, name: str = None) -> None:
        favorite = self._get_folder_link(name)
        if not os.path.isfile(favorite):
            self._create_shortcut(favorite, folder_path)

    @if_frozen
    def unregister_folder_link(self, name: str = None) -> None:
        with suppress(OSError):
            os.remove(self._get_folder_link(name))

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

    def _create_shortcut(self, favorite: str, filepath: str) -> None:
        try:
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(favorite)
            shortcut.Targetpath = filepath
            shortcut.WorkingDirectory = os.path.dirname(filepath)
            shortcut.IconLocation = filepath
            shortcut.save()
        except:
            log.exception(f"Could not create the favorite for {filepath!r}")
        else:
            log.debug(f"Registered new favorite in Explorer for {filepath!r}")

    def _get_folder_link(self, name: str = None) -> str:
        return os.path.join(Options.home, "Links", (name or APP_NAME) + ".lnk")
