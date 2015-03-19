from PyQt4.QtCore import QObject, QCoreApplication
from PyQt4.QtCore import pyqtSlot, pyqtSignal
from nxdrive.logging_config import get_logger
from nxdrive.commandline import DEFAULT_REMOTE_WATCHER_DELAY
from nxdrive.commandline import DEFAULT_UPDATE_SITE_URL
from nxdrive.client.common import DEFAULT_REPOSITORY_NAME
from nxdrive.client import LocalClient
from nxdrive.client import RemoteFileSystemClient
from nxdrive.client import RemoteFilteredFileSystemClient
from nxdrive.client import RemoteDocumentClient
from nxdrive.utils import normalized_path
from nxdrive.utils import current_milli_time
from nxdrive.engine.workers import Worker
from threading import local
import os
import datetime
from cookielib import CookieJar
#from nxdrive.engine.activity import Action.actions

log = get_logger(__name__)


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
        log.log(self._level, "Synchronization is complete")

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
    _start = pyqtSignal()
    _stop = pyqtSignal()
    _scanPair = pyqtSignal(str)
    syncStarted = pyqtSignal(object)
    syncCompleted = pyqtSignal()
    syncSuspended = pyqtSignal()
    syncResumed = pyqtSignal()
    invalidAuthentication = pyqtSignal()
    newConflict = pyqtSignal(object)
    newSync = pyqtSignal(object, object)
    newError = pyqtSignal(object)
    newQueueItem = pyqtSignal(object)
    version = "test"

    def __init__(self, manager, definition, binder=None, processors=5,
                 remote_watcher_delay=DEFAULT_REMOTE_WATCHER_DELAY,
                 remote_doc_client_factory=RemoteDocumentClient,
                 remote_fs_client_factory=RemoteFileSystemClient,
                 remote_filtered_fs_client_factory=RemoteFilteredFileSystemClient):
        super(Engine, self).__init__()

        # Used for binding server / roots and managing tokens
        self.remote_doc_client_factory = remote_doc_client_factory

        # Used for FS synchronization operations
        self.remote_fs_client_factory = remote_fs_client_factory
        # Used for FS synchronization operations
        self.remote_filtered_fs_client_factory = remote_filtered_fs_client_factory
        # Stop if invalid credentials
        self.invalidAuthentication.connect(self.stop)

        self.timeout = 30
        self._handshake_timeout = 60
        # Make all the automation client related to this controller
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
        self._local = local()
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
        self._local_watcher.localScanFinished.connect(self._remote_watcher.run)
        self._queue_manager = self._create_queue_manager(processors)
        # Launch queue processors after first remote_watcher pass
        self._remote_watcher.initiate.connect(self._queue_manager.init_processors)
        # Connect last_sync checked
        self._remote_watcher.updated.connect(self._check_last_sync)
        # Connect for sync start
        self.newQueueItem.connect(self._check_sync_start)
        self._queue_manager.newItem.connect(self._check_sync_start)
        # Connect components signals to engine signals
        self._queue_manager.newItem.connect(self.newQueueItem)
        self._queue_manager.newError.connect(self.newError)
        self._dao.newConflict.connect(self.newConflict)
        # Scan in remote_watcher thread
        self._scanPair.connect(self._remote_watcher.scan_pair)

    @pyqtSlot(object)
    def _check_sync_start(self, row_id):
        if not self._sync_started:
            queue_size = self._queue_manager.get_overall_size()
            if queue_size > 0:
                self._sync_started = True
                self.syncStarted.emit(queue_size)

    def get_last_files(self, number, direction=None):
        return self._dao.get_last_files(number, direction)

    def add_filter(self, path):
        remote_ref = os.path.basename(path)
        remote_parent_path = os.path.dirname(path)
        if remote_ref is None:
            return
        self._dao.add_filter(path)
        pair = self._dao.get_state_from_remote_with_path(remote_ref, remote_parent_path)
        if pair is None:
            return
        self._dao.delete_remote_state(pair)

    def remove_filter(self, path):
        self.get_dao().remove_filter(path)
        # Scan the "new" pair, use signal/slot to not block UI
        self._scanPair.emit(path)

    def is_syncing(self):
        return self._sync_started

    def is_paused(self):
        return self._pause

    def open_edit(self, remote_ref):
        doc_ref = remote_ref
        if "#" in doc_ref:
            doc_ref = doc_ref[doc_ref.rfind('#'):]
        log.debug("Will try to open edit : %s", doc_ref)
        # TODO Implement a TemporaryWorker
        from threading import Thread

        def run():
            self._manager.get_drive_edit().edit(self._server_url,
                                                doc_ref, self._remote_user)
        self._edit_thread = Thread(target=run)
        self._edit_thread.start()

    def open_remote(self, url=None):
        if url is None:
            url = self.get_remote_url()
        self._manager.open_local_file(url)

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
        self._dao.dispose()
        # Remove DB
        log.debug("Remove DB file %s", self._get_db_file())
        os.remove(self._get_db_file())
        return

    def check_fs_marker(self):
        tag = 'drive-fs-test'
        tag_value = 'NXDRIVE_VERIFICATION'
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
        self._server_url = self._dao.get_config("server_url")
        self._remote_user = self._dao.get_config("remote_user")
        self._remote_password = self._dao.get_config("remote_password")
        self._remote_token = self._dao.get_config("remote_token")
        self._device_id = self._manager.device_id

    def get_server_url(self):
        return self._dao.get_config("server_url")

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
                        server_version=None,
                        username=self._remote_user,
                        local_folder=self._local_folder,
                        initialized=True,
                        pwd_update_required=self.has_invalid_credentials())

    def get_local_folder(self):
        return self._local_folder

    def set_invalid_credentials(self, value=True):
        changed = self._invalid_credentials != value
        self._invalid_credentials = value
        if value and changed:
            self.invalidAuthentication.emit()

    def has_invalid_credentials(self):
        return self._invalid_credentials

    def get_queue_manager(self):
        return self._queue_manager

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
        log.debug('Checking sync completed: queue manager is %s and overall size = %d',
                  'active' if self._queue_manager.active() else 'inactive', self._queue_manager.get_overall_size())
        local_metrics = self._local_watcher.get_metrics()
        if (self._queue_manager.get_overall_size() == 0 and not self._queue_manager.active()
            and self._remote_watcher.get_metrics()["empty_polls"] > 0 and
            (current_milli_time() - local_metrics["last_event"]) > WIN_MOVE_RESOLUTION_PERIOD):
            self._dao.update_config("last_sync_date", datetime.datetime.utcnow())
            if local_metrics['last_event'] == 0:
                log.warn("No watchdog event detected but sync is completed")
            if self._sync_started:
                self._sync_started = False
            log.debug('Emitting syncCompleted')
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
        log.debug("Engine start")
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
        metrics["error_files"] = self._dao.get_error_count()
        metrics["conflicted_files"] = self._dao.get_conflict_count()
        metrics["files_size"] = self._dao.get_global_size()
        metrics["invalid_credentials"] = self._invalid_credentials
        return metrics

    def get_conflicts(self):
        return self._dao.get_conflicts()

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
        for thread in self._threads:
            if thread.isRunning():
                thread.wait(5000)
        log.debug("Engine %s stopped", self._uid)

    def _get_client_cache(self):
        if not hasattr(self._local, 'remote_clients'):
            self._local.remote_clients = dict()
        return self._local.remote_clients

    def use_trash(self):
        return True

    def get_update_infos(self, client=None):
        if client is None:
            client = self.get_remote_doc_client()
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
        self.start()

    def bind(self, binder):
        self._server_url = self._normalize_url(binder.url)
        self._remote_user = binder.username
        self._remote_password = binder.password
        self._remote_token = None
        if hasattr(binder, 'token'):
            self._remote_token = binder.token
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
        self._dao.update_config("server_url", self._server_url)
        self._dao.update_config("remote_user", self._remote_user)
        self._dao.update_config("remote_password", self._remote_password)
        self._dao.update_config("remote_token", self._remote_token)
        self.get_update_infos(nxclient)
        # Check for the root
        # If the top level state for the server binding doesn't exist,
        # create the local folder and the top level state. This can be
        # the case when initializing the DB manually with a SQL script.
        root = self._dao.get_state_from_local("/")
        if root is None:
            from nxdrive.client.common import BaseClient
            if os.path.exists(self._local_folder):
                BaseClient.unset_path_readonly(self._local_folder)
            self._make_local_folder(self._local_folder)
            self._add_top_level_state()
            BaseClient.set_path_readonly(self._local_folder)

    def _make_local_folder(self, local_folder):
        if not os.path.exists(local_folder):
            os.makedirs(local_folder)
            # OSI package
            # TODO self.register_folder_link(local_folder)
        # Put the ROOT in readonly

    def cancel_action_on(self, doc_pair, recursive=True):
        from nxdrive.engine.processor import Processor
        for thread in self._threads:
            if isinstance(thread, Processor):
                pair = thread._current_doc_pair
                if pair.local_path.starts_with(doc_pair.local_path):
                    thread.quit()

    def get_local_client(self):
        return LocalClient(self._local_folder)

    def get_server_version(self):
        return self._dao.get_config("server_version")

    def get_update_url(self):
        return self._dao.get_config("update_url", DEFAULT_UPDATE_SITE_URL)

    def get_beta_update_url(self):
        return self._dao.get_config("beta_update_url")

    @pyqtSlot()
    def invalidate_client_cache(self):
        self._client_cache_timestamps.clear()

    def _add_top_level_state(self):
        local_client = self.get_local_client()
        local_info = local_client.get_info(u'/')

        remote_client = self.get_remote_client()
        remote_info = remote_client.get_filesystem_root_info()

        self._dao.insert_local_state(local_info, '')
        row = self._dao.get_state_from_local('/')
        self._dao.update_remote_state(row, remote_info, '', versionned=False)
        local_client.set_root_id(self._server_url + "|" + self._remote_user +
                            "|" + self._manager.device_id + "|" + self._uid)
        # Use version+1 as we just update the remote info
        self._dao.synchronize_state(row)
        # The root should also be sync

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
        remote_client_cache = cache.get(cache_key)
        if remote_client_cache is not None:
            remote_client = remote_client_cache[0]
            timestamp = remote_client_cache[1]
        client_cache_timestamp = self._client_cache_timestamps.get(cache_key)

        if remote_client_cache is None or timestamp < client_cache_timestamp:
            if filtered:
                remote_client = self.remote_filtered_fs_client_factory(
                        self._server_url, self._remote_user,
                        self._manager.device_id, self.version, self._dao,
                        proxies=self._manager.proxies,
                        proxy_exceptions=self._manager.proxy_exceptions,
                        password=self._remote_password,
                        timeout=self.timeout, cookie_jar=self.cookie_jar,
                        token=self._remote_token, check_suspended=None)
            else:
                remote_client = self.remote_fs_client_factory(
                        self._server_url, self._remote_user,
                        self._manager.device_id, self.version,
                        proxies=self._manager.proxies,
                        proxy_exceptions=self._manager.proxy_exceptions,
                        password=self._remote_password,
                        timeout=self.timeout, cookie_jar=self.cookie_jar,
                        token=self._remote_token, check_suspended=None)
            if client_cache_timestamp is None:
                client_cache_timestamp = 0
                self._client_cache_timestamps[cache_key] = 0
            cache[cache_key] = remote_client, client_cache_timestamp
        return cache[cache_key][0]

    def get_remote_doc_client(self, repository=DEFAULT_REPOSITORY_NAME, base_folder=None):
        return self.remote_doc_client_factory(
            self._server_url, self._remote_user,
            self._manager.device_id, self.version,
            proxies=self._manager.proxies,
            proxy_exceptions=self._manager.proxy_exceptions,
            password=self._remote_password, token=self._remote_token,
            repository=repository, base_folder=base_folder,
            timeout=self.timeout, cookie_jar=self.cookie_jar)

    def create_processor(self, item_getter, name=None):
        from nxdrive.engine.processor import Processor
        return Processor(self, item_getter, name=name)
