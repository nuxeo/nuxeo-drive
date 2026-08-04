"""Unit tests for nxdrive.alfresco.engine.watcher.remote_watcher."""

from datetime import datetime, timezone
from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

import pytest
from alfresco.exceptions import AuthenticationError as AlfrescoAuthError
from alfresco.exceptions import NetworkError as AlfrescoNetworkError

from nxdrive.alfresco.engine.watcher.remote_watcher import AlfrescoRemoteWatcher
from nxdrive.drive.constants import ROOT
from nxdrive.drive.objects import RemoteFileInfo


@pytest.fixture
def watcher():
    """Build an AlfrescoRemoteWatcher with mocked engine and DAO."""
    return _make_watcher()


def _make_watcher():
    """Build an AlfrescoRemoteWatcher with mocked engine and DAO (non-fixture)."""
    engine = MagicMock()
    dao = MagicMock()
    dao.get_config.return_value = None

    with patch.object(AlfrescoRemoteWatcher, "__init__", lambda self, *a, **kw: None):
        w = AlfrescoRemoteWatcher(engine, dao)

    w.engine = engine
    w.dao = dao
    w._last_remote_full_scan = None
    w._next_check = 0
    w._interact = MagicMock()
    w.remoteScanFinished = MagicMock()
    w.remoteWatcherStopped = MagicMock()
    return w


def _make_doc_pair(**kwargs):
    """Create a minimal DocPair mock."""
    pair = MagicMock()
    pair.remote_ref = kwargs.get("remote_ref", "node-id-123")
    pair.remote_parent_path = kwargs.get("remote_parent_path", "")
    pair.local_path = kwargs.get("local_path", ROOT)
    pair.local_name = kwargs.get("local_name", "folder")
    pair.pair_state = kwargs.get("pair_state", "synchronized")
    pair.last_remote_updated = kwargs.get("last_remote_updated", "2024-01-01 00:00:00")
    pair.local_digest = kwargs.get("local_digest", None)
    pair.processor = kwargs.get("processor", 0)
    return pair


def _make_remote_info(**kwargs):
    """Create a minimal RemoteFileInfo mock."""
    info = MagicMock(spec=RemoteFileInfo)
    info.uid = kwargs.get("uid", "node-id-123")
    info.name = kwargs.get("name", "MyFolder")
    info.folderish = kwargs.get("folderish", True)
    info.path = kwargs.get("path", "/Company Home/MyFolder")
    info.last_modification_time = kwargs.get(
        "last_modification_time", datetime(2024, 1, 1, tzinfo=timezone.utc)
    )
    info.digest = kwargs.get("digest", None)
    return info


class TestGetMetrics:
    def test_includes_last_scan_and_next_polling(self):
        watcher = _make_watcher()
        watcher._last_remote_full_scan = datetime(2024, 6, 1, tzinfo=timezone.utc)
        watcher._next_check = 1234.5

        with patch.object(
            AlfrescoRemoteWatcher.__bases__[0], "get_metrics", return_value={}
        ):
            metrics = watcher.get_metrics()

        assert metrics["last_remote_full_scan"] == datetime(
            2024, 6, 1, tzinfo=timezone.utc
        )
        assert metrics["next_polling"] == 1234.5


class TestScanRemote:
    def test_no_remote_returns_early(self):
        watcher = _make_watcher()
        watcher.engine.remote = None
        watcher.scan_remote()
        watcher.dao.get_state_from_local.assert_not_called()

    def test_no_root_pair_returns_early(self):
        watcher = _make_watcher()
        watcher.engine.remote = MagicMock()
        watcher.engine.download_dir = PurePosixPath("/")
        watcher.dao.get_state_from_local.return_value = None
        watcher.scan_remote()
        # Should not have tried to get node
        watcher.engine.remote._node_to_remote_file_info.assert_not_called()

    def test_auth_error_sets_invalid_credentials(self):
        watcher = _make_watcher()
        remote = MagicMock()
        remote.get_node.side_effect = AlfrescoAuthError("expired")
        watcher.engine.remote = remote
        watcher.engine.download_dir = PurePosixPath("/")

        root_pair = _make_doc_pair(remote_ref="root-node")
        watcher.dao.get_state_from_local.return_value = root_pair

        watcher.scan_remote()
        watcher.engine.set_invalid_credentials.assert_called_once()

    def test_network_error_does_not_crash(self):
        watcher = _make_watcher()
        remote = MagicMock()
        remote.get_node.side_effect = AlfrescoNetworkError("timeout")
        watcher.engine.remote = remote
        watcher.engine.download_dir = PurePosixPath("/")

        root_pair = _make_doc_pair(remote_ref="root-node")
        watcher.dao.get_state_from_local.return_value = root_pair

        # Should not raise
        watcher.scan_remote()
        watcher.engine.set_invalid_credentials.assert_not_called()

    def test_successful_scan_updates_timestamp(self):
        watcher = _make_watcher()
        remote = MagicMock()
        root_info = _make_remote_info(uid="root-node", folderish=True)
        remote._node_to_remote_file_info.return_value = root_info
        remote.get_node.return_value = MagicMock()
        watcher.engine.remote = remote
        watcher.engine.download_dir = PurePosixPath("/")

        root_pair = _make_doc_pair(remote_ref="root-node")
        watcher.dao.get_state_from_local.return_value = root_pair

        with patch.object(watcher, "_scan_remote_recursive"):
            watcher.scan_remote()

        assert watcher._last_remote_full_scan is not None
        watcher.dao.update_config.assert_called_once()
        watcher.remoteScanFinished.emit.assert_called_once()


class TestScanRemoteRecursive:
    def test_non_folderish_returns_immediately(self):
        watcher = _make_watcher()
        pair = _make_doc_pair()
        info = _make_remote_info(folderish=False)

        watcher._scan_remote_recursive(pair, info)
        watcher._interact.assert_not_called()

    def test_no_remote_returns_early(self):
        watcher = _make_watcher()
        watcher.engine.remote = None
        pair = _make_doc_pair()
        info = _make_remote_info(folderish=True)

        watcher._scan_remote_recursive(pair, info)

    def test_new_item_inserted(self):
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        # Remote has one child
        child_node = MagicMock()
        remote.client.nodes.iter_children.return_value = [child_node]
        child_info = _make_remote_info(uid="child-1", name="Doc.txt", folderish=False)
        remote._node_to_remote_file_info.return_value = child_info

        # No existing DB children
        watcher.dao.get_remote_children.return_value = []
        watcher.dao.is_filter.return_value = False

        parent_pair = _make_doc_pair(
            remote_ref="parent-node", remote_parent_path="", local_path=ROOT
        )
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.insert_remote_state.assert_called_once()

    def test_existing_item_unchanged_updates_state(self):
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        child_node = MagicMock()
        remote.client.nodes.iter_children.return_value = [child_node]
        child_info = _make_remote_info(
            uid="child-1",
            name="Doc.txt",
            folderish=False,
            last_modification_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        remote._node_to_remote_file_info.return_value = child_info

        existing_pair = _make_doc_pair(
            remote_ref="child-1",
            last_remote_updated="2024-01-01 00:00:00",
            pair_state="synchronized",
        )
        watcher.dao.get_remote_children.return_value = [existing_pair]
        watcher.dao.is_filter.return_value = False

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.update_remote_state.assert_called()
        watcher.dao.force_remote.assert_not_called()

    def test_content_change_forces_remote(self):
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        child_node = MagicMock()
        remote.client.nodes.iter_children.return_value = [child_node]
        child_info = _make_remote_info(
            uid="child-1",
            name="Doc.txt",
            folderish=False,
            last_modification_time=datetime(
                2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc
            ),
        )
        remote._node_to_remote_file_info.return_value = child_info

        existing_pair = _make_doc_pair(
            remote_ref="child-1",
            last_remote_updated="2024-01-01 00:00:00",
            pair_state="synchronized",
        )
        watcher.dao.get_remote_children.return_value = [existing_pair]
        watcher.dao.is_filter.return_value = False

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.force_remote.assert_called_once_with(existing_pair)

    def test_missing_children_marked_deleted(self):
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        # No remote children
        remote.client.nodes.iter_children.return_value = []

        # But DB has one child
        orphan = _make_doc_pair(remote_ref="orphan-node")
        watcher.dao.get_remote_children.return_value = [orphan]

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.delete_remote_state.assert_called_once_with(orphan)

    def test_filtered_path_skipped(self):
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        child_node = MagicMock()
        remote.client.nodes.iter_children.return_value = [child_node]
        child_info = _make_remote_info(uid="child-1", name="Filtered", folderish=True)
        remote._node_to_remote_file_info.return_value = child_info

        watcher.dao.get_remote_children.return_value = []
        watcher.dao.is_filter.return_value = True  # Path is filtered

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")

        with patch(
            "nxdrive.alfresco.engine.watcher.remote_watcher.is_top_folder_excluded",
            return_value=False,
        ):
            watcher._scan_remote_recursive(
                parent_pair, _make_remote_info(uid="parent-node")
            )

        watcher.dao.insert_remote_state.assert_not_called()


class TestHandleChanges:
    def test_first_pass_calls_scan_remote(self):
        watcher = _make_watcher()
        watcher.engine.remote = MagicMock()
        watcher.engine.queue_manager.get_overall_size.return_value = 0
        watcher.updated = MagicMock()
        watcher.initiate = MagicMock()
        watcher.empty_polls = 0
        with patch.object(watcher, "scan_remote") as mock_scan:
            with patch.object(watcher, "_scan_local_changes"):
                watcher._handle_changes(first_pass=True)
        mock_scan.assert_called_once()

    def test_subsequent_pass_calls_scan_remote(self):
        watcher = _make_watcher()
        watcher.engine.remote = MagicMock()
        watcher.engine.queue_manager.get_overall_size.return_value = 0
        watcher.updated = MagicMock()
        watcher.initiate = MagicMock()
        watcher.empty_polls = 0
        with patch.object(watcher, "scan_remote") as mock_scan:
            with patch.object(watcher, "_scan_local_changes"):
                watcher._handle_changes(first_pass=False)
        mock_scan.assert_called_once()


class TestScanLocalChanges:
    def test_calls_scan_local_recursive(self):
        watcher = _make_watcher()
        watcher.engine.local = MagicMock()
        watcher.engine.local.exists.return_value = True

        with patch.object(watcher, "_scan_local_recursive") as mock_slr:
            with patch.object(watcher, "_process_pending_deletions"):
                watcher._scan_local_changes()

        mock_slr.assert_called_once()

    def test_missing_root_returns_early(self):
        watcher = _make_watcher()
        watcher.engine.local = MagicMock()
        watcher.engine.local.exists.return_value = False
        with patch.object(watcher, "_scan_local_recursive") as mock_slr:
            watcher._scan_local_changes()
        mock_slr.assert_not_called()


class TestProcessPendingDeletions:
    def test_deletes_when_ref_not_seen(self):
        watcher = _make_watcher()
        pair = _make_doc_pair(remote_ref="node-1", local_path=PurePosixPath("/a.txt"))
        watcher._process_pending_deletions([pair], set())
        watcher.engine.delete_doc.assert_called_once_with(pair.local_path)

    def test_skips_when_ref_still_present(self):
        watcher = _make_watcher()
        pair = _make_doc_pair(remote_ref="node-1", local_path=PurePosixPath("/a.txt"))
        watcher._process_pending_deletions([pair], {"node-1"})
        watcher.engine.delete_doc.assert_not_called()

    def test_empty_list_is_noop(self):
        watcher = _make_watcher()
        watcher._process_pending_deletions([], set())
        watcher.engine.delete_doc.assert_not_called()


class TestScanLocalRecursive:
    def _setup(self):
        watcher = _make_watcher()
        local = MagicMock()
        dao = MagicMock()
        return watcher, local, dao

    def test_new_local_file_inserted(self):
        watcher, local, dao = self._setup()
        child_info = MagicMock()
        child_info.path = PurePosixPath("/root/newfile.txt")
        child_info.folderish = False
        local.get_children_info.return_value = [child_info]
        local.is_ignored.return_value = False
        local.get_remote_id.return_value = None
        dao.get_local_children.return_value = []

        seen = set()
        pending = []
        watcher._scan_local_recursive(ROOT, local, dao, seen, pending)

        dao.insert_local_state.assert_called_once()

    def test_locally_modified_file_updates_state(self):
        watcher, local, dao = self._setup()
        child_info = MagicMock()
        child_info.path = PurePosixPath("/root/existing.txt")
        child_info.folderish = False
        child_info.get_digest.return_value = "new_digest"
        local.get_children_info.return_value = [child_info]
        local.is_ignored.return_value = False
        local.get_remote_id.return_value = "remote-ref-1"

        db_pair = _make_doc_pair(
            local_name="existing.txt",
            pair_state="synchronized",
            local_digest="old_digest",
        )
        dao.get_local_children.return_value = [db_pair]

        seen = set()
        pending = []
        watcher._scan_local_recursive(ROOT, local, dao, seen, pending)

        dao.update_local_state.assert_called_once()
        assert db_pair.local_digest == "new_digest"
        assert db_pair.local_state == "modified"

    def test_deleted_file_appended_to_pending(self):
        watcher, local, dao = self._setup()
        local.get_children_info.return_value = []

        db_pair = _make_doc_pair(
            local_name="gone.txt",
            pair_state="synchronized",
            local_path=PurePosixPath("/root/gone.txt"),
        )
        dao.get_local_children.return_value = [db_pair]
        local.exists.return_value = False

        seen = set()
        pending = []
        watcher._scan_local_recursive(ROOT, local, dao, seen, pending)

        assert db_pair in pending

    def test_ignored_file_skipped(self):
        watcher, local, dao = self._setup()
        child_info = MagicMock()
        child_info.path = PurePosixPath("/root/.DS_Store")
        child_info.folderish = False
        local.get_children_info.return_value = [child_info]
        local.is_ignored.return_value = True
        dao.get_local_children.return_value = []

        seen = set()
        pending = []
        watcher._scan_local_recursive(ROOT, local, dao, seen, pending)

        dao.insert_local_state.assert_not_called()

    def test_oserror_during_listing_returns_safely(self):
        watcher, local, dao = self._setup()
        local.get_children_info.side_effect = OSError("permission denied")

        seen = set()
        pending = []
        # Should not raise
        watcher._scan_local_recursive(ROOT, local, dao, seen, pending)
