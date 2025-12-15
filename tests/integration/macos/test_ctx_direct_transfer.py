"""Integration tests for ctx_direct_transfer method - macOS only."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.engine.engine import Engine
from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestCtxDirectTransfer:
    """Test suite for ctx_direct_transfer method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app.filters_dlg = None
        app.display_warning = Mock()
        app.show_server_folders = Mock()

        yield app, manager

        manager.close()

    def test_ctx_direct_transfer_server_config_not_ready(self, mock_application):
        """Test ctx_direct_transfer when server config is not ready."""
        app, manager = mock_application

        test_path = Path("/test/path/file.txt")

        with patch.object(manager, "wait_for_server_config", return_value=False), patch(
            "nxdrive.gui.application.APP_NAME", "TestApp"
        ):
            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path)

            # Verify warning was displayed
            app.display_warning.assert_called_once_with(
                "Direct Transfer - TestApp", "DIRECT_TRANSFER_NOT_POSSIBLE", []
            )
            # Verify show_server_folders was not called
            app.show_server_folders.assert_not_called()

    def test_ctx_direct_transfer_feature_disabled(self, mock_application):
        """Test ctx_direct_transfer when direct transfer feature is disabled."""
        app, manager = mock_application

        test_path = Path("/test/path/file.txt")

        with patch.object(manager, "wait_for_server_config", return_value=True), patch(
            "nxdrive.gui.application.Feature"
        ) as mock_feature, patch("nxdrive.gui.application.APP_NAME", "TestApp"):
            mock_feature.direct_transfer = False

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path)

            # Verify warning was displayed
            app.display_warning.assert_called_once_with(
                "Direct Transfer - TestApp", "DIRECT_TRANSFER_NOT_ENABLED", []
            )
            # Verify show_server_folders was not called
            app.show_server_folders.assert_not_called()

    def test_ctx_direct_transfer_synced_file_not_allowed(self, mock_application):
        """Test ctx_direct_transfer rejects files in synced folders."""
        app, manager = mock_application

        # Create mock engine with local folder
        mock_engine = Mock(spec=Engine)
        mock_engine.local_folder = Path("/sync/folder")

        manager.engines = {"engine1": mock_engine}

        test_path = Path("/sync/folder/subfolder/file.txt")

        with patch.object(manager, "wait_for_server_config", return_value=True), patch(
            "nxdrive.gui.application.Feature"
        ) as mock_feature, patch("nxdrive.gui.application.log"), patch(
            "nxdrive.gui.application.APP_NAME", "TestApp"
        ):
            mock_feature.direct_transfer = True

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path, None, False)

            # Verify warning was displayed
            app.display_warning.assert_called_once_with(
                "Direct Transfer - TestApp",
                "DIRECT_TRANSFER_NOT_ALLOWED",
                [str(test_path)],
            )
            # Verify show_server_folders was not called
            app.show_server_folders.assert_not_called()

    def test_ctx_direct_transfer_no_engines(self, mock_application):
        """Test ctx_direct_transfer when no engines are configured."""
        app, manager = mock_application

        manager.engines = {}
        test_path = Path("/test/path/file.txt")

        with patch.object(manager, "wait_for_server_config", return_value=True), patch(
            "nxdrive.gui.application.Feature"
        ) as mock_feature, patch("nxdrive.gui.application.log"), patch(
            "nxdrive.gui.application.APP_NAME", "TestApp"
        ):
            mock_feature.direct_transfer = True

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path)

            # Verify warning was displayed
            app.display_warning.assert_called_once_with(
                "Direct Transfer - TestApp", "DIRECT_TRANSFER_NO_ACCOUNT", []
            )
            # Verify show_server_folders was not called
            app.show_server_folders.assert_not_called()

    def test_ctx_direct_transfer_single_engine(self, mock_application):
        """Test ctx_direct_transfer with single engine."""
        app, manager = mock_application

        # Create mock engine
        mock_engine = Mock(spec=Engine)
        mock_engine.local_folder = Path("/sync/folder")

        manager.engines = {"engine1": mock_engine}
        test_path = Path("/other/path/file.txt")

        with patch.object(manager, "wait_for_server_config", return_value=True), patch(
            "nxdrive.gui.application.Feature"
        ) as mock_feature, patch("nxdrive.gui.application.log"):
            mock_feature.direct_transfer = True

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path)

            # Verify show_server_folders was called with the engine
            app.show_server_folders.assert_called_once_with(
                mock_engine, test_path, None
            )
            # Verify no warning was displayed
            app.display_warning.assert_not_called()

    def test_ctx_direct_transfer_multiple_engines_user_selects(self, mock_application):
        """Test ctx_direct_transfer with multiple engines and user selection."""
        app, manager = mock_application

        # Create mock engines
        mock_engine1 = Mock(spec=Engine)
        mock_engine1.local_folder = Path("/sync1")

        mock_engine2 = Mock(spec=Engine)
        mock_engine2.local_folder = Path("/sync2")

        manager.engines = {"engine1": mock_engine1, "engine2": mock_engine2}
        test_path = Path("/other/path/file.txt")

        with patch.object(manager, "wait_for_server_config", return_value=True), patch(
            "nxdrive.gui.application.Feature"
        ) as mock_feature, patch("nxdrive.gui.application.log"), patch.object(
            app, "_select_account", return_value=mock_engine1
        ) as mock_select:
            mock_feature.direct_transfer = True

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path)

            # Verify _select_account was called
            mock_select.assert_called_once()
            # Verify show_server_folders was called with selected engine
            app.show_server_folders.assert_called_once_with(
                mock_engine1, test_path, None
            )

    def test_ctx_direct_transfer_multiple_engines_user_cancels(self, mock_application):
        """Test ctx_direct_transfer with multiple engines when user cancels selection."""
        app, manager = mock_application

        # Create mock engines
        mock_engine1 = Mock(spec=Engine)
        mock_engine1.local_folder = Path("/sync1")

        mock_engine2 = Mock(spec=Engine)
        mock_engine2.local_folder = Path("/sync2")

        manager.engines = {"engine1": mock_engine1, "engine2": mock_engine2}
        test_path = Path("/other/path/file.txt")

        with patch.object(manager, "wait_for_server_config", return_value=True), patch(
            "nxdrive.gui.application.Feature"
        ) as mock_feature, patch("nxdrive.gui.application.log"), patch.object(
            app, "_select_account", return_value=None
        ) as mock_select, patch(
            "nxdrive.gui.application.APP_NAME", "TestApp"
        ):
            mock_feature.direct_transfer = True

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path)

            # Verify _select_account was called
            mock_select.assert_called_once()
            # Verify warning was displayed
            app.display_warning.assert_called_once_with(
                "Direct Transfer - TestApp", "DIRECT_TRANSFER_NO_ACCOUNT", []
            )
            # Verify show_server_folders was not called
            app.show_server_folders.assert_not_called()

    def test_ctx_direct_transfer_with_folder_path(self, mock_application):
        """Test ctx_direct_transfer with custom folder_path parameter."""
        app, manager = mock_application

        # Create mock engine
        mock_engine = Mock(spec=Engine)
        mock_engine.local_folder = Path("/sync/folder")

        manager.engines = {"engine1": mock_engine}
        test_path = Path("/other/path/file.txt")
        folder_path = "/custom/server/path"

        with patch.object(manager, "wait_for_server_config", return_value=True), patch(
            "nxdrive.gui.application.Feature"
        ) as mock_feature, patch("nxdrive.gui.application.log"):
            mock_feature.direct_transfer = True

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path, folder_path)

            # Verify show_server_folders was called with folder_path
            app.show_server_folders.assert_called_once_with(
                mock_engine, test_path, folder_path
            )

    def test_ctx_direct_transfer_from_web(self, mock_application):
        """Test ctx_direct_transfer with from_web=True skips sync check."""
        app, manager = mock_application

        # Create mock engine with local folder
        mock_engine = Mock(spec=Engine)
        mock_engine.local_folder = Path("/sync/folder")

        manager.engines = {"engine1": mock_engine}

        # Path that would normally be rejected
        test_path = Path("/sync/folder/subfolder/file.txt")

        with patch.object(manager, "wait_for_server_config", return_value=True), patch(
            "nxdrive.gui.application.Feature"
        ) as mock_feature, patch("nxdrive.gui.application.log"):
            mock_feature.direct_transfer = True

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path, None, True)

            # Verify show_server_folders was called (sync check was skipped)
            app.show_server_folders.assert_called_once_with(
                mock_engine, test_path, None
            )
            # Verify no warning was displayed
            app.display_warning.assert_not_called()

    def test_ctx_direct_transfer_with_folders_dialog(self, mock_application):
        """Test ctx_direct_transfer with active FoldersDialog emits signal."""
        app, manager = mock_application

        # Create mock engine
        mock_engine = Mock(spec=Engine)
        mock_engine.local_folder = Path("/sync/folder")

        manager.engines = {"engine1": mock_engine}
        test_path = Path("/other/path/file.txt")

        # Setup mock FoldersDialog
        mock_dialog = Mock()
        mock_dialog.newCtxTransfer = Mock()
        app.filters_dlg = mock_dialog

        with patch.object(manager, "wait_for_server_config", return_value=True), patch(
            "nxdrive.gui.application.Feature"
        ) as mock_feature, patch("nxdrive.gui.application.log"):
            mock_feature.direct_transfer = True

            # Mock dialog type name
            mock_dialog.__class__.__name__ = "FoldersDialog"

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path)

            # Verify signal was emitted
            mock_dialog.newCtxTransfer.emit.assert_called_once_with([str(test_path)])
            # Verify show_server_folders was not called
            app.show_server_folders.assert_not_called()

    def test_ctx_direct_transfer_with_non_folders_dialog(self, mock_application):
        """Test ctx_direct_transfer with active non-FoldersDialog calls show_server_folders."""
        app, manager = mock_application

        # Create mock engine
        mock_engine = Mock(spec=Engine)
        mock_engine.local_folder = Path("/sync/folder")

        manager.engines = {"engine1": mock_engine}
        test_path = Path("/other/path/file.txt")

        # Setup mock dialog (not FoldersDialog)
        mock_dialog = Mock()
        app.filters_dlg = mock_dialog

        with patch.object(manager, "wait_for_server_config", return_value=True), patch(
            "nxdrive.gui.application.Feature"
        ) as mock_feature, patch("nxdrive.gui.application.log"):
            mock_feature.direct_transfer = True

            # Mock dialog type name (not FoldersDialog)
            mock_dialog.__class__.__name__ = "DocumentsDialog"

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path)

            # Verify show_server_folders was called
            app.show_server_folders.assert_called_once_with(
                mock_engine, test_path, None
            )

    def test_ctx_direct_transfer_logs_path(self, mock_application):
        """Test ctx_direct_transfer logs the path when not from web."""
        app, manager = mock_application

        # Create mock engine
        mock_engine = Mock(spec=Engine)
        mock_engine.local_folder = Path("/sync/folder")

        manager.engines = {"engine1": mock_engine}
        test_path = Path("/other/path/file.txt")

        with patch.object(manager, "wait_for_server_config", return_value=True), patch(
            "nxdrive.gui.application.Feature"
        ) as mock_feature, patch("nxdrive.gui.application.log") as mock_log:
            mock_feature.direct_transfer = True

            from nxdrive.gui.application import Application as RealApp

            bound_method = RealApp.ctx_direct_transfer.__get__(app, Application)
            bound_method(test_path, None, False)

            # Verify logging occurred
            mock_log.info.assert_called_once()
            log_message = mock_log.info.call_args[0][0]
            assert "Direct Transfer" in log_message
            assert str(test_path) in log_message
