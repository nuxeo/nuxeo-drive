"""Integration tests for _doc_deleted method - macOS only."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.constants import DelAction
from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestDocDeleted:
    """Test suite for _doc_deleted method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager and engine."""
        manager = Manager(tmp())

        # Create engine mock
        engine = Mock()
        engine.uid = "test_engine"
        engine.rollback_delete = Mock()
        engine.delete_doc = Mock()

        # Create application mock
        app = MagicMock(spec=Application)
        app.manager = manager
        app.icon = Mock()
        app.confirm_deletion = Mock(return_value=DelAction.UNSYNC)

        yield app, manager, engine

        manager.close()

    def test_doc_deleted_with_server_deletion_disabled(self, mock_application):
        """Test document deletion when server deletion behavior is disabled."""
        app, manager, engine = mock_application
        path = Path("/test/path")

        with patch("nxdrive.gui.application.Behavior") as mock_behavior:
            mock_behavior.server_deletion = False

            # Bind and call the method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._doc_deleted.__get__(app, Application)
            app.sender = Mock(return_value=engine)

            bound_method(path)

            # Verify delete_doc called with UNSYNC mode
            engine.delete_doc.assert_called_once_with(path, mode=DelAction.UNSYNC)
            engine.rollback_delete.assert_not_called()
            app.confirm_deletion.assert_not_called()

    def test_doc_deleted_with_rollback(self, mock_application):
        """Test document deletion with rollback action."""
        app, manager, engine = mock_application
        path = Path("/test/path")
        app.confirm_deletion = Mock(return_value=DelAction.ROLLBACK)

        with patch("nxdrive.gui.application.Behavior") as mock_behavior:
            mock_behavior.server_deletion = True

            # Bind and call the method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._doc_deleted.__get__(app, Application)
            app.sender = Mock(return_value=engine)

            bound_method(path)

            # Verify rollback_delete called
            engine.rollback_delete.assert_called_once_with(path)
            engine.delete_doc.assert_not_called()
            app.confirm_deletion.assert_called_once_with(path)

    def test_doc_deleted_with_delete_action(self, mock_application):
        """Test document deletion with delete action."""
        app, manager, engine = mock_application
        path = Path("/test/path")
        app.confirm_deletion = Mock(return_value=DelAction.DEL_SERVER)

        with patch("nxdrive.gui.application.Behavior") as mock_behavior:
            mock_behavior.server_deletion = True

            # Bind and call the method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._doc_deleted.__get__(app, Application)
            app.sender = Mock(return_value=engine)

            bound_method(path)

            # Verify delete_doc called with the returned mode
            engine.delete_doc.assert_called_once_with(path, mode=DelAction.DEL_SERVER)
            engine.rollback_delete.assert_not_called()
            app.confirm_deletion.assert_called_once_with(path)

    def test_doc_deleted_with_unsync_action(self, mock_application):
        """Test document deletion with unsync action."""
        app, manager, engine = mock_application
        path = Path("/test/path")
        app.confirm_deletion = Mock(return_value=DelAction.UNSYNC)

        with patch("nxdrive.gui.application.Behavior") as mock_behavior:
            mock_behavior.server_deletion = True

            # Bind and call the method
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp._doc_deleted.__get__(app, Application)
            app.sender = Mock(return_value=engine)

            bound_method(path)

            # Verify delete_doc called with UNSYNC mode
            engine.delete_doc.assert_called_once_with(path, mode=DelAction.UNSYNC)
            engine.rollback_delete.assert_not_called()
            app.confirm_deletion.assert_called_once_with(path)
