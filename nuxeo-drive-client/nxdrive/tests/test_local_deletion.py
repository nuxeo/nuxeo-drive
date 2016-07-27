from nxdrive.tests.common_unit_test import UnitTestCase
from nxdrive.osi import AbstractOSIntegration
import shutil
import os


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
        abs_path = self.local_client_1._abspath('/File_To_Delete.txt')
        # Pretend we had trash the file
        shutil.move(abs_path, os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'))
        self.wait_sync(wait_for_async=True)
        self.assertFalse(self.remote_document_client_1.exists('/File_To_Delete.txt'))
        self.assertFalse(self.local_client_1.exists('/File_To_Delete.txt'))
        # See if it untrash or recreate
        shutil.move(os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'), self.local_client_1._abspath('/'))
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.remote_document_client_1.exists(old_info.uid))
        self.assertTrue(self.local_client_1.exists('/File_To_Delete.txt'))


    def test_untrash_file_with_rename(self):
        self.local_client_1.make_file('/', 'File_To_Delete.txt', 'This is a content')
        self.wait_sync()
        self.assertTrue(self.remote_document_client_1.exists('/File_To_Delete.txt'))
        uid = self.local_client_1.get_remote_id('/File_To_Delete.txt')
        old_info = self.remote_document_client_1.get_info('/File_To_Delete.txt', use_trash=True)
        abs_path = self.local_client_1._abspath('/File_To_Delete.txt')
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
        shutil.move(os.path.join(self.local_test_folder_1, 'File_To_Delete2.txt'), self.local_client_1._abspath('/'))
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.remote_document_client_1.exists(old_info.uid))
        self.assertTrue(self.local_client_1.exists('/File_To_Delete2.txt'))
        self.assertFalse(self.local_client_1.exists('/File_To_Delete.txt'))
        self.assertEqual(self.local_client_1.get_content('/File_To_Delete2.txt'), 'New content')

    def test_untrash_file_on_delete_parent(self):
        file_path = '/ToDelete/File_To_Delete.txt'
        self.local_client_1.make_folder('/', 'ToDelete')
        self.local_client_1.make_file('/ToDelete', 'File_To_Delete.txt', 'This is a content')
        self.wait_sync()
        self.assertTrue(self.remote_document_client_1.exists(file_path))
        old_info = self.remote_document_client_1.get_info(file_path, use_trash=True)
        abs_path = self.local_client_1._abspath(file_path)
        # Pretend we had trash the file
        shutil.move(abs_path, os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'))
        self.wait_sync(wait_for_async=True)
        self.local_client_1.delete('/ToDelete')
        self.wait_sync(wait_for_async=True)
        self.assertFalse(self.remote_document_client_1.exists(file_path))
        self.assertFalse(self.local_client_1.exists(file_path))
        # See if it untrash or recreate
        self.local_client_1.make_folder('/', 'ToDelete')
        shutil.move(os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'), self.local_client_1._abspath('/ToDelete/'))
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
        abs_path = self.local_client_1._abspath(file_path)
        # Pretend we had trash the file
        shutil.move(abs_path, os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'))
        self.local_client_1.delete('/ToDelete')
        self.wait_sync(wait_for_async=True)
        self.assertFalse(self.remote_document_client_1.exists(file_path))
        self.assertFalse(self.local_client_1.exists(file_path))
        # See if it untrash or recreate
        self.local_client_1.make_folder('/', 'ToDelete')
        shutil.move(os.path.join(self.local_test_folder_1, 'File_To_Delete.txt'), self.local_client_1._abspath('/ToDelete/'))
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.remote_document_client_1.exists(old_info.uid))
        self.assertTrue(self.local_client_1.exists(file_path))