import datetime
import json
import os
import os.path
import shutil
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from logging import getLogger
from pathlib import Path, PurePath
from threading import Thread
from time import sleep
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Type
from urllib.parse import urlsplit

import requests
from nuxeo.exceptions import Forbidden, HTTPError
from nuxeo.handlers.default import Uploader

from ..auth import Token
from ..client.local import LocalClient
from ..client.local.base import LocalClientMixin
from ..client.remote_client import Remote
from ..constants import LINUX, MAC, ROOT, SYNC_ROOT, WINDOWS, DelAction, TransferStatus
from ..dao.engine import EngineDAO
from ..exceptions import (
    AddonForbiddenError,
    AddonNotInstalledError,
    EngineInitError,
    MissingXattrSupport,
    PairInterrupt,
    RootAlreadyBindWithDifferentAccount,
    ThreadInterrupt,
    UnknownDigest,
)
from ..feature import Feature
from ..metrics.constants import (
    DT_NEW_FOLDER,
    DT_SESSION_FILE_COUNT,
    DT_SESSION_FOLDER_COUNT,
    DT_SESSION_ITEM_COUNT,
    DT_SESSION_NUMBER,
    DT_SESSION_STATUS,
    SYNC_ROOT_COUNT,
)
from ..objects import Binder, DocPairs, EngineDef, Metrics, Session
from ..options import Options
from ..qt.imports import QObject, QThread, QThreadPool, pyqtSignal, pyqtSlot
from ..state import State
from ..utils import (
    client_certificate,
    current_thread_id,
    decrypt,
    encrypt,
    find_icon,
    find_suitable_tmp_dir,
    force_decode,
    grouper,
    if_frozen,
    safe_filename,
    safe_long_path,
    set_path_readonly,
    unset_path_readonly,
)
from .activity import Action, FileAction
from .processor import Processor
from .queue_manager import QueueManager
from .watcher.local_watcher import LocalWatcher
from .watcher.remote_watcher import RemoteWatcher
from .workers import Worker

if TYPE_CHECKING:
    from ..manager import Manager  # noqa

__all__ = ("Engine", "ServerBindingSettings")

log = getLogger(__name__)


class Engine(QObject):
    """Used for threads interaction."""

    started = pyqtSignal()
    _stop = pyqtSignal()
    _scanPair = pyqtSignal(str)
    errorOpenedFile = pyqtSignal(object)
    longPathError = pyqtSignal(object)
    syncStarted = pyqtSignal(object)
    syncCompleted = pyqtSignal()
    # Sent when files are in error but the rest is OK
    syncPartialCompleted = pyqtSignal()
    syncSuspended = pyqtSignal()
    syncResumed = pyqtSignal()
    rootDeleted = pyqtSignal()
    rootMoved = pyqtSignal(Path)
    docDeleted = pyqtSignal(Path)
    fileAlreadyExists = pyqtSignal(Path, Path)
    uiChanged = pyqtSignal(str)
    authChanged = pyqtSignal(str)
    noSpaceLeftOnDevice = pyqtSignal()
    invalidAuthentication = pyqtSignal()
    newConflict = pyqtSignal(object)
    newReadonly = pyqtSignal(object, object)
    deleteReadonly = pyqtSignal(object)
    newLocked = pyqtSignal(object, object, object)
    newSyncStarted = pyqtSignal(object)
    newSyncEnded = pyqtSignal(object)
    newError = pyqtSignal(object)
    newQueueItem = pyqtSignal(object)
    offline = pyqtSignal()
    online = pyqtSignal()

    # Direct Transfer
    directTranferError = pyqtSignal(Path)
    directTransferSessionFinished = pyqtSignal(str, str, str)

    type = "NXDRIVE"
    # Folder locker - LocalFolder processor can prevent
    # others processors to operate on a folder
    _folder_lock: Optional[Path] = None

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
        super().__init__()

        self.version = manager.version
        self.remote: Remote = None  # type: ignore
        self._remote_token: Token = None  # type: ignore

        self.remote_cls = remote_cls
        self.local_cls = local_cls
        self.download_dir: Path = ROOT

        # Initialize those attributes first to be sure .stop()
        # can be called without missing ones
        self._threads: List[QThread] = []

        # Stop if invalid credentials
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
        # Pause if in debug
        self._pause: bool = Options.debug
        self._sync_started = False
        self._invalid_credentials = False
        self._offline_state = False
        self.dao = EngineDAO(self._get_db_file())

        # The password is only set when binding an account for the 1st time,
        # then only the token will be available and used
        self._remote_password: str = ""

        if binder:
            try:
                self.bind(binder)
            except Exception:
                # Unlock the database for its removal from the Manager
                # (especially blocker on Windows which forbids the deletion)
                self.dispose_db()
                raise

        self._load_configuration()

        self.download_dir = self._set_download_dir()
        self.csv_dir = self._set_csv_dir_or_cleanup()

        if not binder:
            self._setup_local_folder(not Options.nofscheck)
            if not self.server_url:
                raise EngineInitError(self)
            self._check_https()
            self.remote = self.init_remote()

        self._create_queue_manager()
        if Feature.synchronization:
            self._create_remote_watcher()
            self._create_local_watcher()

        # Connect for sync start
        self.newQueueItem.connect(self._check_sync_start)

        # Some conflict can be resolved automatically
        self.dao.newConflict.connect(self.conflict_resolver)

        self._set_root_icon()
        self._user_cache: Dict[str, str] = {}

        # Pause in case of no more space on the device
        self.noSpaceLeftOnDevice.connect(self.suspend)

        # Will manage Runners
        self._threadpool = QThreadPool().globalInstance()

        self._send_roots_metrics()

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} "
            f"name={self.name!r}, "
            f"server_url={self.server_url!r}, "
            f"has_token={bool(self._remote_token)!r}, "
            f"is_offline={self.is_offline()!r}, "
            f"uid={self.uid!r}, "
            f"type={self.type!r}>"
        )

    def export(self) -> Dict[str, Any]:
        bind = self.get_binder()
        return {
            "uid": self.uid,
            "type": self.type,
            "name": self.name,
            "offline": self.is_offline(),
            "metrics": self.get_metrics(),
            "started": self.is_started(),
            "syncing": self.is_syncing(),
            "paused": self.is_paused(),
            "local_folder": str(self.local_folder),
            "queue": self.queue_manager.get_metrics(),
            "web_authentication": bind.web_authentication,
            "server_url": bind.server_url,
            "default_ui": self.wui,
            "ui": self.force_ui or self.wui,
            "username": bind.username,
            "need_password_update": bind.pwd_update_required,
            "initialized": bind.initialized,
            "server_version": bind.server_version,
            "threads": self._get_threads(),
        }

    def _create_queue_manager(self) -> None:
        kwargs = {"max_file_processors": 2 if Options.debug else self._proc_count}
        self.queue_manager: QueueManager = QueueManager(self, self.dao, **kwargs)

        # Connect for sync start
        self.queue_manager.newItem.connect(self._check_sync_start)

        # Connect components signals to engine signals
        self.queue_manager.newItem.connect(self.newQueueItem)
        self.queue_manager.newErrorGiveUp.connect(self.newError)

        if not Feature.synchronization:
            # Launch queue processors when the Engine started
            self.started.connect(self.queue_manager.init_processors)

    def _create_local_watcher(self) -> None:
        self._local_watcher = LocalWatcher(self, self.dao)
        self.create_thread(self._local_watcher, "LocalWatcher")

        # Launch the Remote Watcher after first local scan
        self._local_watcher.localScanFinished.connect(self._remote_watcher.run)

        # Other signals
        self._local_watcher.rootDeleted.connect(self.rootDeleted)
        self._local_watcher.rootMoved.connect(self.rootMoved)
        self._local_watcher.docDeleted.connect(self.docDeleted)
        self._local_watcher.fileAlreadyExists.connect(self.fileAlreadyExists)

    def _create_remote_watcher(self) -> None:
        self._remote_watcher = RemoteWatcher(self, self.dao)
        self.create_thread(self._remote_watcher, "RemoteWatcher", start_connect=False)

        # Launch queue processors after first remote_watcher pass
        self._remote_watcher.initiate.connect(self.queue_manager.init_processors)
        self._remote_watcher.remoteWatcherStopped.connect(
            self.queue_manager.shutdown_processors
        )

        # Connect last_sync checked
        self._remote_watcher.updated.connect(self._check_last_sync)

        # Scan in remote_watcher thread
        self._scanPair.connect(self._remote_watcher.scan_pair)

    def _get_threads(self) -> List[Dict[str, Any]]:
        return [thread.worker.export() for thread in self._threads]

    @pyqtSlot(object)
    def _check_sync_start(self, *, row_id: str = None) -> None:
        if not self._sync_started:
            queue_size = self.queue_manager.get_overall_size()
            if queue_size > 0:
                self._sync_started = True
                self.syncStarted.emit(queue_size)

    def reinit(self) -> None:
        started = not self._stopped
        if started:
            self.stop()
        if Feature.synchronization:
            self.dao.reinit_states()
            self._check_root()
        self.download_dir = self._set_download_dir()
        if started:
            self.start()

    def send_metric(self, category: str, action: str, label: str, /) -> None:
        self.manager.tracker.send_metric(category, action, label)  # type: ignore

    def stop_processor_on(self, path: Path, /) -> None:
        for worker in self.queue_manager.get_processors_on(path):
            log.debug(
                f"Quitting processor: {worker!r} as requested to stop on {path!r}"
            )
            worker.quit()

    def _set_download_dir(self) -> Path:
        """Guess a good location for a download folder."""
        if self.download_dir is not ROOT and self.download_dir.is_dir():
            return self.download_dir

        download_dir = find_suitable_tmp_dir(self.local_folder, self.manager.home)
        download_dir = safe_long_path(download_dir) / ".tmp" / self.uid
        log.info(f"Using temporary download folder {download_dir!r}")
        download_dir.mkdir(parents=True, exist_ok=True)

        # Update the LocalClient attribute as it is needed by .rename()
        self.local.download_dir = download_dir

        return download_dir

    def _set_csv_dir_or_cleanup(self) -> Path:
        """
        Create the CSV dir if not already exist.
        Otherwise cleanup old tmp CSV files.
        """
        csv_dir = safe_long_path(self.manager.home) / "csv"
        if csv_dir.is_dir():
            log.info(f"Cleaning CSV folder {csv_dir!r}")
            tmp_files = csv_dir.glob("*.tmp")
            for tmp in tmp_files:
                tmp.unlink()
        else:
            log.info(f"Creating CSV folder {csv_dir!r}")
            csv_dir.mkdir()
        return csv_dir

    def set_local_folder(self, path: Path, /) -> None:
        log.info(f"Update local folder to {path!r}")
        self.local_folder = path
        self._local_watcher.stop()
        self._create_local_watcher()
        self.manager.update_engine_path(self.uid, path)

    def set_local_folder_lock(self, path: Path, /) -> None:
        self._folder_lock = path
        # Check for each processor
        log.info(f"Local Folder locking on {path!r}")
        while self.queue_manager.has_file_processors_on(path):
            log.debug("Local folder locking wait for file processor to finish")
            sleep(1)
        log.info(f"Local Folder lock setup completed on {path!r}")

    def set_ui(self, value: str, /, *, overwrite: bool = True) -> None:
        name = ("wui", "force_ui")[overwrite]
        if getattr(self, name, "") == value:
            return

        key_name = ("force_ui", "ui")[name == "wui"]
        self.dao.update_config(key_name, value)
        setattr(self, name, value)
        log.info(f"{name} preferences set to {value}")
        self.uiChanged.emit(self.uid)

    def release_folder_lock(self) -> None:
        log.info("Local Folder unlocking")
        self._folder_lock = None

    def set_offline(self, *, value: bool = True) -> None:
        if value == self._offline_state:
            return

        self._offline_state = value
        if value:
            log.info(f"Engine {self.uid} goes offline")
            self.queue_manager.suspend()
            self.offline.emit()
        else:
            log.info(f"Engine {self.uid} goes online")
            self.queue_manager.resume()
            self.online.emit()

    def is_offline(self) -> bool:
        return self._offline_state

    def add_filter(self, path: str, /) -> None:
        remote_ref = os.path.basename(path)
        remote_parent_path = os.path.dirname(path)
        if not remote_ref:
            return
        self.dao.add_filter(path)
        pair = self.dao.get_state_from_remote_with_path(remote_ref, remote_parent_path)
        if not pair:
            log.info(f"Cannot find the pair: {remote_ref} ({remote_parent_path!r})")
            return
        self.dao.delete_remote_state(pair)

    def remove_filter(self, path: str, /) -> None:
        self.dao.remove_filter(path)
        # Scan the "new" pair, use signal/slot to not block UI
        self._scanPair.emit(path)

    def delete_doc(self, path: Path, /, *, mode: DelAction = None) -> None:
        """Delete doc after prompting the user for the mode."""

        doc_pair = self.dao.get_state_from_local(path)
        if not doc_pair:
            log.info(f"Unable to delete non-existent doc {path}")
            return

        # In case the deleted path is not synced, there is no
        # need to ask the user what to do.
        if doc_pair.remote_state == "unknown":
            self.dao.remove_state(doc_pair)
            return

        if not mode:
            mode = self.manager.get_deletion_behavior()

        if mode is DelAction.DEL_SERVER:
            # Delete on server
            doc_pair.update_state("deleted", doc_pair.remote_state)
            self.dao.delete_local_state(doc_pair)
        elif mode is DelAction.UNSYNC:
            # Add document to filters
            self.dao.remove_state(doc_pair)
            if doc_pair.remote_parent_path and doc_pair.remote_ref:
                self.dao.add_filter(
                    f"{doc_pair.remote_parent_path}/{doc_pair.remote_ref}"
                )

    def _save_last_dt_session_infos(
        self,
        remote_path: str,
        remote_ref: str,
        remote_title: str,
        duplicate_behavior: str,
        last_local_selected_location: Optional[Path],
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

    def _create_remote_folder(
        self, remote_parent_path: str, new_folder: str, session_id: int, /
    ) -> Dict[str, Any]:
        try:
            return self.remote.upload_folder(
                remote_parent_path,
                {"title": new_folder},
                headers={DT_NEW_FOLDER: 1, DT_SESSION_NUMBER: session_id},
            )
        except Exception:
            log.warning(
                f"Could not create the {new_folder!r} folder in the {remote_parent_path!r} remote folder",
                exc_info=True,
            )
            self.directTranferError.emit(PurePath(remote_parent_path, new_folder))
            return {}

    def _direct_transfer(
        self,
        local_paths: Dict[Path, int],
        remote_parent_path: str,
        remote_parent_ref: str,
        remote_parent_title: str,
        /,
        *,
        duplicate_behavior: str = "create",
        last_local_selected_location: Optional[Path] = None,
        new_folder: Optional[str] = None,
    ) -> None:
        """Plan the Direct Transfer."""

        # Save last dt session infos for next times
        self._save_last_dt_session_infos(
            remote_parent_path,
            remote_parent_ref,
            remote_parent_title,
            duplicate_behavior,
            last_local_selected_location,
        )
        if new_folder:
            self.send_metric("direct_transfer", "new_folder", "1")
            expected_session_uid = self.dao.get_count("uid != 0", table="Sessions") + 1
            item = self._create_remote_folder(
                remote_parent_path, new_folder, expected_session_uid
            )
            if not item:
                return
            remote_parent_path = item["path"]
            remote_parent_ref = item["uid"]

        # Allow to only create a folder and return.
        if not local_paths:
            return

        all_paths = local_paths.keys()
        items = [
            (
                path.as_posix(),
                path.parent.as_posix(),
                path.name,
                path.is_dir(),
                size,
                remote_parent_path,
                remote_parent_ref,
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
        # Read https://jira.nuxeo.com/secure/EditComment!default.jspa?id=152399&commentId=503487
        # for why we can't have metrics about dupes creation on uploads.

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
        new_folder: Optional[str] = None,
    ) -> None:
        """Plan the Direct Transfer."""
        self._direct_transfer(
            local_paths,
            remote_parent_path,
            remote_parent_ref,
            remote_parent_title,
            duplicate_behavior=duplicate_behavior,
            last_local_selected_location=last_local_selected_location,
            new_folder=new_folder,
        )

    def direct_transfer_async(
        self,
        local_paths: Dict[Path, int],
        remote_parent_path: str,
        remote_parent_ref: str,
        remote_parent_title: str,
        /,
        *,
        duplicate_behavior: str = "create",
        last_local_selected_location: Optional[Path] = None,
        new_folder: Optional[str] = None,
    ) -> None:
        """Plan the Direct Transfer. Async to not freeze the GUI."""
        from .workers import Runner

        runner = Runner(
            self._direct_transfer,
            local_paths,
            remote_parent_path,
            remote_parent_ref,
            remote_parent_title,
            duplicate_behavior=duplicate_behavior,
            last_local_selected_location=last_local_selected_location,
            new_folder=new_folder,
        )
        self._threadpool.start(runner)

    def rollback_delete(self, path: Path, /) -> None:
        """Re-synchronize a document when a deletion is cancelled."""
        doc_pair = self.dao.get_state_from_local(path)
        if not doc_pair:
            log.info(f"Unable to rollback delete on non-existent doc {path}")
            return
        if doc_pair.folderish:
            self.dao.remove_state_children(doc_pair)
        self.dao.force_remote_creation(doc_pair)
        if doc_pair.folderish:
            self._remote_watcher.scan_remote(from_state=doc_pair)

    def get_metadata_url(self, remote_ref: str, /, *, edit: bool = False) -> str:
        """
        Build the document's metadata URL based on the server's UI.
        Default is Web-UI.  In case of unknown UI, use the default value.

        :param remote_ref: The document remote reference (UID) of the
            document we want to show metadata.
        :param edit: Show the metadata edit page instead of the document.
        :return: The complete URL.
        """
        uid = remote_ref.split("#")[-1]
        repo = self.remote.client.repository
        page = ("view_documents", "view_drive_metadata")[edit]

        urls = {
            "jsf": f"{self.server_url}nxdoc/{repo}/{uid}/{page}",
            "web": f"{self.server_url}ui#!/doc/{uid}",
        }
        return urls[self.force_ui or self.wui]

    def is_syncing(self) -> bool:
        return self._sync_started

    def is_paused(self) -> bool:
        return self._pause

    def open_edit(self, remote_ref: str, remote_name: str, /) -> None:
        doc_ref = remote_ref
        if "#" in doc_ref:
            doc_ref = doc_ref[doc_ref.rfind("#") + 1 :]
        log.info(f"Will try to open edit : {doc_ref}")
        # TODO Implement a TemporaryWorker

        def run() -> None:
            self.manager.directEdit.emit(
                self.server_url, doc_ref, self.remote_user, None
            )

        self._edit_thread = Thread(target=run)
        self._edit_thread.start()

    def open_remote(self, *, url: str = None) -> None:
        if url is None:
            url = self.server_url
        self.manager.open_local_file(url)

    def resume(self) -> None:
        log.info(f"Engine {self.uid} is resuming")
        self._pause = False

        # If stopped then start the engine
        if self._stopped:
            self.start()
            return

        self.queue_manager.resume()
        for thread in self._threads:
            if thread.isRunning():
                thread.worker.resume()
            else:
                thread.start()
        self.resume_suspended_transfers()
        self.syncResumed.emit()

    def _resume_transfers(
        self, nature: str, func: Callable, /, *, is_direct_transfer: bool = False
    ) -> None:
        """Resume all transfers returned by the *func* function."""
        resume = self.dao.resume_transfer
        get_state = self.dao.get_state_from_id

        transfers = func()
        if not isinstance(transfers, list):
            transfers = [transfers]

        for transfer in transfers:
            if transfer.uid is None:
                continue

            resume(nature, transfer.uid, is_direct_transfer=is_direct_transfer)

            doc_pair = get_state(transfer.doc_pair)
            if doc_pair:
                self.queue_manager.push(doc_pair)

    def resume_transfer(
        self, nature: str, uid: int, /, *, is_direct_transfer: bool = False
    ) -> None:
        """Resume a single transfer with its nature and UID."""
        meth = (
            self.dao.get_download
            if nature == "download"
            else self.dao.get_dt_upload
            if is_direct_transfer
            else self.dao.get_upload
        )
        func = partial(meth, uid=uid)  # type: ignore
        self._resume_transfers(nature, func, is_direct_transfer=is_direct_transfer)

    def resume_suspended_transfers(self) -> None:
        """Resume all suspended transfers."""
        dao = self.dao
        status = TransferStatus.SUSPENDED

        self._resume_transfers(
            "download", partial(dao.get_downloads_with_status, status)
        )
        self._resume_transfers("upload", partial(dao.get_uploads_with_status, status))
        self._resume_transfers(
            "upload",
            partial(dao.get_dt_uploads_with_status, status),
            is_direct_transfer=True,
        )

        # Update the systray icon and syncing count in the systray, if there are any resumed transfers
        self._check_sync_start()

    def resume_session(self, uid: int, /) -> None:
        """Resume all transfers for given session."""
        self.dao.change_session_status(uid, TransferStatus.ONGOING)
        self.dao.resume_session(uid)

    def _manage_staled_transfers(self) -> None:
        """
        That method manages staled transfers. A staled transfer has the ONGOING status.

        Normally, this status cannot be if the application was correctly shut down.
        In that case, such transfers will be purged. This likely mean there was an error somewhere and
        the transfer will unlikely being able to resume.

        On the other end, if the application effectively crashed at the previous run,
        such transfers should be adapted to being able to resume.
        """

        app_has_crashed = State.has_crashed
        dao = self.dao

        for nature in ("download", "upload"):
            meth = getattr(dao, f"get_{nature}s_with_status")
            for transfer in meth(TransferStatus.ONGOING):
                if app_has_crashed:
                    # Update the status to let .resume_suspended_transfers() processing it
                    transfer.status = TransferStatus.SUSPENDED
                    dao.set_transfer_status(nature, transfer)
                    log.info(f"Updated status of staled {transfer}")
                else:
                    # Remove staled transfers
                    is_direct_transfer = (
                        nature == "upload" and transfer.is_direct_transfer
                    )
                    dao.remove_transfer(
                        nature,
                        path=transfer.path,
                        is_direct_transfer=is_direct_transfer,
                    )
                    log.info(f"Removed staled {transfer}")

    def cancel_upload(self, transfer_uid: int, /) -> None:
        """Cancel an ongoing Direct Transfer upload and clean the database."""
        log.debug(f"Canceling transfer {transfer_uid}")
        upload = self.dao.get_dt_upload(uid=transfer_uid)
        if not upload:
            return

        doc_pair = self.dao.get_state_from_local(upload.path)
        if not doc_pair:
            return

        # The Upload is currently being processed by a thread.
        # We need to make the thread stop before cancelling the ongoing upload.
        if upload.status is TransferStatus.ONGOING and doc_pair.processor:
            # The CANCELLED status will trigger an exception in the thread that will remove the upload.
            upload.status = TransferStatus.CANCELLED
            self.dao.set_transfer_status("upload", upload)
            return

        # The Upload is not ONGOING so we can remove it safely.
        self.remote.cancel_batch(upload.batch)
        self.dao.remove_transfer("upload", path=upload.path, is_direct_transfer=True)

        self.dao.remove_state(doc_pair)
        session = self.dao.decrease_session_counts(doc_pair.session)
        self.handle_session_status(session)

    def cancel_session(self, uid: int, /) -> None:
        """Cancel all transfers for given session."""
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

        # We could cancel all batches, but in reality it would freeze the GUI.
        # Cancelling a session with a lot of items is worthless the use of a specific thread
        # to do the clean-up ourselves. Let the server doing it for us. We will be able to
        # tackle a possible issue in time.
        # for batch in self.dao.cancel_session(uid):
        #     self.remote.cancel_batch(batch)

    def suspend(self) -> None:
        if self._pause:
            return

        log.info(f"Engine {self.uid} is suspending")
        self._pause = True
        self.dao.suspend_transfers()
        self.queue_manager.suspend()
        for thread in self._threads:
            thread.worker.suspend()
        self.syncSuspended.emit()

    def unbind(self) -> None:
        self.stop()
        self.manager.osi.unwatch_folder(self.local_folder)
        self.manager.osi.unregister_folder_link(self.local_folder)
        self.dispose_db()
        self.manager.remove_engine_dbs(self.uid)

        try:
            shutil.rmtree(self.download_dir)
        except FileNotFoundError:
            # Folder already removed
            pass
        except OSError:
            log.warning("Download folder removal error", exc_info=True)

        if self.remote:
            self.remote.revoke_token()

    def check_fs_marker(self) -> bool:
        tag, tag_value = "drive-fs-test", "NXDRIVE_VERIFICATION"
        if not self.local_folder.is_dir():
            self.rootDeleted.emit()
            return False

        self.local.set_remote_id(ROOT, tag_value, name=tag)
        if self.local.get_remote_id(ROOT, name=tag) != tag_value:
            return False

        self.local.remove_remote_id(ROOT, name=tag)
        return not bool(self.local.get_remote_id(ROOT, name=tag))

    @staticmethod
    def _normalize_url(url: str, /) -> str:
        """Ensure that user provided url always has a trailing '/'"""
        if not url:
            raise ValueError(f"Invalid url: {url!r}")
        if not url.endswith("/"):
            return url + "/"
        return url

    def _send_roots_metrics(self) -> None:
        """Send a metric about the number of locally enabled sync roots."""
        if not self.remote or not Feature.synchronization:
            return
        roots_count = self.dao.get_count(f"remote_parent_path = '{SYNC_ROOT}'")
        self.remote.metrics.send({SYNC_ROOT_COUNT: roots_count})

    def _load_token(self) -> Token:
        """Retrieve the token from the database."""
        stored_token = self.dao.get_config("remote_token")
        key = f"{self.remote_user}{self.server_url}"
        try:
            clear_token = force_decode(decrypt(stored_token, key))
        except UnicodeDecodeError:
            clear_token = stored_token
        try:
            # OAuth2 token
            res: Token = json.loads(clear_token)
        except (TypeError, json.JSONDecodeError):
            # Nuxeo token
            res = clear_token

        # Ensure the token is saved chiphered
        if stored_token == clear_token:
            log.info("Removing clear token from the database")
            self._save_token(clear_token)

        return res

    def _save_token(self, token: Token) -> None:
        """Store the token into the database."""
        if not token:
            return
        stored_token = json.dumps(token) if isinstance(token, dict) else token
        key = f"{self.remote_user}{self.server_url}"
        secure_token = encrypt(stored_token, key)
        self.dao.update_config("remote_token", secure_token)

    def _load_configuration(self) -> None:
        self._web_authentication = self.dao.get_bool("web_authentication")
        self.server_url = self.dao.get_config("server_url")
        self.hostname = urlsplit(self.server_url).hostname
        self.wui = self.dao.get_config("ui", default="web")
        self.force_ui = self.dao.get_config("force_ui")
        self.remote_user = self.dao.get_config("remote_user")
        self._remote_token = self._load_token()
        self._ssl_verify = self.dao.get_bool("ssl_verify", default=True)
        if Options.ssl_no_verify:
            self._ssl_verify = False
        self._ca_bundle = Options.ca_bundle or self.dao.get_config("ca_bundle")
        self._client_certificate = client_certificate()

        if not self._remote_token:
            self.set_invalid_credentials(
                reason="found no token in engine configuration"
            )

    def _get_db_file(self) -> Path:
        return self.manager.get_engine_db(self.uid)

    def get_binder(self) -> "ServerBindingSettings":
        return ServerBindingSettings(
            self.server_url,
            self._web_authentication,
            self.remote_user,
            self.local_folder,
            True,
            pwd_update_required=self.has_invalid_credentials(),
        )

    def set_invalid_credentials(
        self, *, value: bool = True, reason: str = None
    ) -> None:
        changed = self._invalid_credentials is not value
        self._invalid_credentials = value
        if not changed:
            return
        if value:
            msg = "Setting invalid credentials"
            if reason:
                msg += f", reason is: {reason}"
            log.warning(msg)
            self.invalidAuthentication.emit()
        self.authChanged.emit(self.uid)

    def has_invalid_credentials(self) -> bool:
        return self._invalid_credentials

    @property
    def have_folder_upload(self) -> bool:
        """Check if the server can handle folder upload via the FileManager."""
        value = self.dao.get_bool("have_folder_upload", default=False)
        if not value:
            value = self.remote.can_use("FileManager.CreateFolder")
            if value:
                self.dao.store_bool("have_folder_upload", True)
        return value

    @staticmethod
    def local_rollback(*, force: bool = False) -> bool:
        """
        :param force: Force the return value to be the one of `force`.
        """

        if isinstance(force, bool):
            return force
        return False

    def create_thread(
        self, worker: Worker, name: str, /, *, start_connect: bool = True
    ) -> QThread:
        if worker is None:
            worker = Worker(self, name=name)

        if isinstance(worker, Processor):
            worker.pairSyncStarted.connect(self.newSyncStarted)
            worker.pairSyncEnded.connect(self.newSyncEnded)

        thread = worker.thread
        if start_connect:
            thread.started.connect(worker.run)
        self._stop.connect(worker.quit)
        thread.finished.connect(self._thread_finished)
        self._threads.append(thread)
        return thread

    def retry_pair(self, row_id: int, /) -> None:
        state = self.dao.get_state_from_id(row_id)
        if state is None:
            return
        self.dao.reset_error(state)

    def ignore_pair(self, row_id: int, reason: str, /) -> None:
        state = self.dao.get_state_from_id(row_id)
        if state is None:
            return
        self.dao.unsynchronize_state(state, reason, ignore=True)
        self.dao.reset_error(state, last_error=reason)

    def resolve_with_local(self, row_id: int, /) -> None:
        row = self.dao.get_state_from_id(row_id)
        if row:
            self.dao.force_local(row)

    def resolve_with_remote(self, row_id: int, /) -> None:
        row = self.dao.get_state_from_id(row_id)
        if row:
            self.dao.force_remote(row)

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
            self.dao.update_config("last_sync_date", datetime.datetime.utcnow())
            log.debug(f"Emitting syncCompleted for engine {self.uid}")
            self._sync_started = False
            self.syncCompleted.emit()

    def _thread_finished(self) -> None:
        for thread in self._threads:
            with suppress(AttributeError):
                if thread in (self._local_watcher.thread, self._remote_watcher.thread):
                    continue
            if thread.isFinished():
                thread.quit()
                self._threads.remove(thread)

    def is_started(self) -> bool:
        return not self._stopped

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

    def get_metrics(self) -> Metrics:
        return {
            "uid": self.uid,
            "conflicted_files": self.dao.get_conflict_count(),
            "error_files": self.dao.get_error_count(),
            "files_size": self.dao.get_global_size(),
            "invalid_credentials": self._invalid_credentials,
            "sync_files": self.dao.get_sync_count(filetype="file"),
            "sync_folders": self.dao.get_sync_count(filetype="folder"),
            "syncing": self.dao.get_syncing_count(),
            "unsynchronized_files": self.dao.get_unsynchronized_count(),
        }

    def get_conflicts(self) -> DocPairs:
        return self.dao.get_conflicts()

    def conflict_resolver(self, row_id: int, /, *, emit: bool = True) -> None:
        pair = self.dao.get_state_from_id(row_id)
        if not pair:
            log.debug("Conflict resolver: empty pair, skipping")
            return

        try:
            parent_ref = self.local.get_remote_id(pair.local_parent_path)
            same_digests = self.local.is_equal_digests(
                pair.local_digest, pair.remote_digest, pair.local_path
            )
            log.warning(
                "Conflict resolver: "
                f"names={pair.remote_name == pair.local_name!r}"
                f"({pair.remote_name!r}|{pair.local_name!r}) "
                f"digests={same_digests!r}"
                f"({pair.local_digest}|{pair.remote_digest}) "
                f"parents={pair.remote_parent_ref == parent_ref!r}"
                f"({pair.remote_parent_ref}|{parent_ref}) "
                f"[emit={emit!r}]"
            )
            if (
                same_digests
                and pair.remote_parent_ref == parent_ref
                and safe_filename(pair.remote_name) == pair.local_name
            ):
                self.dao.synchronize_state(pair)
            elif emit:
                # Raise conflict only if not resolvable
                self.newConflict.emit(row_id)
                self.manager.osi.send_sync_status(
                    pair, self.local.abspath(pair.local_path)
                )
        except ThreadInterrupt:
            # The engine has not yet started, just skip the exception as the conflict
            # is already seen by the user from within the systray menu and in the conflicts window.
            pass
        except UnknownDigest:
            log.info(
                f"Delaying conflict resolution of {pair!r} because of non-standard digest"
            )
        except Exception:
            log.exception("Conflict resolver error")

    def is_stopped(self) -> bool:
        return self._stopped

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

    def use_trash(self) -> bool:
        """Use the local trash mechanisms."""
        return self.local.can_use_trash()

    def update_token(self, token: Token, username: str, /) -> None:
        self._load_configuration()
        self._remote_token = token
        self.remote.update_token(token)
        self._save_token(self._remote_token)
        self.set_invalid_credentials(value=False)
        if username != self.remote_user:
            self.remote_user = username
            self.dao.update_config("remote_user", username)
            self.manager.restartNeeded.emit()
        else:
            self.start()

    def init_remote(self) -> Remote:
        # Used for FS synchronization operations
        args = (self.server_url, self.remote_user, self.manager.device_id, self.version)

        verify = self._ca_bundle
        if not (verify and self._ssl_verify):
            verify = self._ssl_verify

        kwargs = {
            "password": self._remote_password,
            "timeout": self.timeout,
            "token": self._remote_token,
            "download_callback": self.suspend_client,
            "upload_callback": self.suspend_client,
            "dao": self.dao,
            "proxy": self.manager.proxy,
            "verify": verify,
            "cert": self._client_certificate,
        }
        return self.remote_cls(*args, **kwargs)

    def _setup_local_folder(self, check_fs: bool) -> None:
        if not Feature.synchronization or not check_fs:
            return

        new_folder = not self.local_folder.is_dir()
        if new_folder:
            self.local_folder.mkdir(parents=True)
        try:
            self._check_fs(self.local_folder)
        except MissingXattrSupport as exc:
            if new_folder:
                with suppress(OSError):
                    self.local.unset_readonly(self.local_folder)
                    self.local_folder.rmdir()
            raise exc

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

        # Persist the user preference about the SSL behavior.
        # It can be tweaked via ca-bundle or ssl-no-verify options. But also
        # from the ponctual bypass-ssl window prompted at the account creation.
        self._ssl_verify = not Options.ssl_no_verify
        self._ca_bundle = Options.ca_bundle
        self._client_certificate = client_certificate()

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
        self.dao.store_bool("ssl_verify", self._ssl_verify)
        self.dao.update_config("ca_bundle", self._ca_bundle)

        # Check for the root
        # If the top level state for the server binding doesn't exist,
        # create the local folder and the top level state.
        self._check_root()

    def _check_fs(self, path: Path, /) -> None:
        if not self.check_fs_marker():
            raise MissingXattrSupport(path)

        if path.is_dir():
            root_id = self.local.get_root_id()
            if root_id:
                # server_url|user|device_id|uid
                server_url, user, *_ = root_id.split("|")
                if (self.server_url, self.remote_user) != (server_url, user):
                    raise RootAlreadyBindWithDifferentAccount(user, server_url)

    @if_frozen
    def _check_https(self) -> None:
        if self.server_url.startswith("https"):
            self.send_metric("server", "protocol", "https")
            return

        url = self.server_url.replace("http://", "https://")
        try:
            proxies = self.manager.proxy.settings(url=url)
            requests.get(url, proxies=proxies)
        except Exception:
            # No need to log the whole exception when using a development environment
            devenv = self.hostname.startswith(("127.0.0.1", "localhost", "192.168."))
            err = f"Server at {self.server_url!r} doesn't seem to handle HTTPS, keeping HTTP."
            if not devenv:
                err += " For information, this is the encountered SSL error:"
            log.warning(err, exc_info=not devenv)
            self.send_metric("server", "protocol", "http")
        else:
            self.server_url = url
            self.dao.update_config("server_url", self.server_url)
            log.info(f"Updated server URL to {self.server_url!r}")
            self.send_metric("server", "protocol", "http->https")

    def _check_root(self) -> None:
        if not Feature.synchronization:
            return

        root = self.dao.get_state_from_local(ROOT)
        if root is None:
            if self.local_folder.is_dir():
                unset_path_readonly(self.local_folder)
            else:
                self.local_folder.mkdir(parents=True)
            self._add_top_level_state()
            self._set_root_icon()
            self.manager.osi.register_folder_link(self.local_folder)
            set_path_readonly(self.local_folder)

    def cancel_action_on(self, pair_id: int, /) -> None:
        for thread in self._threads:
            if hasattr(thread, "worker") and isinstance(thread.worker, Processor):
                pair = thread.worker.get_current_pair()
                if pair is not None and pair.id == pair_id:
                    thread.worker.quit()

    @if_frozen
    def _set_root_icon(self) -> None:
        """Set the folder icon if not already done."""
        if self.local.has_folder_icon(ROOT):
            return

        if LINUX:
            icon = find_icon("emblem.svg")
        elif MAC:
            icon = find_icon("folder_mac.dat")
        else:
            icon = find_icon("folder_windows.ico")

        if not icon:
            log.error(f"Missing icon from the package: {icon!r}")
            return

        locker = self.local.unlock_ref(ROOT, unlock_parent=False)
        try:
            self.local.set_folder_icon(ROOT, icon)
        except Exception:
            log.warning("Icon folder cannot be set", exc_info=True)
        finally:
            self.local.lock_ref(ROOT, locker)

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

    def create_processor(self, item_getter: Callable, /) -> Processor:
        return Processor(self, item_getter)

    def dispose_db(self) -> None:
        if self.dao:
            self.dao.dispose()

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


@dataclass
class ServerBindingSettings:
    """Summarize server binding settings."""

    server_url: str
    web_authentication: bool
    username: str
    local_folder: Path
    initialized: bool
    server_version: Optional[str] = None
    password: Optional[str] = None
    pwd_update_required: bool = False
