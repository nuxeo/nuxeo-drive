import os

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient


class TestIntegrationCopy(IntegrationTestCase):

    def test_synchronize_remote_copy(self):
        # Get local and remote clients
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_document_client_1

        # Bind the server and root workspace
        self.bind_server(self.ndrive_1, self.user_1, self.nuxeo_url, self.local_nxdrive_folder_1, self.password_1)
        #TODO: allow use of self.bind_root(self.ndrive_1, self.workspace, self.local_nxdrive_folder_1)
        remote.register_as_root(self.workspace)

        # Create a file and a folder in the remote root workspace
        remote.make_file('/', 'test.odt', 'Some content.')
        remote.make_folder('/', 'Test folder')

        # Copy the file to the folder remotely
        remote.copy('/test.odt', '/Test folder')

        # Launch ndrive, expecting 4 synchronized items
        self.ndrive(self.ndrive_1)
        self.assertTrue(local.exists('/'))
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/test.odt'))
        self.assertTrue(local.exists('/Test folder/test.odt'))
        self.assertEquals(local.get_content('/Test folder/test.odt'),
                          'Some content.')
