"""
Test pause/resume transfers in differents scenarii.
"""
from unittest.mock import patch

import pytest
from nxdrive.constants import FILE_BUFFER_SIZE, TransferStatus, WINDOWS
from nxdrive.options import Options

from .. import ensure_no_exception
from .common import OneUserTest, SYNC_ROOT_FAC_ID


class TestDownload(OneUserTest):
    def setUp(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

    def test_pause_download_manually(self):
        """
        Pause the transfer by simulating a click on the pause/resume icon
        on the current download in the systray menu.
        """

        def callback(*_, **__):
            """
            This will mimic what is done in SystrayTranfer.qml:
                - call API.pause_transfer() that will call:
                    - engine.get_dao().pause_transfer(nature, transfer_uid)
            Then the download will be paused by the Engine:
                - Engine.suspend_client() (== Remote.download_callback) will:
                    - raise DownloadPaused(download.uid)
            """
            # Ensure we have 1 ongoing download
            downloads = dao.get_downloads()
            assert downloads
            download = downloads[0]
            assert download.status == TransferStatus.ONGOING

            # Pause the download
            dao.pause_transfer("download", download.uid)

            # Call the original function to make the paused download effective
            callback_orig()

        engine = self.engine_1
        dao = self.engine_1.get_dao()
        callback_orig = engine.remote.download_callback

        # Remotely create a file that will be downloaded locally
        self.remote_1.make_file(
            f"{SYNC_ROOT_FAC_ID}{self.workspace}",
            "test.bin",
            content=b"0" * FILE_BUFFER_SIZE * 2,
        )

        # There is no download, right now
        assert not dao.get_downloads()

        with patch.object(engine.remote, "download_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync(wait_for_async=True)
            assert dao.get_downloads_with_status(TransferStatus.PAUSED)

        # Resume the download
        engine.resume_transfer("download", dao.get_downloads()[0].uid)
        self.wait_sync(wait_for_async=True)
        assert not dao.get_downloads()

    def test_pause_download_automatically(self):
        """
        Pause the transfer by simulating an application exit
        or clicking on the Suspend menu entry from the systray.
        """

        def callback(*_, **__):
            """This will mimic what is done in SystrayMenu.qml: suspend the app."""
            # Ensure we have 1 ongoing download
            downloads = dao.get_downloads()
            assert downloads
            download = downloads[0]
            assert download.status == TransferStatus.ONGOING

            # Suspend!
            self.manager_1.suspend()

            # Call the original function to make the suspended download effective
            callback_orig()

        engine = self.engine_1
        dao = self.engine_1.get_dao()
        callback_orig = engine.remote.download_callback

        # Remotely create a file that will be downloaded locally
        self.remote_1.make_file(
            f"{SYNC_ROOT_FAC_ID}{self.workspace}",
            "test.bin",
            content=b"0" * FILE_BUFFER_SIZE * 2,
        )

        # There is no download, right now
        assert not dao.get_downloads()

        with patch.object(engine.remote, "download_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync(wait_for_async=True)
            assert dao.get_downloads_with_status(TransferStatus.SUSPENDED)

        # Resume the download
        self.manager_1.resume()
        self.wait_sync(wait_for_async=True)
        assert not dao.get_downloads()

    def test_modifying_paused_download(self):
        """Modifying a paused download should discard the current download."""

        def callback(*_, **__):
            """Pause the download and apply changes to the document."""
            nonlocal count
            count += 1

            if count == 1:
                # Ensure we have 1 ongoing download
                downloads = dao.get_downloads()
                assert downloads
                download = downloads[0]
                assert download.status == TransferStatus.ONGOING

                # Pause the download
                dao.pause_transfer("download", download.uid)

                # Apply changes to the document
                remote.update_content(file.uid, b"remotely changed")

            # Call the original function to make the paused download effective
            callback_orig()

        count = 0
        remote = self.remote_1
        engine = self.engine_1
        dao = self.engine_1.get_dao()
        callback_orig = engine.remote.download_callback

        # Remotely create a file that will be downloaded locally
        file = remote.make_file(
            f"{SYNC_ROOT_FAC_ID}{self.workspace}",
            "test.bin",
            content=b"0" * FILE_BUFFER_SIZE * 2,
        )

        # There is no download, right now
        assert not dao.get_downloads()

        with patch.object(engine.remote, "download_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync(wait_for_async=True)

        # Resync and check the local content is correct
        self.wait_sync(wait_for_async=True)
        assert not dao.get_downloads()
        assert self.local_1.get_content("/test.bin") == b"remotely changed"

    def test_deleting_paused_download(self):
        """Deleting a paused download should discard the current download."""

        def callback(*_, **__):
            """Pause the download and delete the document."""
            # Ensure we have 1 ongoing download
            downloads = dao.get_downloads()
            assert downloads
            download = downloads[0]
            assert download.status == TransferStatus.ONGOING

            # Pause the download
            dao.pause_transfer("download", download.uid)

            # Remove the document
            remote.delete(file.uid)

            # Call the original function to make the paused download effective
            callback_orig()

        remote = self.remote_1
        engine = self.engine_1
        dao = self.engine_1.get_dao()
        callback_orig = engine.remote.download_callback

        # Remotely create a file that will be downloaded locally
        file = remote.make_file(
            f"{SYNC_ROOT_FAC_ID}{self.workspace}",
            "test.bin",
            content=b"0" * FILE_BUFFER_SIZE * 2,
        )

        # There is no download, right now
        assert not dao.get_downloads()

        with patch.object(engine.remote, "download_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync(wait_for_async=True)

        # Resync and check the file does not exist
        self.wait_sync(wait_for_async=True)
        assert not dao.get_downloads()
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

        def callback(*_):
            """
            This will mimic what is done in SystrayTranfer.qml:
                - call API.pause_transfer() that will call:
                    - engine.get_dao().pause_transfer(nature, transfer_uid)
            Then the upload will be paused in Remote.upload().
            """
            # Ensure we have 1 ongoing upload
            uploads = dao.get_uploads()
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Pause the upload
            dao.pause_transfer("upload", upload.uid)

        engine = self.engine_1
        dao = self.engine_1.get_dao()

        # Locally create a file that will be uploaded remotely
        self.local_1.make_file("/", "test.bin", content=b"0" * FILE_BUFFER_SIZE * 2)

        # There is no upload, right now
        assert not dao.get_uploads()

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync()
            assert dao.get_uploads_with_status(TransferStatus.PAUSED)

        # Resume the upload
        engine.resume_transfer("upload", dao.get_uploads()[0].uid)
        self.wait_sync()
        assert not dao.get_uploads()

    def test_pause_upload_automatically(self):
        """
        Pause the transfer by simulating an application exit
        or clicking on the Suspend menu entry from the systray.
        """

        def callback(*_):
            """This will mimic what is done in SystrayMenu.qml: suspend the app."""
            # Ensure we have 1 ongoing upload
            uploads = dao.get_uploads()
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Suspend!
            self.manager_1.suspend()

        engine = self.engine_1
        dao = self.engine_1.get_dao()

        # Locally create a file that will be uploaded remotely
        self.local_1.make_file("/", "test.bin", content=b"0" * FILE_BUFFER_SIZE * 2)

        # There is no upload, right now
        assert not dao.get_uploads()

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync()
            assert dao.get_uploads_with_status(TransferStatus.SUSPENDED)

        # Resume the upload
        self.manager_1.resume()
        self.wait_sync()
        assert not dao.get_uploads()

    def test_modifying_paused_upload(self):
        """Modifying a paused upload should discard the current upload."""

        def callback(*_):
            """Pause the upload and apply changes to the document."""
            # Ensure we have 1 ongoing upload
            uploads = dao.get_uploads()
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Pause the upload
            dao.pause_transfer("upload", upload.uid)

            # Apply changes to the document
            local.update_content("/test.bin", b"locally changed")

        local = self.local_1
        engine = self.engine_1
        dao = self.engine_1.get_dao()

        # Locally create a file that will be uploaded remotely
        self.local_1.make_file("/", "test.bin", content=b"0" * FILE_BUFFER_SIZE * 2)

        # There is no upload, right now
        assert not dao.get_uploads()

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync()

        # Resync and check the local content is correct
        self.wait_sync()
        assert not dao.get_uploads()
        assert self.local_1.get_content("/test.bin") == b"locally changed"

    @pytest.mark.skipif(
        WINDOWS,
        reason="Cannot test the behavior as the local deletion is blocked by the OS.",
    )
    def test_deleting_paused_upload(self):
        """Deleting a paused upload should discard the current upload."""

        def callback(*_):
            """Pause the upload and delete the document."""
            # Ensure we have 1 ongoing upload
            uploads = dao.get_uploads()
            assert uploads
            upload = uploads[0]
            assert upload.status == TransferStatus.ONGOING

            # Pause the upload
            dao.pause_transfer("upload", upload.uid)

            # Remove the document
            # (this is the problematic part on Windows, because for the
            #  file descriptor to be released we need to escape from
            #  Remote.upload(), which is not possible from here)
            local.delete("/test.bin")

        local = self.local_1
        engine = self.engine_1
        dao = self.engine_1.get_dao()

        # Locally create a file that will be uploaded remotely
        self.local_1.make_file("/", "test.bin", content=b"0" * FILE_BUFFER_SIZE * 2)

        # There is no upload, right now
        assert not dao.get_uploads()

        with patch.object(engine.remote, "upload_callback", new=callback):
            with ensure_no_exception():
                self.wait_sync()

        # Resync and check the file does not exist
        self.wait_sync()
        assert not dao.get_uploads()
        assert not self.remote_1.exists("/test.bin")
