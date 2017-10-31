# coding: utf-8
import os
from ctypes import windll

import _winreg
import win32api
import win32file
from win32com.client import Dispatch
from win32con import LOGPIXELSX

from nxdrive.logging_config import get_logger
from nxdrive.osi import AbstractOSIntegration
from nxdrive.osi.windows.win32_handlers import WindowsProcessFileHandlerSniffer

log = get_logger(__name__)


class WindowsIntegration(AbstractOSIntegration):

    RUN_KEY = 'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
    __zoom_factor = None

    def __init__(self, manager):
        super(WindowsIntegration, self).__init__(manager)
        self._file_sniffer = WindowsProcessFileHandlerSniffer()

    def get_menu_parent_key(self):
        return 'Software\\Classes\\*\\shell\\' + self._manager.app_name

    def get_menu_key(self):
        return self.get_menu_parent_key() + '\\command'

    @staticmethod
    def _delete_reg_value(reg, path, value):
        try:
            with _winreg.OpenKey(reg, path, 0, _winreg.KEY_ALL_ACCESS) as key:
                _winreg.DeleteValue(key, value)
                return True
        except WindowsError:
            return False

    def get_open_files(self, pids=None):
        return self._file_sniffer.get_open_files(pids)

    @staticmethod
    def _update_reg_key(reg, path, attributes=()):
        """ Helper function to create / set a key with attribute values. """

        key = _winreg.CreateKey(reg, path)
        _winreg.CloseKey(key)
        with _winreg.OpenKey(reg, path, 0, _winreg.KEY_WRITE) as key:
            for attribute, type_, value in attributes:
                # Handle None case for app name in
                # contextual_menu.register_contextual_menu_win32
                if attribute == 'None':
                    attribute = None
                _winreg.SetValueEx(key, attribute, 0, type_, value)

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

    def register_startup(self):
        """ Register ndrive as a startup application in the registry. """

        reg_key = self.RUN_KEY
        app_name = self._manager.app_name
        exe_path = self._manager.find_exe_path()
        if exe_path is None:
            log.warning('Not a frozen windows exe:'
                        'skipping startup application registration')
            return

        log.debug(
            'Registering %r application %r to registry key %r',
            app_name, exe_path, reg_key)
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        self._update_reg_key(
            reg, reg_key,
            [(app_name, _winreg.REG_SZ, exe_path)],
        )

    def unregister_startup(self):
        self._delete_reg_value(
            _winreg.HKEY_CURRENT_USER, self.RUN_KEY, self._manager.app_name)

    def register_protocol_handlers(self):
        """Register ndrive as a protocol handler in the Registry"""
        exe_path = self._manager.find_exe_path()
        app_name = self._manager.app_name
        if exe_path is None:
            return

        log.debug('Registering "nxdrive" protocol handler to: %r', exe_path)
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)

        # Register Nuxeo Drive as a software as a protocol command provider
        command = '"' + exe_path + '" "%1"'
        self._update_reg_key(
            reg, 'Software\\' + app_name,
            [('', _winreg.REG_SZ, app_name)],
        )
        # TODO: add an icon for Nuxeo Drive too
        self._update_reg_key(
            reg, 'Software\\' + app_name + '\\Protocols\\nxdrive',
            [('URL Protocol', _winreg.REG_SZ, '')],
        )
        # TODO: add an icon for the nxdrive protocol too
        self._update_reg_key(
            reg,
            'Software\\' + app_name + '\\Protocols\\nxdrive\\shell\\open\\command',
            [('', _winreg.REG_SZ, command)],
        )
        # Create the nxdrive protocol key
        nxdrive_class_path = 'Software\\Classes\\nxdrive'
        self._update_reg_key(
            reg, nxdrive_class_path,
            [
                ('EditFlags', _winreg.REG_DWORD, 2),
                ('', _winreg.REG_SZ, 'URL:nxdrive Protocol'),
                ('URL Protocol', _winreg.REG_SZ, ''),
            ],
        )
        # Create the nxdrive command key
        command_path = nxdrive_class_path + '\\shell\\open\\command'
        self._update_reg_key(
            reg, command_path,
            [('', _winreg.REG_SZ, command)],
        )

    def _recursive_delete(self, key0, key1, key2=''):
        """ Delete a key and its subkeys. """

        current = key1 if not key2 else key1 + '\\' + key2
        with _winreg.OpenKey(key0, current, 0, _winreg.KEY_ALL_ACCESS) as key:
            info = _winreg.QueryInfoKey(key)
            for x in range(info[0]):
                """
                Deleting the subkey will change the SubKey count used by EnumKey.
                We must always pass 0 to EnumKey so we always get back the new
                first SubKey.
                """
                subkey = _winreg.EnumKey(key, 0)
                try:
                    _winreg.DeleteKey(key, subkey)
                except WindowsError:
                    self._recursive_delete(key0, current, key2=subkey)

        try:
            _winreg.DeleteKey(key0, key1)
        except WindowsError:
            pass

    def unregister_protocol_handlers(self):
        app_name = self._manager.app_name
        reg = _winreg.HKEY_CURRENT_USER
        self._recursive_delete(reg, 'Software\\' + app_name + '\\Protocols\\nxdrive')
        self._recursive_delete(reg, 'Software\\Classes\\nxdrive')

    def register_contextual_menu(self):
        # TODO: better understand why / how this works.
        # See https://jira.nuxeo.com/browse/NXDRIVE-120
        app_name = 'None'
        args = ' metadata --file "%1"'
        exe_path = self._manager.find_exe_path() + args
        if exe_path is None:
            return
        icon_path = self._manager.find_exe_path() + ',0'
        log.debug('Registering %r application %r to registry key %r',
                  app_name, exe_path, self.get_menu_key())
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        self._update_reg_key(
            reg, self.get_menu_key(),
            [(app_name, _winreg.REG_SZ, exe_path)],
        )
        self._update_reg_key(
            reg, self.get_menu_parent_key(),
            [("Icon", _winreg.REG_SZ, icon_path)],
        )

    @staticmethod
    def is_same_partition(folder1, folder2):
        volume = win32file.GetVolumePathName(folder1)
        return volume == win32file.GetVolumePathName(folder2)

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
        try:
            with _winreg.OpenKey(reg, 'Software\\Nuxeo\\Drive', 0, _winreg.KEY_READ) as key:
                for i in range(_winreg.QueryInfoKey(key)[1]):
                    k, v, _ = _winreg.EnumValue(key, i)
                    result[k.replace('-', '_').lower()] = v
        except WindowsError:
            pass
        return result

    def unregister_contextual_menu(self):
        reg = _winreg.HKEY_CURRENT_USER
        if self._delete_reg_value(reg, self.get_menu_key(), ''):
            _winreg.DeleteKey(reg, self.get_menu_key())
            _winreg.DeleteKey(reg, self.get_menu_parent_key())

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
