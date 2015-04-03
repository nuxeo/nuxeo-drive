import time

from nxdrive.tests.common import IntegrationTestCase
from nose.plugins.skip import SkipTest


class TestVersioning(IntegrationTestCase):

    def setUp(self):
        super(TestVersioning, self).setUp()

        self.bind_server(self.ndrive_1, self.user_1, self.nuxeo_url, self.local_nxdrive_folder_1, self.password_1)
        self.bind_root(self.ndrive_1, self.workspace, self.local_nxdrive_folder_1)
        self.ndrive(self.ndrive_1)

        self.bind_server(self.ndrive_2, self.user_2, self.nuxeo_url, self.local_nxdrive_folder_2, self.password_2)
        self.bind_root(self.ndrive_2, self.workspace, self.local_nxdrive_folder_2)
        self.ndrive(self.ndrive_2)

        self.remote_client_1 = self.remote_document_client_1
        self.remote_client_2 = self.remote_document_client_2

        # Call the Nuxeo operation to set the versioning delay to 30 seconds
        self.versioning_delay = self.OS_STAT_MTIME_RESOLUTION * 30
        self.root_remote_client.execute(
            "NuxeoDrive.SetVersioningOptions",
            delay=str(self.versioning_delay))

    def test_versioning(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        # Create a file as user 1
        self.local_client_1.make_file('/', 'Test versioning.txt',
            "This is version 0")
        self.ndrive(self.ndrive_1)
        doc = self.root_remote_client.fetch(
            self.TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 0)

        # Synchronize it for user 2
        self.assertTrue(self.remote_client_2.exists('/Test versioning.txt'))
        self.ndrive(self.ndrive_2)
        self.assertTrue(self.local_client_2.exists('/Test versioning.txt'))

        # Update it as user 2 => should be versioned
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        self.local_client_2.update_content('/Test versioning.txt',
            "Modified content")
        self.ndrive(self.ndrive_2)
        doc = self.root_remote_client.fetch(
            self.TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 1)

        # Update it as user 2 => should NOT be versioned
        # since the versioning delay is not passed by
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        self.local_client_2.update_content('/Test versioning.txt',
            "Content twice modified")
        self.ndrive(self.ndrive_2)
        doc = self.root_remote_client.fetch(
            self.TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 1)

        # Wait for versioning delay expiration then update it as user 2 after
        # => should be versioned since the versioning delay is passed by
        time.sleep(self.versioning_delay + 2.0)
        self.local_client_2.update_content('/Test versioning.txt',
            "Updated again!!")
        self.ndrive(self.ndrive_2)
        doc = self.root_remote_client.fetch(
            self.TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 2)

    def test_version_restore(self):
        remote_client = self.remote_client_1
        local_client = self.local_client_1

        # Create a remote doc
        doc = remote_client.make_file(self.workspace,
                                    'Document to restore.txt',
                                    content="Initial content.")
        self.wait()
        self.ndrive()
        self.assertTrue(local_client.exists('/Document to restore.txt'))
        self.assertEquals(local_client.get_content('/Document to restore.txt'),
                          "Initial content.")

        # Create version 1.0, update content, then restore version 1.0
        remote_client.create_version(doc, 'Major')
        # Ensure that modification time is different between the version
        # and the updated live document, otherwise the synchronizer won't
        # consider the restored document (with the modification date of
        # the version) as to be updated
        time.sleep(1.0)
        remote_client.update_content(doc, "Updated content.")
        self.wait()
        self.ndrive()
        self.assertEquals(local_client.get_content('/Document to restore.txt'),
                          "Updated content.")
        version_uid = remote_client.get_versions(doc)[0][0]
        remote_client.restore_version(version_uid)
        self.wait()
        self.ndrive()
        self.assertEquals(local_client.get_content('/Document to restore.txt'),
                          "Initial content.")

    def _assert_version(self, doc, major, minor):
        self.assertEquals(doc['properties']['uid:major_version'], major)
        self.assertEquals(doc['properties']['uid:minor_version'], minor)
