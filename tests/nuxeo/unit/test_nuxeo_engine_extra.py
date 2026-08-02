"""Extra unit tests for nxdrive.nuxeo.engine.engine module — targets uncovered lines."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest


def _make_engine():
    """Create a mock Engine instance bypassing QObject __init__."""
    from nxdrive.nuxeo.engine.engine import Engine

    with patch.object(Engine, "__init__", return_value=None):
        engine = Engine.__new__(Engine)
    engine.dao = MagicMock()
    engine.remote = MagicMock()
    engine.manager = MagicMock()
    engine.local = MagicMock()
    engine._name = "test"
    engine.uid = "test-uid"
    engine.hostname = "localhost"
    engine.remote_user = "admin"
    engine.server_url = "http://localhost:8080/nuxeo/"
    engine._remote_token = None
    engine._remote_password = None
    engine._web_authentication = False
    engine._stopped = False
    engine._sync_started = False
    engine._threads = []
    engine._folder_lock = None
    engine.local_folder = Path("/tmp/nuxeo-drive-test")
    engine.queue_manager = MagicMock()
    engine._local_watcher = MagicMock()
    engine._remote_watcher = MagicMock()
    engine._scanPair = MagicMock()
    engine.syncStarted = MagicMock()
    engine.syncCompleted = MagicMock()
    engine.syncPartialCompleted = MagicMock()
    engine.started = MagicMock()
    engine._stop = MagicMock()
    engine.cancelTimerSignal = MagicMock()
    engine.directTransferNewFolderSuccess = MagicMock()
    engine.directTransferNewFolderError = MagicMock()
    engine.directTransferSessionFinished = MagicMock()
    engine.displayPendingTask = MagicMock()
    engine._threadpool = MagicMock()
    engine._user_cache = {}
    engine.version = "1.0.0"
    engine.timeout = 30
    engine.remote_cls = MagicMock()
    engine.wui = "web"
    engine.force_ui = ""
    engine._edit_thread = None
    engine.doc_container_type = "Workspace"
    engine.startTimerSignal = MagicMock()
    return engine


# ------------------------------------------------------------------ _create_remote_watcher


class TestCreateRemoteWatcher:
    def test_creates_and_connects_signals(self):
        engine = _make_engine()
        with patch("nxdrive.nuxeo.engine.engine.RemoteWatcher") as MockRW:
            mock_watcher = MagicMock()
            MockRW.return_value = mock_watcher
            engine.create_thread = MagicMock()
            engine._create_remote_watcher()

        MockRW.assert_called_once_with(engine, engine.dao)
        engine.create_thread.assert_called_once_with(
            mock_watcher, "RemoteWatcher", start_connect=False
        )
        mock_watcher.initiate.connect.assert_called_once()
        mock_watcher.remoteWatcherStopped.connect.assert_called_once()
        mock_watcher.updated.connect.assert_called_once()


# ------------------------------------------------------------------ set_local_folder_lock


class TestSetLocalFolderLock:
    def test_sets_lock_and_waits(self):
        engine = _make_engine()
        engine.queue_manager.has_file_processors_on.side_effect = [True, False]

        with patch("nxdrive.nuxeo.engine.engine.sleep"):
            engine.set_local_folder_lock(Path("/tmp/locked"))

        assert engine._folder_lock == Path("/tmp/locked")

    def test_no_wait_if_no_processors(self):
        engine = _make_engine()
        engine.queue_manager.has_file_processors_on.return_value = False

        engine.set_local_folder_lock(Path("/tmp/locked"))
        assert engine._folder_lock == Path("/tmp/locked")


# ------------------------------------------------------------------ _manage_staled_transfers


class TestManageStaledTransfersExtra:
    def test_upload_direct_transfer_removal(self):
        from nxdrive.drive.constants import TransferStatus

        engine = _make_engine()
        transfer = MagicMock()
        transfer.status = TransferStatus.ONGOING
        transfer.path = Path("/tmp/f.txt")
        transfer.is_direct_transfer = True
        engine.dao.get_downloads_with_status.return_value = []
        engine.dao.get_uploads_with_status.return_value = [transfer]

        with patch("nxdrive.nuxeo.engine.engine.State") as MockState:
            MockState.has_crashed = False
            engine._manage_staled_transfers()

        engine.dao.remove_transfer.assert_called_once_with(
            "upload", path=transfer.path, is_direct_transfer=True
        )


# ------------------------------------------------------------------ _check_last_sync


class TestCheckLastSync:
    def test_not_started_returns_early(self):
        engine = _make_engine()
        engine._sync_started = False
        engine._check_last_sync()
        engine.syncCompleted.emit.assert_not_called()

    def test_queue_has_items_no_complete(self):
        engine = _make_engine()
        engine._sync_started = True
        engine.queue_manager.get_overall_size.return_value = 5
        engine.queue_manager.get_errors_count.return_value = 0
        engine.queue_manager.active.return_value = False
        engine._local_watcher.empty_events.return_value = True
        engine._remote_watcher.empty_polls = 0

        with patch("nxdrive.nuxeo.engine.engine.WINDOWS", False):
            engine._check_last_sync()
        engine.syncCompleted.emit.assert_not_called()

    def test_active_queue_no_complete(self):
        engine = _make_engine()
        engine._sync_started = True
        engine.queue_manager.get_overall_size.return_value = 0
        engine.queue_manager.get_errors_count.return_value = 0
        engine.queue_manager.active.return_value = True
        engine._local_watcher.empty_events.return_value = True
        engine._remote_watcher.empty_polls = 0

        with patch("nxdrive.nuxeo.engine.engine.WINDOWS", False):
            engine._check_last_sync()
        engine.syncCompleted.emit.assert_not_called()

    def test_empty_events_false_no_complete(self):
        engine = _make_engine()
        engine._sync_started = True
        engine.queue_manager.get_overall_size.return_value = 0
        engine.queue_manager.get_errors_count.return_value = 0
        engine.queue_manager.active.return_value = False
        engine._local_watcher.empty_events.return_value = False
        engine._remote_watcher.empty_polls = 0

        with patch("nxdrive.nuxeo.engine.engine.WINDOWS", False):
            engine._check_last_sync()
        engine.syncCompleted.emit.assert_not_called()

    def test_errors_emit_partial(self):
        engine = _make_engine()
        engine._sync_started = True
        engine.queue_manager.get_overall_size.return_value = 0
        engine.queue_manager.get_errors_count.return_value = 3
        engine.queue_manager.active.return_value = False
        engine._local_watcher.empty_events.return_value = True
        engine._remote_watcher.empty_polls = 0
        engine.dao.get_syncing_count.return_value = 0

        with patch("nxdrive.nuxeo.engine.engine.WINDOWS", False):
            engine._check_last_sync()
        engine.syncPartialCompleted.emit.assert_called_once()
        engine.syncCompleted.emit.assert_not_called()

    def test_no_errors_emit_completed(self):
        engine = _make_engine()
        engine._sync_started = True
        engine.queue_manager.get_overall_size.return_value = 0
        engine.queue_manager.get_errors_count.return_value = 0
        engine.queue_manager.active.return_value = False
        engine._local_watcher.empty_events.return_value = True
        engine._remote_watcher.empty_polls = 0
        engine.dao.get_syncing_count.return_value = 0

        with patch("nxdrive.nuxeo.engine.engine.WINDOWS", False):
            engine._check_last_sync()
        engine.syncCompleted.emit.assert_called_once()
        assert engine._sync_started is False

    def test_windows_logging(self):
        engine = _make_engine()
        engine._sync_started = True
        engine.queue_manager.get_overall_size.return_value = 0
        engine.queue_manager.get_errors_count.return_value = 0
        engine.queue_manager.active.return_value = False
        engine._local_watcher.empty_events.return_value = True
        engine._local_watcher.get_win_queue_size.return_value = 0
        engine._local_watcher.get_win_folder_scan_size.return_value = 0
        engine._remote_watcher.empty_polls = 0
        engine.dao.get_syncing_count.return_value = 0

        with patch("nxdrive.nuxeo.engine.engine.WINDOWS", True):
            engine._check_last_sync()
        engine.syncCompleted.emit.assert_called_once()


# ------------------------------------------------------------------ cancel_action_on


class TestCancelActionOn:
    def test_cancels_matching_processor(self):
        from nxdrive.nuxeo.engine.processor import Processor

        engine = _make_engine()
        mock_thread = MagicMock()
        mock_worker = MagicMock(spec=Processor)
        mock_pair = MagicMock()
        mock_pair.id = 42
        mock_worker.get_current_pair.return_value = mock_pair
        mock_thread.worker = mock_worker
        engine._threads = [mock_thread]

        engine.cancel_action_on(42)
        mock_worker.quit.assert_called_once()

    def test_no_cancel_different_pair_id(self):
        from nxdrive.nuxeo.engine.processor import Processor

        engine = _make_engine()
        mock_thread = MagicMock()
        mock_worker = MagicMock(spec=Processor)
        mock_pair = MagicMock()
        mock_pair.id = 99
        mock_worker.get_current_pair.return_value = mock_pair
        mock_thread.worker = mock_worker
        engine._threads = [mock_thread]

        engine.cancel_action_on(42)
        mock_worker.quit.assert_not_called()

    def test_no_cancel_when_pair_is_none(self):
        from nxdrive.nuxeo.engine.processor import Processor

        engine = _make_engine()
        mock_thread = MagicMock()
        mock_worker = MagicMock(spec=Processor)
        mock_worker.get_current_pair.return_value = None
        mock_thread.worker = mock_worker
        engine._threads = [mock_thread]

        engine.cancel_action_on(42)
        mock_worker.quit.assert_not_called()

    def test_thread_without_worker_attr(self):
        engine = _make_engine()
        mock_thread = MagicMock(spec=[])  # no worker attribute
        engine._threads = [mock_thread]

        # Should not raise
        engine.cancel_action_on(42)


# ------------------------------------------------------------------ suspend_client


class TestSuspendClient:
    def test_paused_raises_thread_interrupt(self):
        from nxdrive.drive.exceptions import ThreadInterrupt

        engine = _make_engine()
        engine.is_paused = MagicMock(return_value=True)
        engine.is_started = MagicMock(return_value=True)

        with pytest.raises(ThreadInterrupt):
            engine.suspend_client(MagicMock())

    def test_not_started_raises_thread_interrupt(self):
        from nxdrive.drive.exceptions import ThreadInterrupt

        engine = _make_engine()
        engine.is_paused = MagicMock(return_value=False)
        engine.is_started = MagicMock(return_value=False)

        with pytest.raises(ThreadInterrupt):
            engine.suspend_client(MagicMock())

    def test_thread_not_started_raises(self):
        from nxdrive.drive.exceptions import ThreadInterrupt
        from nxdrive.nuxeo.engine.processor import Processor

        engine = _make_engine()
        engine.is_paused = MagicMock(return_value=False)
        engine.is_started = MagicMock(return_value=True)

        mock_thread = MagicMock()
        mock_worker = MagicMock(spec=Processor)
        mock_worker.is_started.return_value = False
        tid = 12345
        mock_worker.thread_id = tid
        mock_thread.worker = mock_worker
        engine._threads = [mock_thread]

        with patch("nxdrive.nuxeo.engine.engine.current_thread_id", return_value=tid):
            with patch(
                "nxdrive.nuxeo.engine.engine.Action.get_current_action",
                return_value=MagicMock(),
            ):
                with pytest.raises(ThreadInterrupt):
                    engine.suspend_client(MagicMock())

    def test_folder_lock_raises_pair_interrupt(self):
        from nxdrive.drive.engine.activity import FileAction
        from nxdrive.drive.exceptions import PairInterrupt

        engine = _make_engine()
        engine.is_paused = MagicMock(return_value=False)
        engine.is_started = MagicMock(return_value=True)
        engine._threads = []
        engine._folder_lock = Path("/tmp/locked")

        mock_action = MagicMock(spec=FileAction)
        mock_action.filepath = Path("/tmp/locked/subdir/file.txt")
        engine.local.get_path.return_value = Path("/tmp/locked/subdir/file.txt")

        with patch("nxdrive.nuxeo.engine.engine.current_thread_id", return_value=1):
            with patch(
                "nxdrive.nuxeo.engine.engine.Action.get_current_action",
                return_value=mock_action,
            ):
                with pytest.raises(PairInterrupt):
                    engine.suspend_client(MagicMock())

    def test_no_lock_no_interrupt(self):
        from nxdrive.drive.engine.activity import FileAction

        engine = _make_engine()
        engine.is_paused = MagicMock(return_value=False)
        engine.is_started = MagicMock(return_value=True)
        engine._threads = []
        engine._folder_lock = None

        mock_action = MagicMock(spec=FileAction)
        mock_action.filepath = Path("/tmp/other/file.txt")

        with patch("nxdrive.nuxeo.engine.engine.current_thread_id", return_value=1):
            with patch(
                "nxdrive.nuxeo.engine.engine.Action.get_current_action",
                return_value=mock_action,
            ):
                # Should not raise
                engine.suspend_client(MagicMock())


# ------------------------------------------------------------------ get_metadata_url


class TestGetMetadataUrl:
    def test_web_ui(self):
        engine = _make_engine()
        engine.wui = "web"
        engine.force_ui = ""
        url = engine.get_metadata_url("default#doc-uid-123")
        assert url == "http://localhost:8080/nuxeo/ui#!/doc/doc-uid-123"

    def test_jsf_ui(self):
        engine = _make_engine()
        engine.wui = "jsf"
        engine.force_ui = ""
        engine.remote.client.repository = "default"
        url = engine.get_metadata_url("default#doc-uid-123")
        assert url == "http://localhost:8080/nuxeo/nxdoc/default/doc-uid-123/view_documents"

    def test_jsf_edit(self):
        engine = _make_engine()
        engine.wui = "jsf"
        engine.force_ui = ""
        engine.remote.client.repository = "default"
        url = engine.get_metadata_url("default#doc-uid-123", edit=True)
        assert url == "http://localhost:8080/nuxeo/nxdoc/default/doc-uid-123/view_drive_metadata"

    def test_force_ui_overrides_wui(self):
        engine = _make_engine()
        engine.wui = "jsf"
        engine.force_ui = "web"
        url = engine.get_metadata_url("default#doc-uid-123")
        assert url == "http://localhost:8080/nuxeo/ui#!/doc/doc-uid-123"


# ------------------------------------------------------------------ get_task_url


class TestGetTaskUrl:
    def test_web_ui(self):
        engine = _make_engine()
        engine.wui = "web"
        engine.force_ui = ""
        url = engine.get_task_url("task-123")
        assert url == "http://localhost:8080/nuxeo/ui#!/tasks/task-123"

    def test_jsf_ui(self):
        engine = _make_engine()
        engine.wui = "jsf"
        engine.force_ui = ""
        engine.remote.client.repository = "default"
        url = engine.get_task_url("task-123")
        assert url == "http://localhost:8080/nuxeo/tasks/default/task-123/view_documents"

    def test_jsf_edit(self):
        engine = _make_engine()
        engine.wui = "jsf"
        engine.force_ui = ""
        engine.remote.client.repository = "default"
        url = engine.get_task_url("task-123", edit=True)
        assert url == "http://localhost:8080/nuxeo/tasks/default/task-123/view_drive_metadata"


# ------------------------------------------------------------------ get_user_full_name


class TestGetUserFullName:
    def test_cached(self):
        engine = _make_engine()
        engine._user_cache = {"jdoe": "John Doe"}
        assert engine.get_user_full_name("jdoe") == "John Doe"

    def test_cache_only_miss(self):
        engine = _make_engine()
        engine._user_cache = {}
        result = engine.get_user_full_name("jdoe", cache_only=True)
        assert result == "jdoe"

    def test_fetches_from_remote(self):
        engine = _make_engine()
        engine._user_cache = {}
        mock_user = MagicMock()
        mock_user.properties = {
            "firstName": "Jane",
            "lastName": "Smith",
            "username": "jsmith",
        }
        engine.remote.users.get.return_value = mock_user
        result = engine.get_user_full_name("jsmith")
        assert result == "Jane Smith"
        assert engine._user_cache["jsmith"] == "Jane Smith"

    def test_fetches_username_if_name_empty(self):
        engine = _make_engine()
        engine._user_cache = {}
        mock_user = MagicMock()
        mock_user.properties = {
            "firstName": "",
            "lastName": "",
            "username": "anonymous",
        }
        engine.remote.users.get.return_value = mock_user
        result = engine.get_user_full_name("anonymous")
        assert result == "anonymous"

    def test_http_error_returns_userid(self):
        from nuxeo.exceptions import HTTPError

        engine = _make_engine()
        engine._user_cache = {}
        engine.remote.users.get.side_effect = HTTPError(status=404, message="Not found")
        result = engine.get_user_full_name("unknown")
        assert result == "unknown"

    def test_type_error_returns_userid(self):
        engine = _make_engine()
        engine._user_cache = {}
        engine.remote.users.get.side_effect = TypeError("bad")
        result = engine.get_user_full_name("baduser")
        assert result == "baduser"


# ------------------------------------------------------------------ open_edit


class TestOpenEdit:
    def test_starts_thread(self):
        engine = _make_engine()
        engine.manager.directEdit = MagicMock()
        with patch("nxdrive.nuxeo.engine.engine.Thread") as MockThread:
            mock_thread = MagicMock()
            MockThread.return_value = mock_thread
            engine.open_edit("default#doc-123", "file.txt")
        mock_thread.start.assert_called_once()

    def test_strips_hash_prefix(self):
        engine = _make_engine()
        engine.manager.directEdit = MagicMock()
        with patch("nxdrive.nuxeo.engine.engine.Thread") as MockThread:
            mock_thread = MagicMock()
            MockThread.return_value = mock_thread
            engine.open_edit("repo#abc-def", "name.pdf")
        # Get the target callable and invoke it to verify doc_ref
        target_fn = MockThread.call_args[1]["target"]
        target_fn()
        engine.manager.directEdit.emit.assert_called_once_with(
            engine.server_url, "abc-def", engine.remote_user, None
        )


# ------------------------------------------------------------------ send_task_notification


class TestSendTaskNotification:
    def test_emits_signal(self):
        engine = _make_engine()
        engine.send_task_notification("task-1", "/path/to/doc", "New Task")
        engine.displayPendingTask.emit.assert_called_once_with(
            "test-uid", "task-1", "/path/to/doc", "New Task"
        )


# ------------------------------------------------------------------ cancel_session


class TestCancelSessionExtra:
    def test_cancel_with_no_folderish(self):
        engine = _make_engine()
        engine.dao.get_session_items.return_value = [
            {"facets": []},
            {"facets": ["Commentable"]},
        ]
        engine.cancel_session(10)
        engine.cancelTimerSignal.emit.assert_called_once_with(10)
        sent = engine.remote.metrics.send.call_args[0][0]
        assert sent["directTransfer.session.file.count"] == 2
        assert sent["directTransfer.session.folder.count"] == 0


# ------------------------------------------------------------------ _check_root


class TestCheckRoot:
    def test_skips_when_sync_disabled(self):
        engine = _make_engine()
        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = False
            engine._check_root()
        engine.dao.get_state_from_local.assert_not_called()

    def test_skips_when_filters_not_configured(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = None
        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = True
            engine._check_root()
        engine.dao.get_state_from_local.assert_not_called()

    def test_root_already_exists(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = "1"
        engine.dao.get_state_from_local.return_value = MagicMock()
        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = True
            engine._check_root()
        # Should not try to add top level state
        engine.dao.insert_local_state.assert_not_called()

    def test_creates_root_when_missing(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = "1"
        engine.dao.get_state_from_local.return_value = None
        engine.local_folder = MagicMock()
        engine.local_folder.is_dir.return_value = True
        engine._add_top_level_state = MagicMock()
        engine._set_root_icon = MagicMock()

        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = True
            with patch("nxdrive.nuxeo.engine.engine.unset_path_readonly"):
                with patch("nxdrive.nuxeo.engine.engine.set_path_readonly"):
                    engine._check_root()

        engine._add_top_level_state.assert_called_once()
        engine._set_root_icon.assert_called_once()

    def test_creates_root_folder_if_not_dir(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = "1"
        engine.dao.get_state_from_local.return_value = None
        engine.local_folder = MagicMock()
        engine.local_folder.is_dir.return_value = False
        engine._add_top_level_state = MagicMock()
        engine._set_root_icon = MagicMock()

        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = True
            with patch("nxdrive.nuxeo.engine.engine.set_path_readonly"):
                engine._check_root()

        engine.local_folder.mkdir.assert_called_once_with(parents=True)

    def test_unauthorized_sets_invalid_creds(self):
        from nuxeo.exceptions import Unauthorized

        engine = _make_engine()
        engine.dao.get_config.return_value = "1"
        engine.dao.get_state_from_local.return_value = None
        engine.local_folder = MagicMock()
        engine.local_folder.is_dir.return_value = True
        engine._add_top_level_state = MagicMock(side_effect=Unauthorized())
        engine.set_invalid_credentials = MagicMock()

        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = True
            with patch("nxdrive.nuxeo.engine.engine.unset_path_readonly"):
                engine._check_root()

        engine.set_invalid_credentials.assert_called_once()


# ------------------------------------------------------------------ _send_roots_metrics


class TestSendRootsMetricsExtra:
    def test_skips_when_sync_disabled(self):
        engine = _make_engine()
        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = False
            engine._send_roots_metrics()
        engine.dao.get_count.assert_not_called()


# ------------------------------------------------------------------ _seed_userid_mapper


class TestSeedUseridMapper:
    def test_seeds_mapper_with_existing_uuid(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = "real-uuid-123"
        engine.remote.client.userid_mapper = {}

        engine._seed_userid_mapper()
        assert engine.remote.client.userid_mapper["admin"] == "real-uuid-123"

    def test_skips_sentinel_value(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = "__nosupport__"
        engine.remote.client.userid_mapper = {}

        # _refresh_user_uuid will be called; simulate it returning sentinel again
        engine._refresh_user_uuid = MagicMock()
        # After refresh, get_config still returns sentinel
        engine.dao.get_config.return_value = "__nosupport__"

        engine._seed_userid_mapper()
        assert "admin" not in engine.remote.client.userid_mapper

    def test_no_uuid_fetches_from_server(self):
        engine = _make_engine()
        # First call returns None (no UUID stored), second returns the fetched UUID
        engine.dao.get_config.side_effect = [None, "fetched-uuid"]
        engine.remote.client.userid_mapper = {}
        engine._refresh_user_uuid = MagicMock()

        engine._seed_userid_mapper()
        engine._refresh_user_uuid.assert_called_once()
        assert engine.remote.client.userid_mapper["admin"] == "fetched-uuid"

    def test_no_uuid_fetch_error_stores_sentinel(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = None
        engine.remote.client.userid_mapper = {}
        engine._refresh_user_uuid = MagicMock(side_effect=Exception("network"))

        engine._seed_userid_mapper()
        engine.dao.update_config.assert_called_with("user_uuid", "__nosupport__")

    def test_nosupport_recheck_now_supported(self):
        """Server previously didn't support UUID, but now does."""
        engine = _make_engine()
        # First get_config returns sentinel, after refresh returns real UUID
        engine.dao.get_config.side_effect = ["__nosupport__", "new-uuid"]
        engine.remote.client.userid_mapper = {}
        engine._refresh_user_uuid = MagicMock()

        engine._seed_userid_mapper()
        assert engine.remote.client.userid_mapper["admin"] == "new-uuid"

    def test_nosupport_recheck_fails(self):
        """Server still doesn't support UUID; recheck errors silently."""
        engine = _make_engine()
        engine.dao.get_config.return_value = "__nosupport__"
        engine.remote.client.userid_mapper = {}
        engine._refresh_user_uuid = MagicMock(side_effect=Exception("fail"))

        engine._seed_userid_mapper()
        assert "admin" not in engine.remote.client.userid_mapper

    def test_no_remote_user_skips(self):
        engine = _make_engine()
        engine.remote_user = ""
        engine.dao.get_config.return_value = None
        engine.remote.client.userid_mapper = {}

        engine._seed_userid_mapper()
        assert "admin" not in engine.remote.client.userid_mapper


# ------------------------------------------------------------------ _refresh_user_uuid


class TestRefreshUserUuid:
    def test_no_remote_returns_early(self):
        engine = _make_engine()
        engine.remote = None
        engine._refresh_user_uuid()
        engine.dao.update_config.assert_not_called()

    def test_no_resolve_username_stores_sentinel(self):
        engine = _make_engine()
        del engine.remote.client.resolve_username
        engine._refresh_user_uuid()
        engine.dao.update_config.assert_called_with("user_uuid", "__nosupport__")

    def test_no_userid_mapper_stores_sentinel(self):
        engine = _make_engine()
        engine.remote.client.resolve_username = MagicMock()
        del engine.remote.client.userid_mapper
        engine._refresh_user_uuid()
        engine.dao.update_config.assert_called_with("user_uuid", "__nosupport__")

    def test_resolves_and_stores_uuid(self):
        engine = _make_engine()
        engine.remote.client.resolve_username = MagicMock()
        engine.remote.client.userid_mapper = {"admin": "uuid-abc"}
        engine._refresh_user_uuid()
        engine.remote.client.resolve_username.assert_called_once_with("admin")
        engine.dao.update_config.assert_called_with("user_uuid", "uuid-abc")

    def test_no_uuid_returned_stores_sentinel(self):
        engine = _make_engine()
        engine.remote.client.resolve_username = MagicMock()
        engine.remote.client.userid_mapper = {}
        engine._refresh_user_uuid()
        engine.dao.update_config.assert_called_with("user_uuid", "__nosupport__")


# ------------------------------------------------------------------ update_token


class TestUpdateToken:
    def test_updates_token_and_starts(self):
        engine = _make_engine()
        engine._load_configuration = MagicMock()
        engine._save_token = MagicMock()
        engine.set_invalid_credentials = MagicMock()
        engine._refresh_user_uuid = MagicMock()
        engine.start = MagicMock()

        engine.update_token({"access_token": "new"}, "admin")

        engine._load_configuration.assert_called_once()
        engine.remote.update_token.assert_called_once()
        engine.set_invalid_credentials.assert_called_once_with(value=False)
        engine._save_token.assert_called_once()
        engine.start.assert_called_once()

    def test_username_changed_triggers_restart(self):
        engine = _make_engine()
        engine._load_configuration = MagicMock()
        engine._save_token = MagicMock()
        engine.set_invalid_credentials = MagicMock()
        engine.manager.restartNeeded = MagicMock()
        engine.start = MagicMock()

        engine.update_token("token-str", "new-user")

        engine.dao.update_config.assert_any_call("remote_user", "new-user")
        engine.dao.update_config.assert_any_call("user_uuid", "")
        engine.manager.restartNeeded.emit.assert_called_once()
        engine.start.assert_not_called()

    def test_uuid_refresh_error_doesnt_raise(self):
        engine = _make_engine()
        engine._load_configuration = MagicMock()
        engine._save_token = MagicMock()
        engine.set_invalid_credentials = MagicMock()
        engine._refresh_user_uuid = MagicMock(side_effect=Exception("fail"))
        engine.start = MagicMock()

        # Should not raise
        engine.update_token("token", "admin")
        engine.start.assert_called_once()


# ------------------------------------------------------------------ init_remote


class TestInitRemote:
    def test_creates_remote(self):
        engine = _make_engine()
        engine.manager.device_id = "dev-1"
        engine.manager.proxy = MagicMock()

        with patch("nxdrive.nuxeo.engine.engine.get_verify", return_value=True):
            with patch(
                "nxdrive.nuxeo.engine.engine.client_certificate", return_value=None
            ):
                result = engine.init_remote()

        engine.remote_cls.assert_called_once()
        args = engine.remote_cls.call_args
        assert args[0][0] == engine.server_url
        assert args[0][1] == "admin"


# ------------------------------------------------------------------ handle_session_status


class TestHandleSessionStatus:
    def test_none_session(self):
        engine = _make_engine()
        engine.handle_session_status(None)
        engine.directTransferSessionFinished.emit.assert_not_called()

    def test_not_done_session(self):
        from nxdrive.drive.constants import TransferStatus

        engine = _make_engine()
        session = MagicMock()
        session.status = TransferStatus.ONGOING
        engine.handle_session_status(session)
        engine.directTransferSessionFinished.emit.assert_not_called()

    def test_done_session_sends_metrics(self):
        from nxdrive.drive.constants import TransferStatus

        engine = _make_engine()
        engine.send_metric = MagicMock()
        session = MagicMock()
        session.status = TransferStatus.DONE
        session.uid = 5
        session.remote_ref = "ref-1"
        session.remote_path = "/path"
        session.total_items = 4
        engine.dao.get_session_items.return_value = [
            {"facets": ["Folderish"]},
            {"facets": []},
            {"facets": []},
            {"facets": ["Folderish", "Other"]},
        ]

        engine.handle_session_status(session)
        engine.directTransferSessionFinished.emit.assert_called_once()
        sent = engine.remote.metrics.send.call_args[0][0]
        assert sent["directTransfer.session.folder.count"] == 2
        assert sent["directTransfer.session.file.count"] == 2


# ------------------------------------------------------------------ _create_remote_folder


class TestCreateRemoteFolder:
    def test_success(self):
        engine = _make_engine()
        engine.remote.upload_folder.return_value = {"path": "/ws/new", "uid": "u1"}
        result = engine._create_remote_folder("/ws", "new", 1)
        assert result == {"path": "/ws/new", "uid": "u1"}
        engine.directTransferNewFolderSuccess.emit.assert_called_once_with("/ws/new")

    def test_failure(self):
        engine = _make_engine()
        engine.remote.upload_folder.side_effect = Exception("fail")
        result = engine._create_remote_folder("/ws", "new", 1)
        assert result == {}
        engine.directTransferNewFolderError.emit.assert_called_once()


# ------------------------------------------------------------------ _create_remote_folder_with_enricher


class TestCreateRemoteFolderWithEnricher:
    def test_success(self):
        engine = _make_engine()
        engine.remote.upload_folder_type.return_value = {"path": "/ws/typed", "uid": "u2"}
        result = engine._create_remote_folder_with_enricher("/ws", "typed", "CustomType", 1)
        assert result == {"path": "/ws/typed", "uid": "u2"}
        engine.directTransferNewFolderSuccess.emit.assert_called_once()

    def test_failure(self):
        engine = _make_engine()
        engine.remote.upload_folder_type.side_effect = Exception("fail")
        result = engine._create_remote_folder_with_enricher("/ws", "typed", "CustomType", 1)
        assert result == {}
        engine.directTransferNewFolderError.emit.assert_called_once()
