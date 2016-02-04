import os
import urllib2

from nxdrive.tests.common_unit_test import UnitTestCase
from nxdrive.client import LocalClient
from nxdrive.client import RemoteDocumentClient
from nxdrive.client.remote_filtered_file_system_client import RemoteFilteredFileSystemClient
from nxdrive.tests import RemoteTestClient
from nxdrive.tests.common import TEST_WORKSPACE_PATH
from nxdrive.client.common import NotFound
from nose.plugins.skip import SkipTest
from time import sleep
from nxdrive.engine.dao.sqlite import EngineDAO

# TODO NXDRIVE-170: refactor
LastKnownState = None


class TestLocalMoveAndRename(UnitTestCase):

    # Sets up the following local hierarchy:
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
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
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
        # Increase timeout as noticed it was sometimes insufficient in Jenkins build
        self.wait_sync(timeout=30)

    def test_local_rename_folder_while_creating(self):
        global marker
        local_client = self.local_client_1
        root_local_client = self.local_root_client_1
        remote_client = self.remote_document_client_1
        marker = False

        def update_remote_state(row, info, remote_parent_path=None, versionned=True, queue=True, force_update=False):
            global marker
            EngineDAO.update_remote_state(self.engine_1._dao, row, info, remote_parent_path=remote_parent_path,
                                          versionned=versionned, queue=queue, force_update=force_update)
            if row.local_name == 'New Folder' and not marker:
                root_local_client.rename(row.local_path, 'Renamed Folder')
                sleep(5)
                marker = True

        self.engine_1._dao.update_remote_state = update_remote_state
        local_client.make_folder('/', 'New Folder')
        self.wait_sync(fail_if_timeout=False)

        self.assertTrue(local_client.exists(u'/Renamed Folder'))
        self.assertFalse(local_client.exists(u'/New Folder'))
        # Path dont change on Nuxeo
        info = remote_client.get_info(u'/New Folder')
        self.assertEquals('Renamed Folder', info.name)
        self.assertEqual(len(local_client.get_children_info(u'/')), 5)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 5)

    def test_local_rename_file_while_creating(self):
        global marker
        local_client = self.local_client_1
        root_local_client = self.local_root_client_1
        remote_client = self.remote_document_client_1
        marker = False

        def update_remote_state(row, info, remote_parent_path=None, versionned=True, queue=True, force_update=False):
            global marker
            EngineDAO.update_remote_state(self.engine_1._dao, row, info, remote_parent_path=remote_parent_path,
                                          versionned=versionned, queue=queue, force_update=force_update)
            if row.local_name == 'File.txt' and not marker:
                root_local_client.rename(row.local_path, 'Renamed File.txt')
                sleep(5)
                marker = True

        self.engine_1._dao.update_remote_state = update_remote_state
        self.local_client_1.make_file('/', u'File.txt',
            content=u'Some Content 2'.encode('utf-8'))
        self.wait_sync(fail_if_timeout=False)
        
        self.assertTrue(local_client.exists(u'/Renamed File.txt'))
        self.assertFalse(local_client.exists(u'/File.txt'))
        # Path dont change on Nuxeo
        info = remote_client.get_info(u'/File.txt')
        self.assertEquals('Renamed File.txt', info.name)
        self.assertEqual(len(local_client.get_children_info(u'/')), 5)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 5)

    def test_local_rename_file(self):
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        original_file_1_uid = remote_client.get_info(
            u'/Original File 1.txt').uid
        local_client.rename(u'/Original File 1.txt', u'Renamed File 1.txt')
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed File 1.txt'))

        self.wait_sync()
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

        self.wait_sync()
        self.assertFalse(local_client.exists(u'/Renamed File 1.txt'))
        self.assertTrue(local_client.exists(u'/Renamed Again File 1.txt'))
        self.assertFalse(local_client.exists(
             u'/Original Folder 1/Original File 1.1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1.1 \xe9.txt'))

        file_1_remote_info = remote_client.get_info(original_file_1_uid)
        self.assertEquals(file_1_remote_info.name,
            u'Renamed Again File 1.txt')

        # User 1 does not have the rights to see the parent container
        # of the test workspace, hence set fetch_parent_uid=False
        parent_of_file_1_remote_info = remote_client.get_info(
            file_1_remote_info.parent_uid, fetch_parent_uid=False)
        self.assertEquals(parent_of_file_1_remote_info.name,
            self.workspace_title)

        file_1_1_remote_info = remote_client.get_info(original_1_1_uid)
        self.assertEquals(file_1_1_remote_info.name,
            u'Renamed File 1.1 \xe9.txt')

        parent_of_file_1_1_remote_info = remote_client.get_info(
            file_1_1_remote_info.parent_uid)
        self.assertEquals(parent_of_file_1_1_remote_info.name,
            u'Original Folder 1')
        self.assertEqual(len(local_client.get_children_info(u'/Original Folder 1')), 3)
        self.assertEqual(len(remote_client.get_children_info(file_1_1_remote_info.parent_uid)), 3)
        self.assertEqual(len(local_client.get_children_info(u'/')), 4)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 4)

    def test_local_rename_file_uppercase(self):
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt

        # Rename 'Renamed File 1.txt' to 'Renamed Again File 1.txt'
        # and 'Original File 1.1.txt' to
        # 'Renamed File 1.1.txt' at the same time as they share
        # the same digest but do not live in the same folder
        original_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt').uid
        local_client.rename(
            u'/Original Folder 1/Original File 1.1.txt',
            u'original File 1.1.txt')

        self.wait_sync()

        file_1_1_remote_info = remote_client.get_info(original_1_1_uid)
        self.assertEquals(file_1_1_remote_info.name,
            u'original File 1.1.txt')

        parent_of_file_1_1_remote_info = remote_client.get_info(
            file_1_1_remote_info.parent_uid)
        self.assertEquals(parent_of_file_1_1_remote_info.name,
            u'Original Folder 1')
        self.assertEqual(len(local_client.get_children_info(u'/Original Folder 1')), 3)
        self.assertEqual(len(remote_client.get_children_info(file_1_1_remote_info.parent_uid)), 3)

    def test_local_move_file(self):
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Move /Original File 1.txt to /Original Folder 1/Original File 1.txt
        original_file_1_uid = remote_client.get_info(
            u'/Original File 1.txt').uid
        local_client.move(u'/Original File 1.txt', u'/Original Folder 1')
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Original File 1.txt'))

        self.wait_sync()
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Original File 1.txt'))

        file_1_remote_info = remote_client.get_info(original_file_1_uid)
        self.assertEquals(file_1_remote_info.name, u'Original File 1.txt')
        parent_of_file_1_remote_info = remote_client.get_info(
            file_1_remote_info.parent_uid)
        self.assertEquals(parent_of_file_1_remote_info.name,
            u'Original Folder 1')
        self.assertEqual(len(local_client.get_children_info(u'/Original Folder 1')), 4)
        self.assertEqual(len(remote_client.get_children_info(file_1_remote_info.parent_uid)), 4)
        self.assertEqual(len(local_client.get_children_info(u'/')), 3)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 3)

    def test_local_move_and_rename_file(self):
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        original_file_1_uid = remote_client.get_info(
            u'/Original File 1.txt').uid

        local_client.move(u'/Original File 1.txt', u'/Original Folder 1', name=u'Renamed File 1 \xe9.txt')
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1 \xe9.txt'))

        self.wait_sync()
        self.assertFalse(local_client.exists(u'/Original File 1.txt'))
        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Renamed File 1 \xe9.txt'))

        file_1_remote_info = remote_client.get_info(original_file_1_uid)
        self.assertEquals(file_1_remote_info.name, u'Renamed File 1 \xe9.txt')
        parent_of_file_1_remote_info = remote_client.get_info(
            file_1_remote_info.parent_uid)
        self.assertEquals(parent_of_file_1_remote_info.name,
            u'Original Folder 1')
        self.assertEqual(len(local_client.get_children_info(u'/Original Folder 1')), 4)
        self.assertEqual(len(remote_client.get_children_info(file_1_remote_info.parent_uid)), 4)
        self.assertEqual(len(local_client.get_children_info(u'/')), 3)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 3)

    def test_local_rename_folder(self):
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
        self.wait_sync()

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

        self.assertEqual(len(local_client.get_children_info(u'/Renamed Folder 1 \xe9')), 3)
        self.assertEqual(len(remote_client.get_children_info(file_1_1_info.parent_uid)), 3)
        self.assertEqual(len(local_client.get_children_info(u'/')), 4)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 4)

    def test_local_rename_folder_while_suspended(self):
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Save the uid of some files and folders prior to renaming
        original_folder_1_uid = remote_client.get_info(
            u'/Original Folder 1').uid
        original_file_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt').uid
        original_sub_folder_1_1_uid = remote_client.get_info(
            u'/Original Folder 1/Sub-Folder 1.1').uid
        children_count = len(local_client.get_children_info(u'/Original Folder 1'))
        self.engine_1.suspend()
        # Rename a non empty folder with some content
        local_client.rename(u'/Original Folder 1', u'Renamed Folder 1 \xe9')
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 1 \xe9'))

        local_client.rename(u'/Renamed Folder 1 \xe9/Sub-Folder 1.1', u'Sub-Folder 2.1')
        self.assertTrue(local_client.exists(u'/Renamed Folder 1 \xe9/Sub-Folder 2.1'))

        self.engine_1.resume()
        # Synchronize: only the folder renaming is detected: all
        # the descendants are automatically realigned
        self.wait_sync(wait_for_async=True)

        # The server folder has been renamed: the uid stays the same
        new_remote_name = remote_client.get_info(original_folder_1_uid).name
        self.assertEquals(new_remote_name, u"Renamed Folder 1 \xe9")

        # The content of the renamed folder is left unchanged
        file_1_1_info = remote_client.get_info(original_file_1_1_uid)
        self.assertEquals(file_1_1_info.name, u"Original File 1.1.txt")
        self.assertEquals(file_1_1_info.parent_uid, original_folder_1_uid)

        sub_folder_1_1_info = remote_client.get_info(
            original_sub_folder_1_1_uid)
        self.assertEquals(sub_folder_1_1_info.name, u"Sub-Folder 2.1")
        self.assertEquals(sub_folder_1_1_info.parent_uid, original_folder_1_uid)
        self.assertEquals(len(local_client.get_children_info(u'/Renamed Folder 1 \xe9')), children_count)
        self.assertEqual(len(remote_client.get_children_info(original_folder_1_uid)), children_count)
        self.assertEqual(len(local_client.get_children_info(u'/')), 4)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 4)

    def test_local_rename_file_after_create(self):
        # Office 2010 and >, create a tmp file with 8 chars and move it right after
        global marker
        local_client = self.local_client_1
        self.local_client_1.make_file('/', u'File.txt',
            content=u'Some Content 2'.encode('utf-8'))
        self.local_client_1.rename('/File.txt', 'Renamed File.txt')
        self.wait_sync(fail_if_timeout=False)
        self.assertTrue(local_client.exists(u'/Renamed File.txt'))
        self.assertFalse(local_client.exists(u'/File.txt'))
        # Path dont change on Nuxeo
        self.assertIsNotNone(local_client.get_remote_id('/Renamed File.txt'))
        self.assertEqual(len(local_client.get_children_info(u'/')), 5)
        self.assertEqual(len(self.remote_document_client_1.get_children_info(self.workspace_1)), 5)

    def test_local_rename_file_after_create_detected(self):
        # Office 2010 and >, create a tmp file with 8 chars and move it right after
        global marker
        local_client = self.local_client_1
        marker = False
        def insert_local_state(info, parent_path):
            global marker
            if info.name == 'File.txt' and not marker:
                self.local_client_1.rename('/File.txt', 'Renamed File.txt')
                sleep(2)
                marker = True
            EngineDAO.insert_local_state(self.engine_1._dao, info, parent_path)
        self.engine_1._dao.insert_local_state = insert_local_state
        # Might be blacklisted once
        self.engine_1.get_queue_manager()._error_interval = 3
        self.local_client_1.make_file('/', u'File.txt',
            content=u'Some Content 2'.encode('utf-8'))
        sleep(10)
        self.wait_sync(fail_if_timeout=False)
        self.assertTrue(local_client.exists(u'/Renamed File.txt'))
        self.assertFalse(local_client.exists(u'/File.txt'))
        # Path dont change on Nuxeo
        self.assertIsNotNone(local_client.get_remote_id('/Renamed File.txt'))
        self.assertEqual(len(local_client.get_children_info(u'/')), 5)
        self.assertEqual(len(self.remote_document_client_1.get_children_info(self.workspace_1)), 5)

    def test_local_move_folder(self):
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
        self.wait_sync()
        # The server folder has been moved: the uid stays the same
        remote_folder_info = remote_client.get_info(original_folder_1_uid)

        # The parent folder is now folder 2
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

        self.assertEqual(len(local_client.get_children_info(u'/Original Folder 2/Original Folder 1')), 3)
        self.assertEqual(len(remote_client.get_children_info(original_folder_1_uid)), 3)
        self.assertEqual(len(local_client.get_children_info(u'/')), 3)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 3)

    def test_concurrent_local_rename_folder(self):
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
        self.wait_sync()

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

        self.assertEqual(len(local_client.get_children_info(u'/Renamed Folder 1')), 3)
        self.assertEqual(len(remote_client.get_children_info(folder_1_uid)), 3)
        self.assertEqual(len(local_client.get_children_info(u'/Renamed Folder 2')), 1)
        self.assertEqual(len(remote_client.get_children_info(folder_2_uid)), 1)
        self.assertEqual(len(local_client.get_children_info(u'/')), 4)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 4)

    def test_local_rename_sync_root_folder(self):
        # Use the Administrator to be able to introspect the container of the
        # test workspace.
        remote_client = RemoteDocumentClient(
            self.nuxeo_url, self.admin_user,
            'nxdrive-test-administrator-device', self.version,
            password=self.password, base_folder=self.workspace)

        folder_1_uid = remote_client.get_info(u'/Original Folder 1').uid

        # Create new clients to be able to introspect the test sync root
        toplevel_local_client = LocalClient(self.local_nxdrive_folder_1)

        toplevel_local_client.rename('/' + self.workspace_title,
            'Renamed Nuxeo Drive Test Workspace')
        self.wait_sync()

        workspace_info = remote_client.get_info(self.workspace)
        self.assertEquals(workspace_info.name,
            u"Renamed Nuxeo Drive Test Workspace")

        folder_1_info = remote_client.get_info(folder_1_uid)
        self.assertEquals(folder_1_info.name, u"Original Folder 1")
        self.assertEquals(folder_1_info.parent_uid, self.workspace)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 4)

    def test_local_rename_readonly_folder(self):
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Check local folder
        self.assertTrue(local_client.exists(u'/Original Folder 1'))
        uid = local_client.get_remote_id(u'/Original Folder 1')
        folder_1_state = self.engine_1.get_dao().get_normal_state_from_remote(uid)
        self.assertTrue(folder_1_state.remote_can_rename)

        # Set remote folder as readonly for test user
        folder_1_path = TEST_WORKSPACE_PATH + u'/Original Folder 1'
        op_input = "doc:" + folder_1_path
        self.root_remote_client.execute("Document.SetACE",
            op_input=op_input,
            user="nuxeoDriveTestUser_user_1",
            permission="Read")
        self.root_remote_client.block_inheritance(folder_1_path,
                                                  overwrite=False)
        self.wait_sync(wait_for_async=True)
        # Check can_rename flag in pair state
        folder_1_state = self.engine_1.get_dao().get_normal_state_from_remote(uid)
        self.assertFalse(folder_1_state.remote_can_rename)

        # Rename local folder
        local_client.rename(u'/Original Folder 1',
                            u'Renamed Folder 1 \xe9')
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 1 \xe9'))

        self.wait_sync()

        # Check remote folder has not been renamed
        folder_1_remote_info = remote_client.get_info(
            u'/Original Folder 1')
        self.assertEquals(folder_1_remote_info.name,
            u'Original Folder 1')

        # Check state of local folder and its children
        folder_1_state = self.engine_1.get_dao().get_normal_state_from_remote(uid)
        self.assertEquals(folder_1_state.remote_name,
                          u'Original Folder 1')

        self.assertTrue(local_client.exists(
            u'/Renamed Folder 1 \xe9/Original File 1.1.txt'))

        self.assertTrue(local_client.exists(
            u'/Renamed Folder 1 \xe9/Sub-Folder 1.1'))

        self.assertTrue(local_client.exists(
            u'/Renamed Folder 1 \xe9/Sub-Folder 1.2'))
        self.assertEqual(len(local_client.get_children_info(u'/Renamed Folder 1 \xe9')), 3)
        self.assertEqual(len(remote_client.get_children_info(folder_1_remote_info.uid)), 3)
        self.assertEqual(len(local_client.get_children_info(u'/')), 4)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 4)

    def test_local_rename_readonly_folder_with_rollback(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        sb, ctl = self.sb_1, self.controller_1

        def watchdog():
            return False

        def rollback():
            return True
        ctl.use_watchdog = watchdog
        ctl.synchronizer.local_full_scan = []
        ctl.local_rollback = rollback
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1
        session = ctl.get_session()

        # Check local folder
        self.assertTrue(local_client.exists(u'/Original Folder 1'))
        folder_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Original Folder 1').one()
        self.assertTrue(folder_1_state.remote_can_rename)

        # Set remote folder as readonly for test user
        folder_1_path = TEST_WORKSPACE_PATH + u'/Original Folder 1'
        op_input = "doc:" + folder_1_path
        self.root_remote_client.execute("Document.SetACE",
            op_input=op_input,
            user="nuxeoDriveTestUser_user_1",
            permission="Read")
        self.root_remote_client.block_inheritance(folder_1_path,
                                                  overwrite=False)

        # Check can_rename flag in pair state
        folder_1_state.refresh_remote(
            self.remote_file_system_client_1)
        self.assertFalse(folder_1_state.remote_can_rename)

        # Rename local folder
        local_client.rename(u'/Original Folder 1',
                            u'Renamed Folder 1 \xe9')
        self.assertFalse(local_client.exists(u'/Original Folder 1'))
        self.assertTrue(local_client.exists(u'/Renamed Folder 1 \xe9'))

        ctl.synchronizer.update_synchronize_server(sb)

        # Check remote folder has not been renamed
        folder_1_remote_info = remote_client.get_info(
            u'/Original Folder 1')
        self.assertEquals(folder_1_remote_info.name,
            u'Original Folder 1')

        # Check state of local folder and its children
        folder_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Original Folder 1').one()
        self.assertEquals(folder_1_state.remote_name,
                          u'Original Folder 1')

        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Original File 1.1.txt'))
        file_1_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Original File 1.1.txt').one()
        self.assertEquals(file_1_1_state.local_name,
                          u'Original File 1.1.txt')
        self.assertEquals(file_1_1_state.remote_name,
                          u'Original File 1.1.txt')

        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Sub-Folder 1.1'))
        folder_1_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Sub-Folder 1.1').one()
        self.assertEquals(folder_1_1_state.local_name,
                          u'Sub-Folder 1.1')
        self.assertEquals(folder_1_1_state.remote_name,
                          u'Sub-Folder 1.1')

    def test_local_move_with_remote_error(self):
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1

        # Check local folder
        self.assertTrue(local_client.exists(u'/Original Folder 1'))

        # Simulate server error
        self.engine_1.remote_filtered_fs_client_factory = RemoteTestClient
        self.engine_1.invalidate_client_cache()
        error = urllib2.HTTPError(None, 500, 'Mock server error', None, None)
        self.engine_1.get_remote_client().make_server_call_raise(error)

        local_client.rename(u'/Original Folder 1', u'IOErrorTest')
        self.wait_sync(timeout=5, fail_if_timeout=False)
        folder_1 = remote_client.get_info(u'/Original Folder 1')
        self.assertEquals(folder_1.name, u'Original Folder 1', 'Move has happen')
        self.assertTrue(local_client.exists(u'/IOErrorTest'))

        # Remove faulty client and set engine online
        self.engine_1.get_remote_client().make_server_call_raise(None)
        self.engine_1.remote_filtered_fs_client_factory = RemoteFilteredFileSystemClient
        self.engine_1.invalidate_client_cache()
        self.engine_1.set_offline(value=False)

        self.wait_sync()
        folder_1 = remote_client.get_info(folder_1.uid)
        self.assertEquals(folder_1.name, u'IOErrorTest', 'Move has not happen')
        self.assertTrue(local_client.exists(u'/IOErrorTest'))
        self.assertEqual(len(local_client.get_children_info(u'/IOErrorTest')), 3)
        self.assertEqual(len(remote_client.get_children_info(folder_1.uid)), 3)
        self.assertEqual(len(local_client.get_children_info(u'/')), 4)
        self.assertEqual(len(remote_client.get_children_info(self.workspace_1)), 4)

    def test_local_delete_readonly_folder(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        sb, ctl = self.sb_1, self.controller_1
        local_client = self.local_client_1
        remote_client = self.remote_document_client_1
        session = ctl.get_session()

        # Check local folder
        self.assertTrue(local_client.exists(u'/Original Folder 1'))
        folder_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Original Folder 1').one()
        self.assertTrue(folder_1_state.remote_can_delete)

        # Set remote folder as readonly for test user
        folder_1_path = TEST_WORKSPACE_PATH + u'/Original Folder 1'
        op_input = "doc:" + folder_1_path
        self.root_remote_client.execute("Document.SetACE",
            op_input=op_input,
            user="nuxeoDriveTestUser_user_1",
            permission="Read")
        self.root_remote_client.block_inheritance(folder_1_path,
                                                  overwrite=False)

        # Check can_delete flag in pair state
        folder_1_state.refresh_remote(
            self.remote_file_system_client_1)
        self.assertFalse(folder_1_state.remote_can_delete)

        # Delete local folder
        local_client.delete(u'/Original Folder 1')
        self.assertRaises(NotFound,
                          local_client.get_info, u'/Original Folder 1')

        self.assertEquals(ctl.synchronizer.update_synchronize_server(sb), 4)

        # Check remote folder and its children have not been deleted
        folder_1_remote_info = remote_client.get_info(
            u'/Original Folder 1')
        self.assertEquals(folder_1_remote_info.name,
            u'Original Folder 1')

        file_1_1_remote_info = remote_client.get_info(
            u'/Original Folder 1/Original File 1.1.txt')
        self.assertEquals(file_1_1_remote_info.name,
            u'Original File 1.1.txt')

        folder_1_1_remote_info = remote_client.get_info(
            u'/Original Folder 1/Sub-Folder 1.1')
        self.assertEquals(folder_1_1_remote_info.name,
            u'Sub-Folder 1.1')

        folder_1_2_remote_info = remote_client.get_info(
            u'/Original Folder 1/Sub-Folder 1.2')
        self.assertEquals(folder_1_2_remote_info.name,
            u'Sub-Folder 1.2')

        # Check local folder and its children have been re-created
        self.assertTrue(local_client.exists(u'/Original Folder 1'))
        folder_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Original Folder 1').one()
        self.assertEquals(folder_1_state.local_name,
                          u'Original Folder 1')
        self.assertEquals(folder_1_state.remote_name,
                          u'Original Folder 1')

        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Original File 1.1.txt'))
        file_1_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Original File 1.1.txt').one()
        self.assertEquals(file_1_1_state.local_name,
                          u'Original File 1.1.txt')
        self.assertEquals(file_1_1_state.remote_name,
                          u'Original File 1.1.txt')

        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Sub-Folder 1.1'))
        folder_1_1_state = session.query(LastKnownState).filter_by(
            local_name=u'Sub-Folder 1.1').one()
        self.assertEquals(folder_1_1_state.local_name,
                          u'Sub-Folder 1.1')
        self.assertEquals(folder_1_1_state.remote_name,
                          u'Sub-Folder 1.1')

        self.assertTrue(local_client.exists(
            u'/Original Folder 1/Sub-Folder 1.2'))
        folder_1_2_state = session.query(LastKnownState).filter_by(
            local_name=u'Sub-Folder 1.2').one()
        self.assertEquals(folder_1_2_state.local_name,
                          u'Sub-Folder 1.2')
        self.assertEquals(folder_1_2_state.remote_name,
                          u'Sub-Folder 1.2')

    # TODO: implement me once canDelete is checked in the synchronizer
    # def test_local_move_sync_root_folder(self):
    #    pass
