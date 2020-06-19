# coding: utf-8
import os
import socket
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Type, Union
from urllib.parse import unquote

import requests
from nuxeo.auth import TokenAuth
from nuxeo.client import Nuxeo
from nuxeo.compat import get_text
from nuxeo.exceptions import CorruptedFile, HTTPError
from nuxeo.models import Document
from nuxeo.utils import get_digest_algorithm, version_lt
from PyQt5.QtWidgets import QApplication

from ..constants import (
    APP_NAME,
    BATCH_SIZE,
    FILE_BUFFER_SIZE,
    TIMEOUT,
    TOKEN_PERMISSION,
    TX_TIMEOUT,
    TransferStatus,
)
from ..engine.activity import Action, DownloadAction, UploadAction, VerificationAction
from ..exceptions import (
    DownloadPaused,
    NotFound,
    ScrollDescendantsError,
    UnknownDigest,
    UploadPaused,
)
from ..objects import Download, NuxeoDocumentInfo, RemoteFileInfo
from ..options import Options
from ..utils import compute_digest, get_device, lock_path, sizeof_fmt, unlock_path
from .proxy import Proxy
from .uploader import BaseUploader
from .uploader.sync import SyncUploader

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
        if action:
            action.chunk_transfer_end_time_ns = monotonic_ns()

    def transfer_end_callback(self, *_: Any) -> None:
        """Callback for each chunked (down|up)loads.
        Called last to set the start time of the next chunk to (down|up)load.
        """
        action = Action.get_current_action()
        if not action:
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

        # Handle transfer pause
        if isinstance(action, DownloadAction):
            # Get the current download and check if it is still ongoing
            download = self.dao.get_download(path=action.filepath)
            if download:
                # Save the progression
                download.progress = action.get_percent()
                self.dao.set_transfer_progress("download", download)

                if download.status not in (TransferStatus.ONGOING, TransferStatus.DONE):
                    # Reset the last transferred chunk speed to skip its display in the systray
                    action.last_chunk_transfer_speed = 0
                    raise DownloadPaused(download.uid or -1)
        elif isinstance(action, UploadAction):
            # Get the current upload and check if it is still ongoing
            upload = self.dao.get_upload(path=action.filepath)
            if upload and upload.status not in (
                TransferStatus.ONGOING,
                TransferStatus.DONE,
            ):
                # Reset the last transferred chunk speed to skip its display in the systray
                action.last_chunk_transfer_speed = 0
                raise UploadPaused(upload.uid or -1)

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

    def _escape(self, path: str) -> str:
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
                tmpname=file_out,
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
                # Store the chunk size and start time for later transfer speed computation
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
                    f.write(view)
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

        def callback(_: Path) -> None:
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
        self, *args: Any, uploader: Type[BaseUploader] = SyncUploader, **kwargs: Any
    ) -> Dict[str, Any]:
        """Upload a file with a batch."""
        return uploader(self).upload(*args, **kwargs)

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
            fs_item_info.digest or "",
            **kwargs,
        )

        # Download completed, remove it from the database
        self.dao.remove_transfer("download", file_path)

        return tmp_file

    def get_fs_children(
        self, fs_item_id: str, filtered: bool = True
    ) -> List[RemoteFileInfo]:
        children = self.execute(command="NuxeoDrive.GetChildren", id=fs_item_id)
        infos = []
        for fs_item in children:
            try:
                infos.append(RemoteFileInfo.from_dict(fs_item))
            except UnknownDigest:
                log.debug(
                    f"Ignoring unsyncable document {fs_item!r} because of unknown digest"
                )
                continue
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
        if not (isinstance(res, dict) and res):
            raise ScrollDescendantsError(res)

        descendants = []
        for fs_item in res["fileSystemItems"]:
            try:
                descendants.append(RemoteFileInfo.from_dict(fs_item))
            except UnknownDigest:
                log.debug(
                    f"Ignoring unsyncable document {fs_item!r} because of unknown digest"
                )
                continue

        return {
            "scroll_id": res["scrollId"],
            "descendants": descendants,
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

    def undelete(self, uid: str) -> None:
        self.documents.untrash(uid)

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
            log.info("Parent's UID is empty, not performing move2().")
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

    def get_note(self, ref: str, file_out: Path = None) -> bytes:
        """Download the text associated to a Note document."""
        doc = self.fetch(ref)
        note = doc["properties"].get("note:note")
        if note:
            content = unquote(note).encode("utf-8")
            if file_out:
                file_out.write_bytes(content)
            return content
        return b""

    def get_blob(
        self, ref: Union[NuxeoDocumentInfo, str], file_out: Path = None, **kwargs: Any
    ) -> bytes:
        if isinstance(ref, NuxeoDocumentInfo):
            doc_id = ref.uid
            if ref.doc_type == "Note":
                return self.get_note(doc_id, file_out=file_out)
        else:
            doc_id = ref

        blob: bytes = self.execute(
            command="Blob.Get",
            input_obj=f"doc:{doc_id}",
            json=False,
            file_out=file_out,
            **kwargs,
        )
        return blob

    def lock(self, ref: str) -> None:
        self.execute(command="Document.Lock", input_obj=f"doc:{self.check_ref(ref)}")

    def unlock(self, ref: str) -> None:
        self.execute(command="Document.Unlock", input_obj=f"doc:{self.check_ref(ref)}")

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
        if version_lt(self.client.server_version, "10.2"):
            return "AND ecm:currentLifeCycleState != 'deleted'"
        return "AND ecm:isTrashed = 0"
