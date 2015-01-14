from PyQt4.QtCore import QObject
from Queue import Queue
from nxdrive.logging_config import get_logger
log = get_logger(__name__)

class QueueItem(object):
    def __init__(self, row_id, folderish, pair_state):
        self.id = row_id
        self.folderish = folderish
        self.pair_state = pair_state


class QueueManager(QObject):
    '''
    classdocs
    '''
    def __init__(self, dao, max_processor=5):
        '''
        Constructor
        '''
        super(QueueManager, self).__init__()
        self._dao = dao
        self._folder_queue = Queue()
        self._local_queue = Queue()
        self._remote_queue = Queue()
        self._dao.register_queue_manager(self)

    def init_queue(self, queue):
        # Dont need to change modify as State is compatible with QueueItem
        for item in queue:
            self.push(item)
        pass

    def push_ref(self, row_id, folderish, pair_state):
        self.push(QueueItem(row_id, folderish, pair_state))

    def push(self, object):
        log.trace("Pushing %d[f:%d] with state: %s", object.id, object.folderish, object.pair_state)
        if object.folderish:
            self._folder_queue.put(object)
        elif object.pair_state.startswith('locally'):
            self._local_queue.put(object)
        elif object.pair_state.startswith('remotely'):
            self._remote_queue.put(object)
        else:
            # deleted and conflicted
            pass