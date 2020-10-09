"""
Uploader used by the Remote client for all upload stuff.
"""
from abc import abstractmethod
from logging import getLogger
from pathlib import Path
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from botocore.exceptions import ClientError
from nuxeo.exceptions import HTTPError
from nuxeo.handlers.default import Uploader
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
        blob, batch = self.upload_chunks(
            file_path, filename=filename, mime_type=mime_type, **kwargs
        )

        # Step 2: link the uploaded blob to the document
        kwargs["file_path"] = file_path
        doc: Dict[str, Any] = self.link_blob_to_doc(command, blob, **kwargs)

        # We need to remove the batch as the "X-Batch-No-Drop" header was used in link_blob_to_doc()
        try:
            batch.delete(0)
        except Exception:
            log.warning("Cannot delete the batch", exc_info=True)

        return doc

    def upload_chunks(
        self,
        file_path: Path,
        filename: str = None,
        mime_type: str = None,
        **kwargs: Any,
    ) -> Tuple[FileBlob, Batch]:
        """Upload a blob by chunks or in one go."""

        engine_uid = kwargs.get("engine_uid", None)
        is_direct_edit = kwargs.pop("is_direct_edit", False)
        is_direct_transfer = kwargs.get("is_direct_transfer", False)
        remote_parent_path = kwargs.pop("remote_parent_path", "")
        remote_parent_ref = kwargs.pop("remote_parent_ref", "")

        blob = FileBlob(str(file_path))
        action = self.upload_action(
            file_path, blob.size, reporter=QApplication.instance(), engine=engine_uid
        )
        if filename:
            blob.name = filename
        if mime_type:
            blob.mimetype = mime_type

        batch: Optional[Batch] = None
        chunk_size = 0

        # See if there is already a transfer for this file
        transfer = self.get_upload(file_path)

        # Used to skip progression update in the finally clause
        transfer_already_paused = False

        try:
            if transfer:
                if transfer.status not in (TransferStatus.ONGOING, TransferStatus.DONE):
                    transfer_already_paused = True
                    raise UploadPaused(transfer.uid or -1)

                log.debug(f"Retrieved transfer for {file_path!r}: {transfer}")

                # When fetching for an eventual batch, specifying the file index
                # is not possible for S3 as there is no blob at the current index
                # until the S3 upload is done itself and the call to
                # batch.complete() done.
                file_idx = None if transfer.batch.get("provider", "") == "s3" else 0

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
                    chunk_size = transfer.chunk_size or 0

                    # The transfer was already completed on the third-party provider
                    if batch.etag:
                        return self._complete_upload(batch, blob)

            if not batch:
                # .uploads.handlers() result is cached, so it is convenient to call it each time here
                # in case the server did not answer correctly the previous time and thus S3 would
                # be completely disabled because of a one-time server error.
                handler = "s3" if Feature.s3 and self.remote.uploads.has_s3() else ""

                # Create a new batch and save it in the DB
                batch = self.remote.uploads.batch(handler=handler)

            # By default, Options.chunk_size is 20, so chunks will be 20MiB.
            # It can be set to a value between 1 and 20 through the config.ini
            chunk_size = chunk_size or (Options.chunk_size * 1024 * 1024)

            # For the upload to be chunked, the Options.chunk_upload must be True
            # and the blob must be bigger than Options.chunk_limit, which by default
            # is equal to Options.chunk_size.
            chunked = (
                Options.chunk_upload and blob.size > Options.chunk_limit * 1024 * 1024
            )

            action.is_direct_transfer = is_direct_transfer

            try:
                uploader: Uploader = batch.get_uploader(
                    blob,
                    chunked=chunked,
                    chunk_size=chunk_size,
                    callback=self.remote.upload_callback,
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "NoSuchUpload":
                    raise

                log.warning(
                    "Either the upload ID does not exist, either the upload was already completed."
                )
                return self._complete_upload(batch, blob)

            log.debug(f"Using {type(uploader).__name__!r} uploader")

            # Ensure to use the real value, else it would open computation weirdness for progress bars
            chunk_size = uploader.chunk_size

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
                    filesize=blob.size,
                    batch=batch.as_dict(),
                    chunk_size=chunk_size,
                    is_direct_transfer=is_direct_transfer,
                    remote_parent_path=remote_parent_path,
                    remote_parent_ref=remote_parent_ref,
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

                if batch.is_s3():
                    self._patch_refresh_token(uploader, transfer)

                # If there is an UploadError, we catch it from the processor
                for _ in uploader.iter_upload():
                    action.progress = chunk_size * len(uploader.blob.uploadedChunkIds)

                    # Save the progression
                    transfer.progress = action.get_percent()
                    self.dao.set_transfer_progress("upload", transfer)

                    # Handle status changes every time a chunk is sent
                    _transfer = self.get_upload(file_path)
                    if _transfer and _transfer.status not in (
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

                # Save the final ETag in the database to prevent future issue if
                # the FileManager throws an error
                transfer.batch = batch.as_dict()
                self.dao.update_upload(transfer)

            self._complete_upload(batch, blob)

            # Transfer is completed, update the status in the database
            transfer.status = TransferStatus.DONE
            self.dao.set_transfer_status("upload", transfer)

            return blob, batch
        finally:
            # Onlty update the progression is the transfer was not paused at startup,
            # else it would set the percent to 0%.
            if transfer_already_paused:
                log.debug(
                    f"Retrieved paused transfer for {file_path!r}: {transfer}, kept paused then"
                )
            else:
                # In case of error, log the progression to help debugging
                percent = action.get_percent()
                if (
                    percent < 100.0
                    and not action.uploaded
                    and transfer
                    and percent
                ):
                    log.debug(f"Upload progression stopped at {percent:.2f}%")
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
        engine_uid = kwargs.pop("engine_uid", None)
        kwargs.pop("is_direct_edit", None)
        kwargs.pop("remote_parent_path", None)
        kwargs.pop("remote_parent_ref", None)
        file_path = kwargs.pop("file_path", None)

        headers = kwargs.pop("headers", {})
        headers["Nuxeo-Transaction-Timeout"] = str(TX_TIMEOUT)

        # By default, the batchId will be removed after its first use.
        # We do not want that for better upload resiliency, especially with large files.
        # The batchId must be removed manually then.
        headers["X-Batch-No-Drop"] = "true"

        action = self.linking_action(
            file_path, blob.size, reporter=QApplication.instance(), engine=engine_uid
        )
        action.is_direct_transfer = kwargs.pop("is_direct_transfer", False)
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

    def _patch_refresh_token(self, uploader: Uploader, transfer: Upload) -> None:
        """Patch Uploader.refresh_token() to save potential credentials changes for next runs."""
        meth_orig = uploader.service.refresh_token

        def refresh(batch: Batch, **kwargs: Any) -> Any:
            # Call the original method
            try:
                return meth_orig(batch, **kwargs)
            finally:
                # Save changes in the database
                log.debug("Batch.extraInfo has been updated")
                transfer.batch = batch.as_dict()
                self.dao.update_upload(transfer)

        uploader.service.refresh_token = refresh

    @staticmethod
    def _complete_upload(batch: Batch, blob: FileBlob) -> Tuple[FileBlob, Batch]:
        """Helper to complete an upload."""

        # Set those attributes as FileBlob does not have them
        # and they are required for the step 2 of .upload_impl()
        blob.batch_id = batch.uid
        blob.fileIdx = 0
        batch.upload_idx = 1

        if not batch.blobs or not batch.blobs[0]:
            batch.blobs[0] = blob

        # Complete the upload on the S3 side
        if batch.is_s3() and not batch.etag:
            batch.complete(timeout=TX_TIMEOUT)

        return blob, batch
