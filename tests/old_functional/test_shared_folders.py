from pathlib import Path

from ..utils import random_png
from . import LocalTest
from .common import TwoUsersTest


class TestSharedFolders(TwoUsersTest):
    def test_move_sync_root_child_to_user_workspace(self):
        """See https://jira.nuxeo.com/browse/NXP-14870"""
        uid = None
        try:
            # Get remote  and local clients
            remote_1 = self.remote_document_client_1
            remote_2 = self.remote_document_client_2

            local_user2 = LocalTest(self.local_nxdrive_folder_2)

            # Make sure personal workspace is created for user1
            # and fetch its uid
            uid = remote_1.make_file_in_user_workspace(
                b"File in user workspace", "UWFile.txt"
            )["parentRef"]

            # As user1 register personal workspace as a sync root
            remote_1.register_as_root(uid)

            # As user1 create a parent folder in user1's personal workspace
            parent_uid = remote_1.make_folder(uid, "Parent")

            # As user1 grant Everything permission to user2 on parent folder
            input_obj = "doc:" + parent_uid
            self.root_remote.execute(
                command="Document.SetACE",
                input_obj=input_obj,
                user=self.user_2,
                permission="Everything",
                grant=True,
            )

            # As user1 create a child folder in parent folder
            child_folder_uid = remote_1.make_folder(parent_uid, "Child")

            # As user2 register parent folder as a sync root
            remote_2.register_as_root(parent_uid)
            remote_2.unregister_as_root(self.workspace)
            # Start engine for user2
            self.engine_2.start()

            # Wait for synchronization
            self.wait_sync(
                wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True
            )

            # Check locally synchronized content
            assert len(local_user2.get_children_info("/")) == 1
            assert local_user2.exists("/Parent")
            assert local_user2.exists("/Parent/Child")

            # As user1 move child folder to user1's personal workspace
            remote_1.move(child_folder_uid, uid)

            # Wait for synchronization
            self.wait_sync(
                wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True
            )

            # Check locally synchronized content
            assert not local_user2.exists("/Parent/Child")

        finally:
            # Cleanup user1 personal workspace
            if uid is not None and self.root_remote.exists(uid):
                self.root_remote.delete(uid, use_trash=False)

    def test_local_changes_while_stopped(self):
        self._test_local_changes_while_not_running(False)

    def test_local_changes_while_unbinded(self):
        self._test_local_changes_while_not_running(True)

    def _test_local_changes_while_not_running(self, unbind):
        """NXDRIVE-646: not uploading renamed file from shared folder."""
        local_1 = self.local_root_client_1
        remote_1 = self.remote_document_client_1
        remote_2 = self.remote_document_client_2

        # Unregister test workspace for user_1
        remote_1.unregister_as_root(self.workspace)

        # Remove ReadWrite permission for user_1 on the test workspace
        test_workspace = f"doc:{self.ws.path}"
        self.root_remote.execute(
            command="Document.SetACE",
            input_obj=test_workspace,
            user=self.user_2,
            permission="ReadWrite",
            grant=True,
        )

        # Create initial folders and files as user_2
        folder = remote_2.make_folder("/", "Folder01")
        subfolder_1 = remote_2.make_folder(folder, "SubFolder01")
        remote_2.make_file(subfolder_1, "Image01.png", random_png())
        file_id = remote_2.make_file(folder, "File01.txt", content=b"plaintext")

        # Grant Read permission for user_1 on the test folder and register
        self.root_remote.execute(
            command="Document.SetACE",
            input_obj=f"doc:{folder}",
            user=self.user_1,
            permission="Read",
        )
        remote_1.register_as_root(folder)

        # Start engine and wait for sync
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # First checks
        file_pair_state = self.engine_1.dao.get_state_from_local(
            Path("/Folder01") / "File01.txt"
        )
        assert file_pair_state is not None
        file_remote_ref = file_pair_state.remote_ref
        assert remote_2.exists("/Folder01")
        assert remote_2.exists("/Folder01/File01.txt")
        assert remote_2.exists("/Folder01/SubFolder01")
        assert remote_2.exists("/Folder01/SubFolder01/Image01.png")
        assert local_1.exists("/Folder01")
        assert local_1.exists("/Folder01/File01.txt")
        assert local_1.exists("/Folder01/SubFolder01")
        assert local_1.exists("/Folder01/SubFolder01/Image01.png")

        # Unbind or stop engine
        if unbind:
            self.send_unbind_engine(1)
            self.wait_unbind_engine(1)
        else:
            self.engine_1.stop()

        # Restore write permission to user_1 (=> ReadWrite)
        self.root_remote.execute(
            command="Document.SetACE",
            input_obj=f"doc:{folder}",
            user=self.user_1,
            permission="ReadWrite",
        )
        self.wait()

        # Make changes
        LocalTest.rename(local_1, "/Folder01/File01.txt", "File01_renamed.txt")
        LocalTest.delete(local_1, "/Folder01/SubFolder01/Image01.png")

        # Bind or start engine and wait for sync
        if unbind:
            self.send_bind_engine(1)
            self.wait_bind_engine(1)
        else:
            self.engine_1.start()
        self.wait_sync()

        # Check client side
        assert local_1.exists("/Folder01")
        # File has been renamed and image deleted
        assert not local_1.exists("/Folder01/File01.txt")
        assert local_1.exists("/Folder01/File01_renamed.txt")
        # The deleted image has been recreated if the unbinding happened
        assert local_1.exists("/Folder01/SubFolder01/Image01.png") is unbind

        # Check server side
        children = remote_2.get_children_info(folder)
        assert len(children) == 2
        file_info = remote_2.get_info(file_id)
        if unbind:
            # File has not been renamed and image has not been deleted
            assert file_info.name == "File01.txt"
            assert remote_2.exists("/Folder01/SubFolder01/Image01.png")
            # File is in conflict
            file_pair_state = self.engine_1.dao.get_normal_state_from_remote(
                file_remote_ref
            )
            assert file_pair_state.pair_state == "conflicted"
        else:
            # File has been renamed and image deleted
            assert file_info.name == "File01_renamed.txt"
            assert not remote_2.exists("/Folder01/SubFolder01/Image01.png")

    def test_conflict_resolution_with_renaming(self):
        """NXDRIVE-645: shared Folders conflict resolution with renaming."""

        local = self.local_1
        remote = self.remote_document_client_2
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Create initial folder and file
        folder = remote.make_folder("/", "Final")
        remote.make_file("/Final", "Aerial04.png", content=random_png())

        # First checks, everything should be online for every one
        self.wait_sync(wait_for_async=True)
        assert remote.exists("/Final")
        assert remote.exists("/Final/Aerial04.png")
        assert local.exists("/Final")
        assert local.exists("/Final/Aerial04.png")
        folder_pair_state = self.engine_1.dao.get_state_from_local(
            Path(self.workspace_title) / "Final"
        )
        assert folder_pair_state is not None

        # Stop clients
        self.engine_1.stop()

        # Make changes
        folder_conflicted = local.make_folder("/", "Finished")
        local.make_file(folder_conflicted, "Aerial04.png", random_png())
        remote.update(folder, properties={"dc:title": "Finished"})

        # Restart clients and wait
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Check remote
        assert remote.exists("/Finished")
        assert remote.exists("/Finished/Aerial04.png")

        # Check client
        assert local.exists("/Finished")
        assert local.exists("/Finished/Aerial04.png")

        # Check folder status
        folder_pair_state = self.engine_1.dao.get_state_from_id(folder_pair_state.id)
        assert folder_pair_state.last_error == "DEDUP"
