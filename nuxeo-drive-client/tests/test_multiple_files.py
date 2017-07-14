'''
Created on Jul 29, 2015

@author: constantinm
Adapted to Drive
'''

import os
import shutil
from unittest import skipIf

from nxdrive.logging_config import get_logger
from nxdrive.osi import AbstractOSIntegration
from tests.common_unit_test import FILE_CONTENT, RandomBug, UnitTestCase

log = get_logger(__name__)


class MultipleFilesTestCase(UnitTestCase):

    NUMBER_OF_LOCAL_FILES = 10
    SYNC_TIMEOUT = 200  # in seconds

    def setUp(self):
        """
        1. create folder 'Nuxeo Drive Test Workspace/a1' with 100 files in it
        2. create folder 'Nuxeo Drive Test Workspace/a2'
        2. create folder 'Nuxeo Drive Test Workspace/a3'
        """
        super(MultipleFilesTestCase, self).setUp()

        self.engine_1.start()
        self.wait_sync()

        # create  folder a1
        self.local_client_1.make_folder("/", ur'a1')
        self.folder_path_1 = os.path.join("/", 'a1')
        # add 100 files in folder 'Nuxeo Drive Test Workspace/a1'
        for file_num in range(1, self.NUMBER_OF_LOCAL_FILES + 1):
            self.local_client_1.make_file(self.folder_path_1,
                                          'local%04d.txt' % file_num,
                                          FILE_CONTENT)
        # create  folder a2
        self.local_client_1.make_folder("/", ur'a2')
        self.folder_path_2 = os.path.join("/", 'a2')
        self.folder_path_3 = os.path.join("/", 'a3')
        self.wait_sync(timeout=self.SYNC_TIMEOUT)

    def test_move_and_copy_paste_folder_original_location_from_child_stopped(self):
        self._move_and_copy_paste_folder_original_location_from_child()

    @RandomBug('NXDRIVE-808', target='mac')
    def test_move_and_copy_paste_folder_original_location_from_child(self):
        self._move_and_copy_paste_folder_original_location_from_child(False)

    def _move_and_copy_paste_folder_original_location_from_child(self, stopped=True):
        src = self.local_client_1.abspath(self.folder_path_1)
        dst = self.local_client_1.abspath(self.folder_path_2)
        shutil.move(src, dst)
        self.wait_sync(timeout=self.SYNC_TIMEOUT)
        self._move_and_copy_paste_folder("/a2/a1", "/", "/a2", stopped=stopped)

    def _move_and_copy_paste_folder(self, folder_1, folder_2, target_folder, stopped=True):
        '''
        /folder_1
        /folder_2
        /target_folder
        Will
        move /folder1 inside /folder2/ as /folder2/folder1
        copy /folder2/folder1 into /target_folder/
        '''
        if stopped:
            self.engine_1.stop()
        src = self.local_client_1.abspath(folder_1)
        dst = self.local_client_1.abspath(folder_2)
        new_path = os.path.join(folder_2, os.path.basename(folder_1))
        copy_path = os.path.join(target_folder, os.path.basename(folder_1))
        log.debug("*** shutil move")
        shutil.move(src, dst)
        # check that 'Nuxeo Drive Test Workspace/a1' does not exist anymore
        self.assertFalse(self.local_client_1.exists(folder_1))
        # check that 'Nuxeo Drive Test Workspace/a2/a1' now exists
        self.assertTrue(self.local_client_1.exists(new_path))
        log.debug('*** shutil copy')
        # copy the 'Nuxeo Drive Test Workspace/a2/a1' tree back under 'Nuxeo Drive Test Workspace'
        shutil.copytree(self.local_client_1.abspath(new_path),
                        self.local_client_1.abspath(copy_path))
        if stopped:
            self.engine_1.start()
        self.wait_sync(timeout=self.SYNC_TIMEOUT)
        log.debug('*** engine 1 synced')

        # asserts
        # expect '/a2/a1' to contain the files
        self.assertTrue(os.path.exists(self.local_client_1.abspath(new_path)))
        children_1 = os.listdir(self.local_client_1.abspath(new_path))
        self.assertEqual(len(children_1), self.NUMBER_OF_LOCAL_FILES,
                         'number of local files (%d) in "%s" is different from original (%d)' %
                         (len(children_1), new_path, self.NUMBER_OF_LOCAL_FILES))
        self.assertEqual(set(children_1), set(['local%04d.txt' % file_num
                                              for file_num in range(1, self.NUMBER_OF_LOCAL_FILES + 1)]),
                         'file names are different')
        # expect 'Nuxeo Drive Test Workspace/a1' to contain also the files
        self.assertTrue(os.path.exists(self.local_client_1.abspath(copy_path)))
        children_2 = os.listdir(self.local_client_1.abspath(copy_path))
        self.assertEqual(len(children_2), self.NUMBER_OF_LOCAL_FILES,
                         'number of local files (%d)in "%s" is different from original (%d)' %
                         (len(children_2), copy_path, self.NUMBER_OF_LOCAL_FILES))
        self.assertEqual(set(children_2), set(['local%04d.txt' % file_num
                                              for file_num in range(1, self.NUMBER_OF_LOCAL_FILES + 1)]),
                         'file names are different')
        # verify the remote one
        a1copy_uid = self.local_client_1.get_remote_id(copy_path)
        self.assertIsNotNone(a1copy_uid)
        a1_uid = self.local_client_1.get_remote_id(new_path)
        self.assertIsNotNone(a1_uid)
        try:
            log.debug("%s and %s: %s/%s", new_path, copy_path, a1_uid, a1copy_uid)
            children_1 = self.remote_file_system_client_1.get_children_info(a1_uid)
            children_2 = self.remote_file_system_client_1.get_children_info(a1copy_uid)
            log.debug("Children1: %r", children_1)
            log.debug("Children2: %r", children_2)
        except:
            pass
        self.assertEqual(len(children_1), self.NUMBER_OF_LOCAL_FILES,
                         'number of remote files (%d) in "%s" is different from original (%d)' %
                         (len(children_1), new_path, self.NUMBER_OF_LOCAL_FILES))
        children_1_name = set()
        for child in children_1:
            children_1_name.add(child.name)
        self.assertEqual(set(children_1_name), set(['local%04d.txt' % file_num
                                                    for file_num in range(1, self.NUMBER_OF_LOCAL_FILES + 1)]),
                         'file names are different')
        self.assertEqual(len(children_2), self.NUMBER_OF_LOCAL_FILES,
                         'number of remote files (%d) in "%s" is different from original (%d)' %
                         (len(children_2), copy_path, self.NUMBER_OF_LOCAL_FILES))
        children_2_name = set()
        for child in children_2:
            children_2_name.add(child.name)
        self.assertEqual(set(children_2_name), set(['local%04d.txt' % file_num
                                                    for file_num in range(1, self.NUMBER_OF_LOCAL_FILES + 1)]),
                         'file names are different')
        log.debug('*** exit MultipleFilesTestCase._move_and_copy_paste_folder')

    @RandomBug('NXDRIVE-720', target='linux')
    @RandomBug('NXDRIVE-813', target='mac')
    def test_move_and_copy_paste_folder_original_location(self):
        self._move_and_copy_paste_folder(self.folder_path_1, self.folder_path_2,
                                         os.path.dirname(self.folder_path_1),
                                         stopped=False)

    @skipIf(AbstractOSIntegration.is_linux(),
            'NXDRIVE-471: Not handled under GNU/Linux as'
            ' creation time is not stored')
    def test_move_and_copy_paste_folder_original_location_stopped(self):
        self._move_and_copy_paste_folder(self.folder_path_1, self.folder_path_2,
                                         os.path.dirname(self.folder_path_1))

    def test_move_and_copy_paste_folder_new_location(self):
        self._move_and_copy_paste_folder(self.folder_path_1, self.folder_path_2,
                                         self.folder_path_3)
