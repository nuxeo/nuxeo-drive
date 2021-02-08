import shutil
from unittest.mock import patch

from nxdrive.engine.watcher.constants import SECURITY_UPDATED_EVENT
from nxdrive.engine.watcher.remote_watcher import RemoteWatcher

from ..utils import random_png
from .common import TwoUsersTest


class TestLocalShareMoveFolders(TwoUsersTest):

    NUMBER_OF_LOCAL_IMAGE_FILES = 10

    def setUp(self):
        """
        1. Create folder a1 in Nuxeo Drive Test Workspace sync root
        2. Create folder a2 in Nuxeo Drive Test Workspace sync root
        3. Add 10 image files in a1
        """

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.engine_1.stop()

        local = self.local_1
        # Create a1 and a2
        self.folder_path_1 = local.make_folder("/", "a1")
        self.folder_path_2 = local.make_folder("/", "a2")

        num = self.NUMBER_OF_LOCAL_IMAGE_FILES
        self.names = {"file%03d.png" % file_num for file_num in range(1, num + 1)}

        # Add image files to a1
        abs_folder_path_1 = local.abspath(self.folder_path_1)
        for file_num in range(1, num + 1):
            file_name = "file%03d.png" % file_num
            file_path = abs_folder_path_1 / file_name
            random_png(file_path)

        self.engine_1.start()
        self.wait_sync(timeout=60, wait_win=True)

        # Check local files in a1
        self._check_local("/a1")

        # Check remote files in a1
        self._check_remote("/a1")

    def _check_local(self, folder):
        local = self.local_1
        assert local.exists(folder)

        children = [child.name for child in local.get_children_info(folder)]
        assert len(children) == self.NUMBER_OF_LOCAL_IMAGE_FILES
        assert set(children) == self.names

    def _check_remote(self, folder):
        local = self.local_1
        remote = self.remote_1

        uid = local.get_remote_id(folder)
        assert uid
        assert remote.fs_exists(uid)

        children = [child.name for child in remote.get_fs_children(uid)]
        assert len(children) == self.NUMBER_OF_LOCAL_IMAGE_FILES
        assert set(children) == self.names

    def test_local_share_move_folder_with_files(self):
        remote = self.root_remote
        local = self.local_1

        src = local.abspath(self.folder_path_1)
        dst = local.abspath(self.folder_path_2)

        input_obj = local.get_remote_id("/a1").split("#")[-1]
        remote.execute(
            command="Document.AddPermission",
            input_obj=input_obj,
            username=self.user_2,
            permission="Everything",
        )

        original_get_changes = RemoteWatcher._get_changes

        def get_changes(self):
            summary = original_get_changes(self)
            for event in summary["fileSystemChanges"]:
                if event["eventId"] == SECURITY_UPDATED_EVENT:
                    nonlocal src
                    nonlocal dst
                    shutil.move(src, dst)
            return summary

        with patch.object(RemoteWatcher, "_get_changes", new=get_changes):
            self.wait_sync()

        # Sync after move operation
        self.wait_sync()
        # Check that a1 doesn't exist anymore locally
        assert not local.exists("/a1")

        # Check local files in a2/a1
        self._check_local("/a2/a1")

        # Check that a1 doesn't exist anymore remotely
        assert len(remote.get_children_info(self.workspace)) == 1

        # Check remote files in a2/a1
        self._check_remote("/a2/a1")

        # As Admin create a folder inside a1
        uid = local.get_remote_id("/a2/a1")
        remote.make_folder(uid.split("#")[-1], "inside_a1")

        self.wait_sync()

        # Check that a1 doesn't exist anymore locally
        assert local.exists("/a2/a1/inside_a1")
