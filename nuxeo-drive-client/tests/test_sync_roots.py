# coding: utf-8
from nxdrive.client import RemoteDocumentClient
from tests.common_unit_test import UnitTestCase


class TestSyncRoots(UnitTestCase):

    def test_register_sync_root_parent(self):
        remote = RemoteDocumentClient(self.nuxeo_url, self.user_1, u'nxdrive-test-device-1', self.version,
                                      password=self.password_1, upload_tmp_dir=self.upload_tmp_dir)
        local = self.local_root_client_1

        # First unregister test Workspace
        remote.unregister_as_root(self.workspace)

        # Create a child folder and register it as a synchronization root
        child = remote.make_folder(self.workspace, 'child')
        remote.make_file(child, 'aFile.txt', u'My content')
        remote.register_as_root(child)

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.assertFalse(local.exists('/Nuxeo Drive Test Workspace'))
        self.assertTrue(local.exists('/child'))
        self.assertTrue(local.exists('/child/aFile.txt'))

        # Register parent folder
        remote.register_as_root(self.workspace)

        # Start engine and wait for synchronization
        self.wait_sync(wait_for_async=True)
        self.assertFalse(local.exists('/child'))
        self.assertTrue(local.exists('/Nuxeo Drive Test Workspace'))
        self.assertTrue(local.exists('/Nuxeo Drive Test Workspace/child'))
        self.assertTrue(local.exists('/Nuxeo Drive Test Workspace/child/aFile.txt'))
