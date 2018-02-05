# coding: utf-8
""" Evolution to try new engine solution. """

from logging import getLogger

from nxdrive.engine.engine import Engine

log = getLogger(__name__)


class EngineNext(Engine):
    type = 'NXDRIVENEXT'

    def create_processor(self, item_getter, name=None):
        from nxdrive.engine.next.processor import Processor
        return Processor(self, item_getter, name=name)

    def _create_queue_manager(self, processors):
        from nxdrive.engine.next.queue_manager import QueueManager
        from nxdrive.options import Options

        if Options.debug:
            return QueueManager(self, self._dao, max_file_processors=2)
        return QueueManager(self, self._dao)

    def _create_local_watcher(self):
        from nxdrive.engine.next.simple_watcher import SimpleWatcher
        return SimpleWatcher(self, self._dao)
