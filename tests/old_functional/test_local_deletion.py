import shutil

import pytest

from nxdrive.constants import WINDOWS
from nxdrive.options import Options

from .common import OneUserTest


class TestLocalDeletion(OneUserTest):
    def setUp(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

    def test_untrash_file(self):
        local = self.local_1
        remote = self.remote_document_client_1
        file1 = "File_To_Delete.txt"

        local.make_file("/", file1, content=b"This is a content")
        self.wait_sync()
        assert remote.exists("/" + file1)

        old_info = remote.get_info(f"/{file1}")
        abs_path = local.abspath(f"/{file1}")

        # Pretend we had trash the file
        shutil.move(abs_path, self.local_test_folder_1 / file1)
        self.wait_sync(wait_for_async=True)
        assert not remote.exists("/" + file1)
        assert not local.exists("/" + file1)
        # See if it untrash or recreate
        shutil.move(self.local_test_folder_1 / file1, local.abspath("/"))
        self.wait_sync(wait_for_async=True)
        assert remote.exists(old_info.uid)
        assert local.exists("/" + file1)

    def test_untrash_file_with_rename(self):
        local = self.local_1
        remote = self.remote_document_client_1
        file1 = "File_To_Delete.txt"
        file2 = "File_To_Delete2.txt"

        local.make_file("/", file1, content=b"This is a content")
        self.wait_sync()
        assert remote.exists(f"/{file1}")
        uid = local.get_remote_id(f"/{file1}")
        old_info = remote.get_info(f"/{file1}")
        abs_path = local.abspath(f"/{file1}")
        # Pretend we had trash the file
        shutil.move(abs_path, self.local_test_folder_1 / file2)
        self.wait_sync(wait_for_async=True)
        assert not remote.exists("/" + file1)
        assert not local.exists("/" + file1)
        (self.local_test_folder_1 / file2).write_bytes(b"New content")
        if WINDOWS:
            # Python API overwrite the tag by default
            (self.local_test_folder_1 / f"{file2}:ndrive").write_text(
                uid, encoding="utf-8"
            )
        # See if it untrash or recreate
        shutil.move(self.local_test_folder_1 / file2, local.abspath("/"))
        self.wait_sync(wait_for_async=True)
        assert remote.exists(old_info.uid)
        assert local.exists("/" + file2)
        assert not local.exists("/" + file1)
        assert local.get_content("/" + file2) == b"New content"

    def test_move_untrash_file_on_parent(self):
        local = self.local_1
        remote = self.remote_document_client_1
        file1 = "File_To_Delete.txt"

        file_path = "/ToDelete/File_To_Delete.txt"
        local.make_folder("/", "ToDelete")
        local.make_file("/ToDelete", file1, content=b"This is a content")
        self.wait_sync()
        assert remote.exists(file_path)
        old_info = remote.get_info(file_path)
        abs_path = local.abspath(file_path)
        # Pretend we had trash the file
        shutil.move(abs_path, self.local_test_folder_1 / file1)
        self.wait_sync()
        local.delete("/ToDelete")
        self.wait_sync()
        assert not remote.exists(file_path)
        assert not local.exists(file_path)

        # See if it untrash or recreate
        shutil.move(self.local_test_folder_1 / file1, local.abspath("/"))
        self.wait_sync()
        new_info = remote.get_info(old_info.uid)
        assert new_info.state == "project"
        assert local.exists(f"/{file1}")
        # Because remote_document_client_1 was used
        assert local.get_remote_id("/").endswith(new_info.parent_uid)

    @Options.mock()
    def test_move_untrash_file_on_parent_with_no_rights(self):
        local = self.local_1
        remote = self.remote_document_client_1
        file1 = "File_To_Delete.txt"

        # Setup
        file_path = "/ToDelete/File_To_Delete.txt"
        local.make_folder("/", "ToDelete")
        local.make_file("/ToDelete", file1, content=b"This is a content")
        self.wait_sync()
        assert remote.exists(file_path)
        old_info = remote.get_info(file_path)
        abs_path = local.abspath(file_path)
        # Pretend we had trash the file
        shutil.move(abs_path, self.local_test_folder_1 / file1)
        self.wait_sync()

        # Remove rights
        folder_path = f"{self.ws.path}/ToDelete"
        input_obj = "doc:" + folder_path
        self.root_remote.execute(
            command="Document.SetACE",
            input_obj=input_obj,
            user=self.user_1,
            permission="Read",
        )
        self.root_remote.block_inheritance(folder_path, overwrite=False)
        self.root_remote.delete(folder_path)
        self.wait_sync(wait_for_async=True)
        assert not remote.exists(file_path)
        assert not local.exists(file_path)

        # See if it untrash or recreate
        shutil.move(self.local_test_folder_1 / file1, local.abspath("/"))
        assert local.get_remote_id("/" + file1)
        self.wait_sync()
        assert local.exists("/" + file1)
        new_uid = local.get_remote_id("/" + file1)
        # Because remote_document_client_1 was used
        assert new_uid
        assert not new_uid.endswith(old_info.uid)

    @pytest.mark.skip(
        reason="Wait to know what is the expectation "
        "- the previous folder does not exist"
    )
    def test_move_untrash_file_on_parent_with_no_rights_on_destination(self):
        local = self.local_1
        remote = self.remote_document_client_1
        file1 = "File_To_Delete.txt"

        # Setup the test
        file_path = "/ToDelete/File_To_Delete.txt"
        local.make_folder("/", "ToDelete")
        local.make_folder("/", "ToCopy")
        local.make_file("/ToDelete", file1, content=b"This is a content")
        self.wait_sync()
        assert remote.exists(file_path)
        remote.get_info(file_path)
        abs_path = local.abspath(file_path)

        # Pretend we had trash the file
        shutil.move(abs_path, self.local_test_folder_1 / file1)
        self.wait_sync()

        # Remove rights
        folder_path = f"{self.ws.path}/ToCopy"
        input_obj = "doc:" + folder_path
        self.root_remote.execute(
            command="Document.SetACE",
            input_obj=input_obj,
            user=self.user_1,
            permission="Read",
        )
        self.root_remote.block_inheritance(folder_path, overwrite=False)
        # Delete
        local.delete("/ToDelete")
        self.wait_sync(wait_for_async=True)
        assert not remote.exists(file_path)
        assert not local.exists(file_path)

        # See if it untrash or unsynchronized
        local.unlock_ref("/ToCopy")
        shutil.move(self.local_test_folder_1 / file1, local.abspath("/ToCopy"))
        self.wait_sync(wait_for_async=True)

    def test_untrash_file_on_delete_parent(self):
        local = self.local_1
        remote = self.remote_document_client_1
        file1 = "File_To_Delete.txt"

        # Setup
        file_path = "/ToDelete/File_To_Delete.txt"
        local.make_folder("/", "ToDelete")
        local.make_file("/ToDelete", file1, content=b"This is a content")
        self.wait_sync()
        assert remote.exists(file_path)
        old_info = remote.get_info(file_path)
        abs_path = local.abspath(file_path)

        # Pretend we had trash the file
        shutil.move(abs_path, self.local_test_folder_1 / file1)
        self.wait_sync()
        local.delete("/ToDelete")
        self.wait_sync()
        assert not remote.exists(file_path)
        assert not local.exists(file_path)

        # See if it untrash or recreate
        local.make_folder("/", "ToDelete")
        shutil.move(self.local_test_folder_1 / file1, local.abspath("/ToDelete"))
        self.wait_sync()
        assert remote.exists(old_info.uid)
        new_info = remote.get_info(old_info.uid)
        assert remote.exists(new_info.parent_uid)
        assert local.exists(file_path)

    def test_trash_file_then_parent(self):
        local = self.local_1
        remote = self.remote_document_client_1
        file1 = "File_To_Delete.txt"

        file_path = "/ToDelete/File_To_Delete.txt"
        local.make_folder("/", "ToDelete")
        local.make_file("/ToDelete", file1, content=b"This is a content")
        self.wait_sync()
        assert remote.exists(file_path)
        old_info = remote.get_info(file_path)
        abs_path = local.abspath(file_path)
        # Pretend we had trash the file
        shutil.move(abs_path, self.local_test_folder_1 / file1)
        local.delete("/ToDelete")
        self.wait_sync()
        assert not remote.exists(file_path)
        assert not local.exists(file_path)
        # See if it untrash or recreate
        local.make_folder("/", "ToDelete")
        shutil.move(self.local_test_folder_1 / file1, local.abspath("/ToDelete"))
        self.wait_sync()
        assert remote.exists(old_info.uid)
        assert local.exists(file_path)

    @Options.mock()
    def test_trash_file_should_respect_deletion_behavior_unsync(self):
        Options.deletion_behavior = "unsync"

        local, engine = self.local_1, self.engine_1
        remote = self.remote_document_client_1
        folder, file = "folder", "file.txt"
        file_path = f"/{folder}/{file}"

        # Create local data
        local.make_folder("/", folder)
        local.make_file(f"/{folder}", file, content=b"This is a content")

        # Sync'n check
        self.wait_sync()
        assert remote.exists(file_path)

        # Mimic "stop Drive"
        engine.stop()

        # Delete the file
        local.delete(file_path)

        # Mimic "start Drive"
        engine.start()
        self.wait_sync()

        # Checks
        assert remote.exists(file_path)
        assert not local.exists(file_path)

    @Options.mock()
    def test_trash_file_should_respect_deletion_behavior_delete_server(self):
        Options.deletion_behavior = "delete_server"

        local, engine = self.local_1, self.engine_1
        remote = self.remote_document_client_1
        folder, file = "folder", "file.txt"
        file_path = f"/{folder}/{file}"

        # Create local data
        local.make_folder("/", folder)
        local.make_file(f"/{folder}", file, content=b"This is a content")

        # Sync'n check
        self.wait_sync()
        assert remote.exists(file_path)

        # Mimic "stop Drive"
        engine.stop()

        # Delete the file
        local.delete(file_path)

        # Mimic "start Drive"
        engine.start()
        self.wait_sync()

        # Checks
        assert not remote.exists(file_path)
        assert not local.exists(file_path)
