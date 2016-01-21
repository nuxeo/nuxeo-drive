import time

from nxdrive.tests.common import TEST_WORKSPACE_PATH
from nxdrive.tests.common import OS_STAT_MTIME_RESOLUTION
from nxdrive.tests.common_unit_test import UnitTestCase


class TestVersioning(UnitTestCase):

    def setUp(self):
        super(TestVersioning, self).setUp()
        self.remote_client_1 = self.remote_document_client_1
        self.remote_client_2 = self.remote_document_client_2
        self.engine_1.start()
        self.engine_2.start()
        # Call the Nuxeo operation to set the versioning delay to 30 seconds
        self.versioning_delay = OS_STAT_MTIME_RESOLUTION * 30
        self.root_remote_client.execute(
            "NuxeoDrive.SetVersioningOptions",
            delay=str(self.versioning_delay))
        self.wait_sync(wait_for_engine_1=True, wait_for_engine_2=True)

    def test_versioning(self):
        # Create a file as user 1
        self.local_client_1.make_file('/', 'Test versioning.txt', "This is version 0")
        self.wait_sync(wait_for_async=True, wait_for_engine_1=True, wait_for_engine_2=True)
        doc = self.root_remote_client.fetch(
            TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 0)

        # Synchronize it for user 2
        self.assertTrue(self.remote_client_2.exists('/Test versioning.txt'))
        self.assertTrue(self.local_client_2.exists('/Test versioning.txt'))

        # Update it as user 2 => should be versioned
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        self.local_client_2.update_content('/Test versioning.txt', "Modified content")
        self.wait_sync(wait_for_engine_1=False, wait_for_engine_2=True)
        doc = self.root_remote_client.fetch(
            TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 1)

        # Update it as user 2 => should NOT be versioned
        # since the versioning delay is not passed by
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        self.local_client_2.update_content('/Test versioning.txt', "Content twice modified")
        self.wait_sync(wait_for_engine_1=False, wait_for_engine_2=True)
        doc = self.root_remote_client.fetch(
            TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 1)

        # Wait for versioning delay expiration then update it as user 2 after
        # => should be versioned since the versioning delay is passed by
        time.sleep(self.versioning_delay + 2.0)
        self.local_client_2.update_content('/Test versioning.txt', "Updated again!!")
        self.wait_sync(wait_for_engine_1=False, wait_for_engine_2=True)
        doc = self.root_remote_client.fetch(
            TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 2)

    def test_version_restore(self):
        remote_client = self.remote_client_1
        local_client = self.local_client_1

        # Create a remote doc
        doc = remote_client.make_file(self.workspace, 'Document to restore.txt', content="Initial content.")
        self.wait_sync(wait_for_engine_1=True, wait_for_engine_2=True)
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
        self.wait_sync(wait_for_engine_1=True, wait_for_engine_2=True)
        self.assertEquals(local_client.get_content('/Document to restore.txt'),
                          "Updated content.")
        version_uid = remote_client.get_versions(doc)[0][0]
        remote_client.restore_version(version_uid)
        self.wait_sync(wait_for_engine_1=True, wait_for_engine_2=True)
        self.assertEquals(local_client.get_content('/Document to restore.txt'),
                          "Initial content.")

    def _assert_version(self, doc, major, minor):
        self.assertEquals(doc['properties']['uid:major_version'], major)
        self.assertEquals(doc['properties']['uid:minor_version'], minor)
