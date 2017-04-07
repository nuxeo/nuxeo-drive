from nxdrive.client import LocalClient
from tests.common_unit_test import RandomBug, UnitTestCase


class TestSynchronizationSuspend(UnitTestCase):
    def get_local_client(self, path):
        if self._testMethodName == 'test_synchronize_deep_folders':
            return LocalClient(path)
        return super(TestSynchronizationSuspend, self).get_local_client(path)

    @RandomBug('NXDRIVE-805', target='windows', repeat=2)
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

    @RandomBug('NXDRIVE-812', target='linux', mode='BYPASS')
    def test_synchronization_end_with_children_ignore_parent(self):
        """ NXDRIVE-655: children of ignored folder are not ignored. """

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
        local.make_folder('/', '.hidden')
        local.make_file('/.hidden', 'Test.txt', 'Plop')
        local.make_folder('/.hidden', 'normal')
        local.make_file('/.hidden/normal', 'Test.txt', 'Plop')
        # Should not try to sync therefor it should not timeout
        self.wait_sync(wait_for_async=True)
        self.assertEqual(len(remote.get_children_info(self.workspace_1)), 4)
