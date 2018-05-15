# coding: utf-8
""" Main Qt application handling OS events and system tray UI. """
import json
import os
from logging import getLogger
from urllib import unquote

import requests
from PyQt4.QtCore import Qt, pyqtSlot
from PyQt4.QtGui import (QAction, QApplication, QDialog, QDialogButtonBox,
                         QIcon, QMenu, QMessageBox, QSystemTrayIcon,
                         QTextEdit, QVBoxLayout)
from markdown import markdown

from .systray import DriveSystrayIcon
from .translator import Translator
from ..engine.activity import Action, FileAction
from ..notification import Notification
from ..options import Options
from ..osi import AbstractOSIntegration
from ..updater.constants import (UPDATE_STATUS_DOWNGRADE_NEEDED,
                                 UPDATE_STATUS_UNAVAILABLE_SITE,
                                 UPDATE_STATUS_UP_TO_DATE)
from ..utils import find_icon, find_resource, parse_protocol_url

log = getLogger(__name__)


class SimpleApplication(QApplication):
    """ Simple application with html and translator. """

    def __init__(self, manager, argv=()):
        super(SimpleApplication, self).__init__(list(argv))
        self.manager = manager

        self.dialogs = dict()
        self.osi = self.manager.osi
        self.setApplicationName(manager.app_name)
        self._init_translator()

    def translate(self, message, values=None):
        return Translator.get(message, values)

    def _show_window(self, window):
        window.show()
        window.raise_()

    def _destroy_dialog(self):
        sender = self.sender()
        name = str(sender.objectName())
        self.dialogs.pop(name, None)

    def _create_unique_dialog(self, name, dialog):
        dialog.setObjectName(name)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.destroyed.connect(self._destroy_dialog)
        self.dialogs[name] = dialog

    def _init_translator(self):
        locale = Options.force_locale or Options.locale
        Translator(
            self.manager,
            find_resource('i18n'),
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

        # This is a windowless application mostly using the system tray
        self.setQuitOnLastWindowClosed(False)

        self.setup_systray()

        # Direct Edit
        self.manager.direct_edit.directEditConflict.connect(
            self._direct_edit_conflict)
        self.manager.direct_edit.directEditError.connect(
            self._direct_edit_error)

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
                log.trace('Filename already in _conflicts_modals: %r',
                          filename)
                return
            log.trace('Putting filename in _conflicts_modals: %r', filename)
            self._conflicts_modals[filename] = True
            info = dict(name=filename)

            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowIcon(QIcon(self.get_window_icon()))
            msg.setText(Translator.get('DIRECT_EDIT_CONFLICT_MESSAGE', info))
            overwrite = msg.addButton(
                Translator.get('DIRECT_EDIT_CONFLICT_OVERWRITE'),
                QMessageBox.AcceptRole)
            cancel = msg.addButton(
                Translator.get('DIRECT_EDIT_CONFLICT_CANCEL'),
                QMessageBox.RejectRole)

            msg.exec_()
            res = msg.clickedButton()
            if res == overwrite:
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

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowIcon(QIcon(self.get_window_icon()))
        msg.setText(Translator.get('DRIVE_ROOT_DELETED', info))
        recreate = msg.addButton(
            Translator.get('DRIVE_ROOT_RECREATE'), QMessageBox.AcceptRole)
        disconnect = msg.addButton(
            Translator.get('DRIVE_ROOT_DISCONNECT'), QMessageBox.RejectRole)

        msg.exec_()
        res = msg.clickedButton()
        if res == disconnect:
            self.manager.unbind_engine(engine.uid)
        elif res == recreate:
            engine.reinit()
            engine.start()

    @pyqtSlot()
    def _no_space_left(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowIcon(QIcon(self.get_window_icon()))
        msg.setText(Translator.get('NO_SPACE_LEFT_ON_DEVICE'))
        msg.addButton(Translator.get('OK'), QMessageBox.AcceptRole)
        msg.exec_()

    @pyqtSlot(str)
    def _root_moved(self, new_path):
        engine = self.sender()
        log.debug('Root has been moved for engine: %s to %r',
                  engine.uid, new_path)
        info = {
            'folder': engine.local_folder,
            'new_folder': new_path,
        }

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowIcon(QIcon(self.get_window_icon()))
        msg.setText(Translator.get('DRIVE_ROOT_MOVED', info))
        move = msg.addButton(
            Translator.get('DRIVE_ROOT_UPDATE'), QMessageBox.AcceptRole)
        recreate = msg.addButton(
            Translator.get('DRIVE_ROOT_RECREATE'), QMessageBox.AcceptRole)
        disconnect = msg.addButton(
            Translator.get('DRIVE_ROOT_DISCONNECT'), QMessageBox.RejectRole)
        msg.exec_()
        res = msg.clickedButton()

        if res == disconnect:
            self.manager.unbind_engine(engine.uid)
        elif res == recreate:
            engine.reinit()
            engine.start()
        elif res == move:
            engine.set_local_folder(unicode(new_path))
            engine.start()

    @pyqtSlot(object)
    def dropped_engine(self, engine):
        # Update icon in case the engine dropped was syncing
        self.change_systray_icon()

    @pyqtSlot()
    def change_systray_icon(self):
        # Update status has the precedence over other ones
        if self.manager.updater.last_status[0] not in (
                UPDATE_STATUS_UNAVAILABLE_SITE,
                UPDATE_STATUS_UP_TO_DATE):
            self.set_icon_state('update')
            return

        syncing = conflict = False
        engines = self.manager.get_engines()
        invalid_credentials = paused = offline = True

        for engine in engines.values():
            syncing |= engine.is_syncing()
            invalid_credentials &= engine.has_invalid_credentials()
            paused &= engine.is_paused()
            offline &= engine.is_offline()
            conflict |= bool(engine.get_conflicts())

        if offline:
            new_state = 'error'
            Action(Translator.get('OFFLINE'))
        elif invalid_credentials:
            new_state = 'error'
            Action(Translator.get('INVALID_CREDENTIALS'))
        elif not engines:
            new_state = 'disabled'
            Action.finish_action()
        elif paused:
            new_state = 'paused'
            Action.finish_action()
        elif syncing:
            new_state = 'syncing'
        elif conflict:
            new_state = 'conflict'
        else:
            new_state = 'idle'
            Action.finish_action()

        self.set_icon_state(new_state)

    @pyqtSlot()
    def show_conflicts_resolution(self, engine):
        conflicts = self.dialogs.get('conflicts')
        if not conflicts:
            from .dialog import WebDialog
            from .conflicts import WebConflictsApi
            conflicts = WebDialog(
                    self,
                    'conflicts.html',
                    api=WebConflictsApi(self, engine),
            )
            self._create_unique_dialog('conflicts', conflicts)

        conflicts.api.set_engine(engine)
        self._show_window(conflicts)

    @pyqtSlot()
    def show_settings(self, section='Accounts'):
        settings = self.dialogs.get('settings')
        if not settings:
            from .settings import WebSettingsDialog
            settings = WebSettingsDialog(self, section)
            self._create_unique_dialog('settings', settings)

        settings.set_section(section)
        self._show_window(settings)

    @pyqtSlot()
    def open_help(self):
        self.manager.open_help()

    @pyqtSlot()
    def destroyed_filters_dialog(self):
        self.filters_dlg = None

    @pyqtSlot()
    def show_filters(self, engine):
        if self.filters_dlg:
            self.filters_dlg.close()
            self.filters_dlg = None

        from ..gui.folders_dialog import FiltersDialog
        self.filters_dlg = FiltersDialog(self, engine)
        self.filters_dlg.destroyed.connect(self.destroyed_filters_dialog)
        self.filters_dlg.show()

    def show_file_status(self):
        from ..gui.status_dialog import StatusDialog
        for _, engine in self.manager.get_engines().items():
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
        engine.set_invalid_credentials(not engine.has_invalid_credentials(),
                                       reason='debug')

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
        debug = self.dialogs.get('debug')
        if not debug:
            from ..debug.wui.engine import EngineDialog
            debug = EngineDialog(self)
            self._create_unique_dialog('debug', debug)
        self._show_window(debug)

    def init_checks(self):
        if Options.debug:
            self.show_debug_window()
        for _, engine in self.manager.get_engines().items():
            self._connect_engine(engine)
        self.manager.newEngine.connect(self._connect_engine)
        self.manager.notification_service.newNotification.connect(
            self._new_notification)
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
            self.manager.notification_service.trigger_notification(
                self.current_notification.uid)

    def _setup_notification_center(self):
        from ..osi.darwin.pyNotificationCenter import (setup_delegator,
                                                       NotificationDelegator)
        if not self._delegator:
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
        self.tray_icon.setIcon(self.icons[state])
        self.icon_state = state
        return True

    def get_tooltip(self):
        actions = Action.get_actions()
        if not actions:
            return self.default_tooltip

        # Display only the first action for now
        for action in actions.values():
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

        url = ('https://api.github.com/repos/nuxeo/nuxeo-drive'
               '/releases/tags/release-' + version)

        if beta:
            version += ' beta'

        try:
            content = requests.get(url)
        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
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
            data = content.json()
        except ValueError:
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

    def show_dialog(self, url):
        from .dialog import WebDialog
        WebDialog(self, url).show()

    def show_metadata(self, file_path):
        self.manager.ctx_edit_metadata(file_path)

    def setup_systray(self):
        icons = {}
        for state in ('idle', 'disabled', 'conflict', 'error',
                      'notification', 'syncing', 'paused', 'update'):
            name = '{}{}.svg'.format(
                state, '_light' if AbstractOSIntegration.is_windows() else '')
            icon = QIcon()
            icon.addFile(find_icon(name), mode=QIcon.Normal)
            if AbstractOSIntegration.is_mac():
                icon.addFile(find_icon('active.svg'), mode=QIcon.Selected)
            icons[state] = icon
        setattr(self, 'icons', icons)

        self.tray_icon = DriveSystrayIcon(self)
        self.tray_icon.setToolTip(self.manager.app_name)
        self.set_icon_state('disabled')
        self.tray_icon.show()

    def event(self, event):
        # type: (QEvent) -> bool

        """ Handle URL scheme events under macOS. """

        url = getattr(event, 'url', None)
        if not url:
            # This is not an event for us!
            return super(Application, self).event(event)

        try:
            final_url = unquote(str(event.url().toString()))
            return self._handle_macos_event(final_url)
        except:
            log.exception('Error handling URL event %r', url)
            return False

    def _handle_macos_event(self, url):
        # type: (str) -> bool
        """ Handle a macOS event URL. """

        info = parse_protocol_url(url)
        if not info:
            return False

        cmd = info['command']
        path = info.get('filepath', None)
        manager = self.manager

        log.debug('Event URL=%s, info=%r', url, info)

        # Event fired by a context menu item
        func = {
            'access-online': manager.ctx_access_online,
            'copy-share-link': manager.ctx_copy_share_link,
            'edit-metadata': manager.ctx_edit_metadata,
        }.get(cmd, None)
        if func:
            func(path)
        elif 'edit' in cmd:
            manager.direct_edit.edit(
                info['server_url'],
                info['doc_id'],
                user=info['user'],
                download_url=info['download_url'])
        elif cmd == 'trigger-watch':
            for engine in manager._engine_definitions:
                manager.osi.watch_folder(engine.local_folder)
        else:
            log.warning('Unknown event URL=%r, info=%r', url, info)
            return False
        return True
