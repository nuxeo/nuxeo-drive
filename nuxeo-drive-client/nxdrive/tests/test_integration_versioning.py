import os
import time

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient


class TestIntegrationVersioning(IntegrationTestCase):

    def setUp(self):
        super(TestIntegrationVersioning, self).setUp()

        self.controller_1.bind_server(self.local_nxdrive_folder_1,
            self.nuxeo_url, self.user_1, self.password_1)
        self.controller_2.bind_server(self.local_nxdrive_folder_2,
            self.nuxeo_url, self.user_2, self.password_2)
        self.controller_1.bind_root(self.local_nxdrive_folder_1,
            self.workspace)
        self.controller_2.bind_root(self.local_nxdrive_folder_2,
            self.workspace)

        self.syn_1 = self.controller_1.synchronizer
        self.syn_2 = self.controller_2.synchronizer
        self.syn_1.loop(delay=0.010, max_loops=1, no_event_init=True)
        self.syn_2.loop(delay=0.010, max_loops=1, no_event_init=True)

        # Fetch server bindings after sync loop as it closes the Session
        self.sb_1 = self.controller_1.get_server_binding(
            self.local_nxdrive_folder_1)
        self.sb_2 = self.controller_2.get_server_binding(
            self.local_nxdrive_folder_2)

        self.remote_client_1 = self.remote_document_client_1
        self.remote_client_2 = self.remote_document_client_2
        sync_root_folder_1 = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        sync_root_folder_2 = os.path.join(self.local_nxdrive_folder_2,
                                       self.workspace_title)
        self.local_client_1 = LocalClient(sync_root_folder_1)
        self.local_client_2 = LocalClient(sync_root_folder_2)

        # Call the Nuxeo operation to set the versioning delay to 10 seconds
        self.versioning_delay = self.OS_STAT_MTIME_RESOLUTION * 10
        self.root_remote_client.execute(
            "NuxeoDrive.SetVersioningOptions",
            delay=str(self.versioning_delay))

    def test_versioning(self):
        # Create a file as user 1
        self.local_client_1.make_file('/', 'Test versioning.txt',
            "This is version 0")
        self._synchronize_and_assert(self.syn_1, self.sb_1, 1)
        doc = self.root_remote_client.fetch(
            self.TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 0)

        # Synchronize it for user 2
        self.assertTrue(self.remote_client_2.exists('/Test versioning.txt'))
        self._synchronize_and_assert(self.syn_2, self.sb_2, 1)
        self.assertTrue(self.local_client_2.exists('/Test versioning.txt'))

        # Update it as user 2 => should be versioned
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        self.local_client_2.update_content('/Test versioning.txt',
            "Modified content")
        self._synchronize_and_assert(self.syn_2, self.sb_2, 1)
        doc = self.root_remote_client.fetch(
            self.TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 1)

        # Update it as user 2 => should NOT be versioned
        # since the versioning delay (10s) is not passed by
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        self.local_client_2.update_content('/Test versioning.txt',
            "Content twice modified")
        self._synchronize_and_assert(self.syn_2, self.sb_2, 1)
        doc = self.root_remote_client.fetch(
            self.TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 1)

        # Update it as user 2 after 10s => should be versioned
        # since the versioning delay is passed by
        time.sleep(self.versioning_delay + 0.1)
        self.local_client_2.update_content('/Test versioning.txt',
            "Updated again!!")
        self._synchronize_and_assert(self.syn_2, self.sb_2, 1)
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
        self._synchronize_and_assert(self.syn_1, self.sb_1, 1)
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
        self._synchronize_and_assert(self.syn_1, self.sb_1, 1)
        self.assertEquals(local_client.get_content('/Document to restore.txt'),
                          "Updated content.")
        version_uid = remote_client.get_versions(doc)[0][0]
        remote_client.restore_version(version_uid)
        self.wait()
        self._synchronize_and_assert(self.syn_1, self.sb_1, 1)
        self.assertEquals(local_client.get_content('/Document to restore.txt'),
                          "Initial content.")

    def _synchronize_and_assert(self, synchronizer, server_binding,
        expected_synchronized):
        n_synchronized = synchronizer.update_synchronize_server(server_binding)
        self.assertEqual(n_synchronized, expected_synchronized)

    def _assert_version(self, doc, major, minor):
        self.assertEquals(doc['properties']['uid:major_version'], major)
        self.assertEquals(doc['properties']['uid:minor_version'], minor)
