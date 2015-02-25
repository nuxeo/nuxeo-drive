from PyQt4.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer
from Queue import Queue, Empty
from nxdrive.logging_config import get_logger
from nxdrive.engine.processor import Processor
from threading import Lock, local
from copy import deepcopy
import time
log = get_logger(__name__)


class QueueItem(object):
    def __init__(self, row_id, folderish, pair_state):
        self.id = row_id
        self.folderish = folderish
        self.pair_state = pair_state

    def __repr__(self):
        return "%s[%d](Folderish:%d, State: %s)" % (
                        self.__class__.__name__, self.id,
                        self.folderish, self.pair_state)


class QueueManager(QObject):
    # Always create thread from the main thread
    newItem = pyqtSignal(object)
    newError = pyqtSignal(object)
    queueEmpty = pyqtSignal()
    queueProcessing = pyqtSignal()
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
        self.enable_local_file_queue(True)
        self.enable_local_folder_queue(True)
        self.enable_remote_file_queue(True)
        self.enable_remote_folder_queue(True)

    def pause(self):
        self.enable_local_file_queue(False)
        self.enable_local_folder_queue(False)
        self.enable_remote_file_queue(False)
        self.enable_remote_folder_queue(False)

    def enable_local_file_queue(self, value=True):
        self._local_file_enable = value
        if self._local_file_thread is not None and not value:
            self._local_file_thread.quit()
        if value:
            self.queueProcessing.emit()

    def enable_local_folder_queue(self, value=True):
        self._local_folder_enable = value
        if self._local_folder_thread is not None and not value:
            self._local_folder_thread.quit()
        if value:
            self.queueProcessing.emit()

    def enable_remote_file_queue(self, value=True):
        self._remote_file_enable = value
        if self._remote_file_thread is not None and not value:
            self._remote_file_thread.quit()
        if value:
            self.queueProcessing.emit()

    def enable_remote_folder_queue(self, value=True):
        self._remote_folder_enable = value
        if self._remote_folder_thread is not None and not value:
            self._remote_folder_thread.quit()
        if value:
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
                self._local_file_queue.put(state)
                log.trace('Pushed to _local_file_queue, now of size: %d', self._local_file_queue.qsize())
            self.newItem.emit(row_id)
        elif state.pair_state.startswith('remotely'):
            if state.folderish:
                self._remote_folder_queue.put(state)
                log.trace('Pushed to _remote_folder_queue, now of size: %d', self._remote_folder_queue.qsize())
            else:
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

    @pyqtSlot()
    def _on_new_error(self):
        self._error_timer.start(1000)

    def push_error(self, doc_pair):
        if doc_pair.error_count >= self._error_threshold:
            log.debug("Giving up on pair : %r", doc_pair)
            return
        interval = self._error_interval * doc_pair.error_count
        doc_pair.error_next_try = interval + int(time.time())
        log.debug("Blacklisting pair %r for %ds", doc_pair, interval)
        self._error_lock.acquire()
        try:
            emit_sig = False
            if len(self._on_error_queue) == 0:
                emit_sig = True
            self._on_error_queue[doc_pair.id] = doc_pair
            if emit_sig:
                self.newError.emit(doc_pair.id)
        finally:
            self._error_lock.release()

    def cancel_queued_errors(self):
        for doc_pair in self._on_error_queue.values():
            doc_pair.error_next_try = 0

    def _get_local_folder(self):
        if self._local_folder_queue.empty():
            return None
        try:
            state = self._local_folder_queue.get(True, 3)
        except Empty:
            return None
        return state

    def _get_local_file(self):
        if self._local_file_queue.empty():
            return None
        try:
            state = self._local_file_queue.get(True, 3)
        except Empty:
            return None
        return state

    def _get_remote_folder(self):
        if self._remote_folder_queue.empty():
            return None
        try:
            state = self._remote_folder_queue.get(True, 3)
        except Empty:
            return None
        return state

    def _get_remote_file(self):
        if self._remote_file_queue.empty():
            return None
        try:
            state = self._remote_file_queue.get(True, 3)
        except Empty:
            return None
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
        return state

    @pyqtSlot()
    def _thread_finished(self):
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

    def active(self):
        log.debug("Active: LocalFolder: %r, LocalFile: %r, RemoteFolder: %r, RemoteFile: %r, Pool:%d",
                    self._local_folder_thread, self._local_file_thread, self._remote_folder_thread, self._remote_file_thread, len(self._processors_pool))
        # Recheck threads
        self._thread_finished()
        return (self._local_folder_thread is not None
                or self._local_file_thread is not None
                or self._remote_file_thread is not None
                or self._remote_folder_thread is not None
                or len(self._processors_pool) > 0)

    def _create_thread(self, item_getter, name=None):
        processor = Processor(self._engine, item_getter, name=name)
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
        metrics["error_queue"] = len(self._on_error_queue)
        metrics["total_queue"] = (metrics["local_folder_queue"] + metrics["local_file_queue"]
                                + metrics["remote_folder_queue"] + metrics["remote_file_queue"])
        metrics["additional_processors"] = len(self._processors_pool)
        return metrics

    def get_overall_size(self):
        return (self._local_folder_queue.qsize() + self._local_file_queue.qsize()
                + self._remote_folder_queue.qsize() + self._remote_file_queue.qsize())

    @pyqtSlot()
    def launch_processors(self):
        if (self._local_folder_queue.empty() and self._local_file_queue.empty()
                and self._remote_file_queue.empty() and self._local_file_queue.qsize()):
            self.queueEmpty.emit()
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
        if self._remote_file_queue.qsize() + self._local_file_queue.qsize() <= 2:
            return
        while len(self._processors_pool) < self._max_processors:
            log.debug("creating additional file processor")
            self._processors_pool.append(self._create_thread(self._get_file, name="GenericProcessor"))
