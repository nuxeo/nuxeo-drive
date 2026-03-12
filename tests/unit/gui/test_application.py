"""Unit tests for the Application class methods."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nxdrive.client.workflow import Workflow
from nxdrive.constants import DelAction
from nxdrive.engine.activity import Action
from nxdrive.metrics.constants import CRASHED_HIT, CRASHED_TRACE
from nxdrive.qt import constants as qt
from nxdrive.qt.imports import QCheckBox, QMessageBox, QRect
from nxdrive.translator import Translator
from nxdrive.updater.constants import (
    UPDATE_STATUS_INCOMPATIBLE_SERVER,
    UPDATE_STATUS_UP_TO_DATE,
)


@pytest.fixture
def mock_manager():
    """Create a mock manager for testing."""
    manager = Mock()
    manager.dao = Mock()
    manager.dao.store_bool = Mock()
    manager.engines = {}
    manager.restartNeeded = Mock()
    manager.restartNeeded.emit = Mock()
    manager.reload_client_global_headers = Mock()
    manager._create_workflow_worker = Mock()
    manager.stop_workflow_worker = Mock()
    manager.get_deletion_behavior = Mock(return_value=DelAction.DEL_SERVER)
    manager.set_deletion_behavior = Mock()
    manager.unbind_engine = Mock()
    manager.updater = Mock()
    manager.updater.status = UPDATE_STATUS_UP_TO_DATE
    return manager


@pytest.fixture
def mock_application(mock_manager):
    """Create a mock application instance."""
    app = Mock()
    app.manager = mock_manager
    app.auto_update_feature_model = Mock()
    app.direct_edit_feature_model = Mock()
    app.direct_transfer_feature_model = Mock()
    app.synchronization_feature_model = Mock()
    app.tasks_management_feature_model = Mock()
    app.tasks_management_feature_model.enabled = False
    app.tasks_management_feature_model.restart_needed = False
    app.added_user_engine_list = []
    app.direct_transfer_model = Mock()
    app.transfer_model = Mock()
    app.tray_icon = Mock()
    app.tray_icon.geometry = Mock(return_value=QRect(100, 100, 32, 32))
    app.systray_window = Mock()
    app.systray_window.width = Mock(return_value=400)
    app.systray_window.height = Mock(return_value=600)
    app.systray_window.show = Mock()
    app.systray_window.raise_ = Mock()
    app.systray_window.close = Mock()
    app.systray_window.setX = Mock()
    app.systray_window.setY = Mock()
    app.task_manager_window = Mock()
    app.task_manager_window.close = Mock()
    app.primaryScreen = Mock(return_value=Mock(devicePixelRatio=Mock(return_value=1.0)))
    app.sender = Mock()
    app.translate = Mock(side_effect=lambda x, values=None: x)
    app.question = Mock()
    app.init_workflow = Mock()
    app.close_tasks_window = Mock()
    app.set_icon_state = Mock(return_value=True)
    return app


class TestUpdateFeatureState:
    """Tests for _update_feature_state method."""

    def test_update_feature_state_existing_feature(self, mock_application):
        """Test updating an existing feature."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None):
            app = Application(None)
            app.manager = mock_application.manager
            app.tasks_management_feature_model = Mock()
            app.direct_edit_feature_model = Mock()
            app.direct_edit_feature_model.enabled = False
            app.direct_edit_feature_model.restart_needed = False

            app._update_feature_state("direct_edit", True)

            assert app.direct_edit_feature_model.enabled is True
            app.manager.reload_client_global_headers.assert_called_once()

    def test_update_feature_state_restart_needed(self, mock_application):
        """Test updating a feature that requires restart."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None):
            app = Application(None)
            app.manager = mock_application.manager
            app.tasks_management_feature_model = Mock()
            app.synchronization_feature_model = Mock()
            app.synchronization_feature_model.enabled = False
            app.synchronization_feature_model.restart_needed = True

            app._update_feature_state("synchronization", False)

            assert app.synchronization_feature_model.enabled is False
            app.manager.reload_client_global_headers.assert_called_once()
            app.manager.restartNeeded.emit.assert_called_once()

    def test_update_feature_state_tasks_management_enabled(self, mock_application):
        """Test enabling tasks management feature."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None):
            app = Application(None)
            app.manager = mock_application.manager
            app.tasks_management_feature_model = Mock()
            app.tasks_management_feature_model.enabled = False
            app.tasks_management_feature_model.restart_needed = False
            app.added_user_engine_list = []
            app.init_workflow = Mock()

            app._update_feature_state("tasks_management", True)

            assert app.tasks_management_feature_model.enabled is True
            app.init_workflow.assert_called_once()
            app.manager._create_workflow_worker.assert_called_once()

    def test_update_feature_state_tasks_management_disabled(self, mock_application):
        """Test disabling tasks management feature."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None):
            app = Application(None)
            app.manager = mock_application.manager
            app.tasks_management_feature_model = Mock()
            app.tasks_management_feature_model.enabled = True
            app.tasks_management_feature_model.restart_needed = False
            app.added_user_engine_list = []

            app._update_feature_state("tasks_management", False)

            assert app.tasks_management_feature_model.enabled is False
            assert app.added_user_engine_list == []
            assert Workflow.user_task_list == {}
            app.manager.stop_workflow_worker.assert_called_once()


class TestActionProgressing:
    """Tests for action_progressing method."""

    def test_action_progressing_not_action_instance(self, mock_application):
        """Test with invalid action object."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.direct_transfer_model = mock_application.direct_transfer_model
            app.transfer_model = mock_application.transfer_model

            # Pass a non-Action object
            app.action_progressing("not_an_action")

            # Should not call any model methods
            mock_application.direct_transfer_model.set_progress.assert_not_called()
            mock_application.transfer_model.set_progress.assert_not_called()

    def test_action_progressing_direct_transfer(self, mock_application):
        """Test action progressing for direct transfer."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.direct_transfer_model = mock_application.direct_transfer_model
            app.transfer_model = mock_application.transfer_model

            action = Mock(spec=Action)
            action.export = Mock(return_value={"is_direct_transfer": True})

            app.action_progressing(action)

            mock_application.direct_transfer_model.set_progress.assert_called_once_with(
                {"is_direct_transfer": True}
            )
            mock_application.transfer_model.set_progress.assert_not_called()

    def test_action_progressing_regular_transfer(self, mock_application):
        """Test action progressing for regular transfer."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.direct_transfer_model = mock_application.direct_transfer_model
            app.transfer_model = mock_application.transfer_model

            action = Mock(spec=Action)
            action.export = Mock(return_value={"is_direct_transfer": False})

            app.action_progressing(action)

            mock_application.transfer_model.set_progress.assert_called_once_with(
                {"is_direct_transfer": False}
            )
            mock_application.direct_transfer_model.set_progress.assert_not_called()


class TestQuestion:
    """Tests for question method."""

    def test_question_default_icon(self, mock_application):
        """Test question with default question icon."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.Application._msgbox"
        ) as mock_msgbox:
            app = Application(None)

            mock_msg = Mock(spec=QMessageBox)
            mock_msgbox.return_value = mock_msg

            result = app.question("Test Header", "Test Message")

            mock_msgbox.assert_called_once_with(
                icon=qt.Question,
                header="Test Header",
                message="Test Message",
                execute=False,
            )
            assert result == mock_msg

    def test_question_custom_icon(self, mock_application):
        """Test question with custom icon."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.Application._msgbox"
        ) as mock_msgbox:
            app = Application(None)

            mock_msg = Mock(spec=QMessageBox)
            mock_msgbox.return_value = mock_msg

            result = app.question("Test Header", "Test Message", icon=qt.Warning)

            mock_msgbox.assert_called_once_with(
                icon=qt.Warning,
                header="Test Header",
                message="Test Message",
                execute=False,
            )
            assert result == mock_msg


class TestSendCrashMetrics:
    """Tests for _send_crash_metrics method."""

    def test_send_crash_metrics_no_crash(self, mock_application):
        """Test when there was no crash."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.State"
        ) as mock_state:
            app = Application(None)
            app.manager = mock_application.manager

            mock_state.has_crashed = False
            mock_state.crash_details = ""

            app._send_crash_metrics()

            # Should return early without doing anything

    def test_send_crash_metrics_crash_without_details(self, mock_application):
        """Test sending crash metrics without details."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.State"
        ) as mock_state:
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager

            mock_engine = Mock()
            mock_engine.remote = Mock()
            mock_engine.remote.metrics = Mock()
            mock_engine.remote.metrics.send = Mock()
            app.manager.engines = {"engine1": mock_engine}

            mock_state.has_crashed = True
            mock_state.crash_details = ""

            app._send_crash_metrics()

            mock_engine.remote.metrics.send.assert_called_once_with({CRASHED_HIT: 1})

    def test_send_crash_metrics_crash_with_details(self, mock_application):
        """Test sending crash metrics with details."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.State"
        ) as mock_state:
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager

            mock_engine = Mock()
            mock_engine.remote = Mock()
            mock_engine.remote.metrics = Mock()
            mock_engine.remote.metrics.send = Mock()
            app.manager.engines = {"engine1": mock_engine}

            mock_state.has_crashed = True
            mock_state.crash_details = "Test crash details"

            app._send_crash_metrics()

            mock_engine.remote.metrics.send.assert_called_once_with(
                {CRASHED_HIT: 1, CRASHED_TRACE: "Test crash details"}
            )

    def test_send_crash_metrics_no_remote(self, mock_application):
        """Test sending crash metrics when engine has no remote."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.State"
        ) as mock_state:
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager

            mock_engine = Mock()
            mock_engine.remote = None
            app.manager.engines = {"engine1": mock_engine}

            mock_state.has_crashed = True
            mock_state.crash_details = ""

            # Should not raise an error
            app._send_crash_metrics()

    def test_send_crash_metrics_multiple_engines(self, mock_application):
        """Test sending crash metrics with multiple engines (only first with remote sends)."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.State"
        ) as mock_state:
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager

            mock_engine1 = Mock()
            mock_engine1.remote = Mock()
            mock_engine1.remote.metrics = Mock()
            mock_engine1.remote.metrics.send = Mock()

            mock_engine2 = Mock()
            mock_engine2.remote = Mock()
            mock_engine2.remote.metrics = Mock()
            mock_engine2.remote.metrics.send = Mock()

            app.manager.engines = {"engine1": mock_engine1, "engine2": mock_engine2}

            mock_state.has_crashed = True
            mock_state.crash_details = ""

            app._send_crash_metrics()

            # Only first engine with remote should send
            mock_engine1.remote.metrics.send.assert_called_once()
            mock_engine2.remote.metrics.send.assert_not_called()


class TestRootMoved:
    """Tests for _root_moved method."""

    def test_root_moved_disconnect(self, mock_application):
        """Test disconnecting when root is moved."""
        from nxdrive.engine.engine import Engine
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch.object(
            Translator, "get", side_effect=lambda x, values=None: x
        ):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager

            mock_engine = Mock(spec=Engine)
            mock_engine.uid = "test_engine"
            mock_engine.local_folder = Path("/test/path")
            app.sender = Mock(return_value=mock_engine)

            mock_msg = Mock(spec=QMessageBox)
            mock_msg.addButton = Mock()
            mock_disconnect_btn = Mock()
            mock_msg.addButton.return_value = mock_disconnect_btn
            mock_msg.exec = Mock()
            mock_msg.clickedButton = Mock(return_value=mock_disconnect_btn)

            with patch.object(app, "question", return_value=mock_msg):
                app._root_moved(Path("/new/path"))

                app.manager.unbind_engine.assert_called_once_with("test_engine")


class TestConfirmDeletion:
    """Tests for confirm_deletion method."""

    def test_confirm_deletion_del_server_confirm(self, mock_application):
        """Test confirming deletion on server."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch.object(
            Translator, "get", side_effect=lambda x, values=None: x
        ):
            app = Application(None)
            app.manager = mock_application.manager
            app.manager.get_deletion_behavior.return_value = DelAction.DEL_SERVER

            mock_msg = Mock(spec=QMessageBox)
            mock_confirm_btn = Mock()
            mock_cb = Mock(spec=QCheckBox)
            mock_cb.isChecked = Mock(return_value=False)
            mock_msg.setCheckBox = Mock()
            mock_msg.addButton = Mock(return_value=mock_confirm_btn)
            mock_msg.exec = Mock()
            mock_msg.clickedButton = Mock(return_value=mock_confirm_btn)

            with patch.object(app, "question", return_value=mock_msg), patch(
                "nxdrive.gui.application.QCheckBox", return_value=mock_cb
            ):
                result = app.confirm_deletion(Path("/test/path"))

                assert result == DelAction.DEL_SERVER

    def test_confirm_deletion_del_server_unsync(self, mock_application):
        """Test choosing unsync instead of deletion on server."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch.object(
            Translator, "get", side_effect=lambda x, values=None: x
        ):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager
            app.manager.get_deletion_behavior.return_value = DelAction.DEL_SERVER

            mock_msg = Mock(spec=QMessageBox)
            mock_unsync_btn = Mock()
            mock_confirm_btn = Mock()
            mock_cb = Mock(spec=QCheckBox)
            mock_cb.isChecked = Mock(return_value=False)
            mock_msg.setCheckBox = Mock()

            # Setup button returns
            button_calls = [mock_unsync_btn, Mock(), mock_confirm_btn]
            mock_msg.addButton = Mock(side_effect=button_calls)
            mock_msg.exec = Mock()
            mock_msg.clickedButton = Mock(return_value=mock_unsync_btn)

            # Second dialog for confirmation
            mock_msg2 = Mock(spec=QMessageBox)
            mock_yes_btn = Mock()
            mock_msg2.addButton = Mock(return_value=mock_yes_btn)
            mock_msg2.exec = Mock()
            mock_msg2.clickedButton = Mock(return_value=mock_yes_btn)

            with patch.object(
                app, "question", side_effect=[mock_msg, mock_msg2]
            ), patch("nxdrive.gui.application.QCheckBox", return_value=mock_cb):
                result = app.confirm_deletion(Path("/test/path"))

                assert result == DelAction.UNSYNC
                app.manager.set_deletion_behavior.assert_called_once_with(
                    DelAction.UNSYNC
                )

    def test_confirm_deletion_unsync_mode(self, mock_application):
        """Test deletion with unsync mode."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch.object(
            Translator, "get", side_effect=lambda x, values=None: x
        ):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager
            app.manager.get_deletion_behavior.return_value = DelAction.UNSYNC

            mock_msg = Mock(spec=QMessageBox)
            mock_confirm_btn = Mock()
            mock_cb = Mock(spec=QCheckBox)
            mock_cb.isChecked = Mock(return_value=False)
            mock_msg.setCheckBox = Mock()
            mock_msg.addButton = Mock(return_value=mock_confirm_btn)
            mock_msg.exec = Mock()
            mock_msg.clickedButton = Mock(return_value=mock_confirm_btn)

            with patch.object(app, "question", return_value=mock_msg), patch(
                "nxdrive.gui.application.QCheckBox", return_value=mock_cb
            ):
                result = app.confirm_deletion(Path("/test/path"))

                assert result == DelAction.UNSYNC

    def test_confirm_deletion_dont_ask_again(self, mock_application):
        """Test deletion with 'don't ask again' checked."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch.object(
            Translator, "get", side_effect=lambda x, values=None: x
        ):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager
            app.manager.get_deletion_behavior.return_value = DelAction.DEL_SERVER

            mock_msg = Mock(spec=QMessageBox)
            mock_confirm_btn = Mock()
            mock_cb = Mock(spec=QCheckBox)
            mock_cb.isChecked = Mock(return_value=True)
            mock_msg.setCheckBox = Mock()
            mock_msg.addButton = Mock(return_value=mock_confirm_btn)
            mock_msg.exec = Mock()
            mock_msg.clickedButton = Mock(return_value=mock_confirm_btn)

            with patch.object(app, "question", return_value=mock_msg), patch(
                "nxdrive.gui.application.QCheckBox", return_value=mock_cb
            ):
                result = app.confirm_deletion(Path("/test/path"))

                assert result == DelAction.DEL_SERVER
                app.manager.dao.store_bool.assert_called_once_with(
                    "show_deletion_prompt", False
                )


class TestChangeSystrayIcon:
    """Tests for change_systray_icon method."""

    def test_change_systray_icon_update_available(self, mock_application):
        """Test icon change when update is available."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager
            app.set_icon_state = Mock(return_value=True)
            app.manager.updater.status = UPDATE_STATUS_INCOMPATIBLE_SERVER

            app.change_systray_icon()

            app.set_icon_state.assert_called_once_with("update")

    def test_change_systray_icon_paused(self, mock_application):
        """Test icon change when engine is paused."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.Action"
        ) as mock_action_class:
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager
            app.set_icon_state = Mock(return_value=True)
            app.manager.updater.status = UPDATE_STATUS_UP_TO_DATE

            mock_engine = Mock()
            mock_engine.is_syncing = Mock(return_value=False)
            mock_engine.has_invalid_credentials = Mock(return_value=False)
            mock_engine.is_paused = Mock(return_value=True)
            mock_engine.is_offline = Mock(return_value=False)
            mock_engine.get_conflicts = Mock(return_value=[])
            app.manager.engines = {"engine1": mock_engine}

            app.change_systray_icon()

            app.set_icon_state.assert_called_once_with("paused")
            mock_action_class.finish_action.assert_called_once()

    def test_change_systray_icon_syncing(self, mock_application):
        """Test icon change when engine is syncing."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager
            app.set_icon_state = Mock(return_value=True)
            app.manager.updater.status = UPDATE_STATUS_UP_TO_DATE

            mock_engine = Mock()
            mock_engine.is_syncing = Mock(return_value=True)
            mock_engine.has_invalid_credentials = Mock(return_value=False)
            mock_engine.is_paused = Mock(return_value=False)
            mock_engine.is_offline = Mock(return_value=False)
            mock_engine.get_conflicts = Mock(return_value=[])
            app.manager.engines = {"engine1": mock_engine}

            app.change_systray_icon()

            app.set_icon_state.assert_called_once_with("syncing")

    def test_change_systray_icon_conflict(self, mock_application):
        """Test icon change when there are conflicts."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager
            app.set_icon_state = Mock(return_value=True)
            app.manager.updater.status = UPDATE_STATUS_UP_TO_DATE

            mock_engine = Mock()
            mock_engine.is_syncing = Mock(return_value=False)
            mock_engine.has_invalid_credentials = Mock(return_value=False)
            mock_engine.is_paused = Mock(return_value=False)
            mock_engine.is_offline = Mock(return_value=False)
            mock_engine.get_conflicts = Mock(return_value=["conflict1"])
            app.manager.engines = {"engine1": mock_engine}

            app.change_systray_icon()

            app.set_icon_state.assert_called_once_with("conflict")

    def test_change_systray_icon_idle(self, mock_application):
        """Test icon change when engine is idle."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.Action"
        ) as mock_action_class:
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.manager = mock_application.manager
            app.set_icon_state = Mock(return_value=True)
            app.manager.updater.status = UPDATE_STATUS_UP_TO_DATE

            mock_engine = Mock()
            mock_engine.is_syncing = Mock(return_value=False)
            mock_engine.has_invalid_credentials = Mock(return_value=False)
            mock_engine.is_paused = Mock(return_value=False)
            mock_engine.is_offline = Mock(return_value=False)
            mock_engine.get_conflicts = Mock(return_value=[])
            app.manager.engines = {"engine1": mock_engine}

            app.change_systray_icon()

            app.set_icon_state.assert_called_once_with("idle")
            mock_action_class.finish_action.assert_called_once()


class TestShowSystray:
    """Tests for show_systray method."""

    def test_show_systray_with_geometry(self, mock_application):
        """Test showing systray with valid geometry."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.WINDOWS", False
        ):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.close_tasks_window = Mock()
            app.systray_window = mock_application.systray_window
            app.tray_icon = mock_application.tray_icon
            app.primaryScreen = mock_application.primaryScreen

            app.show_systray()

            app.close_tasks_window.assert_called_once()
            app.systray_window.close.assert_called_once()
            app.systray_window.setX.assert_called_once()
            app.systray_window.setY.assert_called_once()
            app.systray_window.show.assert_called_once()
            app.systray_window.raise_.assert_called_once()

    def test_show_systray_empty_geometry(self, mock_application):
        """Test showing systray with empty geometry (fallback to cursor position)."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.WINDOWS", False
        ), patch("nxdrive.gui.application.QCursor") as mock_cursor:
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.close_tasks_window = Mock()
            app.systray_window = mock_application.systray_window
            app.primaryScreen = mock_application.primaryScreen

            # Simulate empty geometry
            mock_empty_rect = Mock()
            mock_empty_rect.isEmpty = Mock(return_value=True)
            app.tray_icon = Mock()
            app.tray_icon.geometry = Mock(return_value=mock_empty_rect)

            mock_pos = Mock()
            mock_pos.x = Mock(return_value=200)
            mock_pos.y = Mock(return_value=300)
            mock_cursor.pos = Mock(return_value=mock_pos)

            app.show_systray()

            app.close_tasks_window.assert_called_once()
            app.systray_window.close.assert_called_once()
            app.systray_window.show.assert_called_once()
            app.systray_window.raise_.assert_called_once()

    def test_show_systray_windows_dpi_scaling(self, mock_application):
        """Test showing systray on Windows with DPI scaling."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.WINDOWS", True
        ):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.close_tasks_window = Mock()
            app.systray_window = mock_application.systray_window
            app.tray_icon = mock_application.tray_icon

            mock_screen = Mock()
            mock_screen.devicePixelRatio = Mock(return_value=2.0)
            app.primaryScreen = Mock(return_value=mock_screen)

            app.show_systray()

            app.close_tasks_window.assert_called_once()
            app.systray_window.close.assert_called_once()
            # DPI ratio of 2.0 should be used for calculations
            app.systray_window.setX.assert_called_once()
            app.systray_window.setY.assert_called_once()
            app.systray_window.show.assert_called_once()
            app.systray_window.raise_.assert_called_once()

    def test_show_systray_negative_y_position(self, mock_application):
        """Test showing systray when calculated y position is negative."""
        from nxdrive.gui.application import Application

        with patch.object(Application, "__init__", lambda x, y: None), patch(
            "nxdrive.gui.application.WINDOWS", False
        ):
            app = Application(None)
            app.tasks_management_feature_model = Mock()
            app.close_tasks_window = Mock()
            app.systray_window = mock_application.systray_window
            app.primaryScreen = mock_application.primaryScreen

            # Set up geometry that would result in negative y
            mock_rect = QRect(50, 50, 32, 32)
            app.tray_icon = Mock()
            app.tray_icon.geometry = Mock(return_value=mock_rect)
            app.systray_window.height = Mock(return_value=800)  # Large height

            app.show_systray()

            # Should adjust y to be below the icon instead
            app.systray_window.setY.assert_called_once()
            # The call should use adjusted position
            call_args = app.systray_window.setY.call_args[0]
            assert isinstance(call_args[0], int)
