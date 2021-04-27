import time
from logging import getLogger
from pathlib import Path
from shutil import copyfile
from unittest.mock import patch

import pytest
from nuxeo.utils import version_lt

from nxdrive.engine.engine import Engine
from nxdrive.options import Options

from .common import OS_STAT_MTIME_RESOLUTION, OneUserTest, TwoUsersTest

log = getLogger(__name__)


class TestRemoteDeletion(OneUserTest):
    def test_synchronize_remote_deletion(self):
        """Test that deleting remote documents is impacted client side

        Use cases:
          - Remotely delete a regular folder
              => Folder should be locally deleted
          - Remotely restore folder from the trash
              => Folder should be locally re-created
          - Remotely delete a synchronization root
              => Synchronization root should be locally deleted
          - Remotely restore synchronization root from the trash
              => Synchronization root should be locally re-created

        See TestIntegrationSecurityUpdates.test_synchronize_denying_read_access
        as the same uses cases are tested
        """
        # Bind the server and root workspace
        self.engine_1.start()
        # Get local and remote clients
        local = self.local_1
        remote = self.remote_document_client_1
        remote_admin = self.root_remote

        # Create documents in the remote root workspace
        # then synchronize
        folder_id = remote.make_folder("/", "Test folder")
        file_id = remote.make_file("/Test folder", "joe.txt", content=b"Some content")

        self.wait_sync(wait_for_async=True)
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.txt")

        # Delete remote folder then synchronize
        remote.delete("/Test folder")
        self.wait_sync(wait_for_async=True)
        assert not local.exists("/Test folder")

        # Restore folder from trash then synchronize
        remote.undelete(folder_id)
        if version_lt(remote.client.server_version, "10.2"):
            remote.undelete(file_id)
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.txt")

        # Delete sync root then synchronize
        remote_admin.delete(self.workspace)
        self.wait_sync(wait_for_async=True)
        assert not local.exists("/")

        # Restore sync root from trash then synchronize
        remote_admin.undelete(self.workspace)
        if version_lt(remote.client.server_version, "10.2"):
            remote_admin.undelete(folder_id)
            remote_admin.undelete(file_id)
        self.wait_sync(wait_for_async=True)
        assert local.exists("/")
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.txt")

    def test_synchronize_remote_deletion_while_upload(self):
        local = self.local_1
        remote = self.remote_document_client_1
        self.engine_1.start()

        def callback(uploader):
            """Add delay when upload and download."""
            time.sleep(1)
            Engine.suspend_client(self.engine_1, uploader)

        with patch.object(self.engine_1.remote, "download_callback", new=callback):
            # Create documents in the remote root workspace
            remote.make_folder("/", "Test folder")
            self.wait_sync(wait_for_async=True)

            # Create a document by streaming a binary file
            file_path = local.abspath("/Test folder") / "testFile.pdf"
            copyfile(self.location / "resources" / "files" / "testFile.pdf", file_path)
            file_path = local.abspath("/Test folder") / "testFile2.pdf"
            copyfile(self.location / "resources" / "files" / "testFile.pdf", file_path)

            # Delete remote folder then synchronize
            remote.delete("/Test folder")
            self.wait_sync(wait_for_async=True)
            assert not local.exists("/Test folder")

    @Options.mock()
    @pytest.mark.randombug("NXDRIVE-1329", repeat=4)
    def test_synchronize_remote_deletion_while_download_file(self):
        local = self.local_1
        remote = self.remote_document_client_1

        def callback(uploader):
            """Add delay when upload and download."""
            if not self.engine_1.has_delete:
                # Delete remote file while downloading
                try:
                    remote.delete("/Test folder/testFile.pdf")
                except Exception:
                    log.exception("Cannot trash")
                else:
                    self.engine_1.has_delete = True
            time.sleep(1)
            Engine.suspend_client(self.engine_1, uploader)

        self.engine_1.start()
        self.engine_1.has_delete = False

        filepath = self.location / "resources" / "files" / "testFile.pdf"

        Options.set("tmp_file_limit", 0.1, setter="manual")
        with patch.object(self.engine_1.remote, "download_callback", new=callback):
            remote.make_folder("/", "Test folder")
            remote.make_file("/Test folder", "testFile.pdf", file_path=filepath)

            self.wait_sync(wait_for_async=True)
            # Sometimes the server does not return the document trash action in summary changes.
            # So it may fail on the next assertion.
            assert not local.exists("/Test folder/testFile.pdf")

    def test_synchronize_remote_deletion_with_close_name(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        local = self.local_1
        remote = self.remote_document_client_1
        remote.make_folder("/", "Folder 1")
        remote.make_folder("/", "Folder 1b")
        remote.make_folder("/", "Folder 1c")
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Folder 1")
        assert local.exists("/Folder 1b")
        assert local.exists("/Folder 1c")
        remote.delete("/Folder 1")
        remote.delete("/Folder 1b")
        remote.delete("/Folder 1c")
        self.wait_sync(wait_for_async=True)
        assert not local.exists("/Folder 1")
        assert not local.exists("/Folder 1b")
        assert not local.exists("/Folder 1c")

    def test_synchronize_remote_deletion_with_wrong_local_remote_id(self):
        local = self.local_1
        remote = self.remote_document_client_1
        remote.make_file("/", "joe.txt", content=b"Some content")

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        assert local.exists("/joe.txt")

        self.engine_1.suspend()
        local.set_remote_id(Path("joe.txt"), "wrong-id")
        remote.delete("/joe.txt")

        self.engine_1.resume()
        self.wait_sync(wait_for_async=True)
        assert local.exists("/joe.txt")

    def test_synchronize_local_folder_rename_remote_deletion(self):
        """Test local folder rename followed by remote deletion"""
        # Bind the server and root workspace

        # Get local and remote clients
        self.engine_1.start()
        local = self.local_1
        remote = self.remote_document_client_1

        # Create a folder with a child file in the remote root workspace
        # then synchronize
        test_folder_uid = remote.make_folder("/", "Test folder")
        remote.make_file(test_folder_uid, "joe.odt", content=b"Some content")

        self.wait_sync(wait_for_async=True)
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.odt")

        # Locally rename the folder then synchronize
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.rename("/Test folder", "Test folder renamed")

        self.wait_sync()
        assert not local.exists("/Test folder")
        assert local.exists("/Test folder renamed")
        assert remote.get_info(test_folder_uid).name == "Test folder renamed"

        # Delete remote folder then synchronize
        remote.delete("/Test folder renamed")

        self.wait_sync(wait_for_async=True)
        assert not remote.exists("/Test folder renamed")
        assert not local.exists("/Test folder renamed")


class TestRemoteDeletion2(TwoUsersTest):
    def test_synchronize_local_folder_lost_permission(self):
        """Test local folder rename followed by remote deletion"""
        # Bind the server and root workspace

        # Get local and remote clients
        self.engine_2.start()
        local = self.local_2
        remote = self.remote_document_client_2

        # Create a folder with a child file in the remote root workspace
        # then synchronize
        test_folder_uid = remote.make_folder("/", "Test folder")
        remote.make_file(test_folder_uid, "joe.odt", content=b"Some content")

        self.wait_sync(
            wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True
        )
        assert local.exists("/Test folder")
        assert local.exists("/Test folder/joe.odt")
        input_obj = "doc:" + self.workspace
        self.root_remote.execute(
            command="Document.RemoveACL", input_obj=input_obj, acl="local"
        )
        self.wait_sync(
            wait_for_async=True, wait_for_engine_1=False, wait_for_engine_2=True
        )
        assert not local.exists("/Test folder")
