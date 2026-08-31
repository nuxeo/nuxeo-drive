"""Focused lifecycle coverage for native GUI windows and Application methods."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.drive.gui import application as application_module
from nxdrive.drive.gui.application import Application
from nxdrive.drive.gui.custom_window import CustomWindow
from nxdrive.drive.gui import systray as systray_module
from nxdrive.drive.gui.systray import DriveSystrayIcon, SystrayWindow
from nxdrive.drive.qt import constants as qt
from nxdrive.drive.qt.imports import (
    QEvent,
    QKeyEvent,
    QObject,
    QSize,
    Qt,
    QWindow,
    Signal,
)


class ApplicationMethodHost:
    """Bind Application methods without constructing another QApplication."""

    def __getattr__(self, name):
        attribute = getattr(Application, name)
        descriptor = getattr(attribute, "__get__", None)
        return descriptor(self, type(self)) if descriptor else attribute


def test_custom_window_constructor_sets_parent_and_visibility_handler(qapp):
    parent = QWindow()
    window = CustomWindow(parent)

    assert window.parent() is parent

    window.close()
    parent.close()


def test_custom_window_key_and_visibility_handlers(qapp):
    class TrackingWindow(CustomWindow):
        def __init__(self):
            self.normal_calls = 0
            self.maximized_calls = 0
            super().__init__()

        def showNormal(self):
            self.normal_calls += 1

        def showMaximized(self):
            self.maximized_calls += 1

    window = TrackingWindow()
    escape = QKeyEvent(
        QEvent.Type.KeyPress, qt.Key_Escape, Qt.KeyboardModifier.NoModifier
    )
    other = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier
    )

    window.keyPressEvent(escape)
    window.keyPressEvent(other)
    window._handle_visibility_change(QWindow.Visibility.FullScreen)
    window._handle_visibility_change(QWindow.Visibility.Windowed)

    assert window.normal_calls == 1
    assert window.maximized_calls == 1
    window.close()


def test_systray_window_constructor_sets_fixed_size_and_active_handler(qapp):
    window = SystrayWindow()

    assert window.minimumSize() == QSize(365, 370)
    assert window.maximumSize() == QSize(365, 370)

    window.close()


def test_drive_systray_constructor_and_context_menu(qapp):
    class FakeApplication(QObject):
        aboutToQuit = Signal()

    application = FakeApplication()
    application.message_clicked = Mock()
    application.hide_systray = Mock()
    application.show_systray = Mock()
    application.show_settings = Mock()
    application.open_help = Mock()
    application.exit_app = Mock()
    application.systray_window = Mock()

    with (
        patch.object(systray_module, "MAC", False),
        patch.object(
            systray_module.Translator,
            "get",
            side_effect=lambda message: message,
        ),
    ):
        icon = DriveSystrayIcon(application)

    menu = icon.contextMenu()
    assert icon.application is application
    assert menu is not None
    assert [action.text() for action in menu.actions() if not action.isSeparator()] == [
        "SETTINGS",
        "HELP",
        "QUIT",
    ]

    application.systray_window.isVisible.side_effect = [True, False]
    icon.handle_mouse_click(qt.Trigger)
    icon.handle_mouse_click(qt.Trigger)
    icon.handle_mouse_click(qt.MiddleClick)
    application.hide_systray.assert_called_once_with()
    application.show_systray.assert_called_once_with()
    application.show_settings.assert_called_once_with("Advanced")

    icon.hide()


def test_shutdown_deletes_qml_engine():
    application = ApplicationMethodHost()
    engine = Mock()
    application.app_engine = engine

    application._shutdown()

    engine.deleteLater.assert_called_once_with()
    assert not hasattr(application, "app_engine")


def test_init_workflow_returns_without_engines(monkeypatch):
    application = ApplicationMethodHost()
    application.manager = SimpleNamespace(engines={})
    application.workflow = None
    application.update_workflow = Mock()
    monkeypatch.setattr(application_module.Feature, "tasks_management", True)

    application.init_workflow()

    assert application.workflow is None
    application.update_workflow.assert_not_called()


def test_init_workflow_returns_when_feature_is_disabled(monkeypatch):
    application = ApplicationMethodHost()
    application.manager = SimpleNamespace(engines={"uid": object()})
    application.workflow = None
    application.update_workflow = Mock()
    monkeypatch.setattr(application_module.Feature, "tasks_management", False)

    application.init_workflow()

    assert application.workflow is None
    application.update_workflow.assert_not_called()


def test_init_workflow_returns_without_registered_class(monkeypatch):
    application = ApplicationMethodHost()
    application.manager = SimpleNamespace(engines={"uid": object()})
    application.workflow = None
    application.update_workflow = Mock()
    monkeypatch.setattr(application_module.Feature, "tasks_management", True)
    monkeypatch.setattr(application_module._st, "first_class_path", lambda _name: "")
    monkeypatch.setattr(application_module._st, "load_class", lambda _path: None)

    with pytest.MonkeyPatch.context() as context:
        log_debug = Mock()
        context.setattr(application_module.log, "debug", log_debug)
        application.init_workflow()

    log_debug.assert_called_once_with(
        "No Workflow class registered; skipping task init"
    )
    assert application.workflow is None
    application.update_workflow.assert_not_called()


def test_init_workflow_creates_registered_workflow(monkeypatch):
    class Workflow:
        pass

    application = ApplicationMethodHost()
    application.manager = SimpleNamespace(engines={"uid": object()})
    application.workflow = None
    application.update_workflow = Mock()
    monkeypatch.setattr(application_module.Feature, "tasks_management", True)
    monkeypatch.setattr(
        application_module._st, "first_class_path", lambda _name: "workflow"
    )
    monkeypatch.setattr(application_module._st, "load_class", lambda _path: Workflow)

    application.init_workflow()

    assert isinstance(application.workflow, Workflow)
    assert application._workflow_cls is Workflow
    application.update_workflow.assert_called_once_with()


def test_init_gui_builds_models_windows_and_initial_engine(monkeypatch, tmp_path):
    application = ApplicationMethodHost()
    engine = MagicMock()
    engine.dao = object()
    manager = MagicMock()
    manager.engines = {"uid": engine}
    application.manager = manager
    application.translate = Mock(side_effect=lambda message, values=None: message)
    application.aboutToQuit = MagicMock()
    application._fill_qml_context = Mock()
    application._window_root = Mock()
    application.get_last_files = Mock()
    application.refresh_transfers = Mock()
    application.update_status = Mock()
    application.add_engines = Mock()
    application.remove_engine = Mock()
    application.refresh_conflicts = Mock()
    application.get_last_files = Mock()
    application._update_feature_state = Mock()
    application._on_color_scheme_changed = Mock()

    qml_root = MagicMock()
    qml_window_root = MagicMock()
    application._window_root.return_value = qml_window_root
    windows = [MagicMock() for _ in range(5)]
    qml_root.findChild.side_effect = windows
    app_engine = MagicMock()
    app_engine.rootObjects.return_value = [qml_root]
    style_hints = MagicMock()
    application.styleHints = Mock(return_value=style_hints)
    engine_model = MagicMock()
    engine_model.engines_uid = ["uid"]

    model_names = (
        "ActiveDirectDownloadModel",
        "ActiveSessionModel",
        "CompletedDirectDownloadModel",
        "CompletedSessionModel",
        "DirectDownloadMonitoringModel",
        "DirectTransferModel",
        "EngineModel",
        "FeatureModel",
        "FileModel",
        "LanguageModel",
        "TasksModel",
        "TransferModel",
    )
    model_patches = [
        patch.object(
            application_module,
            name,
            return_value=engine_model if name == "EngineModel" else MagicMock(),
        )
        for name in model_names
    ]
    for model_patch in model_patches:
        model_patch.start()
    monkeypatch.setattr(
        application_module, "find_resource", lambda *_args, **_kwargs: tmp_path / "Main.qml"
    )
    try:
        with (
            patch.object(
                application_module, "QQmlApplicationEngine", return_value=app_engine
            ),
            patch.object(
                application_module.Translator,
                "languages",
                return_value=[("en", "English")],
            ),
        ):
            application.init_gui()
    finally:
        for model_patch in reversed(model_patches):
            model_patch.stop()

    assert application.api is not None
    assert application.engine_model is engine_model
    assert application.conflicts_window is windows[0]
    assert application.settings_window is windows[1]
    assert application.systray_window is windows[2]
    assert application.direct_transfer_window is windows[3]
    assert application.task_manager_window is windows[4]
    application._fill_qml_context.assert_called_once_with(app_engine.rootContext())
    app_engine.load.assert_called_once()
    application.get_last_files.assert_called_once_with("uid")
    application.refresh_transfers.assert_called_once_with(engine.dao)
    application.update_status.assert_called_once_with(engine)
    style_hints.colorSchemeChanged.connect.assert_called_once_with(
        application._on_color_scheme_changed
    )


def test_connect_engine_wires_all_refresh_and_state_signals():
    application = ApplicationMethodHost()
    engine = MagicMock()
    engine.dao = MagicMock()
    manager = MagicMock()
    manager.engines = {"uid": engine}
    application.manager = manager
    application.change_systray_icon = Mock()

    application._connect_engine(engine)

    engine.syncStarted.connect.assert_called_once_with(
        application.change_systray_icon
    )
    engine.rootDeleted.connect.assert_called_once_with(application._root_deleted)
    engine.docDeleted.connect.assert_called_once_with(application._doc_deleted)
    engine.newSyncStarted.connect.assert_called_once_with(application.refresh_files)
    engine.dao.transferUpdated.connect.assert_called_once()
    engine.dao.directTransferUpdated.connect.assert_called_once()
    assert engine.dao.directDownloadUpdated.connect.call_count == 3
    assert engine.dao.sessionUpdated.connect.call_count == 2
    engine.newSyncEnded.connect.assert_any_call(manager.sentry_metrics.send_sync_event)
    engine.newSyncEnded.connect.assert_any_call(engine.remote.metrics.push_sync_event)
    application.change_systray_icon.assert_called_once_with()
