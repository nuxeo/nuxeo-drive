"""Nuxeo-specific engine — extends the generic Engine with Nuxeo
automation operations, Direct Transfer, Direct Edit integration,
and Nuxeo-specific credential handling.
"""

import os
from contextlib import suppress
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Type

from nuxeo.exceptions import Forbidden, HTTPError, Unauthorized
from nuxeo.handlers.default import Uploader

from nxdrive.drive import server_type as _st
from nxdrive.drive.client.local import LocalClient
from nxdrive.drive.client.local.base import LocalClientMixin
from nxdrive.drive.constants import ROOT, WINDOWS, TransferStatus
from nxdrive.drive.engine.activity import Action, FileAction
from nxdrive.drive.engine.engine import Engine as _EngineBase
from nxdrive.drive.engine.engine import ServerBindingSettings  # noqa: F401 – re-export
from nxdrive.drive.exceptions import (
    AddonForbiddenError,
    AddonNotInstalledError,
    PairInterrupt,
    ThreadInterrupt,
)
from nxdrive.drive.feature import Feature
from nxdrive.drive.metrics.constants import (
    DT_NEW_FOLDER,
    DT_SESSION_FILE_COUNT,
    DT_SESSION_FOLDER_COUNT,
    DT_SESSION_ITEM_COUNT,
    DT_SESSION_NUMBER,
    DT_SESSION_STATUS,
    SYNC_ROOT_COUNT,
)
from nxdrive.drive.objects import Binder, EngineDef, Session
from nxdrive.drive.options import Options
from nxdrive.drive.qt.imports import pyqtSlot
from nxdrive.drive.utils import (
    client_certificate,
    current_thread_id,
    get_verify,
    grouper,
    set_path_readonly,
    unset_path_readonly,
)
from nxdrive.nuxeo.client.remote_client import Remote
from nxdrive.nuxeo.engine.processor import Processor
from nxdrive.nuxeo.engine.watcher.remote_watcher import RemoteWatcher

if TYPE_CHECKING:
    from nxdrive.drive.engine.workers import Worker
    from nxdrive.drive.manager import Manager  # noqa
    from nxdrive.drive.qt.imports import QThread

SYNC_ROOT = _st.get("NUXEO").sync_root

__all__ = ("Engine",)

log = getLogger(__name__)


class Engine(_EngineBase):
    """Nuxeo-specific sync engine.

    Extends the generic ``Engine`` base with Nuxeo automation operations,
    Direct Transfer, Direct Edit, and Nuxeo-specific credential handling.
    """

    def __init__(
        self,
        manager: "Manager",
        definition: EngineDef,
        /,
        *,
        binder: Binder = None,
        processors: int = 10,
        remote_cls: Type[Remote] = Remote,
        local_cls: Type[LocalClientMixin] = LocalClient,
    ) -> None:
        super().__init__(
            manager,
            definition,
            binder=binder,
            processors=processors,
            remote_cls=remote_cls,
            local_cls=local_cls,
        )

    # ------------------------------------------------------------------ overrides

    def export(self) -> Dict[str, Any]:
        result = super().export()
        result["syncing"] = self.is_syncing()
        result["initialized"] = self.get_binder().initialized
        return result

    def _create_remote_watcher(self) -> None:
        self._remote_watcher = RemoteWatcher(self, self.dao)
        self.create_thread(self._remote_watcher, "RemoteWatcher", start_connect=False)
        self._remote_watcher.initiate.connect(self.queue_manager.init_processors)
        self._remote_watcher.remoteWatcherStopped.connect(
            self.queue_manager.shutdown_processors
        )
        self._remote_watcher.updated.connect(self._check_last_sync)
        self._scanPair.connect(self._remote_watcher.scan_pair)

    @pyqtSlot()
    def _check_last_sync(self) -> None:
        if not self._sync_started:
            return

        watcher = self._local_watcher
        empty_events = watcher.empty_events()
        errors = self.queue_manager.get_errors_count()
        qm_size = self.queue_manager.get_overall_size()
        qm_active = self.queue_manager.active()
        active_status = "active" if qm_active else "inactive"
        empty_polls = self._remote_watcher.empty_polls
        win_info = ""

        if WINDOWS:
            win_info = (
                f". Windows [queue_size={watcher.get_win_queue_size()}, "
                f" folder_scan_size={watcher.get_win_folder_scan_size()}]"
            )

        log.info(
            f"Checking sync for engine {self.uid}: queue manager is {active_status} (size={qm_size}), "
            f"empty remote polls count is {empty_polls}, local watcher empty events is {empty_events}, "
            f"errors queue size is {errors} and syncing count is {self.dao.get_syncing_count()}"
            f"{win_info}"
        )

        if qm_size > 0 or not empty_events or qm_active:
            return

        if errors:
            log.debug(f"Emitting syncPartialCompleted for engine {self.uid}")
            self.syncPartialCompleted.emit()
        else:
            self.dao.update_config("last_sync_date", datetime.now(tz=timezone.utc))
            log.debug(f"Emitting syncCompleted for engine {self.uid}")
            self._sync_started = False
            self.syncCompleted.emit()

    def create_thread(
        self, worker: "Worker", name: str, /, *, start_connect: bool = True
    ) -> "QThread":
        if isinstance(worker, Processor):
            worker.pairSyncStarted.connect(self.newSyncStarted)
            worker.pairSyncEnded.connect(self.newSyncEnded)
        return super().create_thread(worker, name, start_connect=start_connect)

    def cancel_action_on(self, pair_id: int, /) -> None:
        for thread in self._threads:
            if hasattr(thread, "worker") and isinstance(thread.worker, Processor):
                pair = thread.worker.get_current_pair()
                if pair is not None and pair.id == pair_id:
                    thread.worker.quit()

    def cancel_session(self, uid: int, /) -> None:
        """Cancel all transfers for given session, with Nuxeo metrics."""
        self.dao.change_session_status(uid, TransferStatus.CANCELLED)
        self.dao.cancel_session(uid)

        docs = self.dao.get_session_items(uid)
        session_item_count = len(docs)
        session_folder_count = sum("Folderish" in doc["facets"] for doc in docs)
        self.remote.metrics.send(
            {
                DT_SESSION_FILE_COUNT: session_item_count - session_folder_count,
                DT_SESSION_FOLDER_COUNT: session_folder_count,
                DT_SESSION_ITEM_COUNT: session_item_count,
                DT_SESSION_STATUS: "cancelled",
            }
        )

    def _check_root(self) -> None:
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
            except Unauthorized:
                self.set_invalid_credentials()
            else:
                self._set_root_icon()
                self.manager.osi.register_folder_link(self.local_folder)
                set_path_readonly(self.local_folder)

    def suspend_client(self, uploader: Uploader, /) -> None:
        if self.is_paused() or not self.is_started():
            raise ThreadInterrupt()

        # Verify thread status
        thread_id = current_thread_id()
        for thread in self._threads:
            if (
                hasattr(thread, "worker")
                and isinstance(thread.worker, Processor)
                and thread.worker.thread_id == thread_id
                and not thread.worker.is_started()
            ):
                raise ThreadInterrupt()

        # Get action
        action = Action.get_current_action()
        if not isinstance(action, FileAction):
            return

        # Check for a possible lock
        current = self.local.get_path(action.filepath)
        if self._folder_lock and self._folder_lock in current.parents:
            log.info(f"PairInterrupt {current!r} because lock on {self._folder_lock!r}")
            raise PairInterrupt()

    @property
    def have_folder_upload(self) -> bool:
        """Check if the server can handle folder upload via the FileManager."""
        value = self.dao.get_bool("have_folder_upload", default=False)
        if not value:
            value = self.remote.can_use("FileManager.CreateFolder")
            if value:
                self.dao.store_bool("have_folder_upload", True)
        return value

    def start(self) -> None:
        log.info(f"Engine {self.uid} is starting")

        # Checking root in case of failed migration
        self._check_root()

        # Launch the server config file updater
        self.manager.server_config_updater.force_poll()

        self._manage_staled_transfers()
        self.resume_suspended_transfers()

        self._stopped = False
        Processor.soft_locks = {}
        for thread in self._threads:
            thread.start()

        # Try to resolve conflict on startup
        for conflict in self.dao.get_conflicts():
            self.conflict_resolver(conflict.id, emit=False)

        self.syncStarted.emit(0)
        self.started.emit()

    def stop(self) -> None:
        log.debug(f"Engine {self.uid} is stopping")

        self.dao.suspend_transfers()

        # Make a backup in case something happens
        self.dao.save_backup()

        if self.remote:
            log.debug("Sending all waiting async metrics.")
            self.remote.metrics.force_poll()

        self._stopped = True

        # The signal will propagate to all Workers. Each Worker being a QThread,
        # the stop() method will be called on each one that will trigger QThread.stop().
        self._stop.emit()

        for thread in self._threads:
            if not thread.wait(5000):
                log.error(f"Thread {thread} is not responding - terminate it")
                thread.terminate()

        with suppress(AttributeError):
            thread = self._local_watcher.thread
            if not thread.wait(5000):
                log.error(f"Thread {thread} is not responding - terminate it")
                thread.terminate()

        with suppress(AttributeError):
            thread = self._remote_watcher.thread
            if not thread.wait(5000):
                log.error(f"Thread {thread} is not responding - terminate it")
                thread.terminate()

        for thread in self._threads:
            if thread.isRunning():
                thread.wait(5000)

        with suppress(AttributeError):
            thread = self._remote_watcher.thread
            if not thread.isRunning():
                thread.wait(5000)

        with suppress(AttributeError):
            thread = self._local_watcher.thread
            if not thread.isRunning():
                thread.wait(5000)

        # Soft locks needs to be reinit in case of threads termination
        Processor.soft_locks = {}
        log.debug(f"Engine {self.uid} stopped")

    def _send_roots_metrics(self) -> None:
        """Send a metric about the number of locally enabled sync roots."""
        if not self.remote or not Feature.synchronization:
            return
        roots_count = self.dao.get_count(f"remote_parent_path = '{SYNC_ROOT}'")
        self.remote.metrics.send({SYNC_ROOT_COUNT: roots_count})

    def init_remote(self) -> Remote:
        # Used for FS synchronization operations
        args = (self.server_url, self.remote_user, self.manager.device_id, self.version)

        kwargs = {
            "password": self._remote_password,
            "timeout": self.timeout,
            "token": self._remote_token,
            "download_callback": self.suspend_client,
            "upload_callback": self.suspend_client,
            "dao": self.dao,
            "proxy": self.manager.proxy,
            "verify": get_verify(),
            "cert": client_certificate(),
        }
        return self.remote_cls(*args, **kwargs)

    def bind(self, binder: Binder, /) -> None:
        check_credentials = not binder.no_check
        check_fs = not (Options.nofscheck or binder.no_fscheck)
        self.server_url = self._normalize_url(binder.url)
        self.remote_user = binder.username
        self._remote_password = binder.password
        if binder.token:
            self._remote_token = binder.token
        self._web_authentication = bool(binder.token)

        # Check first if the folder is on a supported FS
        if check_fs:
            self._setup_local_folder(check_fs)

        if check_credentials:
            self.remote = self.init_remote()
            if not self._remote_token:
                self._remote_token = self.remote.request_token()
            if not self._remote_token:
                self.remote = None  # type: ignore

        # Save the configuration
        self.dao.store_bool("web_authentication", self._web_authentication)
        self.dao.update_config("server_url", self.server_url)
        self.dao.update_config("remote_user", self.remote_user)
        self._save_token(self._remote_token)

        # Check for the root
        # If the top level state for the server binding doesn't exist,
        # create the local folder and the top level state.
        self._check_root()

    def _add_top_level_state(self) -> None:
        if not self.remote:
            return

        try:
            if not self.remote.can_use("NuxeoDrive.GetTopLevelFolder"):
                raise AddonNotInstalledError()
        except Forbidden:
            log.warning(
                "Current user was not allowed to access 'NuxeoDrive.*' operations",
                exc_info=True,
            )
            raise AddonForbiddenError()

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
        # The root should also be sync

    def create_processor(self, item_getter: Callable, /) -> Processor:
        return Processor(self, item_getter)

    # ------------------------------------------------------------------ Direct Transfer

    def _save_last_dt_session_infos(
        self,
        remote_path: str,
        remote_ref: str,
        remote_title: str,
        duplicate_behavior: str,
        last_local_selected_location: Optional[Path],
        last_local_selected_doc_type: Optional[str],
        /,
    ) -> None:
        """Store last dt session infos into the database for later runs."""
        self.dao.update_config("dt_last_remote_location", remote_path)
        self.dao.update_config("dt_last_remote_location_ref", remote_ref)
        self.dao.update_config("dt_last_remote_location_title", remote_title)
        self.dao.update_config("dt_last_duplicates_behavior", duplicate_behavior)
        if last_local_selected_location:
            self.dao.update_config(
                "dt_last_local_selected_location", last_local_selected_location
            )
        if last_local_selected_doc_type:
            self.dao.update_config(
                "dt_last_local_selected_doc_type", last_local_selected_doc_type
            )

    def _create_remote_folder(
        self, remote_parent_path: str, new_folder: str, session_id: int, /
    ) -> Dict[str, Any]:
        try:
            res = self.remote.upload_folder(
                remote_parent_path,
                {"title": new_folder},
                headers={DT_NEW_FOLDER: 1, DT_SESSION_NUMBER: session_id},
            )
            self.directTransferNewFolderSuccess.emit(res["path"])
            return res
        except Exception:
            log.warning(
                f"Could not create the {new_folder!r} folder in the {remote_parent_path!r} remote folder",
                exc_info=True,
            )
            self.directTransferNewFolderError.emit()
            return {}

    def _create_remote_folder_with_enricher(
        self,
        remote_parent_path: str,
        new_folder: str,
        new_folder_type: str,
        session_id: int,
        /,
    ) -> Dict[str, Any]:
        try:
            payload = {
                "entity-type": "document",
                "name": new_folder,
                "type": new_folder_type,
                "properties": {"dc:title": new_folder},
            }

            res = self.remote.upload_folder_type(remote_parent_path, payload)
            new_path = f"{remote_parent_path}/{new_folder}"
            self.directTransferNewFolderSuccess.emit(new_path)
            return res
        except Exception:
            log.warning(
                f"Could not create the {new_folder!r} folder with type {new_folder_type!r} in {remote_parent_path!r}",
                exc_info=True,
            )
            self.directTransferNewFolderError.emit()
            return {}

    def _direct_transfer(
        self,
        local_paths: Dict[Path, int],
        remote_parent_path: str,
        remote_parent_ref: str,
        remote_parent_title: str,
        /,
        *,
        document_type: str = "",
        container_type: str = "",
        duplicate_behavior: str = "create",
        last_local_selected_location: Optional[Path] = None,
        last_local_selected_doc_type: Optional[str] = None,
        new_folder: Optional[str] = None,
        new_folder_type: Optional[str] = None,
    ) -> None:
        """Plan the Direct Transfer."""

        # Save last dt session infos for next times
        self._save_last_dt_session_infos(
            remote_parent_path,
            remote_parent_ref,
            remote_parent_title,
            duplicate_behavior,
            last_local_selected_location,
            last_local_selected_doc_type,
        )
        if new_folder:
            self.send_metric("direct_transfer", "new_folder", "1")
            expected_session_uid = self.dao.get_count("uid != 0", table="Sessions") + 1
            if not new_folder_type or new_folder_type == self.doc_container_type:
                item = self._create_remote_folder(
                    remote_parent_path, new_folder, expected_session_uid
                )
            else:
                item = self._create_remote_folder_with_enricher(
                    remote_parent_path,
                    new_folder,
                    new_folder_type,
                    expected_session_uid,
                )
            if not item:
                return
            remote_parent_path = item["path"]
            remote_parent_ref = item["uid"]

        # Allow to only create a folder and return.
        if not local_paths:
            return

        all_paths = local_paths.keys()
        doc_type = None
        if document_type == self.doc_container_type:
            doc_type = None
        else:
            doc_type = document_type

        cont_type = None
        if container_type == self.doc_container_type:
            cont_type = None
        else:
            cont_type = container_type
        items = [
            (
                path.as_posix(),
                path.parent.as_posix(),
                path.name,
                path.is_dir(),
                size,
                remote_parent_path,
                remote_parent_ref,
                doc_type if not path.is_dir() else cont_type,
                duplicate_behavior,
                "todo" if path.parent in all_paths else "unknown",
            )
            for path, size in sorted(local_paths.items())
        ]

        # Add all paths into the database to plan the upload, by batch
        bsize = Options.database_batch_size
        log.info("Planning items to Direct Transfer ...")
        log.debug(
            f" ... database_batch_size is {bsize}, duplicate_behavior is {duplicate_behavior!r}"
        )
        current_max_row_id = -1
        description = os.path.basename(items[0][0])
        if len(items) > 1:
            description = f"{description} (+{len(items) - 1:,})"
        session_uid = self.dao.create_session(
            remote_parent_path, remote_parent_ref, len(items), self.uid, description
        )

        for batch_items in grouper(items, bsize):
            row_id = self.dao.plan_many_direct_transfer_items(batch_items, session_uid)
            if current_max_row_id == -1:
                current_max_row_id = row_id

        log.info(f" ... Planned {len(items):,} item(s) to Direct Transfer, let's gooo!")

        # And add new pairs to the queue
        self.dao.queue_many_direct_transfer_items(current_max_row_id)

    def handle_session_status(self, session: Optional[Session], /) -> None:
        """Check the session status and send a notification if finished."""
        if not session or session.status is not TransferStatus.DONE:
            return

        self.directTransferSessionFinished.emit(
            self.uid, session.remote_ref, session.remote_path
        )
        session_folder_count = sum(
            "Folderish" in doc["facets"]
            for doc in self.dao.get_session_items(session.uid)
        )
        self.remote.metrics.send(
            {
                DT_SESSION_FILE_COUNT: session.total_items - session_folder_count,
                DT_SESSION_FOLDER_COUNT: session_folder_count,
                DT_SESSION_ITEM_COUNT: session.total_items,
                DT_SESSION_STATUS: "done",
            }
        )
        self.send_metric("direct_transfer", "session_items", str(session.total_items))

    def direct_transfer(
        self,
        local_paths: Dict[Path, int],
        remote_parent_path: str,
        remote_parent_ref: str,
        remote_parent_title: str,
        /,
        *,
        duplicate_behavior: str = "create",
        last_local_selected_location: Optional[Path] = None,
        last_local_selected_doc_type: Optional[Path] = None,
        new_folder: Optional[str] = None,
        new_folder_type: Optional[str] = None,
    ) -> None:
        """Plan the Direct Transfer."""
        self._direct_transfer(
            local_paths,
            remote_parent_path,
            remote_parent_ref,
            remote_parent_title,
            duplicate_behavior=duplicate_behavior,
            last_local_selected_location=last_local_selected_location,
            last_local_selected_doc_type=last_local_selected_doc_type,
            new_folder=new_folder,
            new_folder_type=new_folder_type,
        )

    def direct_transfer_async(
        self,
        local_paths: Dict[Path, int],
        remote_parent_path: str,
        remote_parent_ref: str,
        remote_parent_title: str,
        /,
        *,
        document_type: str,
        container_type: str,
        duplicate_behavior: str = "create",
        last_local_selected_location: Optional[Path] = None,
        last_local_selected_doc_type: Optional[str] = None,
        new_folder: Optional[str] = None,
        new_folder_type: Optional[str] = None,
    ) -> None:
        """Plan the Direct Transfer. Async to not freeze the GUI."""
        from nxdrive.drive.engine.workers import Runner

        runner = Runner(
            self._direct_transfer,
            local_paths,
            remote_parent_path,
            remote_parent_ref,
            remote_parent_title,
            document_type=document_type,
            container_type=container_type,
            duplicate_behavior=duplicate_behavior,
            last_local_selected_location=last_local_selected_location,
            last_local_selected_doc_type=last_local_selected_doc_type,
            new_folder=new_folder,
            new_folder_type=new_folder_type,
        )
        if self._threadpool:
            self._threadpool.start(runner)
        else:
            log.warning("Cannot start direct transfer, thread pool is not available")

    # ------------------------------------------------------------------ Nuxeo-specific

    def get_metadata_url(self, remote_ref: str, /, *, edit: bool = False) -> str:
        """
        Build the document's metadata URL based on the server's UI.
        Default is Web-UI.  In case of unknown UI, use the default value.
        """
        uid = remote_ref.split("#")[-1]
        repo = self.remote.client.repository
        page = ("view_documents", "view_drive_metadata")[edit]

        urls = {
            "jsf": f"{self.server_url}nxdoc/{repo}/{uid}/{page}",
            "web": f"{self.server_url}ui#!/doc/{uid}",
        }
        return urls[self.force_ui or self.wui]

    def get_task_url(self, remote_ref: str, /, *, edit: bool = False) -> str:
        """
        Build the task's URL based on the server's UI.
        Default is Web-UI.  In case of unknown UI, use the default value.
        """
        repo = self.remote.client.repository
        page = ("view_documents", "view_drive_metadata")[edit]

        urls = {
            "jsf": f"{self.server_url}tasks/{repo}/{remote_ref}/{page}",
            "web": f"{self.server_url}ui#!/tasks/{remote_ref}",
        }
        return urls[self.force_ui or self.wui]

    def open_edit(self, remote_ref: str, remote_name: str, /) -> None:
        doc_ref = remote_ref
        if "#" in doc_ref:
            doc_ref = doc_ref[doc_ref.rfind("#") + 1 :]
        log.info(f"Will try to open edit : {doc_ref}")

        def run() -> None:
            self.manager.directEdit.emit(
                self.server_url, doc_ref, self.remote_user, None
            )

        self._edit_thread = Thread(target=run)
        self._edit_thread.start()

    def get_user_full_name(self, userid: str, /, *, cache_only: bool = False) -> str:
        """Get the last contributor full name."""

        try:
            return self._user_cache[userid]
        except KeyError:
            full_name = userid

        if not cache_only:
            try:
                prop = self.remote.users.get(userid).properties
            except HTTPError:
                pass
            except (TypeError, KeyError):
                log.exception("Content error")
            else:
                first_name = prop.get("firstName") or ""
                last_name = prop.get("lastName") or ""
                full_name = " ".join([first_name, last_name]).strip()
                if not full_name:
                    full_name = prop.get("username", userid)
                self._user_cache[userid] = full_name

        return full_name

    def send_task_notification(
        self, task_id: str, remote_path: str, notification_title: str, /
    ) -> None:
        self.displayPendingTask.emit(self.uid, task_id, remote_path, notification_title)
