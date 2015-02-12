
from nxdrive.tests.common import IntegrationTestCase


class TestCopy(IntegrationTestCase):

    def test_synchronize_remote_copy(self):
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Create a file and a folder in the remote root workspace
        remote.make_file('/', 'test.odt', 'Some content.')
        remote.make_folder('/', 'Test folder')

        # Launch ndrive and check synchronization
        self.setUpDrive_1(firstSync=True)
        self.assertTrue(local.exists('/'))
        self.assertTrue(local.exists('/Test folder'))
        self.assertTrue(local.exists('/test.odt'))

        # Copy the file to the folder remotely
        remote.copy('/test.odt', '/Test folder')

        # Launch ndrive and check synchronization
        self.ndrive()
        self.assertTrue(local.exists('/Test folder/test.odt'))
        self.assertEquals(local.get_content('/Test folder/test.odt'),
                          'Some content.')
