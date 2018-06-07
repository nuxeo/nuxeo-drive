# coding: utf-8
import os
import shutil
import sys
import tempfile
import unittest

from nxdrive.engine.dao.sqlite import EngineDAO
from .common import clean_dir


def get_default_db(name='test_engine.db'):
    return os.path.join(os.path.dirname(__file__), 'resources', name)


def clean_dao(dao):
    dao.dispose()
    if sys.platform == 'win32':
        os.remove(dao.get_db())


class EngineDAOTest(unittest.TestCase):

    def get_db_temp_file(self):
        tmp_db = tempfile.NamedTemporaryFile(suffix='test_db', dir=self.tmpdir)
        if sys.platform == 'win32':
            tmp_db.close()
        return tmp_db

    def setUp(self):
        self.tmpdir = os.path.join(os.environ.get('WORKSPACE', ''), 'tmp')
        self.addCleanup(clean_dir, self.tmpdir)

        if not os.path.isdir(self.tmpdir):
            os.makedirs(self.tmpdir)
        tmp_db = self.get_db_temp_file()

        with open(get_default_db(), 'rb') as db, open(tmp_db.name, 'wb') as f:
            f.write(db.read())
        self._dao = EngineDAO(tmp_db.name)
        self.addCleanup(clean_dao, self._dao)

    def test_init_db(self):
        init_db = self.get_db_temp_file()
        if sys.platform != 'win32':
            os.remove(init_db.name)

        dao = EngineDAO(init_db.name)

        # Test filters table
        assert not dao.get_filters()

        # Test state table
        assert not dao.get_conflicts()

        # Test configuration
        assert dao.get_config('remote_user') is None

        # Test RemoteScan table
        assert not dao.is_path_scanned('/')

        clean_dao(dao)

    def test_migration_db_v1_with_duplicates(self):
        # Test a non empty db
        migrate_db = self.get_db_temp_file()
        database = get_default_db('test_engine_migration_duplicate.db')
        with open(migrate_db.name, 'wb') as f, open(database, 'rb') as db:
            f.write(db.read())

        self._dao = EngineDAO(migrate_db.name)
        c = self._dao._get_read_connection().cursor()
        rows = c.execute('SELECT * FROM States').fetchall()
        assert not rows

        cols = c.execute("PRAGMA table_info('States')").fetchall()
        assert len(cols) == 31
        assert self._dao.get_config('remote_last_event_log_id') is None
        assert self._dao.get_config('remote_last_full_scan') is None

    def test_migration_db_v1(self):
        init_db = self.get_db_temp_file()

        # Test empty db
        dao = EngineDAO(init_db.name)
        clean_dao(dao)

        # Test a non empty db
        migrate_db = self.get_db_temp_file()
        db = open(get_default_db('test_engine_migration.db'), 'rb')
        with open(migrate_db.name, 'wb') as f:
            f.write(db.read())

        self._dao = EngineDAO(migrate_db.name)
        c = self._dao._get_read_connection().cursor()

        cols = c.execute("PRAGMA table_info('States')").fetchall()
        assert len(cols) == 31

        cols = c.execute('SELECT * FROM States').fetchall()
        assert len(cols) == 63

        self.test_batch_folder_files()
        self.test_batch_upload_files()
        self.test_conflicts()
        self.test_errors()
        self.test_acquire_processors()
        self.test_configuration()

    def test_conflicts(self):
        assert self._dao.get_conflict_count() == 3
        assert len(self._dao.get_conflicts()) == 3

    def test_errors(self):
        assert self._dao.get_error_count() == 1
        assert not self._dao.get_error_count(5)
        assert len(self._dao.get_errors()) == 1
        row = self._dao.get_errors()[0]

        # Test reset error
        self._dao.reset_error(row)
        assert not self._dao.get_error_count()
        row = self._dao.get_state_from_id(row.id)
        assert row.last_error is None
        assert row.last_error_details is None
        assert not row.error_count

        # Test increase
        self._dao.increase_error(row, 'Test')
        assert not self._dao.get_error_count()
        self._dao.increase_error(row, 'Test 2')
        assert not self._dao.get_error_count()
        assert self._dao.get_error_count(1) == 1
        self._dao.increase_error(row, 'Test 3')
        assert not self._dao.get_error_count()
        assert self._dao.get_error_count(2) == 1

        # Synchronize with wrong version should fail
        assert not self._dao.synchronize_state(row, version=row.version-1)
        assert self._dao.get_error_count(2) == 1

        # Synchronize should reset error
        assert self._dao.synchronize_state(row)
        assert not self._dao.get_error_count(2)

    def test_remote_scans(self):
        assert not self._dao.is_path_scanned('/')

        self._dao.add_path_scanned('/Test')
        assert self._dao.is_path_scanned('/Test')
        assert not self._dao.is_path_scanned('/Test2')

        self._dao.clean_scanned()
        assert not self._dao.is_path_scanned('/Test')

    def test_last_sync(self):
        # Based only on file so not showing 2
        ids = [58, 8, 62, 61, 60]
        files = self._dao.get_last_files(5)
        assert len(files) == 5
        for i in range(5):
            assert files[i].id == ids[i]

        ids = [58, 62, 61, 60, 63]
        files = self._dao.get_last_files(5, 'remote')
        assert len(files) == 5
        for i in range(5):
            assert files[i].id == ids[i]

        ids = [8, 11, 5]
        files = self._dao.get_last_files(5, 'local')
        assert len(files) == 3
        for i in range(3):
            assert files[i].id == ids[i]

    def test_batch_folder_files(self):
        # Verify that the batch is ok
        ids = range(25, 47)
        index = 0
        state = self._dao.get_state_from_id(25)  # ids[index])

        while index < len(ids) - 1:
            index += 1
            state = self._dao.get_next_folder_file(state.remote_ref)
            assert state.id == ids[index]

        while index > 0:
            index -= 1
            state = self._dao.get_previous_folder_file(state.remote_ref)
            assert state.id == ids[index]

        assert self._dao.get_previous_folder_file(state.remote_ref) is None

        # Last file is 9
        state = self._dao.get_state_from_id(46)
        assert self._dao.get_next_folder_file(state.remote_ref) is None

    def test_batch_upload_files(self):
        # Verify that the batch is ok
        ids = [58, 62, 61, 60, 63]
        index = 0
        state = self._dao.get_state_from_id(ids[index])

        while index < len(ids)-1:
            index += 1
            state = self._dao.get_next_sync_file(state.remote_ref, 'upload')
            assert state.id == ids[index]

        while index > 0:
            index -= 1
            state = self._dao.get_previous_sync_file(state.remote_ref,
                                                     'upload')
            assert state.id == ids[index]

        assert self._dao.get_previous_sync_file(
            state.remote_ref, 'upload') is None

        # Last file is 9
        state = self._dao.get_state_from_id(9)
        assert self._dao.get_next_sync_file(
            state.remote_ref, 'upload') is None

    def test_reinit_processors(self):
        state = self._dao.get_state_from_id(1)
        assert not state.processor

    def test_acquire_processors(self):
        assert self._dao.acquire_processor(666, 2)

        # Cannot acquire processor if different processor
        assert not self._dao.acquire_processor(777, 2)

        # Can re-acquire processor if same processor
        assert self._dao.acquire_processor(666, 2)
        assert self._dao.release_processor(666)

        # Check the auto-release
        assert self._dao.acquire_processor(666, 2)
        row = self._dao.get_state_from_id(2)
        self._dao.synchronize_state(row)
        assert not self._dao.release_processor(666)

    def test_configuration(self):
        result = self._dao.get_config('empty', 'DefaultValue')
        assert result == 'DefaultValue'

        result = self._dao.get_config('remote_user', 'DefaultValue')
        assert result == 'Administrator'

        self._dao.update_config('empty', 'notAnymore')
        result = self._dao.get_config('empty', 'DefaultValue')
        assert result != 'DefaultValue'
        self._dao.update_config('remote_user', 'Test')
        result = self._dao.get_config('remote_user', 'DefaultValue')
        assert result == 'Test'

        self._dao.update_config('empty', None)
        result = self._dao.get_config('empty', 'DefaultValue')
        assert result == 'DefaultValue'

        result = self._dao.get_config('empty')
        assert result is None

    def test_filters(self):
        # Contains by default /fakeFilter/Test_Parent and /fakeFilter/Retest
        assert len(self._dao.get_filters()) == 2

        self._dao.remove_filter('/fakeFilter/Retest')
        assert len(self._dao.get_filters()) == 1

        # Should delete the subchild filter
        self._dao.add_filter('/fakeFilter')
        assert len(self._dao.get_filters()) == 1

        self._dao.add_filter('/otherFilter')
        assert len(self._dao.get_filters()) == 2


def test_corrupted_database():
    """ DatabaseError: database disk image is malformed. """

    # Need to make a copy of the file because it will be fixed in-place
    database = 'bad.db'
    shutil.copy(get_default_db('test_corrupted_database.db'), database)

    dao = EngineDAO(database)
    try:
        c = dao._get_read_connection().cursor()
        cols = c.execute('SELECT * FROM States').fetchall()
        assert len(cols) == 3
    finally:
        clean_dao(dao)
