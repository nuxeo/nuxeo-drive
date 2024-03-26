import shutil
import time
from pathlib import Path
from unittest.mock import patch

from nxdrive.constants import MAC, WINDOWS

from .. import ensure_no_exception
from .conftest import SYNC_ROOT_FAC_ID, OneUserTest


class TestLocalCreations(OneUserTest):
    def test_mini_scenario(self):
        local = self.local_root_client_1
        remote = self.remote_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        local.make_folder(f"/{self.workspace_title}", "A")
        folder_path_1 = f"{self.workspace_title}/A"

        test_doc_path = self.location / "resources" / "files" / "cat.jpg"
        abs_folder_path_1 = local.abspath(f"/{folder_path_1}")
        dst_path = abs_folder_path_1 / "cat.jpg"
        shutil.copyfile(test_doc_path, dst_path)

        self.wait_sync(timeout=100)
        uid = local.get_remote_id(f"/{folder_path_1}/cat.jpg")
        assert remote.fs_exists(uid)

    def test_local_modification_date(self):
        """Check that the files have the Platform modification date."""
        remote = self.remote_document_client_1
        local = self.local_1
        engine = self.engine_1

        filename = "abc.txt"
        remote.make_file("/", filename, content=b"1234")
        remote_mtime = time.time()

        time.sleep(3)

        engine.start()
        self.wait_sync(wait_for_async=True)

        filename = f"/{filename}"
        assert local.exists(filename)
        assert local.abspath(filename).stat().st_mtime < remote_mtime

    def test_local_creation_date(self):
        """Check that the files have the Platform modification date."""
        remote = self.remote_1
        local = self.local_1
        engine = self.engine_1
        sleep_time = 3

        workspace_id = f"{SYNC_ROOT_FAC_ID}{self.workspace}"
        filename = "abc.txt"
        file_id = remote.make_file(workspace_id, filename, content=b"1234").uid
        after_ctime = time.time()

        time.sleep(sleep_time)
        filename = f"a{filename}"
        remote.rename(file_id, filename)
        after_mtime = time.time()

        engine.start()
        self.wait_sync(wait_for_async=True)

        filename = f"/{filename}"
        assert local.exists(filename)
        stats = local.abspath(filename).stat()
        local_mtime = stats.st_mtime

        # Note: GNU/Linux does not have a creation time
        if MAC or WINDOWS:
            local_ctime = stats.st_birthtime if MAC else stats.st_ctime
            assert local_ctime < after_ctime
            assert local_ctime + sleep_time <= local_mtime

        assert local_mtime < after_mtime + 0.5

    def recovery_scenario(self, cleanup: bool = True):
        """
        A recovery test, scenario:
            1. Add a new account using the foo folder.
            2. Remove the account, keep the foo folder as-is.
            3. Remove xattrs using the clean-folder CLI argument (if *cleanup* is True).
            4. Re-add the account using the foo folder.

        The goal is to check that local data is not re-downloaded at all.
        Drive should simply recreate the database and check the all files are there.
        """
        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Create folders and files on the server
        workspace_id = f"{SYNC_ROOT_FAC_ID}{self.workspace}"
        folder_uid = self.remote_1.make_folder(workspace_id, "a folder").uid
        self.remote_1.make_file(folder_uid, "file1.bin", content=b"0321" * 42)
        self.remote_1.make_file(folder_uid, "file2.bin", content=b"12365" * 42)
        self.remote_1.make_folder(folder_uid, "folder 2")

        # Start engine and wait for synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Local checks
        assert self.local_1.exists("/a folder")
        assert self.local_1.exists("/a folder/file1.bin")
        assert self.local_1.exists("/a folder/file2.bin")
        assert self.local_1.exists("/a folder/folder 2")

        # Stop the engine for following actions
        self.engine_1.stop()

        if cleanup:
            # Remove xattrs
            folder = Path("a folder")
            self.local_1.clean_xattr_folder_recursive(folder, cleanup=True)
            self.local_1.remove_remote_id(folder, cleanup=True)

            # Ensure xattrs are gone
            assert not self.local_1.get_remote_id(folder)
            assert not self.local_1.get_remote_id(folder / "file1.bin")
            assert not self.local_1.get_remote_id(folder / "file2.bin")
            assert not self.local_1.get_remote_id(folder / "folder 2")

        # Destroy the database but keep synced files
        self.unbind_engine(1, purge=False)

        def download(*_, **__):
            """
            Patch Remote.download() to be able to check that nothing
            will be downloaded as local data is already there.
            """
            assert 0, "No download should be done!"

        # Re-bind the account using the same folder
        self.bind_engine(1, start_engine=False)

        # Start the sync
        with patch.object(self.engine_1.remote, "download", new=download):
            with ensure_no_exception():
                self.engine_1.start()
                self.wait_sync(wait_for_async=True)

        # No error expected
        assert not self.engine_1.dao.get_errors(limit=0)

        # Checks
        for client in (self.local_1, self.remote_1):
            assert client.exists("/a folder")
            assert client.exists("/a folder/file1.bin")
            assert client.exists("/a folder/file2.bin")
            assert client.exists("/a folder/folder 2")
