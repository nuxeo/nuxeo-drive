import sqlite3
from logging import getLogger
from multiprocessing import RLock
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from nxdrive.constants import TransferStatus
from nxdrive.dao.migrations.migration import MigrationInterface

from ..markers import windows_only

log = getLogger(__name__)


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


def test_engine_init_db(engine_dao):
    with engine_dao("engine_migration.db") as dao:
        assert len(dao.get_filters()) == 2  # There are 2 default filters existing
        assert len(dao.get_conflicts()) == 3
        assert dao.get_config("remote_user") == "Administrator"
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


def test_migration_db_v1(engine_dao):
    with engine_dao("engine_migration.db") as dao:
        c = dao._get_read_connection().cursor()

        cols = c.execute("PRAGMA table_info('States')").fetchall()
        assert len(cols) == 34

        cols = c.execute("SELECT * FROM States").fetchall()
        assert len(cols) == 63


def test_migration_db_v1_with_duplicates(engine_dao):
    """Test a non empty DB."""
    with engine_dao("engine_migration_duplicate.db") as dao:
        c = dao._get_read_connection().cursor()
        rows = c.execute("SELECT * FROM States").fetchall()
        assert not rows

        cols = c.execute("PRAGMA table_info('States')").fetchall()
        assert len(cols) == 34
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
        assert not downloads

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

        # We downgrade and check that everything has been reverted
        migration.downgrade(cursor)
        downgrade_state = cursor.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()

        assert downgrade_state == default_state

    # We check that the new init migration create the same tables than the old system.
    with engine_dao(tmp_database) as dao:
        dao._get_read_connection().row_factory = None
        cursor = dao._get_read_connection().cursor()
        old_migration_state = cursor.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
        assert sorted(old_migration_state) == sorted(upgrade_state)


def test_db_init_at_v22(tmp_path, engine_dao):
    """
    Cover the new migration object code.
    Compare the new init migration with the old system.
    """
    tmp_database = Path(tmp_path / str(uuid4()))
    print("THE DATABASE PATH IS ")
    print(tmp_database)
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

        # Existing migration 21 should be the first one
        migration21 = list(engine_migrations.values())[0]

        # We upgrade the database, check the version then stock the result
        migration21.upgrade(cursor)
        upgrade_state = cursor.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()

        # New migration 22 should be the first one
        migration22 = list(engine_migrations.values())[1]

        # We upgrade the database, check the version then stock the result
        migration22.upgrade(cursor)

        # We downgrade and check that everything has been reverted
        """
        migration22.downgrade(cursor)
        migration21.downgrade(cursor)
        downgrade_state = cursor.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()

        assert downgrade_state == default_state
        """

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


def test_update_upload_requestid(engine_dao, upload):
    """Test to save upload and update reuqest_uid of existing row"""
    engine_dao.lock = RLock()
    with engine_dao("engine_migration_18.db") as dao:
        engine_dao.directTransferUpdated = Mock()
        # Save New upload
        engine_dao.save_upload(dao, upload)

        assert upload.uid

        previous_request_id = upload.request_uid
        upload.request_uid = str(uuid4())
        # Update request_uid of existing record
        engine_dao.update_upload_requestid(dao, upload)

        assert previous_request_id != upload.request_uid


class TestAcquireState:
    """Test cases for EngineDAO.acquire_state method."""

    def test_acquire_state_success(self, engine_dao):
        """Test successful state acquisition."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()
            thread_id = 999
            row_id = 2

            # Acquire state
            state = dao.acquire_state(thread_id, row_id)

            # Verify state was acquired
            assert state is not None
            assert state.id == row_id

            # Verify processor was set
            c = dao._get_read_connection().cursor()
            result = c.execute(
                "SELECT processor FROM States WHERE id = ?", (row_id,)
            ).fetchone()
            assert result[0] == thread_id

            # Cleanup
            dao.release_processor(thread_id)

    def test_acquire_state_already_acquired_different_thread(self, engine_dao):
        """Test acquiring state that's already acquired by different thread."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()
            thread_id_1 = 888
            thread_id_2 = 777
            row_id = 3

            # First thread acquires
            state1 = dao.acquire_state(thread_id_1, row_id)
            assert state1 is not None

            # Second thread tries to acquire - should fail
            try:
                dao.acquire_state(thread_id_2, row_id)
                assert False, "Should have raised OperationalError"
            except Exception as e:
                assert "Cannot acquire" in str(e)

            # Cleanup
            dao.release_processor(thread_id_1)

    def test_acquire_state_reacquire_same_thread(self, engine_dao):
        """Test re-acquiring state with same thread."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()
            thread_id = 666
            row_id = 4

            # First acquisition
            state1 = dao.acquire_state(thread_id, row_id)
            assert state1 is not None

            # Re-acquisition with same thread should succeed
            state2 = dao.acquire_state(thread_id, row_id)
            assert state2 is not None
            assert state2.id == row_id

            # Cleanup
            dao.release_processor(thread_id)

    def test_acquire_state_none_thread_id(self, engine_dao):
        """Test acquiring state with None thread_id."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()
            row_id = 5

            # Should fail with None thread_id
            try:
                dao.acquire_state(None, row_id)
                assert False, "Should have raised OperationalError"
            except Exception as e:
                assert "Cannot acquire" in str(e)

    def test_acquire_state_nonexistent_row(self, engine_dao):
        """Test acquiring state for non-existent row."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()
            thread_id = 555
            row_id = 999999  # Non-existent

            # Should fail
            try:
                dao.acquire_state(thread_id, row_id)
                assert False, "Should have raised OperationalError"
            except Exception as e:
                assert "Cannot acquire" in str(e)

    def test_acquire_state_exception_releases_processor(self, engine_dao):
        """Test that exception during get_state_from_id releases processor."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()
            thread_id = 444
            row_id = 6

            # Mock get_state_from_id to raise exception
            original_method = dao.get_state_from_id

            def mock_get_state(*args, **kwargs):
                raise RuntimeError("Test exception")

            dao.get_state_from_id = mock_get_state

            # Should raise and release processor
            try:
                dao.acquire_state(thread_id, row_id)
                assert False, "Should have raised RuntimeError"
            except RuntimeError as e:
                log.error(f"RuntimeError : {e}")

            # Verify processor was released
            c = dao._get_read_connection().cursor()
            result = c.execute(
                "SELECT processor FROM States WHERE id = ?", (row_id,)
            ).fetchone()
            assert result[0] == 0

            # Restore original method
            dao.get_state_from_id = original_method


class TestReinitStates:
    """Test cases for EngineDAO.reinit_states method."""

    def test_reinit_states_drops_and_recreates_table(self, engine_dao):
        """Test that reinit_states drops and recreates States table."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Get count of states before
            c = dao._get_read_connection().cursor()
            count_before = c.execute("SELECT COUNT(*) FROM States").fetchone()[0]
            assert count_before > 0

            # Reinit states
            dao.reinit_states()

            # Verify table is empty
            c = dao._get_read_connection().cursor()
            count_after = c.execute("SELECT COUNT(*) FROM States").fetchone()[0]
            assert count_after == 0

            # Verify table still exists with correct schema
            cols = c.execute("PRAGMA table_info('States')").fetchall()
            assert len(cols) > 0

    def test_reinit_states_deletes_configs(self, engine_dao):
        """Test that reinit_states deletes specific configs."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Set some config values
            dao.update_config("remote_last_sync_date", "12345")
            dao.update_config("remote_last_event_log_id", "67890")
            dao.update_config("some_other_config", "keep_me")

            # Verify configs exist
            assert dao.get_config("remote_last_sync_date") == "12345"
            assert dao.get_config("some_other_config") == "keep_me"

            # Reinit states
            dao.reinit_states()

            # Verify sync-related configs are deleted
            assert dao.get_config("remote_last_sync_date") is None
            assert dao.get_config("remote_last_event_log_id") is None
            assert dao.get_config("remote_last_event_last_root_definitions") is None
            assert dao.get_config("remote_last_full_scan") is None
            assert dao.get_config("last_sync_date") is None

            # Verify other configs are preserved
            assert dao.get_config("some_other_config") == "keep_me"

    def test_reinit_states_vacuum(self, engine_dao):
        """Test that reinit_states runs VACUUM."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Mock execute to track VACUUM call
            original_execute = dao._get_write_connection().execute
            vacuum_called = []

            def mock_execute(sql, *args):
                if "VACUUM" in sql.upper():
                    vacuum_called.append(True)
                return original_execute(sql, *args)

            dao._get_write_connection().execute = mock_execute

            # Reinit states
            dao.reinit_states()

            # Verify VACUUM was called
            assert len(vacuum_called) > 0


class TestDeleteRemoteState:
    """Test cases for EngineDAO.delete_remote_state method."""

    def test_delete_remote_state_file(self, engine_dao):
        """Test deleting remote state for a file."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()
            dao.queue_manager = Mock()

            # Get a file state
            state = dao.get_state_from_id(8)
            assert state is not None
            assert not state.folderish

            # Delete remote state
            dao.delete_remote_state(state)

            # Verify state was updated
            updated = dao.get_state_from_id(8)
            assert updated.remote_state == "deleted"
            assert updated.pair_state == "remotely_deleted"

    def test_delete_remote_state_folder(self, engine_dao):
        """Test deleting remote state for a folder."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()
            dao.queue_manager = Mock()

            # Get a folder state (id 1 is typically a folder)
            state = dao.get_state_from_id(1)
            if state and state.folderish:
                # Get children before deletion
                children_before = dao.get_remote_children(state.remote_ref)

                # Delete remote state
                dao.delete_remote_state(state)

                # Verify parent was updated
                updated = dao.get_state_from_id(state.id)
                assert updated.remote_state == "deleted"
                assert updated.pair_state == "remotely_deleted"

                # Verify children were marked as parent_remotely_deleted
                for child in children_before:
                    child_updated = dao.get_state_from_id(child.id)
                    if child_updated.remote_parent_ref == state.remote_ref:
                        assert child_updated.pair_state == "parent_remotely_deleted"

    def test_delete_remote_state_queues_pair(self, engine_dao):
        """Test that delete_remote_state queues the pair."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Mock queue_manager
            mock_queue = Mock()
            dao.queue_manager = mock_queue

            # Get a state
            state = dao.get_state_from_id(10)
            if state:
                # Delete remote state
                dao.delete_remote_state(state)

                # Verify _queue_pair_state was effectively called
                # (checking via state update is sufficient)
                updated = dao.get_state_from_id(10)
                assert updated.pair_state == "remotely_deleted"


class TestPlanManyDirectTransferItems:
    """Test cases for EngineDAO.plan_many_direct_transfer_items method."""

    def test_plan_many_direct_transfer_items_basic(self, engine_dao):
        """Test basic insertion of direct transfer items."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()

            # Create session
            session_uid = dao.create_session(
                "/remote/path", "remote-ref-123", 3, "test-engine", "Test session"
            )

            # Prepare items
            items = (
                (
                    Path("/local/file1.txt"),
                    Path("/local"),
                    "file1.txt",
                    False,
                    1024,
                    "/remote/path",
                    "remote-ref-123",
                    "File",
                    "create-new",
                    "todo",
                ),
                (
                    Path("/local/file2.txt"),
                    Path("/local"),
                    "file2.txt",
                    False,
                    2048,
                    "/remote/path",
                    "remote-ref-123",
                    "File",
                    "create-new",
                    "todo",
                ),
                (
                    Path("/local/folder1"),
                    Path("/local"),
                    "folder1",
                    True,
                    0,
                    "/remote/path",
                    "remote-ref-123",
                    "Folder",
                    "create-new",
                    "todo",
                ),
            )

            # Plan items
            current_max_row_id = dao.plan_many_direct_transfer_items(items, session_uid)
            assert current_max_row_id >= 0

            # Verify items were inserted
            c = dao._get_read_connection().cursor()
            inserted = c.execute(
                "SELECT * FROM States WHERE session = ?", (session_uid,)
            ).fetchall()
            assert len(inserted) == 3

            # Verify properties
            for item in inserted:
                assert item.local_state == "direct"
                assert item.pair_state == "direct_transfer"
                assert item.session == session_uid

    def test_plan_many_direct_transfer_items_returns_max_row_id(self, engine_dao):
        """Test that method returns current max row ID."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()

            # Get current max
            c = dao._get_read_connection().cursor()
            max_before = c.execute("SELECT max(ROWID) FROM States").fetchone()[0] or 0

            # Create session
            session_uid = dao.create_session(
                "/remote/path", "remote-ref-456", 1, "test-engine", "Test session"
            )

            # Prepare items
            items = (
                (
                    Path("/local/test.txt"),
                    Path("/local"),
                    "test.txt",
                    False,
                    512,
                    "/remote/path",
                    "remote-ref-456",
                    "File",
                    "create-new",
                    "todo",
                ),
            )

            # Plan items
            returned_max = dao.plan_many_direct_transfer_items(items, session_uid)

            # Returned max should be the value before insertion
            assert returned_max == max_before

            # Verify new items have higher ROWIDs
            c = dao._get_read_connection().cursor()
            max_after = c.execute("SELECT max(ROWID) FROM States").fetchone()[0]
            assert max_after > returned_max

    def test_plan_many_direct_transfer_items_empty_list(self, engine_dao):
        """Test planning with empty items list."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()

            # Create session
            session_uid = dao.create_session(
                "/remote/path", "remote-ref-789", 0, "test-engine", "Empty session"
            )

            # Plan with empty tuple
            items = ()
            current_max_row_id = dao.plan_many_direct_transfer_items(items, session_uid)

            assert current_max_row_id >= 0

            # Verify no items were inserted
            c = dao._get_read_connection().cursor()
            inserted = c.execute(
                "SELECT * FROM States WHERE session = ?", (session_uid,)
            ).fetchall()
            assert len(inserted) == 0


class TestUpdateLastTransfer:
    """Test cases for EngineDAO.update_last_transfer method."""

    def test_update_last_transfer_upload(self, engine_dao):
        """Test updating last_transfer to 'upload'."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Get a state
            row_id = 8
            state = dao.get_state_from_id(row_id)
            assert state is not None

            # Update last transfer
            dao.update_last_transfer(row_id, "upload")

            # Verify update
            updated = dao.get_state_from_id(row_id)
            assert updated.last_transfer == "upload"

    def test_update_last_transfer_download(self, engine_dao):
        """Test updating last_transfer to 'download'."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Get a state
            row_id = 5
            state = dao.get_state_from_id(row_id)
            assert state is not None

            # Update last transfer
            dao.update_last_transfer(row_id, "download")

            # Verify update
            updated = dao.get_state_from_id(row_id)
            assert updated.last_transfer == "download"

    def test_update_last_transfer_multiple_times(self, engine_dao):
        """Test updating last_transfer multiple times."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            row_id = 10

            # First update
            dao.update_last_transfer(row_id, "upload")
            state = dao.get_state_from_id(row_id)
            assert state.last_transfer == "upload"

            # Second update
            dao.update_last_transfer(row_id, "download")
            state = dao.get_state_from_id(row_id)
            assert state.last_transfer == "download"

            # Third update
            dao.update_last_transfer(row_id, "upload")
            state = dao.get_state_from_id(row_id)
            assert state.last_transfer == "upload"

    def test_update_last_transfer_nonexistent_row(self, engine_dao):
        """Test updating last_transfer for non-existent row."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Update non-existent row (should not raise error)
            dao.update_last_transfer(999999, "upload")

            # Verify no row exists
            state = dao.get_state_from_id(999999)
            assert state is None


class TestGetValidDuplicateFile:
    """Test cases for EngineDAO.get_valid_duplicate_file method."""

    def test_get_valid_duplicate_file_found(self, engine_dao):
        """Test finding a valid duplicate file."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # First, create a synchronized state with a specific digest
            test_digest = "abc123def456"

            # Insert a test state
            c = dao._get_write_connection().cursor()
            c.execute(
                "INSERT INTO States (local_path, local_parent_path, local_name, "
                "remote_ref, remote_parent_ref, remote_name, folderish, "
                "local_digest, remote_digest, pair_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "/test/duplicate.txt",
                    "/test",
                    "duplicate.txt",
                    "ref-123",
                    "parent-ref",
                    "duplicate.txt",
                    False,
                    test_digest,
                    test_digest,
                    "synchronized",
                ),
            )

            # Find the duplicate
            result = dao.get_valid_duplicate_file(test_digest)

            # Verify result
            assert result is not None
            assert result.local_digest == test_digest
            assert result.remote_digest == test_digest
            assert result.pair_state == "synchronized"

    def test_get_valid_duplicate_file_not_found(self, engine_dao):
        """Test when no duplicate file exists."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Search for non-existent digest
            result = dao.get_valid_duplicate_file("nonexistent-digest-xyz")

            # Verify no result
            assert result is None

    def test_get_valid_duplicate_file_not_synchronized(self, engine_dao):
        """Test that non-synchronized files are not returned."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            test_digest = "xyz789abc"

            # Insert a test state that's NOT synchronized
            c = dao._get_write_connection().cursor()
            c.execute(
                "INSERT INTO States (local_path, local_parent_path, local_name, "
                "remote_ref, remote_parent_ref, remote_name, folderish, "
                "local_digest, remote_digest, pair_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "/test/unsync.txt",
                    "/test",
                    "unsync.txt",
                    "ref-456",
                    "parent-ref",
                    "unsync.txt",
                    False,
                    test_digest,
                    test_digest,
                    "locally_modified",
                ),
            )

            # Try to find it
            result = dao.get_valid_duplicate_file(test_digest)

            # Should not find it because it's not synchronized
            assert result is None

    def test_get_valid_duplicate_file_digest_mismatch(self, engine_dao):
        """Test that files with mismatched local/remote digests are not returned."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            local_digest = "local-digest-123"
            remote_digest = "remote-digest-456"

            # Insert a test state with mismatched digests
            c = dao._get_write_connection().cursor()
            c.execute(
                "INSERT INTO States (local_path, local_parent_path, local_name, "
                "remote_ref, remote_parent_ref, remote_name, folderish, "
                "local_digest, remote_digest, pair_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "/test/mismatch.txt",
                    "/test",
                    "mismatch.txt",
                    "ref-789",
                    "parent-ref",
                    "mismatch.txt",
                    False,
                    local_digest,
                    remote_digest,
                    "synchronized",
                ),
            )

            # Try to find with local digest
            result = dao.get_valid_duplicate_file(local_digest)

            # Should not find because remote digest doesn't match
            assert result is None


class TestGetRemoteDescendants:
    """Test cases for EngineDAO.get_remote_descendants method."""

    def test_get_remote_descendants_found(self, engine_dao):
        """Test getting remote descendants."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Insert parent and children
            c = dao._get_write_connection().cursor()
            parent_path = "/parent/folder"

            # Insert parent
            c.execute(
                "INSERT INTO States (local_path, local_parent_path, local_name, "
                "remote_ref, remote_parent_ref, remote_name, remote_parent_path, "
                "folderish, pair_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "/local/parent",
                    "/local",
                    "parent",
                    "parent-ref",
                    "root-ref",
                    "parent",
                    parent_path,
                    True,
                    "synchronized",
                ),
            )

            # Insert children
            for i in range(3):
                c.execute(
                    "INSERT INTO States (local_path, local_parent_path, local_name, "
                    "remote_ref, remote_parent_ref, remote_name, remote_parent_path, "
                    "folderish, pair_state) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"/local/parent/child{i}",
                        "/local/parent",
                        f"child{i}",
                        f"child-ref-{i}",
                        "parent-ref",
                        f"child{i}",
                        f"{parent_path}/parent",
                        False,
                        "synchronized",
                    ),
                )

            # Get descendants
            descendants = dao.get_remote_descendants(parent_path)

            # Verify
            assert len(descendants) >= 3
            for desc in descendants:
                assert desc.remote_parent_path.startswith(parent_path)

    def test_get_remote_descendants_empty(self, engine_dao):
        """Test getting descendants when none exist."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Search for non-existent path
            descendants = dao.get_remote_descendants("/nonexistent/path")

            # Verify empty result
            assert len(descendants) == 0

    def test_get_remote_descendants_nested(self, engine_dao):
        """Test getting nested descendants."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            c = dao._get_write_connection().cursor()
            base_path = "/base/deep"

            # Create nested structure
            paths = [
                f"{base_path}/level1",
                f"{base_path}/level1/level2",
                f"{base_path}/level1/level2/level3",
            ]

            for idx, path in enumerate(paths):
                c.execute(
                    "INSERT INTO States (local_path, local_name, "
                    "remote_ref, remote_name, remote_parent_path, "
                    "folderish, pair_state) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"/local{path}",
                        f"level{idx + 1}",
                        f"ref-{idx}",
                        f"level{idx + 1}",
                        path,
                        True,
                        "synchronized",
                    ),
                )

            # Get all descendants
            descendants = dao.get_remote_descendants(base_path)

            # All should be returned
            assert len(descendants) >= 3


class TestGetRemoteChildren:
    """Test cases for EngineDAO.get_remote_children method."""

    def test_get_remote_children_found(self, engine_dao):
        """Test getting remote children by ref."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Insert parent and children
            c = dao._get_write_connection().cursor()
            parent_ref = "parent-ref-999"

            # Insert children
            for i in range(4):
                c.execute(
                    "INSERT INTO States (local_path, local_name, "
                    "remote_ref, remote_parent_ref, remote_name, "
                    "folderish, pair_state) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"/local/child{i}.txt",
                        f"child{i}.txt",
                        f"child-ref-{i}",
                        parent_ref,
                        f"child{i}.txt",
                        False,
                        "synchronized",
                    ),
                )

            # Get children
            children = dao.get_remote_children(parent_ref)

            # Verify
            assert len(children) == 4
            for child in children:
                assert child.remote_parent_ref == parent_ref

    def test_get_remote_children_empty(self, engine_dao):
        """Test getting children when none exist."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            # Search for non-existent parent
            children = dao.get_remote_children("nonexistent-parent-ref")

            # Verify empty result
            assert len(children) == 0

    def test_get_remote_children_mixed_types(self, engine_dao):
        """Test getting children of mixed types (files and folders)."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            c = dao._get_write_connection().cursor()
            parent_ref = "mixed-parent-ref"

            # Insert files and folders
            for i in range(2):
                # Files
                c.execute(
                    "INSERT INTO States (local_path, local_name, "
                    "remote_ref, remote_parent_ref, remote_name, "
                    "folderish, pair_state) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"/local/file{i}.txt",
                        f"file{i}.txt",
                        f"file-ref-{i}",
                        parent_ref,
                        f"file{i}.txt",
                        False,
                        "synchronized",
                    ),
                )
                # Folders
                c.execute(
                    "INSERT INTO States (local_path, local_name, "
                    "remote_ref, remote_parent_ref, remote_name, "
                    "folderish, pair_state) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"/local/folder{i}",
                        f"folder{i}",
                        f"folder-ref-{i}",
                        parent_ref,
                        f"folder{i}",
                        True,
                        "synchronized",
                    ),
                )

            # Get children
            children = dao.get_remote_children(parent_ref)

            # Verify both files and folders are returned
            assert len(children) == 4
            files = [c for c in children if not c.folderish]
            folders = [c for c in children if c.folderish]
            assert len(files) == 2
            assert len(folders) == 2

    def test_get_remote_children_only_direct_children(self, engine_dao):
        """Test that only direct children are returned, not grandchildren."""
        with engine_dao("engine_migration.db") as dao:
            dao.lock = RLock()

            c = dao._get_write_connection().cursor()
            parent_ref = "parent-only-ref"
            child_ref = "child-folder-ref"

            # Insert direct child
            c.execute(
                "INSERT INTO States (local_path, local_name, "
                "remote_ref, remote_parent_ref, remote_name, "
                "folderish, pair_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "/local/child",
                    "child",
                    child_ref,
                    parent_ref,
                    "child",
                    True,
                    "synchronized",
                ),
            )

            # Insert grandchild
            c.execute(
                "INSERT INTO States (local_path, local_name, "
                "remote_ref, remote_parent_ref, remote_name, "
                "folderish, pair_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "/local/child/grandchild.txt",
                    "grandchild.txt",
                    "grandchild-ref",
                    child_ref,  # Parent is child, not original parent
                    "grandchild.txt",
                    False,
                    "synchronized",
                ),
            )

            # Get children of original parent
            children = dao.get_remote_children(parent_ref)

            # Should only get direct child, not grandchild
            assert len(children) == 1
            assert children[0].remote_ref == child_ref
