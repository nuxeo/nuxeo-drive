'''
@author: Remi Cattiau
'''
from PyQt4.QtCore import QThread, QObject, pyqtSignal, pyqtSlot, QCoreApplication
from threading import current_thread
from time import sleep, time
from nxdrive.engine.activity import Action, IdleAction
from nxdrive.logging_config import get_logger
from urllib2 import HTTPError

log = get_logger(__name__)


class ThreadInterrupt(Exception):
    pass


class PairInterrupt(Exception):
    pass

'''
' Utility class that handle one thread
'''


class Worker(QObject):
    _thread = None
    _continue = False
    _action = None
    _name = None
    _thread_id = None
    _engine = None
    _pause = False
    actionUpdate = pyqtSignal(object)
    stopWorker = pyqtSignal()

    def __init__(self, thread=None, name=None):
        super(Worker, self).__init__()
        if thread is None:
            thread = QThread()
        self.moveToThread(thread)
        thread.worker = self
        self._thread = thread
        if name is None:
            name = type(self).__name__
        self._name = name
        self._running = False
        self._thread.terminated.connect(self._terminated)
        self.stopWorker.connect(self.quit)

    @pyqtSlot()
    def quit(self):
        self._continue = False

    def is_started(self):
        return self._continue

    def is_paused(self):
        return self._pause

    def start(self):
        self._thread.start()

    def stop(self):
        self._continue = False
        self.stopWorker.emit()
        if not self._thread.wait(5000):
            log.warn("Thread %d is not responding - terminate it", self._thread_id, exc_info=True)
            self._thread.terminate()
        if self._thread.isRunning():
            self._thread.wait(5000)

    def resume(self):
        self._pause = False

    def suspend(self):
        self._pause = True

    def _end_action(self):
        Action.finish_action()
        self._action = None

    def get_thread(self):
        return self._thread

    def _interact(self):
        QCoreApplication.processEvents()
        # Handle thread pause
        while (self._pause and self._continue):
            QCoreApplication.processEvents()
            sleep(0.01)
        # Handle thread interruption
        if not self._continue:
            raise ThreadInterrupt()

    def _execute(self):
        while (1):
            self._interact()
            sleep(0.01)

    def _terminated(self):
        log.debug("Thread %s(%r) terminated"
                    % (self._name, self._thread_id))

    def _update_action(self, action):
        self.actionUpdate.emit(action)

    def get_action(self):
        action = Action.get_current_action(self._thread_id)
        if action is None:
            action = self._action
        if action is None:
            action = IdleAction()
        return action

    def get_metrics(self):
        metrics = dict()
        metrics['name'] = self._name
        metrics['thread_id'] = self._thread_id
        # Get action from activity as methods can have its own Action
        metrics['action'] = self.get_action()
        if hasattr(self, '_metrics'):
            metrics = dict(metrics.items() + self._metrics.items())
        return metrics

    @pyqtSlot()
    def run(self):
        if self._running:
            return
        self._running = True
        self._continue = True
        self._pause = False
        reason = ''
        self._thread_id = current_thread().ident
        e = None
        try:
            try:
                log.debug("Thread %s(%d) start"
                            % (self._name, self._thread_id))
                self._execute()
                log.debug("Thread %s(%d) end"
                            % (self._name, self._thread_id))
            except ThreadInterrupt:
                log.debug("Thread %s(%d) interrupted"
                            % (self._name, self._thread_id))
                reason = 'interrupt'
            except Exception as ex:
                log.warn("Thread %s(%d) ended with exception : %r"
                                % (self._name, self._thread_id, ex))
                log.exception(ex)
                e = ex
                reason = 'exception'
            self._clean(reason, e)
        finally:
            self._thread.exit(0)
            self._running = False

    def _clean(self, reason, e=None):
        pass


class EngineWorker(Worker):
    def __init__(self, engine, dao, thread=None, name=None):
        super(EngineWorker, self).__init__(thread, name)
        self._engine = engine
        self._engine.invalidClientsCache.connect(self._reset_clients)
        self._dao = dao

    @pyqtSlot()
    def _reset_clients(self):
        pass

    def _clean(self, reason, e=None):
        if e is not None and type(e) == HTTPError:
            if e.code == 401:
                self._engine.set_invalid_credentials(reason="got HTTPError %d while cleaning EngineWorker '%s'"
                                                     % (e.code, self._name), exception=e)
                self._reset_clients()
        self._engine.get_dao().dispose_thread()

    def giveup_error(self, doc_pair, error, exception=None):
        details = repr(exception) if exception else None
        log.debug('Give up for error [%s] (%r) for %r', error, details, doc_pair)
        self._dao.increase_error(doc_pair, error, details=details, incr=self._engine.get_queue_manager().get_error_threshold()+1)
        # Push it to generate the error notification
        self._engine.get_queue_manager().push_error(doc_pair, exception=exception)

    def increase_error(self, doc_pair, error, exception=None):
        details = repr(exception) if exception else None
        log.debug('Increasing error [%s] (%r) for %r', error, details, doc_pair)
        self._dao.increase_error(doc_pair, error, details=details)
        self._engine.get_queue_manager().push_error(doc_pair, exception=exception)


class PollWorker(Worker):
    def __init__(self, check_interval, thread=None, name=None):
        super(PollWorker, self).__init__(thread, name)
        # Be sure to run on start
        self._thread.started.connect(self.run)
        self._check_interval = check_interval
        # Check at start
        self._next_check = 0
        self._enable = True
        self._metrics = dict()
        self._metrics['last_poll'] = 0

    def get_metrics(self):
        metrics = super(PollWorker, self).get_metrics()
        metrics['polling_interval'] = self._check_interval
        metrics['polling_next'] = self.get_next_poll()
        return dict(metrics.items() + self._metrics.items())

    def get_last_poll(self):
        if self._metrics['last_poll'] > 0:
            return int(time()) - self._metrics['last_poll']
        else:
            return -1

    def get_next_poll(self):
        return self._next_check - int(time())

    @pyqtSlot()
    def force_poll(self):
        self._next_check = 0

    def _execute(self):
        while (self._enable):
            self._interact()
            if self.get_next_poll() <= 0:
                if self._poll():
                    self._metrics['last_poll'] = int(time())
                self._next_check = int(time()) + self._check_interval
            sleep(0.01)

    def _poll(self):
        return True

'''
' Just a DummyWorker with infinite loop
'''


class DummyWorker(Worker):
    def _execute(self):
        while (1):
            self._interact()
            sleep(0.01)


'''
' Just a CrazyWorker with infinite loop - no control
'''


class CrazyWorker(Worker):
    def _execute(self):
        while (1):
            sleep(0.01)

'''
' Just a DummyWorker with progression from 0 to 100
'''


class ProgressWorker(Worker):
    def _execute(self):
        self._progress = 0
        while (self._progress < 100):
            self._interact()
            self._progress = self._progress + 1
            sleep(1)

    def get_metrics(self):
        metrics = super(ProgressWorker, self).get_metrics()
        metrics['progress'] = self._progress
        return metrics

