"""Unit tests for DarwinIntegration class methods."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nxdrive.objects import DocPair
from nxdrive.options import Options
from nxdrive.osi.darwin.darwin import DarwinIntegration


@pytest.fixture
def mock_manager():
    """Create a mock manager."""
    manager = Mock()
    manager.version = "1.0.0"
    manager.home = Path("/tmp/nuxeo-drive")
    return manager


@pytest.fixture
def darwin_integration(mock_manager):
    """Create a DarwinIntegration instance for testing."""
    integration = DarwinIntegration(mock_manager)
    return integration


@pytest.fixture
def frozen_app():
    """Set Options.is_frozen to True for testing frozen app behavior."""
    original_value = Options.is_frozen
    Options.set("is_frozen", True, setter="manual")
    yield
    Options.set("is_frozen", original_value, setter="manual")


class TestInit:
    """Test cases for init method."""

    @patch("nxdrive.osi.darwin.darwin.subprocess.check_call")
    def test_init_success(self, mock_check_call, frozen_app, darwin_integration):
        """Test successful initialization of FinderSync."""
        darwin_integration._finder_sync_loaded = False
        darwin_integration.init()

        assert mock_check_call.call_count == 2
        assert darwin_integration._finder_sync_loaded is True

        # Verify the commands called
        calls = mock_check_call.call_args_list
        assert calls[0][0][0] == [
            "pluginkit",
            "-e",
            "use",
            "-i",
            darwin_integration.FINDERSYNC_ID,
        ]
        assert calls[1][0][0] == ["pluginkit", "-a", darwin_integration.FINDERSYNC_PATH]

    @patch("nxdrive.osi.darwin.darwin.subprocess.check_call")
    def test_init_already_loaded(self, mock_check_call, frozen_app, darwin_integration):
        """Test init when FinderSync is already loaded."""
        darwin_integration._finder_sync_loaded = True
        darwin_integration.init()

        # Should not call subprocess if already loaded
        mock_check_call.assert_not_called()

    @patch("nxdrive.osi.darwin.darwin.subprocess.check_call")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_init_error(
        self, mock_log, mock_check_call, frozen_app, darwin_integration
    ):
        """Test init when subprocess fails."""
        mock_check_call.side_effect = subprocess.CalledProcessError(1, "cmd")
        darwin_integration._finder_sync_loaded = False

        darwin_integration.init()

        assert darwin_integration._finder_sync_loaded is False
        mock_log.exception.assert_called_once_with("Error while starting FinderSync")


class TestCleanup:
    """Test cases for cleanup method."""

    @patch("nxdrive.osi.darwin.darwin.subprocess.check_call")
    def test_cleanup_success(self, mock_check_call, frozen_app, darwin_integration):
        """Test successful cleanup of FinderSync."""
        darwin_integration._finder_sync_loaded = True
        darwin_integration.cleanup()

        mock_check_call.assert_called_once()
        assert darwin_integration._finder_sync_loaded is False

        # Verify the command called
        expected_cmd = [
            "pluginkit",
            "-e",
            "ignore",
            "-i",
            darwin_integration.FINDERSYNC_ID,
        ]
        mock_check_call.assert_called_once_with(expected_cmd)

    @patch("nxdrive.osi.darwin.darwin.subprocess.check_call")
    def test_cleanup_not_loaded(self, mock_check_call, frozen_app, darwin_integration):
        """Test cleanup when FinderSync is not loaded."""
        darwin_integration._finder_sync_loaded = False
        darwin_integration.cleanup()

        # Should not call subprocess if not loaded
        mock_check_call.assert_not_called()

    @patch("nxdrive.osi.darwin.darwin.subprocess.check_call")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_cleanup_error(
        self, mock_log, mock_check_call, frozen_app, darwin_integration
    ):
        """Test cleanup when subprocess fails."""
        mock_check_call.side_effect = subprocess.CalledProcessError(1, "cmd")
        darwin_integration._finder_sync_loaded = True

        darwin_integration.cleanup()

        # When error occurs, _finder_sync_loaded stays True
        assert darwin_integration._finder_sync_loaded is True
        mock_log.warning.assert_called_once_with(
            "Error while stopping FinderSync", exc_info=True
        )


class TestOpenLocalFile:
    """Test cases for open_local_file method."""

    @patch("nxdrive.osi.darwin.darwin.subprocess.Popen")
    def test_open_local_file_without_select(self, mock_popen, darwin_integration):
        """Test opening a local file without selection."""
        file_path = "/Users/test/file.txt"
        darwin_integration.open_local_file(file_path)

        mock_popen.assert_called_once_with(["open", file_path])

    @patch("nxdrive.osi.darwin.darwin.subprocess.Popen")
    def test_open_local_file_with_select(self, mock_popen, darwin_integration):
        """Test opening a local file with selection."""
        file_path = "/Users/test/file.txt"
        darwin_integration.open_local_file(file_path, select=True)

        mock_popen.assert_called_once_with(["open", "-R", file_path])


class TestStartupEnabled:
    """Test cases for startup_enabled method."""

    def test_startup_enabled_true(self, frozen_app, darwin_integration, tmp_path):
        """Test startup_enabled when agent file exists."""
        agent_file = tmp_path / "test_agent.plist"
        agent_file.write_text("test", encoding="utf-8")

        with patch.object(
            darwin_integration, "_get_agent_file", return_value=agent_file
        ):
            result = darwin_integration.startup_enabled()

        assert result is True

    def test_startup_enabled_false(self, frozen_app, darwin_integration, tmp_path):
        """Test startup_enabled when agent file does not exist."""
        agent_file = tmp_path / "non_existent_agent.plist"

        with patch.object(
            darwin_integration, "_get_agent_file", return_value=agent_file
        ):
            result = darwin_integration.startup_enabled()

        assert result is False


class TestRegisterStartup:
    """Test cases for register_startup method."""

    @patch(
        "nxdrive.osi.darwin.darwin.sys.executable",
        "/Applications/Nuxeo Drive.app/Contents/MacOS/ndrive",
    )
    @patch("nxdrive.osi.darwin.darwin.os.path.realpath")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_register_startup_success(
        self, mock_log, mock_realpath, frozen_app, darwin_integration, tmp_path
    ):
        """Test successful registration of startup agent."""
        agent_file = tmp_path / "agent.plist"
        agent_parent = agent_file.parent
        agent_parent.mkdir(parents=True, exist_ok=True)

        mock_realpath.return_value = (
            "/Applications/Nuxeo Drive.app/Contents/MacOS/ndrive"
        )

        with patch.object(
            darwin_integration, "_get_agent_file", return_value=agent_file
        ), patch.object(darwin_integration, "startup_enabled", return_value=False):
            darwin_integration.register_startup()

        assert agent_file.exists()
        content = agent_file.read_text(encoding="utf-8")
        assert "/Applications/Nuxeo Drive.app/Contents/MacOS/ndrive" in content
        assert "org.nuxeo.drive.agentlauncher" in content
        mock_log.info.assert_called()

    def test_register_startup_already_enabled(
        self, frozen_app, darwin_integration, tmp_path
    ):
        """Test register_startup when already enabled."""
        agent_file = tmp_path / "agent.plist"

        with patch.object(
            darwin_integration, "_get_agent_file", return_value=agent_file
        ), patch.object(darwin_integration, "startup_enabled", return_value=True):
            darwin_integration.register_startup()

        # Should not create the file if already enabled
        assert not agent_file.exists()

    @patch(
        "nxdrive.osi.darwin.darwin.sys.executable",
        "/Applications/Nuxeo Drive.app/Contents/MacOS/ndrive",
    )
    @patch("nxdrive.osi.darwin.darwin.os.path.realpath")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_register_startup_creates_parent_dir(
        self, mock_log, mock_realpath, frozen_app, darwin_integration, tmp_path
    ):
        """Test that register_startup creates parent directory if needed."""
        agent_file = tmp_path / "new_dir" / "agent.plist"

        mock_realpath.return_value = (
            "/Applications/Nuxeo Drive.app/Contents/MacOS/ndrive"
        )

        with patch.object(
            darwin_integration, "_get_agent_file", return_value=agent_file
        ), patch.object(darwin_integration, "startup_enabled", return_value=False):
            darwin_integration.register_startup()

        assert agent_file.parent.exists()
        assert agent_file.exists()


class TestUnregisterStartup:
    """Test cases for unregister_startup method."""

    @patch("nxdrive.osi.darwin.darwin.log")
    def test_unregister_startup_success(
        self, mock_log, frozen_app, darwin_integration, tmp_path
    ):
        """Test successful unregistration of startup agent."""
        agent_file = tmp_path / "agent.plist"
        agent_file.write_text("test content", encoding="utf-8")

        with patch.object(
            darwin_integration, "_get_agent_file", return_value=agent_file
        ), patch.object(darwin_integration, "startup_enabled", return_value=True):
            darwin_integration.unregister_startup()

        assert not agent_file.exists()
        mock_log.info.assert_called_once()

    def test_unregister_startup_not_enabled(
        self, frozen_app, darwin_integration, tmp_path
    ):
        """Test unregister_startup when not enabled."""
        agent_file = tmp_path / "non_existent_agent.plist"

        with patch.object(
            darwin_integration, "_get_agent_file", return_value=agent_file
        ), patch.object(darwin_integration, "startup_enabled", return_value=False):
            darwin_integration.unregister_startup()

        # Should not raise any error


class TestRegisterProtocolHandlers:
    """Test cases for register_protocol_handlers method."""

    @patch("nxdrive.osi.darwin.darwin.NSBundle")
    @patch("nxdrive.osi.darwin.darwin.LSSetDefaultHandlerForURLScheme")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_register_protocol_handlers_success(
        self, mock_log, mock_ls_set, mock_bundle, frozen_app, darwin_integration
    ):
        """Test successful registration of protocol handlers."""
        mock_bundle.mainBundle().bundleIdentifier.return_value = "org.nuxeo.drive"

        darwin_integration.register_protocol_handlers()

        mock_ls_set.assert_called_once_with("nxdrive", "org.nuxeo.drive")
        mock_log.info.assert_called_once()

    @patch("nxdrive.osi.darwin.darwin.NSBundle")
    @patch("nxdrive.osi.darwin.darwin.LSSetDefaultHandlerForURLScheme")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_register_protocol_handlers_python_app(
        self, mock_log, mock_ls_set, mock_bundle, frozen_app, darwin_integration
    ):
        """Test skipping protocol handler registration from Python app bundle."""
        mock_bundle.mainBundle().bundleIdentifier.return_value = "org.python.python"

        darwin_integration.register_protocol_handlers()

        mock_ls_set.assert_not_called()
        mock_log.info.assert_called_once_with(
            "Skipping URL scheme registration as this program "
            " was launched from the Python OSX app bundle"
        )


class TestUnwatchFolder:
    """Test cases for unwatch_folder method."""

    @patch("nxdrive.osi.darwin.darwin.log")
    def test_unwatch_folder(self, mock_log, frozen_app, darwin_integration, tmp_path):
        """Test unwatching a folder."""
        folder = tmp_path / "test_folder"
        folder.mkdir()

        with patch.object(darwin_integration, "_set_monitoring") as mock_set_monitoring:
            darwin_integration.unwatch_folder(folder)

        mock_set_monitoring.assert_called_once_with("unwatch", folder)
        mock_log.info.assert_called_once()


class TestSendSyncStatus:
    """Test cases for send_sync_status method."""

    @patch("nxdrive.osi.darwin.darwin.get_formatted_status")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_send_sync_status_success(
        self, mock_log, mock_get_status, frozen_app, darwin_integration, tmp_path
    ):
        """Test sending sync status successfully."""
        state = Mock(spec=DocPair)
        path = tmp_path / "test_file.txt"
        mock_get_status.return_value = {"path": str(path), "status": "synced"}

        with patch.object(darwin_integration, "_send_notification") as mock_send:
            darwin_integration.send_sync_status(state, path)

        mock_get_status.assert_called_once_with(state, path)
        mock_send.assert_called_once()
        mock_log.debug.assert_called()

    @patch("nxdrive.osi.darwin.darwin.get_formatted_status")
    def test_send_sync_status_no_status(
        self, mock_get_status, frozen_app, darwin_integration, tmp_path
    ):
        """Test send_sync_status when status is None."""
        state = Mock(spec=DocPair)
        path = tmp_path / "test_file.txt"
        mock_get_status.return_value = None

        with patch.object(darwin_integration, "_send_notification") as mock_send:
            darwin_integration.send_sync_status(state, path)

        mock_send.assert_not_called()

    @patch("nxdrive.osi.darwin.darwin.get_formatted_status")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_send_sync_status_error(
        self, mock_log, mock_get_status, frozen_app, darwin_integration, tmp_path
    ):
        """Test send_sync_status when an exception occurs."""
        state = Mock(spec=DocPair)
        path = tmp_path / "test_file.txt"
        mock_get_status.side_effect = Exception("Test error")

        darwin_integration.send_sync_status(state, path)

        mock_log.exception.assert_called_once_with(
            "Error while trying to send status to FinderSync"
        )


class TestSendContentSyncStatus:
    """Test cases for send_content_sync_status method."""

    @patch("nxdrive.osi.darwin.darwin.get_formatted_status")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_send_content_sync_status_success(
        self, mock_log, mock_get_status, frozen_app, darwin_integration, tmp_path
    ):
        """Test sending content sync status successfully."""
        states = []
        for i in range(3):
            state = Mock(spec=DocPair)
            state.local_name = f"file{i}.txt"
            states.append(state)

        path = tmp_path / "test_folder"
        path.mkdir()
        mock_get_status.return_value = {"status": "synced"}

        with patch.object(darwin_integration, "_send_notification") as mock_send:
            darwin_integration.send_content_sync_status(states, path)

        assert mock_get_status.call_count == 3
        mock_send.assert_called_once()
        mock_log.debug.assert_called()

    @patch("nxdrive.osi.darwin.darwin.get_formatted_status")
    def test_send_content_sync_status_batching(
        self, mock_get_status, frozen_app, darwin_integration, tmp_path
    ):
        """Test send_content_sync_status with batching."""
        # Set batch size to 2 for testing
        Options.set("findersync_batch_size", 2, setter="manual")

        states = []
        for i in range(5):
            state = Mock(spec=DocPair)
            state.local_name = f"file{i}.txt"
            states.append(state)

        path = tmp_path / "test_folder"
        path.mkdir()
        mock_get_status.return_value = {"status": "synced"}

        with patch.object(darwin_integration, "_send_notification") as mock_send:
            darwin_integration.send_content_sync_status(states, path)

        # Should send 3 notifications (2+2+1)
        assert mock_send.call_count == 3

    @patch("nxdrive.osi.darwin.darwin.get_formatted_status")
    def test_send_content_sync_status_file_not_found(
        self, mock_get_status, frozen_app, darwin_integration, tmp_path
    ):
        """Test send_content_sync_status when FileNotFoundError occurs."""
        state = Mock(spec=DocPair)
        state.local_name = "file.txt"
        states = [state]

        path = tmp_path / "non_existent_folder"
        mock_get_status.side_effect = FileNotFoundError()

        # Should not raise an exception
        darwin_integration.send_content_sync_status(states, path)

    @patch("nxdrive.osi.darwin.darwin.get_formatted_status")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_send_content_sync_status_error(
        self, mock_log, mock_get_status, frozen_app, darwin_integration, tmp_path
    ):
        """Test send_content_sync_status when an exception occurs."""
        state = Mock(spec=DocPair)
        state.local_name = "file.txt"
        states = [state]

        path = tmp_path / "test_folder"
        path.mkdir()
        mock_get_status.side_effect = Exception("Test error")

        darwin_integration.send_content_sync_status(states, path)

        mock_log.exception.assert_called_once_with(
            "Error while trying to send status to FinderSync"
        )


class TestRegisterContextualMenu:
    """Test cases for register_contextual_menu method."""

    @patch("nxdrive.osi.darwin.darwin.Translator")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_register_contextual_menu(
        self, mock_log, mock_translator, frozen_app, darwin_integration
    ):
        """Test registering contextual menu."""
        mock_translator.get.side_effect = lambda key: f"Menu_{key}"

        with patch.object(darwin_integration, "_send_notification") as mock_send:
            darwin_integration.register_contextual_menu()

        # Verify Translator.get was called for each menu item
        assert mock_translator.get.call_count == 4

        # Verify _send_notification was called
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "entries" in call_args[0][1]
        mock_log.debug.assert_called()


class TestRegisterFolderLink:
    """Test cases for register_folder_link method."""

    @patch("nxdrive.osi.darwin.darwin.LSSharedFileListInsertItemURL")
    @patch("nxdrive.osi.darwin.darwin.CFURLCreateWithString")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_register_folder_link_success(
        self,
        mock_log,
        mock_create_url,
        mock_insert,
        frozen_app,
        darwin_integration,
        tmp_path,
    ):
        """Test successful registration of folder link."""
        folder = tmp_path / "test_folder"
        folder.mkdir()

        mock_favorites = ["fav1", "fav2"]
        mock_create_url.return_value = "file://test_url"
        mock_insert.return_value = "new_item"

        with patch.object(
            darwin_integration, "_get_favorite_list", return_value=mock_favorites
        ), patch.object(darwin_integration, "_find_item_in_list", return_value=None):
            darwin_integration.register_folder_link(folder)

        mock_insert.assert_called_once()
        mock_log.info.assert_called_once()

    @patch("nxdrive.osi.darwin.darwin.log")
    def test_register_folder_link_already_exists(
        self, mock_log, frozen_app, darwin_integration, tmp_path
    ):
        """Test register_folder_link when folder already exists in favorites."""
        folder = tmp_path / "test_folder"
        folder.mkdir()

        mock_favorites = ["fav1", "fav2"]
        existing_item = "existing_item"

        with patch.object(
            darwin_integration, "_get_favorite_list", return_value=mock_favorites
        ), patch.object(
            darwin_integration, "_find_item_in_list", return_value=existing_item
        ):
            darwin_integration.register_folder_link(folder)

        # Should return early, no log.info about registration
        assert not any(
            "Registered new favorite" in str(call_arg)
            for call_arg in mock_log.info.call_args_list
        )

    @patch("nxdrive.osi.darwin.darwin.log")
    def test_register_folder_link_no_favorites(
        self, mock_log, frozen_app, darwin_integration, tmp_path
    ):
        """Test register_folder_link when favorites list is empty or None."""
        folder = tmp_path / "test_folder"
        folder.mkdir()

        with patch.object(darwin_integration, "_get_favorite_list", return_value=[]):
            darwin_integration.register_folder_link(folder)

        mock_log.warning.assert_called_once_with(
            "Could not fetch the Finder favorite list."
        )

    @patch("nxdrive.osi.darwin.darwin.CFURLCreateWithString")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_register_folder_link_invalid_url(
        self, mock_log, mock_create_url, frozen_app, darwin_integration, tmp_path
    ):
        """Test register_folder_link when URL creation fails."""
        folder = tmp_path / "test_folder"
        folder.mkdir()

        mock_favorites = ["fav1"]
        mock_create_url.return_value = None

        with patch.object(
            darwin_integration, "_get_favorite_list", return_value=mock_favorites
        ), patch.object(darwin_integration, "_find_item_in_list", return_value=None):
            darwin_integration.register_folder_link(folder)

        mock_log.warning.assert_called_once()
        assert "Could not generate valid favorite URL" in str(
            mock_log.warning.call_args
        )

    @patch("nxdrive.osi.darwin.darwin.LSSharedFileListInsertItemURL")
    @patch("nxdrive.osi.darwin.darwin.CFURLCreateWithString")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_register_folder_link_insert_fails(
        self,
        mock_log,
        mock_create_url,
        mock_insert,
        frozen_app,
        darwin_integration,
        tmp_path,
    ):
        """Test register_folder_link when insertion fails."""
        folder = tmp_path / "test_folder"
        folder.mkdir()

        mock_favorites = ["fav1"]
        mock_create_url.return_value = "file://test_url"
        mock_insert.return_value = None

        with patch.object(
            darwin_integration, "_get_favorite_list", return_value=mock_favorites
        ), patch.object(darwin_integration, "_find_item_in_list", return_value=None):
            darwin_integration.register_folder_link(folder)

        # Should not log success if insertion returns None
        assert not any(
            "Registered new favorite" in str(call_arg)
            for call_arg in mock_log.info.call_args_list
        )


class TestUnregisterFolderLink:
    """Test cases for unregister_folder_link method."""

    @patch("nxdrive.osi.darwin.darwin.LSSharedFileListItemRemove")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_unregister_folder_link_success(
        self, mock_log, mock_remove, frozen_app, darwin_integration, tmp_path
    ):
        """Test successful unregistration of folder link."""
        folder = tmp_path / "test_folder"
        folder.mkdir()

        mock_favorites = ["fav1", "fav2"]
        mock_item = "existing_item"

        with patch.object(
            darwin_integration, "_get_favorite_list", return_value=mock_favorites
        ), patch.object(
            darwin_integration, "_find_item_in_list", return_value=mock_item
        ):
            darwin_integration.unregister_folder_link(folder)

        mock_remove.assert_called_once_with(mock_favorites, mock_item)
        assert any(
            "removed from Finder favorites" in str(call_arg)
            for call_arg in mock_log.info.call_args_list
        )

    @patch("nxdrive.osi.darwin.darwin.log")
    def test_unregister_folder_link_not_found(
        self, mock_log, frozen_app, darwin_integration, tmp_path
    ):
        """Test unregister_folder_link when folder is not in favorites."""
        folder = tmp_path / "test_folder"
        folder.mkdir()

        mock_favorites = ["fav1", "fav2"]

        with patch.object(
            darwin_integration, "_get_favorite_list", return_value=mock_favorites
        ), patch.object(darwin_integration, "_find_item_in_list", return_value=None):
            darwin_integration.unregister_folder_link(folder)

        assert any(
            "not found in Finder favorites" in str(call_arg)
            for call_arg in mock_log.info.call_args_list
        )

    @patch("nxdrive.osi.darwin.darwin.log")
    def test_unregister_folder_link_no_favorites(
        self, mock_log, frozen_app, darwin_integration, tmp_path
    ):
        """Test unregister_folder_link when favorites list cannot be fetched."""
        folder = tmp_path / "test_folder"
        folder.mkdir()

        with patch.object(darwin_integration, "_get_favorite_list", return_value=None):
            darwin_integration.unregister_folder_link(folder)

        mock_log.warning.assert_called_once_with("Could not fetch Finder favorites")

    @patch("nxdrive.osi.darwin.darwin.LSSharedFileListItemRemove")
    @patch("nxdrive.osi.darwin.darwin.log")
    def test_unregister_folder_link_error(
        self, mock_log, mock_remove, frozen_app, darwin_integration, tmp_path
    ):
        """Test unregister_folder_link when removal fails."""
        folder = tmp_path / "test_folder"
        folder.mkdir()

        mock_favorites = ["fav1", "fav2"]
        mock_item = "existing_item"
        mock_remove.side_effect = Exception("Test error")

        with patch.object(
            darwin_integration, "_get_favorite_list", return_value=mock_favorites
        ), patch.object(
            darwin_integration, "_find_item_in_list", return_value=mock_item
        ):
            darwin_integration.unregister_folder_link(folder)

        mock_log.exception.assert_called_once()
        assert "Cannot remove" in str(mock_log.exception.call_args)


class TestGetFavoriteList:
    """Test cases for _get_favorite_list method."""

    @patch("nxdrive.osi.darwin.darwin.LSSharedFileListCreate")
    def test_get_favorite_list(self, mock_create, darwin_integration):
        """Test getting the favorite list."""
        mock_favorites = ["fav1", "fav2", "fav3"]
        mock_create.return_value = mock_favorites

        result = darwin_integration._get_favorite_list()

        assert result == mock_favorites
        mock_create.assert_called_once()


class TestFindItemInList:
    """Test cases for _find_item_in_list method."""

    @patch("nxdrive.osi.darwin.darwin.LSSharedFileListCopySnapshot")
    @patch("nxdrive.osi.darwin.darwin.LSSharedFileListItemCopyDisplayName")
    def test_find_item_in_list_found(
        self, mock_get_name, mock_snapshot, darwin_integration
    ):
        """Test finding an item in the list."""
        mock_item1 = Mock()
        mock_item2 = Mock()
        mock_item3 = Mock()
        mock_snapshot.return_value = ([mock_item1, mock_item2, mock_item3], None)
        mock_get_name.side_effect = ["item1", "item2", "item3"]

        result = darwin_integration._find_item_in_list(["list"], "item2")

        assert result == mock_item2
        assert mock_get_name.call_count == 2

    @patch("nxdrive.osi.darwin.darwin.LSSharedFileListCopySnapshot")
    @patch("nxdrive.osi.darwin.darwin.LSSharedFileListItemCopyDisplayName")
    def test_find_item_in_list_not_found(
        self, mock_get_name, mock_snapshot, darwin_integration
    ):
        """Test not finding an item in the list."""
        mock_item1 = Mock()
        mock_item2 = Mock()
        mock_snapshot.return_value = ([mock_item1, mock_item2], None)
        mock_get_name.side_effect = ["item1", "item2"]

        result = darwin_integration._find_item_in_list(["list"], "item3")

        assert result is None
        assert mock_get_name.call_count == 2

    @patch("nxdrive.osi.darwin.darwin.LSSharedFileListCopySnapshot")
    def test_find_item_in_list_empty(self, mock_snapshot, darwin_integration):
        """Test finding an item in an empty list."""
        mock_snapshot.return_value = ([], None)

        result = darwin_integration._find_item_in_list(["list"], "item")

        assert result is None
