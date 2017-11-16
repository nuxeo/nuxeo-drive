# coding: utf-8
import os
import sys
import tempfile
import unittest

from nxdrive.engine.dao.sqlite import EngineDAO
from nxdrive.engine.engine import Engine
from tests.common import clean_dir


class EngineDAOTest(unittest.TestCase):

    def _get_default_db(self, name='test_engine.db'):
        return os.path.join(os.path.dirname(__file__), 'resources', name)

    def _clean_dao(self, dao):
        dao.dispose()
        if sys.platform == 'win32':
            os.remove(dao.get_db())

    def get_db_temp_file(self):
        tmp_db = tempfile.NamedTemporaryFile(suffix="test_db", dir=self.tmpdir)
        if sys.platform == 'win32':
            tmp_db.close()
        return tmp_db

    def setUp(self):
        self.build_workspace = os.environ.get('WORKSPACE')
        self.tmpdir = None
        if self.build_workspace is not None:
            self.tmpdir = os.path.join(self.build_workspace, 'tmp')
            if not os.path.isdir(self.tmpdir):
                os.makedirs(self.tmpdir)
            self.addCleanup(clean_dir, self.tmpdir)
        self.tmp_db = self.get_db_temp_file()

        with open(self._get_default_db(), 'rb') as db, \
                open(self.tmp_db.name, 'wb') as f:
            f.write(db.read())
        self._dao = EngineDAO(self.tmp_db.name)
        self.addCleanup(self._clean_dao, self._dao)

    def test_init_db(self):
        init_db = self.get_db_temp_file()
        if sys.platform != 'win32':
            os.remove(init_db.name)
        dao = EngineDAO(init_db.name)
        # Test filters table
        self.assertEqual(0, len(dao.get_filters()))
        # Test state table
        self.assertEqual(0, len(dao.get_conflicts()))
        # Test configuration
        self.assertIsNone(dao.get_config("remote_user"))
        # Test RemoteScan table
        self.assertFalse(dao.is_path_scanned("/"))
        self._clean_dao(dao)

    def test_migration_db_v1_with_duplicates(self):
        # Test a non empty db
        migrate_db = self.get_db_temp_file()
        db = open(self._get_default_db('test_engine_migration_duplicate.db'), 'rb')
        with open(migrate_db.name, 'wb') as f:
            f.write(db.read())
        self._dao = EngineDAO(migrate_db.name)
        c = self._dao._get_read_connection().cursor()
        rows = c.execute("SELECT * FROM States").fetchall()
        self.assertEqual(len(rows), 0)
        cols = c.execute("PRAGMA table_info('States')").fetchall()
        self.assertEqual(len(cols), 30)
        self.assertIsNone(self._dao.get_config("remote_last_event_log_id"))
        self.assertIsNone(self._dao.get_config("remote_last_full_scan"))

    def test_migration_db_v1(self):
        init_db = self.get_db_temp_file()
        # Test empty db
        dao = EngineDAO(init_db.name)
        self._clean_dao(dao)
        # Test a non empty db
        migrate_db = self.get_db_temp_file()
        db = open(self._get_default_db('test_engine_migration.db'), 'rb')
        with open(migrate_db.name, 'wb') as f:
            f.write(db.read())
        self._dao = EngineDAO(migrate_db.name)
        c = self._dao._get_read_connection().cursor()
        cols = c.execute("PRAGMA table_info('States')").fetchall()
        self.assertEqual(len(cols), 30)
        cols = c.execute("SELECT * FROM States").fetchall()
        self.assertEqual(len(cols), 63)
        self.test_batch_folder_files()
        self.test_batch_upload_files()
        self.test_conflicts()
        self.test_errors()
        self.test_acquire_processors()
        self.test_configuration()

    def test_conflicts(self):
        self.assertEqual(self._dao.get_conflict_count(), 3)
        self.assertEqual(len(self._dao.get_conflicts()), 3)

    def test_errors(self):
        self.assertEqual(self._dao.get_error_count(), 1)
        self.assertEqual(self._dao.get_error_count(5), 0)
        self.assertEqual(len(self._dao.get_errors()), 1)
        row = self._dao.get_errors()[0]
        # Test reset error
        self._dao.reset_error(row)
        self.assertEqual(self._dao.get_error_count(), 0)
        row = self._dao.get_state_from_id(row.id)
        self.assertIsNone(row.last_error)
        self.assertIsNone(row.last_error_details)
        self.assertEqual(row.error_count, 0)
        # Test increase
        self._dao.increase_error(row, "Test")
        self.assertEqual(self._dao.get_error_count(), 0)
        self._dao.increase_error(row, "Test 2")
        self.assertEqual(self._dao.get_error_count(), 0)
        self.assertEqual(self._dao.get_error_count(1), 1)
        self._dao.increase_error(row, "Test 3")
        self.assertEqual(self._dao.get_error_count(), 0)
        self.assertEqual(self._dao.get_error_count(2), 1)
        # Synchronize with wrong version should fail
        self.assertFalse(self._dao.synchronize_state(row, version=row.version-1))
        self.assertEqual(self._dao.get_error_count(2), 1)
        # Synchronize should reset error
        self.assertTrue(self._dao.synchronize_state(row))
        self.assertEqual(self._dao.get_error_count(2), 0)

    def test_remote_scans(self):
        self.assertFalse(self._dao.is_path_scanned("/"))
        self._dao.add_path_scanned("/Test")
        self.assertTrue(self._dao.is_path_scanned("/Test"))
        self.assertFalse(self._dao.is_path_scanned("/Test2"))
        self._dao.clean_scanned()
        self.assertFalse(self._dao.is_path_scanned("/Test"))

    def test_last_sync(self):
        # Based only on file so not showing 2
        ids = [58, 8, 62, 61, 60]
        files = self._dao.get_last_files(5)
        self.assertEqual(len(files), 5)
        for i in range(5):
            self.assertEqual(files[i].id, ids[i])
        ids = [58, 62, 61, 60, 63]
        files = self._dao.get_last_files(5, "remote")
        self.assertEqual(len(files), 5)
        for i in range(5):
            self.assertEqual(files[i].id, ids[i])
        ids = [8, 11, 5]
        files = self._dao.get_last_files(5, "local")
        self.assertEqual(len(files), 3)
        for i in range(3):
            self.assertEqual(files[i].id, ids[i])

    def test_batch_folder_files(self):
        # Verify that the batch is ok
        ids = range(25, 47)
        index = 0
        state = self._dao.get_state_from_id(25) #ids[index])
        while index < len(ids)-1:
            index = index + 1
            state = self._dao.get_next_folder_file(state.remote_ref)
            self.assertEqual(state.id, ids[index])
        while index > 0:
            index = index - 1
            state = self._dao.get_previous_folder_file(state.remote_ref)
            self.assertEqual(state.id, ids[index])
        self.assertIsNone(self._dao.get_previous_folder_file(state.remote_ref))
        # Last file is 9
        state = self._dao.get_state_from_id(46)
        self.assertIsNone(self._dao.get_next_folder_file(state.remote_ref))

    def test_batch_upload_files(self):
        # Verify that the batch is ok
        ids = [58, 62, 61, 60, 63]
        index = 0
        state = self._dao.get_state_from_id(ids[index])
        while index < len(ids)-1:
            index = index + 1
            state = self._dao.get_next_sync_file(state.remote_ref, Engine.BATCH_MODE_UPLOAD)
            self.assertEqual(state.id, ids[index])
        while index > 0:
            index = index - 1
            state = self._dao.get_previous_sync_file(state.remote_ref, Engine.BATCH_MODE_UPLOAD)
            self.assertEqual(state.id, ids[index])
        self.assertIsNone(self._dao.get_previous_sync_file(state.remote_ref, Engine.BATCH_MODE_UPLOAD))
        # Last file is 9
        state = self._dao.get_state_from_id(9)
        self.assertIsNone(self._dao.get_next_sync_file(state.remote_ref, Engine.BATCH_MODE_UPLOAD))

    def test_reinit_processors(self):
        state = self._dao.get_state_from_id(1)
        self.assertEqual(state.processor, 0)

    def test_acquire_processors(self):
        self.assertTrue(self._dao.acquire_processor(666, 2))
        # Cannot acquire processor if different processor
        self.assertFalse(self._dao.acquire_processor(777, 2))
        # Can re-acquire processor if same processor
        self.assertTrue(self._dao.acquire_processor(666, 2))
        self.assertTrue(self._dao.release_processor(666))

        # Check the auto-release
        self.assertTrue(self._dao.acquire_processor(666, 2))
        row = self._dao.get_state_from_id(2)
        self._dao.synchronize_state(row)
        self.assertFalse(self._dao.release_processor(666))

    def test_configuration(self):
        result = self._dao.get_config("empty", "DefaultValue")
        self.assertEqual(result, "DefaultValue")
        result = self._dao.get_config("remote_user", "DefaultValue")
        self.assertEqual(result, "Administrator")
        self._dao.update_config("empty", "notAnymore")
        result = self._dao.get_config("empty", "DefaultValue")
        self.assertNotEquals(result, "DefaultValue")
        self._dao.update_config("remote_user", "Test")
        result = self._dao.get_config("remote_user", "DefaultValue")
        self.assertEqual(result, "Test")
        self._dao.update_config("empty", None)
        result = self._dao.get_config("empty", "DefaultValue")
        self.assertEqual(result, "DefaultValue")
        result = self._dao.get_config("empty")
        self.assertEqual(result, None)

    def test_filters(self):
        # Contains by default /fakeFilter/Test_Parent and /fakeFilter/Retest
        self.assertEqual(len(self._dao.get_filters()), 2)
        self._dao.remove_filter(u"/fakeFilter/Retest")
        self.assertEqual(len(self._dao.get_filters()), 1)
        self._dao.add_filter(u"/fakeFilter")
        # Should delete the subchild filter
        self.assertEqual(len(self._dao.get_filters()), 1)
        self._dao.add_filter(u"/otherFilter")
        self.assertEqual(len(self._dao.get_filters()), 2)
