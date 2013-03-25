import os
import time

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nxdrive.client import RemoteFileSystemClient
from nxdrive.client import RemoteDocumentClient


class TestIntegrationRemoteMoveAndRename(IntegrationTestCase):

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
        super(TestIntegrationRemoteMoveAndRename, self).setUp()

        self.sb_1 = self.controller_1.bind_server(
            self.local_nxdrive_folder_1,
            self.nuxeo_url, self.user_1, self.password_1)

        self.controller_1.bind_root(self.local_nxdrive_folder_1,
            self.workspace)

        self.controller_1.synchronizer.update_synchronize_server(self.sb_1)

        sync_root_folder_1 = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        self.local_client_1 = LocalClient(sync_root_folder_1)
        self.remote_client_1 = self.remote_file_system_client_1

        self.workspace_id = 'defaultSyncRootFolderItemFactory#default#' + self.workspace

        self.file_1_id = self.remote_client_1.make_file(self.workspace_id,
            u'Original File 1.txt',
            content=u'Some Content 1'.encode('utf-8'))

        self.file_2_id = self.remote_client_1.make_file(self.workspace_id,
            u'Original File 2.txt',
            content=u'Some Content 2'.encode('utf-8'))

        self.folder_1_id = self.remote_client_1.make_folder(self.workspace_id,
            u'Original Folder 1')
        self.folder_1_1_id = self.remote_client_1.make_folder(
            self.folder_1_id, u'Sub-Folder 1.1')
        self.folder_1_2_id = self.remote_client_1.make_folder(
            self.folder_1_id, u'Sub-Folder 1.2')
        self.file_1_1_id = self.remote_client_1.make_file(
            self.folder_1_id,
            u'Original File 1.1.txt',
            content=u'Some Content 1'.encode('utf-8'))  # Same content as OF1

        self.folder_2_id = self.remote_client_1.make_folder(self.workspace_id,
            'Original Folder 2')
        self.file_3_id = self.remote_client_1.make_file(self.folder_2_id,
            u'Original File 3.txt',
            content=u'Some Content 3'.encode('utf-8'))

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.controller_1.synchronizer.update_synchronize_server(self.sb_1)

    def test_remote_rename_file(self):
        sb, ctl = self.sb_1, self.controller_1
        remote_client = self.remote_client_1
        local_client = self.local_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        remote_client.rename(self.file_1_id, u'Renamed File 1.txt')
        self.assertEquals(remote_client.get_info(self.file_1_id).name,
            u'Renamed File 1.txt')

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)

        self.assertEquals(remote_client.get_info(self.file_1_id).name,
            u'Renamed File 1.txt')
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed File 1.txt'))

        # Rename 'Renamed File 1.txt' to 'Renamed Again File 1.txt'
        # and 'Original File 1.1.txt' to
        # 'Renamed File 1.1.txt' at the same time as they share
        # the same digest but do not live in the same folder
        remote_client.rename(self.file_1_id, 'Renamed Again File 1.txt')
        self.assertEquals(remote_client.get_info(self.file_1_id).name,
            u'Renamed Again File 1.txt')
        remote_client.rename(self.file_1_1_id, u'Renamed File 1.1 \xe9.txt')
        self.assertEquals(remote_client.get_info(self.file_1_1_id).name,
            u'Renamed File 1.1 \xe9.txt')

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 2)

        self.assertEquals(remote_client.get_info(self.file_1_id).name,
            u'Renamed Again File 1.txt')
        self.assertEquals(remote_client.get_info(self.file_1_1_id).name,
            u'Renamed File 1.1 \xe9.txt')
        self.assertFalse(local_client.exists(u'/Renamed File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed Again File 1.txt'))
        self.assertFalse(local_client.exists(
            u'/Original Folder 1/Original File 1.1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1.1 \xe9.txt'))

        # Check parents of renamed files to ensure it is an actual rename
        # that has been performed and not a move
        file_1_local_info = local_client.get_info(
            u'/Renamed Again File 1.txt')
        file_1_parent_path = file_1_local_info.filepath.rsplit('/', 1)[0]
        self.assertEquals(os.path.basename(file_1_parent_path),
            self.workspace_title)

        file_1_1_local_info = local_client.get_info(
            u'/Original Folder 1/Renamed File 1.1 \xe9.txt')
        file_1_1_parent_path = file_1_1_local_info.filepath.rsplit('/', 1)[0]
        self.assertEquals(os.path.basename(file_1_1_parent_path),
            u'Original Folder 1')

    def test_remote_rename_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        remote_client = self.remote_client_1
        local_client = self.local_client_1

        # Rename a non empty folder with some content
        remote_client.rename(self.folder_1_id, u'Renamed Folder 1 \xe9')
        self.assertEquals(remote_client.get_info(self.folder_1_id).name,
            u'Renamed Folder 1 \xe9')

        # Synchronize: only the folder renaming is detected: all
        # the descendants are automatically realigned
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)

        # The client folder has been renamed
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 1 \xe9'))

        # The content of the renamed folder is left unchanged
        self.assertTrue(local_client.exists(
            u'/Renamed Folder 1 \xe9/Original File 1.1.txt'))
        file_1_1_local_info = local_client.get_info(
            u'/Renamed Folder 1 \xe9/Original File 1.1.txt')
        file_1_1_parent_path = file_1_1_local_info.filepath.rsplit('/', 1)[0]
        self.assertEquals(os.path.basename(file_1_1_parent_path),
            u'Renamed Folder 1 \xe9')

        self.assertTrue(local_client.exists(
            u'/Renamed Folder 1 \xe9/Sub-Folder 1.1'))
        folder_1_1_local_info = local_client.get_info(
            u'/Renamed Folder 1 \xe9/Sub-Folder 1.1')
        folder_1_1_parent_path = folder_1_1_local_info.filepath.rsplit('/', 1)[0]
        self.assertEquals(os.path.basename(folder_1_1_parent_path),
            u'Renamed Folder 1 \xe9')

        # The more things change, the more they remain the same.
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 0)