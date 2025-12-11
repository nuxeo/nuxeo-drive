"""Unit tests for Engine class methods."""

from pathlib import Path
from threading import Thread
from time import sleep
from unittest.mock import Mock, call, patch

import pytest

from nxdrive.constants import DelAction, TransferStatus
from nxdrive.dao.engine import EngineDAO
from nxdrive.engine.engine import Engine
from nxdrive.engine.queue_manager import QueueManager
from nxdrive.engine.watcher.local_watcher import LocalWatcher
from nxdrive.engine.watcher.remote_watcher import RemoteWatcher
from nxdrive.feature import Feature
from nxdrive.objects import Session


@pytest.fixture
def mock_manager():
    """Create a mock manager."""
    manager = Mock()
    manager.version = "1.0.0"
    manager.home = Path("/tmp/nuxeo-drive")
    manager.tracker = Mock()
    manager.tracker.send_metric = Mock()
    manager.update_engine_path = Mock()
    manager.get_deletion_behavior = Mock(return_value=DelAction.DEL_SERVER)
    manager.directEdit = Mock()
    manager.directEdit.emit = Mock()
    manager.open_local_file = Mock()
    return manager


@pytest.fixture
def mock_dao():
    """Create a mock DAO."""
    dao = Mock(spec=EngineDAO)
    dao.update_config = Mock()
    dao.get_config = Mock(return_value=None)
    dao.add_filter = Mock()
    dao.remove_filter = Mock()
    dao.get_state_from_remote_with_path = Mock()
    dao.delete_remote_state = Mock()
    dao.get_state_from_local = Mock()
    dao.remove_state = Mock()
    dao.delete_local_state = Mock()
    dao.force_remote_creation = Mock()
    dao.remove_state_children = Mock()
    dao.create_session = Mock(return_value=1)
    dao.plan_many_direct_transfer_items = Mock(return_value=1)
    dao.queue_many_direct_transfer_items = Mock()
    dao.get_session_items = Mock(return_value=[])
    dao.get_count = Mock(return_value=0)
    dao.decrease_session_counts = Mock(return_value=None)
    dao.get_dt_upload = Mock()
    dao.remove_transfer = Mock()
    dao.reinit_states = Mock()
    dao.pause_session = Mock()
    dao.resume_session = Mock()
    dao.change_session_status = Mock()
    dao.cancel_session = Mock()
    dao.resume_transfer = Mock()
    dao.get_downloads_with_status = Mock(return_value=[])
    dao.get_uploads_with_status = Mock(return_value=[])
    dao.get_dt_uploads_with_status = Mock(return_value=[])
    dao.get_download = Mock()
    dao.get_upload = Mock()
    return dao


@pytest.fixture
def mock_remote():
    """Create a mock remote client."""
    remote = Mock()
    remote.upload_folder = Mock(
        return_value={"path": "/test/folder", "uid": "test-uid-123"}
    )
    remote.upload_folder_type = Mock(
        return_value={"path": "/test/folder", "uid": "test-uid-123"}
    )
    remote.metrics = Mock()
    remote.metrics.send = Mock()
    remote.cancel_batch = Mock()
    remote.client = Mock()
    remote.client.repository = "default"
    return remote


@pytest.fixture
def mock_queue_manager():
    """Create a mock queue manager."""
    qm = Mock(spec=QueueManager)
    qm.get_processors_on = Mock(return_value=[])
    qm.has_file_processors_on = Mock(return_value=False)
    qm.suspend = Mock()
    qm.resume = Mock()
    qm.init_processors = Mock()
    qm.shutdown_processors = Mock()
    qm.get_metrics = Mock(return_value={})
    return qm


@pytest.fixture
def mock_engine(mock_manager, mock_dao, mock_remote, mock_queue_manager, tmp_path):
    """Create a mock engine instance."""
    # Create a mock engine with all necessary attributes
    engine = Mock(spec=Engine)

    # Setup basic attributes
    engine.uid = "test-engine-uid"
    engine.name = "Test Engine"
    engine.local_folder = tmp_path / "sync"
    engine.local_folder.mkdir(exist_ok=True)
    engine.manager = mock_manager
    engine.dao = mock_dao
    engine.remote = mock_remote
    engine._remote_token = Mock()
    engine.queue_manager = mock_queue_manager
    engine._stopped = True
    engine._pause = False
    engine._sync_started = False
    engine._offline_state = False
    engine.wui = "web"
    engine.force_ui = ""
    engine.server_url = "https://test.nuxeo.com"
    engine.remote_user = "testuser"
    engine._threads = []
    engine._threadpool = Mock()
    engine._threadpool.start = Mock()
    engine.doc_container_type = "Automatic"
    engine._folder_lock = None

    # Mock local client
    engine.local = Mock()
    engine.local.get_path = Mock()
    engine.local.unset_readonly = Mock()

    # Mock watchers
    engine._local_watcher = Mock(spec=LocalWatcher)
    engine._local_watcher.stop = Mock()
    engine._remote_watcher = Mock(spec=RemoteWatcher)
    engine._remote_watcher.scan_remote = Mock()

    # Mock signals
    engine.uiChanged = Mock()
    engine.uiChanged.emit = Mock()
    engine.offline = Mock()
    engine.offline.emit = Mock()
    engine.online = Mock()
    engine.online.emit = Mock()
    engine._scanPair = Mock()
    engine._scanPair.emit = Mock()
    engine.directTransferNewFolderSuccess = Mock()
    engine.directTransferNewFolderSuccess.emit = Mock()
    engine.directTransferNewFolderError = Mock()
    engine.directTransferNewFolderError.emit = Mock()
    engine.directTransferSessionFinished = Mock()
    engine.directTransferSessionFinished.emit = Mock()
    engine.syncResumed = Mock()
    engine.syncResumed.emit = Mock()

    # Create actual Engine methods as they are not mocked by default
    engine.reinit = Engine.reinit.__get__(engine, Engine)
    engine.stop_processor_on = Engine.stop_processor_on.__get__(engine, Engine)
    engine.set_local_folder = Engine.set_local_folder.__get__(engine, Engine)
    engine.set_local_folder_lock = Engine.set_local_folder_lock.__get__(engine, Engine)
    engine.set_ui = Engine.set_ui.__get__(engine, Engine)
    engine.release_folder_lock = Engine.release_folder_lock.__get__(engine, Engine)
    engine.set_offline = Engine.set_offline.__get__(engine, Engine)
    engine.add_filter = Engine.add_filter.__get__(engine, Engine)
    engine.remove_filter = Engine.remove_filter.__get__(engine, Engine)
    engine._save_last_dt_session_infos = Engine._save_last_dt_session_infos.__get__(
        engine, Engine
    )
    engine._create_remote_folder = Engine._create_remote_folder.__get__(engine, Engine)
    engine._create_remote_folder_with_enricher = (
        Engine._create_remote_folder_with_enricher.__get__(engine, Engine)
    )
    engine._direct_transfer = Engine._direct_transfer.__get__(engine, Engine)
    engine.handle_session_status = Engine.handle_session_status.__get__(engine, Engine)
    engine.direct_transfer_async = Engine.direct_transfer_async.__get__(engine, Engine)
    engine.rollback_delete = Engine.rollback_delete.__get__(engine, Engine)
    engine.open_edit = Engine.open_edit.__get__(engine, Engine)
    engine.open_remote = Engine.open_remote.__get__(engine, Engine)
    engine.resume = Engine.resume.__get__(engine, Engine)
    engine.send_metric = Engine.send_metric.__get__(engine, Engine)
    engine._resume_transfers = Engine._resume_transfers.__get__(engine, Engine)
    engine.resume_transfer = Engine.resume_transfer.__get__(engine, Engine)
    engine.resume_session = Engine.resume_session.__get__(engine, Engine)
    engine._manage_staled_transfers = Engine._manage_staled_transfers.__get__(
        engine, Engine
    )
    engine.cancel_upload = Engine.cancel_upload.__get__(engine, Engine)
    engine.suspend = Engine.suspend.__get__(engine, Engine)
    engine.unbind = Engine.unbind.__get__(engine, Engine)
    engine.local_rollback = Engine.local_rollback.__get__(engine, Engine)
    engine.create_thread = Engine.create_thread.__get__(engine, Engine)
    engine.retry_pair = Engine.retry_pair.__get__(engine, Engine)
    engine.ignore_pair = Engine.ignore_pair.__get__(engine, Engine)
    engine.resolve_with_local = Engine.resolve_with_local.__get__(engine, Engine)
    engine.resolve_with_remote = Engine.resolve_with_remote.__get__(engine, Engine)
    engine._check_last_sync = Engine._check_last_sync.__get__(engine, Engine)
    engine._thread_finished = Engine._thread_finished.__get__(engine, Engine)
    engine.stop = Engine.stop.__get__(engine, Engine)
    engine.update_token = Engine.update_token.__get__(engine, Engine)
    engine._setup_local_folder = Engine._setup_local_folder.__get__(engine, Engine)
    engine._check_https = Engine._check_https.__get__(engine, Engine)
    engine.cancel_action_on = Engine.cancel_action_on.__get__(engine, Engine)
    engine._add_top_level_state = Engine._add_top_level_state.__get__(engine, Engine)
    engine.suspend_client = Engine.suspend_client.__get__(engine, Engine)
    engine._create_local_watcher = Mock()

    return engine


class TestReinit:
    """Test cases for Engine.reinit method."""

    def test_reinit_when_stopped(self, mock_engine):
        """Test reinit when engine is stopped."""
        mock_engine._stopped = True

        with patch.object(mock_engine, "stop") as mock_stop:
            with patch.object(mock_engine, "start") as mock_start:
                with patch.object(mock_engine, "_check_root") as mock_check_root:
                    with patch.object(Feature, "synchronization", True):
                        mock_engine.reinit()

        # Should not call stop since already stopped
        mock_stop.assert_not_called()
        mock_start.assert_not_called()
        mock_engine.dao.reinit_states.assert_called_once()
        mock_check_root.assert_called_once()

    def test_reinit_when_started(self, mock_engine):
        """Test reinit when engine is started."""
        mock_engine._stopped = False

        with patch.object(mock_engine, "stop") as mock_stop:
            with patch.object(mock_engine, "start") as mock_start:
                with patch.object(mock_engine, "_check_root") as mock_check_root:
                    with patch.object(Feature, "synchronization", True):
                        mock_engine.reinit()

        # Should call stop and start
        mock_stop.assert_called_once()
        mock_start.assert_called_once()
        mock_engine.dao.reinit_states.assert_called_once()
        mock_check_root.assert_called_once()

    def test_reinit_without_synchronization(self, mock_engine):
        """Test reinit when synchronization feature is disabled."""
        mock_engine._stopped = True

        with patch.object(mock_engine, "_check_root") as mock_check_root:
            with patch.object(Feature, "synchronization", False):
                mock_engine.reinit()

        # Should not call reinit_states or check_root
        mock_engine.dao.reinit_states.assert_not_called()
        mock_check_root.assert_not_called()


class TestStopProcessorOn:
    """Test cases for Engine.stop_processor_on method."""

    def test_stop_processor_on_with_workers(self, mock_engine):
        """Test stopping processors on a path with active workers."""
        test_path = Path("/test/path")
        mock_worker = Mock()
        mock_engine.queue_manager.get_processors_on.return_value = [mock_worker]

        mock_engine.stop_processor_on(test_path)

        mock_engine.queue_manager.get_processors_on.assert_called_once_with(test_path)

    def test_stop_processor_on_without_workers(self, mock_engine):
        """Test stopping processors on a path without active workers."""
        test_path = Path("/test/path")
        mock_engine.queue_manager.get_processors_on.return_value = []

        mock_engine.stop_processor_on(test_path)

        mock_engine.queue_manager.get_processors_on.assert_called_once_with(test_path)


class TestSetLocalFolder:
    """Test cases for Engine.set_local_folder method."""

    def test_set_local_folder(self, mock_engine, tmp_path):
        """Test setting a new local folder."""
        new_path = tmp_path / "new_sync"
        new_path.mkdir()

        with patch.object(mock_engine, "_create_local_watcher") as mock_create:
            mock_engine.set_local_folder(new_path)

        assert mock_engine.local_folder == new_path
        mock_engine._local_watcher.stop.assert_called_once()
        mock_create.assert_called_once()
        mock_engine.manager.update_engine_path.assert_called_once_with(
            mock_engine.uid, new_path
        )


class TestSetLocalFolderLock:
    """Test cases for Engine.set_local_folder_lock method."""

    def test_set_local_folder_lock_no_processors(self, mock_engine):
        """Test setting folder lock when no processors are active."""
        test_path = Path("/test/path")
        mock_engine.queue_manager.has_file_processors_on.return_value = False

        mock_engine.set_local_folder_lock(test_path)

        assert mock_engine._folder_lock == test_path
        mock_engine.queue_manager.has_file_processors_on.assert_called_once_with(
            test_path
        )

    def test_set_local_folder_lock_with_processors(self, mock_engine):
        """Test setting folder lock when processors are active."""
        test_path = Path("/test/path")
        call_count = [0]

        def side_effect(path):
            call_count[0] += 1
            # Return True for first two calls, then False
            return call_count[0] <= 2

        mock_engine.queue_manager.has_file_processors_on.side_effect = side_effect

        with patch("nxdrive.engine.engine.sleep") as mock_sleep:
            mock_engine.set_local_folder_lock(test_path)

        assert mock_engine._folder_lock == test_path
        # Should have called has_file_processors_on 3 times
        assert mock_engine.queue_manager.has_file_processors_on.call_count == 3
        # Should have slept 2 times (once per True return)
        assert mock_sleep.call_count == 2


class TestSetUI:
    """Test cases for Engine.set_ui method."""

    def test_set_ui_force_ui(self, mock_engine):
        """Test setting force_ui."""
        mock_engine.force_ui = ""

        mock_engine.set_ui("jsf", overwrite=True)

        assert mock_engine.force_ui == "jsf"
        mock_engine.dao.update_config.assert_called_once_with("force_ui", "jsf")
        mock_engine.uiChanged.emit.assert_called_once_with(mock_engine.uid)

    def test_set_ui_wui(self, mock_engine):
        """Test setting wui."""
        mock_engine.wui = "web"

        mock_engine.set_ui("jsf", overwrite=False)

        assert mock_engine.wui == "jsf"
        mock_engine.dao.update_config.assert_called_once_with("ui", "jsf")
        mock_engine.uiChanged.emit.assert_called_once_with(mock_engine.uid)

    def test_set_ui_same_value(self, mock_engine):
        """Test setting UI to the same value - should return early."""
        mock_engine.force_ui = "jsf"

        mock_engine.set_ui("jsf", overwrite=True)

        # Should not update or emit
        mock_engine.dao.update_config.assert_not_called()
        mock_engine.uiChanged.emit.assert_not_called()


class TestReleaseFolderLock:
    """Test cases for Engine.release_folder_lock method."""

    def test_release_folder_lock(self, mock_engine):
        """Test releasing folder lock."""
        mock_engine._folder_lock = Path("/test/path")

        mock_engine.release_folder_lock()

        assert mock_engine._folder_lock is None


class TestSetOffline:
    """Test cases for Engine.set_offline method."""

    def test_set_offline_to_true(self, mock_engine):
        """Test setting engine offline."""
        mock_engine._offline_state = False

        mock_engine.set_offline(value=True)

        assert mock_engine._offline_state is True
        mock_engine.queue_manager.suspend.assert_called_once()
        mock_engine.offline.emit.assert_called_once()

    def test_set_offline_to_false(self, mock_engine):
        """Test setting engine online."""
        mock_engine._offline_state = True

        mock_engine.set_offline(value=False)

        assert mock_engine._offline_state is False
        mock_engine.queue_manager.resume.assert_called_once()
        mock_engine.online.emit.assert_called_once()

    def test_set_offline_same_value(self, mock_engine):
        """Test setting offline to same value - should return early."""
        mock_engine._offline_state = True

        mock_engine.set_offline(value=True)

        # Should not suspend or emit
        mock_engine.queue_manager.suspend.assert_not_called()
        mock_engine.offline.emit.assert_not_called()


class TestAddFilter:
    """Test cases for Engine.add_filter method."""

    def test_add_filter_with_valid_pair(self, mock_engine):
        """Test adding filter with valid pair."""
        path = "/remote/path/file.txt"
        mock_pair = Mock()
        mock_engine.dao.get_state_from_remote_with_path.return_value = mock_pair

        mock_engine.add_filter(path)

        mock_engine.dao.add_filter.assert_called_once_with(path)
        mock_engine.dao.get_state_from_remote_with_path.assert_called_once_with(
            "file.txt", "/remote/path"
        )
        mock_engine.dao.delete_remote_state.assert_called_once_with(mock_pair)

    def test_add_filter_without_pair(self, mock_engine):
        """Test adding filter without valid pair."""
        path = "/remote/path/file.txt"
        mock_engine.dao.get_state_from_remote_with_path.return_value = None

        mock_engine.add_filter(path)

        mock_engine.dao.add_filter.assert_called_once_with(path)
        mock_engine.dao.delete_remote_state.assert_not_called()

    def test_add_filter_empty_remote_ref(self, mock_engine):
        """Test adding filter with empty remote ref."""
        path = "/remote/path/"

        mock_engine.add_filter(path)

        # Should return early without adding filter
        mock_engine.dao.add_filter.assert_not_called()


class TestRemoveFilter:
    """Test cases for Engine.remove_filter method."""

    def test_remove_filter(self, mock_engine):
        """Test removing filter."""
        path = "/remote/path/file.txt"

        mock_engine.remove_filter(path)

        mock_engine.dao.remove_filter.assert_called_once_with(path)
        mock_engine._scanPair.emit.assert_called_once_with(path)


class TestSaveLastDTSessionInfos:
    """Test cases for Engine._save_last_dt_session_infos method."""

    def test_save_last_dt_session_infos_all_params(self, mock_engine, tmp_path):
        """Test saving all DT session infos."""
        remote_path = "/remote/path"
        remote_ref = "ref-123"
        remote_title = "Test Title"
        duplicate_behavior = "create"
        last_local_location = tmp_path / "local"
        last_doc_type = "File"

        mock_engine._save_last_dt_session_infos(
            remote_path,
            remote_ref,
            remote_title,
            duplicate_behavior,
            last_local_location,
            last_doc_type,
        )

        # Verify all update_config calls
        expected_calls = [
            call("dt_last_remote_location", remote_path),
            call("dt_last_remote_location_ref", remote_ref),
            call("dt_last_remote_location_title", remote_title),
            call("dt_last_duplicates_behavior", duplicate_behavior),
            call("dt_last_local_selected_location", last_local_location),
            call("dt_last_local_selected_doc_type", last_doc_type),
        ]
        mock_engine.dao.update_config.assert_has_calls(expected_calls, any_order=False)

    def test_save_last_dt_session_infos_minimal_params(self, mock_engine):
        """Test saving minimal DT session infos."""
        remote_path = "/remote/path"
        remote_ref = "ref-123"
        remote_title = "Test Title"
        duplicate_behavior = "create"

        mock_engine._save_last_dt_session_infos(
            remote_path,
            remote_ref,
            remote_title,
            duplicate_behavior,
            None,
            None,
        )

        # Should only have 4 calls (not including optional params)
        assert mock_engine.dao.update_config.call_count == 4


class TestCreateRemoteFolder:
    """Test cases for Engine._create_remote_folder method."""

    def test_create_remote_folder_success(self, mock_engine):
        """Test creating remote folder successfully."""
        remote_parent_path = "/parent/path"
        new_folder = "New Folder"
        session_id = 123

        result = mock_engine._create_remote_folder(
            remote_parent_path, new_folder, session_id
        )

        assert result == {"path": "/test/folder", "uid": "test-uid-123"}
        mock_engine.remote.upload_folder.assert_called_once()
        mock_engine.directTransferNewFolderSuccess.emit.assert_called_once_with(
            "/test/folder"
        )

    def test_create_remote_folder_failure(self, mock_engine):
        """Test creating remote folder with exception."""
        remote_parent_path = "/parent/path"
        new_folder = "New Folder"
        session_id = 123

        mock_engine.remote.upload_folder.side_effect = Exception("Upload failed")

        result = mock_engine._create_remote_folder(
            remote_parent_path, new_folder, session_id
        )

        assert result == {}
        mock_engine.directTransferNewFolderError.emit.assert_called_once()


class TestCreateRemoteFolderWithEnricher:
    """Test cases for Engine._create_remote_folder_with_enricher method."""

    def test_create_remote_folder_with_enricher_success(self, mock_engine):
        """Test creating remote folder with enricher successfully."""
        remote_parent_path = "/parent/path"
        new_folder = "New Folder"
        new_folder_type = "CustomFolder"
        session_id = 123

        result = mock_engine._create_remote_folder_with_enricher(
            remote_parent_path, new_folder, new_folder_type, session_id
        )

        assert result == {"path": "/test/folder", "uid": "test-uid-123"}
        mock_engine.remote.upload_folder_type.assert_called_once()
        mock_engine.directTransferNewFolderSuccess.emit.assert_called_once()

    def test_create_remote_folder_with_enricher_failure(self, mock_engine):
        """Test creating remote folder with enricher with exception."""
        remote_parent_path = "/parent/path"
        new_folder = "New Folder"
        new_folder_type = "CustomFolder"
        session_id = 123

        mock_engine.remote.upload_folder_type.side_effect = Exception("Upload failed")

        result = mock_engine._create_remote_folder_with_enricher(
            remote_parent_path, new_folder, new_folder_type, session_id
        )

        assert result == {}
        mock_engine.directTransferNewFolderError.emit.assert_called_once()


class TestDirectTransfer:
    """Test cases for Engine._direct_transfer method."""

    def test_direct_transfer_with_files(self, mock_engine, tmp_path):
        """Test direct transfer with files."""
        # Create test files
        file1 = tmp_path / "file1.txt"
        file1.write_text("content1")
        file2 = tmp_path / "file2.txt"
        file2.write_text("content2")

        local_paths = {file1: 100, file2: 200}
        remote_parent_path = "/remote/path"
        remote_parent_ref = "ref-123"
        remote_parent_title = "Remote Title"

        with patch("nxdrive.engine.engine.Options") as mock_options:
            mock_options.database_batch_size = 50

            mock_engine._direct_transfer(
                local_paths,
                remote_parent_path,
                remote_parent_ref,
                remote_parent_title,
            )

        # Verify session infos were saved
        assert mock_engine.dao.update_config.call_count >= 4

        # Verify session was created
        mock_engine.dao.create_session.assert_called_once()

        # Verify items were planned
        mock_engine.dao.plan_many_direct_transfer_items.assert_called_once()
        mock_engine.dao.queue_many_direct_transfer_items.assert_called_once()

    def test_direct_transfer_with_new_folder(self, mock_engine, tmp_path):
        """Test direct transfer with new folder creation."""
        file1 = tmp_path / "file1.txt"
        file1.write_text("content1")

        local_paths = {file1: 100}
        remote_parent_path = "/remote/path"
        remote_parent_ref = "ref-123"
        remote_parent_title = "Remote Title"
        new_folder = "New Folder"

        with patch.object(mock_engine, "send_metric") as mock_metric:
            with patch("nxdrive.engine.engine.Options") as mock_options:
                mock_options.database_batch_size = 50

                mock_engine._direct_transfer(
                    local_paths,
                    remote_parent_path,
                    remote_parent_ref,
                    remote_parent_title,
                    new_folder=new_folder,
                )

        # Verify folder creation was attempted
        mock_metric.assert_called_once_with("direct_transfer", "new_folder", "1")
        mock_engine.remote.upload_folder.assert_called_once()

    def test_direct_transfer_only_create_folder(self, mock_engine):
        """Test direct transfer with only folder creation."""
        local_paths = {}
        remote_parent_path = "/remote/path"
        remote_parent_ref = "ref-123"
        remote_parent_title = "Remote Title"
        new_folder = "New Folder"

        with patch.object(mock_engine, "send_metric"):
            mock_engine._direct_transfer(
                local_paths,
                remote_parent_path,
                remote_parent_ref,
                remote_parent_title,
                new_folder=new_folder,
            )

        # Should create folder but not plan any items
        mock_engine.remote.upload_folder.assert_called_once()
        mock_engine.dao.create_session.assert_not_called()

    def test_direct_transfer_with_document_type(self, mock_engine, tmp_path):
        """Test direct transfer with custom document type."""
        file1 = tmp_path / "file1.txt"
        file1.write_text("content1")

        local_paths = {file1: 100}
        remote_parent_path = "/remote/path"
        remote_parent_ref = "ref-123"
        remote_parent_title = "Remote Title"

        with patch("nxdrive.engine.engine.Options") as mock_options:
            mock_options.database_batch_size = 50

            mock_engine._direct_transfer(
                local_paths,
                remote_parent_path,
                remote_parent_ref,
                remote_parent_title,
                document_type="CustomDoc",
                container_type="CustomFolder",
            )

        mock_engine.dao.plan_many_direct_transfer_items.assert_called_once()


class TestHandleSessionStatus:
    """Test cases for Engine.handle_session_status method."""

    def test_handle_session_status_done(self, mock_engine):
        """Test handling completed session."""
        session = Mock(spec=Session)
        session.status = TransferStatus.DONE
        session.uid = 123
        session.remote_ref = "ref-123"
        session.remote_path = "/remote/path"
        session.total_items = 10

        mock_engine.dao.get_session_items.return_value = [
            {"facets": ["Folderish"]},
            {"facets": ["File"]},
            {"facets": ["Folderish"]},
        ]

        with patch.object(mock_engine, "send_metric") as mock_metric:
            mock_engine.handle_session_status(session)

        mock_engine.directTransferSessionFinished.emit.assert_called_once_with(
            mock_engine.uid, "ref-123", "/remote/path"
        )
        mock_engine.remote.metrics.send.assert_called_once()
        mock_metric.assert_called_once_with("direct_transfer", "session_items", "10")

    def test_handle_session_status_not_done(self, mock_engine):
        """Test handling non-completed session."""
        session = Mock(spec=Session)
        session.status = TransferStatus.ONGOING

        mock_engine.handle_session_status(session)

        # Should return early without emitting
        mock_engine.directTransferSessionFinished.emit.assert_not_called()

    def test_handle_session_status_none(self, mock_engine):
        """Test handling None session."""
        mock_engine.handle_session_status(None)

        # Should return early without emitting
        mock_engine.directTransferSessionFinished.emit.assert_not_called()


class TestDirectTransferAsync:
    """Test cases for Engine.direct_transfer_async method."""

    def test_direct_transfer_async(self, mock_engine, tmp_path):
        """Test async direct transfer."""
        file1 = tmp_path / "file1.txt"
        file1.write_text("content1")

        local_paths = {file1: 100}
        remote_parent_path = "/remote/path"
        remote_parent_ref = "ref-123"
        remote_parent_title = "Remote Title"

        # Need to patch where Runner is imported within the function
        with patch("nxdrive.engine.workers.Runner") as mock_runner_class:
            mock_runner_instance = Mock()
            mock_runner_class.return_value = mock_runner_instance

            mock_engine.direct_transfer_async(
                local_paths,
                remote_parent_path,
                remote_parent_ref,
                remote_parent_title,
                document_type="File",
                container_type="Folder",
            )

        # Verify Runner was created with correct arguments
        mock_runner_class.assert_called_once()
        # Verify the runner was started
        mock_engine._threadpool.start.assert_called_once_with(mock_runner_instance)


class TestRollbackDelete:
    """Test cases for Engine.rollback_delete method."""

    def test_rollback_delete_file(self, mock_engine):
        """Test rollback delete for a file."""
        path = Path("/test/file.txt")
        mock_pair = Mock()
        mock_pair.folderish = False
        mock_engine.dao.get_state_from_local.return_value = mock_pair

        mock_engine.rollback_delete(path)

        mock_engine.dao.get_state_from_local.assert_called_once_with(path)
        mock_engine.dao.remove_state_children.assert_not_called()
        mock_engine.dao.force_remote_creation.assert_called_once_with(mock_pair)

    def test_rollback_delete_folder(self, mock_engine):
        """Test rollback delete for a folder."""
        path = Path("/test/folder")
        mock_pair = Mock()
        mock_pair.folderish = True
        mock_engine.dao.get_state_from_local.return_value = mock_pair

        mock_engine.rollback_delete(path)

        mock_engine.dao.remove_state_children.assert_called_once_with(mock_pair)
        mock_engine.dao.force_remote_creation.assert_called_once_with(mock_pair)
        mock_engine._remote_watcher.scan_remote.assert_called_once()

    def test_rollback_delete_no_pair(self, mock_engine):
        """Test rollback delete when no pair exists."""
        path = Path("/test/file.txt")
        mock_engine.dao.get_state_from_local.return_value = None

        mock_engine.rollback_delete(path)

        # Should return early
        mock_engine.dao.force_remote_creation.assert_not_called()


class TestOpenEdit:
    """Test cases for Engine.open_edit method."""

    def test_open_edit_simple_ref(self, mock_engine):
        """Test opening edit with simple reference."""
        remote_ref = "doc-ref-123"
        remote_name = "document.txt"

        mock_engine.open_edit(remote_ref, remote_name)

        # Wait a bit for thread to start
        sleep(0.1)

        # Thread should have been created
        assert hasattr(mock_engine, "_edit_thread")
        assert isinstance(mock_engine._edit_thread, Thread)

    def test_open_edit_with_hash(self, mock_engine):
        """Test opening edit with reference containing hash."""
        remote_ref = "repo#doc-ref-123"
        remote_name = "document.txt"

        mock_engine.open_edit(remote_ref, remote_name)

        # Wait a bit for thread to start
        sleep(0.1)

        # Thread should have been created
        assert hasattr(mock_engine, "_edit_thread")
        assert isinstance(mock_engine._edit_thread, Thread)


class TestOpenRemote:
    """Test cases for Engine.open_remote method."""

    def test_open_remote_with_url(self, mock_engine):
        """Test opening remote with specific URL."""
        url = "https://test.nuxeo.com/specific/path"

        mock_engine.open_remote(url=url)

        mock_engine.manager.open_local_file.assert_called_once_with(url)

    def test_open_remote_without_url(self, mock_engine):
        """Test opening remote with default server URL."""
        mock_engine.open_remote()

        mock_engine.manager.open_local_file.assert_called_once_with(
            mock_engine.server_url
        )


class TestResume:
    """Test cases for Engine.resume method."""

    def test_resume_when_stopped(self, mock_engine):
        """Test resume when engine is stopped."""
        mock_engine._stopped = True

        with patch.object(mock_engine, "start") as mock_start:
            with patch.object(mock_engine, "resume_suspended_transfers"):
                mock_engine.resume()

        # Should call start and return early
        mock_start.assert_called_once()
        mock_engine.queue_manager.resume.assert_not_called()

    def test_resume_when_paused(self, mock_engine):
        """Test resume when engine is paused but running."""
        mock_engine._stopped = False
        mock_engine._pause = True

        # Create mock threads
        mock_thread1 = Mock()
        mock_thread1.isRunning.return_value = True
        mock_thread1.worker = Mock()

        mock_thread2 = Mock()
        mock_thread2.isRunning.return_value = False

        mock_engine._threads = [mock_thread1, mock_thread2]

        with patch.object(
            mock_engine, "resume_suspended_transfers"
        ) as mock_resume_transfers:
            mock_engine.resume()

        assert mock_engine._pause is False
        mock_engine.queue_manager.resume.assert_called_once()
        mock_thread1.worker.resume.assert_called_once()
        mock_thread2.start.assert_called_once()
        mock_resume_transfers.assert_called_once()
        mock_engine.syncResumed.emit.assert_called_once()

    def test_resume_with_no_threads(self, mock_engine):
        """Test resume with no threads."""
        mock_engine._stopped = False
        mock_engine._pause = True
        mock_engine._threads = []

        with patch.object(mock_engine, "resume_suspended_transfers"):
            mock_engine.resume()

        assert mock_engine._pause is False
        mock_engine.queue_manager.resume.assert_called_once()
        mock_engine.syncResumed.emit.assert_called_once()


class TestResumeTransfers:
    """Test cases for Engine._resume_transfers method."""

    def test_resume_transfers_with_list(self, mock_engine):
        """Test resuming transfers with a list of transfers."""
        mock_transfer1 = Mock()
        mock_transfer1.uid = 1
        mock_transfer1.doc_pair = 10

        mock_transfer2 = Mock()
        mock_transfer2.uid = 2
        mock_transfer2.doc_pair = 20

        mock_func = Mock(return_value=[mock_transfer1, mock_transfer2])

        mock_doc_pair1 = Mock()
        mock_doc_pair2 = Mock()
        mock_engine.dao.get_state_from_id.side_effect = [mock_doc_pair1, mock_doc_pair2]
        mock_engine.queue_manager.push = Mock()

        mock_engine._resume_transfers("download", mock_func)

        assert mock_engine.dao.resume_transfer.call_count == 2
        mock_engine.dao.resume_transfer.assert_any_call(
            "download", 1, is_direct_transfer=False
        )
        mock_engine.dao.resume_transfer.assert_any_call(
            "download", 2, is_direct_transfer=False
        )
        assert mock_engine.queue_manager.push.call_count == 2

    def test_resume_transfers_with_single(self, mock_engine):
        """Test resuming transfers with a single transfer."""
        mock_transfer = Mock()
        mock_transfer.uid = 1
        mock_transfer.doc_pair = 10

        mock_func = Mock(return_value=mock_transfer)
        mock_doc_pair = Mock()
        mock_engine.dao.get_state_from_id.return_value = mock_doc_pair
        mock_engine.queue_manager.push = Mock()

        mock_engine._resume_transfers("upload", mock_func, is_direct_transfer=True)

        mock_engine.dao.resume_transfer.assert_called_once_with(
            "upload", 1, is_direct_transfer=True
        )
        mock_engine.queue_manager.push.assert_called_once_with(mock_doc_pair)

    def test_resume_transfers_skip_none_uid(self, mock_engine):
        """Test resuming transfers skips transfers with None uid."""
        mock_transfer = Mock()
        mock_transfer.uid = None

        mock_func = Mock(return_value=[mock_transfer])

        mock_engine._resume_transfers("download", mock_func)

        mock_engine.dao.resume_transfer.assert_not_called()
        mock_engine.queue_manager.push.assert_not_called()


class TestResumeTransfer:
    """Test cases for Engine.resume_transfer method."""

    def test_resume_download(self, mock_engine):
        """Test resuming a download."""
        mock_transfer = Mock()
        mock_transfer.uid = 1
        mock_transfer.doc_pair = 10
        mock_engine.dao.get_download.return_value = mock_transfer
        mock_engine.dao.get_state_from_id.return_value = Mock()
        mock_engine.queue_manager.push = Mock()

        mock_engine.resume_transfer("download", 1)

        mock_engine.dao.get_download.assert_called_once_with(uid=1)

    def test_resume_upload(self, mock_engine):
        """Test resuming an upload."""
        mock_transfer = Mock()
        mock_transfer.uid = 2
        mock_transfer.doc_pair = 20
        mock_engine.dao.get_upload.return_value = mock_transfer
        mock_engine.dao.get_state_from_id.return_value = Mock()
        mock_engine.queue_manager.push = Mock()

        mock_engine.resume_transfer("upload", 2)

        mock_engine.dao.get_upload.assert_called_once_with(uid=2)

    def test_resume_direct_transfer_upload(self, mock_engine):
        """Test resuming a direct transfer upload."""
        mock_transfer = Mock()
        mock_transfer.uid = 3
        mock_transfer.doc_pair = 30
        mock_engine.dao.get_dt_upload.return_value = mock_transfer
        mock_engine.dao.get_state_from_id.return_value = Mock()
        mock_engine.queue_manager.push = Mock()

        mock_engine.resume_transfer("upload", 3, is_direct_transfer=True)

        mock_engine.dao.get_dt_upload.assert_called_once_with(uid=3)


class TestResumeSession:
    """Test cases for Engine.resume_session method."""

    def test_resume_session(self, mock_engine):
        """Test resuming a session."""
        session_uid = 123

        mock_engine.resume_session(session_uid)

        mock_engine.dao.change_session_status.assert_called_once_with(
            session_uid, TransferStatus.ONGOING
        )
        mock_engine.dao.resume_session.assert_called_once_with(session_uid)


class TestManageStaledTransfers:
    """Test cases for Engine._manage_staled_transfers method."""

    def test_manage_staled_transfers_after_crash(self, mock_engine):
        """Test managing staled transfers after app crash."""
        mock_download = Mock()
        mock_download.status = TransferStatus.ONGOING
        mock_download.is_direct_transfer = False
        mock_download.path = Path("/test/file.txt")

        mock_upload = Mock()
        mock_upload.status = TransferStatus.ONGOING
        mock_upload.is_direct_transfer = True
        mock_upload.path = Path("/test/upload.txt")

        mock_engine.dao.get_downloads_with_status.return_value = [mock_download]
        mock_engine.dao.get_uploads_with_status.return_value = [mock_upload]

        with patch("nxdrive.engine.engine.State") as mock_state:
            mock_state.has_crashed = True
            mock_engine._manage_staled_transfers()

        # Should update status to SUSPENDED
        assert mock_engine.dao.set_transfer_status.call_count == 2
        assert mock_download.status == TransferStatus.SUSPENDED
        assert mock_upload.status == TransferStatus.SUSPENDED

    def test_manage_staled_transfers_no_crash(self, mock_engine):
        """Test managing staled transfers when no crash occurred."""
        mock_download = Mock()
        mock_download.status = TransferStatus.ONGOING
        mock_download.is_direct_transfer = False
        mock_download.path = Path("/test/file.txt")

        mock_upload = Mock()
        mock_upload.status = TransferStatus.ONGOING
        mock_upload.is_direct_transfer = True
        mock_upload.path = Path("/test/upload.txt")

        mock_engine.dao.get_downloads_with_status.return_value = [mock_download]
        mock_engine.dao.get_uploads_with_status.return_value = [mock_upload]

        with patch("nxdrive.engine.engine.State") as mock_state:
            mock_state.has_crashed = False
            mock_engine._manage_staled_transfers()

        # Should remove staled transfers
        assert mock_engine.dao.remove_transfer.call_count == 2


class TestCancelUpload:
    """Test cases for Engine.cancel_upload method."""

    def test_cancel_upload_not_found(self, mock_engine):
        """Test canceling upload when upload not found."""
        mock_engine.dao.get_dt_upload.return_value = None

        mock_engine.cancel_upload(123)

        mock_engine.dao.get_dt_upload.assert_called_once_with(uid=123)
        mock_engine.dao.get_state_from_local.assert_not_called()

    def test_cancel_upload_no_doc_pair(self, mock_engine):
        """Test canceling upload when doc pair not found."""
        mock_upload = Mock()
        mock_upload.path = Path("/test/file.txt")
        mock_engine.dao.get_dt_upload.return_value = mock_upload
        mock_engine.dao.get_state_from_local.return_value = None

        mock_engine.cancel_upload(123)

        mock_engine.remote.cancel_batch.assert_not_called()

    def test_cancel_ongoing_upload(self, mock_engine):
        """Test canceling ongoing upload."""
        mock_upload = Mock()
        mock_upload.status = TransferStatus.ONGOING
        mock_upload.path = Path("/test/file.txt")

        mock_doc_pair = Mock()
        mock_doc_pair.processor = 999
        mock_doc_pair.session = 456

        mock_engine.dao.get_dt_upload.return_value = mock_upload
        mock_engine.dao.get_state_from_local.return_value = mock_doc_pair

        mock_engine.cancel_upload(123)

        # Should set status to CANCELLED but not remove
        assert mock_upload.status == TransferStatus.CANCELLED
        mock_engine.dao.set_transfer_status.assert_called_once_with(
            "upload", mock_upload
        )
        mock_engine.remote.cancel_batch.assert_not_called()

    def test_cancel_non_ongoing_upload(self, mock_engine):
        """Test canceling non-ongoing upload."""
        mock_upload = Mock()
        mock_upload.status = TransferStatus.SUSPENDED
        mock_upload.path = Path("/test/file.txt")
        mock_upload.batch = "batch-123"

        mock_doc_pair = Mock()
        mock_doc_pair.processor = None
        mock_doc_pair.session = 456

        mock_engine.dao.get_dt_upload.return_value = mock_upload
        mock_engine.dao.get_state_from_local.return_value = mock_doc_pair

        mock_engine.cancel_upload(123)

        mock_engine.remote.cancel_batch.assert_called_once_with("batch-123")
        mock_engine.dao.remove_transfer.assert_called_once_with(
            "upload", path=mock_upload.path, is_direct_transfer=True
        )
        mock_engine.dao.remove_state.assert_called_once_with(mock_doc_pair)


class TestSuspend:
    """Test cases for Engine.suspend method."""

    def test_suspend(self, mock_engine):
        """Test suspending engine."""
        mock_engine._pause = False
        mock_thread = Mock()
        mock_thread.worker = Mock()
        mock_engine._threads = [mock_thread]
        mock_engine.syncSuspended = Mock()
        mock_engine.syncSuspended.emit = Mock()

        mock_engine.suspend()

        assert mock_engine._pause is True
        mock_engine.dao.suspend_transfers.assert_called_once()
        mock_engine.queue_manager.suspend.assert_called_once()
        mock_thread.worker.suspend.assert_called_once()
        mock_engine.syncSuspended.emit.assert_called_once()

    def test_suspend_already_paused(self, mock_engine):
        """Test suspending when already paused."""
        mock_engine._pause = True

        mock_engine.suspend()

        # Should return early without doing anything
        mock_engine.dao.suspend_transfers.assert_not_called()


class TestUnbind:
    """Test cases for Engine.unbind method."""

    def test_unbind(self, mock_engine, tmp_path):
        """Test unbinding engine."""
        mock_engine.download_dir = tmp_path / "downloads"
        mock_engine.download_dir.mkdir()

        with patch.object(mock_engine, "stop") as mock_stop:
            with patch.object(mock_engine, "dispose_db") as mock_dispose:
                with patch("nxdrive.engine.engine.shutil"):
                    mock_engine.unbind()

        mock_stop.assert_called_once()
        mock_engine.manager.osi.unwatch_folder.assert_called_once_with(
            mock_engine.local_folder
        )
        mock_engine.manager.osi.unregister_folder_link.assert_called_once_with(
            mock_engine.local_folder
        )
        mock_dispose.assert_called_once()
        mock_engine.manager.remove_engine_dbs.assert_called_once_with(mock_engine.uid)
        mock_engine.remote.revoke_token.assert_called_once()


class TestLocalRollback:
    """Test cases for Engine.local_rollback method."""

    def test_local_rollback_force_true(self, mock_engine):
        """Test local rollback with force=True."""
        result = Engine.local_rollback(force=True)
        assert result is True

    def test_local_rollback_force_false(self, mock_engine):
        """Test local rollback with force=False."""
        result = Engine.local_rollback(force=False)
        assert result is False

    def test_local_rollback_default(self, mock_engine):
        """Test local rollback with default."""
        result = Engine.local_rollback()
        assert result is False


class TestCreateThread:
    """Test cases for Engine.create_thread method."""

    def test_create_thread_with_worker(self, mock_engine):
        """Test creating thread with provided worker."""
        from nxdrive.engine.workers import Worker

        mock_worker = Mock(spec=Worker)
        mock_worker.thread = Mock()
        mock_worker.run = Mock()
        mock_worker.quit = Mock()

        thread = mock_engine.create_thread(mock_worker, "TestWorker")

        assert thread == mock_worker.thread
        mock_worker.thread.started.connect.assert_called_once()
        assert thread in mock_engine._threads

    def test_create_thread_without_start_connect(self, mock_engine):
        """Test creating thread without start_connect."""
        from nxdrive.engine.workers import Worker

        mock_worker = Mock(spec=Worker)
        mock_worker.thread = Mock()

        thread = mock_engine.create_thread(
            mock_worker, "TestWorker", start_connect=False
        )

        assert thread == mock_worker.thread
        mock_worker.thread.started.connect.assert_not_called()


class TestRetryPair:
    """Test cases for Engine.retry_pair method."""

    def test_retry_pair(self, mock_engine):
        """Test retrying a pair."""
        mock_state = Mock()
        mock_engine.dao.get_state_from_id.return_value = mock_state

        mock_engine.retry_pair(123)

        mock_engine.dao.get_state_from_id.assert_called_once_with(123)
        mock_engine.dao.reset_error.assert_called_once_with(mock_state)

    def test_retry_pair_not_found(self, mock_engine):
        """Test retrying pair when state not found."""
        mock_engine.dao.get_state_from_id.return_value = None

        mock_engine.retry_pair(123)

        mock_engine.dao.reset_error.assert_not_called()


class TestIgnorePair:
    """Test cases for Engine.ignore_pair method."""

    def test_ignore_pair(self, mock_engine):
        """Test ignoring a pair."""
        mock_state = Mock()
        mock_engine.dao.get_state_from_id.return_value = mock_state

        mock_engine.ignore_pair(123, "Test reason")

        mock_engine.dao.get_state_from_id.assert_called_once_with(123)
        mock_engine.dao.unsynchronize_state.assert_called_once_with(
            mock_state, "Test reason", ignore=True
        )
        mock_engine.dao.reset_error.assert_called_once_with(
            mock_state, last_error="Test reason"
        )

    def test_ignore_pair_not_found(self, mock_engine):
        """Test ignoring pair when state not found."""
        mock_engine.dao.get_state_from_id.return_value = None

        mock_engine.ignore_pair(123, "Test reason")

        mock_engine.dao.unsynchronize_state.assert_not_called()


class TestResolveWithLocal:
    """Test cases for Engine.resolve_with_local method."""

    def test_resolve_with_local(self, mock_engine):
        """Test resolving conflict with local version."""
        mock_row = Mock()
        mock_engine.dao.get_state_from_id.return_value = mock_row

        mock_engine.resolve_with_local(123)

        mock_engine.dao.get_state_from_id.assert_called_once_with(123)
        mock_engine.dao.force_local.assert_called_once_with(mock_row)

    def test_resolve_with_local_not_found(self, mock_engine):
        """Test resolving with local when row not found."""
        mock_engine.dao.get_state_from_id.return_value = None

        mock_engine.resolve_with_local(123)

        mock_engine.dao.force_local.assert_not_called()


class TestResolveWithRemote:
    """Test cases for Engine.resolve_with_remote method."""

    def test_resolve_with_remote(self, mock_engine):
        """Test resolving conflict with remote version."""
        mock_row = Mock()
        mock_engine.dao.get_state_from_id.return_value = mock_row

        mock_engine.resolve_with_remote(123)

        mock_engine.dao.get_state_from_id.assert_called_once_with(123)
        mock_engine.dao.force_remote.assert_called_once_with(mock_row)

    def test_resolve_with_remote_not_found(self, mock_engine):
        """Test resolving with remote when row not found."""
        mock_engine.dao.get_state_from_id.return_value = None

        mock_engine.resolve_with_remote(123)

        mock_engine.dao.force_remote.assert_not_called()


class TestCheckLastSync:
    """Test cases for Engine._check_last_sync method."""

    def test_check_last_sync_not_started(self, mock_engine):
        """Test check last sync when sync not started."""
        mock_engine._sync_started = False

        mock_engine._check_last_sync()

        # Should return early
        mock_engine._local_watcher.empty_events.assert_not_called()

    def test_check_last_sync_queue_not_empty(self, mock_engine):
        """Test check last sync when queue not empty."""
        mock_engine._sync_started = True
        mock_engine._local_watcher.empty_events.return_value = True
        mock_engine.queue_manager.get_errors_count.return_value = 0
        mock_engine.queue_manager.get_overall_size.return_value = 5
        mock_engine.queue_manager.active.return_value = False
        mock_engine._remote_watcher.empty_polls = 3
        mock_engine.dao.get_syncing_count.return_value = 0
        mock_engine.syncCompleted = Mock()
        mock_engine.syncCompleted.emit = Mock()

        mock_engine._check_last_sync()

        # Should not emit syncCompleted
        mock_engine.syncCompleted.emit.assert_not_called()

    def test_check_last_sync_completed_no_errors(self, mock_engine):
        """Test check last sync when sync completed without errors."""
        mock_engine._sync_started = True
        mock_engine._local_watcher.empty_events.return_value = True
        mock_engine.queue_manager.get_errors_count.return_value = 0
        mock_engine.queue_manager.get_overall_size.return_value = 0
        mock_engine.queue_manager.active.return_value = False
        mock_engine._remote_watcher.empty_polls = 3
        mock_engine.dao.get_syncing_count.return_value = 0
        mock_engine.syncCompleted = Mock()
        mock_engine.syncCompleted.emit = Mock()

        with patch("nxdrive.engine.engine.datetime"):
            mock_engine._check_last_sync()

        assert mock_engine._sync_started is False
        mock_engine.dao.update_config.assert_called_once()
        mock_engine.syncCompleted.emit.assert_called_once()

    def test_check_last_sync_completed_with_errors(self, mock_engine):
        """Test check last sync when sync completed with errors."""
        mock_engine._sync_started = True
        mock_engine._local_watcher.empty_events.return_value = True
        mock_engine.queue_manager.get_errors_count.return_value = 2
        mock_engine.queue_manager.get_overall_size.return_value = 0
        mock_engine.queue_manager.active.return_value = False
        mock_engine._remote_watcher.empty_polls = 3
        mock_engine.dao.get_syncing_count.return_value = 0
        mock_engine.syncPartialCompleted = Mock()
        mock_engine.syncPartialCompleted.emit = Mock()

        mock_engine._check_last_sync()

        mock_engine.syncPartialCompleted.emit.assert_called_once()


class TestThreadFinished:
    """Test cases for Engine._thread_finished method."""

    def test_thread_finished(self, mock_engine):
        """Test handling finished threads."""
        mock_thread1 = Mock()
        mock_thread1.isFinished.return_value = True
        mock_thread1.quit = Mock()

        mock_thread2 = Mock()
        mock_thread2.isFinished.return_value = False

        mock_engine._threads = [mock_thread1, mock_thread2]

        mock_engine._thread_finished()

        mock_thread1.quit.assert_called_once()
        assert mock_thread1 not in mock_engine._threads
        assert mock_thread2 in mock_engine._threads


class TestStop:
    """Test cases for Engine.stop method."""

    def test_stop(self, mock_engine):
        """Test stopping engine."""
        mock_engine._stopped = False
        mock_thread = Mock()
        mock_thread.wait.return_value = True
        mock_thread.isRunning.return_value = False
        mock_engine._threads = [mock_thread]
        mock_engine._stop = Mock()
        mock_engine._stop.emit = Mock()

        with patch("nxdrive.engine.engine.Processor") as mock_processor:
            mock_engine.stop()

        assert mock_engine._stopped is True
        mock_engine.dao.suspend_transfers.assert_called_once()
        mock_engine.dao.save_backup.assert_called_once()
        mock_engine.remote.metrics.force_poll.assert_called_once()
        mock_engine._stop.emit.assert_called_once()
        mock_processor.soft_locks = {}


class TestUpdateToken:
    """Test cases for Engine.update_token method."""

    def test_update_token_same_user(self, mock_engine):
        """Test updating token with same user."""
        mock_token = Mock()
        mock_engine.remote_user = "testuser"

        with patch.object(mock_engine, "_load_configuration"):
            with patch.object(mock_engine, "_save_token"):
                with patch.object(mock_engine, "set_invalid_credentials"):
                    with patch.object(mock_engine, "start") as mock_start:
                        mock_engine.update_token(mock_token, "testuser")

        assert mock_engine._remote_token == mock_token
        mock_engine.remote.update_token.assert_called_once_with(mock_token)
        mock_start.assert_called_once()
        mock_engine.manager.restartNeeded.emit.assert_not_called()

    def test_update_token_different_user(self, mock_engine):
        """Test updating token with different user."""
        mock_token = Mock()
        mock_engine.remote_user = "olduser"
        mock_engine.manager.restartNeeded = Mock()
        mock_engine.manager.restartNeeded.emit = Mock()

        with patch.object(mock_engine, "_load_configuration"):
            with patch.object(mock_engine, "_save_token"):
                with patch.object(mock_engine, "set_invalid_credentials"):
                    mock_engine.update_token(mock_token, "newuser")

        assert mock_engine.remote_user == "newuser"
        mock_engine.dao.update_config.assert_called_with("remote_user", "newuser")
        mock_engine.manager.restartNeeded.emit.assert_called_once()


class TestSetupLocalFolder:
    """Test cases for Engine._setup_local_folder method."""

    def test_setup_local_folder_no_sync(self, mock_engine):
        """Test setup local folder when synchronization disabled."""
        mock_local_folder = Mock()
        mock_local_folder.is_dir = Mock()
        mock_engine.local_folder = mock_local_folder

        with patch.object(Feature, "synchronization", False):
            mock_engine._setup_local_folder(True)

        # Should return early
        mock_local_folder.is_dir.assert_not_called()

    def test_setup_local_folder_no_check(self, mock_engine):
        """Test setup local folder without check_fs."""
        mock_local_folder = Mock()
        mock_local_folder.is_dir = Mock()
        mock_engine.local_folder = mock_local_folder

        with patch.object(Feature, "synchronization", True):
            mock_engine._setup_local_folder(False)

        # Should return early
        mock_local_folder.is_dir.assert_not_called()


class TestCancelActionOn:
    """Test cases for Engine.cancel_action_on method."""

    def test_cancel_action_on(self, mock_engine):
        """Test canceling action on specific pair."""
        from nxdrive.engine.processor import Processor

        mock_pair = Mock()
        mock_pair.id = 123

        mock_worker = Mock(spec=Processor)
        mock_worker.get_current_pair.return_value = mock_pair
        mock_worker.quit = Mock()

        mock_thread = Mock()
        mock_thread.worker = mock_worker

        mock_engine._threads = [mock_thread]

        mock_engine.cancel_action_on(123)

        mock_worker.quit.assert_called_once()

    def test_cancel_action_on_no_match(self, mock_engine):
        """Test canceling action when pair not found."""
        from nxdrive.engine.processor import Processor

        mock_pair = Mock()
        mock_pair.id = 456

        mock_worker = Mock(spec=Processor)
        mock_worker.get_current_pair.return_value = mock_pair
        mock_worker.quit = Mock()

        mock_thread = Mock()
        mock_thread.worker = mock_worker

        mock_engine._threads = [mock_thread]

        mock_engine.cancel_action_on(123)

        mock_worker.quit.assert_not_called()


class TestSuspendClient:
    """Test cases for Engine.suspend_client method."""

    def test_suspend_client_when_paused(self, mock_engine):
        """Test suspend client when engine is paused."""
        from nxdrive.exceptions import ThreadInterrupt

        mock_engine._pause = True
        mock_uploader = Mock()

        with pytest.raises(ThreadInterrupt):
            mock_engine.suspend_client(mock_uploader)

    def test_suspend_client_when_stopped(self, mock_engine):
        """Test suspend client when engine is stopped."""
        from nxdrive.exceptions import ThreadInterrupt

        mock_engine._pause = False
        mock_engine._stopped = True
        mock_uploader = Mock()

        with pytest.raises(ThreadInterrupt):
            mock_engine.suspend_client(mock_uploader)

    def test_suspend_client_with_folder_lock(self, mock_engine):
        """Test suspend client with folder lock."""
        from nxdrive.engine.activity import FileAction
        from nxdrive.exceptions import PairInterrupt

        mock_engine._pause = False
        mock_engine._stopped = False
        mock_engine._folder_lock = Path("/test/locked")
        mock_uploader = Mock()

        mock_action = Mock(spec=FileAction)
        mock_action.filepath = Path("/test/locked/subfolder/file.txt")

        mock_engine.local.get_path = Mock(
            return_value=Path("/test/locked/subfolder/file.txt")
        )

        with patch.object(mock_engine, "is_paused", return_value=False):
            with patch.object(mock_engine, "is_started", return_value=True):
                with patch(
                    "nxdrive.engine.engine.current_thread_id", return_value=12345
                ):
                    with patch("nxdrive.engine.engine.Action") as mock_action_cls:
                        mock_action_cls.get_current_action.return_value = mock_action
                        with pytest.raises(PairInterrupt):
                            mock_engine.suspend_client(mock_uploader)
