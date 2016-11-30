'''
@author: Remi Cattiau
'''
from nxdrive.osi import AbstractOSIntegration
from nxdrive.logging_config import get_logger
import os
import sys
import platform
import uuid
if sys.platform == "win32":
    import _winreg
log = get_logger(__name__)


class WindowsIntegration(AbstractOSIntegration):
    RUN_KEY = 'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
    EXPLORER = 'SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer'

    def __init__(self, manager):
        super(WindowsIntegration, self).__init__(manager)
        from nxdrive.osi.windows.win32_handlers import WindowsProcessFileHandlerSniffer
        self._file_sniffer = WindowsProcessFileHandlerSniffer()

    def get_menu_parent_key(self):
        return 'Software\\Classes\\*\\shell\\' + self._manager.get_appname()

    def get_menu_key(self):
        return self.get_menu_parent_key() + '\\command'

    def _delete_reg_value(self, reg, path, value):
        if platform.machine().endswith('64'):
            access_mask = _winreg.KEY_ALL_ACCESS | _winreg.KEY_WOW64_64KEY
        else:
            access_mask = _winreg.KEY_ALL_ACCESS
        try:
            key = _winreg.OpenKey(reg, path, 0, access_mask)
        except Exception, e:
            return False
        try:
            _winreg.DeleteValue(key, value)
        except Exception, e:
            return False
        _winreg.CloseKey(key)
        return True

    def get_open_files(self, pids=None):
        return self._file_sniffer.get_open_files(pids)

    '''
       Add registry entries to support to pin in navigation panel.
    '''

    def _add_reg_entries(self, local_folder, engine_id, name ):
        engine_id_guid = '{' + str(uuid.UUID(engine_id)) + '}'
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        path = 'Software\\Classes\\CLSID\\' + engine_id_guid
        self._update_reg_key(reg, path, [
                                    ('', _winreg.REG_SZ, self._manager._get_default_nuxeo_drive_name()),
                                    ('System.IsPinnedToNamespaceTree', _winreg.REG_DWORD, 0x1),
                                    ('SortOrderIndex', _winreg.REG_DWORD, 0x42), ],)
        self._update_reg_key(reg, path + '\\DefaultIcon', [
                                                            ('', _winreg.REG_SZ, self._manager.find_exe_path() + ',0'), ],)
        self._update_reg_key(reg, path + '\\InProcServer32', [
                                                            ('', _winreg.REG_EXPAND_SZ, '%systemroot%\system32\shell32.dll'), ],)
        self._update_reg_key(reg, path + '\\Instance', [
                                                            ('CLSID', _winreg.REG_SZ, '{0E5AAE11-A475-4c5b-AB00-C66DE400274E}'), ],)
        self._update_reg_key(reg, path + '\\Instance\\InitPropertyBag', [
                                                            ('Attributes', _winreg.REG_DWORD, 0x00000011),
                                                            ('TargetFolderPath', _winreg.REG_SZ, local_folder), ],)
        self._update_reg_key(reg, path + '\\ShellFolder', [
                                                            ('FolderValueFlags', _winreg.REG_DWORD, 0x28),
                                                            ('Attributes', _winreg.REG_DWORD, 0xf080004d), ],)
        self._update_reg_key(reg, self.EXPLORER + '\\HideDesktopIcons\\NewStartPanel', [
                                                            (engine_id_guid, _winreg.REG_DWORD, 0x1), ],)
        self._update_reg_key(reg, self.EXPLORER + '\\Desktop\\NameSpace\\' + engine_id_guid, [
                                                            ('', _winreg.REG_SZ, name), ],)

    def _update_reg_key(self, reg, path, attributes=()):
        """Helper function to create / set a key with attribute values"""

        if platform.machine().endswith('64'):
            access_mask = _winreg.KEY_ALL_ACCESS | _winreg.KEY_WOW64_64KEY
        else:
            access_mask = _winreg.KEY_ALL_ACCESS

        key = _winreg.CreateKeyEx(reg, path, 0, access_mask)
        _winreg.CloseKey(key)
        key = _winreg.OpenKey(reg, path, 0, access_mask)
        for attribute, type_, value in attributes:
            # Handle None case for app name in
            # contextual_menu.register_contextual_menu_win32
            if attribute == "None":
                attribute = None
            _winreg.SetValueEx(key, attribute, 0, type_, value)
        _winreg.CloseKey(key)

    def get_zoom_factor(self):
        try:
            if AbstractOSIntegration.os_version_below("6.0.6000"):
                # API added on Vista
                return 1.00
            from ctypes import windll
            from win32con import LOGPIXELSX
            # Enable DPI detection
            windll.user32.SetProcessDPIAware()
            # Get Desktop DC
            hDC = windll.user32.GetDC(None)
            dpiX = windll.gdi32.GetDeviceCaps( hDC, LOGPIXELSX)
            windll.user32.ReleaseDC(None, hDC)
            # Based on https://technet.microsoft.com/en-us/library/dn528846.aspx
            return dpiX / 96.0
        except Exception as e:
            log.debug("Can't get zoom factor: %r", e)
        return 1.00

    '''
    classdocs
    '''
    def register_startup(self):
        """Register ndrive as a startup application in the Registry"""

        reg_key = self.RUN_KEY
        app_name = self._manager.get_appname()
        exe_path = self._manager.find_exe_path()
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
        exe_path = self._manager.find_exe_path()
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

    def traverse_path(self, reg, start_path, access_mask, enrties_list):
        key = _winreg.OpenKey(reg, start_path, 0, access_mask)
        count = 0
        child_count = _winreg.QueryInfoKey(key)[0]
        while count < child_count:
            reg_name = _winreg.EnumKey(key, count)
            self.traverse_path(reg, start_path + '\\' + reg_name, access_mask, enrties_list)
            enrties_list.append(start_path + '\\' + reg_name)
            count = count + 1
        _winreg.CloseKey(key)

    '''
        delete registry entries added for windows 10 navigation panel
    '''

    def _delete_registry_entries(self, engine_id):
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        path = 'Software\\Classes\\CLSID'
        engine_id_guid = '{' + str(uuid.UUID(engine_id)) + '}'
        self._recursive_delete(reg, path, engine_id_guid)
        self._recursive_delete(reg, self.EXPLORER + '\Desktop\NameSpace', engine_id_guid)
        self._delete_reg_value(reg, self.EXPLORER + '\HideDesktopIcons\NewStartPanel', engine_id_guid)

    def _recursive_delete(self, reg, start_path, name):
        if platform.machine().endswith('64'):
            access_mask = _winreg.KEY_ALL_ACCESS | _winreg.KEY_WOW64_64KEY
        else:
            access_mask = _winreg.KEY_ALL_ACCESS

        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        entries_list = list()
        self.traverse_path(reg, start_path + '\\' + name, access_mask, entries_list)
        entries_list.append(start_path + '\\' + name)
        key = _winreg.OpenKey(reg, start_path, 0, access_mask)
        for entry in entries_list:
            local_path = entry
            _winreg.DeleteKey(key, local_path.replace(start_path + '\\', ''))
        _winreg.CloseKey(key)

    def unregister_protocol_handlers(self):
        app_name = self._manager.get_appname()
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        self._recursive_delete(reg, 'Software', app_name)
        self._recursive_delete(reg, 'Software\\Classes', 'nxdrive')

    def register_contextual_menu(self):
        # TODO: better understand why / how this works.
        # See https://jira.nuxeo.com/browse/NXDRIVE-120
        app_name = "None"
        args = " metadata --file \"%1\""
        exe_path = self._manager.find_exe_path() + args
        if exe_path is None:
            log.warning('Not a frozen windows exe: '
                        'skipping startup application registration')
            return
        icon_path = self._manager.find_exe_path() + ",0"
        log.debug("Registering '%s' application %s to registry key %s",
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

    def is_same_partition(self, folder1, folder2):
        import win32file
        volume = win32file.GetVolumePathName(folder1)
        return volume == win32file.GetVolumePathName(folder2)

    def is_partition_supported(self, folder):
        if folder[-1] != os.path.sep:
            folder = folder + os.path.sep
        import win32file
        if win32file.GetDriveType(folder) != win32file.DRIVE_FIXED:
            return False
        volume = win32file.GetVolumePathName(folder)
        import win32api
        t = win32api.GetVolumeInformation(volume)
        return t[-1] == 'NTFS'

    def get_system_configuration(self):
        result = dict()
        try:
            reg = _winreg.ConnectRegistry(None, _winreg.HKEY_LOCAL_MACHINE)
            key = _winreg.OpenKey(reg, "Software\\Nuxeo\\Drive", 0, _winreg.KEY_READ)
            for i in xrange(0, _winreg.QueryInfoKey(key)[1]):
                subkey = _winreg.EnumValue(key, i)
                result[subkey[0].replace('-', '_')] = subkey[1]
            _winreg.CloseKey(key)
        except WindowsError:
            pass
        return result

    def unregister_contextual_menu(self):
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        if self._delete_reg_value(reg, self.get_menu_key(), ''):
            _winreg.DeleteKey(reg, self.get_menu_key())
            _winreg.DeleteKey(reg, self.get_menu_parent_key())

    def register_folder_link(self, folder_path, engine_id, name=None):
        file_lnk = self._get_folder_link(name)
        self._create_shortcut(file_lnk, folder_path)
        if platform.release() == '10':
            self._add_reg_entries(folder_path, engine_id, name)

    def unregister_folder_link(self, name, engine_id):

        if platform.release() == '10':
            self._delete_registry_entries(engine_id)

        file_lnk = self._get_folder_link(name)
        if file_lnk is None:
            return
        if os.path.exists(file_lnk):
            os.remove(file_lnk)

    def register_desktop_link(self):
        self._create_shortcut(self._get_desktop_link(), self._manager.find_exe_path())

    def unregister_desktop_link(self):
        link = self._get_desktop_link()
        if os.path.exists(link):
            os.remove(link)

    def _get_desktop_link(self):
        return os.path.join(self._get_desktop_folder(), self._manager.get_appname() + ".lnk")

    def _get_desktop_folder(self):
        from win32com.shell import shell, shellcon
        return shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOP, 0, 0)

    def _create_shortcut(self, link, filepath, iconpath=None, description=None):
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
            iconpath = self._manager.find_exe_path()
        if description is None:
            description = self._manager.get_appname()
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
