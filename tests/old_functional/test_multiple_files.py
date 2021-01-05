import shutil
from pathlib import Path

import pytest

from nxdrive.constants import LINUX, MAC

from ..markers import not_linux
from .common import OneUserTest


class TestMultipleFiles(OneUserTest):

    NUMBER_OF_LOCAL_FILES = 10
    SYNC_TIMEOUT = 10  # in seconds

    def setUp(self):
        """
        1. create folder 'Nuxeo Drive Test Workspace/a1' with 100 files in it
        2. create folder 'Nuxeo Drive Test Workspace/a2'
        2. create folder 'Nuxeo Drive Test Workspace/a3'
        """

        self.engine_1.start()
        self.wait_sync()
        local = self.local_1

        # Create  folder a1
        self.folder_path_1 = local.make_folder("/", "a1")

        # Add 100 files in folder 'Nuxeo Drive Test Workspace/a1'
        for file_num in range(1, self.NUMBER_OF_LOCAL_FILES + 1):
            local.make_file(
                self.folder_path_1, "local%04d.txt" % file_num, content=b"content"
            )

        # Create  folder a2
        self.folder_path_2 = local.make_folder("/", "a2")
        self.folder_path_3 = Path("a3")
        self.wait_sync(wait_for_async=True, timeout=self.SYNC_TIMEOUT)

    def test_move_and_copy_paste_folder_original_location_from_child_stopped(self):
        self._move_and_copy_paste_folder_original_location_from_child()

    def test_move_and_copy_paste_folder_original_location_from_child(self):
        self._move_and_copy_paste_folder_original_location_from_child(False)

    def _move_and_copy_paste_folder_original_location_from_child(self, stopped=True):
        local = self.local_1
        src = local.abspath(self.folder_path_1)
        dst = local.abspath(self.folder_path_2)
        shutil.move(src, dst)
        self.wait_sync(timeout=self.SYNC_TIMEOUT)
        self._move_and_copy_paste_folder(
            Path("a2/a1"), Path(""), Path("a2"), stopped=stopped
        )

    def _move_and_copy_paste_folder(
        self, folder_1: Path, folder_2: Path, target_folder: Path, stopped=True
    ):
        """
        /folder_1
        /folder_2
        /target_folder
        Will
        move /folder1 inside /folder2/ as /folder2/folder1
        copy /folder2/folder1 into /target_folder/
        """
        if stopped:
            self.engine_1.stop()
        remote = self.remote_1
        local = self.local_1
        src = local.abspath(folder_1)
        dst = local.abspath(folder_2)
        new_path = folder_2 / folder_1.name
        copy_path = target_folder / folder_1.name
        shutil.move(src, dst)
        # check that 'Nuxeo Drive Test Workspace/a1' does not exist anymore
        assert not local.exists(folder_1)
        # check that 'Nuxeo Drive Test Workspace/a2/a1' now exists
        assert local.exists(new_path)
        # copy the 'Nuxeo Drive Test Workspace/a2/a1' tree
        # back under 'Nuxeo Drive Test Workspace'
        shutil.copytree(local.abspath(new_path), local.abspath(copy_path))
        if stopped:
            self.engine_1.start()
        self.wait_sync(timeout=self.SYNC_TIMEOUT)

        # asserts
        # expect '/a2/a1' to contain the files
        # expect 'Nuxeo Drive Test Workspace/a1' to also contain the files
        num = self.NUMBER_OF_LOCAL_FILES
        names = {"local%04d.txt" % n for n in range(1, num + 1)}

        for path in (new_path, copy_path):
            # Local
            assert local.abspath(path).exists()
            children = [f.name for f in local.abspath(path).iterdir()]

            assert len(children) == num
            assert set(children) == names

            # Remote
            uid = local.get_remote_id(path)
            assert uid

            children = remote.get_fs_children(uid)
            assert len(children) == num
            children_names = {child.name for child in children}
            assert children_names == names

    @pytest.mark.randombug("NXDRIVE-720", condition=LINUX)
    @pytest.mark.randombug("NXDRIVE-813", condition=MAC)
    def test_move_and_copy_paste_folder_original_location(self):
        self._move_and_copy_paste_folder(
            self.folder_path_1,
            self.folder_path_2,
            self.folder_path_1.parent,
            stopped=False,
        )

    @not_linux(
        reason="NXDRIVE-471: Not handled under GNU/Linux as "
        "creation time is not stored"
    )
    def test_move_and_copy_paste_folder_original_location_stopped(self):
        self._move_and_copy_paste_folder(
            self.folder_path_1, self.folder_path_2, self.folder_path_1.parent
        )

    def test_move_and_copy_paste_folder_new_location(self):
        self._move_and_copy_paste_folder(
            self.folder_path_1, self.folder_path_2, self.folder_path_3
        )
