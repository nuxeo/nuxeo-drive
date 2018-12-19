# coding: utf-8
import shutil
import time
from typing import Optional

from nxdrive.engine.dao.sqlite import EngineDAO
from nxdrive.objects import DocPair
from nxdrive.utils import normalized_path


class MockEngineDao(EngineDAO):
    """ Convenient class with auto-cleanup at exit. """

    def __init__(self, fname):
        db = normalized_path(__file__).parent / "resources" / fname
        tmp = db.with_name(f"{db.name}_copy.db")
        shutil.copy(db, tmp)
        time.sleep(1)
        super().__init__(tmp)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dispose()
        self._db.unlink()

    def _get_adjacent_sync_file(
        self, ref: str, comp: str, order: str, sync_mode: str = None
    ) -> Optional[DocPair]:
        state = self.get_normal_state_from_remote(ref)
        if state is None:
            return None

        mode = f" AND last_transfer='{sync_mode}' " if sync_mode else ""
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States "
            f"WHERE last_sync_date {comp} ? "
            "   AND (pair_state != 'unsynchronized' "
            "   AND pair_state != 'conflicted') "
            "   AND folderish = 0 "
            f"{mode}"
            f"ORDER BY last_sync_date {order}"
            " LIMIT 1",
            (state.last_sync_date,),
        ).fetchone()

    def _get_adjacent_folder_file(
        self, ref: str, comp: str, order: str
    ) -> Optional[DocPair]:
        state = self.get_normal_state_from_remote(ref)
        if not state:
            return None
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE remote_parent_ref = ?"
            f"  AND remote_name {comp} ?"
            "   AND folderish = 0 "
            f"ORDER BY remote_name {order}"
            " LIMIT 1",
            (state.remote_parent_ref, state.remote_name),
        ).fetchone()

    def get_previous_folder_file(self, ref: str) -> Optional[DocPair]:
        return self._get_adjacent_folder_file(ref, "<", "DESC")

    def get_next_folder_file(self, ref: str) -> Optional[DocPair]:
        return self._get_adjacent_folder_file(ref, ">", "ASC")

    def get_previous_sync_file(
        self, ref: str, sync_mode: str = None
    ) -> Optional[DocPair]:
        return self._get_adjacent_sync_file(ref, ">", "ASC", sync_mode)

    def get_next_sync_file(self, ref: str, sync_mode: str = None) -> Optional[DocPair]:
        return self._get_adjacent_sync_file(ref, "<", "DESC", sync_mode)


def test_acquire_processors():
    with MockEngineDao("test_engine_migration.db") as dao:
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


def test_batch_folder_files():
    """ Verify that the batch is ok. """
    with MockEngineDao("test_engine_migration.db") as dao:
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


def test_batch_upload_files():
    """ Verify that the batch is ok. """
    with MockEngineDao("test_engine_migration.db") as dao:
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


def test_configuration():
    with MockEngineDao("test_engine_migration.db") as dao:
        result = dao.get_config("empty", "DefaultValue")
        assert result == "DefaultValue"

        result = dao.get_config("remote_user", "DefaultValue")
        assert result == "Administrator"

        dao.update_config("empty", "notAnymore")
        result = dao.get_config("empty", "DefaultValue")
        assert result != "DefaultValue"
        dao.update_config("remote_user", "Test")
        result = dao.get_config("remote_user", "DefaultValue")
        assert result == "Test"

        dao.update_config("empty", None)
        result = dao.get_config("empty", "DefaultValue")
        assert result == "DefaultValue"

        result = dao.get_config("empty")
        assert result is None


def test_conflicts():
    with MockEngineDao("test_engine_migration.db") as dao:
        assert dao.get_conflict_count() == 3
        assert len(dao.get_conflicts()) == 3


def test_corrupted_database():
    """ DatabaseError: database disk image is malformed. """
    with MockEngineDao("test_corrupted_database.db") as dao:
        c = dao._get_read_connection().cursor()
        cols = c.execute("SELECT * FROM States").fetchall()
        assert len(cols) == 3


def test_errors():
    with MockEngineDao("test_engine_migration.db") as dao:
        assert dao.get_error_count() == 1
        assert not dao.get_error_count(5)
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
        assert dao.get_error_count(1) == 1
        dao.increase_error(row, "Test 3")
        assert not dao.get_error_count()
        assert dao.get_error_count(2) == 1

        # Synchronize with wrong version should fail
        assert not dao.synchronize_state(row, version=row.version - 1)
        assert dao.get_error_count(2) == 1

        # Synchronize should reset error
        assert dao.synchronize_state(row)
        assert not dao.get_error_count(2)


def test_filters():
    """ Contains by default /fakeFilter/Test_Parent and /fakeFilter/Retest. """
    with MockEngineDao("test_engine_migration.db") as dao:
        assert len(dao.get_filters()) == 2

        dao.remove_filter("/fakeFilter/Retest")
        assert len(dao.get_filters()) == 1

        # Should delete the subchild filter
        dao.add_filter("/fakeFilter")
        assert len(dao.get_filters()) == 1

        dao.add_filter("/otherFilter")
        assert len(dao.get_filters()) == 2


def test_init_db():
    with MockEngineDao("test_manager_migration.db") as dao:
        assert not dao.get_filters()
        assert not dao.get_conflicts()
        assert dao.get_config("remote_user") is None
        assert not dao.is_path_scanned("/")


def test_last_sync():
    """ Based only on file so not showing 2. """
    with MockEngineDao("test_engine_migration.db") as dao:
        ids = [58, 8, 62, 61, 60]
        files = dao.get_last_files(5)
        assert len(files) == 5
        for i in range(5):
            assert files[i].id == ids[i]

        ids = [58, 62, 61, 60, 63]
        files = dao.get_last_files(5, "remote")
        assert len(files) == 5
        for i in range(5):
            assert files[i].id == ids[i]

        ids = [8, 11, 5]
        files = dao.get_last_files(5, "local")
        assert len(files) == 3
        for i in range(3):
            assert files[i].id == ids[i]


def test_migration_db_v1():
    with MockEngineDao("test_engine_migration.db") as dao:
        c = dao._get_read_connection().cursor()

        cols = c.execute("PRAGMA table_info('States')").fetchall()
        assert len(cols) == 31

        cols = c.execute("SELECT * FROM States").fetchall()
        assert len(cols) == 63


def test_migration_db_v1_with_duplicates():
    """ Test a non empty DB. """
    with MockEngineDao("test_engine_migration_duplicate.db") as dao:
        c = dao._get_read_connection().cursor()
        rows = c.execute("SELECT * FROM States").fetchall()
        assert not rows

        cols = c.execute("PRAGMA table_info('States')").fetchall()
        assert len(cols) == 31
        assert dao.get_config("remote_last_event_log_id") is None
        assert dao.get_config("remote_last_full_scan") is None


def test_reinit_processors():
    with MockEngineDao("test_engine_migration.db") as dao:
        state = dao.get_state_from_id(1)
        assert not state.processor
