# coding: utf-8
from itertools import product
from time import sleep

import pytest
from mock import patch
from nuxeo.exceptions import HTTPError

from nxdrive.engine.dao.sqlite import EngineDAO
from . import DocRemote, LocalTest, RemoteTest
from .common import UnitTestCase


# TODO NXDRIVE-170: refactor


class TestLocalMoveAndRename(UnitTestCase):
    # Sets up the following local hierarchy:
    # Nuxeo Drive Test Workspace
    #    |-- Original File 1.txt
    #    |-- Original File 2.txt
    #    |-- Original Folder 1
    #    |       |-- Sub-Folder 1.1
    #    |       |-- Sub-Folder 1.2
    #    |       |-- Original File 1.1.txt
    #    |-- Original Folder 2
    #    |       |-- Original File 3.txt
    def setUp(self):
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
            EngineDAO.update_remote_state(self.engine_1._dao, row, *args, **kwargs)
            if row.local_name == "New Folder" and not marker:
                root_local.rename(row.local_path, "Renamed Folder")
                marker = True

        with patch.object(
            self.engine_1._dao, "update_remote_state", new=update_remote_state
        ):
            local.make_folder("/", "New Folder")
            self.wait_sync(fail_if_timeout=False)

            assert local.exists("/Renamed Folder")
            assert not local.exists("/New Folder")

            # Path doesn't change on Nuxeo
            info = remote.get_info("/New Folder")
            assert info.name == "Renamed Folder"
            assert len(local.get_children_info("/")) == 5
            assert len(remote.get_children_info(self.workspace_1)) == 5

    def test_local_rename_file_while_creating(self):
        local = self.engine_1.local
        remote = self.remote_document_client_1
        root_local = self.local_root_client_1
        marker = False

        def set_remote_id(ref: str, remote_id: bytes, name: str = "ndrive"):
            nonlocal local, marker
            LocalTest.set_remote_id(local, ref, remote_id, name)
            if not marker and ref.endswith("/File.txt"):
                root_local.rename(ref, "Renamed File.txt")
                marker = True

        with patch.object(self.engine_1.local, "set_remote_id", new=set_remote_id):
            self.local_1.make_file("/", "File.txt", content=b"Some Content 2")
            self.wait_sync(fail_if_timeout=False)

            local = self.local_1
            assert local.exists("/Renamed File.txt")
            assert not local.exists("/File.txt")

            # Path doesn't change on Nuxeo
            info = remote.get_info("/File.txt")
            assert info.name == "Renamed File.txt"
            assert len(local.get_children_info("/")) == 5
            assert len(remote.get_children_info(self.workspace_1)) == 5

    def test_local_rename_file_while_creating_before_marker(self):
        local = self.engine_1.local
        remote = self.remote_document_client_1
        root_local = self.local_root_client_1
        marker = False

        def set_remote_id(ref: str, remote_id: bytes, name: str = "ndrive"):
            nonlocal local, marker
            if not marker and ref.endswith("/File.txt"):
                root_local.rename(ref, "Renamed File.txt")
                marker = True
            LocalTest.set_remote_id(local, ref, remote_id, name)

        with patch.object(self.engine_1.local, "set_remote_id", new=set_remote_id):
            self.local_1.make_file("/", "File.txt", content=b"Some Content 2")
            self.wait_sync(fail_if_timeout=False)

            local = self.local_1
            assert local.exists("/Renamed File.txt")
            assert not local.exists("/File.txt")

            # Path doesn't change on Nuxeo
            info = remote.get_info("/File.txt")
            assert info.name == "Renamed File.txt"
            assert len(local.get_children_info("/")) == 5
            assert len(remote.get_children_info(self.workspace_1)) == 5

    def test_local_rename_file_while_creating_after_marker(self):
        marker = False
        local = self.local_1
        root_local = self.local_root_client_1
        remote = self.remote_document_client_1

        def update_remote_state(row, *args, **kwargs):
            nonlocal marker
            EngineDAO.update_remote_state(self.engine_1._dao, row, *args, **kwargs)
            if not marker and row.local_name == "File.txt":
                root_local.rename(row.local_path, "Renamed File.txt")
                marker = True

        with patch.object(
            self.engine_1._dao, "update_remote_state", new=update_remote_state
        ):
            local.make_file("/", "File.txt", content=b"Some Content 2")
            self.wait_sync(fail_if_timeout=False)

            assert local.exists("/Renamed File.txt")
            assert not local.exists("/File.txt")

            # Path doesn't change on Nuxeo
            info = remote.get_info("/File.txt")
            assert info.name == "Renamed File.txt"
            assert len(local.get_children_info("/")) == 5
            assert len(remote.get_children_info(self.workspace_1)) == 5

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
        assert len(remote.get_children_info(self.workspace_1)) == 4

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
        assert len(remote.get_children_info(self.workspace_1)) == 3

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
        assert len(remote.get_children_info(self.workspace_1)) == 3

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
        assert len(remote.get_children_info(self.workspace_1)) == 4

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
        assert len(remote.get_children_info(self.workspace_1)) == 4

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
        assert local.get_remote_id("/Renamed File.txt") is not None
        assert len(local.get_children_info("/")) == 5
        assert len(remote.get_children_info(self.workspace_1)) == 5

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
            EngineDAO.insert_local_state(self.engine_1._dao, info, parent_path)

        with patch.object(
            self.engine_1._dao, "insert_local_state", new=insert_local_state
        ):
            # Might be blacklisted once
            self.engine_1.get_queue_manager()._error_interval = 3
            local.make_file("/", "File.txt", content=b"Some Content 2")
            sleep(10)
            self.wait_sync(fail_if_timeout=False)

            assert local.exists("/Renamed File.txt")
            assert not local.exists("/File.txt")

            # Path doesn't change on Nuxeo
            assert local.get_remote_id("/Renamed File.txt") is not None
            assert len(local.get_children_info("/")) == 5
            assert len(remote.get_children_info(self.workspace_1)) == 5

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
        assert len(remote.get_children_info(self.workspace_1)) == 3

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
        assert len(remote.get_children_info(self.workspace_1)) == 4

    def test_local_rename_sync_root_folder(self):
        # Use the Administrator to be able to introspect the container of the
        # test workspace.
        remote = DocRemote(
            pytest.nuxeo_url,
            pytest.user,
            "nxdrive-test-administrator-device",
            pytest.version,
            password=pytest.password,
            base_folder=self.workspace,
        )
        folder_1_uid = remote.get_info("/Original Folder 1").uid

        # Create new clients to be able to introspect the test sync root
        toplevel_local_client = LocalTest(self.local_nxdrive_folder_1)

        toplevel_local_client.rename(
            "/" + self.workspace_title, "Renamed Nuxeo Drive Test Workspace"
        )
        self.wait_sync()

        workspace_info = remote.get_info(self.workspace)
        assert workspace_info.name == "Renamed Nuxeo Drive Test Workspace"

        folder_1_info = remote.get_info(folder_1_uid)
        assert folder_1_info.name == "Original Folder 1"
        assert folder_1_info.parent_uid == self.workspace
        assert len(remote.get_children_info(self.workspace_1)) == 4

    def test_local_move_with_remote_error(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Check local folder
        assert local.exists("/Original Folder 1")

        # Simulate server error
        self.engine_1.remote = RemoteTest(
            pytest.nuxeo_url,
            self.user_1,
            "nxdrive-test-administrator-device",
            pytest.version,
            password=self.password_1,
        )
        error = HTTPError(status=500, message="Mock server error")
        self.engine_1.remote.make_server_call_raise(error)

        local.rename("/Original Folder 1", "OSErrorTest")
        self.wait_sync(timeout=5, fail_if_timeout=False)
        folder_1 = remote.get_info("/Original Folder 1")
        assert folder_1.name == "Original Folder 1"
        assert local.exists("/OSErrorTest")

        # Remove faulty client and set engine online
        self.engine_1.remote.make_server_call_raise(None)
        self.engine_1.set_offline(value=False)

        self.wait_sync()
        folder_1 = remote.get_info(folder_1.uid)
        assert folder_1.name == "OSErrorTest"
        assert local.exists("/OSErrorTest")
        assert len(local.get_children_info("/OSErrorTest")) == 3
        assert len(remote.get_children_info(folder_1.uid)) == 3
        assert len(local.get_children_info("/")) == 4
        assert len(remote.get_children_info(self.workspace_1)) == 4

    # TODO: implement me once canDelete is checked in the synchronizer
    # def test_local_move_sync_root_folder(self):
    #    pass


class TestLocalMove(UnitTestCase):
    def test_nxdrive_1033(self):
        """
1. Connect Drive in 2 PC's with same account (Drive-01, Drive-02)
2. Drive-01: Create a Folder "Folder01" and upload 20 files into it
3. Drive-02: Wait for folder and files to sync in 2nd PC (Drive-02)
4. Drive-01: Create a folder "878" in folder "Folder01" and move all the files
    into folder "878"
5. Drive-02: Wait for files to sync in Drive-02

Expected result: In Drive-02, all files should move into folder "878"

Stack:

sqlite Updating remote state for row=<StateRow> with info=...
sqlite Increasing version to 1 for pair <StateRow>
remote_watcher Unexpected error
Traceback (most recent call last):
  File "remote_watcher.py", line 487, in _handle_changes
    self._update_remote_states()
  File "remote_watcher.py", line 699, in _update_remote_states
    force_update=lock_update)
  File "sqlite.py", line 1401, in update_remote_state
    row.remote_state, row.pair_state, row.id))
  File "sqlite.py", line 65, in execute
    obj = super().execute(*args, **kwargs)
IntegrityError: UNIQUE constraint failed:
                States.remote_ref, States.remote_parent_ref

---

Understanding:

When the client 1 created the 878 folder and then moved all files into it, the
client 2 received unordered events.  Still on the client 2, 878 was created if
needed by one of its children: 1st error of duplicate type when the folder
creation event was handled later.

Another error was the remote creation twice of a given document because of the
previous error. We found then in the database 2 rows with the same remote_ref
but different remote_parent_ref (as one was under "/Folder01" and the other
into "/Folder01/878". Later when doing the move, it failed with the previous
traceback.

With the fix, we now have a clean database without any errors and all events
are well taken into account.
        """

        local1, local2 = self.local_1, self.local_2
        self.engine_1.start()
        self.engine_2.start()
        self.wait_sync(wait_for_async=True)

        # Create documents
        files = ["test_file_%d.odt" % i for i in range(1, 21)]
        srcname = "Folder 01"
        folder = local1.make_folder("/", srcname)
        srcname = "/" + srcname
        for filename in files:
            local1.make_file(srcname, filename, content=filename.encode())

        # Checks
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True)
        for local, filename in product((local1, local2), files):
            assert local.exists(srcname + "/" + filename)

        # Step 4
        dstname = "8 78"
        dst = local1.make_folder(srcname, dstname)
        dstname = "/" + dstname
        for child in local1.get_children_info(folder):
            if not child.folderish:
                local1.move(child.path, dst)

        # Checks
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True, timeout=120)

        for local in {local1, local2}:
            assert len(local.get_children_info("/")) == 1
            assert len(local.get_children_info(srcname)) == 1
            assert len(local.get_children_info(srcname + dstname)) == len(files)

        for dao in {self.engine_1.get_dao(), self.engine_2.get_dao()}:
            assert not dao.get_errors(limit=0)
            assert not dao.get_filters()
            assert not dao.get_unsynchronizeds()

        for remote, ws in zip(
            (self.remote_document_client_1, self.remote_document_client_2),
            (self.workspace_1, self.workspace_2),
        ):
            # '/'
            children = remote.get_children_info(ws)
            assert len(children) == 1

            # srcname
            children = remote.get_children_info(children[0].uid)
            assert len(children) == 1

            # srcname + dstname
            children = remote.get_children_info(children[0].uid)
            assert len(children) == len(files)
