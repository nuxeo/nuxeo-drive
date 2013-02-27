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
        self.sb_1 = self.controller_1.get_server_binding(
            self.local_nxdrive_folder_1)
        self.sb_2 = self.controller_2.get_server_binding(
            self.local_nxdrive_folder_2)
        self.controller_1.bind_root(self.local_nxdrive_folder_1,
            self.workspace)
        self.controller_2.bind_root(self.local_nxdrive_folder_2,
            self.workspace)

        self.syn_1 = self.controller_1.synchronizer
        self.syn_2 = self.controller_2.synchronizer
        self.syn_1.loop(delay=0.010, max_loops=1)
        self.syn_2.loop(delay=0.010, max_loops=1)

        self.remote_client_1 = self.remote_document_client_1
        self.remote_client_2 = self.remote_document_client_2
        sync_root_folder_1 = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        sync_root_folder_2 = os.path.join(self.local_nxdrive_folder_2,
                                       self.workspace_title)
        self.local_client_1 = LocalClient(sync_root_folder_1)
        self.local_client_2 = LocalClient(sync_root_folder_2)

        # Call the Nuxeo operation to set the versioning delay to 3 seconds
        self.versioning_delay = self.OS_STAT_MTIME_RESOLUTION * 3
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
        self._assert_version(doc, '0', '0')

        # Synchronize it for user 2
        self.assertTrue(self.remote_client_2.exists('/Test versioning.txt'))
        self._synchronize_and_assert(self.syn_2, self.sb_2, 1, wait=True)
        self.assertTrue(self.local_client_2.exists('/Test versioning.txt'))

        # Update it as user 2 => should be versioned
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        self.local_client_2.update_content('/Test versioning.txt',
            "Modified content")
        self._synchronize_and_assert(self.syn_2, self.sb_2, 1)
        doc = self.root_remote_client.fetch(
            self.TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, '0', '1')

        # Update it as user 2 => should NOT be versioned
        # since the versioning delay (3s) is not passed by
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        self.local_client_2.update_content('/Test versioning.txt',
            "Content twice modified")
        self._synchronize_and_assert(self.syn_2, self.sb_2, 1)
        doc = self.root_remote_client.fetch(
            self.TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, '0', '1')

        # Update it as user 2 after 3s => should be versioned
        # since the versioning delay is passed by
        time.sleep(self.versioning_delay + 0.1)
        self.local_client_2.update_content('/Test versioning.txt',
            "Updated again!!")
        self._synchronize_and_assert(self.syn_2, self.sb_2, 1)
        doc = self.root_remote_client.fetch(
            self.TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, '0', '2')

    def _synchronize_and_assert(self, synchronizer, server_binding,
        expected_synchronized, wait=False):
        if wait:
            # Wait for audit changes to be detected after the 1 second step
            time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        n_synchronized = synchronizer.update_synchronize_server(server_binding)
        self.assertEqual(n_synchronized, expected_synchronized)

    def _assert_version(self, doc, major, minor):
        self.assertEquals(doc['properties']['uid:major_version'], major)
        self.assertEquals(doc['properties']['uid:minor_version'], minor)