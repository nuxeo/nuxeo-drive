"""Integration tests for Application._root_moved method."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestRootMoved:
    """Tests for Application._root_moved."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock application with manager."""
        manager = Manager(tmp())

        # Create mocked Application
        app = MagicMock(spec=Application)
        app.manager = manager

        # Create a mocked engine
        engine = Mock()
        engine.uid = "test_engine"
        engine.local_folder = Path("/old/path")
        engine.set_local_folder = Mock()
        engine.reinit = Mock()
        engine.start = Mock()

        yield app, manager, engine

    def test_root_moved_disconnect(self, mock_application):
        """Test disconnecting when root is moved."""
        app, manager, engine = mock_application
        new_path = Path("/new/path")

        with patch("nxdrive.gui.application.Translator") as mock_translator:
            mock_translator.get.return_value = "Mocked text"

            # Create the question dialog mock
            question_dialog = Mock()
            question_dialog.exec = Mock()
            disconnect_button = Mock()
            recreate_button = Mock()
            move_button = Mock()

            buttons = [move_button, recreate_button, disconnect_button]
            call_count = [0]

            def add_button_side_effect(text, role):
                button = buttons[call_count[0]]
                call_count[0] += 1
                return button

            question_dialog.addButton = Mock(side_effect=add_button_side_effect)
            question_dialog.clickedButton = Mock(return_value=disconnect_button)

            app.question = Mock(return_value=question_dialog)
            manager.unbind_engine = Mock()

            # Bind and call the method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._root_moved.__get__(app, Application)
            app.sender = Mock(return_value=engine)

            bound_method(new_path)

            # Assertions
            assert question_dialog.exec.called
            manager.unbind_engine.assert_called_once_with(engine.uid)

    def test_root_moved_recreate(self, mock_application):
        """Test recreating when root is moved."""
        app, manager, engine = mock_application
        new_path = Path("/new/path")

        with patch("nxdrive.gui.application.Translator") as mock_translator:
            mock_translator.get.return_value = "Mocked text"

            # Create the question dialog mock
            question_dialog = Mock()
            question_dialog.exec = Mock()
            disconnect_button = Mock()
            recreate_button = Mock()
            move_button = Mock()

            buttons = [move_button, recreate_button, disconnect_button]
            call_count = [0]

            def add_button_side_effect(text, role):
                button = buttons[call_count[0]]
                call_count[0] += 1
                return button

            question_dialog.addButton = Mock(side_effect=add_button_side_effect)
            question_dialog.clickedButton = Mock(return_value=recreate_button)

            app.question = Mock(return_value=question_dialog)
            engine.reinit = Mock()
            engine.start = Mock()

            # Bind and call the method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._root_moved.__get__(app, Application)
            app.sender = Mock(return_value=engine)

            bound_method(new_path)

            # Assertions
            assert question_dialog.exec.called
            engine.reinit.assert_called_once()
            engine.start.assert_called_once()

    def test_root_moved_move(self, mock_application):
        """Test moving to new path when root is moved."""
        app, manager, engine = mock_application
        new_path = Path("/new/path")

        with patch("nxdrive.gui.application.Translator") as mock_translator:
            mock_translator.get.return_value = "Mocked text"

            # Create the question dialog mock
            question_dialog = Mock()
            question_dialog.exec = Mock()
            move_button = Mock()
            recreate_button = Mock()
            disconnect_button = Mock()

            buttons = [move_button, recreate_button, disconnect_button]
            call_count = [0]

            def add_button_side_effect(text, role):
                button = buttons[call_count[0]]
                call_count[0] += 1
                return button

            question_dialog.addButton = Mock(side_effect=add_button_side_effect)
            question_dialog.clickedButton = Mock(return_value=move_button)

            app.question = Mock(return_value=question_dialog)

            # Bind and call the method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._root_moved.__get__(app, Application)
            app.sender = Mock(return_value=engine)

            bound_method(new_path)

            # Assertions
            assert question_dialog.exec.called
            engine.set_local_folder.assert_called_once_with(new_path)
            engine.start.assert_called_once()
