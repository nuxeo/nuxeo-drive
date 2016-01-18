__author__ = 'loopingz'
from nxdrive.engine.queue_manager import QueueManager as OldQueueManager
from nxdrive.logging_config import get_logger
import time
log = get_logger(__name__)


class QueueManager(OldQueueManager):
    def __init__(self, engine, dao, max_file_processors=5):
        super(QueueManager, self).__init__(engine, dao, max_file_processors=5)

    def postpone_pair(self, doc_pair, interval=60):
        doc_pair.error_next_try = interval + int(time.time())
        log.debug("Blacklisting pair for %ds: %r", interval, doc_pair)
        self._error_lock.acquire()
        try:
            self._on_error_queue[doc_pair.id] = doc_pair
            if not self._error_timer.isActive():
                self.newError.emit(doc_pair.id)
        finally:
            self._error_lock.release()
