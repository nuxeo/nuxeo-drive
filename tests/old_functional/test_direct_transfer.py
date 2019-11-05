"""
Test the Direct Transfer feature in differents scenarii.
"""
from contextlib import suppress
from os import scandir
from pathlib import Path
from shutil import copyfile, copytree
from time import sleep
from unittest.mock import patch
from uuid import uuid4

import pytest
from nuxeo.exceptions import HTTPError
from nuxeo.models import Document
from nxdrive.constants import TransferStatus
from nxdrive.options import Options
from requests.exceptions import ConnectionError

from .common import OneUserTest
from .. import ensure_no_exception
from ..markers import not_windows


class TestDirectTransfer(OneUserTest):
    def setUp(self):
        # No sync root, to ease testing
        self.remote_1.unregister_as_root(self.workspace)
        self.engine_1.start()

        # Lower chunk_* options to have chunked uploads without having to create big files
        self.default_chunk_limit = Options.chunk_limit
        self.default_chunk_size = Options.chunk_size
        Options.chunk_limit = 1
        Options.chunk_size = 1

        # The file used for the Direct Transfer (must be > 1 MiB)
        source = self.location / "resources" / "test_engine_migration_duplicate.db"
        # Work with a copy of the file to allow parallel testing
        self.file = self.tmpdir / f"{uuid4()}.bin"
        copyfile(source, self.file)

    def tearDown(self):
        # Restore options
        Options.chunk_limit = self.default_chunk_limit
        Options.chunk_size = self.default_chunk_size

        # Disconnect eventual signals to prevent failures when tests are run in parallel
        with suppress(TypeError):
            self.engine_1.directTranferDuplicateError.disconnect(
                self.app.user_choice_cancel
            )
        with suppress(TypeError):
            self.engine_1.directTranferDuplicateError.disconnect(
                self.app.user_choice_replace
            )

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
        else:
            return bool(doc.properties.get("file:content"))

    def sync_and_check(self, should_have_blob: bool = True) -> None:
        # Sync
        self.wait_sync()

        # Check the error count
        assert not self.engine_1.dao.get_errors(limit=0)

        # Check the uploads count
        assert not list(self.engine_1.dao.get_uploads())

        # Check the file exists on the server and has a blob attached
        if should_have_blob:
            assert self.has_blob()
        else:
            assert not self.has_blob()

    def test_with_engine_not_started(self):
        """A Direct Transfer should work even if engines are stopped."""
        pytest.xfail("Waiting for NXDRIVE-1910")

        engine = self.engine_1
        dao = self.engine_1.dao

        engine.stop()

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with ensure_no_exception():
            engine.direct_transfer(self.file, self.ws.path)
            self.sync_and_check()

    def test_duplicate_file_but_no_blob_attached(self):
        """The file already exists on the server but has no blob attached yet."""

        # Create the document on the server, with no blob attached
        new_doc = Document(
            name=self.file.name, type="File", properties={"dc:title": self.file.name}
        )
        doc = self.root_remote.documents.create(new_doc, parent_path=self.ws.path)
        assert doc.properties.get("file:content") is None

        with ensure_no_exception():
            # The upload should work: the doc will be retrieved and the blob uploaded and attached
            self.engine_1.direct_transfer(self.file, self.ws.path)
            self.sync_and_check()

        # Ensure there is only 1 document on the server
        children = self.remote_document_client_1.get_children_info(self.workspace)
        assert len(children) == 1
        assert children[0].name == self.file.name

    def test_duplicate_file_cancellation(self):
        """The file already exists on the server and has a blob attached.
        Then, the user wants to cancel the transfer.
        """

        # Mimic the user clicking on "Cancel"
        self.engine_1.directTranferDuplicateError.connect(self.app.user_choice_cancel)

        def upload(*_, **__):
            """Patch Remote.upload() to be able to check that nothing will be uploaded."""
            assert 0, "No twice upload should be done!"

        with ensure_no_exception():
            # 1st upload: OK
            self.engine_1.direct_transfer(self.file, self.ws.path)
            self.sync_and_check()

            # 2nd upload: it should be cancelled by the user
            with patch.object(self.engine_1.remote, "upload", new=upload):
                self.engine_1.direct_transfer(self.file, self.ws.path)
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
        self.engine_1.directTranferDuplicateError.connect(self.app.user_choice_replace)

        with ensure_no_exception():
            # 1st upload: OK
            self.engine_1.direct_transfer(self.file, self.ws.path)
            self.sync_and_check()

            # To ease testing, we change local file content
            self.file.write_bytes(b"blob changed!")

            # 2nd upload: the blob should be replaced on the server
            self.engine_1.direct_transfer(self.file, self.ws.path)
            self.sync_and_check()

        # Ensure the signal was emitted
        assert self.app.emitted

        # Ensure there is only 1 document on the server
        children = self.remote_document_client_1.get_children_info(self.workspace)
        assert len(children) == 1
        assert children[0].name == self.file.name

        # Ensure the blob content was updated
        doc = self.app.doc
        assert isinstance(doc, Document)
        assert doc.fetch_blob(xpath="file:content") == b"blob changed!"

    def test_pause_upload_manually(self):
        """
        Pause the transfer by simulating a click on the pause/resume icon
        on the current upload in the systray menu.
        """

        def callback(*_):
            """
            This will mimic what is done in SystrayTranfer.qml:
                - call API.pause_transfer() that will call:
                    - engine.dao.pause_transfer(nature, transfer_uid)
            Then the upload will be paused in Remote.upload().
            """
            # Ensure we have 1 ongoing upload
            uploads = list(dao.get_uploads())
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Pause the upload
            dao.pause_transfer("upload", upload.uid, 50.0)

        engine = self.engine_1
        dao = self.engine_1.dao

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                engine.direct_transfer(self.file, self.ws.path)
                self.wait_sync()
            assert dao.get_uploads_with_status(TransferStatus.PAUSED)

        # Resume the upload
        engine.resume_transfer("upload", list(dao.get_uploads())[0].uid)
        self.sync_and_check()

    def test_pause_upload_automatically(self):
        """
        Pause the transfer by simulating an application exit
        or clicking on the Suspend menu entry from the systray.
        """

        def callback(*_):
            """This will mimic what is done in SystrayMenu.qml: suspend the app."""
            # Ensure we have 1 ongoing upload
            uploads = list(dao.get_uploads())
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Suspend!
            self.manager_1.suspend()

        engine = self.engine_1
        dao = self.engine_1.dao

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                engine.direct_transfer(self.file, self.ws.path)
                self.wait_sync()
            assert dao.get_uploads_with_status(TransferStatus.SUSPENDED)

        # Resume the upload
        self.manager_1.resume()
        self.sync_and_check()

    def test_modifying_paused_upload(self):
        """Modifying a paused upload should discard the current upload."""

        def callback(*_):
            """Pause the upload and apply changes to the document."""
            # Ensure we have 1 ongoing upload
            uploads = list(dao.get_uploads())
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Pause the upload
            dao.pause_transfer("upload", upload.uid, 50.0)

            # Apply changes to the file
            self.file.write_bytes(b"locally changed")

        engine = self.engine_1
        dao = self.engine_1.dao

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                engine.direct_transfer(self.file, self.ws.path)
                self.wait_sync()

        # Resume the upload
        engine.resume_transfer("upload", list(dao.get_uploads())[0].uid)
        self.sync_and_check()
        # Check the local content is correct
        assert self.file.read_bytes() == b"locally changed"

    @not_windows(
        reason="Cannot test the behavior as the local deletion is blocked by the OS."
    )
    def test_deleting_paused_upload(self):
        """Deleting a paused upload should discard the current upload."""

        def callback(*_):
            """Pause the upload and delete the document."""
            # Ensure we have 1 ongoing upload
            uploads = list(dao.get_uploads())
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Pause the upload
            dao.pause_transfer("upload", upload.uid, 50.0)

            # Remove the document
            # (this is the problematic part on Windows, because for the
            #  file descriptor to be released we need to escape from
            #  Remote.upload(), which is not possible from here)
            self.file.unlink()
            assert not self.file.exists()

        engine = self.engine_1
        dao = self.engine_1.dao

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                engine.direct_transfer(self.file, self.ws.path)
                self.wait_sync()

        # Resume the upload
        engine.resume_transfer("upload", list(dao.get_uploads())[0].uid)
        self.sync_and_check(should_have_blob=False)

    def test_not_server_error_upload(self):
        """Test an error happening after chunks were uploaded, at the NuxeoDrive.CreateFile operation call."""

        def link_blob_to_doc(*args, **kwargs):
            """Simulate an exception that is not handled by the Processor."""
            raise ValueError("Mocked exception")

        engine = self.engine_1
        dao = self.engine_1.dao

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "link_blob_to_doc", new=link_blob_to_doc):
            with ensure_no_exception():
                engine.direct_transfer(self.file, self.ws.path)
                self.wait_sync()

                # There should be 1 upload with ONGOING transfer status
                uploads = list(dao.get_uploads())
                assert len(uploads) == 1
                upload = uploads[0]
                assert upload.status == TransferStatus.ONGOING

                # The file exists on the server but has no blob yet
                assert not self.has_blob()

                # The doc should be in error
                assert len(dao.get_errors(limit=0)) == 1

        # Reset the error
        for state in dao.get_errors():
            dao.reset_error(state)

        self.sync_and_check()

    def test_server_error_but_upload_ok(self):
        """
        Test an error happening after chunks were uploaded and the Blob.AttachOnDocument operation call.
        This could happen if a proxy does not understand well the final requests as seen in NXDRIVE-1753.
        """
        pytest.skip("Not yet implemented.")

        def link_blob_to_doc(*args, **kwargs):
            # Call the original method to effectively end the upload process
            link_blob_to_doc_orig(*args, **kwargs)

            # The file should be present on the server
            assert self.remote_1.exists(f"/{self.file.name}")

            # There should be 1 upload with ONGOING transfer status
            uploads = list(dao.get_uploads())
            assert len(uploads) == 1
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # And throw an error
            stack = (
                "The proxy server received an invalid response from an upstream server."
            )
            raise HTTPError(status=502, message="Mocked Proxy Error", stacktrace=stack)

        engine = self.engine_1
        dao = self.engine_1.dao
        link_blob_to_doc_orig = engine.remote.link_blob_to_doc

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "link_blob_to_doc", new=link_blob_to_doc):
            with ensure_no_exception():
                engine.direct_transfer(self.file, self.ws.path)
                self.wait_sync()

                # There should be no upload as the Processor has checked the file existence
                # on the server and so deleted the upload from the database
                assert not list(dao.get_uploads())

        self.sync_and_check()

    def test_server_error_upload(self):
        """Test a server error happening after chunks were uploaded, at the Blob.AttachOnDocument operation call."""

        def link_blob_to_doc(*args, **kwargs):
            """Simulate a server error."""
            raise ConnectionError("Mocked exception")

        engine = self.engine_1
        dao = self.engine_1.dao

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "link_blob_to_doc", new=link_blob_to_doc):
            with ensure_no_exception():
                engine.direct_transfer(self.file, self.ws.path)
                self.wait_sync()

                # There should be 1 upload with ONGOING transfer status
                uploads = list(dao.get_uploads())
                assert len(uploads) == 1
                upload = uploads[0]
                assert upload.status == TransferStatus.ONGOING

                # The file exists on the server but has no blob yet
                assert not self.has_blob()

        self.sync_and_check()

    def test_chunk_upload_error(self):
        """Test a server error happening while uploading chunks."""

        def send_data(*args, **kwargs):
            """Simulate an error."""
            raise ConnectionError("Mocked error")

        def callback(upload):
            """Patch send_data() after chunk 1 is sent."""
            if len(upload.blob.uploadedChunkIds) == 1:
                upload.service.send_data = send_data

        engine = self.engine_1
        dao = self.engine_1.dao
        bad_remote = self.get_bad_remote()
        bad_remote.upload_callback = callback

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine, "remote", new=bad_remote):
            with ensure_no_exception():
                engine.direct_transfer(self.file, self.ws.path)
                self.wait_sync()

                # There should be 1 upload with ONGOING transfer status
                uploads = list(dao.get_uploads())
                assert len(uploads) == 1
                upload = uploads[0]
                assert upload.status == TransferStatus.ONGOING

                # The file exists on the server but has no blob yet
                assert not self.has_blob()

        self.sync_and_check()


class TestDirectTransferFolder(OneUserTest):
    def setUp(self):
        # No sync root, to ease testing
        self.remote_1.unregister_as_root(self.workspace)
        self.engine_1.start()

        # The folder used for the Direct Transfer (must be > 1 MiB)
        folder = self.location / "resources"
        # Work with a copy of the folder to allow parallel testing
        self.folder = self.tmpdir / str(uuid4())
        copytree(folder, self.folder, copy_function=copyfile)

        self.files, self.folders = self.get_tree(self.folder)
        # 10 = tests/resources
        #  3 = tests/resources/i18n
        assert len(self.files) == 10 + 3
        # tests/resources/i18n
        assert len(self.folders) == 1

        # Lower chunk_* options to have chunked uploads without having to create big files
        self.default_chunk_limit = Options.chunk_limit
        self.default_chunk_size = Options.chunk_size
        Options.chunk_limit = 1
        Options.chunk_size = 1

    def tearDown(self):
        # Restore options
        Options.chunk_limit = self.default_chunk_limit
        Options.chunk_size = self.default_chunk_size

    def get_tree(self, path: Path):
        files, folders = [], []

        with scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    files.append(Path(entry.path))
                elif entry.is_dir():
                    folder = Path(entry.path)
                    folders.append(folder)
                    subfiles, subfolders = self.get_tree(folder)
                    files.extend(subfiles)
                    folders.extend(subfolders)

        return files, folders

    def has_blob(self, file: str) -> bool:
        """Check that *file* exists on the server and has a blob attached.
        As when doing a Direct Transfer, the document is first created on the server,
        this is the only way to check if the blob upload has been finished successfully.
        """
        try:
            doc = self.root_remote.documents.get(path=f"{self.ws.path}/{file}")
        except Exception:
            return False
        else:
            return bool(doc.properties.get("file:content"))

    def sync_and_check(self) -> None:
        # Let time for uploads to be planned
        sleep(3)

        # Sync
        self.wait_sync()

        # Check the error count
        assert not self.engine_1.dao.get_errors(limit=0)

        # Check the uploads count
        assert not list(self.engine_1.dao.get_uploads())

        # Check files exist on the server with their attached blob
        for file in self.files:
            doc = str(file.relative_to(self.folder))
            assert self.has_blob(doc)

        # Check subfolders
        for folder in self.folders:
            doc = str(folder.relative_to(self.folder))
            assert self.root_remote.documents.get(path=f"{self.ws.path}/{doc}")

    def test_folder(self):
        """Test the Direct Transfer on a folder containing files and a sufolder."""

        # There is no upload, right now
        assert not list(self.engine_1.dao.get_uploads())

        with ensure_no_exception():
            self.engine_1.direct_transfer(self.folder, self.ws.path)
            self.sync_and_check()
