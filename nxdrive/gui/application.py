# coding: utf-8
""" Main Qt application handling OS events and system tray UI. """
from logging import getLogger
from math import sqrt
from os import getenv
from typing import Any, Dict, List, Optional, Union
from urllib.parse import unquote

import requests
from markdown import markdown
from PyQt5.QtCore import Qt, QUrl, pyqtSlot, QEvent
from PyQt5.QtGui import QFont, QFontMetricsF, QIcon
from PyQt5.QtQml import QQmlApplicationEngine
from PyQt5.QtQuick import QQuickView, QQuickWindow
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

from ..constants import LINUX, MAC, WINDOWS
from ..engine.activity import Action, FileAction
from ..notification import Notification
from ..options import Options
from ..translator import Translator
from ..updater.constants import (
    UPDATE_STATUS_DOWNGRADE_NEEDED,
    UPDATE_STATUS_UNAVAILABLE_SITE,
    UPDATE_STATUS_UP_TO_DATE,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_UPDATING,
)
from ..utils import find_icon, find_resource, parse_protocol_url, short_name
from .api import QMLDriveApi
from .systray import DriveSystrayIcon, SystrayWindow
from .view import EngineModel, FileModel, LanguageModel


if getenv("NXDRIVE_DEV") == "1":
    from .dev.authentication import auth
else:
    from .authentication import auth


__all__ = ("Application",)

# Enable High-DPI
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

log = getLogger(__name__)


class Application(QApplication):
    """Main Nuxeo Drive application controlled by a system tray icon + menu"""

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

        font = QFont("Helvetica, Arial, sans-serif", 12)
        self.setFont(font)
        self.ratio = sqrt(QFontMetricsF(font).height() / 12)

        self.init_gui()

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

    def init_gui(self) -> None:

        self.api = QMLDriveApi(self)
        self.conflicts_model = FileModel()
        self.engine_model = EngineModel()
        self.file_model = FileModel()
        self.ignoreds_model = FileModel()
        self.language_model = LanguageModel()

        self.add_engines(list(self.manager._engines.values()))
        self.engine_model.statusChanged.connect(self.update_status)
        self.language_model.addLanguages(Translator.languages())

        if WINDOWS:
            self.conflicts_window = QQuickView()
            self.settings_window = QQuickView()
            self.systray_window = QQuickView()

            self._fill_qml_context(self.conflicts_window.rootContext())
            self._fill_qml_context(self.settings_window.rootContext())
            self._fill_qml_context(self.systray_window.rootContext())

            self.conflicts_window.setSource(
                QUrl.fromLocalFile(find_resource("qml", "Conflicts.qml"))
            )
            self.settings_window.setSource(
                QUrl.fromLocalFile(find_resource("qml", "Settings.qml"))
            )
            self.systray_window.setSource(
                QUrl.fromLocalFile(find_resource("qml", "Systray.qml"))
            )
            self.systray_window.setFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Popup
            )
        else:
            self.app_engine = QQmlApplicationEngine()
            self._fill_qml_context(self.app_engine.rootContext())
            self.app_engine.load(QUrl.fromLocalFile(find_resource("qml", "Main.qml")))
            root = self.app_engine.rootObjects()[0]
            self.conflicts_window = root.findChild(QQuickWindow, "conflictsWindow")
            self.settings_window = root.findChild(QQuickWindow, "settingsWindow")
            self.systray_window = root.findChild(SystrayWindow, "systrayWindow")

        self.manager.newEngine.connect(self.add_engines)
        self.manager.initEngine.connect(self.add_engines)
        self.manager.dropEngine.connect(self.remove_engine)
        self._window_root(self.systray_window).getLastFiles.connect(self.get_last_files)
        self.api.setMessage.connect(self._window_root(self.settings_window).setMessage)

        if self.manager.get_engines():
            current_uid = self.engine_model.engines_uid[0]
            self.get_last_files(current_uid)
            self.update_status(self.engine_model.engines[current_uid])

    def add_engines(self, engines: Union["Engine", List["Engine"]]) -> None:
        if not engines:
            return

        engines = engines if isinstance(engines, list) else [engines]
        for engine in engines:
            self.engine_model.addEngine(engine)

    def remove_engine(self, uid: str) -> None:
        self.engine_model.removeEngine(uid)

    def _fill_qml_context(self, context: "QQmlContext") -> None:

        context.setContextProperty("ConflictsModel", self.conflicts_model)
        context.setContextProperty("EngineModel", self.engine_model)
        context.setContextProperty("FileModel", self.file_model)
        context.setContextProperty("IgnoredsModel", self.ignoreds_model)
        context.setContextProperty("languageModel", self.language_model)
        context.setContextProperty("api", self.api)
        context.setContextProperty("application", self)
        context.setContextProperty("currentLanguage", self.current_language())
        context.setContextProperty("manager", self.manager)
        context.setContextProperty("ratio", self.ratio)
        context.setContextProperty("tl", Translator._singleton)
        context.setContextProperty(
            "nuxeoVersionText", "Nuxeo Drive " + self.manager.version
        )
        metrics = self.manager.get_metrics()
        context.setContextProperty(
            "modulesVersionText",
            (
                f'Python {metrics["python_version"]}, '
                f'Qt {metrics["qt_version"]}, '
                f'SIP {metrics["sip_version"]}'
            ),
        )

        colors = {
            "darkBlue": "#1F28BF",
            "nuxeoBlue": "#0066FF",
            "lightBlue": "#00ADED",
            "teal": "#73D2CF",
            "purple": "#8400FF",
            "red": "#C02828",
            "orange": "#FF9E00",
            "darkGray": "#495055",
            "mediumGray": "#7F8284",
            "lightGray": "#BCBFBF",
            "lighterGray": "#F5F5F5",
        }

        for name, value in colors.items():
            context.setContextProperty(name, value)

    def _window_root(self, window):
        if WINDOWS:
            return window.rootObject()
        return window

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
                Translator.get("DIRECT_EDIT_CONFLICT_MESSAGE", [short_name(filename)])
            )
            overwrite = msg.addButton(
                Translator.get("DIRECT_EDIT_CONFLICT_OVERWRITE"), QMessageBox.AcceptRole
            )
            msg.addButton(Translator.get("CANCEL"), QMessageBox.RejectRole)

            msg.exec_()
            res = msg.clickedButton()
            if res == overwrite:
                self.manager.direct_edit.force_update(ref, digest)
            del self._conflicts_modals[filename]
        except:
            log.exception(
                "Error while displaying Direct Edit conflict modal dialog for %r",
                filename,
            )

    @pyqtSlot(str, list)
    def _direct_edit_error(self, message: str, values: List[str]) -> None:
        """ Display a simple Direct Edit error message. """

        msg = QMessageBox()
        msg.setWindowTitle("Direct Edit - {self.manager.app_name}")
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
        self.conflicts_model.empty()
        self.ignoreds_model.empty()

        self.conflicts_model.addFiles(self.api.get_conflicts(engine.uid))
        self.conflicts_model.addFiles(self.api.get_errors(engine.uid))
        self.ignoreds_model.addFiles(self.api.get_unsynchronizeds(engine.uid))

        self._window_root(self.conflicts_window).setEngine.emit(engine.uid)
        self.conflicts_window.show()

    @pyqtSlot()
    def show_settings(self, section: str = "General") -> None:
        sections = {"General": 0, "Accounts": 1, "About": 2}
        self._window_root(self.settings_window).setSection.emit(sections[section])
        self.settings_window.show()

    @pyqtSlot()
    def show_systray(self) -> None:
        icon = self.tray_icon.geometry()

        if not icon or icon.isEmpty():
            # On Ubuntu it's likely we can't retrieve the geometry.
            # We're simply displaying the systray in the top right corner.
            screen = self.desktop().screenGeometry()
            pos_x = screen.right() - self.systray_window.width() - 20
            pos_y = 30
        else:
            pos_x = max(0, icon.x() + icon.width() - self.systray_window.width())
            pos_y = icon.y() - self.systray_window.height()
            if pos_y < 0:
                pos_y = icon.y() + icon.height()

        self.systray_window.setX(pos_x)
        self.systray_window.setY(pos_y)

        self.systray_window.show()
        self.systray_window.raise_()

    @pyqtSlot()
    def hide_systray(self):
        self.systray_window.hide()

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
        self.api._callback_params = callback_params
        auth(self, url)

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
            if action and action.type and not action.type.startswith("_"):
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
        dialog.setWindowTitle(f"{self.manager.app_name} {version} - Release notes")
        dialog.setWindowIcon(QIcon(self.get_window_icon()))

        dialog.resize(600, 400)

        notes = QTextEdit()
        notes.setStyleSheet("background-color: #eee; border: none;")
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

    def event(self, event: QEvent) -> bool:
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

    def update_status(self, engine: "Engine") -> None:
        state = message = submessage = ""

        update_status = self.manager.updater.last_status
        conflicts = engine.get_conflicts()
        errors = engine.get_errors()

        if engine.has_invalid_credentials():
            state = "auth_expired"
        elif update_status[0] == UPDATE_STATUS_DOWNGRADE_NEEDED:
            state = "downgrade"
            message = update_status[1]
            submessage = self.manager.updater.nature
        elif update_status[0] == UPDATE_STATUS_UPDATE_AVAILABLE:
            state = "update"
            message = update_status[1]
            submessage = self.manager.updater.nature
        elif update_status[0] == UPDATE_STATUS_UPDATING:
            state = "updating"
            message = update_status[1]
            submessage = update_status[2]
        elif engine.is_paused():
            state = "suspended"
        elif engine.is_syncing():
            state = "syncing"
        elif conflicts:
            state = "conflicted"
            message = str(len(conflicts))
        elif errors:
            state = "error"
            message = str(len(errors))
        self._window_root(self.systray_window).setStatus.emit(
            state, message, submessage
        )

    @pyqtSlot(str)
    def get_last_files(self, uid: str) -> None:
        files = self.api.get_last_files(uid, 10, "")
        self.file_model.empty()
        self.file_model.addFiles(files)

    def current_language(self) -> Optional[str]:
        lang = Translator.locale()
        for tag, name in self.language_model.languages:
            if tag == lang:
                return name
        return None
