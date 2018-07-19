# coding: utf-8
""" Main Qt application handling OS events and system tray UI. """
from logging import getLogger
from math import sqrt
from typing import Any, Dict
from urllib.parse import unquote

import requests
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont, QFontMetricsF, QIcon
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
)
from markdown import markdown

from .authentication import QMLAuthenticationApi, WebAuthenticationDialog
from .settings import QMLSettingsApi
from .systray import DriveSystrayIcon
from ..constants import LINUX, MAC, WINDOWS
from ..engine.activity import Action, FileAction
from ..notification import Notification
from ..options import Options
from ..translator import Translator
from ..updater.constants import (
    UPDATE_STATUS_DOWNGRADE_NEEDED,
    UPDATE_STATUS_UNAVAILABLE_SITE,
    UPDATE_STATUS_UP_TO_DATE,
)
from ..utils import find_icon, find_resource, parse_protocol_url

__all__ = ("Application",)

log = getLogger(__name__)


class Application(QApplication):
    """Main Nuxeo drive application controlled by a system tray icon + menu"""

    tray_icon = None
    icon_state = None

    def __init__(self, manager: "Manager", *args: Any) -> None:
        super().__init__(list(*args))
        self.manager = manager

        self.dialogs = dict()
        self.osi = self.manager.osi
        self.setWindowIcon(QIcon(self.get_window_icon()))
        self.setApplicationName(manager.app_name)
        self._init_translator()
        self.setQuitOnLastWindowClosed(False)
        self._delegator = None

        self.filters_dlg = None
        self._conflicts_modals = dict()
        self.current_notification = None
        self.default_tooltip = self.manager.app_name
        font = QFont("Neue Haas Grotesk Display Std, Helvetica, Arial, sans-serif", 12)
        self.setFont(font)
        self.ratio = sqrt(QFontMetricsF(font).height() / 12)

        self.aboutToQuit.connect(self.manager.stop)
        self.manager.dropEngine.connect(self.dropped_engine)

        # This is a windowless application mostly using the system tray
        self.setQuitOnLastWindowClosed(False)

        self.setup_systray()

        # Direct Edit
        self.manager.direct_edit.directEditConflict.connect(self._direct_edit_conflict)
        self.manager.direct_edit.directEditError.connect(self._direct_edit_error)

        # Check if actions is required, separate method so it can be overridden
        self.init_checks()

        # Setup notification center for macOS
        if MAC:
            self._setup_notification_center()

        # Application update
        self.manager.updater.appUpdated.connect(self.quit)

        # Display release notes on new version
        if self.manager.old_version != self.manager.version:
            self.show_release_notes(self.manager.version)

    def translate(self, message: str, values: dict = None) -> str:
        return Translator.get(message, values)

    def _show_window(self, window: "QWindow") -> None:
        window.show()
        window.raise_()

    def _destroy_dialog(self) -> None:
        sender = self.sender()
        name = sender.objectName()
        self.dialogs.pop(name, None)

    def _create_unique_dialog(self, name: str, dialog: QDialog) -> None:
        dialog.setObjectName(name)
        dialog.destroyed.connect(self._destroy_dialog)
        self.dialogs[name] = dialog

    def _init_translator(self) -> None:
        locale = Options.force_locale or Options.locale
        Translator(
            self.manager,
            find_resource("i18n"),
            self.manager.get_config("locale", locale),
        )
        self.installTranslator(Translator._singleton)

    @staticmethod
    def get_window_icon() -> str:
        return find_icon("app_icon.svg")

    @pyqtSlot(str, str, str)
    def _direct_edit_conflict(self, filename: str, ref: str, digest: str) -> None:
        log.trace("Entering _direct_edit_conflict for %r / %r", filename, ref)
        try:
            if filename in self._conflicts_modals:
                log.trace("Filename already in _conflicts_modals: %r", filename)
                return
            log.trace("Putting filename in _conflicts_modals: %r", filename)
            self._conflicts_modals[filename] = True

            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowIcon(QIcon(self.get_window_icon()))
            msg.setText(
                Translator.get("DIRECT_EDIT_CONFLICT_MESSAGE", [shortname(filename)])
            )
            overwrite = msg.addButton(
                Translator.get("DIRECT_EDIT_CONFLICT_OVERWRITE"), QMessageBox.AcceptRole
            )
            cancel = msg.addButton(
                Translator.get("DIRECT_EDIT_CONFLICT_CANCEL"), QMessageBox.RejectRole
            )

            msg.exec_()
            res = msg.clickedButton()
            if res == overwrite:
                self.manager.direct_edit.force_update(ref, digest)
            del self._conflicts_modals[filename]
        except:
            log.exception(
                "Error while displaying Direct Edit" " conflict modal dialog for %r",
                filename,
            )

    @pyqtSlot(str, dict)
    def _direct_edit_error(self, message: str, values: dict) -> None:
        """ Display a simple Direct Edit error message. """

        msg = QMessageBox()
        msg.setWindowTitle("Direct Edit")
        msg.setWindowIcon(QIcon(self.get_window_icon()))
        msg.setIcon(QMessageBox.Warning)
        msg.setTextFormat(Qt.RichText)
        msg.setText(self.translate(message, values))
        msg.exec_()

    @pyqtSlot()
    def _root_deleted(self) -> None:
        engine = self.sender()
        log.debug("Root has been deleted for engine: %s", engine.uid)

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowIcon(QIcon(self.get_window_icon()))
        msg.setText(Translator.get("DRIVE_ROOT_DELETED", [engine.local_folder]))
        recreate = msg.addButton(
            Translator.get("DRIVE_ROOT_RECREATE"), QMessageBox.AcceptRole
        )
        disconnect = msg.addButton(
            Translator.get("DRIVE_ROOT_DISCONNECT"), QMessageBox.RejectRole
        )

        msg.exec_()
        res = msg.clickedButton()
        if res == disconnect:
            self.manager.unbind_engine(engine.uid)
        elif res == recreate:
            engine.reinit()
            engine.start()

    @pyqtSlot()
    def _no_space_left(self) -> None:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowIcon(QIcon(self.get_window_icon()))
        msg.setText(Translator.get("NO_SPACE_LEFT_ON_DEVICE"))
        msg.addButton(Translator.get("OK"), QMessageBox.AcceptRole)
        msg.exec_()

    @pyqtSlot(str)
    def _root_moved(self, new_path: str) -> None:
        engine = self.sender()
        log.debug("Root has been moved for engine: %s to %r", engine.uid, new_path)
        info = [engine.local_folder, new_path]

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowIcon(QIcon(self.get_window_icon()))
        msg.setText(Translator.get("DRIVE_ROOT_MOVED", info))
        move = msg.addButton(
            Translator.get("DRIVE_ROOT_UPDATE"), QMessageBox.AcceptRole
        )
        recreate = msg.addButton(
            Translator.get("DRIVE_ROOT_RECREATE"), QMessageBox.AcceptRole
        )
        disconnect = msg.addButton(
            Translator.get("DRIVE_ROOT_DISCONNECT"), QMessageBox.RejectRole
        )
        msg.exec_()
        res = msg.clickedButton()

        if res == disconnect:
            self.manager.unbind_engine(engine.uid)
        elif res == recreate:
            engine.reinit()
            engine.start()
        elif res == move:
            engine.set_local_folder(new_path)
            engine.start()

    @pyqtSlot(object)
    def dropped_engine(self, engine: "Engine") -> None:
        # Update icon in case the engine dropped was syncing
        self.change_systray_icon()

    @pyqtSlot()
    def change_systray_icon(self) -> None:
        # Update status has the precedence over other ones
        if self.manager.updater.last_status[0] not in (
            UPDATE_STATUS_UNAVAILABLE_SITE,
            UPDATE_STATUS_UP_TO_DATE,
        ):
            self.set_icon_state("update")
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
            new_state = "error"
            Action(Translator.get("OFFLINE"))
        elif invalid_credentials:
            new_state = "error"
            Action(Translator.get("AUTH_EXPIRED"))
        elif not engines:
            new_state = "disabled"
            Action.finish_action()
        elif paused:
            new_state = "paused"
            Action.finish_action()
        elif syncing:
            new_state = "syncing"
        elif conflict:
            new_state = "conflict"
        else:
            new_state = "idle"
            Action.finish_action()

        self.set_icon_state(new_state)

    @pyqtSlot()
    def show_conflicts_resolution(self, engine: "Engine") -> None:
        conflicts = self.dialogs.get("conflicts")
        if not conflicts:
            from .conflicts import ConflictsView

            conflicts = ConflictsView(self, engine)
            self._create_unique_dialog("conflicts", conflicts)

        conflicts.set_engine(engine)
        self._show_window(conflicts)

    @pyqtSlot()
    def show_settings(self, section: str = "General") -> None:
        settings = self.dialogs.get("settings")
        if not settings:
            from .settings import SettingsView

            settings = SettingsView(self, section)
            self._create_unique_dialog("settings", settings)

        settings.set_section(section)
        self._show_window(settings)

    @pyqtSlot()
    def open_help(self) -> None:
        self.manager.open_help()

    @pyqtSlot()
    def destroyed_filters_dialog(self) -> None:
        self.filters_dlg = None

    @pyqtSlot()
    def show_filters(self, engine: "Engine") -> None:
        if self.filters_dlg:
            self.filters_dlg.close()
            self.filters_dlg = None

        from ..gui.folders_dialog import FiltersDialog

        self.filters_dlg = FiltersDialog(self, engine)
        self.filters_dlg.destroyed.connect(self.destroyed_filters_dialog)
        self.filters_dlg.show()

    def show_file_status(self) -> None:
        from ..gui.status_dialog import StatusDialog

        for _, engine in self.manager.get_engines().items():
            self.status = StatusDialog(engine.get_dao())
            self.status.show()
            break

    def show_activities(self) -> None:
        return
        # TODO: Create activities window
        self.activities.show()

    @pyqtSlot(str, object)
    def _open_authentication_dialog(
        self, url: str, callback_params: Dict[str, str]
    ) -> None:
        settings = self.dialogs.get("settings")
        api = settings.api if settings else QMLSettingsApi(self)
        api = QMLAuthenticationApi(api, callback_params)
        dialog = WebAuthenticationDialog(self, url, api)
        dialog.setWindowModality(Qt.NonModal)
        dialog.show()

    @pyqtSlot(object)
    def _connect_engine(self, engine: "Engine") -> None:
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
    def _debug_toggle_invalid_credentials(self) -> None:
        sender = self.sender()
        engine = sender.data()
        engine.set_invalid_credentials(
            not engine.has_invalid_credentials(), reason="debug"
        )

    @pyqtSlot()
    def _debug_show_file_status(self) -> None:
        from ..gui.status_dialog import StatusDialog

        sender = self.sender()
        engine = sender.data()
        self.status_dialog = StatusDialog(engine.get_dao())
        self.status_dialog.show()

    def _create_debug_engine_menu(self, engine: "Engine", parent: QMenu) -> QMenu:
        menu = QMenu(parent)
        action = QAction(Translator.get("DEBUG_INVALID_CREDENTIALS"), menu)
        action.setCheckable(True)
        action.setChecked(engine.has_invalid_credentials())
        action.setData(engine)
        action.triggered.connect(self._debug_toggle_invalid_credentials)
        menu.addAction(action)
        action = QAction(Translator.get("DEBUG_FILE_STATUS"), menu)
        action.setData(engine)
        action.triggered.connect(self._debug_show_file_status)
        menu.addAction(action)
        return menu

    def create_debug_menu(self, menu: QMenu) -> None:
        menu.addAction(Translator.get("DEBUG_WINDOW"), self.show_debug_window)
        for engine in self.manager.get_engines().values():
            action = QAction(engine.name, menu)
            action.setMenu(self._create_debug_engine_menu(engine, menu))
            action.setData(engine)
            menu.addAction(action)

    @pyqtSlot()
    def show_debug_window(self) -> None:
        return
        debug = self.dialogs.get("debug")
        # TODO: if not debug: Create debug window
        self._show_window(debug)

    def init_checks(self) -> None:
        if Options.debug:
            self.show_debug_window()
        for _, engine in self.manager.get_engines().items():
            self._connect_engine(engine)
        self.manager.newEngine.connect(self._connect_engine)
        self.manager.notification_service.newNotification.connect(
            self._new_notification
        )
        self.manager.updater.updateAvailable.connect(self._update_notification)
        if not self.manager.get_engines():
            self.show_settings()
        else:
            for engine in self.manager.get_engines().values():
                # Prompt for settings if needed
                if engine.has_invalid_credentials():
                    self.show_settings("Accounts_" + engine.uid)
                    break
        self.manager.start()

    @pyqtSlot()
    def _update_notification(self) -> None:
        self.change_systray_icon()

        # Display a notification
        status, version = self.manager.updater.last_status[:2]

        msg = ("AUTOUPDATE_UPGRADE", "AUTOUPDATE_DOWNGRADE")[
            status == UPDATE_STATUS_DOWNGRADE_NEEDED
        ]
        description = Translator.get(msg, [version])
        flags = Notification.FLAG_BUBBLE | Notification.FLAG_UNIQUE
        if LINUX:
            description += " " + Translator.get("AUTOUPDATE_MANUAL")
            flags |= Notification.FLAG_SYSTRAY

        log.warning(description)
        notification = Notification(
            uuid="AutoUpdate",
            flags=flags,
            title=Translator.get("NOTIF_UPDATE_TITLE", [version]),
            description=description,
        )
        self.manager.notification_service.send_notification(notification)

    @pyqtSlot()
    def message_clicked(self) -> None:
        if self.current_notification:
            self.manager.notification_service.trigger_notification(
                self.current_notification.uid
            )

    def _setup_notification_center(self) -> None:
        from ..osi.darwin.pyNotificationCenter import (
            setup_delegator,
            NotificationDelegator,
        )

        if not self._delegator:
            self._delegator = NotificationDelegator.alloc().init()
            self._delegator._manager = self.manager
        setup_delegator(self._delegator)

    @pyqtSlot(object)
    def _new_notification(self, notif: Notification) -> None:
        if not notif.is_bubble():
            return

        if self._delegator is not None:
            # Use notification center
            from ..osi.darwin.pyNotificationCenter import notify

            return notify(
                notif.title, None, notif.description, user_info={"uuid": notif.uid}
            )

        icon = QSystemTrayIcon.Information
        if notif.level == Notification.LEVEL_WARNING:
            icon = QSystemTrayIcon.Warning
        elif notif.level == Notification.LEVEL_ERROR:
            icon = QSystemTrayIcon.Critical

        self.current_notification = notif
        self.tray_icon.showMessage(notif.title, notif.description, icon, 10000)

    def set_icon_state(self, state: str) -> bool:
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

    def get_tooltip(self) -> str:
        actions = Action.get_actions()
        if not actions:
            return self.default_tooltip

        # Display only the first action for now
        for action in actions.values():
            if action and not action.type.startswith("_"):
                break
        else:
            return self.default_tooltip

        if isinstance(action, FileAction):
            if action.get_percent() is not None:
                return "%s - %s - %s - %d%%" % (
                    self.default_tooltip,
                    action.type,
                    action.filename,
                    action.get_percent(),
                )
            return "%s - %s - %s" % (self.default_tooltip, action.type, action.filename)
        elif action.get_percent() is not None:
            return "%s - %s - %d%%" % (
                self.default_tooltip,
                action.type,
                action.get_percent(),
            )

        return "%s - %s" % (self.default_tooltip, action.type)

    def show_release_notes(self, version: str) -> None:
        """ Display release notes of a given version. """

        beta = self.manager.get_beta_channel()
        log.debug("Showing release notes, version=%r beta=%r", version, beta)

        # For now, we do care about beta only
        if not beta:
            return

        url = (
            "https://api.github.com/repos/nuxeo/nuxeo-drive"
            "/releases/tags/release-" + version
        )

        if beta:
            version += " beta"

        try:
            content = requests.get(url)
        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
                log.error("[%s] Release does not exist", version)
            else:
                log.exception(
                    "[%s] Network error while fetching release notes", version
                )
            return
        except:
            log.exception("[%s] Unknown error while fetching release notes", version)
            return

        try:
            data = content.json()
        except ValueError:
            log.exception("[%s] Invalid release notes", version)
            return
        finally:
            del content

        try:
            html = markdown(data["body"])
        except KeyError:
            log.error("[%s] Release notes is missing its body", version)
            return
        except (UnicodeDecodeError, ValueError):
            log.exception("[%s] Release notes conversion error", version)
            return

        dialog = QDialog()
        dialog.setWindowTitle("Drive %s - Release notes" % version)
        dialog.setWindowIcon(QIcon(self.get_window_icon()))

        dialog.resize(600, 400)

        notes = QTextEdit()
        notes.setStyleSheet("background-color: #eee;" "border: none;")
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

    def show_metadata(self, file_path: str) -> None:
        self.manager.ctx_edit_metadata(file_path)

    def setup_systray(self) -> None:
        icons = {}
        for state in {
            "conflict",
            "disabled",
            "error",
            "idle",
            "notification",
            "paused",
            "syncing",
            "update",
        }:
            name = "{}{}.svg".format(state, "_light" if WINDOWS else "")
            icon = QIcon()
            icon.addFile(find_icon(name))
            if MAC:
                icon.addFile(find_icon("active.svg"), mode=QIcon.Selected)
            icons[state] = icon
        setattr(self, "icons", icons)

        self.tray_icon = DriveSystrayIcon(self)
        if not self.tray_icon.isSystemTrayAvailable():
            log.critical("There is no system tray available!")
        else:
            self.tray_icon.setToolTip(self.manager.app_name)
            self.set_icon_state("disabled")
            self.tray_icon.show()

    def event(self, event: "QEvent") -> bool:
        """ Handle URL scheme events under macOS. """

        url = getattr(event, "url", None)
        if not url:
            # This is not an event for us!
            return super().event(event)

        try:
            final_url = unquote(event.url().toString())
            return self._handle_macos_event(final_url)
        except:
            log.exception("Error handling URL event %r", url)
            return False

    def _handle_macos_event(self, url: str) -> bool:
        """ Handle a macOS event URL. """

        info = parse_protocol_url(url)
        if not info:
            return False

        cmd = info["command"]
        path = info.get("filepath", None)
        manager = self.manager

        log.debug("Event URL=%s, info=%r", url, info)

        # Event fired by a context menu item
        func = {
            "access-online": manager.ctx_access_online,
            "copy-share-link": manager.ctx_copy_share_link,
            "edit-metadata": manager.ctx_edit_metadata,
        }.get(cmd, None)
        if func:
            func(path)
        elif "edit" in cmd:
            manager.direct_edit.edit(
                info["server_url"],
                info["doc_id"],
                user=info["user"],
                download_url=info["download_url"],
            )
        elif cmd == "trigger-watch":
            for engine in manager._engine_definitions:
                manager.osi.watch_folder(engine.local_folder)
        else:
            log.warning("Unknown event URL=%r, info=%r", url, info)
            return False
        return True
