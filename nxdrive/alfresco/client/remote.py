"""
Alfresco remote client for the Drive engine.

Wraps the ``alfresco.Alfresco`` client to provide the interface
expected by the Drive Engine for account binding and synchronization.
"""

import time
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from alfresco import Alfresco
from alfresco.auth import BasicAuth, OAuth2Auth, TicketAuth
from alfresco.exceptions import AlfrescoError, ConflictError, CorruptedFile
from alfresco.models.node import Node

from nxdrive.alfresco.auth.refresh import RefreshingOAuth2Auth
from nxdrive.alfresco.sync_filters import is_top_folder_excluded
from nxdrive.drive.constants import TransferStatus
from nxdrive.drive.exceptions import DownloadPaused, NotFound, RemoteConflict
from nxdrive.drive.metrics.utils import user_agent
from nxdrive.drive.objects import Download, RemoteFileInfo, Upload
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
        on_token_refreshed: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.server_url = url
        self.user_id = user_id
        self.device_id = device_id
        self.version = version
        self.timeout = timeout if timeout > 0 else 30

        if dao:
            self.dao = dao

        # Retained so ``update_token()`` can re-attach the same callback
        # when it rebuilds the auth object after a UI re-auth.
        self._on_token_refreshed = on_token_refreshed

        # Build the authentication handler
        if token and isinstance(token, dict):
            # OAuth2 token dict.
            # ``expires_at`` is a POSIX timestamp persisted by
            # ``AlfrescoOAuthentication.get_token_dict()``. Convert it to a
            # remaining-lifetime (``expires_in``) so ``OAuth2Auth`` can decide
            # when to proactively refresh. If the token is already past its
            # expiry, pass ``expires_in=1`` — that flags it as expired
            # (accounting for the built-in 30-second skew) so the very first
            # request triggers a refresh instead of sending a stale token.
            expires_at = token.get("expires_at")
            expires_in: Optional[int] = None
            if expires_at:
                remaining = int(float(expires_at) - time.time())
                expires_in = remaining if remaining > 0 else 1
            auth = RefreshingOAuth2Auth.from_token(
                access_token=token.get("access_token", ""),
                refresh_token=token.get("refresh_token"),
                expires_in=expires_in,
                token_url=token.get("token_url"),
                client_id=token.get("client_id"),
                # ``None`` for public / PKCE clients — vendor accepts it.
                client_secret=token.get("client_secret"),
                on_refresh=on_token_refreshed,
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

    def update_token(self, token: Any, /) -> None:
        """Rebuild the auth handler in place after a token refresh.

        Called by :meth:`nxdrive.drive.engine.engine.Engine.update_token`
        after the re-authentication browser flow completes. Without this
        method the base ``Engine.update_token`` raises ``AttributeError``
        on ``self.remote.update_token(token)``, which is silently caught
        higher up as ``CONNECTION_UNKNOWN`` and leaves the systray banner
        stuck on "Authentication expired".

        Supports the two token shapes the constructor accepts:

        * ``dict`` — an OAuth2 token dict enriched with ``token_url`` and
          ``client_id`` (produced by
          :meth:`nxdrive.alfresco.auth.oauth2.AlfrescoOAuthentication.get_token`).
          Rebuilds a :class:`RefreshingOAuth2Auth` so proactive refresh
          keeps working.
        * ``str`` — a bare bearer access token (legacy path). Rebuilds a
          plain :class:`OAuth2Auth`.

        Other shapes are ignored (basic-auth / ticket accounts do not
        flow through the OAuth browser re-auth).
        """
        if isinstance(token, dict):
            expires_at = token.get("expires_at")
            expires_in: Optional[int] = None
            if expires_at:
                remaining = int(float(expires_at) - time.time())
                expires_in = remaining if remaining > 0 else 1
            new_auth: Any = RefreshingOAuth2Auth.from_token(
                access_token=token.get("access_token", ""),
                refresh_token=token.get("refresh_token"),
                expires_in=expires_in,
                token_url=token.get("token_url"),
                client_id=token.get("client_id"),
                client_secret=token.get("client_secret"),
                # Re-attach the same persistence callback the engine
                # supplied at construction time; without this, silent
                # refreshes after a UI re-auth stop being persisted.
                on_refresh=self._on_token_refreshed,
            )
        elif isinstance(token, str) and token:
            new_auth = OAuth2Auth.from_token(access_token=token)
        else:
            return

        self.auth = new_auth
        # The underlying ``alfresco.Alfresco`` client dispatches HTTP
        # requests via ``self.client.session``; ``requests.Session.auth``
        # is applied to every subsequent request. Swap both so cached
        # references (e.g. the client's own ``auth`` attribute if any)
        # stay consistent.
        with suppress(AttributeError):
            self.client.auth = new_auth
        session = getattr(self.client, "session", None)
        if session is not None:
            session.auth = new_auth

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

        Provides the ``get_fs_children()`` interface expected by the
        folder-picker dialog ("Choose folders to sync") so that it
        works with Alfresco servers.

        Uses ``iter_children`` (server-side pagination handled by the
        Alfresco Python client) so folders with more than 100 items
        are fully enumerated. This matches what the remote watcher
        actually syncs — otherwise the selective-sync dialog would
        show only the first 100 children of a folder while the scan
        would still pull the rest and sync them unconditionally
        (root cause of NXDRIVE-3186 "selected 2 files but all synced").
        """
        nodes = list(self.client.nodes.iter_children(fs_item_id, include=["path"]))
        infos = [self._node_to_remote_file_info(n) for n in nodes]

        # Always hide Alfresco system folders from the folder-picker
        # dialog so the user cannot accidentally re-enable them.
        # See ``nxdrive/alfresco/sync_filters.py`` for the rule.
        infos = [info for info in infos if not is_top_folder_excluded(info.path)]

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
    # the generic ``Remote`` API surface.  The methods below bridge the
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
        # Prefer the server-provided digest (``Node.digest`` /
        # ``Node.digest_algorithm``) when Alfresco returns one.  Fall back
        # to whatever we stored in the DB during upload so the Processor's
        # conflict check doesn't see a spurious None-vs-hash mismatch.
        if info.digest is None:
            if node.digest:
                info.digest = node.digest
                info.digest_algorithm = (node.digest_algorithm or "md5").lower()
            elif hasattr(self, "dao"):
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

        Uses the ``client.nodes.download_to()`` helper for the chunked
        read/write loop.  When the caller supplies a ``fs_item_info``
        with a non-empty ``digest``, verify the downloaded file matches
        and raise :class:`CorruptedFile` on mismatch.

        When a ``dao`` is available a ``Download`` row is registered
        before the transfer starts and updated on every chunk so the
        systray transfer list and "Remaining items" counter refresh in
        real time.  The row is removed on successful completion or on
        error.  If the user pauses the transfer through the systray, a
        :class:`DownloadPaused` is raised so the Processor can move on
        to the next queue item; the row stays in the database with
        ``PAUSED`` status ready to be resumed.
        """
        file_out.parent.mkdir(parents=True, exist_ok=True)

        dao = getattr(self, "dao", None)
        doc_pair_id = kwargs.get("doc_pair_id")
        engine_uid = kwargs.get("engine_uid")

        # Register a Download row so the systray can render a progress
        # bar and honour pause/resume.  ``save_download`` does not
        # populate ``uid`` on the object it receives, so re-fetch to
        # obtain the row identifier used for progress/status updates.
        download: Optional[Download] = None
        if dao is not None:
            download = dao.get_download(path=file_path)
            if download is None:
                dao.save_download(
                    Download(
                        None,
                        path=file_path,
                        status=TransferStatus.ONGOING,
                        engine=engine_uid,
                        doc_pair=doc_pair_id,
                        filesize=0,
                        tmpname=file_out,
                        url=None,
                    )
                )
                download = dao.get_download(path=file_path)

        def _on_progress(written: int, total: Optional[int]) -> None:
            if dao is None or download is None or download.uid is None:
                return
            # Capture the real file size the first time the server sends
            # Content-Length so the progress bar has a denominator.
            if total and not download.filesize:
                download.filesize = total
            download.progress = (written * 100.0 / total) if total else 0.0
            dao.set_transfer_progress("download", download)
            # Check pause/cancel by re-reading the row every chunk.
            current = dao.get_download(uid=download.uid)
            if current and current.status in (
                TransferStatus.PAUSED,
                TransferStatus.SUSPENDED,
                TransferStatus.CANCELLED,
            ):
                raise DownloadPaused(download.uid or -1)

        try:
            self.client.nodes.download_to(
                fs_item_id,
                str(file_out),
                chunk_size=65536,
                progress=_on_progress if dao is not None else None,
            )
        except DownloadPaused:
            # Leave the row in place with PAUSED status so the systray
            # keeps showing the item.  The Alfresco download endpoint
            # does not honour ``Range: bytes=X-``, so when the user
            # resumes we will refetch from byte 0 -- acceptable trade-off.
            raise
        except Exception:
            # Any real failure: clean the row so we don't leak stale
            # transfer entries in the systray.
            if dao is not None:
                dao.remove_transfer("download", path=file_path)
            raise

        # Server-side digest verification (opt-in: only when caller
        # provided the expected digest via fs_item_info).
        if fs_item_info and fs_item_info.digest:
            algo = (fs_item_info.digest_algorithm or "md5").lower()
            local_digest = compute_digest(file_out, algo)
            if local_digest and local_digest.lower() != fs_item_info.digest.lower():
                if dao is not None:
                    dao.remove_transfer("download", path=file_path)
                raise CorruptedFile(str(file_out), fs_item_info.digest, local_digest)

        # Remove the download record if the DAO is available
        if dao is not None:
            dao.remove_transfer("download", path=file_path)

        return file_out

    def _register_upload(
        self,
        file_path: Path,
        *,
        doc_pair_id: Optional[int] = None,
        engine_uid: Optional[str] = None,
    ) -> None:
        """Insert an ``Upload`` row so the systray shows the transfer.

        Alfresco's multipart POST is a single blocking call with no
        per-byte hook, so we cannot animate a filling progress bar for
        uploads. Registering the row still gives the user visible
        feedback: the file appears in the systray's transfer list while
        the POST is in flight, then vanishes on completion (see
        :meth:`_finish_upload`).
        """
        dao = getattr(self, "dao", None)
        if dao is None:
            return
        if dao.get_upload(path=file_path):
            return
        try:
            filesize = Path(str(file_path)).stat().st_size
        except OSError:
            filesize = 0
        dao.save_upload(
            Upload(
                None,
                path=file_path,
                status=TransferStatus.ONGOING,
                engine=engine_uid,
                doc_pair=doc_pair_id,
                filesize=filesize,
            )
        )

    def _finish_upload(self, file_path: Path) -> None:
        """Remove the ``Upload`` row registered by :meth:`_register_upload`."""
        dao = getattr(self, "dao", None)
        if dao is None:
            return
        dao.remove_transfer("upload", path=file_path)

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
        doc_pair_id = kwargs.get("doc_pair_id")
        engine_uid = kwargs.get("engine_uid")
        self._register_upload(file_path, doc_pair_id=doc_pair_id, engine_uid=engine_uid)
        try:
            target_name = filename or Path(str(file_path)).name
            # Check for an existing node with the same name.
            # ``iter_children`` walks the server-side pagination automatically
            # and short-circuits at the first match; ``list_children`` would
            # only see the first 100 children and miss duplicates in larger
            # folders (same class of bug as NXDRIVE-3186).
            try:
                for child in self.client.nodes.iter_children(parent_id):
                    if child.name == target_name and child.is_file:
                        log.info(
                            f"Node {target_name!r} already exists in "
                            f"{parent_id!r} (id={child.id!r}), updating "
                            "content instead of creating"
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
            try:
                node = self.upload(parent_id, str(file_path), name=filename)
            except ConflictError as exc:
                # Someone else created a node with the same name in
                # this folder between our iter_children check and the
                # upload call.  Surface as a conflict so the processor
                # can flip the pair to ``conflicted`` instead of
                # retrying blindly.
                log.warning(
                    f"Alfresco returned 409 uploading {filename!r} "
                    f"to {parent_id!r}: {exc}"
                )
                raise RemoteConflict(str(exc)) from exc
            info = self._node_to_remote_file_info(node)
            info.digest = compute_digest(Path(str(file_path)), "md5")
            info.digest_algorithm = "md5"
            return info
        finally:
            self._finish_upload(file_path)

    def stream_update(
        self,
        fs_item_id: str,
        file_path: Path,
        /,
        *,
        parent_fs_item_id: str = None,
        filename: str = None,
        engine_uid: str = None,
        **kwargs: Any,
    ) -> RemoteFileInfo:
        """Update content of an existing file and return ``RemoteFileInfo``.

        Mirrors ``Remote.stream_update()`` — the Processor calls this
        to update file content during ``_synchronize_locally_modified``.
        """
        doc_pair_id = kwargs.get("doc_pair_id")
        self._register_upload(file_path, doc_pair_id=doc_pair_id, engine_uid=engine_uid)
        try:
            try:
                node = self.update_content(fs_item_id, str(file_path))
            except ConflictError as exc:
                # The server refused the update because the node has
                # been modified since we last read it (version /
                # concurrent-modification conflict).  Surface as a
                # conflict so the processor flips the pair to
                # ``conflicted`` and the user is notified.
                log.warning(f"Alfresco returned 409 updating {fs_item_id!r}: {exc}")
                raise RemoteConflict(str(exc)) from exc
            info = self._node_to_remote_file_info(node)
            info.digest = compute_digest(Path(str(file_path)), "md5")
            info.digest_algorithm = "md5"
            return info
        finally:
            self._finish_upload(file_path)

    def make_folder(
        self, parent_id: str, name: str, /, *, overwrite: bool = False
    ) -> RemoteFileInfo:
        """Create a folder and return ``RemoteFileInfo``.

        Mirrors ``Remote.make_folder()`` — the Processor calls this
        to create a folder on the server during
        ``_synchronize_locally_created``.

        Reconciliation: if a folder with *name* already exists under
        *parent_id* (HTTP 409 "Duplicate child name"), adopt the
        existing remote folder instead of failing.  This mirrors the
        behaviour of :meth:`stream_file` for files and lets the
        processor recover when the local disk still holds a folder
        that was previously synchronised but whose DAO state has been
        wiped (e.g. after the user disables + re-enables the
        synchronisation feature).  Without this, the parent folder
        stays stuck in ``locally_created`` forever and every child
        file below it raises ``ParentNotSynced`` on every processor
        tick.
        """
        try:
            node = self.create_folder(parent_id, name)
        except ConflictError as exc:
            log.info(
                f"Folder {name!r} already exists under {parent_id!r} "
                f"({exc}); adopting the existing remote folder"
            )
            existing = self._find_child_folder(parent_id, name)
            if existing is None:
                # Conflict reported but child not found — surface the
                # original error so it is not silently swallowed.
                raise
            node = existing
        return self._node_to_remote_file_info(node)

    def _find_child_folder(self, parent_id: str, name: str, /) -> Optional[Node]:
        """Return the existing child folder *name* under *parent_id*,
        or ``None`` if no matching folder is found.

        Uses ``iter_children`` to walk server-side pagination so that
        matches beyond the first 100 children are still found (same
        rationale as the file-reconciliation path in :meth:`stream_file`).
        """
        try:
            for child in self.client.nodes.iter_children(parent_id):
                if child.name == name and child.is_folder:
                    return child
        except Exception:
            log.debug(
                f"Could not scan {parent_id!r} for existing folder " f"{name!r}",
                exc_info=True,
            )
        return None

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
