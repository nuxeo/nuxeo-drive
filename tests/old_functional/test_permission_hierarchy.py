import hashlib
from contextlib import suppress
from pathlib import Path

import pytest
from nuxeo.exceptions import Forbidden

from nxdrive.constants import WINDOWS

from ..markers import windows_only
from . import LocalTest
from .common import OneUserTest, TwoUsersTest


class TestPermissionHierarchy(OneUserTest):
    def setup_method(self, method):
        super().setup_method(method, register_roots=False, server_profile="permission")

        self.local_1 = LocalTest(self.local_nxdrive_folder_1)

        # Make sure user workspace is created and fetch its UID
        res = self.remote_document_client_1.make_file_in_user_workspace(
            b"contents", "USFile.txt"
        )
        self.workspace_uid = res["parentRef"]

    def teardown_method(self, method):
        with suppress(Exception):
            self.root_remote.delete(self.workspace_uid, use_trash=False)
        super().teardown_method(method)

    def test_sync_delete_root(self):
        # Create test folder in user workspace as test user
        remote = self.remote_document_client_1
        test_folder_uid = remote.make_folder(self.workspace_uid, "test_folder")
        # Create a document in the test folder
        remote.make_file(test_folder_uid, "test_file.txt", content=b"Some content.")

        # Register test folder as a sync root
        remote.register_as_root(test_folder_uid)

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Check locally synchronized content
        root = Path("My Docs/test_folder")
        assert self.local_1.exists(root)
        assert self.local_1.exists(root / "test_file.txt")

        # Delete test folder
        remote.delete(test_folder_uid)
        self.wait_sync(wait_for_async=True)

        # Check locally synchronized content
        assert not self.local_1.exists(root)
        assert not self.local_1.get_children_info("/My Docs")


class TestPermissionHierarchy2(TwoUsersTest):
    def setup_method(self, method):
        super().setup_method(method, register_roots=False, server_profile="permission")

        self.local_1 = LocalTest(self.local_nxdrive_folder_1)
        self.local_2 = LocalTest(self.local_nxdrive_folder_2)

        # Make sure user workspace is created and fetch its UID
        res = self.remote_document_client_1.make_file_in_user_workspace(
            b"contents", "USFile.txt"
        )
        self.workspace_uid = res["parentRef"]

    def teardown_method(self, method):
        with suppress(Exception):
            self.root_remote.delete(self.workspace_uid, use_trash=False)
        super().teardown_method(method)

    @windows_only(reason="Only Windows ignores file permissions.")
    def test_permission_awareness_after_resume(self):
        remote = self.remote_document_client_1
        remote2 = self.remote_document_client_2
        local = self.local_2

        root = remote.make_folder(self.workspace_uid, "testing")
        folder = remote.make_folder(root, "FolderA")

        # Register user workspace as a sync root for user1
        remote.register_as_root(self.workspace_uid)

        # Register root folder as a sync root for user2
        self.set_readonly(self.user_2, root, grant=False)
        remote2.register_as_root(root)

        # Read only folder for user 2
        self.set_readonly(self.user_2, folder)

        # Start'n sync
        self.engine_2.start()
        self.wait_sync(
            wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True
        )
        self.engine_2.stop()

        # Checks
        root = Path("Other Docs/testing/FolderA")
        assert local.exists(root)

        # Create documents
        abspath = local.abspath(root)
        new_folder = abspath / "FolderCreated"
        new_folder.mkdir()
        (new_folder / "file.txt").write_bytes(b"content")

        # Change from RO to RW for the shared folder
        self.set_readonly(self.user_2, folder, grant=False)

        # Sync
        self.engine_2.start()
        self.wait_sync(
            wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True
        )

        # Status check
        dao = self.engine_2.dao
        assert not dao.get_errors(limit=0)
        assert not dao.get_filters()
        assert not dao.get_unsynchronizeds()

        # Local check
        assert local.exists(root / "FolderCreated/file.txt")

        # Remote checks
        children = remote.get_children_info(folder)
        assert len(children) == 1
        assert children[0].name == "FolderCreated"

        children = remote.get_children_info(children[0].uid)
        assert len(children) == 1
        assert children[0].name == "file.txt"

    def test_sync_delete_shared_folder(self):
        remote = self.remote_document_client_1
        self.engine_1.start()
        # Register user workspace as a sync root for user1
        remote.register_as_root(self.workspace_uid)

        # Create test folder in user workspace as user1
        test_folder_uid = remote.make_folder(self.workspace_uid, "test_folder")
        self.wait_sync(wait_for_async=True)
        assert self.local_1.exists("/My Docs")
        assert self.local_1.exists("/My Docs/test_folder")

        # Grant ReadWrite permission to user2 on test folder
        self.set_readonly(self.user_2, test_folder_uid, grant=False)
        self.wait_sync(wait_for_async=True)

        # Register test folder as a sync root for user2
        self.remote_document_client_2.register_as_root(test_folder_uid)
        self.wait_sync(wait_for_async=True)

        # Delete test folder
        remote.delete(test_folder_uid)
        self.wait_sync(wait_for_async=True)

        # Check locally synchronized content
        assert not self.local_1.exists("/My Docs/test_folder")
        children = self.local_1.get_children_info("/My Docs")
        assert len(children) == 1

    @pytest.mark.randombug("NXDRIVE-1582")
    def test_sync_unshared_folder(self):
        # Register user workspace as a sync root for user1
        remote = self.remote_document_client_1
        remote2 = self.remote_document_client_2
        remote.register_as_root(self.workspace_uid)

        self.engine_2.start()
        self.wait_sync(
            wait_for_async=True, wait_for_engine_2=True, wait_for_engine_1=False
        )
        # Check locally synchronized content
        assert self.local_2.exists("/My Docs")
        assert self.local_2.exists("/Other Docs")

        # Create test folder in user workspace as user1
        test_folder_uid = remote.make_folder(self.workspace_uid, "Folder A")
        folder_b = remote.make_folder(test_folder_uid, "Folder B")
        folder_c = remote.make_folder(folder_b, "Folder C")
        folder_d = remote.make_folder(folder_c, "Folder D")
        remote.make_folder(folder_d, "Folder E")

        # Grant ReadWrite permission to user2 on test folder
        self.set_readonly(self.user_2, test_folder_uid, grant=False)

        # Register test folder as a sync root for user2
        remote2.register_as_root(test_folder_uid)
        self.wait_sync(
            wait_for_async=True, wait_for_engine_2=True, wait_for_engine_1=False
        )
        assert self.local_2.exists("/Other Docs/Folder A")
        assert self.local_2.exists(
            "/Other Docs/Folder A/Folder B/Folder C/Folder D/Folder E"
        )
        # Use for later get_fs_item checks
        folder_b_fs = self.local_2.get_remote_id("/Other Docs/Folder A/Folder B")
        folder_a_fs = self.local_2.get_remote_id("/Other Docs/Folder A")
        # Unshare Folder A and share Folder C
        self.root_remote.execute(
            command="Document.RemoveACL",
            input_obj=f"doc:{test_folder_uid}",
            acl="local",
        )
        self.set_readonly(self.user_2, folder_c)
        remote2.register_as_root(folder_c)
        self.wait_sync(
            wait_for_async=True, wait_for_engine_2=True, wait_for_engine_1=False
        )
        assert not self.local_2.exists("/Other Docs/Folder A")
        assert self.local_2.exists("/Other Docs/Folder C")
        assert self.local_2.exists("/Other Docs/Folder C/Folder D/Folder E")

        # Verify that we don't have any 403 errors
        assert not self.remote_2.get_fs_item(folder_a_fs)
        assert not self.remote_2.get_fs_item(folder_b_fs)

    def test_sync_move_permission_removal(self):
        if WINDOWS:
            self.app.quit()
            pytest.xfail(
                "Following the NXDRIVE-836 fix, this test always fails because "
                "when moving a file from a RO folder to a RW folder will end up"
                " being a simple file creation. As we cannot know events order,"
                " we cannot understand a local move is being made just before "
                "a security update. To bo fixed with the engine refactoring."
            )

        remote = self.remote_document_client_1
        remote2 = self.remote_document_client_2
        local = self.local_2

        root = remote.make_folder(self.workspace_uid, "testing")
        readonly = remote.make_folder(root, "ReadFolder")
        readwrite = remote.make_folder(root, "WriteFolder")

        # Register user workspace as a sync root for user1
        remote.register_as_root(self.workspace_uid)

        # Register root folder as a sync root for user2
        self.set_readonly(self.user_2, root, grant=False)
        remote2.register_as_root(root)

        # Make one read-only document
        remote.make_file_with_blob(readonly, "file_ro.txt", b"Read-only doc.")

        # Read only folder for user 2
        self.set_readonly(self.user_2, readonly)

        # Basic test to be sure we are in RO mode
        with pytest.raises(Forbidden):
            remote2.make_file(readonly, "test.txt", content=b"test")

        # ReadWrite folder for user 2
        self.set_readonly(self.user_2, readwrite, grant=False)

        # Start'n sync
        self.engine_2.start()
        self.wait_sync(
            wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True
        )

        # Checks
        root = Path("Other Docs/testing")
        assert local.exists(root / "ReadFolder")
        assert local.exists(root / "ReadFolder/file_ro.txt")
        assert local.exists(root / "WriteFolder")
        content = local.get_content(root / "ReadFolder/file_ro.txt")
        assert content == b"Read-only doc."

        # Move the read-only file
        local.move(
            root / "ReadFolder/file_ro.txt", root / "WriteFolder", name="file_rw.txt"
        )

        # Remove RO on ReadFolder folder
        self.set_readonly(self.user_2, readonly, grant=False)

        # Edit the new writable file
        new_data = b"Now a fresh read-write doc."
        local.update_content(root / "WriteFolder/file_rw.txt", new_data)

        # Sync
        self.wait_sync(
            wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True
        )

        # Status check
        dao = self.engine_2.dao
        assert not dao.get_errors(limit=0)
        assert not dao.get_filters()
        assert not dao.get_unsynchronizeds()

        # Local checks
        assert not local.exists(root / "ReadFolder/file_ro.txt")
        assert not local.exists(root / "WriteFolder/file_ro.txt")
        assert local.exists(root / "WriteFolder/file_rw.txt")
        content = local.get_content(root / "WriteFolder/file_rw.txt")
        assert content == new_data

        # Remote checks
        assert not remote.get_children_info(readonly)
        children = remote.get_children_info(readwrite)
        assert len(children) == 1
        blob = children[0].get_blob("file:content")
        assert blob.name == "file_rw.txt"
        assert blob.digest == hashlib.md5(new_data).hexdigest()
