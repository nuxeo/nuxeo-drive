# coding: utf-8
import sys
from logging import getLogger


log = getLogger(__name__)


class AbstractOSIntegration(object):

    zoom_factor = 1.0

    def __init__(self, manager):
        self._manager = manager

    def register_startup(self):
        pass

    def unregister_startup(self):
        pass

    @staticmethod
    def is_partition_supported(folder):
        return True

    def uninstall(self):
        """ Several action to do before uninstalling Drive. """

        # macOS only
        self.unregister_contextual_menu()
        self.unregister_protocol_handlers()
        self.unregister_startup()

        # Windows and macOS
        self.unregister_folder_link(None)

    def register_protocol_handlers(self):
        pass

    def unregister_protocol_handlers(self):
        pass

    def register_contextual_menu(self):
        pass

    def unregister_contextual_menu(self):
        pass

    def register_folder_link(self, folder_path, name=None):
        pass

    def unregister_folder_link(self, name):
        pass

    def get_system_configuration(self):
        return dict()

    @staticmethod
    def is_mac():
        return sys.platform == 'darwin'

    @staticmethod
    def is_windows():
        return sys.platform == 'win32'

    @staticmethod
    def is_linux():
        return not (AbstractOSIntegration.is_mac()
                    or AbstractOSIntegration.is_windows())

    @staticmethod
    def get(manager):
        if AbstractOSIntegration.is_mac():
            from nxdrive.osi.darwin.darwin import DarwinIntegration
            integration, nature = DarwinIntegration, 'macOS'
        elif AbstractOSIntegration.is_windows():
            from nxdrive.osi.windows.windows import WindowsIntegration
            integration, nature = WindowsIntegration, 'Windows'
        else:
            integration, nature = AbstractOSIntegration, 'None'

        log.debug('OS integration type: %s', nature)
        return integration(manager)
