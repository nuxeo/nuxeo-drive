# coding: utf-8
from .common import UnitTestCase


class TestSyncRoots(UnitTestCase):

    def test_register_sync_root_parent(self):
        remote = self.remote_document_client_1
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
        assert not local.exists('/Nuxeo Drive Test Workspace')
        assert local.exists('/child')
        assert local.exists('/child/aFile.txt')

        # Register parent folder
        remote.register_as_root(self.workspace)

        # Start engine and wait for synchronization
        self.wait_sync(wait_for_async=True)
        assert not local.exists('/child')
        assert local.exists('/Nuxeo Drive Test Workspace')
        assert local.exists('/Nuxeo Drive Test Workspace/child')
        assert local.exists('/Nuxeo Drive Test Workspace/child/aFile.txt')
