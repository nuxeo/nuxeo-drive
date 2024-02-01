from pathlib import Path

from ..utils import random_png
from . import LocalTest
from .conftest import TwoUsersTest


class TestSharedFolders(TwoUsersTest):
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
