import os
import time

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nxdrive.model import LastKnownState


class TestIntegrationRemoteDeletion(IntegrationTestCase):

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

        # Delete remote folder then synchronize
        remote.delete('/Test folder')
        self._synchronize(syn)
        self.assertFalse(local.exists('/Test folder'))

        # Restore folder from trash then synchronize
        # Undeleting each item as following 'undelete' transition
        # doesn't act recursively, should use TrashService instead
        # through a dedicated operation
        remote.undelete('/Test folder')
        remote.undelete('/Test folder/joe.txt')
        self._synchronize(syn)
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

        # Delete sync root then synchronize
        remote.delete('/')
        self._synchronize(syn)
        self.assertFalse(local.exists('/'))

        # Restore sync root from trash then synchronize
        remote.undelete('/')
        remote.undelete('/Test folder')
        remote.undelete('/Test folder/joe.txt')
        self._synchronize(syn)
        self.assertTrue(local.exists('/'))
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.txt'))

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

        # Delete remote folder and make some local changes
        # concurrently then synchronize
        remote.delete('/Test folder')
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        # Create new file
        local.make_file('/Test folder', 'new.odt', "New content")
        # Create new folder with files
        local.make_folder('/Test folder', 'Sub folder 2')
        local.make_file('/Test folder/Sub folder 2', 'sub file 2.txt',
                        'Other content')
        # Update file
        local.update_content('/Test folder/joe.odt', 'Some updated content')
        self._synchronize(syn)
        # Only locally modified content should exist
        # and should be marked as 'unsynchronized', other content should
        # have been deleted
        # Local check
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder/joe.odt'))
        self.assertEquals(local.get_content('/Test folder/joe.odt'),
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
        session = ctl.get_session()
        self._check_pair_state(session, '/Test folder', 'unsynchronized')
        self._check_pair_state(session, '/Test folder/joe.odt',
                               'unsynchronized')
        self._check_pair_state(session, '/Test folder/new.odt',
                               'unsynchronized')
        self._check_pair_state(session, '/Test folder/Sub folder 2',
                               'unsynchronized')
        self._check_pair_state(session,
                               '/Test folder/Sub folder 2/sub file 2.txt',
                               'unsynchronized')
        # Remote check
        self.assertFalse(remote.exists('/Test folder'))

        # Restore remote folder and its children from trash then synchronize
        remote.undelete('/Test folder')
        remote.undelete('/Test folder/joe.odt')
        remote.undelete('/Test folder/jack.odt')
        remote.undelete('/Test folder/Sub folder 1')
        remote.undelete('/Test folder/Sub folder 1/sub file 1.txt')
        self._synchronize(syn)
        # Remotely restored documents should be merged with
        # locally modified content which should be unmarked
        # as 'unsynchronized' and therefore synchronized upstream
        # Local check
        self.assertTrue(local.exists('/Test folder'))
        children_info = local.get_children_info('/Test folder')
        self.assertEquals(len(children_info), 6)
        for info in children_info:
            if info.name == 'joe.odt':
                remote_version = info
            elif info.name.startswith('joe (') and info.name.endswith(').odt'):
                local_version = info
        self.assertTrue(remote_version is not None)
        self.assertTrue(local_version is not None)
        self.assertTrue(local.exists(remote_version.path))
        self.assertEquals(local.get_content(remote_version.path),
                          'Some content')
        self.assertTrue(local.exists(local_version.path))
        self.assertEquals(local.get_content(local_version.path),
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
        self._check_pair_state(session, '/Test folder', 'synchronized')
        self._check_pair_state(session, '/Test folder/joe.odt',
                               'synchronized')
        self._check_pair_state(session, '/Test folder/new.odt',
                               'synchronized')
        self._check_pair_state(session, '/Test folder/Sub folder 2',
                               'synchronized')
        self._check_pair_state(session,
                               '/Test folder/Sub folder 2/sub file 2.txt',
                               'synchronized')
        # Remote check
        self.assertTrue(remote.exists('/Test folder'))
        test_folder_uid = remote.get_info('/Test folder').uid
        children_info = remote.get_children_info(test_folder_uid)
        self.assertEquals(len(children_info), 6)
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
                          'Some content')
        local_version_ref_length = (len(local_version.path)
                                     - len(self.TEST_WORKSPACE_PATH))
        local_version_ref = local_version.path[-local_version_ref_length:]
        self.assertTrue(remote.exists(local_version_ref))
        self.assertEquals(remote.get_content(local_version_ref),
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
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/Test folder/jack.odt', 'Some updated content')
        self._synchronize(syn)
        # File should be kept locally and be marked as 'unsynchronized'.
        # Local check
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertEquals(local.get_content('/Test folder/jack.odt'),
                          'Some updated content')
        # Remote check
        self.assertFalse(remote.exists('/Test folder/jack.odt'))
        # State check
        session = ctl.get_session()
        self._check_pair_state(session, '/Test folder', 'synchronized')
        self._check_pair_state(session, '/Test folder/jack.odt',
                               'unsynchronized')

        # Remotely restore file from the trash then synchronize
        remote.undelete('/Test folder/jack.odt')
        self._synchronize(syn)
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
        self.assertEquals(local.get_content(remote_version.path),
                          'Some content')
        self.assertTrue(local.exists(local_version.path))
        self.assertEquals(local.get_content(local_version.path),
                          'Some updated content')
        # Remote check
        self.assertTrue(remote.exists(remote_version.path))
        self.assertEquals(remote.get_content(remote_version.path),
                          'Some content')
        local_version_path = self._truncate_remote_path(local_version.path)
        self.assertTrue(remote.exists(local_version_path))
        self.assertEquals(remote.get_content(local_version_path),
                          'Some updated content')
        # State check
        self._check_pair_state(session, remote_version.path,
                               'synchronized')
        self._check_pair_state(session, local_version.path,
                               'synchronized')

        # Delete remote file and rename it locally
        # concurrently then synchronize
        remote.delete('/Test folder/jack.odt')
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.rename('/Test folder/jack.odt', 'jack renamed.odt')
        self._synchronize(syn)
        # File should be kept locally and be marked as 'synchronized'
        # Local check
        self.assertFalse(local.exists('/Test folder/jack.odt'))
        self.assertTrue(local.exists('/Test folder/jack renamed.odt'))
        self.assertEquals(local.get_content('/Test folder/jack renamed.odt'),
                          'Some content')
        # Remote check
        self.assertFalse(remote.exists('/Test folder/jack.odt'))
        # State check
        session = ctl.get_session()
        self._check_pair_state(session, '/Test folder', 'synchronized')
        self._check_pair_state(session, '/Test folder/jack renamed.odt',
                               'synchronized')

        # Remotely restore file from the trash then synchronize
        remote.undelete('/Test folder/jack.odt')
        self._synchronize(syn)
        # Remotely restored file should be merged with locally renamed file
        # and both files should be marked as 'synchronized'
        # Local check
        self.assertTrue(local.exists('/Test folder/jack.odt'))
        self.assertEquals(local.get_content('/Test folder/jack.odt'),
                          'Some content')
        self.assertTrue(local.exists('/Test folder/jack renamed.odt'))
        self.assertEquals(local.get_content('/Test folder/jack renamed.odt'),
                          'Some content')
        # Remote check
        self.assertTrue(remote.exists('/Test folder/jack.odt'))
        self.assertEquals(remote.get_content('/Test folder/jack.odt'),
                          'Some content')
        self.assertTrue(remote.exists('/Test folder/jack renamed.odt'))
        self.assertEquals(remote.get_content('/Test folder/jack renamed.odt'),
                          'Some content')
        # State check
        self._check_pair_state(session, '/Test folder/jack.odt',
                               'synchronized')
        self._check_pair_state(session, '/Test folder/jack renamed.odt',
                               'synchronized')

    def _synchronize(self, synchronizer):
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        synchronizer.loop(delay=0.1, max_loops=2)

    def _check_pair_state(self, session, local_path, pair_state):
        local_path = '/' + self.workspace_title + local_path
        doc_pair = session.query(LastKnownState).filter_by(
            local_path=local_path).one()
        self.assertEquals(doc_pair.pair_state, pair_state)

    def _truncate_remote_path(self, path):
        doc_name = path.rsplit('/', 1)[1]
        if len(doc_name) > self.DOC_NAME_MAX_LENGTH:
            path_length = len(path) - len(doc_name) + self.DOC_NAME_MAX_LENGTH
            return path[:path_length]
        else:
            return path
