import json
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
from .constants import ENDPOINT, REQUEST_METRICS, SYNC_ACTION, SYNC_TIME

log = getLogger(__name__)


if TYPE_CHECKING:
    from ..client.remote_client import Remote


class CustomPollMetrics(PollWorker):
    def __init__(self, remote: "Remote") -> None:
        super().__init__(Options.custom_metrics_poll_interval, "CustomMetrics")

        self._remote = remote
        self._metrics_queue: Queue = Queue()
        self._timeout = Options.timeout if Options.timeout > 0 else TIMEOUT

    @property
    def enable(self) -> bool:
        state: bool = Options.custom_metrics
        return state

    def _poll(self) -> bool:
        dumps = json.dumps
        try:
            while True:
                try:
                    metrics = self._metrics_queue.get_nowait()
                except Empty:
                    break
                try:
                    headers = {REQUEST_METRICS: dumps(metrics)}
                    self._remote.client.request(
                        "GET", ENDPOINT, headers=headers, timeout=self._timeout
                    )
                except ThreadInterrupt:
                    raise
                except Exception:
                    # NXDRIVE-2676: do not send again metrics on error to not pollute logs.
                    log.warning("Could not send metrics", exc_info=True)
        except ThreadInterrupt:
            raise
        return True

    def force_poll(self) -> None:
        """Call the poll method without waiting for timeout."""
        self._poll()

    def send(self, metrics: Metrics) -> None:
        """Push metrics into the queue, if enabled."""
        if not self.enable or not metrics:
            return
        self._metrics_queue.put(metrics)

    @pyqtSlot(object)
    def push_sync_event(self, metrics: Metrics, /) -> None:
        """Transform then push metrics generated by the newSyncEnded signal, if enabled."""
        if not self.enable:
            return
        elapsed = monotonic_ns() - metrics["start_ns"]
        self.send({SYNC_ACTION: metrics["handler"], SYNC_TIME: elapsed})
