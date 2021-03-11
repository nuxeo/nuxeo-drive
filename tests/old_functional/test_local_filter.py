from nxdrive.constants import SYNC_ROOT

from .common import FS_ITEM_ID_PREFIX, SYNC_ROOT_FAC_ID, OneUserTest


class TestLocalFilter(OneUserTest):
    def test_synchronize_local_filter(self):
        """Test that filtering remote documents is impacted client side

        Just do a single test as it is the same as
        test_integration_remote_deletion

        Use cases:
          - Filter delete a regular folder
              => Folder should be locally deleted
          - Unfilter restore folder from the trash
              => Folder should be locally re-created
          - Filter a synchronization root
              => Synchronization root should be locally deleted
          - Unfilter synchronization root from the trash
              => Synchronization root should be locally re-created

        See TestIntegrationSecurityUpdates.test_synchronize_denying_read_access
        as the same uses cases are tested
        """
        # Bind the server and root workspace
        self.engine_1.start()
        # Get local and remote clients
        local = self.local_1
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder("/", "Test folder")
        remote.make_file("/Test folder", "joe.txt", content=b"Some content")
        self.wait_sync(wait_for_async=True)
        # Fake server binding with the unit test class
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.txt")

        # Add remote folder as filter then synchronize
        doc = remote.get_info("/Test folder")
        root_path = f"{SYNC_ROOT}/{SYNC_ROOT_FAC_ID}{doc.root}"
        doc_path = f"{root_path}/{FS_ITEM_ID_PREFIX}{doc.uid}"

        self.engine_1.add_filter(doc_path)
        self.wait_sync()
        assert not local.exists("/Test folder")

        self.engine_1.remove_filter(doc_path)
        self.wait_sync()
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.txt")

        self.engine_1.add_filter(doc_path)
        self.wait_sync()
        assert not local.exists("/Test folder")

        # Delete sync root then synchronize
        self.engine_1.add_filter(root_path)
        self.wait_sync()
        assert not local.exists("/")

        # Restore sync root from trash then synchronize
        self.engine_1.remove_filter(root_path)
        self.wait_sync()
        assert local.exists("/")
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.txt")

    def test_synchronize_local_office_temp(self):
        # Should synchronize directly local folder with hex name
        # Bind the server and root workspace
        hexaname = "1234ABCD"
        hexafile = "2345BCDF"
        self.engine_1.start()
        self.wait_sync()
        self.local_1.make_folder("/", hexaname)
        self.local_1.make_file("/", hexafile, content=b"test")
        # Make sure that a folder is synchronized directly
        # no matter what and the file is postponed
        self.wait_sync(enforce_errors=False, fail_if_timeout=False)
        children = self.remote_document_client_1.get_children_info(self.workspace)
        assert len(children) == 1

        # Force the postponed to ensure it's synchronized now
        self.engine_1.queue_manager.requeue_errors()
        self.wait_sync(wait_for_async=True)
        assert self.local_1.exists("/" + hexafile)
        children = self.remote_document_client_1.get_children_info(self.workspace)
        assert len(children) == 2
        assert children[1].name == "2345BCDF"

    def test_synchronize_local_filter_with_move(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder("/", "Test")
        remote.make_file("/Test", "joe.txt", content=b"Some content")
        remote.make_folder("/Test", "Subfolder")
        remote.make_folder("/Test", "Filtered")
        remote.make_file("/Test/Subfolder", "joe2.txt", content=b"Some content")
        remote.make_file("/Test/Subfolder", "joe3.txt", content=b"Somecossntent")
        remote.make_folder("/Test/Subfolder/", "SubSubfolder")
        remote.make_file(
            "/Test/Subfolder/SubSubfolder", "joe4.txt", content=b"Some qwqwqontent"
        )

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Test")
        assert local.exists("/Test/joe.txt")
        assert local.exists("/Test/Filtered")
        assert local.exists("/Test/Subfolder")
        assert local.exists("/Test/Subfolder/joe2.txt")
        assert local.exists("/Test/Subfolder/joe3.txt")
        assert local.exists("/Test/Subfolder/SubSubfolder")
        assert local.exists("/Test/Subfolder/SubSubfolder/joe4.txt")

        # Add remote folder as filter then synchronize
        doc_file = remote.get_info("/Test/joe.txt")
        doc = remote.get_info("/Test")
        filtered_doc = remote.get_info("/Test/Filtered")
        root_path = f"{SYNC_ROOT}/{SYNC_ROOT_FAC_ID}{doc.root}"
        doc_path_filtered = f"{root_path}/{FS_ITEM_ID_PREFIX}{doc.uid}/{FS_ITEM_ID_PREFIX}{filtered_doc.uid}"

        self.engine_1.add_filter(doc_path_filtered)
        self.wait_sync()
        assert not local.exists("/Test/Filtered")

        # Move joe.txt to filtered folder on the server
        remote.move(doc_file.uid, filtered_doc.uid)
        self.wait_sync(wait_for_async=True)

        # It now delete on the client
        assert not local.exists("/Test/joe.txt")
        assert local.exists("/Test/Subfolder")
        assert local.exists("/Test/Subfolder/joe2.txt")
        assert local.exists("/Test/Subfolder/joe3.txt")
        assert local.exists("/Test/Subfolder/SubSubfolder")
        assert local.exists("/Test/Subfolder/SubSubfolder/joe4.txt")

        # Now move the subfolder
        doc_file = remote.get_info("/Test/Subfolder")
        remote.move(doc_file.uid, filtered_doc.uid)
        self.wait_sync(wait_for_async=True)

        # Check that all has been deleted
        assert not local.exists("/Test/joe.txt")
        assert not local.exists("/Test/Subfolder")
        assert not local.exists("/Test/Subfolder/joe2.txt")
        assert not local.exists("/Test/Subfolder/joe3.txt")
        assert not local.exists("/Test/Subfolder/SubSubfolder")
        assert not local.exists("/Test/Subfolder/SubSubfolder/joe4.txt")

    def test_synchronize_local_filter_with_remote_trash(self):
        self.engine_1.start()

        # Get local and remote clients
        local = self.local_1
        remote = self.remote_document_client_1

        # Create documents in the remote root workspace
        # then synchronize
        folder_id = remote.make_folder("/", "Test")
        remote.make_file("/Test", "joe.txt", content=b"Some content")

        self.wait_sync(wait_for_async=True)
        assert local.exists("/Test")
        assert local.exists("/Test/joe.txt")

        # Add remote folder as filter then synchronize
        doc = remote.get_info("/Test")
        root_path = f"{SYNC_ROOT}/{SYNC_ROOT_FAC_ID}{doc.root}"
        doc_path = f"{root_path}/{FS_ITEM_ID_PREFIX}{doc.uid}"

        self.engine_1.add_filter(doc_path)
        self.wait_sync()
        assert not local.exists("/Test")

        # Delete remote folder then synchronize
        remote.delete("/Test")
        self.wait_sync(wait_for_async=True)
        assert not local.exists("/Test")

        # Restore folder from trash then synchronize
        remote.undelete(folder_id)
        # NXDRIVE-xx check that the folder is not created as it is filtered
        self.wait_sync(wait_for_async=True)
        assert not local.exists("/Test")
