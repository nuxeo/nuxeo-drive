import time
import urllib2
import socket

from nxdrive.tests.common import TEST_WORKSPACE_PATH
from nxdrive.tests.common import OS_STAT_MTIME_RESOLUTION
from nxdrive.tests.common_unit_test import UnitTestCase
from nxdrive.tests.common_unit_test import DEFAULT_WAIT_SYNC_TIMEOUT
from nxdrive.client import LocalClient
from nxdrive.tests import RemoteTestClient
from nxdrive.client.remote_filtered_file_system_client import RemoteFilteredFileSystemClient
from nxdrive.osi import AbstractOSIntegration


class TestSynchronizationSuspend(UnitTestCase):
    def get_local_client(self, path):
        if self._testMethodName == 'test_synchronize_deep_folders':
            return LocalClient(path)
        return super(TestSynchronizationSuspend, self).get_local_client(path)

    def test_basic_synchronization_suspend(self):
        local = self.local_client_1
        remote = self.remote_document_client_1
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Let's create some document on the client and the server
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()

        # Launch ndrive and check synchronization
        self.wait_sync(wait_for_async=True)
        self.assertTrue(remote.exists('/Folder 3'))
        self.assertTrue(local.exists('/Folder 1'))
        self.assertTrue(local.exists('/Folder 2'))
        self.assertTrue(local.exists('/File 5.txt'))
        self.engine_1.get_queue_manager().suspend()
        local.make_folder('/', 'Folder 4')
        local.make_file('/Folder 4', 'Test.txt', 'Plop')
        self.wait_sync(wait_for_async=True, fail_if_timeout=False)
        self.assertEqual(len(remote.get_children_info(self.workspace_1)), 4)
        self.assertTrue(self.engine_1.get_queue_manager().is_paused())
