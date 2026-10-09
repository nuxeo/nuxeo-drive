"""Regression tests for the stale-state defects found in the 2026-10-08 run.

Two real failures drove these:

* ``file2.txt`` was uploaded twice and took several cycles to report as
  synced, because the uploader wrote its own out-of-date snapshot of the row
  over a decision another thread had already made.
* Remote edits to ``file2.txt`` were never downloaded, because the stored
  "server digest" still held what *we* had uploaded and nothing can ever
  replace it — Alfresco serves no content hash.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.alfresco.client.remote import AlfrescoRemote
from nxdrive.alfresco.engine.processor import LOCKED_ON_SERVER, AlfrescoProcessor
from nxdrive.alfresco.engine.watcher.remote_watcher import AlfrescoRemoteWatcher

PROCESSOR = "nxdrive.alfresco.engine.processor"

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _watcher():
    with patch.object(AlfrescoRemoteWatcher, "__init__", return_value=None):
        watcher = AlfrescoRemoteWatcher.__new__(AlfrescoRemoteWatcher)
    watcher.engine = MagicMock()
    watcher.dao = MagicMock()
    watcher._cycle_count = 0
    watcher._interact = MagicMock()
    watcher._lock_was_released = MagicMock(return_value=False)
    return watcher


def _processor():
    engine = MagicMock()
    engine.uid = "test-uid"
    engine.queue_manager.get_error_threshold.return_value = 3
    engine.download_dir = Path("/tmp/downloads")
    proc = AlfrescoProcessor(engine, MagicMock(return_value=None))
    proc.dao = engine.dao
    proc.local = engine.local
    proc.remote = engine.remote
    proc.dao.get_filters.return_value = []
    proc.dao.get_normal_state_from_remote.return_value = None
    proc._conflicting_remote_twin = MagicMock(return_value=None)
    proc.remove_void_transfers = MagicMock()

    parent = MagicMock(
        remote_ref="parent-1",
        remote_parent_path="/root",
        remote_can_create_child=True,
        remote_name="conflict",
    )
    proc.dao.get_state_from_local.return_value = parent
    proc.remote.get_fs_info.return_value = MagicMock(path="/Company Home/conflict")
    proc.remote.stream_file.return_value = MagicMock(uid="node-1", digest="abc")
    return proc


def _pair(**overrides):
    pair = MagicMock()
    pair.id = 1
    pair.version = 0
    pair.folderish = False
    pair.remote_ref = ""
    pair.local_name = "file.txt"
    pair.local_path = Path("conflict/file.txt")
    pair.local_parent_path = Path("conflict")
    pair.local_digest = "abc"
    pair.local_state = "created"
    pair.pair_state = "locally_created"
    pair.error_count = 0
    for key, value in overrides.items():
        setattr(pair, key, value)
    return pair


def _info(**overrides):
    info = MagicMock()
    info.uid = "node-1"
    info.name = "file.txt"
    info.folderish = False
    info.version_label = "1.0"
    info.is_locked = False
    info.last_modification_time = None
    for key, value in overrides.items():
        setattr(info, key, value)
    return info


# ---------------------------------------------------------------------------
# The uploader must not resurrect a state another thread has replaced
# ---------------------------------------------------------------------------


class TestCreationRaceGuard:
    def test_unchanged_row_is_synchronised_normally(self):
        proc = _processor()
        pair = _pair(version=4)
        proc.dao.get_state_from_id.return_value = _pair(
            version=4, pair_state="locally_created"
        )

        proc._synchronize_locally_created(pair)

        proc.dao.synchronize_state.assert_called_once_with(pair)

    def test_a_row_re_decided_mid_upload_is_left_alone(self):
        """This is the double upload: our snapshot said ``locally_created``."""
        proc = _processor()
        pair = _pair(version=0)
        fresh = _pair(version=2, pair_state="synchronized", local_state="synchronized")
        proc.dao.get_state_from_id.return_value = fresh

        proc._synchronize_locally_created(pair)

        # Writing the stale snapshot would have queued a second upload.
        proc.dao.synchronize_state.assert_not_called()
        assert proc.dao.update_remote_state.call_args.args[0] is fresh

    def test_the_newer_row_still_gets_the_upload_baseline(self):
        proc = _processor()
        fresh = _pair(version=2, pair_state="synchronized")
        proc.dao.get_state_from_id.return_value = fresh

        proc._synchronize_locally_created(_pair(version=0))

        kwargs = proc.dao.update_remote_state.call_args.kwargs
        assert kwargs["force_update"] is True

    def test_a_conflict_raised_mid_upload_is_not_written_over(self):
        proc = _processor()
        proc.dao.get_state_from_id.return_value = _pair(
            version=2, pair_state="conflicted"
        )

        proc._synchronize_locally_created(_pair(version=0))

        proc.dao.update_remote_state.assert_not_called()
        proc.dao.synchronize_state.assert_not_called()

    def test_a_conflict_is_honoured_even_when_the_version_did_not_move(self):
        """``_mark_conflicted`` goes through ``_force_sync``, which does not
        bump ``version`` — so the version check alone would miss it."""
        proc = _processor()
        pair = _pair(version=7)
        proc.dao.get_state_from_id.return_value = _pair(
            version=7, pair_state="conflicted"
        )

        proc._synchronize_locally_created(pair)

        proc.dao.update_remote_state.assert_not_called()
        proc.dao.synchronize_state.assert_not_called()


class TestUploadBaseline:
    def test_creation_records_the_version_it_produced(self):
        """Without ``force_update`` the DAO returns before saving it."""
        proc = _processor()
        pair = _pair(version=4)
        proc.dao.get_state_from_id.return_value = _pair(version=4)

        proc._synchronize_locally_created(pair)

        assert proc.dao.update_remote_state.call_args.kwargs["force_update"] is True

    def test_modification_records_the_version_it_produced(self):
        proc = _processor()
        pair = _pair(remote_ref="node-1", remote_can_update=True, local_digest="new")
        proc.local.is_equal_digests.return_value = False
        proc.remote.stream_update.return_value = _info()

        proc._synchronize_locally_modified(pair)

        assert proc.dao.update_remote_state.call_args.kwargs["force_update"] is True

    def test_unchanged_modification_also_refreshes_the_baseline(self):
        proc = _processor()
        pair = _pair(remote_ref="node-1", remote_can_update=True)
        proc.local.is_equal_digests.return_value = True

        proc._synchronize_locally_modified(pair)

        proc.remote.stream_update.assert_not_called()
        assert proc.dao.update_remote_state.call_args.kwargs["force_update"] is True


# ---------------------------------------------------------------------------
# A lock conflict must not be cleared without the server confirming it
# ---------------------------------------------------------------------------


class TestLockReleaseNeedsConfirmation:
    """The feed never reports lock state, so its ``is_locked=False`` default
    is indistinguishable from a real "not locked" answer."""

    @staticmethod
    def _watcher():
        watcher = _watcher()
        # The shared builder stubs this out; these tests exercise the real one.
        del watcher._lock_was_released
        return watcher

    def _parked(self):
        return _pair(pair_state="conflicted", last_error=LOCKED_ON_SERVER)

    def test_a_failed_lookup_keeps_the_conflict(self):
        watcher = self._watcher()
        watcher.engine.remote.get_node.side_effect = OSError("offline")

        assert (
            watcher._lock_was_released(self._parked(), _info(is_locked=False)) is False
        )

    def test_a_confirmed_release_clears_it(self):
        watcher = self._watcher()
        watcher.engine.remote.get_node.return_value = MagicMock(
            is_locked=False, version_label="1.1", lock_owner=None
        )

        assert watcher._lock_was_released(self._parked(), _info()) is True

    def test_a_node_still_locked_keeps_the_conflict(self):
        watcher = self._watcher()
        watcher.engine.remote.get_node.return_value = MagicMock(
            is_locked=True, version_label="1.1", lock_owner="admin"
        )

        assert watcher._lock_was_released(self._parked(), _info()) is False

    def test_the_server_is_always_asked_even_with_a_version_in_hand(self):
        """A version label says nothing about the lock."""
        watcher = self._watcher()
        watcher.engine.remote.get_node.return_value = MagicMock(
            is_locked=True, version_label="2.0", lock_owner="admin"
        )

        watcher._lock_was_released(self._parked(), _info(version_label="2.0"))

        watcher.engine.remote.get_node.assert_called_once_with("node-1")

    def test_only_lock_parked_pairs_qualify(self):
        watcher = self._watcher()
        other = _pair(pair_state="conflicted", last_error="DIFFERENT_CONTENT")

        assert watcher._lock_was_released(other, _info()) is False
        watcher.engine.remote.get_node.assert_not_called()


# ---------------------------------------------------------------------------
# Releasing a lock must not overwrite a decision the user already made
# ---------------------------------------------------------------------------


class TestLockReleaseIsConditional:
    """The re-check reads the row, calls the server, then writes it back.

    The user can resolve the conflict in that gap, and ``_force_sync`` does not
    bump ``version``, so its optimistic lock would not notice.
    """

    def test_the_release_is_guarded_by_the_lock_reason(self):
        watcher = _watcher()
        pair = _pair(pair_state="conflicted", last_error=LOCKED_ON_SERVER)

        watcher._release_lock_conflict(pair)

        watcher.dao._force_sync.assert_not_called()
        kwargs = watcher.dao.force_sync_if_conflicted.call_args.kwargs
        assert kwargs["last_error"] == LOCKED_ON_SERVER

    def test_a_row_the_user_already_resolved_is_left_alone(self):
        watcher = _watcher()
        watcher.dao.force_sync_if_conflicted.return_value = False

        watcher._release_lock_conflict(_pair(pair_state="locally_resolved"))

        watcher.dao.force_sync_if_conflicted.assert_called_once()
        watcher.dao._force_sync.assert_not_called()


# ---------------------------------------------------------------------------
# A download must not crash on the server's timestamp format
# ---------------------------------------------------------------------------


class TestDownloadKeepsTheRemoteTimestamp:
    """``change_file_date`` only parses ``YYYY-MM-DD HH:MM:SS``.

    The server hands back a timezone-aware ``datetime``; passing it straight
    through raised after the bytes had landed but before the DB caught up,
    leaving the pair to download the same file on every poll.
    """

    def _proc_for_download(self, remote_info):
        proc = _processor()
        proc.remote.get_fs_info.return_value = remote_info
        proc._download_content = MagicMock(return_value=Path("/tmp/dl/file.txt"))
        proc._refresh_local_state = MagicMock()
        proc._refresh_remote = MagicMock()
        proc.local.abspath.return_value = Path("/sync/file.txt")
        proc.local.get_remote_id.return_value = "node-1"
        proc.local.move.return_value = MagicMock(
            filepath=Path("/sync/file.txt"), get_digest=MagicMock(return_value="abc")
        )
        return proc

    def test_a_datetime_is_normalised_before_it_reaches_the_filesystem(self):
        from datetime import datetime, timezone

        stamp = datetime(2026, 10, 9, 7, 21, 51, 123456, tzinfo=timezone.utc)
        proc = self._proc_for_download(MagicMock(last_modification_time=stamp))

        proc._update_remotely(_pair(remote_name="file.txt"), False)

        assert (
            proc.local.change_file_date.call_args.kwargs["mtime"]
            == "2026-10-09 07:21:51"
        )

    def test_the_db_fallback_still_works_without_a_snapshot(self):
        proc = self._proc_for_download(None)
        proc.remote.get_fs_info.side_effect = OSError("offline")

        proc._update_remotely(
            _pair(remote_name="file.txt", last_remote_updated="2026-10-06 09:19:59"),
            False,
        )

        assert (
            proc.local.change_file_date.call_args.kwargs["mtime"]
            == "2026-10-06 09:19:59"
        )


# ---------------------------------------------------------------------------
# A digest we can no longer vouch for must not block a download
# ---------------------------------------------------------------------------


class TestStaleDigest:
    def test_a_content_change_forgets_the_stored_digest(self):
        watcher = _watcher()
        watcher._content_changed = MagicMock(return_value=True)
        pair = _pair(pair_state="synchronized", remote_state="synchronized")

        watcher._reconcile_child(pair, _info(), "/remote", Path("/sync"))

        watcher.dao.clear_remote_digest.assert_called_once_with(pair)
        watcher.dao.force_remote.assert_called_once_with(pair)

    def test_an_unchanged_node_keeps_its_digest(self):
        watcher = _watcher()
        watcher._content_changed = MagicMock(return_value=False)
        pair = _pair(pair_state="synchronized", remote_state="synchronized")

        watcher._reconcile_child(pair, _info(), "/remote", Path("/sync"))

        watcher.dao.clear_remote_digest.assert_not_called()


class TestGetFsInfoDigest:
    """``get_fs_info`` may only report a digest the server vouches for."""

    def _remote(self, node):
        remote = AlfrescoRemote.__new__(AlfrescoRemote)
        remote.get_node = MagicMock(return_value=node)
        remote.dao = MagicMock()
        return remote

    def _node(self, *, digest=None):
        node = MagicMock()
        node.name = "file.txt"
        node.id = "node-1"
        node.parent_id = "parent-1"
        node.path = None
        node.is_folder = False
        node.is_file = True
        node.modified_at = None
        node.created_at = None
        node.modified_by_user = {"id": "admin"}
        node.lock_owner = None
        node.version_label = "2.0"
        node.is_locked = False
        node.digest = digest
        node.digest_algorithm = "md5" if digest else None
        return node

    def test_a_server_digest_is_reported(self):
        remote = self._remote(self._node(digest="SERVERHASH"))
        assert remote.get_fs_info("node-1").digest == "SERVERHASH"

    def test_the_stored_digest_is_not_reported_as_the_servers(self):
        """Alfresco serves no hash; the stored one is our own upload."""
        remote = self._remote(self._node())
        remote.dao.get_normal_state_from_remote.return_value = MagicMock(
            remote_digest="OURUPLOAD"
        )

        info = remote.get_fs_info("node-1")

        assert info.digest is None
        remote.dao.get_normal_state_from_remote.assert_not_called()

    @pytest.mark.parametrize("digest", (None, "SERVERHASH"))
    def test_the_version_label_always_comes_through(self, digest):
        remote = self._remote(self._node(digest=digest))
        assert remote.get_fs_info("node-1").version_label == "2.0"


# ---------------------------------------------------------------------------
# A download must leave the baseline matching what was served
# ---------------------------------------------------------------------------


class TestRefreshRemote:
    def test_the_not_dirty_shortcut_is_skipped(self):
        """Alfresco sends no digest, so the shortcut always fires otherwise."""
        proc = _processor()

        proc._refresh_remote(_pair(remote_ref="node-1"), _info(version_label="4.0"))

        kwargs = proc.dao.update_remote_state.call_args.kwargs
        assert kwargs["force_update"] is True
        assert kwargs["versioned"] is False
        assert kwargs["queue"] is False

    def test_the_server_is_asked_when_no_info_is_supplied(self):
        proc = _processor()
        proc.remote.get_fs_info.return_value = _info(version_label="4.0")

        proc._refresh_remote(_pair(remote_ref="node-1"))

        proc.remote.get_fs_info.assert_called_once_with("node-1")


class TestDownloadBaseline:
    """A "Use remote" download can serve a newer revision than the conflict.

    The watcher leaves a conflicted row alone, so ``last_remote_updated`` still
    names the revision that raised the conflict while the bytes on disk are
    whatever the server holds now.
    """

    def _proc(self, served):
        proc = _processor()
        proc.local.abspath.return_value = Path("/sync/conflict/file.txt")
        proc._download_content = MagicMock(return_value=Path("/tmp/dl/file.txt"))
        proc.local.get_remote_id.return_value = "node-1"
        proc.local.move.return_value = MagicMock(
            filepath=Path("/sync/conflict/file.txt"),
            get_digest=MagicMock(return_value="newhash"),
        )
        proc._refresh_local_state = MagicMock()
        proc.remote.get_fs_info.return_value = served
        return proc

    def _pair(self):
        return _pair(
            remote_ref="node-1",
            remote_name="file.txt",
            last_remote_updated="2026-10-08 10:21:34",
        )

    def test_the_file_is_stamped_with_the_revision_actually_served(self):
        served = _info(last_modification_time="2026-10-08 10:23:16")
        proc = self._proc(served)

        with patch(f"{PROCESSOR}.shutil"):
            proc._update_remotely(self._pair(), False)

        assert (
            proc.local.change_file_date.call_args.kwargs["mtime"]
            == "2026-10-08 10:23:16"
        )

    def test_the_served_revision_becomes_the_new_baseline(self):
        """Otherwise the next local edit sees drift and raises a false conflict."""
        served = _info(version_label="4.0")
        proc = self._proc(served)

        with patch(f"{PROCESSOR}.shutil"):
            proc._update_remotely(self._pair(), False)

        assert proc.dao.update_remote_state.call_args.args[1] is served
        assert proc.dao.update_remote_state.call_args.kwargs["force_update"] is True

    def test_the_server_is_asked_only_once(self):
        proc = self._proc(_info(version_label="4.0"))

        with patch(f"{PROCESSOR}.shutil"):
            proc._update_remotely(self._pair(), False)

        proc.remote.get_fs_info.assert_called_once_with("node-1")

    def test_the_revision_is_read_before_the_bytes_are_fetched(self):
        """A revision landing mid-download must not become the baseline.

        If it did, the next poll would compare the stored version against that
        same revision, see no change, and never fetch the bytes we skipped.
        """
        order = []
        proc = self._proc(_info(version_label="4.0"))
        proc.remote.get_fs_info.side_effect = lambda *a: (
            order.append("read-revision") or _info(version_label="4.0")
        )
        proc._download_content.side_effect = lambda *a: (
            order.append("download") or Path("/tmp/dl/file.txt")
        )

        with patch(f"{PROCESSOR}.shutil"):
            proc._update_remotely(self._pair(), False)

        assert order == ["read-revision", "download"]

    def test_an_unreachable_server_falls_back_to_the_stored_timestamp(self):
        proc = self._proc(None)
        proc.remote.get_fs_info.side_effect = OSError("boom")

        with patch(f"{PROCESSOR}.shutil"):
            proc._update_remotely(self._pair(), False)

        assert (
            proc.local.change_file_date.call_args.kwargs["mtime"]
            == "2026-10-08 10:21:34"
        )
        proc.dao.update_remote_state.assert_not_called()

    def test_a_failed_pre_read_never_falls_back_to_a_post_read(self):
        """Fetching after the transfer is what the pre-read exists to avoid.

        A revision landing mid-download would be saved as the baseline while
        the bytes on disk are the older one, and the next poll would compare
        equal and never fetch it. Leaving the old baseline alone makes that
        poll see a difference and download again.
        """
        proc = self._proc(None)
        proc.remote.get_fs_info.side_effect = OSError("boom")

        with patch(f"{PROCESSOR}.shutil"):
            proc._update_remotely(self._pair(), False)

        proc.remote.get_fs_info.assert_called_once_with("node-1")
        proc.dao.update_remote_state.assert_not_called()
