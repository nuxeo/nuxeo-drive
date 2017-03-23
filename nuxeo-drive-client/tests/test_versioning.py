import time

from tests.common import OS_STAT_MTIME_RESOLUTION, TEST_WORKSPACE_PATH
from tests.common import log
from tests.common_unit_test import UnitTestCase


class TestVersioning(UnitTestCase):

    def test_versioning(self):
        local = self.local_client_1
        self.engine_1.start()

        # Create a file as user 2
        self.remote_document_client_2.make_file('/', 'Test versioning.txt', "This is version 0")
        self.assertTrue(self.remote_document_client_2.exists('/Test versioning.txt'))
        doc = self.root_remote_client.fetch(TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 0)

        # Synchronize it for user 1
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/Test versioning.txt'))

        # Update it as user 1 => should be versioned
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content('/Test versioning.txt', "Modified content")
        self.wait_sync()
        doc = self.root_remote_client.fetch(
            TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 1)

        # Update it as user 1 => should NOT be versioned
        # since the versioning delay is not passed by
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content('/Test versioning.txt', "Content twice modified")
        self.wait_sync()
        doc = self.root_remote_client.fetch(
            TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 1)

    def test_version_restore(self):
        remote_client = self.remote_document_client_1
        local_client = self.local_client_1

        self.engine_1.start()

        # Create a remote doc
        doc = remote_client.make_file(self.workspace, 'Document to restore.txt', content="Initial content.")
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local_client.exists('/Document to restore.txt'))
        self.assertEqual(local_client.get_content('/Document to restore.txt'),
                         "Initial content.")

        # Create version 1.0, update content, then restore version 1.0
        remote_client.create_version(doc, 'Major')
        remote_client.update_content(doc, "Updated content.")
        self.wait_sync(wait_for_async=True)
        self.assertEqual(local_client.get_content('/Document to restore.txt'),
                         "Updated content.")
        version_uid = remote_client.get_versions(doc)[0][0]
        remote_client.restore_version(version_uid)
        self.wait_sync(wait_for_async=True)
        self.assertEqual(local_client.get_content('/Document to restore.txt'),
                         "Initial content.")

    def _assert_version(self, doc, major, minor):
        self.assertEqual(doc['properties']['uid:major_version'], major)
        self.assertEqual(doc['properties']['uid:minor_version'], minor)
