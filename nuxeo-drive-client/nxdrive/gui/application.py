"""Main Qt application handling OS events and system tray UI"""

import os
import time
import sys
from nxdrive.synchronizer import SynchronizerThread
from nxdrive.protocol_handler import parse_protocol_url
from nxdrive.logging_config import get_logger
from nxdrive.gui.resources import find_icon
from nxdrive.gui.settings import prompt_settings
from nxdrive.gui.update_prompt import prompt_update
from nxdrive.gui.updated import notify_updated

from nxdrive.updater import AppUpdater
from nxdrive.updater import UPDATE_STATUS_UPGRADE_NEEDED
from nxdrive.updater import UPDATE_STATUS_DOWNGRADE_NEEDED
from nxdrive.updater import UPDATE_STATUS_UPDATE_AVAILABLE
from nxdrive.updater import UPDATE_STATUS_UP_TO_DATE
from nxdrive.updater import UPDATE_STATUS_UNAVAILABLE_SITE
from nxdrive.updater import UPDATE_STATUS_MISSING_INFO
from nxdrive.updater import UPDATE_STATUS_MISSING_VERSION

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
    update_check = QtCore.pyqtSignal()


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
        self.communicator.update_check.connect(
            self.refresh_update_status)

        # Timer to spin the transferring icon
        self.icon_spin_timer = QtCore.QTimer()
        self.icon_spin_timer.timeout.connect(self.spin_transferring_icon)
        self.icon_spin_count = 0

        # This is a windowless application mostly using the system tray
        self.setQuitOnLastWindowClosed(False)
        # Current state
        self.state = 'disabled'
        # Last state before suspend
        self.last_state = 'enabled'

        # Application update
        self.updater = None
        self.update_status = None
        self.update_version = None
        self.restart_updated_app = False
        self.quit_app_after_sync_stopped = True

        # Systray menu
        self._setup_systray()
        self.tray_icon_menu = QtGui.QMenu()
        self.binding_info = {}
        self.binding_menu_actions = {}
        self.global_menu_actions = {}
        self.update_menu()
        self._tray_icon.setContextMenu(self.tray_icon_menu)

        # Application update notification
        if self.controller.is_updated():
            notify_updated(self.controller.get_version())

        if self.controller.is_credentials_update_required():
            # Prompt for settings if needed (performs a check for application
            # update)
            self.settings()
        else:
            # Initial check for application update (then periodic checks will
            # be done by the synchronizer thread)
            self.refresh_update_status()
            # Start long running synchronization thread
            self.start_synchronization_thread()

    def refresh_update_status(self):
        # TODO: first read update site URL from local configuration
        # See https://jira.nuxeo.com/browse/NXP-14403
        server_bindings = self.controller.list_server_bindings()
        if not server_bindings:
            log.warning("Found no server binding, thus no update site URL,"
                        " can't check for application update")
        elif self.state != 'paused':
            # Let's refresh_update_info of the first server binding
            sb = server_bindings[0]
            self.controller.refresh_update_info(sb.local_folder)
            # Use server binding's update site URL as a version finder to
            # build / update the application updater.
            update_url = sb.update_url
            server_version = sb.server_version
            if self.updater is None:
                # Build application updater if it doesn't exist
                try:
                    self.updater = AppUpdater(version_finder=update_url)
                except Exception as e:
                    log.warning(e)
                    return
            else:
                # If application updater exists, simply update its version
                # finder
                self.updater.set_version_finder(update_url)
            # Set update status and update version
            self.update_status, self.update_version = (
                        self.updater.get_update_status(
                            self.controller.get_version(), server_version))
            if self.update_status == UPDATE_STATUS_UNAVAILABLE_SITE:
                # Update site unavailable
                log.warning("Update site is unavailable, as a consequence"
                            " update features won't be available")
            elif self.update_status in [UPDATE_STATUS_MISSING_INFO,
                                      UPDATE_STATUS_MISSING_VERSION]:
                # Information or version missing in update site
                log.warning("Some information or version file is missing in"
                            " the update site, as a consequence update"
                            " features won't be available")
            else:
                # Update information successfully fetched
                log.info("Fetched information from update site %s: update"
                         " status = '%s', update version = '%s'",
                         self.updater.get_update_site(), self.update_status,
                         self.update_version)
                if self._is_update_required():
                    # Current client version not compatible with server
                    # version, upgrade or downgrade needed.
                    # Let's stop synchronization thread.
                    log.info("As current client version is not compatible with"
                             " server version, an upgrade or downgrade is"
                             " needed. Synchronization thread won't start"
                             " until then.")
                    self.stop_sync_thread()
                elif (self._is_update_available()
                      and self.controller.is_auto_update()):
                    # Update available and auto-update checked, let's process
                    # update
                    log.info("An application update is available and"
                             " auto-update is checked")
                    self.action_update(auto_update=True)
                    return
                elif (self._is_update_available()
                      and not self.controller.is_auto_update()):
                    # Update available and auto-update not checked, let's just
                    # update the systray icon and menu and let the user
                    # explicitly choose to  update
                    log.info("An update is available and auto-update is not"
                             " checked, let's just update the systray icon and"
                             " menu and let the user explicitly choose to"
                             " update")
                else:
                    # Application is up-to-date
                    log.info("Application is up-to-date")
            self.state = self._get_current_active_state()
            self.update_running_icon()
            self.communicator.menu.emit()

    def _is_update_required(self):
        return self.update_status in [UPDATE_STATUS_UPGRADE_NEEDED,
                                      UPDATE_STATUS_DOWNGRADE_NEEDED]

    def _is_update_available(self):
        return self.update_status == UPDATE_STATUS_UPDATE_AVAILABLE

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

    def suspend_resume(self):
        if self.state != 'paused':
            # Suspend sync
            if self._is_sync_thread_started():
                # A sync thread is active, first update last state, current
                # state, icon and menu.
                self.last_state = self.state
                # If sync thread is asleep (waiting for next sync batch) set
                # current state to 'paused' directly, else set current state
                # to 'suspending' waiting for feedback from sync thread.
                if self.state == 'asleep':
                    self.state = 'paused'
                else:
                    self.state = 'suspending'
                self.update_running_icon()
                self.communicator.menu.emit()
                # Suspend the synchronizer thread: it will call
                # notify_sync_suspended() then wait until it gets notified by
                # a call to resume().
                self.sync_thread.suspend()
            else:
                log.debug('No active synchronization thread, suspending sync'
                          ' has no effect, keeping current state: %s',
                          self.state)
        else:
            # Update state, icon and menu
            self.state = self.last_state
            self.update_running_icon()
            self.communicator.menu.emit()
            # Resume sync
            self.sync_thread.resume()

    def action_quit(self):
        self.quit_app_after_sync_stopped = True
        self.restart_updated_app = False
        self._stop()

    def action_update(self, auto_update=False):
        if auto_update:
            update = self.updater.update(self.update_version)
        else:
            update = prompt_update(self._is_update_required(),
                               self.controller.get_version(),
                               self.update_version, self.updater)
        if update:
            log.info("Will quit Nuxeo Drive and restart updated version %s",
                     self.update_version)
            self.quit_app_after_sync_stopped = True
            self.restart_updated_app = True
            self._stop()

    def stop_sync_thread(self):
        self.quit_app_after_sync_stopped = False
        self._stop()

    def _stop(self):
        if self._is_sync_thread_started():
            # A sync thread is active, first update state, icon and menu
            if self.quit_app_after_sync_stopped:
                self.state = 'stopping'
                self.update_running_icon()
                self.communicator.menu.emit()
            # Ask the controller to stop: the synchronization loop will break
            # and call notify_sync_stopped() which will finally emit a signal
            # to handle_stop() to quit the application.
            self.controller.stop()
            # Notify synchronization thread in case it was suspended
            self.sync_thread.resume()
        else:
            # Quit directly
            self.handle_stop()

    @QtCore.pyqtSlot()
    def handle_stop(self):
        if self.quit_app_after_sync_stopped:
            log.info('Quitting Nuxeo Drive')
            # Close thread-local Session
            log.debug("Calling Controller.dispose() from Qt Application to"
                      " close thread-local Session")
            self.controller.dispose()
            if self.restart_updated_app:
                # Restart application by loading updated executable into
                # current process
                log.debug("Exiting Qt application")
                self.quit()
                self.deleteLater()

                current_version = self.updater.get_active_version()
                updated_version = self.update_version
                log.info("Current application version: %s", current_version)
                log.info("Updated application version: %s", updated_version)

                executable = sys.executable
                log.info("Current executable is: %s", executable)
                updated_executable = executable.replace(current_version,
                                                        updated_version)
                log.info("Updated executable is: %s", updated_executable)

                args = [updated_executable]
                args.extend(sys.argv[1:])
                log.info("Loading updated executable into current process"
                          " with args: %r", args)
                os.execl(updated_executable, *args)
            else:
                self.quit()

    def update_running_icon(self):
        if self.state not in ['enabled', 'update_available', 'transferring']:
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
            self.update_running_icon()
            self.communicator.menu.emit()

    def get_binding_info(self, server_binding):
        local_folder = server_binding.local_folder
        if local_folder not in self.binding_info:
            self.binding_info[local_folder] = BindingInfo(server_binding)
        return self.binding_info[local_folder]

    def notify_sync_started(self):
        log.debug('Synchronization started')
        # Update state, icon and menu
        self.state = self._get_current_active_state()
        self.update_running_icon()
        self.communicator.menu.emit()

    def notify_sync_stopped(self):
        log.debug('Synchronization stopped')
        self.sync_thread = None
        # Send stop signal
        self.communicator.stop.emit()

    def notify_sync_asleep(self):
        # Update state to 'asleep' when sync thread is going to sleep
        # (waiting for next sync batch)
        self.state = 'asleep'

    def notify_sync_woken_up(self):
        # Update state to current active state when sync thread is woken up and
        # was not suspended
        if self.state != 'paused':
            self.state = self._get_current_active_state()
        else:
            self.last_state = self._get_current_active_state()

    def notify_sync_suspended(self):
        log.debug('Synchronization suspended')
        # Update state, icon and menu
        self.state = 'paused'
        self.update_running_icon()
        self.communicator.menu.emit()

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
            self.state = 'disabled'
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
            self.state = self._get_current_active_state()
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

    def notify_check_update(self):
        log.debug('Checking for application update')
        self.communicator.update_check.emit()

    def _get_current_active_state(self):
        if self._is_update_available():
            return 'update_available'
        elif self._is_update_required():
            return 'disabled'
        elif self.state == 'paused':
            return 'paused'
        else:
            return 'enabled'

    def _setup_systray(self):
        self._tray_icon = QtGui.QSystemTrayIcon()
        self._tray_icon.setToolTip('Nuxeo Drive')
        self.update_running_icon()
        self._tray_icon.show()

    @QtCore.pyqtSlot(str)
    def handle_invalid_credentials(self, local_folder):
        sb = self.controller.get_server_binding(unicode(local_folder))
        sb.invalidate_credentials()
        self.controller.get_session().commit()
        self.communicator.menu.emit()

    @QtCore.pyqtSlot()
    def update_menu(self):
        # TODO: i18n action labels

        server_bindings = self.controller.list_server_bindings()
        # Global actions
        global_status_action = self.global_menu_actions.get('global_status')
        global_status_sep = self.global_menu_actions.get('global_status_sep')
        settings_action = self.global_menu_actions.get('settings')
        suspend_resume_action = self.global_menu_actions.get('suspend_resume')
        quit_action = self.global_menu_actions.get('quit')
        update_action = self.global_menu_actions.get('update')

        # Handle global status message
        if not server_bindings:
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
        for sb in server_bindings:
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

        # Update
        if update_action is None:
            if (self.update_status is not None and self.updater is not None
                and self.update_status != UPDATE_STATUS_UP_TO_DATE):
                update_label = self.updater.get_update_label(
                                                            self.update_status)
                # TODO if possible: set text color to #FC8700 (same as icon)
                update_action = QtGui.QAction(update_label,
                                              self.tray_icon_menu,
                                              triggered=self.action_update)
                if self.update_status in [UPDATE_STATUS_UNAVAILABLE_SITE,
                                          UPDATE_STATUS_MISSING_INFO,
                                          UPDATE_STATUS_MISSING_VERSION]:
                    update_action.setEnabled(False)
                self._insert_menu_action(update_action,
                                             before_action=quit_action)
                self.global_menu_actions['update'] = update_action
                # Disable suspend_resume action if needed
                if (self._is_update_required()
                    and suspend_resume_action is not None):
                    suspend_resume_action.setEnabled(False)
        else:
            if (self.update_status is not None
                and self.update_status != UPDATE_STATUS_UP_TO_DATE):
                # Update update action label
                update_label = self.updater.get_update_label(
                                                            self.update_status)
                update_action.setText(update_label)
                if self.update_status in [UPDATE_STATUS_UNAVAILABLE_SITE,
                                          UPDATE_STATUS_MISSING_INFO,
                                          UPDATE_STATUS_MISSING_VERSION]:
                    update_action.setEnabled(False)
                else:
                    update_action.setEnabled(True)
                # Disable suspend_resume action if needed
                if (self._is_update_required()
                    and suspend_resume_action is not None):
                    suspend_resume_action.setEnabled(False)
            else:
                # Remove update action from menu and from global menu action
                # cache
                self.tray_icon_menu.removeAction(update_action)
                del self.global_menu_actions['update']

        # Suspend / resume
        if server_bindings:
            if suspend_resume_action is None:
                suspend_resume_action = QtGui.QAction(
                                        "Suspend synchronization",
                                        self.tray_icon_menu,
                                        triggered=self.suspend_resume)
                self._insert_menu_action(suspend_resume_action,
                                         before_action=settings_action)
                self.global_menu_actions['suspend_resume'] = (
                                                        suspend_resume_action)
            else:
                if self.state == 'suspending':
                    suspend_resume_action.setText(
                                            'Suspending synchronization...')
                    # Disable suspend_resume, update and quit actions when
                    # suspending
                    suspend_resume_action.setEnabled(False)
                    if quit_action is not None:
                        quit_action.setEnabled(False)
                    if update_action is not None:
                        update_action.setEnabled(False)
                elif self.state == 'paused':
                    suspend_resume_action.setText('Resume synchronization')
                    # Enable suspend_resume and quit actions when paused
                    suspend_resume_action.setEnabled(True)
                    if quit_action is not None:
                        quit_action.setEnabled(True)
                    # Disable update action when paused
                    if update_action is not None:
                        update_action.setEnabled(False)
                else:
                    suspend_resume_action.setText('Suspend synchronization')

        # Quit
        if quit_action is None:
            quit_action = QtGui.QAction("Quit", self.tray_icon_menu,
                                        triggered=self.action_quit)
            self.tray_icon_menu.addAction(quit_action)
            self.global_menu_actions['quit'] = quit_action
        else:
            if self.state == 'stopping':
                quit_action.setText('Quitting...')
                # Disable quit, suspend_resume and update actions when quitting
                quit_action.setEnabled(False)
                if suspend_resume_action is not None:
                    suspend_resume_action.setEnabled(False)
                if update_action is not None:
                    update_action.setEnabled(False)

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
        general_settings = self.controller.get_general_settings()
        version = self.controller.get_version()
        settings_accepted = prompt_settings(self.controller, sb_settings,
                                            proxy_settings, general_settings,
                                            version)
        if settings_accepted:
            # Check for application udpate
            self.refresh_update_status()
            # Start synchronization thread if needed
            self.start_synchronization_thread()
        return settings_accepted

    def start_synchronization_thread(self):
        # Make sure an application update is not required and synchronization
        # thread is not already started before actually starting it
        if (not self._is_update_required()
            and not self._is_sync_thread_started()):
            delay = getattr(self.options, 'delay', 5.0)
            max_sync_step = getattr(self.options, 'max_sync_step', 10)
            update_check_delay = getattr(self.options, 'update_check_delay',
                                         3600)
            # Controller and its database session pool are thread safe,
            # hence reuse it directly
            self.controller.synchronizer.register_frontend(self)
            self.controller.synchronizer.delay = delay
            self.controller.synchronizer.max_sync_step = max_sync_step
            self.controller.synchronizer.update_check_delay = (
                                                update_check_delay)

            self.sync_thread = SynchronizerThread(self.controller)
            log.info("Starting new synchronization thread %r",
                     self.sync_thread)
            self.sync_thread.start()
            log.info("Synchronization thread %r started", self.sync_thread)

    def _is_sync_thread_started(self):
        return self.sync_thread is not None and self.sync_thread.isAlive()

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
