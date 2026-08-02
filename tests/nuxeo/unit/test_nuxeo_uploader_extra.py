"""Extra unit tests for nxdrive.nuxeo.client.uploader — BaseUploader methods."""

import json
from pathlib import Path
from time import monotonic_ns
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from nxdrive.drive.constants import TransferStatus
from nxdrive.drive.exceptions import UploadCancelled, UploadPaused


def _make_uploader():
    """Create a concrete BaseUploader instance with mocked dependencies."""
    from nxdrive.nuxeo.client.uploader import BaseUploader

    class ConcreteUploader(BaseUploader):
        def get_upload(self, *, path=None, doc_pair=None):
            return self._mock_get_upload(path=path, doc_pair=doc_pair)

        def upload(self, file_path, /, *, command="", filename=None, **kwargs):
            return self.upload_impl(file_path, command, filename=filename, **kwargs)

    with patch.object(BaseUploader, "__init__", return_value=None):
        uploader = ConcreteUploader.__new__(ConcreteUploader)

    uploader.remote = MagicMock()
    uploader.dao = MagicMock()
    uploader.verification_needed = True
    uploader._mock_get_upload = Mock(return_value=None)
    return uploader


def _mock_transfer(**kwargs):
    transfer = Mock()
    defaults = dict(
        uid=1,
        path=Path("/tmp/file.txt"),
        status=TransferStatus.ONGOING,
        batch={"batchId": "batch-1", "provider": ""},
        batch_obj=MagicMock(),
        chunk_size=1024 * 1024,
        engine="eng-1",
        filesize=5000,
        is_direct_transfer=False,
        is_direct_edit=False,
        remote_parent_path="",
        remote_parent_ref="",
        doc_pair=10,
        request_uid=None,
        progress=0,
        is_dirty=False,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(transfer, k, v)
    return transfer


# ---------------------------------------------------------------------------
# _handle_transfer_status
# ---------------------------------------------------------------------------


class TestHandleTransferStatus:
    def test_cancelled_raises_upload_cancelled(self):
        uploader = _make_uploader()
        transfer = _mock_transfer(status=TransferStatus.CANCELLED, uid=42)

        with pytest.raises(UploadCancelled) as exc_info:
            uploader._handle_transfer_status(transfer)
        assert exc_info.value.transfer_id == 42

    def test_paused_raises_upload_paused(self):
        uploader = _make_uploader()
        transfer = _mock_transfer(status=TransferStatus.PAUSED, uid=7)

        with pytest.raises(UploadPaused) as exc_info:
            uploader._handle_transfer_status(transfer)
        assert exc_info.value.transfer_id == 7

    def test_suspended_raises_upload_paused(self):
        uploader = _make_uploader()
        transfer = _mock_transfer(status=TransferStatus.SUSPENDED, uid=3)

        with pytest.raises(UploadPaused) as exc_info:
            uploader._handle_transfer_status(transfer)
        assert exc_info.value.transfer_id == 3

    def test_ongoing_passes(self):
        uploader = _make_uploader()
        transfer = _mock_transfer(status=TransferStatus.ONGOING)

        # Should not raise
        uploader._handle_transfer_status(transfer)

    def test_done_passes(self):
        uploader = _make_uploader()
        transfer = _mock_transfer(status=TransferStatus.DONE)

        # Should not raise
        uploader._handle_transfer_status(transfer)


# ---------------------------------------------------------------------------
# _ping_batch_id
# ---------------------------------------------------------------------------


class TestPingBatchId:
    def test_no_provider_returns_last_ping(self):
        uploader = _make_uploader()
        transfer = _mock_transfer()
        transfer.batch_obj.provider = ""  # No provider

        last_ping = 1000
        result = uploader._ping_batch_id(transfer, last_ping)
        assert result == last_ping

    def test_recent_ping_returns_last_ping(self):
        uploader = _make_uploader()
        transfer = _mock_transfer()
        transfer.batch_obj.provider = "s3"

        # last_ping is very recent (current time)
        last_ping = monotonic_ns()
        result = uploader._ping_batch_id(transfer, last_ping)
        assert result == last_ping
        transfer.batch_obj.get.assert_not_called()

    def test_old_ping_calls_get_and_returns_current(self):
        uploader = _make_uploader()
        transfer = _mock_transfer()
        transfer.batch_obj.provider = "s3"

        # last_ping is old (> 55 minutes ago)
        _56_min_ns = 56 * 60 * 1000 * 1000 * 1000
        last_ping = monotonic_ns() - _56_min_ns

        before = monotonic_ns()
        result = uploader._ping_batch_id(transfer, last_ping)
        after = monotonic_ns()

        transfer.batch_obj.get.assert_called_once_with(None)
        assert before <= result <= after


# ---------------------------------------------------------------------------
# _get_transfer
# ---------------------------------------------------------------------------


class TestGetTransfer:
    def test_existing_paused_transfer_raises(self):
        from nuxeo.constants import UP_AMAZON_S3
        from nuxeo.models import FileBlob

        uploader = _make_uploader()
        existing = _mock_transfer(status=TransferStatus.PAUSED, uid=55)
        uploader._mock_get_upload = Mock(return_value=existing)

        blob = Mock(spec=FileBlob)
        blob.size = 1024

        with pytest.raises(UploadPaused) as exc_info:
            uploader._get_transfer(Path("/tmp/f.txt"), blob, "cmd", doc_pair=1)
        assert exc_info.value.transfer_id == 55

    def test_existing_ongoing_batch_404_restarts(self):
        from nuxeo.exceptions import HTTPError
        from nuxeo.models import FileBlob

        uploader = _make_uploader()
        existing = _mock_transfer(status=TransferStatus.ONGOING, uid=10)
        existing.batch = {"batchId": "old-batch", "provider": ""}
        uploader._mock_get_upload = Mock(return_value=existing)
        uploader.remote.uploads.get.side_effect = HTTPError(status=404, message="gone")

        # When batch is gone, should create a new one
        new_batch = MagicMock()
        new_batch.as_dict.return_value = {"batchId": "new-batch"}
        uploader.remote.uploads.has_s3.return_value = False
        uploader.remote.uploads.batch.return_value = new_batch

        blob = Mock(spec=FileBlob)
        blob.size = 2048

        with patch("nxdrive.nuxeo.client.uploader.Feature") as feature_mock:
            feature_mock.s3 = False
            with patch("nxdrive.nuxeo.client.uploader.Options") as opts_mock:
                opts_mock.chunk_size = 20
                opts_mock.use_idempotent_requests = False
                result = uploader._get_transfer(
                    Path("/tmp/f.txt"), blob, "FileManager.Import", doc_pair=1
                )

        assert result is not None
        # A new transfer should have been saved
        assert uploader.dao.remove_transfer.called

    def test_new_transfer_creation(self):
        from nuxeo.models import FileBlob

        uploader = _make_uploader()
        uploader._mock_get_upload = Mock(return_value=None)

        new_batch = MagicMock()
        new_batch.as_dict.return_value = {"batchId": "fresh-batch"}
        uploader.remote.uploads.has_s3.return_value = False
        uploader.remote.uploads.batch.return_value = new_batch

        blob = Mock(spec=FileBlob)
        blob.size = 4096

        with patch("nxdrive.nuxeo.client.uploader.Feature") as feature_mock:
            feature_mock.s3 = False
            with patch("nxdrive.nuxeo.client.uploader.Options") as opts_mock:
                opts_mock.chunk_size = 20
                opts_mock.use_idempotent_requests = False
                result = uploader._get_transfer(
                    Path("/tmp/f.txt"), blob, "cmd", doc_pair=2
                )

        assert result is not None
        uploader.remote.uploads.batch.assert_called_once()

    def test_json_decode_error_on_batch_creation(self):
        from nuxeo.exceptions import HTTPError
        from nuxeo.models import FileBlob

        uploader = _make_uploader()
        uploader._mock_get_upload = Mock(return_value=None)
        uploader.remote.uploads.has_s3.return_value = False
        uploader.remote.uploads.batch.side_effect = json.JSONDecodeError("err", "", 0)

        blob = Mock(spec=FileBlob)
        blob.size = 1024

        with patch("nxdrive.nuxeo.client.uploader.Feature") as feature_mock:
            feature_mock.s3 = False
            with pytest.raises(HTTPError) as exc_info:
                uploader._get_transfer(Path("/tmp/f.txt"), blob, "cmd", doc_pair=3)
            assert exc_info.value.status == 500

    def test_existing_ongoing_s3_batch_no_file_idx(self):
        """When transfer is S3, file_idx should be None for the get() check."""
        from nuxeo.constants import UP_AMAZON_S3
        from nuxeo.models import Batch, FileBlob

        uploader = _make_uploader()
        existing = _mock_transfer(status=TransferStatus.ONGOING, uid=20)
        existing.batch = {"batchId": "s3-batch", "provider": UP_AMAZON_S3}
        uploader._mock_get_upload = Mock(return_value=existing)
        uploader.remote.uploads.get.return_value = Mock()  # batch still exists

        blob = Mock(spec=FileBlob)
        blob.size = 5000

        with patch("nxdrive.nuxeo.client.uploader.Batch") as batch_cls:
            batch_instance = MagicMock()
            batch_cls.return_value = batch_instance
            result = uploader._get_transfer(Path("/tmp/f.txt"), blob, "cmd", doc_pair=4)

        # For S3, file_idx=None
        uploader.remote.uploads.get.assert_called_once_with("s3-batch", file_idx=None)


# ---------------------------------------------------------------------------
# upload_chunks — basic coverage
# ---------------------------------------------------------------------------


class TestUploadChunks:
    def test_non_chunked_upload(self):
        uploader = _make_uploader()
        transfer = _mock_transfer()
        transfer.batch_obj.is_s3.return_value = False
        transfer.batch_obj.get_uploader.return_value = Mock(chunked=False)

        blob = Mock()
        blob.size = 100
        blob.fd = None

        with patch("nxdrive.nuxeo.client.uploader.QApplication") as qa:
            qa.instance.return_value = None
            uploader.upload_chunks(transfer, blob, False)

        transfer.batch_obj.get_uploader.assert_called_once()
        uploader_obj = transfer.batch_obj.get_uploader.return_value
        uploader_obj.upload.assert_called_once()

    def test_chunked_upload_iterates(self):
        uploader = _make_uploader()
        uploader._ping_batch_id = Mock(return_value=monotonic_ns())
        transfer = _mock_transfer()
        transfer.batch_obj.is_s3.return_value = False

        mock_uploader_obj = Mock()
        mock_uploader_obj.chunked = True
        mock_uploader_obj.chunk_size = 512
        mock_uploader_obj.blob = Mock()
        mock_uploader_obj.blob.uploadedChunkIds = [0, 1, 2]
        mock_uploader_obj.iter_upload.return_value = iter([None, None, None])
        transfer.batch_obj.get_uploader.return_value = mock_uploader_obj

        blob = Mock()
        blob.size = 1536
        blob.fd = None

        with patch("nxdrive.nuxeo.client.uploader.QApplication") as qa:
            qa.instance.return_value = None
            uploader.upload_chunks(transfer, blob, True)

        mock_uploader_obj.iter_upload.assert_called_once()


# ---------------------------------------------------------------------------
# _link_blob_to_doc
# ---------------------------------------------------------------------------


class TestLinkBlobToDoc:
    def test_success_delegates_to_link_blob_to_doc(self):
        uploader = _make_uploader()
        uploader.link_blob_to_doc = Mock(return_value={"uid": "doc-1"})
        transfer = _mock_transfer()
        blob = Mock()

        result = uploader._link_blob_to_doc("cmd", transfer, blob, False)
        assert result == {"uid": "doc-1"}
        uploader.link_blob_to_doc.assert_called_once()

    def test_http_404_sets_status_ongoing_and_reraises(self):
        from nuxeo.exceptions import HTTPError

        uploader = _make_uploader()
        uploader.link_blob_to_doc = Mock(
            side_effect=HTTPError(status=404, message="gone")
        )
        uploader._set_transfer_status = Mock()
        transfer = _mock_transfer()
        blob = Mock()

        with pytest.raises(HTTPError):
            uploader._link_blob_to_doc("cmd", transfer, blob, True)

        uploader._set_transfer_status.assert_called_once_with(
            transfer, TransferStatus.ONGOING
        )

    def test_http_non_404_reraises_without_status_change(self):
        from nuxeo.exceptions import HTTPError

        uploader = _make_uploader()
        uploader.link_blob_to_doc = Mock(
            side_effect=HTTPError(status=500, message="server")
        )
        uploader._set_transfer_status = Mock()
        transfer = _mock_transfer()
        blob = Mock()

        with pytest.raises(HTTPError):
            uploader._link_blob_to_doc("cmd", transfer, blob, False)

        uploader._set_transfer_status.assert_not_called()


# ---------------------------------------------------------------------------
# _set_transfer_status
# ---------------------------------------------------------------------------


class TestSetTransferStatus:
    def test_sets_and_saves(self):
        uploader = _make_uploader()
        transfer = _mock_transfer(status=TransferStatus.ONGOING)

        uploader._set_transfer_status(transfer, TransferStatus.DONE)

        assert transfer.status is TransferStatus.DONE
        uploader.dao.set_transfer_status.assert_called_once_with("upload", transfer)
