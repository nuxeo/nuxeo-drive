import os
import time

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient


class TestIntegrationMoveAndRename(IntegrationTestCase):

    def setUp(self):
        super(TestIntegrationMoveAndRename, self).setUp()

        self.sb_1 = self.controller_1.bind_server(
            self.local_nxdrive_folder_1,
            self.nuxeo_url, self.user_1, self.password_1)

        self.controller_1.bind_root(self.local_nxdrive_folder_1,
            self.workspace)

        self.controller_1.synchronizer.update_synchronize_server(self.sb_1)

        sync_root_folder_1 = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        self.local_client_1 = LocalClient(sync_root_folder_1)

        self.local_client_1.make_file('/', 'Original File 1.txt',
            content=u'Some Content 1'.encode('utf-8'))

        self.local_client_1.make_file('/', 'Original File 2.txt',
            content=u'Some Content 2'.encode('utf-8'))

        self.local_client_1.make_folder('/', 'Original Folder 1')
        self.local_client_1.make_folder('/Original Folder 1', 'Sub-Folder 1.1')
        self.local_client_1.make_folder('/Original Folder 1', 'Sub-Folder 1.2')
        self.local_client_1.make_file('/Original Folder 1',
            'Original Duplicate File 1.1.txt',
            content=u'Some Content 1'.encode('utf-8'))  # Same content as OF1

        self.local_client_1.make_folder('/', 'Original Folder 2')
        self.controller_1.synchronizer.update_synchronize_server(self.sb_1)

    def test_local_rename_file(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        original_file_1_uid = remote_client.get_info(
            '/Original File 1.txt').uid
        local_client.rename('/Original File 1.txt', 'Renamed File 1.txt')
        self.assertFalse(local_client.exists('/Original File 1.txt'))
        self.assertTrue(local_client.exists('/Renamed File 1.txt'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)
        self.assertFalse(local_client.exists('/Original File 1.txt'))
        self.assertTrue(local_client.exists('/Renamed File 1.txt'))
        original_file_1_remote_info = remote_client.get_info(
            original_file_1_uid)
        self.assertEquals(original_file_1_remote_info.name,
            'Renamed File 1.txt')

        # Rename 'Renamed File 1.txt' to 'Renamed Again File 1.txt'
        # and 'Original Duplicate File 1.1.txt' to
        # 'Renamed Duplicate File 1.1.txt' at the same time as they share
        # the same digest but do not live in the same folder
        original_duplicate_1_1_uid = remote_client.get_info(
            '/Original Folder 1/Original Duplicate File 1.1.txt').uid
        local_client.rename(
            '/Original Folder 1/Original Duplicate File 1.1.txt',
            'Renamed Duplicate File 1.1.txt')
        self.assertFalse(local_client.exists(
             '/Original Folder 1/Original Duplicate File 1.1.txt'))
        self.assertTrue(local_client.exists(
            '/Original Folder 1/Renamed Duplicate File 1.1.txt'))
        local_client.rename('/Renamed File 1.txt', 'Renamed Again File 1.txt')
        self.assertFalse(local_client.exists('/Renamed File 1.txt'))
        self.assertTrue(local_client.exists('/Renamed Again File 1.txt'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 2)
        self.assertFalse(local_client.exists('/Renamed File 1.txt'))
        self.assertTrue(local_client.exists('/Renamed Again File 1.txt'))
        self.assertFalse(local_client.exists(
             '/Original Folder 1/Original Duplicate File 1.1.txt'))
        self.assertTrue(local_client.exists(
            '/Original Folder 1/Renamed Duplicate File 1.1.txt'))

        original_file_1_remote_info = remote_client.get_info(
             original_file_1_uid)
        self.assertEquals(original_file_1_remote_info.name,
                          'Renamed Again File 1.txt')
        original_duplicate_1_1_remote_info = remote_client.get_info(
             original_duplicate_1_1_uid)
        self.assertEquals(original_duplicate_1_1_remote_info.name,
                          'Renamed Duplicate File 1.1.txt')

        # TODO check that parent folders have not changes

    def test_local_rename_folder(self):
        pass

    def test_local_rename_sync_root_folder(self):
        pass

    def test_local_move_file(self):
        pass

    def test_local_move_folder(self):
        pass

    def test_local_move_sync_root_folder(self):
        pass