import os

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nose.plugins.skip import SkipTest


class TestIntegrationRemoteDeletion(IntegrationTestCase):

    def test_synchronize_remote_deletion(self):
        raise SkipTest("Skipped for the moment as it generates too much"
                       " error logs")

        """Test that deleting remote root document while uploading is handled

        See https://jira.nuxeo.com/browse/NXDRIVE-39
        See TestIntegrationSecurityUpdates.test_synchronize_denying_read_access
        as the same uses cases are tested
        """
        # Bind the server and root workspace
        ctl = self.controller_1
        # Override the behavior to force use of trash
        ctl.trash_modified_file = lambda: True
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Get local and remote clients
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_document_client_1

        syn = ctl.synchronizer
        self._synchronize(syn)
        # Create documents in the local root workspace
        # then synchronize
        local.make_folder('/', 'Test folder')
        i = 0
        while i < 400:
            local.make_file('/Test folder', ('joe%d.bin' % i), 'Some content')
            i += 1

        self._synchronize(syn)
        # All files should not be synchronized
        self.assertTrue(remote.exists('/Test folder'))
        self.assertTrue(remote.exists('/Test folder/joe0.bin'))
        self.assertFalse(remote.exists('/Test folder/joe399.bin'))

        # Delete remote folder then synchronize
        remote.delete('/Test folder')
        # Error counter should be in place
        self._synchronize(syn)
        self.assertFalse(local.exists('/Test folder'))

    def test_trash_modified_file(self):
        """Test deleting a remote folder while a file is locally created in it.

        See https://jira.nuxeo.com/browse/NXDRIVE-39
        See TestIntegrationRemoteDeletion.test_synchronize_remote_deletion_local_modification
        as the same use case is tested.
        """
        ctl = self.controller_1
        # Override the behavior to force use of trash
        ctl.trash_modified_file = lambda: True

        # Bind the server and root workspace
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Get local and remote clients
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_document_client_1

        syn = ctl.synchronizer

        # Create a remote folder then synchronize
        remote.make_folder('/', 'Test folder')
        self._synchronize(syn)
        self.assertTrue(remote.exists('/Test folder'))
        self.assertTrue(local.exists('/Test folder'))

        # Delete remote folder and create files in the local one then
        # synchronize
        remote.delete('/Test folder')
        local.make_file('/Test folder', 'joe.txt', 'My name is Joe.')
        self._synchronize(syn)

        self.assertFalse(remote.exists('/Test folder'))
        self.assertFalse(local.exists('/Test folder'))
