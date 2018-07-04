# coding: utf-8
import os
import shutil

from mock import patch

from nxdrive.engine.watcher import RemoteWatcher
from .common import UnitTestCase

wait_for_security_update = False
src = None
dst = None
original_get_changes = RemoteWatcher._get_changes


def mock_get_changes(self, *args, **kwargs):
    global wait_for_security_update
    global src
    global dst
    if wait_for_security_update:
        summary = original_get_changes(self, *args, **kwargs)
        for event in summary["fileSystemChanges"]:
            if event["eventId"] == "securityUpdated":
                shutil.move(src, dst)
        return summary
    return original_get_changes(self, *args, **kwargs)


class TestLocalShareMoveFolders(UnitTestCase):

    NUMBER_OF_LOCAL_IMAGE_FILES = 10
    FILE_NAME_PATTERN = "file%03d.%s"

    def setUp(self):
        """
        1. Create folder a1 in Nuxeo Drive Test Workspace sycn root
        2. Create folder a2 in Nuxeo Drive Test Workspace sycn root
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

        # Add image files to a1
        abs_folder_path_1 = local.abspath(self.folder_path_1)
        for file_num in range(1, num + 1):
            file_name = self.FILE_NAME_PATTERN % (file_num, "png")
            file_path = os.path.join(abs_folder_path_1, file_name)
            self.generate_random_png(file_path)

        self.engine_1.start()
        self.wait_sync(timeout=60, wait_win=True)

        # Check local files in a1
        self._check_local("/a1")

        # Check remote files in a1
        self._check_remote("/a1")

    def _check_local(self, folder):
        local = self.local_1
        num = self.NUMBER_OF_LOCAL_IMAGE_FILES
        names = set(["file%03d.png" % file_num for file_num in range(1, num + 1)])

        assert local.exists(folder)
        children = [child.name for child in local.get_children_info(folder)]
        assert len(children) == num
        assert set(children) == names

    def _check_remote(self, folder):
        local = self.local_1
        remote = self.remote_1
        num = self.NUMBER_OF_LOCAL_IMAGE_FILES
        names = set(["file%03d.png" % file_num for file_num in range(1, num + 1)])

        uid = local.get_remote_id(folder)
        assert uid is not None
        assert remote.fs_exists(uid)

        children = [child.name for child in remote.get_fs_children(uid)]
        assert len(children) == num
        assert set(children) == names

    @patch.object(RemoteWatcher, "_get_changes", mock_get_changes)
    def test_local_share_move_folder_with_files(self):
        global wait_for_security_update, src, dst

        remote = self.root_remote
        local = self.local_1

        src = local.abspath(self.folder_path_1)
        dst = local.abspath(self.folder_path_2)

        wait_for_security_update = True
        input_obj = local.get_remote_id("/a1").split("#")[-1]
        remote.operations.execute(
            command="Document.AddPermission",
            input_obj=input_obj,
            username=self.user_2,
            permission="Everything",
        )

        self.wait_sync()

        wait_for_security_update = False

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
