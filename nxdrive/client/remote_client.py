# coding: utf-8
import os
import socket
import time
from contextlib import suppress
from logging import getLogger
from os.path import isfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, TYPE_CHECKING
from urllib.parse import unquote

import requests
from nuxeo.auth import TokenAuth
from nuxeo.client import Nuxeo
from nuxeo.compat import get_text
from nuxeo.exceptions import CorruptedFile, HTTPError
from nuxeo.models import FileBlob, Batch
from nuxeo.uploads import Uploader
from nuxeo.utils import get_digest_algorithm
from PyQt5.QtWidgets import QApplication

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
    DownloadAction,
    LinkingAction,
    UploadAction,
    VerificationAction,
)
from ..exceptions import NotFound, ScrollDescendantsError, UploadPaused
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
        self.download_callback = download_callback

        # Callback function used for chunked uploads.
        # It will be forwarded to Batch.get_uploader() on the Nuxeo Python Client side.
        self.upload_callback = upload_callback

        self._has_new_trash_service = not version_le(self.client.server_version, "10.1")

        if base_folder is not None:
            base_folder_doc = self.fetch(base_folder)
            self._base_folder_ref = base_folder_doc["uid"]
            self._base_folder_path = base_folder_doc["path"]
        else:
            self._base_folder_ref, self._base_folder_path = None, None

    def __repr__(self) -> str:
        attrs = ", ".join(
            f"{attr}={getattr(self, attr, None)!r}"
            for attr in sorted(self.__init__.__code__.co_varnames[1:])  # type: ignore
        )
        return f"<{self.__class__.__name__} {attrs}>"

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
        ref = self._escape(self._check_ref(ref))
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

        if download and download.tmpname and not isfile(download.tmpname):
            # Reset if the TMP file does not exist anymore
            download = None

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
            )
            self.dao.save_download(download)

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
                callback = kwargs.pop("callback", self.download_callback)
                self.operations.save_to_file(
                    action,
                    resp,
                    file_out,
                    chunk_size=FILE_BUFFER_SIZE,
                    callback=callback,
                )
            else:
                view = memoryview(resp.content)
                with file_out.open(mode="wb") as f:
                    f.write(view)

                    # Force write of file to disk
                    f.flush()
                    os.fsync(f.fileno())

            self.check_integrity(digest, action)

            # Download finished!
            download.status = TransferStatus.DONE
            self.dao.set_transfer_status("download", download)
        finally:
            DownloadAction.finish_action()
            lock_path(file_out, locker)
            del resp

        return file_out

    def check_integrity(self, digest: str, download_action: DownloadAction) -> None:
        """
        Check the integrity of a downloaded file.

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
        blob, duration = self.upload_chunks(
            file_path, filename=filename, mime_type=mime_type, **params
        )

        # Step 2: link the uploaded blob to the document
        params["file_path"] = file_path
        item = self.link_blob_to_doc(command, blob, duration, **params)

        # Transfer is completed, delete the upload from the database
        self.dao.remove_transfer("upload", file_path)

        return item

    def upload_chunks(
        self,
        file_path: Path,
        filename: str = None,
        mime_type: str = None,
        **params: Any,
    ) -> Tuple[FileBlob, int]:
        """Upload a blob by chunks or in one go."""

        tick = time.monotonic()
        action = UploadAction(file_path, reporter=QApplication.instance())
        blob = FileBlob(str(file_path))
        if filename:
            blob.name = filename
        if mime_type:
            blob.mimetype = mime_type

        batch = None
        chunk_size = None
        try:
            # See if there is already a transfer for this file
            upload = self.dao.get_upload(path=file_path)
            if upload:
                log.debug(f"Retrieved transfer for {file_path!r}: {upload}")
                if upload.status not in (TransferStatus.ONGOING, TransferStatus.DONE):
                    raise UploadPaused(upload.uid or -1)

                # Check if the associated batch still exists server-side
                try:
                    self.uploads.get(upload.batch, upload.idx)
                except Exception:
                    log.debug(
                        f"No associated batch found, restarting from zero",
                        exc_info=True,
                    )
                else:
                    log.debug(f"Associated batch found, resuming the upload")
                    batch = Batch(batchId=upload.batch, service=self.uploads)
                    batch._upload_idx = upload.idx
                    chunk_size = upload.chunk_size

            if not batch:
                # Create a new batch and save it in the DB
                batch = self.uploads.batch()

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
                    batch=batch.uid,
                    idx=batch._upload_idx,
                    chunk_size=chunk_size,
                )
                self.dao.save_upload(upload)

            # Set those attributes as FileBlob does not have them
            # and they are required for the step 2 of .upload()
            blob.batch_id = upload.batch
            blob.fileIdx = upload.idx

            uploader: Uploader = batch.get_uploader(
                blob,
                chunked=chunked,
                chunk_size=chunk_size,
                callback=self.upload_callback,
            )

            # Update the progress on chunked upload only as the first call to
            # action.progress will set the action.uploaded attr to True for
            # empty files. This is not what we want: empty files are legits.
            if uploader.chunked:
                action.progress = chunk_size * len(uploader.blob.uploadedChunkIds)

            log.debug(
                f"Upload progression is {action.get_percent():.2f}% (chunk size is {sizeof_fmt(chunk_size)})"
            )

            if action.get_percent() < 100.0 or not action.uploaded:
                if uploader.chunked:
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

            # Transfer is completed, update the status in the database
            upload.status = TransferStatus.DONE
            self.dao.set_transfer_status("upload", upload)

            duration = int(time.monotonic() - tick)
            action.transfer_duration = duration
            if duration > 0:
                log.debug(
                    f"Size: {sizeof_fmt(blob.size)}, speed: {sizeof_fmt(blob.size / duration)}/s"
                )

            return blob, duration
        finally:
            # In case of error, log the progression to help debugging
            percent = action.get_percent()
            if percent < 100.0 and not action.uploaded:
                log.debug(f"Upload progression stopped at {percent:.2f}%")

                # Save the progression
                if upload:  # mypy fix ...
                    upload.progress = percent
                    self.dao.set_transfer_progress("upload", upload)

            UploadAction.finish_action()

            if blob.fd:
                blob.fd.close()

    def link_blob_to_doc(
        self, command: str, blob: FileBlob, duration: int, **params
    ) -> Dict[str, Any]:
        """Link the given uploaded *blob* to the given document (refs are passed into *params*)."""

        # Remove additionnal parameters to prevent a BadQuery
        params.pop("engine_uid", None)
        params.pop("is_direct_edit", None)
        file_path = params.pop("file_path")

        # Use upload duration * 2 as Nuxeo transaction timeout
        timeout = max(TX_TIMEOUT, duration * 2)
        headers = {"Nuxeo-Transaction-Timeout": str(timeout)}

        log.debug(
            f"Setting connection timeout to {timeout:,} seconds to handle the file creation on the server"
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
                timeout=timeout,
                **params,
            )
        finally:
            LinkingAction.finish_action()

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

    def _check_ref(self, ref: str) -> str:
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
            doc = self.fetch(self._check_ref(ref))
        except NotFound:
            if raise_if_missing:
                raise NotFound(
                    f"Could not find {self._check_ref(ref)!r} on {self.client.host}"
                )
            return None

        parent_uid = None
        if fetch_parent_uid and doc["path"]:
            parent_uid = self.fetch(os.path.dirname(doc["path"]))["uid"]

        doc.update(
            {"root": self._base_folder_ref, "repository": self.client.repository}
        )
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
            command="Document.Lock", input_obj=f"doc:{self._check_ref(ref)}"
        )

    def unlock(self, ref: str) -> Dict[str, Any]:
        return self.execute(
            command="Document.Unlock", input_obj=f"doc:{self._check_ref(ref)}"
        )

    def register_as_root(self, ref: str) -> bool:
        self.execute(
            command="NuxeoDrive.SetSynchronization",
            input_obj=f"doc:{self._check_ref(ref)}",
            enable=True,
        )
        return True

    def unregister_as_root(self, ref: str) -> bool:
        self.execute(
            command="NuxeoDrive.SetSynchronization",
            input_obj=f"doc:{self._check_ref(ref)}",
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
