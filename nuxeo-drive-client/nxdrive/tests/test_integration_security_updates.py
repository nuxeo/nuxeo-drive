import os
import time

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nxdrive.model import LastKnownState


class TestIntegrationSecurityUpdates(IntegrationTestCase):

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
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Get local and remote clients
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder('/', 'Test folder')
        remote.make_file('/Test folder', 'joe.txt', 'Some content')

        syn = ctl.synchronizer
        self._synchronize(syn)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

        # Remove Read permission for test user on a regular folder
        # then synchronize
        self._set_read_permission("nuxeoDriveTestUser_user_1",
                                  self.TEST_WORKSPACE_PATH + '/Test folder',
                                  False)
        self._synchronize(syn)
        self.assertFalse(local.exists('/Test folder'))

        # Add Read permission back for test user then synchronize
        self._set_read_permission("nuxeoDriveTestUser_user_1",
                                  self.TEST_WORKSPACE_PATH + '/Test folder',
                                  True)
        self._synchronize(syn)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

        # Remove Read permission for test user on a sync root
        # then synchronize
        self._set_read_permission("nuxeoDriveTestUser_user_1",
                                  self.TEST_WORKSPACE_PATH,
                                  False)
        self._synchronize(syn)
        self.assertFalse(local.exists('/'))

        # Add Read permission back for test user then synchronize
        self._set_read_permission("nuxeoDriveTestUser_user_1",
                                  self.TEST_WORKSPACE_PATH,
                                  True)
        self._synchronize(syn)
        self.assertTrue(local.exists('/'))
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

    def test_synchronize_denying_read_access_local_modification(self):
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
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Get local and remote clients
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
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

        syn = ctl.synchronizer
        self._synchronize(syn)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.odt'))
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertTrue(local.exists('/Test folder/Sub folder 1'))
        self.assertTrue(local.exists(
                                '/Test folder/Sub folder 1/sub file 1.txt'))

        # Remove Read permission for test user on a regular folder
        # and make some local and remote changes concurrently then synchronize
        test_folder_path = self.TEST_WORKSPACE_PATH + '/Test folder'
        self._set_read_permission("nuxeoDriveTestUser_user_1",
                                  test_folder_path, False)
        # Local changes
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
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

        self._synchronize(syn)
        # Only locally modified content should exist
        # and should be marked as 'unsynchronized', other content should
        # have been deleted.
        # Remote changes should not be impacted client side.
        # Local changes should not be impacted server side.
        # Local check
        self.assertTrue(local.exists('/Test folder'))
        self.assertEquals(len(local.get_children_info('/Test folder')), 3)
        self.assertTrue(local.exists('/Test folder/joe.odt'))
        self.assertEquals(local.get_content('/Test folder/joe.odt'),
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
        session = ctl.get_session()
        self._check_pair_state(session, '/Test folder', 'unsynchronized')
        self._check_pair_state(session, '/Test folder/joe.odt',
                               'unsynchronized')
        self._check_pair_state(session, '/Test folder/local.odt',
                               'unsynchronized')
        self._check_pair_state(session, '/Test folder/Local sub folder 2',
                               'unsynchronized')
        self._check_pair_state(session,
                        '/Test folder/Local sub folder 2/local sub file 2.txt',
                        'unsynchronized')
        # Remote check
        test_folder_uid = root_remote.get_info(test_folder_path).uid
        self.assertEquals(len(root_remote.get_children_info(
                                                        test_folder_uid)), 5)
        self.assertTrue(root_remote.exists(test_folder_path + '/joe.odt'))
        self.assertEquals(root_remote.get_content(
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
        self._set_read_permission("nuxeoDriveTestUser_user_1",
                                  self.TEST_WORKSPACE_PATH + '/Test folder',
                                  True)
        self._synchronize(syn)
        # Remote documents should be merged with locally modified content
        # which should be unmarked as 'unsynchronized' and therefore
        # synchronized upstream.
        # Local check
        self.assertTrue(local.exists('/Test folder'))
        children_info = local.get_children_info('/Test folder')
        self.assertEquals(len(children_info), 8)
        for info in children_info:
            if info.name == 'joe.odt':
                remote_version = info
            elif info.name.startswith('joe (') and info.name.endswith(').odt'):
                local_version = info
        self.assertTrue(remote_version is not None)
        self.assertTrue(local_version is not None)
        self.assertTrue(local.exists(remote_version.path))
        self.assertEquals(local.get_content(remote_version.path),
                          'Some remotely updated content')
        self.assertTrue(local.exists(local_version.path))
        self.assertEquals(local.get_content(local_version.path),
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
        self._check_pair_state(session, '/Test folder', 'synchronized')
        self._check_pair_state(session, '/Test folder/joe.odt',
                               'synchronized')
        self._check_pair_state(session, '/Test folder/local.odt',
                               'synchronized')
        self._check_pair_state(session, '/Test folder/Local sub folder 2',
                               'synchronized')
        self._check_pair_state(session,
                        '/Test folder/Local sub folder 2/local sub file 2.txt',
                        'synchronized')
        # Remote check
        self.assertTrue(remote.exists('/Test folder'))
        children_info = remote.get_children_info(test_folder_uid)
        self.assertEquals(len(children_info), 8)
        for info in children_info:
            if info.name == 'joe.odt':
                remote_version = info
            elif info.name.startswith('joe (') and info.name.endswith(').odt'):
                local_version = info
        self.assertTrue(remote_version is not None)
        self.assertTrue(local_version is not None)
        remote_version_ref_length = (len(remote_version.path)
                                     - len(self.TEST_WORKSPACE_PATH))
        remote_version_ref = remote_version.path[-remote_version_ref_length:]
        self.assertTrue(remote.exists(remote_version_ref))
        self.assertEquals(remote.get_content(remote_version_ref),
                          'Some remotely updated content')
        local_version_ref_length = (len(local_version.path)
                                     - len(self.TEST_WORKSPACE_PATH))
        local_version_ref = local_version.path[-local_version_ref_length:]
        self.assertTrue(remote.exists(local_version_ref))
        self.assertEquals(remote.get_content(local_version_ref),
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

    def _synchronize(self, synchronizer):
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        synchronizer.loop(delay=0.1, max_loops=2)

    def _set_read_permission(self, user, doc_path, grant):
        op_input = "doc:" + doc_path
        grant = "true" if grant else "false"
        self.root_remote_client.execute("Document.SetACE",
            op_input=op_input,
            user=user,
            permission="ReadWrite",
            grant=grant)
        self.root_remote_client.execute("Document.SetACE",
            op_input=op_input,
            user=user,
            permission="Read",
            grant=grant)

    def _check_pair_state(self, session, local_path, pair_state):
        local_path = '/' + self.workspace_title + local_path
        doc_pair = session.query(LastKnownState).filter_by(
            local_path=local_path).one()
        self.assertEquals(doc_pair.pair_state, pair_state)
