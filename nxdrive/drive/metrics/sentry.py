import os
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, Dict

from sentry_sdk import metrics

from ..engine.workers import PollWorker
from ..options import Options
from ..qt.imports import pyqtSlot

if TYPE_CHECKING:
    from ..manager import Manager


class SentryMetrics(PollWorker):
    def __init__(self, manager: "Manager", /, *, interval: int = 60 * 60) -> None:
        super().__init__(interval, "SentryMetrics")
        self.manager = manager

    @property
    def enable(self) -> bool:
        return Options.use_analytics

    @pyqtSlot(object)
    def send_sync_event(self, event: Dict[str, Any], /) -> None:
        if not self.enable:
            return

        elapsed = monotonic_ns() - event["start_ns"]
        if elapsed > 0:
            metrics.distribution(
                "drive.sync.duration",
                elapsed,
                unit="nanosecond",
                tags={"handler": event["handler"]},
            )

    @pyqtSlot(str, int)
    def send_direct_edit_open(self, filename: str, timing: int, /) -> None:
        self._send_direct_edit("open", filename, timing)

    @pyqtSlot(str, int)
    def send_direct_edit_edit(self, filename: str, timing: int, /) -> None:
        self._send_direct_edit("edit", filename, timing)

    def _send_direct_edit(self, action: str, filename: str, timing: int, /) -> None:
        if not self.enable:
            return

        extension = os.path.splitext(filename)[1].lower() or "unknown"
        metrics.distribution(
            "drive.direct_edit.duration",
            timing,
            unit="millisecond",
            tags={"action": action, "extension": extension},
        )

    @pyqtSlot(bool, int)
    def send_direct_transfer(self, folderish: bool, size: int, /) -> None:
        if not self.enable:
            return

        metrics.distribution(
            "drive.direct_transfer.size",
            size,
            unit="byte",
            tags={"type": "folder" if folderish else "file"},
        )

    @pyqtSlot()
    def send_stats(self) -> None:
        if not self.enable:
            return

        for engine in self.manager.engines.copy().values():
            for key, value in engine.get_metrics().items():
                if isinstance(value, int):
                    metrics.gauge(f"drive.engine.{key}", value)

    @pyqtSlot()
    def _poll(self) -> bool:
        self.send_stats()
        return self.enable
