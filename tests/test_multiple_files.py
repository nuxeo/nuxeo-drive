# coding: utf-8
import os
import shutil
import sys
from logging import getLogger

import pytest

from nxdrive.osi import AbstractOSIntegration
from .common import FILE_CONTENT, UnitTestCase

log = getLogger(__name__)


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
        local = self.local_1
        # create  folder a1
        local.make_folder('/', ur'a1')
        self.folder_path_1 = os.path.join('/', 'a1')
        # add 100 files in folder 'Nuxeo Drive Test Workspace/a1'
        for file_num in range(1, self.NUMBER_OF_LOCAL_FILES + 1):
            local.make_file(self.folder_path_1, 'local%04d.txt' % file_num,
                            FILE_CONTENT)
        # create  folder a2
        local.make_folder('/', ur'a2')
        self.folder_path_2 = os.path.join('/', 'a2')
        self.folder_path_3 = os.path.join('/', 'a3')
        self.wait_sync(timeout=self.SYNC_TIMEOUT)

    def test_move_and_copy_paste_folder_original_location_from_child_stopped(self):
        self._move_and_copy_paste_folder_original_location_from_child()

    @pytest.mark.randombug('NXDRIVE-808', condition=(sys.platform == 'darwin'))
    def test_move_and_copy_paste_folder_original_location_from_child(self):
        self._move_and_copy_paste_folder_original_location_from_child(False)

    def _move_and_copy_paste_folder_original_location_from_child(
            self, stopped=True):
        local = self.local_1
        src = local.abspath(self.folder_path_1)
        dst = local.abspath(self.folder_path_2)
        shutil.move(src, dst)
        self.wait_sync(timeout=self.SYNC_TIMEOUT)
        self._move_and_copy_paste_folder('/a2/a1', '/', '/a2', stopped=stopped)

    def _move_and_copy_paste_folder(self, folder_1, folder_2, target_folder,
                                    stopped=True):
        """
        /folder_1
        /folder_2
        /target_folder
        Will
        move /folder1 inside /folder2/ as /folder2/folder1
        copy /folder2/folder1 into /target_folder/
        """
        if stopped:
            self.engine_1.stop()
        remote = self.remote_1
        local = self.local_1
        src = local.abspath(folder_1)
        dst = local.abspath(folder_2)
        new_path = os.path.join(folder_2, os.path.basename(folder_1))
        copy_path = os.path.join(target_folder, os.path.basename(folder_1))
        log.debug('*** shutil move')
        shutil.move(src, dst)
        # check that 'Nuxeo Drive Test Workspace/a1' does not exist anymore
        assert not local.exists(folder_1)
        # check that 'Nuxeo Drive Test Workspace/a2/a1' now exists
        assert local.exists(new_path)
        log.debug('*** shutil copy')
        # copy the 'Nuxeo Drive Test Workspace/a2/a1' tree
        # back under 'Nuxeo Drive Test Workspace'
        shutil.copytree(local.abspath(new_path),
                        local.abspath(copy_path))
        if stopped:
            self.engine_1.start()
        self.wait_sync(timeout=self.SYNC_TIMEOUT)
        log.debug('*** engine 1 synced')

        # asserts
        # expect '/a2/a1' to contain the files
        # expect 'Nuxeo Drive Test Workspace/a1' to also contain the files
        num = self.NUMBER_OF_LOCAL_FILES
        names = set(['local%04d.txt' % n for n in range(1, num + 1)])

        for path in (new_path, copy_path):
            # Local
            assert os.path.exists(local.abspath(path))
            children = os.listdir(local.abspath(path))

            assert len(children) == num,\
                'number of local files (%d) in "%s" is different ' \
                'from original (%d)' % (len(children), path, num)
            assert set(children) == names, 'file names are different'

            # Remote
            uid = local.get_remote_id(path)
            assert uid is not None
            log.debug('%s uid is %s', path, uid)

            children = remote.get_fs_children(uid)
            log.debug('Children of %s: %r', path, children)
            assert len(children) == num, \
                'number of remote files (%d) in "%s" is different ' \
                'from original (%d)' % (len(children), path, num)
            children_names = set([child.name for child in children])
            assert children_names == names, 'file names are different'

        log.debug('*** exit MultipleFilesTestCase._move_and_copy_paste_folder')

    @pytest.mark.randombug('NXDRIVE-720', condition=(sys.platform == 'linux2'))
    @pytest.mark.randombug('NXDRIVE-813', condition=(sys.platform == 'darwin'))
    def test_move_and_copy_paste_folder_original_location(self):
        self._move_and_copy_paste_folder(self.folder_path_1, self.folder_path_2,
                                         os.path.dirname(self.folder_path_1),
                                         stopped=False)

    @pytest.mark.skipif(AbstractOSIntegration.is_linux(),
                        reason='NXDRIVE-471: Not handled under GNU/Linux as '
                        'creation time is not stored')
    def test_move_and_copy_paste_folder_original_location_stopped(self):
        self._move_and_copy_paste_folder(
            self.folder_path_1, self.folder_path_2,
            os.path.dirname(self.folder_path_1))

    def test_move_and_copy_paste_folder_new_location(self):
        self._move_and_copy_paste_folder(
            self.folder_path_1, self.folder_path_2, self.folder_path_3)
