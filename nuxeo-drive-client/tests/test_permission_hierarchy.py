# coding: utf-8
import hashlib
from urllib2 import HTTPError

from nxdrive.client import LocalClient, RemoteDocumentClient
from nxdrive.osi import AbstractOSIntegration
from tests.common_unit_test import UnitTestCase


class TestPermissionHierarchy(UnitTestCase):

    def setUpApp(self):
        super(TestPermissionHierarchy, self).setUpApp(
            server_profile='permission')

    def tearDownApp(self):
        super(TestPermissionHierarchy, self).tearDownApp(
            server_profile='permission')

    def setUp(self):
        self.admin = self.root_remote_client
        self.user1 = RemoteDocumentClient(self.nuxeo_url,
                                          self.user_1,
                                          'nxdrive-test-device-1',
                                          self.version,
                                          password=self.password_1,
                                          upload_tmp_dir=self.upload_tmp_dir)
        self.user2 = RemoteDocumentClient(self.nuxeo_url,
                                          self.user_2,
                                          'nxdrive-test-device-2',
                                          self.version,
                                          password=self.password_2,
                                          upload_tmp_dir=self.upload_tmp_dir)
        self.local_client_1 = LocalClient(self.local_nxdrive_folder_1)
        self.local_client_2 = LocalClient(self.local_nxdrive_folder_2)

        # Make sure user workspace is created and fetch its UID
        self.workspace_uid = self.user1.make_file_in_user_workspace(
            'File in user workspace', filename='USFile.txt')['parentRef']

    def tearDown(self):
        # Cleanup user workspace
        if self.workspace_uid and self.admin.exists(self.workspace_uid):
            self.admin.delete(self.workspace_uid, use_trash=False)

    def set_readonly(self, user, doc_path, grant=True):
        """
        Mark one folder as RO or RW.
        :param bool grant: Set RO if True else RW.
        """

        op_input = 'doc:' + doc_path
        if grant:
            self.root_remote_client.execute('Document.SetACE',
                                            op_input=op_input,
                                            user=user,
                                            permission='Read')
            self.root_remote_client.block_inheritance(
                doc_path, overwrite=False)
        else:
            self.root_remote_client.execute('Document.SetACE',
                                            op_input=op_input,
                                            user=user,
                                            permission='ReadWrite',
                                            grant='true')

    def test_sync_delete_root(self):
        # Create test folder in user workspace as test user
        test_folder_uid = self.user1.make_folder(
            self.workspace_uid, 'test_folder')
        # Create a document in the test folder
        self.user1.make_file(
            test_folder_uid, 'test_file.txt', 'Some content.')

        # Register test folder as a sync root
        self.user1.register_as_root(test_folder_uid)

        # Start engine
        self.engine_1.start()

        # Wait for synchronization
        self.wait_sync(wait_for_async=True)

        # Check locally synchronized content
        root = '/My Docs/test_folder'
        self.assertTrue(self.local_client_1.exists(root))
        self.assertTrue(self.local_client_1.exists(root + '/test_file.txt'))

        # Delete test folder
        self.user1.delete(test_folder_uid)

        # Wait for synchronization
        self.wait_sync(wait_for_async=True)

        # Check locally synchronized content
        self.assertFalse(self.local_client_1.exists(root))
        self.assertEqual(
            len(self.local_client_1.get_children_info('/My Docs')), 0)

    def test_sync_delete_shared_folder(self):
        # Register user workspace as a sync root for user1
        self.user1.register_as_root(self.workspace_uid)

        # Start engine
        self.engine_1.start()

        # Wait for synchronization
        self.wait_sync(wait_for_async=True)
        # Check locally synchronized content
        self.assertTrue(self.local_client_1.exists('/My Docs'))

        # Create test folder in user workspace as user1
        test_folder_uid = self.user1.make_folder(
            self.workspace_uid, 'test_folder')
        # Wait for synchronization
        self.wait_sync(wait_for_async=True)
        # Check locally synchronized content
        self.assertTrue(self.local_client_1.exists('/My Docs/test_folder'))

        # Grant ReadWrite permission to user2 on test folder
        self.set_readonly(self.user_2, test_folder_uid, grant=False)
        self.wait_sync(wait_for_async=True)

        # Register test folder as a sync root for user2
        self.user2.register_as_root(test_folder_uid)
        # Wait for synchronization
        self.wait_sync(wait_for_async=True)

        # Delete test folder
        self.user1.delete(test_folder_uid)

        # Synchronize deletion
        self.wait_sync(wait_for_async=True)
        # Check locally synchronized content
        self.assertFalse(self.local_client_1.exists('/My Docs/test_folder'))
        self.assertEqual(
            len(self.local_client_1.get_children_info('/My Docs')), 1)

    def test_sync_unshared_folder(self):
        # Register user workspace as a sync root for user1
        self.user1.register_as_root(self.workspace_uid)

        # Start engine
        self.engine_2.start()

        # Wait for synchronization
        self.wait_sync(wait_for_async=True,
                       wait_for_engine_2=True,
                       wait_for_engine_1=False)
        # Check locally synchronized content
        self.assertTrue(self.local_client_2.exists('/My Docs'))
        self.assertTrue(self.local_client_2.exists('/Other Docs'))

        # Create test folder in user workspace as user1
        test_folder_uid = self.user1.make_folder(self.workspace_uid, 'Folder A')
        folder_b = self.user1.make_folder(test_folder_uid, 'Folder B')
        folder_c = self.user1.make_folder(folder_b, 'Folder C')
        folder_d = self.user1.make_folder(folder_c, 'Folder D')
        self.user1.make_folder(folder_d, 'Folder E')

        # Grant ReadWrite permission to user2 on test folder
        self.set_readonly(self.user_2, test_folder_uid, grant=False)

        # Register test folder as a sync root for user2
        self.user2.register_as_root(test_folder_uid)
        # Wait for synchronization
        self.wait_sync(wait_for_async=True,
                       wait_for_engine_2=True,
                       wait_for_engine_1=False)
        self.assertTrue(self.local_client_2.exists('/Other Docs/Folder A'))
        self.assertTrue(self.local_client_2.exists(
            '/Other Docs/Folder A/Folder B/Folder C/Folder D/Folder E'))
        # Use for later get_fs_item checks
        folder_b_fs = self.local_client_2.get_remote_id(
            '/Other Docs/Folder A/Folder B')
        folder_a_fs = self.local_client_2.get_remote_id('/Other Docs/Folder A')
        # Unshare Folder A and share Folder C
        self.admin.execute('Document.RemoveACL',
                           op_input='doc:' + test_folder_uid,
                           acl='local')
        self.set_readonly(self.user_2, folder_c)
        self.user2.register_as_root(folder_c)
        self.wait_sync(wait_for_async=True,
                       wait_for_engine_2=True,
                       wait_for_engine_1=False)
        self.assertFalse(self.local_client_2.exists('/Other Docs/Folder A'))
        self.assertTrue(self.local_client_2.exists('/Other Docs/Folder C'))
        self.assertTrue(self.local_client_2.exists(
            '/Other Docs/Folder C/Folder D/Folder E'))

        # Verify that we dont have any 403 errors
        self.assertIsNone(self.remote_file_system_client_2.get_fs_item(
            folder_a_fs))
        self.assertIsNone(self.remote_file_system_client_2.get_fs_item(
            folder_b_fs))

    def test_sync_move_permission_removal(self):
        root = self.user1.make_folder(self.workspace_uid, 'testing')
        readonly = self.user1.make_folder(root, 'ReadFolder')
        readwrite = self.user1.make_folder(root, 'WriteFolder')

        # Register user workspace as a sync root for user1
        self.user1.register_as_root(self.workspace_uid)

        # Register root folder as a sync root for user2
        self.set_readonly(self.user_2, root, grant=False)
        self.user2.register_as_root(root)

        # Make one read-only document
        self.user1.make_file(readonly, 'file_ro.txt', content='Read-only doc.')

        # Read only folder for user 2
        self.set_readonly(self.user_2, readonly)

        # Basic test to be sure we are in RO mode
        with self.assertRaises(HTTPError):
            self.user2.make_file(readonly, 'test.txt', content='test')

        # ReadWrite folder for user 2
        self.set_readonly(self.user_2, readwrite, grant=False)

        # Start'n sync
        self.engine_2.start()
        self.wait_sync(wait_for_async=True,
                       wait_for_engine_1=False,
                       wait_for_engine_2=True)

        # Checks
        root = '/Other Docs/testing/'
        self.assertTrue(self.local_client_2.exists(root + 'ReadFolder'))
        self.assertTrue(self.local_client_2.exists(
            root + 'ReadFolder/file_ro.txt'))
        self.assertTrue(self.local_client_2.exists(root + 'WriteFolder'))
        self.assertEqual(
            self.local_client_2.get_content(root + 'ReadFolder/file_ro.txt'),
            'Read-only doc.')

        # Move the read-only file
        self.local_client_2.move(root + 'ReadFolder/file_ro.txt',
                                 root + 'WriteFolder',
                                 name='file_rw.txt')

        # Remove RO on ReadFolder folder
        self.set_readonly(self.user_2, readonly, grant=False)

        # Edit the new writable file
        self.local_client_2.update_content(root + 'WriteFolder/file_rw.txt',
                                           'Now a fresh read-write doc.')

        # Sync
        self.wait_sync(wait_for_async=True,
                       wait_for_engine_1=False,
                       wait_for_engine_2=True)

        # Local checks
        self.assertFalse(self.local_client_2.exists(
            root + 'ReadFolder/file_ro.txt'))
        self.assertFalse(self.local_client_2.exists(
            root + 'WriteFolder/file_ro.txt'))
        self.assertTrue(self.local_client_2.exists(
            root + 'WriteFolder/file_rw.txt'))
        self.assertEqual(
            self.local_client_2.get_content(root + 'WriteFolder/file_rw.txt'),
            'Now a fresh read-write doc.')

        # Remote checks
        self.assertEqual(len(self.user1.get_children_info(readonly)), 0)
        children = self.user1.get_children_info(readwrite)
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].filename, 'file_rw.txt')
        good_digest = hashlib.md5('Now a fresh read-write doc.').hexdigest()
        self.assertEqual(children[0].digest, good_digest)
        # No errors check
        self.assertEqual(len(self.engine_2.get_dao().get_errors()), 0)
