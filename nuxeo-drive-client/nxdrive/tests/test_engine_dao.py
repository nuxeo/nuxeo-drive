'''
Created on 31 mars 2015

@author: Remi Cattiau
'''
import unittest
import os
import nxdrive
from nxdrive.engine.dao.sqlite import EngineDAO
import tempfile


class EngineDAOTest(unittest.TestCase):

    def _get_default_db(self):
        nxdrive_path = os.path.dirname(nxdrive.__file__)
        return os.path.join(nxdrive_path, 'tests', 'resources', 'test_engine.db')

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix="test_db")
        db = open(self._get_default_db(), 'rb')
        print (self.tmp_db.name)
        with open(self.tmp_db.name, 'wb') as f:
            f.write(db.read())
        self._dao = EngineDAO(self.tmp_db.name)

    def tearDown(self):
        self._dao.dispose()

    def test_init_db(self):
        init_db = tempfile.NamedTemporaryFile(suffix="test_db")
        dao = EngineDAO(init_db.name)
        # Test filters table
        self.assertEquals(0, len(dao.get_filters()))
        # Test state table
        self.assertEquals(0, len(dao.get_conflicts()))
        # Test configuration
        self.assertIsNone(dao.get_config("remote_user"))
        # Test RemoteScan table
        self.assertFalse(dao.is_path_scanned("/"))

    def test_remote_scans(self):
        self.assertFalse(self._dao.is_path_scanned("/"))
        self._dao.add_path_scanned("/Test")
        self.assertTrue(self._dao.is_path_scanned("/Test"))
        self.assertFalse(self._dao.is_path_scanned("/Test2"))
        self._dao.clean_scanned()
        self.assertFalse(self._dao.is_path_scanned("/Test"))

    def test_reinit_processors(self):
        state = self._dao.get_state_from_id(1)
        self.assertEquals(state.processor, 0)

    def test_acquire_processors(self):
        self.assertTrue(self._dao.acquire_processor(666, 2))
        self.assertFalse(self._dao.acquire_processor(666, 2))
        self._dao.release_processor(666)
        self.assertTrue(self._dao.acquire_processor(666, 2))
        row = self._dao.get_state_from_id(2)
        # Check the auto-release
        self._dao.synchronize_state(row)
        self.assertTrue(self._dao.acquire_processor(666, 2))

    def test_configuration(self):
        result = self._dao.get_config("empty", "DefaultValue")
        self.assertEquals(result, "DefaultValue")
        result = self._dao.get_config("remote_user", "DefaultValue")
        self.assertEquals(result, "Administrator")
        self._dao.update_config("empty", "notAnymore")
        result = self._dao.get_config("empty", "DefaultValue")
        self.assertNotEquals(result, "DefaultValue")
        self._dao.update_config("remote_user", "Test")
        result = self._dao.get_config("remote_user", "DefaultValue")
        self.assertEquals(result, "Test")
        self._dao.update_config("empty", None)
        result = self._dao.get_config("empty", "DefaultValue")
        self.assertEquals(result, "DefaultValue")
        result = self._dao.get_config("empty")
        self.assertEquals(result, None)

    def test_filters(self):
        # Contains by default /fakeFilter/Test_Parent and /fakeFilter/Retest
        self.assertEquals(len(self._dao.get_filters()), 2)
        self._dao.remove_filter(u"/fakeFilter/Retest")
        self.assertEquals(len(self._dao.get_filters()), 1)
        self._dao.add_filter(u"/fakeFilter")
        # Should delete the subchild filter
        self.assertEquals(len(self._dao.get_filters()), 1)
        self._dao.add_filter(u"/otherFilter")
        self.assertEquals(len(self._dao.get_filters()), 2)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()