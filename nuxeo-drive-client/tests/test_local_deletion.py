# coding: utf-8
import os
import shutil
from unittest import skip

from nxdrive.options import Options
from nxdrive.osi import AbstractOSIntegration
from .common_unit_test import UnitTestCase


class TestLocalDeletion(UnitTestCase):

    def setUp(self):
        super(TestLocalDeletion, self).setUp()
        self.engine_1.start()
        self.wait_sync()

    def test_untrash_file(self):
        self.local_client_1.make_file('/', 'File_To_Delete.txt', 'This is a content')
        self.wait_sync()
        self.assertTrue(self.remote_document_client_1.exists('/File_To_Delete.txt'))
        old_info = self.remote_document_client_1.get_info('/File_To_Delete.txt', use_trash=True)
        abs_path = self.local_client_1.abspath('/File_To_Delete.txt')
        # Pretend we had trash the file
        shutil.move(abs_path, os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'))
        self.wait_sync(wait_for_async=True)
        self.assertFalse(self.remote_document_client_1.exists('/File_To_Delete.txt'))
        self.assertFalse(self.local_client_1.exists('/File_To_Delete.txt'))
        # See if it untrash or recreate
        shutil.move(os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'), self.local_client_1.abspath('/'))
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.remote_document_client_1.exists(old_info.uid))
        self.assertTrue(self.local_client_1.exists('/File_To_Delete.txt'))

    def test_untrash_file_with_rename(self):
        self.local_client_1.make_file('/', 'File_To_Delete.txt', 'This is a content')
        self.wait_sync()
        self.assertTrue(self.remote_document_client_1.exists('/File_To_Delete.txt'))
        uid = self.local_client_1.get_remote_id('/File_To_Delete.txt')
        old_info = self.remote_document_client_1.get_info('/File_To_Delete.txt', use_trash=True)
        abs_path = self.local_client_1.abspath('/File_To_Delete.txt')
        # Pretend we had trash the file
        shutil.move(abs_path, os.path.join(self.local_test_folder_1, 'File_To_Delete2.txt'))
        self.wait_sync(wait_for_async=True)
        self.assertFalse(self.remote_document_client_1.exists('/File_To_Delete.txt'))
        self.assertFalse(self.local_client_1.exists('/File_To_Delete.txt'))
        with open(os.path.join(self.local_test_folder_1, 'File_To_Delete2.txt'), 'w') as f:
            f.write('New content')
        if AbstractOSIntegration.is_windows():
            # Python API overwrite the tag by default
            with open(os.path.join(self.local_test_folder_1, 'File_To_Delete2.txt:ndrive'), 'w') as f:
                f.write(uid)
        # See if it untrash or recreate
        shutil.move(os.path.join(self.local_test_folder_1, 'File_To_Delete2.txt'), self.local_client_1.abspath('/'))
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.remote_document_client_1.exists(old_info.uid))
        self.assertTrue(self.local_client_1.exists('/File_To_Delete2.txt'))
        self.assertFalse(self.local_client_1.exists('/File_To_Delete.txt'))
        self.assertEqual(self.local_client_1.get_content('/File_To_Delete2.txt'), 'New content')

    def test_move_untrash_file_on_parent(self):
        file_path = '/ToDelete/File_To_Delete.txt'
        self.local_client_1.make_folder('/', 'ToDelete')
        self.local_client_1.make_file('/ToDelete', 'File_To_Delete.txt', 'This is a content')
        self.wait_sync()
        self.assertTrue(self.remote_document_client_1.exists(file_path))
        old_info = self.remote_document_client_1.get_info(file_path, use_trash=True)
        abs_path = self.local_client_1.abspath(file_path)
        # Pretend we had trash the file
        shutil.move(abs_path, os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'))        
        self.wait_sync(wait_for_async=True)
        self.local_client_1.delete('/ToDelete')
        self.wait_sync(wait_for_async=True)
        self.assertFalse(self.remote_document_client_1.exists(file_path))
        self.assertFalse(self.local_client_1.exists(file_path))
        # See if it untrash or recreate
        shutil.move(os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'), self.local_client_1.abspath('/'))
        self.wait_sync(wait_for_async=True)
        new_info = self.remote_document_client_1.get_info(old_info.uid, use_trash=True)        
        self.assertEqual(new_info.state, 'project')
        self.assertTrue(self.local_client_1.exists('/File_To_Delete.txt'))
        # Because remote_document_client_1 was used
        self.assertTrue(self.local_client_1.get_remote_id('/').endswith(new_info.parent_uid))

    @Options.mock()
    def test_move_untrash_file_on_parent_with_no_rights(self):
        # Setup
        file_path = '/ToDelete/File_To_Delete.txt'
        self.local_client_1.make_folder('/', 'ToDelete')
        self.local_client_1.make_file('/ToDelete', 'File_To_Delete.txt', 'This is a content')
        self.wait_sync()
        self.assertTrue(self.remote_document_client_1.exists(file_path))
        old_info = self.remote_document_client_1.get_info(file_path, use_trash=True)
        abs_path = self.local_client_1.abspath(file_path)
        # Pretend we had trash the file
        shutil.move(abs_path, os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'))
        self.wait_sync(wait_for_async=True)

        # Remove rights
        folder_path = u'/default-domain/workspaces/nuxeo-drive-test-workspace/ToDelete'
        op_input = "doc:" + folder_path
        self.root_remote_client.execute("Document.SetACE",
                                        op_input=op_input,
                                        user=self.user_1,
                                        permission="Read")
        self.root_remote_client.block_inheritance(folder_path, overwrite=False)
        self.root_remote_client.delete(folder_path)
        self.wait_sync(wait_for_async=True)
        self.assertFalse(self.remote_document_client_1.exists(file_path))
        self.assertFalse(self.local_client_1.exists(file_path))

        # See if it untrash or recreate
        shutil.move(os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'), self.local_client_1.abspath('/'))
        self.assertIsNotNone(self.local_client_1.get_remote_id('/File_To_Delete.txt'))
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.local_client_1.exists('/File_To_Delete.txt'))
        new_uid = self.local_client_1.get_remote_id('/File_To_Delete.txt')
        # Because remote_document_client_1 was used
        self.assertIsNotNone(new_uid)
        self.assertFalse(new_uid.endswith(old_info.uid))

    @skip('Wait to know what is the expectation - the previous folder doesnt exist')
    def test_move_untrash_file_on_parent_with_no_rights_on_destination(self):
        # Setup the test
        file_path = '/ToDelete/File_To_Delete.txt'
        self.local_client_1.make_folder('/', 'ToDelete')
        self.local_client_1.make_folder('/', 'ToCopy')
        self.local_client_1.make_file('/ToDelete', 'File_To_Delete.txt', 'This is a content')
        self.wait_sync()
        self.assertTrue(self.remote_document_client_1.exists(file_path))
        old_info = self.remote_document_client_1.get_info(file_path, use_trash=True)
        abs_path = self.local_client_1.abspath(file_path)

        # Pretend we had trash the file
        shutil.move(abs_path, os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'))
        self.wait_sync(wait_for_async=True)

        # Remove rights
        folder_path = u'/default-domain/workspaces/nuxeo-drive-test-workspace/ToCopy'
        op_input = "doc:" + folder_path
        self.root_remote_client.execute("Document.SetACE",
                                        op_input=op_input,
                                        user=self.user_1,
                                        permission="Read")
        self.root_remote_client.block_inheritance(folder_path, overwrite=False)
        # Delete
        self.local_client_1.delete('/ToDelete')
        self.wait_sync(wait_for_async=True)
        self.assertFalse(self.remote_document_client_1.exists(file_path))
        self.assertFalse(self.local_client_1.exists(file_path))

        # See if it untrash or unsynchronized
        self.local_client_1.unlock_ref('/ToCopy')
        shutil.move(os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'), self.local_client_1.abspath('/ToCopy'))
        self.wait_sync(wait_for_async=True)

    def test_untrash_file_on_delete_parent(self):
        # Setup
        file_path = '/ToDelete/File_To_Delete.txt'
        self.local_client_1.make_folder('/', 'ToDelete')
        self.local_client_1.make_file('/ToDelete', 'File_To_Delete.txt', 'This is a content')
        self.wait_sync()
        self.assertTrue(self.remote_document_client_1.exists(file_path))
        old_info = self.remote_document_client_1.get_info(file_path, use_trash=True)
        abs_path = self.local_client_1.abspath(file_path)

        # Pretend we had trash the file
        shutil.move(abs_path, os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'))
        self.wait_sync(wait_for_async=True)
        self.local_client_1.delete('/ToDelete')
        self.wait_sync(wait_for_async=True)
        self.assertFalse(self.remote_document_client_1.exists(file_path))
        self.assertFalse(self.local_client_1.exists(file_path))

        # See if it untrash or recreate
        self.local_client_1.make_folder('/', 'ToDelete')
        shutil.move(os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'), self.local_client_1.abspath('/ToDelete/'))
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.remote_document_client_1.exists(old_info.uid))
        new_info = self.remote_document_client_1.get_info(old_info.uid, use_trash=True)
        self.assertTrue(self.remote_document_client_1.exists(new_info.parent_uid))
        self.assertTrue(self.local_client_1.exists(file_path))

    def test_trash_file_then_parent(self):
        file_path = '/ToDelete/File_To_Delete.txt'
        self.local_client_1.make_folder('/', 'ToDelete')
        self.local_client_1.make_file('/ToDelete', 'File_To_Delete.txt', 'This is a content')
        self.wait_sync()
        self.assertTrue(self.remote_document_client_1.exists(file_path))
        old_info = self.remote_document_client_1.get_info(file_path, use_trash=True)
        abs_path = self.local_client_1.abspath(file_path)
        # Pretend we had trash the file
        shutil.move(abs_path, os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'))
        self.local_client_1.delete('/ToDelete')
        self.wait_sync(wait_for_async=True)
        self.assertFalse(self.remote_document_client_1.exists(file_path))
        self.assertFalse(self.local_client_1.exists(file_path))
        # See if it untrash or recreate
        self.local_client_1.make_folder('/', 'ToDelete')
        shutil.move(os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'), self.local_client_1.abspath('/ToDelete/'))
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.remote_document_client_1.exists(old_info.uid))
        self.assertTrue(self.local_client_1.exists(file_path))

