# coding: utf-8
import datetime
import os
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from threading import Thread, current_thread
from time import sleep
from typing import Any, Callable, Dict, List, Optional, Type, TYPE_CHECKING
from urllib.parse import urlsplit

from dataclasses import dataclass
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from nuxeo.exceptions import HTTPError

from .activity import Action, FileAction
from .dao.sqlite import EngineDAO
from .processor import Processor
from .queue_manager import QueueManager
from .watcher.local_watcher import LocalWatcher
from .watcher.remote_watcher import RemoteWatcher
from .workers import Worker
from ..client.local_client import LocalClient
from ..client.remote_client import Remote
from ..constants import MAC, ROOT, WINDOWS, DelAction
from ..exceptions import (
    InvalidDriveException,
    PairInterrupt,
    RootAlreadyBindWithDifferentAccount,
    ThreadInterrupt,
)
from ..objects import DocPairs, Binder, Metrics, EngineDef
from ..options import Options
from ..utils import (
    find_icon,
    if_frozen,
    safe_filename,
    set_path_readonly,
    unset_path_readonly,
)

if TYPE_CHECKING:
    from ..manager import Manager  # noqa

__all__ = ("Engine", "ServerBindingSettings")

log = getLogger(__name__)


class FsMarkerException(Exception):
    pass


class Engine(QObject):
    """ Used for threads interaction. """

    _start = pyqtSignal()
    _stop = pyqtSignal()
    _scanPair = pyqtSignal(str)
    errorOpenedFile = pyqtSignal(object)
    longPathError = pyqtSignal(object)
    syncStarted = pyqtSignal(object)
    syncCompleted = pyqtSignal()
    # Sent when files are in blacklist but the rest is ok
    syncPartialCompleted = pyqtSignal()
    syncSuspended = pyqtSignal()
    syncResumed = pyqtSignal()
    rootDeleted = pyqtSignal()
    rootMoved = pyqtSignal(str)
    docDeleted = pyqtSignal(Path)
    fileAlreadyExists = pyqtSignal(Path, Path)
    uiChanged = pyqtSignal()
    authChanged = pyqtSignal()
    noSpaceLeftOnDevice = pyqtSignal()
    invalidAuthentication = pyqtSignal()
    newConflict = pyqtSignal(object)
    newReadonly = pyqtSignal(object, object)
    deleteReadonly = pyqtSignal(object)
    newLocked = pyqtSignal(object, object, object)
    newSync = pyqtSignal(object)
    newError = pyqtSignal(object)
    newQueueItem = pyqtSignal(object)
    offline = pyqtSignal()
    online = pyqtSignal()

    type = "NXDRIVE"
    # Folder locker - LocalFolder processor can prevent
    # others processors to operate on a folder
    _folder_lock: Optional[Path] = None

    def __init__(
        self,
        manager: "Manager",
        definition: EngineDef,
        binder: Binder = None,
        processors: int = 5,
        remote_cls: Type[Remote] = Remote,
        local_cls: Type[LocalClient] = LocalClient,
    ) -> None:
        super().__init__()

        self.version = manager.version

        self.remote_cls = remote_cls
        self.local_cls = local_cls

        # Initialize those attributes first to be sure .stop()
        # can be called without missing ones
        self._threads: List[QThread] = []

        # Stop if invalid credentials
        self.invalidAuthentication.connect(self.stop)
        self.timeout = Options.handshake_timeout
        self.manager = manager

        self.local_folder = Path(definition.local_folder)
        self.folder = str(self.local_folder)
        self.local = self.local_cls(self.local_folder)

        self.uid = definition.uid
        self.name = definition.name
        self._stopped = True
        self._pause = False
        self._sync_started = False
        self._invalid_credentials = False
        self._offline_state = False
        self._dao = EngineDAO(self._get_db_file())

        if binder:
            self.bind(binder)
        self._load_configuration()

        if not binder:
            self._check_https()
            self.remote = self.init_remote()

        self._local_watcher = self._create_local_watcher()
        self.create_thread(worker=self._local_watcher)
        self._remote_watcher = self._create_remote_watcher(Options.delay)
        self.create_thread(worker=self._remote_watcher, start_connect=False)

        # Launch remote_watcher after first local scan
        self._local_watcher.rootDeleted.connect(self.rootDeleted)
        self._local_watcher.rootMoved.connect(self.rootMoved)
        self._local_watcher.docDeleted.connect(self.docDeleted)
        self._local_watcher.localScanFinished.connect(self._remote_watcher.run)
        self._queue_manager = self._create_queue_manager(processors)

        self._local_watcher.fileAlreadyExists.connect(self.fileAlreadyExists)

        # Launch queue processors after first remote_watcher pass
        self._remote_watcher.initiate.connect(self._queue_manager.init_processors)
        self._remote_watcher.remoteWatcherStopped.connect(
            self._queue_manager.shutdown_processors
        )

        # Connect last_sync checked
        self._remote_watcher.updated.connect(self._check_last_sync)

        # Connect for sync start
        self.newQueueItem.connect(self._check_sync_start)
        self._queue_manager.newItem.connect(self._check_sync_start)

        # Connect components signals to engine signals
        self._queue_manager.newItem.connect(self.newQueueItem)
        self._queue_manager.newErrorGiveUp.connect(self.newError)

        # Some conflict can be resolved automatically
        self._dao.newConflict.connect(self.conflict_resolver)
        # Try to resolve conflict on startup
        for conflict in self._dao.get_conflicts():
            self.conflict_resolver(conflict.id, emit=False)

        # Scan in remote_watcher thread
        self._scanPair.connect(self._remote_watcher.scan_pair)

        self._set_root_icon()
        self._user_cache: Dict[str, str] = {}

        # Pause in case of no more space on the device
        self.noSpaceLeftOnDevice.connect(self.suspend)

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} "
            f"name={self.name!r}, offline={self._offline_state!r}, "
            f"uid={self.uid!r}, type={self.type!r}>"
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
            "queue": self.get_queue_manager().get_metrics(),
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

    def _get_threads(self) -> List[Dict[str, Any]]:
        result = []
        for thread in self.get_threads():
            result.append(thread.worker.export())
        return result

    @pyqtSlot(object)
    def _check_sync_start(self, row_id: str = None) -> None:
        if not self._sync_started:
            queue_size = self._queue_manager.get_overall_size()
            if queue_size > 0:
                self._sync_started = True
                self.syncStarted.emit(queue_size)

    def reinit(self) -> None:
        started = not self._stopped
        if started:
            self.stop()
        self._dao.reinit_states()
        self._check_root()
        if started:
            self.start()

    def stop_processor_on(self, path: Path) -> None:
        for worker in self.get_queue_manager().get_processors_on(path):
            log.debug(
                f"Quitting processor: {worker!r} as requested to stop on {path!r}"
            )
            worker.quit()

    def set_local_folder(self, path: Path) -> None:
        log.info(f"Update local folder to {path!r}")
        self.local_folder = path
        self._local_watcher.stop()
        self._create_local_watcher()
        self.manager.update_engine_path(self.uid, path)

    def set_local_folder_lock(self, path: Path) -> None:
        self._folder_lock = path
        # Check for each processor
        log.info(f"Local Folder locking on {path!r}")
        while self.get_queue_manager().has_file_processors_on(path):
            log.debug("Local folder locking wait for file processor to finish")
            sleep(1)
        log.info(f"Local Folder lock setup completed on {path!r}")

    def set_ui(self, value: str, overwrite: bool = True) -> None:
        name = ("wui", "force_ui")[overwrite]
        if getattr(self, name, "") == value:
            return

        key_name = ("force_ui", "ui")[name == "wui"]
        self._dao.update_config(key_name, value)
        setattr(self, name, value)
        log.info(f"{name} preferences set to {value}")
        self.uiChanged.emit()

    def release_folder_lock(self) -> None:
        log.info("Local Folder unlocking")
        self._folder_lock = None

    def get_last_files(
        self, number: int, direction: str = "", duration: int = None
    ) -> DocPairs:
        """ Return the last files transferred (see EngineDAO). """
        return self._dao.get_last_files(number, direction, duration)

    def get_last_files_count(self, direction: str = "", duration: int = None) -> int:
        """ Return the count of the last files transferred (see EngineDAO). """
        return self._dao.get_last_files_count(direction, duration)

    def set_offline(self, value: bool = True) -> None:
        if value == self._offline_state:
            return
        self._offline_state = value
        if value:
            log.info(f"Engine {self.uid} goes offline")
            self._queue_manager.suspend()
            self.offline.emit()
        else:
            log.info(f"Engine {self.uid} goes online")
            self._queue_manager.resume()
            self.online.emit()

    def is_offline(self) -> bool:
        return self._offline_state

    def add_filter(self, path: str) -> None:
        remote_ref = os.path.basename(path)
        remote_parent_path = os.path.dirname(path)
        if not remote_ref:
            return
        self._dao.add_filter(path)
        pair = self._dao.get_state_from_remote_with_path(remote_ref, remote_parent_path)
        if not pair:
            log.info(f"Cannot find the pair: {remote_ref} ({remote_parent_path!r})")
            return
        self._dao.delete_remote_state(pair)

    def remove_filter(self, path: str) -> None:
        self._dao.remove_filter(path)
        # Scan the "new" pair, use signal/slot to not block UI
        self._scanPair.emit(path)

    def delete_doc(self, path: Path, mode: DelAction = None) -> None:
        """ Delete doc after prompting the user for the mode. """
        if not mode:
            mode = self.manager.get_deletion_behavior()

        doc_pair = self._dao.get_state_from_local(path)
        if not doc_pair:
            log.info(f"Unable to delete non-existant doc {path}")
            return
        if mode is DelAction.DEL_SERVER:
            # Delete on server
            doc_pair.update_state("deleted", doc_pair.remote_state)
            if doc_pair.remote_state == "unknown":
                self._dao.remove_state(doc_pair)
            else:
                self._dao.delete_local_state(doc_pair)
        elif mode is DelAction.UNSYNC:
            # Add document to filters
            self._dao.remove_state(doc_pair)
            self._dao.add_filter(
                doc_pair.remote_parent_path + "/" + doc_pair.remote_ref
            )

    def rollback_delete(self, path: Path) -> None:
        """ Re-synchronize a document when a deletion is cancelled. """
        doc_pair = self._dao.get_state_from_local(path)
        if not doc_pair:
            log.info(f"Unable to rollback delete on non-existant doc {path}")
            return
        if doc_pair.folderish:
            self._dao.remove_state_children(doc_pair)
        self._dao.force_remote_creation(doc_pair)
        if doc_pair.folderish:
            self._remote_watcher._scan_remote(doc_pair)

    def get_metadata_url(self, remote_ref: str, edit: bool = False) -> str:
        """
        Build the document's metadata URL based on the server's UI.
        Default is Web-UI.  In case of unknown UI, use the default value.

        :param remote_ref: The document remote reference (UID) of the
            document we want to show metadata.
        :param edit: Show the metadata edit page instead of the document.
        :return: The complete URL.
        """

        _, repo, uid = remote_ref.split("#", 2)
        page = ("view_documents", "view_drive_metadata")[edit]
        token = self.get_remote_token()

        urls = {
            "jsf": f"{self.server_url}nxdoc/{repo}/{uid}/{page}?token={token}",
            "web": f"{self.server_url}ui?token={token}#!/doc/{uid}",
        }
        return urls[self.force_ui or self.wui]

    def get_remote_url(self) -> str:
        """
        Build the server's URL based on the server's UI.
        Default is Web-UI.  In case of unknown UI, use the default value.

        :return: The complete URL.
        """

        urls = {
            "jsf": (
                f"{self.server_url}nxhome/{Options.remote_repo}/@view_home?"
                "tabIds=USER_CENTER%3AuserCenterNuxeoDrive"
            ),
            "web": f"{self.server_url}ui?token={self.get_remote_token()}#!/drive",
        }
        return urls[self.force_ui or self.wui]

    def is_syncing(self) -> bool:
        return self._sync_started

    def is_paused(self) -> bool:
        return self._pause

    def open_edit(self, remote_ref: str, remote_name: str) -> None:
        doc_ref = remote_ref
        if "#" in doc_ref:
            doc_ref = doc_ref[doc_ref.rfind("#") + 1 :]
        log.info(f"Will try to open edit : {doc_ref}")
        # TODO Implement a TemporaryWorker

        def run():
            self.manager.direct_edit.edit(
                self.server_url, doc_ref, user=self.remote_user
            )

        self._edit_thread = Thread(target=run)
        self._edit_thread.start()

    def open_remote(self, url: str = None) -> None:
        if url is None:
            url = self.get_remote_url()
        self.manager.open_local_file(url)

    def resume(self) -> None:
        self._pause = False
        # If stopped then start the engine
        if self._stopped:
            self.start()
            return
        self._queue_manager.resume()
        for thread in self._threads:
            if thread.isRunning():
                thread.worker.resume()
            else:
                thread.start()
        self.syncResumed.emit()

    def suspend(self) -> None:
        if self._pause:
            return
        self._pause = True
        self._queue_manager.suspend()
        for thread in self._threads:
            thread.worker.suspend()
        self.syncSuspended.emit()

    def unbind(self) -> None:
        self.stop()
        try:
            if self.remote:
                self.remote.revoke_token()
        except HTTPError:
            # Token already revoked
            pass
        except:
            log.exception("Unbind error")

        self.manager.osi.unregister_folder_link(self.local_folder)

        self.dispose_db()
        try:
            os.remove(self._get_db_file())
        except OSError as exc:
            if exc.errno != 2:  # File not found, already removed
                log.exception("Database removal error")

    def check_fs_marker(self) -> bool:
        tag, tag_value = "drive-fs-test", b"NXDRIVE_VERIFICATION"
        if not self.local_folder.is_dir():
            self.rootDeleted.emit()
            return False

        self.local.set_remote_id(ROOT, tag_value, tag)
        if self.local.get_remote_id(ROOT, tag) != tag_value.decode("utf-8"):
            return False

        self.local.remove_remote_id(ROOT, tag)
        return not bool(self.local.get_remote_id(ROOT, tag))

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Ensure that user provided url always has a trailing '/'"""
        if not url:
            raise ValueError(f"Invalid url: {url!r}")
        if not url.endswith("/"):
            return url + "/"
        return url

    def _load_configuration(self) -> None:
        self._web_authentication = self._dao.get_bool("web_authentication")
        self.server_url = self._dao.get_config("server_url")
        self.hostname = urlsplit(self.server_url).hostname
        self.wui = self._dao.get_config("ui", default="jsf")
        self.force_ui = self._dao.get_config("force_ui")
        self.remote_user = self._dao.get_config("remote_user")
        self.account = f"{self.remote_user} • {self.name}"
        self._remote_password = self._dao.get_config("remote_password")
        self._remote_token = self._dao.get_config("remote_token")
        self._ssl_verify = self._dao.get_bool("ssl_verify", default=True)
        if Options.ssl_no_verify:
            self._ssl_verify = False
        self._ca_bundle = Options.ca_bundle or self._dao.get_config("ca_bundle")
        if self._remote_password is None and self._remote_token is None:
            self.set_invalid_credentials(
                reason="found no password nor token in engine configuration"
            )

    def get_remote_token(self) -> Optional[str]:
        return self._dao.get_config("remote_token")

    def _create_queue_manager(self, processors: int) -> QueueManager:
        kwargs = {"max_file_processors": 2 if Options.debug else processors}
        return QueueManager(self, self._dao, **kwargs)

    def _create_remote_watcher(self, delay: int) -> RemoteWatcher:
        return RemoteWatcher(self, self._dao, delay)

    def _create_local_watcher(self) -> LocalWatcher:
        return LocalWatcher(self, self._dao)

    def _get_db_file(self) -> Path:
        return self.manager.home / f"ndrive_{self.uid}.db"

    def get_binder(self) -> "ServerBindingSettings":
        return ServerBindingSettings(  # type: ignore
            self.server_url,
            self._web_authentication,
            self.remote_user,
            self.local_folder,
            True,
            pwd_update_required=self.has_invalid_credentials(),
        )

    def set_invalid_credentials(self, value: bool = True, reason: str = None) -> None:
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
        self.authChanged.emit()

    def has_invalid_credentials(self) -> bool:
        return self._invalid_credentials

    def get_queue_manager(self) -> QueueManager:
        return self._queue_manager

    def get_dao(self) -> EngineDAO:
        return self._dao

    @staticmethod
    def local_rollback(force: bool = False) -> bool:
        """
        :param force: Force the return value to be the one of `force`.
        """

        if isinstance(force, bool):
            return force
        return False

    def create_thread(
        self, worker: Worker = None, name: str = None, start_connect: bool = True
    ) -> QThread:
        if worker is None:
            worker = Worker(self, name=name)

        if isinstance(worker, Processor):
            worker.pairSync.connect(self.newSync)

        thread = worker.thread
        if start_connect:
            thread.started.connect(worker.run)
        self._stop.connect(worker.quit)
        thread.finished.connect(self._thread_finished)
        self._threads.append(thread)
        return thread

    def retry_pair(self, row_id: int) -> None:
        state = self._dao.get_state_from_id(row_id)
        if state is None:
            return
        self._dao.reset_error(state)

    def ignore_pair(self, row_id: int, reason: str = None) -> None:
        state = self._dao.get_state_from_id(row_id)
        if state is None:
            return
        self._dao.unsynchronize_state(state, last_error=reason, ignore=True)
        self._dao.reset_error(state, last_error=reason)

    def resolve_with_local(self, row_id: int) -> None:
        row = self._dao.get_state_from_id(row_id)
        if row:
            self._dao.force_local(row)

    def resolve_with_remote(self, row_id: int) -> None:
        row = self._dao.get_state_from_id(row_id)
        if row:
            self._dao.force_remote(row)

    @pyqtSlot()
    def _check_last_sync(self) -> None:
        if not self._sync_started:
            return

        watcher = self._local_watcher
        empty_events = watcher.empty_events()
        blacklist_size = self._queue_manager.get_errors_count()
        qm_size = self._queue_manager.get_overall_size()
        active_status = "active" if self._queue_manager.active() else "inactive"
        empty_polls = self._remote_watcher.get_metrics()["empty_polls"]
        win_info = ""

        if WINDOWS:
            win_info = (
                f". Windows [queue_size={watcher.get_win_queue_size()}, "
                f" folder_scan_size={watcher.get_win_folder_scan_size()}]"
            )

        log.info(
            f"Checking sync for engine {self.uid}: queue manager is {active_status} (size={qm_size}), "
            f"empty remote polls count is {empty_polls}, local watcher empty events is {empty_events}, "
            f"blacklist size is {blacklist_size} and syncing count is {self._dao.get_syncing_count()}"
            f"{win_info}"
        )

        if qm_size > 0 or not empty_events:
            return

        if blacklist_size:
            log.debug(f"Emitting syncPartialCompleted for engine {self.uid}")
            self.syncPartialCompleted.emit()
        else:
            self._dao.update_config("last_sync_date", datetime.datetime.utcnow())
            log.debug(f"Emitting syncCompleted for engine {self.uid}")
            self._sync_started = False
            self.syncCompleted.emit()

    def _thread_finished(self) -> None:
        for thread in self._threads:
            if thread == self._local_watcher.thread:
                continue
            if thread == self._remote_watcher.thread:
                continue
            if thread.isFinished():
                self._threads.remove(thread)

    def is_started(self) -> bool:
        return not self._stopped

    def start(self) -> None:
        if not self.check_fs_marker():
            raise FsMarkerException()

        # Checking root in case of failed migration
        self._check_root()

        # Launch the server confg file updater
        if self.manager.server_config_updater:
            self.manager.server_config_updater.force_poll()

        self._stopped = False
        Processor.soft_locks = {}
        log.info(f"Engine {self.uid} is starting")
        for thread in self._threads:
            thread.start()
        self.syncStarted.emit(0)
        self._start.emit()

    def get_threads(self) -> List[QThread]:
        return self._threads

    def get_metrics(self) -> Metrics:
        return {
            "uid": self.uid,
            "conflicted_files": self._dao.get_conflict_count(),
            "error_files": self._dao.get_error_count(),
            "files_size": self._dao.get_global_size(),
            "invalid_credentials": self._invalid_credentials,
            "sync_files": self._dao.get_sync_count(filetype="file"),
            "sync_folders": self._dao.get_sync_count(filetype="folder"),
            "syncing": self._dao.get_syncing_count(),
            "unsynchronized_files": self._dao.get_unsynchronized_count(),
        }

    def get_conflicts(self) -> DocPairs:
        return self._dao.get_conflicts()

    def conflict_resolver(self, row_id: int, emit: bool = True) -> None:
        pair = self._dao.get_state_from_id(row_id)
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
                self._dao.synchronize_state(pair)
            elif emit:
                # Raise conflict only if not resolvable
                self.newConflict.emit(row_id)
                self.manager.osi.send_sync_status(
                    pair, self.local.abspath(pair.local_path)
                )
        except:
            log.exception("Conflict resolver error")

    def get_errors(self) -> DocPairs:
        return self._dao.get_errors()

    def is_stopped(self) -> bool:
        return self._stopped

    def stop(self) -> None:
        log.debug(f"Engine {self.uid} stopping")

        # Make a backup in case something happens
        self._dao.save_backup()

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

    @staticmethod
    def use_trash() -> bool:
        return True

    def update_token(self, token: str) -> None:
        self._load_configuration()
        self._remote_token = token
        self.remote.update_token(token)
        self._dao.update_config("remote_token", self._remote_token)
        self.set_invalid_credentials(value=False)
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
            "check_suspended": self.suspend_client,
            "dao": self._dao,
            "proxy": self.manager.proxy,
            "verify": verify,
        }
        return self.remote_cls(*args, **kwargs)

    def bind(self, binder: Binder) -> None:
        check_credentials = not binder.no_check
        check_fs = not (Options.nofscheck or binder.no_fscheck)
        self.server_url = self._normalize_url(binder.url)
        self.remote_user = binder.username
        self.account = f"{self.remote_user} • {self.name}"
        self._remote_password = binder.password
        self._remote_token = binder.token
        self._web_authentication = self._remote_token is not None
        self.remote = None  # type: ignore

        # Check first if the folder is on a supported FS
        if check_fs:
            new_folder = not self.local_folder.is_dir()
            if new_folder:
                self.local_folder.mkdir(parents=True)
            try:
                self._check_fs(self.local_folder)
            except InvalidDriveException as exc:
                if new_folder:
                    with suppress(OSError):
                        self.local.unset_readonly(self.local_folder)
                        self.local_folder.rmdir()
                raise exc

        # Persist the user preference about the SSL behavior.
        # It can be tweaked via ca-bundle or ssl-no-verify options. But also
        # from the ponctual bypass-ssl window prompted at the account creation.
        self._ssl_verify = not Options.ssl_no_verify
        self._ca_bundle = Options.ca_bundle

        if check_credentials:
            self.remote = self.init_remote()
            if not self._remote_token:
                self._remote_token = self.remote.request_token()

        if self._remote_token is not None:
            # The server supports token based identification: do not store the
            # password in the DB
            self._remote_password = None

        # Save the configuration
        self._dao.store_bool("web_authentication", self._web_authentication)
        self._dao.update_config("server_url", self.server_url)
        self._dao.update_config("remote_user", self.remote_user)
        self._dao.update_config("remote_password", self._remote_password)
        self._dao.update_config("remote_token", self._remote_token)
        self._dao.store_bool("ssl_verify", self._ssl_verify)
        self._dao.update_config("ca_bundle", self._ca_bundle)

        # Check for the root
        # If the top level state for the server binding doesn't exist,
        # create the local folder and the top level state.
        self._check_root()

    def _check_fs(self, path: Path) -> None:
        if not self.manager.osi.is_partition_supported(path):
            raise InvalidDriveException()

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
            return

        try:
            url = self.server_url.replace("http://", "https://")
            proxies = self.manager.proxy.settings(url=url)
            import requests

            requests.get(url, proxies=proxies)
            self.server_url = url
            self._dao.update_config("server_url", self.server_url)
            log.info(f"Updated server url to {self.server_url}")
        except Exception:
            log.warning(
                f"Server at {self.server_url} doesn't seem to handle HTTPS, keeping HTTP",
                exc_info=True,
            )

    def _check_root(self) -> None:
        root = self._dao.get_state_from_local(ROOT)
        if root is None:
            if self.local_folder.is_dir():
                unset_path_readonly(self.local_folder)
            self._make_local_folder(self.local_folder)
            self._add_top_level_state()
            self._set_root_icon()
            self.manager.osi.register_folder_link(self.local_folder)
            set_path_readonly(self.local_folder)

    def _make_local_folder(self, local_folder: Path) -> None:
        local_folder.mkdir(parents=True, exist_ok=True)
        # Put the ROOT in readonly

    def cancel_action_on(self, pair_id: int) -> None:
        for thread in self._threads:
            if hasattr(thread, "worker") and isinstance(thread.worker, Processor):
                pair = thread.worker.get_current_pair()
                if pair is not None and pair.id == pair_id:
                    thread.worker.quit()

    @if_frozen
    def _set_root_icon(self) -> None:
        state = self.local.has_folder_icon(ROOT)
        if isinstance(state, str):
            # Save the original version in the database for later stats
            # and proceed to the new icon installation.
            self.manager.set_config("original_version", state)
        elif state:
            return

        if MAC:
            icon = find_icon("folder_mac.dat")
        elif WINDOWS:
            icon = find_icon("folder_windows.ico")
        else:
            # No implementation on GNU/Linux
            return

        if not icon:
            return

        locker = self.local.unlock_ref(ROOT, unlock_parent=False)
        try:
            self.local.set_folder_icon(ROOT, icon)
        except:
            log.exception("Icon folder cannot be set")
        finally:
            self.local.lock_ref(ROOT, locker)

    def _add_top_level_state(self) -> None:
        if not self.remote:
            return

        local_info = self.local.get_info(ROOT)
        self._dao.insert_local_state(local_info, None)
        row = self._dao.get_state_from_local(ROOT)
        if not row:
            return

        remote_info = self.remote.get_filesystem_root_info()
        self._dao.update_remote_state(
            row, remote_info, remote_parent_path="", versioned=False
        )
        value = "|".join(
            (self.server_url, self.remote_user, self.manager.device_id, self.uid)
        )
        self.local.set_root_id(value.encode("utf-8"))
        self.local.set_remote_id(ROOT, remote_info.uid)
        self._dao.synchronize_state(row)
        # The root should also be sync

    def suspend_client(self, message: str = None) -> None:
        if self.is_paused() or self._stopped:
            raise ThreadInterrupt()

        # Verify thread status
        thread_id = current_thread().ident
        for thread in self._threads:
            if (
                hasattr(thread, "worker")
                and isinstance(thread.worker, Processor)
                and thread.worker.thread_id == thread_id
                and not thread.worker.is_started()
            ):
                raise ThreadInterrupt()

        # Get action
        current_file = None
        action = Action.get_current_action()
        if isinstance(action, FileAction):
            current_file = self.local.get_path(action.filepath)
        if (
            current_file is not None
            and self._folder_lock is not None
            and self._folder_lock in current_file.parents
        ):
            log.info(
                f"PairInterrupt {current_file!r} because lock on {self._folder_lock!r}"
            )
            raise PairInterrupt()

    def create_processor(self, item_getter: Callable, **kwargs: Any) -> Processor:
        return Processor(self, item_getter, **kwargs)

    def dispose_db(self) -> None:
        if self._dao:
            self._dao.dispose()

    def get_user_full_name(self, userid: str, cache_only: bool = False) -> str:
        """ Get the last contributor full name. """

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
    """ Summarize server binding settings. """

    server_url: str
    web_authentication: str
    username: str
    local_folder: Path
    initialized: bool
    server_version: Optional[str] = None
    password: Optional[str] = None
    pwd_update_required: bool = False
