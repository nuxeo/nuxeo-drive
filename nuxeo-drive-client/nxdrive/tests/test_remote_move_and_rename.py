import os
import time
import sys

from nxdrive.tests.common import REMOTE_MODIFICATION_TIME_RESOLUTION
from nxdrive.tests.common_unit_test import UnitTestCase
from nxdrive.client import LocalClient
from nxdrive.client import RemoteDocumentClient
from nxdrive.engine.engine import Engine
from shutil import copyfile
from mock import patch


class TestRemoteMoveAndRename(UnitTestCase):

    # Sets up the following remote hierarchy:
    # Nuxeo Drive Test Workspace
    #    |-- Original File 1.txt
    #    |-- Original File 2.txt
    #    |-- Original Folder 1
    #    |       |-- Sub-Folder 1.1
    #    |       |-- Sub-Folder 1.2
    #    |       |-- Original File 1.1.txt
    #    |-- Original Folder 2
    #    |       |-- Original File 3.txt

    def setUp(self):
        super(TestRemoteMoveAndRename, self).setUp()
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.remote_client_1 = self.remote_file_system_client_1

        self.workspace_id = ('defaultSyncRootFolderItemFactory#default#'
                            + self.workspace)
        self.workspace_pair_local_path = u'/' + self.workspace_title

        self.file_1_id = self.remote_client_1.make_file(self.workspace_id,
            u'Original File 1.txt',
            content=u'Some Content 1'.encode('utf-8')).uid

        self.file_2_id = self.remote_client_1.make_file(self.workspace_id,
            u'Original File 2.txt',
            content=u'Some Content 2'.encode('utf-8')).uid

        self.folder_1_id = self.remote_client_1.make_folder(self.workspace_id,
            u'Original Folder 1').uid
        self.folder_1_1_id = self.remote_client_1.make_folder(
            self.folder_1_id, u'Sub-Folder 1.1').uid
        self.folder_1_2_id = self.remote_client_1.make_folder(
            self.folder_1_id, u'Sub-Folder 1.2').uid
        self.file_1_1_id = self.remote_client_1.make_file(
            self.folder_1_id,
            u'Original File 1.1.txt',
            content=u'Some Content 1'.encode('utf-8')).uid  # Same content as OF1

        self.folder_2_id = self.remote_client_1.make_folder(self.workspace_id,
            'Original Folder 2').uid
        self.file_3_id = self.remote_client_1.make_file(self.folder_2_id,
            u'Original File 3.txt',
            content=u'Some Content 3'.encode('utf-8')).uid
        self.wait_sync(wait_for_async=True)

    def _get_state(self, remote):
        return self.engine_1.get_dao().get_normal_state_from_remote(remote)

    def _remote_rename_while_upload(self):
        # Get local and remote clients
        local = self.local_client_1
        remote = self.remote_file_system_client_1

        # Add delay when upload and download
        def suspend_check(reason):
            if not local.exists('/Test folder renamed'):
                time.sleep(1)
            Engine.suspend_client(self.engine_1, reason)

        self.engine_1.suspend_client = suspend_check

        # Create documents in the remote root workspace
        # then synchronize
        self.workspace_id = ('defaultSyncRootFolderItemFactory#default#'
                            + self.workspace)
        self.workspace_pair_local_path = u'/' + self.workspace_title

        folder_id = remote.make_folder(self.workspace_id, u'Test folder').uid
        self.wait_sync(wait_for_async=True)

        # Create a document by streaming a binary file
        file_path = os.path.join(local._abspath('/Test folder'), 'testFile.pdf')
        copyfile('nxdrive/tests/resources/testFile.pdf', file_path)
        file_path = os.path.join(local._abspath('/Test folder'), 'testFile2.pdf')
        copyfile('nxdrive/tests/resources/testFile.pdf', file_path)

        # Rename remote folder then synchronize
        self.remote_file_system_client_1.rename(folder_id, u'Test folder renamed')
        self.wait_sync(wait_for_async=True, fail_if_timeout=False)
        self.assertFalse(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder renamed'))
        self.assertTrue(local.exists('/Test folder renamed/testFile.pdf'))
        self.assertTrue(local.exists('/Test folder renamed/testFile2.pdf'))

    def test_synchronize_remote_rename_while_upload(self):
        if sys.platform != 'win32':
            with patch('nxdrive.client.base_automation_client.os.fstatvfs') as mock_os:
                from mock import Mock
                mock_os.return_value = Mock()
                mock_os.return_value.f_bsize = 4096
                self._remote_rename_while_upload()
        else:
            self._remote_rename_while_upload()

    def _remote_rename_while_download_file(self):
        global has_rename
        has_rename = False
        # Get local and remote clients
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Add delay when upload and download
        def suspend_check(reason):
            global has_rename
            if not has_rename:
                # Rename remote file while downloading
                try:
                    self.remote_file_system_client_1.rename(folder_id, u'Test folder renamed')
                    has_rename = True
                except:
                    pass
            if local.exists('/Test folder'):
                time.sleep(3)
            Engine.suspend_client(self.engine_1, reason)

        self.engine_1.suspend_client = suspend_check
        self.engine_1.invalidate_client_cache()

        # Create documents in the remote root workspace
        # then synchronize
        self.workspace_id = ('defaultSyncRootFolderItemFactory#default#'
                            + self.workspace)
        self.workspace_pair_local_path = u'/' + self.workspace_title

        folder_id = self.remote_file_system_client_1.make_folder(self.workspace_id, u'Test folder').uid

        with open('nxdrive/tests/resources/testFile.pdf', 'r') as content_file:
            content = content_file.read()
        self.remote_document_client_1.make_file('/Test folder', 'testFile.pdf', content)

        # Rename remote folder then synchronize
        self.wait_sync(wait_for_async=True, fail_if_timeout=False)
        self.assertFalse(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder renamed'))
        self.assertTrue(local.exists('/Test folder renamed/testFile.pdf'))

    def test_synchronize_remote_move_while_download_file(self):
        if sys.platform != 'win32':
            with patch('nxdrive.client.base_automation_client.os.fstatvfs', return_value=False) as mock_os:
                from mock import Mock
                mock_os.return_value = Mock()
                mock_os.return_value.f_bsize = 4096
                self._remote_move_while_download_file()
        else:
            self._remote_move_while_download_file()

    def _remote_move_while_download_file(self):
        global has_rename
        has_rename = False
        # Get local and remote clients
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        self.workspace_id = ('defaultSyncRootFolderItemFactory#default#'
                            + self.workspace)
        self.workspace_pair_local_path = u'/' + self.workspace_title

        folder_id = self.remote_file_system_client_1.make_folder(self.workspace_id, u'Test folder').uid
        new_folder_id = self.remote_file_system_client_1.make_folder(folder_id, u'New folder').uid
        self.wait_sync(wait_for_async=True, fail_if_timeout=False)

        # Add delay when upload and download
        def suspend_check(reason):
            global has_rename
            if not has_rename:
                # Rename remote file while downloading
                try:
                    self.remote_file_system_client_1.move(file_id, new_folder_id)
                    has_rename = True
                except:
                    pass
            if local.exists('/Test folder'):
                time.sleep(3)
            Engine.suspend_client(self.engine_1, reason)

        self.engine_1.suspend_client = suspend_check
        self.engine_1.invalidate_client_cache()


        with open('nxdrive/tests/resources/testFile.pdf', 'r') as content_file:
            content = content_file.read()
        file_id = self.remote_file_system_client_1.make_file(folder_id, 'testFile.pdf', content).uid

        # Rename remote folder then synchronize
        self.wait_sync(wait_for_async=True, fail_if_timeout=False)
        self.assertFalse(local.exists('/Test folder/testFile.pdf'))
        self.assertTrue(local.exists('/Test folder/New folder/testFile.pdf'))

    def test_synchronize_remote_rename_while_download_file(self):
        if sys.platform != 'win32':
            with patch('nxdrive.client.base_automation_client.os.fstatvfs', return_value=False) as mock_os:
                from mock import Mock
                mock_os.return_value = Mock()
                mock_os.return_value.f_bsize = 4096
                self._remote_rename_while_download_file()
        else:
            self._remote_rename_while_download_file()

    def test_remote_rename_file(self):
        remote_client = self.remote_client_1
        local_client = self.local_client_1

        file_1_docref = self.file_1_id.split("#")[-1]
        file_1_version = self.remote_document_client_1.get_info(file_1_docref).version
        # Rename /Original File 1.txt to /Renamed File 1.txt
        remote_client.rename(self.file_1_id, u'Renamed File 1.txt')
        self.assertEquals(remote_client.get_info(self.file_1_id).name,
            u'Renamed File 1.txt')

        self.wait_sync(wait_for_async=True)

        version = self.remote_document_client_1.get_info(file_1_docref).version
        # Check remote file name
        self.assertEquals(remote_client.get_info(self.file_1_id).name, u'Renamed File 1.txt')
        self.assertEquals(file_1_version, version, "Version should not increased")
        # Check local file name
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed File 1.txt'))
        # Check file state
        file_1_state = self._get_state(self.file_1_id)
        self.assertEquals(file_1_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Renamed File 1.txt')
        self.assertEquals(file_1_state.local_name, u'Renamed File 1.txt')

        # Rename 'Renamed File 1.txt' to 'Renamed Again File 1.txt'
        # and 'Original File 1.1.txt' to
        # 'Renamed File 1.1.txt' at the same time as they share
        # the same digest but do not live in the same folder
        # Wait for 1 second to make sure the file's last modification time
        # will be different from the pair state's last remote update time
        time.sleep(REMOTE_MODIFICATION_TIME_RESOLUTION)
        remote_client.rename(self.file_1_id, 'Renamed Again File 1.txt')
        self.assertEquals(remote_client.get_info(self.file_1_id).name,
            u'Renamed Again File 1.txt')
        remote_client.rename(self.file_1_1_id, u'Renamed File 1.1 \xe9.txt')
        self.assertEquals(remote_client.get_info(self.file_1_1_id).name,
            u'Renamed File 1.1 \xe9.txt')

        self.wait_sync(wait_for_async=True)

        info = remote_client.get_info(self.file_1_id)
        self.assertEquals(info.name, u'Renamed Again File 1.txt')
        self.assertEquals(remote_client.get_info(self.file_1_1_id).name,
            u'Renamed File 1.1 \xe9.txt')
        version = self.remote_document_client_1.get_info(file_1_docref).version
        self.assertEquals(file_1_version, version, "Version should not increased")
        # Check local file names
        self.assertFalse(local_client.exists(u'/Renamed File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed Again File 1.txt'))
        self.assertFalse(local_client.exists(
            u'/Original Folder 1/Original File 1.1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1.1 \xe9.txt'))
        # Check file states
        file_1_state = self._get_state(self.file_1_id)
        self.assertEquals(file_1_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Renamed Again File 1.txt')
        self.assertEquals(file_1_state.local_name, u'Renamed Again File 1.txt')
        file_1_1_state = self._get_state(self.file_1_1_id)
        self.assertEquals(file_1_1_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Original Folder 1/Renamed File 1.1 \xe9.txt')
        self.assertEquals(file_1_1_state.local_name,
            u'Renamed File 1.1 \xe9.txt')

        # Check parents of renamed files to ensure it is an actual rename
        # that has been performed and not a move
        file_1_local_info = local_client.get_info(
            u'/Renamed Again File 1.txt')
        file_1_parent_path = os.path.dirname(file_1_local_info.filepath)
        self.assertEquals(file_1_parent_path, self.sync_root_folder_1)

        file_1_1_local_info = local_client.get_info(
            u'/Original Folder 1/Renamed File 1.1 \xe9.txt')
        file_1_1_parent_path = os.path.dirname(file_1_1_local_info.filepath)
        self.assertEquals(file_1_1_parent_path,
            os.path.join(self.sync_root_folder_1, u'Original Folder 1'))

    def test_remote_rename_update_content_file(self):
        remote_client = self.remote_client_1
        local_client = self.local_client_1

        # Update the content of /Original File 1.txt and rename it
        # to /Renamed File 1.txt
        remote_client.update_content(self.file_1_id, 'Updated content',
                                     filename=u'Renamed File 1.txt')
        self.assertEquals(remote_client.get_info(self.file_1_id).name,
            u'Renamed File 1.txt')
        self.assertEquals(remote_client.get_content(self.file_1_id),
            'Updated content')

        self.wait_sync(wait_for_async=True)

        # Check local file name
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed File 1.txt'))
        self.assertEquals(local_client.get_content(u'/Renamed File 1.txt'),
                          'Updated content')

    def test_remote_move_file(self):
        remote_client = self.remote_client_1
        local_client = self.local_client_1

        # Move /Original File 1.txt to /Original Folder 1/Original File 1.txt
        remote_client.move(self.file_1_id, self.folder_1_id)
        self.assertEquals(remote_client.get_info(self.file_1_id).name,
            u'Original File 1.txt')
        self.assertEquals(remote_client.get_info(self.file_1_id).parent_uid,
            self.folder_1_id)

        self.wait_sync(wait_for_async=True)

        # Check remote file
        self.assertEquals(remote_client.get_info(self.file_1_id).name,
            u'Original File 1.txt')
        self.assertEquals(remote_client.get_info(self.file_1_id).parent_uid,
            self.folder_1_id)
        # Check local file
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Original File 1.txt'))
        file_1_local_info = local_client.get_info(
            u'/Original Folder 1/Original File 1.txt')
        file_1_parent_path = os.path.dirname(file_1_local_info.filepath)
        self.assertEquals(file_1_parent_path,
            os.path.join(self.sync_root_folder_1, u'Original Folder 1'))
        # Check file state
        file_1_state = self._get_state(self.file_1_id)
        self.assertEquals(file_1_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Original Folder 1/Original File 1.txt')
        self.assertEquals(file_1_state.local_name, u'Original File 1.txt')

    def test_remote_move_and_rename_file(self):
        remote_client = self.remote_client_1
        local_client = self.local_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        remote_client.rename(self.file_1_id, u'Renamed File 1 \xe9.txt')
        remote_client.move(self.file_1_id, self.folder_1_id)
        self.assertEquals(remote_client.get_info(self.file_1_id).name,
            u'Renamed File 1 \xe9.txt')
        self.assertEquals(remote_client.get_info(self.file_1_id).parent_uid,
            self.folder_1_id)

        self.wait_sync(wait_for_async=True)

        # Check remote file
        self.assertEquals(remote_client.get_info(self.file_1_id).name,
            u'Renamed File 1 \xe9.txt')
        self.assertEquals(remote_client.get_info(self.file_1_id).parent_uid,
            self.folder_1_id)
        # Check local file
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1 \xe9.txt'))
        file_1_local_info = local_client.get_info(
            u'/Original Folder 1/Renamed File 1 \xe9.txt')
        file_1_parent_path = os.path.dirname(file_1_local_info.filepath)
        self.assertEquals(file_1_parent_path,
            os.path.join(self.sync_root_folder_1, u'Original Folder 1'))
        # Check file state
        file_1_state = self._get_state(self.file_1_id)
        self.assertEquals(file_1_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Original Folder 1/Renamed File 1 \xe9.txt')
        self.assertEquals(file_1_state.local_name, u'Renamed File 1 \xe9.txt')

    def test_remote_rename_folder(self):
        remote_client = self.remote_client_1
        local_client = self.local_client_1

        # Rename a non empty folder with some content
        remote_client.rename(self.folder_1_id, u'Renamed Folder 1 \xe9')
        self.assertEquals(remote_client.get_info(self.folder_1_id).name,
            u'Renamed Folder 1 \xe9')

        # Synchronize: only the folder renaming is detected: all
        # the descendants are automatically realigned
        self.wait_sync(wait_for_async=True)

        # The client folder has been renamed
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 1 \xe9'))

        # The content of the renamed folder is left unchanged
        # Check child name
        self.assertTrue(local_client.exists(
            u'/Renamed Folder 1 \xe9/Original File 1.1.txt'))
        file_1_1_local_info = local_client.get_info(
            u'/Renamed Folder 1 \xe9/Original File 1.1.txt')
        file_1_1_parent_path = os.path.dirname(file_1_1_local_info.filepath)
        self.assertEquals(file_1_1_parent_path,
            os.path.join(self.sync_root_folder_1, u'Renamed Folder 1 \xe9'))
        # Check child state
        file_1_1_state = self._get_state(self.file_1_1_id)
        self.assertEquals(file_1_1_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Renamed Folder 1 \xe9/Original File 1.1.txt')
        self.assertEquals(file_1_1_state.local_name, u'Original File 1.1.txt')

        # Check child name
        self.assertTrue(local_client.exists(
            u'/Renamed Folder 1 \xe9/Sub-Folder 1.1'))
        folder_1_1_local_info = local_client.get_info(
            u'/Renamed Folder 1 \xe9/Sub-Folder 1.1')
        folder_1_1_parent_path = os.path.dirname(
            folder_1_1_local_info.filepath)
        self.assertEquals(folder_1_1_parent_path,
            os.path.join(self.sync_root_folder_1, u'Renamed Folder 1 \xe9'))
        # Check child state
        folder_1_1_state = self._get_state(self.folder_1_1_id)
        self.assertEquals(folder_1_1_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Renamed Folder 1 \xe9/Sub-Folder 1.1')
        self.assertEquals(folder_1_1_state.local_name, u'Sub-Folder 1.1')

    def test_remote_rename_case_folder(self):
        remote_client = self.remote_client_1
        local_client = self.local_client_1
        self.assertTrue(local_client.exists('/Original Folder 1'))
        remote_client.rename(self.folder_1_id, 'Original folder 1')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local_client.exists('/Original folder 1'))
        remote_client.rename(self.folder_1_id, 'Original Folder 1')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local_client.exists('/Original Folder 1'))

    def test_remote_rename_case_folder_stopped(self):
        remote_client = self.remote_client_1
        local_client = self.local_client_1
        self.engine_1.stop()
        self.assertTrue(local_client.exists('/Original Folder 1'))
        remote_client.rename(self.folder_1_id, 'Original folder 1')
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local_client.exists('/Original folder 1'))
        self.engine_1.stop()
        remote_client.rename(self.folder_1_id, 'Original Folder 1')
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local_client.exists('/Original Folder 1'))

    def test_remote_move_folder(self):
        remote_client = self.remote_client_1
        local_client = self.local_client_1

        # Move a non empty folder with some content
        remote_client.move(self.folder_1_id, self.folder_2_id)
        self.assertEquals(remote_client.get_info(self.folder_1_id).name,
            u'Original Folder 1')
        self.assertEquals(remote_client.get_info(self.folder_1_id).parent_uid,
            self.folder_2_id)

        # Synchronize: only the folder move is detected: all
        # the descendants are automatically realigned
        self.wait_sync(wait_for_async=True)

        # Check remote folder
        self.assertEquals(remote_client.get_info(self.folder_1_id).name,
            u'Original Folder 1')
        self.assertEquals(remote_client.get_info(self.folder_1_id).parent_uid,
            self.folder_2_id)
        # Check local folder
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 2/Original Folder 1'))
        folder_1_local_info = local_client.get_info(
            u'/Original Folder 2/Original Folder 1')
        folder_1_parent_path = os.path.dirname(folder_1_local_info.filepath)
        self.assertEquals(folder_1_parent_path,
            os.path.join(self.sync_root_folder_1, u'Original Folder 2'))
        # Check folder state
        folder_1_state = self._get_state(self.folder_1_id)
        self.assertEquals(folder_1_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Original Folder 2/Original Folder 1')
        self.assertEquals(folder_1_state.local_name, u'Original Folder 1')

        # The content of the renamed folder is left unchanged
        self.assertTrue(local_client.exists(
            u'/Original Folder 2/Original Folder 1/Original File 1.1.txt'))
        file_1_1_local_info = local_client.get_info(
            u'/Original Folder 2/Original Folder 1/Original File 1.1.txt')
        file_1_1_parent_path = os.path.dirname(file_1_1_local_info.filepath)
        self.assertEquals(file_1_1_parent_path,
            os.path.join(self.sync_root_folder_1,
                         u'Original Folder 2',
                         u'Original Folder 1'))
        # Check child state
        file_1_1_state = self._get_state(self.file_1_1_id)
        self.assertEquals(file_1_1_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Original Folder 2/Original Folder 1/Original File 1.1.txt')
        self.assertEquals(file_1_1_state.local_name, u'Original File 1.1.txt')

        # Check child name
        self.assertTrue(local_client.exists(
            u'/Original Folder 2/Original Folder 1/Sub-Folder 1.1'))
        folder_1_1_local_info = local_client.get_info(
            u'/Original Folder 2/Original Folder 1/Sub-Folder 1.1')
        folder_1_1_parent_path = os.path.dirname(
            folder_1_1_local_info.filepath)
        self.assertEquals(folder_1_1_parent_path,
            os.path.join(self.sync_root_folder_1,
                         u'Original Folder 2',
                         u'Original Folder 1'))
        # Check child state
        folder_1_1_state = self._get_state(self.folder_1_1_id)
        self.assertEquals(folder_1_1_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Original Folder 2/Original Folder 1/Sub-Folder 1.1')
        self.assertEquals(folder_1_1_state.local_name, u'Sub-Folder 1.1')

    def test_concurrent_remote_rename_folder(self):
        remote_client = self.remote_client_1
        local_client = self.local_client_1

        # Rename non empty folders concurrently
        remote_client.rename(self.folder_1_id, u'Renamed Folder 1')
        self.assertEquals(remote_client.get_info(self.folder_1_id).name,
            u'Renamed Folder 1')
        remote_client.rename(self.folder_2_id, u'Renamed Folder 2')
        self.assertEquals(remote_client.get_info(self.folder_2_id).name,
            u'Renamed Folder 2')

        # Synchronize: only the folder renaming is detected: all
        # the descendants are automatically realigned
        self.wait_sync(wait_for_async=True)

        # The content of the renamed folders is left unchanged
        # Check child name
        self.assertTrue(local_client.exists(
            u'/Renamed Folder 1/Original File 1.1.txt'))
        file_1_1_local_info = local_client.get_info(
            u'/Renamed Folder 1/Original File 1.1.txt')
        file_1_1_parent_path = os.path.dirname(file_1_1_local_info.filepath)
        self.assertEquals(file_1_1_parent_path,
            os.path.join(self.sync_root_folder_1, u'Renamed Folder 1'))
        # Check child state
        file_1_1_state = self._get_state(self.file_1_1_id)
        self.assertEquals(file_1_1_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Renamed Folder 1/Original File 1.1.txt')
        self.assertEquals(file_1_1_state.local_name, u'Original File 1.1.txt')

        # Check child name
        self.assertTrue(local_client.exists(
            u'/Renamed Folder 2/Original File 3.txt'))
        file_3_local_info = local_client.get_info(
            u'/Renamed Folder 2/Original File 3.txt')
        file_3_parent_path = os.path.dirname(file_3_local_info.filepath)
        self.assertEquals(file_3_parent_path,
            os.path.join(self.sync_root_folder_1, u'Renamed Folder 2'))
        # Check child state
        file_3_state = self._get_state(self.file_3_id)
        self.assertEquals(file_3_state.local_path,
            self.workspace_pair_local_path + '/'
            + u'Renamed Folder 2/Original File 3.txt')
        self.assertEquals(file_3_state.local_name, u'Original File 3.txt')

    def test_remote_rename_sync_root_folder(self):
        remote_client = self.remote_client_1
        local_client = LocalClient(self.local_nxdrive_folder_1)

        # Rename a sync root folder
        remote_client.rename(self.workspace_id,
            u'Renamed Nuxeo Drive Test Workspace')
        self.assertEquals(remote_client.get_info(self.workspace_id).name,
            u'Renamed Nuxeo Drive Test Workspace')

        # Synchronize: only the sync root folder renaming is detected: all
        # the descendants are automatically realigned
        self.wait_sync(wait_for_async=True)

        # The client folder has been renamed
        self.assertFalse(local_client.exists(u'/Nuxeo Drive Test Workspace'))
        self.assertTrue(local_client.exists(
            u'/Renamed Nuxeo Drive Test Workspace'))

        renamed_workspace_path = os.path.join(self.local_nxdrive_folder_1,
            u'Renamed Nuxeo Drive Test Workspace')
        # The content of the renamed folder is left unchanged
        # Check child name
        self.assertTrue(local_client.exists(
            u'/Renamed Nuxeo Drive Test Workspace/Original File 1.txt'))
        file_1_local_info = local_client.get_info(
            u'/Renamed Nuxeo Drive Test Workspace/Original File 1.txt')
        file_1_parent_path = os.path.dirname(file_1_local_info.filepath)
        self.assertEquals(file_1_parent_path, renamed_workspace_path)
        # Check child state
        file_1_state = self._get_state(self.file_1_id)
        self.assertEquals(file_1_state.local_path,
            u'/Renamed Nuxeo Drive Test Workspace/Original File 1.txt')
        self.assertEquals(file_1_state.local_name, u'Original File 1.txt')

        # Check child name
        self.assertTrue(local_client.exists(
            u'/Renamed Nuxeo Drive Test Workspace/Original Folder 1'))
        folder_1_local_info = local_client.get_info(
            u'/Renamed Nuxeo Drive Test Workspace/Original Folder 1')
        folder_1_parent_path = os.path.dirname(folder_1_local_info.filepath)
        self.assertEquals(folder_1_parent_path, renamed_workspace_path)
        # Check child state
        folder_1_state = self._get_state(self.folder_1_id)
        self.assertEquals(folder_1_state.local_path,
            u'/Renamed Nuxeo Drive Test Workspace/Original Folder 1')
        self.assertEquals(folder_1_state.local_name, u'Original Folder 1')

        # Check child name
        self.assertTrue(local_client.exists(
            u'/Renamed Nuxeo Drive Test Workspace/'
            u'Original Folder 1/Sub-Folder 1.1'))
        folder_1_1_local_info = local_client.get_info(
            u'/Renamed Nuxeo Drive Test Workspace/'
            u'Original Folder 1/Sub-Folder 1.1')
        folder_1_1_parent_path = os.path.dirname(
            folder_1_1_local_info.filepath)
        self.assertEquals(folder_1_1_parent_path,
            os.path.join(renamed_workspace_path, u'Original Folder 1'))
        # Check child state
        folder_1_1_state = self._get_state(self.folder_1_1_id)
        self.assertEquals(folder_1_1_state.local_path,
            u'/Renamed Nuxeo Drive Test Workspace'
            '/Original Folder 1/Sub-Folder 1.1')
        self.assertEquals(folder_1_1_state.local_name, u'Sub-Folder 1.1')

        # Check child name
        self.assertTrue(local_client.exists(
            u'/Renamed Nuxeo Drive Test Workspace/'
            u'Original Folder 1/Original File 1.1.txt'))
        file_1_1_local_info = local_client.get_info(
            u'/Renamed Nuxeo Drive Test Workspace/'
            'Original Folder 1/Original File 1.1.txt')
        file_1_1_parent_path = os.path.dirname(file_1_1_local_info.filepath)
        self.assertEquals(file_1_1_parent_path,
            os.path.join(renamed_workspace_path, u'Original Folder 1'))
        # Check child state
        file_1_1_state = self._get_state(self.file_1_1_id)
        self.assertEquals(file_1_1_state.local_path,
                          u'/Renamed Nuxeo Drive Test Workspace'
                          '/Original Folder 1/Original File 1.1.txt')
        self.assertEquals(file_1_1_state.local_name, u'Original File 1.1.txt')

    def test_remote_move_to_non_sync_root(self):
        # Grant ReadWrite permission on Workspaces for test user
        workspaces_path = u'/default-domain/workspaces'
        op_input = "doc:" + workspaces_path
        self.root_remote_client.execute("Document.SetACE",
            op_input=op_input,
            user="nuxeoDriveTestUser_user_1",
            permission="ReadWrite",
            grant="true")

        workspaces_info = self.root_remote_client.fetch(workspaces_path)
        workspaces = workspaces_info[u'uid']

        # Get remote client with Workspaces as base folder and local client
        remote_client = RemoteDocumentClient(
            self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
            self.version,
            password=self.password_1, base_folder=workspaces,
            upload_tmp_dir=self.upload_tmp_dir)
        local_client = self.local_client_1

        # Create a non synchronized folder
        unsync_folder = remote_client.make_folder(u'/', u'Non synchronized folder')

        try:
            # Move Original Folder 1 to Non synchronized folder
            remote_client.move(u'/nuxeo-drive-test-workspace/Original Folder 1',
                               u'/Non synchronized folder')
            self.assertFalse(remote_client.exists(
                                u'/nuxeo-drive-test-workspace/Original Folder 1'))
            self.assertTrue(remote_client.exists(
                                u'/Non synchronized folder/Original Folder 1'))

            # Synchronize: the folder move is detected as a deletion
            self.wait_sync(wait_for_async=True)

            # Check local folder
            self.assertFalse(local_client.exists(u'/Original Folder 1'))
            # Check folder state
            folder_1_state = self._get_state(self.folder_1_id)
            self.assertEquals(folder_1_state, None)
        finally:
            # Clean the non synchronized folder
            remote_client.delete(unsync_folder, use_trash=False)
