import os

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient


class TestIntegrationCopy(IntegrationTestCase):

    def test_synchronize_remote_copy(self):
        # Bind the server and root workspace
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Launch first synchronization
        self.wait_audit_change_finder_if_needed()
        self.wait()
        syn = ctl.synchronizer
        syn.loop(delay=0.1, max_loops=1)

        # Get local and remote clients
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_document_client_1

        # Create a file and a folder in the remote root workspace
        # then synchronize
        remote.make_file('/', 'test.odt', 'Some content.')
        remote.make_folder('/', 'Test folder')

        self.wait_audit_change_finder_if_needed()
        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        self.assertTrue(local.exists('/test.odt'))
        self.assertTrue(local.exists('/Test folder'))

        # Copy the file to the folder remotely then synchronize
        remote.copy('/test.odt', '/Test folder')

        self.wait_audit_change_finder_if_needed()
        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        self.assertTrue(local.exists('/Test folder/test.odt'))
        self.assertEquals(local.get_content('/Test folder/test.odt'),
                          'Some content.')
