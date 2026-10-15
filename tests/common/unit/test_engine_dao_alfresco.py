"""Schema and DAO behaviour added for Alfresco conflict detection (NXDRIVE-3287).

Two things must hold for the Nuxeo engine to stay unaffected:

* ``update_remote_state`` keeps its old behaviour unless ``no_baseline`` is
  explicitly asked for;
* ``_force_sync`` clears the conflict reason unless one is passed, so the Nuxeo
  engine, which never passes one, behaves exactly as before.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from nxdrive.drive.dao.engine import EngineDAO
from nxdrive.drive.objects import RemoteFileInfo

OLD_TIME = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
NEW_TIME = datetime(2025, 6, 7, 8, 9, 10, tzinfo=timezone.utc)


@pytest.fixture()
def dao(tmp_path):
    instance = EngineDAO(tmp_path / "engine-alfresco.db")
    try:
        yield instance
    finally:
        instance.dispose()


def _info(*, name="file.txt", modified=NEW_TIME, is_locked=False):
    return RemoteFileInfo(
        name=name,
        uid="node-1",
        parent_uid="parent-1",
        path=f"/{name}",
        folderish=False,
        last_modification_time=modified,
        creation_time=OLD_TIME,
        last_contributor="alice",
        digest=None,
        digest_algorithm=None,
        download_url=None,
        can_rename=True,
        can_delete=True,
        can_update=True,
        can_create_child=False,
        lock_owner=None,
        lock_created=None,
        can_scroll_descendants=False,
        is_locked=is_locked,
    )


def _insert(dao, **overrides):
    """Create a row through the production insert path and return it."""
    row_id = dao.insert_remote_state(
        _info(**overrides),
        "/remote",
        Path("/sync/file.txt"),
        Path("/sync"),
    )
    return dao.get_state_from_id(row_id)


def _raw(dao, row_id):
    cursor = dao._get_read_connection().cursor()
    return cursor.execute(
        "SELECT last_remote_updated, remote_locked FROM States WHERE id = ?",
        (row_id,),
    ).fetchone()


class TestSchema:
    def test_the_new_column_exists_with_a_safe_default(self, dao):
        pair = _insert(dao)
        assert pair.remote_locked == 0

    def test_the_lock_is_persisted_on_insert(self, dao):
        pair = _insert(dao, is_locked=True)
        assert pair.remote_locked == 1


class TestUpdateRemoteStateBaseline:
    def test_the_baseline_is_refreshed_by_default(self, dao):
        """The Nuxeo engine never passes ``no_baseline`` and must not change."""
        pair = _insert(dao, modified=OLD_TIME)

        dao.update_remote_state(
            pair,
            _info(name="renamed.txt", modified=NEW_TIME),
            remote_parent_path="/remote",
            force_update=True,
        )

        updated, locked = _raw(dao, pair.id)
        assert locked == 0
        assert str(NEW_TIME)[:19] in str(updated)

    def test_no_baseline_keeps_the_timestamp_and_lock(self, dao):
        """Overwriting these makes the server look unchanged against itself."""
        pair = _insert(dao, modified=OLD_TIME)
        before = _raw(dao, pair.id)

        dao.update_remote_state(
            pair,
            _info(name="renamed.txt", modified=NEW_TIME),
            remote_parent_path="/remote",
            no_baseline=True,
        )

        assert _raw(dao, pair.id) == before

    def test_no_baseline_still_applies_a_remote_rename(self, dao):
        pair = _insert(dao)

        dao.update_remote_state(
            pair,
            _info(name="renamed.txt"),
            remote_parent_path="/remote",
            no_baseline=True,
        )

        assert dao.get_state_from_id(pair.id).remote_name == "renamed.txt"


class TestUpdateRemoteNaming:
    """Used for pairs the processor owns, where only a rename may land.

    ``update_remote_state`` matches on ``id`` alone and writes the sync state
    from the caller's copy of the row, so a decision taken after that copy was
    read would be overwritten and the pair requeued for upload.
    """

    def _state(self, dao, row_id):
        cursor = dao._get_read_connection().cursor()
        return cursor.execute(
            "SELECT local_state, remote_state, pair_state, version"
            " FROM States WHERE id = ?",
            (row_id,),
        ).fetchone()

    def test_the_rename_lands(self, dao):
        pair = _insert(dao)

        assert dao.update_remote_naming(
            pair, _info(name="renamed.txt"), remote_parent_path="/elsewhere"
        )

        refreshed = dao.get_state_from_id(pair.id)
        assert refreshed.remote_name == "renamed.txt"
        assert refreshed.remote_parent_path == "/elsewhere"

    def test_a_conflict_raised_in_the_gap_survives(self, dao):
        """The race this method exists for."""
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)
        dao._force_sync(
            dao.get_state_from_id(pair.id),
            "modified",
            "modified",
            "conflicted",
            last_error="REMOTE_DRIFTED",
        )

        dao.update_remote_naming(stale, _info(name="renamed.txt"))

        local, remote, state, _ = self._state(dao, pair.id)
        assert (local, remote, state) == ("modified", "modified", "conflicted")
        assert dao.get_state_from_id(pair.id).remote_name == "renamed.txt"

    def test_the_baseline_is_left_alone(self, dao):
        pair = _insert(dao, modified=OLD_TIME, is_locked=True)
        before = _raw(dao, pair.id)

        dao.update_remote_naming(pair, _info(name="renamed.txt", modified=NEW_TIME))

        assert _raw(dao, pair.id) == before

    def test_the_version_is_not_bumped(self, dao):
        """Bumping it would break the optimistic lock of an in-flight upload."""
        pair = _insert(dao)
        before = self._state(dao, pair.id)[3]

        dao.update_remote_naming(pair, _info(name="renamed.txt"))

        assert self._state(dao, pair.id)[3] == before

    def test_nothing_is_queued(self, dao):
        pair = _insert(dao)
        dao.queue_pair_state = None  # any queueing attempt would raise

        assert dao.update_remote_naming(pair, _info(name="renamed.txt"))

    def test_the_caller_s_row_agrees_with_the_database(self, dao):
        pair = _insert(dao)

        dao.update_remote_naming(
            pair, _info(name="renamed.txt"), remote_parent_path="/elsewhere"
        )

        assert pair.remote_name == "renamed.txt"
        assert pair.remote_parent_path == "/elsewhere"

    def test_a_vanished_row_reports_failure(self, dao):
        pair = _insert(dao)
        dao._get_write_connection().cursor().execute(
            "DELETE FROM States WHERE id = ?", (pair.id,)
        )

        assert dao.update_remote_naming(pair, _info(name="renamed.txt")) is False


class TestSynchronizeStateOnlyIfConflicted:
    """For decisions taken on a copy read before a slow probe.

    ``content_matches`` can read two 10 MB windows, which is long enough for
    the user to resolve the same conflict from the Conflicts panel.
    """

    def _state(self, dao, row_id):
        return dao.get_state_from_id(row_id).pair_state

    def _conflicted(self, dao, **overrides):
        pair = _insert(dao, **overrides)
        dao._force_sync(pair, "modified", "modified", "conflicted")
        return dao.get_state_from_id(pair.id)

    def test_a_still_conflicted_row_is_synchronized(self, dao):
        pair = self._conflicted(dao)

        assert dao.synchronize_state(pair, only_if_conflicted=True)
        assert self._state(dao, pair.id) == "synchronized"

    def test_a_row_resolved_in_the_meantime_is_left_alone(self, dao):
        pair = self._conflicted(dao)
        stale = dao.get_state_from_id(pair.id)
        dao.force_local(dao.get_state_from_id(pair.id))

        assert dao.synchronize_state(stale, only_if_conflicted=True) is False
        assert self._state(dao, pair.id) == "locally_resolved"

    def test_a_folder_does_not_fall_back_to_an_unguarded_write(self, dao):
        """The fallback drops the version guard, which is the whole point."""
        pair = self._conflicted(dao, name="folder")
        pair.folderish = True
        dao.force_local(dao.get_state_from_id(pair.id))

        assert dao.synchronize_state(pair, only_if_conflicted=True) is False
        assert self._state(dao, pair.id) == "locally_resolved"

    def test_the_default_keeps_the_nuxeo_behaviour(self, dao):
        """Nuxeo never passes the flag and must be able to leave a conflict."""
        pair = self._conflicted(dao)

        assert dao.synchronize_state(dao.get_state_from_id(pair.id))
        assert self._state(dao, pair.id) == "synchronized"

    def test_the_default_still_retries_unversioned_for_a_folder(self, dao):
        pair = _insert(dao, name="folder")
        pair.folderish = True
        stale_version = pair.version + 5
        pair.version = stale_version

        assert dao.synchronize_state(pair)
        assert self._state(dao, pair.id) == "synchronized"


class TestForceSyncIfConflictedAbsentReason:
    """``None`` is the reason of an unreasoned conflict, so it has to mean
    "still has no reason" rather than "do not check the reason"."""

    def _conflicted(self, dao, *, reason=None):
        pair = _insert(dao)
        dao._force_sync(pair, "modified", "modified", "conflicted", last_error=reason)
        return dao.get_state_from_id(pair.id)

    def test_an_unreasoned_conflict_qualifies(self, dao):
        pair = self._conflicted(dao)

        assert dao.force_sync_if_conflicted(
            pair,
            "modified",
            "synchronized",
            "locally_modified",
            expected_last_error=None,
        )
        assert dao.get_state_from_id(pair.id).pair_state == "locally_modified"

    def test_a_reason_raised_in_the_gap_is_refused(self, dao):
        """The data-loss case: a processor parks the row while the resolver is
        probing the server, and the resolver then clears the park."""
        pair = self._conflicted(dao, reason="LOCKED_ON_SERVER")

        released = dao.force_sync_if_conflicted(
            pair,
            "modified",
            "synchronized",
            "locally_modified",
            expected_last_error=None,
        )

        assert released is False
        row = dao.get_state_from_id(pair.id)
        assert (row.pair_state, row.last_error) == ("conflicted", "LOCKED_ON_SERVER")

    def test_a_resolved_row_is_still_refused(self, dao):
        pair = self._conflicted(dao)
        dao.force_local(dao.get_state_from_id(pair.id))

        assert (
            dao.force_sync_if_conflicted(
                pair,
                "modified",
                "synchronized",
                "locally_modified",
                expected_last_error=None,
            )
            is False
        )
        assert dao.get_state_from_id(pair.id).pair_state == "locally_resolved"

    def test_the_argument_cannot_be_omitted(self, dao):
        """No default, so "accept any reason" cannot creep back in."""
        pair = self._conflicted(dao)

        with pytest.raises(TypeError):
            dao.force_sync_if_conflicted(
                pair, "modified", "synchronized", "locally_modified"
            )


class TestUpdateRemoteStateExpectedVersion:
    """For callers that decided on a copy read before a slow probe."""

    def test_a_matching_version_is_written(self, dao):
        pair = _insert(dao)

        assert dao.update_remote_state(
            pair,
            _info(name="renamed.txt"),
            remote_parent_path="/remote",
            force_update=True,
            expected_version=pair.version,
        )
        assert dao.get_state_from_id(pair.id).remote_name == "renamed.txt"

    def test_a_row_that_moved_on_is_refused(self, dao):
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)
        # Anything that bumps the version, e.g. the local scanner claiming it.
        dao.update_remote_state(
            dao.get_state_from_id(pair.id), _info(name="other.txt"), force_update=True
        )

        assert (
            dao.update_remote_state(
                stale,
                _info(name="renamed.txt"),
                remote_parent_path="/remote",
                force_update=True,
                expected_version=stale.version,
            )
            is False
        )
        assert dao.get_state_from_id(pair.id).remote_name == "other.txt"

    def test_the_default_writes_without_a_version_guard(self, dao):
        """Nuxeo never passes it and must keep today's behaviour."""
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)
        stale.version += 5

        assert dao.update_remote_state(
            stale, _info(name="renamed.txt"), force_update=True
        )
        assert dao.get_state_from_id(pair.id).remote_name == "renamed.txt"


class TestUpdateRemoteStateExpectedPairState:
    """``_force_sync`` leaves ``version`` alone, so a conflict raised after the
    caller's read still satisfies the version predicate on its own."""

    def test_a_conflict_raised_in_the_gap_is_refused(self, dao):
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)
        dao.set_conflict_state(dao.get_state_from_id(pair.id))

        refused = dao.update_remote_state(
            stale,
            _info(name="renamed.txt"),
            remote_parent_path="/remote",
            force_update=True,
            expected_version=stale.version,
            expected_pair_state=stale.pair_state,
        )

        assert refused is False
        assert dao.get_state_from_id(pair.id).pair_state == "conflicted"

    def test_an_unchanged_state_is_written(self, dao):
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)

        assert dao.update_remote_state(
            stale,
            _info(name="renamed.txt"),
            remote_parent_path="/remote",
            force_update=True,
            expected_version=stale.version,
            expected_pair_state=stale.pair_state,
        )
        assert dao.get_state_from_id(pair.id).remote_name == "renamed.txt"

    def test_the_default_writes_without_a_state_guard(self, dao):
        """Nuxeo never passes it and must keep today's behaviour."""
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)
        dao.set_conflict_state(dao.get_state_from_id(pair.id))

        assert dao.update_remote_state(
            stale, _info(name="renamed.txt"), force_update=True
        )
        assert dao.get_state_from_id(pair.id).remote_name == "renamed.txt"


class TestSynchronizeStateExpectedPairState:
    """The baseline write and the synchronised transition are two statements.

    Nothing bumps ``version`` in between, so only the state the first write
    committed can tell the second one that a conflict landed in the gap.
    """

    def test_a_conflict_raised_in_the_gap_is_not_cleared(self, dao):
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)
        dao.set_conflict_state(dao.get_state_from_id(pair.id))

        assert (
            dao.synchronize_state(stale, expected_pair_state=stale.pair_state) is False
        )
        assert dao.get_state_from_id(pair.id).pair_state == "conflicted"

    def test_an_unchanged_state_is_synchronized(self, dao):
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)

        assert dao.synchronize_state(stale, expected_pair_state=stale.pair_state)
        assert dao.get_state_from_id(pair.id).pair_state == "synchronized"

    def test_a_folder_does_not_fall_back_to_an_unguarded_write(self, dao):
        """The fallback drops the version guard, which would defeat the point."""
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)
        stale.folderish = True
        dao.set_conflict_state(dao.get_state_from_id(pair.id))

        assert (
            dao.synchronize_state(stale, expected_pair_state=stale.pair_state) is False
        )
        assert dao.get_state_from_id(pair.id).pair_state == "conflicted"

    def test_the_default_synchronizes_without_a_state_guard(self, dao):
        """Nuxeo never passes it and must keep today's behaviour."""
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)
        dao.set_conflict_state(dao.get_state_from_id(pair.id))

        assert dao.synchronize_state(stale)
        assert dao.get_state_from_id(pair.id).pair_state == "synchronized"


class TestForceRemoteExpectedPairState:
    """``force_remote`` clears ``last_error``, so an unguarded one erases the
    reason a conflict was raised for."""

    def test_a_conflict_raised_in_the_gap_is_not_overwritten(self, dao):
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)
        dao.set_conflict_state(dao.get_state_from_id(pair.id))

        assert dao.force_remote(stale, expected_pair_state=stale.pair_state) is False
        assert dao.get_state_from_id(pair.id).pair_state == "conflicted"

    def test_a_refused_write_is_not_queued(self, dao):
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)
        dao.set_conflict_state(dao.get_state_from_id(pair.id))
        dao.queue_manager = Mock()

        dao.force_remote(stale, expected_pair_state=stale.pair_state)

        dao.queue_manager.push_ref.assert_not_called()

    def test_an_unchanged_state_is_forced(self, dao):
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)

        assert dao.force_remote(stale, expected_pair_state=stale.pair_state)
        assert dao.get_state_from_id(pair.id).pair_state == "remotely_modified"

    def test_the_default_forces_without_a_state_guard(self, dao):
        """Nuxeo never passes it and must keep today's behaviour."""
        pair = _insert(dao)
        stale = dao.get_state_from_id(pair.id)
        dao.set_conflict_state(dao.get_state_from_id(pair.id))

        assert dao.force_remote(stale)
        assert dao.get_state_from_id(pair.id).pair_state == "remotely_modified"


class TestForceSyncClearsTheRemoteDigest:
    """A digest invalidated by the flip must not be readable after it."""

    def _digest(self, dao, row_id):
        cursor = dao._get_read_connection().cursor()
        return cursor.execute(
            "SELECT remote_digest FROM States WHERE id = ?", (row_id,)
        ).fetchone()[0]

    def _with_digest(self, dao):
        pair = _insert(dao)
        cursor = dao._get_write_connection().cursor()
        cursor.execute(
            "UPDATE States SET remote_digest = ? WHERE id = ?", ("OURUPLOAD", pair.id)
        )
        return dao.get_state_from_id(pair.id)

    def test_the_digest_dies_with_the_conflict(self, dao):
        pair = self._with_digest(dao)

        dao._force_sync(
            pair, "modified", "modified", "conflicted", clear_remote_digest=True
        )

        assert self._digest(dao, pair.id) is None
        # The caller keeps using this row, so it must agree with the database.
        assert pair.remote_digest is None

    def test_a_refused_flip_leaves_the_digest_alone(self, dao):
        """Nothing was invalidated, because nothing was decided."""
        pair = self._with_digest(dao)
        stale = dao.get_state_from_id(pair.id)
        stale.version += 1

        dao._force_sync(
            stale, "modified", "modified", "conflicted", clear_remote_digest=True
        )

        assert self._digest(dao, pair.id) == "OURUPLOAD"

    def test_the_default_keeps_it(self, dao):
        """Nuxeo never asks for this and must keep today's behaviour."""
        pair = self._with_digest(dao)

        dao._force_sync(pair, "modified", "modified", "conflicted")

        assert self._digest(dao, pair.id) == "OURUPLOAD"


class TestUpdateLocalDigest:
    """Acknowledging the bytes on disk, without claiming anything else."""

    def test_only_the_digest_moves(self, dao):
        pair = _insert(dao)
        before = dao.get_state_from_id(pair.id)

        dao.update_local_digest(pair, "on-disk-now")

        after = dao.get_state_from_id(pair.id)
        assert after.local_digest == "on-disk-now"
        assert pair.local_digest == "on-disk-now"
        assert (after.pair_state, after.version) == (before.pair_state, before.version)


class TestClearRemoteDigest:
    """A digest we can no longer vouch for must not pass as the server's."""

    def _digest(self, dao, row_id):
        cursor = dao._get_read_connection().cursor()
        return cursor.execute(
            "SELECT remote_digest FROM States WHERE id = ?", (row_id,)
        ).fetchone()[0]

    def test_the_stored_digest_is_removed(self, dao):
        pair = _insert(dao)
        cursor = dao._get_write_connection().cursor()
        cursor.execute(
            "UPDATE States SET remote_digest = ? WHERE id = ?", ("OURUPLOAD", pair.id)
        )

        dao.clear_remote_digest(pair)

        assert self._digest(dao, pair.id) is None
        # The caller keeps using this row, so it must agree with the database.
        assert pair.remote_digest is None

    def test_clearing_an_already_empty_digest_is_harmless(self, dao):
        pair = _insert(dao)
        dao.clear_remote_digest(pair)
        assert self._digest(dao, pair.id) is None

    def test_nothing_else_about_the_row_changes(self, dao):
        pair = _insert(dao, is_locked=True)

        dao.clear_remote_digest(pair)

        refreshed = dao.get_state_from_id(pair.id)
        assert refreshed.remote_locked == 1
        assert refreshed.remote_ref == "node-1"
        assert refreshed.pair_state == pair.pair_state


class TestForceSyncReason:
    """``_force_sync`` also fires ``newConflict``.

    A resolver woken by that signal must never find the conflict without the
    reason that justifies it, so the two have to land in one statement.
    """

    def _row(self, dao, row_id):
        cursor = dao._get_read_connection().cursor()
        return cursor.execute(
            "SELECT pair_state, last_error, last_error_details, error_count "
            "FROM States WHERE id = ?",
            (row_id,),
        ).fetchone()

    def test_the_reason_lands_with_the_state_flip(self, dao):
        pair = _insert(dao)

        assert dao._force_sync(
            pair,
            "modified",
            "modified",
            "conflicted",
            last_error="LOCKED_ON_SERVER",
            last_error_details="admin",
        )

        state, error, details, count = self._row(dao, pair.id)
        assert state == "conflicted"
        assert error == "LOCKED_ON_SERVER"
        assert details == "admin"
        # Still a conflict, not an error.
        assert count == 0
        assert pair.last_error == "LOCKED_ON_SERVER"

    def test_omitting_the_reason_clears_it_as_before(self, dao):
        """The Nuxeo engine never passes one and must keep the old behaviour."""
        pair = _insert(dao)
        dao._get_write_connection().cursor().execute(
            "UPDATE States SET last_error = ?, last_error_details = ? WHERE id = ?",
            ("SOMETHING_OLD", "stale", pair.id),
        )

        assert dao._force_sync(pair, "synchronized", "modified", "remotely_modified")

        _, error, details, _ = self._row(dao, pair.id)
        assert error is None
        assert details is None


class TestForceSyncIfConflicted:
    """``_force_sync`` never bumps ``version``, so its lock cannot separate
    two concurrent flips. The reason has to be part of the condition.
    """

    def _conflicted(self, dao, *, reason="LOCKED_ON_SERVER"):
        pair = _insert(dao)
        dao._force_sync(pair, "modified", "modified", "conflicted", last_error=reason)
        return dao.get_state_from_id(pair.id)

    def _state(self, dao, row_id):
        row = dao.get_state_from_id(row_id)
        return row.pair_state, row.last_error

    def test_a_matching_row_is_released(self, dao):
        pair = self._conflicted(dao)

        released = dao.force_sync_if_conflicted(
            pair,
            "modified",
            "synchronized",
            "locally_modified",
            expected_last_error="LOCKED_ON_SERVER",
        )

        assert released is True
        assert self._state(dao, pair.id) == ("locally_modified", None)
        assert pair.last_error is None

    def test_a_different_reason_is_refused(self, dao):
        pair = self._conflicted(dao, reason="DIFFERENT_CONTENT")

        released = dao.force_sync_if_conflicted(
            pair,
            "modified",
            "synchronized",
            "locally_modified",
            expected_last_error="LOCKED_ON_SERVER",
        )

        assert released is False
        assert self._state(dao, pair.id) == ("conflicted", "DIFFERENT_CONTENT")

    def test_a_row_resolved_in_the_meantime_is_refused(self, dao):
        """What the lock sweep races against: the user clicking "use mine"."""
        pair = self._conflicted(dao)
        dao.force_local(dao.get_state_from_id(pair.id))

        released = dao.force_sync_if_conflicted(
            pair,
            "modified",
            "synchronized",
            "locally_modified",
            expected_last_error="LOCKED_ON_SERVER",
        )

        assert released is False
        assert self._state(dao, pair.id)[0] == "locally_resolved"

    def test_a_stale_version_is_still_refused(self, dao):
        pair = self._conflicted(dao)
        stale = dao.get_state_from_id(pair.id)
        stale.version += 1

        assert (
            dao.force_sync_if_conflicted(
                stale,
                "modified",
                "synchronized",
                "locally_modified",
                expected_last_error="LOCKED_ON_SERVER",
            )
            is False
        )
