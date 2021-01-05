"""
Test behaviors when the server allows duplicates and not the client.
"""
from pathlib import Path

import pytest

from .common import OneUserTest


class TestSynchronizationDedup(OneUserTest):
    def test_children_of_folder_in_dedup_error(self):
        """
        NXDRIVE-1037: Children of a folder that is in DEDUP error should be
        ignored.
        """

        local = self.local_1
        engine = self.engine_1
        remote = self.remote_document_client_1
        engine.start()

        # Step 1: create Unisys folder (1st)
        remote.make_folder(self.workspace, "Unisys")
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Unisys")

        # Step 2: create Unisys folder (2nd)
        unisys2 = remote.make_folder(self.workspace, "Unisys")
        self.wait_sync(wait_for_async=True)

        # Check DEDUP error
        doc_pair = engine.dao.get_normal_state_from_remote(
            "defaultFileSystemItemFactory#default#" + unisys2
        )
        assert doc_pair.last_error == "DEDUP"

        # Step 3: create a child in the 2nd Unisys folder
        foo = remote.make_file(unisys2, "foo.txt", content=b"42")
        self.wait_sync(wait_for_async=True)

        # Check the file is not created and not present in the database
        assert not local.exists("/Unisys/foo.txt")
        assert not engine.dao.get_normal_state_from_remote(
            "defaultFileSystemItemFactory#default#" + unisys2 + "/" + foo
        )

        # Check there is nothing syncing
        assert not engine.dao.get_syncing_count()


class TestSynchronizationDedupCaseSensitive(OneUserTest):
    """NXDRIVE-842: do not sync duplicate conflicted folder content."""

    def setUp(self):
        self.local = self.local_root_client_1
        self.remote = self.remote_document_client_1

        # Make documents in the 1st future root folder
        #    /
        #    ├── citrus
        #    │   └── fruits
        #    │       ├── lemon.txt
        #    │       └── orange.txt
        self.remote.make_folder("/", "citrus")
        self.root1 = self.remote.make_folder("/citrus", "fruits")
        self.remote.make_file(self.root1, "lemon.txt", content=b"lemon")
        self.remote.make_file(self.root1, "orange.txt", content=b"orange")

        # Make documents in the 2nd future root folder
        #    /
        #    ├── fruits
        #        ├── cherries.txt
        #        ├── mango.txt
        #        └── papaya.txt
        self.root2 = self.remote.make_folder("/", "fruits")
        self.remote.make_file(self.root2, "cherries.txt", content=b"cherries")
        self.remote.make_file(self.root2, "mango.txt", content=b"mango")
        self.remote.make_file(self.root2, "papaya.txt", content=b"papaya")

        # Register new roots
        #    /
        #    ├── citrus
        #    │   └── fruits (self.root1)
        #    │       ├── lemon.txt
        #    │       └── orange.txt
        #    ├── fruits (self.root2)
        #        ├── cherries.txt
        #        ├── mango.txt
        #        └── papaya.txt
        self.remote.unregister_as_root(self.workspace)
        self.remote.register_as_root(self.root1)
        self.remote.register_as_root(self.root2)

        # Start and wait
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Checks
        # No duplicate possible, there is one "fruits" folder at the root
        assert len(self.local.get_children_info("/")) == 1
        # As events are coming in the reverse order, we should have self.root2
        # synced first, which contains 3 files
        assert len(self.local.get_children_info("/fruits")) == 3

    def check(
        self, count_root: int, count_folder: int, count_fixed_folder: int = -1
    ) -> None:
        self.wait_sync(wait_for_async=True)

        get = self.local.get_children_info
        assert len(get("/")) == count_root
        assert len(get("/fruits")) == count_folder
        if count_fixed_folder > -1:
            assert len(get("/fruits-renamed")) == count_fixed_folder

        # Ensure there is no postponed nor documents in error
        assert not self.engine_1.dao.get_error_count(threshold=0)

    def test_file_sync_under_dedup_shared_folders_rename_remotely_dupe(self):
        self.remote.update(self.root1, properties={"dc:title": "fruits-renamed"})
        self.check(2, 3, count_fixed_folder=2)

    @pytest.mark.randombug(
        "Several rounds may be needed, specially on Windows", condition=True
    )
    def test_file_sync_under_dedup_shared_folders_rename_remotely(self):
        self.remote.update(self.root2, properties={"dc:title": "fruits-renamed"})
        self.check(2, 2, count_fixed_folder=3)

    def test_file_sync_under_dedup_shared_folders_delete_remotely(self):
        self.remote.delete(self.root2)
        self.check(1, 2)

    def test_file_sync_under_dedup_shared_folders_delete_remotely_dupe(self):
        self.remote.delete(self.root1)
        self.check(1, 3)

    def test_file_sync_under_dedup_shared_folders_delete_locally(self):
        self.engine_1.local.delete(Path("fruits"))
        self.check(1, 2)
        assert self.root1 in self.local.get_remote_id("/fruits")

    def test_file_sync_under_dedup_shared_folders_rename_locally(self):
        self.engine_1.local.rename(Path("fruits"), "fruits-renamed")
        self.check(2, 2, count_fixed_folder=3)
