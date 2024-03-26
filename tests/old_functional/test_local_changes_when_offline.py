""""
Test if changes made to local file system when Drive is offline sync's back
later when Drive becomes online.
"""
import pytest

from nxdrive.constants import WINDOWS

from .common import FILE_CONTENT, OneUserTest


class TestOfflineChangesSync(OneUserTest):
    def setUp(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        self.local = self.local_1
        self.remote = self.remote_document_client_1

        # Create a folder and a file on the server
        self.folder1_remote = self.remote.make_folder("/", "Folder1")
        self.file1_remote = self.remote.make_file(
            self.folder1_remote, "File1.txt", FILE_CONTENT
        )
        self.wait_sync(wait_for_async=True)

    def test_copy_paste_when_engine_suspended(self):
        """
        Copy paste and a rename operation together on same file while Drive is
        offline should be detected and synced to server as soon as Drive comes
        back online.
        """
        self.copy_past_and_rename(stop_engine=True)

    @pytest.mark.randombug("Unstable on Windows", condition=WINDOWS)
    def test_copy_paste_normal(self):
        """
        Copy paste and a rename operation together on same file while Drive is
        online should be detected and synced to server.
        """
        self.copy_past_and_rename()
