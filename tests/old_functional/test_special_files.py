from shutil import copyfile

from .. import ensure_no_exception
from .common import OneUserTest


class TestSpecialFiles(OneUserTest):
    def test_keynote(self):
        """Syncing a (macOS) Keynote file should work (NXDRIVE-619).
        Both sync directions are tests.
        """
        local = self.local_1
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # The testing file
        src = self.location / "resources" / "files" / "keynote.key"

        # Create a local file
        file = local.abspath("/") / "keynote1.key"
        copyfile(src, file)

        # Create a distant file
        remote.make_file("/", "keynote2.key", content=src.read_bytes())

        # Sync
        with ensure_no_exception():
            self.wait_sync(wait_for_async=True)

        # Checks
        assert not self.engine_1.dao.get_errors(limit=0)
        for idx in range(1, 3):
            assert local.exists(f"/keynote{idx}.key")
            assert remote.exists(f"/keynote{idx}.key")
