"""
Test the Direct Transfer feature in different scenarii.
"""
from shutil import copyfile
from time import sleep
from unittest.mock import patch
from uuid import uuid4

import pytest
from nuxeo.exceptions import HTTPError
from nxdrive.client.uploader.direct_transfer import DirectTransferUploader
from nxdrive.constants import TransferStatus
from nxdrive.exceptions import NotFound
from nxdrive.options import Options
from requests.exceptions import ConnectionError

from .. import ensure_no_exception
from ..markers import not_windows
from .common import OneUserNoSync, OneUserTest


class DirectTransfer:
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
        source = (
            self.location / "resources" / "databases" / "engine_migration_duplicate.db"
        )
        assert source.stat().st_size > 1024 * 1024

        # Work with a copy of the file to allow parallel testing
        self.file = self.tmpdir / f"{uuid4()}.bin"
        copyfile(source, self.file)

    def tearDown(self):
        # Restore options
        Options.chunk_limit = self.default_chunk_limit
        Options.chunk_size = self.default_chunk_size

    def has_blob(self) -> bool:
        """Check that *self.file* exists on the server and has a blob attached."""
        try:
            children = self.remote_document_client_1.documents.get_children(
                path=self.ws.path
            )
            assert len(children) == 1
            doc = children[0]
            assert doc.properties["dc:title"] == self.file.name
        except Exception:
            return False
        return bool(doc.properties["file:content"])

    def no_uploads(self) -> bool:
        """Check there is no ongoing uploads."""
        assert not self.engine_1.dao.get_dt_upload(path=self.file)

    def sync_and_check(
        self, should_have_blob: bool = True, check_for_blob: bool = True
    ) -> None:
        # Let time for uploads to be planned
        sleep(3)

        # Sync
        self.wait_sync()

        # Check the error count
        assert not self.engine_1.dao.get_errors(limit=0)

        # Check the uploads count
        assert not list(self.engine_1.dao.get_dt_uploads())

        # Check the file exists on the server and has a blob attached

        if not check_for_blob:
            # Useful when checking for duplicates creation
            return

        if should_have_blob:
            assert self.has_blob()
        else:
            assert not self.has_blob()

    def direct_transfer(self, duplicate_behavior: str = "create") -> None:
        self.engine_1.direct_transfer(
            [self.file],
            self.ws.path,
            self.ws.uid,
            duplicate_behavior=duplicate_behavior,
        )

    def test_upload(self):
        """A regular Direct Transfer."""

        # There is no upload, right now
        self.no_uploads()

        with ensure_no_exception():
            self.direct_transfer()
            self.sync_and_check()

    def test_cancel_upload(self):
        """
        Pause the transfer by simulating a click on the pause/resume icon
        on the current upload in the DT window; and cancel the upload.
        """

        def callback(*_):
            """This will mimic what is done in TransferItem.qml."""
            # Ensure we have 1 ongoing upload
            uploads = list(dao.get_dt_uploads())
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Pause the upload
            dao.pause_transfer("upload", upload.uid, 50.0)

        engine = self.engine_1
        dao = self.engine_1.dao

        # There is no upload, right now
        self.no_uploads()

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.direct_transfer()
                self.wait_sync()

            assert dao.get_dt_uploads_with_status(TransferStatus.PAUSED)

            # Cancel the upload
            upload = list(dao.get_dt_uploads())[0]
            engine.cancel_upload(upload.uid)

        self.sync_and_check(should_have_blob=False)

    def test_with_engine_not_started(self):
        """A Direct Transfer should work even if engines are stopped."""
        pytest.xfail("Waiting for NXDRIVE-1910")

        self.engine_1.stop()

        # There is no upload, right now
        self.no_uploads()

        with ensure_no_exception():
            self.direct_transfer()
            self.sync_and_check()

    @Options.mock()
    def test_duplicate_file_create(self):
        """
        The file already exists on the server.
        The user wants to continue the transfer and create a duplicate.
        """

        with ensure_no_exception():
            # 1st upload: OK
            self.direct_transfer()
            self.sync_and_check()

            # 2nd upload: a new document will be created
            self.direct_transfer(duplicate_behavior="create")
            self.sync_and_check(check_for_blob=False)

        # Ensure there are 2 documents on the server
        children = self.remote_document_client_1.get_children_info(self.workspace)
        assert len(children) == 2
        assert children[0].name == self.file.name
        assert children[1].name == self.file.name

    def test_duplicate_file_ignore(self):
        """
        The file already exists on the server.
        The user wants to cancel the transfer to prevent duplicates.
        """

        class NoChunkUpload(DirectTransferUploader):
            def upload_chunks(self, *_, **__):
                """Patch Remote.upload() to be able to check that nothing will be uploaded."""
                assert 0, "No twice upload should be done!"

        def upload(*args, **kwargs):
            """Set our specific uploader to check for twice upload."""
            kwargs.pop("uploader")
            return upload_orig(*args, uploader=NoChunkUpload, **kwargs)

        engine = self.engine_1
        upload_orig = engine.remote.upload

        # There is no upload, right now
        self.no_uploads()

        with ensure_no_exception():
            # 1st upload: OK
            self.direct_transfer()
            self.sync_and_check()

            # 2nd upload: it should be cancelled
            with patch.object(engine.remote, "upload", new=upload):
                self.direct_transfer(duplicate_behavior="ignore")
                self.sync_and_check()

        # Ensure there is only 1 document on the server
        self.sync_and_check()

    @Options.mock()
    def test_duplicate_file_override(self):
        """
        The file already exists on the server.
        The user wants to continue the transfer and replace the document.
        """

        with ensure_no_exception():
            # 1st upload: OK
            self.direct_transfer()
            self.sync_and_check()

            # To ease testing, we change local file content
            self.file.write_bytes(b"blob changed!")

            # 2nd upload: the blob should be replaced on the server
            self.direct_transfer(duplicate_behavior="override")
            self.sync_and_check()

        # Ensure there is only 1 document on the server
        children = self.remote_document_client_1.get_children_info(self.workspace)
        assert len(children) == 1
        assert children[0].name == self.file.name

        # Ensure the blob content was updated
        assert (
            self.remote_1.get_blob(children[0].uid, xpath="file:content")
            == b"blob changed!"
        )

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
            uploads = list(dao.get_dt_uploads())
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Pause the upload
            dao.pause_transfer("upload", upload.uid, 50.0)

        engine = self.engine_1
        dao = self.engine_1.dao

        # There is no upload, right now
        self.no_uploads()

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.direct_transfer()
                self.wait_sync()
            assert dao.get_dt_uploads_with_status(TransferStatus.PAUSED)

        # Resume the upload
        engine.resume_transfer(
            "upload", list(dao.get_dt_uploads())[0].uid, is_direct_transfer=True
        )
        self.sync_and_check()

    def test_pause_upload_automatically(self):
        """
        Pause the transfer by simulating an application exit
        or clicking on the Suspend menu entry from the systray.
        """

        def callback(*_):
            """This will mimic what is done in SystrayMenu.qml: suspend the app."""
            # Ensure we have 1 ongoing upload
            uploads = list(dao.get_dt_uploads())
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Suspend!
            self.manager_1.suspend()

        engine = self.engine_1
        dao = engine.dao

        # There is no upload, right now
        self.no_uploads()

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.direct_transfer()
                self.wait_sync()
            assert dao.get_dt_uploads_with_status(TransferStatus.SUSPENDED)

        # Resume the upload
        self.manager_1.resume()
        self.sync_and_check()

    def test_modifying_paused_upload(self):
        """Modifying a paused upload should discard the current upload."""

        def callback(*_):
            """Pause the upload and apply changes to the document."""
            # Ensure we have 1 ongoing upload
            uploads = list(dao.get_dt_uploads())
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Pause the upload
            dao.pause_transfer("upload", upload.uid, 50.0)

            # Apply changes to the file
            self.file.write_bytes(b"locally changed")

        engine = self.engine_1
        dao = engine.dao

        # There is no upload, right now
        self.no_uploads()

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.direct_transfer()
                self.wait_sync()

        # Resume the upload
        engine.resume_transfer(
            "upload", list(dao.get_dt_uploads())[0].uid, is_direct_transfer=True
        )
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
            uploads = list(dao.get_dt_uploads())
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
        dao = engine.dao

        # There is no upload, right now
        self.no_uploads()

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.direct_transfer()
                self.wait_sync()

        # Resume the upload
        engine.resume_transfer(
            "upload", list(dao.get_dt_uploads())[0].uid, is_direct_transfer=True
        )
        self.sync_and_check(should_have_blob=False)

    def test_server_error_but_upload_ok(self):
        """
        Test an error happening after chunks were uploaded and the FileManager.Import operation call.
        This could happen if a proxy does not understand well the final requests as seen in NXDRIVE-1753.
        """
        pytest.skip("Not yet implemented.")

        class BadUploader(DirectTransferUploader):
            """Used to simulate bad server responses."""

            def link_blob_to_doc(self, *args, **kwargs):
                """Simulate a server error."""
                # Call the original method to effectively end the upload process
                super().link_blob_to_doc(*args, **kwargs)

                # The file should be present on the server
                # assert self.remote.exists(file_path)

                # There should be 1 upload with DONE transfer status
                uploads = list(dao.get_dt_uploads())
                assert len(uploads) == 1
                upload = uploads[0]
                assert upload.status == TransferStatus.DONE

                # And throw an error
                stack = "The proxy server received an invalid response from an upstream server."
                raise HTTPError(
                    status=502, message="Mocked Proxy Error", stacktrace=stack
                )

        def upload(*args, **kwargs):
            """Set our specific uploader to simulate server error."""
            kwargs.pop("uploader")
            return upload_orig(*args, uploader=BadUploader, **kwargs)

        # file_path = f"{self.ws.path}/{self.file.name}"
        engine = self.engine_1
        dao = engine.dao
        upload_orig = engine.remote.upload

        # There is no upload, right now
        self.no_uploads()

        with patch.object(engine.remote, "upload", new=upload):
            with ensure_no_exception():
                self.direct_transfer()
                self.wait_sync()

                # There should be no upload as the Processor has checked the file existence
                # on the server and so deleted the upload from the database
                self.no_uploads()

        self.sync_and_check()

    def test_upload_ok_but_network_lost_in_the_meantime(self):
        """
        NXDRIVE-2233 scenario:

            - Start a Direct Transfer.
            - When all chunks are uploaded, and just after having called the FileManager
              operation: the network connection is lost.
            - The request being started, it has a 6 hours timeout.
            - But the document was created on the server because the call has been made.
            - Finally, after 6 hours, the network was restored in the meantime, but the
              FileManager will throw a 404 error because the batchId was already consumed.
            - The transfer will be displayed in the Direct Transfer window, but nothing more
              will be done.

        Such transfer must be removed from the database.
        """

        class BadUploader(DirectTransferUploader):
            """Used to simulate bad server responses."""

            def link_blob_to_doc(self, *args, **kwargs):
                """End the upload and simulate a network loss."""
                # Call the original method to effectively end the upload process
                super().link_blob_to_doc(*args, **kwargs)

                # And throw an error
                raise NotFound("Mock'ed error")

        def upload(*args, **kwargs):
            """Set our specific uploader."""
            kwargs.pop("uploader")
            return upload_orig(*args, uploader=BadUploader, **kwargs)

        # file_path = f"{self.ws.path}/{self.file.name}"
        engine = self.engine_1
        dao = engine.dao
        upload_orig = engine.remote.upload

        # There is no upload, right now
        self.no_uploads()

        with patch.object(engine.remote, "upload", new=upload):
            with ensure_no_exception():
                self.direct_transfer()
                self.wait_sync()

        # The document has been created
        self.sync_and_check()

        # There should be no upload as the Processor has made the clean-up
        self.no_uploads()

        # There is no state to handle in the database
        assert not dao.get_local_children("/")

    def test_server_error_upload(self):
        """Test a server error happening after chunks were uploaded, at the Blob.AttachOnDocument operation call."""

        class BadUploader(DirectTransferUploader):
            """Used to simulate bad server responses."""

            def link_blob_to_doc(self, *args, **kwargs):
                """Simulate a server error."""
                raise ConnectionError("Mocked exception")

        def upload(*args, **kwargs):
            """Set our specific uploader to simulate server error."""
            kwargs.pop("uploader")
            return upload_orig(*args, uploader=BadUploader, **kwargs)

        engine = self.engine_1
        dao = engine.dao
        upload_orig = engine.remote.upload

        # There is no upload, right now
        self.no_uploads()

        with patch.object(engine.remote, "upload", new=upload):
            with ensure_no_exception():
                self.direct_transfer()
                self.wait_sync()

                # There should be 1 upload with ONGOING transfer status
                uploads = list(dao.get_dt_uploads())
                assert len(uploads) == 1
                upload = uploads[0]
                assert upload.status == TransferStatus.DONE

                # The file does not exist on the server
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
        dao = engine.dao
        bad_remote = self.get_bad_remote()
        bad_remote.upload_callback = callback

        # There is no upload, right now
        self.no_uploads()

        with patch.object(engine, "remote", new=bad_remote):
            with ensure_no_exception():
                self.direct_transfer()
                self.wait_sync()

                # There should be 1 upload with ONGOING transfer status
                uploads = list(dao.get_dt_uploads())
                assert len(uploads) == 1
                upload = uploads[0]
                assert upload.status == TransferStatus.ONGOING

                # The file does not exist on the server
                assert not self.has_blob()

        self.sync_and_check()


class TestDirectTransfer(OneUserTest, DirectTransfer):
    """Direct Transfer in "normal" mode, i.e.: when synchronization features are enabled."""

    def setUp(self):
        DirectTransfer.setUp(self)


class TestDirectTransferNoSync(OneUserNoSync, DirectTransfer):
    """Direct Transfer should work when synchronization features are not enabled."""

    def setUp(self):
        DirectTransfer.setUp(self)


class DirectTransferFolder:
    def setUp(self):
        # No sync root, to ease testing
        self.remote_1.unregister_as_root(self.workspace)
        self.engine_1.start()

    def get_children(self, path, children_list):
        children = self.remote_1.get_children(path)["entries"]
        for child in children:
            if child["type"] == "Folder":
                children_list = self.get_children(child["path"], children_list)
            children_list.append(child["title"])
        return children_list

    def test_simple_folder(self):
        """Test the Direct Transfer on an simple empty folder."""

        # There is no upload, right now
        assert not list(self.engine_1.dao.get_dt_uploads())

        empty_folder = self.tmpdir / str(uuid4())
        empty_folder.mkdir()

        with ensure_no_exception():
            self.engine_1.direct_transfer([empty_folder], self.ws.path, self.ws.uid)
            self.wait_sync()

        # Ensure there is only 1 folder created at the workspace root
        children = self.remote_1.get_children(self.ws.path)["entries"]
        assert len(children) == 1
        assert children[0]["title"] == empty_folder.name

        # All has been uploaded
        assert not list(self.engine_1.dao.get_dt_uploads())

    def test_sub_folders(self):
        """Test the Direct Transfer on an simple empty folder."""

        # There is no upload, right now
        assert not list(self.engine_1.dao.get_dt_uploads())

        created = []

        root_folder = self.tmpdir / str(uuid4())
        root_folder.mkdir()

        created.append(root_folder.name)
        for _ in range(3):
            sub_folder = root_folder / f"folder_{str(uuid4())}"
            sub_folder.mkdir()
            created.append(sub_folder.name)
            for _ in range(2):
                sub_file = sub_folder / f"file_{str(uuid4())}"
                sub_file.write_text("test", encoding="utf8")
                created.append(sub_file.name)

        with ensure_no_exception():
            self.engine_1.direct_transfer([root_folder], self.ws.path, self.ws.uid)
            self.wait_sync()

        # Ensure there is only 1 folder created at the workspace root
        children = self.remote_1.get_children(self.ws.path)["entries"]
        assert len(children) == 1
        root = children[0]

        # All has been uploaded
        children = self.get_children(root["path"], [root["title"]])
        assert sorted(created) == sorted(children)

        # There is nothing more to upload
        assert not list(self.engine_1.dao.get_dt_uploads())

        # And there is no error
        assert not self.engine_1.dao.get_errors(limit=0)

    def test_sub_files(self):
        """Test the Direct Transfer on a folder with many files."""

        # There is no upload, right now
        assert not list(self.engine_1.dao.get_dt_uploads())

        created = []

        root_folder = self.tmpdir / str(uuid4())
        root_folder.mkdir()

        created.append(root_folder.name)
        for _ in range(5):
            sub_file = root_folder / f"file_{str(uuid4())}"
            sub_file.write_text("test", encoding="utf8")
            created.append(sub_file.name)

        with ensure_no_exception():
            self.engine_1.direct_transfer([root_folder], self.ws.path, self.ws.uid)
            self.wait_sync()

        # Ensure there is only 1 folder created at the workspace root
        children = self.remote_1.get_children(self.ws.path)["entries"]
        assert len(children) == 1
        root = children[0]

        # All has been uploaded
        children = self.get_children(root["path"], [root["title"]])
        assert sorted(created) == sorted(children)

        # There is nothing more to upload
        assert not list(self.engine_1.dao.get_dt_uploads())

        # And there is no error
        assert not self.engine_1.dao.get_errors(limit=0)


class TestDirectTransferFolder(OneUserTest, DirectTransferFolder):
    """Direct Transfer in "normal" mode, i.e.: when synchronization features are enabled."""

    def setUp(self):
        DirectTransferFolder.setUp(self)


# class TestDirectTransferFolderNoSync(OneUserNoSync, DirectTransferFolder):
#     """Direct Transfer should work when synchronization features are not enabled."""

#     def setUp(self):
#         DirectTransferFolder.setUp(self)
