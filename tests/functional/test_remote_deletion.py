import time
from logging import getLogger
from unittest.mock import patch

import pytest

from nxdrive.engine.engine import Engine
from nxdrive.options import Options

# from .conftest import OS_STAT_MTIME_RESOLUTION, OneUserTest, TwoUsersTest
from .conftest import OneUserTest

log = getLogger(__name__)


class TestRemoteDeletion(OneUserTest):
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
