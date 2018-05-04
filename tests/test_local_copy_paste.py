# coding: utf-8
import os
import shutil
import sys

from .common_unit_test import FILE_CONTENT, RandomBug, UnitTestCase


class TestLocalCopyPaste(UnitTestCase):

    NUMBER_OF_LOCAL_TEXT_FILES = 10
    NUMBER_OF_LOCAL_IMAGE_FILES = 10
    NUMBER_OF_LOCAL_FILES_TOTAL = (NUMBER_OF_LOCAL_TEXT_FILES +
                                   NUMBER_OF_LOCAL_IMAGE_FILES)
    FILE_NAME_PATTERN = 'file%03d%s'
    TEST_DOC_RESOURCE = 'cat.jpg'
    FOLDER_1 = u'A'
    FOLDER_2 = u'B'
    SYNC_TIMEOUT = 100  # in seconds

    """
    1. create folder 'Nuxeo Drive Test Workspace/A' with 100 files in it
    2. create folder 'Nuxeo Drive Test Workspace/B'
    """

    def setUp(self):
        super(TestLocalCopyPaste, self).setUp()

        remote = self.remote_1
        local_root = self.local_root_client_1
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.engine_1.stop()
        assert local_root.exists('/Nuxeo Drive Test Workspace'),\
            'Nuxeo Drive Test Workspace should be sync'

        # create  folder A
        local_root.make_folder('/Nuxeo Drive Test Workspace', self.FOLDER_1)
        self.folder_path_1 = os.path.join('/Nuxeo Drive Test Workspace',
                                          self.FOLDER_1)

        # create  folder B
        # NXDRIVE-477 If created after files are created inside A,
        # creation of B isn't detected wy Watchdog!
        # Reproducible with watchdemo, need to investigate.
        # That's why we are now using local scan for setUp.
        local_root.make_folder('/Nuxeo Drive Test Workspace', self.FOLDER_2)
        self.folder_path_2 = os.path.join('/Nuxeo Drive Test Workspace',
                                          self.FOLDER_2)

        # add text files in folder 'Nuxeo Drive Test Workspace/A'
        self.local_files_list = []
        for file_num in range(1, self.NUMBER_OF_LOCAL_TEXT_FILES + 1):
            filename = self.FILE_NAME_PATTERN % (file_num, '.txt')
            local_root.make_file(self.folder_path_1, filename, FILE_CONTENT)
            self.local_files_list.append(filename)

        test_resources_path = self._get_test_resources_path()
        if test_resources_path is None:
            test_resources_path = 'tests/resources'
        self.test_doc_path = os.path.join(test_resources_path,
                                          TestLocalCopyPaste.TEST_DOC_RESOURCE)

        # add image files in folder 'Nuxeo Drive Test Workspace/A'
        abs_folder_path_1 = local_root.abspath(self.folder_path_1)
        for file_num in range(self.NUMBER_OF_LOCAL_TEXT_FILES + 1,
                              self.NUMBER_OF_LOCAL_FILES_TOTAL + 1):
            filename = self.FILE_NAME_PATTERN % (file_num, os.path.splitext(
                self.TEST_DOC_RESOURCE)[1])
            dst_path = os.path.join(abs_folder_path_1, filename)
            shutil.copyfile(self.test_doc_path, dst_path)
            self.local_files_list.append(filename)

        self.engine_1.start()
        self.wait_sync(timeout=self.SYNC_TIMEOUT)
        self.engine_1.stop()

        # get remote folders reference ids
        self.remote_ref_1 = local_root.get_remote_id(self.folder_path_1)
        assert self.remote_ref_1 is not None
        self.remote_ref_2 = local_root.get_remote_id(self.folder_path_2)
        assert self.remote_ref_2 is not None
        assert remote.fs_exists(self.remote_ref_1),\
            'remote folder for %s does not exist' % self.folder_path_1
        assert remote.fs_exists(self.remote_ref_2),\
            'remote folder for %s does not exist' % self.folder_path_2

        assert (len(remote.get_fs_children(self.remote_ref_1))
                == self.NUMBER_OF_LOCAL_FILES_TOTAL)

    # @RandomBug('NXDRIVE-815', target='mac', repeat=5)
    # @RandomBug('NXDRIVE-815', target='windows', repeat=5)
    def test_local_copy_paste_files(self):
        self._local_copy_paste_files()

    def test_local_copy_paste_files_stopped(self):
        self._local_copy_paste_files(stopped=True)

    def _local_copy_paste_files(self, stopped=False):
        if not stopped:
            self.engine_1.start()
        # copy all children (files) of A to B
        remote = self.remote_1
        local_root = self.local_root_client_1
        src = local_root.abspath(self.folder_path_1)
        dst = local_root.abspath(self.folder_path_2)
        num = self.NUMBER_OF_LOCAL_FILES_TOTAL
        for f in os.listdir(src):
            shutil.copy(os.path.join(src, f), dst)
        if stopped:
            self.engine_1.start()
        self.wait_sync(timeout=self.SYNC_TIMEOUT)

        # expect local 'Nuxeo Drive Test Workspace/A' to contain all the files
        abs_folder_path_1 = local_root.abspath(self.folder_path_1)
        assert os.path.exists(abs_folder_path_1)
        children_1 = os.listdir(abs_folder_path_1)

        cond1 = len(children_1) == num
        error1 = ('number of local files (%d) in "%s" is different '
                  'from original (%d)') % (len(children_1),
                                           self.folder_path_1, num)
        expected = set(self.local_files_list)
        actual = set(children_1)
        cond2 = actual == expected

        if not cond2:
            extra = '\n'.join(actual.difference(expected))
            missing = '\n'.join(expected.difference(actual))
            error2 = ('file names in "%s" are different, e.g. duplicate files '
                      '(renamed)\nunexpected files:\n%s\n\nmissing '
                      'files\n%s') % (self.folder_path_1, extra, missing)

        # expect local 'Nuxeo Drive Test Workspace/B' to contain the same files
        abs_folder_path_2 = local_root.abspath(self.folder_path_2)
        assert os.path.exists(abs_folder_path_2)
        children_2 = os.listdir(abs_folder_path_2)
        cond3 = len(children_2) == num
        error3 = ('number of local files (%d) in "%s" is different '
                  'from original (%d)') % (len(children_2),
                                           self.folder_path_2, num)

        actual = set(children_2)
        cond4 = actual == expected
        if not cond4:
            extra = '\n'.join(actual.difference(expected))
            missing = '\n'.join(expected.difference(actual))
            error4 = ('file names in "%s" are different, e.g. duplicate files '
                      '(renamed)\nunexpected files:\n%s\n\nmissing '
                      'files\n%s') % (self.folder_path_2, extra, missing)

        # expect remote 'Nuxeo Drive Test Workspace/A' to contain all the files
        # just compare the names
        remote_ref_1_name = remote.get_fs_info(self.remote_ref_1).name
        remote_children_1 = [remote_info.name
                             for remote_info in remote.get_fs_children(
                                self.remote_ref_1)]

        cond5 = len(remote_children_1) == num
        error5 = ('number of remote files (%d) in "%s" is different '
                  'from original (%d)') % (len(remote_children_1),
                                           remote_ref_1_name, num)

        remote_expected = set(self.local_files_list)
        remote_actual = set(remote_children_1)
        cond6 = remote_actual == remote_expected
        if not cond6:
            extra = '\n'.join(actual.difference(remote_expected))
            missing = '\n'.join(expected.difference(remote_actual))
            error6 = ('remote file names in "%s" are different, e.g. '
                      'duplicate files (renamed)\nunexpected files:'
                      '\n%s\n\nmissing files\n%s') % (remote_ref_1_name,
                                                      extra, missing)

        # expect remote 'Nuxeo Drive Test Workspace/B' to contain all the files
        # just compare the names
        remote_ref_2_name = remote.get_fs_info(self.remote_ref_2).name
        remote_children_2 = [remote_info.name
                             for remote_info
                             in remote.get_fs_children(self.remote_ref_2)]

        cond7 = len(remote_children_2) == num
        error7 = ('number of remote files (%d) in "%s" is different '
                  'from original (%d)') % (len(remote_children_2),
                                           remote_ref_2_name, num)
        remote_expected = set(self.local_files_list)
        remote_actual = set(remote_children_2)
        cond8 = remote_actual == remote_expected
        if not cond8:
            extra = '\n'.join(actual.difference(remote_expected))
            missing = '\n'.join(expected.difference(remote_actual))
            error8 = ('remote file names in "%s" are different, e.g. '
                      'duplicate files (renamed)\nunexpected files:'
                      '\n%s\n\nmissing files\n%s') % (remote_ref_2_name,
                                                      extra, missing)

        assert cond1, error1
        assert cond2, error2
        assert cond3, error3
        assert cond4, error4
        assert cond5, error5
        assert cond6, error6
        assert cond7, error7
        assert cond8, error8

    def _get_test_resources_path(self):
        module = sys.modules[self.__module__]
        test_resources_path = os.path.join(
            os.path.dirname(module.__file__), 'resources')
        return test_resources_path
