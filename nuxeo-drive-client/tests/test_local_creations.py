import os
import shutil

import pytest

from common_unit_test import UnitTestCase
from nxdrive.logging_config import get_logger
from tests.common_unit_test import FILE_CONTENT

log = get_logger(__name__)


class TestLocalCreations(UnitTestCase):

    def test_local_create_folders_and_children_files(self):
        """
        1. create folder 'Nuxeo Drive Test Workspace/A' with 100 files in it
        2. create folder 'Nuxeo Drive Test Workspace/B'
        """

        len_text_files = 10
        len_pictures = 10
        total_files = len_text_files + len_pictures
    
        self.engine_1.get_local_watcher().set_windows_queue_threshold(1000)
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # create  folder A
        self.local_root_client_1.make_folder("/Nuxeo Drive Test Workspace", u'A')
        self.folder_path_1 = os.path.join("/Nuxeo Drive Test Workspace", u'A')

        # add text files in folder 'Nuxeo Drive Test Workspace/A'
        self.local_files_list = []
        for file_num in range(1, len_text_files + 1):
            filename = 'file%03d.txt' % file_num
            self.local_root_client_1.make_file(self.folder_path_1, filename, FILE_CONTENT)
            self.local_files_list.append(filename)

        self.test_doc_path = os.path.join(self.location + '/resources', 'cat.jpg')

        # add image files in folder 'Nuxeo Drive Test Workspace/A'
        abs_folder_path_1 = self.local_root_client_1.abspath(self.folder_path_1)
        for file_num in range(len_text_files + 1, total_files + 1):
            filename = 'file%03d.txt' % file_num
            dst_path = os.path.join(abs_folder_path_1, filename)
            shutil.copyfile(self.test_doc_path, dst_path)
            self.local_files_list.append(filename)

        # create  folder B
        self.local_root_client_1.make_folder("/Nuxeo Drive Test Workspace", u'B')
        self.folder_path_2 = os.path.join("/Nuxeo Drive Test Workspace", u'B')

        # wait for sync
        self.wait_sync(timeout=100)

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
                         total_files)

        # expect local 'Nuxeo Drive Test Workspace/A' to contain all the files
        abs_folder_path_1 = self.local_root_client_1.abspath(self.folder_path_1)
        self.assertTrue(os.path.exists(abs_folder_path_1))
        children_1 = os.listdir(abs_folder_path_1)
        postcondition1 = len(children_1) == total_files
        postcondition1_error = 'number of local files (%d) in "%s" is different from original (%d)' % \
                               (len(children_1), self.folder_path_1, total_files)
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

        postcondition3 = len(remote_children_1) == total_files
        postcondition3_error = 'number of remote files (%d) in "%s" is different from original (%d)' % \
                               (len(remote_children_1), remote_ref_1_name, total_files)
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

    @pytest.mark.timeout(20)
    def test_local_create_folders_upper_lower_cases(self):
        """
        Infinite loop when renaming a folder from lower case to upper case
        on Windows (or more specifically case insensitive OSes).

        We use a special timeout to prevent infinite loops when this test
        fails.  And it should until fixed, but keep it to detect regression.
        """

        remote = self.remote_document_client_1
        local = self.local_client_1
        engine = self.engine_1

        # Create an innocent file, lower case
        folder = 'abc'
        remote.make_folder('/', folder)
        engine.start()
        self.wait_sync(wait_for_async=True)

        # Check
        self.assertTrue(remote.exists('/' + folder))
        self.assertTrue(local.exists('/' + folder))

        # Locally rename to upper case.  A possible infinite loop can occur.
        folder_upper = folder.upper()
        local.rename('/' + folder, folder_upper)
        self.wait_sync()

        # Checks
        children = remote.get_children_info(self.workspace_1)
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].name, folder_upper)
        children = local.get_children_info('/')
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].name, folder_upper)

    @pytest.mark.timeout(20)
    def test_local_create_files_upper_lower_cases(self):
        """
        Infinite loop when renaming a file from lower case to upper case
        on Windows (or more specifically case insensitive OSes).

        We use a special timeout to prevent infinite loops when this test
        fails.  And it should until fixed, but keep it to detect regression.
        """

        remote = self.remote_document_client_1
        local = self.local_client_1
        engine = self.engine_1

        # Create an innocent file, lower case
        filename = 'abc.txt'
        remote.make_file('/', filename, content=b'cAsE')
        engine.start()
        self.wait_sync(wait_for_async=True)

        # Check
        self.assertTrue(remote.exists('/' + filename))
        self.assertTrue(local.exists('/' + filename))

        # Locally rename to upper case.  A possible infinite loop can occur.
        filename_upper = filename.upper()
        local.rename('/' + filename, filename_upper)
        self.wait_sync()

        # Checks
        children = remote.get_children_info(self.workspace_1)
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].name, filename_upper)
        children = local.get_children_info('/')
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].name, filename_upper)
