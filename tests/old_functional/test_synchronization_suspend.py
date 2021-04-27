import pytest

from nxdrive.constants import LINUX, WINDOWS

from .common import SYNC_ROOT_FAC_ID, OneUserTest


class TestSynchronizationSuspend(OneUserTest):
    def test_basic_synchronization_suspend(self):
        local = self.local_1
        remote = self.remote_document_client_1
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Let's create some document on the client and the server
        local.make_folder("/", "Folder 3")
        self.make_server_tree()

        # Launch ndrive and check synchronization
        self.wait_sync(wait_for_async=True)
        assert remote.exists("/Folder 3")
        assert local.exists("/Folder 1")
        assert local.exists("/Folder 2")
        assert local.exists("/File 5.txt")
        self.engine_1.queue_manager.suspend()
        local.make_folder("/", "Folder 4")
        local.make_file("/Folder 4", "Test.txt", content=b"Plop")
        self.wait_sync(wait_for_async=True, fail_if_timeout=False)
        assert len(remote.get_children_info(self.workspace)) == 4
        assert self.engine_1.queue_manager.is_paused()

    def test_synchronization_local_watcher_paused_when_offline(self):
        """NXDRIVE-680: fix unwanted local upload when offline."""

        local = self.local_1
        remote = self.remote_document_client_1
        engine = self.engine_1

        # Create one file locally and wait for sync
        engine.start()
        self.wait_sync(wait_for_async=True)
        local.make_file("/", "file1.txt", content=b"42")
        self.wait_sync()

        # Checks
        assert remote.exists("/file1.txt")
        assert local.exists("/file1.txt")

        # Simulate offline mode (no more network for instance)
        engine.queue_manager.suspend()

        # Create a bunch of files locally
        local.make_folder("/", "files")
        for num in range(60 if WINDOWS else 20):
            local.make_file(
                "/files",
                "file-" + str(num) + ".txt",
                content=b"Content of file-" + bytes(num),
            )
        self.wait_sync(fail_if_timeout=False)

        # Checks
        assert len(remote.get_children_info(self.workspace)) == 1
        assert engine.queue_manager.is_paused()

        # Restore network connection
        engine.queue_manager.resume()

        # Wait for sync and check synced files
        self.wait_sync(wait_for_async=True)
        assert len(remote.get_children_info(self.workspace)) == 2
        assert not engine.queue_manager.is_paused()

    def test_synchronization_end_with_children_ignore_parent(self):
        """NXDRIVE-655: children of ignored folder are not ignored."""

        local = self.local_1
        remote = self.remote_document_client_1
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Let's create some document on the client and the server
        local.make_folder("/", "Folder 3")
        self.make_server_tree()

        # Launch ndrive and check synchronization
        self.wait_sync(wait_for_async=True)
        assert remote.exists("/Folder 3")
        assert local.exists("/Folder 1")
        assert local.exists("/Folder 2")
        assert local.exists("/File 5.txt")
        local.make_folder("/", ".hidden")
        local.make_file("/.hidden", "Test.txt", content=b"Plop")
        local.make_folder("/.hidden", "normal")
        local.make_file("/.hidden/normal", "Test.txt", content=b"Plop")
        # Should not try to sync therefore it should not timeout
        self.wait_sync(wait_for_async=True)
        assert len(remote.get_children_info(self.workspace)) == 4

    @pytest.mark.xfail(LINUX, reason="NXDRIVE-1690", strict=True)
    def test_folder_renaming_while_offline(self):
        """
        Scenario:
            - create a folder with a subfolder and a file, on the server
            - launch Drive
            - wait for sync completion
            - pause Drive
            - locally rename the parent folder
            - locally rename the sub folder
            - locally delete the file
            - resume Drive

        Result before NXDRIVE-695:
            - sub folder is renamed on the server
            - the deleted file is not removed on the server (incorrect)
        """

        local = self.local_1
        remote = self.remote_1
        engine = self.engine_1

        # Create a folder with a subfolder and a file on the server
        folder = remote.make_folder(f"{SYNC_ROOT_FAC_ID}{self.workspace}", "folder").uid
        subfolder = remote.make_folder(folder, "subfolder").uid
        remote.make_file(subfolder, "file.txt", content=b"42")

        # Start the sync
        engine.start()
        self.wait_sync(wait_for_async=True)

        # Checks
        assert remote.exists("/folder/subfolder/file.txt")
        assert local.exists("/folder/subfolder/file.txt")

        # Suspend the sync
        engine.suspend()
        assert engine.is_paused()

        # Rename the parent folder and its subfolder; delete the file
        local.rename("/folder", "folder-renamed")
        local.rename("/folder-renamed/subfolder", "subfolder-renamed")
        local.delete("/folder-renamed/subfolder-renamed/file.txt")

        # Resume the sync
        engine.resume()
        assert not engine.is_paused()
        self.wait_sync()

        # Local checks
        assert local.exists("/folder-renamed/subfolder-renamed")
        assert not local.exists("/folder-renamed/subfolder-renamed/file.txt")
        assert not local.exists("/folder")

        # Remote checks
        assert remote.exists("/folder-renamed/subfolder-renamed")
        assert not remote.exists("/folder-renamed/subfolder-renamed/file.txt")
        assert not remote.exists("/folder")
