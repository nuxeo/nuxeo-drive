import shutil
import time
from pathlib import Path
from time import sleep
from unittest.mock import patch

import pytest
from nuxeo.exceptions import HTTPError

from nxdrive.dao.engine import EngineDAO

from .. import ensure_no_exception, env
from . import DocRemote, LocalTest
from .common import OS_STAT_MTIME_RESOLUTION, OneUserTest

# TODO NXDRIVE-170: refactor


class TestLocalMoveAndRename(OneUserTest):
    def setUp(self):
        """
        Sets up the following local hierarchy:
        Nuxeo Drive Test Workspace
           |-- Original File 1.txt
           |-- Original File 2.txt
           |-- Original Folder 1
           |       |-- Sub-Folder 1.1
           |       |-- Sub-Folder 1.2
           |       |-- Original File 1.1.txt
           |-- Original Folder 2
           |       |-- Original File 3.txt
        """

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        local = self.local_1
        local.make_file("/", "Original File 1.txt", content=b"Some Content 1")
        local.make_file("/", "Original File 2.txt", content=b"Some Content 2")

        local.make_folder("/", "Original Folder 1")
        local.make_folder("/Original Folder 1", "Sub-Folder 1.1")
        local.make_folder("/Original Folder 1", "Sub-Folder 1.2")

        # Same content as OF1
        local.make_file(
            "/Original Folder 1", "Original File 1.1.txt", content=b"Some Content 1"
        )

        local.make_folder("/", "Original Folder 2")
        local.make_file(
            "/Original Folder 2", "Original File 3.txt", content=b"Some Content 3"
        )
        self.wait_sync()

    def test_local_rename_folder_while_creating(self):
        local = self.local_1
        root_local = self.local_root_client_1
        remote = self.remote_document_client_1
        marker = False

        def update_remote_state(row, *args, **kwargs):
            nonlocal marker
            EngineDAO.update_remote_state(self.engine_1.dao, row, *args, **kwargs)
            if row.local_name == "New Folder" and not marker:
                root_local.rename(row.local_path, "Renamed Folder")
                marker = True

        with patch.object(
            self.engine_1.dao, "update_remote_state", new=update_remote_state
        ):
            local.make_folder("/", "New Folder")
            self.wait_sync(fail_if_timeout=False)

            assert local.exists("/Renamed Folder")
            assert not local.exists("/New Folder")

            # Path is updated on Nuxeo
            info = remote.get_info("/Renamed Folder")
            assert info.name == "Renamed Folder"
            assert len(local.get_children_info("/")) == 5
            assert len(remote.get_children_info(self.workspace)) == 5

    def test_local_rename_file_while_creating(self):
        local = self.engine_1.local
        remote = self.remote_document_client_1
        marker = False

        def set_remote_id(ref: Path, remote_id: bytes, name: str = "ndrive"):
            nonlocal local, marker
            LocalTest.set_remote_id(local, ref, remote_id, name=name)
            if not marker and ref.name == "File.txt":
                local.rename(ref, "Renamed File.txt")
                marker = True

        with patch.object(self.engine_1.local, "set_remote_id", new=set_remote_id):
            self.local_1.make_file("/", "File.txt", content=b"Some Content 2")
            self.wait_sync(fail_if_timeout=False)

            local = self.local_1
            assert local.exists("/Renamed File.txt")
            assert not local.exists("/File.txt")

            # Path is updated on Nuxeo
            info = remote.get_info("/Renamed File.txt")
            assert info.name == "Renamed File.txt"
            assert len(local.get_children_info("/")) == 5
            assert len(remote.get_children_info(self.workspace)) == 5

    @pytest.mark.randombug("NXDRIVE-811", condition=True, mode="REPEAT")
    def test_local_rename_file_while_creating_before_marker(self):
        local = self.local_1
        remote = self.remote_document_client_1
        marker = False

        def set_remote_id(ref: Path, remote_id: bytes, name: str = "ndrive"):
            nonlocal local, marker
            if not marker and ref.name == "File.txt":
                self.engine_1.local.rename(ref, "Renamed File.txt")
                marker = True
            LocalTest.set_remote_id(local, ref, remote_id, name=name)

        with patch.object(self.engine_1.local, "set_remote_id", new=set_remote_id):
            local.make_file("/", "File.txt", content=b"Some Content 2")
            self.wait_sync(fail_if_timeout=False)

            assert local.exists("/Renamed File.txt")
            assert not local.exists("/File.txt")

            # Path is updated on Nuxeo
            info = remote.get_info("/Renamed File.txt")
            assert info.name == "Renamed File.txt"
            assert len(local.get_children_info("/")) == 5
            assert len(remote.get_children_info(self.workspace)) == 5

    def test_local_rename_file_while_creating_after_marker(self):
        marker = False
        local = self.local_1
        remote = self.remote_document_client_1

        def update_remote_state(row, *args, **kwargs):
            nonlocal marker
            EngineDAO.update_remote_state(self.engine_1.dao, row, *args, **kwargs)
            if not marker and row.local_name == "File.txt":
                self.engine_1.local.rename(row.local_path, "Renamed File.txt")
                marker = True

        with patch.object(
            self.engine_1.dao, "update_remote_state", new=update_remote_state
        ):
            local.make_file("/", "File.txt", content=b"Some Content 2")
            self.wait_sync(fail_if_timeout=False)

            assert local.exists("/Renamed File.txt")
            assert not local.exists("/File.txt")

            # Path is updated on Nuxeo
            info = remote.get_info("/Renamed File.txt")
            assert info.name == "Renamed File.txt"
            assert len(local.get_children_info("/")) == 5
            assert len(remote.get_children_info(self.workspace)) == 5

    def test_replace_file(self):
        local = self.local_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        uid = local.get_remote_id("/Original File 1.txt")
        local.remove_remote_id("/Original File 1.txt")
        local.update_content("/Original File 1.txt", b"plop")
        self.wait_sync(fail_if_timeout=False)
        assert local.get_remote_id("/Original File 1.txt") == uid

    def test_local_rename_file(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        uid_1 = remote.get_info("/Original File 1.txt").uid
        local.rename("/Original File 1.txt", "Renamed File 1.txt")
        assert not local.exists("/Original File 1.txt")
        assert local.exists("/Renamed File 1.txt")

        self.wait_sync()
        assert not local.exists("/Original File 1.txt")
        assert local.exists("/Renamed File 1.txt")
        assert remote.get_info(uid_1).name == "Renamed File 1.txt"

        # Rename 'Renamed File 1.txt' to 'Renamed Again File 1.txt'
        # and 'Original File 1.1.txt' to
        # 'Renamed File 1.1.txt' at the same time as they share
        # the same digest but do not live in the same folder
        uid_1_1 = remote.get_info("/Original Folder 1/Original File 1.1.txt").uid
        local.rename(
            "/Original Folder 1/Original File 1.1.txt", "Renamed File 1.1 \xe9.txt"
        )
        assert not local.exists("/Original Folder 1/Original File 1.1.txt")
        assert local.exists("/Original Folder 1/Renamed File 1.1 \xe9.txt")
        local.rename("/Renamed File 1.txt", "Renamed Again File 1.txt")
        assert not local.exists("/Renamed File 1.txt")
        assert local.exists("/Renamed Again File 1.txt")

        self.wait_sync()
        assert not local.exists("/Renamed File 1.txt")
        assert local.exists("/Renamed Again File 1.txt")
        assert not local.exists("/Original Folder 1/Original File 1.1.txt")
        assert local.exists("/Original Folder 1/Renamed File 1.1 \xe9.txt")

        info_1 = remote.get_info(uid_1)
        assert info_1.name == "Renamed Again File 1.txt"

        # User 1 does not have the rights to see the parent container
        # of the test workspace, hence set fetch_parent_uid=False
        parent_1 = remote.get_info(info_1.parent_uid, fetch_parent_uid=False)
        assert parent_1.name == self.workspace_title

        info_1_1 = remote.get_info(uid_1_1)
        assert info_1_1.name == "Renamed File 1.1 \xe9.txt"

        parent_1_1 = remote.get_info(info_1_1.parent_uid)
        assert parent_1_1.name == "Original Folder 1"
        assert len(local.get_children_info("/Original Folder 1")) == 3
        assert len(remote.get_children_info(info_1_1.parent_uid)) == 3
        assert len(local.get_children_info("/")) == 4
        assert len(remote.get_children_info(self.workspace)) == 4

    def test_local_rename_file_uppercase_stopped(self):
        local = self.local_1
        remote = self.remote_document_client_1
        self.engine_1.stop()

        # Rename /Original File 1.txt to /Renamed File 1.txt

        # Rename 'Renamed File 1.txt' to 'Renamed Again File 1.txt'
        # and 'Original File 1.1.txt' to
        # 'Renamed File 1.1.txt' at the same time as they share
        # the same digest but do not live in the same folder
        uid = remote.get_info("/Original Folder 1/Original File 1.1.txt").uid
        local.rename(
            "/Original Folder 1/Original File 1.1.txt", "original File 1.1.txt"
        )

        self.engine_1.start()
        self.wait_sync()

        info = remote.get_info(uid)
        assert info.name == "original File 1.1.txt"

        parent_info = remote.get_info(info.parent_uid)
        assert parent_info.name == "Original Folder 1"
        assert len(local.get_children_info("/Original Folder 1")) == 3
        assert len(remote.get_children_info(info.parent_uid)) == 3

    def test_local_rename_file_uppercase(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt

        # Rename 'Renamed File 1.txt' to 'Renamed Again File 1.txt'
        # and 'Original File 1.1.txt' to
        # 'Renamed File 1.1.txt' at the same time as they share
        # the same digest but do not live in the same folder
        uid = remote.get_info("/Original Folder 1/Original File 1.1.txt").uid
        local.rename(
            "/Original Folder 1/Original File 1.1.txt", "original File 1.1.txt"
        )

        self.wait_sync()

        info = remote.get_info(uid)
        assert info.name == "original File 1.1.txt"

        parent_info = remote.get_info(info.parent_uid)
        assert parent_info.name == "Original Folder 1"
        assert len(local.get_children_info("/Original Folder 1")) == 3
        assert len(remote.get_children_info(info.parent_uid)) == 3

    def test_local_move_file(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # "/Original File 1.txt" -> "/Original Folder 1/Original File 1.txt"
        uid = remote.get_info("/Original File 1.txt").uid
        local.move("/Original File 1.txt", "/Original Folder 1")
        assert not local.exists("/Original File 1.txt")
        assert local.exists("/Original Folder 1/Original File 1.txt")

        self.wait_sync()
        assert not local.exists("/Original File 1.txt")
        assert local.exists("/Original Folder 1/Original File 1.txt")

        info = remote.get_info(uid)
        assert info.name == "Original File 1.txt"
        parent_info = remote.get_info(info.parent_uid)
        assert parent_info.name == "Original Folder 1"
        assert len(local.get_children_info("/Original Folder 1")) == 4
        assert len(remote.get_children_info(info.parent_uid)) == 4
        assert len(local.get_children_info("/")) == 3
        assert len(remote.get_children_info(self.workspace)) == 3

    def test_local_move_file_rollback(self):
        """Test a local move into a folder that is not allowed on the server,
        and so we locally revert/cancel the move.
        Sometimes the rollback itself is canceled because the doc pair has
        no a remote name. The cause is not yet known.
        We would then end on such errors (see NXDRIVE-1952):

            # Nuxeo Drive <= 4.2.0
            AttributeError: 'NoneType' object has no attribute 'rstrip'
            File "engine/processor.py", line 1383, in _handle_failed_remote_rename
            File "client/local_client.py", line 629, in rename
            File "utils.py", line 569, in safe_os_filename
            File "utils.py", line 555, in safe_filename

        Or even:

            # Nuxeo Drive > 4.2.0
            TypeError: expected string or bytes-like object
            File "engine/processor.py", line 1462, in _handle_failed_remote_rename
            File "client/local/base.py", line 458, in rename
            File "utils.py", line 622, in safe_os_filename
            File "utils.py", line 607, in safe_filename
            File ".../re.py", line 192, in sub
        """
        local = self.local_1

        # Move "/Original File 1.txt" -> "/Original Folder 1/Original File 1.txt"
        local.move("/Original File 1.txt", "/Original Folder 1")
        # And change the file name too
        local.rename(
            "/Original Folder 1/Original File 1.txt", "Original File 1-ren.txt"
        )
        # Checks
        assert not local.exists("/Original File 1.txt")
        assert not local.exists("/Original Folder 1/Original File 1.txt")
        assert local.exists("/Original Folder 1/Original File 1-ren.txt")

        def rename(*args, **kwargs):
            raise ValueError("Mock'ed rename error")

        def allow_rollback(*args, **kwargs):
            """Allow rollback on all OSes."""
            return True

        with patch.object(self.engine_1.remote, "rename", new=rename):
            with patch.object(self.engine_1, "local_rollback", new=allow_rollback):
                with ensure_no_exception():
                    self.wait_sync()

        # The file has been moved again to its original location
        assert not local.exists("/Original File 1.txt")
        assert not local.exists("/Original File 1-ren.txt")
        assert not local.exists("/Original Folder 1/Original File 1-ren.txt")
        assert local.exists("/Original Folder 1/Original File 1.txt")
        assert not self.engine_1.dao.get_errors(limit=0)

    def test_local_move_and_rename_file(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Rename /Original File 1.txt to /Renamed File 1.txt
        uid = remote.get_info("/Original File 1.txt").uid

        local.move(
            "/Original File 1.txt", "/Original Folder 1", name="Renamed File 1 \xe9.txt"
        )
        assert not local.exists("/Original File 1.txt")
        assert local.exists("/Original Folder 1/Renamed File 1 \xe9.txt")

        self.wait_sync()
        assert not local.exists("/Original File 1.txt")
        assert local.exists("/Original Folder 1/Renamed File 1 \xe9.txt")

        info = remote.get_info(uid)
        assert info.name == "Renamed File 1 \xe9.txt"
        parent_info = remote.get_info(info.parent_uid)
        assert parent_info.name == "Original Folder 1"
        assert len(local.get_children_info("/Original Folder 1")) == 4
        assert len(remote.get_children_info(info.parent_uid)) == 4
        assert len(local.get_children_info("/")) == 3
        assert len(remote.get_children_info(self.workspace)) == 3

    def test_local_rename_folder(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Save the uid of some files and folders prior to renaming
        folder_1 = remote.get_info("/Original Folder 1").uid
        file_1_1 = remote.get_info("/Original Folder 1/Original File 1.1.txt").uid
        folder_1_1 = remote.get_info("/Original Folder 1/Sub-Folder 1.1").uid

        # Rename a non empty folder with some content
        local.rename("/Original Folder 1", "Renamed Folder 1 \xe9")
        assert not local.exists("/Original Folder 1")
        assert local.exists("/Renamed Folder 1 \xe9")

        # Synchronize: only the folder renaming is detected: all
        # the descendants are automatically realigned
        self.wait_sync()

        # The server folder has been renamed: the uid stays the same
        assert remote.get_info(folder_1).name == "Renamed Folder 1 \xe9"

        # The content of the renamed folder is left unchanged
        file_info = remote.get_info(file_1_1)
        assert file_info.name == "Original File 1.1.txt"
        assert file_info.parent_uid == folder_1

        folder_info = remote.get_info(folder_1_1)
        assert folder_info.name == "Sub-Folder 1.1"
        assert folder_info.parent_uid == folder_1

        assert len(local.get_children_info("/Renamed Folder 1 \xe9")) == 3
        assert len(remote.get_children_info(file_info.parent_uid)) == 3
        assert len(local.get_children_info("/")) == 4
        assert len(remote.get_children_info(self.workspace)) == 4

    def test_local_rename_folder_while_suspended(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Save the uid of some files and folders prior to renaming
        folder_1 = remote.get_info("/Original Folder 1").uid
        file_1_1 = remote.get_info("/Original Folder 1/Original File 1.1.txt").uid
        folder_1_1 = remote.get_info("/Original Folder 1/Sub-Folder 1.1").uid
        count = len(local.get_children_info("/Original Folder 1"))
        self.engine_1.suspend()

        # Rename a non empty folder with some content
        local.rename("/Original Folder 1", "Renamed Folder 1 \xe9")
        assert not local.exists("/Original Folder 1")
        assert local.exists("/Renamed Folder 1 \xe9")

        local.rename("/Renamed Folder 1 \xe9/Sub-Folder 1.1", "Sub-Folder 2.1")
        assert local.exists("/Renamed Folder 1 \xe9/Sub-Folder 2.1")

        # Same content as OF1
        local.make_file("/Renamed Folder 1 \xe9", "Test.txt", content=b"Some Content 1")
        count += 1
        self.engine_1.resume()
        # Synchronize: only the folder renaming is detected: all
        # the descendants are automatically realigned
        self.wait_sync(wait_for_async=True)

        # The server folder has been renamed: the uid stays the same
        assert remote.get_info(folder_1).name == "Renamed Folder 1 \xe9"

        # The content of the renamed folder is left unchanged
        file_info = remote.get_info(file_1_1)
        assert file_info.name == "Original File 1.1.txt"
        assert file_info.parent_uid == folder_1

        folder_info = remote.get_info(folder_1_1)
        assert folder_info.name == "Sub-Folder 2.1"
        assert folder_info.parent_uid == folder_1
        assert len(local.get_children_info("/Renamed Folder 1 \xe9")) == count
        assert len(remote.get_children_info(folder_1)) == count
        assert len(local.get_children_info("/")) == 4
        assert len(remote.get_children_info(self.workspace)) == 4

    def test_local_rename_file_after_create(self):
        # Office 2010 and >, create a tmp file with 8 chars
        # and move it right after
        local = self.local_1
        remote = self.remote_document_client_1

        local.make_file("/", "File.txt", content=b"Some Content 2")
        local.rename("/File.txt", "Renamed File.txt")

        self.wait_sync(fail_if_timeout=False)

        assert local.exists("/Renamed File.txt")
        assert not local.exists("/File.txt")
        # Path don't change on Nuxeo
        assert local.get_remote_id("/Renamed File.txt")
        assert len(local.get_children_info("/")) == 5
        assert len(remote.get_children_info(self.workspace)) == 5

    def test_local_rename_file_after_create_detected(self):
        # MS Office 2010+ creates a tmp file with 8 chars
        # and move it right after
        local = self.local_1
        remote = self.remote_document_client_1
        marker = False

        def insert_local_state(info, parent_path):
            nonlocal marker
            if info.name == "File.txt" and not marker:
                local.rename("/File.txt", "Renamed File.txt")
                sleep(2)
                marker = True
            EngineDAO.insert_local_state(self.engine_1.dao, info, parent_path)

        with patch.object(
            self.engine_1.dao, "insert_local_state", new=insert_local_state
        ):
            # Might be temporary ignored once
            self.engine_1.queue_manager._error_interval = 3
            local.make_file("/", "File.txt", content=b"Some Content 2")
            sleep(10)
            self.wait_sync(fail_if_timeout=False)

            assert local.exists("/Renamed File.txt")
            assert not local.exists("/File.txt")

            # Path doesn't change on Nuxeo
            assert local.get_remote_id("/Renamed File.txt")
            assert len(local.get_children_info("/")) == 5
            assert len(remote.get_children_info(self.workspace)) == 5

    def test_local_move_folder(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Save the uid of some files and folders prior to move
        folder_1 = remote.get_info("/Original Folder 1").uid
        folder_2 = remote.get_info("/Original Folder 2").uid
        file_1_1 = remote.get_info("/Original Folder 1/Original File 1.1.txt").uid
        folder_1_1 = remote.get_info("/Original Folder 1/Sub-Folder 1.1").uid

        # Move a non empty folder with some content
        local.move("/Original Folder 1", "/Original Folder 2")
        assert not local.exists("/Original Folder 1")
        assert local.exists("/Original Folder 2/Original Folder 1")

        # Synchronize: only the folder move is detected: all
        # the descendants are automatically realigned
        self.wait_sync()

        # The server folder has been moved: the uid stays the same
        # The parent folder is now folder 2
        assert remote.get_info(folder_1).parent_uid == folder_2

        # The content of the renamed folder is left unchanged
        file_1_1_info = remote.get_info(file_1_1)
        assert file_1_1_info.name == "Original File 1.1.txt"
        assert file_1_1_info.parent_uid == folder_1

        folder_1_1_info = remote.get_info(folder_1_1)
        assert folder_1_1_info.name == "Sub-Folder 1.1"
        assert folder_1_1_info.parent_uid == folder_1

        assert len(local.get_children_info("/Original Folder 2/Original Folder 1")) == 3
        assert len(remote.get_children_info(folder_1)) == 3
        assert len(local.get_children_info("/")) == 3
        assert len(remote.get_children_info(self.workspace)) == 3

    def test_concurrent_local_rename_folder(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Save the uid of some files and folders prior to renaming
        folder_1 = remote.get_info("/Original Folder 1").uid
        file_1_1 = remote.get_info("/Original Folder 1/Original File 1.1.txt").uid
        folder_2 = remote.get_info("/Original Folder 2").uid
        file_3 = remote.get_info("/Original Folder 2/Original File 3.txt").uid

        # Rename a non empty folders concurrently
        local.rename("/Original Folder 1", "Renamed Folder 1")
        local.rename("/Original Folder 2", "Renamed Folder 2")
        assert not local.exists("/Original Folder 1")
        assert local.exists("/Renamed Folder 1")
        assert not local.exists("/Original Folder 2")
        assert local.exists("/Renamed Folder 2")

        # Synchronize: only the folder renamings are detected: all
        # the descendants are automatically realigned
        self.wait_sync()

        # The server folders have been renamed: the uid stays the same
        folder_1_info = remote.get_info(folder_1)
        assert folder_1_info.name == "Renamed Folder 1"

        folder_2_info = remote.get_info(folder_2)
        assert folder_2_info.name == "Renamed Folder 2"

        # The content of the folder has been left unchanged
        file_1_1_info = remote.get_info(file_1_1)
        assert file_1_1_info.name == "Original File 1.1.txt"
        assert file_1_1_info.parent_uid == folder_1

        file_3_info = remote.get_info(file_3)
        assert file_3_info.name == "Original File 3.txt"
        assert file_3_info.parent_uid == folder_2

        assert len(local.get_children_info("/Renamed Folder 1")) == 3
        assert len(remote.get_children_info(folder_1)) == 3
        assert len(local.get_children_info("/Renamed Folder 2")) == 1
        assert len(remote.get_children_info(folder_2)) == 1
        assert len(local.get_children_info("/")) == 4
        assert len(remote.get_children_info(self.workspace)) == 4

    def test_local_replace(self):
        local = LocalTest(self.local_test_folder_1)
        remote = self.remote_document_client_1
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Create 2 files with the same name but different content
        # in separate folders
        local.make_file("/", "test.odt", content=b"Some content.")
        local.make_folder("/", "folder")
        shutil.copyfile(
            self.local_test_folder_1 / "test.odt",
            self.local_test_folder_1 / "folder" / "test.odt",
        )
        local.update_content("/folder/test.odt", content=b"Updated content.")

        # Copy the newest file to the root workspace and synchronize it
        sync_root = self.local_nxdrive_folder_1 / self.workspace_title
        test_file = self.local_test_folder_1 / "folder" / "test.odt"
        shutil.copyfile(test_file, sync_root / "test.odt")
        self.wait_sync()
        assert remote.exists("/test.odt")
        assert remote.get_content("/test.odt") == b"Updated content."

        # Copy the oldest file to the root workspace and synchronize it.
        # First wait a bit for file time stamps to increase enough.
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        shutil.copyfile(self.local_test_folder_1 / "test.odt", sync_root / "test.odt")
        self.wait_sync()
        assert remote.exists("/test.odt")
        assert remote.get_content("/test.odt") == b"Some content."

    def test_local_rename_sync_root_folder(self):
        # Use the Administrator to be able to introspect the container of the
        # test workspace.
        remote = DocRemote(
            self.nuxeo_url,
            env.NXDRIVE_TEST_USERNAME,
            "nxdrive-test-administrator-device",
            self.version,
            password=env.NXDRIVE_TEST_PASSWORD,
            base_folder=self.workspace,
        )
        folder_1_uid = remote.get_info("/Original Folder 1").uid

        # Create new clients to be able to introspect the test sync root
        toplevel_local_client = LocalTest(self.local_nxdrive_folder_1)

        toplevel_local_client.rename(
            Path(self.workspace_title), "Renamed Nuxeo Drive Test Workspace"
        )
        self.wait_sync()

        workspace_info = remote.get_info(self.workspace)
        assert workspace_info.name == "Renamed Nuxeo Drive Test Workspace"

        folder_1_info = remote.get_info(folder_1_uid)
        assert folder_1_info.name == "Original Folder 1"
        assert folder_1_info.parent_uid == self.workspace
        assert len(remote.get_children_info(self.workspace)) == 4

    def test_local_move_with_remote_error(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Check local folder
        assert local.exists("/Original Folder 1")

        # Simulate server error
        bad_remote = self.get_bad_remote()
        error = HTTPError(status=500, message="Mock server error")
        bad_remote.make_server_call_raise(error)

        with patch.object(self.engine_1, "remote", new=bad_remote):
            local.rename("/Original Folder 1", "OSErrorTest")
            self.wait_sync(timeout=5, fail_if_timeout=False)
            folder_1 = remote.get_info("/Original Folder 1")
            assert folder_1.name == "Original Folder 1"
            assert local.exists("/OSErrorTest")

        # Set engine online as starting from here the behavior is restored
        self.engine_1.set_offline(value=False)

        self.wait_sync()
        folder_1 = remote.get_info(folder_1.uid)
        assert folder_1.name == "OSErrorTest"
        assert local.exists("/OSErrorTest")
        assert len(local.get_children_info("/OSErrorTest")) == 3
        assert len(remote.get_children_info(folder_1.uid)) == 3
        assert len(local.get_children_info("/")) == 4
        assert len(remote.get_children_info(self.workspace)) == 4

    # TODO: implement me once canDelete is checked in the synchronizer
    # def test_local_move_sync_root_folder(self):
    #    pass
