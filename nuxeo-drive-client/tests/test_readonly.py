# coding: utf-8
import os
import time
from unittest import skipIf

from nxdrive.logging_config import get_logger
from nxdrive.osi import AbstractOSIntegration
from tests.common import OS_STAT_MTIME_RESOLUTION, TEST_WORKSPACE_PATH
from tests.common_unit_test import RandomBug, UnitTestCase

log = get_logger(__name__)


class TestReadOnly(UnitTestCase):

    def setUp(self):
        super(TestReadOnly, self).setUp()
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

    def _set_readonly_permission(self, user, doc_path, grant):
        op_input = "doc:" + doc_path
        if grant:
            self.root_remote_client.execute("Document.SetACE", op_input=op_input, user=user, permission="Read")
            self.root_remote_client.block_inheritance(doc_path,
                                                      overwrite=False)
        else:
            self.root_remote_client.execute("Document.SetACE", op_input=op_input, user=user, permission="Write",
                                            grant="true")

    def test_rename_readonly_file(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test folder')
        remote.make_file('/Test folder', 'joe.odt', 'Some content')
        remote.make_file('/Test folder', 'jack.odt', 'Some content')
        remote.make_folder('/Test folder', 'Sub folder 1')
        remote.make_file('/Test folder/Sub folder 1', 'sub file 1.txt',
                         'Content')
        self._set_readonly_permission(self.user_1, TEST_WORKSPACE_PATH + '/Test folder', True)
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.odt'))
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertTrue(local.exists('/Test folder/Sub folder 1'))
        self.assertTrue(local.exists('/Test folder/Sub folder 1/sub file 1.txt'))

        # Local changes
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        # Create new file
        # Fake the readonly forcing
        local.unset_readonly('/Test folder')
        local.make_file('/Test folder', 'local.odt', 'New local content')
        # Create new folder with files
        local.make_folder('/Test folder', 'Local sub folder 2')
        local.make_file('/Test folder/Local sub folder 2', 'local sub file 2.txt', 'Other local content')
        # Update file
        local.unset_readonly('/Test folder/joe.odt')
        local.update_content('/Test folder/joe.odt', 'Some locally updated content')
        local.set_readonly('/Test folder/joe.odt')
        local.set_readonly('/Test folder')

        # TODO Might rollback if rollback only !
        self.wait_sync()
        self.assertFalse(remote.exists('/Test folder/local.odt'))
        self.assertFalse(remote.exists('/Test folder/Local sub folder 2'))
        self.assertFalse(remote.exists('/Test folder/Local sub folder 2/local sub file 2.txt'))
        self.assertTrue(local.exists('/Test folder/local.odt'))
        self.assertEqual(remote.get_content('/Test folder/joe.odt'), 'Some content')

    def touch(self, fname):
        try:
            with open(fname, 'w') as f:
                f.write('Test')
        except Exception as e:
            log.debug('Exception occurs during touch: %r', e)
            return False
        return True

    @skipIf(AbstractOSIntegration.is_windows(),
            'Readonly folder let new file creation')
    def test_readonly_user_access(self):
        # Should not be able to create content in root folder
        fname = os.path.join(self.local_nxdrive_folder_1, 'test.txt')
        self.assertFalse(self.touch(fname), "Should not be able to create in ROOT folder")
        fname = os.path.join(self.sync_root_folder_1, 'test.txt')
        self.assertTrue(self.touch(fname), "Should be able to create in SYNCROOT folder")
        fname = os.path.join(self.sync_root_folder_1, 'Test folder', 'test.txt')
        self.assertFalse(self.touch(fname), "Should be able to create in SYNCROOT folder")
        fname = os.path.join(self.sync_root_folder_1, 'Test folder', 'Sub folder 1', 'test.txt')
        self.assertFalse(self.touch(fname), "Should be able to create in SYNCROOT folder")

    @skipIf(AbstractOSIntegration.is_windows(),
            'Readonly folder let new file creation')
    @RandomBug('NXDRIVE-816', target='mac', mode='BYPASS')
    def test_file_readonly_change(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test folder')
        remote.make_file('/Test folder', 'joe.odt', 'Some content')
        remote.make_file('/Test folder', 'jack.odt', 'Some content')
        remote.make_folder('/Test folder', 'Sub folder 1')
        remote.make_file('/Test folder/Sub folder 1', 'sub file 1.txt',
                         'Content')
        self._set_readonly_permission(self.user_1, TEST_WORKSPACE_PATH + '/Test folder', True)
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.odt'))
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertTrue(local.exists('/Test folder/Sub folder 1'))
        self.assertTrue(local.exists('/Test folder/Sub folder 1/sub file 1.txt'))

        # Update the content on the server
        self.root_remote_client.update_content(TEST_WORKSPACE_PATH + '/Test folder/joe.odt',
                                               'Some remotely updated content', 'joe.odt')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.get_content('/Test folder/joe.odt'), 'Some remotely updated content')

        # Remove the readonly
        self._set_readonly_permission(self.user_1, TEST_WORKSPACE_PATH + '/Test folder', False)
        self.wait_sync(wait_for_async=True)
        fname = os.path.join(self.sync_root_folder_1, 'Test folder', 'test.txt')
        fname2 = os.path.join(self.sync_root_folder_1, 'Test folder', 'Sub folder 1', 'test.txt')
        # Check it works
        self.assertTrue(self.touch(fname))
        self.assertTrue(self.touch(fname2))

        # First remove the files
        os.remove(fname)
        os.remove(fname2)
        # Put it back readonly
        self._set_readonly_permission(self.user_1, TEST_WORKSPACE_PATH + '/Test folder', True)
        self.wait_sync(wait_for_async=True)

        # Check it works
        self.assertFalse(self.touch(fname))
        self.assertFalse(self.touch(fname2))

    def test_locked_document(self):
        remote = self.remote_document_client_1
        remote.make_folder('/', 'Test locking')
        remote.make_file('/Test locking', 'myDoc.odt', 'Some content')
        self.wait_sync(wait_for_async=True)

        # Check readonly flag is not set for a document that isn't locked
        user1_file_path = os.path.join(self.sync_root_folder_1, 'Test locking', 'myDoc.odt')
        self.assertTrue(os.path.exists(user1_file_path))
        self.assertTrue(self.touch(user1_file_path))
        self.wait_sync()

        # Check readonly flag is not set for a document locked by the current user
        remote.lock('/Test locking/myDoc.odt')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.touch(user1_file_path))
        remote.unlock('/Test locking/myDoc.odt')
        self.wait_sync(wait_for_async=True)

        # Check readonly flag is set for a document locked by another user
        self.remote_document_client_2.lock('/Test locking/myDoc.odt')
        self.wait_sync(wait_for_async=True)
        self.assertFalse(self.touch(user1_file_path))

        # Check readonly flag is unset for a document unlocked by another user
        self.remote_document_client_2.unlock('/Test locking/myDoc.odt')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.touch(user1_file_path))

    def test_local_readonly_modify(self):
        self.local_root_client_1.make_folder('/', 'Test')
        self.local_root_client_1.make_file('/Test', 'Test.txt', 'Some content')
        self.wait_sync()
        self.engine_1.stop()
        self.local_root_client_1.update_content('/Test/Test.txt', 'Another content')
        self.engine_1.start()
        self.wait_sync()
        self.assertEqual(len(self.engine_1.get_dao().get_errors()), 0)

