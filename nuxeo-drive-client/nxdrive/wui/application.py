"""Main Qt application handling OS events and system tray UI"""

import os
import sys
import subprocess
from nxdrive.client.common import DEFAULT_REPOSITORY_NAME
from nxdrive.osi import parse_protocol_url
from nxdrive.logging_config import get_logger
from nxdrive.engine.activity import Action, FileAction
from nxdrive.gui.resources import find_icon
from nxdrive.utils import find_resource_dir
from nxdrive.wui.translator import Translator
from nxdrive.wui.systray import DriveSystrayIcon
from nxdrive.osi import AbstractOSIntegration
from nxdrive.notification import Notification
from nxdrive.wui.modal import WebModal

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

    def __init__(self, server_binding, repository=DEFAULT_REPOSITORY_NAME):
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


class SimpleApplication(QApplication):
    """ Simple application with html and translator
    """
    def __init__(self, manager, options, argv=()):
        super(SimpleApplication, self).__init__(list(argv))
        self.options = options
        self.manager = manager
        self.setApplicationName(manager.get_appname())
        # Init translator
        self._init_translator()

    def translate(self, message, values=None):
        return Translator.get(message, values)

    def _get_skin(self):
        return 'ui5'

    def get_osi(self):
        return self.manager.get_osi()

    def _init_translator(self):
        if (self.options is not None):
            default_locale = self.options.locale
        else:
            default_locale = 'en'
        from nxdrive.wui.translator import Translator
        Translator(self.manager, self.get_htmlpage('i18n.js'),
                        self.manager.get_config("locale", default_locale))

    def get_htmlpage(self, page):
        import nxdrive
        nxdrive_path = os.path.dirname(nxdrive.__file__)
        ui_path = os.path.join(nxdrive_path, 'data', self._get_skin())
        return os.path.join(find_resource_dir(self._get_skin(), ui_path), page).replace("\\","/")

    def get_window_icon(self):
        return find_icon('nuxeo_drive_icon_64.png')

    def get_cache_folder(self):
        return os.path.join(self.manager.get_configuration_folder(), "cache", "wui")


class Application(SimpleApplication):
    """Main Nuxeo drive application controlled by a system tray icon + menu"""

    def __init__(self, manager, options, argv=()):
        super(Application, self).__init__(manager, options, list(argv))
        self.setQuitOnLastWindowClosed(False)
        self._delegator = None
        from nxdrive.scripting import DriveUiScript
        self.manager.set_script_object(DriveUiScript(manager, self))
        self.mainEngine = None
        self.filters_dlg = None
        self._conflicts_modals = dict()
        self.current_notification = None
        # Make dialog unique
        self.uniqueDialogs = dict()

        for _, engine in self.manager.get_engines().iteritems():
            self.mainEngine = engine
            break
        if self.mainEngine is not None and options.debug:
            from nxdrive.engine.engine import EngineLogger
            self.engineLogger = EngineLogger(self.mainEngine)
        self.engineWidget = None

        self.aboutToQuit.connect(self.manager.stop)
        self.manager.dropEngine.connect(self.dropped_engine)

        # Timer to spin the transferring icon
        self.icon_spin_timer = QtCore.QTimer()
        self.icon_spin_timer.timeout.connect(self.spin_transferring_icon)
        self.icon_spin_count = 0

        # Application update
        self.manager.get_updater().appUpdated.connect(self.app_updated)
        self.updated_version = None

        # This is a windowless application mostly using the system tray
        self.setQuitOnLastWindowClosed(False)

        self.setup_systray()

        # Direct Edit conflict
        self.manager.get_drive_edit().driveEditConflict.connect(self._direct_edit_conflict)

        # Check if actions is required, separate method so it can be override
        self.init_checks()
        self.engineWidget = None

        # Setup notification center for Mac
        if AbstractOSIntegration.is_mac():
            if AbstractOSIntegration.os_version_above("10.8"):
                self._setup_notification_center()

    @QtCore.pyqtSlot(str, str, str)
    def _direct_edit_conflict(self, filename, ref, digest):
        try:
            log.trace('Entering _direct_edit_conflict for %r / %r', filename, ref)
            filename = unicode(filename)
            log.trace('Unicode filename: %r', filename)
            if filename in self._conflicts_modals:
                log.trace('Filename already in _conflicts_modals: %r', filename)
                return
            log.trace('Putting filename in _conflicts_modals: %r', filename)
            self._conflicts_modals[filename] = True
            info = dict()
            info["name"] = filename
            dlg = WebModal(self, Translator.get("DIRECT_EDIT_CONFLICT_MESSAGE", info))
            dlg.add_button("OVERWRITE", Translator.get("DIRECT_EDIT_CONFLICT_OVERWRITE"))
            dlg.add_button("CANCEL", Translator.get("DIRECT_EDIT_CONFLICT_CANCEL"))
            res = dlg.exec_()
            if res == "OVERWRITE":
                self.manager.get_drive_edit().force_update(unicode(ref), unicode(digest))
            del self._conflicts_modals[filename]
        except Exception:
            log.exception('Error while displaying Direct Edit conflict modal dialog for %r', filename)

    @QtCore.pyqtSlot()
    def _root_deleted(self):
        engine = self.sender()
        info = dict()
        log.debug("Root has been deleted for engine: %s", engine.get_uid())
        info["folder"] = engine.get_local_folder()
        dlg = WebModal(self, Translator.get("DRIVE_ROOT_DELETED", info))
        dlg.add_button("RECREATE", Translator.get("DRIVE_ROOT_RECREATE"), style="primary")
        dlg.add_button("DISCONNECT", Translator.get("DRIVE_ROOT_DISCONNECT"), style="danger")
        res = dlg.exec_()
        if res == "DISCONNECT":
            self.manager.unbind_engine(engine.get_uid())
        elif res == "RECREATE":
            engine.reinit()
            engine.start()

    @QtCore.pyqtSlot(str)
    def _root_moved(self, new_path):
        engine = self.sender()
        info = dict()
        log.debug("Root has been moved for engine: %s to '%s'", engine.get_uid(), new_path)
        info["folder"] = engine.get_local_folder()
        info["new_folder"] = new_path
        dlg = WebModal(self, Translator.get("DRIVE_ROOT_MOVED", info))
        dlg.add_button("MOVE", Translator.get("DRIVE_ROOT_UPDATE"), style="primary")
        dlg.add_button("RECREATE", Translator.get("DRIVE_ROOT_RECREATE"))
        dlg.add_button("DISCONNECT", Translator.get("DRIVE_ROOT_DISCONNECT"), style="danger")
        res = dlg.exec_()
        if res == "DISCONNECT":
            self.manager.unbind_engine(engine.get_uid())
        elif res == "RECREATE":
            engine.reinit()
            engine.start()
        elif res == "MOVE":
            engine.set_local_folder(unicode(new_path))
            engine.start()

    def get_cache_folder(self):
        return os.path.join(self.manager.get_configuration_folder(), "cache", "wui")

    def _get_skin(self):
        return 'ui5'

    def get_window_icon(self):
        return find_icon('nuxeo_drive_icon_64.png')

    def get_htmlpage(self, page):
        import nxdrive
        nxdrive_path = os.path.dirname(nxdrive.__file__)
        ui_path = os.path.join(nxdrive_path, 'data', self._get_skin())
        return os.path.join(find_resource_dir(self._get_skin(), ui_path), page).replace("\\","/")

    def _init_translator(self):
        from nxdrive.wui.translator import Translator
        Translator(self.manager, self.get_htmlpage('i18n.js'),
                        self.manager.get_config("locale", self.options.locale))

    @QtCore.pyqtSlot(object)
    def dropped_engine(self, engine):
        # Update icon in case the engine dropped was syncing
        self.change_systray_icon()

    @QtCore.pyqtSlot()
    def change_systray_icon(self):
        syncing = False
        engines = self.manager.get_engines()
        invalid_credentials = True
        paused = True
        offline = True
        for _, engine in engines.iteritems():
            syncing = syncing | engine.is_syncing()
            invalid_credentials = invalid_credentials & engine.has_invalid_credentials()
            paused = paused & engine.is_paused()
            offline = offline & engine.is_offline()
        new_state = "asleep"
        if len(engines) == 0 or paused or offline:
            new_state = "disabled"
        elif invalid_credentials:
            new_state = 'stopping'
        elif syncing:
            new_state = 'transferring'
        log.trace("Should change icon to %s", new_state)
        self.set_icon_state(new_state)

    def _get_settings_dialog(self, section):
        from nxdrive.wui.settings import WebSettingsDialog
        return WebSettingsDialog(self, section)

    def _get_conflicts_dialog(self, engine):
        from nxdrive.wui.dialog import WebDialog
        from nxdrive.wui.conflicts import WebConflictsApi
        return WebDialog(self, "conflicts.html", api=WebConflictsApi(self, engine))

    @QtCore.pyqtSlot()
    def show_conflicts_resolution(self, engine):
        conflicts = self._get_unique_dialog("conflicts")
        if conflicts is None:
            conflicts = self._get_conflicts_dialog(engine)
            self._create_unique_dialog("conflicts", conflicts)
        else:
            conflicts._api.set_engine(engine)
        self._show_window(conflicts)

    @QtCore.pyqtSlot()
    def show_settings(self, section="Accounts"):
        if section is None:
            section = "Accounts"
        settings = self._get_unique_dialog("settings")
        if settings is None:
            settings = self._get_settings_dialog(section)
            self._create_unique_dialog("settings", settings)
        else:
            settings.set_section(section)
        self._show_window(settings)

    def _show_window(self, window):
        window.show()
        window.raise_()

    def _get_unique_dialog(self, name):
        if name in self.uniqueDialogs:
            return self.uniqueDialogs[name]
        return None

    def _destroy_dialog(self):
        sender = self.sender()
        name = str(sender.objectName())
        if name in self.uniqueDialogs:
            del self.uniqueDialogs[name]

    def _create_unique_dialog(self, name, dialog):
        self.uniqueDialogs[name] = dialog
        dialog.setObjectName(name)
        dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        dialog.destroyed.connect(self._destroy_dialog)

    @QtCore.pyqtSlot()
    def destroyed_filters_dialog(self):
        self.filters_dlg = None

    def _get_filters_dialog(self, engine):
        from nxdrive.gui.folders_dialog import FiltersDialog
        return FiltersDialog(self, engine)

    @QtCore.pyqtSlot()
    def show_filters(self, engine):
        if self.filters_dlg is not None:
            self.filters_dlg.close()
            self.filters_dlg = None
        self.filters_dlg = self._get_filters_dialog(engine)
        self.filters_dlg.destroyed.connect(self.destroyed_filters_dialog)
        self.filters_dlg.show()

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
        engine.invalidAuthentication.connect(self.change_systray_icon)
        engine.syncSuspended.connect(self.change_systray_icon)
        engine.syncResumed.connect(self.change_systray_icon)
        engine.offline.connect(self.change_systray_icon)
        engine.online.connect(self.change_systray_icon)
        engine.rootDeleted.connect(self._root_deleted)
        engine.rootMoved.connect(self._root_moved)

    @QtCore.pyqtSlot()
    def _debug_toggle_invalid_credentials(self):
        sender = self.sender()
        engine = sender.data().toPyObject()
        engine.set_invalid_credentials(not engine.has_invalid_credentials(), reason='debug')

    @QtCore.pyqtSlot()
    def _debug_show_file_status(self):
        from nxdrive.gui.status_dialog import StatusDialog
        sender = self.sender()
        engine = sender.data().toPyObject()
        self.statusDialog = StatusDialog(engine.get_dao())
        self.statusDialog.show()

    def _create_debug_engine_menu(self, engine, parent):
        menuDebug = QtGui.QMenu(parent)
        action = QtGui.QAction(Translator.get("DEBUG_INVALID_CREDENTIALS"), menuDebug)
        action.setCheckable(True)
        action.setChecked(engine.has_invalid_credentials())
        action.setData(engine)
        action.triggered.connect(self._debug_toggle_invalid_credentials)
        menuDebug.addAction(action)
        action = QtGui.QAction(Translator.get("DEBUG_FILE_STATUS"), menuDebug)
        action.setData(engine)
        action.triggered.connect(self._debug_show_file_status)
        menuDebug.addAction(action)
        return menuDebug

    def create_debug_menu(self, parent):
        menuDebug = QtGui.QMenu(parent)
        menuDebug.addAction(Translator.get("DEBUG_WINDOW"), self.show_debug_window)
        for engine in self.manager.get_engines().values():
            action = QtGui.QAction(engine._name, menuDebug)
            action.setMenu(self._create_debug_engine_menu(engine, menuDebug))
            action.setData(engine)
            menuDebug.addAction(action)
        return menuDebug

    def _get_debug_dialog(self):
        from nxdrive.debug.wui.engine import EngineDialog
        return EngineDialog(self)

    @QtCore.pyqtSlot()
    def show_debug_window(self):
        debug = self._get_unique_dialog("debug")
        if debug is None:
            debug = self._get_debug_dialog()
            self._create_unique_dialog("debug", debug)
        self._show_window(debug)

    def init_checks(self):
        if self.manager.is_debug():
            self.show_debug_window()
        for _, engine in self.manager.get_engines().iteritems():
            self._connect_engine(engine)
        self.manager.newEngine.connect(self._connect_engine)
        self.manager.get_notification_service().newNotification.connect(self._new_notification)
        self.manager.get_updater().updateAvailable.connect(self._update_notification)
        if not self.manager.get_engines():
            self.show_settings()
        else:
            for engine in self.manager.get_engines().values():
                # Prompt for settings if needed
                if engine.has_invalid_credentials():
                    self.show_settings('Accounts_' + engine._uid)
                    break
        self.manager.start()

    @QtCore.pyqtSlot()
    def _update_notification(self):
        replacements = dict()
        replacements["version"] = self.manager.get_updater().get_status()[1]
        notification = Notification(uuid="AutoUpdate",
                                    flags=Notification.FLAG_BUBBLE|Notification.FLAG_VOLATILE|Notification.FLAG_UNIQUE,
                                    title=Translator.get("AUTOUPDATE_NOTIFICATION_TITLE", replacements),
                                    description=Translator.get("AUTOUPDATE_NOTIFICATION_MESSAGE", replacements))
        self.manager.get_notification_service().send_notification(notification)

    @QtCore.pyqtSlot()
    def _message_clicked(self):
        if self.current_notification is None:
            return
        self.manager.get_notification_service().trigger_notification(self.current_notification.get_uid())

    def _setup_notification_center(self):
        from nxdrive.osi.darwin.pyNotificationCenter import setup_delegator, NotificationDelegator
        if self._delegator is None:
            self._delegator = NotificationDelegator.alloc().init()
            self._delegator._manager = self.manager
        setup_delegator(self._delegator)

    @QtCore.pyqtSlot(object)
    def _new_notification(self, notification):
        if not notification.is_bubble():
            return
        if AbstractOSIntegration.is_mac():
            if AbstractOSIntegration.os_version_above("10.8"):
                from nxdrive.osi.darwin.pyNotificationCenter import notify, NotificationDelegator
                if self._delegator is None:
                    self._delegator = NotificationDelegator.alloc().init()
                    self._delegator._manager = self.manager
                # Use notification center
                userInfo = dict()
                userInfo["uuid"] = notification.get_uid()
                return notify(notification.get_title(), None, notification.get_description(), userInfo=userInfo)
        self.current_notification = notification
        icon = QtGui.QSystemTrayIcon.Information
        if (notification.get_level() == Notification.LEVEL_WARNING):
            icon = QtGui.QSystemTrayIcon.Warning
        elif (notification.get_level() == Notification.LEVEL_ERROR):
            icon =  QtGui.QSystemTrayIcon.Critical
        self.show_message(notification.get_title(), notification.get_description(), icon=icon)

    def get_systray_menu(self):
        from nxdrive.wui.systray import WebSystray
        return WebSystray(self, self._tray_icon)

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

    def get_osi(self):
        return self.manager.get_osi()

    def update_tooltip(self):
        # Update also the file
        self._tray_icon.setToolTip(self.get_tooltip())

    def get_default_tooltip(self):
        return self.manager.get_appname()

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

    @QtCore.pyqtSlot(str)
    def app_updated(self, updated_version):
        self.updated_version = str(updated_version)
        log.info('Quitting Nuxeo Drive and restarting updated version %s', self.updated_version)
        self.manager.stopped.connect(self.restart)
        log.debug("Exiting Qt application")
        self.quit()

    @QtCore.pyqtSlot()
    def restart(self):
        """ Restart application by loading updated executable into current process"""
        current_version = self.manager.get_updater().get_active_version()
        log.info("Current application version: %s", current_version)
        log.info("Updated application version: %s", self.updated_version)

        executable = sys.executable
        # TODO NXP-13818: better handle this!
        if sys.platform == 'darwin':
            executable = executable.replace('python',
                                            self.get_mac_app())
        log.info("Current executable is: %s", executable)
        updated_executable = executable.replace(current_version,
                                                self.updated_version)
        log.info("Updated executable is: %s", updated_executable)

        args = [updated_executable]
        args.extend(sys.argv[1:])
        log.info("Opening subprocess with args: %r", args)
        subprocess.Popen(args)

    def get_mac_app(self):
        return 'ndrive'

    def show_message(self, title, message, icon=QtGui.QSystemTrayIcon.Information, timeout=10000):
        self._tray_icon.showMessage(title, message, icon, timeout)

    def show_dialog(self, url):
        from nxdrive.wui.dialog import WebDialog
        dialog = WebDialog(self, url)
        dialog.show()

    def show_metadata(self, file_path):
        from nxdrive.wui.metadata import CreateMetadataWebDialog
        self._metadata_dialog = CreateMetadataWebDialog(self.manager, file_path)
        self._metadata_dialog.show()

    def setup_systray(self):
        self._tray_icon = DriveSystrayIcon()
        self._tray_icon.setToolTip(self.manager.get_appname())
        self.set_icon_state("disabled")
        self._tray_icon.show()
        self.tray_icon_menu = self.get_systray_menu()
        self._tray_icon.setContextMenu(self.tray_icon_menu)
        self._tray_icon.messageClicked.connect(self._message_clicked)

    def event(self, event):
        """Handle URL scheme events under OSX"""
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
                        self.manager.get_drive_edit().edit(
                            info['server_url'], info['doc_id'], user=info['user'], download_url=info['download_url'])
                    elif info.get('command') == 'edit':
                        # Kept for backward compatibility
                        self.manager.get_drive_edit().edit(
                            info['server_url'], info['item_id'])
            except:
                log.error("Error handling URL event: %s", url, exc_info=True)
        return super(Application, self).event(event)
