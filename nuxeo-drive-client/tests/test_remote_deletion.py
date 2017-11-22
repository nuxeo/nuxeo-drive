# coding: utf-8
import os
import sys
import time
from shutil import copyfile
from unittest import skip

from mock import patch

from nxdrive.engine.engine import Engine
from tests.common import DOC_NAME_MAX_LENGTH, OS_STAT_MTIME_RESOLUTION, \
    TEST_WORKSPACE_PATH
from tests.common_unit_test import UnitTestCase


suspend_client_ = Engine.suspend


class TestRemoteDeletion(UnitTestCase):

    def tearDown(self):
        self.engine_1.suspend_client = suspend_client_
        super(TestRemoteDeletion, self).tearDown()

    def test_synchronize_remote_deletion(self):
        """Test that deleting remote documents is impacted client side

        Use cases:
          - Remotely delete a regular folder
              => Folder should be locally deleted
          - Remotely restore folder from the trash
              => Folder should be locally re-created
          - Remotely delete a synchronization root
              => Synchronization root should be locally deleted
          - Remotely restore synchronization root from the trash
              => Synchronization root should be locally re-created

        See TestIntegrationSecurityUpdates.test_synchronize_denying_read_access
        as the same uses cases are tested
        """
        # Bind the server and root workspace
        self.engine_1.start()
        # Get local and remote clients
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test folder')
        remote.make_file('/Test folder', 'joe.txt', 'Some content')

        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

        # Delete remote folder then synchronize
        remote.delete('/Test folder')
        self.wait_sync(wait_for_async=True)
        self.assertFalse(local.exists('/Test folder'))

        # Restore folder from trash then synchronize
        # Undeleting each item as following 'undelete' transition
        # doesn't act recursively, should use TrashService instead
        # through a dedicated operation
        remote.undelete('/Test folder')
        remote.undelete('/Test folder/joe.txt')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

        # Delete sync root then synchronize
        remote.delete('/')
        self.wait_sync(wait_for_async=True)
        self.assertFalse(local.exists('/'))

        # Restore sync root from trash then synchronize
        remote.undelete('/')
        remote.undelete('/Test folder')
        remote.undelete('/Test folder/joe.txt')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/'))
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

    def _remote_deletion_while_upload(self):

        # Add delay when upload and download
        def suspend_check(reason):
            time.sleep(1)
            Engine.suspend_client(self.engine_1, reason)

        self.engine_1.suspend_client = suspend_check
        # Bind the server and root workspace
        self.engine_1.invalidate_client_cache()
        self.engine_1.start()

        # Get local and remote clients
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test folder')
        self.wait_sync(wait_for_async=True)

        # Create a document by streaming a binary file
        file_path = os.path.join(local.abspath('/Test folder'), 'testFile.pdf')
        copyfile(self.location + '/resources/testFile.pdf', file_path)
        file_path = os.path.join(local.abspath('/Test folder'), 'testFile2.pdf')
        copyfile(self.location + '/resources/testFile.pdf', file_path)

        # Delete remote folder then synchronize
        remote.delete('/Test folder')
        self.wait_sync(wait_for_async=True, timeout=120)
        self.assertFalse(local.exists('/Test folder'))

    def test_synchronize_remote_deletion_while_upload(self):
        if sys.platform != 'win32':
            with patch('nxdrive.client.base_automation_client.os.fstatvfs') as mock_os:
                from mock import Mock
                mock_os.return_value = Mock()
                mock_os.return_value.f_bsize = 4096
                self._remote_deletion_while_upload()
        else:
            self._remote_deletion_while_upload()

    def _remote_deletion_while_download_file(self):
        global has_delete
        has_delete = False

        # Add delay when upload and download
        def suspend_check(reason):
            global has_delete
            time.sleep(1)
            Engine.suspend_client(self.engine_1, reason)
            if not has_delete:
                # Delete remote file while downloading
                try:
                    remote.delete('/Test folder/testFile.pdf')
                    has_delete = True
                except:
                    pass

        self.engine_1.suspend_client = suspend_check
        # Bind the server and root workspace
        self.engine_1.invalidate_client_cache()
        self.engine_1.start()
        # Get local and remote clients
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test folder')
        with open(self.location + '/resources/testFile.pdf', 'r') as content_file:
            content = content_file.read()
        remote.make_file('/Test folder', 'testFile.pdf', content)

        self.wait_sync(wait_for_async=True)
        self.assertFalse(local.exists('/Test folder/testFile.pdf'))

    def test_synchronize_remote_deletion_while_download_file(self):
        if sys.platform != 'win32':
            with patch('os.path.isdir', return_value=False) as mock_os:
                from mock import Mock
                mock_os.return_value = Mock()
                mock_os.return_value.f_bsize = 4096
                self._remote_deletion_while_download_file()
        else:
            self._remote_deletion_while_download_file()

    @skip('Behavior has changed with trash feature - remove this test ?')
    def test_synchronize_remote_deletion_local_modification(self):
        """Test remote deletion with concurrent local modification

        Use cases:
          - Remotely delete a regular folder and make some
            local changes concurrently.
              => Only locally modified content should be kept
                 and should be marked as 'unsynchronized',
                 other content should be deleted.
          - Remotely restore folder from the trash.
              => Remote documents should be merged with
                 locally modified content which should be unmarked
                 as 'unsynchronized'.
          - Remotely delete a file and locally update its content concurrently.
              => File should be kept locally and be marked as 'unsynchronized'.
          - Remotely restore file from the trash.
              => Remote file should be merged with locally modified file with
                 a conflict detection and both files should be marked
                 as 'synchronized'.
          - Remotely delete a file and locally rename it concurrently.
              => File should be kept locally and be marked as 'synchronized'.
          - Remotely restore file from the trash.
              => Remote file should be merged with locally renamed file and
                 both files should be marked as 'synchronized'.

        See TestIntegrationSecurityUpdates
                .test_synchronize_denying_read_access_local_modification
        as the same uses cases are tested.

        Note that we use the .odt extension for test files to make sure
        that they are created as File and not Note documents on the server
        when synchronized upstream, as the current implementation of
        RemoteDocumentClient is File oriented.
        """
        # Bind the server and root workspace
        self.engine_1.start()
        # Get local and remote clients
        local = self.local_client_1
        remote = self.remote_document_client_2

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test folder')
        remote.make_file('/Test folder', 'joe.odt', 'Some content')
        remote.make_file('/Test folder', 'jack.odt', 'Some content')
        remote.make_folder('/Test folder', 'Sub folder 1')
        remote.make_file('/Test folder/Sub folder 1', 'sub file 1.txt',
                         'Content')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.odt'))
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertTrue(local.exists('/Test folder/Sub folder 1'))
        self.assertTrue(local.exists(
                                '/Test folder/Sub folder 1/sub file 1.txt'))

        # Delete remote folder and make some local changes
        # concurrently then synchronize
        remote.delete('/Test folder')
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        # Create new file
        local.make_file('/Test folder', 'new.odt', "New content")
        # Create new folder with files
        local.make_folder('/Test folder', 'Sub folder 2')
        local.make_file('/Test folder/Sub folder 2', 'sub file 2.txt',
                        'Other content')
        # Update file
        local.update_content('/Test folder/joe.odt', 'Some updated content')
        self.wait_sync(wait_for_async=True)
        # Only locally modified content should exist
        # and should be marked as 'unsynchronized', other content should
        # have been deleted
        # Local check
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.odt'))
        self.assertEqual(local.get_content('/Test folder/joe.odt'),
                         'Some updated content')
        self.assertTrue(local.exists('/Test folder/new.odt'))
        self.assertTrue(local.exists('/Test folder/Sub folder 2'))
        self.assertTrue(local.exists(
                                '/Test folder/Sub folder 2/sub file 2.txt'))

        self.assertFalse(local.exists('/Test folder/jack.odt'))
        self.assertFalse(local.exists('/Test folder/Sub folder 1'))
        self.assertFalse(local.exists(
                                '/Test folder/Sub folder 1/sub file 1.txt'))
        # State check
        self._check_pair_state('/Test folder', 'unsynchronized')
        self._check_pair_state('/Test folder/joe.odt',
                               'unsynchronized')
        self._check_pair_state('/Test folder/new.odt',
                               'unsynchronized')
        self._check_pair_state('/Test folder/Sub folder 2',
                               'unsynchronized')
        self._check_pair_state('/Test folder/Sub folder 2/sub file 2.txt',
                               'unsynchronized')
        # Remote check
        self.assertFalse(remote.exists('/Test folder'))

        # Restore remote folder and its children from trash then synchronize
        remote.undelete('/Test folder')
        remote.undelete('/Test folder/joe.odt')
        remote.undelete('/Test folder/jack.odt')
        remote.undelete('/Test folder/Sub folder 1')
        remote.undelete('/Test folder/Sub folder 1/sub file 1.txt')
        self.wait_sync(wait_for_async=True)
        # Remotely restored documents should be merged with
        # locally modified content which should be unmarked
        # as 'unsynchronized' and therefore synchronized upstream
        # Local check
        self.assertTrue(local.exists('/Test folder'))
        children_info = local.get_children_info('/Test folder')
        self.assertEqual(len(children_info), 6)
        for info in children_info:
            if info.name == 'joe.odt':
                remote_version = info
            elif info.name.startswith('joe (') and info.name.endswith(').odt'):
                local_version = info
        self.assertTrue(remote_version is not None)
        self.assertTrue(local_version is not None)
        self.assertTrue(local.exists(remote_version.path))
        self.assertEqual(local.get_content(remote_version.path),
                          'Some content')
        self.assertTrue(local.exists(local_version.path))
        self.assertEqual(local.get_content(local_version.path),
                          'Some updated content')
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertTrue(local.exists('/Test folder/new.odt'))
        self.assertTrue(local.exists('/Test folder/Sub folder 1'))
        self.assertTrue(local.exists(
                                '/Test folder/Sub folder 1/sub file 1.txt'))
        self.assertTrue(local.exists('/Test folder/Sub folder 2'))
        self.assertTrue(local.exists(
                                '/Test folder/Sub folder 2/sub file 2.txt'))
        # State check
        self._check_pair_state('/Test folder', 'synchronized')
        self._check_pair_state('/Test folder/joe.odt',
                               'synchronized')
        self._check_pair_state('/Test folder/new.odt',
                               'synchronized')
        self._check_pair_state('/Test folder/Sub folder 2',
                               'synchronized')
        self._check_pair_state('/Test folder/Sub folder 2/sub file 2.txt',
                               'synchronized')
        # Remote check
        self.assertTrue(remote.exists('/Test folder'))
        test_folder_uid = remote.get_info('/Test folder').uid
        children_info = remote.get_children_info(test_folder_uid)
        self.assertEqual(len(children_info), 6)
        for info in children_info:
            if info.name == 'joe.odt':
                remote_version = info
            elif info.name.startswith('joe (') and info.name.endswith(').odt'):
                local_version = info
        self.assertTrue(remote_version is not None)
        self.assertTrue(local_version is not None)
        remote_version_ref_length = (len(remote_version.path)
                                     - len(TEST_WORKSPACE_PATH))
        remote_version_ref = remote_version.path[-remote_version_ref_length:]
        self.assertTrue(remote.exists(remote_version_ref))
        self.assertEqual(remote.get_content(remote_version_ref),
                         'Some content')
        local_version_ref_length = (len(local_version.path)
                                     - len(TEST_WORKSPACE_PATH))
        local_version_ref = local_version.path[-local_version_ref_length:]
        self.assertTrue(remote.exists(local_version_ref))
        self.assertEqual(remote.get_content(local_version_ref),
                         'Some updated content')
        self.assertTrue(remote.exists('/Test folder/jack.odt'))
        self.assertTrue(remote.exists('/Test folder/new.odt'))
        self.assertTrue(remote.exists('/Test folder/Sub folder 1'))
        self.assertTrue(remote.exists(
                                '/Test folder/Sub folder 1/sub file 1.txt'))
        self.assertTrue(remote.exists('/Test folder/Sub folder 2'))
        self.assertTrue(remote.exists(
                    '/Test folder/Sub folder 2/sub file 2.txt'))

        # Delete remote file and update its local content
        # concurrently then synchronize
        remote.delete('/Test folder/jack.odt')
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content('/Test folder/jack.odt', 'Some updated content')
        self.wait_sync(wait_for_async=True)
        # File should be kept locally and be marked as 'unsynchronized'.
        # Local check
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertEqual(local.get_content('/Test folder/jack.odt'),
                         'Some updated content')
        # Remote check
        self.assertFalse(remote.exists('/Test folder/jack.odt'))
        # State check
        self._check_pair_state('/Test folder', 'synchronized')
        self._check_pair_state('/Test folder/jack.odt', 'unsynchronized')

        # Remotely restore file from the trash then synchronize
        remote.undelete('/Test folder/jack.odt')
        self.wait_sync(wait_for_async=True)
        # Remotely restored file should be merged with locally modified file
        # with a conflict detection and both files should be marked
        # as 'synchronized'
        # Local check
        children_info = local.get_children_info('/Test folder')
        for info in children_info:
            if info.name == 'jack.odt':
                remote_version = info
            elif (info.name.startswith('jack (')
                  and info.name.endswith(').odt')):
                local_version = info
        self.assertTrue(remote_version is not None)
        self.assertTrue(local_version is not None)
        self.assertTrue(local.exists(remote_version.path))
        self.assertEqual(local.get_content(remote_version.path),
                         'Some content')
        self.assertTrue(local.exists(local_version.path))
        self.assertEqual(local.get_content(local_version.path),
                         'Some updated content')
        # Remote check
        self.assertTrue(remote.exists(remote_version.path))
        self.assertEqual(remote.get_content(remote_version.path),
                         'Some content')
        local_version_path = self._truncate_remote_path(local_version.path)
        self.assertTrue(remote.exists(local_version_path))
        self.assertEqual(remote.get_content(local_version_path),
                         'Some updated content')
        # State check
        self._check_pair_state(remote_version.path, 'synchronized')
        self._check_pair_state(local_version.path, 'synchronized')

        # Delete remote file and rename it locally
        # concurrently then synchronize
        remote.delete('/Test folder/jack.odt')
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.rename('/Test folder/jack.odt', 'jack renamed.odt')
        self.wait_sync(wait_for_async=True)
        # File should be kept locally and be marked as 'synchronized'
        # Local check
        self.assertFalse(local.exists('/Test folder/jack.odt'))
        self.assertTrue(local.exists('/Test folder/jack renamed.odt'))
        self.assertEqual(local.get_content('/Test folder/jack renamed.odt'),
                         'Some content')
        # Remote check
        self.assertFalse(remote.exists('/Test folder/jack.odt'))
        # State check
        self._check_pair_state('/Test folder', 'synchronized')
        self._check_pair_state('/Test folder/jack renamed.odt', 'synchronized')

        # Remotely restore file from the trash then synchronize
        remote.undelete('/Test folder/jack.odt')
        self.wait_sync(wait_for_async=True)
        # Remotely restored file should be merged with locally renamed file
        # and both files should be marked as 'synchronized'
        # Local check
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertEqual(local.get_content('/Test folder/jack.odt'),
                         'Some content')
        self.assertTrue(local.exists('/Test folder/jack renamed.odt'))
        self.assertEqual(local.get_content('/Test folder/jack renamed.odt'),
                         'Some content')
        # Remote check
        self.assertTrue(remote.exists('/Test folder/jack.odt'))
        self.assertEqual(remote.get_content('/Test folder/jack.odt'),
                         'Some content')
        self.assertTrue(remote.exists('/Test folder/jack renamed.odt'))
        self.assertEqual(remote.get_content('/Test folder/jack renamed.odt'),
                         'Some content')
        # State check
        self._check_pair_state('/Test folder/jack.odt', 'synchronized')
        self._check_pair_state('/Test folder/jack renamed.odt', 'synchronized')

    def test_synchronize_remote_deletion_with_close_name(self):
        self.engine_1.start()
        local = self.local_client_1
        remote = self.remote_document_client_1
        remote.make_folder('/', "Folder 1")
        remote.make_folder('/', "Folder 1b")
        remote.make_folder('/', "Folder 1c")
        self.wait_sync()
        self.assertTrue(local.exists('/Folder 1'))
        self.assertTrue(local.exists('/Folder 1b'))
        self.assertTrue(local.exists('/Folder 1c'))
        remote.delete('/Folder 1')
        remote.delete('/Folder 1b')
        remote.delete('/Folder 1c')
        self.wait_sync()
        self.assertFalse(local.exists('/Folder 1'))
        self.assertFalse(local.exists('/Folder 1b'))
        self.assertFalse(local.exists('/Folder 1c'))

    def test_synchronize_local_folder_lost_permission(self):
        """Test local folder rename followed by remote deletion"""
        # Bind the server and root workspace

        # Get local and remote clients
        self.engine_2.start()
        local = self.local_client_2
        remote = self.remote_document_client_2

        # Create a folder with a child file in the remote root workspace
        # then synchronize
        test_folder_uid = remote.make_folder('/', 'Test folder')
        remote.make_file(test_folder_uid, 'joe.odt', 'Some content')

        self.wait_sync(wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.odt'))
        op_input = "doc:" + self.workspace
        self.root_remote_client.execute("Document.RemoveACL", op_input=op_input, acl="local")
        # Disable for now as get_acls seems to cause an issue
        self.wait_sync(wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True)
        self.assertFalse(local.exists('/Test folder'))

    def test_synchronize_local_folder_rename_remote_deletion(self):
        """Test local folder rename followed by remote deletion"""
        # Bind the server and root workspace

        # Get local and remote clients
        self.engine_1.start()
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Create a folder with a child file in the remote root workspace
        # then synchronize
        test_folder_uid = remote.make_folder('/', 'Test folder')
        remote.make_file(test_folder_uid, 'joe.odt', 'Some content')

        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.odt'))

        # Locally rename the folder then synchronize
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.rename('/Test folder', 'Test folder renamed')

        self.wait_sync()
        self.assertFalse(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder renamed'))
        self.assertEqual(remote.get_info(test_folder_uid).name,
                         'Test folder renamed')

        # Delete remote folder then synchronize
        remote.delete('/Test folder')

        self.wait_sync(wait_for_async=True)
        self.assertFalse(remote.exists('/Test folder renamed'))
        self.assertFalse(local.exists('/Test folder renamed'))

    def _check_pair_state(self, session, local_path, pair_state):
        local_path = '/' + self.workspace_title + local_path
        doc_pair = self.engine_1.get_dao().get_state_from_local(local_path)
        self.assertEqual(doc_pair.pair_state, pair_state)

    def _truncate_remote_path(self, path):
        doc_name = path.rsplit('/', 1)[1]
        if len(doc_name) > DOC_NAME_MAX_LENGTH:
            path_length = len(path) - len(doc_name) + DOC_NAME_MAX_LENGTH
            return path[:path_length]
        else:
            return path
