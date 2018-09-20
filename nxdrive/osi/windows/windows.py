# coding: utf-8
import os
import sys
from contextlib import suppress
from ctypes import windll  # type: ignore
from logging import getLogger
from typing import Any, Dict

import win32api
import win32file
import winreg
from win32com.client import Dispatch
from win32con import LOGPIXELSX

from .. import AbstractOSIntegration
from ...constants import APP_NAME
from ...options import Options
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
        result = dict()
        reg = winreg.HKEY_CURRENT_USER
        reg_key = "Software\\Nuxeo\\Drive"
        with suppress(WindowsError):
            with winreg.OpenKey(reg, reg_key, 0, winreg.KEY_READ) as key:
                for i in range(winreg.QueryInfoKey(key)[1]):
                    k, v, _ = winreg.EnumValue(key, i)
                    result[k.replace("-", "_").lower()] = v
        return result

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
        reg = winreg.HKEY_CURRENT_USER
        reg_key = "Software\\Microsoft\\Windows\\CurrentVersion\\Run"

        try:
            with winreg.CreateKey(reg, reg_key) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, sys.executable)
            return True
        except WindowsError:
            log.exception("Error while trying to modify registry.")
            return False

    @if_frozen
    def unregister_startup(self) -> bool:
        reg = winreg.HKEY_CURRENT_USER
        reg_key = "Software\\Microsoft\\Windows\\CurrentVersion\\Run"

        try:
            with winreg.OpenKey(reg, reg_key, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
            return True
        except WindowsError:
            log.exception("Error while trying to modify registry.")
            return False

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
        return os.path.join(
            Options.home, "Links", (name or self._manager.app_name) + ".lnk"
        )
