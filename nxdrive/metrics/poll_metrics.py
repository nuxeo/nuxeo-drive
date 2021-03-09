from logging import getLogger
from queue import Empty, Queue
from time import monotonic_ns
from typing import TYPE_CHECKING

from ..constants import TIMEOUT
from ..engine.workers import PollWorker
from ..exceptions import ThreadInterrupt
from ..objects import Metrics
from ..options import Options
from ..qt.imports import pyqtSlot
from .constants import CHECK_INTERVAL, ENDPOINT, SYNC_ACTION, SYNC_TIME

log = getLogger(__name__)


if TYPE_CHECKING:
    from ..client.remote_client import Remote


class CustomPollMetrics(PollWorker):
    def __init__(self, remote: "Remote") -> None:
        super().__init__(CHECK_INTERVAL, "CustomMetrics")

        self._remote = remote
        self._metrics_queue: Queue = Queue()

        self._timeout = Options.timeout if Options.timeout > 0 else TIMEOUT
        self._enabled = Options.custom_metrics

    def _poll(self) -> bool:
        if not self._enabled:
            self.quit()  # Quit thread on first poll
            return False

        errors = []  # Errors are stored and re-injected on exception
        try:
            while True:
                try:
                    metrics = self._metrics_queue.get_nowait()
                    print(f"Sending {metrics}")  # DEV
                except Empty:
                    break
                try:
                    self._remote.client.request(
                        "GET", ENDPOINT, headers=metrics, timeout=self._timeout
                    )
                except ThreadInterrupt:
                    raise
                except Exception:
                    log.warning(
                        "Could not send metrics. Pushing to queue.", exc_info=True
                    )
                    errors.append(metrics)
        finally:
            for elem in errors:
                self.send(elem)
        return True

    def send(self, metrics: Metrics) -> None:
        if self._enabled:
            self._metrics_queue.put(metrics)

    @pyqtSlot(object)
    def push_sync_event(self, metrics: Metrics, /) -> None:
        if not self._enabled:
            return
        elapsed = monotonic_ns() - metrics["start_ns"]
        self.send(
            {
                SYNC_ACTION: metrics["handler"],
                SYNC_TIME: elapsed,
            }
        )
