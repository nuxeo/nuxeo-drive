"""Main QT application handling OS events and system tray UI"""

import os
from threading import Thread
from nxdrive.protocol_handler import parse_protocol_url
from nxdrive.logging_config import get_logger
from nxdrive.gui.resources import find_icon
from nxdrive.gui.authentication import prompt_authentication
from nxdrive.controller import default_nuxeo_drive_folder

log = get_logger(__name__)

# Keep QT an optional dependency for now
QtGui, QApplication, QObject = None, object, object
try:
    from PySide import QtGui
    from PySide import QtCore
    QApplication = QtGui.QApplication
    QObject = QtCore.QObject
    log.debug("QT / PySide successfully imported")
except ImportError:
    log.warning("QT / PySide is not installed: GUI is disabled")
    pass


class Communicator(QObject):
    """Handle communication between sync and main GUI thread

    Use a signal to notify the main thread event loops about states update by
    the synchronization thread.

    """
    # (event name, new icon, rebuild menu)
    icon = QtCore.Signal(str)
    menu = QtCore.Signal()
    stop = QtCore.Signal()


class BindingInfo(object):
    """Summarize the state of each server connection"""

    online = True

    n_pending = 0

    has_more_pending = False

    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.short_name = os.path.basename(folder_path)

    def get_status_message(self):
        # TODO: i18n
        if self.online:
            if self.n_pending != 0:
                return "%d%s pending operations" % (
                    self.n_pending, '+' if self.has_more_pending else '')
            else:
                return "Up-to-date"
        else:
            return "Offline"

    def __str__(self):
        return "%s: %s" % (self.short_name, self.get_status_message())


class Application(QApplication):
    """Main Nuxeo drive application controlled by a system tray icon + menu"""

    sync_thread = None

    def __init__(self, controller, options, argv=()):
        super(Application, self).__init__(list(argv))
        self.controller = controller
        self.options = options

        # This is a windowless application mostly using the system tray
        self.setQuitOnLastWindowClosed(False)
        self._setup_systray()
        self.quit_on_stop = False
        self.state = 'paused'
        self.binding_info = {}
        self.rebuild_menu()

        # Put communication channel in place and start synchronization thread
        self.communicator = Communicator()
        self.communicator.icon.connect(self.set_icon)
        self.communicator.menu.connect(self.rebuild_menu)
        self.communicator.stop.connect(self.handle_stop)
        self.start_synchronization_thread()

    def get_info(self, local_folder):
        info = self.binding_info.get(local_folder, None)
        if info is None:
            info = BindingInfo(local_folder)
            self.binding_info[local_folder] = info
        return info

    @QtCore.Slot(str)
    def set_icon(self, state):
        """Execute systray icon change operations triggered by state change

        The synchronization thread can update the state info but cannot
        directly call QtGui widget methods. The should be executed by the main
        thread event loop, hence the delegation to this method that is
        triggered by a signal to allow for message passing between the 2
        threads.

        """
        icon = find_icon('nuxeo_drive_systray_icon_%s_18.png' % state)
        if icon is not None:
            self._tray_icon.setIcon(QtGui.QIcon(icon))
        else:
            log.warning('Icon not found: %s', icon)

    def action_quit(self):
        self.communicator.icon.emit('stopping')
        self.state = 'quitting'
        self.quit_on_stop = True
        self.communicator.menu.emit()
        if self.sync_thread is not None:
            # Ask the conntroller to stop: the synchronization loop will in turn
            # call notify_sync_stopped and finally handle_stop
            self.controller.stop()
        else:
            # quit directly
            self.quit()

    @QtCore.Slot()
    def handle_stop(self):
        if self.quit_on_stop:
            self.quit()

    def notify_local_folders(self, local_folders):
        """Cleanup unbound server bindings if any"""
        refresh = False
        for registered_folder in self.binding_info.keys():
            if registered_folder not in local_folders:
                del self.binding_info[registered_folder]
                refresh = True
        if refresh:
            self.communicator.menu.emit()

    def notify_sync_started(self):
        self.state = 'running'
        self.communicator.icon.emit('enabled')
        self.communicator.menu.emit()

    def notify_sync_stopped(self):
        self.state = 'paused'
        self.sync_thread = None
        self.communicator.icon.emit('disabled')
        self.communicator.menu.emit()
        self.communicator.stop.emit()

    def notify_offline(self, local_folder):
        info = self.get_info(local_folder)
        info.online = True
        if (self.state == 'running'
            and all(not i.online for i in self.binding_info.values())):
            self.communicator.icon.emit('disabled')
        self.communicator.menu.emit()

    def notify_pending(self, local_folder, n_pending, or_more=False):
        info = self.get_info(local_folder)
        info.online = True
        if (self.state == 'running'
            and any(i.online for i in self.binding_info.values())):
            self.communicator.icon.emit('enabled')
        self.communicator.menu.emit()

    def _setup_systray(self):
        self._tray_icon = QtGui.QSystemTrayIcon()
        self.set_icon('disabled')
        self._tray_icon.show()

    @QtCore.Slot()
    def rebuild_menu(self):
        tray_icon_menu = QtGui.QMenu()
        # TODO: iterate over current binding info to build server specific menu
        # sections
        # TODO: i18n action labels

        for binding_info in self.binding_info.values():
            open_folder = lambda: self.controller.open_local_file(
                binding_info.folder_path)
            open_folder_action = QtGui.QAction(
                binding_info.short_name, tray_icon_menu, triggered=open_folder)
            tray_icon_menu.addAction(open_folder_action)
            tray_icon_menu.addSeparator()

        # TODO: add pause action if in running state
        # TODO: add start action if in paused state
        quit_action = QtGui.QAction("&Quit", tray_icon_menu,
                                    triggered=self.action_quit)
        if self.state == 'quitting':
            quit_action.setEnabled(False)
        tray_icon_menu.addAction(quit_action)
        self._tray_icon.setContextMenu(tray_icon_menu)

    def start_synchronization_thread(self):
        if len(self.controller.list_server_bindings()) == 0:
            if prompt_authentication(
                self.controller, default_nuxeo_drive_folder(), app=self):
                self.communicator.icon.emit('enabled')

        if self.sync_thread is None:
            fault_tolerant = not getattr(self.options, 'stop_on_error', True)
            delay = getattr(self.options, 'delay', 5.0)
            self.sync_thread = Thread(target=self.controller.loop,
                                      kwargs={"frontend": self,
                                              "fault_tolerant": fault_tolerant,
                                              "delay": delay})
            self.sync_thread.start()

    def event(self, event):
        """Handle URL scheme events under OSX"""
        if hasattr(event, 'url'):
            url = event.url().toString()
            info = parse_protocol_url(url)
            if info is not None:
                if info.command == 'edit':
                    # This is a quick operation, no need to fork a QThread
                    self.controller.launch_file_editor(
                        info.server_url, info.repository, info.docref)
        return super(Application, self).event(event)
