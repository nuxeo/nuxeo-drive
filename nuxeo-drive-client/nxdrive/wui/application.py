# coding: utf-8
""" Main Qt application handling OS events and system tray UI. """

import json
import os
import urllib2
from logging import getLogger

from PyQt4.QtCore import Qt, pyqtSlot
from PyQt4.QtGui import (QAction, QApplication, QDialog, QDialogButtonBox,
                         QIcon, QMenu, QMessageBox, QMovie, QSystemTrayIcon,
                         QTextEdit, QVBoxLayout)
from markdown import markdown

from .modal import WebModal
from .systray import DriveSystrayIcon
from .translator import Translator
from ..engine.activity import Action, FileAction
from ..notification import Notification
from ..options import Options
from ..osi import AbstractOSIntegration
from ..updater.constants import (UPDATE_STATUS_DOWNGRADE_NEEDED,
                                 UPDATE_STATUS_UP_TO_DATE)
from ..utils import find_icon, find_resource, parse_protocol_url

log = getLogger(__name__)


class SimpleApplication(QApplication):
    """ Simple application with html and translator. """

    def __init__(self, manager, argv=()):
        super(SimpleApplication, self).__init__(list(argv))
        # Make dialog unique
        self.uniqueDialogs = dict()

        self.manager = manager
        self.osi = self.manager.osi
        self.setApplicationName(manager.app_name)
        self._init_translator()

    def translate(self, message, values=None):
        return Translator.get(message, values)

    def _show_window(self, window):
        window.show()
        window.raise_()

    def _get_unique_dialog(self, name):
        if name in self.uniqueDialogs:
            return self.uniqueDialogs[name]

    def _destroy_dialog(self):
        sender = self.sender()
        name = str(sender.objectName())
        if name in self.uniqueDialogs:
            del self.uniqueDialogs[name]

    def _create_unique_dialog(self, name, dialog):
        self.uniqueDialogs[name] = dialog
        dialog.setObjectName(name)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.destroyed.connect(self._destroy_dialog)

    def _init_translator(self):
        locale = Options.force_locale or Options.locale
        Translator(
            self.manager,
            find_resource('i18n', ''),
            self.manager.get_config('locale', locale),
        )

    @staticmethod
    def get_htmlpage(page):
        return find_resource(Options.theme, page).replace('\\', '/')

    @staticmethod
    def get_window_icon():
        return find_icon('icon_64.png')

    def get_cache_folder(self):
        return os.path.join(self.manager.nxdrive_home, 'cache', 'wui')


class Application(SimpleApplication):
    """Main Nuxeo drive application controlled by a system tray icon + menu"""

    tray_icon = None
    icon_state = None

    def __init__(self, manager, *args):
        super(Application, self).__init__(manager, *args)
        self.setQuitOnLastWindowClosed(False)
        self._delegator = None
        from ..scripting import DriveUiScript
        self.manager.set_script_object(DriveUiScript(manager, self))
        self.filters_dlg = None
        self._conflicts_modals = dict()
        self.current_notification = None
        self.default_tooltip = self.manager.app_name

        self.aboutToQuit.connect(self.manager.stop)
        self.manager.dropEngine.connect(self.dropped_engine)

        # Movie to animate the transferring icon
        self.animated_icon = QMovie(find_icon('transferring.gif'))
        self.animated_icon.frameChanged.connect(self._update_animated_icon)

        # This is a windowless application mostly using the system tray
        self.setQuitOnLastWindowClosed(False)

        self.setup_systray()

        # Direct Edit
        self.manager.direct_edit.directEditConflict.connect(self._direct_edit_conflict)
        self.manager.direct_edit.directEditError.connect(self._direct_edit_error)

        # Check if actions is required, separate method so it can be overridden
        self.init_checks()

        # Setup notification center for macOS
        if AbstractOSIntegration.is_mac():
            self._setup_notification_center()

        # Application update
        self.manager.updater.appUpdated.connect(self.quit)

        # Display release notes on new version
        if self.manager.old_version != self.manager.version:
            self.show_release_notes(self.manager.version)

    @pyqtSlot(str, str, str)
    def _direct_edit_conflict(self, filename, ref, digest):
        log.trace('Entering _direct_edit_conflict for %r / %r', filename, ref)
        try:
            filename = unicode(filename)
            if filename in self._conflicts_modals:
                log.trace('Filename already in _conflicts_modals: %r', filename)
                return
            log.trace('Putting filename in _conflicts_modals: %r', filename)
            self._conflicts_modals[filename] = True
            info = dict(name=filename)
            dlg = WebModal(
                self,
                Translator.get('DIRECT_EDIT_CONFLICT_MESSAGE', info),
            )
            dlg.add_button('OVERWRITE',
                           Translator.get('DIRECT_EDIT_CONFLICT_OVERWRITE'))
            dlg.add_button('CANCEL',
                           Translator.get('DIRECT_EDIT_CONFLICT_CANCEL'))
            res = dlg.exec_()
            if res == 'OVERWRITE':
                self.manager.direct_edit.force_update(unicode(ref),
                                                      unicode(digest))
            del self._conflicts_modals[filename]
        except:
            log.exception('Error while displaying Direct Edit'
                          ' conflict modal dialog for %r', filename)

    @pyqtSlot(str, dict)
    def _direct_edit_error(self, message, values):
        """ Display a simple Direct Edit error message. """

        msg = QMessageBox()
        msg.setWindowTitle('Direct Edit')
        msg.setWindowIcon(QIcon(self.get_window_icon()))
        msg.setIcon(QMessageBox.Warning)
        msg.setTextFormat(Qt.RichText)
        msg.setText(self.translate(unicode(message), values))
        msg.exec_()

    @pyqtSlot()
    def _root_deleted(self):
        engine = self.sender()
        info = {'folder': engine.local_folder}
        log.debug('Root has been deleted for engine: %s', engine.uid)
        dlg = WebModal(self, Translator.get('DRIVE_ROOT_DELETED', info))
        dlg.add_button('RECREATE',
                       Translator.get('DRIVE_ROOT_RECREATE'),
                       style='primary')
        dlg.add_button('DISCONNECT',
                       Translator.get('DRIVE_ROOT_DISCONNECT'),
                       style='danger')
        res = dlg.exec_()
        if res == 'DISCONNECT':
            self.manager.unbind_engine(engine.uid)
        elif res == 'RECREATE':
            engine.reinit()
            engine.start()

    @pyqtSlot()
    def _no_space_left(self):
        dialog = WebModal(self, Translator.get('NO_SPACE_LEFT_ON_DEVICE'))
        dialog.add_button('OK', Translator.get('OK'))
        dialog.exec_()

    @pyqtSlot(str)
    def _root_moved(self, new_path):
        engine = self.sender()
        log.debug('Root has been moved for engine: %s to %r', engine.uid, new_path)
        info = {
            'folder': engine.local_folder,
            'new_folder': new_path,
        }
        dlg = WebModal(self, Translator.get('DRIVE_ROOT_MOVED', info))
        dlg.add_button('MOVE',
                       Translator.get('DRIVE_ROOT_UPDATE'),
                       style='primary')
        dlg.add_button('RECREATE', Translator.get('DRIVE_ROOT_RECREATE'))
        dlg.add_button('DISCONNECT',
                       Translator.get('DRIVE_ROOT_DISCONNECT'),
                       style='danger')
        res = dlg.exec_()
        if res == 'DISCONNECT':
            self.manager.unbind_engine(engine.uid)
        elif res == 'RECREATE':
            engine.reinit()
            engine.start()
        elif res == 'MOVE':
            engine.set_local_folder(unicode(new_path))
            engine.start()

    def get_cache_folder(self):
        return os.path.join(self.manager.nxdrive_home, 'cache', 'wui')

    @pyqtSlot(object)
    def dropped_engine(self, engine):
        # Update icon in case the engine dropped was syncing
        self.change_systray_icon()

    @pyqtSlot()
    def change_systray_icon(self):
        # Update status has the precedence over other ones
        if self.manager.updater.last_status[0] != UPDATE_STATUS_UP_TO_DATE:
            self.set_icon_state('update_available')
            return

        syncing = False
        engines = self.manager.get_engines()
        invalid_credentials = True
        paused = True
        offline = True

        for engine in engines.itervalues():
            syncing |= engine.is_syncing()
            invalid_credentials &= engine.has_invalid_credentials()
            paused &= engine.is_paused()
            offline &= engine.is_offline()

        if offline:
            new_state = 'stopping'
            Action(Translator.get('OFFLINE'))
        elif invalid_credentials:
            new_state = 'stopping'
            Action(Translator.get('INVALID_CREDENTIALS'))
        elif not engines or paused:
            new_state = 'disabled'
            Action.finish_action()
        elif syncing:
            new_state = 'transferring'
        else:
            new_state = 'asleep'
            Action.finish_action()

        self.set_icon_state(new_state)

    def _update_animated_icon(self):
        icon = QIcon(self.animated_icon.currentPixmap())
        self.tray_icon.setIcon(icon)

    def _get_settings_dialog(self, section):
        from .settings import WebSettingsDialog
        return WebSettingsDialog(self, section)

    def _get_conflicts_dialog(self, engine):
        from .dialog import WebDialog
        from .conflicts import WebConflictsApi
        return WebDialog(
            self,
            'conflicts.html',
            api=WebConflictsApi(self, engine),
        )

    @pyqtSlot()
    def show_conflicts_resolution(self, engine):
        conflicts = self._get_unique_dialog('conflicts')
        if conflicts is None:
            conflicts = self._get_conflicts_dialog(engine)
            self._create_unique_dialog('conflicts', conflicts)
        else:
            conflicts.api.set_engine(engine)
        self._show_window(conflicts)

    @pyqtSlot()
    def show_settings(self, section='Accounts'):
        if section is None:
            section = 'Accounts'
        settings = self._get_unique_dialog('settings')
        if settings is None:
            settings = self._get_settings_dialog(section)
            self._create_unique_dialog('settings', settings)
        else:
            settings.set_section(section)
        self._show_window(settings)

    @pyqtSlot()
    def open_help(self):
        self.manager.open_help()

    @pyqtSlot()
    def destroyed_filters_dialog(self):
        self.filters_dlg = None

    def _get_filters_dialog(self, engine):
        from ..gui.folders_dialog import FiltersDialog
        return FiltersDialog(self, engine)

    @pyqtSlot()
    def show_filters(self, engine):
        if self.filters_dlg is not None:
            self.filters_dlg.close()
            self.filters_dlg = None
        self.filters_dlg = self._get_filters_dialog(engine)
        self.filters_dlg.destroyed.connect(self.destroyed_filters_dialog)
        self.filters_dlg.show()

    def show_file_status(self):
        from ..gui.status_dialog import StatusDialog
        for _, engine in self.manager.get_engines().iteritems():
            self.status = StatusDialog(engine.get_dao())
            self.status.show()
            break

    def show_activities(self):
        from .activity import WebActivityDialog
        self.activities = WebActivityDialog(self)
        self.activities.show()

    @pyqtSlot(object)
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
        engine.noSpaceLeftOnDevice.connect(self._no_space_left)
        self.change_systray_icon()

    @pyqtSlot()
    def _debug_toggle_invalid_credentials(self):
        sender = self.sender()
        engine = sender.data().toPyObject()
        engine.set_invalid_credentials(not engine.has_invalid_credentials(), reason='debug')

    @pyqtSlot()
    def _debug_show_file_status(self):
        from ..gui.status_dialog import StatusDialog
        sender = self.sender()
        engine = sender.data().toPyObject()
        self.status_dialog = StatusDialog(engine.get_dao())
        self.status_dialog.show()

    def _create_debug_engine_menu(self, engine, parent):
        menu = QMenu(parent)
        action = QAction(Translator.get('DEBUG_INVALID_CREDENTIALS'), menu)
        action.setCheckable(True)
        action.setChecked(engine.has_invalid_credentials())
        action.setData(engine)
        action.triggered.connect(self._debug_toggle_invalid_credentials)
        menu.addAction(action)
        action = QAction(Translator.get('DEBUG_FILE_STATUS'), menu)
        action.setData(engine)
        action.triggered.connect(self._debug_show_file_status)
        menu.addAction(action)
        return menu

    def create_debug_menu(self, menu):
        menu.addAction(Translator.get('DEBUG_WINDOW'), self.show_debug_window)
        for engine in self.manager.get_engines().values():
            action = QAction(engine.name, menu)
            action.setMenu(self._create_debug_engine_menu(engine, menu))
            action.setData(engine)
            menu.addAction(action)

    @pyqtSlot()
    def show_debug_window(self):
        debug = self._get_unique_dialog('debug')
        if debug is None:
            from ..debug.wui.engine import EngineDialog
            debug = EngineDialog(self)
            self._create_unique_dialog('debug', debug)
        self._show_window(debug)

    def init_checks(self):
        if Options.debug:
            self.show_debug_window()
        for _, engine in self.manager.get_engines().iteritems():
            self._connect_engine(engine)
        self.manager.newEngine.connect(self._connect_engine)
        self.manager.notification_service.newNotification.connect(self._new_notification)
        self.manager.updater.updateAvailable.connect(self._update_notification)
        if not self.manager.get_engines():
            self.show_settings()
        else:
            for engine in self.manager.get_engines().values():
                # Prompt for settings if needed
                if engine.has_invalid_credentials():
                    self.show_settings('Accounts_' + engine.uid)
                    break
        self.manager.start()

    @pyqtSlot()
    def _update_notification(self):
        self.change_systray_icon()

        # Display a notification
        status, version = self.manager.updater.last_status[:2]
        replacements = {'version': version}

        msg = ('AUTOUPDATE_UPGRADE',
               'AUTOUPDATE_DOWNGRADE')[status == UPDATE_STATUS_DOWNGRADE_NEEDED]
        description = Translator.get(msg, replacements)
        flags = Notification.FLAG_BUBBLE | Notification.FLAG_UNIQUE
        if AbstractOSIntegration.is_linux():
            description += ' ' + Translator.get('AUTOUPDATE_MANUAL')
            flags |= Notification.FLAG_SYSTRAY

        log.warning(description)
        notification = Notification(
            uuid='AutoUpdate',
            flags=flags,
            title=Translator.get('NOTIF_UPDATE_TITLE', replacements),
            description=description
        )
        self.manager.notification_service.send_notification(notification)

    @pyqtSlot()
    def message_clicked(self):
        if self.current_notification:
            self.manager.notification_service.trigger_notification(self.current_notification.uid)

    def _setup_notification_center(self):
        from ..osi.darwin.pyNotificationCenter import setup_delegator, NotificationDelegator
        if self._delegator is None:
            self._delegator = NotificationDelegator.alloc().init()
            self._delegator._manager = self.manager
        setup_delegator(self._delegator)

    @pyqtSlot(object)
    def _new_notification(self, notif):
        if not notif.is_bubble():
            return

        if self._delegator is not None:
            # Use notification center
            from ..osi.darwin.pyNotificationCenter import notify
            return notify(
                notif.title,
                None,
                notif.description,
                user_info={'uuid': notif.uid},
            )

        icon = QSystemTrayIcon.Information
        if notif.level == Notification.LEVEL_WARNING:
            icon = QSystemTrayIcon.Warning
        elif notif.level == Notification.LEVEL_ERROR:
            icon = QSystemTrayIcon.Critical

        self.current_notification = notif
        self.tray_icon.showMessage(notif.title, notif.description, icon, 10000)

    def set_icon_state(self, state):
        """
        Execute systray icon change operations triggered by state change.

        The synchronization thread can update the state info but cannot
        directly call QtGui widget methods. This should be executed by the main
        thread event loop, hence the delegation to this method that is
        triggered by a signal to allow for message passing between the 2
        threads.

        Return True of the icon has changed state.
        """

        if self.icon_state == state:
            # Nothing to update
            return False

        self.tray_icon.setToolTip(self.get_tooltip())

        # Handle animated transferring icon
        if state == 'transferring':
            self.animated_icon.start()
        else:
            self.animated_icon.stop()
            icon = find_icon('systray_icon_%s_18.png' % state)
            self.tray_icon.setIcon(QIcon(icon))

        self.icon_state = state
        return True

    def get_tooltip(self):
        actions = Action.get_actions()
        if not actions:
            return self.default_tooltip

        # Display only the first action for now
        for action in actions.itervalues():
            if action and not action.type.startswith('_'):
                break
        else:
            return self.default_tooltip

        if isinstance(action, FileAction):
            if action.get_percent() is not None:
                return '%s - %s - %s - %d%%' % (
                    self.default_tooltip,
                    action.type, action.filename,
                    action.get_percent(),
                )
            return '%s - %s - %s' % (
                self.default_tooltip,
                action.type, action.filename,
            )
        elif action.get_percent() is not None:
            return '%s - %s - %d%%' % (
                self.default_tooltip,
                action.type,
                action.get_percent(),
            )

        return '%s - %s' % (
            self.default_tooltip,
            action.type,
        )

    def show_release_notes(self, version):
        """ Display release notes of a given version. """

        beta = self.manager.get_beta_channel()
        log.debug('Showing release notes, version=%r beta=%r', version, beta)

        # For now, we do care about beta only
        if not beta:
            return

        url = ('https://api.github.com/repos/'
               'nuxeo/nuxeo-drive'
               '/releases/tags/'
               'release-' + version)

        if beta:
            version += ' beta'

        try:
            content = urllib2.urlopen(url).read()
        except urllib2.HTTPError as exc:
            if exc.code == 404:
                log.error('[%s] Release does not exist', version)
            else:
                log.exception(
                    '[%s] Network error while fetching release notes', version)
            return
        except:
            log.exception(
                '[%s] Unknown error while fetching release notes', version)
            return

        try:
            data = json.loads(content)
        except (TypeError, ValueError):
            log.exception('[%s] Invalid release notes', version)
            return

        try:
            html = markdown(data['body'])
        except KeyError:
            log.error('[%s] Release notes is missing its body', version)
            return
        except (UnicodeDecodeError, ValueError):
            log.exception('[%s] Release notes conversion error', version)
            return

        dialog = QDialog()
        dialog.setWindowTitle('Drive %s - Release notes' % version)
        dialog.setWindowIcon(QIcon(self.get_window_icon()))

        dialog.resize(600, 400)

        notes = QTextEdit()
        notes.setStyleSheet(
            'background-color: #eee;'
            'border: none;'
        )
        notes.setReadOnly(True)
        notes.setHtml(html)

        buttons = QDialogButtonBox()
        buttons.setStandardButtons(QDialogButtonBox.Ok)
        buttons.clicked.connect(dialog.accept)

        layout = QVBoxLayout()
        layout.addWidget(notes)
        layout.addWidget(buttons)
        dialog.setLayout(layout)
        dialog.exec_()

    @staticmethod
    def get_mac_app():
        return 'ndrive'

    def show_dialog(self, url):
        from .dialog import WebDialog
        WebDialog(self, url).show()

    def show_metadata(self, file_path):
        self.manager.open_metadata_window(file_path)

    def setup_systray(self):
        self.tray_icon = DriveSystrayIcon(self)
        self.tray_icon.setToolTip(self.manager.app_name)
        self.set_icon_state('disabled')
        self.tray_icon.show()

    def event(self, event):
        """Handle URL scheme events under OSX"""
        if hasattr(event, 'url'):
            url = str(event.url().toString())
            try:
                info = parse_protocol_url(url)
                log.debug('Event url=%s, info=%r', url, info)
                if info is not None:
                    log.debug('Received nxdrive URL scheme event: %s', url)
                    cmd = info['command']
                    path = info.get('filepath', None)
                    manager = self.manager

                    # Command to open the file on the platform in the browser
                    if cmd == 'access':
                        manager.open_metadata_window(path)

                    # Command to copy the platform share link in the clipboard
                    elif cmd == 'share_link':
                        manager.copy_share_link(path)

                    # Command to direct edit the file
                    elif 'edit' in cmd:
                        # This is a quick operation, no need to fork a QThread
                        manager.direct_edit.edit(
                            info['server_url'], info['doc_id'],
                            user=info['user'],
                            download_url=info['download_url'])

                    # Command to trigger the watch on the synced folders
                    elif cmd == 'trigger_watch':
                        log.debug('Received triggerWatch')
                        if manager._engines is None:
                            manager.load()
                        for engine in manager._engine_definitions:
                            manager.osi.watch_folder(engine.local_folder)

                    # Command to retrieve the sync status of a file
                    elif cmd == 'sync_status':
                        log.debug('Received getSyncStatus')
                        if manager._engines is None:
                            manager.load()
                        rel_path = None
                        for engine in manager._engine_definitions:
                            # Only send status if we picked the right
                            # engine and if we're not targeting the root
                            if (path.startswith(engine.local_folder)
                                    and not os.path.samefile(
                                        path, engine.local_folder)):
                                rel_path = path.replace(engine.local_folder,
                                                        '')
                                dao = manager._engines[engine.uid]._dao
                                state = dao.get_state_from_local(rel_path)
                                manager.osi.send_sync_status(state, path)
                                break
            except:
                log.exception('Error handling URL event: %s', url)
        return super(Application, self).event(event)
