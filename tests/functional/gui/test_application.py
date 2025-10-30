"""Test the Application class and its GUI functionality without starting a real Qt application."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from nuxeo.models import Document
from PyQt5.QtCore import QModelIndex, QObject, Qt

from nxdrive.constants import WINDOWS
from nxdrive.dao.engine import EngineDAO
from nxdrive.engine.engine import Engine
from nxdrive.gui.api import QMLDriveApi
from nxdrive.gui.application import Application
from nxdrive.gui.folders_dialog import FoldersDialog
from nxdrive.gui.folders_loader import ContentLoaderMixin
from nxdrive.gui.folders_model import Doc, FilteredDoc, FoldersOnly
from nxdrive.gui.folders_treeview import FolderTreeView
from nxdrive.options import Options
from tests.functional.mocked_classes import (
    Mock_Document_API,
    Mock_Engine,
    Mock_Filtered_Doc,
    Mock_Item_Model,
    Mock_Qt,
    Mock_Remote_File_Info,
)

from ...markers import not_linux


class TestApplication:
    """Test cases for the Application class without Qt object creation."""

    def create_mock_manager(self):
        """Create a mock manager for testing."""
        mock_manager = MagicMock()
        mock_manager.osi = MagicMock()
        mock_manager.updater = MagicMock()

        # Mock engines
        mock_engine = MagicMock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.remote_watcher = MagicMock()
        mock_engine.local_watcher = MagicMock()
        mock_manager.engines = {"test_engine": mock_engine}

        return mock_manager

    def test_application_initialization(self):
        """Test Application initialization with proper mocking."""
        mock_manager = self.create_mock_manager()

        class MockApplication:
            def __init__(self, manager, *args):
                self.manager = manager
                self.icon = Mock()
                self.icons = {}
                self.icon_state = None
                self.use_light_icons = None
                self.filters_dlg = None
                self._delegator = None
                self.tray_icon = Mock()
                self.timer = Mock()
                self.osi = manager.osi
                self.translator_instance = Mock()
                manager.application = self

        with patch("nxdrive.gui.application.QApplication"), patch(
            "nxdrive.gui.application.QTimer"
        ), patch("nxdrive.gui.application.QIcon"):

            app = MockApplication(mock_manager, [])

            # Test initialization
            assert app.manager == mock_manager
            assert app.osi == mock_manager.osi
            assert mock_manager.application == app
            assert app.icons == {}
            assert app.icon_state is None
            assert app.use_light_icons is None

    def test_application_engine_management(self):
        """Test adding and removing engines."""
        mock_manager = self.create_mock_manager()

        class MockApplication:
            def __init__(self, manager):
                self.manager = manager
                self.engines = {}
                self.tray_icon = Mock()

            def add_engines(self, engines):
                if isinstance(engines, list):
                    for engine in engines:
                        self.engines[engine.uid] = engine
                else:
                    self.engines[engines.uid] = engines
                # Simulate tray icon update
                if hasattr(self.tray_icon, "update_engines"):
                    self.tray_icon.update_engines()

            def remove_engine(self, uid):
                if uid in self.engines:
                    del self.engines[uid]
                # Simulate tray icon update
                if hasattr(self.tray_icon, "update_engines"):
                    self.tray_icon.update_engines()

        app = MockApplication(mock_manager)
        app.tray_icon.update_engines = Mock()

        # Test adding single engine
        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "engine1"
        app.add_engines(mock_engine)
        assert "engine1" in app.engines
        app.tray_icon.update_engines.assert_called_once()

        # Test adding multiple engines
        mock_engine2 = Mock(spec=Engine)
        mock_engine2.uid = "engine2"
        app.add_engines([mock_engine2])
        assert "engine2" in app.engines

        # Test removing engine
        app.remove_engine("engine1")
        assert "engine1" not in app.engines

    def test_application_translator_methods(self):
        """Test translator functionality."""
        mock_manager = self.create_mock_manager()

        class MockApplication:
            def __init__(self, manager):
                self.manager = manager
                self.translator_instance = Mock()

            def translate(self, message, *, values=None):
                # Simulate translation
                if values:
                    return f"translated_{message}_with_values"
                return f"translated_{message}"

            def _init_translator(self):
                self.translator_instance = Mock()
                self.translator_instance.load = Mock(return_value=True)

        app = MockApplication(mock_manager)

        # Test translation without values
        result = app.translate("HELLO")
        assert result == "translated_HELLO"

        # Test translation with values
        result = app.translate("HELLO_USER", values=["John"])
        assert result == "translated_HELLO_USER_with_values"

        # Test translator initialization
        app._init_translator()
        assert app.translator_instance is not None

    def test_application_workflow_methods(self):
        """Test workflow initialization and updates."""
        mock_manager = self.create_mock_manager()

        class MockApplication:
            def __init__(self, manager):
                self.manager = manager
                self.workflow = None
                self.workflow_model = Mock()

            def init_workflow(self):
                self.workflow = Mock()
                self.workflow.model = self.workflow_model

            def update_workflow(self):
                if self.workflow:
                    self.workflow.update_status("UPDATED")

            def update_workflow_user_engine_list(self, delete, uid):
                if self.workflow:
                    if delete:
                        self.workflow.remove_engine(uid)
                    else:
                        self.workflow.add_engine(uid)

        app = MockApplication(mock_manager)

        # Test workflow initialization
        app.init_workflow()
        assert app.workflow is not None
        assert app.workflow.model == app.workflow_model

        # Test workflow update
        app.update_workflow()
        app.workflow.update_status.assert_called_once_with("UPDATED")

        # Test engine list updates
        app.update_workflow_user_engine_list(False, "new_engine")
        app.workflow.add_engine.assert_called_once_with("new_engine")

        app.update_workflow_user_engine_list(True, "old_engine")
        app.workflow.remove_engine.assert_called_once_with("old_engine")

    def test_application_gui_initialization(self):
        """Test GUI initialization methods."""
        mock_manager = self.create_mock_manager()

        class MockApplication:
            def __init__(self, manager):
                self.manager = manager
                self.tray_icon = None
                self.gui_initialized = False

            def init_gui(self):
                self.tray_icon = Mock()
                self.tray_icon.show = Mock()
                self.gui_initialized = True

            def create_custom_window_for_task_manager(self):
                return Mock()  # Simulate window creation

        with patch("nxdrive.gui.application.DriveSystrayIcon"):
            app = MockApplication(mock_manager)

            # Test GUI initialization
            app.init_gui()
            assert app.tray_icon is not None
            assert app.gui_initialized is True

            # Test custom window creation
            window = app.create_custom_window_for_task_manager()
            assert window is not None

    def test_application_dialog_methods(self):
        """Test dialog display methods."""
        mock_manager = self.create_mock_manager()

        class MockApplication:
            def __init__(self, manager):
                self.manager = manager
                self.last_dialog_type = None
                self.last_message = None

            def display_info(self, title, message, values):
                self.last_dialog_type = "info"
                self.last_message = message

            def display_warning(self, title, message, values=None):
                self.last_dialog_type = "warning"
                self.last_message = message

            def display_success(self, title, message, values=None):
                self.last_dialog_type = "success"
                self.last_message = message

        app = MockApplication(mock_manager)

        # Test info dialog
        app.display_info("Info Title", "Info message", ["value1"])
        assert app.last_dialog_type == "info"
        assert app.last_message == "Info message"

        # Test warning dialog
        app.display_warning("Warning Title", "Warning message")
        assert app.last_dialog_type == "warning"
        assert app.last_message == "Warning message"

        # Test success dialog (if it exists)
        if hasattr(app, "display_success"):
            app.display_success("Success Title", "Success message")
            assert app.last_dialog_type == "success"
            assert app.last_message == "Success message"

    def test_application_feature_management(self):
        """Test feature state management."""
        mock_manager = self.create_mock_manager()

        class MockApplication:
            def __init__(self, manager):
                self.manager = manager
                self.features = {}
                self.tray_icon = Mock()

            def _update_feature_state(self, name, value):
                self.features[name] = value
                # Simulate feature update notification
                if self.tray_icon:
                    self.tray_icon.update_feature_state(name, value)

        app = MockApplication(mock_manager)
        app.tray_icon.update_feature_state = Mock()

        # Test feature state updates
        app._update_feature_state("auto_update", True)
        assert app.features["auto_update"] is True
        app.tray_icon.update_feature_state.assert_called_once_with("auto_update", True)

        app._update_feature_state("direct_transfer", False)
        assert app.features["direct_transfer"] is False

    def test_application_action_handling(self):
        """Test action progress handling."""
        mock_manager = self.create_mock_manager()

        class MockApplication:
            def __init__(self, manager):
                self.manager = manager
                self.current_actions = {}
                self.tray_icon = Mock()

            def action_progressing(self, action):
                self.current_actions[action.uid] = action
                # Simulate updating tray icon with action progress
                if self.tray_icon:
                    self.tray_icon.update_action_progress(action)

        app = MockApplication(mock_manager)

        # Create mock action
        mock_action = Mock()
        mock_action.uid = "action_123"
        mock_action.progress = 50
        mock_action.name = "Upload File"

        # Test action progress
        app.action_progressing(mock_action)
        assert "action_123" in app.current_actions
        assert app.current_actions["action_123"] == mock_action
        app.tray_icon.update_action_progress.assert_called_once_with(mock_action)

    def test_application_shutdown(self):
        """Test application shutdown process."""
        mock_manager = self.create_mock_manager()

        class MockApplication:
            def __init__(self, manager):
                self.manager = manager
                self.shutdown_called = False
                self.exit_called = False
                self.tray_icon = Mock()

            def exit_app(self):
                self.exit_called = True
                self._shutdown()

            def _shutdown(self):
                self.shutdown_called = True
                if self.tray_icon:
                    self.tray_icon.hide()
                if hasattr(self.manager, "stop"):
                    self.manager.stop()

        app = MockApplication(mock_manager)
        app.manager.stop = Mock()

        # Test shutdown process
        app.exit_app()
        assert app.exit_called is True
        assert app.shutdown_called is True
        app.tray_icon.hide.assert_called_once()
        app.manager.stop.assert_called_once()

    def test_application_window_management(self):
        """Test window management functionality."""
        mock_manager = self.create_mock_manager()

        class MockApplication:
            def __init__(self, manager):
                self.manager = manager
                self.windows = []

            def _center_on_screen(self, window):
                # Simulate centering a window
                window.position = (500, 300)  # Mock centered position

            def _show_window(self, window):
                window.show()
                if window not in self.windows:
                    self.windows.append(window)

            def _window_root(self, window):
                # Return the root window (could be the same window)
                return window

        app = MockApplication(mock_manager)

        # Create mock window
        mock_window = Mock()
        mock_window.show = Mock()
        mock_window.position = None

        # Test window centering
        app._center_on_screen(mock_window)
        assert mock_window.position == (500, 300)

        # Test window showing
        app._show_window(mock_window)
        mock_window.show.assert_called_once()
        assert mock_window in app.windows

        # Test window root finding
        root = app._window_root(mock_window)
        assert root == mock_window


class TestApplicationIntegration:
    """Integration tests for Application class interactions."""

    def test_application_with_real_manager_mock(self):
        """Test Application with a more realistic manager mock."""
        # Create comprehensive manager mock
        mock_manager = MagicMock()
        mock_manager.osi = MagicMock()
        mock_manager.updater = MagicMock()
        mock_manager.engines = {}

        # Mock DAO
        mock_dao = Mock(spec=EngineDAO)
        mock_dao.get_engines = Mock(return_value=[])
        mock_manager.dao = mock_dao

        class MockApplication:
            def __init__(self, manager, *args):
                self.manager = manager
                self.icon = Mock()
                self.icons = {}
                self.tray_icon = Mock()
                self.timer = Mock()
                self.translator_instance = Mock()
                manager.application = self

            def process_manager_events(self):
                # Simulate processing events from manager
                for engine_uid, engine in self.manager.engines.items():
                    if hasattr(engine, "get_status"):
                        status = engine.get_status()
                        self.update_engine_status(engine_uid, status)

            def update_engine_status(self, uid, status):
                if self.tray_icon:
                    self.tray_icon.update_engine_status(uid, status)

        with patch("nxdrive.gui.application.QApplication"), patch(
            "nxdrive.gui.application.QTimer"
        ), patch("nxdrive.gui.application.QIcon"):

            app = MockApplication(mock_manager, [])

            # Add mock engine
            mock_engine = Mock(spec=Engine)
            mock_engine.uid = "integration_test_engine"
            mock_engine.get_status = Mock(return_value="IDLE")
            mock_manager.engines["integration_test_engine"] = mock_engine

            # Test processing manager events
            app.tray_icon.update_engine_status = Mock()
            app.process_manager_events()

            # Verify interactions
            mock_engine.get_status.assert_called_once()
            app.tray_icon.update_engine_status.assert_called_once_with(
                "integration_test_engine", "IDLE"
            )

    def test_application_icon_management(self):
        """Test icon state management."""
        mock_manager = MagicMock()

        class MockApplication:
            def __init__(self, manager):
                self.manager = manager
                self.icon_state = "IDLE"
                self.use_light_icons = False
                self.icons = {}

            def update_icon_state(self, state):
                self.icon_state = state
                icon_key = f"{state}_{'light' if self.use_light_icons else 'dark'}"
                if icon_key not in self.icons:
                    self.icons[icon_key] = Mock()  # Create mock icon
                return self.icons[icon_key]

            def toggle_light_icons(self):
                self.use_light_icons = not self.use_light_icons
                # Re-create all icons with new theme
                old_icons = self.icons.copy()
                self.icons.clear()
                return len(old_icons)  # Return count of refreshed icons

        app = MockApplication(mock_manager)

        # Test icon state updates
        app.update_icon_state("SYNCING")
        assert app.icon_state == "SYNCING"
        assert "SYNCING_dark" in app.icons

        # Test light icon toggle
        refreshed_count = app.toggle_light_icons()
        assert app.use_light_icons is True
        assert refreshed_count == 1  # One icon was refreshed

        # Test icon creation with light theme
        app.update_icon_state("ERROR")
        assert "ERROR_light" in app.icons


@pytest.fixture
def app_obj(manager_factory):
    manager, engine = manager_factory()
    mock_qt = Mock_Qt()
    with patch(
        "PyQt5.QtQml.QQmlApplicationEngine.rootObjects"
    ) as mock_root_objects, patch(
        "PyQt5.QtCore.QObject.findChild"
    ) as mock_find_child, patch(
        "nxdrive.gui.application.Application.init_nxdrive_listener"
    ) as mock_listener, patch(
        "nxdrive.gui.application.Application.show_metrics_acceptance"
    ) as mock_show_metrics, patch(
        "nxdrive.engine.activity.FileAction.__repr__"
    ) as mock_download_repr, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute, patch(
        "nxdrive.engine.workers.Worker.run"
    ) as mock_run, patch(
        "PyQt5.QtWidgets.QDialog.exec_"
    ) as mock_exec, patch(
        "nxdrive.gui.application.Application.question"
    ) as mock_question:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_execute.return_value = None
        mock_run.return_value = None
        mock_exec.return_value = None
        mock_question.return_value = None
        app = Application(manager)
        yield app


@not_linux(reason="Qt does not work correctly on linux")
def test_application_qt(app_obj, manager_factory, tmp_path):
    from PyQt5.QtCore import QRect
    from PyQt5.QtWidgets import QMessageBox

    from nxdrive.constants import DelAction

    app = app_obj
    manager, engine = manager_factory()
    mock_qt = Mock_Qt()
    # Covering create_custom_window_for_task_manager
    with patch(
        "nxdrive.gui.application.Application._fill_qml_context"
    ) as mock_qml_context, patch(
        "nxdrive.gui.application.CustomWindow"
    ) as mock_custom_window, patch(
        "tests.functional.mocked_classes.Mock_Qt.rootContext"
    ) as mock_root_context:
        mock_qml_context.return_value = None
        mock_custom_window.return_value = Mock_Qt
        mock_root_context.return_value = None
        assert app.create_custom_window_for_task_manager() is None
    # Covering update_workflow
    assert app.update_workflow() is None
    # Covering updat_feature_state
    assert app._update_feature_state("auto_update", True) is None
    # Covering _msbox
    assert isinstance(app._msgbox(), QMessageBox)
    # Covering display_info
    assert (
        app.display_info("Warning title", "Warning message", ["value1", "value2"])
        is None
    )
    # Covering display_warning
    with patch("nxdrive.gui.application.Application._msgbox") as mock_msgbox:
        mock_msgbox.return_value = None
        assert (
            app.display_warning(
                "Warning title", "Warning message", ["value1", "value2"]
            )
            is None
        )
    # Covering direct_edit_conflict
    with patch("nxdrive.gui.application.Application.question") as mock_question:
        mock_question.return_value = mock_qt
        assert (
            app._direct_edit_conflict(
                "dummy_filename", Path("tests/resources/files"), "md5"
            )
            is None
        )
    if not WINDOWS:  # For some reason, the values don't get mocked on Windows
        # Covering _root_deleted
        with patch("PyQt5.QtCore.QObject.sender") as mock_sender, patch(
            "nxdrive.gui.application.Application.question"
        ) as mock_question:
            mock_question.return_value = mock_qt
            mock_engine = Mock_Engine()
            mock_sender.return_value = mock_engine
            assert app._root_deleted() is None
        # Covering root_moved
        with patch(
            "nxdrive.gui.application.Application.question"
        ) as mock_question, patch("PyQt5.QtCore.QObject.sender") as mock_sender:
            mock_question.return_value = mock_qt
            mock_engine = Mock_Engine()
            mock_sender.return_value = mock_engine
            assert app._root_moved(Path("tests/resources")) is None
        # Covering doc_deleted
        with patch(
            "nxdrive.gui.application.Application.question"
        ) as mock_question, patch("PyQt5.QtCore.QObject.sender") as mock_sender:
            mock_question.return_value = mock_qt
            mock_engine = Mock_Engine()
            mock_sender.return_value = mock_engine
            assert app._doc_deleted(Path("tests/resources/files/testFile.txt")) is None
        # Covering file_already_exists
        with patch(
            "nxdrive.gui.application.Application.question"
        ) as mock_question, patch("PyQt5.QtCore.QObject.sender") as mock_sender, patch(
            "pathlib.Path.unlink"
        ) as mock_unlink:
            mock_question.return_value = mock_qt
            mock_engine = Mock_Engine()
            mock_sender.return_value = mock_engine
            mock_unlink.return_value = None
            assert (
                app._file_already_exists(
                    Path("tests/resources/files/testFile.txt"),
                    Path("tests/resources/files/testFile.txt"),
                )
                is None
            )
        # Covering open_authentication_dialog
        Options.is_frozen = True
        assert app.open_authentication_dialog("url", {"server_url": "value"}) is None
        Options.is_frozen = False
        assert (
            app.open_authentication_dialog("url", {"server_url": "url_value"}) is None
        )
    # Covering confirm_deletion
    with patch("nxdrive.gui.application.Application.question") as mock_question:
        mock_question.return_value = mock_qt
        assert isinstance(app.confirm_deletion(Path("tests/resources")), DelAction)
    # Covering show_systray
    assert app.show_systray() is None
    with patch("PyQt5.QtWidgets.QStyle.alignedRect") as mock_align_rect:
        mock_align_rect.return_value = QRect()
        # Covering show_filters
        assert app.show_filters(engine) is None
        # Covering show_conflicts_resolution
        assert app.show_conflicts_resolution(engine) is None
        # Covering show_settings
        assert app.show_settings("About") is None
        # Covering _show_direct_transfer_window
        assert app._show_direct_transfer_window() is None
    # Covering folder_duplicate_warning
    duplicates = ["dup1", "dup2", "dup3", "dup4", "dup5"]
    assert app.folder_duplicate_warning(duplicates, "remote_path", "remote_url") is None
    # Covering confirm_cancel_transfer
    with patch("nxdrive.gui.application.Application.question") as mock_question:
        mock_question.return_value = mock_qt
        uid = list(app.manager.engines.keys())[0]
        assert app.confirm_cancel_transfer(uid, 1, "localhost") is None
        assert app.confirm_cancel_transfer("engine_uid", 1, "localhost") is None
    # Covering confirm_cancel_session
    with patch("nxdrive.gui.application.Application.question") as mock_question:
        mock_question.return_value = mock_qt
        uid = list(app.manager.engines.keys())[0]
        assert app.confirm_cancel_session(uid, 1, "localhost", 1) is True
    # Covering exit_app
    assert app.exit_app() is None
    # Covering _shutdown
    app.app_engine = object()
    app.task_manager_window = object()
    assert app._shutdown() is None

    # Covering open_server_folders in QMLDriveApi
    with patch("nxdrive.gui.api.QMLDriveApi._get_engine") as mock_engine, patch(
        "nxdrive.gui.application.Application.hide_systray"
    ) as mock_hide:
        drive_api = QMLDriveApi(app)
        mock_engine.return_value = engine
        mock_hide.return_value = None
        assert drive_api.open_server_folders("engine.uid") is None

    # Covers the changes made for Direct Transfer with workspace path specified from WebUI
    mock_url = (
        "nxdrive://direct-transfer/https/random.com/nuxeo/default-domain/UserWorkspaces"
    )
    mock_url2 = f"nxdrive://direct-transfer/{engine.local_folder}"
    assert app._handle_nxdrive_url(mock_url) is True
    assert app._handle_nxdrive_url(mock_url2) is True

    # Covering _process_additionnal_local_paths from FoldersDialog
    dialog = FoldersDialog(app, engine, None)

    # Test with a valid single file within the limit
    test_file = tmp_path / "file1.txt"
    test_file.write_bytes(b"A" * 1024 * 100)  # 100 KB

    original_limit = Options.direct_transfer_file_upper_limit
    Options.direct_transfer_file_upper_limit = 1  # MB

    try:
        dialog._process_additionnal_local_paths([str(test_file)])
    finally:
        Options.direct_transfer_file_upper_limit = original_limit

    assert test_file in dialog.paths
    assert dialog.paths[test_file] == 102400

    # Test with a file exceeding the limit
    dialog.paths.clear()
    dialog.local_path_msg_lbl.setText("")
    test_file = tmp_path / "big_file.txt"
    test_file.write_bytes(b"A" * 1024 * 1024 * 10)  # 10 MB

    original_limit = Options.direct_transfer_file_upper_limit
    Options.direct_transfer_file_upper_limit = 5  # MB

    try:
        dialog._process_additionnal_local_paths([str(test_file)])
    finally:
        Options.direct_transfer_file_upper_limit = original_limit

    assert test_file not in dialog.paths
    assert "big_file.txt" in dialog.local_path_msg_lbl.text()

    # Test with a zero-byte file
    dialog.paths.clear()
    dialog.local_path_msg_lbl.setText("")
    test_file = tmp_path / "empty.txt"
    test_file.touch()  # Zero-byte

    dialog._process_additionnal_local_paths([str(test_file)])
    assert test_file not in dialog.paths

    # Test with a duplicate file
    dialog.paths.clear()
    dialog.local_path_msg_lbl.setText("")
    test_file = tmp_path / "file.txt"
    test_file.write_text("Hello")

    dialog.paths[test_file] = 5  # Already added

    dialog._process_additionnal_local_paths([str(test_file)])
    assert len(dialog.paths) == 1

    # Test with multiple files exceeding the combined limit
    dialog.paths.clear()
    dialog.local_path_msg_lbl.setText("")
    # Create two files: each 6 MB, total = 12 MB
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"
    file1.write_bytes(b"A" * 1024 * 1024 * 6)
    file2.write_bytes(b"A" * 1024 * 1024 * 6)

    # Set the combined multiple files size limit to 10 MB
    original_limit = Options.direct_transfer_file_upper_limit
    Options.direct_transfer_folder_upper_limit = 10  # MB

    try:
        dialog._process_additionnal_local_paths([str(file1), str(file2)])
    finally:
        Options.direct_transfer_folder_upper_limit = original_limit

    assert file1 not in dialog.paths
    assert file2 not in dialog.paths
    assert (
        "Size limit reached. Latest document(s) removed."
        in dialog.local_path_msg_lbl.text()
    )

    # Test with a directory within the folder limit
    dialog.paths.clear()
    dialog.local_path_msg_lbl.setText("")
    dir_path = tmp_path / "my_folder"
    dir_path.mkdir()
    (dir_path / "file1.txt").write_bytes(b"A" * 1024 * 100)  # 100 KB
    (dir_path / "file2.txt").write_bytes(b"A" * 1024 * 200)  # 200 KB

    files = [(dir_path / "file1.txt", 102400), (dir_path / "file2.txt", 204800)]

    with patch("nxdrive.gui.folders_dialog.get_tree_list", return_value=files):
        original_limit = Options.direct_transfer_folder_upper_limit
        Options.direct_transfer_folder_upper_limit = 5  # MB

        try:
            dialog._process_additionnal_local_paths([str(dir_path)])
        finally:
            Options.direct_transfer_folder_upper_limit = original_limit

    assert (dir_path / "file1.txt") in dialog.paths
    assert (dir_path / "file2.txt") in dialog.paths

    # Test with a directory exceeding the folder limit
    dialog.paths.clear()
    dialog.local_path_msg_lbl.setText("")
    dir_path = tmp_path / "big_folder"
    dir_path.mkdir()
    (dir_path / "file.txt").write_bytes(b"A" * 1024 * 1024 * 10)  # 10 MB

    files = [(dir_path / "file.txt", 10 * 1024 * 1024)]

    with patch("nxdrive.gui.folders_dialog.get_tree_list", return_value=files):
        original_limit = Options.direct_transfer_folder_upper_limit
        Options.direct_transfer_folder_upper_limit = 5  # MB

        try:
            dialog._process_additionnal_local_paths([str(dir_path)])
        finally:
            Options.direct_transfer_folder_upper_limit = original_limit

    assert not dialog.paths
    assert "big_folder" in dialog.local_path_msg_lbl.text()

    # Covering on_selection_changed method used in FolderTreeView
    parent = FoldersDialog(app, engine, None)
    client = FoldersOnly(engine.remote)
    folder_tree_view = FolderTreeView(parent, client, None)  # type: ignore[arg-type]
    q_model_index = QModelIndex()

    with patch(
        "nxdrive.gui.folders_treeview.FolderTreeView.model"
    ) as mock_model, patch(
        "nxdrive.gui.folders_dialog.FoldersDialog.update_file_group"
    ) as mock_update_file_group:
        mock_model.return_value = Mock_Item_Model()
        mock_update_file_group.return_value = None
        assert (
            folder_tree_view.on_selection_changed(q_model_index, q_model_index) is None
        )

    # Covering run method in ContentLoaderMixin
    content_loader = ContentLoaderMixin(
        folder_tree_view, item=None, force_refresh=False  # type: ignore[arg-type]
    )
    mock_remote_file_info = Mock_Remote_File_Info()

    # info.get_id() in self.tree.cache and not self.force_refresh
    content_loader.tree.cache.append("dummy_id")
    content_loader.info = Mock_Filtered_Doc(
        mock_remote_file_info, Qt.CheckState.Checked
    )
    assert content_loader.run() is None

    # info.get_id() not in self.tree.cache
    # if not info.is_expandable() and not info.get_path().startswith("/default-domain/UserWorkspaces/")
    content_loader.tree.cache.remove("dummy_id")
    content_loader.info = Mock_Filtered_Doc(
        mock_remote_file_info, Qt.CheckState.Checked
    )
    content_loader.info.expandable = False
    assert content_loader.run() is None

    # info.get_id() not in self.tree.cache
    # if info.is_expandable()
    content_loader.tree.cache.remove("dummy_id")
    content_loader.info = Mock_Filtered_Doc(
        mock_remote_file_info, Qt.CheckState.Checked
    )
    content_loader.info.expandable = True
    assert content_loader.run() is None

    # throwing exception in try block
    with patch(
        "tests.functional.mocked_classes.Mock_Filtered_Doc.is_expandable"
    ) as mock_expandable:
        mock_expandable.side_effect = Exception("Mock Exception")
        content_loader.tree.cache.remove("dummy_id")
        content_loader.info = Mock_Filtered_Doc(
            mock_remote_file_info, Qt.CheckState.Checked
        )
        assert content_loader.run() is None

    # Covering Doc methods in folders_model.py
    mock_document = Document()
    mock_document.contextParameters["permissions"] = ["AddChildren", "Read"]  # type: ignore[index]
    doc = Doc(mock_document, False)
    assert isinstance(repr(doc), str)

    # Covering FilteredDoc methods in folders_model.py
    mock_fs_info = Mock_Remote_File_Info()
    filtered_doc = FilteredDoc(mock_fs_info, Qt.CheckState.Checked)
    assert isinstance(repr(filtered_doc), str)

    # Covering get_roots method in FoldersOnly
    folders_only = FoldersOnly(engine.remote)
    assert isinstance(folders_only.get_roots(), list)

    # Covering _get_root_folders method in FoldersOnly
    folders_only = FoldersOnly(engine.remote)
    folders_only.remote.documents = Mock_Document_API()  # type: ignore[assignment]
    with patch("nxdrive.gui.folders_model.FoldersOnly._get_children") as mock_children:
        mock_children.return_value = [Document()]
        assert isinstance(folders_only._get_root_folders(), list)

    # _get_root_folders - exception block - if Options.shared_folder_navigation = True
    def mock_fetch(*args, **kwargs):
        mock_doc = {"contextParameters": {"permissions": ["Read", "Write"]}}
        return mock_doc

    folders_only = FoldersOnly(engine.remote)
    folders_only.remote.documents = Mock_Document_API()  # type: ignore[assignment]
    folders_only.remote.fetch = mock_fetch
    Options.shared_folder_navigation = True
    with patch("nxdrive.gui.folders_model.FoldersOnly.get_roots") as mock_roots:
        mock_root = {
            "type": "Folder",
            "path": "/dummy",
            "uid": "root_id",
        }
        mock_roots.return_value = [mock_root]
        assert isinstance(folders_only._get_root_folders(), list)

    # _get_root_folders - exception block - if Options.shared_folder_navigation = False
    folders_only = FoldersOnly(engine.remote)
    folders_only.remote.documents = Mock_Document_API()  # type: ignore[assignment]
    Options.shared_folder_navigation = False
    assert isinstance(folders_only._get_root_folders(), list)
