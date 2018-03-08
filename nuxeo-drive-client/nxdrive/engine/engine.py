# coding: utf-8
import datetime
import os
import urllib2
from cookielib import CookieJar
from logging import getLogger
from threading import Thread, current_thread
from time import sleep

from PyQt4.QtCore import QCoreApplication, QObject, pyqtSignal, pyqtSlot

from nxdrive.client import (LocalClient, RemoteDocumentClient,
                            RemoteFileSystemClient,
                            RemoteFilteredFileSystemClient)
from nxdrive.client.base_automation_client import Unauthorized
from nxdrive.client.common import BaseClient, NotFound, safe_filename
from nxdrive.client.rest_api_client import RestAPIClient
from nxdrive.engine.activity import Action, FileAction
from nxdrive.engine.dao.sqlite import EngineDAO
from nxdrive.engine.processor import Processor
from nxdrive.engine.queue_manager import QueueManager
from nxdrive.engine.watcher.local_watcher import LocalWatcher
from nxdrive.engine.watcher.remote_watcher import RemoteWatcher
from nxdrive.engine.workers import PairInterrupt, ThreadInterrupt, Worker
from nxdrive.options import Options
from nxdrive.osi import AbstractOSIntegration
from nxdrive.utils import find_icon, normalized_path

log = getLogger(__name__)


class InvalidDriveException(Exception):
    pass


class RootAlreadyBindWithDifferentAccount(Exception):

    def __init__(self, username, url):
        self.username = username
        self.url = url


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
    noSpaceLeftOnDevice = pyqtSignal()
    invalidAuthentication = pyqtSignal()
    invalidClientsCache = pyqtSignal()
    newConflict = pyqtSignal(object)
    newReadonly = pyqtSignal(object, object)
    deleteReadonly = pyqtSignal(object)
    newLocked = pyqtSignal(object, object, object)
    newSync = pyqtSignal(object, object)
    newError = pyqtSignal(object)
    newQueueItem = pyqtSignal(object)
    offline = pyqtSignal()
    online = pyqtSignal()

    type = 'NXDRIVE'

    def __init__(self, manager, definition, binder=None, processors=5,
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
        self.local_folder = definition.local_folder
        self.uid = definition.uid
        self.name = definition.name
        self._stopped = True
        self._pause = False
        self._sync_started = False
        self._invalid_credentials = False
        self._offline_state = False
        self._threads = list()
        self._dao = EngineDAO(self._get_db_file())
        if binder is not None:
            self.bind(binder)
        self._load_configuration()
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
            self.conflict_resolver(conflict.id, emit=False)
        # Scan in remote_watcher thread
        self._scanPair.connect(self._remote_watcher.scan_pair)
        # Set the root icon
        self._set_root_icon()
        # Set user full name
        self._user_cache = dict()
        # Pause in case of no more space on the device
        self.noSpaceLeftOnDevice.connect(self.suspend)

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
            log.trace('Quitting processor: %r as requested to stop on %r', worker, path)
            worker.quit()

    def set_local_folder(self, path):
        log.debug("Update local folder to '%s'", path)
        self.local_folder = path
        self._local_watcher.stop()
        self._create_local_watcher()
        self._manager.update_engine_path(self.uid, path)

    def set_local_folder_lock(self, path):
        self._folder_lock = path
        # Check for each processor
        log.debug('Local Folder locking on %r', path)
        while self.get_queue_manager().has_file_processors_on(path):
            log.trace("Local folder locking wait for file processor to finish")
            sleep(1)
        log.debug('Local Folder lock setup completed on %r', path)

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
            log.debug("Engine %s goes offline", self.uid)
            self._queue_manager.suspend()
            self.offline.emit()
        else:
            log.debug("Engine %s goes online", self.uid)
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
            log.debug('Cannot find the pair: %s (%r)', remote_ref, remote_parent_path)
            return
        self._dao.delete_remote_state(pair)

    def remove_filter(self, path):
        self.get_dao().remove_filter(path)
        # Scan the "new" pair, use signal/slot to not block UI
        self._scanPair.emit(path)

    def get_metadata_url(self, remote_ref):
        """
        Build the document's metadata URL based on the server's UI.
        Default is Web-UI.  In case of unknown UI, use the default value.

        :param str remote_ref: The document remote reference (UID) of the
            document we want to show metadata.
        :return str: The complete URL.
        """

        urls = {
            'jsf': '{server}nxdoc/{repo}/{uid}/view_documents?token={token}',
            'web': '{server}ui?token={token}#!/doc/{uid}',
        }

        remote_ref_segments = remote_ref.split('#', 2)
        infos = {
            'server': self.server_url,
            'repo': remote_ref_segments[1],
            'uid': remote_ref_segments[2],
            'token': self.get_remote_token(),
        }
        return urls.get(Options.ui, 'web').format(**infos)

    def get_remote_url(self):
        """
        Build the server's URL based on the server's UI.
        Default is Web-UI.  In case of unknown UI, use the default value.

        :return str: The complete URL.
        """

        urls = {
            'jsf': '{server}nxhome/{repo}/default-domain@view_home?tabIds=USER_CENTER%3AuserCenterNuxeoDrive',
            'web': '{server}ui?token={token}#!/drive',
        }

        infos = {
            'server': self.server_url,
            'repo': Options.remote_repo,
            'token': self.get_remote_token(),
        }
        return urls.get(Options.ui, 'web').format(**infos)

    def is_syncing(self):
        return self._sync_started

    def is_paused(self):
        return self._pause

    def open_edit(self, remote_ref, remote_name):
        doc_ref = remote_ref
        if '#' in doc_ref:
            doc_ref = doc_ref[doc_ref.rfind('#') + 1:]
        log.debug('Will try to open edit : %s', doc_ref)
        # TODO Implement a TemporaryWorker

        def run():
            self._manager.direct_edit.edit(
                self._server_url,
                doc_ref,
                user=self._remote_user,
            )
        self._edit_thread = Thread(target=run)
        self._edit_thread.start()

    def open_remote(self, url=None):
        if url is None:
            url = self.get_remote_url()
        self._manager.open_local_file(url)

    def resume(self):
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
            doc_client = self.get_remote_doc_client()
            if doc_client:
                doc_client.revoke_token()
        except Unauthorized:
            # Token already revoked
            # The exception can happened in both get_remote_doc_client()
            # and revoke_token()
            pass
        except:
            log.exception('Unbind error')

        self.dispose_db()
        log.debug('Remove DB file %r', self._get_db_file())
        try:
            os.remove(self._get_db_file())
        except (IOError, OSError) as exc:
            if exc.errno != 2:  # File not found, already removed
                log.exception('Database removal error')

        self._manager.osi.unregister_folder_link(self.local_folder)

    def check_fs_marker(self):
        tag = 'drive-fs-test'
        tag_value = 'NXDRIVE_VERIFICATION'
        if not os.path.exists(self.local_folder):
            self.rootDeleted.emit()
            return False
        client = self.get_local_client()
        client.set_remote_id('/', tag_value, tag)
        if client.get_remote_id('/', tag) != tag_value:
            return False
        client.remove_remote_id('/', tag)
        return client.get_remote_id('/', tag) is None

    @staticmethod
    def _normalize_url(url):
        """Ensure that user provided url always has a trailing '/'"""
        if not url:
            raise ValueError('Invalid url: %r' % url)
        if not url.endswith(u'/'):
            return url + u'/'
        return url

    def _load_configuration(self):
        self._web_authentication = self._dao.get_config('web_authentication', '0') == '1'
        self._server_url = self._dao.get_config('server_url')
        self._remote_user = self._dao.get_config('remote_user')
        self._remote_password = self._dao.get_config('remote_password')
        self._remote_token = self._dao.get_config('remote_token')
        if self._remote_password is None and self._remote_token is None:
            self.set_invalid_credentials(
                reason='found no password nor token in engine configuration')

    @property
    def server_url(self):
        return self._dao.get_config('server_url')

    @property
    def remote_user(self):
        return self._dao.get_config('remote_user')

    def get_remote_token(self):
        return self._dao.get_config("remote_token")

    def _create_queue_manager(self, processors):
        kwargs = {}
        if Options.debug:
            kwargs['max_file_processors'] = 2

        return QueueManager(self, self._dao, **kwargs)

    def _create_remote_watcher(self, delay):
        return RemoteWatcher(self, self._dao, delay)

    def _create_local_watcher(self):
        return LocalWatcher(self, self._dao)

    def _get_db_file(self):
        return os.path.join(normalized_path(self._manager.nxdrive_home),
                            'ndrive_' + self.uid + '.db')

    def get_abspath(self, path):
        return self.get_local_client().abspath(path)

    def get_binder(self):
        return ServerBindingSettings(
            server_url=self._server_url,
            web_authentication=self._web_authentication,
            username=self._remote_user,
            local_folder=self.local_folder,
            initialized=True,
            pwd_update_required=self.has_invalid_credentials())

    def set_invalid_credentials(self, value=True, reason=None):
        changed = self._invalid_credentials != value
        self._invalid_credentials = value
        if value and changed:
            msg = 'Setting invalid credentials'
            if reason:
                msg += ', reason is: %s' % reason
            log.error(msg)
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

    @staticmethod
    def local_rollback(force=None):
        """
        :param mixed force: Force the return value to be the one of `force`.
        :rtype: bool
        """

        if isinstance(force, bool):
            return force
        return False

    def create_thread(self, worker=None, name=None, start_connect=True):
        if worker is None:
            worker = Worker(self, name=name)
        # If subclass of Processor then connect the newSync signal
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

    def unsynchronize_pair(self, row_id, reason=None):
        state = self._dao.get_state_from_id(row_id)
        if state is None:
            return
        self._dao.unsynchronize_state(state, last_error=reason)
        self._dao.reset_error(state, last_error=reason)

    def resolve_with_local(self, row_id):
        row = self._dao.get_state_from_id(row_id)
        self._dao.force_local(row)

    def resolve_with_remote(self, row_id):
        row = self._dao.get_state_from_id(row_id)
        self._dao.force_remote(row)

    @pyqtSlot()
    def _check_last_sync(self):
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
                log.trace('No watchdog event detected but sync is completed')
            if self._sync_started:
                self._sync_started = False
            log.trace('Emitting syncCompleted for engine %s', self.uid)
            self.syncCompleted.emit()

    def _thread_finished(self):
        for thread in self._threads:
            if thread == self._local_watcher.get_thread():
                continue
            if thread == self._remote_watcher.get_thread():
                continue
            if thread.isFinished():
                self._threads.remove(thread)

    def is_started(self):
        return not self._stopped

    def start(self):
        if not self.check_fs_marker():
            raise FsMarkerException()

        # Checking root in case of failed migration
        self._check_root()

        # Launch the server confg file updater
        if self._manager.server_config_updater:
            self._manager.server_config_updater.force_poll()

        self._stopped = False
        Processor.soft_locks = dict()
        log.debug('Engine %s is starting', self.uid)
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
            log.debug("%r", thread.worker.get_metrics())
        log.debug("%r", self._queue_manager.get_metrics())

    def get_metrics(self):
        return {
            'conflicted_files': self._dao.get_conflict_count(),
            'error_files': self._dao.get_error_count(),
            'files_size': self._dao.get_global_size(),
            'invalid_credentials': self._invalid_credentials,
            'sync_files': self._dao.get_sync_count(filetype='file'),
            'sync_folders': self._dao.get_sync_count(filetype='folder'),
            'syncing': self._dao.get_syncing_count(),
            'unsynchronized_files': self._dao.get_unsynchronized_count(),
        }

    def get_conflicts(self):
        return self._dao.get_conflicts()

    def conflict_resolver(self, row_id, emit=True):
        pair = self._dao.get_state_from_id(row_id)
        if not pair:
            log.trace('Conflict resolver: empty pair, skipping')
            return

        try:
            local_client = self.get_local_client()
            parent_ref = local_client.get_remote_id(pair.local_parent_path)
            same_digests = local_client.is_equal_digests(pair.local_digest,
                                                         pair.remote_digest,
                                                         pair.local_path)
            log.warning(
                'Conflict resolver: names=%r(%r|%r) digests=%r(%s|%s)'
                ' parents=%r(%s|%s) [emit=%r]',
                pair.remote_name == pair.local_name,
                pair.remote_name,
                pair.local_name,
                same_digests,
                pair.local_digest,
                pair.remote_digest,
                pair.remote_parent_ref == parent_ref,
                pair.remote_parent_ref,
                parent_ref,
                emit,
            )
            if (same_digests
                    and pair.remote_parent_ref == parent_ref
                    and safe_filename(pair.remote_name) == pair.local_name):
                self._dao.synchronize_state(pair)
            elif emit:
                # Raise conflict only if not resolvable
                self.newConflict.emit(row_id)
        except:
            log.exception('Conflict resolver error')

    def get_errors(self):
        return self._dao.get_errors()

    def is_stopped(self):
        return self._stopped

    def stop(self):
        self._stopped = True
        log.trace('Engine %s stopping', self.uid)
        self._stop.emit()
        for thread in self._threads:
            if not thread.wait(5000):
                log.warning('Thread is not responding - terminate it')
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
        log.trace('Engine %s stopped', self.uid)

    @staticmethod
    def use_trash():
        return True

    def get_update_infos(self, client=None):
        client = client or self.get_remote_doc_client()
        if not client:
            return

        update_info = client.get_update_info()
        log.debug('Fetched update info for engine [%s] from server %s: %r',
                  self.name, self._server_url, update_info)
        self._dao.update_config(
            'server_version', update_info.get('serverVersion'))

    def update_password(self, password):
        self._load_configuration()
        nxclient = self.remote_doc_client_factory(
            self._server_url, self._remote_user, self._manager.device_id,
            self._manager.get_version(), proxies=self._manager.get_proxies(self._server_url),
            proxy_exceptions=self._manager.proxy_exceptions,
            password=str(password), timeout=self._handshake_timeout)
        self._remote_token = nxclient.request_token()
        if self._remote_token is None:
            raise Exception
        self._dao.update_config("remote_token", self._remote_token)
        self.set_invalid_credentials(value=False)
        self.invalidate_client_cache()
        # In case of a binding
        self._check_root()
        self.start()

    def update_token(self, token):
        self._load_configuration()
        self._remote_token = token
        self._dao.update_config("remote_token", self._remote_token)
        self.set_invalid_credentials(value=False)
        self.invalidate_client_cache()
        self.start()

    def bind(self, binder):
        check_credential = True
        if hasattr(binder, 'no_check') and binder.no_check:
            check_credential = False
        check_fs = not Options.nofscheck
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
                if not os.path.exists(os.path.dirname(self.local_folder)):
                    raise NotFound()
                if not os.path.exists(self.local_folder):
                    os.mkdir(self.local_folder)
                    created_folder = True
                self._check_fs(self.local_folder)
            except Exception as e:
                if created_folder:
                    try:
                        local_client = self.get_local_client()
                        local_client.unset_readonly(self.local_folder)
                        os.rmdir(self.local_folder)
                    except:
                        pass
                raise e
        nxclient = None
        if check_credential:
            nxclient = self.remote_doc_client_factory(
                self._server_url,
                self._remote_user,
                self._manager.device_id,
                self._manager.get_version(),
                proxies=self._manager.get_proxies(self._server_url),
                proxy_exceptions=self._manager.proxy_exceptions,
                password=self._remote_password,
                token=self._remote_token,
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
        if not self._manager.osi.is_partition_supported(path):
            raise InvalidDriveException()
        if os.path.exists(path):
            local_client = self.get_local_client()
            root_id = local_client.get_root_id()
            if root_id is not None:
                # server_url|user|device_id|uid
                token = root_id.split("|")
                if self._server_url != token[0] or self._remote_user != token[1]:
                    raise RootAlreadyBindWithDifferentAccount(token[1], token[0])

    def _check_root(self):
        root = self._dao.get_state_from_local("/")
        if root is None:
            if os.path.exists(self.local_folder):
                BaseClient.unset_path_readonly(self.local_folder)
            self._make_local_folder(self.local_folder)
            self._add_top_level_state()
            self._set_root_icon()
            self.add_to_favorites()
            BaseClient.set_path_readonly(self.local_folder)

    def add_to_favorites(self):
        # type: () -> None
        """
        Register the local folder as a favorite.
        Let the possibility to override that method from tests.
        """
        self._manager.osi.register_folder_link(self.local_folder)

    def _make_local_folder(self, local_folder):
        if not os.path.exists(local_folder):
            os.makedirs(local_folder)
        # Put the ROOT in readonly

    def cancel_action_on(self, pair_id):
        for thread in self._threads:
            if hasattr(thread, "worker") and isinstance(thread.worker, Processor):
                pair = thread.worker.get_current_pair()
                if pair is not None and pair.id == pair_id:
                    thread.worker.quit()

    def get_local_client(self):
        client = LocalClient(
            self.local_folder,
            case_sensitive=self._case_sensitive,
        )
        if self._case_sensitive is None and os.path.exists(self.local_folder):
            self._case_sensitive = client.is_case_sensitive()
        return client

    def get_server_version(self):
        server_version = self._dao.get_config('server_version')
        Options.set('server_version', server_version, setter='server')
        return server_version

    @pyqtSlot()
    def invalidate_client_cache(self):
        log.debug("Invalidate client cache")
        self._remote_clients.clear()
        self.invalidClientsCache.emit()

    def _set_root_icon(self):
        local_client = self.get_local_client()
        if not local_client.exists('/') or local_client.has_folder_icon('/'):
            return

        if AbstractOSIntegration.is_mac():
            icon = find_icon('folder_mac.dat')
        elif AbstractOSIntegration.is_windows():
            icon = find_icon('folder_windows.ico')
        else:
            # No implementation on Linux
            return

        if not icon:
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
        if not remote_client:
            return

        remote_info = remote_client.get_filesystem_root_info()

        self._dao.insert_local_state(local_info, '')
        row = self._dao.get_state_from_local('/')
        self._dao.update_remote_state(row, remote_info, remote_parent_path='', versioned=False)
        local_client.set_root_id(self._server_url + "|" + self._remote_user +
                            "|" + self._manager.device_id + "|" + self.uid)
        local_client.set_remote_id('/', remote_info.uid)
        self._dao.synchronize_state(row)
        # The root should also be sync

    def suspend_client(self, *_):
        if self.is_paused() or self._stopped:
            raise ThreadInterrupt
        # Verify thread status
        thread_id = current_thread().ident
        for thread in self._threads:
            if (hasattr(thread, 'worker')
                    and isinstance(thread.worker, Processor)
                    and thread.worker.get_thread_id() == thread_id
                    and not thread.worker.is_started()):
                raise ThreadInterrupt
        # Get action
        current_file = None
        action = Action.get_current_action()
        if isinstance(action, FileAction):
            client = self.get_local_client()
            current_file = client.get_path(action.filepath)
        if (current_file is not None and self._folder_lock is not None
                and current_file.startswith(self._folder_lock)):
            log.debug('PairInterrupt %r because lock on %r',
                      current_file, self._folder_lock)
            raise PairInterrupt

    def get_remote_client(self, filtered=True):
        """ Return a client for the FileSystem abstraction. """

        if self._invalid_credentials:
            return None

        cache_key = (self._manager.device_id, filtered)
        remote_client = self._remote_clients.get(cache_key)

        if remote_client is None:
            kwargs = {
                'proxies': self._manager.get_proxies(self._server_url),
                'proxy_exceptions': self._manager.proxy_exceptions,
                'password': self._remote_password,
                'timeout': self.timeout,
                'cookie_jar': self.cookie_jar,
                'token': self._remote_token,
                'check_suspended': self.suspend_client,
            }
            if filtered:
                kwargs['dao'] = self._dao

            cls = (self.remote_fs_client_factory,
                   self.remote_filtered_fs_client_factory)[filtered]
            remote_client = cls(
                self._server_url,
                self._remote_user,
                self._manager.device_id,
                self.version,
                **kwargs)

            self._remote_clients[cache_key] = remote_client

        return remote_client

    def get_remote_doc_client(self, repository=Options.remote_repo, base_folder=None):
        if self._invalid_credentials:
            return None

        cache_key = (self._manager.device_id, 'remote_doc')
        remote_client = self._remote_clients.get(cache_key)

        if not remote_client:
            remote_client = self.remote_doc_client_factory(
                self._server_url,
                self._remote_user,
                self._manager.device_id,
                self.version,
                proxies=self._manager.get_proxies(self._server_url),
                proxy_exceptions=self._manager.proxy_exceptions,
                password=self._remote_password,
                token=self._remote_token,
                repository=repository,
                base_folder=base_folder,
                timeout=self._handshake_timeout,
                cookie_jar=self.cookie_jar,
                check_suspended=self.suspend_client)
            self._remote_clients[cache_key] = remote_client

        return remote_client

    def create_processor(self, item_getter, **kwargs):
        return Processor(self, item_getter, **kwargs)

    def dispose_db(self):
        if self._dao is not None:
            self._dao.dispose()

    def get_rest_api_client(self):
        return RestAPIClient(
            self.server_url,
            self.remote_user,
            self._manager.device_id,
            self._manager.get_version(),
            token=self.get_remote_token(),
            timeout=self.timeout,
            cookie_jar=self.cookie_jar,
            proxies=self._manager.get_proxies(self._server_url),
            proxy_exceptions=self._manager.proxy_exceptions,
        )

    def get_user_full_name(self, userid, cache_only=False):
        """ Get the last contributor full name. """

        try:
            return self._user_cache[userid]
        except KeyError:
            full_name = userid

        if not cache_only:
            rest_client = self.get_rest_api_client()
            try:
                response = rest_client.get_user_full_name(userid)
                prop = response['properties']
            except urllib2.URLError:
                log.exception('Network error')
            except (TypeError, KeyError):
                log.exception('Content error')
            else:
                first_name = prop.get('firstName') or ''
                last_name = prop.get('lastName') or ''
                full_name = ' '.join([first_name, last_name]).strip()
                if not full_name:
                    full_name = prop.get('username', userid)
                self._user_cache[userid] = full_name

        return full_name


class ServerBindingSettings(object):
    """ Summarize server binding settings. """

    def __init__(
        self,
        server_version=None,
        password=None,
        pwd_update_required=False,
        **kwargs
    ):
        self.server_version = server_version
        self.password = password
        self.pwd_update_required = pwd_update_required
        for arg, value in kwargs.items():
            setattr(self, arg, value)

    def __repr__(self):
        attrs = ', '.join('{}={!r}'.format(attr, getattr(self, attr, None))
                          for attr in sorted(vars(self)))
        return '<{} {}>'.format(self.__class__.__name__, attrs)
