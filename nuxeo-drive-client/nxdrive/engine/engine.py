from PyQt4.QtCore import QObject, QCoreApplication
from PyQt4.QtCore import pyqtSlot, pyqtSignal
from nxdrive.logging_config import get_logger
from nxdrive.commandline import DEFAULT_REMOTE_WATCHER_DELAY
from nxdrive.commandline import DEFAULT_UPDATE_SITE_URL
from nxdrive.client.common import DEFAULT_REPOSITORY_NAME
from nxdrive.client.common import NotFound
from nxdrive.client import LocalClient
from nxdrive.client import RemoteFileSystemClient
from nxdrive.client import RemoteFilteredFileSystemClient
from nxdrive.client import RemoteDocumentClient
from nxdrive.utils import normalized_path
from nxdrive.engine.processor import Processor
from threading import current_thread
from nxdrive.osi import AbstractOSIntegration
from nxdrive.engine.workers import Worker, ThreadInterrupt, PairInterrupt
from nxdrive.engine.activity import Action, FileAction
from time import sleep
WindowsError = None
try:
    from exceptions import WindowsError
except ImportError:
    pass  # this will never be raised under unix
import os
import datetime
from cookielib import CookieJar
from nxdrive.client.common import safe_filename
from nxdrive.gui.resources import find_icon
import urllib2

log = get_logger(__name__)


class InvalidDriveException(Exception):
    pass


class RootAlreadyBindWithDifferentAccount(Exception):

    def __init__(self, username, url):
        self._username = username
        self._url = url

    def get_username(self):
        return self._username

    def get_url(self):
        return self._url

class FsMarkerException(Exception):
    pass


class EngineLogger(QObject):
    def __init__(self, engine):
        super(EngineLogger, self).__init__()
        self._dao = engine.get_dao()
        self._engine = engine
        self._engine.logger = self
        self._level = 10
        self._engine.syncStarted.connect(self.logSyncStart)
        self._engine.syncCompleted.connect(self.logSyncComplete)
        self._engine.newConflict.connect(self.logConflict)
        self._engine.newSync.connect(self.logSync)
        self._engine.newError.connect(self.logError)
        self._engine.newQueueItem.connect(self.logQueueItem)

    def _log_pair(self, row_id, msg, handler=None):
        pair = self._dao.get_state_from_id(row_id)
        if handler is not None:
            log.log(self._level, msg, pair, handler)
        else:
            log.log(self._level, msg, pair)

    @pyqtSlot()
    def logSyncComplete(self):
        log.log(self._level, "Synchronization is complete for engine %s",
                self.sender().get_uid())

    @pyqtSlot(object)
    def logSyncStart(self):
        log.log(self._level, "Synchronization starts ( items)")

    @pyqtSlot(object)
    def logConflict(self, row_id):
        self._log_pair(row_id, "Conflict on %r")

    @pyqtSlot(object, object)
    def logSync(self, row, metrics):
        log.log(self._level, "Sync on %r with %r", row, metrics)

    @pyqtSlot(object)
    def logError(self, row_id):
        self._log_pair(row_id, "Error on %r")

    @pyqtSlot(object)
    def logQueueItem(self, row_id):
        self._log_pair(row_id, "QueueItem on %r")

'''
' Used for threads interaction
'''


class Engine(QObject):
    BATCH_MODE_UPLOAD = "upload"
    BATCH_MODE_FOLDER = "folder"
    BATCH_MODE_DOWNLOAD = "download"
    BATCH_MODE_SYNC = "sync"
    _start = pyqtSignal()
    _stop = pyqtSignal()
    _scanPair = pyqtSignal(str)
    syncStarted = pyqtSignal(object)
    syncCompleted = pyqtSignal()
    # Sent when files are in blacklist but the rest is ok
    syncPartialCompleted = pyqtSignal()
    syncSuspended = pyqtSignal()
    syncResumed = pyqtSignal()
    rootDeleted = pyqtSignal()
    rootMoved = pyqtSignal(str)
    invalidAuthentication = pyqtSignal()
    invalidClientsCache = pyqtSignal()
    newConflict = pyqtSignal(object)
    newReadonly = pyqtSignal(object, object)
    newLocked = pyqtSignal(object, object, object)
    newSync = pyqtSignal(object, object)
    newError = pyqtSignal(object)
    newQueueItem = pyqtSignal(object)
    offline = pyqtSignal()
    online = pyqtSignal()

    def __init__(self, manager, definition, binder=None, processors=5,
                 remote_watcher_delay=DEFAULT_REMOTE_WATCHER_DELAY,
                 remote_doc_client_factory=RemoteDocumentClient,
                 remote_fs_client_factory=RemoteFileSystemClient,
                 remote_filtered_fs_client_factory=RemoteFilteredFileSystemClient):
        super(Engine, self).__init__()

        self.version = manager.get_version()
        self._remote_clients = dict()
        # Used for binding server / roots and managing tokens
        self.remote_doc_client_factory = remote_doc_client_factory

        # Used for FS synchronization operations
        self.remote_fs_client_factory = remote_fs_client_factory
        # Used for FS synchronization operations
        self.remote_filtered_fs_client_factory = remote_filtered_fs_client_factory
        # Stop if invalid credentials
        self.invalidAuthentication.connect(self.stop)
        # Folder locker - LocalFolder processor can prevent others processors to operate on a folder
        self._folder_lock = None
        # Case sensitive partition
        self._case_sensitive = None
        self.timeout = 30
        self._handshake_timeout = 60
        # Make all the automation client related to this manager
        # share cookies using threadsafe jar
        self.cookie_jar = CookieJar()
        self._manager = manager
        # Remove remote client cache on proxy update
        self._manager.proxyUpdated.connect(self.invalidate_client_cache)
        self._local_folder = definition.local_folder
        self._type = "NXDRIVE"
        self._uid = definition.uid
        self._name = definition.name
        self._stopped = True
        self._pause = False
        self._sync_started = False
        self._invalid_credentials = False
        self._offline_state = False
        self._threads = list()
        self._client_cache_timestamps = dict()
        self._dao = self._create_dao()
        if binder is not None:
            self.bind(binder)
        self._load_configuration()
        self._local_watcher = self._create_local_watcher()
        self.create_thread(worker=self._local_watcher)
        self._remote_watcher = self._create_remote_watcher(remote_watcher_delay)
        self.create_thread(worker=self._remote_watcher, start_connect=False)
        # Launch remote_watcher after first local scan
        self._local_watcher.rootDeleted.connect(self.rootDeleted)
        self._local_watcher.rootMoved.connect(self.rootMoved)
        self._local_watcher.localScanFinished.connect(self._remote_watcher.run)
        self._queue_manager = self._create_queue_manager(processors)
        # Launch queue processors after first remote_watcher pass
        self._remote_watcher.initiate.connect(self._queue_manager.init_processors)
        self._remote_watcher.remoteWatcherStopped.connect(self._queue_manager.shutdown_processors)
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
            self._conflict_resolver(conflict.id, emit=False)
        # Scan in remote_watcher thread
        self._scanPair.connect(self._remote_watcher.scan_pair)
        # Set the root icon
        self._set_root_icon()
        # Set user full name
        self._user_cache = dict()

    @pyqtSlot(object)
    def _check_sync_start(self, row_id):
        if not self._sync_started:
            queue_size = self._queue_manager.get_overall_size()
            if queue_size > 0:
                self._sync_started = True
                self.syncStarted.emit(queue_size)

    def reinit(self):
        started = not self._stopped
        if started:
            self.stop()
        self._dao.reinit_states()
        self._check_root()
        if started:
            self.start()

    def stop_processor_on(self, path):
        for worker in self.get_queue_manager().get_processors_on(path, exact_match=True):
            log.trace("Quitting processor: %r as requested to stop on %s", worker, path)
            worker.quit()

    def set_local_folder(self, path):
        log.debug("Update local folder to '%s'", path)
        self._local_folder = path
        self._local_watcher.stop()
        self._create_local_watcher()
        self._manager.update_engine_path(self._uid, path)

    def set_local_folder_lock(self, path):
        self._folder_lock = path
        # Check for each processor
        log.debug("Local Folder locking on '%s'", path)
        while self.get_queue_manager().has_file_processors_on(path):
            log.trace("Local folder locking wait for file processor to finish")
            sleep(1)
        log.debug("Local Folder lock setup completed on '%s'", path)

    def release_folder_lock(self):
        log.debug("Local Folder unlocking")
        self._folder_lock = None

    def get_last_files(self, number, direction=None):
        return self._dao.get_last_files(number, direction)

    def set_offline(self, value=True):
        if value == self._offline_state:
            return
        self._offline_state = value
        if value:
            log.debug("Engine %s goes offline", self._uid)
            self._queue_manager.suspend()
            self.offline.emit()
        else:
            log.debug("Engine %s goes online", self._uid)
            self._queue_manager.resume()
            self.online.emit()

    def is_offline(self):
        return self._offline_state

    def add_filter(self, path):
        remote_ref = os.path.basename(path)
        remote_parent_path = os.path.dirname(path)
        if remote_ref is None:
            return
        self._dao.add_filter(path)
        pair = self._dao.get_state_from_remote_with_path(remote_ref, remote_parent_path)
        if pair is None:
            log.debug("Can't find the pair: %s (%s)", remote_ref, remote_parent_path)
            return
        self._dao.delete_remote_state(pair)

    def remove_filter(self, path):
        self.get_dao().remove_filter(path)
        # Scan the "new" pair, use signal/slot to not block UI
        self._scanPair.emit(path)

    def get_document_id(self, remote_ref):
        remote_ref_segments = remote_ref.split("#", 2)
        return remote_ref_segments[2]

    def get_metadata_url(self, remote_ref):
        DRIVE_METADATA_VIEW = 'view_drive_metadata'
        metadata_url = self.get_server_url()
        remote_ref_segments = remote_ref.split("#", 2)
        repo = remote_ref_segments[1]
        doc_id = remote_ref_segments[2]
        metadata_url += ("nxdoc/" + repo + "/" + doc_id +
                                 "/" + DRIVE_METADATA_VIEW)
        return metadata_url

    def is_syncing(self):
        return self._sync_started

    def is_paused(self):
        return self._pause

    def open_edit(self, remote_ref, remote_name):
        doc_ref = remote_ref
        if "#" in doc_ref:
            doc_ref = doc_ref[doc_ref.rfind('#') + 1:]
        log.debug("Will try to open edit : %s", doc_ref)
        # TODO Implement a TemporaryWorker
        from threading import Thread

        def run():
            self._manager.get_drive_edit().edit(self._server_url,
                                                doc_ref, filename=remote_name, user=self._remote_user)
        self._edit_thread = Thread(target=run)
        self._edit_thread.start()

    def open_remote(self, url=None):
        if url is None:
            url = self.get_remote_url()
        self._manager.open_local_file(url)

    def get_previous_file(self, ref, mode):
        if mode == Engine.BATCH_MODE_FOLDER:
            return self._dao.get_previous_folder_file(ref)
        if mode == Engine.BATCH_MODE_SYNC:
            mode = None
        return self._dao.get_previous_sync_file(ref, sync_mode=mode)

    def get_next_file(self, ref, mode):
        if mode == Engine.BATCH_MODE_FOLDER:
            return self._dao.get_next_folder_file(ref)
        if mode == Engine.BATCH_MODE_SYNC:
            mode = None
        return self._dao.get_next_sync_file(ref, sync_mode=mode)

    def resume(self):
        # If stopped then start the engine
        if self._stopped:
            self.start()
            return
        self._pause = False
        self._queue_manager.resume()
        for thread in self._threads:
            if thread.isRunning():
                thread.worker.resume()
            else:
                thread.start()
        self.syncResumed.emit()

    def suspend(self):
        if self._pause:
            return
        self._pause = True
        self._queue_manager.suspend()
        for thread in self._threads:
            thread.worker.suspend()
        self.syncSuspended.emit()

    def unbind(self):
        self.stop()
        try:
            # Dont fail if not possible to remove token
            doc_client = self.get_remote_doc_client()
            doc_client.revoke_token()
        except Exception as e:
            log.exception(e)
        self.dispose_db()
        # Remove DB
        log.debug("Remove DB file %s", self._get_db_file())
        try:
            os.remove(self._get_db_file())
        except (IOError, OSError, WindowsError) as ioe:
            log.exception(ioe)
        return

    def check_fs_marker(self):
        tag = 'drive-fs-test'
        tag_value = 'NXDRIVE_VERIFICATION'
        if not os.path.exists(self._local_folder):
            self.rootDeleted.emit()
            return False
        client = self.get_local_client()
        client.set_remote_id('/', tag_value, tag)
        if client.get_remote_id('/', tag) != tag_value:
            return False
        client.remove_remote_id('/', tag)
        if client.get_remote_id('/', tag) != None:
            return False
        return True

    def _normalize_url(self, url):
        """Ensure that user provided url always has a trailing '/'"""
        if url is None or not url:
            raise ValueError("Invalid url: %r" % url)
        if not url.endswith(u'/'):
            return url + u'/'
        return url

    def _load_configuration(self):
        self._web_authentication = self._dao.get_config("web_authentication", "0") == "1"
        self._server_url = self._dao.get_config("server_url")
        self._remote_user = self._dao.get_config("remote_user")
        self._remote_password = self._dao.get_config("remote_password")
        self._remote_token = self._dao.get_config("remote_token")
        self._device_id = self._manager.device_id
        if self._remote_password is None and self._remote_token is None:
            self.set_invalid_credentials(reason="found no password nor token in engine configuration")

    def get_server_url(self):
        return self._dao.get_config("server_url")

    def get_remote_user(self):
        return self._dao.get_config("remote_user")

    def get_remote_token(self):
        return self._dao.get_config("remote_token")

    def _create_queue_manager(self, processors):
        from nxdrive.engine.queue_manager import QueueManager
        if self._manager.is_debug():
            return QueueManager(self, self._dao, max_file_processors=2)
        return QueueManager(self, self._dao)

    def _create_remote_watcher(self, delay):
        from nxdrive.engine.watcher.remote_watcher import RemoteWatcher
        return RemoteWatcher(self, self._dao, delay)

    def _create_local_watcher(self):
        from nxdrive.engine.watcher.local_watcher import LocalWatcher
        return LocalWatcher(self, self._dao)

    def _get_db_file(self):
        return os.path.join(normalized_path(self._manager.get_configuration_folder()),
                                "ndrive_" + self._uid + ".db")

    def _create_dao(self):
        from nxdrive.engine.dao.sqlite import EngineDAO
        return EngineDAO(self._get_db_file())

    def get_remote_url(self):
        server_link = self._dao.get_config("server_url", "")
        repository = DEFAULT_REPOSITORY_NAME
        if not server_link.endswith('/'):
            server_link += '/'
        url_suffix = ('@view_home?tabIds=MAIN_TABS:home,'
                      'USER_CENTER:userCenterNuxeoDrive')
        server_link += 'nxhome/' + repository + url_suffix
        return server_link

    def get_abspath(self, path):
        return self.get_local_client()._abspath(path)

    def get_binder(self):
        from nxdrive.manager import ServerBindingSettings
        return ServerBindingSettings(server_url=self._server_url,
                        web_authentication=self._web_authentication,
                        server_version=None,
                        username=self._remote_user,
                        local_folder=self._local_folder,
                        initialized=True,
                        pwd_update_required=self.has_invalid_credentials())

    def get_local_folder(self):
        return self._local_folder

    def get_uid(self):
        return self._uid

    def set_invalid_credentials(self, value=True, reason=None, exception=None):
        changed = self._invalid_credentials != value
        self._invalid_credentials = value
        if value and changed:
            msg = 'Setting invalid credentials'
            if reason is not None:
                msg += ', reason is: %s' % reason
            log.error(msg, exc_info=exception is not None)
            self.invalidAuthentication.emit()

    def has_invalid_credentials(self):
        return self._invalid_credentials

    def get_queue_manager(self):
        return self._queue_manager

    def get_local_watcher(self):
        return self._local_watcher

    def get_remote_watcher(self):
        return self._remote_watcher

    def get_dao(self):
        return self._dao

    def local_rollback(self):
        return False

    def create_thread(self, worker=None, name=None, start_connect=True):
        if worker is None:
            worker = Worker(self, name=name)
        # If subclass of Processor then connect the newSync signal
        from nxdrive.engine.processor import Processor
        if isinstance(worker, Processor):
            worker.pairSync.connect(self.newSync)
        thread = worker.get_thread()
        if start_connect:
            thread.started.connect(worker.run)
        self._stop.connect(worker.quit)
        thread.finished.connect(self._thread_finished)
        self._threads.append(thread)
        return thread

    def retry_pair(self, row_id):
        state = self._dao.get_state_from_id(row_id)
        if state is None:
            return
        self._dao.reset_error(state)

    def unsynchronize_pair(self, row_id):
        state = self._dao.get_state_from_id(row_id)
        if state is None:
            return
        self._dao.synchronize_state(state, state='unsynchronized')
        self._dao.reset_error(state)

    def resolve_with_local(self, row_id):
        row = self._dao.get_state_from_id(row_id)
        self._dao.force_local(row)

    def resolve_with_remote(self, row_id):
        row = self._dao.get_state_from_id(row_id)
        self._dao.force_remote(row)

    def resolve_with_duplicate(self, row_id):
        row = self._dao.get_state_from_id(row_id)
        self._dao.increase_error(row, "DUPLICATING")
        from threading import Thread

        def run():
            local_client = self.get_local_client()
            # Duplicate the file
            local_client.duplicate_file(row.local_path)
            # Force the remote
            self._dao.force_remote(row)
        self._duplicate_thread = Thread(target=run)
        self._duplicate_thread.start()

    def get_last_sync(self):
        return self._dao.get_config("last_sync_date", None)

    @pyqtSlot()
    def _check_last_sync(self):
        from nxdrive.engine.watcher.local_watcher import WIN_MOVE_RESOLUTION_PERIOD
        empty_events = self._local_watcher.empty_events()
        blacklist_size = self._queue_manager.get_errors_count()
        qm_size = self._queue_manager.get_overall_size()
        qm_active = self._queue_manager.active()
        empty_polls = self._remote_watcher.get_metrics()["empty_polls"]
        if not AbstractOSIntegration.is_windows():
            win_info = 'not Windows'
        else:
            win_info = 'Windows with win queue size = %d and win folder scan size = %d' % (
                self._local_watcher.get_win_queue_size(), self._local_watcher.get_win_folder_scan_size())
        log.debug('Checking sync completed: queue manager is %s, overall size = %d, empty polls count = %d'
                  ', local watcher empty events = %d, blacklist = %d, %s',
                  'active' if qm_active else 'inactive', qm_size, empty_polls,
                    empty_events, blacklist_size, win_info)
        local_metrics = self._local_watcher.get_metrics()
        if (qm_size == 0 and not qm_active and empty_polls > 0
                and empty_events):
            if blacklist_size != 0:
                self.syncPartialCompleted.emit()
                return
            self._dao.update_config("last_sync_date", datetime.datetime.utcnow())
            if local_metrics['last_event'] == 0:
                log.warn("No watchdog event detected but sync is completed")
            if self._sync_started:
                self._sync_started = False
            log.debug('Emitting syncCompleted for engine %s', self.get_uid())
            self.syncCompleted.emit()

    def _thread_finished(self):
        for thread in self._threads:
            if thread == self._local_watcher._thread:
                continue
            if thread == self._remote_watcher._thread:
                continue
            if thread.isFinished():
                self._threads.remove(thread)

    def is_started(self):
        return not self._stopped

    def start(self):
        if not self.check_fs_marker():
            raise FsMarkerException()
        self._stopped = False
        Processor.soft_locks = dict()
        log.debug("Engine %s starting", self.get_uid())
        for thread in self._threads:
            thread.start()
        self.syncStarted.emit(0)
        self._start.emit()

    def get_threads(self):
        return self._threads

    def get_status(self):
        QCoreApplication.processEvents()
        log.debug("Engine status")
        for thread in self._threads:
            log.debug("%r" % thread.worker.get_metrics())
        log.debug("%r" % self._queue_manager.get_metrics())

    def get_metrics(self):
        metrics = dict()
        metrics["sync_folders"] = self._dao.get_sync_count(filetype="folder")
        metrics["sync_files"] = self._dao.get_sync_count(filetype="file")
        metrics["syncing"] = self._dao.get_syncing_count()
        metrics["error_files"] = self._dao.get_error_count()
        metrics["conflicted_files"] = self._dao.get_conflict_count()
        metrics["files_size"] = self._dao.get_global_size()
        metrics["invalid_credentials"] = self._invalid_credentials
        return metrics

    def get_conflicts(self):
        return self._dao.get_conflicts()

    def conflict_resolver(self, row_id):
        self._conflict_resolver(row_id)

    def _conflict_resolver(self, row_id, emit=True):
        try:
            pair = self._dao.get_state_from_id(row_id)
            local_client = self.get_local_client()
            parent_ref = local_client.get_remote_id(pair.local_parent_path)
            log.warn("conflict_resolver: name: %d digest: %d(%s/%s) parents: %d(%s/%s)", pair.remote_name == pair.local_name,
                      local_client.is_equal_digests(pair.local_digest, pair.remote_digest, pair.local_path),
                      pair.local_digest, pair.remote_digest,
                      pair.remote_parent_ref == parent_ref,
                      pair.remote_parent_ref, parent_ref)
            if (safe_filename(pair.remote_name) == pair.local_name
                and local_client.is_equal_digests(pair.local_digest, pair.remote_digest, pair.local_path)
                    and pair.remote_parent_ref == parent_ref):
                self._dao.synchronize_state(pair)
            elif emit:
                # Raise conflict only if not resolvable
                self.newConflict.emit(row_id)
        except Exception:
            pass

    def get_errors(self):
        return self._dao.get_errors()

    def is_stopped(self):
        return self._stopped

    def stop(self):
        self._stopped = True
        log.debug("Engine %s stopping", self._uid)
        self._stop.emit()
        for thread in self._threads:
            if not thread.wait(5000):
                log.warn("Thread is not responding - terminate it")
                thread.terminate()
        if not self._local_watcher._thread.wait(5000):
            self._local_watcher._thread.terminate()
        if not self._remote_watcher._thread.wait(5000):
            self._remote_watcher._thread.terminate()
        for thread in self._threads:
            if thread.isRunning():
                thread.wait(5000)
        if not self._remote_watcher._thread.isRunning():
            self._remote_watcher._thread.wait(5000)
        if not self._local_watcher._thread.isRunning():
            self._local_watcher._thread.wait(5000)
        # Soft locks needs to be reinit in case of threads termination
        Processor.soft_locks = dict()
        log.debug("Engine %s stopped", self._uid)

    def _get_client_cache(self):
        return self._remote_clients

    def use_trash(self):
        return True

    def get_update_infos(self, client=None):
        if client is None:
            client = self.get_remote_doc_client()
        if client is None:
            return
        update_info = client.get_update_info()
        log.debug("Fetched update info for engine [%s] from server %s: %r", self._name, self._server_url, update_info)
        self._dao.update_config("server_version", update_info.get("serverVersion"))
        self._dao.update_config("update_url", update_info.get("updateSiteURL"))
        beta_update_site_url = update_info.get("betaUpdateSiteURL")
        # Consider empty string as None
        if not beta_update_site_url:
            beta_update_site_url = None
        self._dao.update_config("beta_update_url", beta_update_site_url)

    def update_password(self, password):
        self._load_configuration()
        nxclient = self.remote_doc_client_factory(
            self._server_url, self._remote_user, self._manager.device_id,
            self._manager.client_version, proxies=self._manager.proxies,
            proxy_exceptions=self._manager.proxy_exceptions,
            password=str(password), timeout=self._handshake_timeout)
        self._remote_token = nxclient.request_token()
        if self._remote_token is None:
            raise Exception
        self._dao.update_config("remote_token", self._remote_token)
        self.set_invalid_credentials(False)
        self.invalidate_client_cache()
        # In case of a binding
        self._check_root()
        self.start()

    def update_token(self, token):
        self._load_configuration()
        self._remote_token = token
        self._dao.update_config("remote_token", self._remote_token)
        self.set_invalid_credentials(False)
        self.start()

    def bind(self, binder):
        check_credential = True
        if hasattr(binder, 'no_check') and binder.no_check:
            check_credential = False
        check_fs = self._manager.is_checkfs()
        if hasattr(binder, 'no_fscheck') and binder.no_fscheck:
            check_fs = False
        self._server_url = self._normalize_url(binder.url)
        self._remote_user = binder.username
        self._remote_password = binder.password
        self._remote_token = binder.token
        self._web_authentication = self._remote_token is not None
        if check_fs:
            created_folder = False
            try:
                if not os.path.exists(os.path.dirname(self._local_folder)):
                    raise NotFound()
                if not os.path.exists(self._local_folder):
                    os.mkdir(self._local_folder)
                    created_folder = True
                self._check_fs(self._local_folder)
            except Exception as e:
                try:
                    if created_folder:
                        os.rmdir(self._local_folder)
                except:
                    pass
                raise e
        nxclient = None
        if check_credential:
            nxclient = self.remote_doc_client_factory(
                self._server_url, self._remote_user, self._manager.device_id,
                self._manager.client_version, proxies=self._manager.proxies,
                proxy_exceptions=self._manager.proxy_exceptions,
                password=self._remote_password, token=self._remote_token,
                timeout=self._handshake_timeout)
            if self._remote_token is None:
                self._remote_token = nxclient.request_token()
        if self._remote_token is not None:
            # The server supports token based identification: do not store the
            # password in the DB
            self._remote_password = None
        # Save the configuration
        self._dao.update_config("web_authentication", self._web_authentication)
        self._dao.update_config("server_url", self._server_url)
        self._dao.update_config("remote_user", self._remote_user)
        self._dao.update_config("remote_password", self._remote_password)
        self._dao.update_config("remote_token", self._remote_token)
        if nxclient:
            self.get_update_infos(nxclient)
            # Check for the root
            # If the top level state for the server binding doesn't exist,
            # create the local folder and the top level state.
            self._check_root()

    def _check_fs(self, path):
        if not self._manager.get_osi().is_partition_supported(path):
            raise InvalidDriveException()
        if os.path.exists(path):
            local_client = self.get_local_client()
            root_id = local_client.get_root_id()
            if root_id is not None:
                # server_url|user|device_id|uid
                token = root_id.split("|")
                if (self._server_url != token[0] or self._remote_user != token[1]):
                    raise RootAlreadyBindWithDifferentAccount(token[1], token[0])

    def _check_root(self):
        root = self._dao.get_state_from_local("/")
        if root is None:
            from nxdrive.client.common import BaseClient
            if os.path.exists(self._local_folder):
                BaseClient.unset_path_readonly(self._local_folder)
            self._make_local_folder(self._local_folder)
            self._add_top_level_state()
            self._set_root_icon()
            BaseClient.set_path_readonly(self._local_folder)

    def _make_local_folder(self, local_folder):
        if not os.path.exists(local_folder):
            os.makedirs(local_folder)
            # OSI package
            # TODO self.register_folder_link(local_folder)
        # Put the ROOT in readonly

    def cancel_action_on(self, pair_id):
        for thread in self._threads:
            if hasattr(thread, "worker") and isinstance(thread.worker, Processor):
                pair = thread.worker._current_doc_pair
                if pair is not None and pair.id == pair_id:
                    thread.worker.quit()

    def get_local_client(self):
        client = LocalClient(self._local_folder, case_sensitive=self._case_sensitive)
        if self._case_sensitive is None and os.path.exists(self._local_folder):
            self._case_sensitive = client.is_case_sensitive()
        return client

    def get_server_version(self):
        return self._dao.get_config("server_version")

    def get_update_url(self):
        return self._dao.get_config("update_url", DEFAULT_UPDATE_SITE_URL)

    def get_beta_update_url(self):
        return self._dao.get_config("beta_update_url")

    @pyqtSlot()
    def invalidate_client_cache(self):
        log.debug("Invalidate client cache")
        self._remote_clients.clear()
        self.invalidClientsCache.emit()

    def _set_root_icon(self):
        local_client = self.get_local_client()
        if local_client.has_folder_icon('/'):
            return
        if AbstractOSIntegration.is_mac():
            if AbstractOSIntegration.os_version_below("10.10"):
                icon = find_icon("NuxeoDrive_Mac_Folder.dat")
            else:
                icon = find_icon("NuxeoDrive_Mac_Yosemite_Folder.dat")
        elif AbstractOSIntegration.is_windows():
            if AbstractOSIntegration.os_version_below("5.2"):
                icon = find_icon("NuxeoDrive_Windows_Xp_Folder.ico")
            else:
                icon = find_icon("NuxeoDrive_Windows_Folder.ico")
        else:
            # No implementation on Linux
            return
        locker = local_client.unlock_ref('/', unlock_parent=False)
        try:
            local_client.set_folder_icon('/', icon)
        finally:
            local_client.lock_ref('/', locker)

    def _add_top_level_state(self):
        local_client = self.get_local_client()
        local_info = local_client.get_info(u'/')

        remote_client = self.get_remote_client()
        remote_info = remote_client.get_filesystem_root_info()

        self._dao.insert_local_state(local_info, '')
        row = self._dao.get_state_from_local('/')
        self._dao.update_remote_state(row, remote_info, remote_parent_path='', versionned=False)
        local_client.set_root_id(self._server_url + "|" + self._remote_user +
                            "|" + self._manager.device_id + "|" + self._uid)
        local_client.set_remote_id('/', remote_info.uid)
        self._dao.synchronize_state(row)
        # The root should also be sync

    def suspend_client(self, reason):
        if self.is_paused() or self._stopped:
            raise ThreadInterrupt
        # Verify thread status
        thread_id = current_thread().ident
        for thread in self._threads:
            if hasattr(thread, "worker") and isinstance(thread.worker, Processor):
                if (thread.worker._thread_id == thread_id and
                        thread.worker._continue == False):
                    raise ThreadInterrupt
        # Get action
        current_file = None
        action = Action.get_current_action()
        if isinstance(action, FileAction):
            client = self.get_local_client()
            current_file = client.get_path(action.filepath)
        if (current_file is not None and self._folder_lock is not None
             and current_file.startswith(self._folder_lock)):
            log.debug("PairInterrupt '%s' because lock on '%s'",
                      current_file, self._folder_lock)
            raise PairInterrupt

    def complete_binder(self, row):
        # Add more information
        row.server_url = self._server_url
        row.username = self._remote_user
        row.has_invalid_credentials = self.has_invalid_credentials

    def get_remote_client(self, filtered=True):
        """Return a client for the FileSystem abstraction."""
        if self._invalid_credentials:
            return None
        cache = self._get_client_cache()

        cache_key = (self._manager.device_id, filtered)
        remote_client = cache.get(cache_key)
        if remote_client is None:
            if filtered:
                remote_client = self.remote_filtered_fs_client_factory(
                        self._server_url, self._remote_user,
                        self._manager.device_id, self.version, self._dao,
                        proxies=self._manager.proxies,
                        proxy_exceptions=self._manager.proxy_exceptions,
                        password=self._remote_password,
                        timeout=self.timeout, cookie_jar=self.cookie_jar,
                        token=self._remote_token, check_suspended=self.suspend_client)
            else:
                remote_client = self.remote_fs_client_factory(
                        self._server_url, self._remote_user,
                        self._manager.device_id, self.version,
                        proxies=self._manager.proxies,
                        proxy_exceptions=self._manager.proxy_exceptions,
                        password=self._remote_password,
                        timeout=self.timeout, cookie_jar=self.cookie_jar,
                        token=self._remote_token, check_suspended=self.suspend_client)
            cache[cache_key] = remote_client
        return remote_client

    def get_remote_doc_client(self, repository=DEFAULT_REPOSITORY_NAME, base_folder=None):
        if self._invalid_credentials:
            return None
        cache = self._get_client_cache()
        cache_key = (self._manager.device_id, 'remote_doc')
        remote_client = cache.get(cache_key)
        if remote_client is None:
            remote_client = self.remote_doc_client_factory(
                self._server_url, self._remote_user,
                self._manager.device_id, self.version,
                proxies=self._manager.proxies,
                proxy_exceptions=self._manager.proxy_exceptions,
                password=self._remote_password, token=self._remote_token,
                repository=repository, base_folder=base_folder,
                timeout=self._handshake_timeout, cookie_jar=self.cookie_jar, check_suspended=self.suspend_client)
            cache[cache_key] = remote_client
        return remote_client

    def create_processor(self, item_getter, name=None):
        from nxdrive.engine.processor import Processor
        return Processor(self, item_getter, name=name)

    def dispose_db(self):
        if self._dao is not None:
            self._dao.dispose()

    def get_rest_api_client(self):
        from nxdrive.client.rest_api_client import RestAPIClient
        rest_client = RestAPIClient(self.get_server_url(), self.get_remote_user(),
                                        self._manager.get_device_id(), self._manager.client_version, None,
                                        self.get_remote_token(), timeout=self.timeout, cookie_jar=self.cookie_jar)
        return rest_client

    def get_user_full_name(self, userid):
        """
            Get the last contributor full name
        """
        fullname = userid
        try:
            if userid in self._user_cache:
                fullname = self._user_cache[userid]
            else:
                rest_client = self.get_rest_api_client()
                response = rest_client.get_user_full_name(userid)
                if response and 'properties' in response:
                    properties = response['properties']
                    firstName = properties.get('firstName')
                    lastName = properties.get('lastName')
                    if firstName and lastName:
                        fullname = " ".join([firstName, lastName]).strip()
                        self._user_cache[userid] = fullname
        except urllib2.URLError as e:
            log.exception(e)
        return fullname
