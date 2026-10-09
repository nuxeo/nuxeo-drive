"""Schema and DAO behaviour added for Alfresco conflict detection (NXDRIVE-3287).

Two things must hold for the Nuxeo engine to stay unaffected:

* ``update_remote_state`` keeps its old behaviour unless ``no_baseline`` is
  explicitly asked for;
* ``set_last_error`` records a reason without inflating ``error_count``, so the
  row stays in the Conflicts list instead of moving to Errors.
"""

from datetime import datetime, timezone
from pathlib import Path

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


def _info(*, name="file.txt", modified=NEW_TIME, version_label="", is_locked=False):
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
        version_label=version_label,
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
        "SELECT last_remote_updated, remote_version, remote_locked "
        "FROM States WHERE id = ?",
        (row_id,),
    ).fetchone()


class TestSchema:
    def test_the_new_columns_exist_with_safe_defaults(self, dao):
        pair = _insert(dao)
        assert pair.remote_version == ""
        assert pair.remote_locked == 0

    def test_version_and_lock_are_persisted_on_insert(self, dao):
        pair = _insert(dao, version_label="1.3", is_locked=True)
        assert pair.remote_version == "1.3"
        assert pair.remote_locked == 1


class TestUpdateRemoteStateBaseline:
    def test_the_baseline_is_refreshed_by_default(self, dao):
        """The Nuxeo engine never passes ``no_baseline`` and must not change."""
        pair = _insert(dao, version_label="1.0")

        dao.update_remote_state(
            pair,
            _info(name="renamed.txt", version_label="1.1", modified=NEW_TIME),
            remote_parent_path="/remote",
            force_update=True,
        )

        updated, version, locked = _raw(dao, pair.id)
        assert version == "1.1"
        assert locked == 0
        assert str(NEW_TIME)[:19] in str(updated)

    def test_no_baseline_keeps_the_version_timestamp_and_lock(self, dao):
        """Overwriting these makes the server look unchanged against itself."""
        pair = _insert(dao, version_label="1.0", modified=OLD_TIME)
        before = _raw(dao, pair.id)

        dao.update_remote_state(
            pair,
            _info(name="renamed.txt", version_label="9.9", modified=NEW_TIME),
            remote_parent_path="/remote",
            no_baseline=True,
        )

        assert _raw(dao, pair.id) == before

    def test_no_baseline_still_applies_a_remote_rename(self, dao):
        pair = _insert(dao, version_label="1.0")

        dao.update_remote_state(
            pair,
            _info(name="renamed.txt", version_label="9.9"),
            remote_parent_path="/remote",
            no_baseline=True,
        )

        assert dao.get_state_from_id(pair.id).remote_name == "renamed.txt"


class TestSetLastError:
    def test_a_reason_is_recorded_without_counting_an_error(self, dao):
        pair = _insert(dao)

        dao.set_last_error(pair, "LOCKED_ON_SERVER", details="admin")

        refreshed = dao.get_state_from_id(pair.id)
        assert refreshed.last_error == "LOCKED_ON_SERVER"
        assert refreshed.last_error_details == "admin"
        # An inflated count would move the row from Conflicts to Errors.
        assert refreshed.error_count == 0


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
        pair = _insert(dao, version_label="1.3")

        dao.clear_remote_digest(pair)

        refreshed = dao.get_state_from_id(pair.id)
        assert refreshed.remote_version == "1.3"
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
        dao.set_last_error(pair, "SOMETHING_OLD", details="stale")

        assert dao._force_sync(pair, "synchronized", "modified", "remotely_modified")

        _, error, details, _ = self._row(dao, pair.id)
        assert error is None
        assert details is None
