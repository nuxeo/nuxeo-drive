"""Main Qt application handling OS events and system tray UI"""

import os
import time
import sys
import subprocess
from nxdrive.osi.protocol import parse_protocol_url
from nxdrive.logging_config import get_logger
from nxdrive.engine.activity import Action, FileAction
from nxdrive.gui.resources import find_icon
from nxdrive.gui.update_prompt import prompt_update
from nxdrive.gui.updated import notify_updated
from nxdrive.updater import AppUpdater
from nxdrive.updater import UPDATE_STATUS_UPGRADE_NEEDED
from nxdrive.updater import UPDATE_STATUS_DOWNGRADE_NEEDED
from nxdrive.updater import UPDATE_STATUS_UPDATE_AVAILABLE
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

    def __init__(self, controller, options, argv=()):
        super(Application, self).__init__(list(argv))
        self.manager = controller
        self.options = options
        self.mainEngine = None
        for _, engine in self.manager.get_engines().iteritems():
            self.mainEngine = engine
            break
        if self.mainEngine is not None and options.debug:
            from nxdrive.engine.engine import EngineLogger
            self.engineLogger = EngineLogger(self.mainEngine)
        self.binding_info = {}
        self.engineWidget = None

        # Timer to spin the transferring icon
        self.icon_spin_timer = QtCore.QTimer()
        self.icon_spin_timer.timeout.connect(self.spin_transferring_icon)
        self.icon_spin_count = 0

        # Application update
        self.updater = None
        self.update_status = None
        self.update_version = None
        self.restart_updated_app = False

        # This is a windowless application mostly using the system tray
        self.setQuitOnLastWindowClosed(False)
        # Current state
        self.state = 'disabled'
        # Last state before suspend
        self.last_state = 'enabled'

        self.setup_systray()

        # Update systray every xs

        # Application update notification
        if self.manager.is_updated():
            notify_updated(self.manager.get_version())

        # Check if actions is required, separate method so it can be override
        self.init_checks()
        self.engineWidget = None

    @QtCore.pyqtSlot()
    def change_systray_icon(self):
        syncing = False
        engines = self.manager.get_engines()
        for _, engine in engines.iteritems():
            syncing = syncing | engine.is_syncing()
        new_state = "asleep"
        if len(engines) == 0:
            new_state = "disabled"
        if syncing:
            new_state = 'transferring'
        self.set_icon_state(new_state)

    @QtCore.pyqtSlot()
    def show_settings(self, section="Accounts"):
        from nxdrive.wui.settings import WebSettingsDialog
        self.webSettingsDialog = WebSettingsDialog(self, section)
        self.webSettingsDialog.show()

    def show_file_status(self):
        from nxdrive.gui.status_dialog import StatusDialog
        for _, engine in self.manager.get_engines().iteritems():
            self.statusDialog = StatusDialog(engine.get_dao())
            self.statusDialog.show()
            return

    def show_activities(self):
        from nxdrive.wui.activity import WebActivityDialog
        self.webEngineWidget = WebActivityDialog(self)
        self.webEngineWidget.show()

    @QtCore.pyqtSlot(object)
    def _connect_engine(self, engine):
        engine.syncStarted.connect(self.change_systray_icon)
        engine.syncCompleted.connect(self.change_systray_icon)

    def init_checks(self):
        if self.manager.is_debug():
            from nxdrive.debug.wui.engine import EngineDialog
            self.debug_windows = EngineDialog(self)
            self.debug_windows.show()
        for _, engine in self.manager.get_engines().iteritems():
            self._connect_engine(engine)
        self.manager.newEngine.connect(self._connect_engine)
        if self.manager.is_credentials_update_required():
            # Prompt for settings if needed (performs a check for application
            # update)
            self.show_settings()
        else:
            # Initial check for application update (then periodic checks will
            # be done by the synchronizer thread)
            self.refresh_update_status()
            # Start long running synchronization thread
            self.manager.start()

    def get_systray_menu(self):
        from nxdrive.wui.systray import WebSystray
        return WebSystray(self, self._tray_icon)

    def get_version_finder(self, update_url):
        # Used by extended application to inject version finder
        return update_url

    def get_updater(self, version_finder):
        # Enable the capacity to extend the AppUpdater
        return AppUpdater(version_finder)

    def refresh_update_status(self):
        # TODO: first read update site URL from local configuration
        # See https://jira.nuxeo.com/browse/NXP-14403
        server_bindings = self.manager.list_server_bindings()
        if not server_bindings:
            log.warning("Found no server binding, thus no update site URL,"
                        " can't check for application update")
        elif self.state != 'paused':
            # Let's refresh_update_info of the first server binding
            sb = server_bindings[0]
            self.manager.refresh_update_info(sb.local_folder)
            # Use server binding's update site URL as a version finder to
            # build / update the application updater.
            update_url = sb.update_url
            server_version = sb.server_version
            if update_url is None or server_version is None:
                log.warning("Update site URL or server version unavailable,"
                            " as a consequence update features won't be"
                            " available")
                return
            if self.updater is None:
                # Build application updater if it doesn't exist
                try:
                    self.updater = self.get_updater(
                                        self.get_version_finder(update_url))
                except Exception as e:
                    log.warning(e)
                    return
            else:
                # If application updater exists, simply update its version
                # finder
                self.updater.set_version_finder(
                                        self.get_version_finder(update_url))
            # Set update status and update version
            self.update_status, self.update_version = (
                        self.updater.get_update_status(
                            self.manager.get_version(), server_version))
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
                    self.manager.stop()
                elif (self._is_update_available()
                      and self.manager.is_auto_update()):
                    # Update available and auto-update checked, let's process
                    # update
                    log.info("An application update is available and"
                             " auto-update is checked")
                    self.action_update(auto_update=True)
                    return
                elif (self._is_update_available()
                      and not self.manager.is_auto_update()):
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
        self._tray_icon.setToolTip(self.get_tooltip())
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

    def update_tooltip(self):
        # Update also the file
        self._tray_icon.setToolTip(self.get_tooltip())

    def get_default_tooltip(self):
        return "Nuxeo Drive"

    def get_tooltip(self):
        actions = Action.get_actions()
        if actions is None or len(actions) == 0:
            return self.get_default_tooltip()
        # Display only the first action for now
        # TODO Get all actions ? or just file action
        action = actions.itervalues().next()
        if action is None:
            return self.get_default_tooltip()
        if isinstance(action, FileAction):
            if action.get_percent() is not None:
                return ("%s - %s - %s - %d%%" %
                                    (self.get_default_tooltip(),
                                    action.type, action.filename,
                                    action.get_percent()))
            else:
                return ("%s - %s - %s" % (self.get_default_tooltip(),
                                    action.type, action.filename))
        elif action.get_percent() is not None:
            return ("%s - %s - %d%%" % (self.get_default_tooltip(),
                                    action.type,
                                    action.get_percent()))
        else:
            return ("%s - %s" % (self.get_default_tooltip(),
                                    action.type))

    def suspend_resume(self):
        if self.state != 'paused':
            # Suspend sync
            if self.manager.is_started():
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
                # Suspend the synchronizer thread: it will call
                # notify_sync_suspended() then wait until it gets notified by
                # a call to resume().
                self.manager.suspend()
            else:
                self.state = 'paused'
                log.debug('No active synchronization thread, suspending sync'
                          ' has no effect, keeping current state: %s',
                          self.state)
        else:
            # Update state, icon and menu
            self.state = self.last_state
            self.update_running_icon()
            # Resume sync
            self.manager.resume()

    def action_update(self, auto_update=False):
        updated = False
        if auto_update:
            try:
                updated = self.updater.update(self.update_version)
            except Exception as e:
                log.error(e, exc_info=True)
                log.warning("An error occurred while trying to automatically"
                            " update Nuxeo Drive to version %s, setting"
                            " 'Auto update' to False", self.update_version)
                self.manager.set_auto_update(False)
        else:
            updated = prompt_update(self.manager,
                                    self._is_update_required(),
                                    self.manager.get_version(),
                                    self.update_version, self.updater)
        if updated:
            log.info("Will quit Nuxeo Drive and restart updated version %s",
                     self.update_version)
            self.quit_app_after_sync_stopped = True
            self.restart_updated_app = True
            self._stop()

    def _stop(self):
        if self.manager.is_started():
            # A sync thread is active, first update state, icon and menu
            if self.quit_app_after_sync_stopped:
                self.state = 'stopping'
                self.update_running_icon()
                self.communicator.menu.emit()
            # Stop the thread
            self.manager.stop()
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
            self.manager.dispose()
            if self.restart_updated_app:
                # Restart application by loading updated executable into
                # current process
                log.debug("Exiting Qt application")
                self.quit()

                current_version = self.updater.get_active_version()
                updated_version = self.update_version
                log.info("Current application version: %s", current_version)
                log.info("Updated application version: %s", updated_version)

                executable = sys.executable
                # TODO NXP-13818: better handle this!
                if sys.platform == 'darwin':
                    executable = executable.replace('python',
                                                    self.get_mac_app())
                log.info("Current executable is: %s", executable)
                updated_executable = executable.replace(current_version,
                                                        updated_version)
                log.info("Updated executable is: %s", updated_executable)

                args = [updated_executable]
                args.extend(sys.argv[1:])
                log.info("Opening subprocess with args: %r", args)
                subprocess.Popen(args)
            else:
                self.quit()

    def get_mac_app(self):
        return 'ndrive'

    def update_running_icon(self):
        # TODO Define is direct call to set_icon_state
        if self.state not in ['enabled', 'update_available', 'transferring']:
            self.set_icon_state(self.state)
            return
        infos = self.binding_info.values()
        if len(infos) > 0 and any(i.online for i in infos):
            self.set_icon_state(self.state)
        else:
            self.set_icon_state("disabled")

    def notify_change(self, doc_pair, old_state):
        self.communicator.change.emit(doc_pair, old_state)

    def handle_change(self, doc_pair, old_state):
        pass

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
                    self.manager.get_session().commit()
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

    def setup_systray(self):
        self._tray_icon = QtGui.QSystemTrayIcon()
        self._tray_icon.setToolTip('Nuxeo Drive')
        self.update_running_icon()
        self._tray_icon.show()
        self.tray_icon_menu = self.get_systray_menu()
        self._tray_icon.setContextMenu(self.tray_icon_menu)

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
                    if info.get('command') == 'download_edit':
                        # This is a quick operation, no need to fork a QThread
                        self.manager.download_edit(
                            info['server_url'], info['repo'], info['doc_id'],
                            info['filename'])
                    elif info.get('command') == 'edit':
                        self.manager.edit(
                            info['server_url'], info['item_id'])
            except:
                log.error("Error handling URL event: %s", url, exc_info=True)
        return super(Application, self).event(event)
