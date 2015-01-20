from PyQt4.QtCore import QObject, pyqtSignal, pyqtSlot
from Queue import Queue
from nxdrive.logging_config import get_logger
from nxdrive.engine.processor import Processor
from threading import Lock, local
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
    newItem = pyqtSignal()
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
        self._local_folder_thread = None
        self._local_file_thread = None
        self._remote_folder_thread = None
        self._remote_file_thread = None
        if max_file_processors < 2:
            max_file_processors = 2
        self._max_processors = max_file_processors - 2
        self._threads_pool = list()
        self._processors_pool = list()
        self._dao.register_queue_manager(self)
        self._get_file_lock = Lock()

    def init_processors(self):
        log.trace("Init processors")
        self.newItem.connect(self.launch_processors)
        self.newItem.emit()

    def init_queue(self, queue):
        # Dont need to change modify as State is compatible with QueueItem
        for item in queue:
            self.push(item)

    def push_ref(self, row_id, folderish, pair_state):
        self.push(QueueItem(row_id, folderish, pair_state))

    def push(self, state):
        if state.pair_state is None:
            log.trace("Don't push an empty pair_state: %r", state)
            return
        log.trace("Pushing %r[f:%d]", state, state.folderish)
        if state.pair_state.startswith('locally'):
            if state.folderish:
                self._local_folder_queue.put(state)
            else:
                self._local_file_queue.put(state)
            self.newItem.emit()
        elif state.pair_state.startswith('remotely'):
            if state.folderish:
                self._remote_folder_queue.put(state)
            else:
                self._remote_file_queue.put(state)
            self.newItem.emit()
        else:
            # deleted and conflicted
            pass

    def _get_local_folder(self):
        log.trace("get next local folder")
        if self._local_folder_queue.empty():
            log.trace("return state: None")
            return None
        state = self._local_folder_queue.get()
        log.trace("return state: %r", state)
        return state

    def _get_local_file(self):
        log.trace("get next local file")
        if self._local_file_queue.empty():
            log.trace("return state: None")
            return None
        state = self._local_file_queue.get()
        log.trace("return state: %r", state)
        return state

    def _get_remote_folder(self):
        log.trace("get next remote folder")
        if self._remote_folder_queue.empty():
            log.trace("return state: None")
            return None
        state = self._remote_folder_queue.get()
        log.trace("return state: %r", state)
        return state

    def _get_remote_file(self):
        log.trace("get next remote file")
        if self._remote_file_queue.empty():
            log.trace("return state: None")
            return None
        state = self._remote_file_queue.get()
        log.trace("return state: %r", state)
        return state

    def _get_file(self):
        log.trace("get next file")
        self._get_file_lock.acquire()
        if self._remote_file_queue.empty() and self._local_file_queue.empty():
            self._get_file_lock.release()
            log.trace("return state: None")
            return None
        state = None
        if (self._remote_file_queue.qsize() > self._local_file_queue.qsize()):
            state = self._remote_file_queue.get()
        else:
            state = self._local_file_queue.get()
        self._get_file_lock.release()
        log.trace("return state: %r", state)
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
            self.newItem.emit()

    def _create_thread(self, item_getter, name=None):
        processor = Processor(self._engine, item_getter, name=name)
        thread = self._engine.create_thread(worker=processor, start_connect=False)
        thread.finished.connect(self._thread_finished)
        thread.terminated.connect(self._thread_finished)
        thread.started.connect(processor.run)
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
        metrics["total_queue"] = (metrics["local_folder_queue"] + metrics["local_file_queue"]
                                + metrics["remote_folder_queue"] + metrics["remote_file_queue"])
        metrics["additional_processors"] = len(self._processors_pool)
        return metrics

    @pyqtSlot()
    def launch_processors(self):
        log.trace("Launch processors")
        if self._local_folder_thread is None and not self._local_folder_queue.empty():
            log.debug("creating local folder processor")
            self._local_folder_thread = self._create_thread(self._get_local_folder, name="LocalFolderProcessor")
        if self._local_file_thread is None and not self._local_file_queue.empty():
            log.debug("creating local file processor")
            self._local_file_thread = self._create_thread(self._get_local_file, name="LocalFileProcessor")
        if self._remote_folder_thread is None and not self._remote_folder_queue.empty():
            log.debug("creating remote folder processor")
            self._remote_folder_thread = self._create_thread(self._get_remote_folder, name="RemoteFolderProcessor")
        if self._remote_file_thread is None and not self._remote_file_queue.empty():
            log.debug("creating remote file processor")
            self._remote_file_thread = self._create_thread(self._get_remote_file, name="RemoteFileProcessor")
        if self._remote_file_queue.qsize() + self._local_file_queue.qsize() <= 2:
            return
        while len(self._processors_pool) < self._max_processors:
            log.debug("creating additional file processor")
            self._processors_pool.append(self._create_thread(self._get_file, name="GenericProcessor"))
