"""
Alfresco Engine — sync engine for Alfresco Content Services.

Subclasses the generic Drive ``Engine`` and overrides the parts that are
Alfresco-specific: remote client creation, credential validation, root
establishment, and the remote watcher.

Phase 1 scope: account addition + synchronization only.
Excluded features: Direct Edit, Direct Transfer, Direct Download.
"""

from logging import getLogger
from typing import TYPE_CHECKING, Any, Type
from urllib.parse import urlsplit

from alfresco.exceptions import AuthenticationError

from nxdrive.alfresco.client.remote import AlfrescoRemote
from nxdrive.alfresco.engine.processor import AlfrescoProcessor
from nxdrive.alfresco.engine.watcher.remote_watcher import AlfrescoRemoteWatcher
from nxdrive.drive import server_type as _st
from nxdrive.drive.client.local import LocalClient
from nxdrive.drive.client.local.base import LocalClientMixin
from nxdrive.drive.constants import ROOT
from nxdrive.drive.engine.engine import Engine
from nxdrive.drive.exceptions import RemoteUnauthorized
from nxdrive.drive.feature import Feature
from nxdrive.drive.objects import Binder, EngineDef
from nxdrive.drive.options import Options
from nxdrive.drive.qt.imports import pyqtSlot
from nxdrive.drive.utils import set_path_readonly, unset_path_readonly

if TYPE_CHECKING:
    from nxdrive.drive.manager import Manager

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

    type = _st.get("ALFRESCO").engine_type

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
        # Must be set before super().__init__() because the base class
        # calls self.bind() which triggers init_remote() which reads this.
        self._alfresco_ticket: str = ""

        super().__init__(
            manager,
            definition,
            binder=binder,
            processors=processors,
            remote_cls=remote_cls,
            local_cls=local_cls,
        )

    # -- Filter selection tracking -------------------------------------------

    def needs_filters_selection(self) -> bool:
        """Return True if the user hasn't yet selected folders to sync.

        Backward-compatible: if a root pair already exists (engine was
        previously configured), treat it as configured even without the flag.
        """
        if not Feature.synchronization:
            return False
        if self.dao.get_config("filters_configured"):
            return False
        # Backward compat: root pair exists → already configured
        if self.dao.get_state_from_local(ROOT) is not None:
            self.dao.update_config("filters_configured", "1")
            return False
        return True

    def mark_filters_configured(self) -> None:
        """Mark that the user has selected folders, then create root and scan."""
        self.dao.update_config("filters_configured", "1")
        self._check_root()
        # Trigger a full remote scan on the next watcher cycle
        self.dao.update_config("remote_need_full_scan", "1")

    # -- Sync state tracking -------------------------------------------------

    @pyqtSlot(object)
    def _check_sync_start(self, *, row_id: str = None) -> None:
        if not self._sync_started:
            queue_size = self.queue_manager.get_overall_size()
            log.info(f"[Alfresco _check_sync_start] queue_size={queue_size}")
            if queue_size > 0:
                self._sync_started = True
                self.syncStarted.emit(queue_size)

    # -- Processor -----------------------------------------------------------

    def create_processor(self, item_getter, /) -> AlfrescoProcessor:
        return AlfrescoProcessor(self, item_getter)

    # -- Remote client -------------------------------------------------------

    def init_remote(self) -> AlfrescoRemote:
        """Create the Alfresco remote client."""
        remote = self.remote_cls(
            self.server_url,
            self.remote_user,
            self.manager.device_id,
            self.version,
            password=self._remote_password,
            timeout=self.timeout,
            token=self._remote_token,
            alfresco_ticket=self._alfresco_ticket,
            dao=self.dao,
            proxy=self.manager.proxy,
        )

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
            except AuthenticationError as exc:
                log.warning("Alfresco authentication failed")
                self.remote = None  # type: ignore[assignment]
                raise RemoteUnauthorized(message=str(exc)) from exc
            except Exception:
                log.warning("Error validating Alfresco credentials", exc_info=True)
                self.remote = None  # type: ignore[assignment]
                raise

            # After successful auth, extract and persist the ticket
            # so the password is never stored.
            if self._remote_password and not self._remote_token:
                auth = getattr(self.remote, "auth", None)
                ticket = getattr(auth, "ticket", None)
                if not ticket:
                    # Fallback: try from the underlying session
                    session_auth = getattr(
                        getattr(getattr(self.remote, "client", None), "session", None),
                        "auth",
                        None,
                    )
                    ticket = getattr(session_auth, "ticket", None)
                if ticket:
                    self._alfresco_ticket = ticket
                    self._remote_password = ""
                    self._save_ticket(ticket)
                    log.info("Alfresco ticket persisted after bind")
                else:
                    log.warning(
                        "Could not extract ticket after successful bind; "
                        "user will be prompted to re-login on next restart"
                    )

        # Save the configuration
        self.dao.store_bool("web_authentication", self._web_authentication)
        self.dao.update_config("server_url", self.server_url)
        self.dao.update_config("remote_user", self.remote_user)
        if self._remote_token:
            self._save_token(self._remote_token)

        # Fetch and store server version info via the Discovery API
        self._fetch_discovery_info()

        # Mark filters as configured before _check_root() so the guard
        # inside _check_root() doesn't skip root pair creation.
        if Feature.synchronization:
            self.dao.update_config("filters_configured", "1")

        # Establish the sync root
        self._check_root()

    # -- Root establishment --------------------------------------------------

    def _check_root(self) -> None:
        """Create the local folder and initial sync state for Alfresco."""
        if not Feature.synchronization:
            return

        # On restart, don't create the root pair until the user has
        # selected which folders to sync via the filters dialog.
        if not self.dao.get_config("filters_configured"):
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

    @pyqtSlot()
    def _check_last_sync(self) -> None:
        """Check whether sync has completed for this Alfresco engine."""
        if not self._sync_started:
            return

        watcher = self._local_watcher
        empty_events = watcher.empty_events()
        qm_size = self.queue_manager.get_overall_size()
        qm_active = self.queue_manager.active()
        errors = self.queue_manager.get_errors_count()

        if qm_size > 0 or not empty_events or qm_active:
            return

        if errors:
            self.syncPartialCompleted.emit()
        else:
            self.dao.update_config(
                "last_sync_date",
                __import__("datetime").datetime.now(
                    tz=__import__("datetime").timezone.utc
                ),
            )
            log.info(f"Sync completed for Alfresco engine {self.uid}")
            self._sync_started = False
            self.syncCompleted.emit()

    def conflict_resolver(self, row_id: int, /, *, emit: bool = True) -> None:
        """Alfresco-specific conflict resolver.

        Alfresco doesn't expose content digests, so ``remote_digest`` in the
        DB is always from our own uploads.  A mismatch between
        ``local_digest`` and ``remote_digest`` therefore means the local
        file was edited after the last upload — *not* a server-side
        conflict.  Reset the pair to ``locally_modified`` so the
        processor uploads the new version.
        """
        pair = self.dao.get_state_from_id(row_id)
        if not pair:
            return

        if (
            pair.pair_state == "conflicted"
            and pair.local_state == "modified"
            and pair.remote_state == "modified"
        ):
            log.info(
                f"Alfresco conflict resolver: resetting {pair.local_name!r} "
                f"to locally_modified (not a real conflict)"
            )
            self.dao._force_sync(pair, "modified", "synchronized", "locally_modified")
            return

        super().conflict_resolver(row_id, emit=emit)

    # -- Overrides for Nuxeo-specific features (disabled in Phase 1) ---------

    @property
    def have_folder_upload(self) -> bool:
        """Alfresco handles folder creation via the Nodes API directly."""
        return True

    def _send_roots_metrics(self) -> None:
        """Skip Nuxeo-specific sync root metrics for Alfresco."""
        pass

    def _load_configuration(self) -> None:
        """Load engine configuration, restoring basic-auth password if needed."""
        self._web_authentication = self.dao.get_bool("web_authentication")
        self.server_url = self.dao.get_config("server_url")
        self.hostname = urlsplit(self.server_url).hostname if self.server_url else None
        self.wui = self.dao.get_config("ui", default="web")
        self.force_ui = self.dao.get_config("force_ui")
        self.remote_user = self.dao.get_config("remote_user")
        self._remote_token = self._load_token()

        if not self._remote_token:
            # For Alfresco basic auth, restore the saved ticket
            self._alfresco_ticket = self._load_ticket()
            if not self._alfresco_ticket:
                log.warning(
                    "No token or ticket found in engine configuration; "
                    "authentication will be checked on first API call"
                )

    def _save_ticket(self, ticket: str) -> None:
        """Store the Alfresco authentication ticket encrypted in the DAO."""
        from nxdrive.drive.utils import encrypt, force_decode

        key = f"{self.remote_user}{self.server_url}"
        secure = force_decode(encrypt(ticket, key))
        self.dao.update_config("alfresco_ticket", secure)

    def _load_ticket(self) -> str:
        """Retrieve and decrypt the stored Alfresco ticket, if any."""
        from nxdrive.drive.utils import decrypt, force_decode

        stored = self.dao.get_config("alfresco_ticket")
        if not stored:
            return ""
        key = f"{self.remote_user}{self.server_url}"
        try:
            return force_decode(decrypt(stored, key))
        except Exception:
            log.debug("Could not decrypt stored ticket", exc_info=True)
            return ""

    def suspend_client(self, uploader: Any = None, /) -> None:
        """Check if the engine is paused or stopped."""
        from nxdrive.drive.exceptions import ThreadInterrupt

        if self.is_paused() or not self.is_started():
            raise ThreadInterrupt()
