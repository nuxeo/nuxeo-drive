"""Unit tests for nxdrive.alfresco.engine.watcher.remote_watcher."""

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from unittest.mock import MagicMock, patch

import pytest
from alfresco.exceptions import AuthenticationError as AlfrescoAuthError
from alfresco.exceptions import NetworkError as AlfrescoNetworkError

from nxdrive.alfresco.client.device_sync import CONF_BOOTSTRAPPED_FOR
from nxdrive.alfresco.engine.watcher.remote_watcher import (
    LOCAL_SCAN_CHUNK,
    AlfrescoRemoteWatcher,
)
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
    dao.get_state_from_local.return_value = None
    dao.get_normal_state_from_remote.return_value = None
    # Nothing has been checkpointed yet, otherwise every folder looks scanned.
    dao.is_path_scanned.return_value = False
    dao.get_paths_to_scan.return_value = []

    with patch.object(AlfrescoRemoteWatcher, "__init__", lambda self, *a, **kw: None):
        w = AlfrescoRemoteWatcher(engine, dao)

    w.engine = engine
    w.dao = dao
    w._last_remote_full_scan = None
    w._next_check = 0
    w._interact = MagicMock()
    w.remoteScanFinished = MagicMock()
    w.remoteWatcherStopped = MagicMock()

    # Device Sync state, as it looks once a subscription is live.
    w._provisioner = MagicMock(
        provisioned=True,
        subscriber_id="subscriber-1",
        subscription_id="subscription-1",
        client_version="1.0.3",
    )
    w._root_node_id = "root-id"
    w._unfiltered_nodes = set()
    w._unfiltered_needs_scan = False
    w._change_failures = {}
    w._local_scan_dirs = []
    w._local_scan_seen = set()
    w._local_scan_deletions = []
    w.first_pass_done = False
    return w


def _polling_watcher():
    """A watcher whose poll cycle is stubbed out, for _handle_changes tests."""
    w = _make_watcher()
    w.engine.remote = MagicMock()
    w.engine.queue_manager.get_overall_size.return_value = 0
    w.updated = MagicMock()
    w.initiate = MagicMock()
    w.empty_polls = 0
    w._bootstrap_if_needed = MagicMock()
    w._apply_unfiltered = MagicMock()
    w._poll_device_sync = MagicMock()
    w._scan_local_changes = MagicMock()
    return w


def _make_doc_pair(**kwargs):
    """Create a minimal DocPair mock."""
    pair = MagicMock()
    pair.remote_ref = kwargs.get("remote_ref", "node-id-123")
    pair.remote_parent_path = kwargs.get("remote_parent_path", "")
    pair.local_path = kwargs.get("local_path", ROOT)
    pair.local_name = kwargs.get("local_name", "folder")
    pair.local_state = kwargs.get("local_state", "synchronized")
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

    def test_unlinked_local_pair_is_adopted_not_duplicated(self):
        """A locally created, not-yet-uploaded pair must be linked, not cloned.

        Inserting a second row for the same ``local_path`` makes both rows
        race on UNIQUE(remote_ref, local_path) and loop forever.
        """
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        remote.client.nodes.iter_children.return_value = [MagicMock()]
        child_info = _make_remote_info(uid="child-1", name="Doc.txt", folderish=False)
        remote._node_to_remote_file_info.return_value = child_info

        watcher.dao.get_remote_children.return_value = []
        watcher.dao.is_filter.return_value = False
        unlinked = _make_doc_pair(
            remote_ref="",
            local_state="created",
            pair_state="locally_created",
            local_path=ROOT / "Doc.txt",
        )
        watcher.dao.get_state_from_local.return_value = unlinked

        parent_pair = _make_doc_pair(
            remote_ref="parent-node", remote_parent_path="", local_path=ROOT
        )
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.insert_remote_state.assert_not_called()
        watcher.dao.update_remote_state.assert_called_once()
        assert watcher.dao.update_remote_state.call_args[0][0] is unlinked

    def test_unlinked_local_creation_is_marked_conflicted(self):
        """Same name created on both sides must surface as a conflict.

        The version must be bumped so an in-flight processor cannot undo
        it through ``synchronize_state``'s optimistic lock.
        """
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        remote.client.nodes.iter_children.return_value = [MagicMock()]
        child_info = _make_remote_info(uid="child-1", name="Doc.txt", folderish=False)
        remote._node_to_remote_file_info.return_value = child_info

        watcher.dao.get_remote_children.return_value = []
        watcher.dao.is_filter.return_value = False
        unlinked = _make_doc_pair(
            remote_ref="",
            local_state="created",
            pair_state="locally_created",
            local_path=ROOT / "Doc.txt",
        )
        watcher.dao.get_state_from_local.return_value = unlinked

        parent_pair = _make_doc_pair(
            remote_ref="parent-node", remote_parent_path="", local_path=ROOT
        )
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        assert unlinked.remote_state == "created"
        assert watcher.dao.update_remote_state.call_args[1]["versioned"] is True
        # Claiming the node would make the processor treat it as its own
        # interrupted upload and overwrite the remote.
        watcher.engine.local.set_remote_id.assert_not_called()

    def test_already_synced_pair_is_linked_without_conflict(self):
        """An unlinked pair that is not a local creation just gets linked."""
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        remote.client.nodes.iter_children.return_value = [MagicMock()]
        child_info = _make_remote_info(uid="child-1", name="Doc.txt", folderish=False)
        remote._node_to_remote_file_info.return_value = child_info

        watcher.dao.get_remote_children.return_value = []
        watcher.dao.is_filter.return_value = False
        existing = _make_doc_pair(
            remote_ref="",
            local_state="synchronized",
            local_path=ROOT / "Doc.txt",
        )
        watcher.dao.get_state_from_local.return_value = existing

        parent_pair = _make_doc_pair(
            remote_ref="parent-node", remote_parent_path="", local_path=ROOT
        )
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        assert existing.remote_state != "created"
        assert watcher.dao.update_remote_state.call_args[1]["versioned"] is False
        watcher.engine.local.set_remote_id.assert_called_once_with(
            ROOT / "Doc.txt", "child-1"
        )

    def test_already_conflicted_pair_is_left_untouched(self):
        """A pair awaiting user arbitration must not be re-linked.

        Refreshing ``last_remote_updated`` would make the engine's
        freshness check see an unchanged remote and auto-resolve it.
        """
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        remote.client.nodes.iter_children.return_value = [MagicMock()]
        child_info = _make_remote_info(uid="child-1", name="Doc.txt", folderish=False)
        remote._node_to_remote_file_info.return_value = child_info

        watcher.dao.get_remote_children.return_value = []
        watcher.dao.is_filter.return_value = False
        # ``_mark_conflicted`` leaves the pair modified/modified, not created.
        conflicted = _make_doc_pair(
            remote_ref="",
            local_state="modified",
            pair_state="conflicted",
            local_path=ROOT / "Doc.txt",
        )
        watcher.dao.get_state_from_local.return_value = conflicted

        parent_pair = _make_doc_pair(
            remote_ref="parent-node", remote_parent_path="", local_path=ROOT
        )
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.update_remote_state.assert_not_called()
        watcher.dao.insert_remote_state.assert_not_called()
        watcher.engine.local.set_remote_id.assert_not_called()

    def test_known_conflicted_child_is_not_refreshed(self):
        """Same guard for a child already linked in the DB."""
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        remote.client.nodes.iter_children.return_value = [MagicMock()]
        child_info = _make_remote_info(
            uid="child-1",
            name="Doc.txt",
            folderish=False,
            last_modification_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        remote._node_to_remote_file_info.return_value = child_info

        conflicted = _make_doc_pair(
            remote_ref="child-1",
            pair_state="conflicted",
            last_remote_updated="2024-01-01 00:00:00",
        )
        watcher.dao.get_remote_children.return_value = [conflicted]
        watcher.dao.is_filter.return_value = False

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.update_remote_state.assert_not_called()

    def test_remote_ref_already_known_is_skipped(self):
        """Illegal state: the same remote ref cannot be created twice."""
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        remote.client.nodes.iter_children.return_value = [MagicMock()]
        child_info = _make_remote_info(uid="child-1", name="Doc.txt", folderish=False)
        remote._node_to_remote_file_info.return_value = child_info

        watcher.dao.get_remote_children.return_value = []
        watcher.dao.is_filter.return_value = False
        watcher.dao.get_normal_state_from_remote.return_value = _make_doc_pair(
            remote_ref="child-1"
        )

        parent_pair = _make_doc_pair(
            remote_ref="parent-node", remote_parent_path="", local_path=ROOT
        )
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.insert_remote_state.assert_not_called()
        watcher.dao.update_remote_state.assert_not_called()

    def test_local_pair_with_other_remote_ref_is_left_alone(self):
        """A same-path pair already bound to another node must not be relinked."""
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        remote.client.nodes.iter_children.return_value = [MagicMock()]
        child_info = _make_remote_info(uid="child-1", name="Doc.txt", folderish=False)
        remote._node_to_remote_file_info.return_value = child_info

        watcher.dao.get_remote_children.return_value = []
        watcher.dao.is_filter.return_value = False
        watcher.dao.get_state_from_local.return_value = _make_doc_pair(
            remote_ref="some-other-node", local_path=ROOT / "Doc.txt"
        )

        parent_pair = _make_doc_pair(
            remote_ref="parent-node", remote_parent_path="", local_path=ROOT
        )
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.insert_remote_state.assert_not_called()
        watcher.dao.update_remote_state.assert_not_called()

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

    @pytest.mark.parametrize("pair_state", ["locally_created", "locally_modified"])
    def test_missing_active_upload_is_not_marked_deleted(self, pair_state):
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote
        remote.client.nodes.iter_children.return_value = []

        active_pair = _make_doc_pair(
            remote_ref="pending-node",
            local_name="uploading.bin",
            pair_state=pair_state,
        )
        watcher.dao.get_remote_children.return_value = [active_pair]

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.delete_remote_state.assert_not_called()

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
    def test_first_pass_polls_device_sync(self):
        watcher = _polling_watcher()
        watcher._handle_changes(first_pass=True)
        watcher._poll_device_sync.assert_called_once()

    def test_subsequent_pass_polls_device_sync(self):
        watcher = _polling_watcher()
        watcher._handle_changes(first_pass=False)
        watcher._poll_device_sync.assert_called_once()

    def test_poll_seeds_then_widens_then_drains(self):
        """The delta is only trusted once seeding and un-filtering have run."""
        watcher = _polling_watcher()
        order = []
        watcher._bootstrap_if_needed.side_effect = lambda: order.append("bootstrap")
        watcher._apply_unfiltered.side_effect = lambda: order.append("unfiltered")
        watcher._poll_device_sync.side_effect = lambda: order.append("poll")

        watcher._handle_changes(first_pass=True)

        assert order == ["bootstrap", "unfiltered", "poll"]


class TestScanLocalChanges:
    def test_scans_the_root(self):
        watcher = _make_watcher()
        watcher.engine.local = MagicMock()
        watcher.engine.local.exists.return_value = True

        with patch.object(watcher, "_scan_local_directory", return_value=0) as mock_dir:
            with patch.object(watcher, "_process_pending_deletions"):
                watcher._scan_local_changes()

        mock_dir.assert_called_once()

    def test_missing_root_returns_early(self):
        watcher = _make_watcher()
        watcher.engine.local = MagicMock()
        watcher.engine.local.exists.return_value = False
        with patch.object(watcher, "_scan_local_directory") as mock_dir:
            watcher._scan_local_changes()
        mock_dir.assert_not_called()

    def test_chunk_budget_pauses_the_sweep(self):
        """A big workspace must not monopolise the watcher thread."""
        watcher = _make_watcher()
        watcher.engine.local = MagicMock()
        watcher.engine.local.exists.return_value = True
        # Every directory yields a full chunk and queues one more folder.
        watcher._local_scan_dirs = []

        def _fake_dir(path, local, dao, /):
            watcher._local_scan_dirs.append(PurePosixPath(f"/sub{len(path.parts)}"))
            return LOCAL_SCAN_CHUNK

        with patch.object(watcher, "_scan_local_directory", side_effect=_fake_dir):
            with patch.object(watcher, "_process_pending_deletions") as mock_del:
                watcher._scan_local_changes()

        # Paused mid-sweep: deletions must wait for a complete walk.
        assert watcher._local_scan_dirs
        mock_del.assert_not_called()

    def test_deletions_only_run_on_a_complete_sweep(self):
        watcher = _make_watcher()
        watcher.engine.local = MagicMock()
        watcher.engine.local.exists.return_value = True

        with patch.object(watcher, "_scan_local_directory", return_value=1):
            with patch.object(watcher, "_process_pending_deletions") as mock_del:
                watcher._scan_local_changes()

        mock_del.assert_called_once()
        assert watcher._local_scan_dirs == []


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


class TestScanLocalDirectory:
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

        watcher._scan_local_directory(ROOT, local, dao)

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

        watcher._scan_local_directory(ROOT, local, dao)

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

        watcher._scan_local_directory(ROOT, local, dao)

        assert db_pair in watcher._local_scan_deletions

    def test_subfolder_is_queued_not_recursed(self):
        """Sub-folders are deferred to the queue so the budget can apply."""
        watcher, local, dao = self._setup()
        child_info = MagicMock()
        child_info.path = PurePosixPath("/root/sub")
        child_info.folderish = True
        local.get_children_info.return_value = [child_info]
        local.is_ignored.return_value = False
        local.get_remote_id.return_value = None
        dao.get_local_children.return_value = []

        watcher._scan_local_directory(ROOT, local, dao)

        assert watcher._local_scan_dirs == [child_info.path]

    def test_ignored_file_skipped(self):
        watcher, local, dao = self._setup()
        child_info = MagicMock()
        child_info.path = PurePosixPath("/root/.DS_Store")
        child_info.folderish = False
        local.get_children_info.return_value = [child_info]
        local.is_ignored.return_value = True
        dao.get_local_children.return_value = []

        watcher._scan_local_directory(ROOT, local, dao)

        dao.insert_local_state.assert_not_called()

    def test_oserror_during_listing_returns_safely(self):
        watcher, local, dao = self._setup()
        local.get_children_info.side_effect = OSError("permission denied")

        # Should not raise, and contributes nothing to the budget.
        assert watcher._scan_local_directory(ROOT, local, dao) == 0


# --- NEW TESTS BELOW ---


class TestHandleChangesExtended:
    """Additional _handle_changes coverage."""

    def test_first_pass_emits_initiate(self):
        watcher = _polling_watcher()
        watcher._handle_changes(first_pass=True)
        watcher.initiate.emit.assert_called_once()
        watcher.updated.emit.assert_not_called()

    def test_subsequent_pass_emits_updated(self):
        watcher = _polling_watcher()
        watcher._handle_changes(first_pass=False)
        watcher.updated.emit.assert_called_once()
        watcher.initiate.emit.assert_not_called()

    def test_auth_error_sets_invalid_credentials(self):
        watcher = _polling_watcher()
        watcher._poll_device_sync.side_effect = AlfrescoAuthError("expired")

        watcher._handle_changes(first_pass=True)

        watcher.engine.set_invalid_credentials.assert_called_once()
        # Once from the failure path, once from _notify_pass_done.
        watcher.updated.emit.assert_called_once()
        watcher.initiate.emit.assert_called_once()

    def test_scan_error_does_not_set_invalid_credentials(self):
        watcher = _polling_watcher()
        watcher._poll_device_sync.side_effect = RuntimeError("unexpected")

        watcher._handle_changes(first_pass=False)

        watcher.engine.set_invalid_credentials.assert_not_called()
        # Failure path plus _notify_pass_done both emit on a later pass.
        assert watcher.updated.emit.call_count == 2

    def test_poll_failure_starts_processors_but_holds_local_creations(self):
        """Two separate concerns: workers must start, the seed must not count.

        ``initiate`` wires up the queue manager, so skipping it strands the
        engine with no workers. ``first_pass_done`` gates local creations, so
        setting it before the remote view is complete duplicates documents
        created server-side while Drive was stopped.
        """
        watcher = _polling_watcher()
        watcher.first_pass_done = False
        watcher._poll_device_sync.side_effect = RuntimeError("unexpected")

        watcher._handle_changes(first_pass=True)

        watcher.initiate.emit.assert_called_once()
        assert watcher.first_pass_done is False

    def test_successful_first_pass_marks_it_done(self):
        watcher = _polling_watcher()
        watcher.first_pass_done = False

        watcher._handle_changes(first_pass=True)

        assert watcher.first_pass_done is True
        watcher.initiate.emit.assert_called_once()

    def test_failed_first_pass_is_retried_as_a_first_pass(self):
        """Otherwise local creations stay blocked for the whole session."""
        watcher = _polling_watcher()
        watcher.first_pass_done = False
        watcher._poll_device_sync.side_effect = [RuntimeError("boom"), None]

        watcher._handle_changes(not watcher.first_pass_done)
        assert watcher.first_pass_done is False

        # The next cycle asks the same question and gets "still the first".
        watcher._handle_changes(not watcher.first_pass_done)
        assert watcher.first_pass_done is True

    def test_no_remote_returns_early(self):
        watcher = _polling_watcher()
        watcher.engine.remote = None

        watcher._handle_changes(first_pass=False)

        watcher._poll_device_sync.assert_not_called()

    def test_queue_size_increase_resets_empty_polls(self):
        watcher = _polling_watcher()
        watcher.engine.queue_manager.get_overall_size.side_effect = [0, 5]
        watcher.empty_polls = 10
        watcher._handle_changes(first_pass=False)
        assert watcher.empty_polls == 0

    def test_no_new_work_increments_empty_polls(self):
        watcher = _polling_watcher()
        watcher.empty_polls = 3
        watcher._handle_changes(first_pass=False)
        assert watcher.empty_polls == 4

    def test_rescan_requested(self):
        watcher = _polling_watcher()
        # An on-demand re-scan clears the seeding marker so the tree is walked
        # again; the subscription itself stays valid.
        watcher.dao.get_config.side_effect = lambda key: (
            "true" if key == "remote_need_full_scan" else None
        )

        watcher._handle_changes(first_pass=False)

        watcher.dao.update_config.assert_any_call("remote_need_full_scan", None)
        watcher.dao.update_config.assert_any_call(CONF_BOOTSTRAPPED_FOR, None)


class TestScanRemoteRecursiveExtended:
    """Additional _scan_remote_recursive coverage."""

    def test_conflicted_pair_skipped(self):
        """Conflicted pairs should not be updated via force_remote."""
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        child_node = MagicMock()
        remote.client.nodes.iter_children.return_value = [child_node]
        child_info = _make_remote_info(
            uid="child-1",
            name="Doc.txt",
            folderish=False,
            last_modification_time=datetime(2024, 6, 15, tzinfo=timezone.utc),
        )
        remote._node_to_remote_file_info.return_value = child_info

        existing_pair = _make_doc_pair(
            remote_ref="child-1",
            last_remote_updated="2024-01-01 00:00:00",
            pair_state="conflicted",
        )
        watcher.dao.get_remote_children.return_value = [existing_pair]
        watcher.dao.is_filter.return_value = False

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        # Should NOT call force_remote or update_remote_state for conflicted
        watcher.dao.force_remote.assert_not_called()
        watcher.dao.update_remote_state.assert_not_called()

    def test_locally_created_pair_skipped_for_force(self):
        """locally_created pairs should update state but not force_remote."""
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        child_node = MagicMock()
        remote.client.nodes.iter_children.return_value = [child_node]
        child_info = _make_remote_info(
            uid="child-1",
            name="Doc.txt",
            folderish=False,
            last_modification_time=datetime(2024, 6, 15, tzinfo=timezone.utc),
        )
        remote._node_to_remote_file_info.return_value = child_info

        existing_pair = _make_doc_pair(
            remote_ref="child-1",
            last_remote_updated="2024-01-01 00:00:00",
            pair_state="locally_created",
        )
        watcher.dao.get_remote_children.return_value = [existing_pair]
        watcher.dao.is_filter.return_value = False

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.update_remote_state.assert_called_once()
        watcher.dao.force_remote.assert_not_called()

    def test_locally_modified_pair_skipped_for_force(self):
        """locally_modified pairs should update state but not force_remote."""
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        child_node = MagicMock()
        remote.client.nodes.iter_children.return_value = [child_node]
        child_info = _make_remote_info(
            uid="child-1",
            name="Doc.txt",
            folderish=False,
            last_modification_time=datetime(2024, 6, 15, tzinfo=timezone.utc),
        )
        remote._node_to_remote_file_info.return_value = child_info

        existing_pair = _make_doc_pair(
            remote_ref="child-1",
            last_remote_updated="2024-01-01 00:00:00",
            pair_state="locally_modified",
        )
        watcher.dao.get_remote_children.return_value = [existing_pair]
        watcher.dao.is_filter.return_value = False

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.update_remote_state.assert_called_once()
        watcher.dao.force_remote.assert_not_called()

    def test_new_folder_recurses(self):
        """Newly inserted folderish items should be recursed into."""
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        child_node = MagicMock()
        remote.client.nodes.iter_children.return_value = [child_node]
        child_info = _make_remote_info(uid="child-folder", name="Sub", folderish=True)
        remote._node_to_remote_file_info.return_value = child_info

        watcher.dao.get_remote_children.return_value = []
        watcher.dao.is_filter.return_value = False
        watcher.dao.insert_remote_state.return_value = 42
        child_pair_from_db = _make_doc_pair(remote_ref="child-folder")
        watcher.dao.get_state_from_id.return_value = child_pair_from_db

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")

        # Mock to prevent infinite recursion on the recursive call
        with patch.object(
            watcher,
            "_scan_remote_recursive",
            wraps=lambda p, i: (
                None
                if p is child_pair_from_db
                else AlfrescoRemoteWatcher._scan_remote_recursive(watcher, p, i)
            ),
        ):
            watcher._scan_remote_recursive(
                parent_pair, _make_remote_info(uid="parent-node")
            )

    def test_system_folder_excluded(self):
        """Alfresco system folders should be skipped."""
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        child_node = MagicMock()
        remote.client.nodes.iter_children.return_value = [child_node]
        child_info = _make_remote_info(
            uid="child-1",
            name="Data Dictionary",
            folderish=True,
            path="/Company Home/Data Dictionary",
        )
        remote._node_to_remote_file_info.return_value = child_info

        watcher.dao.get_remote_children.return_value = []

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")

        # is_top_folder_excluded should return True for Data Dictionary
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )

        watcher.dao.insert_remote_state.assert_not_called()

    def test_iter_children_error_returns_early(self):
        """Error listing children should be handled gracefully."""
        watcher = _make_watcher()
        remote = MagicMock()
        watcher.engine.remote = remote

        remote.client.nodes.iter_children.side_effect = RuntimeError("network")
        watcher.dao.get_remote_children.return_value = []

        parent_pair = _make_doc_pair(remote_ref="parent-node", remote_parent_path="")
        # Should not raise
        watcher._scan_remote_recursive(
            parent_pair, _make_remote_info(uid="parent-node")
        )
        watcher.dao.insert_remote_state.assert_not_called()
        watcher.dao.delete_remote_state.assert_not_called()


class TestScanPairResetsNextCheck:
    """scan_pair resets _next_check so the next poll happens sooner."""

    def test_scan_remote_updates_next_check(self):
        watcher = _make_watcher()
        remote = MagicMock()
        root_info = _make_remote_info(uid="root-node", folderish=True)
        remote._node_to_remote_file_info.return_value = root_info
        remote.get_node.return_value = MagicMock()
        watcher.engine.remote = remote
        watcher.engine.download_dir = PurePosixPath("/")

        root_pair = _make_doc_pair(remote_ref="root-node")
        watcher.dao.get_state_from_local.return_value = root_pair
        watcher._next_check = 999999

        with patch.object(watcher, "_scan_remote_recursive"):
            watcher.scan_remote()

        # _next_check is not directly reset by scan_remote, but
        # _last_remote_full_scan should be updated
        assert watcher._last_remote_full_scan is not None


class TestExecuteLoop:
    """Tests for _execute loop with ThreadInterrupt."""

    def test_thread_interrupt_emits_stopped_and_reraises(self):
        from nxdrive.drive.exceptions import ThreadInterrupt

        watcher = _make_watcher()
        watcher._next_check = 0
        watcher.updated = MagicMock()
        watcher.initiate = MagicMock()

        call_count = 0

        def handle_changes_side_effect(first_pass):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise ThreadInterrupt()

        with patch.object(
            watcher, "_handle_changes", side_effect=handle_changes_side_effect
        ):
            with pytest.raises(ThreadInterrupt):
                watcher._execute()

        watcher.remoteWatcherStopped.emit.assert_called_once()


class TestMatchOrCreateChild:
    """Same name on both sides: documents conflict, folders merge.

    A folder conflict is not actionable -- "keep local" or "keep remote"
    cannot be answered without discarding the folder's children -- and the
    processor already adopts a same-named remote folder, so flagging one here
    only makes the conflict count depend on which side wins the race.
    """

    @staticmethod
    def _unlinked_local_pair():
        return MagicMock(id=7, remote_ref="", local_state="created")

    @staticmethod
    def _remote(folderish):
        return MagicMock(
            uid="remote-id", name="nested", folderish=folderish, parent_uid="p"
        )

    def _link(self, folderish):
        watcher = _make_watcher()
        existing = self._unlinked_local_pair()
        watcher.dao.get_state_from_local.return_value = existing
        watcher.dao.get_normal_state_from_remote.return_value = None

        watcher._match_or_create_child(
            self._remote(folderish),
            Path("conflicts/nested"),
            Path("conflicts"),
            "/Company Home/conflicts",
        )
        return watcher, existing

    def test_a_folder_is_linked_not_conflicted(self):
        watcher, existing = self._link(folderish=True)

        assert existing.remote_state != "created"
        assert watcher.dao.update_remote_state.call_args.kwargs["versioned"] is False

    def test_a_document_still_conflicts(self):
        watcher, existing = self._link(folderish=False)

        assert existing.remote_state == "created"
        assert watcher.dao.update_remote_state.call_args.kwargs["versioned"] is True

    def test_a_merged_folder_claims_the_remote_id(self):
        """Only a conflict must leave the xattr alone."""
        watcher, _ = self._link(folderish=True)

        watcher.engine.local.set_remote_id.assert_called_once()

    def test_a_conflicting_document_does_not_claim_the_remote_id(self):
        watcher, _ = self._link(folderish=False)

        watcher.engine.local.set_remote_id.assert_not_called()


class TestNewFolderPriority:
    """A newly found folder is swept before the rest of the backlog.

    The sweep only examines LOCAL_SCAN_CHUNK entries per cycle, so appending
    a new folder holds its contents back until the whole tree has been walked
    -- minutes on a large workspace, which is what QA saw as a slow upload.
    """

    @staticmethod
    def _child(path, folderish=True):
        info = MagicMock()
        info.path = PurePosixPath(path)
        info.folderish = folderish
        return info

    def _scan(self, *, known):
        watcher = _make_watcher()
        local = MagicMock()
        dao = MagicMock()
        local.get_children_info.return_value = [self._child("/root/fresh")]
        local.is_ignored.return_value = False
        local.get_remote_id.return_value = None
        if known:
            pair = MagicMock(local_name="fresh", pair_state="synchronized", processor=0)
            dao.get_local_children.return_value = [pair]
        else:
            dao.get_local_children.return_value = []

        watcher._local_scan_dirs = [PurePosixPath("/root/backlog")]
        watcher._scan_local_directory(ROOT, local, dao)
        return watcher._local_scan_dirs

    def test_a_new_folder_is_scanned_before_the_backlog(self):
        assert self._scan(known=False)[0] == PurePosixPath("/root/fresh")

    def test_an_already_known_folder_waits_its_turn(self):
        assert self._scan(known=True)[-1] == PurePosixPath("/root/fresh")
