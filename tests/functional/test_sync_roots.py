import os

from .conftest import OneUserTest


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
        folder_name = str(os.listdir(local.base_folder)[0])
        file_path = os.path.join(folder_name, "aFile.txt")
        assert folder_name.startswith(
            "test_register_sync_root_parent"
        ) and folder_name.endswith("child")
        assert local.exists(file_path)
