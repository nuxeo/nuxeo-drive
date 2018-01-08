# coding: utf-8
import os
import shutil
import tempfile
from logging import getLogger

from common_unit_test import UnitTestCase
from tests.common_unit_test import FILE_CONTENT

log = getLogger(__name__)
TEST_TIMEOUT = 60


class TestLocalPaste(UnitTestCase):

    NUMBER_OF_LOCAL_FILES = 25
    TEMP_FOLDER = u'temp_folder'
    FOLDER_A1 = u'a1'
    FOLDER_A2 = u'a2'
    FILENAME_PATTERN = u'file%03d.txt'

    '''
        1. create folder 'temp/a1' with more than 20 files in it
        2. create folder 'temp/a2', empty
        3. copy 'a1' and 'a2', in this order to the test sync root
        4. repeat step 3, but copy 'a2' and 'a1', in this order (to the test sync root)
        5. Verify that both folders and their content is sync to DM, in both steps 3 and 4
    '''

    def setUp(self):
        super(TestLocalPaste, self).setUp()

        log.debug('*** enter TestLocalPaste.setUp()')
        log.debug('*** engine1 starting')
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        log.debug('*** engine 1 synced')
        self.assertTrue(self.local_client_1.exists('/'), "Test sync root should be sync")
        self.workspace_abspath = self.local_client_1.abspath('/')

        # create  folder a1 and a2 under a temp folder
        self.local_temp = tempfile.mkdtemp(self.TEMP_FOLDER)
        self.folder1 = os.path.join(self.local_temp, self.FOLDER_A1)
        os.makedirs(self.folder1)
        self.folder2 = os.path.join(self.local_temp, self.FOLDER_A2)
        os.makedirs(self.folder2)
        # add files in folder 'temp/a1'
        for file_num in range(1, self.NUMBER_OF_LOCAL_FILES + 1):
            filename = self.FILENAME_PATTERN % file_num
            with open(os.path.join(self.folder1, filename), 'w') as f:
                f.write(FILE_CONTENT)

        log.debug('*** exit TestLocalPaste.setUp()')

    def tearDown(self):
        log.debug('*** enter TestLocalPaste.tearDown()')
        # delete temp folder
        shutil.rmtree(self.local_temp)
        super(TestLocalPaste, self).tearDown()
        log.debug('*** exit TestLocalPaste.tearDown()')

    """
    copy 'a2' to 'Nuxeo Drive Test Workspace', then 'a1' to 'Nuxeo Drive Test Workspace'
    """
    def test_copy_paste_empty_folder_first(self):
        log.debug('*** enter TestLocalPaste.test_copy_paste_empty_folder_first()')
        # copy 'temp/a2' under 'Nuxeo Drive Test Workspace'
        shutil.copytree(self.folder2, os.path.join(self.workspace_abspath, self.FOLDER_A2))
        # copy 'temp/a1' under 'Nuxeo Drive Test Workspace'
        shutil.copytree(self.folder1, os.path.join(self.workspace_abspath, self.FOLDER_A1))
        self.wait_sync(timeout=TEST_TIMEOUT)

        # check that '/Nuxeo Drive Test Workspace/a1' does exist
        self.assertTrue(self.local_client_1.exists(os.path.join('/', self.FOLDER_A1)))
        # check that '/Nuxeo Drive Test Workspace/a2' does exist
        self.assertTrue(self.local_client_1.exists(os.path.join('/', self.FOLDER_A2)))
        # check that '/Nuxeo Drive Test Workspace/a1/ has all the files
        children = os.listdir(os.path.join(self.workspace_abspath, self.FOLDER_A1))
        self.assertEqual(len(children), self.NUMBER_OF_LOCAL_FILES,
                         'folder /Nuxeo Drive Test Workspace/%s has %d files (expected %d)' %
                         (self.FOLDER_A1, len(children), self.NUMBER_OF_LOCAL_FILES))
        # check that remote (DM) 'Nuxeo Drive Test Workspace/a1' exists
        remote_ref_1 = self.local_client_1.get_remote_id(os.path.join('/', self.FOLDER_A1))
        self.assertTrue(self.remote_file_system_client_1.exists(remote_ref_1))
        # check that remote (DM) 'Nuxeo Drive Test Workspace/a2' exists
        remote_ref_2 = self.local_client_1.get_remote_id(os.path.join('/', self.FOLDER_A2))
        self.assertTrue(self.remote_file_system_client_1.exists(remote_ref_2))
        # check that remote (DM) 'Nuxeo Drive Test Workspace/a1' has all the files
        remote_children = [remote_info.name
                           for remote_info in self.remote_file_system_client_1.get_children_info(remote_ref_1)]
        self.assertEqual(len(remote_children), self.NUMBER_OF_LOCAL_FILES,
                         'remote folder /Nuxeo Drive Test Workspace/%s has %d files (expected %d)' %
                         (self.FOLDER_A1, len(remote_children), self.NUMBER_OF_LOCAL_FILES))

        log.debug('*** exit TestLocalPaste.test_copy_paste_empty_folder_first()')

    """
    copy 'a1' to 'Nuxeo Drive Test Workspace', then 'a2' to 'Nuxeo Drive Test Workspace'
    """
    def test_copy_paste_empty_folder_last(self):
        log.debug('*** enter TestLocalPaste.test_copy_paste_empty_folder_last()')
        workspace_abspath = self.local_client_1.abspath('/')
        # copy 'temp/a1' under 'Nuxeo Drive Test Workspace'
        shutil.copytree(self.folder1, os.path.join(workspace_abspath, self.FOLDER_A1))
        # copy 'temp/a2' under 'Nuxeo Drive Test Workspace'
        shutil.copytree(self.folder2, os.path.join(workspace_abspath, self.FOLDER_A2))
        self.wait_sync(timeout=TEST_TIMEOUT)

        # check that '/Nuxeo Drive Test Workspace/a1' does exist
        self.assertTrue(self.local_client_1.exists(os.path.join('/', self.FOLDER_A1)))
        # check that '/Nuxeo Drive Test Workspace/a2' does exist
        self.assertTrue(self.local_client_1.exists(os.path.join('/', self.FOLDER_A2)))
        # check that '/Nuxeo Drive Test Workspace/a1/ has all the files
        children = os.listdir(os.path.join(self.workspace_abspath, self.FOLDER_A1))
        self.assertEqual(len(children), self.NUMBER_OF_LOCAL_FILES,
                         'folder /Nuxeo Drive Test Workspace/%s has %d files (expected %d)' %
                         (self.FOLDER_A1, len(children), self.NUMBER_OF_LOCAL_FILES))
        # check that remote (DM) 'Nuxeo Drive Test Workspace/a1' exists
        remote_ref_1 = self.local_client_1.get_remote_id(os.path.join('/', self.FOLDER_A1))
        self.assertTrue(self.remote_file_system_client_1.exists(remote_ref_1))
        # check that remote (DM) 'Nuxeo Drive Test Workspace/a2' exists
        remote_ref_2 = self.local_client_1.get_remote_id(os.path.join('/', self.FOLDER_A2))
        self.assertTrue(self.remote_file_system_client_1.exists(remote_ref_2))
        # check that remote (DM) 'Nuxeo Drive Test Workspace/a1' has all the files
        remote_children = [remote_info.name
                           for remote_info in self.remote_file_system_client_1.get_children_info(remote_ref_1)]
        self.assertEqual(len(remote_children), self.NUMBER_OF_LOCAL_FILES,
                         'remote folder /Nuxeo Drive Test Workspace/%s has %d files (expected %d)' %
                         (self.FOLDER_A1, len(remote_children), self.NUMBER_OF_LOCAL_FILES))

        log.debug('*** exit TestLocalPaste.test_copy_paste_empty_folder_last()')

    """
    copy 'a1' to 'Nuxeo Drive Test Workspace', then 'a2' to 'Nuxeo Drive Test Workspace'
    """
    def test_copy_paste_same_file(self):
        log.debug('*** enter TestLocalPaste.test_copy_paste_same_file()')
        name = self.FILENAME_PATTERN % 1
        workspace_abspath = self.local_client_1.abspath('/')
        path = os.path.join('/', self.FOLDER_A1, name)
        copypath = os.path.join('/', self.FOLDER_A1, name + 'copy')
        # copy 'temp/a1' under 'Nuxeo Drive Test Workspace'
        os.mkdir(os.path.join(workspace_abspath, self.FOLDER_A1))
        shutil.copy2(os.path.join(self.folder1, name), os.path.join(workspace_abspath, self.FOLDER_A1, name))
        self.wait_sync(timeout=TEST_TIMEOUT)

        # check that '/Nuxeo Drive Test Workspace/a1' does exist
        self.assertTrue(self.local_client_1.exists(os.path.join('/', self.FOLDER_A1)))
        # check that '/Nuxeo Drive Test Workspace/a1/ has all the files
        children = os.listdir(os.path.join(self.workspace_abspath, self.FOLDER_A1))
        self.assertEqual(len(children), 1)
        # check that remote (DM) 'Nuxeo Drive Test Workspace/a1' exists
        remote_ref_1 = self.local_client_1.get_remote_id(os.path.join('/', self.FOLDER_A1))
        self.assertTrue(self.remote_file_system_client_1.exists(remote_ref_1))
        remote_children = [remote_info.name
                           for remote_info in self.remote_file_system_client_1.get_children_info(remote_ref_1)]
        self.assertEqual(len(remote_children), 1)
        remote_id = self.local_client_1.get_remote_id(path)

        log.debug('*** copy file TestLocalPaste.test_copy_paste_same_file()')
        shutil.copy2(self.local_client_1.abspath(path), self.local_client_1.abspath(copypath))
        self.local_client_1.set_remote_id(copypath, remote_id)
        log.debug('*** wait for sync TestLocalPaste.test_copy_paste_same_file()')
        self.wait_sync(timeout=TEST_TIMEOUT)
        remote_children = [remote_info.name
                           for remote_info in self.remote_file_system_client_1.get_children_info(remote_ref_1)]
        self.assertEqual(len(remote_children), 2)
        children = os.listdir(os.path.join(self.workspace_abspath, self.FOLDER_A1))
        self.assertEqual(len(children), 2)
        log.debug('*** exit TestLocalPaste.test_copy_paste_same_file()')
