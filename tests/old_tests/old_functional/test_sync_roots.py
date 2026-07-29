from .common import OneUserTest


class TestSyncRoots(OneUserTest):
    def test_register_sync_root_parent(self):
        remote = self.remote_document_client_1
        local = self.local_root_client_1

        # First unregister test Workspace
        remote.unregister_as_root(self.workspace)

        # Create a child folder and register it as a synchronization root
        child = remote.make_folder(self.workspace, "child")
        remote.make_file(child, "aFile.txt", content=b"My content")
        remote.register_as_root(child)

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert not local.exists(f"/{self.workspace_title}")
        assert local.exists("/child")
        assert local.exists("/child/aFile.txt")

        # Register parent folder
        remote.register_as_root(self.workspace)

        # Start engine and wait for synchronization
        self.wait_sync(wait_for_async=True)
        assert not local.exists("/child")
        assert local.exists(f"/{self.workspace_title}")
        assert local.exists(f"/{self.workspace_title}/child")
        assert local.exists(f"/{self.workspace_title}/child/aFile.txt")
