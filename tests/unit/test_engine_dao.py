import os
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from nxdrive.constants import TransferStatus
from nxdrive.dao.migrations.migration import MigrationInterface

from ..markers import windows_only


def test_acquire_processors(engine_dao):
    with engine_dao("engine_migration.db") as dao:
        assert dao.acquire_processor(666, 2)

        # Cannot acquire processor if different processor
        assert not dao.acquire_processor(777, 2)

        # Can re-acquire processor if same processor
        assert dao.acquire_processor(666, 2)
        assert dao.release_processor(666)

        # Check the auto-release
        assert dao.acquire_processor(666, 2)
        row = dao.get_state_from_id(2)
        dao.synchronize_state(row)
        assert not dao.release_processor(666)


def test_batch_folder_files(engine_dao):
    """Verify that the batch is ok."""
    with engine_dao("engine_migration.db") as dao:
        ids = range(25, 47)
        index = 0
        state = dao.get_state_from_id(25)  # ids[index])

        while index < len(ids) - 1:
            index += 1
            state = dao.get_next_folder_file(state.remote_ref)
            assert state.id == ids[index]

        while index > 0:
            index -= 1
            state = dao.get_previous_folder_file(state.remote_ref)
            assert state.id == ids[index]

        assert dao.get_previous_folder_file(state.remote_ref) is None

        # Last file is 9
        state = dao.get_state_from_id(46)
        assert dao.get_next_folder_file(state.remote_ref) is None


def test_batch_upload_files(engine_dao):
    """Verify that the batch is ok."""
    with engine_dao("engine_migration.db") as dao:
        ids = [58, 62, 61, 60, 63]
        index = 0
        state = dao.get_state_from_id(ids[index])

        while index < len(ids) - 1:
            index += 1
            state = dao.get_next_sync_file(state.remote_ref, "upload")
            assert state.id == ids[index]

        while index > 0:
            index -= 1
            state = dao.get_previous_sync_file(state.remote_ref, "upload")
            assert state.id == ids[index]

        assert dao.get_previous_sync_file(state.remote_ref, "upload") is None

        # Last file is 9
        state = dao.get_state_from_id(9)
        assert dao.get_next_sync_file(state.remote_ref, "upload") is None


def test_configuration_get(engine_dao):
    with engine_dao("engine_migration.db") as dao:
        result = dao.get_config("empty", default="DefaultValue")
        assert result == "DefaultValue"

        result = dao.get_config("remote_user", default="DefaultValue")
        assert result == "Administrator"

        dao.update_config("empty", "notAnymore")
        result = dao.get_config("empty", default="DefaultValue")
        assert result != "DefaultValue"
        dao.update_config("remote_user", "Test")
        result = dao.get_config("remote_user", default="DefaultValue")
        assert result == "Test"

        dao.update_config("empty", None)
        result = dao.get_config("empty", default="DefaultValue")
        assert result == "DefaultValue"

        result = dao.get_config("empty")
        assert result is None


def test_configuration_get_bool(engine_dao):
    with engine_dao("engine_migration.db") as dao:
        # Boolean parameter set to True
        name = "something"
        dao.store_bool(name, True)
        assert dao.get_bool(name) is True
        assert dao.get_bool(name, default=True) is True
        assert dao.get_bool(name, default=False) is True
        assert dao.get_bool(name, default="nothing") is True

        # Boolean parameter set to False
        dao.store_bool(name, False)
        assert dao.get_bool(name) is False
        assert dao.get_bool(name, default=True) is False
        assert dao.get_bool(name, default=False) is False
        assert dao.get_bool(name, default="nothing") is False

        # Unknown parameter
        assert dao.get_bool("unk") is False
        assert dao.get_bool("unk", default="string") is False
        assert dao.get_bool("unk", default=True) is True
        assert dao.get_bool("unk", default=0) is False
        assert dao.get_bool("unk", default=1) is True

        # Mimic old behavior to ensure no regression

        dao.store_int("web_authentication", 0)
        res = dao.get_config("web_authentication", default="0") == "1"
        assert not res
        assert dao.get_bool("web_authentication") is res

        dao.store_int("web_authentication", 1)
        res = dao.get_config("web_authentication", default="0") == "1"
        assert res
        assert dao.get_bool("web_authentication") is res

        res = dao.get_config("ssl_verify", default="1") != "0"
        assert res
        assert dao.get_bool("ssl_verify", default=True) is res

        is_frozen = True  # False value for Options.is_frozen
        res = (
            dao.get_config("direct_edit_auto_lock", default=str(int(is_frozen))) == "1"
        )
        assert res
        assert dao.get_bool("direct_edit_auto_lock", default=is_frozen) is res

        is_frozen = False  # False value for Options.is_frozen
        res = (
            dao.get_config("direct_edit_auto_lock", default=str(int(is_frozen))) == "1"
        )
        assert not res
        assert dao.get_bool("direct_edit_auto_lock", default=is_frozen) is res

        res = dao.get_config("light_icons") == "1"
        assert not res
        assert dao.get_bool("light_icons") is res


def test_configuration_get_int(engine_dao):
    with engine_dao("engine_migration.db") as dao:
        # Boolean parameter set to True
        name = "something"
        dao.store_int(name, 42)
        assert dao.get_int(name) == 42
        assert dao.get_int(name, default=-42) == 42
        assert dao.get_int(name, default=0) == 42
        assert dao.get_int(name, default="nothing") == 42

        # Boolean parameter set to False
        dao.store_int(name, -42)
        assert dao.get_int(name) == -42
        assert dao.get_int(name, default=42) == -42
        assert dao.get_int(name, default=0) == -42
        assert dao.get_int(name, default="nothing") == -42

        # Unknown parameter
        assert dao.get_int("unk") == 0
        assert dao.get_int("unk", default="string") == 0
        assert dao.get_int("unk", default=False) == 0
        assert dao.get_int("unk", default=True) == 1
        assert dao.get_int("unk", default=1) == 1

        # Mimic old behavior to ensure no regression

        res = int(dao.get_config("remote_last_sync_date", default=0))
        assert res == 1_427_818_905_000
        assert dao.get_int("remote_last_sync_date") == res

        dao.delete_config("remote_last_sync_date")
        res = int(dao.get_config("remote_last_sync_date", default=0))
        assert res == 0
        assert dao.get_int("remote_last_sync_date") == res


def test_conflicts(engine_dao):
    with engine_dao("engine_migration.db") as dao:
        assert dao.get_conflict_count() == 3
        assert len(dao.get_conflicts()) == 3


def test_corrupted_database(engine_dao):
    """DatabaseError: database disk image is malformed."""
    with engine_dao("corrupted_database.db") as dao:
        c = dao._get_read_connection().cursor()
        cols = c.execute("SELECT * FROM States").fetchall()
        assert len(cols) == 3


def test_errors(engine_dao):
    with engine_dao("engine_migration.db") as dao:
        assert dao.get_error_count() == 1
        assert not dao.get_error_count(threshold=5)
        assert len(dao.get_errors()) == 1
        row = dao.get_errors()[0]

        # Test reset error
        dao.reset_error(row)
        assert not dao.get_error_count()
        row = dao.get_state_from_id(row.id)
        assert row.last_error is None
        assert row.last_error_details is None
        assert not row.error_count

        # Test increase
        dao.increase_error(row, "Test")
        assert not dao.get_error_count()
        dao.increase_error(row, "Test 2")
        assert not dao.get_error_count()
        assert dao.get_error_count(threshold=1) == 1
        dao.increase_error(row, "Test 3")
        assert not dao.get_error_count()
        assert dao.get_error_count(threshold=2) == 1

        # Synchronize with wrong version should fail
        assert not dao.synchronize_state(row, version=row.version - 1)
        assert dao.get_error_count(threshold=2) == 1

        # Synchronize should reset error
        assert dao.synchronize_state(row)
        assert not dao.get_error_count(threshold=2)


def test_filters(engine_dao):
    """Contains by default /fakeFilter/Test_Parent and /fakeFilter/Retest."""
    with engine_dao("engine_migration.db") as dao:
        assert len(dao.get_filters()) == 2

        dao.remove_filter("/fakeFilter/Retest")
        assert len(dao.get_filters()) == 1

        # Should delete the subchild filter
        dao.add_filter("/fakeFilter")
        assert len(dao.get_filters()) == 1

        dao.add_filter("/otherFilter")
        assert len(dao.get_filters()) == 2


def test_reinit_processors(engine_dao):
    with engine_dao("engine_migration.db") as dao:
        state = dao.get_state_from_id(1)
        assert not state.processor


def test_manager_init_db(engine_dao):
    with engine_dao("manager_migration.db") as dao:
        assert not dao.get_filters()
        assert not dao.get_conflicts()
        assert dao.get_config("remote_user") is None
        assert not dao.is_path_scanned("/")


def test_manager_db_init_at_v04(tmp_path, engine_dao):
    """
    Cover the new migration object code.
    Check that the downgrade remove all new tables.
    """
    with sqlite3.connect(":memory:") as conn:
        cursor = conn.cursor()

        # The database is empty
        default_state = cursor.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
        assert not default_state

        # We import the engine_migrations dictionary
        from nxdrive.dao.migrations.manager import manager_migrations

        # New migration 04 should be the first one
        migration = list(manager_migrations.values())[0]

        # We upgrade the database, check the version
        migration.upgrade(cursor)
        assert cursor.execute("PRAGMA user_version").fetchone()[0] == migration.version

        # We downgrade and check that everything has been reverted
        migration.downgrade(cursor)
        downgrade_state = cursor.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
        assert (
            cursor.execute("PRAGMA user_version").fetchone()[0]
            == migration.previous_version
        )
        assert downgrade_state == default_state


def test_last_sync(engine_dao):
    """Based only on file so not showing 2."""
    with engine_dao("engine_migration.db") as dao:
        ids = [58, 8, 62, 61, 60]
        files = dao.get_last_files(5)
        assert len(files) == 5
        for i in range(5):
            assert files[i].id == ids[i]

        ids = [58, 62, 61, 60, 63]
        files = dao.get_last_files(5, direction="remote")
        assert len(files) == 5
        for i in range(5):
            assert files[i].id == ids[i]

        ids = [8, 11, 5]
        files = dao.get_last_files(5, direction="local")
        assert len(files) == 3
        for i in range(3):
            assert files[i].id == ids[i]


def test_dao_register_adapter(engine_dao):
    """Non-regression test for NXDRIVE-2489: ensure local paths do not contain backslashes."""
    local_path = Path(os.path.realpath(__file__))

    with engine_dao("engine_migration_16.db") as dao:
        dao._get_write_connection().row_factory = None
        c = dao._get_write_connection().cursor()

        c.execute(
            "INSERT INTO States "
            "(last_local_updated, local_digest, local_path, "
            "local_parent_path, local_name, folderish, size, "
            "local_state, remote_state, pair_state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'created', 'unknown', ?)",
            (
                datetime.now(),
                "mocked",
                local_path,
                local_path.parent,
                local_path.name,
                False,
                500,
                "unknown",
            ),
        )

        row = c.execute(
            "SELECT local_path, local_parent_path FROM States WHERE id = ?", (3,)
        ).fetchone()
        assert row
        assert "\\" not in row[0]
        assert "\\" not in row[1]


def test_migration_db_v1(engine_dao):
    with engine_dao("engine_migration.db") as dao:
        c = dao._get_read_connection().cursor()

        cols = c.execute("PRAGMA table_info('States')").fetchall()
        assert len(cols) == 33

        cols = c.execute("SELECT * FROM States").fetchall()
        assert len(cols) == 63


def test_migration_db_v1_with_duplicates(engine_dao):
    """Test a non empty DB."""
    with engine_dao("engine_migration_duplicate.db") as dao:
        c = dao._get_read_connection().cursor()
        rows = c.execute("SELECT * FROM States").fetchall()
        assert not rows

        cols = c.execute("PRAGMA table_info('States')").fetchall()
        assert len(cols) == 33
        assert dao.get_config("remote_last_event_log_id") is None
        assert dao.get_config("remote_last_full_scan") is None


@windows_only
def test_migration_db_v8(engine_dao):
    """Verify Downloads.tmpname after migration from v7 to v8."""
    with engine_dao("engine_migration_8.db") as dao:

        for download in dao.get_downloads():
            assert str(download.tmpname).startswith("\\\\?\\")


def test_migration_db_v9(engine_dao):
    """Verify Downloads.path and Uploads.path types after migration."""
    with engine_dao("engine_migration_8.db") as dao:
        downloads = list(dao.get_downloads())
        assert len(downloads) == 1


def test_migration_db_v10(engine_dao):
    """Verify Downloads after migration from v9 to v10."""
    with engine_dao("engine_migration_10.db") as dao:
        downloads = list(dao.get_downloads())
        assert len(downloads) == 0

        states = list(dao.get_states_from_partial_local(Path()))
        assert len(states) == 4

        bad_digest_file = dao.get_state_from_local(
            Path("/Tests Drive/Live Connect/Test document Live Connect")
        )
        assert not bad_digest_file


def test_migration_db_v15(engine_dao):
    """Verify States and Session after migration from v14 to v15."""
    with engine_dao("engine_migration_15.db") as dao:
        local_parent_path = "/home/test/Downloads"

        # There should be only one session
        assert not dao.get_session(0)
        assert not dao.get_session(2)
        last_session = dao.get_session(1)
        assert last_session

        # The 4 dt items should be linked to the session
        doc_pairs = dao.get_local_children(Path(local_parent_path))
        assert len(doc_pairs) == 4
        for pair in doc_pairs:
            assert pair.session == last_session.uid

        # Verify session content
        assert last_session
        assert last_session.status == TransferStatus.ONGOING
        assert last_session.uploaded_items == 0
        assert last_session.total_items == 4


def test_migration_db_v16(engine_dao):
    """Verify States and Session after migration from v15 to v16."""
    with engine_dao("engine_migration_16.db") as dao:
        # There should be only two sessions
        assert dao.get_session(1)
        session = dao.get_session(2)
        assert session

        # Verify session content
        assert session.status == TransferStatus.ONGOING
        assert session.uploaded_items == 0
        assert session.total_items == 1
        assert session.engine
        assert not session.completed_on
        assert session.created_on
        assert session.planned_items == 1


@windows_only
def test_migration_db_v18(engine_dao):
    """Verify States after migration from v17 to v18."""
    with engine_dao("engine_migration_18.db") as dao:
        dao._get_read_connection().row_factory = None
        c = dao._get_read_connection().cursor()

        rows = c.execute(
            "SELECT local_path, local_parent_path FROM States",
        ).fetchall()

        assert rows
        for row in rows:
            if row[0].startswith("/SYNC"):
                assert "\\" not in row[0]
                assert "\\" not in row[1]


def test_migration_db_v20(engine_dao):
    """Verify Uploads.request_uid presence after v20 migration."""
    with engine_dao("engine_migration_16.db") as dao:
        dao._get_read_connection().row_factory = None
        c = dao._get_read_connection().cursor()
        rows = c.execute("SELECT request_uid FROM Uploads").fetchall()
        assert rows
        for row in rows:
            # The request_uid default value is None
            assert not row[0]


def test_db_init_at_v21(tmp_path, engine_dao):
    """
    Cover the new migration object code.
    Compare the new init migration with the old system.
    """
    tmp_database = Path(tmp_path / str(uuid4()))
    with sqlite3.connect(tmp_database) as conn:
        cursor = conn.cursor()

        assert tmp_database.exists()

        # The database file is empty
        default_state = cursor.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
        assert not default_state

        # We import the engine_migrations dictionary
        from nxdrive.dao.migrations.engine import engine_migrations

        # New migration 21 should be the first one
        migration = list(engine_migrations.values())[0]

        # We upgrade the database, check the version then stock the result
        migration.upgrade(cursor)
        upgrade_state = cursor.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
        assert cursor.execute("PRAGMA user_version").fetchone()[0] == migration.version

        # We downgrade and check that everything has been reverted
        migration.downgrade(cursor)
        downgrade_state = cursor.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
        assert (
            cursor.execute("PRAGMA user_version").fetchone()[0]
            == migration.previous_version
        )
        assert downgrade_state == default_state

    # We check that the new init migration create the same tables than the old system.
    with engine_dao(tmp_database) as dao:
        dao._get_read_connection().row_factory = None
        cursor = dao._get_read_connection().cursor()
        old_migration_state = cursor.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
        assert sorted(old_migration_state) == sorted(upgrade_state)


def test_migration_interface():
    """Test done for code coverage of the abstract class."""
    with patch.object(
        MigrationInterface, "__abstractmethods__", set()
    ), sqlite3.connect(":memory:") as conn:
        interface = MigrationInterface()
        cursor = conn.cursor()

        assert not interface.upgrade(cursor)
        assert not interface.downgrade(cursor)
        assert not interface.previous_version
        assert not interface.version
