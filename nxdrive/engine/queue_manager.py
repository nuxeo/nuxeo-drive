# coding: utf-8
import time
from contextlib import suppress
from copy import deepcopy
from logging import getLogger
from queue import Empty, Queue
from threading import Lock
from typing import Any, Callable, List, Optional

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from .processor import Processor
from ..objects import DocPair, Metrics, NuxeoDocumentInfo

__all__ = ("QueueManager",)

log = getLogger(__name__)
WINERROR_CODE_PROCESS_CANNOT_ACCESS_FILE = 32


class QueueItem:
    def __init__(self, row_id: int, folderish: bool, pair_state: DocPair) -> None:
        self.id = row_id
        self.folderish = folderish
        self.pair_state = pair_state

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}[{self.id}](folderish={self.folderish!r}, "
            f"state={self.pair_state!r})"
        )


class QueueManager(QObject):
    # Always create thread from the main thread
    newItem = pyqtSignal(object)
    newError = pyqtSignal(object)
    newErrorGiveUp = pyqtSignal(object)
    queueProcessing = pyqtSignal()
    queueFinishedProcessing = pyqtSignal()

    # Only used by Unit Test
    _disable = False

    def __init__(
        self, engine: "Engine", dao: "EngineDAO", max_file_processors: int = 5
    ) -> None:
        super().__init__()
        self._dao = dao
        self._engine = engine
        self._local_folder_queue = Queue()
        self._local_file_queue = Queue()
        self._remote_file_queue = Queue()
        self._remote_folder_queue = Queue()
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
        self._processors_pool = list()
        self._get_file_lock = Lock()
        # Should not operate on thread while we are inspecting them
        """
        This error required to add a lock for inspecting threads,
        as the below Traceback shows the processor thread was ended while the method was running:
        Traceback (most recent call last):
           File "engine/watcher/local_watcher.py", line 845, in handle_watchdog_event
             self.scan_pair(rel_path)
           File "engine/watcher/local_watcher.py", line 271, in scan_pair
             self._suspend_queue()
           File "engine/watcher/local_watcher.py", line 265, in _suspend_queue
             for processor in self._engine.get_queue_manager().get_processors_on('/', exact_match=False):
           File "engine/queue_manager.py", line 413, in get_processors_on
             res.append(self._local_file_thread.worker)
         AttributeError: 'NoneType' object has no attribute 'worker'
        """
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

    def init_processors(self) -> None:
        log.trace("Init processors")
        self.newItem.connect(self.launch_processors)
        self.queueProcessing.emit()

    def shutdown_processors(self) -> None:
        log.trace("Shutdown processors")
        with suppress(TypeError):
            # TypeError: disconnect() failed between 'newItem' and 'launch_processors'
            self.newItem.disconnect(self.launch_processors)

    @staticmethod
    def _copy_queue(queue: Queue) -> Queue:
        result = deepcopy(queue.queue)
        result.reverse()
        return result

    def set_max_processors(self, max_file_processors: int) -> None:
        if max_file_processors < 2:
            max_file_processors = 2
        self._max_processors = max_file_processors - 2

    def resume(self) -> None:
        log.debug("Resuming queue")
        self.enable_local_file_queue(True, False)
        self.enable_local_folder_queue(True, False)
        self.enable_remote_file_queue(True, False)
        self.enable_remote_folder_queue(True, False)
        self.queueProcessing.emit()

    def is_paused(self) -> bool:
        return any(
            {
                not self._local_file_enable,
                not self._local_folder_enable,
                not self._remote_file_enable,
                not self._remote_folder_enable,
            }
        )

    def suspend(self) -> None:
        log.debug("Suspending queue")
        self.enable_local_file_queue(False)
        self.enable_local_folder_queue(False)
        self.enable_remote_file_queue(False)
        self.enable_remote_folder_queue(False)

    def enable_local_file_queue(self, value: bool = True, emit: bool = True) -> None:
        self._local_file_enable = value
        if self._local_file_thread is not None and not value:
            self._local_file_thread.quit()
        if value and emit:
            self.queueProcessing.emit()

    def enable_local_folder_queue(self, value: bool = True, emit: bool = True) -> None:
        self._local_folder_enable = value
        if self._local_folder_thread is not None and not value:
            self._local_folder_thread.quit()
        if value and emit:
            self.queueProcessing.emit()

    def enable_remote_file_queue(self, value: bool = True, emit: bool = True) -> None:
        self._remote_file_enable = value
        if self._remote_file_thread is not None and not value:
            self._remote_file_thread.quit()
        if value and emit:
            self.queueProcessing.emit()

    def enable_remote_folder_queue(self, value: bool = True, emit: bool = True) -> None:
        self._remote_folder_enable = value
        if self._remote_folder_thread is not None and not value:
            self._remote_folder_thread.quit()
        if value and emit:
            self.queueProcessing.emit()

    def get_local_file_queue(self) -> Queue:
        return self._copy_queue(self._local_file_queue)

    def get_remote_file_queue(self) -> Queue:
        return self._copy_queue(self._remote_file_queue)

    def get_local_folder_queue(self) -> Queue:
        return self._copy_queue(self._local_folder_queue)

    def get_remote_folder_queue(self) -> Queue:
        return self._copy_queue(self._remote_folder_queue)

    def push_ref(
        self, row_id: int, folderish: bool, pair_state: NuxeoDocumentInfo
    ) -> None:
        self.push(QueueItem(row_id, folderish, pair_state))

    def push(self, state: NuxeoDocumentInfo) -> None:
        if state.pair_state is None:
            log.trace(f"Don't push an empty pair_state: {state!r}")
            return
        log.trace(f"Pushing {state!r}")
        row_id = state.id
        if state.pair_state.startswith("locally"):
            if state.folderish:
                self._local_folder_queue.put(state)
                log.trace(
                    "Pushed to _local_folder_queue, now of size: "
                    f"{self._local_folder_queue.qsize()}"
                )
            else:
                if "deleted" in state.pair_state:
                    self._engine.cancel_action_on(state.id)
                self._local_file_queue.put(state)
                log.trace(
                    "Pushed to _local_file_queue, now of size: "
                    f"{self._local_file_queue.qsize()}"
                )
            self.newItem.emit(row_id)
        elif state.pair_state.startswith("remotely"):
            if state.folderish:
                self._remote_folder_queue.put(state)
                log.trace(
                    f"Pushed to _remote_folder_queue, now of size: "
                    f"{self._remote_folder_queue.qsize()}"
                )
            else:
                if "deleted" in state.pair_state:
                    self._engine.cancel_action_on(state.id)
                self._remote_file_queue.put(state)
                log.trace(
                    "Pushed to _remote_file_queue, now of size: "
                    f"{self._remote_file_queue.qsize()}"
                )
            self.newItem.emit(row_id)
        else:
            # deleted and conflicted
            log.debug(f"Not processable state: {state!r}")

    @pyqtSlot()
    def _on_error_timer(self) -> None:
        cur_time = int(time.time())
        with self._error_lock:
            for doc_pair in list(self._on_error_queue.values()):
                if doc_pair.error_next_try < cur_time:
                    queue_item = QueueItem(
                        doc_pair.id, doc_pair.folderish, doc_pair.pair_state
                    )
                    del self._on_error_queue[doc_pair.id]
                    log.debug(
                        f"End of blacklist period, pushing doc_pair: {doc_pair!r}"
                    )
                    self.push(queue_item)
            if not self._on_error_queue:
                self._error_timer.stop()

    def _is_on_error(self, row_id: int) -> bool:
        return row_id in self._on_error_queue

    @pyqtSlot()
    def _on_new_error(self) -> None:
        self._error_timer.start(1000)

    def get_errors_count(self) -> int:
        return len(self._on_error_queue)

    def get_error_threshold(self) -> int:
        return self._error_threshold

    def push_error(
        self,
        doc_pair: NuxeoDocumentInfo,
        exception: Exception = None,
        interval: int = None,
    ) -> None:
        error_count = doc_pair.error_count
        if (
            isinstance(exception, OSError)
            and hasattr(exception, "winerror")
            and exception.winerror == WINERROR_CODE_PROCESS_CANNOT_ACCESS_FILE
        ):
            log.debug(
                "Detected WindowsError with code %d: '%s', won't increase next try interval",
                WINERROR_CODE_PROCESS_CANNOT_ACCESS_FILE,
                exception.strerror if hasattr(exception, "strerror") else "",
            )
            error_count = 1
        if error_count > self._error_threshold:
            self.newErrorGiveUp.emit(doc_pair.id)
            log.debug(f"Giving up on pair : {doc_pair!r}")
            return
        if interval is None:
            interval = self._error_interval * error_count
        doc_pair.error_next_try = interval + int(time.time())
        log.debug(f"Blacklisting pair for {interval}s: {doc_pair!r}")
        with self._error_lock:
            emit_sig = False
            if doc_pair.id not in self._on_error_queue:
                emit_sig = True
            self._on_error_queue[doc_pair.id] = doc_pair
            if emit_sig:
                self.newError.emit(doc_pair.id)

    def requeue_errors(self) -> None:
        with self._error_lock:
            for doc_pair in self._on_error_queue.values():
                doc_pair.error_next_try = 0

    def _get_local_folder(self) -> Optional[str]:
        if self._local_folder_queue.empty():
            return None
        try:
            state = self._local_folder_queue.get(True, 3)
        except Empty:
            return None
        if state is not None and self._is_on_error(state.id):
            return self._get_local_folder()
        return state

    def _get_local_file(self) -> Optional[NuxeoDocumentInfo]:
        if self._local_file_queue.empty():
            return None
        try:
            state = self._local_file_queue.get(True, 3)
        except Empty:
            return None
        if state is not None and self._is_on_error(state.id):
            return self._get_local_file()
        return state

    def _get_remote_folder(self) -> Optional[NuxeoDocumentInfo]:
        if self._remote_folder_queue.empty():
            return None
        try:
            state = self._remote_folder_queue.get(True, 3)
        except Empty:
            return None
        if state is not None and self._is_on_error(state.id):
            return self._get_remote_folder()
        return state

    def _get_remote_file(self) -> Optional[NuxeoDocumentInfo]:
        if self._remote_file_queue.empty():
            return None
        try:
            state = self._remote_file_queue.get(True, 3)
        except Empty:
            return None
        if state is not None and self._is_on_error(state.id):
            return self._get_remote_file()
        return state

    def _get_file(self) -> Optional[NuxeoDocumentInfo]:
        with self._get_file_lock:
            if self._remote_file_queue.empty() and self._local_file_queue.empty():
                return None
            if self._remote_file_queue.qsize() > self._local_file_queue.qsize():
                state = self._get_remote_file()
            else:
                state = self._get_local_file()
        if state is not None and self._is_on_error(state.id):
            return self._get_file()
        return state

    @pyqtSlot()
    def _thread_finished(self) -> None:
        with self._thread_inspection:
            for thread in self._processors_pool:
                if thread.isFinished():
                    self._processors_pool.remove(thread)
            if (
                self._local_folder_thread is not None
                and self._local_folder_thread.isFinished()
            ):
                self._local_folder_thread = None
            if (
                self._local_file_thread is not None
                and self._local_file_thread.isFinished()
            ):
                self._local_file_thread = None
            if (
                self._remote_folder_thread is not None
                and self._remote_folder_thread.isFinished()
            ):
                self._remote_folder_thread = None
            if (
                self._remote_file_thread is not None
                and self._remote_file_thread.isFinished()
            ):
                self._remote_file_thread = None
            if not self._engine.is_paused() and not self._engine.is_stopped():
                self.newItem.emit(None)

    def active(self) -> bool:
        # Recheck threads
        self._thread_finished()
        return self.is_active()

    def is_active(self) -> bool:
        return any(
            {
                self._local_folder_thread is not None,
                self._local_file_thread is not None,
                self._remote_file_thread is not None,
                self._remote_folder_thread is not None,
                len(self._processors_pool) > 0,
            }
        )

    def _create_thread(self, item_getter: Callable, **kwargs: Any) -> QThread:
        processor = self._engine.create_processor(item_getter, **kwargs)
        thread = self._engine.create_thread(worker=processor)
        thread.finished.connect(self._thread_finished)
        thread.start()
        return thread

    def get_metrics(self) -> Metrics:
        metrics = {
            "local_folder_queue": self._local_folder_queue.qsize(),
            "local_file_queue": self._local_file_queue.qsize(),
            "remote_folder_queue": self._remote_folder_queue.qsize(),
            "remote_file_queue": self._remote_file_queue.qsize(),
            "remote_file_thread": self._remote_file_thread is not None,
            "remote_folder_thread": self._remote_folder_thread is not None,
            "local_file_thread": self._local_file_thread is not None,
            "local_folder_thread": self._local_folder_thread is not None,
            "error_queue": self.get_errors_count(),
            "additional_processors": len(self._processors_pool),
        }
        metrics["total_queue"] = (
            metrics["local_folder_queue"]
            + metrics["local_file_queue"]
            + metrics["remote_folder_queue"]
            + metrics["remote_file_queue"]
        )
        return metrics

    def get_overall_size(self) -> int:
        return (
            self._local_folder_queue.qsize()
            + self._local_file_queue.qsize()
            + self._remote_folder_queue.qsize()
            + self._remote_file_queue.qsize()
        )

    @staticmethod
    def is_processing_file(proc: QThread, path: str, exact_match: bool = False) -> bool:
        if not proc:
            return False

        worker = proc.worker
        if not isinstance(worker, Processor):
            return False

        doc_pair = worker.get_current_pair()
        if doc_pair is None or doc_pair.local_path is None:
            return False

        if exact_match:
            result = doc_pair.local_path == path
        else:
            result = doc_pair.local_path.startswith(path)
        if result:
            log.trace(f"Worker({worker.get_metrics()!r}) is processing: {path!r}")
        return result

    def interrupt_processors_on(self, path: str, exact_match: bool = True) -> None:
        for proc in self.get_processors_on(path, exact_match):
            proc.stop()

    def get_processors_on(self, path: str, exact_match: bool = True) -> List[Processor]:
        with self._thread_inspection:
            res = []
            if self.is_processing_file(
                self._local_folder_thread, path, exact_match=exact_match
            ):
                res.append(self._local_folder_thread.worker)
            elif self.is_processing_file(
                self._remote_folder_thread, path, exact_match=exact_match
            ):
                res.append(self._remote_folder_thread.worker)
            elif self.is_processing_file(
                self._local_file_thread, path, exact_match=exact_match
            ):
                res.append(self._local_file_thread.worker)
            elif self.is_processing_file(
                self._remote_file_thread, path, exact_match=exact_match
            ):
                res.append(self._remote_file_thread.worker)
            else:
                for thread in self._processors_pool:
                    if self.is_processing_file(thread, path, exact_match=exact_match):
                        res.append(thread.worker)
        return res

    def has_file_processors_on(self, path: str) -> bool:
        with self._thread_inspection:
            # First check local and remote file
            if self.is_processing_file(
                self._local_file_thread or self._remote_file_thread, path
            ):
                return True
            for thread in self._processors_pool:
                if self.is_processing_file(thread, path):
                    return True
            return False

    @pyqtSlot()
    def launch_processors(self) -> None:
        if (
            self._disable
            or self.is_paused()
            or (
                self._local_folder_queue.empty()
                and self._local_file_queue.empty()
                and self._remote_folder_queue.empty()
                and self._remote_file_queue.empty()
            )
        ):
            if not self.is_active():
                self.queueFinishedProcessing.emit()
            return

        if (
            self._local_folder_thread is None
            and not self._local_folder_queue.empty()
            and self._local_folder_enable
        ):
            self._local_folder_thread = self._create_thread(
                self._get_local_folder, name="LocalFolderProcessor"
            )

        if (
            self._local_file_thread is None
            and not self._local_file_queue.empty()
            and self._local_file_enable
        ):
            self._local_file_thread = self._create_thread(
                self._get_local_file, name="LocalFileProcessor"
            )

        if (
            self._remote_folder_thread is None
            and not self._remote_folder_queue.empty()
            and self._remote_folder_enable
        ):
            self._remote_folder_thread = self._create_thread(
                self._get_remote_folder, name="RemoteFolderProcessor"
            )

        if (
            self._remote_file_thread is None
            and not self._remote_file_queue.empty()
            and self._remote_file_enable
        ):
            self._remote_file_thread = self._create_thread(
                self._get_remote_file, name="RemoteFileProcessor"
            )

        if self._remote_file_queue.qsize() == 0 and self._local_file_queue.qsize() == 0:
            return

        while len(self._processors_pool) < self._max_processors:
            self._processors_pool.append(
                self._create_thread(self._get_file, name="GenericProcessor")
            )
