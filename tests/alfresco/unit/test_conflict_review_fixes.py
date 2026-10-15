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
from threading import Lock
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.alfresco.content_compare import PARTIAL_COMPARE_ATTEMPTS, content_matches
from nxdrive.alfresco.engine.engine import AlfrescoEngine
from nxdrive.alfresco.engine.processor import (
    DIFFERENT_CONTENT,
    FILE_OPEN_LOCALLY,
    LOCKED_ON_SERVER,
    MAX_OPEN_FILE_DEFERRALS,
    REMOTE_DRIFTED,
    AlfrescoProcessor,
)
from nxdrive.alfresco.engine.watcher.remote_watcher import AlfrescoRemoteWatcher
from nxdrive.drive.constants import UNACCESSIBLE_HASH
from nxdrive.drive.exceptions import ThreadInterrupt

CONTENT_COMPARE = "nxdrive.alfresco.content_compare"

#: What the pair last recorded for the local file, and what hashing it yields
#: when nobody has touched it.
ON_DISK = "ondisk"


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
    # Normally set in __init__, which is bypassed here.
    engine._deferred_conflicts = {}
    engine._deferred_conflicts_lock = Lock()
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
    # The late re-read before the irreversible delete has its own tests; a
    # bare mock row never matches, so it would abort every other one.
    proc._decision_changed = MagicMock(return_value=False)
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
    pair.pair_state = "conflicted"
    pair.local_digest = ON_DISK
    pair.error_count = 0
    for key, value in overrides.items():
        setattr(pair, key, value)
    return pair


def _info(**overrides):
    info = MagicMock()
    info.uid = "node-1"
    info.name = "file.txt"
    info.folderish = False
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
            engine._decide_conflict(1)

        engine.dao.synchronize_state.assert_called_once_with(
            pair, only_if_conflicted=True, expected_last_error=None
        )
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
            engine._decide_conflict(1)

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
            engine._decide_conflict(1)

        engine.newConflict.emit.assert_called_once_with(1)
        engine.dao.synchronize_state.assert_not_called()

    def test_missing_local_file_surfaces_without_comparing(self):
        engine = _engine()
        pair = _pair(last_sync_date=None)
        engine.dao.get_state_from_id.return_value = pair
        engine.local.abspath.return_value = MagicMock(is_file=lambda: False)

        with patch("nxdrive.alfresco.engine.engine.content_matches") as matches:
            engine._decide_conflict(1)

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
            engine._decide_conflict(1)

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

    @pytest.mark.parametrize("reason", (FILE_OPEN_LOCALLY, LOCKED_ON_SERVER))
    def test_a_reason_arriving_while_deferred_still_wins(self, reason):
        """``conflict_resolver`` defers, then a processor parks the row.

        The state still reads as "conflicted", so only ``last_error`` can tell
        the deferred worker that this is no longer its decision to make.
        """
        engine = _engine()
        pair = _pair(last_error=reason)
        engine.dao.get_state_from_id.return_value = pair

        engine._decide_conflict(1)

        engine.remote.get_fs_info.assert_not_called()
        engine.dao.force_sync_if_conflicted.assert_not_called()
        engine.dao.synchronize_state.assert_not_called()
        engine.newConflict.emit.assert_called_once_with(1)

    def test_synced_pair_with_unchanged_remote_still_resets(self):
        """The legitimate spurious-conflict path must keep working."""
        engine = _engine()
        pair = _pair()
        engine.dao.get_state_from_id.return_value = pair
        engine.remote.get_fs_info.return_value = _info()

        with patch(
            "nxdrive.alfresco.engine.processor._fmt_remote_ts",
            return_value="2026-10-06 09:19:59",
        ), patch("nxdrive.alfresco.engine.engine.content_matches", return_value=True):
            engine._decide_conflict(1)

        engine.dao.force_sync_if_conflicted.assert_called_once_with(
            pair,
            "modified",
            "synchronized",
            "locally_modified",
            expected_last_error=None,
        )
        engine.newConflict.emit.assert_not_called()


class TestResolverUsesTheTimestampThenTheBytes:
    """Alfresco exposes no digest, so the clock decides and bytes settle a tie.

    ACCEPTED LIMITATION: an edit inside the stored second that also leaves
    both 10 MB comparison windows identical reads as "unchanged".
    """

    def test_a_moved_timestamp_is_a_conflict(self):
        engine = _engine()
        pair = _pair(last_remote_updated="2026-10-06 09:19:59.000+00:00")
        engine.dao.get_state_from_id.return_value = pair
        engine.remote.get_fs_info.return_value = _info()

        with patch(
            "nxdrive.alfresco.engine.processor._fmt_remote_ts",
            return_value="2026-10-07 11:00:00",
        ):
            engine._decide_conflict(1)

        engine.dao.force_sync_if_conflicted.assert_not_called()
        engine.newConflict.emit.assert_called_once_with(1)

    @pytest.mark.parametrize("identical, resolves", ((True, True), (False, False)))
    def test_the_same_second_is_settled_by_the_bytes(self, identical, resolves):
        """The clock is truncated to whole seconds, so a match proves nothing."""
        engine = _engine()
        pair = _pair(last_remote_updated="2026-10-06 09:19:59.999000+00:00")
        engine.dao.get_state_from_id.return_value = pair
        engine.remote.get_fs_info.return_value = _info()

        with patch(
            "nxdrive.alfresco.engine.processor._fmt_remote_ts",
            return_value="2026-10-06 09:19:59",
        ), patch(
            "nxdrive.alfresco.engine.engine.content_matches", return_value=identical
        ):
            engine._decide_conflict(1)

        assert engine.dao.force_sync_if_conflicted.called is resolves

    def test_an_unreadable_remote_timestamp_is_a_conflict(self):
        """Nothing to compare means the user decides, not us."""
        engine = _engine()
        engine.dao.get_state_from_id.return_value = _pair()
        engine.remote.get_fs_info.return_value = _info()

        with patch("nxdrive.alfresco.engine.processor._fmt_remote_ts", return_value=""):
            engine._decide_conflict(1)

        engine.dao.force_sync_if_conflicted.assert_not_called()
        engine.newConflict.emit.assert_called_once_with(1)

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


class TestConflictResolverStaysOffTheGuiThread:
    """``conflict_resolver`` is a ``newConflict`` slot, so it runs on the GUI
    thread. One server round trip per conflicting file froze the window for
    16 s across 50 files, and again on every restart."""

    @pytest.mark.parametrize(
        "reason",
        (FILE_OPEN_LOCALLY, LOCKED_ON_SERVER, DIFFERENT_CONTENT, REMOTE_DRIFTED),
    )
    def test_a_reasoned_conflict_costs_nothing(self, reason):
        engine = _engine()
        engine.dao.get_state_from_id.return_value = _pair(last_error=reason)

        engine.conflict_resolver(1)

        engine.remote.get_fs_info.assert_not_called()
        engine.remote.get_node.assert_not_called()
        assert engine._deferred_conflicts == {}

    def test_anything_else_is_parked_instead_of_decided(self):
        engine = _engine()
        engine.dao.get_state_from_id.return_value = _pair(last_error=None)

        engine.conflict_resolver(1)

        engine.remote.get_fs_info.assert_not_called()
        engine.dao.synchronize_state.assert_not_called()
        engine.dao._force_sync.assert_not_called()
        assert engine._deferred_conflicts == {1: True}

    def test_the_same_pair_is_not_parked_twice(self):
        engine = _engine()
        engine.dao.get_state_from_id.return_value = _pair(last_error=None)

        engine.conflict_resolver(1)
        engine.conflict_resolver(1)

        assert engine._deferred_conflicts == {1: True}

    def test_a_silent_request_is_remembered_as_silent(self):
        """``Engine.start()`` re-checks old conflicts with ``emit=False``.

        Losing that would pop a notification for every conflict still open
        from the previous session.
        """
        engine = _engine()
        engine.dao.get_state_from_id.return_value = _pair(last_error=None)

        engine.conflict_resolver(1, emit=False)

        assert engine._deferred_conflicts == {1: False}

    def test_silence_wins_when_a_pair_is_parked_both_ways(self):
        engine = _engine()
        engine.dao.get_state_from_id.return_value = _pair(last_error=None)

        engine.conflict_resolver(1)
        engine.conflict_resolver(1, emit=False)

        assert engine._deferred_conflicts == {1: False}

    def test_the_flag_reaches_the_decision(self):
        engine = _engine()
        engine._deferred_conflicts = {1: False, 2: True}
        engine._decide_conflict = MagicMock()

        engine.resolve_deferred_conflicts()

        assert engine._decide_conflict.call_args_list[0].kwargs["emit"] is False
        assert engine._decide_conflict.call_args_list[1].kwargs["emit"] is True

    def test_draining_decides_each_parked_pair_once(self):
        engine = _engine()
        engine._deferred_conflicts = {1: True, 2: True, 3: True}
        engine._decide_conflict = MagicMock()

        engine.resolve_deferred_conflicts()

        assert engine._decide_conflict.call_count == 3
        assert engine._deferred_conflicts == {}

    def test_one_bad_pair_does_not_strand_the_rest(self):
        engine = _engine()
        engine._deferred_conflicts = {1: True, 2: True, 3: True}
        engine._decide_conflict = MagicMock(side_effect=[OSError("boom"), None, None])

        engine.resolve_deferred_conflicts()

        assert engine._decide_conflict.call_count == 3

    def test_a_pair_resolved_before_the_drain_is_skipped(self):
        engine = _engine()
        engine.dao.get_state_from_id.return_value = _pair(pair_state="synchronized")

        engine._decide_conflict(1)

        engine.remote.get_fs_info.assert_not_called()
        engine.dao.synchronize_state.assert_not_called()


# ---------------------------------------------------------------------------
# Fix 2 — timestamp first, bytes last
# ---------------------------------------------------------------------------


class TestContentChangedOrdering:
    """``nodeTimestamp`` decides; an unmoved timestamp is confirmed by bytes.

    ACCEPTED LIMITATION: an edit inside the second we already hold, which also
    leaves both 10 MB comparison windows identical, reads as "no change".
    """

    def test_folder_is_never_a_content_change(self):
        watcher = _watcher()
        assert watcher._content_changed(_pair(), _info(folderish=True), True) is False

    def test_a_moved_timestamp_is_a_content_change(self):
        watcher = _watcher()
        watcher._timestamp_moved = MagicMock(return_value=True)
        watcher._content_differs = MagicMock()

        assert watcher._content_changed(_pair(), _info(), True) is True
        # The clock already answered; the bytes cost a download.
        watcher._content_differs.assert_not_called()

    def test_an_unmoved_timestamp_is_settled_by_the_bytes(self):
        watcher = _watcher()
        watcher._timestamp_moved = MagicMock(return_value=False)
        watcher._content_differs = MagicMock(return_value=True)

        assert watcher._content_changed(_pair(), _info(), True) is True
        watcher._content_differs.assert_called_once()

    def test_identical_bytes_at_the_same_second_are_not_a_change(self):
        watcher = _watcher()
        watcher._timestamp_moved = MagicMock(return_value=False)
        watcher._content_differs = MagicMock(return_value=False)

        assert watcher._content_changed(_pair(), _info(), True) is False

    def test_a_pair_with_no_timestamp_at_all_is_a_change(self):
        watcher = _watcher()
        watcher._content_differs = MagicMock()

        changed = watcher._content_changed(
            _pair(last_remote_updated=None), _info(), True
        )

        assert changed is True
        watcher._content_differs.assert_not_called()

    def test_the_decision_costs_no_network_call(self):
        """The feed carries everything this needs; fetching was the old cost."""
        watcher = _watcher()
        watcher._timestamp_moved = MagicMock(return_value=True)

        watcher._content_changed(_pair(), _info(), True)

        watcher.engine.remote.get_node.assert_not_called()


class TestAScanDoesNotHashEveryFile:
    """A full scan enumerates; it does not assert that anything changed.

    Confirming an unmoved timestamp against the bytes there would hash every
    unchanged file on every scan - roughly 20 MB each, on the whole tree.
    """

    def test_an_unmoved_timestamp_is_taken_at_face_value(self):
        watcher = _watcher()
        watcher._timestamp_moved = MagicMock(return_value=False)
        watcher._content_differs = MagicMock(return_value=True)

        assert watcher._content_changed(_pair(), _info(), False) is False
        watcher._content_differs.assert_not_called()

    def test_a_moved_timestamp_is_still_a_change(self):
        watcher = _watcher()
        watcher._timestamp_moved = MagicMock(return_value=True)

        assert watcher._content_changed(_pair(), _info(), False) is True

    def test_the_scan_path_does_not_report_a_change(self):
        """``_reconcile_child`` defaults to enumeration; only the feed asserts."""
        watcher = _watcher()
        watcher._lock_was_released = MagicMock(return_value=False)
        watcher._content_changed = MagicMock(return_value=False)
        pair = _pair(pair_state="synchronized", remote_state="synchronized")

        watcher._reconcile_child(pair, _info(), "/remote", Path("/sync"))

        assert watcher._content_changed.call_args.args[2] is False


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
    def test_processor_owned_pair_only_gets_its_naming_refreshed(self, state):
        """Anything else here would be written from a row already read.

        The processor can raise a conflict in that gap, and a write matched on
        ``id`` alone would put the pair back to ``locally_modified`` and requeue
        the upload the conflict exists to stop.
        """
        watcher = _watcher()
        watcher._lock_was_released = MagicMock(return_value=False)
        watcher._content_changed = MagicMock()
        pair = _pair(pair_state=state, remote_state="synchronized")
        info = _info()

        assert watcher._reconcile_child(pair, info, "/remote", Path("/sync")) is pair

        watcher.dao.update_remote_naming.assert_called_once()
        kwargs = watcher.dao.update_remote_naming.call_args.kwargs
        assert kwargs["remote_parent_path"] == "/remote"
        # No sync state, no baseline, no queueing.
        watcher.dao.update_remote_state.assert_not_called()
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
        watcher.dao.force_remote.assert_called_once()
        assert watcher.dao.force_remote.call_args.args[0] is pair

    def test_the_forced_transition_is_guarded_on_the_committed_state(self):
        """``force_remote`` clears ``last_error``, so a conflict raised between
        the two writes would lose the reason it was raised for. Nothing bumps
        ``version`` in that gap, so only the state can refuse it."""
        watcher = _watcher()
        watcher._lock_was_released = MagicMock(return_value=False)
        watcher._content_changed = MagicMock(return_value=True)
        pair = _pair(pair_state="synchronized", remote_state="synchronized")

        watcher._reconcile_child(pair, _info(), "/remote", Path("/sync"))

        kwargs = watcher.dao.force_remote.call_args.kwargs
        assert kwargs["expected_pair_state"] == "synchronized"

    def test_the_baseline_waits_for_the_transition(self):
        """The drift check reads ``last_remote_updated``. Advancing it on a row
        that stays locally modified tells that check the server never moved,
        and the upload goes straight over the remote edit."""
        watcher = _watcher()
        watcher._lock_was_released = MagicMock(return_value=False)
        watcher._content_changed = MagicMock(return_value=True)
        pair = _pair(pair_state="synchronized", remote_state="synchronized")

        watcher._reconcile_child(pair, _info(), "/remote", Path("/sync"))

        assert watcher.dao.update_remote_state.call_args.kwargs["no_baseline"] is True
        watcher.dao.update_remote_baseline.assert_called_once()

    def test_a_refused_transition_leaves_the_baseline_behind(self):
        watcher = _watcher()
        watcher._lock_was_released = MagicMock(return_value=False)
        watcher._content_changed = MagicMock(return_value=True)
        watcher.dao.force_remote.return_value = False
        pair = _pair(pair_state="synchronized", remote_state="synchronized")

        watcher._reconcile_child(pair, _info(), "/remote", Path("/sync"))

        watcher.dao.update_remote_baseline.assert_not_called()

    def test_the_unchanged_path_is_guarded_too(self):
        """It is reached *after* the byte comparison, so it has had just as
        long for a decision to land: a same-second rename with matching bytes
        answers "unchanged" seconds later."""
        watcher = _watcher()
        watcher._lock_was_released = MagicMock(return_value=False)
        watcher._content_changed = MagicMock(return_value=False)
        pair = _pair(pair_state="synchronized", remote_state="synchronized", version=6)

        watcher._reconcile_child(pair, _info(), "/remote", Path("/sync"))

        kwargs = watcher.dao.update_remote_state.call_args.kwargs
        assert kwargs["expected_version"] == 6
        assert kwargs["expected_pair_state"] == "synchronized"

    def test_the_content_change_write_is_guarded_on_state_too(self):
        """The byte comparison can take seconds, and ``_force_sync`` raises a
        conflict without bumping ``version``."""
        watcher = _watcher()
        watcher._lock_was_released = MagicMock(return_value=False)
        watcher._content_changed = MagicMock(return_value=True)
        pair = _pair(pair_state="synchronized", remote_state="synchronized", version=9)

        watcher._reconcile_child(pair, _info(), "/remote", Path("/sync"))

        kwargs = watcher.dao.update_remote_state.call_args.kwargs
        assert kwargs["expected_version"] == 9
        assert kwargs["expected_pair_state"] == "synchronized"

    def test_a_refused_write_does_not_clear_the_digest_or_queue(self):
        watcher = _watcher()
        watcher._lock_was_released = MagicMock(return_value=False)
        watcher._content_changed = MagicMock(return_value=True)
        watcher.dao.update_remote_state.return_value = False
        pair = _pair(pair_state="synchronized", remote_state="synchronized")

        watcher._reconcile_child(pair, _info(), "/remote", Path("/sync"))

        watcher.dao.clear_remote_digest.assert_not_called()
        watcher.dao.force_remote.assert_not_called()


# ---------------------------------------------------------------------------
# Bounded deferral for a file the user has open
# ---------------------------------------------------------------------------


class TestLocalFileInUse:
    """A probe that could not answer lets the download through, and says so.

    Unsupported platforms are filtered by ``has_file_open_detection``, so a
    ``None`` from the detector means the probe itself failed. Raising a
    conflict there would hand the user something they cannot act on, so the
    download proceeds and the failure is logged as an error instead.
    """

    def _proc(self, answer, /, *, detects=True):
        proc = _processor()
        proc.engine.manager.osi.has_file_open_detection.return_value = detects
        proc.engine.manager.osi.is_file_open.return_value = answer
        return proc

    @pytest.mark.parametrize(
        "answer, in_use", ((True, True), (False, False), (None, False))
    )
    def test_only_a_definite_yes_holds_the_download_back(self, answer, in_use):
        assert self._proc(answer)._local_file_in_use(_pair()) is in_use

    def test_a_failed_probe_is_logged_as_a_warning(self, caplog):
        """ "I do not know" is not a decision: the pair has to go one way, and
        the log is the record that detection, not sync, is what failed."""
        caplog.set_level("WARNING")

        assert self._proc(None)._local_file_in_use(_pair()) is False

        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any("Open-file detection could not answer" in m for m in warnings)
        assert any("file.txt" in m for m in warnings)

    @pytest.mark.parametrize("answer", (True, False))
    def test_an_answered_probe_logs_nothing(self, caplog, answer):
        caplog.set_level("WARNING")

        self._proc(answer)._local_file_in_use(_pair())

        assert not [r for r in caplog.records if r.levelname == "WARNING"]

    def test_a_platform_that_cannot_answer_is_not_consulted(self, caplog):
        """Nothing changes, and nothing is logged, where the feature is absent."""
        caplog.set_level("WARNING")
        proc = self._proc(None, detects=False)

        assert proc._local_file_in_use(_pair()) is False
        proc.engine.manager.osi.is_file_open.assert_not_called()
        assert not [r for r in caplog.records if r.levelname == "WARNING"]

    def test_a_folder_is_never_in_use(self):
        proc = self._proc(None)

        assert proc._local_file_in_use(_pair(folderish=True)) is False
        proc.engine.manager.osi.is_file_open.assert_not_called()


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


class TestOpenFileRecheckedAfterTheDownload:
    """``delete_final`` is permanent and the transfer can take minutes.

    The verdict taken before it started says nothing about the file we are
    about to destroy, so it has to be re-taken at the last possible moment.
    """

    def _proc(self, in_use, /):
        proc = _processor()
        proc._download_content = MagicMock(return_value=Path("/tmp/dl/file.txt"))
        proc._local_file_in_use = MagicMock(return_value=in_use)
        proc._defer_open_file = MagicMock()
        proc._refresh_local_state = MagicMock()
        proc._refresh_remote = MagicMock()
        proc.local.abspath.return_value = Path("/sync/file.txt")
        proc.local.get_info.return_value.get_digest.return_value = ON_DISK
        return proc

    def test_a_file_opened_during_the_download_is_not_destroyed(self):
        proc = self._proc(True)

        assert proc._update_remotely(_pair(remote_name="file.txt"), False) is False

        proc.local.delete_final.assert_not_called()
        proc.local.move.assert_not_called()
        proc._defer_open_file.assert_called_once()

    def test_the_abandoned_download_is_cleaned_up(self):
        """Otherwise every deferral leaks a copy of the file on disk."""
        proc = self._proc(True)

        with patch("nxdrive.alfresco.engine.processor.shutil.rmtree") as rmtree:
            proc._update_remotely(_pair(remote_name="file.txt"), False)

        proc.local.move.assert_not_called()
        rmtree.assert_called_once_with(Path("/tmp/dl"))

    def test_a_closed_file_is_still_replaced(self):
        proc = self._proc(False)

        assert proc._update_remotely(_pair(remote_name="file.txt"), False) is True

        proc.local.delete_final.assert_called_once()

    def test_a_deferred_pair_is_not_marked_synchronized(self):
        """``_update_remotely`` cannot stop its caller without saying so."""
        proc = self._proc(True)
        proc.local.is_equal_digests.return_value = False
        pair = _pair(
            pair_state="remotely_modified",
            remote_name="file.txt",
            local_digest=ON_DISK,
            remote_digest="bbb",
        )

        proc._synchronize_remotely_modified(pair)

        proc.dao.synchronize_state.assert_not_called()


class TestEditDuringTheDownload:
    """An open-file probe answers for one instant; the user can edit, save and
    close inside a transfer that takes minutes. Only the bytes on disk report
    that, so they are read on both sides of it."""

    def _proc(self, digests, /):
        proc = _processor()
        proc._download_content = MagicMock(return_value=Path("/tmp/dl/file.txt"))
        proc._local_file_in_use = MagicMock(return_value=False)
        proc._mark_conflicted = MagicMock()
        proc._refresh_local_state = MagicMock()
        proc._refresh_remote = MagicMock()
        proc.local.abspath.return_value = Path("/sync/file.txt")
        proc.local.get_info.return_value.get_digest.side_effect = digests
        return proc

    def test_an_edit_made_during_the_transfer_is_not_deleted(self):
        proc = self._proc([ON_DISK, "after"])

        assert proc._update_remotely(_pair(remote_name="file.txt"), False) is False

        proc.local.delete_final.assert_not_called()
        proc.local.move.assert_not_called()

    def test_the_edit_becomes_a_conflict_the_user_must_settle(self):
        """Both sides changed, so neither copy may be chosen for the user."""
        proc = self._proc([ON_DISK, "after"])

        proc._update_remotely(_pair(remote_name="file.txt"), False)

        proc._mark_conflicted.assert_called_once()
        assert proc._mark_conflicted.call_args.kwargs["reason"] == DIFFERENT_CONTENT

    def test_the_abandoned_download_is_cleaned_up(self):
        proc = self._proc([ON_DISK, "after"])

        with patch("nxdrive.alfresco.engine.processor.shutil.rmtree") as rmtree:
            proc._update_remotely(_pair(remote_name="file.txt"), False)

        rmtree.assert_called_once_with(Path("/tmp/dl"))

    def test_an_untouched_file_is_still_replaced(self):
        proc = self._proc([ON_DISK, ON_DISK, ON_DISK])

        assert proc._update_remotely(_pair(remote_name="file.txt"), False) is True

        proc.local.delete_final.assert_called_once()
        proc._mark_conflicted.assert_not_called()

    @pytest.mark.parametrize("unreadable", (UNACCESSIBLE_HASH, "", None))
    def test_an_unreadable_hash_does_not_raise_a_conflict(self, unreadable):
        """A hash we could not take is not evidence of an edit, and the user
        cannot act on a conflict raised for one."""
        proc = self._proc([unreadable, "after", "after"])

        assert proc._update_remotely(_pair(remote_name="file.txt"), False) is True

        proc._mark_conflicted.assert_not_called()

    def test_a_failing_hash_does_not_stop_the_download(self):
        proc = self._proc(OSError("gone"))

        assert proc._update_remotely(_pair(remote_name="file.txt"), False) is True

        proc._mark_conflicted.assert_not_called()

    def test_an_edit_made_before_the_first_hash_is_caught(self):
        """The first hash is already taken after the metadata call, so a save
        made since the row was read is baked into both hashes and they compare
        equal. The recorded digest is the only witness left."""
        proc = self._proc([ON_DISK, ON_DISK])
        pair = _pair(remote_name="file.txt", local_digest="recorded-earlier")

        assert proc._update_remotely(pair, False) is False

        proc._download_content.assert_not_called()
        proc.local.delete_final.assert_not_called()
        assert proc._mark_conflicted.call_args.kwargs["reason"] == DIFFERENT_CONTENT

    @pytest.mark.parametrize("recorded", (None, "", UNACCESSIBLE_HASH))
    def test_an_unusable_recorded_digest_is_not_evidence(self, recorded):
        proc = self._proc([ON_DISK, ON_DISK, ON_DISK])
        pair = _pair(remote_name="file.txt", local_digest=recorded)

        assert proc._update_remotely(pair, False) is True

        proc._mark_conflicted.assert_not_called()


class TestBaselineAfterTheReplace:
    """The local file is written before the baseline is recorded, and the
    watcher can register an edit in between."""

    def _proc(self):
        proc = _processor()
        proc._download_content = MagicMock(return_value=Path("/tmp/dl/file.txt"))
        proc._local_file_in_use = MagicMock(return_value=False)
        proc._refresh_local_state = MagicMock(return_value=True)
        proc.local.abspath.return_value = Path("/sync/file.txt")
        proc.local.get_info.return_value.get_digest.return_value = ON_DISK
        return proc

    def test_the_baseline_write_is_guarded(self):
        proc = self._proc()
        pair = _pair(remote_name="file.txt", version=7, pair_state="remotely_modified")

        proc._update_remotely(pair, False)

        kwargs = proc.dao.update_remote_state.call_args.kwargs
        assert kwargs["expected_version"] == 7
        assert kwargs["expected_pair_state"] == "remotely_modified"

    def test_a_refused_baseline_stops_the_handler(self):
        """Carrying on would mark a newer local edit as already synchronised."""
        proc = self._proc()
        proc.dao.update_remote_state.return_value = False

        assert proc._update_remotely(_pair(remote_name="file.txt"), False) is False

    def test_a_refused_baseline_is_not_synchronized(self):
        proc = self._proc()
        proc.dao.update_remote_state.return_value = False
        proc.local.is_equal_digests.return_value = False
        pair = _pair(
            pair_state="remotely_modified",
            remote_name="file.txt",
            local_digest=ON_DISK,
            remote_digest="bbb",
        )

        proc._synchronize_remotely_modified(pair)

        proc.dao.synchronize_state.assert_not_called()

    def test_the_final_synchronization_carries_the_committed_state(self):
        proc = self._proc()
        proc.local.is_equal_digests.return_value = False
        pair = _pair(
            pair_state="remotely_modified",
            remote_name="file.txt",
            local_digest=ON_DISK,
            remote_digest="bbb",
        )

        proc._synchronize_remotely_modified(pair)

        kwargs = proc.dao.synchronize_state.call_args.kwargs
        assert kwargs["expected_pair_state"] == "remotely_modified"

    def test_the_local_state_write_is_guarded_too(self):
        """It runs first and writes ``pair_state`` from the stale row, so a
        guard on any later write is only comparing against this one."""
        proc = self._proc()
        proc._refresh_local_state = MagicMock(return_value=True)
        pair = _pair(remote_name="file.txt", version=4, pair_state="remotely_modified")

        proc._update_remotely(pair, False)

        kwargs = proc._refresh_local_state.call_args.kwargs
        assert kwargs["expected_version"] == 4
        assert kwargs["expected_pair_state"] == "remotely_modified"

    def test_a_refused_local_state_write_stops_the_handler(self):
        proc = self._proc()
        proc._refresh_local_state = MagicMock(return_value=False)

        assert proc._update_remotely(_pair(remote_name="file.txt"), False) is False

        proc.dao.update_remote_state.assert_not_called()


class TestResolveWithRemoteTerminates:
    """ "Use remote" has to be a way out, not another lap.

    The conflict can be raised because the bytes on disk no longer match
    ``local_digest`` -- a save the watchdog missed. Flipping the states alone
    leaves that mismatch, so the processor raises the same conflict again and
    the user is stuck in a loop with no exit.
    """

    def _engine_with(self, on_disk, /):
        engine = _engine()
        engine.local.get_info.return_value.get_digest.return_value = on_disk
        engine.dao.get_state_from_id.return_value = _pair(
            local_digest="recorded-earlier"
        )
        # The real DAO writes the value back onto the row it was handed.
        engine.dao.update_local_digest.side_effect = lambda row, digest: setattr(
            row, "local_digest", digest
        )
        return engine

    def test_the_stale_baseline_is_replaced_before_the_flip(self):
        engine = self._engine_with("what-is-on-disk-now")

        with patch.object(AlfrescoEngine.__bases__[0], "resolve_with_remote"):
            engine._acknowledge_local_bytes(1)

        engine.dao.update_local_digest.assert_called_once()
        assert engine.dao.update_local_digest.call_args.args[1] == "what-is-on-disk-now"

    def test_the_download_then_runs_instead_of_re_conflicting(self):
        """The whole point: the second pass must get past the digest check."""
        engine = self._engine_with("what-is-on-disk-now")
        with patch.object(AlfrescoEngine.__bases__[0], "resolve_with_remote"):
            engine._acknowledge_local_bytes(1)
        resolved = engine.dao.update_local_digest.call_args.args[0]

        proc = _processor()
        proc._download_content = MagicMock(return_value=Path("/tmp/dl/file.txt"))
        proc._local_file_in_use = MagicMock(return_value=False)
        proc._mark_conflicted = MagicMock()
        proc._refresh_local_state = MagicMock(return_value=True)
        proc.local.abspath.return_value = Path("/sync/file.txt")
        proc.local.get_info.return_value.get_digest.return_value = "what-is-on-disk-now"
        resolved.remote_name = "file.txt"

        assert proc._update_remotely(resolved, False) is True

        proc._mark_conflicted.assert_not_called()

    @pytest.mark.parametrize("unreadable", (UNACCESSIBLE_HASH, "", None))
    def test_an_unreadable_file_still_resolves(self, unreadable):
        """A missing local file is the commonest "use remote" case of all."""
        engine = self._engine_with(unreadable)

        with patch.object(AlfrescoEngine.__bases__[0], "resolve_with_remote") as base:
            engine._acknowledge_local_bytes(1)

        engine.dao.update_local_digest.assert_not_called()
        base.assert_called_once_with(1)

    def test_a_failing_probe_does_not_block_the_resolution(self):
        engine = self._engine_with("x")
        engine.local.get_info.side_effect = OSError("gone")

        with patch.object(AlfrescoEngine.__bases__[0], "resolve_with_remote") as base:
            engine._acknowledge_local_bytes(1)

        base.assert_called_once_with(1)


class TestConflictDropsTheRemoteDigest:
    """Alfresco serves no content hash, so ``remote_digest`` only holds what
    *we* last uploaded. A conflict says the two sides differ, which makes that
    value a claim about the server we can no longer make -- and a later
    download would use it to reuse a local duplicate instead of fetching."""

    def test_the_flip_clears_it_in_the_same_statement(self):
        proc = _processor()

        proc._mark_conflicted(_pair(), reason=REMOTE_DRIFTED)

        kwargs = proc.dao._force_sync.call_args.kwargs
        assert kwargs["clear_remote_digest"] is True


class TestAResolutionDuringTheDownload:
    """The digest checks only see *edits*. Choosing "Use local" changes the
    row and leaves the file alone, so it sails past them -- and the local copy
    the user just chose to keep gets replaced by the server's."""

    def _proc(self, current, /):
        proc = _processor()
        # The shared builder stubs this out; these tests exercise the real one.
        del proc._decision_changed
        proc._download_content = MagicMock(return_value=Path("/tmp/dl/file.txt"))
        proc._local_file_in_use = MagicMock(return_value=False)
        proc._mark_conflicted = MagicMock()
        proc._refresh_local_state = MagicMock(return_value=True)
        proc.local.abspath.return_value = Path("/sync/file.txt")
        proc.local.get_info.return_value.get_digest.return_value = ON_DISK
        proc.dao.get_state_from_id.return_value = current
        return proc

    def _pair(self):
        return _pair(remote_name="file.txt", version=3, pair_state="remotely_modified")

    def test_the_chosen_local_copy_is_not_replaced(self):
        resolved = _pair(version=3, pair_state="locally_resolved")
        proc = self._proc(resolved)

        assert proc._update_remotely(self._pair(), False) is False

        proc.local.delete_final.assert_not_called()
        proc.local.move.assert_not_called()

    def test_the_download_is_cleaned_up(self):
        proc = self._proc(_pair(version=3, pair_state="locally_resolved"))

        with patch("nxdrive.alfresco.engine.processor.shutil.rmtree") as rmtree:
            proc._update_remotely(self._pair(), False)

        rmtree.assert_called_once_with(Path("/tmp/dl"))

    def test_a_version_bump_also_aborts(self):
        proc = self._proc(_pair(version=9, pair_state="remotely_modified"))

        assert proc._update_remotely(self._pair(), False) is False

        proc.local.delete_final.assert_not_called()

    def test_a_row_deleted_meanwhile_aborts(self):
        proc = self._proc(None)

        assert proc._update_remotely(self._pair(), False) is False

        proc.local.delete_final.assert_not_called()

    def test_an_undisturbed_row_is_still_replaced(self):
        proc = self._proc(_pair(version=3, pair_state="remotely_modified"))

        assert proc._update_remotely(self._pair(), False) is True

        proc.local.delete_final.assert_called_once()

    def test_no_conflict_is_raised_for_a_decision_already_taken(self):
        """The user settled it; re-parking would hand it back to them."""
        proc = self._proc(_pair(version=3, pair_state="locally_resolved"))

        proc._update_remotely(self._pair(), False)

        proc._mark_conflicted.assert_not_called()


class TestLockParkKeepsThePendingOperation:
    """A server lock is temporary. Resuming a move as a modification runs the
    content handler, which never calls the server's move API -- the rename is
    marked synchronised and silently lost."""

    def test_a_move_keeps_its_local_state_while_parked(self):
        proc = _processor()
        pair = _pair(local_state="moved", pair_state="locally_moved")

        proc._mark_locked_on_server(pair, "alice")

        assert proc.dao._force_sync.call_args.args[1] == "moved"

    def test_an_edit_is_parked_as_before(self):
        proc = _processor()
        pair = _pair(local_state="modified", pair_state="locally_modified")

        proc._mark_locked_on_server(pair, "alice")

        assert proc.dao._force_sync.call_args.args[1] == "modified"

    def test_other_conflicts_still_normalise_the_local_state(self):
        """Only a temporary park has something to hand back."""
        proc = _processor()

        proc._mark_conflicted(_pair(local_state="moved"), reason=DIFFERENT_CONTENT)

        assert proc.dao._force_sync.call_args.args[1] == "modified"

    def test_a_released_move_goes_back_to_the_move_handler(self):
        watcher = _watcher()
        pair = _pair(pair_state="conflicted", local_state="moved")

        watcher._release_lock_conflict(pair)

        args = watcher.dao.force_sync_if_conflicted.call_args.args
        assert args[1:] == ("moved", "synchronized", "locally_moved")

    def test_a_released_edit_goes_back_to_the_content_handler(self):
        watcher = _watcher()
        pair = _pair(pair_state="conflicted", local_state="modified")

        watcher._release_lock_conflict(pair)

        args = watcher.dao.force_sync_if_conflicted.call_args.args
        assert args[1:] == ("modified", "synchronized", "locally_modified")


class TestResolveWithRemoteIsNotOnTheGuiThread:
    """`api.py` calls this straight from a slot, and hashing reads the whole
    file. It also has to survive a paused engine: the shared client's digest
    callback aborts then, which would skip the baseline and restart the loop."""

    def _engine(self, **overrides):
        engine = _engine()
        info = MagicMock()
        info.get_digest.return_value = overrides.get("digest", "on-disk-now")
        engine.local.get_info.return_value = info
        engine.dao.get_state_from_id.return_value = _pair(
            local_digest="recorded-earlier"
        )
        return engine, info

    def test_the_hash_is_not_taken_on_the_calling_thread(self):
        engine, _ = self._engine()

        with patch("nxdrive.alfresco.engine.engine.QThreadPool") as pool, patch.object(
            AlfrescoEngine.__bases__[0], "resolve_with_remote"
        ):
            engine.resolve_with_remote(1)

        pool.globalInstance.return_value.start.assert_called_once()
        engine.local.get_info.assert_not_called()

    def test_the_pause_callback_is_cleared_for_this_read(self):
        """``suspend_client`` raises while paused, which would skip the
        baseline write and leave the resolution to loop on resume."""
        engine, info = self._engine()

        with patch.object(AlfrescoEngine.__bases__[0], "resolve_with_remote"):
            engine._acknowledge_local_bytes(1)

        assert info.digest_callback is None
        engine.dao.update_local_digest.assert_called_once()

    def test_the_shared_client_is_left_alone(self):
        """Clearing it on the client would disarm every background hash."""
        engine, _ = self._engine()
        before = engine.local.digest_callback

        with patch.object(AlfrescoEngine.__bases__[0], "resolve_with_remote"):
            engine._acknowledge_local_bytes(1)

        assert engine.local.digest_callback is before

    def test_a_choice_made_while_hashing_wins(self):
        engine, _ = self._engine()
        engine.dao.get_state_from_id.side_effect = [
            _pair(pair_state="conflicted"),
            _pair(pair_state="locally_resolved"),
        ]

        with patch.object(AlfrescoEngine.__bases__[0], "resolve_with_remote") as base:
            engine._acknowledge_local_bytes(1)

        base.assert_not_called()

    def test_an_unreadable_file_still_resolves(self):
        engine, _ = self._engine()
        engine.local.get_info.side_effect = OSError("gone")

        with patch.object(AlfrescoEngine.__bases__[0], "resolve_with_remote") as base:
            engine._acknowledge_local_bytes(1)

        engine.dao.update_local_digest.assert_not_called()
        base.assert_called_once_with(1)


class TestAdoptionBindsTheXattr:
    """The watcher leaves the xattr unset for an independently created file,
    and ``_synchronize_remotely_deleted`` refuses to delete anything whose
    xattr does not name the node. Adopting without it strands the file."""

    def _engine_matching(self):
        engine = _engine()
        engine.local.abspath.return_value = MagicMock(is_file=lambda: True)
        return engine

    def test_the_file_is_bound_before_it_is_adopted(self):
        engine = self._engine_matching()
        pair = _pair(last_sync_date=None)
        engine.dao.get_state_from_id.return_value = pair

        with patch("nxdrive.alfresco.engine.engine.content_matches", return_value=True):
            engine._decide_conflict(1)

        engine.local.set_remote_id.assert_called_once_with(
            pair.local_path, pair.remote_ref
        )
        engine.dao.synchronize_state.assert_called_once()

    def test_a_failed_binding_keeps_the_conflict(self):
        """Adopting anyway is what leaves the file behind on deletion."""
        engine = self._engine_matching()
        engine.dao.get_state_from_id.return_value = _pair(last_sync_date=None)
        engine.local.set_remote_id.side_effect = OSError("no xattr")

        with patch("nxdrive.alfresco.engine.engine.content_matches", return_value=True):
            engine._decide_conflict(1)

        engine.dao.synchronize_state.assert_not_called()
        engine.newConflict.emit.assert_called_once_with(1)


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

        watcher.dao.force_sync_if_conflicted.assert_called_once_with(
            pair,
            "modified",
            "synchronized",
            "locally_modified",
            expected_last_error=LOCKED_ON_SERVER,
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

        watcher.dao.force_sync_if_conflicted.assert_called_once_with(
            second,
            "modified",
            "synchronized",
            "locally_modified",
            expected_last_error=LOCKED_ON_SERVER,
        )


class TestShutdownIsNotSwallowed:
    """``ThreadInterrupt`` is an ``Exception``, and ``_interact()`` raises it
    to ask the worker to stop. A broad handler that keeps it turns a stop into
    a logged failure followed by more network work."""

    def _watcher_at_the_post_poll_blocks(self):
        watcher = _watcher()
        watcher.engine.remote = MagicMock()
        watcher._ensure_provisioned = MagicMock(return_value=True)
        watcher._bootstrap_if_needed = MagicMock(return_value=True)
        watcher._apply_unfiltered = MagicMock()
        watcher._poll_device_sync = MagicMock(return_value=True)
        watcher._scan_local_changes = MagicMock()
        watcher._sweep_lock_conflicts = MagicMock()
        watcher.engine.queue_manager.get_overall_size.return_value = 0
        watcher.empty_polls = 0
        watcher.dao.get_config.return_value = None
        watcher.updated = MagicMock()
        return watcher

    @pytest.mark.parametrize(
        "blocking",
        ("_scan_local_changes", "_sweep_lock_conflicts"),
    )
    def test_a_stop_request_travels_out_of_the_post_poll_blocks(self, blocking):
        watcher = self._watcher_at_the_post_poll_blocks()
        getattr(watcher, blocking).side_effect = ThreadInterrupt

        with pytest.raises(ThreadInterrupt):
            watcher._do_handle_changes(False)

    def test_a_stop_during_the_scan_skips_the_remaining_network_work(self):
        watcher = self._watcher_at_the_post_poll_blocks()
        watcher._scan_local_changes.side_effect = ThreadInterrupt

        with pytest.raises(ThreadInterrupt):
            watcher._do_handle_changes(False)

        watcher._sweep_lock_conflicts.assert_not_called()
        watcher.engine.resolve_deferred_conflicts.assert_not_called()

    def test_an_ordinary_failure_is_still_absorbed(self):
        """Only the stop travels; a real error must not kill the poll loop."""
        watcher = self._watcher_at_the_post_poll_blocks()
        watcher._sweep_lock_conflicts.side_effect = OSError("boom")

        watcher._do_handle_changes(False)

        watcher.engine.resolve_deferred_conflicts.assert_called_once()


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

    def test_a_file_that_vanishes_during_the_server_reads_is_unknown(self, tmp_path):
        """The remote range requests take seconds, and the contract promises
        ``None`` for a local file that cannot be read -- callers rely on that
        to take their safe path rather than having the error thrown at them."""
        local = tmp_path / "file.txt"
        local.write_bytes(b"hello")
        remote = MagicMock()

        def _delete_then_answer(*_args, **_kwargs):
            local.unlink(missing_ok=True)
            return b"hello"

        remote.get_content_range.side_effect = _delete_then_answer

        assert content_matches(remote, local, "node-1", remote_size=5) is None

    def test_a_file_appended_to_while_hashing_is_unknown(self, tmp_path):
        """The size doubles as the tail offset and was measured before the
        remote reads, so an append is hashed at the old offset and simply not
        looked at -- the two windows then match."""
        local = tmp_path / "file.txt"
        local.write_bytes(b"hello")
        remote = MagicMock()

        def _append_then_answer(*_args, **_kwargs):
            local.write_bytes(b"hello-and-more")
            return b"hello"

        remote.get_content_range.side_effect = _append_then_answer

        assert content_matches(remote, local, "node-1", remote_size=5) is None

    def test_a_stable_file_is_still_compared(self, tmp_path):
        local = tmp_path / "file.txt"
        local.write_bytes(b"hello")
        remote = MagicMock()
        remote.get_content_range.return_value = b"hello"

        assert content_matches(remote, local, "node-1", remote_size=5) is True

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
