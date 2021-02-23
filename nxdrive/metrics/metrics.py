from logging import getLogger
from queue import Empty, Queue
from time import monotonic_ns
from typing import TYPE_CHECKING

from ..constants import TIMEOUT
from ..engine.workers import Worker
from ..exceptions import ThreadInterrupt
from ..objects import Metrics
from ..options import Options
from ..qt.imports import pyqtSlot
from .constants import ENDPOINT, SYNC_ACTION, SYNC_TIME

log = getLogger(__name__)


if TYPE_CHECKING:
    from ..client.remote_client import Remote


class CustomMetrics(Worker):
    def __init__(self, remote: "Remote") -> None:
        super().__init__("CustomMetrics")

        self._remote = remote
        self._metrics_queue: Queue = Queue()
        self._stop = False

        self.timeout = Options.timeout if Options.timeout > 0 else TIMEOUT
        self.thread.started.connect(self.run)

    def _execute(self) -> None:
        try:
            while True:
                try:
                    metrics = self._metrics_queue.get(timeout=1)
                    print(f"Sending {metrics}")  # DEV
                    if not Options.custom_metrics:
                        continue
                    self._remote.client.request(
                        "GET", ENDPOINT, headers=metrics, timeout=self.timeout
                    )
                except Empty:
                    continue
                except Exception:
                    log.warning(
                        "Could not send metrics. Pushing to queue.", exc_info=True
                    )
                    self.send(metrics)
                    continue
        except ThreadInterrupt:
            raise

    def send(self, metrics: Metrics) -> None:
        self._metrics_queue.put(metrics)

    @pyqtSlot(object)
    def push_sync_event(self, metrics: Metrics, /) -> None:
        elapsed = monotonic_ns() - metrics["start_ns"]
        self.send(
            {
                SYNC_ACTION: metrics["handler"],
                SYNC_TIME: elapsed,
            }
        )
