# coding: utf-8
import os
import shutil
import sys
import time
from logging import getLogger

import pytest

from common_unit_test import UnitTestCase
from .common_unit_test import FILE_CONTENT

log = getLogger(__name__)


class TestLocalCreations(UnitTestCase):

    def test_mini_scenario(self):
        local = self.local_root_client_1
        remote = self.remote_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        local.make_folder('/' + self.workspace_title, 'A')
        folder_path_1 = self.workspace_title + '/A'

        test_doc_path = os.path.join(self.location, 'resources', 'cat.jpg')
        abs_folder_path_1 = local.abspath('/' + folder_path_1)
        dst_path = os.path.join(abs_folder_path_1, 'cat.jpg')
        shutil.copyfile(test_doc_path, dst_path)

        self.wait_sync(timeout=100)
        uid = local.get_remote_id('/' + folder_path_1 + '/cat.jpg')
        assert remote.fs_exists(uid)

    def test_local_create_folders_and_children_files(self):
        """
        1. create folder 'Nuxeo Drive Test Workspace/A' with 100 files in it
        2. create folder 'Nuxeo Drive Test Workspace/B'
        """

        local = self.local_root_client_1
        remote = self.remote_1
        len_text_files = 10
        len_pictures = 10
        total_files = len_text_files + len_pictures
    
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Create the folder A
        local.make_folder('/' + self.workspace_title, 'A')
        folder_path_1 = self.workspace_title + '/A'

        # Add text files into A
        for file_num in range(1, len_text_files + 1):
            filename = 'file_%02d.txt' % file_num
            local.make_file('/' + folder_path_1, filename, FILE_CONTENT)

        # Add pictures into A
        test_doc_path = os.path.join(self.location, 'resources', 'cat.jpg')
        abs_folder_path_1 = local.abspath('/' + folder_path_1)
        for file_num in range(len_text_files + 1, total_files + 1):
            filename = 'file_%02d.jpg' % file_num
            dst_path = os.path.join(abs_folder_path_1, filename)
            shutil.copyfile(test_doc_path, dst_path)

        # Create the folder B, and sync
        local.make_folder('/' + self.workspace_title, 'B')
        folder_path_2 = self.workspace_title + '/B'
        self.wait_sync(timeout=100)

        # Get remote folders reference IDs
        remote_ref_1 = local.get_remote_id('/' + folder_path_1)
        assert remote_ref_1 is not None
        assert remote.fs_exists(remote_ref_1)
        remote_ref_2 = local.get_remote_id('/' + folder_path_2)
        assert remote_ref_2 is not None
        assert remote.fs_exists(remote_ref_2)

        assert len(remote.get_fs_children(remote_ref_1)) == total_files

    @pytest.mark.timeout(40)
    def test_local_create_folders_upper_lower_cases(self):
        """
        Infinite loop when renaming a folder from lower case to upper case
        on Windows (or more specifically case insensitive OSes).

        We use a special timeout to prevent infinite loops when this test
        fails.  And it should until fixed, but keep it to detect regression.
        """

        remote = self.remote_document_client_1
        local = self.local_1
        engine = self.engine_1

        # Create an innocent folder, lower case
        folder = 'abc'
        remote.make_folder('/', folder)
        engine.start()
        self.wait_sync(wait_for_async=True)

        # Check
        assert remote.exists('/' + folder)
        assert local.exists('/' + folder)

        # Locally rename to upper case.  A possible infinite loop can occur.
        folder_upper = folder.upper()
        local.rename('/' + folder, folder_upper)
        self.wait_sync()

        # Checks
        children = remote.get_children_info(self.workspace_1)
        assert len(children) ==  1
        assert children[0].name ==  folder_upper
        children = local.get_children_info('/')
        assert len(children) ==  1
        assert children[0].name ==  folder_upper

    @pytest.mark.timeout(40)
    def test_local_create_files_upper_lower_cases(self):
        """
        Infinite loop when renaming a file from lower case to upper case
        on Windows (or more specifically case insensitive OSes).

        We use a special timeout to prevent infinite loops when this test
        fails.  And it should until fixed, but keep it to detect regression.
        """

        remote = self.remote_document_client_1
        local = self.local_1
        engine = self.engine_1

        # Create an innocent file, lower case
        filename = 'abc.txt'
        remote.make_file('/', filename, content=b'cAsE')
        engine.start()
        self.wait_sync(wait_for_async=True)

        # Check
        assert remote.exists('/' + filename)
        assert local.exists('/' + filename)

        # Locally rename to upper case.  A possible infinite loop can occur.
        filename_upper = filename.upper()
        local.rename('/' + filename, filename_upper)
        self.wait_sync()

        # Checks
        children = remote.get_children_info(self.workspace_1)
        assert len(children) ==  1
        assert children[0].name ==  filename_upper
        children = local.get_children_info('/')
        assert len(children) ==  1
        assert children[0].name ==  filename_upper

    def test_local_create_folders_with_dots(self):
        """ Check that folders containing dots are well synced. """

        remote = self.remote_document_client_1
        local = self.local_1
        engine = self.engine_1

        engine.start()
        self.wait_sync(wait_for_async=True)

        folder1 = 'Affaire.1487689320370'
        folder2 = 'Affaire.1487689320.370'
        local.make_folder('/', folder1)
        local.make_folder('/', folder2)
        self.wait_sync()

        # Check
        assert remote.exists('/' + folder1)
        assert remote.exists('/' + folder2)
        assert local.exists('/' + folder1)
        assert local.exists('/' + folder2)

    def test_local_modification_date(self):
        """ Check that the files have the Platform modification date. """
        remote = self.remote_document_client_1
        local = self.local_1
        engine = self.engine_1

        filename = 'abc.txt'
        remote.make_file('/', filename, content=b'1234')
        remote_mtime = time.time()

        time.sleep(3)

        engine.start()
        self.wait_sync(wait_for_async=True)

        filename = '/{}'.format(filename)
        assert local.exists(filename)
        assert os.stat(local.abspath(filename)).st_mtime < remote_mtime

    def test_local_creation_date(self):
        """ Check that the files have the Platform modification date. """
        remote = self.remote_1
        local = self.local_1
        engine = self.engine_1

        workspace_id = 'defaultSyncRootFolderItemFactory#default#{}'.format(
            self.workspace)

        filename = 'abc.txt'
        file_id = remote.make_file(workspace_id, filename, content=b'1234').uid
        after_ctime = time.time()

        time.sleep(3)
        filename = 'a' + filename
        remote.rename(file_id, filename)
        after_mtime = time.time()

        engine.start()
        self.wait_sync(wait_for_async=True)

        filename = '/{}'.format(filename)
        assert local.exists(filename)
        local_mtime = os.stat(local.abspath(filename)).st_mtime

        if sys.platform in ('darwin', 'win32'):
            if sys.platform == 'darwin':
                local_ctime = os.stat(local.abspath(filename)).st_birthtime
            else:
                local_ctime = os.stat(local.abspath(filename)).st_ctime
            assert local_ctime < after_ctime
            assert local_ctime + 3 <= local_mtime

        assert local_mtime < after_mtime
