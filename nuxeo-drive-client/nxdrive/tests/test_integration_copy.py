import os

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient


class TestIntegrationCopy(IntegrationTestCase):

    def test_synchronize_remote_copy(self):
        # Get local and remote clients
        local = self.local_client_1
        remote = self.remote_document_client_1

        self.setUpDrive_1()
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
