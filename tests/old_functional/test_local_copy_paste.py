import shutil

from .common import FILE_CONTENT, OneUserTest


class TestLocalCopyPaste(OneUserTest):

    NUMBER_OF_LOCAL_TEXT_FILES = 10
    NUMBER_OF_LOCAL_IMAGE_FILES = 10
    NUMBER_OF_LOCAL_FILES_TOTAL = (
        NUMBER_OF_LOCAL_TEXT_FILES + NUMBER_OF_LOCAL_IMAGE_FILES
    )
    FILE_NAME_PATTERN = "file%03d%s"

    """
    1. Create folder "/A" with 100 files in it
    2. Create folder "/B"
    """

    def setUp(self):
        remote = self.remote_1
        local = self.local_1
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.engine_1.stop()
        assert local.exists("/")

        # create  folder A
        local.make_folder("/", "A")
        self.folder_path_1 = "/A"

        # create  folder B
        # NXDRIVE-477 If created after files are created inside A,
        # creation of B isn't detected wy Watchdog!
        # Reproducible with watchdemo, need to investigate.
        # That's why we are now using local scan for setup_method().
        local.make_folder("/", "B")
        self.folder_path_2 = "/B"

        # add text files in folder 'Nuxeo Drive Test Workspace/A'
        self.local_files_list = []
        for file_num in range(1, self.NUMBER_OF_LOCAL_TEXT_FILES + 1):
            filename = self.FILE_NAME_PATTERN % (file_num, ".txt")
            local.make_file(self.folder_path_1, filename, FILE_CONTENT)
            self.local_files_list.append(filename)

        # add image files in folder 'Nuxeo Drive Test Workspace/A'
        abs_folder_path_1 = local.abspath(self.folder_path_1)
        test_doc_path = self.location / "resources" / "files" / "cat.jpg"
        for file_num in range(
            self.NUMBER_OF_LOCAL_TEXT_FILES + 1, self.NUMBER_OF_LOCAL_FILES_TOTAL + 1
        ):
            filename = self.FILE_NAME_PATTERN % (file_num, ".jpg")
            dst_path = abs_folder_path_1 / filename
            shutil.copyfile(test_doc_path, dst_path)
            self.local_files_list.append(filename)

        self.engine_1.start()
        self.wait_sync()
        self.engine_1.stop()

        # get remote folders reference ids
        self.remote_ref_1 = local.get_remote_id(self.folder_path_1)
        assert self.remote_ref_1
        self.remote_ref_2 = local.get_remote_id(self.folder_path_2)
        assert self.remote_ref_2
        assert remote.fs_exists(self.remote_ref_1)
        assert remote.fs_exists(self.remote_ref_2)

        assert (
            len(remote.get_fs_children(self.remote_ref_1))
            == self.NUMBER_OF_LOCAL_FILES_TOTAL
        )

    def test_local_copy_paste_files(self):
        self._local_copy_paste_files()

    def test_local_copy_paste_files_stopped(self):
        self._local_copy_paste_files(stopped=True)

    def _local_copy_paste_files(self, stopped=False):
        if not stopped:
            self.engine_1.start()

        # Copy all children (files) of A to B
        remote = self.remote_1
        local = self.local_1
        src = local.abspath(self.folder_path_1)
        dst = local.abspath(self.folder_path_2)
        num = self.NUMBER_OF_LOCAL_FILES_TOTAL
        expected_files = set(self.local_files_list)

        for f in src.iterdir():
            shutil.copy(f, dst)

        if stopped:
            self.engine_1.start()
        self.wait_sync(timeout=60)

        # Expect local "/A" to contain all the files
        abs_folder_path_1 = local.abspath(self.folder_path_1)
        assert abs_folder_path_1.exists()
        children = [f.name for f in abs_folder_path_1.iterdir()]
        assert len(children) == num
        assert set(children) == expected_files

        # expect local "/B" to contain the same files
        abs_folder_path_2 = local.abspath(self.folder_path_2)
        assert abs_folder_path_2.exists()
        children = [f.name for f in abs_folder_path_2.iterdir()]
        assert len(children) == num
        assert set(children) == expected_files

        # expect remote "/A" to contain all the files
        # just compare the names
        children = [
            remote_info.name
            for remote_info in remote.get_fs_children(self.remote_ref_1)
        ]
        assert len(children) == num
        assert set(children) == expected_files

        # expect remote "/B" to contain all the files
        # just compare the names
        children = [
            remote_info.name
            for remote_info in remote.get_fs_children(self.remote_ref_2)
        ]
        assert len(children) == num
        assert set(children) == expected_files
