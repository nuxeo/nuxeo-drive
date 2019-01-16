# coding: utf-8
import shutil
import time
from logging import getLogger
from pathlib import Path

import pytest
from nuxeo.exceptions import HTTPError

from nxdrive.constants import WINDOWS
from nxdrive.engine.watcher.local_watcher import WIN_MOVE_RESOLUTION_PERIOD
from .common import TEST_WORKSPACE_PATH, UnitTestCase

log = getLogger(__name__)


class TestReadOnly(UnitTestCase):
    def setUp(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

    @staticmethod
    def touch(path: Path):
        if WINDOWS and not path.parent.is_dir():
            path.parent.mkdir()
        try:
            path.write_bytes(b"Test")
        except OSError:
            log.exception("Enable to touch")
            return False
        return True

    def test_document_locked(self):
        """ Check locked documents: they are read-only. """

        remote = self.remote_document_client_1
        remote.make_folder("/", "Test locking")
        remote.make_file("/Test locking", "myDoc.odt", content=b"Some content")
        filepath = "/Test locking/myDoc.odt"

        self.wait_sync(wait_for_async=True)

        # Check readonly flag is not set for a document that isn't locked
        user1_file_path = self.sync_root_folder_1 / filepath.lstrip("/")
        assert user1_file_path.exists()
        assert self.touch(user1_file_path)
        self.wait_sync()

        # Check readonly flag is not set for a document locked by the
        # current user
        remote.lock(filepath)
        self.wait_sync(wait_for_async=True)
        assert self.touch(user1_file_path)
        remote.unlock(filepath)
        self.wait_sync(wait_for_async=True)

        # Check readonly flag is set for a document locked by another user
        self.remote_document_client_2.lock(filepath)
        self.wait_sync(wait_for_async=True)
        assert not self.touch(user1_file_path)

        # Check readonly flag is unset for a document unlocked by another user
        self.remote_document_client_2.unlock(filepath)
        self.wait_sync(wait_for_async=True)
        assert self.touch(user1_file_path)

    def test_file_add(self):
        """
        Should not be able to create files in root folder.
        On Windows, those files are ignored.
        """

        remote = self.remote_document_client_1

        # Try to create the file
        state = self.touch(self.local_nxdrive_folder_1 / "test.txt")

        if not WINDOWS:
            # The creation must have failed
            assert not state
        else:
            # The file is locally created and should be ignored
            self.wait_sync(wait_for_async=True)
            ignored = self.engine_1.get_dao().get_unsynchronizeds()
            assert len(ignored) == 1
            assert ignored[0].local_path == Path("test.txt")

            # Check there is nothing uploaded to the server
            assert not remote.get_children_info("/")

    def test_file_content_change(self):
        """
        No upload server side but possible to change the file locally
        without error, if the OS allowes it (unlikely).
        """

        local = self.local_1
        remote = self.remote_document_client_1

        # Create documents and sync
        folder = remote.make_folder("/", "folder")
        remote.make_file(folder, "foo.txt", content=b"42")
        self.set_readonly(self.user_1, TEST_WORKSPACE_PATH + "/folder")
        self.wait_sync(wait_for_async=True)
        assert remote.exists("/folder")
        assert remote.exists("/folder/foo.txt")

        # Try to change the file content locally
        with pytest.raises(OSError):
            local.abspath("/folder/foo.txt").write_bytes(b"Change")

        with pytest.raises(OSError):
            local.update_content("/folder/foo.txt", b"Locally changed")

        # Try to change the file content remotely
        with pytest.raises(HTTPError):
            remote.update_content("/folder/foo.txt", b"Remotely changed")

    def test_file_delete(self):
        """ Local deletions are filtered. """

        remote = self.remote_document_client_1
        local = self.local_1

        folder = remote.make_folder("/", "test-ro")
        remote.make_file(folder, "test.txt", content=b"42")
        self.set_readonly(self.user_1, TEST_WORKSPACE_PATH + "/test-ro")
        self.wait_sync(wait_for_async=True)
        assert local.exists("/test-ro/test.txt")
        assert not self.engine_1.get_dao().get_filters()

        # Delete the file and check if is re-downloaded
        local.unset_readonly("/test-ro")
        local.delete("/test-ro/test.txt")
        if WINDOWS:
            time.sleep((WIN_MOVE_RESOLUTION_PERIOD // 1000) + 1)
        self.wait_sync()
        assert not local.exists("/test-ro/test.txt")

        # Check that it is filtered
        assert self.engine_1.get_dao().get_filters()

        # Check the file is still present on the server
        assert remote.exists("/test-ro/test.txt")

    def test_file_move_from_ro_to_ro(self):
        """
        Local moves from a read-only folder to a read-only folder.
          - source is ignored
          - destination is ignored

        Server side: no changes.
        Client side: no errors.
        """

        remote = self.remote_document_client_1
        local = self.local_1

        # folder-src is the source from where documents will be moved, RO
        # folder-dst is the destination where documents will be moved, RO
        src = local.make_folder("/", "folder-src")
        dst = local.make_folder("/", "folder-dst")
        local.make_file("/folder-src", "here.txt", content=b"stay here")
        self.wait_sync()
        assert remote.exists("/folder-src/here.txt")
        assert remote.exists("/folder-dst")

        self.set_readonly(self.user_1, TEST_WORKSPACE_PATH)
        self.wait_sync(wait_for_async=True)

        doc_abs = local.abspath(src) / "here.txt"
        dst_abs = local.abspath(dst)
        if not WINDOWS:
            # The move should fail
            with pytest.raises(OSError):
                shutil.move(doc_abs, dst_abs)
        else:
            # The move happens
            shutil.move(doc_abs, dst_abs)
            time.sleep((WIN_MOVE_RESOLUTION_PERIOD // 1000) + 1)
            self.wait_sync()

            # Check that nothing has changed
            assert not local.exists("/folder-src/here.txt")
            assert local.exists("/folder-dst/here.txt")
            assert remote.exists("/folder-src/here.txt")

            # But also, check that the server received nothing
            assert not remote.exists("/folder-dst/here.txt")

            # We should not have any error
            assert not self.engine_1.get_dao().get_errors(limit=0)

    def test_file_move_from_ro_to_rw(self):
        """
        Local moves from a read-only folder to a read-write folder.
          - source is ignored
          - destination is seen as a creation

        Server side: only the files in the RW folder are created.
        Client side: no errors.

        Associated ticket: NXDRIVE-836
        """

        remote = self.remote_document_client_1
        local = self.local_1

        # folder-ro is the source from where documents will be moved, RO
        # folder-rw is the destination where documents will be moved, RW
        src = local.make_folder("/", "folder-ro")
        dst = local.make_folder("/", "folder-rw")
        local.make_file("/folder-ro", "here.txt", content=b"stay here")
        self.wait_sync()
        assert remote.exists("/folder-ro/here.txt")
        assert remote.exists("/folder-rw")

        self.set_readonly(self.user_1, TEST_WORKSPACE_PATH + "/folder-ro")
        self.wait_sync(wait_for_async=True)

        doc_abs = local.abspath(src) / "here.txt"
        dst_abs = local.abspath(dst)
        if not WINDOWS:
            # The move should fail
            with pytest.raises(OSError):
                shutil.move(doc_abs, dst_abs)
        else:
            # The move happens
            shutil.move(doc_abs, dst_abs)
            time.sleep((WIN_MOVE_RESOLUTION_PERIOD // 1000) + 1)
            self.wait_sync()

            # Check that nothing has changed
            assert not local.exists("/folder-ro/here.txt")
            assert local.exists("/folder-rw/here.txt")
            assert remote.exists("/folder-ro/here.txt")

            # But also, check that the server received the new document because
            # the destination is RW
            assert remote.exists("/folder-rw/here.txt")

            # We should not have any error
            assert not self.engine_1.get_dao().get_errors(limit=0)

    @pytest.mark.skip(True, reason="TODO NXDRIVE-740")
    def test_file_move_from_rw_to_ro(self):
        pass

    def test_file_rename(self):
        """
        No upload server side but possible to rename the file locally
        without error.
        """

        local = self.local_1
        remote = self.remote_document_client_1

        # Create documents and sync
        folder = local.make_folder("/", "folder")
        local.make_file("/folder", "foo.txt", content=b"42")
        self.wait_sync()
        assert remote.exists("/folder")
        assert remote.exists("/folder/foo.txt")

        # Set read-only
        self.set_readonly(self.user_1, TEST_WORKSPACE_PATH + "/folder")
        self.wait_sync(wait_for_async=True)

        # Locally rename the file
        doc = local.abspath(folder) / "foo.txt"
        dst = local.abspath(folder) / "bar.txt"
        if not WINDOWS:
            # The rename should fail
            with pytest.raises(OSError):
                doc.rename(dst)
        else:
            # The rename happens locally but nothing remotely
            doc.rename(dst)
            self.wait_sync()
            assert remote.exists("/folder/foo.txt")
            assert not remote.exists("/folder/bar.txt")

            # We should not have any error
            assert not self.engine_1.get_dao().get_errors(limit=0)

    def test_folder_add(self):
        """
        Should not be able to create folders in root folder.
        On Windows, those folders are ignored.
        """

        remote = self.remote_document_client_1
        folder = self.local_nxdrive_folder_1 / "foo" / "test.txt"

        if not WINDOWS:
            # The creation must have failed
            assert not self.touch(folder)
        else:
            # The folder and its child are locally created
            self.touch(folder)

            # Sync and check that it is ignored
            self.wait_sync(wait_for_async=True)
            ignored = [
                d.local_path.as_posix()
                for d in self.engine_1.get_dao().get_unsynchronizeds()
            ]
            assert list(sorted(ignored)) == ["foo", "foo/test.txt"]

            # Check there is nothing uploaded to the server
            assert not remote.get_children_info("/")

    def test_folder_delete(self):
        """ Local deletions are filtered. """

        remote = self.remote_document_client_1
        local = self.local_1

        folder = remote.make_folder("/", "test-ro")
        remote.make_folder(folder, "foo")
        self.set_readonly(self.user_1, TEST_WORKSPACE_PATH + "/test-ro")
        self.wait_sync(wait_for_async=True)
        assert local.exists("/test-ro/foo")
        assert not self.engine_1.get_dao().get_filters()

        # Delete the file and check if is re-downloaded
        local.unset_readonly("/test-ro")
        local.delete("/test-ro/foo")
        if WINDOWS:
            time.sleep((WIN_MOVE_RESOLUTION_PERIOD // 1000) + 1)
        self.wait_sync()
        assert not local.exists("/test-ro/foo")

        # Check that it is filtered
        assert self.engine_1.get_dao().get_filters()

        # Check the file is still present on the server
        assert remote.exists("/test-ro/foo")

    def test_folder_move_from_ro_to_ro(self):
        """
        Local moves from a read-only folder to a read-only folder.
          - source is ignored
          - destination is ignored

        Server side: no changes.
        Client side: no errors.
        """

        remote = self.remote_document_client_1
        local = self.local_1

        # folder-src is the source that will be moved, RO
        # folder-dst is the destination, RO
        folder_ro1 = remote.make_folder("/", "folder-src")
        folder_ro2 = remote.make_folder("/", "folder-dst")
        remote.make_file(folder_ro1, "here.txt", content=b"stay here")
        remote.make_file(folder_ro2, "there.txt", content=b"stay here too")
        self.set_readonly(self.user_1, TEST_WORKSPACE_PATH)
        self.wait_sync(wait_for_async=True)
        assert local.exists("/folder-src/here.txt")
        assert remote.exists("/folder-dst")

        src = local.abspath("/folder-src")
        dst = local.abspath("/folder-dst")
        if not WINDOWS:
            # The move should fail
            with pytest.raises(OSError):
                shutil.move(src, dst)
        else:
            # The move happens
            shutil.move(src, dst)
            time.sleep((WIN_MOVE_RESOLUTION_PERIOD // 1000) + 1)
            self.wait_sync()

            # Check that nothing has changed
            assert not local.exists("/folder-src")
            assert local.exists("/folder-dst/there.txt")
            assert local.exists("/folder-dst/folder-src/here.txt")
            assert remote.exists("/folder-src/here.txt")
            assert remote.exists("/folder-dst/there.txt")

            # But also, check that the server received nothing
            assert not remote.exists("/folder-dst/folder-src")

            # We should not have any error
            assert not self.engine_1.get_dao().get_errors(limit=0)

    def test_folder_move_from_ro_to_rw(self):
        """
        Local moves from a read-only folder to a read-write folder.
          - source is ignored
          - destination is filtered

        Server side: no changes.
        Client side: no errors.
        """

        remote = self.remote_document_client_1
        local = self.local_1

        # folder-src is the source that will be moved, RO
        # folder-dst is the destination, RO
        folder_ro1 = remote.make_folder("/", "folder-src")
        folder_ro2 = remote.make_folder("/", "folder-dst")
        remote.make_file(folder_ro1, "here.txt", content=b"stay here")
        remote.make_file(folder_ro2, "there.txt", content=b"stay here too")
        self.set_readonly(self.user_1, TEST_WORKSPACE_PATH)
        self.wait_sync(wait_for_async=True)
        assert local.exists("/folder-src/here.txt")
        assert remote.exists("/folder-dst")

        src = local.abspath("/folder-src")
        dst = local.abspath("/folder-dst")
        if not WINDOWS:
            # The move should fail
            with pytest.raises(OSError):
                shutil.move(src, dst)
        else:
            # The move happens
            shutil.move(src, dst)
            time.sleep((WIN_MOVE_RESOLUTION_PERIOD // 1000) + 1)
            self.wait_sync()

            # Check that nothing has changed
            assert not local.exists("/folder-src")
            assert local.exists("/folder-dst/there.txt")
            assert local.exists("/folder-dst/folder-src/here.txt")
            assert remote.exists("/folder-src/here.txt")
            assert remote.exists("/folder-dst/there.txt")
            assert not remote.exists("/folder-dst/folder-src")
            assert not remote.exists("/folder-dst/folder-src/here.txt")

            # We should not have any error
            assert not self.engine_1.get_dao().get_errors(limit=0)

            # Check that it is filtered
            assert self.engine_1.get_dao().get_filters()
            doc_pair = remote.get_info(folder_ro1)
            root_path = (
                "/org.nuxeo.drive.service.impl"
                ".DefaultTopLevelFolderItemFactory#"
                "/defaultSyncRootFolderItemFactory#default#"
                "{}/defaultFileSystemItemFactory#default#{}"
            )
            ref = root_path.format(doc_pair.root, doc_pair.uid)
            assert self.engine_1.get_dao().is_filter(ref)

    @pytest.mark.skip(True, reason="TODO NXDRIVE-740")
    def test_folder_move_from_rw_to_ro(self):
        pass

    def test_folder_rename(self):
        """
        No upload server side but possible to rename the folder locally
        without error, and it will be re-renamed.
        """

        local = self.local_1
        remote = self.remote_document_client_1

        # Create documents and sync
        folder = local.make_folder("/", "foo")
        self.wait_sync()
        assert remote.exists("/foo")

        # Set read-only
        self.set_readonly(self.user_1, TEST_WORKSPACE_PATH)
        self.wait_sync(wait_for_async=True)

        # Check can_delete flag in pair state
        state = self.get_dao_state_from_engine_1("/foo")
        assert not state.remote_can_delete

        # Locally rename the folder
        src = local.abspath(folder)
        dst = src.with_name("bar")
        if not WINDOWS:
            # The rename should fail
            with pytest.raises(OSError):
                src.rename(dst)
        else:
            # The rename happens locally but:
            #     - nothing remotely
            #     - the folder is re-renamed to its original name
            src.rename(dst)
            self.wait_sync()
            assert local.exists("/foo")
            assert not local.exists("/bar")
            assert remote.exists("/foo")
            assert not remote.exists("/bar")

            # We should not have any error
            assert not self.engine_1.get_dao().get_errors(limit=0)

    @pytest.mark.skipif(not WINDOWS, reason="Windows only.")
    def test_nxdrive_836(self):
        """
        NXDRIVE-836: Bad behaviors with read-only documents on Windows.

Scenario:

1. User1: Server: Create folder "ReadFolder" and share with User2 with read
   permission and upload doc/xml files into it
2. User1: Server: Create folder "MEFolder" and share with User2 with Manage
   Everything permission
3. User2: Server: Enable Nuxeo Drive Synchronization for both folders
4. User2: Client: Launch Drive client and Wait for sync completion
5. User2: Client: Move the files(drag and drop) from "ReadFolder" to "MEFolder"
6. User1: Server: Remove the read permission for "ReadFolder" for User2
7. User2: Client: Remove the read only attribue for moved files in "MEFolder"
   and Edit the files.

Expected Result: Files should sync with the server.
        """

        local = self.local_1
        remote = self.remote_document_client_1

        # Create documents and sync
        remote.make_folder("/", "ReadFolder")
        remote.make_folder("/", "MEFolder")
        remote.make_file("/ReadFolder", "shareme.doc", content=b"Scheherazade")
        self.set_readonly(self.user_1, TEST_WORKSPACE_PATH + "/ReadFolder")
        self.wait_sync(wait_for_async=True)

        # Checks
        for client in (remote, local):
            for doc in ("/ReadFolder/shareme.doc", "/MEFolder"):
                assert client.exists(doc)

        # Move
        src = local.abspath("/ReadFolder/shareme.doc")
        dst = local.abspath("/MEFolder")
        shutil.move(src, dst)
        time.sleep((WIN_MOVE_RESOLUTION_PERIOD // 1000) + 1)
        self.wait_sync()

        # Remove read-only
        self.set_readonly(self.user_1, TEST_WORKSPACE_PATH + "/ReadFolder", grant=False)
        self.wait_sync(wait_for_async=True)
        local.unset_readonly("/MEFolder/shareme.doc")

        # Checks
        assert remote.exists("/ReadFolder/shareme.doc")
        assert remote.exists("/MEFolder/shareme.doc")
        assert not self.engine_1.get_dao().get_errors(limit=0)
        assert not self.engine_1.get_dao().get_unsynchronizeds()
