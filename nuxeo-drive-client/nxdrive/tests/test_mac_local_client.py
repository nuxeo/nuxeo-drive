'''
Created on 15 Mar 2016

@author: mconstanmtin
'''


import os
import sys
import tempfile
import shutil
from unittest import skipIf, skip

from common_unit_test import UnitTestCase


if sys.platform == 'darwin':
    from nxdrive.tests.mac_local_client import MacLocalClient

TEST_FILE = "cat.jpg"
DUP_TEST_FILE = "cat__1.jpg"


class TestMacClient(UnitTestCase):

    def setUp(self):
        super(TestMacClient, self).setUp()
        self.resource_dir = self.get_test_resources_path()
        self.local_client = MacLocalClient(self.local_nxdrive_folder_1)
        self.test_file = os.path.join(self.resource_dir, TEST_FILE)
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        super(TestMacClient, self).tearDown()

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_copy_to_dir(self):
        self.local_client.copy(self.test_file, self.test_dir)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'copy does not exist')
        self.assertTrue(os.path.exists(os.path.join(self.resource_dir, TEST_FILE)), 'original does not exist')

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_copy_source_file_does_not_exist(self):
        missing_test_file = os.path.join(self.resource_dir, 'foo.jpg')
        with self.assertRaises(IOError) as cm:
            self.local_client.copy(missing_test_file, self.test_dir)

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_copy_src_dir_does_not_exist(self):
        missing_test_file = os.path.join(self.resource_dir + '_1', TEST_FILE)
        with self.assertRaises(IOError) as cm:
            self.local_client.copy(missing_test_file, self.test_dir)

    # @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    @skip('LocalClient._abspath_deduped method does not work for paths outside base_folder, TBD')
    def test_duplicate_file(self):
        # make a copy first
        self.local_client.copy(self.test_file, self.test_dir)
        self.local_client.duplicate_file(os.path.join(self.test_dir, TEST_FILE))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'original does not exist')
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, DUP_TEST_FILE)), 'duplicate does not exist')

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_duplicate_file_does_not_exist(self):
        missing_test_file = os.path.join(self.resource_dir, 'foo.jpg')
        with self.assertRaises(IOError) as cm:
            self.local_client.duplicate_file(missing_test_file)

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_move(self):
        # make a copy first
        self.local_client.copy(self.test_file, self.test_dir)
        # create a subdirectory
        os.makedirs(os.path.join(self.test_dir, 'temp'))
        # move file to the subdirectory
        self.local_client.move(os.path.join(self.test_dir, TEST_FILE), os.path.join(self.test_dir, 'temp'))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, 'temp', TEST_FILE)), 'copy does not exist')
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'original still exists')

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_move_with_name(self):
        # make a copy first
        self.local_client.copy(self.test_file, self.test_dir)
        # create a subdirectory
        os.makedirs(os.path.join(self.test_dir, 'temp'))
        # move file to the subdirectory
        self.local_client.move(os.path.join(self.test_dir, TEST_FILE), os.path.join(self.test_dir, 'temp'),
                               name='cat1.jpg')
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, 'temp', 'cat1.jpg')), 'copy does not exist')
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'original still exists')

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_move_dst_dir_does_not_exist(self):
        with self.assertRaises(IOError) as cm:
            self.local_client.move(os.path.join(self.test_dir, TEST_FILE), os.path.join(self.test_dir, 'temp'))

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_move_source_file_does_not_exist(self):
        missing_test_file = os.path.join(self.resource_dir, 'foo.jpg')
        with self.assertRaises(IOError) as cm:
            self.local_client.move(missing_test_file, self.test_dir)

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_rename(self):
        # make a copy first
        self.local_client.copy(self.test_file, self.test_dir)
        # rename the file copy
        self.local_client.rename(os.path.join(self.test_dir, TEST_FILE), "dog.jpg")
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "dog.jpg")), 'rename does not exist')
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'original still exists')

    @skipIf(sys.platform != 'darwin', 'test is only for Mac')
    def test_delete(self):
        # make a copy first
        self.local_client.copy(self.test_file, self.test_dir)
        # delete the file copy
        self.local_client.delete(os.path.join(self.test_dir, TEST_FILE))
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, TEST_FILE)), 'original still exists')