'''
@author: Remi Cattiau
'''
from nxdrive.osi import AbstractOSIntegration
from nxdrive.logging_config import get_logger
from nxdrive.utils import find_exe_path
import _winreg

log = get_logger(__name__)


class WindowsIntegration(AbstractOSIntegration):
    RUN_KEY = 'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
    MENU_KEY = 'Software\\Classes\\*\\shell\\Nuxeo drive\\command'

    def _delete_reg_value(self, reg, path, value):
        key = _winreg.OpenKey(reg, path, 0, _winreg.KEY_ALL_ACCESS)
        _winreg.DeleteValue(key, value)
        _winreg.CloseKey(key)

    def _update_reg_key(self, reg, path, attributes=()):
        """Helper function to create / set a key with attribute values"""
        key = _winreg.CreateKey(reg, path)
        _winreg.CloseKey(key)
        key = _winreg.OpenKey(reg, path, 0, _winreg.KEY_WRITE)
        for attribute, type_, value in attributes:
            # Handle None case for app name in
            # contextual_menu.register_contextual_menu_win32
            if attribute == "None":
                attribute = None
            _winreg.SetValueEx(key, attribute, 0, type_, value)
        _winreg.CloseKey(key)

    '''
    classdocs
    '''
    def register_startup(self):
        """Register ndrive as a startup application in the Registry"""

        reg_key = self.RUN_KEY
        app_name = self._manager.get_appname()
        exe_path = find_exe_path()
        if exe_path is None:
            log.warning('Not a frozen windows exe: '
                     'skipping startup application registration')
            return

        log.debug("Registering '%s' application %s to registry key %s",
            app_name, exe_path, reg_key)
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        self._update_reg_key(
            reg, reg_key,
            [(app_name, _winreg.REG_SZ, exe_path)],
        )

    def unregister_startup(self):
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        self._delete_reg_value(reg, self.RUN_KEY, self._manager.get_appname())

    def register_protocol_handlers(self):
        """Register ndrive as a protocol handler in the Registry"""
        exe_path = find_exe_path()
        if exe_path is None:
            log.warning('Not a frozen windows exe: '
                     'skipping protocol handler registration')
            return

        log.debug("Registering 'nxdrive' protocol handler to: %s", exe_path)
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)

        # Register Nuxeo Drive as a software as a protocol command provider
        command = '"' + exe_path + '" "%1"'
        self._update_reg_key(
            reg, 'Software\\Nuxeo Drive',
            [('', _winreg.REG_SZ, 'Nuxeo Drive')],
        )
        # TODO: add an icon for Nuxeo Drive too
        self._update_reg_key(
            reg, 'Software\\Nuxeo Drive\\Protocols\\nxdrive',
            [('URL Protocol', _winreg.REG_SZ, '')],
        )
        # TODO: add an icon for the nxdrive protocol too
        self._update_reg_key(
            reg,
            'Software\\Nuxeo Drive\\Protocols\\nxdrive\\shell\\open\\command',
            [('', _winreg.REG_SZ, command)],
        )
        # Create the nxdrive protocol key
        nxdrive_class_path = 'Software\\Classes\\nxdrive'
        self._update_win32_reg_key(
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

    def unregister_protocol_handlers(self):
        # TODO Handle this too
        pass

    def register_contextual_menu(self):
        # TODO: better understand why / how this works.
        # See https://jira.nuxeo.com/browse/NXDRIVE-120
        app_name = "None"
        args = " metadata --file \"%1\""
        exe_path = find_exe_path() + args
        if exe_path is None:
            log.warning('Not a frozen windows exe: '
                        'skipping startup application registration')
            return

        log.debug("Registering '%s' application %s to registry key %s",
                  app_name, exe_path, REG_KEY)
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        self.update_reg_key(
            reg, self.MENU_KEY,
            [(app_name, _winreg.REG_SZ, exe_path)],
        )

    def unregister_contextual_menu(self):
        # TODO Handle this too
        pass