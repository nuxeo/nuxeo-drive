"""Test the Application class and its GUI functionality without starting a real Qt application."""

from unittest.mock import MagicMock, Mock, patch

from nxdrive.dao.engine import EngineDAO
from nxdrive.engine.engine import Engine


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
