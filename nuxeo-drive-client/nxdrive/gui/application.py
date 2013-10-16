"""Main Qt application handling OS events and system tray UI"""

import os
from threading import Thread
from nxdrive.protocol_handler import parse_protocol_url
from nxdrive.logging_config import get_logger
from nxdrive.gui.resources import find_icon
from nxdrive.gui.settings import prompt_settings

log = get_logger(__name__)

# Keep Qt an optional dependency for now
QtGui, QApplication, QObject = None, object, object
try:
    from PyQt4 import QtGui
    from PyQt4 import QtCore
    QApplication = QtGui.QApplication
    QObject = QtCore.QObject
    log.debug("Qt / PyQt4 successfully imported")
except ImportError:
    log.warning("Qt / PyQt4 is not installed: GUI is disabled")
    pass


class Communicator(QObject):
    """Handle communication between sync and main GUI thread

    Use a signal to notify the main thread event loops about states update by
    the synchronization thread.

    """
    # (event name, new icon, rebuild menu)
    icon = QtCore.pyqtSignal(str)
    menu = QtCore.pyqtSignal()
    stop = QtCore.pyqtSignal()
    invalid_credentials = QtCore.pyqtSignal(str)


class BindingInfo(object):
    """Summarize the state of each server connection"""

    online = False
    n_pending = -1
    has_more_pending = False

    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.short_name = os.path.basename(folder_path)

    def get_status_message(self):
        # TODO: i18n
        if self.online:
            if self.n_pending > 0:
                return "%d%s pending operations..." % (
                    self.n_pending, '+' if self.has_more_pending else '')
            elif self.n_pending == 0:
                return "Folder up to date"
            else:
                return "Looking for changes..."
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

        # Put communication channel in place for intra and inter-thread
        # communication for UI change notifications
        self.communicator = Communicator()
        self.communicator.icon.connect(self.set_icon_state)
        self.communicator.menu.connect(self.rebuild_menu)
        self.communicator.stop.connect(self.handle_stop)
        self.communicator.invalid_credentials.connect(
            self.handle_invalid_credentials)

        # This is a windowless application mostly using the system tray
        self.setQuitOnLastWindowClosed(False)
        self.state = 'paused'
        self.quit_on_stop = False
        self.binding_info = {}
        self._setup_systray()
        self.rebuild_menu()

        # Start long running synchronization thread
        self.start_synchronization_thread()

    def get_info(self, local_folder):
        info = self.binding_info.get(local_folder, None)
        if info is None:
            info = BindingInfo(local_folder)
            self.binding_info[local_folder] = info
        return info

    @QtCore.pyqtSlot(str)
    def set_icon_state(self, state):
        """Execute systray icon change operations triggered by state change

        The synchronization thread can update the state info but cannot
        directly call QtGui widget methods. The should be executed by the main
        thread event loop, hence the delegation to this method that is
        triggered by a signal to allow for message passing between the 2
        threads.

        Return True of the icon has changed state.

        """
        if self.get_icon_state() == state:
            # Nothing to update
            return False
        icon = find_icon('nuxeo_drive_systray_icon_%s_18.png' % state)
        if icon is not None:
            self._tray_icon.setIcon(QtGui.QIcon(icon))
        else:
            log.warning('Icon not found: %s', icon)
        self._icon_state = state
        log.debug('Updated icon state to: %s', state)
        return True

    def get_icon_state(self):
        return getattr(self, '_icon_state', None)

    def action_quit(self):
        self.communicator.icon.emit('stopping')
        self.state = 'quitting'
        self.quit_on_stop = True
        self.communicator.menu.emit()
        if self.sync_thread is not None and self.sync_thread.isAlive():
            # Ask the controller to stop: the synchronization loop will in turn
            # call notify_sync_stopped and finally handle_stop
            self.controller.stop()
        else:
            # quit directly
            self.quit()

    @QtCore.pyqtSlot()
    def handle_stop(self):
        if self.quit_on_stop:
            self.quit()

    def update_running_icon(self):
        if self.state != 'running':
            self.communicator.icon.emit('disabled')
            return
        infos = self.binding_info.values()
        if len(infos) > 0 and any(i.online for i in infos):
            self.communicator.icon.emit('enabled')
        else:
            self.communicator.icon.emit('disabled')

    def notify_local_folders(self, local_folders):
        """Cleanup unbound server bindings if any"""
        refresh = False
        for registered_folder in self.binding_info.keys():
            if registered_folder not in local_folders:
                del self.binding_info[registered_folder]
                refresh = True
        for local_folder in local_folders:
            if local_folder not in self.binding_info:
                self.binding_info[local_folder] = BindingInfo(local_folder)
                refresh = True
        if refresh:
            log.debug(u'Detected changes in the list of local folders: %s',
                      u", ".join(local_folders))
            self.communicator.menu.emit()
            self.update_running_icon()

    def get_binding_info(self, local_folder):
        if local_folder not in self.binding_info:
            self.binding_info[local_folder] = BindingInfo(local_folder)
        return self.binding_info[local_folder]

    def notify_sync_started(self):
        log.debug('Synchronization started')
        self.state = 'running'
        self.communicator.menu.emit()
        self.update_running_icon()

    def notify_sync_stopped(self):
        log.debug('Synchronization stopped')
        self.state = 'paused'
        self.sync_thread = None
        self.update_running_icon()
        self.communicator.menu.emit()
        self.communicator.stop.emit()

    def notify_online(self, local_folder):
        info = self.get_info(local_folder)
        if not info.online:
            # Mark binding as offline and update UI
            log.debug('Switching to online mode for: %s', local_folder)
            info.online = True
            self.update_running_icon()
            self.communicator.menu.emit()

    def notify_offline(self, local_folder, exception):
        info = self.get_info(local_folder)
        code = getattr(exception, 'code', None)
        if code is not None:
            reason = "Server returned HTTP code %r" % code
        else:
            reason = str(exception)
        if info.online:
            # Mark binding as offline and update UI
            log.debug('Switching to offline mode (reason: %s) for: %s',
                      reason, local_folder)
            info.online = False
            self.update_running_icon()
            self.communicator.menu.emit()

        if code == 401:
            log.debug('Detected invalid credentials for: %s', local_folder)
            self.communicator.invalid_credentials.emit(local_folder)

    def notify_pending(self, local_folder, n_pending, or_more=False):
        info = self.get_info(local_folder)
        if n_pending != info.n_pending:
            log.debug("%d pending operations for: %s", n_pending, local_folder)
            self.communicator.menu.emit()
        # Update pending stats
        info.n_pending = n_pending
        info.has_more_pending = or_more

        if not info.online:
            log.debug("Switching to online mode for: %s", local_folder)
            # Mark binding as online and update UI
            info.online = True
            self.update_running_icon()
            self.communicator.menu.emit()

    def _setup_systray(self):
        self._tray_icon = QtGui.QSystemTrayIcon()
        self.update_running_icon()
        self._tray_icon.show()

    @QtCore.pyqtSlot(str)
    def handle_invalid_credentials(self, local_folder):
        sb = self.controller.get_server_binding(str(local_folder))
        sb.invalidate_credentials()
        self.controller.get_session().commit()
        self.communicator.menu.emit()

    @QtCore.pyqtSlot()
    def rebuild_menu(self):
        tray_icon_menu = QtGui.QMenu()
        # TODO: i18n action labels
        for sb in self.controller.list_server_bindings():
            # Link to open the server binding folder
            binding_info = self.get_binding_info(sb.local_folder)
            open_folder = lambda: self.controller.open_local_file(
                binding_info.folder_path)
            open_folder_msg = "Open %s folder" % binding_info.short_name
            open_folder_action = QtGui.QAction(
                open_folder_msg, tray_icon_menu, triggered=open_folder)
            tray_icon_menu.addAction(open_folder_action)

            # Pending status
            status_message = binding_info.get_status_message()
            # Need to re-fetch authentication token when expired
            if sb.has_invalid_credentials():
                status_message += " (credentials update required)"
            status_action = tray_icon_menu.addAction(status_message)
            status_action.setEnabled(False)

            tray_icon_menu.addSeparator()

        if not self.controller.list_server_bindings():
            status_action = tray_icon_menu.addAction(
                                "Waiting for server registration")
            status_action.setEnabled(False)
            tray_icon_menu.addSeparator()

        # Settings
        settings_action = QtGui.QAction("Settings",
                                    tray_icon_menu,
                                    triggered=self.settings)
        tray_icon_menu.addAction(settings_action)
        tray_icon_menu.addSeparator()

        # TODO: add pause action if in running state
        # TODO: add start action if in paused state
        quit_action = QtGui.QAction("Quit", tray_icon_menu,
                                    triggered=self.action_quit)
        if self.state == 'quitting':
            quit_action.setEnabled(False)
        tray_icon_menu.addAction(quit_action)
        self._tray_icon.setContextMenu(tray_icon_menu)

    def settings(self):
        sb_settings = self.controller.get_server_binding_settings()
        proxy_settings = self.controller.get_proxy_settings()
        return prompt_settings(self.controller, sb_settings, proxy_settings,
                               app=self)

    def start_synchronization_thread(self):
        if len(self.controller.list_server_bindings()) == 0:
            self.settings()

        if self.sync_thread is None or not self.sync_thread.isAlive():
            delay = getattr(self.options, 'delay', 5.0)
            max_sync_step = getattr(self.options, 'max_sync_step', 10)
            # Controller and its database session pool should be thread safe,
            # hence reuse it directly
            self.controller.synchronizer.register_frontend(self)
            self.controller.synchronizer.delay = delay
            self.controller.synchronizer.max_sync_step = max_sync_step

            self.sync_thread = Thread(target=sync_loop,
                                      args=(self.controller,))
            self.sync_thread.start()

    def event(self, event):
        """Handle URL scheme events under OSX"""
        if hasattr(event, 'url'):
            url = event.url().toString()
            try:
                info = parse_protocol_url(url)
                if info is not None:
                    log.debug("Received nxdrive URL scheme event: %s", url)
                    if info.get('command') == 'edit':
                        # This is a quick operation, no need to fork a QThread
                        self.controller.launch_file_editor(
                            info['server_url'], info['item_id'])
            except:
                log.error("Error handling URL event: %s", url, exc_info=True)
        return super(Application, self).event(event)


def sync_loop(controller, **kwargs):
    """Wrapper to log uncaught exception in the sync thread"""
    try:
        controller.synchronizer.loop(**kwargs)
    except Exception, e:
        log.error("Error in synchronization thread: %s", e, exc_info=True)
