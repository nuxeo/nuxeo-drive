"""
Alfresco remote client for Nuxeo Drive.

Wraps the ``alfresco.Alfresco`` client to provide the interface
expected by the Drive Engine for account binding and synchronization.
"""

from logging import getLogger
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from alfresco import Alfresco
from alfresco.auth import BasicAuth, OAuth2Auth, TicketAuth
from alfresco.exceptions import AlfrescoError
from alfresco.models.node import Node

from ..constants import APP_NAME
from ..metrics.utils import current_os, user_agent
from ..objects import RemoteFileInfo
from ..options import Options
from ..utils import compute_digest

if TYPE_CHECKING:
    from ..client.proxy import Proxy
    from ..dao.engine import EngineDAO

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
        proxy: "Proxy" = None,
        download_callback: Callable = None,
        upload_callback: Callable = None,
        dao: "EngineDAO" = None,
        timeout: int = Options.timeout,
        verify: bool = True,
        cert: Tuple[str] = None,
        sync_service_url: Optional[str] = None,
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
            sync_service_url=sync_service_url,
        )

        # Set custom headers on the session
        self.client.session.headers.update(
            {
                "X-Device-Id": device_id,
                "User-Agent": user_agent(),
            }
        )

        # Subscriber/subscription IDs for sync service (populated during bind)
        self.subscriber_id: Optional[str] = None
        self.subscription_id: Optional[str] = None

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
        from pathlib import Path

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

    def delete(self, node_id: str, *, permanent: bool = False) -> None:
        self.client.nodes.delete(node_id, permanent=permanent)

    def move(
        self,
        node_id: str,
        target_parent_id: str,
        name: Optional[str] = None,
    ) -> Node:
        return self.client.nodes.move(node_id, target_parent_id, name=name)

    def copy(
        self,
        node_id: str,
        target_parent_id: str,
        name: Optional[str] = None,
    ) -> Node:
        return self.client.nodes.copy(node_id, target_parent_id, name=name)

    def rename(self, node_id: str, new_name: str) -> Node:
        return self.client.nodes.update(node_id, {"name": new_name})

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

    # -- Sync operations -----------------------------------------------------

    def register_subscriber(self, device_os: str = "") -> str:
        """Register this device as a subscriber with the Sync Service.

        Returns the server-assigned subscriber id.
        """
        sub = self.client.sync_service.create_subscriber(
            device_os=device_os or current_os(),
            application=APP_NAME,
        )
        self.subscriber_id = sub.id
        return sub.id

    def subscribe_folder(self, target_node_id: str) -> str:
        """Create a sync subscription for a folder.

        Returns the subscription id.
        """
        if not self.subscriber_id:
            raise AlfrescoError(
                "No subscriber registered; call register_subscriber() first"
            )
        subscription = self.client.sync_service.create_subscription(
            self.subscriber_id,
            target_node_id,
        )
        self.subscription_id = subscription.id
        return subscription.id

    def get_changes(self, since: Optional[str] = None, max_items: int = 100) -> Dict:
        """Fetch remote changes since the given marker.

        Works with either the Sync Service (subscriber/subscription)
        or the Sync AMP (sync set), depending on what has been configured.
        """
        if self.subscriber_id and self.subscription_id:
            return self.client.sync_service.get_changes(
                self.subscriber_id,
                self.subscription_id,
                since=since,
                max_items=max_items,
            )
        # Fallback: no sync service configured
        return {}

    def sync(self, sync_request: Optional[Dict] = None) -> Dict:
        """Push local changes to the sync service."""
        if self.subscriber_id and self.subscription_id:
            return self.client.sync_service.sync(
                self.subscriber_id,
                self.subscription_id,
                sync_request=sync_request,
            )
        return {}

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

    def get_server_version(self) -> str:
        """Return the ACS version string from the Discovery API."""
        discovery = self.get_discovery()
        repo = discovery.get("entry", {}).get("repository", {})
        version = repo.get("version", {})
        return version.get("display", "unknown")


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
