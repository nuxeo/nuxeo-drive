import shutil
import tempfile
from pathlib import Path

from nxdrive.utils import normalized_path

from .common import FILE_CONTENT, OneUserTest

TEST_TIMEOUT = 60


class TestLocalPaste(OneUserTest):

    NUMBER_OF_LOCAL_FILES = 25
    TEMP_FOLDER = "temp_folder"
    FOLDER_A1 = Path("a1")
    FOLDER_A2 = Path("a2")
    FILENAME_PATTERN = "file%03d.txt"

    def setUp(self):
        """
        1. create folder 'temp/a1' with more than 20 files in it
        2. create folder 'temp/a2', empty
        3. copy 'a1' and 'a2', in this order to the test sync root
        4. repeat step 3, but copy 'a2' and 'a1', in this order
        (to the test sync root)
        5. Verify that both folders and their content is sync to DM,
        in both steps 3 and 4
        """

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        local = self.local_1
        assert local.exists("/")
        self.workspace_abspath = local.abspath("/")

        # Create  folder a1 and a2 under a temp folder
        self.local_temp = normalized_path(tempfile.mkdtemp(self.TEMP_FOLDER))
        self.folder1 = self.local_temp / self.FOLDER_A1
        self.folder1.mkdir(parents=True)
        self.folder2 = self.local_temp / self.FOLDER_A2
        self.folder2.mkdir(parents=True)

        # Add files in folder 'temp/a1'
        for file_num in range(1, self.NUMBER_OF_LOCAL_FILES + 1):
            filename = self.FILENAME_PATTERN % file_num
            (self.folder1 / filename).write_bytes(FILE_CONTENT)

    def tearDown(self):
        shutil.rmtree(self.local_temp)

    def test_copy_paste_empty_folder_first(self):
        """
        copy 'a2' to 'Nuxeo Drive Test Workspace',
        then 'a1' to 'Nuxeo Drive Test Workspace'
        """
        # copy 'temp/a2' under 'Nuxeo Drive Test Workspace'
        shutil.copytree(self.folder2, self.workspace_abspath / self.FOLDER_A2)
        # copy 'temp/a1' under 'Nuxeo Drive Test Workspace'
        shutil.copytree(self.folder1, self.workspace_abspath / self.FOLDER_A1)
        self.wait_sync(timeout=TEST_TIMEOUT)

        self._check_integrity()

    def test_copy_paste_empty_folder_last(self):
        """
        copy 'a1' to 'Nuxeo Drive Test Workspace',
        then 'a2' to 'Nuxeo Drive Test Workspace'
        """
        # copy 'temp/a1' under 'Nuxeo Drive Test Workspace'
        shutil.copytree(self.folder1, self.workspace_abspath / self.FOLDER_A1)
        # copy 'temp/a2' under 'Nuxeo Drive Test Workspace'
        shutil.copytree(self.folder2, self.workspace_abspath / self.FOLDER_A2)
        self.wait_sync(timeout=TEST_TIMEOUT)

        self._check_integrity()

    def _check_integrity(self):
        local = self.local_1
        remote = self.remote_1
        num = self.NUMBER_OF_LOCAL_FILES
        # check that '/Nuxeo Drive Test Workspace/a1' does exist
        assert local.exists(self.FOLDER_A1)
        # check that '/Nuxeo Drive Test Workspace/a2' does exist
        assert local.exists(self.FOLDER_A2)
        # check that '/Nuxeo Drive Test Workspace/a1/ has all the files
        children = list((self.workspace_abspath / self.FOLDER_A1).iterdir())
        assert len(children) == num
        # check that remote (DM) 'Nuxeo Drive Test Workspace/a1' exists
        remote_ref_1 = local.get_remote_id(self.FOLDER_A1)
        assert remote.fs_exists(remote_ref_1)
        # check that remote (DM) 'Nuxeo Drive Test Workspace/a2' exists
        remote_ref_2 = local.get_remote_id(self.FOLDER_A2)
        assert remote.fs_exists(remote_ref_2)
        # check that remote (DM) 'Nuxeo Drive Test Workspace/a1'
        # has all the files
        children = [
            remote_info.name for remote_info in remote.get_fs_children(remote_ref_1)
        ]
        assert len(children) == num

    def test_copy_paste_same_file(self):
        local = self.local_1
        remote = self.remote_1
        name = self.FILENAME_PATTERN % 1
        workspace_abspath = local.abspath("/")
        path = self.FOLDER_A1 / name
        copypath = self.FOLDER_A1 / f"{name}copy"
        # copy 'temp/a1' under 'Nuxeo Drive Test Workspace'
        (workspace_abspath / self.FOLDER_A1).mkdir()
        shutil.copy2(self.folder1 / name, workspace_abspath / path)

        self.wait_sync(timeout=TEST_TIMEOUT)

        # check that '/Nuxeo Drive Test Workspace/a1' does exist
        assert local.exists(self.FOLDER_A1)
        # check that '/Nuxeo Drive Test Workspace/a1/ has all the files
        children = list((self.workspace_abspath / self.FOLDER_A1).iterdir())
        assert len(children) == 1
        # check that remote (DM) 'Nuxeo Drive Test Workspace/a1' exists
        remote_ref = local.get_remote_id(self.FOLDER_A1)
        assert remote.fs_exists(remote_ref)
        remote_children = [
            remote_info.name for remote_info in remote.get_fs_children(remote_ref)
        ]
        assert len(remote_children) == 1
        remote_id = local.get_remote_id(path)

        shutil.copy2(local.abspath(path), local.abspath(copypath))
        local.set_remote_id(copypath, remote_id)
        self.wait_sync(timeout=TEST_TIMEOUT)
        remote_children = [
            remote_info.name for remote_info in remote.get_fs_children(remote_ref)
        ]
        assert len(remote_children) == 2
        children = list((self.workspace_abspath / self.FOLDER_A1).iterdir())
        assert len(children) == 2
