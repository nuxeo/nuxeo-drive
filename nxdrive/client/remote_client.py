# coding: utf-8
import os
import socket
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from time import monotonic_ns
from typing import Any, Callable, Dict, List, Optional, Union, TYPE_CHECKING
from urllib.parse import unquote

import requests
from nuxeo.auth import TokenAuth
from nuxeo.client import Nuxeo
from nuxeo.compat import get_text
from nuxeo.exceptions import CorruptedFile, HTTPError
from nuxeo.handlers.default import Uploader
from nuxeo.models import Batch, FileBlob, Document
from nuxeo.utils import get_digest_algorithm
from PyQt5.QtWidgets import QApplication

from .local import LocalClient
from .proxy import Proxy
from ..constants import (
    APP_NAME,
    BATCH_SIZE,
    FILE_BUFFER_SIZE,
    TIMEOUT,
    TOKEN_PERMISSION,
    TX_TIMEOUT,
    TransferStatus,
)
from ..engine.activity import (
    Action,
    DownloadAction,
    LinkingAction,
    UploadAction,
    VerificationAction,
)
from ..exceptions import (
    DirectTransferDuplicateFoundError,
    NotFound,
    ScrollDescendantsError,
    UploadPaused,
)
from ..objects import NuxeoDocumentInfo, RemoteFileInfo, Download, Upload
from ..options import Options
from ..utils import (
    compute_digest,
    get_device,
    lock_path,
    sizeof_fmt,
    unlock_path,
    version_le,
)

if TYPE_CHECKING:
    from ..engine.dao.sqlite import EngineDAO  # noqa

__all__ = ("Remote",)

log = getLogger(__name__)

socket.setdefaulttimeout(TX_TIMEOUT)


class Remote(Nuxeo):
    def __init__(
        self,
        url: str,
        user_id: str,
        device_id: str,
        version: str,
        password: str = None,
        token: str = None,
        proxy: Proxy = None,
        download_callback: Callable = None,
        upload_callback: Callable = None,
        base_folder: str = None,
        dao: "EngineDAO" = None,
        repository: str = Options.remote_repo,
        timeout: int = Options.timeout,
        **kwargs: Any,
    ) -> None:
        auth = TokenAuth(token) if token else (user_id, password)

        super().__init__(
            auth=auth,
            host=url,
            app_name=APP_NAME,
            version=version,
            repository=repository,
            **kwargs,
        )

        self.client.headers.update(
            {
                "X-User-Id": user_id,
                "X-Device-Id": device_id,
                "Cache-Control": "no-cache",
            }
        )

        self.set_proxy(proxy)

        if dao:
            self.dao = dao

        self.timeout = timeout if timeout > 0 else TIMEOUT

        self.device_id = device_id
        self.user_id = user_id
        self.version = version

        # Callback function used for downloads.
        # Note: the order is important, keep it!
        self.download_callback = (
            self.transfer_start_callback,
            download_callback,
            self.transfer_end_callback,
        )

        # Callback function used for chunked uploads.
        # It will be forwarded to Batch.get_uploader() on the Nuxeo Python Client side.
        # Note: the order is important, keep it!
        self.upload_callback = (
            self.transfer_start_callback,
            upload_callback,
            self.transfer_end_callback,
        )

        self._has_new_trash_service = not version_le(self.client.server_version, "10.1")

        if base_folder is not None:
            base_folder_doc = self.fetch(base_folder)
            self.base_folder_ref = base_folder_doc["uid"]
            self._base_folder_path = base_folder_doc["path"]
        else:
            self.base_folder_ref, self._base_folder_path = None, None

    def __repr__(self) -> str:
        attrs = ", ".join(
            f"{attr}={getattr(self, attr, None)!r}"
            for attr in sorted(self.__init__.__code__.co_varnames[1:])  # type: ignore
        )
        return f"<{type(self).__name__} {attrs}>"

    def transfer_start_callback(self, *_: Any) -> None:
        """Callback for each chunked (down|up)loads.
        Called first to set the end time of the current (down|up)loaded chunk.
        """
        action = Action.get_current_action()
        if action:  # mypy fix ...
            action.chunk_transfer_end_time_ns = monotonic_ns()

    def transfer_end_callback(self, *_: Any) -> None:
        """Callback for each chunked (down|up)loads.
        Called last to set the start time of the next chunk to (down|up)load.
        """
        action = Action.get_current_action()
        if not action:  # mypy fix ...
            return

        # Handle transfer speed
        action.transferred_chunks += 1
        duration = (
            action.chunk_transfer_end_time_ns - action.chunk_transfer_start_time_ns
        )
        if duration > 1_000_000_000:  # 1 second in nanoseconds
            # x 1,073,741,824 to counter the duration that is exprimed in nanoseconds
            speed = action.last_chunk_transfer_speed = (
                action.chunk_size
                * action.transferred_chunks
                * 1_073_741_824.0
                / duration
            )
            log.debug(f"Chunk transfer speed was {sizeof_fmt(speed)}/s")
            action.transferred_chunks = 1

        # Update the transfer start timer for the next iteration
        if duration > 1_000_000_000:
            action.chunk_transfer_start_time_ns = monotonic_ns()

    def execute(self, **kwargs: Any) -> Any:
        """
        This is the end point where all HTTP calls are done.
        The goal is to handle specific errors early.
        """
        # Unauthorized and Forbidden exceptions are handled by the Python client.
        try:
            return self.operations.execute(**kwargs)
        except HTTPError as e:
            if e.status == requests.codes.not_found:
                raise NotFound()
            raise e

    def _escape(self, path) -> str:
        """Escape any single quote with an antislash to further use in a NXQL query."""
        return path.replace("'", r"\'")

    def exists(self, ref: str, use_trash: bool = True) -> bool:
        """
        Check if a document exists on the server.

        :param ref: Document reference (UID).
        :param use_trash: Filter documents inside the trash.
        :rtype: bool
        """
        ref = self._escape(self.check_ref(ref))
        id_prop = "ecm:path" if ref.startswith("/") else "ecm:uuid"
        trash = self._get_trash_condition() if use_trash else ""

        query = f"SELECT * FROM Document WHERE {id_prop} = '{ref}' {trash} AND ecm:isVersion = 0 LIMIT 1"
        results = self.query(query)
        return len(results["entries"]) == 1

    def request_token(self, revoke: bool = False) -> Optional[str]:
        """Request and return a new token for the user"""
        token = self.client.request_auth_token(
            device_id=self.device_id,
            app_name=APP_NAME,
            permission=TOKEN_PERMISSION,
            device=get_device(),
            revoke=revoke,
        )
        return None if "\n" in token else token

    def revoke_token(self) -> None:
        self.request_token(revoke=True)

    def update_token(self, token: str) -> None:
        self.auth = TokenAuth(token)
        self.client.auth = self.auth

    def personal_space(self) -> Document:
        """Retrieve the "Personal space" special folder.
        If the folder does not exist yet, it will be lazily created with that call.
        """
        return Document(**self.execute(command="UserWorkspace.Get"))

    def download(
        self, url: str, file_path: Path, file_out: Path, digest: str, **kwargs: Any
    ) -> Path:
        log.debug(
            f"Downloading file from {url!r} to {file_out!r} with digest={digest!r}"
        )

        headers: Dict[str, str] = {}
        downloaded = 0
        if file_out:
            # Retrieve current size of the TMP file, if any, to know where to start the download
            with suppress(FileNotFoundError):
                downloaded = file_out.stat().st_size
                headers = {"Range": f"bytes={downloaded}-"}

        resp = self.client.request(
            "GET", url.replace(self.client.host, ""), headers=headers
        )

        if not file_out:
            # Return the pointer to the data
            result = resp.content
            del resp
            return result

        size = int(resp.headers.get("Content-Length", 0)) if resp else 0
        chunked = size > (Options.tmp_file_limit * 1024 * 1024)

        # Retrieve the eventual ongoing download
        download = self.dao.get_download(path=file_path)

        if not download:
            # Add a new download entry in the database
            download = Download(
                None,
                path=file_path,
                status=TransferStatus.ONGOING,
                tmpname=str(file_out),
                url=url,
                filesize=size,
                doc_pair=kwargs.pop("doc_pair_id", None),
                engine=kwargs.pop("engine_uid", None),
                is_direct_edit=kwargs.pop("is_direct_edit", False),
            )
            self.dao.save_download(download)

        if chunked:
            action = DownloadAction(
                file_path, tmppath=file_out, reporter=QApplication.instance()
            )
            action.size = size
            action.progress = downloaded
            log.debug(
                f"Download progression is {action.get_percent():.2f}% "
                f"(data length is {sizeof_fmt(size)}, "
                f"chunked is {chunked}, chunk size is {sizeof_fmt(FILE_BUFFER_SIZE)})"
            )

        locker = unlock_path(file_out)
        try:
            if chunked:
                # Store the chunck size and start time for later transfer speed computation
                action.chunk_size = FILE_BUFFER_SIZE
                action.chunk_transfer_start_time_ns = monotonic_ns()

                callback = kwargs.pop("callback", self.download_callback)
                self.operations.save_to_file(
                    action,
                    resp,
                    file_out,
                    chunk_size=FILE_BUFFER_SIZE,
                    callback=callback,
                )

                self.check_integrity(digest, action)
            else:
                with memoryview(resp.content) as view, file_out.open(mode="wb") as f:
                    # TODO: NXDRIVE-1945, remove "type: ignore" when mypy 0.750 comes out
                    f.write(view)  # type: ignore
                    # Force write of file to disk
                    f.flush()
                    os.fsync(f.fileno())

                self.check_integrity_simple(digest, file_out)

            # Download finished!
            download.status = TransferStatus.DONE
            self.dao.set_transfer_status("download", download)
        finally:
            if chunked:
                DownloadAction.finish_action()
            lock_path(file_out, locker)
            del resp

        return file_out

    def check_integrity(self, digest: str, download_action: DownloadAction) -> None:
        """
        Check the integrity of a downloaded chunked file.
        Update the progress of the verification during the computation of the digest.
        """
        digester = get_digest_algorithm(digest)
        filepath = download_action.tmppath or download_action.filepath

        # Terminate the download action to be able to start the verification one as we are allowing
        # only 1 action per thread.
        # Note that this is not really needed as the verification action would replace the download
        # one, but let's do things right.
        DownloadAction.finish_action()

        verif_action = VerificationAction(filepath, reporter=QApplication.instance())

        def callback(_):
            verif_action.progress += FILE_BUFFER_SIZE

        try:
            computed_digest = compute_digest(filepath, digester, callback=callback)
            if digest != computed_digest:
                # TMP file and Downloads table entry will be deleted
                # by the calling method
                raise CorruptedFile(filepath, digest, computed_digest)
        finally:
            VerificationAction.finish_action()

    def check_integrity_simple(self, digest: str, file: Path) -> None:
        """Check the integrity of a relatively small downloaded file."""
        digester = get_digest_algorithm(digest)
        computed_digest = compute_digest(file, digester)
        if digest != computed_digest:
            raise CorruptedFile(file, digest, computed_digest)

    def upload(
        self,
        file_path: Path,
        command: str,
        filename: str = None,
        mime_type: str = None,
        **params: Any,
    ) -> Dict[str, Any]:
        """
        Upload a file with a batch.
        If command is not None, the operation is executed with the batch as an input.

        If an exception happens at step 1 or 2, the upload will be continued the next
        time the Processor handle the document (it will be postponed due to the error).

        If the error was raised at step 1, the upload will not start from zero: it will
        resume from the next chunk based on what previously chunks were sent.
        This is dependent of the chunk TTL configured on the server (it must be large enough
        to handle big files).

        If the error was raised at step 2, the step 1 will be checked to ensure the blob
        was successfuly uploaded. But it most cases, nothing will be uploaded twice.
        Also, it the error is one of HTTP 502 or 503, the Processor will check for
        the file existence to bypass errors happening *after* the operation was successful.
        If it exists, the error is skipped and the upload is seen as a success.
        """
        # Step 1: upload the blob
        blob = self.upload_chunks(
            file_path, filename=filename, mime_type=mime_type, **params
        )

        # Step 2: link the uploaded blob to the document
        params["file_path"] = file_path
        item = self.link_blob_to_doc(command, blob, **params)

        # Transfer is completed, delete the upload from the database
        self.dao.remove_transfer("upload", file_path)

        return item

    def upload_chunks(
        self,
        file_path: Path,
        filename: str = None,
        mime_type: str = None,
        **params: Any,
    ) -> FileBlob:
        """Upload a blob by chunks or in one go."""

        action = UploadAction(file_path, reporter=QApplication.instance())
        blob = FileBlob(str(file_path))
        if filename:
            blob.name = filename
        if mime_type:
            blob.mimetype = mime_type

        batch = None
        chunk_size = None
        upload: Optional[Upload] = None

        try:
            # See if there is already a transfer for this file
            upload = self.dao.get_upload(path=file_path)

            if upload:
                log.debug(f"Retrieved transfer for {file_path!r}: {upload}")
                if upload.status not in (TransferStatus.ONGOING, TransferStatus.DONE):
                    raise UploadPaused(upload.uid or -1)

                # When fetching for an eventual batch, specifying the file index
                # is not possible for S3 as there is no blob at the current index
                # until the S3 upload is done itself and the call to
                # batch.complete() done.
                file_idx = upload.batch["upload_idx"]
                if upload.batch.get("provider", "") == "s3":
                    file_idx = None

                # Check if the associated batch still exists server-side
                try:
                    self.uploads.get(upload.batch["batchId"], file_idx=file_idx)
                except Exception:
                    log.debug(
                        f"No associated batch found, restarting from zero",
                        exc_info=True,
                    )
                else:
                    log.debug(f"Associated batch found, resuming the upload")
                    batch = Batch(service=self.uploads, **upload.batch)
                    chunk_size = upload.chunk_size

            if not batch:
                # .uploads.handlers() result is cached, so it is convenient to call it each time here
                # in case the server did not answered correctly the previous time and thus S3 would
                # be completely disabled because of a one-time server error.
                handler = "s3" if "s3" in self.uploads.handlers() else ""

                # Create a new batch and save it in the DB
                batch = self.uploads.batch(handler=handler)

            # By default, Options.chunk_size is 20, so chunks will be 20MiB.
            # It can be set to a value between 1 and 20 through the config.ini
            chunk_size = chunk_size or (Options.chunk_size * 1024 * 1024)

            # For the upload to be chunked, the Options.chunk_upload must be True
            # and the blob must be bigger than Options.chunk_limit, which by default
            # is equal to Options.chunk_size.
            chunked = (
                Options.chunk_upload and blob.size > Options.chunk_limit * 1024 * 1024
            )

            engine_uid = params.pop("engine_uid", None)
            is_direct_edit = params.pop("is_direct_edit", False)

            if not upload:
                # Add an upload entry in the database
                upload = Upload(
                    None,
                    file_path,
                    TransferStatus.ONGOING,
                    engine=engine_uid,
                    is_direct_edit=is_direct_edit,
                    batch=batch.as_dict(),
                    chunk_size=chunk_size,
                )
                self.dao.save_upload(upload)

            # Set those attributes as FileBlob does not have them
            # and they are required for the step 2 of .upload()
            blob.batch_id = batch.uid
            blob.fileIdx = batch.upload_idx

            uploader: Uploader = batch.get_uploader(
                blob,
                chunked=chunked,
                chunk_size=chunk_size,
                callback=self.upload_callback,
            )
            log.debug(f"Using {type(uploader).__name__!r} uploader")

            # Update the progress on chunked upload only as the first call to
            # action.progress will set the action.uploaded attr to True for
            # empty files. This is not what we want: empty files are legits.
            if uploader.chunked:
                action.progress = chunk_size * len(uploader.blob.uploadedChunkIds)

            if action.get_percent() < 100.0 or not action.uploaded:
                if uploader.chunked:
                    if batch.provider == "s3":
                        first_time = True

                        def save_s3_details(uploader_):
                            # For S3, the uploader calls all callbacks before starting
                            # the actual upload. This is convenient to allow us to save
                            # the multipart upload ID and accurate chunk size.
                            nonlocal first_time
                            if not first_time:
                                return

                            upload.batch = uploader_.batch.as_dict()
                            upload.chunk_limit = uploader_.chunk_size
                            self.dao.update_upload(upload)
                            first_time = False

                        uploader.callback += (save_s3_details,)

                    # Store the chunck size and start time for later transfer speed computation
                    action.chunk_size = chunk_size
                    action.chunk_transfer_start_time_ns = monotonic_ns()

                    # If there is an UploadError, we catch it from the processor
                    for _ in uploader.iter_upload():
                        # Here 0 may happen when doing a single upload
                        action.progress += uploader.chunk_size or 0

                        # Save the progression
                        upload.progress = action.get_percent()
                        self.dao.set_transfer_progress("upload", upload)

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

                    upload.progress = action.get_percent()

            # Complete the upload (this is a no-op when using the default upload provider)
            batch.complete()

            # Transfer is completed, update the status in the database
            upload.status = TransferStatus.DONE
            self.dao.set_transfer_status("upload", upload)

            return blob
        finally:
            # In case of error, log the progression to help debugging
            percent = action.get_percent()
            if percent < 100.0 and not action.uploaded:
                log.debug(f"Upload progression stopped at {percent:.2f}%")

                # Save the progression
                if upload:
                    upload.progress = percent
                    self.dao.set_transfer_progress("upload", upload)

            UploadAction.finish_action()

            if blob.fd:
                blob.fd.close()

    def link_blob_to_doc(
        self, command: str, blob: FileBlob, **params
    ) -> Dict[str, Any]:
        """Link the given uploaded *blob* to the given document (refs are passed into *params*)."""

        # Remove additionnal parameters to prevent a BadQuery
        params.pop("engine_uid", None)
        params.pop("is_direct_edit", None)
        file_path = params.pop("file_path")

        headers = {"Nuxeo-Transaction-Timeout": str(TX_TIMEOUT)}
        log.debug(
            f"Setting connection timeout to {TX_TIMEOUT:,} seconds to handle the file creation on the server"
        )

        # Terminate the upload action to be able to start the finalization one as we are allowing
        # only 1 action per thread.
        # Note that this is not really needed as the finalization action would replace the upload
        # one, but let's do things right.
        UploadAction.finish_action()

        LinkingAction(file_path, reporter=QApplication.instance())
        try:
            return self.execute(
                command=command,
                input_obj=blob,
                headers=headers,
                timeout=TX_TIMEOUT,
                **params,
            )
        finally:
            LinkingAction.finish_action()

    def get_document_or_none(self, uid: str = "", path: str = "") -> Optional[Document]:
        """Fetch a document base don given criterias or return None if not found on the server."""
        doc: Optional[Document] = None
        try:
            doc = self.documents.get(uid=uid, path=path)
        except HTTPError as exc:
            if exc.status != requests.codes.not_found:
                raise
        return doc

    def direct_transfer(
        self, file: Path, parent_path: str, engine_uid: str, replace_blob: bool = False
    ):
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
        """
        log.info(f"Direct Transfer of {file!r} into {parent_path!r}")

        # The remote file, when created, is stored in the file xattrs.
        # So retrieve it and if it is defined, the document creation should
        # be skipped to prevent duplicate creations.
        remote_ref = LocalClient.get_path_remote_id(file, name="remote")

        doc: Optional[Document] = None

        if remote_ref:
            # The remote ref is set, so it means either the file has already been uploaded,
            # either a previous upload failed: the document was created, or not, and it has
            # a blob attached, or not. In any cases, we need to ensure the user can upload
            # without headhache.
            doc = self.get_document_or_none(uid=remote_ref)

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
                        remote_ref = doc.uid
                        break
            """

            doc = self.get_document_or_none(path=f"{parent_path}/{file.name}")
            if doc:
                remote_ref = doc.uid

        if not replace_blob and doc and doc.properties.get("file:content"):
            # The document already exists and has a blob attached. Ask the user what to do.
            raise DirectTransferDuplicateFoundError(file, doc)

        if not doc:
            # Create the document on the server
            nature = "File" if file.is_file() else "Folder"
            doc = self.documents.create(
                Document(
                    name=file.name, type=nature, properties={"dc:title": file.name}
                ),
                parent_path=parent_path,
            )
            remote_ref = doc.uid

        # If the path is a folder, there is no more work to do
        if file.is_dir():
            return

        # Save the remote document's UID into the file xattrs, in case next steps fails
        LocalClient.set_path_remote_id(file, remote_ref, name="remote")

        # Upload the blob and attach it to the document
        self.upload(
            file,
            engine_uid=engine_uid,
            document=remote_ref,
            command="Blob.AttachOnDocument",
            xpath="file:content",
            void_op=True,
        )

    def get_fs_info(
        self, fs_item_id: str, parent_fs_item_id: str = None
    ) -> RemoteFileInfo:
        fs_item = self.get_fs_item(fs_item_id, parent_fs_item_id=parent_fs_item_id)
        if fs_item is None:
            raise NotFound(f"Could not find {fs_item_id!r} on {self.client.host!r}")
        return RemoteFileInfo.from_dict(fs_item)

    def get_filesystem_root_info(self) -> RemoteFileInfo:
        toplevel_folder = self.execute(command="NuxeoDrive.GetTopLevelFolder")
        return RemoteFileInfo.from_dict(toplevel_folder)

    def stream_content(
        self,
        fs_item_id: str,
        file_path: Path,
        file_out: Path,
        parent_fs_item_id: str = None,
        fs_item_info: RemoteFileInfo = None,
        **kwargs: Any,
    ) -> Path:
        """Stream the binary content of a file system item to a tmp file

        Raises NotFound if file system item with id fs_item_id
        cannot be found
        """
        if not fs_item_info:
            fs_item_info = self.get_fs_info(
                fs_item_id, parent_fs_item_id=parent_fs_item_id
            )

        # Download the blob
        tmp_file = self.download(
            self.client.host + fs_item_info.download_url,
            file_path,
            file_out,
            fs_item_info.digest or "",  # mypy fix ...
            **kwargs,
        )

        # Download completed, remove it from the database
        self.dao.remove_transfer("download", file_path)

        return tmp_file

    def get_fs_children(
        self, fs_item_id: str, filtered: bool = True
    ) -> List[RemoteFileInfo]:
        children = self.execute(command="NuxeoDrive.GetChildren", id=fs_item_id)
        infos = [RemoteFileInfo.from_dict(fs_item) for fs_item in children]

        if filtered:
            filtered_infos = []
            for info in infos:
                if not self.is_filtered(info.path):
                    filtered_infos.append(info)
                else:
                    log.info(f"Filtering out item {info!r}")
            return filtered_infos
        return infos

    def scroll_descendants(
        self, fs_item_id: str, scroll_id: Optional[str], batch_size: int = BATCH_SIZE
    ) -> Dict[str, Any]:
        res = self.execute(
            command="NuxeoDrive.ScrollDescendants",
            id=fs_item_id,
            scrollId=scroll_id,
            batchSize=batch_size,
        )
        if not isinstance(res, dict) or not res:
            raise ScrollDescendantsError(res)

        return {
            "scroll_id": res["scrollId"],
            "descendants": [
                RemoteFileInfo.from_dict(fs_item) for fs_item in res["fileSystemItems"]
            ],
        }

    def is_filtered(self, path: str, filtered: bool = True) -> bool:
        if filtered:
            return self.dao.is_filter(path)
        return False

    def make_folder(
        self, parent_id: str, name: str, overwrite: bool = False
    ) -> RemoteFileInfo:
        fs_item = self.execute(
            command="NuxeoDrive.CreateFolder",
            parentId=parent_id,
            name=name,
            overwrite=overwrite,
        )
        return RemoteFileInfo.from_dict(fs_item)

    def stream_file(
        self,
        parent_id: str,
        file_path: Path,
        filename: str = None,
        mime_type: str = None,
        overwrite: bool = False,
        **kwargs: Any,
    ) -> RemoteFileInfo:
        """Create a document by streaming the file with the given path

        :param overwrite: Allows to overwrite an existing document with the
        same title on the server.
        """
        fs_item = self.upload(
            file_path,
            "NuxeoDrive.CreateFile",
            filename=filename,
            mime_type=mime_type,
            parentId=parent_id,
            overwrite=overwrite,
            **kwargs,
        )
        return RemoteFileInfo.from_dict(fs_item)

    def stream_update(
        self,
        fs_item_id: str,
        file_path: Path,
        parent_fs_item_id: str = None,
        filename: str = None,
        **kwargs: Any,
    ) -> RemoteFileInfo:
        """Update a document by streaming the file with the given path"""
        fs_item = self.upload(
            file_path,
            "NuxeoDrive.UpdateFile",
            filename=filename,
            id=fs_item_id,
            parentId=parent_fs_item_id,
            **kwargs,
        )
        return RemoteFileInfo.from_dict(fs_item)

    def delete(self, fs_item_id: str, parent_fs_item_id: str = None) -> None:
        self.execute(
            command="NuxeoDrive.Delete", id=fs_item_id, parentId=parent_fs_item_id
        )

    def undelete(self, uid: str) -> str:
        input_obj = "doc:" + uid
        if not self._has_new_trash_service:
            return self.execute(
                command="Document.SetLifeCycle", input_obj=input_obj, value="undelete"
            )
        else:
            return self.documents.untrash(uid)

    def rename(self, fs_item_id: str, new_name: str) -> RemoteFileInfo:
        return RemoteFileInfo.from_dict(
            self.execute(command="NuxeoDrive.Rename", id=fs_item_id, name=new_name)
        )

    def move(self, fs_item_id: str, new_parent_id: str) -> RemoteFileInfo:
        return RemoteFileInfo.from_dict(
            self.execute(
                command="NuxeoDrive.Move", srcId=fs_item_id, destId=new_parent_id
            )
        )

    def move2(self, fs_item_id: str, parent_ref: str, name: str) -> Dict[str, Any]:
        """Move a document using the Document.Move operation."""
        if "#" in fs_item_id:
            fs_item_id = fs_item_id.split("#")[-1]
        if "#" in parent_ref:
            parent_ref = parent_ref.split("#")[-1]
        if not parent_ref:
            log.info("Parent uid is empty, not performing move2.")
            return {}
        return self.documents.move(fs_item_id, parent_ref, name=name)

    def get_fs_item(
        self, fs_item_id: str, parent_fs_item_id: str = None
    ) -> Optional[Dict[str, Any]]:
        if not fs_item_id:
            log.warning("get_fs_item() called without fs_item_id")
            return None
        return self.execute(
            command="NuxeoDrive.GetFileSystemItem",
            id=fs_item_id,
            parentId=parent_fs_item_id,
        )

    def get_changes(
        self, last_root_definitions: str, log_id: int = 0
    ) -> Dict[str, Any]:
        return self.execute(
            command="NuxeoDrive.GetChangeSummary",
            lowerBound=log_id,
            lastSyncActiveRootDefinitions=last_root_definitions,
        )

    # From DocumentClient
    def fetch(self, ref: str, **kwargs: Any) -> Dict[str, Any]:
        return self.execute(command="Document.Fetch", value=get_text(ref), **kwargs)

    def check_ref(self, ref: str) -> str:
        if ref.startswith("/") and self._base_folder_path is not None:
            # This is a path ref (else an id ref)
            if self._base_folder_path.endswith("/"):
                ref = self._base_folder_path + ref[1:]
            else:
                ref = self._base_folder_path + ref
        return ref

    def query(self, query: str) -> Dict[str, Any]:
        """
        Note: We cannot use this code because it does not handle unicode characters in the query.

            >>> return self.client.query(query)
        """
        return self.execute(command="Document.Query", query=query)

    def get_info(
        self, ref: str, raise_if_missing: bool = True, fetch_parent_uid: bool = True
    ) -> Optional[NuxeoDocumentInfo]:
        try:
            doc = self.fetch(self.check_ref(ref))
        except NotFound:
            if raise_if_missing:
                raise NotFound(
                    f"Could not find {self.check_ref(ref)!r} on {self.client.host}"
                )
            return None

        parent_uid = None
        if fetch_parent_uid and doc["path"]:
            parent_uid = self.fetch(os.path.dirname(doc["path"]))["uid"]

        doc.update({"root": self.base_folder_ref, "repository": self.client.repository})
        return NuxeoDocumentInfo.from_dict(doc, parent_uid=parent_uid)

    def get_blob(
        self, ref: Union[NuxeoDocumentInfo, str], file_out: Path = None, **kwargs: Any
    ) -> bytes:
        if isinstance(ref, NuxeoDocumentInfo):
            doc_id = ref.uid
            if ref.doc_type == "Note":
                doc = self.fetch(doc_id)
                content = doc["properties"].get("note:note")
                if content:
                    content = unquote(content).encode("utf-8")
                    if file_out:
                        file_out.write_bytes(content)
                return content
        else:
            doc_id = ref

        return self.execute(
            command="Blob.Get",
            input_obj=f"doc:{doc_id}",
            json=False,
            file_out=file_out,
            **kwargs,
        )

    def lock(self, ref: str) -> Dict[str, Any]:
        return self.execute(
            command="Document.Lock", input_obj=f"doc:{self.check_ref(ref)}"
        )

    def unlock(self, ref: str) -> Dict[str, Any]:
        return self.execute(
            command="Document.Unlock", input_obj=f"doc:{self.check_ref(ref)}"
        )

    def register_as_root(self, ref: str) -> bool:
        self.execute(
            command="NuxeoDrive.SetSynchronization",
            input_obj=f"doc:{self.check_ref(ref)}",
            enable=True,
        )
        return True

    def unregister_as_root(self, ref: str) -> bool:
        self.execute(
            command="NuxeoDrive.SetSynchronization",
            input_obj=f"doc:{self.check_ref(ref)}",
            enable=False,
        )
        return True

    def set_proxy(self, proxy: Proxy = None) -> None:
        if proxy:
            settings = proxy.settings(url=self.client.host)
            self.client.client_kwargs["proxies"] = settings

    def get_server_configuration(self) -> Dict[str, Any]:
        try:
            return self.client.request(
                "GET", f"{self.client.api_path}/drive/configuration"
            ).json()
        except Exception as exc:
            log.warning(f"Error getting server configuration: {exc}")
            return {}

    def _get_trash_condition(self) -> str:
        if not self._has_new_trash_service:
            return "AND ecm:currentLifeCycleState != 'deleted'"
        return "AND ecm:isTrashed = 0"
