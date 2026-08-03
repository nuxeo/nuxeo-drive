"""Unit tests for nxdrive.nuxeo.client.uploader.__init__ (BaseUploader) module."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nxdrive.drive.constants import TransferStatus
from nxdrive.drive.exceptions import UploadCancelled, UploadPaused


def _make_base_uploader():
    """Create a BaseUploader with mocked dependencies."""
    from nxdrive.nuxeo.client.uploader import BaseUploader

    with patch.object(BaseUploader, "__init__", return_value=None):
        uploader = BaseUploader.__new__(BaseUploader)
    uploader.remote = Mock()
    uploader.dao = Mock()
    uploader.verification_needed = True
    return uploader


class TestHandleTransferStatus:
    def test_cancelled_raises(self):
        uploader = _make_base_uploader()
        transfer = Mock()
        transfer.status = TransferStatus.CANCELLED
        transfer.uid = 42
        with pytest.raises(UploadCancelled):
            uploader._handle_transfer_status(transfer)

    def test_paused_raises(self):
        uploader = _make_base_uploader()
        transfer = Mock()
        transfer.status = TransferStatus.PAUSED
        transfer.uid = 10
        with pytest.raises(UploadPaused):
            uploader._handle_transfer_status(transfer)

    def test_ongoing_does_not_raise(self):
        uploader = _make_base_uploader()
        transfer = Mock()
        transfer.status = TransferStatus.ONGOING
        transfer.uid = 5
        # Should not raise
        uploader._handle_transfer_status(transfer)

    def test_done_does_not_raise(self):
        uploader = _make_base_uploader()
        transfer = Mock()
        transfer.status = TransferStatus.DONE
        transfer.uid = 5
        uploader._handle_transfer_status(transfer)


class TestSetTransferStatus:
    def test_sets_status_and_saves(self):
        uploader = _make_base_uploader()
        transfer = Mock()
        transfer.status = TransferStatus.ONGOING
        uploader._set_transfer_status(transfer, TransferStatus.DONE)
        assert transfer.status == TransferStatus.DONE
        uploader.dao.set_transfer_status.assert_called_once_with("upload", transfer)


class TestPingBatchId:
    def test_no_provider_returns_last_ping(self):
        uploader = _make_base_uploader()
        transfer = Mock()
        transfer.batch_obj = Mock()
        transfer.batch_obj.provider = ""
        result = uploader._ping_batch_id(transfer, 100)
        assert result == 100

    def test_within_55_minutes_returns_last_ping(self):
        from time import monotonic_ns

        uploader = _make_base_uploader()
        transfer = Mock()
        transfer.batch_obj = Mock()
        transfer.batch_obj.provider = "s3"
        # Use a recent ping time
        last_ping = monotonic_ns() - (10 * 1000 * 1000 * 1000)  # 10 seconds ago
        result = uploader._ping_batch_id(transfer, last_ping)
        assert result == last_ping

    def test_after_55_minutes_pings_and_returns_new_time(self):
        from time import monotonic_ns

        uploader = _make_base_uploader()
        transfer = Mock()
        transfer.batch_obj = Mock()
        transfer.batch_obj.provider = "s3"
        transfer.batch_obj.uid = "batch-123"
        # Use a very old ping time
        last_ping = monotonic_ns() - (60 * 60 * 1000 * 1000 * 1000)  # 60 min ago
        result = uploader._ping_batch_id(transfer, last_ping)
        assert result > last_ping
        transfer.batch_obj.get.assert_called_once_with(None)


class TestCompleteUpload:
    def test_sets_blob_attributes(self):
        uploader = _make_base_uploader()
        transfer = Mock()
        transfer.batch_obj = Mock()
        transfer.batch_obj.uid = "batch-abc"
        transfer.batch_obj.blobs = {0: None}
        transfer.status = TransferStatus.ONGOING
        blob = Mock()
        uploader._complete_upload(transfer, blob)
        assert blob.batchId == "batch-abc"
        assert blob.fileIdx == 0
        assert transfer.batch_obj.upload_idx == 1
        transfer.batch_obj.complete.assert_called_once()

    def test_done_status_does_not_complete(self):
        uploader = _make_base_uploader()
        transfer = Mock()
        transfer.batch_obj = Mock()
        transfer.batch_obj.uid = "batch-abc"
        transfer.batch_obj.blobs = {0: Mock()}
        transfer.status = TransferStatus.DONE
        blob = Mock()
        uploader._complete_upload(transfer, blob)
        transfer.batch_obj.complete.assert_not_called()


class TestLinkBlobToDoc:
    def test_link_blob_to_doc_404_sets_ongoing(self):
        from nuxeo.exceptions import HTTPError

        uploader = _make_base_uploader()
        transfer = Mock()
        transfer.batch_obj = Mock()
        transfer.batch_obj.uid = "batch-1"
        transfer.request_uid = ""
        transfer.is_direct_transfer = False
        transfer.path = Path("/tmp/test.txt")
        transfer.engine = "eng-1"
        transfer.doc_pair = 1
        blob = Mock()
        blob.size = 100

        uploader.link_blob_to_doc = Mock(
            side_effect=HTTPError(status=404, message="not found")
        )
        with patch("nxdrive.nuxeo.client.uploader.QApplication") as mock_app:
            mock_app.instance.return_value = Mock()
            with pytest.raises(HTTPError):
                uploader._link_blob_to_doc("cmd", transfer, blob, False)
        # Transfer should be set back to ONGOING
        uploader.dao.set_transfer_status.assert_called_once()
        assert transfer.status == TransferStatus.ONGOING


class TestGetTransfer:
    def test_new_transfer_created_when_no_existing(self):
        uploader = _make_base_uploader()
        uploader.get_upload = Mock(return_value=None)
        uploader.remote.uploads = Mock()
        uploader.remote.uploads.has_s3.return_value = False
        mock_batch = Mock()
        mock_batch.as_dict.return_value = {"batchId": "b1", "provider": ""}
        uploader.remote.uploads.batch.return_value = mock_batch

        with patch("nxdrive.nuxeo.client.uploader.Feature") as mock_feature:
            mock_feature.s3 = False
            with patch("nxdrive.nuxeo.client.uploader.Options") as mock_opts:
                mock_opts.chunk_size = 10
                mock_opts.use_idempotent_requests = False

                blob = Mock()
                blob.size = 1000
                transfer = uploader._get_transfer(
                    Path("/tmp/f.txt"), blob, "FileManager.Import"
                )

        assert transfer is not None
        uploader.dao.save_upload.assert_called_once()

    def test_existing_paused_transfer_raises(self):
        uploader = _make_base_uploader()
        existing_transfer = Mock()
        existing_transfer.status = TransferStatus.PAUSED
        existing_transfer.uid = 7
        uploader.get_upload = Mock(return_value=existing_transfer)

        blob = Mock()
        blob.size = 500

        with pytest.raises(UploadPaused):
            uploader._get_transfer(Path("/tmp/f.txt"), blob, "cmd", doc_pair=1)

    def test_existing_ongoing_transfer_resumes(self):
        uploader = _make_base_uploader()
        existing_transfer = Mock()
        existing_transfer.status = TransferStatus.ONGOING
        existing_transfer.batch = {"batchId": "b2", "provider": ""}
        existing_transfer.uid = 5
        uploader.get_upload = Mock(return_value=existing_transfer)
        uploader.remote.uploads = Mock()
        uploader.remote.uploads.get.return_value = Mock()

        blob = Mock()
        blob.size = 500

        with patch("nxdrive.nuxeo.client.uploader.Batch") as mock_batch_cls:
            mock_batch_cls.return_value = Mock()
            transfer = uploader._get_transfer(
                Path("/tmp/f.txt"), blob, "cmd", doc_pair=1
            )
        # Should return the existing transfer with batch_obj attached
        assert transfer.batch_obj is not None


class TestTransferAutoTypeFile:
    def test_executes_command(self):
        uploader = _make_base_uploader()
        uploader.remote.execute.return_value = {"uid": "doc-1"}
        blob = Mock()
        result = uploader._transfer_autoType_file(
            "FileManager.Import", blob, {"params": "value"}
        )
        assert result == {"uid": "doc-1"}
        uploader.remote.execute.assert_called_once()


class TestTransferDocTypeFile:
    def test_creates_document_with_type(self):
        uploader = _make_base_uploader()
        uploader.remote.client = Mock()
        uploader.remote.fetch = Mock(return_value={"uid": "new-doc"})

        transfer = Mock()
        transfer.name = "MyFile.pdf"
        transfer.batch_obj = Mock()
        transfer.batch_obj.uid = "batch-xyz"
        transfer.remote_parent_path = "/workspaces/folder1"

        headers = {"Nuxeo-Transaction-Timeout": "300"}
        result = uploader._transfer_docType_file(transfer, headers, "File")
        assert result == {"uid": "new-doc"}
        uploader.remote.client.request.assert_called_once()
