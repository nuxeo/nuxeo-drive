# coding: utf-8
import time

import pytest

from .common import (
    OS_STAT_MTIME_RESOLUTION,
    REMOTE_MODIFICATION_TIME_RESOLUTION,
    TEST_DEFAULT_DELAY,
    UnitTestCase,
)


class TestConcurrentSynchronization(UnitTestCase):
    def create_docs(self, parent, number, name_pattern=None, delay=1.0):
        return pytest.root_remote.operations.execute(
            command="NuxeoDrive.CreateTestDocuments",
            input_obj="doc:" + parent,
            namePattern=name_pattern,
            number=number,
            delay=int(delay * 1000),
        )

    def test_find_changes_with_many_doc_creations(self):
        local = self.local_1

        # Synchronize root workspace
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert local.exists("/")
        assert not local.get_children_info("/")

        # List of children names to create
        n_children = 5
        child_name_pattern = "child_%03d.txt"
        children_names = [child_name_pattern % i for i in range(n_children)]

        # Create the children to synchronize on the remote server concurrently
        # in a long running transaction
        self.create_docs(
            self.workspace, n_children, name_pattern=child_name_pattern, delay=0.5
        )

        # Wait for the synchronizer thread to complete
        self.wait_sync(wait_for_async=True)

        # Check that all the children creations where detected despite the
        # creation transaction spanning longer than the individual audit
        # query time ranges.
        local_children_names = [c.name for c in local.get_children_info("/")]
        local_children_names.sort()
        assert local_children_names == children_names

    def test_delete_local_folder_2_clients(self):
        # Get local clients for each device and remote client
        local1 = self.local_1
        local2 = self.local_2
        remote = self.remote_document_client_1

        # Check synchronization roots for drive1,
        # there should be 1, the test workspace
        sync_roots = remote.get_roots()
        assert len(sync_roots) == 1
        assert sync_roots[0].name == self.workspace_title

        # Launch first synchronization on both devices
        self.engine_1.start()
        self.engine_2.start()
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True)

        # Test workspace should be created locally on both devices
        assert local1.exists("/")
        assert local2.exists("/")

        # Make drive1 create a remote folder in the
        # test workspace and a file inside this folder,
        # then synchronize both devices
        test_folder = remote.make_folder(self.workspace, "Test folder")
        remote.make_file(test_folder, "test.odt", content=b"Some content.")

        self.wait_sync(wait_for_async=True, wait_for_engine_2=True)

        # Test folder should be created locally on both devices
        assert local1.exists("/Test folder")
        assert local1.exists("/Test folder/test.odt")
        assert local2.exists("/Test folder")
        assert local2.exists("/Test folder/test.odt")

        # Delete Test folder locally on one of the devices
        local1.delete("/Test folder")
        assert not local1.exists("/Test folder")

        # Wait for synchronization engines to complete
        # Wait for Windows delete and also async
        self.wait_sync(wait_win=True, wait_for_async=True, wait_for_engine_2=True)

        # Test folder should be deleted on the server and on both devices
        assert not remote.exists(test_folder)
        assert not local1.exists("/Test folder")
        assert not local2.exists("/Test folder")

    def test_delete_local_folder_delay_remote_changes_fetch(self):
        # Get local and remote clients
        local = self.local_1
        remote = self.remote_document_client_1

        # Launch first synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Test workspace should be created locally
        assert local.exists("/")

        # Create a local folder in the test workspace and a file inside
        # this folder, then synchronize
        folder = local.make_folder("/", "Test folder")
        local.make_file(folder, "test.odt", content=b"Some content.")

        self.wait_sync()

        # Test folder should be created remotely in the test workspace
        assert remote.exists("/Test folder")
        assert remote.exists("/Test folder/test.odt")

        # Delete Test folder locally before fetching remote changes,
        # then synchronize
        local.delete("/Test folder")
        assert not local.exists("/Test folder")

        self.wait_sync()

        # Test folder should be deleted remotely in the test workspace.
        # Even though fetching the remote changes will send
        # 'documentCreated' events for Test folder and its child file
        # as a result of the previous synchronization loop, since the folder
        # will not have been renamed nor moved since last synchronization,
        # its remote pair state will not be marked as 'modified',
        # see Model.update_remote().
        # Thus the pair state will be ('deleted', 'synchronized'), resolved as
        # 'locally_deleted'.
        assert not remote.exists("Test folder")

        # Check Test folder has not been re-created locally
        assert not local.exists("/Test folder")

    def test_rename_local_folder(self):
        # Get local and remote clients
        local1 = self.local_1
        local2 = self.local_2

        # Launch first synchronization
        self.engine_1.start()
        self.engine_2.start()
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True)

        # Test workspace should be created locally
        assert local1.exists("/")
        assert local2.exists("/")

        # Create a local folder in the test workspace and a file inside
        # this folder, then synchronize
        local1.make_folder("/", "Test folder")
        local1.rename("/Test folder", "Renamed folder")
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True)
        assert local1.exists("/Renamed folder")
        assert local2.exists("/Renamed folder")

    def test_delete_local_folder_update_remote_folder_property(self):
        # Get local and remote clients
        local = self.local_1
        remote = self.remote_document_client_1

        # Launch first synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Test workspace should be created locally
        assert local.exists("/")

        # Create a local folder in the test workspace and a file inside
        # this folder, then synchronize
        folder = local.make_folder("/", "Test folder")
        local.make_file(folder, "test.odt", content=b"Some content.")

        self.wait_sync()

        # Test folder should be created remotely in the test workspace
        assert remote.exists("/Test folder")
        assert remote.exists("/Test folder/test.odt")

        # Delete Test folder locally and remotely update one of its properties
        # concurrently, then synchronize
        self.engine_1.suspend()
        local.delete("/Test folder")
        assert not local.exists("/Test folder")
        test_folder_ref = remote._check_ref("/Test folder")
        # Wait for 1 second to make sure the folder's last modification time
        # will be different from the pair state's last remote update time
        time.sleep(REMOTE_MODIFICATION_TIME_RESOLUTION)
        remote.update(
            test_folder_ref, properties={"dc:description": "Some description."}
        )
        test_folder = remote.fetch(test_folder_ref)
        assert test_folder["properties"]["dc:description"] == "Some description."
        self.engine_1.resume()

        self.wait_sync(wait_for_async=True)

        # Test folder should be deleted remotely in the test workspace.
        assert not remote.exists("/Test folder")

        # Check Test folder has not been re-created locally
        assert not local.exists("/Test folder")

    def test_update_local_file_content_update_remote_file_property(self):
        # Get local and remote clients
        local = self.local_1
        remote = self.remote_document_client_1

        # Launch first synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Test workspace should be created locally
        assert local.exists("/")

        # Create a local file in the test workspace then synchronize
        local.make_file("/", "test.odt", content=b"Some content.")

        self.wait_sync()

        # Test file should be created remotely in the test workspace
        assert remote.exists("/test.odt")

        self.engine_1.get_queue_manager().suspend()
        # Locally update the file content and remotely update one of its
        # properties concurrently, then synchronize
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content("/test.odt", b"Updated content.")
        assert local.get_content("/test.odt") == b"Updated content."
        test_file_ref = remote._check_ref("/test.odt")
        # Wait for 1 second to make sure the file's last modification time
        # will be different from the pair state's last remote update time
        time.sleep(REMOTE_MODIFICATION_TIME_RESOLUTION)
        remote.update(test_file_ref, properties={"dc:description": "Some description."})
        test_file = remote.fetch(test_file_ref)
        assert test_file["properties"]["dc:description"] == "Some description."
        time.sleep(TEST_DEFAULT_DELAY)
        self.engine_1.get_queue_manager().resume()

        self.wait_sync(wait_for_async=True)

        # Test file should be updated remotely in the test workspace,
        # and no conflict should be detected.
        # Even though fetching the remote changes will send a
        # 'documentModified' event for the test file as a result of its
        # dc:description property update, since the file will not have been
        # renamed nor moved and its content not modified since last
        # synchronization, its remote pair state will not be marked as
        # 'modified', see Model.update_remote().
        # Thus the pair state will be ('modified', 'synchronized'), resolved as
        # 'locally_modified'.
        assert remote.exists("/test.odt")
        assert remote.get_content("/test.odt") == b"Updated content."
        test_file = remote.fetch(test_file_ref)
        assert test_file["properties"]["dc:description"] == "Some description."
        assert len(remote.get_children_info(self.workspace)) == 1

        # Check that the content of the test file has not changed
        assert local.exists("/test.odt")
        assert local.get_content("/test.odt") == b"Updated content."
        assert len(local.get_children_info("/")) == 1
