# coding: utf-8
import time
from logging import getLogger
from typing import TYPE_CHECKING

from ..queue_manager import QueueManager as OldQueueManager
from ...objects import DocPair

if TYPE_CHECKING:
    from ..engine.engine import Engine  # noqa
    from ..engine.dao.sqlite import EngineDAO  # noqa

__all__ = ("QueueManager",)

log = getLogger(__name__)


class QueueManager(OldQueueManager):
    def __init__(
        self, engine: "Engine", dao: "EngineDAO", max_file_processors: int = 5
    ) -> None:
        super().__init__(engine, dao, max_file_processors=max_file_processors)

    def postpone_pair(self, doc_pair: DocPair, interval: int = 60) -> None:
        doc_pair.error_next_try = interval + int(time.time())
        log.debug(f"Blacklisting pair for {interval}s: {doc_pair!r}")
        with self._error_lock:
            self._on_error_queue[doc_pair.id] = doc_pair
            if not self._error_timer.isActive():
                self.newError.emit(doc_pair.id)
