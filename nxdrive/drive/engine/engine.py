"""Server-agnostic engine base class.

Provides the full sync-engine lifecycle (start / stop / suspend / resume),
queue management, transfer management, conflict resolution, folder setup,
and token persistence.  Server-specific behaviour (remote-client creation,
binding, root setup, Direct Transfer, etc.) is left to subclasses in the
``nuxeo/`` and ``alfresco/`` packages.
"""

import json
import os
import os.path
import shutil
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from logging import getLogger
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Type
from urllib.parse import urlsplit

import requests

from nxdrive.drive.auth import Token
from nxdrive.drive.client.local import LocalClient
from nxdrive.drive.client.local.base import LocalClientMixin
from nxdrive.drive.constants import LINUX, MAC, ROOT, DelAction, TransferStatus
from nxdrive.drive.dao.engine import EngineDAO
from nxdrive.drive.engine.queue_manager import QueueManager
from nxdrive.drive.engine.watcher.local_watcher import LocalWatcher
from nxdrive.drive.engine.workers import Worker
from nxdrive.drive.exceptions import (
    EngineInitError,
    MissingXattrSupport,
    RootAlreadyBindWithDifferentAccount,
    ThreadInterrupt,
    UnknownDigest,
)
from nxdrive.drive.feature import Feature
from nxdrive.drive.objects import Binder, DocPairs, EngineDef, Metrics, Session
from nxdrive.drive.options import Options
from nxdrive.drive.qt.imports import QObject, QThread, QThreadPool, pyqtSignal, pyqtSlot
from nxdrive.drive.state import State
from nxdrive.drive.utils import (
    decrypt,
    encrypt,
    find_icon,
    find_suitable_tmp_dir,
    force_decode,
    if_frozen,
    safe_filename,
    safe_long_path,
    set_path_readonly,
    unset_path_readonly,
)

if TYPE_CHECKING:
    from nxdrive.drive.manager import Manager  # noqa

__all__ = ("Engine", "ServerBindingSettings")

log = getLogger(__name__)


class Engine(QObject):
    """Server-agnostic sync engine base.

    Subclasses **must** override at least:
    - ``init_remote()``
    - ``bind()``
    - ``_create_remote_watcher()``
    - ``_add_top_level_state()``
    - ``create_processor()``
    """

    # ------------------------------------------------------------------ signals
    started = pyqtSignal()
    _stop = pyqtSignal()
    _scanPair = pyqtSignal(str)
    errorOpenedFile = pyqtSignal(object)
    longPathError = pyqtSignal(object)
    syncStarted = pyqtSignal(object)
    syncCompleted = pyqtSignal()
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

    # Direct Transfer (may not be used by all server types)
    directTranferError = pyqtSignal(Path)
    directTransferNewFolderError = pyqtSignal()
    directTransferNewFolderSuccess = pyqtSignal(str)
    directTransferSessionFinished = pyqtSignal(str, str, str)
    displayPendingTask = pyqtSignal(str, str, str, str)

    type = "NXDRIVE"
    _folder_lock: Optional[Path] = None

    # ------------------------------------------------------------------ __init__
    def __init__(
        self,
        manager: "Manager",
        definition: EngineDef,
        /,
        *,
        binder: Binder = None,
        processors: int = 10,
        remote_cls: type = None,
        local_cls: Type[LocalClientMixin] = LocalClient,
    ) -> None:
        super().__init__()

        self.version = manager.version
        self.remote: Any = None
        self._remote_token: Token = None  # type: ignore

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
            self._check_https()
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

        self._send_roots_metrics()

    # ------------------------------------------------------------------ repr / export
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
            "paused": self.is_paused(),
            "local_folder": str(self.local_folder),
            "queue": self.queue_manager.get_metrics(),
            "web_authentication": bind.web_authentication,
            "server_url": bind.server_url,
            "default_ui": self.wui,
            "ui": self.force_ui or self.wui,
            "username": bind.username,
            "need_password_update": bind.pwd_update_required,
            "server_version": bind.server_version,
            "threads": self._get_threads(),
        }

    # ------------------------------------------------------------------ queue / watcher / processor setup
    def _create_queue_manager(self) -> None:
        kwargs = {"max_file_processors": 2 if Options.debug else self._proc_count}
        self.queue_manager: QueueManager = QueueManager(self, self.dao, **kwargs)

        self.queue_manager.newItem.connect(self._check_sync_start)
        self.queue_manager.newItem.connect(self.newQueueItem)
        self.queue_manager.newErrorGiveUp.connect(self.newError)

        if not Feature.synchronization:
            self.started.connect(self.queue_manager.init_processors)

    def _create_local_watcher(self) -> None:
        self._local_watcher = LocalWatcher(self, self.dao)
        self.create_thread(self._local_watcher, "LocalWatcher")

        self._local_watcher.localScanFinished.connect(self._remote_watcher.run)

        self._local_watcher.rootDeleted.connect(self.rootDeleted)
        self._local_watcher.rootMoved.connect(self.rootMoved)
        self._local_watcher.docDeleted.connect(self.docDeleted)
        self._local_watcher.fileAlreadyExists.connect(self.fileAlreadyExists)

    def _create_remote_watcher(self) -> None:
        """Create the remote watcher.  **Must be overridden** by subclasses."""
        raise NotImplementedError

    # ------------------------------------------------------------------ extension points
    def init_remote(self) -> Any:
        """Create and return the remote client.  **Must be overridden.**"""
        raise NotImplementedError

    def bind(self, binder: Binder, /) -> None:
        """Bind this engine to a remote server.  **Must be overridden.**"""
        raise NotImplementedError

    def _add_top_level_state(self) -> None:
        """Insert the top-level sync root into the DAO.  **Must be overridden.**"""
        raise NotImplementedError

    def create_processor(self, item_getter: Callable, /) -> Any:
        """Return a new Processor instance.  **Must be overridden.**"""
        raise NotImplementedError

    def _send_roots_metrics(self) -> None:
        """Send sync-root metrics.  No-op by default."""

    @property
    def have_folder_upload(self) -> bool:
        """Whether the server supports folder upload.  Default True."""
        return True

    def suspend_client(self, uploader: Any = None, /) -> None:
        """Check whether the current processor thread should be interrupted."""
        if self.is_paused() or not self.is_started():
            raise ThreadInterrupt()

    # ------------------------------------------------------------------ threads & misc
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

    # ------------------------------------------------------------------ paths & directories
    def _set_download_dir(self) -> Path:
        if self.download_dir is not ROOT and self.download_dir.is_dir():
            return self.download_dir

        download_dir = find_suitable_tmp_dir(self.local_folder, self.manager.home)
        download_dir = safe_long_path(download_dir) / ".tmp" / self.uid
        log.info(f"Using temporary download folder {download_dir!r}")
        download_dir.mkdir(parents=True, exist_ok=True)

        self.local.download_dir = download_dir
        return download_dir

    def _set_csv_dir_or_cleanup(self) -> Path:
        csv_dir = safe_long_path(self.manager.home) / "csv"
        if csv_dir.is_dir():
            log.info(f"Cleaning CSV folder {csv_dir!r}")
            for tmp in csv_dir.glob("*.tmp"):
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

    # ------------------------------------------------------------------ online / offline
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

    # ------------------------------------------------------------------ filters
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
        self._scanPair.emit(path)

    # ------------------------------------------------------------------ document ops
    def delete_doc(self, path: Path, /, *, mode: DelAction = None) -> None:
        doc_pair = self.dao.get_state_from_local(path)
        if not doc_pair:
            log.info(f"Unable to delete non-existent doc {path}")
            return
        if doc_pair.remote_state == "unknown":
            self.dao.remove_state(doc_pair)
            return
        if not mode:
            mode = self.manager.get_deletion_behavior()
        if mode is DelAction.DEL_SERVER:
            doc_pair.update_state("deleted", doc_pair.remote_state)
            self.dao.delete_local_state(doc_pair)
        elif mode is DelAction.UNSYNC:
            self.dao.remove_state(doc_pair)
            if doc_pair.remote_parent_path and doc_pair.remote_ref:
                self.dao.add_filter(
                    f"{doc_pair.remote_parent_path}/{doc_pair.remote_ref}"
                )

    def rollback_delete(self, path: Path, /) -> None:
        doc_pair = self.dao.get_state_from_local(path)
        if not doc_pair:
            log.info(f"Unable to rollback delete on non-existent doc {path}")
            return
        if doc_pair.folderish:
            self.dao.remove_state_children(doc_pair)
        self.dao.force_remote_creation(doc_pair)
        if doc_pair.folderish:
            self._remote_watcher.scan_remote(from_state=doc_pair)

    # ------------------------------------------------------------------ sync state
    def is_syncing(self) -> bool:
        return self._sync_started

    def is_paused(self) -> bool:
        return self._pause

    def open_remote(self, *, url: str = None) -> None:
        if url is None:
            url = self.server_url
        self.manager.open_local_file(url)

    # ------------------------------------------------------------------ resume / suspend
    def resume(self) -> None:
        log.info(f"Engine {self.uid} is resuming")
        self._pause = False
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
        self._check_sync_start()

    def resume_session(self, uid: int, /) -> None:
        self.dao.change_session_status(uid, TransferStatus.ONGOING)
        self.dao.resume_session(uid)

    def _manage_staled_transfers(self) -> None:
        app_has_crashed = State.has_crashed
        dao = self.dao
        for nature in ("download", "upload"):
            meth = getattr(dao, f"get_{nature}s_with_status")
            for transfer in meth(TransferStatus.ONGOING):
                if app_has_crashed:
                    transfer.status = TransferStatus.SUSPENDED
                    dao.set_transfer_status(nature, transfer)
                    log.info(f"Updated status of staled {transfer}")
                else:
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
        log.debug(f"Canceling transfer {transfer_uid}")
        upload = self.dao.get_dt_upload(uid=transfer_uid)
        if not upload:
            return
        doc_pair = self.dao.get_state_from_local(upload.path)
        if not doc_pair:
            return
        if upload.status is TransferStatus.ONGOING and doc_pair.processor:
            upload.status = TransferStatus.CANCELLED
            self.dao.set_transfer_status("upload", upload)
            return
        self.remote.cancel_batch(upload.batch)
        self.dao.remove_transfer("upload", path=upload.path, is_direct_transfer=True)
        self.dao.remove_state(doc_pair)
        session = self.dao.decrease_session_counts(doc_pair.session)
        self.handle_session_status(session)

    def handle_session_status(self, session: Optional[Session], /) -> None:
        """Handle session lifecycle.  Override for metrics/notifications."""

    def cancel_session(self, uid: int, /) -> None:
        self.dao.change_session_status(uid, TransferStatus.CANCELLED)
        self.dao.cancel_session(uid)

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
            pass
        except OSError:
            log.warning("Download folder removal error", exc_info=True)
        if self.remote:
            self.remote.revoke_token()

    # ------------------------------------------------------------------ FS marker
    def check_fs_marker(self) -> bool:
        tag, tag_value = "drive-fs-test", "NXDRIVE_VERIFICATION"
        if not self.local_folder.is_dir():
            self.rootDeleted.emit()
            return False
        self.local.set_remote_id(ROOT, tag_value, name=tag)
        if self.local.get_remote_id(ROOT, name=tag) != tag_value:
            return False
        self.local.remove_remote_id(ROOT, name=tag)
        return True

    @staticmethod
    def _normalize_url(url: str, /) -> str:
        if not url.endswith("/"):
            url += "/"
        return url

    # ------------------------------------------------------------------ token persistence
    def _load_token(self) -> Token:
        stored_token = self.dao.get_config("remote_token")
        key = f"{self.remote_user}{self.server_url}"
        try:
            clear_token = force_decode(decrypt(stored_token, key))
        except UnicodeDecodeError:
            clear_token = stored_token
        try:
            res: Token = json.loads(clear_token)
        except (TypeError, json.JSONDecodeError):
            res = clear_token
        if stored_token == clear_token:
            log.info("Removing clear token from the database")
            self._save_token(clear_token)
        return res

    def _save_token(self, token: Token) -> None:
        if not token:
            return
        stored_token = json.dumps(token) if isinstance(token, dict) else token
        key = f"{self.remote_user}{self.server_url}"
        secure_token = force_decode(encrypt(stored_token, key))
        self.dao.update_config("remote_token", secure_token)

    def _load_configuration(self) -> None:
        self._web_authentication = self.dao.get_bool("web_authentication")
        self.server_url = self.dao.get_config("server_url")
        self.hostname = urlsplit(self.server_url).hostname if self.server_url else None
        self.wui = self.dao.get_config("ui", default="web")
        self.force_ui = self.dao.get_config("force_ui")
        self.remote_user = self.dao.get_config("remote_user")
        self._remote_token = self._load_token()
        if not self._remote_token:
            self.set_invalid_credentials(
                reason="found no token in engine configuration"
            )

    def _get_db_file(self) -> Path:
        return self.manager.get_engine_db(self.uid, self.type)

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

    @staticmethod
    def local_rollback(*, force: bool = False) -> bool:
        if isinstance(force, bool):
            return force
        return False

    # ------------------------------------------------------------------ threading
    def create_thread(
        self, worker: Worker, name: str, /, *, start_connect: bool = True
    ) -> QThread:
        if worker is None:
            worker = Worker(self, name=name)
        thread = worker.thread
        if start_connect:
            thread.started.connect(worker.run)
        self._stop.connect(worker.quit)
        thread.finished.connect(self._thread_finished)
        self._threads.append(thread)
        return thread

    # ------------------------------------------------------------------ conflict / retry / resolve
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
        log.info(
            f"Checking sync for engine {self.uid}: queue manager is {active_status} (size={qm_size}), "
            f"empty remote polls count is {empty_polls}, local watcher empty events is {empty_events}, "
            f"errors queue size is {errors} and syncing count is {self.dao.get_syncing_count()}"
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

    # ------------------------------------------------------------------ start / stop
    def start(self) -> None:
        log.info(f"Engine {self.uid} is starting")
        self._check_root()
        self.manager.server_config_updater.force_poll()
        self._manage_staled_transfers()
        self.resume_suspended_transfers()
        self._stopped = False
        for thread in self._threads:
            thread.start()
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
                self.newConflict.emit(row_id)
                self.manager.osi.send_sync_status(
                    pair, self.local.abspath(pair.local_path)
                )
        except ThreadInterrupt:
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
        self.dao.save_backup()
        if self.remote:
            log.debug("Sending all waiting async metrics.")
            self.remote.metrics.force_poll()
        self._stopped = True
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
        log.debug(f"Engine {self.uid} stopped")

    def use_trash(self) -> bool:
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

    # ------------------------------------------------------------------ local folder setup
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

    def _check_root(self) -> None:
        """Check/create the sync root.  Override for server-specific root setup."""
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

    def _check_fs(self, path: Path, /) -> None:
        if not self.check_fs_marker():
            raise MissingXattrSupport(path)
        if path.is_dir():
            root_id = self.local.get_root_id()
            if root_id:
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

    def cancel_action_on(self, pair_id: int, /) -> None:
        for thread in self._threads:
            if hasattr(thread, "worker"):
                pair = thread.worker.get_current_pair()
                if pair is not None and pair.id == pair_id:
                    thread.worker.quit()

    @if_frozen
    def _set_root_icon(self) -> None:
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

    def dispose_db(self) -> None:
        if self.dao:
            self.dao.dispose()


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
