""""
Test if changes made to local file system when Drive is offline sync's back
later when Drive becomes online.
"""
from .conftest import FILE_CONTENT, OneUserTest


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

    def copy_past_and_rename(self, stop_engine: bool = False):
        if stop_engine:
            # Make Drive offline (by suspend)
            self.engine_1.suspend()

        # Make a copy of the file (with xattr included)
        self.local_1.copy("/Folder1/File1.txt", "/Folder1/File1 - Copy.txt")

        # Rename the original file
        self.local.rename("/Folder1/File1.txt", "File1_renamed.txt")

        if stop_engine:
            # Bring Drive online (by resume)
            self.engine_1.resume()

        self.wait_sync()

        # Verify there is no local changes
        assert self.local.exists("/Folder1/File1_renamed.txt")
        assert self.local.exists("/Folder1/File1 - Copy.txt")
        assert not self.local.exists("/Folder1/File1.txt")

        # Verify that local changes are uploaded to server successfully
        if self.remote.exists("/Folder1/File1 - Copy.txt"):
            # '/Folder1/File1 - Copy.txt' is uploaded to server.
            # So original file named should be changed as 'File_renamed.txt'
            remote_info = self.remote.get_info(self.file1_remote)
            assert remote_info.name == "File1 - Copy.txt"

        else:
            # Original file is renamed as 'File1 - Copy.txt'.
            # This is a bug only if Drive is online during copy + rename
            assert self.remote.exists("/Folder1/File1_renamed.txt")
            remote_info = self.remote.get_info(self.file1_remote)
            assert remote_info.name == "File1_renamed.txt"

        assert not self.remote.exists("/Folder1/File1.txt")
