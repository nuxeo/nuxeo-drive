"""Extra unit tests for nxdrive.nuxeo.engine.watcher.remote_watcher — key methods."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.drive.exceptions import NotFound


def _make_watcher():
    from nxdrive.nuxeo.engine.watcher.remote_watcher import RemoteWatcher

    w = RemoteWatcher.__new__(RemoteWatcher)
    w.engine = MagicMock()
    w.dao = MagicMock()
    w._last_sync_date = 0
    w._last_event_log_id = 0
    w._last_root_definitions = ""
    w._last_remote_full_scan = None
    w._next_check = 0
    w._metrics = {}
    w._interact = Mock()
    w.remoteScanFinished = MagicMock()
    w.changesFound = MagicMock()
    w.noChangesFound = MagicMock()
    return w


def _mock_remote_info(**kwargs):
    info = Mock()
    defaults = dict(
        uid="uid-1",
        name="folder1",
        path="/default-domain/uid-1",
        parent_uid="parent-uid",
        folderish=True,
        digest=None,
        digest_algorithm=None,
        can_delete=True,
        can_rename=True,
        can_update=True,
        can_create_child=True,
        can_scroll_descendants=True,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(info, k, v)
    return info


def _mock_doc_pair(**kwargs):
    pair = Mock()
    defaults = dict(
        id=1,
        remote_ref="uid-1",
        remote_parent_path="/default-domain",
        local_path=Path("folder1"),
        local_parent_path=Path(""),
        remote_name="folder1",
        remote_can_delete=True,
        remote_can_rename=True,
        remote_can_update=True,
        remote_can_create_child=True,
        remote_digest=None,
        remote_parent_ref="parent-uid",
        pair_state="synchronized",
        last_error=None,
        folderish=True,
        local_digest=None,
        version=1,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(pair, k, v)
    return pair


# ---------------------------------------------------------------------------
# get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    def test_returns_metrics_dict(self):
        w = _make_watcher()
        w._last_sync_date = 12345
        w._last_event_log_id = 99
        w._last_root_definitions = "root1"
        w._last_remote_full_scan = None
        w._next_check = 42
        # Provide super().get_metrics() behavior
        with patch(
            "nxdrive.drive.engine.watcher.remote_watcher_base.RemoteWatcherBase.get_metrics",
            return_value={},
        ):
            m = w.get_metrics()
        assert m["last_remote_sync_date"] == 12345
        assert m["last_event_log_id"] == 99
        assert m["last_root_definitions"] == "root1"
        assert m["next_polling"] == 42


# ---------------------------------------------------------------------------
# _check_modified (static)
# ---------------------------------------------------------------------------


class TestCheckModified:
    def test_no_change(self):
        from nxdrive.nuxeo.engine.watcher.remote_watcher import RemoteWatcher

        pair = _mock_doc_pair()
        info = _mock_remote_info()
        assert RemoteWatcher._check_modified(pair, info) is False

    def test_name_changed(self):
        from nxdrive.nuxeo.engine.watcher.remote_watcher import RemoteWatcher

        pair = _mock_doc_pair(remote_name="old_name")
        info = _mock_remote_info(name="new_name")
        assert RemoteWatcher._check_modified(pair, info) is True

    def test_digest_changed(self):
        from nxdrive.nuxeo.engine.watcher.remote_watcher import RemoteWatcher

        pair = _mock_doc_pair(remote_digest="aaa")
        info = _mock_remote_info(digest="bbb")
        assert RemoteWatcher._check_modified(pair, info) is True

    def test_parent_changed(self):
        from nxdrive.nuxeo.engine.watcher.remote_watcher import RemoteWatcher

        pair = _mock_doc_pair(remote_parent_ref="old-parent")
        info = _mock_remote_info(parent_uid="new-parent")
        assert RemoteWatcher._check_modified(pair, info) is True


# ---------------------------------------------------------------------------
# _init_scan_remote
# ---------------------------------------------------------------------------


class TestInitScanRemote:
    def test_none_remote_info_raises(self):
        w = _make_watcher()
        pair = _mock_doc_pair()
        with pytest.raises(ValueError, match="Cannot bind"):
            w._init_scan_remote(pair, None)

    def test_non_folderish_returns_none(self):
        w = _make_watcher()
        pair = _mock_doc_pair()
        info = _mock_remote_info(folderish=False)
        result = w._init_scan_remote(pair, info)
        assert result is None

    def test_already_scanned_returns_none(self):
        w = _make_watcher()
        pair = _mock_doc_pair(remote_parent_path="/domain")
        info = _mock_remote_info(uid="uid-1", folderish=True)
        w.dao.is_path_scanned.return_value = True
        result = w._init_scan_remote(pair, info)
        assert result is None

    def test_success_returns_path(self):
        w = _make_watcher()
        pair = _mock_doc_pair(remote_parent_path="/domain", local_path=Path("f"))
        info = _mock_remote_info(uid="uid-1", folderish=True)
        w.dao.is_path_scanned.return_value = False
        result = w._init_scan_remote(pair, info)
        assert result == "/domain/uid-1"


# ---------------------------------------------------------------------------
# scan_pair
# ---------------------------------------------------------------------------


class TestScanPair:
    def test_scan_pair_adds_path(self):
        w = _make_watcher()
        w.scan_pair("/default-domain/uid-1")
        w.dao.add_path_to_scan.assert_called_once_with("/default-domain/uid-1")
        assert w._next_check == 0


# ---------------------------------------------------------------------------
# _scan_pair
# ---------------------------------------------------------------------------


class TestInternalScanPair:
    def test_none_remote_path_returns(self):
        w = _make_watcher()
        w._scan_pair(None)
        # Should not crash

    def test_filtered_path_returns(self):
        w = _make_watcher()
        w.dao.is_filter.return_value = True
        w._scan_pair("/domain/uid-1")
        w.engine.remote.get_fs_info.assert_not_called()

    def test_not_found_returns(self):
        w = _make_watcher()
        w.dao.is_filter.return_value = False
        w.engine.remote.get_fs_info.side_effect = NotFound("gone")
        w._scan_pair("/domain/uid-1")
        # Should not crash

    def test_existing_pair_calls_do_scan(self):
        w = _make_watcher()
        w.dao.is_filter.return_value = False
        child_info = _mock_remote_info()
        w.engine.remote.get_fs_info.return_value = child_info
        existing_pair = _mock_doc_pair()
        w.dao.get_state_from_remote_with_path.return_value = existing_pair
        w._do_scan_remote = Mock()
        w._scan_pair("/domain/uid-1")
        w._do_scan_remote.assert_called_once_with(existing_pair, child_info)


# ---------------------------------------------------------------------------
# _find_remote_child_match_or_create
# ---------------------------------------------------------------------------


class TestFindRemoteChildMatchOrCreate:
    def test_parent_dedup_error_returns_none(self):
        w = _make_watcher()
        parent = _mock_doc_pair(last_error="DEDUP")
        child_info = _mock_remote_info()
        result = w._find_remote_child_match_or_create(parent, child_info)
        assert result is None

    def test_already_exists_in_db_returns_none(self):
        w = _make_watcher()
        parent = _mock_doc_pair(last_error=None)
        child_info = _mock_remote_info(uid="existing-uid")
        w.dao.get_normal_state_from_remote.return_value = Mock()  # exists
        result = w._find_remote_child_match_or_create(parent, child_info)
        assert result is None


# ---------------------------------------------------------------------------
# _do_scan_remote routing
# ---------------------------------------------------------------------------


class TestDoScanRemote:
    def test_scroll_capable_uses_scroll(self):
        w = _make_watcher()
        pair = _mock_doc_pair()
        info = _mock_remote_info(can_scroll_descendants=True)
        w._scan_remote_scroll = Mock()
        w._scan_remote_recursive = Mock()
        w._do_scan_remote(pair, info)
        w._scan_remote_scroll.assert_called_once()
        w._scan_remote_recursive.assert_not_called()

    def test_no_scroll_uses_recursive(self):
        w = _make_watcher()
        pair = _mock_doc_pair()
        info = _mock_remote_info(can_scroll_descendants=False)
        w._scan_remote_scroll = Mock()
        w._scan_remote_recursive = Mock()
        w._do_scan_remote(pair, info)
        w._scan_remote_recursive.assert_called_once()
        w._scan_remote_scroll.assert_not_called()


# ---------------------------------------------------------------------------
# scan_remote
# ---------------------------------------------------------------------------


class TestScanRemote:
    def test_no_from_state_returns(self):
        w = _make_watcher()
        w.dao.get_state_from_local.return_value = None
        w._get_changes = Mock()
        w.scan_remote()
        w._get_changes.assert_not_called()

    def test_not_found_returns(self):
        w = _make_watcher()
        state = _mock_doc_pair()
        w.dao.get_state_from_local.return_value = state
        w.engine.remote.get_fs_info.side_effect = NotFound("gone")
        w.scan_remote()
        # Should not crash, no _get_changes called

    def test_success_calls_do_scan(self):
        w = _make_watcher()
        state = _mock_doc_pair()
        w.dao.get_state_from_local.return_value = state
        remote_info = _mock_remote_info()
        w.engine.remote.get_fs_info.return_value = remote_info
        w.dao.update_remote_state.return_value = False
        w._get_changes = Mock()
        w._do_scan_remote = Mock()
        w.dao.clean_scanned = Mock()
        w.dao.update_config = Mock()
        w.remove_void_transfers = Mock()
        w.scan_remote()
        w._get_changes.assert_called_once()
        w._do_scan_remote.assert_called_once_with(state, remote_info)
