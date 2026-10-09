"""Regression tests for the review findings on PR #6489 (NXDRIVE-3287).

Each test pins one decision that, when it went the other way, silently
discarded a user edit:

* **Fix 1** — ``conflict_resolver`` must not auto-resolve a pair it has no
  baseline to judge, and must never touch a conflict the engine raised
  deliberately.
* **Fix 2** — the version label decides before the second-truncated
  timestamp, and a pair with neither falls back to comparing bytes.
* **Fix 3** — a pair the processor owns keeps its sync baseline.
* **Bound** — a file held open locally defers a limited number of times and
  then becomes a conflict.
* **Sweep** — parked lock conflicts are re-checked on odd cycles only.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.alfresco.content_compare import PARTIAL_COMPARE_ATTEMPTS, content_matches
from nxdrive.alfresco.engine.engine import AlfrescoEngine
from nxdrive.alfresco.engine.processor import (
    FILE_OPEN_LOCALLY,
    LOCKED_ON_SERVER,
    MAX_OPEN_FILE_DEFERRALS,
    AlfrescoProcessor,
)
from nxdrive.alfresco.engine.watcher.remote_watcher import AlfrescoRemoteWatcher

CONTENT_COMPARE = "nxdrive.alfresco.content_compare"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _engine():
    """An AlfrescoEngine with every collaborator mocked out."""
    with patch.object(AlfrescoEngine, "__init__", return_value=None):
        engine = AlfrescoEngine.__new__(AlfrescoEngine)
    engine.dao = MagicMock()
    engine.remote = MagicMock()
    engine.local = MagicMock()
    engine.manager = MagicMock()
    engine.queue_manager = MagicMock()
    engine.newConflict = MagicMock()
    return engine


def _watcher():
    with patch.object(AlfrescoRemoteWatcher, "__init__", return_value=None):
        watcher = AlfrescoRemoteWatcher.__new__(AlfrescoRemoteWatcher)
    watcher.engine = MagicMock()
    watcher.dao = MagicMock()
    watcher._cycle_count = 0
    watcher._interact = MagicMock()
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
    return proc


def _pair(**overrides):
    pair = MagicMock()
    pair.id = 1
    pair.folderish = False
    pair.remote_ref = "node-1"
    pair.local_name = "file.txt"
    pair.local_path = Path("/sync/file.txt")
    pair.last_sync_date = 1234567890
    pair.last_error = None
    pair.last_remote_updated = "2026-10-06 09:19:59.999000+00:00"
    pair.remote_version = "1.0"
    pair.pair_state = "conflicted"
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
# Fix 1 — conflict_resolver must not guess
# ---------------------------------------------------------------------------


class TestConflictResolverNeverSynced:
    """A pair with no ``last_sync_date`` has no baseline worth comparing."""

    def test_never_synced_with_identical_content_auto_resolves(self):
        engine = _engine()
        pair = _pair(last_sync_date=None)
        engine.dao.get_state_from_id.return_value = pair
        engine.local.abspath.return_value = MagicMock(is_file=lambda: True)

        with patch("nxdrive.alfresco.engine.engine.content_matches", return_value=True):
            engine.conflict_resolver(1)

        engine.dao.synchronize_state.assert_called_once_with(pair)
        engine.newConflict.emit.assert_not_called()
        # The timestamp shortcut must not run for a pair with no baseline.
        engine.dao._force_sync.assert_not_called()

    def test_never_synced_with_different_content_surfaces(self):
        engine = _engine()
        pair = _pair(last_sync_date=None)
        engine.dao.get_state_from_id.return_value = pair
        engine.local.abspath.return_value = MagicMock(is_file=lambda: True)

        with patch(
            "nxdrive.alfresco.engine.engine.content_matches", return_value=False
        ):
            engine.conflict_resolver(1)

        engine.newConflict.emit.assert_called_once_with(1)
        engine.dao.synchronize_state.assert_not_called()
        engine.dao._force_sync.assert_not_called()

    def test_never_synced_with_unknown_content_surfaces(self):
        """``None`` means "could not tell" and must never auto-resolve."""
        engine = _engine()
        pair = _pair(last_sync_date=None)
        engine.dao.get_state_from_id.return_value = pair
        engine.local.abspath.return_value = MagicMock(is_file=lambda: True)

        with patch("nxdrive.alfresco.engine.engine.content_matches", return_value=None):
            engine.conflict_resolver(1)

        engine.newConflict.emit.assert_called_once_with(1)
        engine.dao.synchronize_state.assert_not_called()

    def test_missing_local_file_surfaces_without_comparing(self):
        engine = _engine()
        pair = _pair(last_sync_date=None)
        engine.dao.get_state_from_id.return_value = pair
        engine.local.abspath.return_value = MagicMock(is_file=lambda: False)

        with patch("nxdrive.alfresco.engine.engine.content_matches") as matches:
            engine.conflict_resolver(1)

        matches.assert_not_called()
        engine.newConflict.emit.assert_called_once_with(1)

    def test_remote_first_race_is_covered(self):
        """The ``("unknown", "created")`` race that used to clobber a file.

        The remote watcher winning the race left the pair in a state the old
        ``created_both_sides`` guard did not recognise, so the timestamp
        shortcut ran against a baseline written from that very node and always
        said "unchanged".
        """
        engine = _engine()
        pair = _pair(last_sync_date=None, local_state="unknown", remote_state="created")
        engine.dao.get_state_from_id.return_value = pair
        engine.local.abspath.return_value = MagicMock(is_file=lambda: True)

        with patch(
            "nxdrive.alfresco.engine.engine.content_matches", return_value=False
        ):
            engine.conflict_resolver(1)

        engine.remote.get_fs_info.assert_not_called()
        engine.dao._force_sync.assert_not_called()
        engine.newConflict.emit.assert_called_once_with(1)


class TestConflictResolverReasoned:
    """Conflicts the engine raised on purpose are not auto-resolvable."""

    @pytest.mark.parametrize("reason", (FILE_OPEN_LOCALLY, LOCKED_ON_SERVER))
    def test_reasoned_conflict_skips_freshness_check(self, reason):
        engine = _engine()
        pair = _pair(last_error=reason)
        engine.dao.get_state_from_id.return_value = pair

        engine.conflict_resolver(1)

        engine.remote.get_fs_info.assert_not_called()
        engine.dao._force_sync.assert_not_called()
        engine.newConflict.emit.assert_called_once_with(1)

    @pytest.mark.parametrize("reason", (FILE_OPEN_LOCALLY, LOCKED_ON_SERVER))
    def test_a_reasoned_pair_that_never_synced_is_not_content_resolved(self, reason):
        """The reason must win over the never-synced byte comparison.

        Otherwise a pair we parked on purpose gets silently synchronised the
        moment its sampled content happens to match.
        """
        engine = _engine()
        pair = _pair(last_error=reason, last_sync_date=None)
        engine.dao.get_state_from_id.return_value = pair
        engine.local.abspath.return_value = MagicMock(is_file=lambda: True)

        with patch(
            "nxdrive.alfresco.engine.engine.content_matches", return_value=True
        ) as matches:
            engine.conflict_resolver(1)

        matches.assert_not_called()
        engine.dao.synchronize_state.assert_not_called()
        engine.newConflict.emit.assert_called_once_with(1)

    @pytest.mark.parametrize("reason", (FILE_OPEN_LOCALLY, LOCKED_ON_SERVER))
    def test_a_reasoned_folder_is_not_auto_resolved_by_its_xattr(self, reason):
        engine = _engine()
        pair = _pair(last_error=reason, folderish=True)
        engine.dao.get_state_from_id.return_value = pair
        engine.local.get_remote_id.return_value = pair.remote_ref

        engine.conflict_resolver(1)

        engine.dao.synchronize_state.assert_not_called()
        engine.newConflict.emit.assert_called_once_with(1)

    def test_synced_pair_with_unchanged_remote_still_resets(self):
        """The legitimate spurious-conflict path must keep working."""
        engine = _engine()
        pair = _pair(last_remote_updated="2026-10-06 09:19:59.999000+00:00")
        engine.dao.get_state_from_id.return_value = pair
        engine.remote.get_fs_info.return_value = _info(
            last_modification_time="2026-10-06 09:19:59"
        )

        with patch(
            "nxdrive.alfresco.engine.processor._fmt_remote_ts",
            return_value="2026-10-06 09:19:59",
        ):
            engine.conflict_resolver(1)

        engine.dao._force_sync.assert_called_once_with(
            pair, "modified", "synchronized", "locally_modified"
        )
        engine.newConflict.emit.assert_not_called()

    def test_emit_false_does_not_notify(self):
        engine = _engine()
        pair = _pair(last_error=LOCKED_ON_SERVER)
        engine.dao.get_state_from_id.return_value = pair

        engine.conflict_resolver(1, emit=False)

        engine.newConflict.emit.assert_not_called()
        engine.queue_manager.interrupt_processors_on.assert_not_called()

    def test_surfacing_interrupts_in_flight_processors(self):
        """An upload still running would overwrite the remote we just flagged."""
        engine = _engine()
        pair = _pair(last_error=LOCKED_ON_SERVER)
        engine.dao.get_state_from_id.return_value = pair

        engine.conflict_resolver(1)

        engine.queue_manager.interrupt_processors_on.assert_called_once_with(
            pair.local_path, exact_match=True
        )


# ---------------------------------------------------------------------------
# Fix 2 — version first, timestamp second, bytes last
# ---------------------------------------------------------------------------


class TestContentChangedOrdering:
    def test_folder_is_never_a_content_change(self):
        watcher = _watcher()
        assert watcher._content_changed(_pair(), _info(folderish=True)) is False

    def test_same_version_vetoes_a_moved_timestamp(self):
        """A rename or tag moves ``modifiedAt`` but not the version label."""
        watcher = _watcher()
        watcher._timestamp_moved = MagicMock(return_value=True)

        changed = watcher._content_changed(
            _pair(remote_version="1.1"), _info(version_label="1.1")
        )

        assert changed is False
        # Authoritative and free: no extra call may be made.
        watcher._timestamp_moved.assert_not_called()
        watcher.engine.remote.get_node.assert_not_called()

    def test_new_version_is_a_content_change(self):
        watcher = _watcher()
        changed = watcher._content_changed(
            _pair(remote_version="1.0"), _info(version_label="1.1")
        )
        assert changed is True

    def test_unmoved_timestamp_short_circuits_before_fetching(self):
        watcher = _watcher()
        watcher._timestamp_moved = MagicMock(return_value=False)
        watcher._fill_version_and_lock = MagicMock()

        changed = watcher._content_changed(
            _pair(remote_version=""), _info(version_label="")
        )

        assert changed is False
        watcher._fill_version_and_lock.assert_not_called()

    def test_moved_timestamp_fetches_version_and_compares(self):
        watcher = _watcher()
        watcher._timestamp_moved = MagicMock(return_value=True)
        info = _info(version_label="")

        def _fill(child_info, /):
            child_info.version_label = "1.0"

        watcher._fill_version_and_lock = MagicMock(side_effect=_fill)

        # The feed had no version, but the fetched one matches the baseline.
        assert watcher._content_changed(_pair(remote_version="1.0"), info) is False

    def test_non_versionable_node_trusts_the_timestamp(self):
        watcher = _watcher()
        watcher._timestamp_moved = MagicMock(return_value=True)
        watcher._fill_version_and_lock = MagicMock()

        changed = watcher._content_changed(
            _pair(remote_version="", last_remote_updated="2026-10-06 09:19:59"),
            _info(version_label=""),
        )

        assert changed is True

    def test_no_baseline_falls_back_to_content_comparison(self):
        """A newly created local file has neither a version nor a timestamp."""
        watcher = _watcher()
        watcher._fill_version_and_lock = MagicMock()
        watcher._content_differs = MagicMock(return_value=True)
        pair = _pair(remote_version="", last_remote_updated=None)

        assert watcher._content_changed(pair, _info(version_label="")) is True
        watcher._content_differs.assert_called_once()

    def test_no_baseline_with_matching_content_is_not_a_change(self):
        watcher = _watcher()
        watcher._fill_version_and_lock = MagicMock()
        watcher._content_differs = MagicMock(return_value=False)
        pair = _pair(remote_version="", last_remote_updated=None)

        assert watcher._content_changed(pair, _info(version_label="")) is False


class TestContentDiffers:
    def test_missing_local_file_counts_as_different(self):
        watcher = _watcher()
        watcher.engine.local.abspath.return_value = MagicMock(is_file=lambda: False)
        assert watcher._content_differs(_pair(), _info()) is True

    @pytest.mark.parametrize(
        "matches, expected", ((True, False), (False, True), (None, True))
    )
    def test_unknown_resolves_to_different(self, matches, expected):
        watcher = _watcher()
        watcher.engine.local.abspath.return_value = MagicMock(is_file=lambda: True)
        with patch(
            "nxdrive.alfresco.engine.watcher.remote_watcher.content_matches",
            return_value=matches,
        ):
            assert watcher._content_differs(_pair(), _info()) is expected


# ---------------------------------------------------------------------------
# Fix 3 — the processor's baseline survives a concurrent remote change
# ---------------------------------------------------------------------------


class TestReconcileChildEarlyReturns:
    @pytest.mark.parametrize("state", ("locally_created", "locally_modified"))
    def test_processor_owned_pair_keeps_its_baseline(self, state):
        watcher = _watcher()
        watcher._lock_was_released = MagicMock(return_value=False)
        watcher._content_changed = MagicMock()
        pair = _pair(pair_state=state, remote_state="synchronized")
        info = _info()

        assert watcher._reconcile_child(pair, info, "/remote", Path("/sync")) is pair

        kwargs = watcher.dao.update_remote_state.call_args.kwargs
        assert kwargs["no_baseline"] is True
        assert "force_update" not in kwargs
        watcher.dao.force_remote.assert_not_called()
        # No point computing a verdict we are not going to act on.
        watcher._content_changed.assert_not_called()

    def test_conflicted_pair_is_left_alone_without_any_call(self):
        watcher = _watcher()
        watcher._lock_was_released = MagicMock(return_value=False)
        watcher._content_changed = MagicMock()
        pair = _pair(pair_state="conflicted", remote_state="synchronized")

        assert watcher._reconcile_child(pair, _info(), "/remote", Path("/sync")) is pair

        watcher.dao.update_remote_state.assert_not_called()
        watcher.dao.force_remote.assert_not_called()
        # The wasted GET /nodes/{id} per cycle is gone.
        watcher._content_changed.assert_not_called()

    def test_healthy_pair_with_a_content_change_is_queued(self):
        watcher = _watcher()
        watcher._lock_was_released = MagicMock(return_value=False)
        watcher._content_changed = MagicMock(return_value=True)
        pair = _pair(pair_state="synchronized", remote_state="synchronized")

        watcher._reconcile_child(pair, _info(), "/remote", Path("/sync"))

        kwargs = watcher.dao.update_remote_state.call_args.kwargs
        assert kwargs["force_update"] is True
        assert kwargs["versioned"] is False
        watcher.dao.force_remote.assert_called_once_with(pair)


# ---------------------------------------------------------------------------
# Bounded deferral for a file the user has open
# ---------------------------------------------------------------------------


class TestDeferOpenFile:
    def test_each_attempt_under_the_bound_postpones(self):
        for attempt in range(MAX_OPEN_FILE_DEFERRALS):
            proc = _processor()
            proc._postpone_pair = MagicMock()
            proc._mark_conflicted = MagicMock()
            pair = _pair(error_count=attempt)

            proc._defer_open_file(pair)

            proc.dao.increase_error.assert_called_once_with(pair, FILE_OPEN_LOCALLY)
            proc._postpone_pair.assert_called_once()
            proc._mark_conflicted.assert_not_called()

    def test_exceeding_the_bound_raises_a_conflict(self):
        proc = _processor()
        proc._postpone_pair = MagicMock()
        proc._mark_conflicted = MagicMock()
        pair = _pair(error_count=MAX_OPEN_FILE_DEFERRALS)

        proc._defer_open_file(pair)

        # The reason travels with the flip, so a resolver woken by the signal
        # cannot see the conflict without it.
        proc._mark_conflicted.assert_called_once_with(pair, reason=FILE_OPEN_LOCALLY)
        proc.dao.set_last_error.assert_not_called()
        proc._postpone_pair.assert_not_called()
        proc.dao.increase_error.assert_not_called()

    def test_error_count_stays_at_or_below_the_queue_threshold(self):
        """Otherwise the pair shows up as an error instead of a conflict."""
        assert MAX_OPEN_FILE_DEFERRALS <= 3


# ---------------------------------------------------------------------------
# Lock sweep
# ---------------------------------------------------------------------------


class TestSweepLockConflicts:
    def test_runs_on_odd_cycles_only(self):
        watcher = _watcher()
        watcher.dao.get_conflicts.return_value = []

        for _ in range(4):
            watcher._sweep_lock_conflicts()

        # Cycles 1 and 3 looked, cycles 2 and 4 returned immediately.
        assert watcher.dao.get_conflicts.call_count == 2

    def test_only_lock_parked_pairs_are_re_checked(self):
        watcher = _watcher()
        locked = _pair(last_error=LOCKED_ON_SERVER)
        other = _pair(last_error=FILE_OPEN_LOCALLY)
        no_ref = _pair(last_error=LOCKED_ON_SERVER, remote_ref=None)
        watcher.dao.get_conflicts.return_value = [locked, other, no_ref]
        watcher.engine.remote.get_node.return_value = MagicMock(is_locked=True)

        watcher._sweep_lock_conflicts()

        watcher.engine.remote.get_node.assert_called_once_with(locked.remote_ref)

    def test_released_lock_is_requeued(self):
        watcher = _watcher()
        pair = _pair(last_error=LOCKED_ON_SERVER)
        watcher.dao.get_conflicts.return_value = [pair]
        watcher.engine.remote.get_node.return_value = MagicMock(is_locked=False)

        watcher._sweep_lock_conflicts()

        watcher.dao._force_sync.assert_called_once_with(
            pair, "modified", "synchronized", "locally_modified"
        )

    def test_a_server_error_does_not_abort_the_sweep(self):
        watcher = _watcher()
        first = _pair(last_error=LOCKED_ON_SERVER, remote_ref="node-1")
        second = _pair(last_error=LOCKED_ON_SERVER, remote_ref="node-2")
        watcher.dao.get_conflicts.return_value = [first, second]
        watcher.engine.remote.get_node.side_effect = [
            OSError("boom"),
            MagicMock(is_locked=False),
        ]

        watcher._sweep_lock_conflicts()

        watcher.dao._force_sync.assert_called_once_with(
            second, "modified", "synchronized", "locally_modified"
        )


# ---------------------------------------------------------------------------
# content_compare
# ---------------------------------------------------------------------------


class TestContentMatches:
    def test_a_size_difference_answers_without_reading_content(self, tmp_path):
        local = tmp_path / "file.txt"
        local.write_bytes(b"hello")
        remote = MagicMock()

        assert content_matches(remote, local, "node-1", remote_size=99) is False
        remote.get_content_range.assert_not_called()

    def test_identical_small_files_match(self, tmp_path):
        local = tmp_path / "file.txt"
        local.write_bytes(b"hello")
        remote = MagicMock()
        remote.get_content_range.return_value = b"hello"

        assert content_matches(remote, local, "node-1", remote_size=5) is True

    def test_same_size_different_bytes_do_not_match(self, tmp_path):
        local = tmp_path / "file.txt"
        local.write_bytes(b"hello")
        remote = MagicMock()
        remote.get_content_range.return_value = b"world"

        assert content_matches(remote, local, "node-1", remote_size=5) is False

    def test_an_unreadable_local_file_is_unknown(self, tmp_path):
        assert content_matches(MagicMock(), tmp_path / "nope.txt", "node-1") is None

    def test_a_persistent_server_error_is_unknown(self, tmp_path):
        local = tmp_path / "file.txt"
        local.write_bytes(b"hello")
        remote = MagicMock()
        remote.get_content_range.side_effect = OSError("boom")

        with patch(f"{CONTENT_COMPARE}.sleep") as slept:
            result = content_matches(remote, local, "node-1", remote_size=5)

        assert result is None
        assert remote.get_content_range.call_count == PARTIAL_COMPARE_ATTEMPTS
        assert slept.call_count == PARTIAL_COMPARE_ATTEMPTS - 1

    def test_a_transient_server_error_is_retried(self, tmp_path):
        local = tmp_path / "file.txt"
        local.write_bytes(b"hello")
        remote = MagicMock()
        remote.get_content_range.side_effect = [OSError("boom"), b"hello"]

        with patch(f"{CONTENT_COMPARE}.sleep"):
            assert content_matches(remote, local, "node-1", remote_size=5) is True

    def test_the_remote_size_is_fetched_when_not_supplied(self, tmp_path):
        local = tmp_path / "file.txt"
        local.write_bytes(b"hello")
        remote = MagicMock()
        remote.get_node.return_value = MagicMock(content=MagicMock(size_in_bytes=5))
        remote.get_content_range.return_value = b"hello"

        assert content_matches(remote, local, "node-1") is True
        remote.get_node.assert_called_once_with("node-1")
