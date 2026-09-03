"""Deterministic unit coverage for the Nuxeo base uploader."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, patch
from uuid import UUID

import pytest
from botocore.exceptions import ClientError
from nuxeo.constants import IDEMPOTENCY_KEY, UP_AMAZON_S3
from nuxeo.exceptions import HTTPError

from nxdrive.drive.constants import TX_TIMEOUT, TransferStatus
from nxdrive.drive.exceptions import UploadCancelled, UploadPaused
from nxdrive.drive.metrics.constants import REQUEST_METRICS, UPLOAD_PROVIDER
from nxdrive.nuxeo.client.uploader import BaseUploader

MODULE = "nxdrive.nuxeo.client.uploader"


class ConcreteUploader(BaseUploader):
    """Minimal concrete implementation used to exercise ``BaseUploader``."""

    def get_upload(self, *, path=None, doc_pair=None):
        return self._mock_get_upload(path=path, doc_pair=doc_pair)

    def upload(self, file_path, /, *, command="", filename=None, **kwargs):
        return self.upload_impl(file_path, command, filename=filename, **kwargs)


def _uploader() -> ConcreteUploader:
    uploader = ConcreteUploader.__new__(ConcreteUploader)
    uploader.remote = MagicMock()
    uploader.dao = MagicMock()
    uploader.verification_needed = True
    uploader._mock_get_upload = Mock(return_value=None)
    return uploader


def _batch(*, s3=False, provider="", etag=None):
    batch = MagicMock()
    batch.uid = "batch-1"
    batch.provider = provider
    batch.etag = etag
    batch.blobs = {0: None}
    batch.is_s3.return_value = s3
    batch.as_dict.return_value = {
        "batchId": batch.uid,
        "provider": UP_AMAZON_S3 if s3 else provider,
    }
    return batch


def _transfer(**overrides):
    values = {
        "uid": 7,
        "name": "file.txt",
        "path": Path("/virtual/file.txt"),
        "status": TransferStatus.ONGOING,
        "batch": {"batchId": "batch-1", "provider": ""},
        "batch_obj": _batch(),
        "chunk_size": 1024,
        "engine": "engine-1",
        "filesize": 2048,
        "is_direct_edit": False,
        "is_direct_transfer": False,
        "remote_parent_path": "/parent",
        "remote_parent_ref": "parent-ref",
        "doc_pair": 12,
        "request_uid": None,
        "progress": 0,
        "is_dirty": False,
        "token_callback": Mock(name="token_callback"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _blob(*, size=100, fd=None):
    return SimpleNamespace(
        size=size,
        name="file.txt",
        fd=fd,
        batchId=None,
        fileIdx=None,
    )


def _action(*percentages):
    action = SimpleNamespace(
        progress=0,
        uploaded=False,
        chunk_size=0,
        chunk_transfer_start_time_ns=0,
        is_direct_transfer=False,
        finalizing_status="",
        get_percent=Mock(side_effect=percentages or [100]),
        finish_action=Mock(),
    )
    return action


def test_init_uses_remote_dao_and_tls_verification_setting():
    remote = SimpleNamespace(dao=MagicMock())
    with patch(f"{MODULE}.get_verify", return_value=False) as get_verify:
        uploader = ConcreteUploader(remote)
    assert uploader.remote is remote
    assert uploader.dao is remote.dao
    assert uploader.verification_needed is False
    get_verify.assert_called_once_with()


def test_abstract_base_method_bodies_are_safe_noops():
    uploader = _uploader()
    assert BaseUploader.get_upload(uploader, path=Path("/x"), doc_pair=None) is None
    assert BaseUploader.upload(uploader, Path("/x"), command="noop") is None


def test_get_transfer_rejects_paused_and_unknown_statuses():
    uploader = _uploader()
    paused = _transfer(status=TransferStatus.PAUSED, uid=19)
    uploader._mock_get_upload.return_value = paused
    with pytest.raises(UploadPaused) as exc:
        uploader._get_transfer(Path("/file"), _blob(), "command", doc_pair=1)
    assert exc.value.transfer_id == 19

    paused.status = TransferStatus.SUSPENDED
    with pytest.raises(UploadPaused):
        uploader._get_transfer(Path("/file"), _blob(), "command", doc_pair=1)


def test_get_transfer_resumes_existing_server_batch_with_correct_file_index():
    uploader = _uploader()
    transfer = _transfer(
        batch={"batchId": "existing", "provider": ""},
        status=TransferStatus.ONGOING,
    )
    uploader._mock_get_upload.return_value = transfer
    resumed_batch = _batch()
    with patch(f"{MODULE}.Batch", return_value=resumed_batch) as batch_cls:
        assert uploader._get_transfer(Path("/file"), _blob(), "command") is transfer

    uploader.remote.uploads.get.assert_called_once_with("existing", file_idx=0)
    batch_cls.assert_called_once_with(
        service=uploader.remote.uploads,
        batchId="existing",
        provider="",
    )
    assert transfer.batch_obj is resumed_batch


def test_get_transfer_uses_no_file_index_when_resuming_s3():
    uploader = _uploader()
    transfer = _transfer(
        batch={"batchId": "existing-s3", "provider": UP_AMAZON_S3},
        status=TransferStatus.DONE,
    )
    uploader._mock_get_upload.return_value = transfer
    with patch(f"{MODULE}.Batch", return_value=_batch(s3=True)):
        uploader._get_transfer(Path("/file"), _blob(), "command")
    uploader.remote.uploads.get.assert_called_once_with("existing-s3", file_idx=None)


def test_get_transfer_propagates_non_not_found_batch_errors():
    uploader = _uploader()
    transfer = _transfer(batch={"batchId": "old", "provider": ""})
    uploader._mock_get_upload.return_value = transfer
    uploader.remote.uploads.get.side_effect = HTTPError(status=503, message="down")
    with pytest.raises(HTTPError) as exc:
        uploader._get_transfer(Path("/file"), _blob(), "command")
    assert exc.value.status == 503
    uploader.remote.uploads.batch.assert_not_called()


def test_get_transfer_restarts_missing_batch_and_persists_direct_s3_upload():
    uploader = _uploader()
    obsolete = _transfer(batch={"batchId": "old", "provider": ""})
    uploader._mock_get_upload.return_value = obsolete
    uploader.remote.uploads.get.side_effect = HTTPError(status=404, message="gone")
    uploader.remote.uploads.has_s3.return_value = True
    batch = _batch(s3=True)
    batch.uid = "new-batch"
    batch.as_dict.return_value = {
        "batchId": "new-batch",
        "provider": UP_AMAZON_S3,
    }
    uploader.remote.uploads.batch.return_value = batch
    transfer = _transfer(
        batch=batch.as_dict(),
        batch_obj=None,
        is_direct_transfer=True,
        request_uid=None,
    )
    fixed_uuid = UUID("12345678-1234-5678-1234-567812345678")

    with patch(f"{MODULE}.Feature", SimpleNamespace(s3=True)), patch(
        f"{MODULE}.Options",
        SimpleNamespace(chunk_size=8, use_idempotent_requests=True),
    ), patch(f"{MODULE}.Upload", return_value=transfer) as upload_cls, patch(
        f"{MODULE}.uuid4", return_value=fixed_uuid
    ):
        result = uploader._get_transfer(
            Path("/virtual/file.txt"),
            _blob(size=4096),
            "FileManager.Import",
            doc_pair=42,
            engine_uid="engine-2",
            is_direct_edit=True,
            is_direct_transfer=True,
            remote_parent_path="/parent",
            remote_parent_ref="parent-ref",
        )

    assert result is transfer
    headers = uploader.remote.uploads.batch.call_args.kwargs["headers"]
    assert json.loads(headers[REQUEST_METRICS]) == {UPLOAD_PROVIDER: UP_AMAZON_S3}
    uploader.remote.uploads.batch.assert_called_once_with(
        handler=UP_AMAZON_S3, headers=headers
    )
    uploader.dao.remove_transfer.assert_called_once_with(
        "upload",
        doc_pair=42,
        path=Path("/virtual/file.txt"),
        is_direct_transfer=True,
    )
    upload_cls.assert_called_once_with(
        None,
        Path("/virtual/file.txt"),
        TransferStatus.ONGOING,
        batch=batch.as_dict(),
        chunk_size=8 * 1024 * 1024,
        engine="engine-2",
        filesize=4096,
        is_direct_edit=True,
        is_direct_transfer=True,
        remote_parent_path="/parent",
        remote_parent_ref="parent-ref",
        doc_pair=42,
    )
    assert transfer.request_uid == str(fixed_uuid)
    assert transfer.batch_obj is batch
    uploader.dao.save_dt_upload.assert_called_once_with(transfer)
    uploader.dao.save_upload.assert_not_called()


def test_get_transfer_creates_nuxeo_upload_and_reports_provider():
    uploader = _uploader()
    uploader.remote.uploads.has_s3.return_value = False
    batch = _batch()
    uploader.remote.uploads.batch.return_value = batch
    transfer = _transfer(batch_obj=None)
    with patch(f"{MODULE}.Feature", SimpleNamespace(s3=True)), patch(
        f"{MODULE}.Options",
        SimpleNamespace(chunk_size=5, use_idempotent_requests=False),
    ), patch(f"{MODULE}.Upload", return_value=transfer):
        assert (
            uploader._get_transfer(Path("/virtual/file.txt"), _blob(), "other")
            is transfer
        )

    headers = uploader.remote.uploads.batch.call_args.kwargs["headers"]
    assert json.loads(headers[REQUEST_METRICS]) == {UPLOAD_PROVIDER: "nuxeo"}
    uploader.dao.save_upload.assert_called_once_with(transfer)
    uploader.dao.save_dt_upload.assert_not_called()


def test_get_transfer_converts_invalid_batch_json_to_http_500():
    uploader = _uploader()
    uploader.remote.uploads.has_s3.return_value = False
    uploader.remote.uploads.batch.side_effect = json.JSONDecodeError("bad", "", 0)
    with patch(f"{MODULE}.Feature", SimpleNamespace(s3=False)):
        with pytest.raises(HTTPError) as exc:
            uploader._get_transfer(Path("/file"), _blob(), "command")
    assert exc.value.status == 500
    uploader.dao.save_upload.assert_not_called()


def test_upload_impl_uploads_closes_links_and_keeps_chunk_delete_best_effort():
    uploader = _uploader()
    fd = Mock()
    blob = _blob(size=2 * 1024 * 1024, fd=fd)
    transfer = _transfer()
    transfer.batch_obj.delete.side_effect = RuntimeError("already deleted")
    uploader._get_transfer = Mock(return_value=transfer)
    uploader.upload_chunks = Mock()
    uploader._complete_upload = Mock()
    uploader._link_blob_to_doc = Mock(return_value={"uid": "document"})
    uploader.remote.escapeCarriageReturn.return_value = "safe-name.txt"

    with patch(f"{MODULE}.FileBlob", return_value=blob), patch(
        f"{MODULE}.Options",
        SimpleNamespace(chunk_upload=True, chunk_limit=1),
    ):
        result = uploader.upload_impl(
            Path("/virtual/file.txt"),
            "FileManager.Import",
            filename="unsafe\rname.txt",
            doc_pair=12,
            engine_uid="engine",
            is_direct_edit=True,
            is_direct_transfer=False,
            remote_parent_path="/parent",
            remote_parent_ref="parent",
            custom="kept",
        )

    assert result == {"uid": "document"}
    assert blob.name == "safe-name.txt"
    uploader.upload_chunks.assert_called_once_with(transfer, blob, True)
    fd.close.assert_called_once_with()
    uploader._complete_upload.assert_called_once_with(transfer, blob)
    assert transfer.status is TransferStatus.DONE
    uploader.dao.set_transfer_status.assert_called_once_with("upload", transfer)
    uploader._link_blob_to_doc.assert_called_once_with(
        "FileManager.Import", transfer, blob, True, custom="kept"
    )
    transfer.batch_obj.delete.assert_called_once_with(0)


def test_upload_impl_closes_blob_when_chunk_upload_fails():
    uploader = _uploader()
    fd = Mock()
    blob = _blob(size=100, fd=fd)
    transfer = _transfer()
    uploader._get_transfer = Mock(return_value=transfer)
    uploader.upload_chunks = Mock(side_effect=RuntimeError("upload failed"))
    uploader._complete_upload = Mock()
    uploader._link_blob_to_doc = Mock()

    with patch(f"{MODULE}.FileBlob", return_value=blob), patch(
        f"{MODULE}.Options", SimpleNamespace(chunk_upload=False)
    ):
        with pytest.raises(RuntimeError, match="upload failed"):
            uploader.upload_impl(Path("/virtual/file.txt"), "command")

    fd.close.assert_called_once_with()
    uploader._complete_upload.assert_not_called()
    uploader._link_blob_to_doc.assert_not_called()
    assert transfer.status is TransferStatus.ONGOING


def test_upload_impl_cancels_conflicted_pair_before_linking():
    uploader = _uploader()
    blob = _blob()
    transfer = _transfer(doc_pair=12)
    uploader._get_transfer = Mock(return_value=transfer)
    uploader.upload_chunks = Mock()
    uploader._complete_upload = Mock()
    uploader._link_blob_to_doc = Mock()
    uploader.dao.get_state_from_id.return_value = SimpleNamespace(
        pair_state="conflicted"
    )

    with patch(f"{MODULE}.FileBlob", return_value=blob), patch(
        f"{MODULE}.Options", SimpleNamespace(chunk_upload=False)
    ):
        with pytest.raises(UploadCancelled) as exc:
            uploader.upload_impl(
                Path("/virtual/file.txt"), "NuxeoDrive.CreateFile", doc_pair=12
            )

    assert exc.value.transfer_id == transfer.uid
    transfer.batch_obj.delete.assert_called_once_with(0)
    uploader.dao.remove_transfer.assert_called_once_with("upload", doc_pair=12)
    uploader._link_blob_to_doc.assert_not_called()


def test_upload_impl_skips_completed_s3_data_and_resumes_done_transfer():
    uploader = _uploader()
    blob = _blob(size=100, fd=Mock())
    s3_batch = _batch(s3=True, etag="etag")
    transfer = _transfer(batch_obj=s3_batch)
    uploader._get_transfer = Mock(return_value=transfer)
    uploader.upload_chunks = Mock()
    uploader._complete_upload = Mock()
    uploader._link_blob_to_doc = Mock(return_value={"uid": "s3-doc"})

    with patch(f"{MODULE}.FileBlob", return_value=blob), patch(
        f"{MODULE}.Options", SimpleNamespace(chunk_upload=False)
    ):
        assert uploader.upload_impl(Path("/file"), "command") == {"uid": "s3-doc"}
    uploader.upload_chunks.assert_not_called()
    uploader._complete_upload.assert_called_once_with(transfer, blob)
    assert transfer.status is TransferStatus.DONE

    uploader._complete_upload.reset_mock()
    uploader.dao.set_transfer_status.reset_mock()
    done = _transfer(status=TransferStatus.DONE, batch_obj=_batch())
    uploader._get_transfer.return_value = done
    with patch(f"{MODULE}.FileBlob", return_value=_blob()), patch(
        f"{MODULE}.Options", SimpleNamespace(chunk_upload=False)
    ):
        uploader.upload_impl(Path("/file"), "command")
    uploader._complete_upload.assert_called_once()
    uploader.dao.set_transfer_status.assert_not_called()


def test_handle_and_set_transfer_status_preserve_database_semantics():
    uploader = _uploader()
    with pytest.raises(UploadCancelled) as cancelled:
        uploader._handle_transfer_status(
            _transfer(uid=0, status=TransferStatus.CANCELLED)
        )
    assert cancelled.value.transfer_id == -1
    with pytest.raises(UploadPaused):
        uploader._handle_transfer_status(
            _transfer(uid=3, status=TransferStatus.SUSPENDED)
        )
    uploader._handle_transfer_status(_transfer(status=TransferStatus.ONGOING))
    uploader._handle_transfer_status(_transfer(status=TransferStatus.DONE))

    transfer = _transfer()
    uploader._set_transfer_status(transfer, TransferStatus.DONE)
    assert transfer.status is TransferStatus.DONE
    uploader.dao.set_transfer_status.assert_called_once_with("upload", transfer)


def test_ping_batch_id_is_deterministic_and_refreshes_only_expired_provider():
    uploader = _uploader()
    transfer = _transfer()
    transfer.batch_obj.provider = ""
    assert uploader._ping_batch_id(transfer, 100) == 100

    transfer.batch_obj.provider = "s3"
    with patch(f"{MODULE}.monotonic_ns", return_value=1_000_000):
        assert uploader._ping_batch_id(transfer, 999_999) == 999_999
    transfer.batch_obj.get.assert_not_called()

    expired = 55 * 60 * 1_000_000_000
    with patch(f"{MODULE}.monotonic_ns", return_value=expired + 10):
        assert uploader._ping_batch_id(transfer, 0) == expired + 10
    transfer.batch_obj.get.assert_called_once_with(None)


def test_upload_chunks_s3_persists_resume_tokens_progress_and_final_etag():
    uploader = _uploader()
    batch = _batch(s3=True, provider=UP_AMAZON_S3)
    batch.blobs = {}
    transfer = _transfer(batch_obj=batch, is_dirty=True)
    action = _action(25, 100)
    uploader.upload_action = Mock(return_value=action)
    upload_handler = MagicMock()
    upload_handler.chunked = True
    upload_handler.chunk_size = 512
    upload_handler.blob = SimpleNamespace(uploadedChunkIds=[])

    def chunks():
        upload_handler.blob.uploadedChunkIds = [0]
        yield None
        upload_handler.blob.uploadedChunkIds = [0, 1]
        yield None

    upload_handler.iter_upload.return_value = chunks()
    batch.get_uploader.return_value = upload_handler
    uploader._ping_batch_id = Mock(side_effect=[101, 102])
    uploader._mock_get_upload.return_value = transfer
    blob = _blob(size=1024)

    with patch(f"{MODULE}.QApplication") as application, patch(
        f"{MODULE}.monotonic_ns", return_value=100
    ):
        reporter = application.instance.return_value
        uploader.upload_chunks(transfer, blob, True)

    uploader.upload_action.assert_called_once_with(
        transfer.path,
        blob.size,
        reporter=reporter,
        engine=transfer.engine,
        doc_pair=transfer.doc_pair,
    )
    batch.get_uploader.assert_called_once_with(
        blob,
        chunked=True,
        chunk_size=transfer.chunk_size,
        callback=uploader.remote.upload_callback,
        token_callback=transfer.token_callback,
    )
    assert action.chunk_size == 512
    assert action.chunk_transfer_start_time_ns == 100
    assert uploader._ping_batch_id.call_args_list == [
        call(transfer, 100),
        call(transfer, 101),
    ]
    assert uploader.dao.set_transfer_progress.call_count == 2
    assert transfer.progress == 100
    assert transfer.is_dirty is False
    assert uploader.dao.update_upload.call_count == 3
    upload_handler.upload.assert_called_once_with()
    action.finish_action.assert_called_once_with()


def test_upload_chunks_checks_cancelled_status_after_every_chunk():
    uploader = _uploader()
    transfer = _transfer()
    upload_handler = MagicMock()
    upload_handler.chunked = True
    upload_handler.chunk_size = 100
    upload_handler.blob = SimpleNamespace(uploadedChunkIds=[0])
    upload_handler.iter_upload.return_value = iter([None])
    transfer.batch_obj.get_uploader.return_value = upload_handler
    action = _action(50)
    uploader.upload_action = Mock(return_value=action)
    uploader._ping_batch_id = Mock(return_value=1)
    uploader._mock_get_upload.return_value = _transfer(
        uid=88, status=TransferStatus.CANCELLED
    )

    with pytest.raises(UploadCancelled) as exc:
        uploader.upload_chunks(transfer, _blob(size=200), True)
    assert exc.value.transfer_id == 88
    uploader.dao.set_transfer_progress.assert_called_once_with("upload", transfer)
    action.finish_action.assert_called_once_with()


def test_upload_chunks_non_chunked_calls_callback_and_updates_memory_progress():
    uploader = _uploader()
    transfer = _transfer()
    upload_handler = MagicMock(chunked=False)
    transfer.batch_obj.get_uploader.return_value = upload_handler
    action = _action(100)
    uploader.upload_action = Mock(return_value=action)
    blob = _blob(size=123)

    uploader.upload_chunks(transfer, blob, False)

    upload_handler.upload.assert_called_once_with()
    assert action.progress == 123
    assert transfer.progress == 100
    transfer.batch_obj.get_uploader.assert_called_once_with(
        blob,
        chunked=False,
        chunk_size=transfer.chunk_size,
        callback=uploader.remote.upload_callback,
    )
    action.finish_action.assert_called_once_with()


def test_upload_chunks_ignores_missing_s3_multipart_upload():
    uploader = _uploader()
    transfer = _transfer()
    error = ClientError(
        {"Error": {"Code": "NoSuchUpload", "Message": "gone"}}, "UploadPart"
    )
    transfer.batch_obj.get_uploader.side_effect = error
    action = _action()
    uploader.upload_action = Mock(return_value=action)

    uploader.upload_chunks(transfer, _blob(), True)
    action.finish_action.assert_called_once_with()


def test_upload_chunks_propagates_other_s3_client_errors():
    uploader = _uploader()
    transfer = _transfer()
    error = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "UploadPart"
    )
    transfer.batch_obj.get_uploader.side_effect = error
    action = _action()
    uploader.upload_action = Mock(return_value=action)

    with pytest.raises(ClientError):
        uploader.upload_chunks(transfer, _blob(), True)
    action.finish_action.assert_called_once_with()


def test_upload_chunks_converts_invalid_json_to_http_500():
    uploader = _uploader()
    transfer = _transfer()
    transfer.batch_obj.get_uploader.side_effect = json.JSONDecodeError("bad", "", 0)
    action = _action()
    uploader.upload_action = Mock(return_value=action)

    with pytest.raises(HTTPError) as exc:
        uploader.upload_chunks(transfer, _blob(), True)
    assert exc.value.status == 500
    action.finish_action.assert_called_once_with()


def test_link_wrapper_resets_ongoing_for_both_not_found_formats():
    uploader = _uploader()
    transfer = _transfer(status=TransferStatus.DONE)
    blob = _blob()
    uploader.link_blob_to_doc = Mock(
        side_effect=HTTPError(status=500, message="Status code: 404 from proxy")
    )
    with pytest.raises(HTTPError):
        uploader._link_blob_to_doc("command", transfer, blob, False)
    assert transfer.status is TransferStatus.ONGOING
    uploader.dao.set_transfer_status.assert_called_once_with("upload", transfer)

    uploader.dao.reset_mock()
    uploader.link_blob_to_doc.side_effect = HTTPError(status=409, message="conflict")
    with pytest.raises(HTTPError):
        uploader._link_blob_to_doc("command", transfer, blob, False)
    uploader.dao.set_transfer_status.assert_not_called()


def test_link_blob_to_doc_builds_resilient_headers_for_typed_direct_transfer():
    uploader = _uploader()
    transfer = _transfer(
        request_uid="request-1",
        is_direct_transfer=True,
        name="report.pdf",
    )
    blob = _blob(size=250)
    action = _action()
    uploader.linking_action = Mock(return_value=action)
    uploader._transfer_docType_file = Mock(return_value={"uid": "typed-doc"})
    caller_headers = {"Caller": "test"}

    result = uploader.link_blob_to_doc(
        "command",
        transfer,
        blob,
        True,
        doc_type="File",
        headers=caller_headers,
    )

    assert result == {"uid": "typed-doc"}
    generated = {
        "Nuxeo-Transaction-Timeout": str(TX_TIMEOUT),
        IDEMPOTENCY_KEY: "request-1",
        "X-Batch-No-Drop": "true",
    }
    uploader._transfer_docType_file.assert_called_once_with(transfer, generated, "File")
    assert caller_headers == {"Caller": "test", **generated}
    assert action.is_direct_transfer is True
    action.finish_action.assert_called_once_with()


def test_link_blob_to_doc_uses_automatic_type_and_default_headers():
    uploader = _uploader()
    transfer = _transfer(request_uid=None, is_direct_transfer=False)
    blob = _blob()
    action = _action()
    uploader.linking_action = Mock(return_value=action)
    uploader._transfer_autoType_file = Mock(return_value={"uid": "auto-doc"})

    result = uploader.link_blob_to_doc("command", transfer, blob, False, value=1)

    assert result == {"uid": "auto-doc"}
    passed_kwargs = uploader._transfer_autoType_file.call_args.args[2]
    assert passed_kwargs["value"] == 1
    assert passed_kwargs["headers"] == {"Nuxeo-Transaction-Timeout": str(TX_TIMEOUT)}
    action.finish_action.assert_called_once_with()


@pytest.mark.parametrize(
    ("message", "rotate_request"),
    [
        ("ordinary failure", True),
        ("TCPKeepAliveHTTPSConnectionPool disconnected", False),
    ],
)
def test_link_blob_to_doc_marks_error_and_rotates_only_safe_request_ids(
    message, rotate_request
):
    uploader = _uploader()
    transfer = _transfer(request_uid="old-request")
    blob = _blob()
    action = _action()
    uploader.linking_action = Mock(return_value=action)
    uploader._transfer_autoType_file = Mock(side_effect=RuntimeError(message))
    fixed_uuid = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    with patch(f"{MODULE}.uuid4", return_value=fixed_uuid):
        with pytest.raises(RuntimeError, match=message):
            uploader.link_blob_to_doc("command", transfer, blob, False)

    assert action.finalizing_status == "Error"
    action.finish_action.assert_called_once_with()
    if rotate_request:
        assert transfer.request_uid == str(fixed_uuid)
        uploader.dao.update_upload_requestid.assert_called_once_with(transfer)
    else:
        assert transfer.request_uid == "old-request"
        uploader.dao.update_upload_requestid.assert_not_called()


def test_transfer_auto_type_honors_timeout_and_forwards_execution_arguments():
    uploader = _uploader()
    blob = _blob()
    uploader.remote.execute.return_value = {"uid": "doc"}
    kwargs = {"timeout": 15, "params": {"name": "value"}}
    assert uploader._transfer_autoType_file("command", blob, kwargs) == {"uid": "doc"}
    uploader.remote.execute.assert_called_once_with(
        command="command",
        input_obj=blob,
        timeout=15,
        params={"name": "value"},
    )
    assert "timeout" not in kwargs


def test_transfer_doc_type_posts_content_and_fetches_created_document():
    uploader = _uploader()
    transfer = _transfer(name="report.pdf", remote_parent_path="/folder")
    transfer.batch_obj.uid = "batch-typed"
    uploader.remote.client.api_path = "/api/v1"
    uploader.remote.fetch.return_value = {"uid": "created"}
    headers = {"Header": "value"}

    assert uploader._transfer_docType_file(transfer, headers, "File") == {
        "uid": "created"
    }
    endpoint = "/api/v1/path/folder"
    uploader.remote.client.request.assert_called_once_with(
        "POST",
        endpoint,
        headers=headers,
        data={
            "entity-type": "document",
            "name": "report.pdf",
            "type": "File",
            "properties": {
                "dc:title": "report.pdf",
                "file:content": {
                    "upload-batch": "batch-typed",
                    "upload-fileId": "0",
                },
            },
        },
        ssl_verify=True,
    )
    uploader.remote.fetch.assert_called_once_with(endpoint, headers=headers)


def test_complete_upload_sets_blob_metadata_and_only_completes_ongoing_batch():
    transfer = _transfer()
    transfer.batch_obj.blobs = {0: None}
    blob = _blob()
    BaseUploader._complete_upload(transfer, blob)
    assert blob.batchId == transfer.batch_obj.uid
    assert blob.fileIdx == 0
    assert transfer.batch_obj.upload_idx == 1
    assert transfer.batch_obj.blobs[0] is blob
    transfer.batch_obj.complete.assert_called_once_with(
        headers={"Nuxeo-Transaction-Timeout": str(TX_TIMEOUT)},
        timeout=TX_TIMEOUT,
    )

    done = _transfer(status=TransferStatus.DONE)
    existing_blob = _blob()
    done.batch_obj.blobs = {0: existing_blob}
    BaseUploader._complete_upload(done, blob)
    assert done.batch_obj.blobs[0] is existing_blob
    done.batch_obj.complete.assert_not_called()
