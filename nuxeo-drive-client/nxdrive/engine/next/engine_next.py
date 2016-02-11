__author__ = 'loopingz'
'''
Evolution to try new engine solution
'''
from nxdrive.engine.engine import Engine, DEFAULT_REMOTE_WATCHER_DELAY
from nxdrive.client.remote_document_client import RemoteDocumentClient
from nxdrive.client.remote_file_system_client import RemoteFileSystemClient
from nxdrive.client.remote_filtered_file_system_client import RemoteFilteredFileSystemClient
from nxdrive.logging_config import get_logger
log = get_logger(__name__)


class EngineNext(Engine):

    def __init__(self, manager, definition, binder=None, processors=5,
                 remote_watcher_delay=DEFAULT_REMOTE_WATCHER_DELAY,
                 remote_doc_client_factory=RemoteDocumentClient,
                 remote_fs_client_factory=RemoteFileSystemClient,
                 remote_filtered_fs_client_factory=RemoteFilteredFileSystemClient):
        super(EngineNext, self).__init__(manager, definition, binder, processors, remote_watcher_delay,
                 remote_doc_client_factory, remote_fs_client_factory, remote_filtered_fs_client_factory)
        self._type = "NXDRIVENEXT"

    def create_processor(self, item_getter, name=None):
        from nxdrive.engine.next.processor import Processor
        return Processor(self, item_getter, name=name)

    def _create_queue_manager(self, processors):
        from nxdrive.engine.next.queue_manager import QueueManager
        if self._manager.is_debug():
            return QueueManager(self, self._dao, max_file_processors=2)
        return QueueManager(self, self._dao)

    def _create_local_watcher(self):
        from nxdrive.engine.next.simple_watcher import SimpleWatcher
        return SimpleWatcher(self, self._dao)

    def get_local_client(self):
        # Disable auto deduplication / user shoud take the decision and it will be renamed on server
        result = super(EngineNext, self).get_local_client()
        result._disable_duplication = False
        return result
