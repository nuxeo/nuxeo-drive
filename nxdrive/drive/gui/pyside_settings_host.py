"""PySide6 host for the Settings window (which contains the Add Account tab).

The application shell (``QApplication``, systray, main event loop, all engines
and I/O) stays on PyQt6.  When ``Application.show_settings()`` is called the
Settings window is rendered by a *dedicated* PySide6 ``QQuickView`` running its
own ``QQmlEngine`` with PySide6-native adapter objects exposed as QML context
properties.  There is no fallback: if the PySide6 host cannot be built, the
error propagates.

Design constraints
------------------
* PyQt6 and PySide6 ``QObject`` instances **cannot** share parent trees or be
  wired directly through signal/slot connections.  Every PyQt6 signal we care
  about is relayed to its PySide6 counterpart through a plain Python callback
  installed on the PyQt6 side, which then ``emit()``s on the PySide6 side.
* The ``QApplication`` singleton is created by PyQt6.  PySide6 code must use
  ``QApplication.instance()`` — never construct a second one.
* ``CustomWindow`` is a PyQt6 type.  We do not try to host Settings.qml inside
  a ``CustomWindow`` from PySide6; instead we load Settings.qml as the root
  item of a plain PySide6 ``QQuickView`` (which behaves like a top-level
  window and matches Settings.qml's ``Item`` root).
* Only the adapter surface actually referenced by ``Settings.qml`` and its
  sub-tree (5 tabs + popups + delegates + Add Account popups) is mirrored.

If the user later toggles languages, feature flags, engines etc. via the
PySide6 UI, the underlying PyQt6 objects are updated (adapters delegate) and
the PyQt6 rest of the app sees the change through its normal signals.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from nxdrive.drive.constants import (
    APP_NAME,
    APP_SERVER,
    APP_VERSION,
    LINUX,
    WINDOWS,
)
from nxdrive.drive.feature import Beta, DisabledFeatures
from nxdrive.drive.options import Options
from nxdrive.drive.qt.imports import PySide as ps
from nxdrive.drive.qt.imports import QUrl as PyQtQUrl
from nxdrive.drive.translator import Translator
from nxdrive.drive.utils import find_icon, find_resource, sizeof_fmt

# NOTE:  imports above pull from the same modules already used by
# ``application.py``; nothing new is created outside this file.


# ---------------------------------------------------------------------------
# Adapter classes.  Each mirrors the *exact* surface consumed by the Settings
# QML tree.  Method signatures match the PyQt6 originals so QML call sites are
# byte-identical.
# ---------------------------------------------------------------------------


class _ApiAdapter(ps.QObject):
    """PySide6 mirror of ``nxdrive/drive/gui/api.py::QMLDriveApi`` — only the
    slots referenced by Settings.qml, its 5 tabs, popups, delegates and the
    Add Account popups (drive + alfresco variants).
    """

    # Signal referenced at application.py line 429 —
    # ``self.api.setMessage.connect(self._window_root(self.settings_window).setMessage)``
    setMessage = ps.Signal(str, str)

    def __init__(self, pyqt_api: Any, parent: Optional[ps.QObject] = None) -> None:
        super().__init__(parent)
        self._api = pyqt_api

    # ---- log / diagnostics -------------------------------------------------
    @ps.Slot(str)
    def log_qml(self, message: str) -> None:
        self._api.log_qml(message)

    @ps.Slot(result=str)
    def generate_report(self) -> str:
        return self._api.generate_report()

    @ps.Slot(str)
    def open_in_explorer(self, path: str) -> None:
        self._api.open_in_explorer(path)

    # ---- features / update url --------------------------------------------
    @ps.Slot(result=list)
    def get_features_list(self) -> List[List[str]]:
        return self._api.get_features_list()

    @ps.Slot(result=str)
    def get_update_url(self) -> str:
        return self._api.get_update_url()

    # ---- proxy / deletion behavior ----------------------------------------
    @ps.Slot(result=str)
    def get_proxy_settings(self) -> str:
        return self._api.get_proxy_settings()

    @ps.Slot(str, str, str, result=bool)
    def set_proxy_settings(self, config: str, url: str, pac_url: str) -> bool:
        return self._api.set_proxy_settings(config, url, pac_url)

    @ps.Slot(result=str)
    def get_deletion_behavior(self) -> str:
        return self._api.get_deletion_behavior()

    @ps.Slot(str)
    def set_deletion_behavior(self, behavior: str) -> None:
        self._api.set_deletion_behavior(behavior)

    # ---- accounts / auth ---------------------------------------------------
    @ps.Slot(result=str)
    def default_server_local_folder(self) -> str:
        return self._api.default_server_local_folder()

    @ps.Slot(result=str)
    def default_server_url_value(self) -> str:
        return self._api.default_server_url_value()

    @ps.Slot(str, result=str)
    def get_free_disk_space(self, path: str) -> str:
        return self._api.get_free_disk_space(path)

    @ps.Slot(ps.QUrl, result=str)
    def to_local_file(self, url: ps.QUrl) -> str:
        # PyQt6 ``to_local_file`` takes a PyQt6 QUrl.  Convert the PySide6
        # QUrl to a string and back to a PyQt6 QUrl before delegating.
        return self._api.to_local_file(PyQtQUrl(url.toString()))

    @ps.Slot(str, str, bool)
    def web_authentication(
        self, server_url: str, local_folder: str, use_new_account: bool
    ) -> None:  # noqa: E501
        self._api.web_authentication(server_url, local_folder, use_new_account)

    @ps.Slot(str, str, str, str)
    def password_auth(
        self, username: str, password: str, server_url: str, local_folder: str
    ) -> None:  # noqa: E501
        self._api.password_auth(username, password, server_url, local_folder)

    @ps.Slot(str, result=str)
    def alfresco_probe_capabilities(self, server_url: str) -> str:
        return self._api.alfresco_probe_capabilities(server_url)

    @ps.Slot(str, result=bool)
    def has_invalid_credentials(self, uid: str) -> bool:
        return self._api.has_invalid_credentials(uid)

    @ps.Slot(str)
    def open_remote_server(self, uid: str) -> None:
        self._api.open_remote_server(uid)

    @ps.Slot(str, str, result=bool)
    def set_server_ui(self, uid: str, server_ui: str) -> bool:
        return self._api.set_server_ui(uid, server_ui)

    @ps.Slot(str)
    def show_conflicts_resolution(self, uid: str) -> None:
        self._api.show_conflicts_resolution(uid)

    @ps.Slot(str, bool)
    def unbind_server(self, uid: str, purge: bool) -> None:
        self._api.unbind_server(uid, purge)

    @ps.Slot(str)
    def web_update_token(self, uid: str) -> None:
        self._api.web_update_token(uid)


class _ManagerAdapter(ps.QObject):
    """PySide6 mirror for the ``manager`` context property."""

    def __init__(self, pyqt_manager: Any, parent: Optional[ps.QObject] = None) -> None:
        super().__init__(parent)
        self._manager = pyqt_manager

    @ps.Slot(str, result=bool)
    def get_feature_state(self, name: str) -> bool:
        return self._manager.get_feature_state(name)

    @ps.Slot(str, bool)
    def set_feature_state(self, name: str, value: bool) -> None:
        self._manager.set_feature_state(name, value)

    @ps.Slot(result=bool)
    def get_auto_start(self) -> bool:
        return self._manager.get_auto_start()

    @ps.Slot(bool)
    def set_auto_start(self, value: bool) -> None:
        self._manager.set_auto_start(value)

    @ps.Slot(result=bool)
    def get_auto_update(self) -> bool:
        return self._manager.get_auto_update()

    @ps.Slot(bool)
    def set_auto_update(self, value: bool) -> None:
        self._manager.set_auto_update(value)

    @ps.Slot(result=bool)
    def get_direct_edit_auto_lock(self) -> bool:
        return self._manager.get_direct_edit_auto_lock()

    @ps.Slot(bool)
    def set_direct_edit_auto_lock(self, value: bool) -> None:
        self._manager.set_direct_edit_auto_lock(value)

    @ps.Slot(result=bool)
    def use_light_icons(self) -> bool:
        return self._manager.use_light_icons()

    @ps.Slot(bool)
    def set_light_icons(self, value: bool) -> None:
        self._manager.set_light_icons(value)

    @ps.Slot(result=bool)
    def use_sentry(self) -> bool:
        return self._manager.use_sentry()

    @ps.Slot(bool)
    def set_sentry(self, value: bool) -> None:
        self._manager.set_sentry(value)

    @ps.Slot(result=str)
    def get_update_channel(self) -> str:
        return self._manager.get_update_channel()

    @ps.Slot(str)
    def set_update_channel(self, value: str) -> None:
        self._manager.set_update_channel(value)

    @ps.Slot(result=str)
    def get_log_level(self) -> str:
        return self._manager.get_log_level()

    @ps.Slot(str)
    def set_log_level(self, value: str) -> None:
        self._manager.set_log_level(value)


class _OsiAdapter(ps.QObject):
    """PySide6 mirror for the ``osi`` context property."""

    def __init__(self, pyqt_osi: Any, parent: Optional[ps.QObject] = None) -> None:
        super().__init__(parent)
        self._osi = pyqt_osi

    @ps.Slot(result=bool)
    def addons_installed(self) -> bool:
        return self._osi.addons_installed()

    @ps.Slot(result=bool)
    def install_addons(self) -> bool:
        return self._osi.install_addons()


class _TranslatorAdapter(ps.QObject):
    """PySide6 mirror for the ``tl`` context property (Translator).

    The QML surface only uses ``tl.tr`` (as a binding-triggering property) and
    ``tl.set_language(tag)``.  Every time the PyQt6 Translator's language
    changes we re-emit ``languageChanged`` on this adapter so QML re-evaluates.
    """

    languageChanged = ps.Signal()

    def __init__(self, parent: Optional[ps.QObject] = None) -> None:
        super().__init__(parent)
        Translator.singleton.languageChanged.connect(self._on_language_changed)

    def _on_language_changed(self) -> None:
        self.languageChanged.emit()

    @ps.Property(str, notify=languageChanged)
    def tr(self) -> str:
        # Same value as PyQt6 Translator.tr — an empty string used only as a
        # dummy binding target.
        return ""

    @ps.Slot(str)
    def set_language(self, lang: str) -> None:
        Translator.singleton.set_language(lang)


class _EngineModelAdapter(ps.QAbstractListModel):
    """PySide6 mirror of ``view.py::EngineModel``.

    Reads engine state through ``application.manager.engines`` (single source
    of truth) and re-emits row insert / remove notifications on top of the
    PyQt6 ``engineChanged`` signal.
    """

    _UID = ps.Qt.UserRole + 1
    _TYPE = ps.Qt.UserRole + 2
    _FOLDER = ps.Qt.UserRole + 3
    _URL = ps.Qt.UserRole + 4
    _UI = ps.Qt.UserRole + 5
    _FORCE_UI = ps.Qt.UserRole + 6
    _ACCOUNT = ps.Qt.UserRole + 7

    _ROLE_NAMES: Dict[int, bytes] = {
        _UID: b"uid",
        _TYPE: b"type",
        _FOLDER: b"folder",
        _URL: b"server_url",
        _UI: b"wui",
        _FORCE_UI: b"force_ui",
        _ACCOUNT: b"remote_user",
    }

    engineChanged = ps.Signal()
    uiChanged = ps.Signal(str)
    authChanged = ps.Signal(str)

    def __init__(self, application: Any, parent: Optional[ps.QObject] = None) -> None:
        super().__init__(parent)
        self._application = application
        self._pyqt_model = application.engine_model
        self._engines_uid: List[str] = list(self._pyqt_model.engines_uid)
        # Relay PyQt6 signals to PySide6 mirror
        self._pyqt_model.engineChanged.connect(self._on_engine_changed)
        self._pyqt_model.uiChanged.connect(self._on_ui_changed)
        self._pyqt_model.authChanged.connect(self._on_auth_changed)

    def _on_engine_changed(self) -> None:
        # Full resync — beginResetModel/endResetModel is safe and simple for a
        # small list of engines.
        self.beginResetModel()
        self._engines_uid = list(self._pyqt_model.engines_uid)
        self.endResetModel()
        self.engineChanged.emit()

    def _on_ui_changed(self, uid: str) -> None:
        try:
            row = self._engines_uid.index(uid)
        except ValueError:
            return
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [self._UI, self._FORCE_UI])
        self.uiChanged.emit(uid)

    def _on_auth_changed(self, uid: str) -> None:
        try:
            row = self._engines_uid.index(uid)
        except ValueError:
            return
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [self._ACCOUNT])
        self.authChanged.emit(uid)

    def roleNames(self) -> Dict[int, ps.QByteArray]:
        return {role: ps.QByteArray(name) for role, name in self._ROLE_NAMES.items()}

    def rowCount(self, parent: ps.QModelIndex = ps.QModelIndex()) -> int:
        return len(self._engines_uid)

    def data(self, index: ps.QModelIndex, role: int = ps.Qt.DisplayRole) -> Any:
        row = index.row()
        if row < 0 or row >= len(self._engines_uid):
            return None
        uid = self._engines_uid[row]
        engine = self._application.manager.engines.get(uid)
        if engine is None:
            return ""
        attr = self._ROLE_NAMES.get(role)
        if attr is None:
            return None
        return getattr(engine, attr.decode(), "")

    @ps.Slot(int, str, result=str)
    def get(self, index: int, role: str = "uid") -> str:
        if index < 0 or index >= len(self._engines_uid):
            return ""
        uid = self._engines_uid[index]
        engine = self._application.manager.engines.get(uid)
        if engine is None:
            return ""
        return getattr(engine, role, "")

    @ps.Property(int, notify=engineChanged)
    def count(self) -> int:
        return len(self._engines_uid)


class _LanguageModelAdapter(ps.QAbstractListModel):
    """PySide6 mirror of ``view.py::LanguageModel``.  Static list — no signals
    to relay (languages are populated once at app init).
    """

    _NAME = ps.Qt.UserRole + 1
    _TAG = ps.Qt.UserRole + 2

    def __init__(
        self, pyqt_language_model: Any, parent: Optional[ps.QObject] = None
    ) -> None:
        super().__init__(parent)
        self._languages: List[Tuple[str, str]] = list(pyqt_language_model.languages)

    def roleNames(self) -> Dict[int, ps.QByteArray]:
        return {
            self._NAME: ps.QByteArray(b"name"),
            self._TAG: ps.QByteArray(b"tag"),
        }

    def rowCount(self, parent: ps.QModelIndex = ps.QModelIndex()) -> int:
        return len(self._languages)

    def data(self, index: ps.QModelIndex, role: int = ps.Qt.DisplayRole) -> Any:
        row = index.row()
        if row < 0 or row >= len(self._languages):
            return None
        tag, name = self._languages[row]
        if role == self._NAME:
            return name
        if role == self._TAG:
            return tag
        return None

    @ps.Slot(int, result=str)
    def getTag(self, index: int) -> str:
        return self._languages[index][0]

    @ps.Slot(int, result=str)
    def getName(self, index: int) -> str:
        return self._languages[index][1]


class _FeatureModelAdapter(ps.QObject):
    """PySide6 mirror of ``view.py::FeatureModel``.  Exposes ``enabled`` as a
    QML property with a ``stateChanged`` notify signal, relayed from the
    PyQt6 FeatureModel.
    """

    stateChanged = ps.Signal()

    def __init__(
        self, pyqt_feature_model: Any, parent: Optional[ps.QObject] = None
    ) -> None:
        super().__init__(parent)
        self._model = pyqt_feature_model
        self._model.stateChanged.connect(self._on_state_changed)

    def _on_state_changed(self) -> None:
        self.stateChanged.emit()

    @ps.Property(bool, notify=stateChanged)
    def enabled(self) -> bool:
        return bool(self._model.enabled)


# ---------------------------------------------------------------------------
# Host
# ---------------------------------------------------------------------------


class PySideSettingsHost:
    """Owns the PySide6 ``QQuickView`` + ``QQmlEngine`` that render Settings.qml.

    Lifecycle:
        host = PySideSettingsHost(application)
        host.show("Accounts")   # first call lazily builds the engine
        host.close()

    The instance is created eagerly by ``Application.__init__`` but the QML
    engine is only built on the first ``show()`` call, matching the deferred
    cost of the PyQt6 settings window.
    """

    _SECTIONS = {
        "Features": 0,
        "Accounts": 1,
        "Sync": 2,
        "Advanced": 3,
        "About": 4,
    }

    def __init__(self, application: Any) -> None:
        self._application = application
        self._view: Optional[ps.QQuickView] = None
        # Keep adapters alive for the lifetime of the host — otherwise QML
        # context properties will point at freed Python objects.
        self._adapters: List[ps.QObject] = []
        # Relay bridge for api.setMessage — installed once the view exists so
        # the settings root Item's setMessage signal fires from PyQt6 events.
        self._setmessage_bridge = None

    # -- public --------------------------------------------------------------

    def show(self, section: str) -> None:
        if self._view is None:
            self._build()
        assert self._view is not None
        root = self._view.rootObject()
        if root is not None:
            try:
                root.setSection.emit(self._SECTIONS[section])
            except AttributeError:
                # setSection is defined on Settings.qml's root Item — if it is
                # not present the QML failed to load; re-raise loudly.
                raise
        self._view.show()
        self._view.raise_()
        self._view.requestActivate()

    def close(self) -> None:
        if self._view is not None:
            self._view.close()

    # -- internal ------------------------------------------------------------

    def _build(self) -> None:
        view = ps.QQuickView()
        view.setResizeMode(ps.QQuickView.ResizeMode.SizeRootObjectToView)
        view.setTitle(Translator.get("SETTINGS_WINDOW_TITLE", values=[APP_NAME]))
        icon_path = find_icon("app_icon.svg")
        if icon_path:
            view.setIcon(ps.QIcon(str(icon_path)))
        view.setMinimumSize(ps.QSize(640, 580))
        self._view = view

        self._fill_context(view.rootContext())

        qml_path = find_resource("qml", file="Settings.qml")
        view.setSource(ps.QUrl.fromLocalFile(str(qml_path)))

        if view.status() != ps.QQuickView.Status.Ready:
            errors = "; ".join(str(e.toString()) for e in view.errors())
            raise RuntimeError(f"PySide6 Settings QML failed to load: {errors}")

        # Wire api.setMessage → root.setMessage
        root = view.rootObject()
        if root is not None:

            def _relay(msg: str, msg_type: str, _root: Any = root) -> None:
                try:
                    _root.setMessage.emit(msg, msg_type)
                except Exception:
                    # If the root Item was destroyed we drop the message.
                    pass

            self._setmessage_bridge = _relay
            self._application.api.setMessage.connect(_relay)

    def _fill_context(self, context: ps.QQmlContext) -> None:
        app = self._application

        # Build adapters (kept alive via self._adapters).
        api_ad = _ApiAdapter(app.api)
        manager_ad = _ManagerAdapter(app.manager)
        osi_ad = _OsiAdapter(app.osi)
        tl_ad = _TranslatorAdapter()
        engine_model_ad = _EngineModelAdapter(app)
        language_model_ad = _LanguageModelAdapter(app.language_model)
        feat_auto_update_ad = _FeatureModelAdapter(app.auto_update_feature_model)
        feat_direct_edit_ad = _FeatureModelAdapter(app.direct_edit_feature_model)
        feat_direct_transfer_ad = _FeatureModelAdapter(
            app.direct_transfer_feature_model
        )
        feat_document_type_ad = _FeatureModelAdapter(
            app.document_type_selection_feature_model
        )
        feat_tasks_management_ad = _FeatureModelAdapter(
            app.tasks_management_feature_model
        )
        feat_synchronization_ad = _FeatureModelAdapter(
            app.synchronization_feature_model
        )

        self._adapters.extend(
            [
                api_ad,
                manager_ad,
                osi_ad,
                tl_ad,
                engine_model_ad,
                language_model_ad,
                feat_auto_update_ad,
                feat_direct_edit_ad,
                feat_direct_transfer_ad,
                feat_document_type_ad,
                feat_tasks_management_ad,
                feat_synchronization_ad,
            ]
        )

        # QObject-backed context properties (adapters)
        context.setContextProperty("api", api_ad)
        context.setContextProperty("manager", manager_ad)
        context.setContextProperty("osi", osi_ad)
        context.setContextProperty("tl", tl_ad)
        context.setContextProperty("EngineModel", engine_model_ad)
        context.setContextProperty("languageModel", language_model_ad)
        context.setContextProperty("feat_auto_update", feat_auto_update_ad)
        context.setContextProperty("feat_direct_edit", feat_direct_edit_ad)
        context.setContextProperty("feat_direct_transfer", feat_direct_transfer_ad)
        context.setContextProperty(
            "feat_document_type_selection", feat_document_type_ad
        )
        context.setContextProperty("feat_tasks_management", feat_tasks_management_ad)
        context.setContextProperty("feat_synchronization", feat_synchronization_ad)

        # Plain data context properties (strings, ints, dicts, url strings).
        # These do not need a binding bridge — they're read once at load time.
        context.setContextProperty("application", None)  # not used by Settings tree
        context.setContextProperty("currentLanguage", app.current_language())
        context.setContextProperty("point_size", app.point_size)
        context.setContextProperty("update_check_delay", Options.update_check_delay)
        context.setContextProperty("isAlpha", Options.is_alpha)
        context.setContextProperty("isFrozen", Options.is_frozen)
        context.setContextProperty("APP_NAME", APP_NAME)
        context.setContextProperty("APP_SERVER", APP_SERVER)
        context.setContextProperty("SERVER_TYPE", Options.server_type)
        context.setContextProperty(
            "serverNewAccountPopupUrl", app._resolve_server_qml_url("new_account")
        )
        context.setContextProperty(
            "serverReloginPopupUrl", app._resolve_server_qml_url("relogin")
        )
        context.setContextProperty("LINUX", LINUX)
        context.setContextProperty("WINDOWS", WINDOWS)
        context.setContextProperty(
            "CHUNK_SIZE",
            sizeof_fmt(Options.chunk_size * 1024 * 1024, suffix=app.tr("BYTE_ABBREV")),
        )
        context.setContextProperty("beta_features", Beta)
        context.setContextProperty("disabled_features", DisabledFeatures)

        version_text = f"{APP_NAME} {APP_VERSION}"
        context.setContextProperty("driveVersionText", version_text)
        metrics = app.manager.get_metrics()
        versions = (
            f"Python {metrics['python_version']}"
            f" & Qt {metrics['qt_version']}"
            f" & Python client {metrics['python_client_version']}"
        )
        if Options.system_wide:
            versions += " [admin]"
        context.setContextProperty("modulesVersionText", versions)
        context.setContextProperty(
            "deviceIdText", f"Device ID: {app.manager.device_id}"
        )

        # Colors (copied verbatim from application._fill_qml_context).
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
            "buttonRedText": "#de350b",
            "buttonGreenText": "#057153",
            "buttonGrayText": "#444747",
            "primaryIcon": "#161616",
            "secondaryIcon": "#525252",
            "disabledIcon": "#C6C6C6",
            "primaryText": "#161616",
            "disabledText": "#C6C6C6",
            "secondaryText": "#525252",
            "progressFilled": "#0066FF",
            "progressFilledLight": "#7D0066FF",
            "popupBackgroundHighlighted": "#F4F4F4",
            "progressEmpty": "#F4F4F4",
            "focusedTab": "#161616",
            "unfocusedTab": "#525252",
            "focusedUnderline": "#0066FF",
            "unfocusedUnderline": "#E0E0E0",
            "settingsTabGroup": "#FFFFFF",
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
            "refreshBackground": "#d0d1d6",
        }
        for name, value in colors.items():
            context.setContextProperty(name, value)
