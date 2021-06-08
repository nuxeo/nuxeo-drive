""" Main Qt application handling OS events and system tray UI. """
import os
import webbrowser
from contextlib import suppress
from functools import partial
from logging import getLogger
from math import sqrt
from pathlib import Path
from random import choice
from time import monotonic
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union
from urllib.parse import unquote_plus, urlparse

from ..behavior import Behavior
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
from ..dao.engine import EngineDAO
from ..engine.activity import Action
from ..engine.engine import Engine
from ..feature import Beta, DisabledFeatures, Feature
from ..gui.folders_dialog import DialogMixin, DocumentsDialog, FoldersDialog
from ..metrics.constants import CRASHED_HIT, CRASHED_TRACE
from ..metrics.utils import current_os
from ..notification import Notification
from ..options import Options
from ..qt import constants as qt
from ..qt.imports import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCursor,
    QDialog,
    QDialogButtonBox,
    QEvent,
    QFont,
    QFontMetricsF,
    QIcon,
    QLabel,
    QLocalServer,
    QLocalSocket,
    QMessageBox,
    QQmlApplicationEngine,
    QQmlContext,
    QQuickView,
    QQuickWindow,
    QRect,
    QSizePolicy,
    QSpacerItem,
    QStyle,
    Qt,
    QTextEdit,
    QTimer,
    QUrl,
    QVBoxLayout,
    QWindow,
    pyqtSlot,
)
from ..state import State
from ..translator import Translator
from ..updater.constants import (
    UPDATE_STATUS_INCOMPATIBLE_SERVER,
    UPDATE_STATUS_UNAVAILABLE_SITE,
    UPDATE_STATUS_UP_TO_DATE,
)
from ..utils import (
    client_certificate,
    find_icon,
    find_resource,
    force_decode,
    if_frozen,
    normalize_event_filename,
    normalized_path,
    parse_protocol_url,
    short_name,
    sizeof_fmt,
    today_is_special,
)
from .api import QMLDriveApi
from .systray import DriveSystrayIcon, SystrayWindow
from .view import (
    ActiveSessionModel,
    CompletedSessionModel,
    DirectTransferModel,
    EngineModel,
    FeatureModel,
    FileModel,
    LanguageModel,
    TransferModel,
)

if MAC:
    from ..osi.darwin.pyNotificationCenter import NotificationDelegator, setup_delegator

if TYPE_CHECKING:
    from ..manager import Manager  # noqa

__all__ = ("Application",)

# Enable High-DPI
QApplication.setAttribute(qt.AA_EnableHighDpiScaling, True)

log = getLogger(__name__)


class Application(QApplication):
    """Main Nuxeo Drive application controlled by a system tray icon + menu"""

    icon = QIcon(str(find_icon("app_icon.svg")))
    icons: Dict[str, QIcon] = {}
    icon_state = None
    use_light_icons = None
    filters_dlg: Optional[DialogMixin] = None
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

        # Timer used to refresh the files list in the systray menu, see .refresh_files()
        self._last_refresh_view = 0.0

        if not self.manager.preferences_metrics_chosen:
            self.show_metrics_acceptance()

        self._conflicts_modals: Dict[str, bool] = {}
        self.current_notification: Optional[Notification] = None
        self.default_tooltip = APP_NAME

        # Font selection (*.point_size* will be used in QML for Hi-DPI scaling)
        point_size = 12
        font = QFont("Helvetica, Times", pointSize=point_size)
        self.setFont(font)
        self.point_size = point_size / sqrt(QFontMetricsF(font).height() / point_size)
        self.today_is_special = today_is_special()

        self.init_gui()

        self.manager.dropEngine.connect(self.dropped_engine)
        self.manager.restartNeeded.connect(self.show_msgbox_restart_needed)

        self.setup_systray()
        self.manager.reloadIconsSet.connect(self.load_icons_set)

        # Direct Edit
        self.manager.direct_edit.directEditConflict.connect(self._direct_edit_conflict)
        self.manager.direct_edit.directEditError[str, list].connect(
            self._direct_edit_error
        )
        self.manager.direct_edit.directEditError[str, list, str].connect(
            self._direct_edit_error
        )

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
            self._show_release_notes(self.manager.old_version, self.manager.version)

        # Listen for nxdrive:// sent by a new instance
        self.init_nxdrive_listener()

        # Connect this slot last so the other slots connected
        # to self.aboutToQuit can run beforehand.
        self.aboutToQuit.connect(self.manager.stop)

        # Send previous crash metrics
        self._send_crash_metrics()

        # Handle the eventual command via the custom URL scheme
        if Options.protocol_url:
            self._handle_nxdrive_url(Options.protocol_url)

    @pyqtSlot()
    def exit_app(self) -> None:
        """Initiate the application exit."""
        State.about_to_quit = True
        self.quit()

    def _shutdown(self) -> None:
        """
        This will be called via the aboutToQuit() signal to delete
        the QML engine before QML contexes to prevent such errors:

            TypeError: Cannot read property ... of null

        See https://bugreports.qt.io/browse/QTBUG-81247.
        """
        if WINDOWS:
            del self.conflicts_window
            del self.settings_window
            del self.systray_window
            del self.direct_transfer_window
        else:
            del self.app_engine

    def init_gui(self) -> None:

        self.api = QMLDriveApi(self)
        self.active_session_model = ActiveSessionModel(self.translate)
        self.auto_update_feature_model = FeatureModel(Feature.auto_update)
        self.completed_session_model = CompletedSessionModel(self.translate)
        self.direct_edit_feature_model = FeatureModel(Feature.direct_edit)
        self.direct_transfer_model = DirectTransferModel(self.translate)
        self.direct_transfer_feature_model = FeatureModel(Feature.direct_transfer)
        self.conflicts_model = FileModel(self.translate)
        self.errors_model = FileModel(self.translate)
        self.engine_model = EngineModel(self)
        self.synchronization_feature_model = FeatureModel(
            Feature.synchronization, restart_needed=True
        )
        self.transfer_model = TransferModel(self.translate)
        self.file_model = FileModel(self.translate)
        self.ignoreds_model = FileModel(self.translate)
        self.language_model = LanguageModel()

        self.add_engines(list(self.manager.engines.values()))
        self.engine_model.statusChanged.connect(self.update_status)
        self.language_model.addLanguages(Translator.languages())

        flags = qt.FramelessWindowHint | qt.WindowStaysOnTopHint

        if WINDOWS:
            # Conflicts
            self.conflicts_window = QQuickView()
            self.conflicts_window.setMinimumWidth(550)
            self.conflicts_window.setMinimumHeight(600)
            self._fill_qml_context(self.conflicts_window.rootContext())
            self.conflicts_window.setSource(
                QUrl.fromLocalFile(str(find_resource("qml", file="Conflicts.qml")))
            )

            # Settings
            self.settings_window = QQuickView()
            self.settings_window.setMinimumWidth(640)
            self.settings_window.setMinimumHeight(580)
            self._fill_qml_context(self.settings_window.rootContext())
            self.settings_window.setSource(
                QUrl.fromLocalFile(str(find_resource("qml", file="Settings.qml")))
            )

            # Systray
            self.systray_window = SystrayWindow()
            self._fill_qml_context(self.systray_window.rootContext())
            self.systray_window.rootContext().setContextProperty(
                "systrayWindow", self.systray_window
            )
            self.systray_window.setSource(
                QUrl.fromLocalFile(str(find_resource("qml", file="Systray.qml")))
            )

            # Direct Transfer
            self.direct_transfer_window = QQuickView()
            self.direct_transfer_window.setMinimumWidth(600)
            self.direct_transfer_window.setMinimumHeight(480)
            self._fill_qml_context(self.direct_transfer_window.rootContext())
            self.direct_transfer_window.setSource(
                QUrl.fromLocalFile(str(find_resource("qml", file="DirectTransfer.qml")))
            )

            flags |= qt.Popup
        else:
            self.app_engine = QQmlApplicationEngine()
            self._fill_qml_context(self.app_engine.rootContext())
            self.app_engine.load(
                QUrl.fromLocalFile(str(find_resource("qml", file="Main.qml")))
            )
            root = self.app_engine.rootObjects()[0]
            self.conflicts_window = root.findChild(QQuickWindow, "conflictsWindow")
            self.settings_window = root.findChild(QQuickWindow, "settingsWindow")
            self.systray_window = root.findChild(SystrayWindow, "systrayWindow")
            self.direct_transfer_window = root.findChild(
                QQuickWindow, "directTransferWindow"
            )

            if LINUX:
                flags |= qt.Drawer

        self.aboutToQuit.connect(self._shutdown)
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
            engine = self.manager.engines[current_uid]
            self.get_last_files(current_uid)
            self.refresh_transfers(engine.dao)
            self.update_status(engine)

        self.manager.updater.updateAvailable.connect(
            self._window_root(self.systray_window).updateAvailable
        )
        self.manager.updater.updateProgress.connect(
            self._window_root(self.systray_window).updateProgress
        )

        self.manager.featureUpdate.connect(self._update_feature_state)

    def _update_feature_state(self, name: str, value: bool, /) -> None:
        """Check if the feature model exists from *name* then update it with *value*."""
        feature = getattr(self, f"{name}_feature_model", None)
        if not feature:
            return
        feature.enabled = value

        if feature.restart_needed:
            self.manager.restartNeeded.emit()

    def _center_on_screen(self, window: QQuickView, /) -> None:
        """Display and center the window on the screen."""
        # Display the window
        self._show_window(window)

        # Find the screen where the cursor is located: in case of multi-screens, this
        # will grab the correct screen depending of the cursor position.
        screen = QApplication.screenAt(QCursor.pos())
        if not screen:
            # The window is not yet painted or seen on the current desktop
            return

        window.setGeometry(
            QStyle.alignedRect(
                qt.LeftToRight,
                qt.AlignCenter,
                window.size(),
                screen.availableGeometry(),
            )
        )

        # Ensure the window is shown on top of others
        self._show_window(window)

    @pyqtSlot(object)
    def action_progressing(self, action: Action, /) -> None:
        if not isinstance(action, Action):
            log.warning(f"An action is needed, got {action!r}")
            return

        export = action.export()
        if export["is_direct_transfer"]:
            self.direct_transfer_model.set_progress(export)
        else:
            self.transfer_model.set_progress(export)

    def add_engines(self, engines: Union[Engine, List[Engine]], /) -> None:
        if not engines:
            return

        engines = engines if isinstance(engines, list) else [engines]
        for engine in engines:
            self.engine_model.addEngine(engine.uid)

    def remove_engine(self, uid: str, /) -> None:
        self.engine_model.removeEngine(uid)

    def _fill_qml_context(self, context: QQmlContext, /) -> None:
        """Fill the context of a QML element with the necessary resources."""

        context.setContextProperty("ActiveSessionModel", self.active_session_model)
        context.setContextProperty(
            "CompletedSessionModel", self.completed_session_model
        )
        context.setContextProperty("ConflictsModel", self.conflicts_model)
        context.setContextProperty("DirectTransferModel", self.direct_transfer_model)
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
        context.setContextProperty("point_size", self.point_size)
        context.setContextProperty("update_check_delay", Options.update_check_delay)
        context.setContextProperty("isFrozen", Options.is_frozen)
        context.setContextProperty("APP_NAME", APP_NAME)
        context.setContextProperty("LINUX", LINUX)
        context.setContextProperty("WINDOWS", WINDOWS)
        context.setContextProperty(
            "CHUNK_SIZE",
            sizeof_fmt(Options.chunk_size * 1024 * 1024, suffix=self.tr("BYTE_ABBREV")),
        )
        context.setContextProperty("feat_auto_update", self.auto_update_feature_model)
        context.setContextProperty("feat_direct_edit", self.direct_edit_feature_model)
        context.setContextProperty(
            "feat_direct_transfer", self.direct_transfer_feature_model
        )
        context.setContextProperty(
            "feat_synchronization", self.synchronization_feature_model
        )
        context.setContextProperty("beta_features", Beta)
        context.setContextProperty("disabled_features", DisabledFeatures)
        context.setContextProperty("tl", Translator.singleton)
        context.setContextProperty(
            "nuxeoVersionText", f"{APP_NAME} {self.manager.version}"
        )
        metrics = self.manager.get_metrics()
        versions = (
            f"Python {metrics['python_version']}"
            f" & Qt {metrics['qt_version']}"
            f" & Python client {metrics['python_client_version']}"
        )
        if Options.system_wide:
            versions += " [admin]"
        if self.today_is_special:
            emoticon = choice("🎅 🤶 🎄 ⛄ ❄️ 🎁".split())
            versions += f" {emoticon}"
        versions += f"\nDevice ID: {self.manager.device_id}"
        context.setContextProperty("modulesVersionText", versions)

        colors = {
            "mediumGray": "#7F8284",
            "lightGray": "#BCBFBF",
            "uiBackground": "#F4F4F4",
            "primaryBg": "#0066FF",
            "primaryBgHover": "#0052CC",
            "primaryButtonText": "#FFFFFF",
            "primaryButtonTextHover": "#FFFFFF",
            "secondaryBg": "transparent",
            "secondaryBgHover": "#0052CC",
            "secondaryButtonText": "#0066FF",
            "secondaryButtonTextHover": "#FFFFFF",
            "primaryIcon": "#161616",
            "secondaryIcon": "#525252",
            "disabledIcon": "#C6C6C6",
            "primaryText": "#161616",
            "disabledText": "#C6C6C6",
            "secondaryText": "#525252",
            "progressFilled": "#0066FF",
            "progressFilledLight": "#7D0066FF",  # Added 50% opacity (format AARRGGBB)
            "progressEmpty": "#F4F4F4",
            "focusedTab": "#161616",
            "unfocusedTab": "#525252",
            "focusedUnderline": "#0066FF",
            "unfocusedUnderline": "#E0E0E0",
            "switchOnEnabled": "#0066FF",
            "switchOffEnabled": "#525252",
            "switchDisabled": "#C6C6C6",
            "interactiveLink": "#0066FF",
            "label": "#525252",
            "grayBorder": "#8D8D8D",
            "iconSuccess": "#24A148",
            "iconFailure": "#DA1E28",
            "errorContent": "#C02828",
            "warningContent": "#FF9E00",
            "lightTheme": "#FFFFFF",
            "darkShadow": "#333333",
        }

        for name, value in colors.items():
            context.setContextProperty(name, value)

    def _window_root(self, window: QWindow, /) -> QWindow:
        if WINDOWS:
            return window.rootObject()
        return window

    def translate(self, message: str, /, *, values: List[Any] = None) -> str:
        return Translator.get(message, values=values)

    def _show_window(self, window: QWindow, /) -> None:
        window.show()
        window.raise_()
        with suppress(AttributeError):
            # QDialog does not have such attribute
            window.requestActivate()

    def _init_translator(self) -> None:
        locale = Options.force_locale or Options.locale
        locale = self.manager.get_config("locale", default=locale)
        Translator(find_resource("i18n"), lang=locale)
        # Make sure that a language change changes external values like
        # the text in the contextual menu
        Translator.on_change(self._handle_language_change)
        # Trigger it now
        self.osi.register_contextual_menu()
        self.installTranslator(Translator.singleton)

    def _msgbox(
        self,
        *,
        icon: QIcon = qt.Information,
        title: str = APP_NAME,
        header: str = "",
        message: str = "",
        details: str = "",
        execute: bool = True,
    ) -> QMessageBox:
        """Display a message box."""
        msg = QMessageBox()
        msg.setWindowTitle(title)
        msg.setWindowIcon(self.icon)
        msg.setIcon(icon)
        msg.setTextFormat(qt.RichText)
        if header:
            msg.setText(header)
        if message:
            msg.setInformativeText(message)
        if details:
            msg.setDetailedText(details)
        if execute:
            msg.exec_()
        return msg

    def display_info(self, title: str, message: str, values: List[str], /) -> None:
        """Display an informative message box."""
        msg_text = self.translate(message, values=values)
        log.info(f"{msg_text} (values={values})")
        self._msgbox(title=title, message=msg_text)

    def display_warning(
        self,
        title: str,
        message: str,
        values: List[str],
        /,
        *,
        details: str = "",
        execute: bool = True,
    ) -> QMessageBox:
        """Display a warning message box."""
        msg_text = self.translate(message, values=values)
        log.warning(f"{msg_text} ({values=}, {details=})")
        return self._msgbox(
            icon=qt.Warning,
            title=title,
            message=msg_text,
            details=details,
            execute=execute,
        )

    def question(
        self, header: str, message: str, /, *, icon: QIcon = qt.Question
    ) -> QMessageBox:
        """Display a question message box."""
        log.debug(f"Question: {message}")
        return self._msgbox(icon=icon, header=header, message=message, execute=False)

    @pyqtSlot(str, Path, str)
    def _direct_edit_conflict(self, filename: str, ref: Path, digest: str, /) -> None:
        log.debug(f"Entering _direct_edit_conflict for {filename!r} / {ref!r}")
        try:
            if filename in self._conflicts_modals:
                log.debug(f"Filename already in _conflicts_modals: {filename!r}")
                return
            log.debug(f"Putting filename in _conflicts_modals: {filename!r}")
            self._conflicts_modals[filename] = True

            msg = self.question(
                Translator.get("DIRECT_EDIT_CONFLICT_HEADER"),
                Translator.get(
                    "DIRECT_EDIT_CONFLICT_MESSAGE", values=[short_name(filename)]
                ),
                icon=qt.Warning,
            )
            overwrite = msg.addButton(
                Translator.get("DIRECT_EDIT_CONFLICT_OVERWRITE"), qt.AcceptRole
            )
            msg.addButton(Translator.get("CANCEL"), qt.RejectRole)
            msg.exec_()
            if msg.clickedButton() == overwrite:
                self.manager.direct_edit.force_update(ref, digest)
            del self._conflicts_modals[filename]
        except Exception:
            log.exception(
                f"Error while displaying Direct Edit conflict modal dialog for {filename!r}"
            )

    @pyqtSlot(str, list)
    @pyqtSlot(str, list, str)
    def _direct_edit_error(
        self, message: str, values: List[str], details: str = ""
    ) -> None:
        """Display a simple Direct Edit error message."""
        self.display_warning(
            f"Direct Edit - {APP_NAME}", message, values, details=details
        )

    @pyqtSlot()
    def _root_deleted(self) -> None:
        engine = self.sender()
        log.info(f"Root has been deleted for engine: {engine.uid}")

        msg = self.question(
            Translator.get("DRIVE_ROOT_DELETED_HEADER"),
            Translator.get(
                "DRIVE_ROOT_DELETED", values=[engine.local_folder, APP_NAME]
            ),
            icon=qt.Critical,
        )
        recreate = msg.addButton(Translator.get("DRIVE_ROOT_RECREATE"), qt.AcceptRole)
        disconnect = msg.addButton(
            Translator.get("DRIVE_ROOT_DISCONNECT"), qt.RejectRole
        )

        msg.exec_()
        res = msg.clickedButton()
        if res == disconnect:
            self.manager.unbind_engine(engine.uid)
        elif res == recreate:
            engine.reinit()
            engine.start()

    def _send_crash_metrics(self) -> None:
        if not State.has_crashed:
            return

        metrics = {CRASHED_HIT: 1}
        if State.crash_details:
            metrics[CRASHED_TRACE] = State.crash_details

        for engine in self.manager.engines.copy().values():
            if engine.remote:
                engine.remote.metrics.send(metrics)
                break

    @pyqtSlot()
    def _no_space_left(self) -> None:
        self.display_warning(APP_NAME, "NO_SPACE_LEFT_ON_DEVICE", [])

    @pyqtSlot(Path)
    def _root_moved(self, new_path: Path, /) -> None:
        engine = self.sender()
        log.info(f"Root has been moved for engine: {engine.uid} to {new_path!r}")
        info = [engine.local_folder, APP_NAME, str(new_path)]

        msg = self.question(
            Translator.get("DRIVE_ROOT_MOVED_HEADER"),
            Translator.get("DRIVE_ROOT_MOVED", values=info),
            icon=qt.Critical,
        )
        move = msg.addButton(Translator.get("DRIVE_ROOT_MOVE"), qt.AcceptRole)
        recreate = msg.addButton(Translator.get("DRIVE_ROOT_RECREATE"), qt.AcceptRole)
        disconnect = msg.addButton(
            Translator.get("DRIVE_ROOT_DISCONNECT"), qt.RejectRole
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

    def confirm_deletion(self, path: Path, /) -> DelAction:
        mode = self.manager.get_deletion_behavior()
        unsync = None
        if mode is DelAction.DEL_SERVER:
            descr = "DELETION_BEHAVIOR_CONFIRM_DELETE"
            confirm_text = "DELETE_FOR_EVERYONE"
        elif mode is DelAction.UNSYNC:
            descr = "DELETION_BEHAVIOR_CONFIRM_UNSYNC"
            confirm_text = "UNSYNC"

        msg = self.question(
            Translator.get("DELETION_BEHAVIOR_HEADER"),
            Translator.get(
                descr, values=[str(path), Translator.get("SELECT_SYNC_FOLDERS")]
            ),
        )
        if mode is DelAction.DEL_SERVER:
            unsync = msg.addButton(Translator.get("JUST_UNSYNC"), qt.RejectRole)
        msg.addButton(Translator.get("CANCEL"), qt.RejectRole)
        confirm = msg.addButton(Translator.get(confirm_text), qt.AcceptRole)

        cb = QCheckBox(Translator.get("DONT_ASK_AGAIN"))
        msg.setCheckBox(cb)

        msg.exec_()
        res = msg.clickedButton()

        if cb.isChecked():
            self.manager.dao.store_bool("show_deletion_prompt", False)

        if res == confirm:
            return mode
        elif res == unsync:
            msg = self.question(
                Translator.get("DELETION_BEHAVIOR_HEADER"),
                Translator.get("DELETION_BEHAVIOR_SWITCH"),
            )
            msg.addButton(Translator.get("NO"), qt.RejectRole)
            confirm = msg.addButton(Translator.get("YES"), qt.AcceptRole)
            msg.exec_()
            if msg.clickedButton() == confirm:
                self.manager.set_deletion_behavior(DelAction.UNSYNC)
            return DelAction.UNSYNC

        return DelAction.ROLLBACK

    @pyqtSlot(Path)
    def _doc_deleted(self, path: Path, /) -> None:
        engine: Engine = self.sender()

        if not Behavior.server_deletion:
            mode = DelAction.UNSYNC
            log.debug(f"Server deletions behavior is False, mode set to {mode.value!r}")
        else:
            mode = self.confirm_deletion(path)

        if mode is DelAction.ROLLBACK:
            # Re-sync the document
            engine.rollback_delete(path)
        else:
            # Delete or filter out the document
            engine.delete_doc(path, mode=mode)

    @pyqtSlot(Path, Path)
    def _file_already_exists(self, oldpath: Path, newpath: Path, /) -> None:
        msg = self.question(
            Translator.get("FILE_ALREADY_EXISTS_HEADER"),
            Translator.get("FILE_ALREADY_EXISTS", values=[str(oldpath)]),
            icon=qt.Critical,
        )
        replace = msg.addButton(Translator.get("REPLACE"), qt.AcceptRole)
        msg.addButton(Translator.get("CANCEL"), qt.RejectRole)
        msg.exec_()
        if msg.clickedButton() == replace:
            oldpath.unlink()
            normalize_event_filename(newpath)
        else:
            newpath.unlink()

    @pyqtSlot(object)
    def dropped_engine(self, engine: Engine, /) -> None:
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
        engines = self.manager.engines.copy()
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

    def refresh_conflicts(self, uid: str, /) -> None:
        """Update the content of the conflicts/errors window."""
        self.conflicts_model.add_files(self.api.get_conflicts(uid))
        self.errors_model.add_files(self.api.get_errors(uid))
        self.ignoreds_model.add_files(self.api.get_unsynchronizeds(uid))

    @pyqtSlot(object)
    def show_conflicts_resolution(self, engine: Engine, /) -> None:
        """Display the conflicts/errors window."""
        self.refresh_conflicts(engine.uid)
        self._window_root(self.conflicts_window).setEngine.emit(engine.uid)
        self._center_on_screen(self.conflicts_window)

    @pyqtSlot(str)
    def show_settings(self, section: str, /) -> None:
        # Note: Keep synced with the Settings.qml file
        sections = {
            "Features": 0,
            "Accounts": 1,
            "Sync": 2,
            "Advanced": 3,
            "About": 4,
        }
        self._window_root(self.settings_window).setSection.emit(sections[section])
        self._center_on_screen(self.settings_window)

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

        self.systray_window.setX(int(pos_x))
        self.systray_window.setY(int(pos_y))

        self.systray_window.show()
        self.systray_window.raise_()

    @pyqtSlot()
    def hide_systray(self) -> None:
        self.systray_window.hide()

    @pyqtSlot()
    def open_help(self) -> None:
        self.manager.open_help()

    @pyqtSlot()
    def destroyed_filters_dialog(self) -> None:
        self.filters_dlg = None

    @pyqtSlot(object)
    def show_filters(self, engine: Engine, /) -> None:
        if self.filters_dlg:
            self.filters_dlg.close()
            self.filters_dlg = None

        self.filters_dlg = DocumentsDialog(self, engine)
        self.filters_dlg.destroyed.connect(self.destroyed_filters_dialog)

        # Close the settings window at the same time of the filters one
        if hasattr(self, "close_settings_too"):
            self.filters_dlg.destroyed.connect(self.settings_window.close)
            delattr(self, "close_settings_too")

        self._center_on_screen(self.settings_window)
        self._show_window(self.filters_dlg)

    def show_server_folders(self, engine: Engine, path: Optional[Path], /) -> None:
        """Display the remote folders dialog window.
        *path* is None when the dialog window is opened from a click on the systray menu icon.
        """
        if self.filters_dlg:
            self.filters_dlg.close()
            self.filters_dlg = None

        self.filters_dlg = FoldersDialog(self, engine, path)
        self.filters_dlg.accepted.connect(self._show_direct_transfer_window)
        self.filters_dlg.destroyed.connect(self.destroyed_filters_dialog)
        self.filters_dlg.show()

    @pyqtSlot()
    def _show_direct_transfer_window(self) -> None:
        """
        Called when the server folders selection dialog is destroyed.
        Show the Direct Transfer window if needed.
        """
        if not self.filters_dlg:
            return
        self.show_direct_transfer_window(self.filters_dlg.engine.uid)

    @pyqtSlot(str)
    def show_direct_transfer_window(self, engine_uid: str, /) -> None:
        """Display the Direct Transfer window."""
        window = self._window_root(self.direct_transfer_window)
        window.setEngine.emit(engine_uid)
        self._center_on_screen(self.direct_transfer_window)

    @pyqtSlot()
    def close_direct_transfer_window(self) -> None:
        """Close the Direct Transfer window."""
        self.direct_transfer_window.close()

    def folder_duplicate_warning(
        self, duplicates: List[str], remote_path: str, remote_url: str, /
    ) -> None:
        """
        Show a dialog to confirm the given transfer cancel.
        Cancel transfer on validation.
        """
        title = Translator.get("FOLDER_DUPLICATES_DETECTED")

        duplicates_list_html = ""
        for index, value in enumerate(duplicates):
            if index == 4:
                duplicates_list_html += "<li>…</li>"
                break
            duplicates_list_html += f"<li>{value}</li>"

        msg_box = self.display_warning(
            title,
            "FOLDER_DUPLICATES_MSG",
            [remote_url, remote_path, duplicates_list_html],
            execute=False,
        )
        spacer = QSpacerItem(600, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        layout = msg_box.layout()
        layout.addItem(spacer, layout.rowCount(), 0, 1, layout.columnCount())
        msg_box.exec_()

    @pyqtSlot(str, int, str)
    def confirm_cancel_transfer(
        self, engine_uid: str, transfer_uid: int, name: str, /
    ) -> None:
        """
        Show a dialog to confirm the given transfer cancel.
        Cancel transfer on validation.
        """
        msg = self.question(
            Translator.get("DIRECT_TRANSFER_CANCEL_HEADER"),
            Translator.get("DIRECT_TRANSFER_CANCEL", values=[name]),
        )
        continued = msg.addButton(Translator.get("YES"), qt.AcceptRole)
        cancel = msg.addButton(Translator.get("NO"), qt.RejectRole)
        msg.setDefaultButton(cancel)
        msg.exec_()
        if msg.clickedButton() == continued:
            engine = self.manager.engines.get(engine_uid)
            if not engine:
                return
            engine.cancel_upload(transfer_uid)

    @pyqtSlot(str, int, str, int, result=bool)
    def confirm_cancel_session(
        self, engine_uid: str, session_uid: int, destination: str, pending_files: int, /
    ) -> bool:
        """
        Show a dialog to confirm the given session cancel.
        Cancel the session on validation.
        Return True if the cancel was confirmed.
        """
        msg = self.question(
            Translator.get("SESSION_CANCEL_HEADER"),
            Translator.get("SESSION_CANCEL", values=[destination, str(pending_files)]),
        )
        continued = msg.addButton(Translator.get("YES"), qt.AcceptRole)
        cancel = msg.addButton(Translator.get("NO"), qt.RejectRole)
        msg.setDefaultButton(cancel)
        msg.exec_()
        if msg.clickedButton() == continued:
            self.api.cancel_session(engine_uid, session_uid)
            return True
        return False

    @pyqtSlot(str, object)
    def open_authentication_dialog(
        self, url: str, callback_params: Dict[str, str], /
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
            QApplication.setOverrideCursor(qt.WaitCursor)
            try:
                webbrowser.open_new_tab(url)
            finally:
                QApplication.restoreOverrideCursor()
        else:
            self._web_auth_not_frozen(callback_params["server_url"])

    def _web_auth_not_frozen(self, url: str, /) -> None:
        """
        Open a dialog box to fill the credentials.
        Then a request will be done using the Python client to
        get a token.

        This is used when the application is not frozen as there is no custom
        protocol handler in this case.
        """

        from nuxeo.client import Nuxeo

        from ..qt.imports import QLineEdit

        dialog = QDialog()
        dialog.setWindowTitle(self.translate("WEB_AUTHENTICATION_WINDOW_TITLE"))
        dialog.setWindowIcon(self.icon)
        dialog.resize(250, 100)

        layout = QVBoxLayout()

        default_user = os.getenv("NXDRIVE_TEST_USERNAME", "Administrator")
        default_pwd = os.getenv("NXDRIVE_TEST_PASSWORD", "Administrator")
        username = QLineEdit(default_user, parent=dialog)
        password = QLineEdit(default_pwd, parent=dialog)
        password.setEchoMode(qt.Password)
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
                cert=client_certificate(),
            )
            try:
                token = nuxeo.client.request_auth_token(
                    self.manager.device_id,
                    TOKEN_PERMISSION,
                    app_name=APP_NAME,
                    device=current_os(full=True),
                )
            except Exception as exc:
                log.error(f"Connection error: {exc}")
                token = ""
            finally:
                del nuxeo

            self.api.handle_token(token, user)
            dialog.close()

        buttons = QDialogButtonBox()
        buttons.setStandardButtons(qt.Cancel | qt.Ok)
        buttons.accepted.connect(auth)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)

        dialog.setLayout(layout)
        dialog.exec_()

    @pyqtSlot(object)
    def _connect_engine(self, engine: Engine, /) -> None:
        engine.syncStarted.connect(self.change_systray_icon)
        engine.syncCompleted.connect(self.change_systray_icon)
        engine.syncCompleted.connect(self.force_refresh_files)
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

        # Refresh the systray files list on each database update
        engine.dao.transferUpdated.connect(partial(self.refresh_transfers, engine.dao))

        # Refresh ongoing Direct Transfer items at startup
        engine.started.connect(partial(self.refresh_direct_transfer_items, engine.dao))

        # Refresh Direct Transfer items on each database update
        engine.dao.directTransferUpdated.connect(
            partial(self.refresh_direct_transfer_items, engine.dao)
        )

        # Refresh ongoing Sessions items at startup
        engine.started.connect(partial(self.refresh_active_sessions_items, engine.dao))

        # Refresh ongoing Sessions items on each database update
        engine.dao.sessionUpdated.connect(
            partial(self.refresh_active_sessions_items, engine.dao)
        )

        # Refresh completed Sessions items at startup
        engine.started.connect(
            partial(self.refresh_completed_sessions_items, engine.dao)
        )

        # Set the list of Engines items at startup
        engine.started.connect(
            partial(self.add_engines, list(self.manager.engines.values()))
        )

        # Refresh completed Sessions items on each database update
        engine.dao.sessionUpdated.connect(
            partial(self.refresh_completed_sessions_items, engine.dao)
        )

        engine.newSyncEnded.connect(self.manager.tracker.send_sync_event)
        engine.newSyncEnded.connect(engine.remote.metrics.push_sync_event)

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
        description = Translator.get(msg, values=[version])
        flags = Notification.FLAG_BUBBLE | Notification.FLAG_UNIQUE

        log.warning(description)
        notification = Notification(
            uuid="AutoUpdate",
            flags=flags,
            title=Translator.get("NOTIF_UPDATE_TITLE", values=[version]),
            description=description,
        )
        self.manager.notification_service.send_notification(notification)

    @pyqtSlot()
    def _server_incompatible(self) -> None:
        version = self.manager.version
        downgrade_version = self.manager.updater.version or ""

        msg = self.question(
            Translator.get("SERVER_INCOMPATIBLE_HEADER", values=[APP_NAME, version]),
            Translator.get("SERVER_INCOMPATIBLE", values=[APP_NAME, downgrade_version]),
            icon=qt.Warning,
        )
        if downgrade_version:
            msg.addButton(
                Translator.get("CONTINUE_USING", values=[version]),
                qt.RejectRole,
            )
            downgrade = msg.addButton(
                Translator.get("DOWNGRADE_TO", values=[downgrade_version]),
                qt.AcceptRole,
            )
        else:
            msg.addButton(Translator.get("CONTINUE"), qt.RejectRole)

        msg.exec_()
        if downgrade_version and msg.clickedButton() == downgrade:
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
        msg = self.question(
            Translator.get("WRONG_CHANNEL_HEADER"),
            Translator.get(
                "WRONG_CHANNEL", values=[version, version_channel, current_channel]
            ),
            icon=qt.Warning,
        )
        switch_channel = msg.addButton(
            Translator.get("USE_CHANNEL", values=[version_channel]),
            qt.AcceptRole,
        )
        downgrade = msg.addButton(
            Translator.get("DOWNGRADE_TO", values=[downgrade_version]),
            qt.AcceptRole,
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
    def _new_notification(self, notif: Notification, /) -> None:
        if not notif.is_bubble():
            return

        if self._delegator is not None:
            # Use notification center
            from ..osi.darwin.pyNotificationCenter import notify

            user_info = {"uuid": notif.uid} if notif.uid else None

            return notify(notif.title, "", notif.description, user_info=user_info)

        if notif.level == Notification.LEVEL_WARNING:
            icon = qt.ST_Warning
        elif notif.level == Notification.LEVEL_ERROR:
            icon = qt.ST_Critical
        else:
            icon = qt.ST_Information

        self.current_notification = notif
        self.tray_icon.showMessage(notif.title, notif.description, icon, 10000)

    @pyqtSlot(str, object)
    def _handle_notification_action(
        self, action: str, action_args: Tuple[Any, ...], /
    ) -> None:
        func = getattr(self.api, action, None)
        if not func:
            log.error(f"Action {action}() is not defined in {self.api}")
            return
        func(*action_args)

    def set_icon_state(self, state: str, /, *, force: bool = False) -> bool:
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
    def _show_release_notes(self, previous: str, current: str, /) -> None:
        """Display release notes of a given version."""

        if "CI" in os.environ or Options.is_alpha:
            return

        channel = self.manager.get_update_channel()
        log.info(f"Showing release notes, {previous=} {current=} {channel=}")
        self.display_info(
            Translator.get("RELEASE_NOTES_TITLE", values=[APP_NAME]),
            "RELEASE_NOTES_MSG",
            [APP_NAME, current],
        )

    def accept_unofficial_ssl_cert(self, hostname: str, /) -> bool:
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
<h2>{Translator.get("SSL_CANNOT_CONNECT", values=[hostname])}</h2>
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
        buttons.setStandardButtons(qt.Ok | qt.Cancel)
        buttons.button(qt.Ok).setEnabled(False)
        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.close)

        def bypass_triggered(state: int) -> None:
            """Enable the OK button only when the checkbox is checked."""
            buttons.button(qt.Ok).setEnabled(bool(state))

        bypass = QCheckBox(Translator.get("SSL_TRUST_ANYWAY"))
        bypass.stateChanged.connect(bypass_triggered)

        layout = QVBoxLayout()
        layout.addWidget(notes)
        layout.addWidget(bypass)
        layout.addWidget(buttons)
        dialog.setLayout(layout)
        dialog.exec_()

        return continue_with_bad_ssl_cert

    def show_metadata(self, path: Path, /) -> None:
        self.manager.ctx_edit_metadata(path)

    @pyqtSlot(bool)
    def load_icons_set(self, use_light_icons: bool, /) -> None:
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
            file = state
            if state == "idle" and self.today_is_special:
                # Credits: https://svg-clipart.com/outline/sv0gv4r-santa-claus-hat-clipart
                file = "xmas"
            file += f"{suffix}.svg"
            icon.addFile(str(find_icon(file)))
            if MAC:
                icon.addFile(mask, mode=qt.Selected)
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
            # Default value for GNU/Linux, macOS and Windows 7
            use_light_icons = False

            if LINUX:
                import distro

                if "manjaro" in distro.name().lower():
                    # Manjaro has a dark them by default and the notification area has the same color
                    # as our dark icons, so use the light ones.
                    use_light_icons = True
            elif MAC and self.osi.dark_mode_in_use():
                # The Dark mode on macOS is set
                use_light_icons = True
            elif WINDOWS:
                # Windows 8+ has a dark them by default
                use_light_icons = True
        else:
            # The value stored in DTB as a string '0' or '1', convert to boolean
            use_light_icons = bool(int(use_light_icons))

        return use_light_icons

    def setup_systray(self) -> None:
        """Setup the icon system tray and its associated menu."""
        self.load_icons_set(self.initial_icons_set())

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

    def event(self, event: QEvent, /) -> bool:
        """Handle URL scheme events under macOS."""
        url = getattr(event, "url", None)
        if not url:
            # This is not an event for us!
            return super().event(event)

        final_url = unquote_plus(event.url().toString())
        try:
            return self._handle_nxdrive_url(final_url)
        except Exception:
            log.exception(f"Error handling URL event {final_url!r}")
            return False

    @pyqtSlot()
    def show_msgbox_restart_needed(self) -> None:
        """Display a message to ask the user to restart the application."""
        self.display_warning(APP_NAME, "RESTART_NEEDED_MSG", [APP_NAME])

    @pyqtSlot(result=str)
    def _nxdrive_url_env(self) -> str:
        """Get the NXDRIVE_URL envar value, empty string if not defined."""
        return os.getenv("NXDRIVE_URL", "")

    @pyqtSlot(str, result=bool)
    def _handle_nxdrive_url(self, url: str, /) -> bool:
        """Handle an nxdrive protocol URL."""

        info = parse_protocol_url(url)
        if not info:
            return False

        # Handle "file://" and regular path
        file = info.get("filepath", "")
        if file:
            file = unquote_plus(urlparse(file).path)

        path = normalized_path(file)
        log.info(f"Event URL={url}, info={info!r}, path={path!r}")

        # Event fired by a context menu item
        cmd = info["command"]
        manager = self.manager
        func = {
            "access-online": manager.ctx_access_online,
            "copy-share-link": manager.ctx_copy_share_link,
            "direct-transfer": self.ctx_direct_transfer,
            "edit-metadata": manager.ctx_edit_metadata,
        }.get(cmd, None)
        if func:
            args: Tuple[Any, ...] = (path,)
        elif "edit" in cmd:
            if not manager.wait_for_server_config():
                self.display_warning(
                    f"Direct Edit - {APP_NAME}", "DIRECT_EDIT_NOT_POSSIBLE", []
                )
                return False

            if manager.restart_needed:
                self.show_msgbox_restart_needed()
                return False

            func = manager.directEdit.emit
            args = (
                info["server_url"],
                info["doc_id"],
                info["user"],
                info["download_url"],
            )
        elif cmd == "authorize":
            func = self.api.continue_oauth2_flow
            args = ({k: v for k, v in info.items() if k != "command"},)
        elif cmd == "token":
            func = self.api.handle_token
            args = (info["token"], info["username"])
        else:
            log.warning(f"Unknown event URL={url}, info={info!r}, path={path!r}")
            return False

        log.info(f"Calling {func}{args}")
        func(*args)
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
        server.setSocketOptions(qt.WorldAccessOption)
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
        """Retrieve the connection with other instances and handle the incoming data."""

        con: QLocalSocket = None
        try:
            con = self._nxdrive_listener.nextPendingConnection()
            log.info("Receiving socket connection for nxdrive protocol handling")
            if not (con and con.waitForConnected()):
                log.error(f"Unable to open server socket: {con.errorString()}")
                return

            if con.waitForReadyRead():
                payload = con.readAll()
                url = force_decode(payload.data())
                self._handle_nxdrive_url(url)

            con.disconnectFromServer()
            if con.state() == qt.ConnectedState:
                con.waitForDisconnected()
        finally:
            del con
        log.info("Successfully closed server socket")

    def _select_account(self, engines: List[Engine], /) -> Optional[Engine]:
        """Display a selection box to let the user choose 1 account."""

        dialog = QDialog()
        dialog.setWindowTitle(
            Translator.get("DIRECT_TRANSFER_WINDOW_TITLE", values=[APP_NAME])
        )
        dialog.setWindowIcon(self.icon)

        selected_engine: Optional[Engine] = None

        def account_selected(index: int) -> None:
            """Callback for when an account is selected."""
            nonlocal selected_engine
            selected_engine = select.itemData(index)
            log.debug(f"Selected engine {selected_engine} ({select.itemText(index)})")

        def accept() -> None:
            nonlocal selected_engine
            selected_engine = select.currentData()
            dialog.accept()

        def close() -> None:
            nonlocal selected_engine
            selected_engine = None
            dialog.close()

        # The text
        label = QLabel(Translator.get("SELECT_ACCOUNT"))

        # The dropdown menu to select the account
        select = QComboBox()
        select.activated.connect(account_selected)
        for engine in engines:
            user = engine.get_user_full_name(engine.remote_user)
            text = f"{user} • {engine.server_url}"
            select.addItem(text, engine)

        # The buttons
        buttons = QDialogButtonBox()
        buttons.setStandardButtons(qt.Ok | qt.Cancel)
        buttons.accepted.connect(accept)
        buttons.rejected.connect(close)

        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(select)
        layout.addWidget(buttons)
        dialog.setLayout(layout)
        dialog.exec_()

        return selected_engine

    def ctx_direct_transfer(self, path: Path, /) -> None:
        """Direct Transfer of local files and folders to anywhere on the server."""

        if not self.manager.wait_for_server_config():
            self.display_warning(
                f"Direct Transfer - {APP_NAME}", "DIRECT_TRANSFER_NOT_POSSIBLE", []
            )
            return

        if not Feature.direct_transfer:
            self.display_warning(
                f"Direct Transfer - {APP_NAME}", "DIRECT_TRANSFER_NOT_ENABLED", []
            )
            return

        # Direct Transfer is not allowed for synced files
        engines = list(self.manager.engines.values())
        if any(e.local_folder in path.parents for e in engines):
            self.display_warning(
                f"Direct Transfer - {APP_NAME}",
                "DIRECT_TRANSFER_NOT_ALLOWED",
                [str(path)],
            )
            return

        log.info(f"Direct Transfer: {path!r}")

        # Select the good account to use
        engine: Optional[Engine] = None
        if len(engines) > 1:
            # The user has to select the desired account
            engine = self._select_account(engines)
        elif engines:
            engine = engines[0]
        if not engine:
            self.display_warning(
                f"Direct Transfer - {APP_NAME}", "DIRECT_TRANSFER_NO_ACCOUNT", []
            )
            return

        self.show_server_folders(engine, path)

    def update_status(self, engine: Engine, /) -> None:
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

    @pyqtSlot(object)
    def refresh_transfers(self, dao: EngineDAO, /) -> None:
        transfers = self.api.get_transfers(dao)
        if transfers != self.transfer_model.transfers:
            self.transfer_model.set_transfers(transfers)

    @pyqtSlot(object)
    def refresh_direct_transfer_items(self, dao: EngineDAO, /) -> None:
        transfers = self.api.get_direct_transfer_items(dao)
        items = self.direct_transfer_model.items
        if transfers != items:
            if not items:
                self.direct_transfer_model.set_items(transfers)
            else:
                # Finalizing status is not stored in the database so it must be updated from the previous list
                # The previous items list may contain shadow items that must be ignored
                pair_finalizing = {
                    item["doc_pair"]: item["finalizing"]
                    for item in items
                    if item.get("finalizing", False) and "shadow" not in item
                }
                for transfer in transfers:
                    if transfer["doc_pair"] in pair_finalizing:
                        transfer["finalizing"] = True
                self.direct_transfer_model.update_items(transfers)

    @pyqtSlot(object)
    def refresh_active_sessions_items(self, dao: EngineDAO, _: bool = False, /) -> None:
        """Refresh the list of active sessions if a change is detected."""
        sessions = self.api.get_active_sessions_items(dao)
        current_sessions = self.active_session_model.sessions
        if sessions != current_sessions:
            if not current_sessions:
                self.active_session_model.set_sessions(sessions)
            else:
                self.active_session_model.update_sessions(sessions)

    @pyqtSlot(object)
    def refresh_completed_sessions_items(
        self, dao: EngineDAO, force: bool = False, /
    ) -> None:
        """Refresh the list of completed sessions if a change is detected."""
        sessions = self.api.get_completed_sessions_items(dao)
        sessions = [self._add_csv_path_to_session(session) for session in sessions]

        if sessions != self.completed_session_model.sessions or force:
            self.completed_session_model.set_sessions(sessions)

    def _add_csv_path_to_session(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Add the *csv_path* key to the session dict."""
        date = row["completed_on"]
        if not date:
            # The session was cancelled
            return row
        name = f"session_{date.replace(':', '-').replace(' ', '_')}.csv"
        csv_path = self.manager.home / "csv" / name
        if csv_path.with_suffix(".tmp").is_file():
            row["csv_path"] = "async_gen"
        else:
            row["csv_path"] = str(csv_path) if csv_path.is_file() else ""
        return row

    @pyqtSlot()
    def force_refresh_files(self) -> None:
        """Force a refreshing of the files list."""
        self._last_refresh_view = 0.0
        self.refresh_files({})

    @pyqtSlot(object)
    def refresh_files(self, metrics: Dict[str, Any], /) -> None:
        """Refresh the files list every second to go easy on the QML side and prevent GUI lags."""
        if monotonic() - self._last_refresh_view > 1.0:
            engine = self.sender()
            self.get_last_files(engine.uid)
            self._last_refresh_view = monotonic()

    @pyqtSlot(str)
    def get_last_files(self, uid: str, /) -> None:
        files = self.api.get_last_files(uid, 10)
        if files != self.file_model.files:
            self.file_model.add_files(files)

    def current_language(self) -> Optional[str]:
        lang = Translator.locale()
        for tag, name in self.language_model.languages:
            if tag == lang:
                return name
        return None

    def show_metrics_acceptance(self) -> None:
        """Display a "friendly" dialog box to ask user for metrics approval."""

        tr = Translator.get

        dialog = QDialog()
        dialog.setWindowTitle(tr("SHARE_METRICS_TITLE", values=[APP_NAME]))
        dialog.setWindowIcon(self.icon)
        layout = QVBoxLayout()

        info = QLabel(tr("SHARE_METRICS_MSG", values=[COMPANY]))
        info.setTextFormat(qt.RichText)
        info.setWordWrap(True)
        layout.addWidget(info)

        def analytics_choice(state: Qt.CheckState) -> None:
            Options.use_analytics = bool(state)

        def errors_choice(state: Qt.CheckState) -> None:
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
        buttons.setStandardButtons(qt.Apply)
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
