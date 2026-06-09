"""
Alfresco remote client for Nuxeo Drive.

Wraps the ``alfresco.Alfresco`` client to provide the interface
expected by the Drive Engine for account binding and synchronization.
"""

from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from alfresco import Alfresco
from alfresco.auth import BasicAuth, OAuth2Auth, TicketAuth
from alfresco.exceptions import AlfrescoError
from alfresco.models.node import Node

from nxdrive.drive.exceptions import NotFound
from nxdrive.drive.metrics.utils import user_agent
from nxdrive.drive.objects import RemoteFileInfo
from nxdrive.drive.options import Options
from nxdrive.drive.utils import compute_digest

if TYPE_CHECKING:
    from nxdrive.drive.client.proxy import Proxy
    from nxdrive.drive.dao.engine import EngineDAO

__all__ = ("AlfrescoRemote",)

log = getLogger(__name__)


class AlfrescoRemote:
    """Remote client for Alfresco Content Services.

    This wraps the ``alfresco.Alfresco`` client and exposes the subset
    of operations needed by the Drive Engine for Phase 1 (account
    addition and synchronization).
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
        token: Any = None,
        alfresco_ticket: str = "",
        proxy: "Proxy" = None,
        download_callback: Callable = None,
        upload_callback: Callable = None,
        dao: "EngineDAO" = None,
        timeout: int = Options.timeout,
        verify: bool = True,
        cert: Tuple[str] = None,
    ) -> None:
        self.server_url = url
        self.user_id = user_id
        self.device_id = device_id
        self.version = version
        self.timeout = timeout if timeout > 0 else 30

        if dao:
            self.dao = dao

        # Build the authentication handler
        if token and isinstance(token, dict):
            # OAuth2 token dict
            auth = OAuth2Auth.from_token(
                access_token=token.get("access_token", ""),
                refresh_token=token.get("refresh_token"),
                token_url=token.get("token_url"),
                client_id=token.get("client_id"),
            )
        elif token and isinstance(token, str):
            # Pre-supplied bearer token string
            auth = OAuth2Auth.from_token(access_token=token)
        elif alfresco_ticket:
            auth = TicketAuth.from_ticket(user_id, alfresco_ticket)
        elif password:
            auth = TicketAuth(user_id, password)
        else:
            auth = BasicAuth(user_id, "")

        self.auth = auth

        # The alfresco-python-client prepends ``/alfresco/api/…`` internally,
        # so strip the trailing ``/alfresco`` from the user-supplied URL to
        # avoid a doubled path segment.
        base_url = url.rstrip("/")
        if base_url.endswith("/alfresco"):
            base_url = base_url[: -len("/alfresco")]

        # Build the Alfresco client
        self.client = Alfresco(
            url=base_url,
            auth=auth,
            timeout=self.timeout,
        )

        # Set custom headers on the session
        self.client.session.headers.update(
            {
                "X-Device-Id": device_id,
                "User-Agent": user_agent(),
            }
        )

        # No-op metrics stub so callers that do ``remote.metrics.send(...)``
        # or ``remote.metrics.push_sync_event(...)`` don't crash.
        self.metrics = _NoOpMetrics()
        self.tasks = _NoOpTasks()

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} "
            f"url={self.server_url!r}, "
            f"user_id={self.user_id!r}>"
        )

    # -- Authentication / validation -----------------------------------------

    def check_credentials(self) -> Dict[str, Any]:
        """Validate credentials by fetching the current user profile.

        Returns the person entry dict on success.
        Raises ``AuthenticationError`` on bad credentials.
        """
        person = self.client.people.get("-me-")
        return person._raw

    # -- Node operations (used by processor) ---------------------------------

    def get_node(self, node_id: str, include: Optional[List[str]] = None) -> Node:
        """Fetch a single node."""
        return self.client.nodes.get(node_id, include=include)

    def get_children(self, node_id: str, *, max_items: int = 100) -> List[Node]:
        return self.client.nodes.list_children(node_id, max_items=max_items)

    def get_content(self, node_id: str) -> bytes:
        """Download binary content of a file node."""
        return self.client.nodes.get_content(node_id)

    def get_content_stream(self, node_id: str) -> Any:
        """Return a streaming response for a node's content."""
        return self.client.nodes.get_content_stream(node_id)

    def download_content(
        self,
        node_id: str,
        target_path: str,
        *,
        expected_digest: Optional[str] = None,
        digest_algorithm: Optional[str] = None,
    ) -> None:
        """Download content to *target_path* with optional checksum verification.

        If *expected_digest* and *digest_algorithm* are provided, the digest
        of the written file is computed and compared.  A mismatch raises
        ``AlfrescoError``.
        """
        content = self.get_content(node_id)
        dest = Path(target_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

        if expected_digest and digest_algorithm:
            local_digest = compute_digest(dest, digest_algorithm)
            if local_digest != expected_digest:
                dest.unlink(missing_ok=True)
                raise AlfrescoError(
                    f"Checksum mismatch for {node_id}: "
                    f"expected {expected_digest!r} ({digest_algorithm}), "
                    f"got {local_digest!r}"
                )

    def upload(
        self,
        parent_id: str,
        file_path: str,
        name: Optional[str] = None,
    ) -> Node:
        """Upload a file to a parent folder."""
        return self.client.nodes.upload(parent_id, file_path=file_path, name=name)

    def update_content(
        self,
        node_id: str,
        file_path: str,
    ) -> Node:
        """Replace the content of an existing file node."""
        return self.client.nodes.update_content(node_id, file_path=file_path)

    def create_folder(
        self,
        parent_id: str,
        name: str,
    ) -> Node:
        """Create a folder under *parent_id*."""
        return self.client.nodes.create_folder(parent_id, name)

    def delete(
        self,
        node_id: str,
        /,
        *,
        permanent: bool = False,
        parent_fs_item_id: str = None,
    ) -> None:
        self.client.nodes.delete(node_id, permanent=permanent)

    def move(
        self,
        node_id: str,
        target_parent_id: str,
        /,
        *,
        name: Optional[str] = None,
    ) -> RemoteFileInfo:
        node = self.client.nodes.move(node_id, target_parent_id, name=name)
        return self._node_to_remote_file_info(node)

    def copy(
        self,
        node_id: str,
        target_parent_id: str,
        name: Optional[str] = None,
    ) -> Node:
        return self.client.nodes.copy(node_id, target_parent_id, name=name)

    def rename(self, node_id: str, new_name: str, /) -> RemoteFileInfo:
        node = self.client.nodes.update(node_id, {"name": new_name})
        return self._node_to_remote_file_info(node)

    # -- Root info (used during account binding) -----------------------------

    def get_root_node(self) -> Node:
        """Return the repository root node."""
        return self.client.nodes.get("-root-", include=["path"])

    def get_filesystem_root_info(self) -> RemoteFileInfo:
        """Return a ``RemoteFileInfo`` for the root node.

        Maps the Alfresco Node model to the Drive-internal
        ``RemoteFileInfo`` dataclass.
        """
        root = self.get_root_node()
        return self._node_to_remote_file_info(root)

    # -- Folder browsing (used by filters dialog) ---------------------------

    def get_fs_children(
        self, fs_item_id: str, /, *, filtered: bool = True
    ) -> List[RemoteFileInfo]:
        """List children of a node as ``RemoteFileInfo`` objects.

        This mirrors the Nuxeo ``Remote.get_fs_children()`` interface so
        that the folder-picker dialog ("Choose folders to sync") works
        with Alfresco servers.
        """
        nodes = self.client.nodes.list_children(fs_item_id, include=["path"])
        infos = [self._node_to_remote_file_info(n) for n in nodes]

        if not filtered or not hasattr(self, "dao"):
            return infos

        return [info for info in infos if not self.dao.is_filter(info.path)]

    def is_filtered(self, path: str, /, *, filtered: bool = True) -> bool:
        """Check if a remote path is filtered out."""
        if not filtered or not hasattr(self, "dao"):
            return False
        return self.dao.is_filter(path)

    # -- Search --------------------------------------------------------------

    def search(self, query: str) -> List[Node]:
        """Run an AFTS search query."""
        return self.client.search.afts(query)

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _node_to_remote_file_info(node: Node) -> RemoteFileInfo:
        """Convert an Alfresco ``Node`` to a Drive ``RemoteFileInfo``."""
        # The Alfresco REST API ``path.elements`` contains the path *to*
        # the node (its ancestor chain) but does NOT include the node
        # itself.  We must append the node's name to get a unique,
        # hierarchical path suitable for the selective-sync filter.
        if node.path and isinstance(node.path, dict):
            elements = node.path.get("elements", [])
            parent_path = "/" + "/".join(e.get("name", "") for e in elements)
            path_str = parent_path.rstrip("/") + "/" + node.name
        else:
            path_str = "/" + node.name

        return RemoteFileInfo(
            name=node.name,
            uid=node.id,
            parent_uid=node.parent_id or "",
            path=path_str,
            folderish=node.is_folder,
            last_modification_time=node.modified_at,
            creation_time=node.created_at,
            last_contributor=(
                node.modified_by_user.get("id", "")
                if isinstance(node.modified_by_user, dict)
                else None
            ),
            digest=None,
            digest_algorithm=None,
            download_url=None,
            can_rename=True,
            can_delete=True,
            can_update=node.is_file,
            can_create_child=node.is_folder,
            lock_owner=None,
            lock_created=None,
            can_scroll_descendants=False,
        )

    # -- Adapter methods (Processor compatibility) ---------------------------
    #
    # The shared ``Processor`` class calls ``self.remote.<method>()`` using
    # the Nuxeo ``Remote`` API surface.  The methods below bridge the
    # naming/signature gap so that the same Processor works with Alfresco.

    def get_fs_info(
        self, fs_item_id: str, /, *, parent_fs_item_id: str = None
    ) -> RemoteFileInfo:
        """Return ``RemoteFileInfo`` for the given node id.

        Mirrors ``Remote.get_fs_info()`` which the Processor uses to
        refresh remote state, check digests, etc.
        """
        try:
            node = self.get_node(fs_item_id, include=["path"])
        except Exception:
            raise NotFound(f"Could not find {fs_item_id!r} on {self.server_url!r}")
        info = self._node_to_remote_file_info(node)
        # Alfresco doesn't expose content digests.  If we previously
        # stored a digest in the DB (set during upload), carry it
        # forward so the Processor's conflict check doesn't see a
        # spurious None-vs-hash mismatch.
        if info.digest is None and hasattr(self, "dao"):
            pair = self.dao.get_normal_state_from_remote(fs_item_id)
            if pair and pair.remote_digest:
                info.digest = pair.remote_digest
                info.digest_algorithm = "md5"
        return info

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
        """Download content of a node to *file_out*.

        Mirrors ``Remote.stream_content()`` — the Processor calls this
        to download file content during ``_synchronize_remotely_created``
        and ``_synchronize_remotely_modified``.
        """
        file_out.parent.mkdir(parents=True, exist_ok=True)

        resp = self.get_content_stream(fs_item_id)
        with open(file_out, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)

        # Remove the download record if the DAO is available
        if hasattr(self, "dao"):
            self.dao.remove_transfer("download", path=file_path)

        return file_out

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
        """Upload a new file and return ``RemoteFileInfo``.

        Mirrors ``Remote.stream_file()`` — the Processor calls this
        to create a new file on the server during
        ``_synchronize_locally_created``.

        Before creating a new node, check if one with the same name
        already exists in the parent folder.  If so, update its content
        instead of creating a duplicate (Alfresco auto-renames
        duplicates by appending ``-1``, ``-2``, etc.).
        """
        target_name = filename or Path(str(file_path)).name
        # Check for an existing node with the same name
        try:
            existing = self.client.nodes.list_children(parent_id)
            for child in existing:
                if child.name == target_name and child.is_file:
                    log.info(
                        f"Node {target_name!r} already exists in {parent_id!r} "
                        f"(id={child.id!r}), updating content instead of creating"
                    )
                    node = self.update_content(child.id, str(file_path))
                    info = self._node_to_remote_file_info(node)
                    info.digest = compute_digest(Path(str(file_path)), "md5")
                    info.digest_algorithm = "md5"
                    return info
        except Exception:
            log.debug(
                "Could not check for existing node, proceeding with create",
                exc_info=True,
            )
        node = self.upload(parent_id, str(file_path), name=filename)
        info = self._node_to_remote_file_info(node)
        info.digest = compute_digest(Path(str(file_path)), "md5")
        info.digest_algorithm = "md5"
        return info

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
        """Update content of an existing file and return ``RemoteFileInfo``.

        Mirrors ``Remote.stream_update()`` — the Processor calls this
        to update file content during ``_synchronize_locally_modified``.
        """
        node = self.update_content(fs_item_id, str(file_path))
        info = self._node_to_remote_file_info(node)
        info.digest = compute_digest(Path(str(file_path)), "md5")
        info.digest_algorithm = "md5"
        return info

    def make_folder(
        self, parent_id: str, name: str, /, *, overwrite: bool = False
    ) -> RemoteFileInfo:
        """Create a folder and return ``RemoteFileInfo``.

        Mirrors ``Remote.make_folder()`` — the Processor calls this
        to create a folder on the server during
        ``_synchronize_locally_created``.
        """
        node = self.create_folder(parent_id, name)
        return self._node_to_remote_file_info(node)

    def get_info(
        self,
        ref: str,
        /,
        *,
        raise_if_missing: bool = True,
        fetch_parent_uid: bool = True,
    ) -> Optional[RemoteFileInfo]:
        """Return ``RemoteFileInfo`` for a node, or ``None``.

        Mirrors ``Remote.get_info()`` — the Processor calls this
        to check if a document still exists on the server (e.g.
        before untrashing).
        """
        try:
            node = self.get_node(ref, include=["path"])
        except Exception:
            if raise_if_missing:
                raise NotFound(f"Could not find {ref!r} on {self.server_url!r}")
            return None
        info = self._node_to_remote_file_info(node)
        # Expose is_trashed so the processor can decide to undelete
        info.is_trashed = getattr(node, "is_trashed", False) or (
            node._raw.get("archivedAt") is not None if hasattr(node, "_raw") else False
        )
        return info

    def fetch(
        self,
        ref: str,
        /,
        *,
        headers: Dict[str, str] = None,
        enrichers: List[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch a node as a raw dict.

        Mirrors ``Remote.fetch()`` — the Processor calls this in
        ``_synchronize_direct_transfer`` to check if a document
        already exists.
        """
        try:
            node = self.get_node(ref, include=["path"])
            return node._raw
        except Exception:
            raise NotFound(f"Could not find {ref!r} on {self.server_url!r}")

    def undelete(self, uid: str, /) -> None:
        """Restore a node from the trashcan.

        Mirrors ``Remote.undelete()``.
        """
        try:
            self.client.trashcan.restore(uid)
        except Exception:
            log.warning(f"Could not restore node {uid!r} from trash", exc_info=True)

    def move2(self, fs_item_id: str, parent_ref: str, name: str, /) -> Dict[str, Any]:
        """Move a node into *parent_ref* and rename it to *name*.

        Mirrors ``Remote.move2()`` — the Processor calls this when
        renaming + moving in the same operation.
        """
        if not parent_ref:
            log.info("Parent's UID is empty, not performing move2().")
            return {}
        node = self.client.nodes.move(fs_item_id, parent_ref, name=name)
        return node._raw if hasattr(node, "_raw") else {}

    def cancel_batch(self, batch_details: Any, /) -> None:
        """No-op — Alfresco does not use batch uploads."""
        pass

    # -- End adapter methods -------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.client.close()

    def revoke_token(self) -> None:
        """No-op for Alfresco — ticket/basic auth has no token to revoke."""
        pass

    def get_server_configuration(self) -> Dict[str, Any]:
        """No-op — Alfresco has no Drive-specific server config endpoint."""
        return {}

    # -- Discovery API -------------------------------------------------------

    def get_discovery(self) -> Dict[str, Any]:
        """Call the Alfresco Discovery API (``/api/discovery``).

        Returns the repository information dict containing server
        version, edition, license details, installed modules, and
        feature flags.  The response is cached on the instance.
        """
        if hasattr(self, "_discovery_cache"):
            return self._discovery_cache

        url = self.server_url.rstrip("/") + "/api/discovery"
        resp = self.client.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json()
        self._discovery_cache = data
        return data


class _NoOpMetrics:
    """Stub that silently absorbs all metrics calls."""

    def send(self, metrics: Any = None) -> None:
        pass

    def push_sync_event(self, metrics: Any = None, /) -> None:
        pass

    def force_poll(self) -> None:
        pass

    def start(self) -> None:
        pass


class _NoOpTasks:
    """Stub so ``application.fetch_pending_tasks()`` works for Alfresco."""

    def get(self, *args: Any, **kwargs: Any) -> list:
        return []
