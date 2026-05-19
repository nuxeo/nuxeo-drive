"""
Alfresco Engine — sync engine for Alfresco Content Services.

Subclasses the Nuxeo Drive ``Engine`` and overrides the parts that are
Nuxeo-specific: remote client creation, credential validation, root
establishment, and the remote watcher.

Phase 1 scope: account addition + synchronization only.
Excluded features: Direct Edit, Direct Transfer, Direct Download.
"""

from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type
from urllib.parse import urlparse, urlunparse

from alfresco.exceptions import AuthenticationError

from ..client.alfresco_remote import AlfrescoRemote
from ..client.local import LocalClient
from ..client.local.base import LocalClientMixin
from ..constants import ALFRESCO_SERVER_TYPE, ROOT
from ..dao.engine import EngineDAO
from ..exceptions import EngineInitError
from ..feature import Feature
from ..objects import Binder, EngineDef
from ..options import Options
from ..qt.imports import QObject, QThread, QThreadPool
from ..utils import set_path_readonly, unset_path_readonly
from .engine import Engine
from .watcher.alfresco_remote_watcher import AlfrescoRemoteWatcher

if TYPE_CHECKING:
    from ..manager import Manager

__all__ = ("AlfrescoEngine",)

log = getLogger(__name__)


class AlfrescoEngine(Engine):
    """Sync engine for Alfresco servers.

    Re-uses the local watcher, queue manager and processor infrastructure
    from the base ``Engine``, but replaces:

    * ``init_remote()`` → creates an ``AlfrescoRemote`` instead of ``Remote``
    * ``bind()`` → validates credentials via the Alfresco People API
    * ``_check_root()`` → uses the Nodes API instead of NuxeoDrive operations
    * ``_create_remote_watcher()`` → uses ``AlfrescoRemoteWatcher``
    """

    type = ALFRESCO_SERVER_TYPE

    def __init__(
        self,
        manager: "Manager",
        definition: EngineDef,
        /,
        *,
        binder: Binder = None,
        processors: int = 10,
        remote_cls: Type[AlfrescoRemote] = AlfrescoRemote,
        local_cls: Type[LocalClientMixin] = LocalClient,
    ) -> None:
        # We must NOT call Engine.__init__ because it hardcodes Remote as the
        # remote_cls default. Instead, we replicate the relevant init steps.
        QObject.__init__(self)

        self.version = manager.version
        self.remote: Optional[AlfrescoRemote] = None  # type: ignore[assignment]
        self._remote_token: Any = None

        self.remote_cls = remote_cls
        self.local_cls = local_cls
        self.download_dir: Path = ROOT

        self.doc_container_type = "Automatic"

        self._threads: List[QThread] = []

        self.invalidAuthentication.connect(self.stop)
        self.timeout = Options.handshake_timeout
        self.manager = manager

        self.local_folder = Path(definition.local_folder)
        self.folder = str(self.local_folder)
        self.local = self.local_cls(
            self.local_folder,
            digest_callback=self.suspend_client,
            download_dir=self.download_dir,
        )

        self.uid = definition.uid
        self.name = definition.name
        self._proc_count = processors
        self._stopped = True
        self._pause: bool = Options.debug
        self._sync_started = False
        self._invalid_credentials = False
        self._offline_state = False
        self.dao = EngineDAO(self._get_db_file())

        self._remote_password: str = ""

        if binder:
            try:
                self.bind(binder)
            except Exception:
                self.dispose_db()
                raise

        self._load_configuration()

        self.download_dir = self._set_download_dir()
        self.csv_dir = self._set_csv_dir_or_cleanup()

        if not binder:
            self._setup_local_folder(not Options.nofscheck)
            if not self.server_url:
                raise EngineInitError(self)
            self.remote = self.init_remote()

        self._create_queue_manager()
        if Feature.synchronization:
            self._create_remote_watcher()
            self._create_local_watcher()

        self.newQueueItem.connect(self._check_sync_start)
        self.dao.newConflict.connect(self.conflict_resolver)

        self._set_root_icon()
        self._user_cache: Dict[str, str] = {}

        self.noSpaceLeftOnDevice.connect(self.suspend)
        self._threadpool = QThreadPool().globalInstance()

    # -- Remote client -------------------------------------------------------

    def init_remote(self) -> AlfrescoRemote:
        """Create the Alfresco remote client."""
        # Restore subscriber/subscription IDs from the DAO if available
        subscriber_id = self.dao.get_config("alfresco_subscriber_id")
        subscription_id = self.dao.get_config("alfresco_subscription_id")
        sync_service_url = self.dao.get_config("alfresco_sync_service_url")

        remote = self.remote_cls(
            self.server_url,
            self.remote_user,
            self.manager.device_id,
            self.version,
            password=self._remote_password,
            timeout=self.timeout,
            token=self._remote_token,
            dao=self.dao,
            proxy=self.manager.proxy,
            sync_service_url=sync_service_url,
        )

        if subscriber_id:
            remote.subscriber_id = subscriber_id
        if subscription_id:
            remote.subscription_id = subscription_id

        return remote

    # -- Account binding -----------------------------------------------------

    def bind(self, binder: Binder, /) -> None:
        """Bind an Alfresco account.

        Validates credentials via the People API and sets up the local
        folder and sync root.
        """
        check_credentials = not binder.no_check
        check_fs = not (Options.nofscheck or binder.no_fscheck)
        self.server_url = self._normalize_url(binder.url)
        self.remote_user = binder.username
        self._remote_password = binder.password
        if binder.token:
            self._remote_token = binder.token
        self._web_authentication = bool(binder.token)

        if check_fs:
            self._setup_local_folder(check_fs)

        if check_credentials:
            self.remote = self.init_remote()
            # Validate credentials by calling the People API
            try:
                self.remote.check_credentials()
            except AuthenticationError:
                log.warning("Alfresco authentication failed")
                self.remote = None  # type: ignore[assignment]
                raise
            except Exception:
                log.warning("Error validating Alfresco credentials", exc_info=True)
                self.remote = None  # type: ignore[assignment]
                raise

        # Save the configuration
        self.dao.store_bool("web_authentication", self._web_authentication)
        self.dao.update_config("server_url", self.server_url)
        self.dao.update_config("remote_user", self.remote_user)
        if self._remote_token:
            self._save_token(self._remote_token)

        # Fetch and store server version info via the Discovery API
        self._fetch_discovery_info()

        # Establish the sync root
        self._check_root()

    # -- Root establishment --------------------------------------------------

    def _check_root(self) -> None:
        """Create the local folder and initial sync state for Alfresco."""
        if not Feature.synchronization:
            return

        root = self.dao.get_state_from_local(ROOT)
        if root is None:
            if self.local_folder.is_dir():
                unset_path_readonly(self.local_folder)
            else:
                self.local_folder.mkdir(parents=True)
            try:
                self._add_top_level_state()
            except AuthenticationError:
                self.set_invalid_credentials()
            else:
                self._set_root_icon()
                self.manager.osi.register_folder_link(self.local_folder)
                set_path_readonly(self.local_folder)

    def _add_top_level_state(self) -> None:
        """Set up the root sync state using the Alfresco Nodes API."""
        if not self.remote:
            return

        local_info = self.local.get_info(ROOT)
        self.dao.insert_local_state(local_info, None)
        row = self.dao.get_state_from_local(ROOT)
        if not row:
            return

        remote_info = self.remote.get_filesystem_root_info()
        self.dao.update_remote_state(
            row, remote_info, remote_parent_path="", versioned=False
        )
        value = "|".join(
            (self.server_url, self.remote_user, self.manager.device_id, self.uid)
        )
        self.local.set_root_id(value.encode("utf-8"))
        self.local.set_remote_id(ROOT, remote_info.uid)
        self.dao.synchronize_state(row)

        # Register with the Sync Service if available
        self._register_sync_subscription(remote_info.uid)

    def _register_sync_subscription(self, root_node_id: str) -> None:
        """Register a subscriber and subscription with the Alfresco Sync Service."""
        if not self.remote:
            return

        # Derive the Sync Service URL from the server URL if not already stored
        sync_service_url = self.dao.get_config("alfresco_sync_service_url")
        if not sync_service_url:
            sync_service_url = self._discover_sync_service_url()
            self.dao.update_config("alfresco_sync_service_url", sync_service_url)
            # Recreate remote with the sync service URL
            self.remote = self.init_remote()
            log.info(f"Alfresco Sync Service URL: {sync_service_url}")

        try:
            subscriber_id = self.remote.register_subscriber()
            self.dao.update_config("alfresco_subscriber_id", subscriber_id)
            log.info(f"Registered Alfresco subscriber: {subscriber_id}")

            subscription_id = self.remote.subscribe_folder(root_node_id)
            self.dao.update_config("alfresco_subscription_id", subscription_id)
            log.info(f"Created Alfresco subscription: {subscription_id}")
        except Exception:
            log.warning(
                "Could not register with Alfresco Sync Service. "
                "Sync will work without change notifications.",
                exc_info=True,
            )

    # -- Remote watcher override ---------------------------------------------

    def _discover_sync_service_url(self) -> str:
        """Discover the Alfresco Sync Service URL.

        Tries, in order:
        1. Health-check on the same host (default Sync Service port 9090)
        2. Health-check on the same host and port (co-located deployment)
        3. Fallback to the port-9090 heuristic

        Returns the base URL for the Sync Service (e.g.
        ``https://host:9090/alfresco``).
        """
        import requests as _requests

        parsed = urlparse(self.server_url)
        candidates = [
            # Standard standalone sync service on port 9090
            urlunparse(
                (
                    parsed.scheme,
                    f"{parsed.hostname}:9090",
                    "/alfresco",
                    "",
                    "",
                    "",
                )
            ),
            # Co-located: sync service on the same port as the repo
            urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    "/alfresco",
                    "",
                    "",
                    "",
                )
            ),
        ]

        for candidate in candidates:
            health_url = (
                candidate.rstrip("/")
                + "/api/-default-/public/sync/versions/1/healthcheck"
            )
            try:
                resp = _requests.get(health_url, timeout=5, verify=True)
                if resp.ok:
                    log.info(f"Sync Service health-check passed at {candidate}")
                    return candidate
            except Exception:
                log.debug(
                    f"Sync Service health-check failed at {candidate}",
                    exc_info=True,
                )

        # Fallback: use the first candidate (port 9090)
        log.warning(
            "Could not verify Sync Service health; " f"falling back to {candidates[0]}"
        )
        return candidates[0]

    def _fetch_discovery_info(self) -> None:
        """Fetch and persist Alfresco server info via the Discovery API."""
        if not self.remote:
            return
        try:
            discovery = self.remote.get_discovery()
            repo = discovery.get("entry", {}).get("repository", {})
            version = repo.get("version", {}).get("display", "unknown")
            edition = repo.get("edition", "unknown")
            self.dao.update_config("alfresco_server_version", version)
            self.dao.update_config("alfresco_server_edition", edition)
            log.info(f"Alfresco server: {edition} {version}")
        except Exception:
            log.debug("Could not fetch Discovery API info", exc_info=True)

    def _create_remote_watcher(self) -> None:
        """Create the Alfresco-specific remote watcher."""
        self._remote_watcher = AlfrescoRemoteWatcher(self, self.dao)
        self.create_thread(
            self._remote_watcher, "AlfrescoRemoteWatcher", start_connect=False
        )

        self._remote_watcher.initiate.connect(self.queue_manager.init_processors)
        self._remote_watcher.remoteWatcherStopped.connect(
            self.queue_manager.shutdown_processors
        )
        self._remote_watcher.updated.connect(self._check_last_sync)
        self._scanPair.connect(self._remote_watcher.scan_pair)

    # -- Overrides for Nuxeo-specific features (disabled in Phase 1) ---------

    @property
    def have_folder_upload(self) -> bool:
        """Alfresco handles folder creation via the Nodes API directly."""
        return True

    def _send_roots_metrics(self) -> None:
        """Skip Nuxeo-specific sync root metrics for Alfresco."""
        pass

    def suspend_client(self, uploader: Any = None, /) -> None:
        """Check if the engine is paused or stopped."""
        from ..exceptions import ThreadInterrupt

        if self.is_paused() or not self.is_started():
            raise ThreadInterrupt()
