'''
@author: Remi Cattiau
'''
from nxdrive.osi import AbstractOSIntegration
from nxdrive.logging_config import get_logger
from nxdrive.utils import find_exe_path
import _winreg
import os
import sys

log = get_logger(__name__)


class WindowsIntegration(AbstractOSIntegration):
    RUN_KEY = 'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
    MENU_PARENT_KEY = 'Software\\Classes\\*\\shell\\Nuxeo drive'
    MENU_KEY = MENU_PARENT_KEY + '\\command'

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
        app_name = self._manager.get_appname()
        if exe_path is None:
            log.warning('Not a frozen windows exe: '
                     'skipping protocol handler registration')
            return

        log.debug("Registering 'nxdrive' protocol handler to: %s", exe_path)
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

    def _recursive_delete(self, reg, start_path, end_path):
        while (len(start_path) < len(end_path)):
            _winreg.DeleteKey(reg, end_path)
            end_path = end_path[0:end_path.rfind('\\')]
            
    def unregister_protocol_handlers(self):
        app_name = self._manager.get_appname()
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        self._recursive_delete(reg, 'Software\\', 'Software\\' + app_name + '\\Protocols\\nxdrive\\shell\\open\\command')
        self._recursive_delete(reg, 'Software\\Classes\\', 'Software\\Classes\\nxdrive\\shell\\open\\command')

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
                  app_name, exe_path, self.MENU_KEY)
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        self._update_reg_key(
            reg, self.MENU_KEY,
            [(app_name, _winreg.REG_SZ, exe_path)],
        )

    def unregister_contextual_menu(self):
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        self._delete_reg_value(reg, self.MENU_KEY, '')
        _winreg.DeleteKey(reg, self.MENU_KEY)
        _winreg.DeleteKey(reg, self.MENU_PARENT_KEY)

    def register_folder_link(self, name, folder_path):
        file_lnk = self._get_folder_link(name)
        self._create_shortcut(file_lnk, folder_path)

    def unregister_folder_link(self, name):
        file_lnk = self._get_folder_link(name)
        if file_lnk is None:
            return
        if os.path.exists(file_lnk):
            os.remove(file_lnk)

    def register_desktop_link(self):
        self._create_shortcut(self._get_desktop_link(), find_exe_path())

    def unregister_desktop_link(self):
        link = self._get_desktop_link()
        if os.path.exists(link):
            os.remove(link)

    def _get_desktop_link(self):
        return os.path.join(self._get_desktop_folder(), self._manager.get_appname() + ".lnk")

    def _get_desktop_folder(self):
        from win32com.shell import shell, shellcon
        return shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOP, 0, 0)

    def _create_shortcut(self, link, filepath, iconpath, description=None):
        import pythoncom
        from win32com.shell import shell, shellcon

        shortcut = pythoncom.CoCreateInstance(
          shell.CLSID_ShellLink,
          None,
          pythoncom.CLSCTX_INPROC_SERVER,
          shell.IID_IShellLink
        )
        executable = filepath
        if iconpath is None:
            iconpath = find_exe_path()
        if description is None:
            description = self.manager.get_appname()
        shortcut.SetPath(executable)
        shortcut.SetDescription(description)
        shortcut.SetIconLocation(iconpath, 0)
        persist_file = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
        persist_file.Save(link, 0)

    def _get_folder_link(self, name=None):
        if name is None:
            name = self._manager.get_appname()
        LOCAL_FAVORITES_FOLDER_WINXP = 'Local Favorites'
        win_version = sys.getwindowsversion()
        if win_version.major == 5:
            favorites = os.path.join(os.path.expanduser('~'), 'Favorites')
            if not os.path.exists(os.path.join(favorites,
                                               LOCAL_FAVORITES_FOLDER_WINXP)):
                os.makedirs(os.path.join(favorites, LOCAL_FAVORITES_FOLDER_WINXP))
            favorites = os.path.join(favorites, LOCAL_FAVORITES_FOLDER_WINXP)
        elif win_version.major > 5:
            favorites = os.path.join(os.path.expanduser('~'), 'Links')
        else:
            log.warning('Windows version %d.%d shortcuts are not supported',
                            win_version.major, win_version.minor)
            return None
        return os.path.join(favorites, name + '.lnk')
