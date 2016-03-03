from PyQt4.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer
from Queue import Queue, Empty
from nxdrive.logging_config import get_logger
from threading import Lock, local
from copy import deepcopy
import time
log = get_logger(__name__)

WINERROR_CODE_PROCESS_CANNOT_ACCESS_FILE = 32

WindowsError = None
try:
    from exceptions import WindowsError
except ImportError:
    pass  # This will never be raised under Unix


class QueueItem(object):
    def __init__(self, row_id, folderish, pair_state):
        self.id = row_id
        self.folderish = folderish
        self.pair_state = pair_state

    def __repr__(self):
        return "%s[%s](Folderish:%s, State: %s)" % (
                        self.__class__.__name__, self.id,
                        self.folderish, self.pair_state)


class QueueManager(QObject):
    # Always create thread from the main thread
    newItem = pyqtSignal(object)
    newError = pyqtSignal(object)
    newErrorGiveUp = pyqtSignal(object)
    queueEmpty = pyqtSignal()
    queueProcessing = pyqtSignal()
    queueFinishedProcessing = pyqtSignal()
    # Only used by Unit Test
    _disable = False
    '''
    classdocs
    '''
    def __init__(self, engine, dao, max_file_processors=5):
        '''
        Constructor
        '''
        super(QueueManager, self).__init__()
        self._dao = dao
        self._engine = engine
        self._local_folder_queue = Queue()
        self._local_file_queue = Queue()
        self._remote_file_queue = Queue()
        self._remote_folder_queue = Queue()
        self._connected = local()
        self._local_folder_enable = True
        self._local_file_enable = True
        self._remote_folder_enable = True
        self._remote_file_enable = True
        self._local_folder_thread = None
        self._local_file_thread = None
        self._remote_folder_thread = None
        self._remote_file_thread = None
        self._error_threshold = 3
        self._error_interval = 60
        self.set_max_processors(max_file_processors)
        self._threads_pool = list()
        self._processors_pool = list()
        self._get_file_lock = Lock()
        # Should not operate on thread while we are inspecting them
        '''
        This error required to add a lock for inspecting threads, as the below Traceback shows the processor thread was ended while the method was running
        Traceback (most recent call last):
           File "/Users/hudson/tmp/workspace/FT-nuxeo-drive-master-osx/nuxeo-drive-client/nxdrive/engine/watcher/local_watcher.py", line 845, in handle_watchdog_event
             self.scan_pair(rel_path)
           File "/Users/hudson/tmp/workspace/FT-nuxeo-drive-master-osx/nuxeo-drive-client/nxdrive/engine/watcher/local_watcher.py", line 271, in scan_pair
             self._suspend_queue()
           File "/Users/hudson/tmp/workspace/FT-nuxeo-drive-master-osx/nuxeo-drive-client/nxdrive/engine/watcher/local_watcher.py", line 265, in _suspend_queue
             for processor in self._engine.get_queue_manager().get_processors_on('/', exact_match=False):
           File "/Users/hudson/tmp/workspace/FT-nuxeo-drive-master-osx/nuxeo-drive-client/nxdrive/engine/queue_manager.py", line 413, in get_processors_on
             res.append(self._local_file_thread.worker)
         AttributeError: 'NoneType' object has no attribute 'worker'
        '''
        self._thread_inspection = Lock()

        # ERROR HANDLING
        self._error_lock = Lock()
        self._on_error_queue = dict()
        self._error_timer = QTimer()
        self._error_timer.timeout.connect(self._on_error_timer)
        self.newError.connect(self._on_new_error)
        self.queueProcessing.connect(self.launch_processors)
        # LAST ACTION
        self._dao.register_queue_manager(self)

    def init_processors(self):
        log.trace("Init processors")
        self.newItem.connect(self.launch_processors)
        self.queueProcessing.emit()

    def shutdown_processors(self):
        log.trace("Shutdown processors")
        try:
            self.newItem.disconnect(self.launch_processors)
        except TypeError:
            # TypeError: disconnect() failed between 'newItem' and 'launch_processors'
            pass

    def init_queue(self, queue):
        # Dont need to change modify as State is compatible with QueueItem
        for item in queue:
            self.push(item)

    def _copy_queue(self, queue):
        result = deepcopy(queue.queue)
        result.reverse()
        return result

    def set_max_processors(self, max_file_processors):
        if max_file_processors < 2:
            max_file_processors = 2
        self._max_processors = max_file_processors - 2

    def resume(self):
        log.debug("Resuming queue")
        self.enable_local_file_queue(True, False)
        self.enable_local_folder_queue(True, False)
        self.enable_remote_file_queue(True, False)
        self.enable_remote_folder_queue(True, False)
        self.queueProcessing.emit()

    def is_paused(self):
        return (not self._local_file_enable or
                    not self._local_folder_enable or
                    not self._remote_file_enable or
                    not self._remote_folder_enable)

    def suspend(self):
        log.debug("Suspending queue")
        self.enable_local_file_queue(False)
        self.enable_local_folder_queue(False)
        self.enable_remote_file_queue(False)
        self.enable_remote_folder_queue(False)


    def enable_local_file_queue(self, value=True, emit=True):
        self._local_file_enable = value
        if self._local_file_thread is not None and not value:
            self._local_file_thread.quit()
        if value and emit:
            self.queueProcessing.emit()

    def enable_local_folder_queue(self, value=True, emit=True):
        self._local_folder_enable = value
        if self._local_folder_thread is not None and not value:
            self._local_folder_thread.quit()
        if value and emit:
            self.queueProcessing.emit()

    def enable_remote_file_queue(self, value=True, emit=True):
        self._remote_file_enable = value
        if self._remote_file_thread is not None and not value:
            self._remote_file_thread.quit()
        if value and emit:
            self.queueProcessing.emit()

    def enable_remote_folder_queue(self, value=True, emit=True):
        self._remote_folder_enable = value
        if self._remote_folder_thread is not None and not value:
            self._remote_folder_thread.quit()
        if value and emit:
            self.queueProcessing.emit()

    def get_local_file_queue(self):
        return self._copy_queue(self._local_file_queue)

    def get_remote_file_queue(self):
        return self._copy_queue(self._remote_file_queue)

    def get_local_folder_queue(self):
        return self._copy_queue(self._local_folder_queue)

    def get_remote_folder_queue(self):
        return self._copy_queue(self._remote_folder_queue)

    def push_ref(self, row_id, folderish, pair_state):
        self.push(QueueItem(row_id, folderish, pair_state))

    def push(self, state):
        if state.pair_state is None:
            log.trace("Don't push an empty pair_state: %r", state)
            return
        log.trace("Pushing %r", state)
        row_id = state.id
        if state.pair_state.startswith('locally'):
            if state.folderish:
                self._local_folder_queue.put(state)
                log.trace('Pushed to _local_folder_queue, now of size: %d', self._local_folder_queue.qsize())
            else:
                if "deleted" in state.pair_state:
                    self._engine.cancel_action_on(state.id)
                self._local_file_queue.put(state)
                log.trace('Pushed to _local_file_queue, now of size: %d', self._local_file_queue.qsize())
            self.newItem.emit(row_id)
        elif state.pair_state.startswith('remotely'):
            if state.folderish:
                self._remote_folder_queue.put(state)
                log.trace('Pushed to _remote_folder_queue, now of size: %d', self._remote_folder_queue.qsize())
            else:
                if "deleted" in state.pair_state:
                    self._engine.cancel_action_on(state.id)
                self._remote_file_queue.put(state)
                log.trace('Pushed to _remote_file_queue, now of size: %d', self._remote_file_queue.qsize())
            self.newItem.emit(row_id)
        else:
            # deleted and conflicted
            log.debug("Not processable state: %r", state)

    @pyqtSlot()
    def _on_error_timer(self):
        cur_time = int(time.time())
        self._error_lock.acquire()
        try:
            for doc_pair in self._on_error_queue.values():
                if doc_pair.error_next_try < cur_time:
                    queueItem = QueueItem(doc_pair.id, doc_pair.folderish, doc_pair.pair_state)
                    del self._on_error_queue[doc_pair.id]
                    log.debug('End of blacklist period, pushing doc_pair: %r', doc_pair)
                    self.push(queueItem)
            if len(self._on_error_queue) == 0:
                self._error_timer.stop()
        finally:
            self._error_lock.release()

    def _is_on_error(self, row_id):
        return row_id in self._on_error_queue

    @pyqtSlot()
    def _on_new_error(self):
        self._error_timer.start(1000)

    def get_errors_count(self):
        return len(self._on_error_queue)

    def get_error_threshold(self):
        return self._error_threshold

    def push_error(self, doc_pair, exception=None):
        error_count = doc_pair.error_count
        if (exception is not None and type(exception) == WindowsError
            and hasattr(exception, 'winerror') and exception.winerror == WINERROR_CODE_PROCESS_CANNOT_ACCESS_FILE):
            log.debug("Detected WindowsError with code %d: '%s', won't increase next try interval",
                      WINERROR_CODE_PROCESS_CANNOT_ACCESS_FILE,
                      exception.strerror if hasattr(exception, 'strerror') else '')
            error_count = 1
        if error_count > self._error_threshold:
            self.newErrorGiveUp.emit(doc_pair.id)
            log.debug("Giving up on pair : %r", doc_pair)
            return
        interval = self._error_interval * error_count
        doc_pair.error_next_try = interval + int(time.time())
        log.debug("Blacklisting pair for %ds: %r", interval, doc_pair)
        self._error_lock.acquire()
        try:
            emit_sig = False
            if doc_pair.id not in self._on_error_queue:
                emit_sig = True
            self._on_error_queue[doc_pair.id] = doc_pair
            if emit_sig:
                self.newError.emit(doc_pair.id)
        finally:
            self._error_lock.release()

    def requeue_errors(self):
        self._error_lock.acquire()
        try:
            for doc_pair in self._on_error_queue.values():
                doc_pair.error_next_try = 0
        finally:
            self._error_lock.release()

    def _get_local_folder(self):
        if self._local_folder_queue.empty():
            return None
        try:
            state = self._local_folder_queue.get(True, 3)
        except Empty:
            return None
        if state is not None and self._is_on_error(state.id):
            return self._get_local_folder()
        return state

    def _get_local_file(self):
        if self._local_file_queue.empty():
            return None
        try:
            state = self._local_file_queue.get(True, 3)
        except Empty:
            return None
        if state is not None and self._is_on_error(state.id):
            return self._get_local_file()
        return state

    def _get_remote_folder(self):
        if self._remote_folder_queue.empty():
            return None
        try:
            state = self._remote_folder_queue.get(True, 3)
        except Empty:
            return None
        if state is not None and self._is_on_error(state.id):
            return self._get_remote_folder()
        return state

    def _get_remote_file(self):
        if self._remote_file_queue.empty():
            return None
        try:
            state = self._remote_file_queue.get(True, 3)
        except Empty:
            return None
        if state is not None and self._is_on_error(state.id):
            return self._get_remote_file()
        return state

    def _get_file(self):
        self._get_file_lock.acquire()
        if self._remote_file_queue.empty() and self._local_file_queue.empty():
            self._get_file_lock.release()
            return None
        state = None
        if (self._remote_file_queue.qsize() > self._local_file_queue.qsize()):
            state = self._get_remote_file()
        else:
            state = self._get_local_file()
        self._get_file_lock.release()
        if state is not None and self._is_on_error(state.id):
            return self._get_file()
        return state

    @pyqtSlot()
    def _thread_finished(self):
        self._thread_inspection.acquire()
        try:
            for thread in self._processors_pool:
                if thread.isFinished():
                    self._processors_pool.remove(thread)
            if (self._local_folder_thread is not None and
                    self._local_folder_thread.isFinished()):
                self._local_folder_thread = None
            if (self._local_file_thread is not None and
                    self._local_file_thread.isFinished()):
                self._local_file_thread = None
            if (self._remote_folder_thread is not None and
                    self._remote_folder_thread.isFinished()):
                self._remote_folder_thread = None
            if (self._remote_file_thread is not None and
                    self._remote_file_thread.isFinished()):
                self._remote_file_thread = None
            if not self._engine.is_paused() and not self._engine.is_stopped():
                self.newItem.emit(None)
        finally:
            self._thread_inspection.release()

    def active(self):
        # Recheck threads
        self._thread_finished()
        return self.is_active()

    def is_active(self):
        return (self._local_folder_thread is not None
                or self._local_file_thread is not None
                or self._remote_file_thread is not None
                or self._remote_folder_thread is not None
                or len(self._processors_pool) > 0)

    def _create_thread(self, item_getter, name=None):
        processor = self._engine.create_processor(item_getter, name=name)
        thread = self._engine.create_thread(worker=processor)
        thread.finished.connect(self._thread_finished)
        thread.terminated.connect(self._thread_finished)
        thread.start()
        return thread

    def get_metrics(self):
        metrics = dict()
        metrics["local_folder_queue"] = self._local_folder_queue.qsize()
        metrics["local_file_queue"] = self._local_file_queue.qsize()
        metrics["remote_folder_queue"] = self._remote_folder_queue.qsize()
        metrics["remote_file_queue"] = self._remote_file_queue.qsize()
        metrics["remote_file_thread"] = self._remote_file_thread is not None
        metrics["remote_folder_thread"] = self._remote_folder_thread is not None
        metrics["local_file_thread"] = self._local_file_thread is not None
        metrics["local_folder_thread"] = self._local_folder_thread is not None
        metrics["error_queue"] = self.get_errors_count()
        metrics["total_queue"] = (metrics["local_folder_queue"] + metrics["local_file_queue"]
                                + metrics["remote_folder_queue"] + metrics["remote_file_queue"])
        metrics["additional_processors"] = len(self._processors_pool)
        return metrics

    def get_overall_size(self):
        return (self._local_folder_queue.qsize() + self._local_file_queue.qsize()
                + self._remote_folder_queue.qsize() + self._remote_file_queue.qsize())

    def is_processing_file(self, worker, path, exact_match=False):
        if not hasattr(worker, "_current_doc_pair"):
            return False
        doc_pair = worker._current_doc_pair
        if (doc_pair is None or doc_pair.local_path is None):
            return False
        if exact_match:
            result = doc_pair.local_path == path
        else:
            result = doc_pair.local_path.startswith(path)
        if result:
            log.trace("Worker(%r) is processing: %r", worker.get_metrics(), path)
        return result

    def interrupt_processors_on(self, path, exact_match=True):
        for proc in self.get_processors_on(path, exact_match):
            proc.stop()

    def get_processors_on(self, path, exact_match=True):
        self._thread_inspection.acquire()
        try:
            res = []
            if self._local_folder_thread is not None:
                if self.is_processing_file(self._local_folder_thread.worker, path, exact_match):
                    res.append(self._local_folder_thread.worker)
            if self._remote_folder_thread is not None:
                if self.is_processing_file(self._remote_folder_thread.worker, path, exact_match):
                    res.append(self._remote_folder_thread.worker)
            if self._local_file_thread is not None:
                if self.is_processing_file(self._local_file_thread.worker, path, exact_match):
                    res.append(self._local_file_thread.worker)
            if self._remote_file_thread is not None:
                if self.is_processing_file(self._remote_file_thread.worker, path, exact_match):
                    res.append(self._remote_file_thread.worker)
            for thread in self._processors_pool:
                if self.is_processing_file(thread.worker, path, exact_match):
                    res.append(thread.worker)
            return res
        finally:
            self._thread_inspection.release()

    def has_file_processors_on(self, path):
        self._thread_inspection.acquire()
        try:
            # First check local and remote file
            if self._local_file_thread is not None:
                if self.is_processing_file(self._local_file_thread.worker, path):
                    return True
            if self._remote_file_thread is not None:
                if self.is_processing_file(self._remote_file_thread.worker, path):
                    return True
            for thread in self._processors_pool:
                if self.is_processing_file(thread.worker, path):
                    return True
            return False
        finally:
            self._thread_inspection.release()

    @pyqtSlot()
    def launch_processors(self):
        if (self._disable or self.is_paused() or (self._local_folder_queue.empty() and self._local_file_queue.empty()
                and self._remote_folder_queue.empty() and self._remote_file_queue.empty())):
            self.queueEmpty.emit()
            if not self.is_active():
                self.queueFinishedProcessing.emit()
            return
        log.trace("Launching processors")
        if self._local_folder_thread is None and not self._local_folder_queue.empty() and self._local_folder_enable:
            log.debug("creating local folder processor")
            self._local_folder_thread = self._create_thread(self._get_local_folder, name="LocalFolderProcessor")
        if self._local_file_thread is None and not self._local_file_queue.empty() and self._local_file_enable:
            log.debug("creating local file processor")
            self._local_file_thread = self._create_thread(self._get_local_file, name="LocalFileProcessor")
        if self._remote_folder_thread is None and not self._remote_folder_queue.empty() and self._remote_folder_enable:
            log.debug("creating remote folder processor")
            self._remote_folder_thread = self._create_thread(self._get_remote_folder, name="RemoteFolderProcessor")
        if self._remote_file_thread is None and not self._remote_file_queue.empty() and self._remote_file_enable:
            log.debug("creating remote file processor")
            self._remote_file_thread = self._create_thread(self._get_remote_file, name="RemoteFileProcessor")
        if self._remote_file_queue.qsize() + self._local_file_queue.qsize() == 0:
            return
        while len(self._processors_pool) < self._max_processors:
            log.debug("creating additional file processor")
            self._processors_pool.append(self._create_thread(self._get_file, name="GenericProcessor"))
