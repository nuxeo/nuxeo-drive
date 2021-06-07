"""
Uploader used by the Remote client for all upload stuff.
"""
import json
from abc import abstractmethod
from logging import getLogger
from pathlib import Path
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import uuid4

from botocore.exceptions import ClientError
from nuxeo.constants import IDEMPOTENCY_KEY, UP_AMAZON_S3
from nuxeo.exceptions import HTTPError
from nuxeo.handlers.default import Uploader
from nuxeo.handlers.s3 import UploaderS3  # noqa; fix lazy import error
from nuxeo.models import Batch, FileBlob

from ...constants import TX_TIMEOUT, TransferStatus
from ...engine.activity import LinkingAction, UploadAction
from ...exceptions import UploadCancelled, UploadPaused
from ...feature import Feature
from ...metrics.constants import REQUEST_METRICS, UPLOAD_PROVIDER
from ...objects import Upload
from ...options import Options
from ...qt.imports import QApplication

if TYPE_CHECKING:
    from ..remote_client import Remote  # noqa

log = getLogger(__name__)

# Idempotent requests for those calls
_IDEMPOTENT_CMDS = {"FileManager.Import", "NuxeoDrive.CreateFile"}


class BaseUploader:
    """Upload capabilities for the Remove client."""

    linking_action = LinkingAction
    upload_action = UploadAction

    def __init__(self, remote: "Remote", /) -> None:
        self.remote = remote
        self.dao = remote.dao

    @abstractmethod
    def get_upload(
        self, *, path: Optional[Path], doc_pair: Optional[int]
    ) -> Optional[Upload]:
        """Retrieve the eventual transfer associated to the given *doc_pair*, if provided, else the given *path*."""

    @abstractmethod
    def upload(
        self,
        file_path: Path,
        /,
        *,
        command: str = "",
        filename: str = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Upload a file with a batch."""

    def _get_transfer(
        self, file_path: Path, blob: FileBlob, command: str, /, **kwargs: Any
    ) -> Upload:
        """Get and instantiate a new transfer."""

        # See if there is already a transfer for this file
        doc_pair = kwargs.get("doc_pair")
        transfer = self.get_upload(doc_pair=doc_pair, path=file_path)
        batch: Optional[Batch] = None
        uploads = self.remote.uploads

        if transfer:
            if transfer.status not in (TransferStatus.ONGOING, TransferStatus.DONE):
                log.debug(f"Retrieved paused transfer {transfer}, kept paused then")
                raise UploadPaused(transfer.uid or -1)

            log.debug(f"Retrieved ongoing transfer {transfer}")

            # When fetching for an eventual batch, specifying the file index
            # is not possible for S3 as there is no blob at the current index
            # until the S3 upload is done itself and the call to
            # batch.complete() done.
            file_idx = None if transfer.batch.get("provider", "") == UP_AMAZON_S3 else 0

            # Check if the associated batch still exists server-side
            try:
                uploads.get(transfer.batch["batchId"], file_idx=file_idx)
            except HTTPError as exc:
                if exc.status != 404:
                    raise
                log.debug("No associated batch found, restarting from zero")
                transfer = None
            else:
                log.debug("Associated batch found, resuming the upload")
                batch = Batch(service=uploads, **transfer.batch)

        if not batch:
            # .uploads.handlers() result is cached, so it is convenient to call it each time here
            # in case the server did not answer correctly the previous time and thus S3 would
            # be completely disabled because of a one-time server error.
            handler = UP_AMAZON_S3 if Feature.s3 and uploads.has_s3() else ""

            # Create a new batch
            metrics = {
                REQUEST_METRICS: json.dumps(
                    {
                        UPLOAD_PROVIDER: handler or "nuxeo",
                    }
                )
            }
            try:
                batch = uploads.batch(handler=handler, headers=metrics)
            except json.JSONDecodeError as exc:
                err = "Cannot parse the batch response: invalid data from the server"
                log.warning(err)
                raise HTTPError(status=500, message=err) from exc

            # Remove eventual obsolete upload (it happens when an upload using S3 has invalid metadatas)
            is_direct_transfer = kwargs.get("is_direct_transfer", False)
            self.dao.remove_transfer(
                "upload",
                doc_pair=doc_pair,
                path=file_path,
                is_direct_transfer=is_direct_transfer,
            )

            # Add an upload entry in the database
            transfer = Upload(
                None,
                file_path,
                TransferStatus.ONGOING,
                batch=batch.as_dict(),
                chunk_size=Options.chunk_size * 1024 * 1024,
                engine=kwargs.get("engine_uid", None),
                filesize=blob.size,
                is_direct_edit=kwargs.get("is_direct_edit", False),
                is_direct_transfer=is_direct_transfer,
                remote_parent_path=kwargs.pop("remote_parent_path", ""),
                remote_parent_ref=kwargs.pop("remote_parent_ref", ""),
                doc_pair=kwargs.pop("doc_pair", None),
            )

            # Inject the request UID, if allowed and required
            if Options.use_idempotent_requests and command in _IDEMPOTENT_CMDS:
                transfer.request_uid = str(uuid4())

            log.info(f"Instantiated transfer {transfer}")
            if transfer.is_direct_transfer:
                self.dao.save_dt_upload(transfer)
            else:
                self.dao.save_upload(transfer)

        assert transfer  # Fix for mypy
        transfer.batch_obj = batch
        return transfer

    def _set_transfer_status(self, transfer: Upload, status: TransferStatus, /) -> None:
        """Set and save the transfer status."""
        transfer.status = status
        self.dao.set_transfer_status("upload", transfer)

    def upload_impl(
        self,
        file_path: Path,
        command: str,
        /,
        *,
        filename: str = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Upload flow implementation.
        If command is not None, the operation is executed with the batch as an input.

        If an exception happens at step 1 or 2, the upload will be continued the next
        time the Processor handle the document (it will be postponed due to the error).

        If the error was raised at step 1, the upload will not start from zero: it will
        resume from the next chunk based on what previously chunks were sent.
        This is dependent of the chunk TTL configured on the server (it must be large enough
        to handle big files).

        If the error was raised at step 2, the step 1 will be checked to ensure the blob
        was successfully uploaded. But it most cases, nothing will be uploaded twice.
        Also, if the error is one of HTTP 502 or 503, the Processor will check for
        the file existence to bypass errors happening *after* the operation was successful.
        If it exists, the error is skipped and the upload is seen as a success.
        """

        # Step 0: tweak the blob
        blob = FileBlob(str(file_path))
        if filename:
            blob.name = self.remote.escape(filename)

        # Step 0.5: retrieve or instantiate a new transfer
        transfer = self._get_transfer(file_path, blob, command, **kwargs)
        self._handle_transfer_status(transfer)

        # Step 0.75: delete superfluous arguments that would raise a BadQuery error later
        kwargs.pop("doc_pair", None),
        kwargs.pop("engine_uid", None)
        kwargs.pop("is_direct_edit", None)
        kwargs.pop("is_direct_transfer", None)
        kwargs.pop("remote_parent_path", None)
        kwargs.pop("remote_parent_ref", None)

        # For the upload to be chunked, the Options.chunk_upload must be True
        # and the blob must be bigger than Options.chunk_limit, which by default
        # is equal to Options.chunk_size.
        chunked = Options.chunk_upload and blob.size > Options.chunk_limit * 1024 * 1024

        # Step 1: upload the blob
        if transfer.status is not TransferStatus.DONE:
            # For S3 direct upload, when the ETag is set means it was already completed on S3.
            # No need then to try to resume the upload on S3 as we would only get an error.
            if transfer.batch_obj.is_s3() and transfer.batch_obj.etag:
                log.debug(
                    "The transfer was already completed on S3, jumping to the completion step"
                )
            else:
                try:
                    self.upload_chunks(transfer, blob, chunked)
                finally:
                    if blob.fd:
                        blob.fd.close()

            # Step 1.5: complete the upload
            self._complete_upload(transfer, blob)

            # The data was transferred, save the status for eventual future retries
            self._set_transfer_status(transfer, TransferStatus.DONE)
        else:
            # Ensure the blob has all required attributes
            self._complete_upload(transfer, blob)

        # Step 2: link the uploaded blob to the document
        doc: Dict[str, Any] = self._link_blob_to_doc(
            command, transfer, blob, chunked, **kwargs
        )

        # Lastly, we need to remove the batch as the "X-Batch-No-Drop" header was used in link_blob_to_doc()
        if chunked:
            try:
                transfer.batch_obj.delete(0)
            except Exception:
                log.warning(
                    f"Cannot delete the batchId {transfer.batch_obj.uid!r}",
                    exc_info=True,
                )

        return doc

    def _handle_transfer_status(self, transfer: Upload, /) -> None:
        """Raise the appropriate exception depending on the transfer status."""
        status = transfer.status
        if status is TransferStatus.CANCELLED:
            raise UploadCancelled(transfer.uid or -1)
        if status is TransferStatus.PAUSED or status not in (
            TransferStatus.ONGOING,
            TransferStatus.DONE,
        ):
            raise UploadPaused(transfer.uid or -1)

    def _ping_batch_id(self, transfer: Upload, last_ping: int) -> int:
        """Ping the batchId on a regular basis to prevent its deletions from the transient store.
        Return the last time the ping was done when it was in less than 55 minutes, else the current time,
        to allow the caller to update its *last_ping* value.
        """
        if not transfer.batch_obj.provider:
            # The upload is going through Nuxeo directly, no need to ping.
            return last_ping

        _55_min_in_ns = 55 * 60 * 1000 * 1000 * 1000
        current_ping = monotonic_ns()
        if current_ping - last_ping < _55_min_in_ns:
            # < 55 minutes, no need to ping
            return last_ping

        log.debug(
            f"Pinging the batchId {transfer.batch_obj.uid!r} to prevent its purgation from the transient store"
        )
        # No file_idx when going outside Nuxeo because there is no blob attached yet
        file_idx = None
        # Simple GET to update the batchID TTL in the transient store
        transfer.batch_obj.get(file_idx)

        return current_ping

    def upload_chunks(self, transfer: Upload, blob: FileBlob, chunked: bool, /) -> None:
        """Upload a blob by chunks or in one go."""

        action = self.upload_action(
            transfer.path,
            blob.size,
            reporter=QApplication.instance(),
            engine=transfer.engine,
            doc_pair=transfer.doc_pair,
        )

        action.is_direct_transfer = transfer.is_direct_transfer

        kwargs = {
            "chunked": chunked,
            "chunk_size": transfer.chunk_size,
            "callback": self.remote.upload_callback,
        }
        if transfer.batch_obj.is_s3():
            kwargs["token_callback"] = transfer.token_callback

        try:
            uploader: Uploader = transfer.batch_obj.get_uploader(blob, **kwargs)
            log.debug(f"Using {uploader!r}")

            if uploader.chunked:
                # Update the progress on chunked upload only as the first call to
                # action.progress will set the action.uploaded attr to True for
                # empty files. This is not what we want: empty files are legits.
                action.progress = uploader.chunk_size * len(
                    uploader.blob.uploadedChunkIds
                )

                # Store the chunk size and start time for later transfer speed computation
                action.chunk_size = uploader.chunk_size
                action.chunk_transfer_start_time_ns = monotonic_ns()

                # To prevent the batchId to be purged from the transient store, we need to "ping" it
                # on a regular basis, see ._ping_batch_id()
                last_ping = action.chunk_transfer_start_time_ns

                if transfer.batch_obj.is_s3():
                    # Save the multipart upload ID
                    transfer.batch = transfer.batch_obj.as_dict()
                    self.dao.update_upload(transfer)

                # If there is an UploadError, we catch it from the processor
                for _ in uploader.iter_upload():
                    # Ensure the batchId will not be purged while uploading the content
                    last_ping = self._ping_batch_id(transfer, last_ping)

                    action.progress = action.chunk_size * len(
                        uploader.blob.uploadedChunkIds
                    )

                    # Save the progression
                    transfer.progress = action.get_percent()
                    self.dao.set_transfer_progress("upload", transfer)

                    # Token was refreshed, save it in the database
                    if transfer.is_dirty:
                        log.debug(f"Batch.extraInfo updated with {transfer.batch!r}")
                        self.dao.update_upload(transfer)
                        transfer.is_dirty = False

                    # Handle status changes every time a chunk is sent
                    _transfer = self.get_upload(
                        doc_pair=transfer.doc_pair, path=transfer.path
                    )
                    if _transfer:
                        self._handle_transfer_status(_transfer)
            else:
                uploader.upload()

                # For empty files, this will set action.uploaded to True,
                # telling us that the file was correctly sent to the server.
                action.progress += blob.size

                transfer.progress = action.get_percent()

            if transfer.batch_obj.is_s3():
                if not transfer.batch_obj.blobs:
                    # This may happen when resuming an upload with all parts sent.
                    # Trigger upload() that will complete the MPU and fill required
                    # attributes like the Batch ETag, blob index, etc..
                    uploader.upload()

                # Save the final ETag in the database to prevent future issue if
                # the FileManager throws an error
                transfer.batch = transfer.batch_obj.as_dict()
                self.dao.update_upload(transfer)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchUpload":
                raise
            log.warning(
                "Either the upload ID does not exist or the it was already completed."
            )
        except json.JSONDecodeError as exc:
            err = "Cannot parse the server response: invalid data from the server"
            log.warning(err)
            raise HTTPError(status=500, message=err) from exc
        finally:
            action.finish_action()

    def _link_blob_to_doc(
        self,
        command: str,
        transfer: Upload,
        blob: FileBlob,
        chunked: bool,
        /,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        try:
            return self.link_blob_to_doc(command, transfer, blob, chunked, **kwargs)
        except HTTPError as exc:
            error = str(exc).lower()
            if exc.status == 404 or "status code: 404" in error:
                # In this case, the upload completion may be obsolete or was not done,
                # changing the transfer status to let the Processor handling it again and
                # (re)do the completion.
                self._set_transfer_status(transfer, TransferStatus.ONGOING)
            raise exc

    def link_blob_to_doc(
        self,
        command: str,
        transfer: Upload,
        blob: FileBlob,
        chunked: bool,
        /,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Link the given uploaded *blob* to the given document."""

        headers = {"Nuxeo-Transaction-Timeout": str(TX_TIMEOUT)}
        if transfer.request_uid:
            headers[IDEMPOTENCY_KEY] = transfer.request_uid

        # By default, the batchId will be removed after its first use.
        # We do not want that for better upload resiliency, especially with large files.
        # The batchId must be removed manually then.
        if chunked:
            headers["X-Batch-No-Drop"] = "true"

        action = self.linking_action(
            transfer.path,
            blob.size,
            reporter=QApplication.instance(),
            engine=transfer.engine,
            doc_pair=transfer.doc_pair,
        )
        action.is_direct_transfer = transfer.is_direct_transfer
        if "headers" in kwargs:
            kwargs["headers"].update(headers)
        else:
            kwargs["headers"] = headers
        try:
            res: Dict[str, Any] = self.remote.execute(
                command=command,
                input_obj=blob,
                timeout=kwargs.pop("timeout", TX_TIMEOUT),
                **kwargs,
            )
            return res
        finally:
            action.finish_action()

    @staticmethod
    def _complete_upload(transfer: Upload, blob: FileBlob, /) -> None:
        """Helper to complete an upload."""

        # Set those attributes as FileBlob does not have them and they are required to complete the upload
        blob.batchId = transfer.batch_obj.uid
        blob.fileIdx = 0
        transfer.batch_obj.upload_idx = 1

        if not transfer.batch_obj.blobs or not transfer.batch_obj.blobs[0]:
            transfer.batch_obj.blobs[0] = blob

        # Complete the upload
        if transfer.status is not TransferStatus.DONE:
            timeout = TX_TIMEOUT
            headers = {"Nuxeo-Transaction-Timeout": str(timeout)}
            transfer.batch_obj.complete(headers=headers, timeout=timeout)
