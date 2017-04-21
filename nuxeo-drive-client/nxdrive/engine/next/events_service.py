from PyQt4.QtCore import QObject, pyqtSignal, pyqtSlot
import threading


class Event:
    def __init__(self):
        pass

    def to_command(self):
        pass

class EventsService(QObject):
    '''
    Service which handle events from watcher
    '''

    flushed = pyqtSignal(object)
    events_ = []
    lock_ = threading.Lock()
    analysers_ = []

    def push_event(self, event):
        '''
        Push an event to the 'queue'
        :param event: Event to push
        :return:
        '''
        # Store event
        # Write log
        # Start IO if needed / possible
        with self.lock_:
            self.events_.append(event)
        pass

    def register_analyser(self, analyser):
        '''
        Register an analyser on the queue
        :param analyser:
        :return:
        '''
        self.analysers_.append(analyser)

    '''
    Start a flush of events
    '''
    @pyqtSlot()
    def flush(self):
        with self._lock:
            batch = self.events_
            self.events_ = []
        for analyser in self.analysers_:
            analyser.handle(batch)
        self.flushed.emit(batch)
