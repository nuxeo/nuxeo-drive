# coding: utf-8
from contextlib import suppress
from logging import getLogger
from threading import current_thread
from time import sleep, time
from typing import Any, Dict, Optional, TYPE_CHECKING

from PyQt5.QtCore import QCoreApplication, QObject, QThread, pyqtSlot

from .activity import Action, IdleAction
from ..exceptions import ThreadInterrupt
from ..objects import Metrics, DocPair

if TYPE_CHECKING:
    from .dao.sqlite import EngineDAO  # noqa
    from .engine import Engine  # noqa

__all__ = ("EngineWorker", "PollWorker", "Worker")

log = getLogger(__name__)


class Worker(QObject):
    """" Utility class that handle one thread. """

    def __init__(self, thread: QThread = None, **kwargs: Any) -> None:
        super().__init__()
        if thread is None:
            thread = QThread()
        self.moveToThread(thread)

        thread.worker = self
        self.thread = thread

        self._name = kwargs.get("name", type(self).__name__)

        self._running = False
        self._continue = False
        self._action: Optional[Action] = None
        self.thread_id: Optional[int] = None
        self._pause = False

        self.thread.finished.connect(self._finished)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} id={self.thread_id}>"

    def export(self) -> Dict[str, Any]:
        action = self.action
        return {
            "action": action.export() if action else None,
            "thread_id": self.thread_id,
            "name": self._name,
            "paused": self.is_paused(),
            "started": self.is_started(),
        }

    def is_started(self) -> bool:
        return self._continue

    def is_paused(self) -> bool:
        return self._pause

    def start(self) -> None:
        """
        Start the worker thread
        """
        self.thread.start()
        log.debug("Thread START")

    def stop(self) -> None:
        """
        Stop the thread, wait 5s before trying to terminate it.
        Return when thread is stopped or 5s max after the termination of
        the thread is sent.
        """

        self.quit()

        if self.thread.isRunning():
            self.thread.wait(5000)

        if self.thread.isRunning():
            log.warning("Thread ZOMBIE")
            self.thread.terminate()

    def resume(self) -> None:
        """ Resume the thread. """

        self._pause = False

    def suspend(self) -> None:
        """
        Ask for thread to suspend.
        It will be truly paused only when the thread call _interact.
        """

        self._pause = True

    def quit(self) -> None:
        """ Order the stop of the thread. Return before thread is stopped. """

        self._continue = False
        self.thread.quit()

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
        log.debug("Thread END")

    @property
    def action(self) -> Action:
        if self._action is None:
            self._action = Action.get_current_action(self.thread_id)
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
            "thread_id": self.thread_id,
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
        self.thread_id = current_thread().ident

        try:
            try:
                self._execute()
            except ThreadInterrupt:
                log.debug("Thread INTERRUPT")
            except Exception:
                log.exception("Thread EXCEPTION")
        finally:
            self.quit()
            self._running = False


class EngineWorker(Worker):
    def __init__(
        self, engine: "Engine", dao: "EngineDAO", thread: QThread = None, **kwargs: Any
    ) -> None:
        super().__init__(thread=thread, **kwargs)
        self.engine = engine
        self.dao = dao

    def giveup_error(
        self, doc_pair: DocPair, error: str, exception: Exception = None
    ) -> None:
        details = str(exception) if exception else None
        log.info(f"Give up for error [{error}] ({details}) for {doc_pair!r}")
        self.dao.increase_error(
            doc_pair,
            error,
            details=details,
            incr=self.engine.queue_manager.get_error_threshold() + 1,
        )
        # Push it to generate the error notification
        self.engine.queue_manager.push_error(doc_pair, exception=exception)

    def increase_error(
        self, doc_pair: DocPair, error: str, exception: Exception = None
    ) -> None:
        details = None
        if exception:
            try:
                details = getattr(exception, "message")
            except AttributeError:
                details = str(exception)
        log.info(f"Increasing error [{error}] ({details}) for {doc_pair!r}")
        self.dao.increase_error(doc_pair, error, details=details)
        self.engine.queue_manager.push_error(doc_pair, exception=exception)

    def remove_void_transfers(self, doc_pair: DocPair) -> None:
        """ Remove uploads and downloads on the target doc pair. """
        if doc_pair.folderish:
            # Folderish documents don't use transfers
            return

        fullpath = self.engine.local.abspath(doc_pair.local_path)
        for nature in ("download", "upload"):
            self.dao.remove_transfer(nature, fullpath)


class PollWorker(Worker):
    def __init__(
        self, check_interval: int, thread: QThread = None, **kwargs: Any
    ) -> None:
        super().__init__(thread=thread, **kwargs)
        # Be sure to run on start
        self.thread.started.connect(self.run)
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

    def _poll(self) -> bool:
        return True
