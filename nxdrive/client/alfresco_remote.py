from __future__ import annotations

from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)

from nuxeo.handlers.default import Uploader
from nuxeo.models import Document

from ..auth import Token
from ..constants import BATCH_SIZE
from ..engine.activity import DownloadAction
from ..objects import Metrics, NuxeoDocumentInfo, RemoteFileInfo, SubTypeEnricher
from ..options import Options
from .alfresco.client import AlfrescoClient, AlfrescoClientError
from .proxy import Proxy
from .uploader import BaseUploader
from .uploader.sync import SyncUploader

if TYPE_CHECKING:
    from ..dao.engine import EngineDAO

log = getLogger(__name__)


class AlfrescoRemote:
    """Signature-compatible adapter for incremental replacement of `Remote`.

    This class intentionally mirrors `nxdrive.client.remote_client.Remote` public
    method signatures so `Engine.init_remote()` wiring can stay unchanged while
    we progressively implement Alfresco-specific behavior.
    """

    def __init__(
        self,
        url: str,
        user_id: str,
        device_id: str,
        version: str,
        /,
        *,
        password: str = "",
        token: Token = None,
        proxy: Proxy = None,
        download_callback: Callable = None,
        upload_callback: Callable = None,
        base_folder: str = None,
        dao: "EngineDAO" = None,
        repository: str = Options.remote_repo,
        timeout: int = Options.timeout,
        verify: bool = True,
        cert: Tuple[str] = None,
    ) -> None:
        self.device_id = device_id
        self.user_id = user_id
        self.version = version
        self.base_folder_ref = base_folder
        self._base_folder_path = None
        self.dao = dao
        self.timeout = timeout
        self.verification_needed = verify
        self.token = token or ""
        self.repository = repository
        self.proxy = proxy
        self.cert = cert
        self.download_callback = download_callback
        self.upload_callback = upload_callback

        self._client = AlfrescoClient(
            url,
            username=user_id,
            password=password,
            token=self.token if isinstance(self.token, str) else "",
            verify=verify,
            timeout=timeout,
        )
        # Keep parity with `Remote` callers expecting `remote.client.repository`.
        self._client.repository = repository
        self._change_cursor = 0
        self.metrics = _NoopMetrics()
        self.tasks = _NoopTasks()

    @property
    def client(self) -> AlfrescoClient:
        """Compatibility alias for code paths using `remote.client` from `Remote`."""
        return self._client

    def can_use(self, operation: str, /) -> bool:
        """Compatibility shim for checks performed by the sync engine."""
        if operation == "NuxeoDrive.GetTopLevelFolder":
            return True
        return False

    @property
    def custom_global_metrics(self) -> Metrics:
        # Keep parity with `Remote` API; metrics integration is pending.
        return {}  # type: ignore[return-value]

    def reload_global_headers(self) -> None:
        return

    def transfer_start_callback(self, uploader: Uploader, /) -> None:
        del uploader

    def transfer_end_callback(self, uploader: Uploader, /) -> None:
        del uploader

    def execute(self, /, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "AlfrescoRemote.execute() is intentionally unsupported"
        )

    @staticmethod
    def escape(path: str, /) -> str:
        return path.replace("'", r"\'").replace("\n", r"\\n").replace("\r", r"\\r")

    @staticmethod
    def escapeCarriageReturn(path: str, /) -> str:
        return path.replace("\n", r"\\n").replace("\r", r"\\r")

    def exists(self, ref: str, /, *, use_trash: bool = True) -> bool:
        del use_trash
        try:
            self._client.get_node(ref)
            return True
        except Exception:
            return False

    def exists_in_parent(self, parent_ref: str, name: str, folderish: bool, /) -> bool:
        del folderish
        children = self._client.list_nodes(parent_ref)
        entries = children.get("list", {}).get("entries", [])
        return any(item.get("entry", {}).get("name") == name for item in entries)

    def request_token(self) -> Token:
        self.token = self._client.authenticate()
        return self.token

    def revoke_token(self) -> None:
        self.token = ""
        self._client.token = ""

    def update_token(self, token: Token, /) -> None:
        self.token = token
        self._client.token = token if isinstance(token, str) else ""

    @property
    def documents(self) -> "_DocumentsStub":
        """Stub for Nuxeo SDK documents API.

        Returns a minimal wrapper that supports enough methods for the GUI
        to work without crashing.
        """
        return _DocumentsStub(self)

    def personal_space(self) -> Document:
        """Retrieve the current user's personal space.

        Resolves the actual Alfresco user-home node so the GUI receives a real
        node ID it can use to list children.  Falls back to a placeholder when
        the path cannot be resolved (e.g. user homes not configured).
        """
        user_home_path = f"/User Homes/{self.user_id}"
        try:
            raw = self._client.get_node_by_path(user_home_path)
            entry = raw.get("entry", {})
            node_id = entry.get("id", "")
            if node_id:
                return self._entry_to_personal_space_document(
                    entry, fallback_path=user_home_path
                )
        except AlfrescoClientError as exc:
            if exc.status_code == 404:
                log.debug(
                    f"Could not resolve Alfresco user-home path {user_home_path!r}; "
                    "falling back to '-my-' lookup."
                )
            else:
                log.debug(
                    f"Could not resolve Alfresco user-home path {user_home_path!r}; "
                    "falling back to '-my-' lookup.",
                    exc_info=True,
                )
        except Exception:
            log.debug(
                f"Could not resolve Alfresco user-home path {user_home_path!r}; "
                "falling back to '-my-' lookup.",
                exc_info=True,
            )

        try:
            raw = self._client.get_node("-my-")
            entry = raw.get("entry", {})
            node_id = entry.get("id", "")
            if node_id:
                return self._entry_to_personal_space_document(
                    entry, fallback_path=user_home_path
                )
        except Exception:
            log.debug(
                "Could not resolve Alfresco personal space via '-my-'; "
                "returning placeholder personal space document.",
                exc_info=True,
            )

        return Document(
            uid="",
            path=user_home_path,
            title=self.user_id,
            type="Folder",
            contextParameters={
                "permissions": ["AddChildren", "Read", "ReadWrite"],
                "hasFolderishChild": True,
            },
        )

    def download(
        self, url: str, file_path: Path, file_out: Path, digest: str, /, **kwargs: Any
    ) -> Path:
        del url, file_path, file_out, digest, kwargs
        raise NotImplementedError("Use stream_content() mapping for Alfresco downloads")

    def check_integrity(self, digest: str, download_action: DownloadAction, /) -> None:
        del digest, download_action

    def check_integrity_simple(self, digest: str, file: Path, /) -> None:
        del digest, file

    def upload(
        self,
        path: Path,
        /,
        *,
        uploader: Type[BaseUploader] = SyncUploader,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        del uploader
        parent_id = kwargs.get("parentId") or kwargs.get("parent_id")
        if not parent_id:
            doc_pair = kwargs.get("doc_pair")
            if doc_pair is not None:
                parent_id = getattr(doc_pair, "remote_parent_ref", "") or ""
                if not parent_id:
                    # Fallback for inconsistent states where only remote_ref is set.
                    parent_id = getattr(doc_pair, "remote_ref", "") or ""
        if parent_id in {"", "-root-"}:
            parent_id = self.get_filesystem_root_info().uid
        if not parent_id:
            raise ValueError("Missing parentId for upload")
        name = kwargs.get("filename")
        relative_path = kwargs.get("relativePath") or kwargs.get("relative_path") or ""
        return self._client.upload_file(
            parent_id,
            path,
            name=name,
            relative_path=relative_path,
        )

    def upload_folder(
        self,
        parent: str,
        params: Dict[str, str],
        /,
        *,
        headers: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        del headers
        return self.upload_folder_type(parent, params)

    def upload_folder_type(
        self,
        parent: str,
        params: Dict[str, str],
        /,
        *,
        headers: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        from nxdrive.client.alfresco.client import AlfrescoClientError
        from nxdrive.exceptions import NotFound

        del headers
        raw_name = params.get("name")
        folder_name = "New Folder" if raw_name is None else raw_name
        if not folder_name.strip():
            raise ValueError("Folder name cannot be empty")
        payload = {
            "name": folder_name,
            "nodeType": "cm:folder",
        }
        try:
            return self._client._request(  # noqa: SLF001 - explicit adapter bridge
                "POST",
                f"{self._client.API_BASE}/nodes/{parent}/children",
                json=payload,
                expected_statuses=(200, 201),
            )
        except AlfrescoClientError as exc:
            if exc.status_code == 404:
                # Parent folder was deleted on the server; cannot create child.
                raise NotFound(
                    f"Cannot create folder in {parent!r}: parent folder no longer exists"
                ) from exc
            raise

    def cancel_batch(self, batch_details: Dict[str, Any], /) -> None:
        del batch_details

    def is_sync_root(self, item: RemoteFileInfo) -> bool:
        return item.parent_uid == "-root-"

    def expand_sync_root_name(self, sync_root: RemoteFileInfo) -> RemoteFileInfo:
        return sync_root

    def get_fs_info(
        self, fs_item_id: str, /, *, parent_fs_item_id: str = None
    ) -> RemoteFileInfo:
        from nxdrive.exceptions import NotFound

        del parent_fs_item_id
        if not fs_item_id or fs_item_id == "-root-":
            # Some existing DB states can carry an empty ref for the top-level row.
            # For Alfresco we map that case and the '-root-' sentinel to
            # the repository root.
            return self.get_filesystem_root_info()
        fs_item = self.get_fs_item(fs_item_id)
        if fs_item is None:
            # Node was deleted on the server but DB still has a reference.
            # Raise NotFound so the watcher can cleanly mark the pair as remotely deleted.
            raise NotFound(f"Remote item {fs_item_id!r} not found")
        return RemoteFileInfo.from_dict(fs_item)

    def get_filesystem_root_info(self) -> RemoteFileInfo:
        root = self.get_fs_item("-root-")
        if root is None:
            # Some Alfresco deployments do not expose "-root-" via GET /nodes/{id}
            # but still allow listing children from "-root-".
            root = {
                "id": "-root-",
                "parentId": "",
                "path": "/",
                "name": "Company Home",
                "folder": True,
                "lastModificationDate": None,
                "creationDate": None,
                "digestAlgorithm": None,
                "digest": None,
                "downloadURL": None,
                "canRename": False,
                "canDelete": False,
                "canUpdate": False,
                "canCreateChild": True,
                # Alfresco public v1 API only exposes /children pages, not a true
                # descendants scroll endpoint compatible with Nuxeo Drive contract.
                "canScrollDescendants": False,
            }
        return RemoteFileInfo.from_dict(root)

    def stream_content(
        self,
        fs_item_id: str,
        file_path: Path,
        file_out: Path,
        /,
        *,
        parent_fs_item_id: str = None,
        fs_item_info: RemoteFileInfo = None,
        **kwargs: Any,
    ) -> Path:
        del file_path, parent_fs_item_id, fs_item_info, kwargs
        data = self._client._request(  # noqa: SLF001 - explicit adapter bridge
            "GET",
            f"{self._client.API_BASE}/nodes/{fs_item_id}/content",
            expected_statuses=(200,),
        )
        # Content endpoint normally streams bytes; keep contract placeholder until
        # the binary transfer path is fully integrated in the uploader pipeline.
        file_out.write_bytes(str(data).encode("utf-8"))
        return file_out

    def get_fs_children(
        self, fs_item_id: str, /, *, filtered: bool = True
    ) -> List[RemoteFileInfo]:
        entries = self._list_all_children_entries(fs_item_id)
        infos = [
            RemoteFileInfo.from_dict(self._node_to_fs_item(e.get("entry", {})))
            for e in entries
        ]
        if not filtered or not self.dao:
            return infos
        return [info for info in infos if not self.is_filtered(info.path)]

    def _list_all_children_entries(
        self, fs_item_id: str, /, *, batch_size: int = BATCH_SIZE
    ) -> List[Dict[str, Any]]:
        """Return all direct children entries by traversing Alfresco pagination."""
        entries: List[Dict[str, Any]] = []
        skip_count = 0
        while True:
            payload = self._client.list_nodes(
                fs_item_id,
                max_items=batch_size,
                skip_count=skip_count,
            )
            listing = payload.get("list", {})
            page_entries = listing.get("entries", [])
            entries.extend(page_entries)

            pagination = (
                listing.get("pagination", {}) if isinstance(listing, dict) else {}
            )
            has_more_items = bool(pagination.get("hasMoreItems"))
            if not has_more_items:
                break

            count = int(pagination.get("count", len(page_entries) or batch_size))
            if count <= 0:
                # Defensive fallback against malformed pagination metadata.
                count = len(page_entries) or batch_size
            skip_count += count
        return entries

    def scroll_descendants(
        self,
        fs_item_id: str,
        scroll_id: Optional[str],
        /,
        *,
        batch_size: int = BATCH_SIZE,
    ) -> Dict[str, Any]:
        # Compatibility fallback: this returns paginated direct children only.
        # The watcher now relies on recursive scans for Alfresco.
        skip_count = int(scroll_id) if scroll_id else 0
        payload = self._client.list_nodes(
            fs_item_id,
            max_items=batch_size,
            skip_count=skip_count,
        )
        listing = payload.get("list", {})
        entries = listing.get("entries", [])
        descendants = [
            RemoteFileInfo.from_dict(self._node_to_fs_item(e.get("entry", {})))
            for e in entries
        ]
        pagination = listing.get("pagination", {}) if isinstance(listing, dict) else {}
        has_more_items = bool(pagination.get("hasMoreItems"))
        next_scroll_id = str(skip_count + len(entries)) if has_more_items else None
        return {"scroll_id": next_scroll_id, "descendants": descendants}

    def is_filtered(self, path: str, /, *, filtered: bool = True) -> bool:
        if not filtered or not self.dao:
            return False
        return bool(self.dao.is_filter(path))

    def make_folder(
        self, parent_id: str, name: str, /, *, overwrite: bool = False
    ) -> RemoteFileInfo:
        from nxdrive.client.alfresco.client import AlfrescoClientError

        log.debug(
            f"make_folder: creating {name!r} in {parent_id!r} (overwrite={overwrite})"
        )
        try:
            raw = self.upload_folder_type(parent_id, {"name": name})
        except AlfrescoClientError as exc:
            if exc.status_code == 409:
                # A folder with this name already exists; find and return it so
                # the local pair can be linked to the existing remote node.
                existing = self._find_child_by_name(parent_id, name, folderish=True)
                if existing is not None:
                    log.info(
                        f"Folder {name!r} already exists in {parent_id!r}; "
                        "reusing existing remote node."
                    )
                    return existing
            if exc.status_code == 403:
                raise PermissionError(
                    f"Alfresco denied folder creation in {parent_id!r}: "
                    "the current user does not have 'create' permission on that folder. "
                    "Check the sync-root folder and user permissions in Alfresco."
                ) from exc
            if exc.status_code == 400:
                log.warning(
                    f"Cannot create folder {name!r} in {parent_id!r}: "
                    "Alfresco rejected the name (HTTP 400). "
                    "The name may contain characters that are illegal in "
                    'Alfresco (e.g. * \\ < > ? : | "). '
                    f"Error detail: {exc.payload}"
                )
            raise
        return RemoteFileInfo.from_dict(self._node_to_fs_item(raw.get("entry", {})))

    def _find_child_by_name(
        self,
        parent_id: str,
        name: str,
        /,
        *,
        folderish: Optional[bool] = None,
    ) -> Optional[RemoteFileInfo]:
        """Return the first child of *parent_id* whose ``name`` matches, or ``None``."""
        try:
            children = self._client.list_nodes(parent_id)
        except Exception:
            return None
        entries = children.get("list", {}).get("entries", [])
        for entry in entries:
            node = entry.get("entry", {})
            if node.get("name") != name:
                continue
            if folderish is not None and bool(node.get("isFolder")) != folderish:
                continue
            return RemoteFileInfo.from_dict(self._node_to_fs_item(node))
        return None

    def stream_file(
        self,
        parent_id: str,
        file_path: Path,
        /,
        *,
        filename: str = None,
        overwrite: bool = False,
        **kwargs: Any,
    ) -> RemoteFileInfo:
        from nxdrive.client.alfresco.client import AlfrescoClientError
        from nxdrive.exceptions import NotFound

        del overwrite
        relative_path = kwargs.get("relativePath") or kwargs.get("relative_path") or ""
        try:
            raw = self._client.upload_file(
                parent_id,
                file_path,
                name=filename,
                relative_path=relative_path,
            )
        except AlfrescoClientError as exc:
            if exc.status_code == 404:
                # Parent folder was deleted on the server; cannot upload.
                raise NotFound(
                    f"Cannot upload to {parent_id!r}: parent folder no longer exists"
                ) from exc
            if exc.status_code == 403:
                raise PermissionError(
                    f"Alfresco denied upload to {parent_id!r}: "
                    "the current user does not have 'create' permission on that folder. "
                    "Check the sync-root folder and user permissions in Alfresco."
                ) from exc
            raise
        return RemoteFileInfo.from_dict(self._node_to_fs_item(raw.get("entry", {})))

    def stream_update(
        self,
        fs_item_id: str,
        file_path: Path,
        /,
        *,
        parent_fs_item_id: str = None,
        filename: str = None,
        engine_uid: str = None,
    ) -> RemoteFileInfo:
        del parent_fs_item_id, filename, engine_uid
        # PUT /nodes/{id}/content expects raw binary data, NOT multipart form-data.
        # Sending multipart (via `files=`) causes Alfresco to return HTTP 400.
        with file_path.open("rb") as stream:
            raw = self._client._request(  # noqa: SLF001 - explicit adapter bridge
                "PUT",
                f"{self._client.API_BASE}/nodes/{fs_item_id}/content",
                data=stream,
                headers={"Content-Type": "application/octet-stream"},
                expected_statuses=(200, 201),
            )
        return RemoteFileInfo.from_dict(self._node_to_fs_item(raw.get("entry", {})))

    def delete(self, fs_item_id: str, /, *, parent_fs_item_id: str = None) -> None:
        del parent_fs_item_id
        self._client.delete_node(fs_item_id)

    def undelete(self, uid: str, /) -> None:
        del uid
        raise NotImplementedError(
            "Alfresco undelete support depends on trash APIs/version"
        )

    def rename(self, fs_item_id: str, new_name: str, /) -> RemoteFileInfo:
        raw = self._client._request(  # noqa: SLF001 - explicit adapter bridge
            "PUT",
            f"{self._client.API_BASE}/nodes/{fs_item_id}",
            json={"name": new_name},
            expected_statuses=(200,),
        )
        return RemoteFileInfo.from_dict(self._node_to_fs_item(raw.get("entry", {})))

    def move(self, fs_item_id: str, new_parent_id: str, /) -> RemoteFileInfo:
        # Alfresco's PUT /nodes/{id} does NOT accept a `parentId` field.
        # Moving a node requires POST /nodes/{id}/move with `targetParentId`.
        raw = self._client._request(  # noqa: SLF001 - explicit adapter bridge
            "POST",
            f"{self._client.API_BASE}/nodes/{fs_item_id}/move",
            json={"targetParentId": new_parent_id},
            expected_statuses=(200,),
        )
        return RemoteFileInfo.from_dict(self._node_to_fs_item(raw.get("entry", {})))

    def move2(self, fs_item_id: str, parent_ref: str, name: str, /) -> Dict[str, Any]:
        # Alfresco's PUT /nodes/{id} does NOT accept a `parentId` field.
        # Moving a node requires POST /nodes/{id}/move with `targetParentId`.
        # When targetParentId equals the current parent, Alfresco treats it as
        # an in-place rename (updating the path/name without changing hierarchy).
        raw = self._client._request(  # noqa: SLF001 - explicit adapter bridge
            "POST",
            f"{self._client.API_BASE}/nodes/{fs_item_id}/move",
            json={"targetParentId": parent_ref, "name": name},
            expected_statuses=(200,),
        )
        return raw.get("entry", raw)

    def get_fs_item(
        self, fs_item_id: str, /, *, parent_fs_item_id: str = None
    ) -> Optional[Dict[str, Any]]:
        from nxdrive.client.alfresco.client import AlfrescoClientError

        del parent_fs_item_id
        try:
            raw = self._client.get_node(fs_item_id)
        except AlfrescoClientError as exc:
            if exc.status_code == 404:
                # Node was deleted on the server; silently return None.
                log.debug(f"Remote node {fs_item_id!r} no longer exists (404)")
                return None
            # Other errors (401, 403, 500, etc.) should be logged for troubleshooting.
            log.warning(
                f"Error fetching remote node {fs_item_id!r}: "
                f"HTTP {exc.status_code} - {exc}"
            )
            return None
        except Exception as exc:
            log.warning(f"Unexpected error fetching remote node {fs_item_id!r}: {exc}")
            return None
        return self._node_to_fs_item(raw.get("entry", {}))

    def get_changes(
        self, last_root_definitions: str, /, *, log_id: int = 0
    ) -> Dict[str, Any]:
        del last_root_definitions, log_id
        # Fallback strategy: ask the watcher to run a full remote scan.
        # This keeps synchronization functional until a proper delta provider is added.
        self._change_cursor += 1
        return {
            "activeSynchronizationRootDefinitions": "alfresco:/",
            "syncDate": int(datetime.now(timezone.utc).timestamp() * 1000),
            "upperBound": self._change_cursor,
            "hasTooManyChanges": True,
            "fileSystemChanges": [],
        }

    def fetch(
        self,
        ref: str,
        /,
        *,
        headers: Dict[str, str] = None,
        enrichers: List[str] = None,
    ) -> Dict[str, Any]:
        del headers, enrichers
        raw = self._client.get_node(ref)
        return raw.get("entry", raw)

    def check_ref(self, ref: str, /) -> str:
        return ref

    def query(self, query: str, /, *, page_size: int = 1) -> Dict[str, Any]:
        del query, page_size
        raise NotImplementedError(
            "NXQL query translation to Alfresco search is pending"
        )

    def get_info(
        self,
        ref: str,
        /,
        *,
        raise_if_missing: bool = True,
        fetch_parent_uid: bool = True,
    ) -> Optional[NuxeoDocumentInfo]:
        del fetch_parent_uid
        item = self.get_fs_item(ref)
        if item is None:
            if raise_if_missing:
                raise ValueError(f"Cannot find remote item {ref!r}")
            return None
        doc = self._fs_item_to_nuxeo_doc(item)
        return NuxeoDocumentInfo.from_dict(doc)

    def get_note(self, ref: str, /, *, file_out: Path = None) -> bytes:
        del ref, file_out
        raise NotImplementedError("Alfresco note documents are not mapped")

    def get_blob(
        self,
        ref: Union[NuxeoDocumentInfo, str],
        /,
        *,
        file_out: Path = None,
        **kwargs: Any,
    ) -> bytes:
        del kwargs
        node_id = ref.uid if isinstance(ref, NuxeoDocumentInfo) else ref
        data = self._client._request(  # noqa: SLF001 - explicit adapter bridge
            "GET",
            f"{self._client.API_BASE}/nodes/{node_id}/content",
            expected_statuses=(200,),
        )
        payload = str(data).encode("utf-8")
        if file_out:
            file_out.write_bytes(payload)
        return payload

    def lock(self, ref: str, /) -> Dict:
        del ref
        raise NotImplementedError("Alfresco lock endpoint mapping is pending")

    def unlock(self, ref: str, /, *, headers: Dict[str, Any] = None) -> None:
        del ref, headers
        raise NotImplementedError("Alfresco unlock endpoint mapping is pending")

    def register_as_root(self, ref: str, /) -> bool:
        del ref
        raise NotImplementedError("No native sync-root registration in Alfresco")

    def unregister_as_root(self, ref: str, /) -> bool:
        del ref
        raise NotImplementedError("No native sync-root registration in Alfresco")

    def set_proxy(self, proxy: Optional[Proxy], /) -> None:
        self.proxy = proxy

    def get_server_configuration(self) -> Dict[str, Any]:
        return {"product": "alfresco", "version": "unknown"}

    def get_config_types(self) -> Dict[str, Any]:
        return {}

    def get_doc_enricher(
        self,
        parent: str,
        enricherType: str = "subtypes",
        isFolderish: bool = True,
    ) -> List[str]:
        del parent, enricherType, isFolderish
        # Keep the GUI contract from Remote.get_doc_enricher(): return an iterable
        # of type names, never an enricher object.
        return []

    def filter_schema(self, enricherList: SubTypeEnricher) -> List[str]:
        del enricherList
        return []

    def _entry_to_personal_space_document(
        self, entry: Dict[str, Any], /, *, fallback_path: str
    ) -> Document:
        permissions = _alfresco_permissions(entry)
        path_info = entry.get("path", {})
        node_path = (
            path_info.get("name", fallback_path)
            if isinstance(path_info, dict)
            else fallback_path
        )
        return Document(
            uid=entry.get("id", ""),
            path=node_path,
            title=self.user_id,
            type="Folder",
            contextParameters={
                "permissions": permissions,
                "hasFolderishChild": True,
            },
        )

    def _node_to_fs_item(self, entry: Dict[str, Any], /) -> Dict[str, Any]:
        modified = entry.get("modifiedAt") or entry.get("modified")
        created = entry.get("createdAt") or entry.get("created")
        is_folder = bool(entry.get("isFolder"))

        # Use allowableOperations when present (requires ?include=allowableOperations).
        # Falls back to sensible defaults when the field is absent (e.g. synthetic
        # root entries created by get_filesystem_root_info).
        allowed_ops = entry.get("allowableOperations")
        if allowed_ops is not None:
            allowed_set = set(allowed_ops)
            can_create = "create" in allowed_set
            can_delete = "delete" in allowed_set
            can_update = "update" in allowed_set
            can_rename = can_update or can_delete
        else:
            # No permission data – assume safe defaults for backwards compat.
            can_create = is_folder
            can_delete = True
            can_update = not is_folder
            can_rename = True

        return {
            "id": entry.get("id", ""),
            "parentId": entry.get("parentId", ""),
            "path": entry.get("path", {}).get("name", "/")
            if isinstance(entry.get("path"), dict)
            else entry.get("path", "/"),
            "name": entry.get("name", ""),
            "folder": is_folder,
            "lastModificationDate": self._iso_to_ms(modified),
            "creationDate": self._iso_to_ms(created),
            "digestAlgorithm": entry.get("content", {}).get("mimeType"),
            "digest": entry.get("content", {}).get("mimeTypeName"),
            "downloadURL": f"{self._client.API_BASE}/nodes/{entry.get('id', '')}/content",
            "canRename": can_rename,
            "canDelete": can_delete,
            "canUpdate": can_update,
            "canCreateChild": can_create,
            # Keep recursive watcher mode on Alfresco (no true descendants scroll API).
            "canScrollDescendants": False,
        }

    def _fs_item_to_nuxeo_doc(self, item: Dict[str, Any], /) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        title = item.get("name", "")
        return {
            "root": self.base_folder_ref or "-root-",
            "uid": item.get("id", ""),
            "path": item.get("path", "/"),
            "properties": {
                "dc:title": title,
                "dc:lastContributor": self.user_id,
            },
            "facets": ["Folderish"] if item.get("folder") else [],
            "lastModified": now,
            "repository": self.repository,
            "type": "cm:folder" if item.get("folder") else "cm:content",
            "state": "project",
            "isTrashed": False,
            "isVersion": False,
            "isProxy": False,
        }

    @staticmethod
    def _iso_to_ms(value: Any, /) -> Optional[int]:
        if not value or not isinstance(value, str):
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return int(datetime.fromisoformat(normalized).timestamp() * 1000)
        except ValueError:
            return None


class _DocumentsStub:
    """Minimal stub for Nuxeo SDK documents API.

    Provides the subset of the Nuxeo Python-client ``Documents`` API that the
    GUI (``FoldersOnly`` / ``_get_root_folders`` / ``_get_children``) needs when
    running against an Alfresco backend.
    """

    def __init__(self, remote: "AlfrescoRemote") -> None:
        self.remote = remote

    # ── path / uid resolution ────────────────────────────────────────────────

    def get(self, path: str = "/", **kwargs: Any) -> Document:
        """Return a Document for the given server *path*.

        The ``path`` parameter is intentionally **not** positional-only so
        callers such as ``folders_model._get_root_folders`` can pass it as a
        keyword argument (``documents.get(path="/")``) without raising a
        ``TypeError``.
        """
        # Also honour ``uid`` keyword used by some Nuxeo SDK call sites.
        uid: str = kwargs.get("uid", "")
        if uid:
            return self._get_by_uid(uid)
        return self._get_by_path(path)

    def _get_by_path(self, path: str) -> Document:
        if path in ("/", ""):
            return Document(
                uid="-root-",
                path="/",
                title="Company Home",
                type="Folder",
                contextParameters={
                    "permissions": ["Read", "AddChildren"],
                    "hasFolderishChild": True,
                },
            )
        try:
            raw = self.remote._client.get_node_by_path(path)  # noqa: SLF001
            return self._node_to_document(raw.get("entry", {}))
        except Exception:
            log.debug(f"Could not resolve Alfresco path {path!r}", exc_info=True)
            return Document(
                uid="",
                path=path,
                title=path.rsplit("/", 1)[-1] or "root",
                type="Folder",
                contextParameters={
                    "permissions": ["Read", "AddChildren"],
                    "hasFolderishChild": True,
                },
            )

    def _get_by_uid(self, uid: str) -> Document:
        try:
            raw = self.remote._client.get_node(uid)  # noqa: SLF001
            return self._node_to_document(raw.get("entry", {}))
        except Exception:
            log.debug(f"Could not fetch Alfresco node {uid!r}", exc_info=True)
            return Document(
                uid=uid,
                path="",
                title=uid,
                type="Folder",
                contextParameters={
                    "permissions": ["Read", "AddChildren"],
                    "hasFolderishChild": True,
                },
            )

    # ── child listing ────────────────────────────────────────────────────────

    def query(
        self,
        opts: Optional[Dict[str, Any]] = None,
        enrichers: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """List folderish children of a node, mimicking the Nuxeo paginated query API.

        ``opts`` is expected to carry::

            {
                "pageProvider": "tree_children",
                "queryParams": "<parent-node-id>",
                "pageSize": -1,
                "currentPageIndex": 0,
            }

        Returns::

            {"entries": [Document, ...], "isNextPageAvailable": False}

        Alfresco pagination is handled internally; all matching children are
        returned in a single call so the caller's ``while`` loop terminates
        immediately.
        """
        del enrichers, kwargs
        opts = opts or {}
        parent_uid: str = opts.get("queryParams") or "-root-"

        # Fetch *all* direct children using the paginated helper (handles
        # Alfresco's max-items ceiling transparently).
        entries = self.remote._list_all_children_entries(parent_uid)  # noqa: SLF001

        docs: List[Document] = [
            self._node_to_document(e.get("entry", {}))
            for e in entries
            if e.get("entry", {}).get("isFolder")
        ]

        return {"entries": docs, "isNextPageAvailable": False}

    # ── helpers ──────────────────────────────────────────────────────────────

    def _node_to_document(self, entry: Dict[str, Any]) -> Document:
        """Convert an Alfresco REST API node entry to a Nuxeo ``Document``."""
        node_id: str = entry.get("id", "")
        name: str = entry.get("name", "")
        is_folder: bool = bool(entry.get("isFolder"))

        path_info = entry.get("path", {})
        node_path: str = (
            path_info.get("name", "/")
            if isinstance(path_info, dict)
            else str(path_info or "/")
        )

        permissions = _alfresco_permissions(entry)

        doc = Document(
            uid=node_id,
            path=node_path,
            title=name,
            type="cm:folder" if is_folder else "cm:content",
            contextParameters={
                "permissions": permissions,
                "hasFolderishChild": is_folder,
            },
        )
        # ``Doc.enable()`` accesses ``doc.facets``; ensure it is always present
        # regardless of whether the nuxeo-python-client version sets it.
        if not hasattr(doc, "facets") or doc.facets is None:
            doc.facets = ["Folderish"] if is_folder else []
        return doc


def _alfresco_permissions(entry: Dict[str, Any]) -> List[str]:
    """Map Alfresco ``allowableOperations`` to the Nuxeo permission strings
    that the GUI relies on (``"Read"``, ``"AddChildren"``, ``"ReadWrite"``).

    When ``allowableOperations`` is absent (not included in the response) we
    return a safe read+write default so the folder remains navigable.
    """
    allowed_ops = entry.get("allowableOperations")
    if allowed_ops is None:
        # No permission data – grant everything so the UI doesn't hide folders.
        return ["Read", "ReadWrite", "AddChildren"]
    allowed_set = set(allowed_ops)
    permissions: List[str] = []
    if "read" in allowed_set:
        permissions.append("Read")
    if "create" in allowed_set:
        permissions.append("AddChildren")
    if "update" in allowed_set:
        permissions.append("ReadWrite")
    return permissions


class _NoopMetrics:
    def send(self, metrics: Dict[str, Any], /) -> None:
        del metrics

    def push_sync_event(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def force_poll(self) -> None:
        return


class _NoopTasks:
    def get(self, options: Dict[str, Any], /) -> List[Any]:
        del options
        return []
