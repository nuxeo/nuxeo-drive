# coding: utf-8
""" Evolution to try new engine solution. """

from logging import getLogger
from typing import Any, Callable, TYPE_CHECKING

from ..engine import Engine

if TYPE_CHECKING:
    from .queue_manager import QueueManager  # noqa
    from .simple_watcher import SimpleWatcher  # noqa

__all__ = ("EngineNext",)

log = getLogger(__name__)


class EngineNext(Engine):
    type = "NXDRIVENEXT"

    def create_processor(self, item_getter: Callable, **kwargs: Any):
        from .processor import Processor

        return Processor(self, item_getter, **kwargs)

    def _create_queue_manager(self, processors: int) -> "QueueManager":
        from .queue_manager import QueueManager  # noqa
        from ...options import Options

        if Options.debug:
            return QueueManager(self, self._dao, max_file_processors=2)
        return QueueManager(self, self._dao)

    def _create_local_watcher(self) -> "SimpleWatcher":
        from .simple_watcher import SimpleWatcher  # noqa

        return SimpleWatcher(self, self._dao)
