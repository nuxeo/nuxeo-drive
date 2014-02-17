"""Main Qt application handling OS events and system tray UI"""

import os
import time
from nxdrive.synchronizer import SynchronizerThread
from nxdrive.protocol_handler import parse_protocol_url
from nxdrive.logging_config import get_logger
from nxdrive.gui.resources import find_icon
from nxdrive.gui.settings import prompt_settings

log = get_logger(__name__)

TIME_FORMAT_PATTERN = '%d %b %H:%M'

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

    def __init__(self, server_binding, repository='default'):
        self.folder_path = server_binding.local_folder
        self.short_name = os.path.basename(server_binding.local_folder)
        self.server_link = self._get_server_link(server_binding.server_url,
                                                 repository)

    def _get_server_link(self, server_url, repository):
        server_link = server_url
        if not server_link.endswith('/'):
            server_link += '/'
        url_suffix = ('@view_home?tabIds=MAIN_TABS:home,'
                      'USER_CENTER:userCenterNuxeoDrive')
        server_link += 'nxhome/' + repository + url_suffix
        return server_link

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
        self.communicator.menu.connect(self.update_menu)
        self.communicator.stop.connect(self.handle_stop)
        self.communicator.invalid_credentials.connect(
            self.handle_invalid_credentials)

        # Timer to spin the transferring icon
        self.icon_spin_timer = QtCore.QTimer()
        self.icon_spin_timer.timeout.connect(self.spin_transferring_icon)
        self.icon_spin_count = 0

        # This is a windowless application mostly using the system tray
        self.setQuitOnLastWindowClosed(False)
        self.state = 'paused'
        self.quit_on_stop = False
        self._setup_systray()
        self.tray_icon_menu = QtGui.QMenu()
        self.binding_info = {}
        self.binding_menu_actions = {}
        self.global_menu_actions = {}
        self.update_menu()
        self._tray_icon.setContextMenu(self.tray_icon_menu)

        # Start long running synchronization thread
        self.start_synchronization_thread()

    @QtCore.pyqtSlot(str)
    def set_icon_state(self, state):
        """Execute systray icon change operations triggered by state change

        The synchronization thread can update the state info but cannot
        directly call QtGui widget methods. This should be executed by the main
        thread event loop, hence the delegation to this method that is
        triggered by a signal to allow for message passing between the 2
        threads.

        Return True of the icon has changed state.

        """
        if self.get_icon_state() == state:
            # Nothing to update
            return False
        # Handle animated transferring icon
        if state == 'transferring':
            self.icon_spin_timer.start(150)
        else:
            self.icon_spin_timer.stop()
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

    def spin_transferring_icon(self):
        icon = find_icon('nuxeo_drive_systray_icon_transferring_%s.png'
                         % (self.icon_spin_count + 1))
        self._tray_icon.setIcon(QtGui.QIcon(icon))
        self.icon_spin_count = (self.icon_spin_count + 1) % 10

    def action_quit(self):
        self.communicator.icon.emit('stopping')
        self.state = 'stopping'
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
        log.debug('Quitting Nuxeo Drive')
        # Close thread-local Session
        log.debug("Calling Controller.dispose() from Qt Application to close"
                  " thread-local Session")
        self.controller.dispose()
        self.quit()

    def update_running_icon(self):
        if self.state not in ['enabled', 'transferring']:
            self.communicator.icon.emit(self.state)
            return
        infos = self.binding_info.values()
        if len(infos) > 0 and any(i.online for i in infos):
            self.communicator.icon.emit(self.state)
        else:
            self.communicator.icon.emit('disabled')

    def notify_local_folders(self, server_bindings):
        """Cleanup unbound server bindings if any"""
        local_folders = [sb.local_folder for sb in server_bindings]
        refresh = False
        for registered_folder in self.binding_info.keys():
            if registered_folder not in local_folders:
                del self.binding_info[registered_folder]
                refresh = True
        for sb in server_bindings:
            if sb.local_folder not in self.binding_info:
                self.binding_info[sb.local_folder] = BindingInfo(sb)
                refresh = True
        if refresh:
            log.debug(u'Detected changes in the list of local folders: %s',
                      u", ".join(local_folders))
            self.communicator.menu.emit()
            self.update_running_icon()

    def get_binding_info(self, server_binding):
        local_folder = server_binding.local_folder
        if local_folder not in self.binding_info:
            self.binding_info[local_folder] = BindingInfo(server_binding)
        return self.binding_info[local_folder]

    def notify_sync_started(self):
        log.debug('Synchronization started')
        self.state = 'enabled'
        self.communicator.menu.emit()
        self.update_running_icon()

    def notify_sync_stopped(self):
        log.debug('Synchronization stopped')
        self.state = 'paused'
        self.sync_thread = None
        self.update_running_icon()
        self.communicator.menu.emit()
        self.communicator.stop.emit()

    def notify_online(self, server_binding):
        info = self.get_binding_info(server_binding)
        if not info.online:
            # Mark binding as offline and update UI
            log.debug('Switching to online mode for: %s',
                      server_binding.local_folder)
            info.online = True
            self.update_running_icon()
            self.communicator.menu.emit()

    def notify_offline(self, server_binding, exception):
        info = self.get_binding_info(server_binding)
        code = getattr(exception, 'code', None)
        if code is not None:
            reason = "Server returned HTTP code %r" % code
        else:
            reason = str(exception)
        local_folder = server_binding.local_folder
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

    def notify_pending(self, server_binding, n_pending, or_more=False):
        # Update icon
        if n_pending > 0:
            self.state = 'transferring'
        else:
            self.state = 'enabled'
        self.update_running_icon()

        if server_binding is not None:
            local_folder = server_binding.local_folder
            info = self.get_binding_info(server_binding)
            if n_pending != info.n_pending:
                log.debug("%d pending operations for: %s", n_pending,
                          local_folder)
                if n_pending == 0 and info.n_pending > 0:
                    current_time = time.time()
                    log.debug("Updating last ended synchronization date"
                              " to %s for: %s",
                              time.strftime(TIME_FORMAT_PATTERN,
                                            time.localtime(current_time)),
                              local_folder)
                    server_binding.last_ended_sync_date = current_time
                    self.controller.get_session().commit()
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
        self._tray_icon.setToolTip('Nuxeo Drive')
        self.update_running_icon()
        self._tray_icon.show()

    @QtCore.pyqtSlot(str)
    def handle_invalid_credentials(self, local_folder):
        sb = self.controller.get_server_binding(str(local_folder))
        sb.invalidate_credentials()
        self.controller.get_session().commit()
        self.communicator.menu.emit()

    @QtCore.pyqtSlot()
    def update_menu(self):
        # TODO: i18n action labels
        settings_action = self.global_menu_actions.get('settings')

        # Handle global status message
        global_status_action = self.global_menu_actions.get('global_status')
        global_status_sep = self.global_menu_actions.get('global_status_sep')
        if not self.controller.list_server_bindings():
            # Add global status action if needed
            if global_status_action is None:
                global_status_action = QtGui.QAction(
                                            "Waiting for server registration",
                                            self.tray_icon_menu)
                global_status_action.setEnabled(False)
                self._insert_menu_action(global_status_action,
                                         before_action=settings_action)
                self.global_menu_actions['global_status'] = (
                                                        global_status_action)
                global_status_sep = QtGui.QAction(self.tray_icon_menu)
                global_status_sep.setSeparator(True)
                self._insert_menu_action(global_status_sep,
                                         before_action=settings_action)
                self.global_menu_actions['global_status_sep'] = (
                                                        global_status_sep)
        else:
            # Remove global status action from menu and from
            # global menu action cache
            if global_status_action and global_status_sep is not None:
                self.tray_icon_menu.removeAction(global_status_action)
                self.tray_icon_menu.removeAction(global_status_sep)
                del self.global_menu_actions['global_status']
                del self.global_menu_actions['global_status_sep']

        obsolete_binding_local_folders = self.binding_menu_actions.keys()
        # Add or update server binding actions
        for sb in self.controller.list_server_bindings():
            if sb.local_folder in obsolete_binding_local_folders:
                obsolete_binding_local_folders.remove(sb.local_folder)
            binding_info = self.get_binding_info(sb)
            last_ended_sync_date = sb.last_ended_sync_date
            sb_actions = self.binding_menu_actions.get(sb.local_folder)
            if sb_actions is None:
                sb_actions = {}
                # Separator
                binding_separator = QtGui.QAction(self.tray_icon_menu)
                binding_separator.setSeparator(True)
                self._insert_menu_action(binding_separator,
                                         before_action=settings_action)
                sb_actions['separator'] = binding_separator

                # Link to open the server binding folder
                open_folder_msg = ("Open %s folder"
                                   % binding_info.short_name)
                open_folder = (lambda folder_path=binding_info.folder_path:
                               self.controller.open_local_file(
                                                            folder_path))
                open_folder_action = QtGui.QAction(open_folder_msg,
                                                   self.tray_icon_menu)
                self.connect(open_folder_action,
                             QtCore.SIGNAL('triggered()'),
                             open_folder)
                self._insert_menu_action(open_folder_action,
                                         before_action=binding_separator)
                sb_actions['open_folder'] = open_folder_action

                # Link to Nuxeo server
                server_link_msg = "Browse Nuxeo server"
                open_server_link = (
                                lambda server_link=binding_info.server_link:
                                self.controller.open_local_file(server_link))
                server_link_action = QtGui.QAction(server_link_msg,
                                                   self.tray_icon_menu)
                self.connect(server_link_action, QtCore.SIGNAL('triggered()'),
                             open_server_link)
                self._insert_menu_action(server_link_action,
                                         before_action=binding_separator)
                sb_actions['server_link'] = server_link_action

                # Pending status
                status_action = QtGui.QAction(self.tray_icon_menu)
                status_action.setEnabled(False)
                self._set_pending_status(status_action, binding_info, sb)
                self._insert_menu_action(status_action,
                                         before_action=binding_separator)
                sb_actions['pending_status'] = status_action

                # Last synchronization date
                if last_ended_sync_date is not  None:
                    last_ended_sync_action = (
                                        self._insert_last_ended_sync_action(
                                            last_ended_sync_date,
                                            binding_separator))
                    sb_actions['last_ended_sync'] = last_ended_sync_action

                # Cache server binding menu actions
                self.binding_menu_actions[sb.local_folder] = sb_actions
            else:
                # Update pending status
                status_action = sb_actions['pending_status']
                self._set_pending_status(status_action, binding_info, sb)

                # Update last synchronization date
                last_ended_sync_action = sb_actions.get('last_ended_sync')
                if last_ended_sync_action is None:
                    if last_ended_sync_date is not None:
                        last_ended_sync_action = (
                                        self._insert_last_ended_sync_action(
                                            last_ended_sync_date,
                                            sb_actions['separator']))
                        sb_actions['last_ended_sync'] = last_ended_sync_action
                else:
                    if last_ended_sync_date is not None:
                        self._set_last_ended_sync(last_ended_sync_action,
                                                  last_ended_sync_date)

        # Remove obsolete binding actions from menu and from
        # binding menu action cache
        for local_folder in obsolete_binding_local_folders:
            sb_actions = self.binding_menu_actions[local_folder]
            if sb_actions is not None:
                for action_id in sb_actions.keys():
                    self.tray_icon_menu.removeAction(sb_actions[action_id])
                    del sb_actions[action_id]
                del self.binding_menu_actions[local_folder]

        # Settings
        if settings_action is None:
            settings_action = QtGui.QAction("Settings",
                                        self.tray_icon_menu,
                                        triggered=self.settings)
            self.tray_icon_menu.addAction(settings_action)
            self.global_menu_actions['settings'] = settings_action
            self.tray_icon_menu.addSeparator()

        # TODO: add pause action if in running state
        # TODO: add start action if in paused state

        # Quit
        quit_action = self.global_menu_actions.get('quit')
        if quit_action is None:
            quit_action = QtGui.QAction("Quit", self.tray_icon_menu,
                                        triggered=self.action_quit)
            if self.state == 'stopping':
                quit_action.setEnabled(False)
                quit_action.setText('Quitting...')
            self.tray_icon_menu.addAction(quit_action)
            self.global_menu_actions['quit'] = quit_action
        else:
            if self.state == 'stopping':
                quit_action.setEnabled(False)
                quit_action.setText('Quitting...')

    def _insert_menu_action(self, action, before_action=None):
        if before_action is not None:
            self.tray_icon_menu.insertAction(before_action, action)
        else:
            self.tray_icon_menu.addAction(action)
        return action

    def _insert_last_ended_sync_action(self, last_ended_sync_date,
                                       before_action):
        last_ended_sync_action = QtGui.QAction(self.tray_icon_menu)
        last_ended_sync_action.setEnabled(False)
        self._set_last_ended_sync(last_ended_sync_action, last_ended_sync_date)
        self._insert_menu_action(last_ended_sync_action,
                                 before_action=before_action)
        return last_ended_sync_action

    def _set_pending_status(self, status_action, binding_info, server_binding):
        status_message = binding_info.get_status_message()
        # Need to re-fetch authentication token when expired
        if server_binding.has_invalid_credentials():
            status_message += " (credentials update required)"
        status_action.setText(status_message)

    def _set_last_ended_sync(self, last_ended_sync_action,
                             last_ended_sync_date):
        last_ended_sync_message = "Last synchronized: %s" % (
                                    time.strftime(TIME_FORMAT_PATTERN,
                                    time.localtime(last_ended_sync_date)))
        last_ended_sync_action.setText(last_ended_sync_message)

    def settings(self):
        sb_settings = self.controller.get_server_binding_settings()
        proxy_settings = self.controller.get_proxy_settings()
        version = self.controller.get_version()
        return prompt_settings(self.controller, sb_settings, proxy_settings,
                               version, app=self)

    def start_synchronization_thread(self):
        if self.controller.is_credentials_update_required():
            self.settings()

        if self.sync_thread is None or not self.sync_thread.isAlive():
            delay = getattr(self.options, 'delay', 5.0)
            max_sync_step = getattr(self.options, 'max_sync_step', 10)
            # Controller and its database session pool are thread safe,
            # hence reuse it directly
            self.controller.synchronizer.register_frontend(self)
            self.controller.synchronizer.delay = delay
            self.controller.synchronizer.max_sync_step = max_sync_step

            self.sync_thread = SynchronizerThread(self.controller)
            log.info("Starting new synchronization Thread: %r"
                   % self.sync_thread)
            self.sync_thread.start()

    def event(self, event):
        """Handle URL scheme events under OSX"""
        log.trace("Received Qt application event")
        if hasattr(event, 'url'):
            url = str(event.url().toString())
            log.debug("Event URL: %s", url)
            try:
                info = parse_protocol_url(url)
                log.debug("URL info: %r", info)
                if info is not None:
                    log.debug("Received nxdrive URL scheme event: %s", url)
                    if info.get('command') == 'edit':
                        # This is a quick operation, no need to fork a QThread
                        self.controller.launch_file_editor(
                            info['server_url'], info['item_id'])
            except:
                log.error("Error handling URL event: %s", url, exc_info=True)
        return super(Application, self).event(event)
