from contextlib import suppress

import pytest

from .common import OneUserTest


class TestCollection(OneUserTest):
    @pytest.fixture(autouse=True)
    def teardown(self):
        yield

        with suppress(Exception):
            # Happened when the test fails at setup_method()
            self.remote_document_client_1.delete(
                self.collection["uid"], use_trash=False
            )

    def test_collection_synchronization(self):
        remote = self.remote_1

        # Remove synchronization root
        remote.unregister_as_root(self.workspace)

        # Create a document "Fiiile" in a folder "Test"
        folder = self.remote_document_client_1.make_folder("/", "Test")
        # Attach a file "abcde.txt" to the document
        doc = self.remote_document_client_1.make_file_with_blob(
            folder, "abcde.txt", b"abcde"
        )

        # Create a collection and add the document to it
        self.collection = remote.execute(
            command="Collection.Create",
            name="CollectionA",
            description="Test collection",
        )
        remote.execute(
            command="Document.AddToCollection",
            collection=self.collection["uid"],
            input_obj=f"doc:{doc}",
        )

        # Register the collection as the synchronization root
        remote.register_as_root(self.collection["uid"])

        # Sync locally
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Get a client on the newly synchronized collection
        local = self.get_local_client(self.local_nxdrive_folder_1 / "CollectionA")

        # Check the attached file is here
        assert local.exists("/abcde.txt")

        # Attach a file "fghij.txt" to the document
        #   This should effectively replace the previous file
        #   since we did not specify another xpath than the main blob.
        self.remote_document_client_1.attach_blob(doc, b"fghij", "fghij.txt")

        # Sync locally
        self.wait_sync(wait_for_async=True)

        # Check the new attached file is here, and the previous isn't
        assert local.exists("/fghij.txt")
        assert not local.exists("/abcde.txt")
