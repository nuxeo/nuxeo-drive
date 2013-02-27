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

        self.local_client_1.make_file('/', u'Original File 1.txt',
            content=u'Some Content 1'.encode('utf-8'))

        self.local_client_1.make_file('/', u'Original File 2.txt',
            content=u'Some Content 2'.encode('utf-8'))

        self.local_client_1.make_folder(u'/', u'Original Folder 1')
        self.local_client_1.make_folder(
            u'/Original Folder 1', u'Sub-Folder 1.1')
        self.local_client_1.make_folder(
            u'/Original Folder 1', u'Sub-Folder 1.2')
        self.local_client_1.make_file(u'/Original Folder 1',
            u'Original File 1.1.txt',
            content=u'Some Content 1'.encode('utf-8'))  # Same content as OF1

        self.local_client_1.make_folder('/', 'Original Folder 2')
        self.local_client_1.make_file('/Original Folder 2',
            u'Original File 3.txt',
            content=u'Some Content 3'.encode('utf-8'))

        self.controller_1.synchronizer.update_synchronize_server(self.sb_1)

    def test_local_rename_file(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        original_file_1_uid = remote_client.get_info(
            u'/Original File 1.txt').uid
        local_client.rename(u'/Original File 1.txt', u'Renamed File 1.txt')
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed File 1.txt'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed File 1.txt'))
        original_file_1_remote_info = remote_client.get_info(
            original_file_1_uid)
        self.assertEquals(original_file_1_remote_info.name,
            u'Renamed File 1.txt')

        # Rename 'Renamed File 1.txt' to 'Renamed Again File 1.txt'
        # and 'Original File 1.1.txt' to
        # 'Renamed File 1.1.txt' at the same time as they share
        # the same digest but do not live in the same folder
        original_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt').uid
        local_client.rename(
            u'/Original Folder 1/Original File 1.1.txt',
            u'Renamed File 1.1 \xe9.txt')
        self.assertFalse(local_client.exists(
             '/Original Folder 1/Original File 1.1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1.1 \xe9.txt'))
        local_client.rename('/Renamed File 1.txt', 'Renamed Again File 1.txt')
        self.assertFalse(local_client.exists(u'/Renamed File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed Again File 1.txt'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 2)
        self.assertFalse(local_client.exists(u'/Renamed File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed Again File 1.txt'))
        self.assertFalse(local_client.exists(
             u'/Original Folder 1/Original File 1.1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1.1 \xe9.txt'))

        file_1_remote_info = remote_client.get_info(original_file_1_uid)
        self.assertEquals(file_1_remote_info.name,
            u'Renamed Again File 1.txt')

        parent_of_file_1_remote_info = remote_client.get_info(
            file_1_remote_info.parent_uid)
        self.assertEquals(parent_of_file_1_remote_info.name,
            self.workspace_title)

        file_1_1_remote_info = remote_client.get_info(original_1_1_uid)
        self.assertEquals(file_1_1_remote_info.name,
            u'Renamed File 1.1 \xe9.txt')

        parent_of_file_1_1_remote_info = remote_client.get_info(
            file_1_1_remote_info.parent_uid)
        self.assertEquals(parent_of_file_1_1_remote_info.name,
            u'Original Folder 1')

    def test_local_move_file(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        original_file_1_uid = remote_client.get_info(
            u'/Original File 1.txt').uid
        local_client.move(u'/Original File 1.txt', u'/Original Folder 1')
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Original File 1.txt'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Original File 1.txt'))

        file_1_remote_info = remote_client.get_info(original_file_1_uid)
        self.assertEquals(file_1_remote_info.name, u'Original File 1.txt')
        parent_of_file_1_remote_info = remote_client.get_info(
            file_1_remote_info.parent_uid)
        self.assertEquals(parent_of_file_1_remote_info.name,
            u'Original Folder 1')

    def test_local_move_and_rename_file(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        original_file_1_uid = remote_client.get_info(
            u'/Original File 1.txt').uid

        local_client.rename(u'/Original File 1.txt', u'Renamed File 1 \xe9.txt')
        local_client.move(u'/Renamed File 1 \xe9.txt', u'/Original Folder 1')
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1 \xe9.txt'))

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1 \xe9.txt'))

        file_1_remote_info = remote_client.get_info(original_file_1_uid)
        self.assertEquals(file_1_remote_info.name, u'Renamed File 1 \xe9.txt')
        parent_of_file_1_remote_info = remote_client.get_info(
            file_1_remote_info.parent_uid)
        self.assertEquals(parent_of_file_1_remote_info.name,
            u'Original Folder 1')

        # Nothing left to do
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 0)

    def test_local_rename_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Save the uid of some files and folders prior to renaming
        original_folder_1_uid = remote_client.get_info(
            u'/Original Folder 1').uid
        original_file_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt').uid
        original_sub_folder_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Sub-Folder 1.1').uid

        # Rename a non empty folder with some content
        local_client.rename(u'/Original Folder 1', u'Renamed Folder 1 \xe9')
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 1 \xe9'))

        # Synchronize: only the folder renaming is detected: all
        # the descendants are automatically realigned
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)

        # The server folder has been renamed: the uid stays the same
        new_remote_name = remote_client.get_info(original_folder_1_uid).name
        self.assertEquals(new_remote_name, u"Renamed Folder 1 \xe9")

        # The content of the renamed folder is left unchanged
        file_1_1_info = remote_client.get_info(original_file_1_1_uid)
        self.assertEquals(file_1_1_info.name, u"Original File 1.1.txt")
        self.assertEquals(file_1_1_info.parent_uid, original_folder_1_uid)

        sub_folder_1_1_info = remote_client.get_info(
            original_sub_folder_1_1_uid)
        self.assertEquals(sub_folder_1_1_info.name, u"Sub-Folder 1.1")
        self.assertEquals(sub_folder_1_1_info.parent_uid,
            original_folder_1_uid)

        # The more things change, the more they remain the same.
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 0)

    def test_local_move_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Save the uid of some files and folders prior to move
        original_folder_1_uid = remote_client.get_info(
            u'/Original Folder 1').uid
        original_folder_2_uid = remote_client.get_info(
            u'/Original Folder 2').uid
        original_file_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt').uid
        original_sub_folder_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Sub-Folder 1.1').uid

        # Move a non empty folder with some content
        local_client.move(u'/Original Folder 1', u'/Original Folder 2')
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 2/Original Folder 1'))

        # Synchronize: only the folder move is detected: all
        # the descendants are automatically realigned
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 1)

        # The server folder has been moved: the uid stays the same
        remote_folder_info = remote_client.get_info(original_folder_1_uid)

        # The parent folder is not folder 2
        self.assertEquals(remote_folder_info.parent_uid,
            original_folder_2_uid)

        # The content of the renamed folder is left unchanged
        file_1_1_info = remote_client.get_info(original_file_1_1_uid)
        self.assertEquals(file_1_1_info.name, u"Original File 1.1.txt")
        self.assertEquals(file_1_1_info.parent_uid, original_folder_1_uid)

        sub_folder_1_1_info = remote_client.get_info(
            original_sub_folder_1_1_uid)
        self.assertEquals(sub_folder_1_1_info.name, u"Sub-Folder 1.1")
        self.assertEquals(sub_folder_1_1_info.parent_uid,
            original_folder_1_uid)

        # The more things change, the more they remain the same.
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 0)

    def test_concurrent_local_rename_folder(self):
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Save the uid of some files and folders prior to renaming
        folder_1_uid = remote_client.get_info(u'/Original Folder 1').uid
        file_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt').uid
        folder_2_uid = remote_client.get_info(u'/Original Folder 2').uid
        file_3_uid = remote_client.get_info(
            u'/Original Folder 2/Original File 3.txt').uid

        # Rename a non empty folders concurrently
        local_client.rename(u'/Original Folder 1', u'Renamed Folder 1')
        local_client.rename(u'/Original Folder 2', u'Renamed Folder 2')
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 1'))
        self.assertFalse(local_client.exists(u'/Original Folder 2'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 2'))

        # Synchronize: only the folder renamings are detected: all
        # the descendants are automatically realigned
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 2)

        # The server folders have been renamed: the uid stays the same
        folder_1_info = remote_client.get_info(folder_1_uid)
        self.assertEquals(folder_1_info.name, u"Renamed Folder 1")

        folder_2_info = remote_client.get_info(folder_2_uid)
        self.assertEquals(folder_2_info.name, u"Renamed Folder 2")

        # The content of the folder has been left unchanged
        file_1_1_info = remote_client.get_info(file_1_1_uid)
        self.assertEquals(file_1_1_info.name, u"Original File 1.1.txt")
        self.assertEquals(file_1_1_info.parent_uid, folder_1_uid)

        file_3_info = remote_client.get_info(file_3_uid)
        self.assertEquals(file_3_info.name, u"Original File 3.txt")
        self.assertEquals(file_3_info.parent_uid, folder_2_uid)

        # The more things change, the more they remain the same.
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 0)

    # def test_local_rename_sync_root_folder(self):
    #    pass

    # def test_local_move_sync_root_folder(self):
    #    pass