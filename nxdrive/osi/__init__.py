# coding: utf-8
from logging import getLogger

from ..constants import MAC, WINDOWS

log = getLogger(__name__)


class AbstractOSIntegration:

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
        """
        Actions to perform before uninstalling Drive.
        One action might do nothing depending on its OS-specific
        implementation.
        """
        self.unregister_startup()
        self.unregister_folder_link(None)

    def register_protocol_handlers(self):
        pass

    def unregister_protocol_handlers(self):
        pass

    def watch_folder(self, folder):
        pass

    def unwatch_folder(self, folder):
        pass

    def send_sync_status(self, state, path):
        pass

    def register_folder_link(self, folder_path, name=None):
        pass

    def unregister_folder_link(self, name):
        pass

    def get_system_configuration(self):
        return dict()

    @staticmethod
    def get(manager):
        if MAC:
            from .darwin.darwin import DarwinIntegration
            integration, nature = DarwinIntegration, 'macOS'
        elif WINDOWS:
            from .windows.windows import WindowsIntegration
            integration, nature = WindowsIntegration, 'Windows'
        else:
            integration, nature = AbstractOSIntegration, 'None'

        log.debug('OS integration type: %s', nature)
        return integration(manager)
