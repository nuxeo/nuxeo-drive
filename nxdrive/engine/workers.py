# coding: utf-8
from contextlib import suppress
from logging import getLogger
from threading import current_thread
from time import sleep, time
from typing import Any

from PyQt5.QtCore import QCoreApplication, QObject, QThread, pyqtSlot

from .activity import Action, IdleAction
from ..exceptions import ThreadInterrupt
from ..objects import Metrics, NuxeoDocumentInfo

__all__ = ("EngineWorker", "PollWorker", "Worker")

log = getLogger(__name__)


class Worker(QObject):
    """" Utility class that handle one thread. """

    _thread = None
    _continue = False
    _action = None
    _name = None
    _thread_id = None
    engine = None
    _pause = False

    def __init__(self, thread: QThread = None, **kwargs: Any) -> None:
        super().__init__()
        if thread is None:
            thread = QThread()
        self.moveToThread(thread)
        thread.worker = self
        self._thread = thread
        self._name = kwargs.get("name", type(self).__name__)
        self._running = False
        self._thread.finished.connect(self._finished)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} ID={self._thread_id}>"

    def is_started(self) -> bool:
        return self._continue

    def is_paused(self) -> bool:
        return self._pause

    def start(self) -> None:
        """
        Start the worker thread
        """
        self._thread.start()

    def stop(self) -> None:
        """
        Stop the thread, wait 5s before trying to terminate it.
        Return when thread is stopped or 5s max after the termination of
        the thread is sent.
        """

        self._continue = False
        if not self._thread.wait(5000):
            log.exception(f"Thread {self._thread_id} is not responding - terminate it")
            self._thread.terminate()
        if self._thread.isRunning():
            self._thread.wait(5000)

    def resume(self) -> None:
        """ Resume the thread. """

        self._pause = False

    def suspend(self) -> None:
        """
        Ask for thread to suspend.
        It will be truly paused only when the thread call _interact.
        """

        self._pause = True

    def _end_action(self) -> None:
        Action.finish_action()
        self._action = None

    def get_thread(self) -> QThread:
        """ Return worker internal thread. """

        return self._thread

    def quit(self) -> None:
        """ Order the stop of the thread. Return before thread is stopped. """

        self._continue = False

    def get_thread_id(self) -> int:
        """ Get the thread ID. """

        return self._thread_id

    def _interact(self) -> None:
        """
        Interact for signal/slot on Qt.
        Also handle the pause/resume of the thread and interruption.
        Return after QT events are processed or thread has been resumed.
        Throw a ThreadInterrupt if the stopping of the thread has been
        order either by stop or quit.
        """

        QCoreApplication.processEvents()
        # Handle thread pause
        while self._pause and self._continue:
            QCoreApplication.processEvents()
            sleep(0.01)
        # Handle thread interruption
        if not self._continue:
            raise ThreadInterrupt()

    def _execute(self) -> None:
        """
        Empty execute method, override this method to add your worker logic.
        """

        while True:
            self._interact()
            sleep(0.01)

    def _finished(self) -> None:
        log.trace(f"Thread {self._name}({self._thread_id}) finished")

    @property
    def action(self) -> Action:
        if self._action is None:
            self._action = Action.get_current_action(self._thread_id)
            if self._action is None:
                self._action = IdleAction()
        return self._action

    @action.setter
    def action(self, value: Any) -> None:
        self._action = value

    def get_metrics(self) -> Metrics:
        """
        Get the Worker metrics.
        :return a dict with differents variables that represent the worker
                activity
        """

        metrics = {
            "name": self._name,
            "thread_id": self._thread_id,
            "action": self.action,
        }
        with suppress(AttributeError):
            metrics.update(self._metrics)
        return metrics

    @pyqtSlot()
    def run(self) -> None:
        """
        Handle the infinite loop run by the worker thread.
        It handles exception and logging.
        """

        if self._running:
            return
        self._running = True
        self._continue = True
        self._pause = False
        self._thread_id = current_thread().ident
        try:
            try:
                self._execute()
            except ThreadInterrupt:
                log.debug(f"Thread {self._name}({self._thread_id}) interrupted")
            except:
                log.exception(f"Thread {self._name}({self._thread_id}) exception")
        finally:
            self._thread.exit(0)
            self._running = False


class EngineWorker(Worker):
    def __init__(
        self, engine: "Engine", dao: "EngineDAO", thread: QThread = None, **kwargs: Any
    ) -> None:
        super().__init__(thread=thread, **kwargs)
        self.engine = engine
        self._dao = dao

    def giveup_error(
        self, doc_pair: NuxeoDocumentInfo, error: str, exception: Exception = None
    ) -> None:
        details = str(exception) if exception else None
        log.debug(f"Give up for error [{error}] ({details}) for {doc_pair!r}")
        self._dao.increase_error(
            doc_pair,
            error,
            details=details,
            incr=self.engine.get_queue_manager().get_error_threshold() + 1,
        )
        # Push it to generate the error notification
        self.engine.get_queue_manager().push_error(doc_pair, exception=exception)

    def increase_error(
        self, doc_pair: NuxeoDocumentInfo, error: str, exception: Exception = None
    ) -> None:
        details = None
        if exception:
            try:
                details = exception.message
            except AttributeError:
                details = str(exception)
        log.debug(f"Increasing error [{error}] ({details}) for {doc_pair!r}")
        self._dao.increase_error(doc_pair, error, details=details)
        self.engine.get_queue_manager().push_error(doc_pair, exception=exception)


class PollWorker(Worker):
    def __init__(
        self, check_interval: int, thread: QThread = None, **kwargs: Any
    ) -> None:
        super().__init__(thread=thread, **kwargs)
        # Be sure to run on start
        self._thread.started.connect(self.run)
        self._check_interval = check_interval
        # Check at start
        self._next_check = 0
        self.enable = True
        self._metrics = {"last_poll": 0}

    def get_metrics(self) -> Metrics:
        metrics = super().get_metrics()
        metrics["polling_interval"] = self._check_interval
        metrics["polling_next"] = self.get_next_poll()
        return {**metrics, **self._metrics}

    def get_last_poll(self) -> int:
        if self._metrics["last_poll"] > 0:
            return int(time()) - self._metrics["last_poll"]
        return -1

    def get_next_poll(self) -> int:
        return self._next_check - int(time())

    @pyqtSlot()
    def force_poll(self) -> None:
        self._next_check = 0

    def _execute(self) -> None:
        while self.enable:
            self._interact()
            if self.get_next_poll() <= 0:
                if self._poll():
                    self._metrics["last_poll"] = int(time())
                self._next_check = int(time()) + self._check_interval
            sleep(0.01)

    def _poll(self) -> True:
        return True
