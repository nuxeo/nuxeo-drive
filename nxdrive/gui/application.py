# coding: utf-8
""" Main Qt application handling OS events and system tray UI. """
import os
import sys
from logging import getLogger
from math import sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from urllib.parse import unquote

import requests
from markdown import markdown
from PyQt5.QtCore import Qt, QRect, QTimer, QUrl, pyqtSlot, QEvent
from PyQt5.QtGui import QCursor, QFont, QFontMetricsF, QIcon, QWindow
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtQml import QQmlApplicationEngine, QQmlContext
from PyQt5.QtQuick import QQuickView, QQuickWindow
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
)

from ..constants import (
    APP_NAME,
    BUNDLE_IDENTIFIER,
    COMPANY,
    LINUX,
    MAC,
    TOKEN_PERMISSION,
    WINDOWS,
    DelAction,
)
from ..engine.activity import Action
from ..engine.engine import Engine
from ..gui.folders_dialog import FiltersDialog
from ..notification import Notification
from ..options import Options
from ..translator import Translator
from ..updater.constants import (
    UPDATE_STATUS_INCOMPATIBLE_SERVER,
    UPDATE_STATUS_UNAVAILABLE_SITE,
    UPDATE_STATUS_UP_TO_DATE,
)
from ..utils import (
    find_icon,
    find_resource,
    force_decode,
    get_device,
    if_frozen,
    normalized_path,
    parse_protocol_url,
    short_name,
    normalize_event_filename,
)
from .api import QMLDriveApi
from .systray import DriveSystrayIcon, SystrayWindow
from .view import EngineModel, FileModel, LanguageModel, TransferModel

if MAC:
    from ..osi.darwin.pyNotificationCenter import setup_delegator, NotificationDelegator

if TYPE_CHECKING:
    from ..manager import Manager  # noqa

__all__ = ("Application",)

# Enable High-DPI
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

log = getLogger(__name__)


class Application(QApplication):
    """Main Nuxeo Drive application controlled by a system tray icon + menu"""

    icon = QIcon(str(find_icon("app_icon.svg")))
    icons: Dict[str, QIcon] = {}
    icon_state = None
    use_light_icons = None
    filters_dlg: Optional[FiltersDialog] = None
    _delegator: Optional["NotificationDelegator"] = None
    tray_icon: DriveSystrayIcon

    def __init__(self, manager: "Manager", *args: Any) -> None:
        # This 1st line is needed to fix:
        #   QML Settings: Failed to initialize QSettings instance. Status code is: 1
        #   QML Settings: The following application identifiers have not been set:
        #       QVector("organizationName", "organizationDomain")
        #
        # This affects the locations where Qt WebEngine stores persistent and cached data
        # (even if we do not use it though).
        #
        # See https://bugreports.qt.io/browse/QTBUG-71669
        # and https://codereview.qt-project.org/c/qt/qtwebengine/+/244966
        #
        # The bug happened with PyQt 5.13.0 on Windows.
        QApplication.setOrganizationName(COMPANY)

        super().__init__(list(*args))
        self.manager = manager

        # Used by SyncAndQuitWorker
        self.manager.application = self

        # Little trick here!
        #
        # Qt strongly builds on a concept called event loop.
        # Such an event loop enables you to write parallel applications without multithreading.
        # The concept of event loops is especially useful for applications where
        # a long living process needs to handle interactions from a user or client.
        # Therefore, you often will find event loops being used in GUI or web frameworks.
        #
        # However, the pitfall here is that Qt is implemented in C++ and not in Python.
        # When we execute app.exec_() we start the Qt/C++ event loop, which loops
        # forever until it is stopped.
        #
        # The problem here is that we don't have any Python events set up yet.
        # So our event loop never churns the Python interpreter and so our signal
        # delivered to the Python process is never processed. Therefore, our
        # Python process never sees the signal until we hit some button of
        # our Qt application window.
        #
        # To circumvent this problem is very easy. We just need to set up a timer
        # kicking off our event loop every few milliseconds.
        #
        # https://machinekoder.com/how-to-not-shoot-yourself-in-the-foot-using-python-qt/
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: None)
        self.timer.start(100)

        self.osi = self.manager.osi
        self.setWindowIcon(self.icon)
        self.setApplicationName(APP_NAME)
        self._init_translator()
        self.setQuitOnLastWindowClosed(False)

        self.ask_for_metrics_approval()

        self._conflicts_modals: Dict[str, bool] = dict()
        self.current_notification: Optional[Notification] = None
        self.default_tooltip = APP_NAME

        font = QFont("Helvetica, Arial, sans-serif", 12)
        self.setFont(font)
        self.ratio = sqrt(QFontMetricsF(font).height() / 12)

        self.init_gui()

        self.manager.dropEngine.connect(self.dropped_engine)

        self.setup_systray()
        self.manager.reloadIconsSet.connect(self.load_icons_set)

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
        self.manager.updater.serverIncompatible.connect(self._server_incompatible)
        self.manager.updater.wrongChannel.connect(self._wrong_channel)

        # Display release notes on new version
        if self.manager.old_version != self.manager.version:
            self.show_release_notes(self.manager.version)

        # Listen for nxdrive:// sent by a new instance
        self.init_nxdrive_listener()

        # Connect this slot last so the other slots connected
        # to self.aboutToQuit can run beforehand.
        self.aboutToQuit.connect(self.manager.stop)

    @if_frozen
    def add_qml_import_path(self, view: QQuickView) -> None:
        """
        Manually set the path to the QML folder to fix errors with unicode paths.
        This is needed only on Windows when packaged with Nuitka.
        """
        if Options.freezer != "nuitka":
            return

        qml_dir = Options.res_dir.parent / "PyQt5" / "Qt" / "qml"
        log.debug(f"Setting QML import path for {view} to {qml_dir!r}")
        view.engine().addImportPath(str(qml_dir))

    def init_gui(self) -> None:

        self.api = QMLDriveApi(self)
        self.conflicts_model = FileModel(self.translate)
        self.errors_model = FileModel(self.translate)
        self.engine_model = EngineModel(self)
        self.transfer_model = TransferModel(self.translate)
        self.file_model = FileModel(self.translate)
        self.ignoreds_model = FileModel(self.translate)
        self.language_model = LanguageModel()

        self.add_engines(list(self.manager.engines.values()))
        self.engine_model.statusChanged.connect(self.update_status)
        self.language_model.addLanguages(Translator.languages())

        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint

        if WINDOWS:
            self.conflicts_window = QQuickView()
            self.add_qml_import_path(self.conflicts_window)
            self.conflicts_window.setMinimumWidth(550)
            self.conflicts_window.setMinimumHeight(600)
            self.settings_window = QQuickView()
            self.add_qml_import_path(self.settings_window)
            self.systray_window = SystrayWindow()
            self.add_qml_import_path(self.systray_window)

            self._fill_qml_context(self.conflicts_window.rootContext())
            self._fill_qml_context(self.settings_window.rootContext())
            self._fill_qml_context(self.systray_window.rootContext())
            self.systray_window.rootContext().setContextProperty(
                "systrayWindow", self.systray_window
            )

            self.conflicts_window.setSource(
                QUrl.fromLocalFile(str(find_resource("qml", "Conflicts.qml")))
            )
            self.settings_window.setSource(
                QUrl.fromLocalFile(str(find_resource("qml", "Settings.qml")))
            )
            self.systray_window.setSource(
                QUrl.fromLocalFile(str(find_resource("qml", "Systray.qml")))
            )
            flags |= Qt.Popup
        else:
            self.app_engine = QQmlApplicationEngine()
            self._fill_qml_context(self.app_engine.rootContext())
            self.app_engine.load(
                QUrl.fromLocalFile(str(find_resource("qml", "Main.qml")))
            )
            root = self.app_engine.rootObjects()[0]
            self.conflicts_window = root.findChild(QQuickWindow, "conflictsWindow")
            self.settings_window = root.findChild(QQuickWindow, "settingsWindow")
            self.systray_window = root.findChild(SystrayWindow, "systrayWindow")
            if LINUX:
                flags |= Qt.Drawer

        self.systray_window.setFlags(flags)

        self.manager.newEngine.connect(self.add_engines)
        self.manager.initEngine.connect(self.add_engines)
        self.manager.dropEngine.connect(self.remove_engine)
        self._window_root(self.conflicts_window).changed.connect(self.refresh_conflicts)
        self._window_root(self.systray_window).appUpdate.connect(self.api.app_update)
        self._window_root(self.systray_window).getLastFiles.connect(self.get_last_files)
        self.api.setMessage.connect(self._window_root(self.settings_window).setMessage)

        if self.manager.engines:
            current_uid = self.engine_model.engines_uid[0]
            self.get_last_files(current_uid)
            self.refresh_transfers()
            self.update_status(self.manager.engines[current_uid])

        self.manager.updater.updateAvailable.connect(
            self._window_root(self.systray_window).updateAvailable
        )
        self.manager.updater.updateProgress.connect(
            self._window_root(self.systray_window).updateProgress
        )

    @pyqtSlot(object)
    def action_progressing(self, action: Action) -> None:
        if not isinstance(action, Action):
            log.warning(f"An action is needed, got {action!r}")
            return
        self.transfer_model.set_progress(action.export())

    def add_engines(self, engines: Union[Engine, List[Engine]]) -> None:
        if not engines:
            return

        engines = engines if isinstance(engines, list) else [engines]
        for engine in engines:
            self.engine_model.addEngine(engine.uid)

    def remove_engine(self, uid: str) -> None:
        self.engine_model.removeEngine(uid)

    def _fill_qml_context(self, context: QQmlContext) -> None:
        """ Fill the context of a QML element with the necessary resources. """
        context.setContextProperty("ConflictsModel", self.conflicts_model)
        context.setContextProperty("ErrorsModel", self.errors_model)
        context.setContextProperty("EngineModel", self.engine_model)
        context.setContextProperty("TransferModel", self.transfer_model)
        context.setContextProperty("FileModel", self.file_model)
        context.setContextProperty("IgnoredsModel", self.ignoreds_model)
        context.setContextProperty("languageModel", self.language_model)
        context.setContextProperty("api", self.api)
        context.setContextProperty("application", self)
        context.setContextProperty("currentLanguage", self.current_language())
        context.setContextProperty("manager", self.manager)
        context.setContextProperty("osi", self.osi)
        context.setContextProperty("updater", self.manager.updater)
        context.setContextProperty("ratio", self.ratio)
        context.setContextProperty("update_check_delay", Options.update_check_delay)
        context.setContextProperty("isFrozen", Options.is_frozen)
        context.setContextProperty("WINDOWS", WINDOWS)
        context.setContextProperty("tl", Translator.singleton)
        context.setContextProperty(
            "nuxeoVersionText", f"{APP_NAME} {self.manager.version}"
        )
        metrics = self.manager.get_metrics()
        versions = (
            f'Python {metrics["python_version"]}, '
            f'Qt {metrics["qt_version"]}, '
            f'SIP {metrics["sip_version"]}'
        )
        if Options.system_wide:
            versions += " [admin]"
        context.setContextProperty("modulesVersionText", versions)

        colors = {
            "darkBlue": "#1F28BF",
            "nuxeoBlue": "#0066FF",
            "lightBlue": "#00ADED",
            "lightGreen": "#A9D843",
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

    def translate(self, message: str, values: List[Any] = None) -> str:
        return Translator.get(message, values)

    def _show_window(self, window: QWindow) -> None:
        window.show()
        window.raise_()
        window.requestActivate()

    def _init_translator(self) -> None:
        locale = Options.force_locale or Options.locale
        Translator(find_resource("i18n"), self.manager.get_config("locale", locale))
        # Make sure that a language change changes external values like
        # the text in the contextual menu
        Translator.on_change(self._handle_language_change)
        # Trigger it now
        self.osi.register_contextual_menu()
        self.installTranslator(Translator.singleton)

    @pyqtSlot(str, Path, str)
    def _direct_edit_conflict(self, filename: str, ref: Path, digest: str) -> None:
        log.debug(f"Entering _direct_edit_conflict for {filename!r} / {ref!r}")
        try:
            if filename in self._conflicts_modals:
                log.debug(f"Filename already in _conflicts_modals: {filename!r}")
                return
            log.debug(f"Putting filename in _conflicts_modals: {filename!r}")
            self._conflicts_modals[filename] = True

            msg = QMessageBox()
            msg.setInformativeText(
                Translator.get("DIRECT_EDIT_CONFLICT_MESSAGE", [short_name(filename)])
            )
            overwrite = msg.addButton(
                Translator.get("DIRECT_EDIT_CONFLICT_OVERWRITE"), QMessageBox.AcceptRole
            )
            msg.addButton(Translator.get("CANCEL"), QMessageBox.RejectRole)
            msg.setIcon(QMessageBox.Warning)
            msg.exec_()
            if msg.clickedButton() == overwrite:
                self.manager.direct_edit.force_update(ref, digest)
            del self._conflicts_modals[filename]
        except Exception:
            log.exception(
                f"Error while displaying Direct Edit conflict modal dialog for {filename!r}"
            )

    @pyqtSlot(str, list)
    def _direct_edit_error(self, message: str, values: List[str]) -> None:
        """ Display a simple Direct Edit error message. """
        msg_text = self.translate(message, values)
        log.warning(f"DirectEdit error message: '{msg_text}', values={values}")
        msg = QMessageBox()
        msg.setWindowTitle(f"Direct Edit - {APP_NAME}")
        msg.setWindowIcon(self.icon)
        msg.setIcon(QMessageBox.Warning)
        msg.setTextFormat(Qt.RichText)
        msg.setText(msg_text)
        msg.exec_()

    @pyqtSlot()
    def _root_deleted(self) -> None:
        engine = self.sender()
        log.info(f"Root has been deleted for engine: {engine.uid}")

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowIcon(self.icon)
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
        msg.setWindowIcon(self.icon)
        msg.setText(Translator.get("NO_SPACE_LEFT_ON_DEVICE"))
        msg.addButton(Translator.get("OK"), QMessageBox.AcceptRole)
        msg.exec_()

    @pyqtSlot(Path)
    def _root_moved(self, new_path: Path) -> None:
        engine = self.sender()
        log.info(f"Root has been moved for engine: {engine.uid} to {new_path!r}")
        info = [engine.local_folder, str(new_path)]

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowIcon(self.icon)
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

    def confirm_deletion(self, path: Path) -> DelAction:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Question)
        msg.setWindowIcon(self.icon)

        cb = QCheckBox(Translator.get("DONT_ASK_AGAIN"))
        msg.setCheckBox(cb)

        mode = self.manager.get_deletion_behavior()
        unsync = None
        if mode is DelAction.DEL_SERVER:
            descr = "DELETION_BEHAVIOR_CONFIRM_DELETE"
            confirm_text = "DELETE_FOR_EVERYONE"
            unsync = msg.addButton(
                Translator.get("JUST_UNSYNC"), QMessageBox.RejectRole
            )
        elif mode is DelAction.UNSYNC:
            descr = "DELETION_BEHAVIOR_CONFIRM_UNSYNC"
            confirm_text = "UNSYNC"

        msg.setText(
            Translator.get(descr, [str(path), Translator.get("SELECT_SYNC_FOLDERS")])
        )
        msg.addButton(Translator.get("CANCEL"), QMessageBox.RejectRole)
        confirm = msg.addButton(Translator.get(confirm_text), QMessageBox.AcceptRole)
        msg.exec_()

        res = msg.clickedButton()
        if cb.isChecked():
            self.manager.dao.store_bool("show_deletion_prompt", False)

        if res == confirm:
            return mode
        if res == unsync:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Question)
            msg.setWindowIcon(self.icon)
            msg.setText(Translator.get("DELETION_BEHAVIOR_SWITCH"))
            msg.addButton(Translator.get("NO"), QMessageBox.RejectRole)
            confirm = msg.addButton(Translator.get("YES"), QMessageBox.AcceptRole)
            msg.exec_()
            res = msg.clickedButton()
            if res == confirm:
                self.manager.set_deletion_behavior(DelAction.UNSYNC)
            return DelAction.UNSYNC
        return DelAction.ROLLBACK

    @pyqtSlot(Path)
    def _doc_deleted(self, path: Path) -> None:
        engine: Engine = self.sender()
        mode = self.confirm_deletion(path)

        if mode is DelAction.ROLLBACK:
            # Re-sync the document
            engine.rollback_delete(path)
        else:
            # Delete or filter out the document
            engine.delete_doc(path, mode)

    @pyqtSlot(Path, Path)
    def _file_already_exists(self, oldpath: Path, newpath: Path) -> None:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowIcon(self.icon)
        msg.setText(Translator.get("FILE_ALREADY_EXISTS", values=[str(oldpath)]))
        replace = msg.addButton(Translator.get("REPLACE"), QMessageBox.AcceptRole)
        msg.addButton(Translator.get("CANCEL"), QMessageBox.RejectRole)
        msg.exec_()
        if msg.clickedButton() == replace:
            oldpath.unlink()
            normalize_event_filename(newpath)
        else:
            newpath.unlink()

    @pyqtSlot(object)
    def dropped_engine(self, engine: Engine) -> None:
        # Update icon in case the engine dropped was syncing
        self.change_systray_icon()

    @pyqtSlot()
    def change_systray_icon(self) -> None:
        # Update status has the precedence over other ones
        if self.manager.updater.status not in (
            UPDATE_STATUS_UNAVAILABLE_SITE,
            UPDATE_STATUS_UP_TO_DATE,
        ):
            self.set_icon_state("update")
            return

        syncing = conflict = False
        engines = self.manager.engines
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

    def refresh_conflicts(self, uid: str) -> None:
        """ Update the content of the conflicts/errors window. """
        self.conflicts_model.empty()
        self.errors_model.empty()
        self.ignoreds_model.empty()

        self.conflicts_model.addFiles(self.api.get_conflicts(uid))
        self.errors_model.addFiles(self.api.get_errors(uid))
        self.ignoreds_model.addFiles(self.api.get_unsynchronizeds(uid))

    @pyqtSlot()
    def show_conflicts_resolution(self, engine: Engine) -> None:
        """ Display the conflicts/errors window. """
        self.refresh_conflicts(engine.uid)
        self._window_root(self.conflicts_window).setEngine.emit(engine.uid)
        self.conflicts_window.show()
        self.conflicts_window.requestActivate()

    @pyqtSlot()
    def show_settings(self, section: str = "General") -> None:
        sections = {"General": 0, "Accounts": 1, "About": 2}
        self._window_root(self.settings_window).setSection.emit(sections[section])
        self.settings_window.show()
        self.settings_window.requestActivate()

    @pyqtSlot()
    def show_systray(self) -> None:
        icon = self.tray_icon.geometry()

        if not icon or icon.isEmpty():
            # On some GNU/Linux flavor it's likely we can't retrieve the geometry.
            # We're simply displaying the systray at the cursor position.
            cur = QCursor.pos()
            icon = QRect(cur.x(), cur.y(), 16, 16)

        # Adjust the position
        dpi_ratio = self.primaryScreen().devicePixelRatio() if WINDOWS else 1
        pos_x = max(
            0, (icon.x() + icon.width()) / dpi_ratio - self.systray_window.width()
        )
        pos_y = icon.y() / dpi_ratio - self.systray_window.height()
        if pos_y < 0:
            pos_y = (icon.y() + icon.height()) / dpi_ratio

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
    def show_filters(self, engine: Engine) -> None:
        if self.filters_dlg:
            self.filters_dlg.close()
            self.filters_dlg = None

        self.filters_dlg = FiltersDialog(self, engine)
        self.filters_dlg.destroyed.connect(self.destroyed_filters_dialog)

        # Close the settings window at the same time of the filters one
        if hasattr(self, "close_settings_too"):
            self.filters_dlg.destroyed.connect(self.settings_window.close)
            delattr(self, "close_settings_too")

        self.filters_dlg.show()
        self._show_window(self.settings_window)

    @pyqtSlot(str, object)
    def open_authentication_dialog(
        self, url: str, callback_params: Dict[str, str]
    ) -> None:
        self.api.callback_params = callback_params
        if Options.is_frozen:
            """
            Authenticate through the browser.

            This authentication requires the server's Nuxeo Drive addon to include
            NXP-25519. Instead of opening the server's login page in a WebKit view
            through the app, it opens in the browser and retrieves the login token
            by opening an nxdrive:// URL.
            """
            self.manager.open_local_file(url)
        else:
            self._web_auth_not_frozen(url)

    def _web_auth_not_frozen(self, url: str) -> None:
        """
        Open a dialog box to fill the credentials.
        Then a request will be done using the Python client to
        get a token.

        This is used when the application is not frozen as there is no custom
        protocol handler in this case.
        """

        from PyQt5.QtWidgets import QLineEdit
        from nuxeo.client import Nuxeo

        dialog = QDialog()
        dialog.setWindowTitle(self.translate("WEB_AUTHENTICATION_WINDOW_TITLE"))
        dialog.setWindowIcon(self.icon)
        dialog.resize(250, 100)

        layout = QVBoxLayout()

        username = QLineEdit("Administrator", parent=dialog)
        password = QLineEdit("Administrator", parent=dialog)
        password.setEchoMode(QLineEdit.Password)
        layout.addWidget(username)
        layout.addWidget(password)

        def auth() -> None:
            """Retrieve a token and create the account."""
            user = str(username.text())
            pwd = str(password.text())
            nuxeo = Nuxeo(
                host=url,
                auth=(user, pwd),
                proxies=self.manager.proxy.settings(url=url),
                verify=Options.ca_bundle or not Options.ssl_no_verify,
            )
            try:
                token = nuxeo.client.request_auth_token(
                    device_id=self.manager.device_id,
                    app_name=APP_NAME,
                    permission=TOKEN_PERMISSION,
                    device=get_device(),
                )
            except Exception as exc:
                log.error(f"Connection error: {exc}")
                token = ""
            finally:
                del nuxeo

            # Check we have a token and not a HTML response
            if "\n" in token:
                token = ""

            self.api.handle_token(token, user)
            dialog.close()

        buttons = QDialogButtonBox()
        buttons.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(auth)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)

        dialog.setLayout(layout)
        dialog.exec_()

    @pyqtSlot(object)
    def _connect_engine(self, engine: Engine) -> None:
        engine.syncStarted.connect(self.change_systray_icon)
        engine.syncCompleted.connect(self.change_systray_icon)
        engine.invalidAuthentication.connect(self.change_systray_icon)
        engine.syncSuspended.connect(self.change_systray_icon)
        engine.syncResumed.connect(self.change_systray_icon)
        engine.offline.connect(self.change_systray_icon)
        engine.online.connect(self.change_systray_icon)
        engine.rootDeleted.connect(self._root_deleted)
        engine.rootMoved.connect(self._root_moved)
        engine.docDeleted.connect(self._doc_deleted)
        engine.fileAlreadyExists.connect(self._file_already_exists)
        engine.noSpaceLeftOnDevice.connect(self._no_space_left)
        engine.newSyncStarted.connect(self.refresh_files)
        engine.newSyncEnded.connect(self.refresh_files)
        engine.dao.transferUpdated.connect(self.refresh_transfers)
        self.change_systray_icon()

    def init_checks(self) -> None:
        for engine in self.manager.engines.copy().values():
            self._connect_engine(engine)

        self.manager.newEngine.connect(self._connect_engine)
        self.manager.notification_service.newNotification.connect(
            self._new_notification
        )
        self.manager.notification_service.triggerNotification.connect(
            self._handle_notification_action
        )
        self.manager.updater.updateAvailable.connect(self._update_notification)
        self.manager.updater.noSpaceLeftOnDevice.connect(self._no_space_left)

        if not self.manager.engines:
            self.show_settings("Accounts")
        else:
            for engine in self.manager.engines.copy().values():
                # Prompt for settings if needed
                if engine.has_invalid_credentials():
                    self.show_settings("Accounts")  # f"Account_{engine.uid}"
                    break

        self.manager.start()

    @pyqtSlot()
    @if_frozen
    def _update_notification(self) -> None:
        self.change_systray_icon()

        # Display a notification
        status, version = self.manager.updater.status, self.manager.updater.version

        msg = ("AUTOUPDATE_UPGRADE", "AUTOUPDATE_DOWNGRADE")[
            status == UPDATE_STATUS_INCOMPATIBLE_SERVER
        ]
        description = Translator.get(msg, [version])
        flags = Notification.FLAG_BUBBLE | Notification.FLAG_UNIQUE

        log.warning(description)
        notification = Notification(
            uuid="AutoUpdate",
            flags=flags,
            title=Translator.get("NOTIF_UPDATE_TITLE", [version]),
            description=description,
        )
        self.manager.notification_service.send_notification(notification)

    @pyqtSlot()
    def _server_incompatible(self) -> None:
        version = self.manager.version
        downgrade_version = self.manager.updater.version or ""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowIcon(self.icon)
        msg.setText(Translator.get("SERVER_INCOMPATIBLE", [version, downgrade_version]))
        if downgrade_version:
            msg.addButton(
                Translator.get("CONTINUE_USING", [version]), QMessageBox.RejectRole
            )
            downgrade = msg.addButton(
                Translator.get("DOWNGRADE_TO", [downgrade_version]),
                QMessageBox.AcceptRole,
            )
        else:
            msg.addButton(Translator.get("CONTINUE"), QMessageBox.RejectRole)
        msg.exec_()

        res = msg.clickedButton()
        if downgrade_version and res == downgrade:
            self.manager.updater.update(downgrade_version)

    @pyqtSlot()
    def _wrong_channel(self) -> None:
        if self.manager.prompted_wrong_channel:
            log.debug(
                "Not prompting for wrong channel, already showed it since startup"
            )
            return
        self.manager.prompted_wrong_channel = True

        version = self.manager.version
        downgrade_version = self.manager.updater.version or ""
        version_channel = self.manager.updater.get_version_channel(version)
        current_channel = self.manager.get_update_channel()
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowIcon(self.icon)
        msg.setText(
            Translator.get("WRONG_CHANNEL", [version, version_channel, current_channel])
        )
        switch_channel = msg.addButton(
            Translator.get("USE_CHANNEL", [version_channel]), QMessageBox.AcceptRole
        )
        downgrade = msg.addButton(
            Translator.get("DOWNGRADE_TO", [downgrade_version]), QMessageBox.AcceptRole
        )
        msg.exec_()

        res = msg.clickedButton()
        if downgrade_version and res == downgrade:
            self.manager.updater.update(downgrade_version)
        elif res == switch_channel:
            self.manager.set_update_channel(version_channel)

    @pyqtSlot()
    def message_clicked(self) -> None:
        if self.current_notification:
            self.manager.notification_service.trigger_notification(
                self.current_notification.uid
            )

    def _setup_notification_center(self) -> None:
        if not self._delegator:
            self._delegator = NotificationDelegator.alloc().init()
            if self._delegator:
                self._delegator.manager = self.manager
        setup_delegator(self._delegator)

    @pyqtSlot(object)
    def _new_notification(self, notif: Notification) -> None:
        if not notif.is_bubble():
            return

        if self._delegator is not None:
            # Use notification center
            from ..osi.darwin.pyNotificationCenter import notify

            user_info = {"uuid": notif.uid} if notif.uid else None

            return notify(notif.title, "", notif.description, user_info=user_info)

        icon = QSystemTrayIcon.Information
        if notif.level == Notification.LEVEL_WARNING:
            icon = QSystemTrayIcon.Warning
        elif notif.level == Notification.LEVEL_ERROR:
            icon = QSystemTrayIcon.Critical

        self.current_notification = notif
        self.tray_icon.showMessage(notif.title, notif.description, icon, 10000)

    @pyqtSlot(str, str)
    def _handle_notification_action(self, action: str, engine_uid: str) -> None:
        func = getattr(self.api, action, None)
        if not func:
            log.error(f"Action {action}() is not defined in {self.api}")
            return
        func(engine_uid)

    def set_icon_state(self, state: str, force: bool = False) -> bool:
        """
        Execute systray icon change operations triggered by state change.

        The synchronization thread can update the state info but cannot
        directly call QtGui widget methods. This should be executed by the main
        thread event loop, hence the delegation to this method that is
        triggered by a signal to allow for message passing between the 2
        threads.

        Return True of the icon has changed state or if force is True.
        """

        if not force and self.icon_state == state:
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

        return f"{self.default_tooltip} - {action!r}"

    @if_frozen
    def show_release_notes(self, version: str) -> None:
        """ Display release notes of a given version. """

        channel = self.manager.get_update_channel()
        log.info(f"Showing release notes, version={version!r} channel={channel}")

        # For now, we do care about beta only
        if channel != "beta":
            return

        url = (
            "https://api.github.com/repos/nuxeo/nuxeo-drive"
            f"/releases/tags/release-{version}"
        )

        if channel != "release":
            version += f" {channel}"

        try:
            # No need for the `verify` kwarg here as GitHub will never use a bad certificate.
            with requests.get(url) as resp:
                data = resp.json()
                html = markdown(data["body"])
        except Exception:
            log.warning(f"[{version}] Release notes retrieval error")
            return

        dialog = QDialog()
        dialog.setWindowTitle(Translator.get("RELEASE_NOTES_TITLE", [APP_NAME]))
        dialog.setWindowIcon(self.icon)

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

    def accept_unofficial_ssl_cert(self, hostname: str) -> bool:
        """Ask the user to bypass the SSL certificate verification."""
        from ..utils import get_certificate_details

        def signature(sig: str) -> str:
            """
            Format the certificate signature.

                >>> signature("0F4019D1E6C52EF9A3A929B6D5613816")
                0f:40:19:d1:e6:c5:2e:f9:a3:a9:29:b6:d5:61:38:16

            """
            from textwrap import wrap

            return str.lower(":".join(wrap(sig, 2)))

        cert = get_certificate_details(hostname=hostname)
        if not cert:
            return False

        subject = [
            f"<li>{details[0][0]}: {details[0][1]}</li>"
            for details in sorted(cert["subject"])
        ]
        issuer = [
            f"<li>{details[0][0]}: {details[0][1]}</li>"
            for details in sorted(cert["issuer"])
        ]
        urls = [
            f"<li><a href='{details}'>{details}</a></li>"
            for details in cert["caIssuers"]
        ]
        sig = f"<code><small>{signature(cert['serialNumber'])}</small></code>"
        message = f"""
<h2>{Translator.get("SSL_CANNOT_CONNECT", [hostname])}</h2>
<p style="color:red">{Translator.get("SSL_HOSTNAME_ERROR")}</p>

<h2>{Translator.get("SSL_CERTIFICATE")}</h2>
<ul>
    {"".join(subject)}
    <li style="margin-top: 10px;">{Translator.get("SSL_SERIAL_NUMBER")} {sig}</li>
    <li style="margin-top: 10px;">{Translator.get("SSL_DATE_FROM")} {cert["notBefore"]}</li>
    <li>{Translator.get("SSL_DATE_EXPIRATION")} {cert["notAfter"]}</li>
</ul>

<h2>{Translator.get("SSL_ISSUER")}</h2>
<ul style="list-style-type:square;">{"".join(issuer)}</ul>

<h2>{Translator.get("URL")}</h2>
<ul>{"".join(urls)}</ul>
"""

        dialog = QDialog()
        dialog.setWindowTitle(Translator.get("SSL_UNTRUSTED_CERT_TITLE"))
        dialog.setWindowIcon(self.icon)
        dialog.resize(600, 650)

        notes = QTextEdit()
        notes.setReadOnly(True)
        notes.setHtml(message)

        continue_with_bad_ssl_cert = False

        def accept() -> None:
            nonlocal continue_with_bad_ssl_cert
            continue_with_bad_ssl_cert = True
            dialog.accept()

        buttons = QDialogButtonBox()
        buttons.setStandardButtons(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.close)

        def bypass_triggered(state: int) -> None:
            """Enable the OK button only when the checkbox is checked."""
            buttons.button(QDialogButtonBox.Ok).setEnabled(bool(state))

        bypass = QCheckBox(Translator.get("SSL_TRUST_ANYWAY"))
        bypass.stateChanged.connect(bypass_triggered)

        layout = QVBoxLayout()
        layout.addWidget(notes)
        layout.addWidget(bypass)
        layout.addWidget(buttons)
        dialog.setLayout(layout)
        dialog.exec_()

        return continue_with_bad_ssl_cert

    def show_metadata(self, path: Path) -> None:
        self.manager.ctx_edit_metadata(path)

    @pyqtSlot(bool)
    def load_icons_set(self, use_light_icons: bool = False) -> None:
        """Load a given icons set (either the default one "dark", or the light one)."""
        if self.use_light_icons is use_light_icons:
            return

        suffix = ("", "_light")[use_light_icons]
        mask = str(find_icon("active.svg"))  # Icon mask for macOS
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
            icon = QIcon()
            icon.addFile(str(find_icon(f"{state}{suffix}.svg")))
            if MAC:
                icon.addFile(mask, mode=QIcon.Selected)
            self.icons[state] = icon

        self.use_light_icons = use_light_icons
        self.manager.set_config("light_icons", use_light_icons)

        # Reload the current showed icon
        if self.icon_state:
            self.set_icon_state(self.icon_state, force=True)

    def initial_icons_set(self) -> bool:
        """
        Try to guess the most appropriate icons set at start.
        The user will still have the possibility to change that in Settings.
        """
        use_light_icons = self.manager.get_config("light_icons", default=None)

        if use_light_icons is None:
            # Default value for GNU/Linux, macOS ans Windows 7
            use_light_icons = False

            if WINDOWS:
                win_ver = sys.getwindowsversion()
                version = (win_ver.major, win_ver.minor)
                if version > (6, 1):  # Windows 7
                    # Windows 8+ has a dark them by default
                    use_light_icons = True
            elif MAC and self.osi.dark_mode_in_use():
                # The Dark mode on macOS is set
                use_light_icons = True
        else:
            # The value stored in DTB as a string '0' or '1', convert to boolean
            use_light_icons = bool(int(use_light_icons))

        return use_light_icons

    def setup_systray(self) -> None:
        """Setup the icon system tray and its associated menu."""
        self.load_icons_set(use_light_icons=self.initial_icons_set())

        self.tray_icon = DriveSystrayIcon(self)
        if not self.tray_icon.isSystemTrayAvailable():
            log.critical("There is no system tray available!")
        else:
            self.tray_icon.setToolTip(APP_NAME)
            self.set_icon_state("disabled")
            self.tray_icon.show()

    def _handle_language_change(self) -> None:
        self.manager.set_config("locale", Translator.locale())
        if not MAC:
            self.tray_icon.setContextMenu(self.tray_icon.get_context_menu())
        self.osi.register_contextual_menu()

    def event(self, event: QEvent) -> bool:
        """ Handle URL scheme events under macOS. """
        url = getattr(event, "url", None)
        if not url:
            # This is not an event for us!
            return super().event(event)

        final_url = unquote(event.url().toString())
        try:
            return self._handle_nxdrive_url(final_url)
        except Exception:
            log.exception(f"Error handling URL event {final_url!r}")
            return False

    def _show_msgbox_restart_needed(self) -> None:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText(Translator.get("RESTART_NEEDED_MSG", values=[APP_NAME]))
        msg.setWindowTitle(APP_NAME)
        msg.addButton(Translator.get("OK"), QMessageBox.AcceptRole)
        msg.exec_()

    @pyqtSlot(result=str)
    def _nxdrive_url_env(self) -> str:
        """Get the NXDRIVE_URL envar value, empty string if not defined."""
        return os.getenv("NXDRIVE_URL", "")

    @pyqtSlot(str, result=bool)
    def _handle_nxdrive_url(self, url: str) -> bool:
        """ Handle an nxdrive protocol URL. """

        info = parse_protocol_url(url)
        if not info:
            return False

        cmd = info["command"]
        path = normalized_path(info.get("filepath", ""))
        manager = self.manager

        log.info(f"Event URL={url}, info={info!r}")

        # Event fired by a context menu item
        func = {
            "access-online": manager.ctx_access_online,
            "copy-share-link": manager.ctx_copy_share_link,
            "edit-metadata": manager.ctx_edit_metadata,
        }.get(cmd, None)
        if func:
            func(path)
        elif "edit" in cmd:
            if self.manager.restart_needed:
                self._show_msgbox_restart_needed()
                return False

            manager.directEdit.emit(
                info["server_url"], info["doc_id"], info["user"], info["download_url"]
            )
        elif cmd == "token":
            self.api.handle_token(info["token"], info["username"])
        else:
            log.warning(f"Unknown event URL={url}, info={info!r}")
            return False
        return True

    def init_nxdrive_listener(self) -> None:
        """
        Set up a QLocalServer to listen to nxdrive protocol calls.

        On Windows, when an nxdrive:// URL is opened, it creates a new
        instance of Nuxeo Drive. As we want the already running instance to
        receive this call (particularly during the login process), we set
        up a QLocalServer in that instance to listen to the new ones who will
        send their data.
        The Qt implementation of QLocalSocket on Windows makes use of named
        pipes. We just need to connect a handler to the newConnection signal
        to process the URLs.
        """
        named_pipe = f"{BUNDLE_IDENTIFIER}.protocol.{os.getpid()}"
        server = QLocalServer()
        server.setSocketOptions(QLocalServer.WorldAccessOption)
        server.newConnection.connect(self._handle_connection)
        try:
            server.listen(named_pipe)
            log.info(f"Listening for nxdrive:// calls on {server.fullServerName()}")
        except Exception:
            log.info(
                f"Unable to start local server on {named_pipe}: {server.errorString()}"
            )

        self._nxdrive_listener = server
        self.aboutToQuit.connect(self._nxdrive_listener.close)

    def _handle_connection(self) -> None:
        """ Retrieve the connection with other instances and handle the incoming data. """

        con: QLocalSocket = None
        try:
            con = self._nxdrive_listener.nextPendingConnection()
            log.info("Receiving socket connection for nxdrive protocol handling")
            if not con or not con.waitForConnected():
                log.error(f"Unable to open server socket: {con.errorString()}")
                return

            if con.waitForReadyRead():
                payload = con.readAll()
                url = force_decode(payload.data())
                self._handle_nxdrive_url(url)

            con.disconnectFromServer()
            if con.state() == QLocalSocket.ConnectedState:
                con.waitForDisconnected()
        finally:
            del con
        log.info("Successfully closed server socket")

    def update_status(self, engine: Engine) -> None:
        """
        Update the systray status for synchronization,
        conflicts/errors and software updates.
        """
        sync_state = error_state = update_state = ""

        if not isinstance(engine, Engine):
            log.error(f"Need an Engine, got {engine!r}")
            return

        update_state = self.manager.updater.status

        # Check synchronization state
        if self.manager.restart_needed:
            sync_state = "restart"
        elif engine.is_paused():
            sync_state = "suspended"
        elif engine.is_syncing():
            sync_state = "syncing"

        # Recompute conflicts and errors to have the right count in the `if` below
        self.refresh_conflicts(engine.uid)

        # Check error state
        if engine.has_invalid_credentials():
            error_state = "auth_expired"
        elif self.conflicts_model.count:
            error_state = "conflicted"
        elif self.errors_model.count:
            error_state = "error"

        self._window_root(self.systray_window).setStatus.emit(
            sync_state, error_state, update_state
        )

    @pyqtSlot()
    def refresh_transfers(self) -> None:
        transfers = self.api.get_transfers()
        if transfers != self.transfer_model.transfers:
            self.transfer_model.set_transfers(transfers)
            self.transfer_model.fileChanged.emit()

    @pyqtSlot(object)
    def refresh_files(self, metrics: Dict[str, Any]) -> None:
        engine = self.sender()
        if not isinstance(engine, Engine):
            return
        self.get_last_files(engine.uid)

    @pyqtSlot(str)
    def get_last_files(self, uid: str) -> None:
        files = self.api.get_last_files(uid, 10)
        if files != self.file_model.files:
            self.file_model.empty()
            self.file_model.addFiles(files)
            self.file_model.fileChanged.emit()

    def current_language(self) -> Optional[str]:
        lang = Translator.locale()
        for tag, name in self.language_model.languages:
            if tag == lang:
                return name
        return None

    def show_metrics_acceptance(self) -> None:
        """ Display a "friendly" dialog box to ask user for metrics approval. """

        tr = Translator.get

        dialog = QDialog()
        dialog.setWindowTitle(tr("SHARE_METRICS_TITLE", [APP_NAME]))
        dialog.setWindowIcon(self.icon)
        layout = QVBoxLayout()

        info = QLabel(tr("SHARE_METRICS_MSG", [COMPANY]))
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)
        layout.addWidget(info)

        def analytics_choice(state) -> None:
            Options.use_analytics = bool(state)

        def errors_choice(state) -> None:
            Options.use_sentry = bool(state)

        # Checkboxes
        em_analytics = QCheckBox(tr("SHARE_METRICS_ERROR_REPORTING"))
        em_analytics.setChecked(True)
        em_analytics.stateChanged.connect(errors_choice)
        layout.addWidget(em_analytics)

        cb_analytics = QCheckBox(tr("SHARE_METRICS_ANALYTICS"))
        cb_analytics.stateChanged.connect(analytics_choice)
        layout.addWidget(cb_analytics)

        # Buttons
        buttons = QDialogButtonBox()
        buttons.setStandardButtons(QDialogButtonBox.Apply)
        buttons.clicked.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.setLayout(layout)
        dialog.resize(400, 200)
        dialog.show()
        dialog.exec_()

        states = []
        if Options.use_analytics:
            states.append("analytics")
        if Options.use_sentry:
            states.append("sentry")

        (Options.nxdrive_home / "metrics.state").write_text(
            "\n".join(states), encoding="utf-8"
        )

    def ask_for_metrics_approval(self) -> None:
        """Should we setup and use Sentry and/or Google Analytics?"""

        # Check the user choice first
        Options.nxdrive_home.mkdir(parents=True, exist_ok=True)

        STATE_FILE = Options.nxdrive_home / "metrics.state"
        if STATE_FILE.is_file():
            lines = STATE_FILE.read_text(encoding="utf-8").splitlines()
            Options.use_sentry = "sentry" in lines
            Options.use_analytics = "analytics" in lines
            # Abort now, the user already decided to use Sentry or not
            return

        # The user did not choose yet, display a message box
        self.show_metrics_acceptance()
