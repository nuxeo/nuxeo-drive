from PyQt4.QtCore import QThread, QObject, QCoreApplication, pyqtSlot, pyqtSignal, QMutex
from threading import current_thread
from nxdrive.logging_config import get_logger
from nxdrive.client import LocalClient
from nxdrive.client import RemoteFileSystemClient
from nxdrive.client import RemoteFilteredFileSystemClient
from nxdrive.client import RemoteDocumentClient
from nxdrive.engine.activity import Action
from threading import local
from time import sleep
import os
from cookielib import CookieJar
#from nxdrive.engine.activity import Action.actions

log = get_logger(__name__)


class ThreadInterrupt(Exception):
    pass

'''
' Utility class that handle one thread
'''
class Worker(QObject):
    _thread = None
    _continue = True
    _action = None
    _name = None
    _thread_id = None
    _engine = None
    _pause = False
    action_update = pyqtSignal(object)

    def __init__(self, engine, thread=None, name=None):
        super(Worker, self).__init__()
        if thread is None:
            thread = QThread()
        self.moveToThread(thread)
        thread.worker = self
        self._thread = thread
        if name is None:
            name = type(self).__name__
        self._name = name
        self._engine = engine
        self._thread.terminated.connect(self._terminated)

    @pyqtSlot()
    def quit(self):
        self._continue = False

    def _end_action(self):
        Action.finish_action()
        self._action = None

    def resume(self):
        self._pause = False

    def pause(self):
        self._pause = True

    def get_thread(self):
        return self._thread

    def _interact(self):
        QCoreApplication.processEvents()
        # Handle thread pause
        while (self._pause and self._continue):
            QCoreApplication.processEvents()
            sleep(1)
        # Handle thread interruption
        if not self._continue:
            raise ThreadInterrupt()

    def _execute(self):
        pass

    def _terminated(self):
        log.debug("Thread %s(%d) terminated"
                    % (self._name, self._thread_id))

    def _update_action(self, action):
        self.action_update.emit(action)

    def get_metrics(self):
        metrics = dict()
        metrics['name'] = self._name
        metrics['thread_id'] = self._thread_id
        # Get action from activity as methods can have its own Action
        action = Action.get_current_action(self._thread_id)
        if action is None:
            action = self._action
        metrics['action'] = action
        if hasattr(self, '_metrics'):
            metrics = dict(metrics.items() + self._metrics.items())
        return metrics

    @pyqtSlot()
    def run(self):
        reason = ''
        self._thread_id = current_thread().ident
        try:
            self._execute()
            log.debug("Thread %s(%d) end"
                        % (self._name, self._thread_id))
        except ThreadInterrupt:
            log.debug("Thread %s(%d) interrupted"
                        % (self._name, self._thread_id))
            reason = 'interrupt'
        except Exception as e:
            log.warn("Thread %s(%d) ended with exception : %r"
                            % (self._name, self._thread_id, e))
            log.exception(e)
            reason = 'exception'
        self._clean(reason)
        self._thread.exit(0)

    def _clean(self, reason):
        pass

'''
' Just a DummyWorker with infinite loop
'''
class DummyWorker(Worker):
    def _execute(self):
        while (1):
            self._interact()
            sleep(1)


'''
' Just a CrazyWorker with infinite loop - no control
'''
class CrazyWorker(Worker):
    def _execute(self):
        while (1):
            sleep(1)

'''
' Just a DummyWorker with progression from 0 to 100
'''
class ProgressWorker(Worker):
    def _execute(self):
        self._progress = 0
        while (self._progress < 100):
            self._interact()
            self._progress = self._progress + 1
            sleep(1)

    def get_metrics(self):
        metrics = super(ProgressWorker, self).get_metrics()
        metrics['progress'] = self._progress
        return metrics


'''
' Used for threads interaction
'''
class Engine(QObject):
    _start = pyqtSignal()
    _stop = pyqtSignal()
    # Used for binding server / roots and managing tokens
    remote_doc_client_factory = RemoteDocumentClient

    # Used for FS synchronization operations
    remote_fs_client_factory = RemoteFileSystemClient
    # Used for FS synchronization operations
    remote_filtered_fs_client_factory = RemoteFilteredFileSystemClient
    version = "test"

    def __init__(self, manager, definition, binder=None, processors=5):
        super(Engine, self).__init__()
        self.timeout = 30
        self._handshake_timeout = 60
        # Make all the automation client related to this controller
        # share cookies using threadsafe jar
        self.cookie_jar = CookieJar()
        self._manager = manager
        # Remove remote client cache on proxy update
        self._manager.proxy_updated.connect(self.invalidate_client_cache)
        self._local_folder = definition.local_folder
        self._uid = definition.uid
        self._stopped = True
        self._local = local()
        self._threads = list()
        self._client_cache_timestamps = dict()
        self._dao = self._create_dao()
        if binder is not None:
            self.bind(binder)
        self._load_configuration()
        self.local_watcher = self.create_thread(worker=self._create_local_watcher())
        self.remote_watcher = self.create_thread(worker=self._create_remote_watcher(), start_connect=False)
        self.local_watcher.worker.localScanFinished.connect(self.remote_watcher.worker.run)
        self._queue_manager = self._create_queue_manager(processors)
        self.remote_watcher.worker.initiate.connect(self._queue_manager.init_processors)

    def _normalize_url(self, url):
        """Ensure that user provided url always has a trailing '/'"""
        if url is None or not url:
            raise ValueError("Invalid url: %r" % url)
        if not url.endswith(u'/'):
            return url + u'/'
        return url

    def _get_engine_db(self):
        return os.path.join(self._manager.get_configuration_folder(),
                                "engine_" + self._uid + ".db")

    def _load_configuration(self):
        self._server_url = self._dao.get_config("server_url")
        self._remote_user = self._dao.get_config("remote_user")
        self._remote_password = self._dao.get_config("remote_password")
        self._remote_token = self._dao.get_config("remote_token")
        self._device_id = self._manager.device_id

    def _create_queue_manager(self, processors):
        from nxdrive.engine.queue_manager import QueueManager
        return QueueManager(self, self._dao)

    def _create_remote_watcher(self):
        from nxdrive.engine.watcher.remote_watcher import RemoteWatcher
        return RemoteWatcher(self, self._dao)

    def _create_local_watcher(self):
        from nxdrive.engine.watcher.local_watcher import LocalWatcher
        return LocalWatcher(self, self._dao)

    def _create_dao(self):
        from nxdrive.engine.dao.sqlite import EngineDAO
        db = os.path.join(self._manager.get_configuration_folder(),
                                "ndrive_" + self._uid + ".db")
        return EngineDAO(db)

    def get_binder(self):
        from nxdrive.manager import ServerBindingSettings
        return ServerBindingSettings(server_url=self._server_url,
                        server_version=None,
                        username=self._remote_user,
                        local_folder=self._local_folder,
                        initialized=True,
                        pwd_update_required=self.has_invalid_credentials())

    def has_invalid_credentials(self):
        return False

    def get_queue_manager(self):
        return self._queue_manager

    def get_dao(self):
        return self._dao

    def local_rollback(self):
        return False

    def create_thread(self, worker=None, name=None, start_connect=True):
        if worker is None:
            worker = Worker(self, name=name)
        thread = worker.get_thread()
        if start_connect:
            thread.started.connect(worker.run)
        self._stop.connect(worker.quit)
        thread.finished.connect(self._thread_finished)
        self._threads.append(thread)
        return thread

    def _thread_finished(self):
        for thread in self._threads:
            if thread.isFinished():
                self._threads.remove(thread)

    def start(self):
        self._stopped = False
        log.debug("Engine start")
        for thread in self._threads:
            thread.start()
        self._start.emit()

    def get_status(self):
        QCoreApplication.processEvents()
        log.debug("Engine status")
        for thread in self._threads:
            log.debug("%r" % thread.worker.get_metrics())
        log.debug("%r" % self._queue_manager.get_metrics())

    def is_paused(self):
        return False

    def is_stopped(self):
        return self._stopped

    def stop(self):
        self._stopped = True
        log.debug("Engine stopping")
        self._stop.emit()
        for thread in self._threads:
            if not thread.wait(3000):
                log.warn("Thread is not responding - terminate it")
                thread.terminate()
        log.debug("Engine stopped")
        # For test purpose only should be remove
        QCoreApplication.exit()

    def _get_client_cache(self):
        if not hasattr(self._local, 'remote_clients'):
            self._local.remote_clients = dict()
        return self._local.remote_clients

    def use_trash(self):
        return True

    def bind(self, binder):
        self._server_url = self._normalize_url(binder.url)
        self._remote_user = binder.username
        self._remote_password = binder.password
        nxclient = self.remote_doc_client_factory(
            self._server_url, self._remote_user, self._manager.device_id,
            self._manager.client_version, proxies=self._manager.proxies,
            proxy_exceptions=self._manager.proxy_exceptions,
            password=self._remote_password, timeout=self._handshake_timeout)
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
        # Check for the root
        # If the top level state for the server binding doesn't exist,
        # create the local folder and the top level state. This can be
        # the case when initializing the DB manually with a SQL script.
        root = self._dao.get_state_from_local("/")
        if root is None:
            from nxdrive.client.common import BaseClient
            BaseClient.unset_path_readonly(self._local_folder)
            self._make_local_folder(self._local_folder)
            self._add_top_level_state()
            BaseClient.set_path_readonly(self._local_folder)
            # TODO Set update info
            # self._set_update_info(server_binding, remote_client=nxclient)

    def _make_local_folder(self, local_folder):
        if not os.path.exists(local_folder):
            os.makedirs(local_folder)
            # OSI package
            # TODO self.register_folder_link(local_folder)
        # Put the ROOT in readonly

    def get_local_client(self):
        return LocalClient(self._local_folder)

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
        local_client.set_root_id(self._server_url + "|" + self._remote_user + "|" +
                                    self._manager.device_id + "|" + self._uid)
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
                        self._server_url, self._remote_user, self._manager.device_id,
                        self.version, self._dao,
                        proxies=self._manager.proxies,
                        proxy_exceptions=self._manager.proxy_exceptions,
                        password=self._remote_password, token=self._remote_token,
                        timeout=self.timeout, cookie_jar=self.cookie_jar,
                        check_suspended=None)
            else:
                remote_client = self.remote_fs_client_factory(
                        self._server_url, self._remote_user, self._manager.device_id,
                        self.version,
                        proxies=self._manager.proxies,
                        proxy_exceptions=self._manager.proxy_exceptions,
                        password=self._remote_password, token=self._remote_token,
                        timeout=self.timeout, cookie_jar=self.cookie_jar,
                        check_suspended=None)
            if client_cache_timestamp is None:
                client_cache_timestamp = 0
                self._client_cache_timestamps[cache_key] = 0
            cache[cache_key] = remote_client, client_cache_timestamp
        return cache[cache_key][0]
