import time
from pathlib import Path

import pytest

from .common import OS_STAT_MTIME_RESOLUTION, OneUserTest


class TestSecurityUpdates(OneUserTest):
    def test_synchronize_denying_read_access(self):
        """Test that denying Read access server side is impacted client side

        Use cases:
          - Deny Read access on a regular folder
              => Folder should be locally deleted
          - Grant Read access back
              => Folder should be locally re-created
          - Deny Read access on a synchronization root
              => Synchronization root should be locally deleted
          - Grant Read access back
              => Synchronization root should be locally re-created

        See TestIntegrationRemoteDeletion.test_synchronize_remote_deletion
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
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.txt")

        # Remove Read permission for test user on a regular folder
        # then synchronize
        self._set_read_permission(self.user_1, f"{self.ws.path}/Test folder", False)
        self.wait_sync(wait_for_async=True)
        assert not local.exists("/Test folder")

        # Add Read permission back for test user then synchronize
        self._set_read_permission(self.user_1, f"{self.ws.path}/Test folder", True)
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.txt")

        # Remove Read permission for test user on a sync root
        # then synchronize
        self._set_read_permission(self.user_1, self.ws.path, False)
        self.wait_sync(wait_for_async=True)
        assert not local.exists("/")

        # Add Read permission back for test user then synchronize
        self._set_read_permission(self.user_1, self.ws.path, True)
        self.wait_sync(wait_for_async=True)
        assert local.exists("/")
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.txt")

    @pytest.mark.skip("NXDRIVE-170: WIP")
    def test_synchronize_denying_read_access_local_modification(self):
        # TO_REVIEW: Trash feature, delete it,
        # might need to modify the behavior
        """Test denying Read access with concurrent local modification

        Use cases:
          - Deny Read access on a regular folder and make some
            local and remote changes concurrently.
              => Only locally modified content should be kept
                 and should be marked as 'unsynchronized',
                 other content should be deleted.
                 Remote changes should not be impacted client side.
                 Local changes should not be impacted server side.
          - Grant Read access back.
              => Remote documents should be merged with
                 locally modified content which should be unmarked
                 as 'unsynchronized' and therefore synchronized upstream.

        See TestIntegrationRemoteDeletion
                .test_synchronize_remote_deletion_local_modification
        as the same uses cases are tested.

        Note that we use the .odt extension for test files to make sure
        that they are created as File and not Note documents on the server
        when synchronized upstream, as the current implementation of
        RemoteDocumentClient is File oriented.
        """
        # Bind the server and root workspace
        self.engine_1.start()
        # Get local and remote clients
        local = self.local_1
        remote = self.remote_document_client_1
        root_remote = self.root_remote

        # Create documents in the remote root workspace
        # then synchronize
        remote.make_folder("/", "Test folder")
        remote.make_file("/Test folder", "joe.odt", content=b"Some content")
        remote.make_file("/Test folder", "jack.odt", content=b"Some content")
        remote.make_folder("/Test folder", "Sub folder 1")
        remote.make_file(
            "/Test folder/Sub folder 1", "sub file 1.txt", content=b"Content"
        )

        self.wait_sync(wait_for_async=True)
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.odt")
        assert local.exists("/Test folder/jack.odt")
        assert local.exists("/Test folder/Sub folder 1")
        assert local.exists("/Test folder/Sub folder 1/sub file 1.txt")

        # Remove Read permission for test user on a regular folder
        # and make some local and remote changes concurrently then synchronize
        test_folder_path = f"{self.ws.path}/Test folder"
        self._set_read_permission(self.user_1, test_folder_path, False)
        # Local changes
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        # Create new file
        local.make_file("/Test folder", "local.odt", content=b"New local content")
        # Create new folder with files
        local.make_folder("/Test folder", "Local sub folder 2")
        local.make_file(
            "/Test folder/Local sub folder 2",
            "local sub file 2.txt",
            content=b"Other local content",
        )
        # Update file
        local.update_content("/Test folder/joe.odt", b"Some locally updated content")
        # Remote changes
        # Create new file
        root_remote.make_file(
            test_folder_path, "remote.odt", content=b"New remote content"
        )
        # Create new folder with files
        root_remote.make_folder(test_folder_path, "Remote sub folder 2")
        root_remote.make_file(
            test_folder_path + "/Remote sub folder 2",
            "remote sub file 2.txt",
            content=b"Other remote content",
        )
        # Update file
        root_remote.update_content(
            test_folder_path + "/joe.odt", b"Some remotely updated content"
        )

        self.wait_sync(wait_for_async=True)
        # Only locally modified content should exist
        # and should be marked as 'unsynchronized', other content should
        # have been deleted.
        # Remote changes should not be impacted client side.
        # Local changes should not be impacted server side.
        # Local check
        assert local.exists("/Test folder")
        assert len(local.get_children_info("/Test folder")) == 3
        assert local.exists("/Test folder/joe.odt")
        assert (
            local.get_content("/Test folder/joe.odt") == b"Some locally updated content"
        )
        assert local.exists("/Test folder/local.odt")
        assert local.exists("/Test folder/Local sub folder 2")
        assert local.exists("/Test folder/Local sub folder 2/local sub file 2.txt")

        assert not local.exists("/Test folder/jack.odt")
        assert not local.exists("/Test folder/remote.odt")
        assert not local.exists("/Test folder/Sub folder 1")
        assert not local.exists("/Test folder/Sub folder 1/sub file 1.txt")
        assert not local.exists("/Test folder/Remote sub folder 1")
        assert not local.exists(
            "/Test folder/Remote sub folder 1/remote sub file 1.txt"
        )
        # State check
        self._check_pair_state("/Test folder", "unsynchronized")
        self._check_pair_state("/Test folder/joe.odt", "unsynchronized")
        self._check_pair_state("/Test folder/local.odt", "unsynchronized")
        self._check_pair_state("/Test folder/Local sub folder 2", "unsynchronized")
        self._check_pair_state(
            "/Test folder/Local sub folder 2/local sub file 2.txt", "unsynchronized"
        )
        # Remote check
        test_folder_uid = root_remote.get_info(test_folder_path).uid
        assert len(root_remote.get_children_info(test_folder_uid)) == 5
        assert root_remote.exists(test_folder_path + "/joe.odt")
        assert (
            root_remote.get_content(test_folder_path + "/joe.odt")
            == b"Some remotely updated content"
        )
        assert root_remote.exists(test_folder_path + "/jack.odt")
        assert root_remote.exists(test_folder_path + "/remote.odt")
        assert root_remote.exists(test_folder_path + "/Sub folder 1")
        assert root_remote.exists(test_folder_path + "/Sub folder 1/sub file 1.txt")
        assert root_remote.exists(test_folder_path + "/Remote sub folder 2")
        assert root_remote.exists(
            f"{test_folder_path}/Remote sub folder 2/remote sub file 2.txt"
        )

        assert not root_remote.exists(test_folder_path + "/local.odt")
        assert not root_remote.exists(test_folder_path + "/Local sub folder 2")
        assert not root_remote.exists(
            f"{test_folder_path}/Local sub folder 1/local sub file 2.txt"
        )

        # Add Read permission back for test user then synchronize
        self._set_read_permission(self.user_1, f"{self.ws.path}/Test folder", True)
        self.wait_sync(wait_for_async=True)
        # Remote documents should be merged with locally modified content
        # which should be unmarked as 'unsynchronized' and therefore
        # synchronized upstream.
        # Local check
        assert local.exists("/Test folder")
        children_info = local.get_children_info("/Test folder")
        assert len(children_info) == 8
        for info in children_info:
            if info.name == "joe.odt":
                remote_version = info
            elif info.name.startswith("joe (") and info.name.endswith(").odt"):
                local_version = info
        assert remote_version is not None
        assert local_version is not None
        assert local.exists(remote_version.path)
        assert (
            local.get_content(remote_version.path) == b"Some remotely updated content"
        )
        assert local.exists(local_version.path)
        assert local.get_content(local_version.path) == b"Some locally updated content"
        assert local.exists("/Test folder/jack.odt")
        assert local.exists("/Test folder/local.odt")
        assert local.exists("/Test folder/remote.odt")
        assert local.exists("/Test folder/Sub folder 1")
        assert local.exists("/Test folder/Sub folder 1/sub file 1.txt")
        assert local.exists("/Test folder/Local sub folder 2")
        assert local.exists("/Test folder/Local sub folder 2/local sub file 2.txt")
        assert local.exists("/Test folder/Remote sub folder 2")
        assert local.exists("/Test folder/Remote sub folder 2/remote sub file 2.txt")
        # State check
        self._check_pair_state("/Test folder", "synchronized")
        self._check_pair_state("/Test folder/joe.odt", "synchronized")
        self._check_pair_state("/Test folder/local.odt", "synchronized")
        self._check_pair_state("/Test folder/Local sub folder 2", "synchronized")
        self._check_pair_state(
            "/Test folder/Local sub folder 2/local sub file 2.txt", "synchronized"
        )
        # Remote check
        assert remote.exists("/Test folder")
        children_info = remote.get_children_info(test_folder_uid)
        assert len(children_info) == 8
        for info in children_info:
            if info.name == "joe.odt":
                remote_version = info
            elif info.name.startswith("joe (") and info.name.endswith(").odt"):
                local_version = info
        assert remote_version is not None
        assert local_version is not None
        remote_version_ref_length = len(remote_version.path) - len(self.ws.path)
        remote_version_ref = remote_version.path[-remote_version_ref_length:]
        assert remote.exists(remote_version_ref)
        assert (
            remote.get_content(remote_version_ref) == b"Some remotely updated content"
        )
        local_version_ref_length = len(local_version.path) - len(self.ws.path)
        local_version_ref = local_version.path[-local_version_ref_length:]
        assert remote.exists(local_version_ref)
        assert remote.get_content(local_version_ref) == b"Some locally updated content"
        assert remote.exists("/Test folder/jack.odt")
        assert remote.exists("/Test folder/local.odt")
        assert remote.exists("/Test folder/remote.odt")
        assert remote.exists("/Test folder/Sub folder 1")
        assert remote.exists("/Test folder/Sub folder 1/sub file 1.txt")
        assert remote.exists("/Test folder/Local sub folder 2")
        assert remote.exists("/Test folder/Local sub folder 2/local sub file 2.txt")
        assert remote.exists("/Test folder/Remote sub folder 2")
        assert remote.exists("/Test folder/Remote sub folder 2/remote sub file 2.txt")

    def _set_read_permission(self, user, doc_path, grant):
        input_obj = "doc:" + doc_path
        if grant:
            self.root_remote.execute(
                command="Document.SetACE",
                input_obj=input_obj,
                user=user,
                permission="Read",
                grant=True,
            )
        else:
            self.root_remote.block_inheritance(doc_path)

    def _check_pair_state(self, local_path, pair_state):
        local_path = Path(self.workspace_title) / local_path
        doc_pair = self.engine_1.dao.get_state_from_local(local_path)
        assert doc_pair.pair_state == pair_state
