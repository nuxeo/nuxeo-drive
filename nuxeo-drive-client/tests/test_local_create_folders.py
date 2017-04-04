from common_unit_test import UnitTestCase
from tests.common_unit_test import log
from tests.common_unit_test import FILE_CONTENT
import os
import sys
import shutil


class TestLocalCreateFolders(UnitTestCase):

    NUMBER_OF_LOCAL_TEXT_FILES = 10
    NUMBER_OF_LOCAL_IMAGE_FILES = 10
    NUMBER_OF_LOCAL_FILES_TOTAL = NUMBER_OF_LOCAL_TEXT_FILES + NUMBER_OF_LOCAL_IMAGE_FILES
    FILE_NAME_PATTERN = 'file%03d.%s'
    TEST_DOC_RESOURCE = 'cat.jpg'
    FOLDER_1 = u'A'
    FOLDER_2 = u'B'
    SYNC_TIMEOUT = 100  # in seconds

    def setUp(self):
        super(TestLocalCreateFolders, self).setUp()

        log.debug('*** enter TestLocalCreateFolders.setUp() ***')
        log.debug('*** engine1 starting ***')
        self.engine_1.get_local_watcher().set_windows_queue_threshold(1000)
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        log.debug('*** engine1 synced ***')
        log.debug("full local root path %s", self.local_root_client_1.get_info("/"))
        self.assertTrue(self.local_root_client_1.exists('/Nuxeo Drive Test Workspace'),
                        "Nuxeo Drive Test Workspace should be sync")

        log.debug('*** exit TestLocalCreateFolders.setUp() ***')

    def tearDown(self):
        log.debug('*** enter TestLocalCreateFolders.tearDown() ***')
        # list content of folder A
        abs_folder_path_1 = self.local_root_client_1.abspath(self.folder_path_1)
        log.debug('content of folder "%s"', abs_folder_path_1)
        for f in os.listdir(abs_folder_path_1):
            log.debug(f)

        # list content of folder B
        abs_folder_path_2 = self.local_root_client_1.abspath(self.folder_path_2)
        log.debug('content of folder "%s"', abs_folder_path_2)
        for f in os.listdir(abs_folder_path_2):
            log.debug(f)

        super(TestLocalCreateFolders, self).tearDown()
        log.debug('*** exit TestLocalCreateFolders.tearDown() ***')

    '''
        1. create folder 'Nuxeo Drive Test Workspace/A' with 100 files in it
        2. create folder 'Nuxeo Drive Test Workspace/B'
    '''
    def test_local_create_folders_and_children_files(self):
        log.debug('*** enter TestLocalCreateFolders.test_local_create_folders_and_children_files() ***')

        # create  folder A
        self.local_root_client_1.make_folder("/Nuxeo Drive Test Workspace", self.FOLDER_1)
        self.folder_path_1 = os.path.join("/Nuxeo Drive Test Workspace", self.FOLDER_1)

        # add text files in folder 'Nuxeo Drive Test Workspace/A'
        self.local_files_list = []
        for file_num in range(1, self.NUMBER_OF_LOCAL_TEXT_FILES + 1):
            filename = self.FILE_NAME_PATTERN % (file_num, 'txt')
            self.local_root_client_1.make_file(self.folder_path_1, filename, FILE_CONTENT)
            self.local_files_list.append(filename)

        test_resources_path = self._get_test_resources_path()
        if test_resources_path is None:
            test_resources_path = 'tests/resources'
        self.test_doc_path = os.path.join(test_resources_path, TestLocalCreateFolders.TEST_DOC_RESOURCE)

        # add image files in folder 'Nuxeo Drive Test Workspace/A'
        abs_folder_path_1 = self.local_root_client_1.abspath(self.folder_path_1)
        for file_num in range(self.NUMBER_OF_LOCAL_TEXT_FILES + 1, self.NUMBER_OF_LOCAL_FILES_TOTAL + 1):
            filename = self.FILE_NAME_PATTERN % (file_num, os.path.splitext(self.TEST_DOC_RESOURCE)[1])
            dst_path = os.path.join(abs_folder_path_1, filename)
            shutil.copyfile(self.test_doc_path, dst_path)
            self.local_files_list.append(filename)
        log.debug('local test files created in Nuxeo Drive Test Workspace/A')

        # create  folder B
        self.local_root_client_1.make_folder("/Nuxeo Drive Test Workspace", self.FOLDER_2)
        self.folder_path_2 = os.path.join("/Nuxeo Drive Test Workspace", self.FOLDER_2)

        # wait for sync
        self.wait_sync(timeout=self.SYNC_TIMEOUT)
        log.debug('*** engine1 synced ***')

        # get remote folders reference ids
        self.remote_ref_1 = self.local_root_client_1.get_remote_id(self.folder_path_1)
        self.assertIsNotNone(self.remote_ref_1)
        self.remote_ref_2 = self.local_root_client_1.get_remote_id(self.folder_path_2)
        self.assertIsNotNone(self.remote_ref_2)

        self.assertTrue(self.remote_file_system_client_1.exists(self.remote_ref_1),
                        'remote folder for %s does not exist' % self.folder_path_1)
        self.assertTrue(self.remote_file_system_client_1.exists(self.remote_ref_2),
                        'remote folder for %s does not exist' % self.folder_path_2)

        self.assertEqual(len(self.remote_file_system_client_1.get_children_info(self.remote_ref_1)),
                         self.NUMBER_OF_LOCAL_FILES_TOTAL)

        # expect local 'Nuxeo Drive Test Workspace/A' to contain all the files
        abs_folder_path_1 = self.local_root_client_1.abspath(self.folder_path_1)
        self.assertTrue(os.path.exists(abs_folder_path_1))
        children_1 = os.listdir(abs_folder_path_1)
        postcondition1 = len(children_1) == self.NUMBER_OF_LOCAL_FILES_TOTAL
        postcondition1_error = 'number of local files (%d) in "%s" is different from original (%d)' % \
                               (len(children_1), self.folder_path_1, self.NUMBER_OF_LOCAL_FILES_TOTAL)
        local_files_expected = set(self.local_files_list)
        local_files_actual = set(children_1)
        postcondition2 = local_files_actual == local_files_expected
        postcondition2_error = 'file names in "%s" are different, e.g. duplicate files (renamed)' % self.folder_path_1
        if not postcondition2:
            unexpected_actual_files = '\n'.join(local_files_actual.difference(local_files_expected))
            missing_expected_files = '\n'.join(local_files_expected.difference(local_files_actual))
            postcondition2_error += '\nunexpected files:\n%s\n\nmissing files\n%s' % (unexpected_actual_files,
                                                                                      missing_expected_files)

        # expect local 'Nuxeo Drive Test Workspace/B' to exist
        abs_folder_path_2 = self.local_root_client_1.abspath(self.folder_path_2)
        self.assertTrue(os.path.exists(abs_folder_path_2))

        # expect remote 'Nuxeo Drive Test Workspace/A' to contain all the files
        # just compare the names
        remote_ref_1_name = self.remote_file_system_client_1.get_info(self.remote_ref_1).name
        remote_children_1 = [remote_info.name
                             for remote_info in self.remote_file_system_client_1.get_children_info(self.remote_ref_1)]

        postcondition3 = len(remote_children_1) == self.NUMBER_OF_LOCAL_FILES_TOTAL
        postcondition3_error = 'number of remote files (%d) in "%s" is different from original (%d)' % \
                               (len(remote_children_1), remote_ref_1_name, self.NUMBER_OF_LOCAL_FILES_TOTAL)
        remote_files_expected = set(self.local_files_list)
        remote_files_actual = set(remote_children_1)
        postcondition4 = remote_files_actual == remote_files_expected
        postcondition4_error = ('remote file names in "%s" are different, e.g. duplicate files (renamed)'
                                % remote_ref_1_name)
        if not postcondition4:
            unexpected_actual_files = '\n'.join(local_files_actual.difference(remote_files_expected))
            missing_expected_files = '\n'.join(local_files_expected.difference(remote_files_actual))
            postcondition4_error += '\nunexpected files:\n%s\n\nmissing files\n%s' % (unexpected_actual_files,
                                                                                      missing_expected_files)

        # output the results before asserting
        if not postcondition1:
            log.debug(postcondition1_error)
        if not postcondition2:
            log.debug(postcondition2_error)
        if not postcondition3:
            log.debug(postcondition3_error)
        if not postcondition4:
            log.debug(postcondition4_error)

        self.assertTrue(postcondition1, postcondition1_error)
        self.assertTrue(postcondition2, postcondition2_error)
        self.assertTrue(postcondition3, postcondition3_error)
        self.assertTrue(postcondition4, postcondition4_error)
        log.debug('*** exit TestLocalCreateFolders.test_local_create_folders_and_children_files() ***')

    def _get_test_resources_path(self):
        try:
            module = sys.modules[self.__module__]
            test_resources_path = os.path.join(os.path.dirname(module.__file__), 'resources')
            return test_resources_path
        except Exception as e:
            log.error('path error: ', e)
