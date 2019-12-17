"""
Test the Direct Transfer feature.
This is not a simple copy of the same test file from functional test.
Here, we test signals transition from within the application.
"""
from contextlib import suppress
from shutil import copyfile
from time import sleep
from unittest.mock import patch
from uuid import uuid4

from nxdrive.options import Options

from .. import ensure_no_exception
from .common import OneUserTest


class TestDirectTransfer(OneUserTest):
    def setUp(self):
        # No sync root, to ease testing
        self.remote_1.unregister_as_root(self.workspace)
        self.engine_1.start()
        self.engine_1.direct_transfer([], "")
        self.dt_manager = self.engine_1.dt_manager

        # Lower chunk_* options to have chunked uploads without having to create big files
        self.default_chunk_limit = Options.chunk_limit
        self.default_chunk_size = Options.chunk_size
        Options.chunk_limit = 1
        Options.chunk_size = 1

        # The file used for the Direct Transfer (must be > 1 MiB)
        source = self.location / "resources" / "test_engine_migration_duplicate.db"
        assert source.stat().st_size > 1024 * 1024

        # Work with a copy of the file to allow parallel testing
        self.file = self.tmpdir / f"{uuid4()}.bin"
        copyfile(source, self.file)

    def tearDown(self):
        # Restore options
        Options.chunk_limit = self.default_chunk_limit
        Options.chunk_size = self.default_chunk_size

        # Disconnect eventual signals to prevent failures when tests are run in parallel
        with suppress(TypeError):
            self.engine_1.directTransferDuplicateError.disconnect(
                self.app.user_choice_cancel
            )
        with suppress(TypeError):
            self.engine_1.directTransferDuplicateError.disconnect(
                self.app.user_choice_replace
            )

    def wait_sync(self) -> None:
        """Wait for the Direct transfer session to finish."""
        for _ in range(30):  # 30 sec maxi
            if not self.dt_manager.is_started:
                break
            sleep(1)

    def sync_and_check(self, should_have_blob: bool = True) -> None:
        # Let some time for the signal to transit (as this is async, the test would fail)
        sleep(3)

        # Sync
        self.wait_sync()

        # Check the error count
        assert not self.engine_1.dao.get_errors(limit=0)

        # Check the file exists on the server and has a blob attached
        blob = self.has_blob()
        assert blob is should_have_blob

    def has_blob(self) -> bool:
        """Check that *self.file* exists on the server and has a blob attached.
        As when doing a Direct Transfer, the document is first created on the server,
        this is the only way to check if the blob upload has been finished successfully.
        """
        try:
            doc = self.root_remote.documents.get(
                path=f"{self.ws.path}/{self.file.name}"
            )
        except Exception:
            return False
        return bool(doc.properties.get("file:content"))

    def test_duplicate_file_cancellation(self):
        """The file already exists on the server and has a blob attached.
        Then, the user wants to cancel the transfer.
        """

        # Mimic the user clicking on "Cancel"
        self.engine_1.directTransferDuplicateError.connect(self.app.user_choice_cancel)

        def upload(*_, **__):
            """Patch Remote.upload() to be able to check that nothing will be uploaded."""
            assert 0, "No twice upload should be done!"

        with ensure_no_exception():
            # 1st upload: OK
            self.engine_1.direct_transfer([self.file], self.ws.path)
            self.sync_and_check()

            # 2nd upload: it should be cancelled by the user
            with patch.object(self.dt_manager.remote, "upload", new=upload):
                self.engine_1.direct_transfer([self.file], self.ws.path)
                self.sync_and_check()

        # Ensure the signal was emitted
        assert self.app.emitted

        # Ensure there is only 1 document on the server
        children = self.remote_document_client_1.get_children_info(self.workspace)
        assert len(children) == 1
        assert children[0].name == self.file.name

    def test_duplicate_file_replace_blob(self):
        """The file already exists on the server and has a blob attached.
        Then, the user wants to replace the blob.
        """

        # Mimic the user clicking on "Replace"
        self.engine_1.directTransferDuplicateError.connect(self.app.user_choice_replace)

        with ensure_no_exception():
            # 1st upload: OK
            self.engine_1.direct_transfer([self.file], self.ws.path)
            self.sync_and_check()

            # To ease testing, we change local file content
            self.file.write_bytes(b"blob changed!")

            # 2nd upload: the blob should be replaced on the server
            self.engine_1.direct_transfer([self.file], self.ws.path)
            self.sync_and_check()

        # Ensure the signal was emitted
        assert self.app.emitted

        # Ensure there is only 1 document on the server
        children = self.engine_1.remote.documents.get_children(path=self.ws.path)
        assert len(children) == 1
        assert children[0].title == self.file.name
        # Ensure the blob content was updated
        assert self.engine_1.remote.get_blob(children[0].uid) == b"blob changed!"
