'''
@author: Remi Cattiau
'''
from PyQt4.QtCore import QThread, QObject, pyqtSignal, pyqtSlot, QCoreApplication
from threading import current_thread
from time import sleep
from nxdrive.engine.activity import Action, IdleAction
from nxdrive.logging_config import get_logger

log = get_logger(__name__)


class ThreadInterrupt(Exception):
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
        self._thread.terminated.connect(self._terminated)

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
        self._thread.stop()

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
            sleep(1)
        # Handle thread interruption
        if not self._continue:
            raise ThreadInterrupt()

    def _execute(self):
        while (1):
            self._interact()
            sleep(1)

    def _terminated(self):
        log.debug("Thread %s(%d) terminated"
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

    def _clean(self, reason, e=None):
        pass


class EngineWorker(Worker):
    def __init__(self, engine, thread=None, name=None):
        super(EngineWorker, self).__init__(thread, name)
        self._engine = engine

    def _clean(self, reason, e=None):
        self._engine.get_dao().dispose_thread()


class PollWorker(Worker):
    def __init__(self, check_interval, thread=None, name=None):
        super(PollWorker, self).__init__(thread, name)
        # Be sure to run on start
        self._thread.started.connect(self.run)
        self._check_interval = check_interval
        # Check at start
        self._current_interval = 0
        self._enable = True

    def get_metrics(self):
        metrics = super(PollWorker, self).get_metrics()
        metrics['polling_interval'] = self._check_interval
        metrics['polling_next'] = self._current_interval
        return dict(metrics.items() + self._metrics.items())

    def _execute(self):
        while (self._enable):
            self._interact()
            if self._current_interval == 0:
                self._poll()
                self._current_interval = self._check_interval
            else:
                self._current_interval = self._current_interval - 1
            sleep(1)

    def _poll(self):
        pass

'''
' Just a DummyWorker with infinite loop
'''


class DummyWorker(Worker):
    def _execute(self):
        while (1):
            self._interact()
            sleep(1)


'''
' Just a CrazyWorker with infinite loop - no control
'''


class CrazyWorker(Worker):
    def _execute(self):
        while (1):
            sleep(1)

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

