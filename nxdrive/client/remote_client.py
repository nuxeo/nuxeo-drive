# coding: utf-8
import os
import socket
import time
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from threading import Lock, current_thread
from typing import Any, Callable, Dict, List, Optional, Union, TYPE_CHECKING
from urllib.parse import unquote

from nuxeo.auth import TokenAuth
from nuxeo.client import Nuxeo
from nuxeo.compat import get_text
from nuxeo.exceptions import HTTPError
from nuxeo.models import FileBlob
from PyQt5.QtWidgets import QApplication

from .proxy import Proxy
from ..constants import (
    APP_NAME,
    DOWNLOAD_TMP_FILE_PREFIX,
    DOWNLOAD_TMP_FILE_SUFFIX,
    FILE_BUFFER_SIZE,
    TIMEOUT,
    TOKEN_PERMISSION,
    TX_TIMEOUT,
    BATCH_SIZE,
)
from ..engine.activity import Action, FileAction
from ..exceptions import Forbidden, NotFound
from ..objects import NuxeoDocumentInfo, RemoteFileInfo
from ..options import Options
from ..utils import get_device, lock_path, unlock_path, version_le

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
        check_suspended: Callable = None,
        base_folder: str = None,
        dao: "EngineDAO" = None,
        repository: str = Options.remote_repo,
        timeout: int = Options.timeout,
        **kwargs: Any,
    ) -> None:
        auth = TokenAuth(token) if token else (user_id, password)
        self.kwargs = kwargs

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

        # Make request to login.jsp to retrieve the JSESSIONID
        self.client.request("GET", "login.jsp", default=None)

        self.set_proxy(proxy)

        if dao:
            self._dao = dao

        self.timeout = timeout if timeout > 0 else TIMEOUT

        self.device_id = device_id
        self.user_id = user_id
        self.version = version
        self.check_suspended = check_suspended
        self._has_new_trash_service = not version_le(self.client.server_version, "10.1")

        self.upload_lock = Lock()

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
        try:
            return self.operations.execute(**kwargs)
        except HTTPError as e:
            stack = getattr(e, "stacktrace", None)
            if e.status in {401, 403}:
                raise Forbidden(stack)
            if e.status == 404:
                raise NotFound(stack)
            raise e

    def _escape(self, path) -> str:
        """Escape any single quote with an antislash to further use in a NXQL query."""
        return path.replace("'", r"\'")

    def exists(
        self, ref: str, use_trash: bool = True, include_versions: bool = False
    ) -> bool:
        """
        Check if a document exists on the server.

        :param ref: Document reference (UID).
        :param use_trash: Filter documents inside the trash.
        :param include_versions:
        :rtype: bool
        """
        ref = self._escape(self._check_ref(ref))
        id_prop = "ecm:path" if ref.startswith("/") else "ecm:uuid"
        trash = self._get_trash_condition() if use_trash else ""
        version = "" if include_versions else "AND ecm:isVersion = 0"

        query = f"SELECT * FROM Document WHERE {id_prop} = '{ref}' {trash} {version} LIMIT 1"
        results = self.query(query)
        return len(results["entries"]) == 1

    def request_token(self, revoke: bool = False) -> str:
        """Request and return a new token for the user"""
        return self.client.request_auth_token(
            device_id=self.device_id,
            app_name=APP_NAME,
            permission=TOKEN_PERMISSION,
            device=get_device(),
            revoke=revoke,
        )

    def revoke_token(self) -> str:
        return self.request_token(revoke=True)

    def update_token(self, token: str) -> None:
        self.auth = TokenAuth(token)
        self.client.auth = self.auth

    def download(
        self, url: str, file_out: Path = None, digest: str = None, **kwargs: Any
    ) -> Path:
        log.debug(
            f"Downloading file from {url!r} to {file_out!r} with digest={digest!r}"
        )

        resp = self.client.request("GET", url.replace(self.client.host, ""))

        current_action = Action.get_current_action()
        if isinstance(current_action, FileAction) and resp:
            current_action.size = int(resp.headers.get("Content-Length", None) or 0)

        if file_out:
            check_suspended = kwargs.pop("check_suspended", self.check_suspended)
            locker = unlock_path(file_out)
            try:
                self.operations.save_to_file(
                    current_action,
                    resp,
                    file_out,
                    digest=digest,
                    chunk_size=FILE_BUFFER_SIZE,
                    check_suspended=check_suspended,
                )
            finally:
                lock_path(file_out, locker)
                del resp
            return file_out
        else:
            result = resp.content
            del resp
            return result

    def upload(
        self,
        file_path: Path,
        command: str,
        filename: str = None,
        mime_type: str = None,
        **params: Any,
    ) -> Dict[str, Any]:
        """ Upload a file with a batch.

        If command is not None, the operation is executed
        with the batch as an input.
        """
        with self.upload_lock:
            tick = time.time()
            action = FileAction(
                "Upload", file_path, filename, reporter=QApplication.instance()
            )
            try:
                # Init resumable upload getting a batch generated by the
                # server. This batch is to be used as a resumable session
                batch = self.uploads.batch()

                blob = FileBlob(str(file_path))
                if filename:
                    blob.name = filename
                if mime_type:
                    blob.mimetype = mime_type

                # By default, Options.chunk_size is 20, so chunks will be 20Mio.
                # It can be set to a value between 1 and 20 through the config.ini
                chunk_size = Options.chunk_size * 1024 * 1024
                # For the upload to be chunked, the Options.chunk_upload must be True
                # and the blob must be bigger than Options.chunk_limit, which by default
                # is equal to Options.chunk_size.
                chunked = (
                    Options.chunk_upload
                    and blob.size > Options.chunk_limit * 1024 * 1024
                )

                uploader = batch.get_uploader(
                    blob, chunked=chunked, chunk_size=chunk_size
                )

                if uploader.chunked:
                    # If there is an UploadError, we catch it from the processor
                    for _ in uploader.iter_upload():
                        # Here 0 may happen when doing a single upload
                        action.progress += uploader.chunk_size or 0
                else:
                    uploader.upload()

                upload_result = uploader.response
                blob.fd.close()

                upload_duration = int(time.time() - tick)
                action.transfer_duration = upload_duration
                # Use upload duration * 2 as Nuxeo transaction timeout
                tx_timeout = max(TX_TIMEOUT, upload_duration * 2)
                log.debug(
                    f"Using {tx_timeout} seconds [max({TX_TIMEOUT}, "
                    f"2 * upload time={upload_duration})] as Nuxeo "
                    f"transaction timeout for batch execution of {command!r} "
                    f"with file {file_path!r}"
                )

                if upload_duration > 0:
                    size = os.stat(file_path).st_size
                    log.debug(
                        f"Speed for {size / 1000} kilobytes is {upload_duration} sec:"
                        f" {size / upload_duration / 1024} Kib/s"
                    )

                headers = {"Nuxeo-Transaction-Timeout": str(tx_timeout)}
                return self.execute(
                    command=command, input_obj=upload_result, headers=headers, **params
                )
            finally:
                FileAction.finish_action()

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
        parent_fs_item_id: str = None,
        fs_item_info: RemoteFileInfo = None,
        file_out: Path = None,
        **kwargs: Any,
    ) -> Path:
        """Stream the binary content of a file system item to a tmp file

        Raises NotFound if file system item with id fs_item_id
        cannot be found
        """
        fs_item_info = fs_item_info or self.get_fs_info(
            fs_item_id, parent_fs_item_id=parent_fs_item_id
        )
        download_url = self.client.host + fs_item_info.download_url
        file_name = file_path.name
        if file_out is None:
            name = "".join(
                [
                    DOWNLOAD_TMP_FILE_PREFIX,
                    file_name,
                    str(current_thread().ident),
                    DOWNLOAD_TMP_FILE_SUFFIX,
                ]
            )
            file_out = file_path.with_name(name)

        FileAction(
            "Download", file_out, file_name, size=0, reporter=QApplication.instance()
        )
        try:
            tmp_file = self.download(
                download_url, file_out=file_out, digest=fs_item_info.digest, **kwargs
            )
        except Exception as e:
            with suppress(FileNotFoundError):
                file_out.unlink()
            raise e
        finally:
            FileAction.finish_action()
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
        return {
            "scroll_id": res["scrollId"],
            "descendants": [
                RemoteFileInfo.from_dict(fs_item) for fs_item in res["fileSystemItems"]
            ],
        }

    def is_filtered(self, path: str, filtered: bool = True) -> bool:
        if filtered:
            return self._dao.is_filter(path)
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
        )
        return RemoteFileInfo.from_dict(fs_item)

    def stream_update(
        self,
        fs_item_id: str,
        file_path: Path,
        parent_fs_item_id: str = None,
        filename: str = None,
    ) -> RemoteFileInfo:
        """Update a document by streaming the file with the given path"""
        fs_item = self.upload(
            file_path,
            "NuxeoDrive.UpdateFile",
            filename=filename,
            id=fs_item_id,
            parentId=parent_fs_item_id,
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
        self,
        ref: str,
        raise_if_missing: bool = True,
        fetch_parent_uid: bool = True,
        include_versions: bool = False,
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
        if fetch_parent_uid:
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
