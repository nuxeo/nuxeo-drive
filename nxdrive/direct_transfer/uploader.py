# coding: utf-8
"""
The Direct Transfer feature.

What: upload methods and exceptions.
"""
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from nuxeo.exceptions import HTTPError
from nuxeo.handlers.default import Uploader
from nuxeo.models import Document, FileBlob

from ..constants import TX_TIMEOUT, TransferStatus
from ..options import Options
from .models import Transfer

if TYPE_CHECKING:
    from ..client.remote_client import Remote  # noqa

log = getLogger(__name__)


class DirectTransferPaused(Exception):
    """A transfer has been paused, the file's processing should stop."""


class DirectTransferDuplicateFoundError(ValueError):
    """
    Exception raised when a duplicate file already exists on the server
    and trying to Direct Transfer a local file with the same name.
    """

    def __init__(self, file: Path, doc: Document) -> None:
        self.file = file
        self.doc = doc

    def __repr__(self) -> str:
        return f"{type(self).__name__}<file={self.file!r}, doc={self.doc!r}>"

    def __str__(self) -> str:
        return (
            f"Document with the name {self.file.name!r} already found on the server: {self.doc}."
            f"Direct Transfer of {self.file!r} postponed after the user decided what to do."
        )


def dt_upload(self: "Remote", transfer: Transfer, **kwargs: Any) -> None:
    """Upload a given file to the given folderish document on the server.

    Note about possible duplicate creation via a race condition client <-> server.
    Given the local *file* with the path "$HOME/some-folder/subfolder/file.odt",
    the file name is "file.odt".

    Scenario:
        - Step 1: local, check for a doc with the path name "file.odt" => nothing returned, continuing;
        - Step 2: server, a document with a path name set to "file.odt" is created;
        - Step 3: local, create the document with the path name "file.odt".

    Even if the elapsed time between steps 1 and 3 is really short, it may happen.

    What can be done to prevent such scenario is not on the Nuxeo Drive side but on the server one.
    For now, 2 options are possible but not qualified to be done in a near future:
        - https://jira.nuxeo.com/browse/NXP-22959;
        - create a new operation `Document.GetOrCreate` that ensures atomicity.

    About kwargs, it is typically used to forward the chunk callback.
    """
    local_path = transfer.local_path
    remote_path = transfer.remote_path
    name = local_path.name
    doc: Optional[Document] = None

    log.info(
        f"Direct Transfer of {local_path!r} into {remote_path!r} (replace_blob={transfer.replace_blob})"
    )

    if transfer.remote_ref:
        # The remote ref is set, so it means either the file has already been uploaded,
        # either a previous upload failed: the document was created, or not, and it has
        # a blob attached, or not. In any cases, we need to ensure the user can upload
        # without headhache.
        doc = self.get_document_or_none(uid=transfer.remote_ref)

    if not doc:
        # We need to handle possbile duplicates based on the file name and
        # the destination folder on the server.
        # Note: using this way may still result in duplicates:
        #  - the user created 2 documents with the same name on Web-UI or another way
        #  - the user then deleted the 1st document
        #  - the other document has a path like "name.TIMESTAMP"
        # So then Drive will not see that document as a duplicate because it will check
        # a path with "name" only.

        # If we really want to avoid that situation, we should use that commented code:
        """
        # Note that it would be too much effort for the server, we do not want that!
        for child in self.documents.get_children(path=parent_path):
            # It is OK to have a folder and a file with the same name,
            # but not 2 files or 2 folders with the same name
            if child.title == file.name:
                local_is_dir = file.isdir()
                remote_is_dir = "Folderish" in child["facets"]
                if local_is_dir is remote_is_dir:
                    # Duplicate found!
                    doc = child
                    transfer.remote_ref = doc.uid
                    break
        """

        doc = self.get_document_or_none(path=f"{remote_path}/{name}")
        if doc:
            transfer.remote_ref = doc.uid

    if not transfer.replace_blob and doc and doc.properties.get("file:content"):
        # The document already exists and has a blob attached. Ask the user what to do.
        raise DirectTransferDuplicateFoundError(local_path, doc)

    if not doc:
        # Create the document on the server
        nature = "File" if transfer.is_file else "Folder"
        transfer.doctype = nature
        doc = self.documents.create(
            Document(name=name, type=nature, properties={"dc:title": name}),
            parent_path=remote_path,
        )
        transfer.remote_ref = doc.uid

    if not transfer.is_file:
        transfer.uploaded = True
        transfer.status = TransferStatus.DONE  # type: ignore

    transfer.save()

    if transfer.is_file:
        # Upload the blob and attach it to the document
        self.dt_do_upload(self, transfer, **kwargs)


def dt_do_upload(self: "Remote", transfer: Transfer, **kwargs: Any) -> None:
    """Upload a file with a batch.

    If an exception happens at step 1 or 2, the upload will be continued the next
    time the Processor handle the document (it will be postponed due to the error).

    If the error was raised at step 1, the upload will not start from zero: it will
    resume from the next chunk based on what previously chunks were sent.
    This is dependent of the chunk TTL configured on the server (it must be large enough
    to handle big files).

    If the error was raised at step 2, the step 1 will be checked to ensure the blob
    was successfully uploaded. But it most cases, nothing will be uploaded twice.
    Also, it the error is one of HTTP 502 or 503, the Processor will check for
    the file existence to bypass errors happening *after* the operation was successful.
    If it exists, the error is skipped and the upload is seen as a success.
    """
    # Step 1: upload the blob
    blob = self.dt_upload_chunks(self, transfer, **kwargs)

    # Step 2: link the uploaded blob to the document
    self.dt_link_blob_to_doc(self, transfer, blob)

    # Transfer is completed, delete the upload from the database
    transfer.status = TransferStatus.DONE  # type: ignore
    transfer.save()


def dt_upload_chunks(self: "Remote", transfer: Transfer, **kwargs: Any) -> FileBlob:
    """Upload a blob by chunks or in one go."""

    blob = FileBlob(str(transfer.local_path))
    blob.name = transfer.local_path.name

    # The upload was already done, no need to make useless calls to the server
    if transfer.uploaded:
        # Set those attributes as FileBlob does not have them
        # and they are required for the step 2 of .dt_do_upload()
        blob.batch_id = transfer.batch.uid
        blob.fileIdx = transfer.batch.upload_idx
        return blob

    chunk_size = 0

    # Check if the associated batch still exists server-side
    if transfer.batch.uid:
        # When fetching for an eventual batch, specifying the file index
        # is not possible for S3 as there is no blob at the current index
        # until the S3 upload is done itself and the call to
        # batch.complete() done.
        file_idx = None if transfer.batch.is_s3() else transfer.batch.upload_idx

        try:
            self.uploads.get(transfer.batch.uid, file_idx=file_idx)
        except Exception:
            transfer.batch.uid = None
            log.debug("No associated batch found, restarting from zero", exc_info=True)
        else:
            log.debug("Associated batch found, resuming the upload")
            transfer.batch.service = self.uploads
            chunk_size = transfer.chunk_size

    if not transfer.batch.uid:
        # .uploads.handlers() result is cached, so it is convenient to call it each time here
        # in case the server did not answer correctly the previous time and thus S3 would
        # be completely disabled because of a one-time server error.
        handler = "s3" if self.uploads.has_s3() else ""

        # Create a new batch and save it in the DB
        transfer.batch = self.uploads.batch(handler=handler)
        transfer.save()

    # Set those attributes as FileBlob does not have them
    # and they are required for the step 2 of .dt_do_upload()
    blob.batch_id = transfer.batch.uid
    blob.fileIdx = transfer.batch.upload_idx

    # By default, Options.chunk_size is 20, so chunks will be 20MiB.
    # It can be set to a value between 1 and 20 through the config.ini
    chunk_size = chunk_size or (Options.chunk_size * 1024 * 1024)

    # For the upload to be chunked, the Options.chunk_upload must be True
    # and the blob must be bigger than Options.chunk_limit, which by default
    # is equal to Options.chunk_size.
    chunked = Options.chunk_upload and blob.size > Options.chunk_limit * 1024 * 1024

    try:
        uploader: Uploader = transfer.batch.get_uploader(
            blob,
            chunked=chunked,
            chunk_size=chunk_size,
            callback=kwargs.get("chunk_callback", None),
        )
        log.debug(f"Using {type(uploader).__name__!r} uploader")

        transfer.chunk_size = uploader.chunk_size

        if uploader.chunked:
            for up in uploader.iter_upload():
                # Save the progression
                transfer.uploaded_size = up.blob.uploadedSize

                # Handle status changes every time a chunk is sent
                if transfer.status not in (TransferStatus.ONGOING, TransferStatus.DONE):
                    raise DirectTransferPaused(transfer.id)

        else:
            uploader.upload()
            transfer.uploaded_size = blob.size

        if transfer.batch.is_s3():
            # Complete the S3 upload
            transfer.batch.complete()

        transfer.uploaded = True
        transfer.batch.upload_idx = 0
        transfer.save()

        return blob
    finally:
        if blob.fd:
            blob.fd.close()


def dt_link_blob_to_doc(self: "Remote", transfer: Transfer, blob: FileBlob) -> None:
    """Link the given uploaded *blob* to the given document.
    The method exists only to be able to test upload errors.
    """
    try:
        self.execute(
            command="Blob.AttachOnDocument",
            input_obj=blob,
            headers={"Nuxeo-Transaction-Timeout": str(TX_TIMEOUT)},
            timeout=TX_TIMEOUT,
            xpath="file:content",
            void_op=True,
            document=transfer.remote_ref,
        )
    except HTTPError as exc:
        if exc.status in (502, 503):
            # As seen with NXDRIVE-1753, an uploaded file may have worked
            # but for some reason the final state is in error. So, let's
            # check if the document is present on the server to bypass
            # (infinite|useless) retries.
            if self.get_document_or_none(uid=transfer.remote_ref):
                return
        raise
