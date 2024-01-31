from contextlib import suppress
from logging import getLogger
from time import sleep, time
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from ..exceptions import ThreadInterrupt
from ..metrics.constants import SYNC_ACTION, SYNC_ERROR_LABEL
from ..objects import DocPair, Metrics
from ..qt.imports import QCoreApplication, QObject, QRunnable, QThread, pyqtSlot
from ..utils import current_thread_id
from .activity import Action, IdleAction

if TYPE_CHECKING:
    from ..dao.engine import EngineDAO  # noqa
    from .engine import Engine  # noqa

__all__ = ("EngineWorker", "PollWorker", "Worker")

log = getLogger(__name__)


class Runner(QRunnable):
    """A simple Qt runner."""

    def __init__(self, fn: Callable, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.error: Optional[Exception] = None

    def run(self) -> None:
        """Start the work!"""
        try:
            self.fn(*self.args, **self.kwargs)
        except Exception as exc:
            self.error = exc


class Worker(QObject):
    """ " Utility class that handle one thread."""

    def __init__(self, name: str, /) -> None:
        super().__init__()
        thread = QThread()
        self.moveToThread(thread)

        thread.worker = self
        self.thread = thread

        self._name = name

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
        """Resume the thread."""

        self._pause = False

    def suspend(self) -> None:
        """
        Ask for thread to suspend.
        It will be truly paused only when the thread call _interact.
        """

        self._pause = True

    def quit(self) -> None:
        """Order the stop of the thread. Return before thread is stopped."""

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
            self._action = Action.get_current_action(thread_id=self.thread_id)
        if self._action is None:
            self._action = IdleAction()
        return self._action

    @action.setter
    def action(self, value: Any, /) -> None:
        self._action = value

    def get_metrics(self) -> Metrics:
        """
        Get the Worker metrics.
        :return a dict with different variables that represent the worker
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
        self.thread_id = current_thread_id()

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
    def __init__(self, engine: "Engine", dao: "EngineDAO", name: str, /) -> None:
        super().__init__(name)
        self.engine = engine
        self.dao = dao

    def giveup_error(
        self, doc_pair: DocPair, error: str, /, *, exception: Exception = None
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
        self.engine.send_metric("sync", "error", error)
        metrics = {
            SYNC_ERROR_LABEL: error.lower(),
            SYNC_ACTION: doc_pair.pair_state,
        }
        self.engine.remote.metrics.send(metrics)

    def increase_error(
        self, doc_pair: DocPair, error: str, /, *, exception: Exception = None
    ) -> None:
        details = str(exception) if exception else None
        log.info(f"Increasing error [{error}] ({details}) for {doc_pair!r}")
        self.dao.increase_error(doc_pair, error, details=details)
        self.engine.queue_manager.push_error(doc_pair, exception=exception)

    def remove_void_transfers(self, doc_pair: DocPair, /) -> None:
        """Remove uploads and downloads on the target doc pair."""
        if doc_pair.folderish:
            # Folderish documents don't use transfers
            return

        fullpath = doc_pair.local_path
        if doc_pair.local_state != "direct":
            fullpath = self.engine.local.abspath(fullpath)
        for nature in ("download", "upload"):
            self.dao.remove_transfer(
                nature,
                path=fullpath,
                is_direct_transfer=doc_pair.local_state == "direct",
            )


class PollWorker(Worker):
    def __init__(self, check_interval: int, name: str, /) -> None:
        super().__init__(name)
        # Be sure to run on start
        self.thread.started.connect(self.run)
        self._check_interval = check_interval
        # Check at start
        self._next_check = 0
        self._metrics = {"last_poll": 0}

    @property
    def enable(self) -> bool:
        """This is a property to let subclasses changes its state dynamically."""
        return True

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
        while True:
            self._interact()
            if self.get_next_poll() <= 0:
                if self.enable and self._poll():
                    self._metrics["last_poll"] = int(time())
                self._next_check = int(time()) + self._check_interval
            sleep(1)

    def _poll(self) -> bool:
        return True
