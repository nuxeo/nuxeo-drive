# coding: utf-8
import os
from ctypes import windll
from logging import getLogger

import _winreg
import win32api
import win32file
from win32com.client import Dispatch
from win32con import LOGPIXELSX

from nxdrive.osi import AbstractOSIntegration

log = getLogger(__name__)


class WindowsIntegration(AbstractOSIntegration):

    __zoom_factor = None

    @property
    def zoom_factor(self):
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
                log.debug('Cannot get zoom factor (using default 1.0)',
                          exc_info=True)
                self.__zoom_factor = 1.0
        return self.__zoom_factor

    @staticmethod
    def is_partition_supported(folder):
        if folder[-1] != os.path.sep:
            folder = folder + os.path.sep
        if win32file.GetDriveType(folder) != win32file.DRIVE_FIXED:
            return False
        volume = win32file.GetVolumePathName(folder)
        t = win32api.GetVolumeInformation(volume)
        return t[-1] == 'NTFS'

    def get_system_configuration(self):
        result = dict()
        reg = _winreg.HKEY_CURRENT_USER
        reg_key = 'Software\\Nuxeo\\Drive'
        try:
            with _winreg.OpenKey(reg, reg_key, 0, _winreg.KEY_READ) as key:
                for i in range(_winreg.QueryInfoKey(key)[1]):
                    k, v, _ = _winreg.EnumValue(key, i)
                    result[k.replace('-', '_').lower()] = v
        except WindowsError:
            pass
        return result

    def register_folder_link(self, folder_path, name=None):
        favorite = self._get_folder_link(name)
        if not os.path.isfile(favorite):
            self._create_shortcut(favorite, folder_path)

    def unregister_folder_link(self, name):
        try:
            os.remove(self._get_folder_link(name))
        except OSError:
            pass

    def _create_shortcut(self, favorite, filepath):
        try:
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(favorite)
            shortcut.Targetpath = filepath
            shortcut.WorkingDirectory = os.path.dirname(filepath)
            shortcut.IconLocation = filepath
            shortcut.save()
        except:
            log.exception('Could not create the favorite for %r', filepath)
        else:
            log.debug('Registered new favorite in Explorer for %r', filepath)

    def _get_folder_link(self, name=None):
        return os.path.join(
            os.path.expanduser('~'),
            'Links',
            (name or self._manager.app_name) + '.lnk')
