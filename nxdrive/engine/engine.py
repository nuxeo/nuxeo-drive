# coding: utf-8
import datetime
import os
from logging import getLogger
from threading import Thread, current_thread
from time import sleep
from typing import Any, Callable, List, Optional, Type
from urllib.parse import urlsplit

from PyQt5.QtCore import QCoreApplication, QObject, QThread, pyqtSignal, pyqtSlot
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
from ..constants import MAC, WINDOWS
from ..exceptions import (
    InvalidDriveException,
    PairInterrupt,
    RootAlreadyBindWithDifferentAccount,
    ThreadInterrupt,
)
from ..objects import Binder, DocPairs, Metrics
from ..options import Options
from ..utils import (
    find_icon,
    if_frozen,
    normalized_path,
    safe_filename,
    set_path_readonly,
    unset_path_readonly,
)

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
    fileDeletionErrorTooLong = pyqtSignal(object)
    syncStarted = pyqtSignal(object)
    syncCompleted = pyqtSignal()
    # Sent when files are in blacklist but the rest is ok
    syncPartialCompleted = pyqtSignal()
    syncSuspended = pyqtSignal()
    syncResumed = pyqtSignal()
    rootDeleted = pyqtSignal()
    rootMoved = pyqtSignal(str)
    uiChanged = pyqtSignal()
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

    def __init__(
        self,
        manager: "Manager",
        definition: object,
        binder: Binder = None,
        processors: int = 5,
        remote_cls: Type[Remote] = Remote,
        local_cls: Type[LocalWatcher] = LocalClient,
    ) -> None:
        super().__init__()

        self.version = manager.version

        self.remote_cls = remote_cls
        self.local_cls = local_cls
        self.remote = None

        # Stop if invalid credentials
        self.invalidAuthentication.connect(self.stop)
        # Folder locker - LocalFolder processor can prevent
        # others processors to operate on a folder
        self._folder_lock = None
        self.timeout = 30
        self._handshake_timeout = 60
        self.manager = manager

        self.local_folder = definition.local_folder
        self.local = self.local_cls(self.local_folder)
        # Keep folder path with backslash to find the right engine when
        # FinderSync is asking for the status of a file
        self.local_folder_bs = self._normalize_url(self.local_folder)

        self.uid = definition.uid
        self.name = definition.name
        self._stopped = True
        self._pause = False
        self._sync_started = False
        self._invalid_credentials = False
        self._offline_state = False
        self._threads = list()
        self._dao = EngineDAO(self._get_db_file())

        if binder:
            self.bind(binder)
        self._load_configuration()

        if not self.remote:
            self.init_remote()

        self._local_watcher = self._create_local_watcher()
        self.create_thread(worker=self._local_watcher)
        self._remote_watcher = self._create_remote_watcher(Options.delay)
        self.create_thread(worker=self._remote_watcher, start_connect=False)

        # Launch remote_watcher after first local scan
        self._local_watcher.rootDeleted.connect(self.rootDeleted)
        self._local_watcher.rootMoved.connect(self.rootMoved)
        self._local_watcher.localScanFinished.connect(self._remote_watcher.run)
        self._queue_manager = self._create_queue_manager(processors)

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
        self._user_cache = dict()

        # Pause in case of no more space on the device
        self.noSpaceLeftOnDevice.connect(self.suspend)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}"
            f"<name={self.name!r}, offline={self._offline_state!r}, "
            f"uid={self.uid!r}, type={self.type!r}>"
        )

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

    def stop_processor_on(self, path: str) -> None:
        for worker in self.get_queue_manager().get_processors_on(path):
            log.trace(
                f"Quitting processor: {worker!r} as requested to stop on {path!r}"
            )
            worker.quit()

    def set_local_folder(self, path: str) -> None:
        log.debug(f"Update local folder to {path!r}")
        self.local_folder = path
        self.local_folder_bs = self._normalize_url(self.local_folder)
        self._local_watcher.stop()
        self._create_local_watcher()
        self.manager.update_engine_path(self.uid, path)

    def set_local_folder_lock(self, path: str) -> None:
        self._folder_lock = path
        # Check for each processor
        log.debug(f"Local Folder locking on {path!r}")
        while self.get_queue_manager().has_file_processors_on(path):
            log.trace("Local folder locking wait for file processor to finish")
            sleep(1)
        log.debug(f"Local Folder lock setup completed on {path!r}")

    def set_ui(self, value: str, overwrite: bool = True) -> None:
        name = ("wui", "force_ui")[overwrite]
        if getattr(self, name, "") == value:
            return

        key_name = ("force_ui", "ui")[name == "wui"]
        self._dao.update_config(key_name, value)
        setattr(self, name, value)
        log.debug(f"{name} preferences set to {value}")
        self.uiChanged.emit()

    def release_folder_lock(self) -> None:
        log.debug("Local Folder unlocking")
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
            log.debug(f"Engine {self.uid} goes offline")
            self._queue_manager.suspend()
            self.offline.emit()
        else:
            log.debug(f"Engine {self.uid} goes online")
            self._queue_manager.resume()
            self.online.emit()

    def is_offline(self) -> bool:
        return self._offline_state

    def add_filter(self, path: str) -> None:
        remote_ref = os.path.basename(path)
        remote_parent_path = os.path.dirname(path)
        if remote_ref is None:
            return
        self._dao.add_filter(path)
        pair = self._dao.get_state_from_remote_with_path(remote_ref, remote_parent_path)
        if not pair:
            log.debug(f"Cannot find the pair: {remote_ref} ({remote_parent_path!r})")
            return
        self._dao.delete_remote_state(pair)

    def remove_filter(self, path: str) -> None:
        self._dao.remove_filter(path)
        # Scan the "new" pair, use signal/slot to not block UI
        self._scanPair.emit(path)

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
        log.debug(f"Will try to open edit : {doc_ref}")
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
        if not os.path.isdir(self.local_folder):
            self.rootDeleted.emit()
            return False

        self.local.set_remote_id("/", tag_value, tag)
        if self.local.get_remote_id("/", tag) != tag_value.decode("utf-8"):
            return False

        self.local.remove_remote_id("/", tag)
        return self.local.get_remote_id("/", tag) is None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Ensure that user provided url always has a trailing '/'"""
        if not url:
            raise ValueError(f"Invalid url: {url!r}")
        if not url.endswith("/"):
            return url + "/"
        return url

    def _load_configuration(self) -> None:
        self._web_authentication = (
            self._dao.get_config("web_authentication", "0") == "1"
        )
        self.server_url = self._dao.get_config("server_url")
        self.hostname = urlsplit(self.server_url).hostname
        self.wui = self._dao.get_config("ui", default="jsf")
        self.force_ui = self._dao.get_config("force_ui")
        self.remote_user = self._dao.get_config("remote_user")
        self._remote_password = self._dao.get_config("remote_password")
        self._remote_token = self._dao.get_config("remote_token")
        if self._remote_password is None and self._remote_token is None:
            self.set_invalid_credentials(
                reason="found no password nor token in engine configuration"
            )

    def get_remote_token(self) -> Optional[str]:
        return self._dao.get_config("remote_token")

    def _create_queue_manager(self, processors: int) -> QueueManager:
        kwargs = {}
        if Options.debug:
            kwargs["max_file_processors"] = 2

        return QueueManager(self, self._dao, **kwargs)

    def _create_remote_watcher(self, delay: int) -> RemoteWatcher:
        return RemoteWatcher(self, self._dao, delay)

    def _create_local_watcher(self) -> LocalWatcher:
        return LocalWatcher(self, self._dao)

    def _get_db_file(self) -> str:
        return os.path.join(
            normalized_path(self.manager.nxdrive_home), "ndrive_" + self.uid + ".db"
        )

    def get_binder(self) -> "ServerBindingSettings":
        return ServerBindingSettings(
            server_url=self.server_url,
            web_authentication=self._web_authentication,
            username=self.remote_user,
            local_folder=self.local_folder,
            initialized=True,
            pwd_update_required=self.has_invalid_credentials(),
        )

    def set_invalid_credentials(self, value: bool = True, reason: str = None) -> None:
        changed = self._invalid_credentials is not value
        self._invalid_credentials = value
        if value and changed:
            msg = "Setting invalid credentials"
            if reason:
                msg += f", reason is: {reason}"
            log.error(msg)
            self.invalidAuthentication.emit()

    def has_invalid_credentials(self) -> bool:
        return self._invalid_credentials

    def get_queue_manager(self) -> QueueManager:
        return self._queue_manager

    def get_local_watcher(self) -> LocalWatcher:
        return self._local_watcher

    def get_remote_watcher(self) -> RemoteWatcher:
        return self._remote_watcher

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

        thread = worker.get_thread()
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

    def unsynchronize_pair(self, row_id: int, reason: str = None) -> None:
        state = self._dao.get_state_from_id(row_id)
        if state is None:
            return
        self._dao.unsynchronize_state(state, last_error=reason)
        self._dao.reset_error(state, last_error=reason)

    def resolve_with_local(self, row_id: int) -> None:
        row = self._dao.get_state_from_id(row_id)
        self._dao.force_local(row)

    def resolve_with_remote(self, row_id: int) -> None:
        row = self._dao.get_state_from_id(row_id)
        self._dao.force_remote(row)

    @pyqtSlot()
    def _check_last_sync(self) -> None:
        empty_events = self._local_watcher.empty_events()
        blacklist_size = self._queue_manager.get_errors_count()
        qm_size = self._queue_manager.get_overall_size()
        qm_active = self._queue_manager.active()
        active_status = "active" if qm_active else "inactive"
        empty_polls = self._remote_watcher.get_metrics()["empty_polls"]
        if not WINDOWS:
            win_info = "not Windows"
        else:
            win_info = (
                "Windows with win queue size = "
                f"{self._local_watcher.get_win_queue_size()} and win folder "
                f"scan size = {self._local_watcher.get_win_folder_scan_size()}"
            )
        log.debug(
            f"Checking sync completed [{self.uid}]: queue manager is {active_status}, "
            f"overall size = {qm_size}, empty polls count = {empty_polls}, "
            f"local watcher empty events = {empty_events}, "
            f"blacklist = {blacklist_size}, {win_info}"
        )
        local_metrics = self._local_watcher.get_metrics()
        if qm_size == 0 and not qm_active and empty_polls > 0 and empty_events:
            if blacklist_size != 0:
                self.syncPartialCompleted.emit()
                return
            self._dao.update_config("last_sync_date", datetime.datetime.utcnow())
            if local_metrics["last_event"] == 0:
                log.trace("No watchdog event detected but sync is completed")
            self._sync_started = False
            log.trace(f"Emitting syncCompleted for engine {self.uid}")
            self.syncCompleted.emit()

    def _thread_finished(self) -> None:
        for thread in self._threads:
            if thread == self._local_watcher.get_thread():
                continue
            if thread == self._remote_watcher.get_thread():
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
        Processor.soft_locks = dict()
        log.debug(f"Engine {self.uid} is starting")
        for thread in self._threads:
            thread.start()
        self.syncStarted.emit(0)
        self._start.emit()

    def get_threads(self) -> List[QThread]:
        return self._threads

    def get_status(self) -> None:
        QCoreApplication.processEvents()
        log.debug("Engine status")
        for thread in self._threads:
            log.debug(f"{thread.worker.get_metrics()!r}")
        log.debug(f"{self._queue_manager.get_metrics()!r}")

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
            log.trace("Conflict resolver: empty pair, skipping")
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
        self._stopped = True
        log.trace(f"Engine {self.uid} stopping")
        self._stop.emit()
        for thread in self._threads:
            if not thread.wait(5000):
                log.warning("Thread is not responding - terminate it")
                thread.terminate()
        if not self._local_watcher.get_thread().wait(5000):
            self._local_watcher.get_thread().terminate()
        if not self._remote_watcher.get_thread().wait(5000):
            self._remote_watcher.get_thread().terminate()
        for thread in self._threads:
            if thread.isRunning():
                thread.wait(5000)
        if not self._remote_watcher.get_thread().isRunning():
            self._remote_watcher.get_thread().wait(5000)
        if not self._local_watcher.get_thread().isRunning():
            self._local_watcher.get_thread().wait(5000)
        # Soft locks needs to be reinit in case of threads termination
        Processor.soft_locks = dict()
        log.trace(f"Engine {self.uid} stopped")

    @staticmethod
    def use_trash() -> bool:
        return True

    def update_password(self, password: str) -> None:
        self._load_configuration()
        self.remote.client.auth = (self.remote.user_id, password)
        self._remote_token = self.remote.request_token()
        if self._remote_token is None:
            raise ValueError
        self._dao.update_config("remote_token", self._remote_token)
        self.set_invalid_credentials(value=False)
        # In case of a binding
        self._check_root()
        self.start()

    def update_token(self, token: str) -> None:
        self._load_configuration()
        self._remote_token = token
        self.remote.update_token(token)
        self._dao.update_config("remote_token", self._remote_token)
        self.set_invalid_credentials(value=False)
        self.start()

    def init_remote(self) -> None:
        # Used for FS synchronization operations
        args = (self.server_url, self.remote_user, self.manager.device_id, self.version)
        kwargs = {
            "password": self._remote_password,
            "timeout": self.timeout,
            "token": self._remote_token,
            "check_suspended": self.suspend_client,
            "dao": self._dao,
            "proxy": self.manager.proxy,
        }
        self.remote = self.remote_cls(*args, **kwargs)

    def bind(self, binder: Binder) -> None:
        check_credentials = not binder.no_check
        check_fs = not (Options.nofscheck or binder.no_fscheck)
        self.server_url = self._normalize_url(binder.url)
        self.remote_user = binder.username
        self._remote_password = binder.password
        self._remote_token = binder.token
        self._web_authentication = self._remote_token is not None

        self.init_remote()

        if check_fs:
            try:
                os.makedirs(self.local_folder, exist_ok=True)
                self._check_fs(self.local_folder)
            except (InvalidDriveException, RootAlreadyBindWithDifferentAccount):
                try:
                    self.local.unset_readonly(self.local_folder)
                    os.rmdir(self.local_folder)
                except:
                    pass
            except OSError:
                raise

        if check_credentials and self._remote_token is None:
            self._remote_token = self.remote.request_token()

        if self._remote_token is not None:
            # The server supports token based identification: do not store the
            # password in the DB
            self._remote_password = None

        # Save the configuration
        self._dao.update_config("web_authentication", self._web_authentication)
        self._dao.update_config("server_url", self.server_url)
        self._dao.update_config("remote_user", self.remote_user)
        self._dao.update_config("remote_password", self._remote_password)
        self._dao.update_config("remote_token", self._remote_token)

        # Check for the root
        # If the top level state for the server binding doesn't exist,
        # create the local folder and the top level state.
        self._check_root()

    def _check_fs(self, path: str) -> None:
        if not self.manager.osi.is_partition_supported(path):
            raise InvalidDriveException()

        if os.path.isdir(path):
            root_id = self.local.get_root_id()
            if root_id is not None:
                # server_url|user|device_id|uid
                server_url, user, *_ = root_id.split("|")
                if (self.server_url, self.remote_user) != (server_url, user):
                    raise RootAlreadyBindWithDifferentAccount(user, server_url)

    def _check_root(self) -> None:
        root = self._dao.get_state_from_local("/")
        if root is None:
            if os.path.isdir(self.local_folder):
                unset_path_readonly(self.local_folder)
            self._make_local_folder(self.local_folder)
            self._add_top_level_state()
            self._set_root_icon()
            self.manager.osi.register_folder_link(self.local_folder)
            set_path_readonly(self.local_folder)

    def _make_local_folder(self, local_folder: str) -> None:
        os.makedirs(local_folder, exist_ok=True)
        # Put the ROOT in readonly

    def cancel_action_on(self, pair_id: int) -> None:
        for thread in self._threads:
            if hasattr(thread, "worker") and isinstance(thread.worker, Processor):
                pair = thread.worker.get_current_pair()
                if pair is not None and pair.id == pair_id:
                    thread.worker.quit()

    @if_frozen
    def _set_root_icon(self) -> None:
        state = self.local.has_folder_icon("/")
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

        locker = self.local.unlock_ref("/", unlock_parent=False)
        try:
            self.local.set_folder_icon("/", icon)
        except:
            log.exception("Icon folder cannot be set")
        finally:
            self.local.lock_ref("/", locker)

    def _add_top_level_state(self) -> None:
        local_info = self.local.get_info("/")

        if not self.remote:
            return

        remote_info = self.remote.get_filesystem_root_info()

        self._dao.insert_local_state(local_info, "")
        row = self._dao.get_state_from_local("/")
        self._dao.update_remote_state(
            row, remote_info, remote_parent_path="", versioned=False
        )
        value = "|".join(
            (self.server_url, self.remote_user, self.manager.device_id, self.uid)
        )
        self.local.set_root_id(value.encode("utf-8"))
        self.local.set_remote_id("/", remote_info.uid)
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
                and thread.worker.get_thread_id() == thread_id
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
            and current_file.startswith(self._folder_lock)
        ):
            log.debug(
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


class ServerBindingSettings:
    """ Summarize server binding settings. """

    def __init__(
        self,
        server_version: str = None,
        password: str = None,
        pwd_update_required: bool = False,
        **kwargs,
    ) -> None:
        self.server_version = server_version
        self.password = password
        self.pwd_update_required = pwd_update_required
        for arg, value in kwargs.items():
            setattr(self, arg, value)

    def __repr__(self) -> str:
        attrs = ", ".join(
            "{}={!r}".format(attr, getattr(self, attr, None))
            for attr in sorted(vars(self))
        )
        return "<{} {}>".format(self.__class__.__name__, attrs)
