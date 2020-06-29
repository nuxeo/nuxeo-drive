"""
Uploader used by the Remote client for all upload stuff.
"""
from abc import abstractmethod
from datetime import datetime, timedelta
from logging import getLogger
from pathlib import Path
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, Dict, Optional

from nuxeo.exceptions import HTTPError
from nuxeo.models import Batch, FileBlob
from PyQt5.QtWidgets import QApplication

from ...constants import TX_TIMEOUT, TransferStatus
from ...engine.activity import LinkingAction, UploadAction
from ...exceptions import UploadPaused
from ...feature import Feature
from ...objects import Upload
from ...options import Options

if TYPE_CHECKING:
    from .remote_client import Remote  # noqa
    from ..engine.dao.sqlite import EngineDAO  # noqa

log = getLogger(__name__)


class BaseUploader:
    """Upload capabilities for the Remove client."""

    linking_action = LinkingAction
    upload_action = UploadAction

    def __init__(self, remote: "Remote") -> None:
        self.remote = remote
        self.dao = remote.dao

    @abstractmethod
    def get_upload(self, file_path: Path) -> Optional[Upload]:
        """Retrieve the eventual transfer associated to the given *file_path*."""

    @abstractmethod
    def upload(
        self,
        file_path: Path,
        command: str,
        filename: str = None,
        mime_type: str = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Upload a file with a batch."""

    def upload_impl(
        self,
        file_path: Path,
        command: str,
        filename: str = None,
        mime_type: str = None,
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
        # Step 1: upload the blob
        blob = self.upload_chunks(
            file_path, filename=filename, mime_type=mime_type, **kwargs
        )

        # Step 2: link the uploaded blob to the document
        kwargs["file_path"] = file_path
        return self.link_blob_to_doc(command, blob, **kwargs)

    def upload_chunks(
        self,
        file_path: Path,
        filename: str = None,
        mime_type: str = None,
        **kwargs: Any,
    ) -> FileBlob:
        """Upload a blob by chunks or in one go."""

        action = self.upload_action(file_path, reporter=QApplication.instance())
        blob = FileBlob(str(file_path))
        if filename:
            blob.name = filename
        if mime_type:
            blob.mimetype = mime_type

        batch: Optional[Batch] = None
        chunk_size = None

        # See if there is already a transfer for this file
        transfer = self.get_upload(file_path)

        try:
            if transfer:
                log.debug(f"Retrieved transfer for {file_path!r}: {transfer}")
                if transfer.status not in (TransferStatus.ONGOING, TransferStatus.DONE):
                    raise UploadPaused(transfer.uid or -1)

                # When fetching for an eventual batch, specifying the file index
                # is not possible for S3 as there is no blob at the current index
                # until the S3 upload is done itself and the call to
                # batch.complete() done.
                file_idx = (
                    None
                    if transfer.batch.get("provider", "") == "s3"
                    else transfer.batch["upload_idx"]
                )

                # Check if the associated batch still exists server-side
                try:
                    self.remote.uploads.get(
                        transfer.batch["batchId"], file_idx=file_idx
                    )
                except HTTPError as exc:
                    if exc.status != 404:
                        raise
                    log.debug("No associated batch found, restarting from zero")
                else:
                    log.debug("Associated batch found, resuming the upload")
                    batch = Batch(service=self.remote.uploads, **transfer.batch)
                    chunk_size = transfer.chunk_size

            if not batch:
                # .uploads.handlers() result is cached, so it is convenient to call it each time here
                # in case the server did not answer correctly the previous time and thus S3 would
                # be completely disabled because of a one-time server error.
                handler = "s3" if Feature.s3 and self.remote.uploads.has_s3() else ""

                # Create a new batch and save it in the DB
                batch = self.remote.uploads.batch(handler=handler)

                if batch.is_s3():
                    self._aws_token_ttl(batch.extraInfo["expiration"] / 1000)

            # By default, Options.chunk_size is 20, so chunks will be 20MiB.
            # It can be set to a value between 1 and 20 through the config.ini
            chunk_size = chunk_size or (Options.chunk_size * 1024 * 1024)

            # For the upload to be chunked, the Options.chunk_upload must be True
            # and the blob must be bigger than Options.chunk_limit, which by default
            # is equal to Options.chunk_size.
            chunked = (
                Options.chunk_upload and blob.size > Options.chunk_limit * 1024 * 1024
            )

            engine_uid = kwargs.pop("engine_uid", None)
            is_direct_edit = kwargs.pop("is_direct_edit", False)
            is_direct_transfer = kwargs.pop("is_direct_transfer", False)

            # Set those attributes as FileBlob does not have them
            # and they are required for the step 2 of .upload_impl()
            blob.batch_id = batch.uid
            blob.fileIdx = batch.upload_idx

            action.is_direct_transfer = is_direct_transfer

            uploader = batch.get_uploader(
                blob,
                chunked=chunked,
                chunk_size=chunk_size,
                callback=self.remote.upload_callback,
            )
            log.debug(f"Using {type(uploader).__name__!r} uploader")

            if not transfer:
                # Remove eventual obsolete upload (it happens when an upload using S3 has invalid metadatas)
                self.dao.remove_transfer("upload", file_path)

                # Add an upload entry in the database
                transfer = Upload(
                    None,
                    file_path,
                    TransferStatus.ONGOING,
                    engine=engine_uid,
                    is_direct_edit=is_direct_edit,
                    batch=batch.as_dict(),
                    chunk_size=chunk_size,
                    is_direct_transfer=is_direct_transfer,
                )
                self.dao.save_upload(transfer)
            elif transfer.batch["batchId"] != batch.uid:
                # The upload was not a fresh one but its batch ID was perimed.
                # Before NXDRIVE-2183, the batch ID was not updated and so the second step
                # of the upload (attaching the blob to a document) was failing.
                transfer.batch["batchId"] = batch.uid
                self.dao.update_upload(transfer)

            if uploader.chunked:
                # Update the progress on chunked upload only as the first call to
                # action.progress will set the action.uploaded attr to True for
                # empty files. This is not what we want: empty files are legits.
                action.progress = chunk_size * len(uploader.blob.uploadedChunkIds)

                # Store the chunk size and start time for later transfer speed computation
                action.chunk_size = chunk_size
                action.chunk_transfer_start_time_ns = monotonic_ns()

                # If there is an UploadError, we catch it from the processor
                for _ in uploader.iter_upload():
                    # Here 0 may happen when doing a single upload
                    action.progress += uploader.chunk_size or 0

                    # Save the progression
                    # transfer.progress = action.get_percent()  # type: ignore
                    # self.dao.set_transfer_progress("upload", transfer)

                    # Handle status changes every time a chunk is sent
                    transfer = self.dao.get_upload(path=file_path)
                    if transfer and transfer.status not in (
                        TransferStatus.ONGOING,
                        TransferStatus.DONE,
                    ):
                        raise UploadPaused(transfer.uid or -1)
            else:
                uploader.upload()

                # For empty files, this will set action.uploaded to True,
                # telling us that the file was correctly sent to the server.
                action.progress += blob.size

                transfer.progress = action.get_percent()

            if batch.is_s3():
                if not batch.blobs:
                    # This may happen when resuming an upload with all parts sent.
                    # Trigger upload() that will complete the MPU and fill required
                    # attributes like the Batch ETag, blob index, etc..
                    uploader.upload()

                # Complete the S3 upload
                # (setting a big timeout to handle big files)
                batch.complete(timeout=TX_TIMEOUT)

            # Transfer is completed, update the status in the database
            transfer.status = TransferStatus.DONE  # type: ignore
            self.dao.set_transfer_status("upload", transfer)

            return blob
        finally:
            # In case of error, log the progression to help debugging
            percent = action.get_percent()
            if percent < 100.0 and not action.uploaded:
                log.debug(f"Upload progression stopped at {percent:.2f}%")

                # Save the progression
                if transfer:
                    transfer.progress = percent
                    self.dao.set_transfer_progress("upload", transfer)

            action.finish_action()

            if blob.fd:
                blob.fd.close()

    def link_blob_to_doc(
        self, command: str, blob: FileBlob, **kwargs: Any
    ) -> Dict[str, Any]:
        """Link the given uploaded *blob* to the given document (refs are passed into *kwargs*)."""

        # Remove additional parameters to prevent a BadQuery
        kwargs.pop("engine_uid", None)
        kwargs.pop("is_direct_edit", None)
        kwargs.pop("is_direct_transfer", None)
        file_path = kwargs.pop("file_path")

        headers = kwargs.pop("headers", {})
        headers["Nuxeo-Transaction-Timeout"] = str(TX_TIMEOUT)

        action = self.linking_action(file_path, reporter=QApplication.instance())
        try:
            res: Dict[str, Any] = self.remote.execute(
                command=command,
                input_obj=blob,
                headers=headers,
                timeout=TX_TIMEOUT,
                **kwargs,
            )
            return res
        finally:
            action.finish_action()

    def _aws_token_ttl(self, timestamp: int) -> timedelta:
        """Return the AWS token TTL for S3 uploads."""
        expiration = datetime.utcfromtimestamp(timestamp)
        ttl = expiration - datetime.utcnow()
        log.debug(f"AWS token will expire in {ttl} [at {expiration} UTC exactly]")
        return ttl
