from PyQt4.QtCore import QThread, QObject, QCoreApplication, QTimer, pyqtSlot, pyqtSignal, QMutex
import sys
from threading import current_thread
from nxdrive.logging_config import get_logger, configure
from nxdrive.client import LocalClient
from nxdrive.client import RemoteFileSystemClient
from nxdrive.client import RemoteFilteredFileSystemClient
from nxdrive.client import RemoteDocumentClient
from threading import local
from time import sleep
from cookielib import CookieJar

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
        metrics['action'] = self._action
        if hasattr(self, '_metrics'):
            metrics = dict(metrics.items() + self._metrics.items())
        return metrics

    @pyqtSlot()
    def run(self):
        self._thread_id = current_thread().ident
        try:
            self._execute()
            log.debug("Thread %s(%d) end"
                        % (self._name, self._thread_id))
        except ThreadInterrupt:
            log.debug("Thread %s(%d) interrupted"
                        % (self._name, self._thread_id))
            pass
        except Exception as e:
            log.warn("Thread %s(%d) ended with exception : %r"
                            % (self._name, self._thread_id, e))
            log.exception(e)
        self._thread.exit(0)


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

    def __init__(self, local_folder, processors=5):
        super(Engine, self).__init__()
        self.timeout = 30
        self.proxies = None
        self.proxy_exceptions = None
        # Make all the automation client related to this controller
        # share cookies using threadsafe jar
        self.cookie_jar = CookieJar()
        from nxdrive.engine.watcher.local_watcher import LocalWatcher
        from nxdrive.engine.watcher.remote_watcher import RemoteWatcher
        from nxdrive.engine.dao.sqlite import SqliteDAO
        self._local_folder = local_folder
        self._local = local()
        self._client_cache_timestamps = dict()
        self._dao = self.create_thread(worker=SqliteDAO(self, '/tmp/test.db'))
        #LocalWatcher(None, None, None)
        self.local_watcher = self.create_thread(worker=LocalWatcher(self, self._dao.worker))
        self.remote_watcher = self.create_thread(worker=RemoteWatcher(self, self._dao.worker), start_connect=False)
        self.local_watcher.worker.localScanFinished.connect(self.remote_watcher.worker.run)
        self.queue_manager = self.create_thread()
        self.queue_processors = list()
        for i in range(0, processors):
            self.queue_processors.append(self.create_thread())
        self.gui = self.create_thread()
        self.threads = list()
        self.threads.append(self._dao)
        self.threads.append(self.local_watcher)
        self.threads.append(self.remote_watcher)
        self.threads.append(self.queue_manager)
        for processor in self.queue_processors:
            self.threads.append(processor)
        self.threads.append(self.gui)

    def create_thread(self, worker=None, name=None, start_connect=True):
        if worker is None:
            worker = Worker(self, name=name)
        if start_connect:
            self._start.connect(worker.run)
        self._stop.connect(worker.quit)
        worker.get_thread().finished.connect(self._thread_finished)
        return worker._thread

    def _thread_finished(self):
        for thread in self.threads:
            if thread.isFinished():
                self.threads.remove(thread)

    @staticmethod
    def bind_server(self, local_folder, server_url, username, password):
        """Bind a local folder to a remote nuxeo server"""
        session = self.get_session()
        local_folder = normalized_path(local_folder)

        # check the connection to the server by issuing an authentication
        # request
        server_url = self._normalize_url(server_url)
        nxclient = self.remote_doc_client_factory(
            server_url, username, self.device_id, self.version,
            proxies=self.proxies, proxy_exceptions=self.proxy_exceptions,
            password=password, timeout=self.handshake_timeout)
        token = nxclient.request_token()
        if token is not None:
            # The server supports token based identification: do not store the
            # password in the DB
            password = None
        try:
            try:
                # Look for an existing server binding for the given local
                # folder
                server_binding = session.query(ServerBinding).filter(
                    ServerBinding.local_folder == local_folder).one()
                if server_binding.server_url != server_url:
                    raise RuntimeError(
                        "%s is already bound to '%s'" % (
                            local_folder, server_binding.server_url))

                if server_binding.remote_user != username:
                    # Update username info if required
                    server_binding.remote_user = username
                    log.info("Updating username to '%s' on server '%s'",
                            username, server_url)

                if (token is None
                    and server_binding.remote_password != password):
                    # Update password info if required
                    server_binding.remote_password = password
                    log.info("Updating password for user '%s' on server '%s'",
                            username, server_url)

                if token is not None and server_binding.remote_token != token:
                    log.info("Updating token for user '%s' on server '%s'",
                            username, server_url)
                    # Update the token info if required
                    server_binding.remote_token = token

                    # Ensure that the password is not stored in the DB
                    if server_binding.remote_password is not None:
                        server_binding.remote_password = None

                # If the top level state for the server binding doesn't exist,
                # create the local folder and the top level state. This can be
                # the case when initializing the DB manually with a SQL script.
                try:
                    self.get_top_level_state(local_folder, session=session)
                except NoResultFound:
                    self._make_local_folder(local_folder)
                    self._add_top_level_state(server_binding, session)

            except NoResultFound:
                # No server binding found for the given local folder
                # First create local folder in the file system
                self._make_local_folder(local_folder)

                # Create ServerBinding instance in DB
                log.info("Binding '%s' to '%s' with account '%s'",
                         local_folder, server_url, username)
                server_binding = ServerBinding(local_folder, server_url,
                                               username,
                                               remote_password=password,
                                               remote_token=token)
                session.add(server_binding)

                # Create the top level state for the server binding
                self._add_top_level_state(server_binding, session)

            # Set update info
            self._set_update_info(server_binding, remote_client=nxclient)

        except:
            # In case an AddonNotInstalled exception is raised, need to
            # invalidate the remote client cache for it to be aware of the new
            # operations when the addon gets installed
            if server_binding is not None:
                self.invalidate_client_cache(server_binding.server_url)
            session.rollback()
            raise

        session.commit()
        return server_binding

    def start(self):
        log.debug("Engine start")
        for thread in self.threads:
            thread.start()
        self._start.emit()

    def get_status(self):
        log.debug("Engine status")
        for thread in self.threads:
            log.debug("%r" % thread.worker.get_metrics())
        QTimer.singleShot(30000, self.get_status)

    def stop(self):
        log.debug("Engine stopping")
        self._stop.emit()
        for thread in self.threads:
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

    def get_local_client(self):
        return LocalClient(self._local_folder)

    def _add_top_level_state(self):
        local_client = self.get_local_client()
        local_info = local_client.get_info(u'/')

        remote_client = self.get_remote_client()
        remote_info = remote_client.get_filesystem_root_info()

        self._dao.worker.insert_local_state(local_info, '')
        self._dao.worker.commit()
        row = self._dao.worker.get_state_from_local('/')
        self._dao.worker.update_remote_state(row, remote_info, '')
        # Use version+1 as we just update the remote info
        self._dao.worker.synchronize_state(row, row.version + 1)
        self._dao.worker.commit()
        # The root should also be sync
        #state.update_state('synchronized', 'synchronized')

    def get_remote_client(self, filtered=True):
        """Return a client for the FileSystem abstraction."""
        cache = self._get_client_cache()
        server_url = "http://localhost:8080/nuxeo/"
        remote_user = "Administrator"
        device_id = "Alpha-Engine-2.0"
        remote_password = "Administrator"
        remote_token = None
        cache_key = (server_url, remote_user, device_id, filtered)
        remote_client_cache = cache.get(cache_key)
        if remote_client_cache is not None:
            remote_client = remote_client_cache[0]
            timestamp = remote_client_cache[1]
        client_cache_timestamp = self._client_cache_timestamps.get(cache_key)

        if remote_client_cache is None or timestamp < client_cache_timestamp:
            if filtered:
                remote_client = self.remote_filtered_fs_client_factory(
                        server_url, remote_user, device_id,
                        self.version, None,
                        proxies=self.proxies,
                        proxy_exceptions=self.proxy_exceptions,
                        password=remote_password, token=remote_token,
                        timeout=self.timeout, cookie_jar=self.cookie_jar,
                        check_suspended=None)
            else:
                remote_client = self.remote_fs_client_factory(
                        server_url, remote_user, device_id,
                        self.version, None,
                        proxies=self.proxies,
                        proxy_exceptions=self.proxy_exceptions,
                        password=remote_password, token=remote_token,
                        timeout=self.timeout, cookie_jar=self.cookie_jar,
                        check_suspended=None)
            if client_cache_timestamp is None:
                client_cache_timestamp = 0
                self._client_cache_timestamps[cache_key] = 0
            cache[cache_key] = remote_client, client_cache_timestamp
        return cache[cache_key][0]

if __name__ == "__main__":
    configure(console_level='TRACE')
    core = QCoreApplication(sys.argv)
    benchmark = u'/Users/looping/nuxeo/sources/nuxeo/addons/nuxeo-drive/tools/benchmark/benchmark_files_local'
    benchmark_remote = u'/Users/looping/nuxeo/sources/nuxeo/addons/nuxeo-drive/tools/benchmark/benchmark_files_remote'
    engine = Engine(benchmark)
    #remote = engine.get_remote_client(True)
    #local = LocalClient(benchmark_remote)
    #from nxdrive.utils import ServerLoader
    #load = ServerLoader(remote, local)
    #load.sync('defaultSyncRootFolderItemFactory#default#238b460a-d4e3-4bde-8849-debadb805d8a', '/')
    #sys.exit()
    root = engine._dao.worker.get_state_from_local('/')
    if root is None:
        engine._add_top_level_state()
    #engine.remote_watcher.worker._execute()
    QTimer.singleShot(20000, engine.get_status)
    QTimer.singleShot(480000, engine.stop)
    engine.start()
    core.exec_()
