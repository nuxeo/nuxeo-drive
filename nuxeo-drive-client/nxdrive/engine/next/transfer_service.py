from PyQt4.QtCore import pyqtSignal, pyqtSlot
from Queue import Queue
from threading import Lock
from nxdrive.engine.workers import Worker
import uuid


class Transfer:
    __slots__ = ['id_', 'state_', 'digest_', 'type_', 'url_']
    def __init__(self, type_, url, digest, state):
        self.id_ = uuid.uuid4()
        self.state_ = state
        self.url_ = url
        self.digest_ = digest
        self.type_ = type_

    def get_id(self):
        return self.id_

    def get_state(self):
        return self.state_

    def get_url(self):
        return self.url_

    def set_state(self, state):
        self.state_ = state

    def get_digest(self):
        return self.digest_

    def get_type(self):
        return self.type_


class TransferService(Worker):
    '''
    Handle the binary transfer
    For download: Just download the file to a temporary folder ( .partials by default )
    For upload: Create a batch on the server and transfer the file content
    '''

    transferError = pyqtSignal(str)
    transferFinished = pyqtSignal(str)

    def __init__(self, remote_client, threads=4):
        self.remote_client_ = remote_client
        self.max_threads_ = threads
        self.download_queue_ = Queue()
        self.upload_queue_ = Queue()
        self.transfers_ = {}
        self.lock_ = Lock()

    def download(self, url, digest):
        '''
        Start a download of file using a ThreadPool

        :param url: Download
        :param digest: Digest of the file to download
        :return: A transfer uuid
        '''
        transfer = Transfer('download', url, digest, 'queued')
        self.transfers_[transfer.get_id()] = transfer
        self._download_queue.put(transfer.get_id())
        return transfer.get_id()


    def upload(self, path, digest):
        '''
        Start a upload of file using a ThreadPool

        :param path: Path to the file to upload
        :param digest: Digest of the file to upload
        :return: A transfer uuid
        '''
        transfer = Transfer('upload', path, digest, 'queued')
        self.transfers_[transfer.get_id()] = transfer
        self._upload_queue.put(transfer.get_id())
        return transfer.get_id()

    @pyqtSlot()
    def pause(self):
        '''
        Need to interrupt the ThreadPool too
        :return:
        '''
        pass

    @pyqtSlot()
    def resume(self):
        '''
        Need to resume the ThreadPool
        :return:
        '''
        pass

    def state(self, id):
        '''
        Return transfer state

        'queued': In the queue but not yet processed
        'inprogress': Currently transfering
        'done': Transfered
        'error': An error occurred during transfer
        'unknown': TransferID not known
        :param id: TranferID
        :return: state of the transfer
        '''
        if id in self.transfers_:
            return self.transfers_[id].get_state()
        return 'unknown'

    def cancel(self, id):
        '''
        Cancel the transfer request
        :param id: TransferID
        :return:
        '''
        if id in self.transfers_:
            if self.transfers_[id].get_state() == 'progress':
                # Interrupt transfer thread
                pass
            elif self.transfers_[id].get_state() == 'done':
                # Clean file or batch
                pass
            with self.lock_:
                del self.transfers_[id]

    def _process(self):
        pass