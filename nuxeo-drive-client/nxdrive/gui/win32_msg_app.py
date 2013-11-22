'''https://jira.nuxeo.com/browse/SUPNXP-9065

On win32 platform, when a separate ndrivew.exe process is launched by a 'edit'
command, which is triggered by a user clicking on a custom URL 'nxdrive://...',
the QApplication object is not initialized at all, so no system tray is
initialised for this process. Therefore, it's not able to show message in
system tray area as it does on Mac OS.

This class is a temporary solution to this issue on Win32.
'''

__author__ = 'jiakuanwang'

from PyQt4 import QtCore
from PyQt4 import QtGui

from nxdrive.logging_config import get_logger
from nxdrive.gui.resources import find_icon
from nxdrive.gui.application import Communicator

log = get_logger(__name__)

class Win32MsgApplication(QtGui.QApplication):
    def __init__(self, controller, argv=()):
        super(Win32MsgApplication, self).__init__(list(argv))
        self.controller = controller

        self._setup_systray()
        self._create_systray_menu()

        self.communicator = Communicator()
        self.communicator.stop.connect(self.quit)

        # Register frontend into the controller so that user message can be
        # notified inside the controller. For more information, please see
        # https://jira.nuxeo.com/browse/SUPNXP-9065
        self.controller.register_frontend(self)

        # Shutdown the app after 10 seconds

    def notify_user_message(self, msg_title, msg_body):
        if msg_title is not None and msg_body is not None:
            self._tray_icon.showMessage(msg_title, msg_body)
        else:
            log.error("Both message title and message body cannot be empty")

    def _setup_systray(self):
        self._tray_icon = QtGui.QSystemTrayIcon()
        self.update_running_icon()
        self._tray_icon.show()

    def _create_systray_menu(self):
        tray_icon_menu = QtGui.QMenu()
        quit_action = QtGui.QAction("&Quit Editor Launcher", tray_icon_menu,
                                    triggered=self.quit)
        tray_icon_menu.addAction(quit_action)
        self._tray_icon.setContextMenu(tray_icon_menu)

    def update_running_icon(self):
        icon = find_icon('nuxeo_drive_systray_icon_%s_18.png' % 'enabled')
        if icon is not None:
            self._tray_icon.setIcon(QtGui.QIcon(icon))
        else:
            log.warning('Icon not found: %s', icon)

    def stop(self):
        log.debug('Stopping win32 message application...')
        self.communicator.stop.emit()