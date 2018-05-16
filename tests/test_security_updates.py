# coding: utf-8
import sys
import time

import pytest

from .common import OS_STAT_MTIME_RESOLUTION, TEST_WORKSPACE_PATH
from .common_unit_test import UnitTestCase


class TestSecurityUpdates(UnitTestCase):

    @pytest.mark.random(
        'NXDRIVE-821', condition=(sys.platform == 'darwin'), mode='BYPASS')
    def test_synchronize_denying_read_access(self):
        """Test that denying Read access server side is impacted client side

        Use cases:
          - Deny Read access on a regular folder
              => Folder should be locally deleted
          - Grant Read access back
              => Folder should be locally re-created
          - Deny Read access on a synchronization root
              => Synchronization root should be locally deleted
          - Grant Read access back
              => Synchronization root should be locally re-created

        See TestIntegrationRemoteDeletion.test_synchronize_remote_deletion
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

        # Remove Read permission for test user on a regular folder
        # then synchronize
        self._set_read_permission(self.user_1,
                                  TEST_WORKSPACE_PATH + '/Test folder',
                                  False)
        self.wait_sync(wait_for_async=True)
        self.assertFalse(local.exists('/Test folder'))

        # Add Read permission back for test user then synchronize
        self._set_read_permission(self.user_1,
                                  TEST_WORKSPACE_PATH + '/Test folder',
                                  True)
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

        # Remove Read permission for test user on a sync root
        # then synchronize
        self._set_read_permission(self.user_1,
                                  TEST_WORKSPACE_PATH,
                                  False)
        self.wait_sync(wait_for_async=True)
        self.assertFalse(local.exists('/'))

        # Add Read permission back for test user then synchronize
        self._set_read_permission(self.user_1,
                                  TEST_WORKSPACE_PATH,
                                  True)
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/'))
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

    @pytest.mark.skip('NXDRIVE-170: WIP')
    def test_synchronize_denying_read_access_local_modification(self):
        # TO_REVIEW: Trash feature, delete it, might need to modify the behavior
        """Test denying Read access with concurrent local modification

        Use cases:
          - Deny Read access on a regular folder and make some
            local and remote changes concurrently.
              => Only locally modified content should be kept
                 and should be marked as 'unsynchronized',
                 other content should be deleted.
                 Remote changes should not be impacted client side.
                 Local changes should not be impacted server side.
          - Grant Read access back.
              => Remote documents should be merged with
                 locally modified content which should be unmarked
                 as 'unsynchronized' and therefore synchronized upstream.

        See TestIntegrationRemoteDeletion
                .test_synchronize_remote_deletion_local_modification
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
        remote = self.remote_document_client_1
        root_remote = self.root_remote_client

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

        # Remove Read permission for test user on a regular folder
        # and make some local and remote changes concurrently then synchronize
        test_folder_path = TEST_WORKSPACE_PATH + '/Test folder'
        self._set_read_permission(self.user_1,
                                  test_folder_path, False)
        # Local changes
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        # Create new file
        local.make_file('/Test folder', 'local.odt', 'New local content')
        # Create new folder with files
        local.make_folder('/Test folder', 'Local sub folder 2')
        local.make_file('/Test folder/Local sub folder 2',
                        'local sub file 2.txt', 'Other local content')
        # Update file
        local.update_content('/Test folder/joe.odt',
                             'Some locally updated content')
        # Remote changes
        # Create new file
        root_remote.make_file(test_folder_path, 'remote.odt',
                              'New remote content')
        # Create new folder with files
        root_remote.make_folder(test_folder_path, 'Remote sub folder 2')
        root_remote.make_file(test_folder_path + '/Remote sub folder 2',
                'remote sub file 2.txt', 'Other remote content')
        # Update file
        root_remote.update_content(test_folder_path + '/joe.odt',
                'Some remotely updated content')

        self.wait_sync(wait_for_async=True)
        # Only locally modified content should exist
        # and should be marked as 'unsynchronized', other content should
        # have been deleted.
        # Remote changes should not be impacted client side.
        # Local changes should not be impacted server side.
        # Local check
        self.assertTrue(local.exists('/Test folder'))
        self.assertEqual(len(local.get_children_info('/Test folder')), 3)
        self.assertTrue(local.exists('/Test folder/joe.odt'))
        self.assertEqual(local.get_content('/Test folder/joe.odt'),
                         'Some locally updated content')
        self.assertTrue(local.exists('/Test folder/local.odt'))
        self.assertTrue(local.exists('/Test folder/Local sub folder 2'))
        self.assertTrue(local.exists(
                    '/Test folder/Local sub folder 2/local sub file 2.txt'))

        self.assertFalse(local.exists('/Test folder/jack.odt'))
        self.assertFalse(local.exists('/Test folder/remote.odt'))
        self.assertFalse(local.exists('/Test folder/Sub folder 1'))
        self.assertFalse(local.exists(
                                '/Test folder/Sub folder 1/sub file 1.txt'))
        self.assertFalse(local.exists('/Test folder/Remote sub folder 1'))
        self.assertFalse(local.exists(
                    '/Test folder/Remote sub folder 1/remote sub file 1.txt'))
        # State check
        self._check_pair_state('/Test folder', 'unsynchronized')
        self._check_pair_state('/Test folder/joe.odt',
                               'unsynchronized')
        self._check_pair_state('/Test folder/local.odt',
                               'unsynchronized')
        self._check_pair_state('/Test folder/Local sub folder 2',
                               'unsynchronized')
        self._check_pair_state('/Test folder/Local sub folder 2/local sub file 2.txt',
                               'unsynchronized')
        # Remote check
        test_folder_uid = root_remote.get_info(test_folder_path).uid
        self.assertEqual(len(root_remote.get_children_info(
                                                        test_folder_uid)), 5)
        self.assertTrue(root_remote.exists(test_folder_path + '/joe.odt'))
        self.assertEqual(root_remote.get_content(
                                            test_folder_path + '/joe.odt'),
                                            'Some remotely updated content')
        self.assertTrue(root_remote.exists(test_folder_path + '/jack.odt'))
        self.assertTrue(root_remote.exists(test_folder_path + '/remote.odt'))
        self.assertTrue(root_remote.exists(test_folder_path + '/Sub folder 1'))
        self.assertTrue(root_remote.exists(
            test_folder_path + '/Sub folder 1/sub file 1.txt'))
        self.assertTrue(root_remote.exists(
            test_folder_path + '/Remote sub folder 2'))
        self.assertTrue(root_remote.exists(
            test_folder_path + '/Remote sub folder 2/remote sub file 2.txt'))

        self.assertFalse(root_remote.exists(test_folder_path + '/local.odt'))
        self.assertFalse(root_remote.exists(
            test_folder_path + '/Local sub folder 2'))
        self.assertFalse(root_remote.exists(
            test_folder_path + '/Local sub folder 1/local sub file 2.txt'))

        # Add Read permission back for test user then synchronize
        self._set_read_permission(self.user_1,
                                  TEST_WORKSPACE_PATH + '/Test folder',
                                  True)
        self.wait_sync(wait_for_async=True)
        # Remote documents should be merged with locally modified content
        # which should be unmarked as 'unsynchronized' and therefore
        # synchronized upstream.
        # Local check
        self.assertTrue(local.exists('/Test folder'))
        children_info = local.get_children_info('/Test folder')
        self.assertEqual(len(children_info), 8)
        for info in children_info:
            if info.name == 'joe.odt':
                remote_version = info
            elif info.name.startswith('joe (') and info.name.endswith(').odt'):
                local_version = info
        self.assertTrue(remote_version is not None)
        self.assertTrue(local_version is not None)
        self.assertTrue(local.exists(remote_version.path))
        self.assertEqual(local.get_content(remote_version.path),
                         'Some remotely updated content')
        self.assertTrue(local.exists(local_version.path))
        self.assertEqual(local.get_content(local_version.path),
                         'Some locally updated content')
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertTrue(local.exists('/Test folder/local.odt'))
        self.assertTrue(local.exists('/Test folder/remote.odt'))
        self.assertTrue(local.exists('/Test folder/Sub folder 1'))
        self.assertTrue(local.exists(
                                '/Test folder/Sub folder 1/sub file 1.txt'))
        self.assertTrue(local.exists('/Test folder/Local sub folder 2'))
        self.assertTrue(local.exists(
                    '/Test folder/Local sub folder 2/local sub file 2.txt'))
        self.assertTrue(local.exists('/Test folder/Remote sub folder 2'))
        self.assertTrue(local.exists(
                    '/Test folder/Remote sub folder 2/remote sub file 2.txt'))
        # State check
        self._check_pair_state('/Test folder', 'synchronized')
        self._check_pair_state('/Test folder/joe.odt',
                               'synchronized')
        self._check_pair_state('/Test folder/local.odt',
                               'synchronized')
        self._check_pair_state('/Test folder/Local sub folder 2',
                               'synchronized')
        self._check_pair_state('/Test folder/Local sub folder 2/local sub file 2.txt',
                        'synchronized')
        # Remote check
        self.assertTrue(remote.exists('/Test folder'))
        children_info = remote.get_children_info(test_folder_uid)
        self.assertEqual(len(children_info), 8)
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
                         'Some remotely updated content')
        local_version_ref_length = (len(local_version.path)
                                     - len(TEST_WORKSPACE_PATH))
        local_version_ref = local_version.path[-local_version_ref_length:]
        self.assertTrue(remote.exists(local_version_ref))
        self.assertEqual(remote.get_content(local_version_ref),
                         'Some locally updated content')
        self.assertTrue(remote.exists('/Test folder/jack.odt'))
        self.assertTrue(remote.exists('/Test folder/local.odt'))
        self.assertTrue(remote.exists('/Test folder/remote.odt'))
        self.assertTrue(remote.exists('/Test folder/Sub folder 1'))
        self.assertTrue(remote.exists(
                                '/Test folder/Sub folder 1/sub file 1.txt'))
        self.assertTrue(remote.exists('/Test folder/Local sub folder 2'))
        self.assertTrue(remote.exists(
                    '/Test folder/Local sub folder 2/local sub file 2.txt'))
        self.assertTrue(remote.exists('/Test folder/Remote sub folder 2'))
        self.assertTrue(remote.exists(
                    '/Test folder/Remote sub folder 2/remote sub file 2.txt'))

    def _set_read_permission(self, user, doc_path, grant):
        op_input = "doc:" + doc_path
        if grant:
            self.root_remote_client.execute("Document.SetACE",
                op_input=op_input,
                user=user,
                permission="Read",
                grant="true")
        else:
            self.root_remote_client.block_inheritance(doc_path)

    def _check_pair_state(self, local_path, pair_state):
        local_path = '/' + self.workspace_title + local_path
        doc_pair = self.engine_1.get_dao().get_state_from_local(local_path)
        self.assertEqual(doc_pair.pair_state, pair_state)
