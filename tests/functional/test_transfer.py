"""
Test pause/resume transfers in different scenarii.
"""
from unittest.mock import patch

import pytest
from requests.exceptions import ConnectionError

from nxdrive.client.uploader.sync import SyncUploader
from nxdrive.constants import FILE_BUFFER_SIZE, TransferStatus
from nxdrive.options import Options
from nxdrive.state import State

from .. import ensure_no_exception
from ..markers import not_windows
from .conftest import SYNC_ROOT_FAC_ID, OneUserTest


class TestDownload(OneUserTest):
    def setUp(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Lower tmp_file_limit options to have chunked downloads without having to create big files
        self.default_tmp_file_limit = Options.tmp_file_limit
        Options.tmp_file_limit = 1

    def tearDown(self):
        Options.tmp_file_limit = self.default_tmp_file_limit

    def test_pause_download_manually(self):
        """
        Pause the transfer by simulating a click on the pause/resume icon
        on the current download in the systray menu.
        """

        def callback(downloader):
            """
            This will mimic what is done in SystrayTranfer.qml:
                - call API.pause_transfer() that will call:
                    - engine.dao.pause_transfer(nature, transfer_uid)
            Then the download will be paused by the Engine:
                - Engine.suspend_client() (== Remote.download_callback) will:
                    - raise DownloadPaused(download.uid)
            """
            # Ensure we have 1 ongoing download
            downloads = list(dao.get_downloads())
            assert downloads
            download = downloads[0]
            assert download.status == TransferStatus.ONGOING

            nonlocal count

            # Check the TMP file is bigger each iteration
            file_out = engine.download_dir / uid / "test.bin"
            assert file_out.stat().st_size == count * FILE_BUFFER_SIZE

            count += 1
            if count == 2:
                # Pause the download
                dao.pause_transfer("download", download.uid, 25.0)

            # Call the original function to make the paused download
            # effective at the 2nd iteration
            for cb in callback_orig:
                cb(downloader)

        engine = self.engine_1
        dao = self.engine_1.dao
        callback_orig = engine.remote.download_callback
        count = 0

        # Remotely create a file that will be downloaded locally
        uid = self.remote_1.make_file(
            f"{SYNC_ROOT_FAC_ID}{self.workspace}",
            "test.bin",
            content=b"0" * FILE_BUFFER_SIZE * 4,
        ).uid.split("#")[-1]

        # There is no download, right now
        assert not list(dao.get_downloads())

        with patch.object(engine.remote, "download_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync(wait_for_async=True)
            assert dao.get_downloads_with_status(TransferStatus.PAUSED)

        # Resume the download
        engine.resume_transfer("download", list(dao.get_downloads())[0].uid)
        self.wait_sync(wait_for_async=True)
        assert not list(dao.get_downloads())

    def test_pause_download_automatically(self):
        """
        Pause the transfer by simulating an application exit
        or clicking on the Suspend menu entry from the systray.
        """

        def callback(downloader):
            """This will mimic what is done in SystrayMenu.qml: suspend the app."""
            # Ensure we have 1 ongoing download
            downloads = list(dao.get_downloads())
            assert downloads
            download = downloads[0]
            assert download.status == TransferStatus.ONGOING

            # Suspend!
            self.manager_1.suspend()

            # Call the original function to make the suspended download effective
            for cb in callback_orig:
                cb(downloader)

        engine = self.engine_1
        dao = self.engine_1.dao
        callback_orig = engine.remote.download_callback

        # Remotely create a file that will be downloaded locally
        self.remote_1.make_file(
            f"{SYNC_ROOT_FAC_ID}{self.workspace}",
            "test.bin",
            content=b"0" * FILE_BUFFER_SIZE * 2,
        )

        # There is no download, right now
        assert not list(dao.get_downloads())

        with patch.object(engine.remote, "download_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync(wait_for_async=True)
            assert dao.get_downloads_with_status(TransferStatus.SUSPENDED)

        # Resume the download
        self.manager_1.resume()
        self.wait_sync(wait_for_async=True)
        assert not list(dao.get_downloads())

    def test_modifying_paused_download(self):
        """Modifying a paused download should discard the current download."""

        def callback(downloader):
            """Pause the download and apply changes to the document."""
            nonlocal count
            count += 1

            if count == 1:
                # Ensure we have 1 ongoing download
                downloads = list(dao.get_downloads())
                assert downloads
                download = downloads[0]
                assert download.status == TransferStatus.ONGOING

                # Pause the download
                dao.pause_transfer("download", download.uid, 0.0)

                # Apply changes to the document
                remote.update_content(file.uid, b"remotely changed")

            # Call the original function to make the paused download effective
            for cb in callback_orig:
                cb(downloader)

        count = 0
        remote = self.remote_1
        engine = self.engine_1
        dao = self.engine_1.dao
        callback_orig = engine.remote.download_callback

        # Remotely create a file that will be downloaded locally
        file = remote.make_file(
            f"{SYNC_ROOT_FAC_ID}{self.workspace}",
            "test.bin",
            content=b"0" * FILE_BUFFER_SIZE * 2,
        )

        # There is no download, right now
        assert not list(dao.get_downloads())

        with patch.object(engine.remote, "download_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync(wait_for_async=True)

        # Resync and check the local content is correct
        self.wait_sync(wait_for_async=True)
        assert not list(dao.get_downloads())
        assert self.local_1.get_content("/test.bin") == b"remotely changed"

    def test_deleting_paused_download(self):
        """Deleting a paused download should discard the current download."""

        def callback(downloader):
            """Pause the download and delete the document."""
            # Ensure we have 1 ongoing download
            downloads = list(dao.get_downloads())
            assert downloads
            download = downloads[0]
            assert download.status == TransferStatus.ONGOING

            # Pause the download
            dao.pause_transfer("download", download.uid, 0.0)

            # Remove the document
            remote.delete(file.uid)

            # Call the original function to make the paused download effective
            for cb in callback_orig:
                cb(downloader)

        remote = self.remote_1
        engine = self.engine_1
        dao = self.engine_1.dao
        callback_orig = engine.remote.download_callback

        # Remotely create a file that will be downloaded locally
        file = remote.make_file(
            f"{SYNC_ROOT_FAC_ID}{self.workspace}",
            "test.bin",
            content=b"0" * FILE_BUFFER_SIZE * 2,
        )

        # There is no download, right now
        assert not list(dao.get_downloads())

        with patch.object(engine.remote, "download_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync(wait_for_async=True)

        # Resync and check the file does not exist
        self.wait_sync(wait_for_async=True)
        assert not list(dao.get_downloads())
        assert not self.local_1.exists("/test.bin")


class TestUpload(OneUserTest):
    def setUp(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Lower chunk_* options to have chunked uploads without having to create big files
        self.default_chunk_limit = Options.chunk_limit
        self.default_chunk_size = Options.chunk_size
        Options.chunk_limit = 1
        Options.chunk_size = 1

    def tearDown(self):
        Options.chunk_limit = self.default_chunk_limit
        Options.chunk_size = self.default_chunk_size

    def test_pause_upload_manually(self):
        """
        Pause the transfer by simulating a click on the pause/resume icon
        on the current upload in the systray menu.
        """

        def callback(uploader):
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

        # Locally create a file that will be uploaded remotely
        self.local_1.make_file("/", "test.bin", content=b"0" * FILE_BUFFER_SIZE * 2)

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync()
            assert dao.get_uploads_with_status(TransferStatus.PAUSED)

        # Resume the upload
        engine.resume_transfer("upload", list(dao.get_uploads())[0].uid)
        self.wait_sync()
        assert not list(dao.get_uploads())

    def test_pause_upload_automatically(self):
        """
        Pause the transfer by simulating an application exit
        or clicking on the Suspend menu entry from the systray.
        """

        def callback(uploader):
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

        # Locally create a file that will be uploaded remotely
        self.local_1.make_file("/", "test.bin", content=b"0" * FILE_BUFFER_SIZE * 2)

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync()
            assert dao.get_uploads_with_status(TransferStatus.SUSPENDED)

        # Resume the upload
        self.manager_1.resume()
        self.wait_sync()
        assert not list(dao.get_uploads())

    def test_modifying_paused_upload(self):
        """Modifying a paused upload should discard the current upload."""

        def callback(uploader):
            """Pause the upload and apply changes to the document."""
            # Ensure we have 1 ongoing upload
            uploads = list(dao.get_uploads())
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Pause the upload
            dao.pause_transfer("upload", upload.uid, 50.0)

            # Apply changes to the document
            local.update_content("/test.bin", b"locally changed")

        local = self.local_1
        engine = self.engine_1
        dao = self.engine_1.dao

        # Locally create a file that will be uploaded remotely
        self.local_1.make_file("/", "test.bin", content=b"0" * FILE_BUFFER_SIZE * 2)

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync()

        # Resync and check the local content is correct
        self.wait_sync()
        assert not list(dao.get_uploads())
        assert self.local_1.get_content("/test.bin") == b"locally changed"

    @not_windows(
        reason="Cannot test the behavior as the local deletion is blocked by the OS."
    )
    def test_deleting_paused_upload(self):
        """Deleting a paused upload should discard the current upload."""

        def callback(uploader):
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
            local.delete("/test.bin")

        local = self.local_1
        engine = self.engine_1
        dao = self.engine_1.dao

        # Locally create a file that will be uploaded remotely
        self.local_1.make_file("/", "test.bin", content=b"0" * FILE_BUFFER_SIZE * 2)

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync()

        # Resync and check the file does not exist
        self.wait_sync()
        assert not list(dao.get_uploads())
        assert not self.remote_1.exists("/test.bin")

    """
    def test_not_server_error_upload(self):
        ""Test an error happening after chunks were uploaded, at the NuxeoDrive.CreateFile operation call.""

        class BadUploader(SyncUploader):
            ""Used to simulate bad server responses.""

            def link_blob_to_doc(self, *args, **kwargs):
                ""Simulate a server error.""
                raise ValueError("Mocked exception")

        def upload(*args, **kwargs):
            ""Set our specific uploader to simulate server error.""
            kwargs.pop("uploader", None)
            return upload_orig(*args, uploader=BadUploader, **kwargs)

        engine = self.engine_1
        dao = engine.dao
        upload_orig = engine.remote.upload

        # Locally create a file that will be uploaded remotely
        self.local_1.make_file("/", "test.bin", content=b"0" * FILE_BUFFER_SIZE * 2)

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "upload", new=upload):
            with ensure_no_exception():
                self.wait_sync()

                # There should be 1 upload with DONE transfer status
                uploads = list(dao.get_uploads())
                assert len(uploads) == 1
                upload = uploads[0]
                assert upload.status == TransferStatus.DONE

                # The file on the server should not exist yet
                assert not self.remote_1.exists("/test.bin")

                # The doc should be in error
                assert len(dao.get_errors(limit=0)) == 1

        # Reset the error
        for state in dao.get_errors():
            dao.reset_error(state)

        # Resync and check the file exist
        self.wait_sync()
        assert not list(dao.get_uploads())
        assert self.remote_1.exists("/test.bin")
    """

    @pytest.mark.randombug("Randomly fail when run in parallel")
    @Options.mock()
    def test_server_error_upload(self):
        """Test a server error happening after chunks were uploaded, at the NuxeoDrive.CreateFile operation call."""

        class BadUploader(SyncUploader):
            """Used to simulate bad server responses."""

            def link_blob_to_doc(self, *args, **kwargs):
                """Simulate a server error."""
                raise ConnectionError("Mocked exception")

        def upload(*args, **kwargs):
            """Set our specific uploader to simulate server error."""
            kwargs.pop("uploader", None)
            return upload_orig(*args, uploader=BadUploader, **kwargs)

        engine = self.engine_1
        dao = engine.dao
        upload_orig = engine.remote.upload

        # Locally create a file that will be uploaded remotely
        self.local_1.make_file("/", "test.bin", content=b"0" * FILE_BUFFER_SIZE * 2)

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "upload", new=upload):
            with ensure_no_exception():
                self.wait_sync()

                # There should be 1 upload with DONE transfer status
                uploads = list(dao.get_uploads())
                assert len(uploads) == 1
                upload = uploads[0]
                assert upload.status == TransferStatus.DONE

                # The file on the server should not exist yet
                assert not self.remote_1.exists("/test.bin")

        # Resync and check the file exists
        self.wait_sync()
        assert not list(dao.get_uploads())
        assert self.remote_1.exists("/test.bin")

    def test_app_crash_simulation(self):
        """
        When the app crashed, ongoing transfers will be removed at the next run.
        See NXDRIVE-2186 for more information.

        To reproduce the issue, we suspend the transfer in the upload's callback,
        then stop the engine and mimic an app crash by manually changing the transfer
        status and State.has_crashed value.
        """

        def callback(uploader):
            """Suspend the upload and engine."""
            self.manager_1.suspend()

        local = self.local_1
        engine = self.engine_1
        dao = engine.dao

        # Locally create a file that will be uploaded remotely
        local.make_file("/", "test.bin", content=b"0" * FILE_BUFFER_SIZE * 2)

        # There is no upload, right now
        assert not list(dao.get_uploads())

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync()

        # For now, the transfer is only suspended
        assert dao.get_uploads_with_status(TransferStatus.SUSPENDED)

        # Stop the engine
        engine.stop()

        # Change the transfer status to ongoing and change the global State to reflect a crash
        upload = list(dao.get_uploads())[0]
        upload.status = TransferStatus.ONGOING
        dao.set_transfer_status("upload", upload)
        assert dao.get_uploads_with_status(TransferStatus.ONGOING)

        # Simple check: nothing has been uploaded yet
        assert not self.remote_1.exists("/test.bin")

        State.has_crashed = True
        try:
            # Start again the engine, it will manage staled transfers.
            # As the app crashed, no transfers should be removed but continued.
            with ensure_no_exception():
                engine.start()
                self.manager_1.resume()
                self.wait_sync()
        finally:
            State.has_crashed = False

        # Check the file has been uploaded
        assert not list(dao.get_uploads())
        assert self.remote_1.exists("/test.bin")
