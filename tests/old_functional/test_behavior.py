"""
Test application Behavior.
"""
from nxdrive.behavior import Behavior

from .. import ensure_no_exception
from .common import OneUserTest


class TestBehavior(OneUserTest):
    def test_server_deletion(self):
        """When server deletion is forbidden, then no remote deletion should be made."""

        local = self.local_1
        remote = self.remote_document_client_1
        self.engine_1.start()

        # Create a remote folder with 1 child, then sync
        remote.make_folder("/", "folder")
        remote.make_file("/folder", "file.bin", content=b"42")
        self.wait_sync(wait_for_async=True)

        # Check everything is synced
        assert local.exists("/folder")
        assert local.exists("/folder/file.bin")

        # Update the server deletion behavior
        Behavior.server_deletion = False

        try:
            # Locally delete the file, then sync
            local.delete("/folder/file.bin")
            self.wait_sync()
            assert not local.exists("/folder/file.bin")

            # The remote file should still be present
            assert remote.exists("/folder")
            assert remote.exists("/folder/file.bin")

            # The file should be filtered
            filters = self.engine_1.dao.get_filters()
            assert len(filters) == 1

            # Locally delete the folder, then sync
            local.delete("/folder")
            self.wait_sync()
            assert not local.exists("/folder")

            # The remote folder and its child should still be present
            assert remote.exists("/folder")
            assert remote.exists("/folder/file.bin")

            # The folder should be filtered
            # (there is still only 1 filter as file is a subfilter of folder)
            filters = self.engine_1.dao.get_filters()
            assert len(filters) == 1
        finally:
            # Restore the server deletion behavior
            Behavior.server_deletion = True

        # [Deeper test]

        # Update the remote file
        remote.update_content("/folder/file.bin", b"222")

        # And see what happens
        with ensure_no_exception():
            self.wait_sync(wait_for_async=True)

        # Nothing should be locally created
        assert not local.exists("/folder")

        # And the folder should still be filtered
        assert len(self.engine_1.dao.get_filters()) == 1
