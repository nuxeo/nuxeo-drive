# coding: utf-8
import hashlib
import sys

import pytest
from nuxeo.exceptions import HTTPError

from nxdrive.client import LocalClient
from .common_unit_test import UnitTestCase


class TestPermissionHierarchy(UnitTestCase):

    def setUpApp(self, **kwargs):
        super(TestPermissionHierarchy, self).setUpApp(
            server_profile='permission')

    def setUp(self):
        self.admin = self.root_remote
        self.local_1 = LocalClient(self.local_nxdrive_folder_1)
        self.local_2 = LocalClient(self.local_nxdrive_folder_2)

        # Make sure user workspace is created and fetch its UID
        res = self.remote_document_client_1.make_file_in_user_workspace(
            'File in user workspace', filename='USFile.txt')
        self.workspace_uid = res['parentRef']
        self.addCleanup(self.delete_wspace)

    def delete_wspace(self):
        # Cleanup user workspace
        if self.workspace_uid and self.admin.exists(self.workspace_uid):
            self.admin.delete(self.workspace_uid, use_trash=False)

    def test_sync_delete_root(self):
        # Create test folder in user workspace as test user
        remote = self.remote_document_client_1
        test_folder_uid = remote.make_folder(self.workspace_uid, 'test_folder')
        # Create a document in the test folder
        remote.make_file(test_folder_uid, 'test_file.txt', 'Some content.')

        # Register test folder as a sync root
        remote.register_as_root(test_folder_uid)

        # Start engine
        self.engine_1.start()

        # Wait for synchronization
        self.wait_sync(wait_for_async=True)

        # Check locally synchronized content
        root = '/My Docs/test_folder'
        assert self.local_1.exists(root)
        assert self.local_1.exists(root + '/test_file.txt')

        # Delete test folder
        remote.delete(test_folder_uid)

        # Wait for synchronization
        self.wait_sync(wait_for_async=True)

        # Check locally synchronized content
        assert not self.local_1.exists(root)
        assert not self.local_1.get_children_info('/My Docs')

    def test_sync_delete_shared_folder(self):
        remote = self.remote_document_client_1
        self.engine_1.start()
        # Register user workspace as a sync root for user1
        remote.register_as_root(self.workspace_uid)

        # Create test folder in user workspace as user1
        test_folder_uid = remote.make_folder(self.workspace_uid, 'test_folder')
        self.wait_sync(wait_for_async=True)
        assert self.local_1.exists('/My Docs')
        assert self.local_1.exists('/My Docs/test_folder')

        # Grant ReadWrite permission to user2 on test folder
        self.set_readonly(self.user_2, test_folder_uid, grant=False)
        self.wait_sync(wait_for_async=True)

        # Register test folder as a sync root for user2
        self.remote_document_client_2.register_as_root(test_folder_uid)
        self.wait_sync(wait_for_async=True)

        # Delete test folder
        remote.delete(test_folder_uid)
        self.wait_sync(wait_for_async=True)

        # Check locally synchronized content
        assert not self.local_1.exists('/My Docs/test_folder')
        children = self.local_1.get_children_info('/My Docs')
        assert len(children) == 1

    def test_sync_unshared_folder(self):
        # Register user workspace as a sync root for user1
        remote = self.remote_document_client_1
        remote2 = self.remote_document_client_2
        remote.register_as_root(self.workspace_uid)

        # Start engine
        self.engine_2.start()

        # Wait for synchronization
        self.wait_sync(wait_for_async=True,
                       wait_for_engine_2=True,
                       wait_for_engine_1=False)
        # Check locally synchronized content
        assert self.local_2.exists('/My Docs')
        assert self.local_2.exists('/Other Docs')

        # Create test folder in user workspace as user1
        test_folder_uid = remote.make_folder(self.workspace_uid, 'Folder A')
        folder_b = remote.make_folder(test_folder_uid, 'Folder B')
        folder_c = remote.make_folder(folder_b, 'Folder C')
        folder_d = remote.make_folder(folder_c, 'Folder D')
        remote.make_folder(folder_d, 'Folder E')

        # Grant ReadWrite permission to user2 on test folder
        self.set_readonly(self.user_2, test_folder_uid, grant=False)

        # Register test folder as a sync root for user2
        remote2.register_as_root(test_folder_uid)
        # Wait for synchronization
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True,
                       wait_for_engine_1=False)
        assert self.local_2.exists('/Other Docs/Folder A')
        assert self.local_2.exists(
            '/Other Docs/Folder A/Folder B/Folder C/Folder D/Folder E')
        # Use for later get_fs_item checks
        folder_b_fs = self.local_2.get_remote_id(
            '/Other Docs/Folder A/Folder B')
        folder_a_fs = self.local_2.get_remote_id('/Other Docs/Folder A')
        # Unshare Folder A and share Folder C
        self.admin.operations.execute(
            command='Document.RemoveACL', input_obj='doc:' + test_folder_uid,
            acl='local')
        self.set_readonly(self.user_2, folder_c)
        remote2.register_as_root(folder_c)
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True,
                       wait_for_engine_1=False)
        assert not self.local_2.exists('/Other Docs/Folder A')
        assert self.local_2.exists('/Other Docs/Folder C')
        assert self.local_2.exists('/Other Docs/Folder C/Folder D/Folder E')

        # Verify that we dont have any 403 errors
        assert not self.remote_2.get_fs_item(folder_a_fs)
        assert not self.remote_2.get_fs_item(folder_b_fs)

    @pytest.mark.xfail(
        sys.platform == 'win32',
        reason='Following the NXDRIVE-836 fix, this test always fails because '
               'when moving a file from a RO folder to a RW folder will end up'
               ' being a simple file creation. As we cannot know events order,'
               ' we cannot understand a local move is being made just before '
               'a security update. To bo fixed with the engine refactoring.')
    def test_sync_move_permission_removal(self):
        remote = self.remote_document_client_1
        remote2 = self.remote_document_client_2
        local = self.local_2

        root = remote.make_folder(self.workspace_uid, 'testing')
        readonly = remote.make_folder(root, 'ReadFolder')
        readwrite = remote.make_folder(root, 'WriteFolder')

        # Register user workspace as a sync root for user1
        remote.register_as_root(self.workspace_uid)

        # Register root folder as a sync root for user2
        self.set_readonly(self.user_2, root, grant=False)
        remote2.register_as_root(root)

        # Make one read-only document
        remote.make_file(readonly, 'file_ro.txt', content=b'Read-only doc.')

        # Read only folder for user 2
        self.set_readonly(self.user_2, readonly)

        # Basic test to be sure we are in RO mode
        with pytest.raises(HTTPError):
            remote2.make_file(readonly, 'test.txt', content=b'test')

        # ReadWrite folder for user 2
        self.set_readonly(self.user_2, readwrite, grant=False)

        # Start'n sync
        self.engine_2.start()
        self.wait_sync(wait_for_async=True, wait_for_engine_1=False,
                       wait_for_engine_2=True)

        # Checks
        root = '/Other Docs/testing/'
        assert local.exists(root + 'ReadFolder')
        assert local.exists(root + 'ReadFolder/file_ro.txt')
        assert local.exists(root + 'WriteFolder')
        content = local.get_content(root + 'ReadFolder/file_ro.txt')
        assert content == 'Read-only doc.'

        # Move the read-only file
        local.move(root + 'ReadFolder/file_ro.txt', root + 'WriteFolder',
                   name='file_rw.txt')

        # Remove RO on ReadFolder folder
        self.set_readonly(self.user_2, readonly, grant=False)

        # Edit the new writable file
        local.update_content(root + 'WriteFolder/file_rw.txt',
                             b'Now a fresh read-write doc.')

        # Sync
        self.wait_sync(wait_for_async=True,
                       wait_for_engine_1=False,
                       wait_for_engine_2=True)

        # Status check
        assert not self.engine_2.get_dao().get_errors(limit=0)
        assert not self.engine_2.get_dao().get_filters()
        assert not self.engine_2.get_dao().get_unsynchronizeds()

        # Local checks
        assert not local.exists(root + 'ReadFolder/file_ro.txt')
        assert not local.exists(root + 'WriteFolder/file_ro.txt')
        assert local.exists(root + 'WriteFolder/file_rw.txt')
        content = local.get_content(root + 'WriteFolder/file_rw.txt')
        assert content == 'Now a fresh read-write doc.'

        # Remote checks
        assert not remote.get_children_info(readonly)
        children = remote.get_children_info(readwrite)
        assert len(children) == 1
        assert children[0].filename == 'file_rw.txt'
        good_digest = hashlib.md5('Now a fresh read-write doc.').hexdigest()
        assert children[0].digest == good_digest
