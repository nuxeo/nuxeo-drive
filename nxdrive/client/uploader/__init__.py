"""
Uploader used by the Remote client for all upload stuff.
"""
from abc import abstractmethod
from logging import getLogger
from pathlib import Path
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, Dict, Optional

from botocore.exceptions import ClientError
from nuxeo.exceptions import HTTPError
from nuxeo.handlers.default import Uploader
from nuxeo.models import Batch, FileBlob

from ...constants import TX_TIMEOUT, TransferStatus
from ...engine.activity import LinkingAction, UploadAction
from ...exceptions import UploadCancelled, UploadPaused
from ...feature import Feature
from ...objects import Upload
from ...options import Options
from ...qt.imports import QApplication

if TYPE_CHECKING:
    from ..remote_client import Remote  # noqa
    from ...engine.dao.sqlite import EngineDAO  # noqa

log = getLogger(__name__)


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
        self, file_path: Path, blob: FileBlob, /, **kwargs: Any
    ) -> Upload:
        """Get and instantiate a new transfer."""

        # See if there is already a transfer for this file
        doc_pair = kwargs.get("doc_pair")
        transfer = self.get_upload(doc_pair=doc_pair, path=file_path)
        batch: Optional[Batch] = None

        if transfer:
            if transfer.status not in (TransferStatus.ONGOING, TransferStatus.DONE):
                log.debug(f"Retrieved paused transfer {transfer}, kept paused then")
                raise UploadPaused(transfer.uid or -1)

            log.debug(f"Retrieved ongoing transfer {transfer}")

            # When fetching for an eventual batch, specifying the file index
            # is not possible for S3 as there is no blob at the current index
            # until the S3 upload is done itself and the call to
            # batch.complete() done.
            file_idx = None if transfer.batch.get("provider", "") == "s3" else 0

            # Check if the associated batch still exists server-side
            try:
                self.remote.uploads.get(transfer.batch["batchId"], file_idx=file_idx)
            except HTTPError as exc:
                if exc.status != 404:
                    raise
                log.debug("No associated batch found, restarting from zero")
            else:
                log.debug("Associated batch found, resuming the upload")
                batch = Batch(service=self.remote.uploads, **transfer.batch)

        if not batch:
            # .uploads.handlers() result is cached, so it is convenient to call it each time here
            # in case the server did not answer correctly the previous time and thus S3 would
            # be completely disabled because of a one-time server error.
            handler = "s3" if Feature.s3 and self.remote.uploads.has_s3() else ""

            # Create a new batch
            batch = self.remote.uploads.batch(handler=handler)

        if not transfer:
            # Remove eventual obsolete upload (it happens when an upload using S3 has invalid metadatas)
            self.dao.remove_transfer("upload", doc_pair=doc_pair, path=file_path)

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
                is_direct_transfer=kwargs.get("is_direct_transfer", False),
                remote_parent_path=kwargs.pop("remote_parent_path", ""),
                remote_parent_ref=kwargs.pop("remote_parent_ref", ""),
                doc_pair=kwargs.pop("doc_pair", None),
            )
            log.debug(f"Instantiated transfer {transfer}")
            if transfer.is_direct_transfer:
                self.dao.save_dt_upload(transfer)
            else:
                self.dao.save_upload(transfer)
        elif transfer.batch["batchId"] != batch.uid:
            # The upload was not a fresh one but its batch ID was perimed.
            # Before NXDRIVE-2183, the batch ID was not updated and so the second step
            # of the upload (attaching the blob to a document) was failing.
            log.debug(
                f"Updating the batchId from {transfer.batch['batchId']} to {batch.uid}"
            )
            transfer.batch["batchId"] = batch.uid
            self.dao.update_upload(transfer)

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
            blob.name = filename

        # Step 0.5: retrieve or instantiate a new transfer
        transfer = self._get_transfer(file_path, blob, **kwargs)
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
            try:
                self.upload_chunks(transfer, blob, chunked)
            finally:
                if blob.fd:
                    blob.fd.close()

            # Step 1.5: complete the upload on the third-party provider
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

        try:
            uploader: Uploader = transfer.batch_obj.get_uploader(
                blob,
                chunked=chunked,
                chunk_size=transfer.chunk_size,
                callback=self.remote.upload_callback,
            )

            log.debug(f"Using {type(uploader).__name__!r} uploader")

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

                if transfer.batch_obj.is_s3():
                    self._patch_refresh_token(uploader, transfer)

                    # Save the multipart upload ID
                    transfer.batch = transfer.batch_obj.as_dict()
                    self.dao.update_upload(transfer)

                # If there is an UploadError, we catch it from the processor
                for _ in uploader.iter_upload():
                    action.progress = action.chunk_size * len(
                        uploader.blob.uploadedChunkIds
                    )

                    # Save the progression
                    transfer.progress = action.get_percent()
                    self.dao.set_transfer_progress("upload", transfer)

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
            if "unable to find batch associated with id" in str(exc).lower():
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

    def _patch_refresh_token(self, uploader: Uploader, transfer: Upload, /) -> None:
        """Patch Uploader.refresh_token() to save potential credentials changes for next runs."""
        meth_orig = uploader.service.refresh_token

        def refresh(batch: Batch, /, **kwargs: Any) -> Any:
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
    def _complete_upload(transfer: Upload, blob: FileBlob, /) -> None:
        """Helper to complete an upload."""

        # Set those attributes as FileBlob does not have them
        # and they are required for the step 2 of .upload_impl()
        blob.batchId = transfer.batch_obj.uid
        blob.fileIdx = 0
        transfer.batch_obj.upload_idx = 1

        if not transfer.batch_obj.blobs or not transfer.batch_obj.blobs[0]:
            transfer.batch_obj.blobs[0] = blob

        # Complete the upload on the S3 side
        if transfer.batch_obj.is_s3() and transfer.status is not TransferStatus.DONE:
            transfer.batch_obj.complete(timeout=TX_TIMEOUT)
