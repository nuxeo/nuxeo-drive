import shutil
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from nuxeo.exceptions import Unauthorized

from nxdrive.constants import MAC, WINDOWS

from .. import ensure_no_exception
from .common import FILE_CONTENT, SYNC_ROOT_FAC_ID, OneUserTest


class TestLocalCreations(OneUserTest):
    def test_create_then_rename_local_folder(self):
        """Prevent regressions on fast create-then-rename folder."""
        local = self.local_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Create a local folder, rename it
        local.make_folder("/", "Test folder")
        if WINDOWS:
            # Too fast folder create-then-rename are not well handled
            time.sleep(1)
        local.rename("/Test folder", "Renamed folder")
        assert local.exists("/Renamed folder")

        # Sync and ensure the file is still renamed
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Renamed folder")

        # Ensure the folder is renamed on the server too
        assert not self.engine_1.dao.get_errors()
        children = self.remote_1.get_children_info(self.workspace)
        assert len(children) == 1
        assert children[0].name == "Renamed folder"

    def test_invalid_credentials_on_file_upload(self):
        local = self.local_1
        engine = self.engine_1
        dao = engine.dao

        engine.start()
        self.wait_sync(wait_for_async=True)

        bad_remote = self.get_bad_remote()
        error = Unauthorized(message="Mock")
        bad_remote.make_upload_raise(error)

        file = "Performance Reports - error n°401.txt"

        with patch.object(engine, "remote", new=bad_remote):
            local.make_file("/", file, content=b"something")
            assert local.exists(f"/{file}")
            self.wait_sync()

            remote_ref = local.get_remote_id(f"/{file}")
            assert not remote_ref
            errors = dao.get_errors()
            assert len(errors) == 1
            assert errors[0].last_error == "INVALID_CREDENTIALS"
            assert not self.remote_1.get_children_info(self.workspace)

        # When the credentials are restored, retrying the sync should work
        errors = dao.get_errors()
        engine.retry_pair(errors[0].id)
        self.wait_sync()

        assert not dao.get_errors()
        children = self.remote_1.get_children_info(self.workspace)
        assert len(children) == 1
        assert children[0].name == file
        children = local.get_children_info("/")
        assert len(children) == 1
        assert children[0].name == file

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

    def test_local_create_folders_and_children_files(self):
        """
        1. create folder 'Nuxeo Drive Test Workspace/A' with 100 files in it
        2. create folder 'Nuxeo Drive Test Workspace/B'
        """

        local = self.local_1
        remote = self.remote_1
        len_text_files = 10
        len_pictures = 10
        total_files = len_text_files + len_pictures

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Create the folder A
        local.make_folder("/", "A")

        # Add text files into A
        for file_num in range(len_text_files):
            filename = f"file_{file_num + 1:02d}.txt"
            local.make_file("/A", filename, content=FILE_CONTENT)

        # Add pictures into A
        test_doc_path = self.location / "resources" / "files" / "cat.jpg"
        abs_folder_path_1 = local.abspath("/A")
        for file_num in range(len_text_files, total_files):
            filename = f"file_{file_num + 1:02d}.jpg"
            dst_path = abs_folder_path_1 / filename
            shutil.copyfile(test_doc_path, dst_path)

        # Create the folder B, and sync
        local.make_folder("/", "B")
        self.wait_sync()

        # Get remote folders reference IDs
        remote_ref_1 = local.get_remote_id("/A")
        assert remote_ref_1
        assert remote.fs_exists(remote_ref_1)
        remote_ref_2 = local.get_remote_id("/B")
        assert remote_ref_2
        assert remote.fs_exists(remote_ref_2)

        assert len(remote.get_fs_children(remote_ref_1)) == total_files

    @pytest.mark.timeout(40)
    def test_local_create_folders_upper_lower_cases(self):
        """
        Infinite loop when renaming a folder from lower case to upper case
        on Windows (or more specifically case insensitive OSes).

        We use a special timeout to prevent infinite loops when this test
        fails.  And it should until fixed, but keep it to detect regression.
        """

        remote = self.remote_document_client_1
        local = self.local_1
        engine = self.engine_1

        # Create an innocent folder, lower case
        folder = "abc"
        remote.make_folder("/", folder)
        engine.start()
        self.wait_sync(wait_for_async=True)

        # Check
        assert remote.exists(f"/{folder}")
        assert local.exists(f"/{folder}")

        # Locally rename to upper case.  A possible infinite loop can occur.
        folder_upper = folder.upper()
        local.rename(f"/{folder}", folder_upper)
        self.wait_sync()

        # Checks
        children = remote.get_children_info(self.workspace)
        assert len(children) == 1
        assert children[0].name == folder_upper
        children = local.get_children_info("/")
        assert len(children) == 1
        assert children[0].name == folder_upper

    @pytest.mark.timeout(40)
    def test_local_create_files_upper_lower_cases(self):
        """
        Infinite loop when renaming a file from lower case to upper case
        on Windows (or more specifically case insensitive OSes).

        We use a special timeout to prevent infinite loops when this test
        fails.  And it should until fixed, but keep it to detect regression.
        """

        remote = self.remote_document_client_1
        local = self.local_1
        engine = self.engine_1

        # Create an innocent file, lower case
        filename = "abc.txt"
        remote.make_file_with_blob("/", filename, b"cAsE")
        engine.start()
        self.wait_sync(wait_for_async=True)

        # Check
        assert remote.exists(f"/{filename}")
        assert local.exists(f"/{filename}")

        # Locally rename to upper case.  A possible infinite loop can occur.
        filename_upper = filename.upper()
        local.rename(f"/{filename}", filename_upper)
        self.wait_sync()

        # Checks
        children = remote.get_children_info(self.workspace)
        assert len(children) == 1
        assert children[0].name == filename_upper
        children = local.get_children_info("/")
        assert len(children) == 1
        assert children[0].name == filename_upper

    def test_local_create_folders_with_dots(self):
        """Check that folders containing dots are well synced."""

        remote = self.remote_document_client_1
        local = self.local_1
        engine = self.engine_1

        engine.start()
        self.wait_sync(wait_for_async=True)

        folder1 = "Affaire.1487689320370"
        folder2 = "Affaire.1487689320.370"
        local.make_folder("/", folder1)
        local.make_folder("/", folder2)
        self.wait_sync()

        # Check
        assert remote.exists(f"/{folder1}")
        assert remote.exists(f"/{folder2}")
        assert local.exists(f"/{folder1}")
        assert local.exists(f"/{folder2}")

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

    def test_local_modification_date_non_latin(self):
        """Check that non-latin files have the Platform modification date."""
        remote = self.remote_document_client_1
        local = self.local_1
        engine = self.engine_1

        filename = "abc こん ツリー.txt"
        content = filename.encode("utf-8")
        remote.make_file("/", filename, content=content)
        remote_mtime = time.time()

        time.sleep(3)

        engine.start()
        self.wait_sync(wait_for_async=True)

        filename = f"/{filename}"
        assert local.exists(filename)
        assert local.abspath(filename).stat().st_mtime < remote_mtime

    def test_local_modification_date_kanjis_file(self):
        """Check that Kanjis files have the Platform modification date."""
        remote = self.remote_1
        local = self.local_1
        engine = self.engine_1

        workspace_id = f"{SYNC_ROOT_FAC_ID}{self.workspace}"
        name = "東京スカイツリー.jpg"
        filepath = self.location / "resources" / "files" / name
        remote.stream_file(workspace_id, filepath)
        remote_mtime = time.time()

        time.sleep(3)

        engine.start()
        self.wait_sync(wait_for_async=True)

        filename = f"/{name}"
        assert local.exists(filename)
        assert local.abspath(filename).stat().st_mtime < remote_mtime + 0.5

    def test_local_modification_date_hiraganas_file(self):
        """Check that Hiraganas files have the Platform modification date."""
        remote = self.remote_1
        local = self.local_1
        engine = self.engine_1

        workspace_id = f"{SYNC_ROOT_FAC_ID}{self.workspace}"
        name = "こんにちは.jpg"
        filepath = self.location / "resources" / "files" / name
        remote.stream_file(workspace_id, filepath)
        remote_mtime = time.time()

        time.sleep(3)

        engine.start()
        self.wait_sync(wait_for_async=True)

        filename = f"/{name}"
        assert local.exists(filename)
        assert local.abspath(filename).stat().st_mtime < remote_mtime + 0.5

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

    def test_local_creation_date_kanjis_file(self):
        """Check that Kanjis files have the Platform modification date."""
        remote = self.remote_1
        local = self.local_1
        engine = self.engine_1
        sleep_time = 3

        workspace_id = f"{SYNC_ROOT_FAC_ID}{self.workspace}"
        name = "東京スカイツリー.jpg"
        filename = self.location / "resources" / "files" / name
        file_id = remote.stream_file(workspace_id, filename).uid
        after_ctime = time.time()

        time.sleep(sleep_time)
        filename = f"a {name}"
        remote.rename(file_id, filename)
        after_mtime = time.time()

        engine.start()
        self.wait_sync(wait_for_async=True)

        file = f"/a {name}"
        assert local.exists(file)
        file = local.abspath(file)
        stats = file.stat()
        local_mtime = stats.st_mtime

        # Note: GNU/Linux does not have a creation time
        if MAC or WINDOWS:
            local_ctime = stats.st_birthtime if MAC else stats.st_ctime
            assert local_ctime < after_ctime
            assert local_ctime + sleep_time <= local_mtime

        assert local_mtime < after_mtime + 0.5

    def test_local_creation_date_hiraganas_file(self):
        """Check that Hiraganas files have the Platform modification date."""
        remote = self.remote_1
        local = self.local_1
        engine = self.engine_1
        sleep_time = 3

        workspace_id = f"{SYNC_ROOT_FAC_ID}{self.workspace}"
        name = "こんにちは.jpg"
        filename = self.location / "resources" / "files" / name
        file_id = remote.stream_file(workspace_id, filename).uid
        after_ctime = time.time()

        time.sleep(sleep_time)
        filename = f"a {name}"
        remote.rename(file_id, filename)
        after_mtime = time.time()

        engine.start()
        self.wait_sync(wait_for_async=True)

        file = f"/a {name}"
        assert local.exists(file)
        file = local.abspath(file)
        stats = file.stat()
        local_mtime = stats.st_mtime

        # Note: GNU/Linux does not have a creation time
        if MAC or WINDOWS:
            local_ctime = stats.st_birthtime if MAC else stats.st_ctime
            assert local_ctime < after_ctime
            assert local_ctime + sleep_time <= local_mtime

        assert local_mtime < after_mtime + 0.5

    def test_local_file_creation_on_file_not_found(self):
        """
        When the NotFound error is raised during the processing of a file that has a valid uid,
        it seems that the code to synchronize locally created file doesn't discard the entry
        from the processing queue. Instead, it adds it back in. We end up with the processor
        looping over the same NotFound file over and over again.

        This happened when editing a Bar.md file with XCode, which briefly created Bar~.md
        during the save process. The Bar~.md apparently has the same xattrs, and it causes the loop.
        """
        local = self.local_1
        remote = self.remote_1
        engine = self.engine_1

        engine.start()
        self.wait_sync(wait_for_async=True)

        # Create a file to have a valid UID
        local.make_file("/", "Bar.md", content=b"bla bla bla")
        self.wait_sync()
        assert remote.exists("/Bar.md")

        # Craft the "Bar~.md" file creation based on real data from "Bar.md"
        info = local.get_info("/Bar.md")
        info.name = "Bar~.md"
        info.path = Path(self.workspace_title) / "Bar~.md"
        info.filepath = info.filepath.with_name("Bar~.md")
        engine.dao.insert_local_state(info, Path(f"/{self.workspace_title}"))

        # Wait and check
        self.wait_sync()
        assert not engine.dao.get_errors()

    def test_local_creation_with_obsolete_xattr(self):
        """
        When a local file/folder has an old remote ref stored in its xattr,
        the sync should be done without error.
        """
        local = self.local_1
        remote = self.remote_1
        engine = self.engine_1

        engine.start()
        self.wait_sync(wait_for_async=True)

        # Stop the engine to be able to alter xattrs before the Processor handles it
        engine.stop()

        # Create a file with an invalid remote ref
        file = local.make_file("/", "obsolete.md", content=b"bla bla bla")
        local.set_path_remote_id(local.abspath(file), "obsolete#remote-ref-file")

        # Create a folder with an invalid remote ref
        folder = local.make_folder("/", "obsolete")
        local.set_path_remote_id(local.abspath(folder), "obsolete#remote-ref-folder")

        with ensure_no_exception():
            engine.start()
            self.wait_sync()

        assert not engine.dao.get_errors()
        assert remote.exists("/obsolete.md")
        assert remote.exists("/obsolete")

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

    def test_local_creation_with_files_existant_without_xattrs(self):
        """NXDRIVE-1882: Recovery test with purgation of attrs."""
        self.recovery_scenario(cleanup=True)

    def test_local_creation_with_files_existant_with_xattr(self):
        """NXDRIVE-1882: Recovery test without purgation of attrs."""
        self.recovery_scenario(cleanup=False)
