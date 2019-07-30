# coding: utf-8
import os
import sys
from logging import getLogger
from typing import Any, Dict, TYPE_CHECKING

from PyQt5.QtCore import QTimer, pyqtSlot
from UniversalAnalytics import Tracker as UATracker

from .workers import Worker
from ..constants import APP_NAME, MAC, WINDOWS
from ..utils import get_arch, get_current_os

if not MAC:
    import locale

if TYPE_CHECKING:
    from .engine import Engine  # noqa
    from ..manager import Manager  # noqa

__all__ = ("Tracker",)

log = getLogger(__name__)


class Tracker(Worker):

    fmt_event = "Send {category}({action}) {label}: {value!r}"

    def __init__(self, manager: "Manager", uid: str = "UA-81135-23") -> None:
        super().__init__()
        self._manager = manager
        self.thread.started.connect(self.run)
        self.uid = uid
        self.app_name = APP_NAME.replace(" ", "")
        self.arch = get_arch()
        self.current_os = " ".join(get_current_os())
        self._tracker = UATracker.create(
            uid, client_id=self._manager.device_id, user_agent=self.user_agent
        )
        self._tracker.set("appName", self.app_name)
        self._tracker.set("appVersion", self._manager.version)
        self._tracker.set("encoding", sys.getfilesystemencoding())
        self._tracker.set("language", self.current_locale)
        self._manager.started.connect(self._send_stats)

        # Send stat every hour
        self._stat_timer = QTimer()
        self._stat_timer.timeout.connect(self._send_stats)

        # Connect engines
        for engine in self._manager.engines.values():
            self.connect_engine(engine)
        self._manager.newEngine.connect(self.connect_engine)
        if self._manager.direct_edit is not None:
            self._manager.direct_edit.openDocument.connect(self._send_directedit_open)
            self._manager.direct_edit.editDocument.connect(self._send_directedit_edit)

    @pyqtSlot(object)
    def connect_engine(self, engine: "Engine") -> None:
        engine.newSyncEnded.connect(self._send_sync_event)

    @property
    def current_locale(self) -> str:
        """ Detect the OS default language. """

        # Guess the encoding
        if MAC:
            # Always UTF-8 on macOS
            encoding = "UTF-8"
        else:
            encoding = locale.getdefaultlocale()[1] or ""

        # Guess the current locale name
        if WINDOWS:
            import ctypes

            l10n_code = (
                ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore
            )
            l10n = locale.windows_locale[l10n_code]
        elif MAC:
            from Foundation import NSLocale

            l10n_code = NSLocale.currentLocale()
            l10n = NSLocale.localeIdentifier(l10n_code)
        else:
            l10n = locale.getdefaultlocale()[0] or ""

        return ".".join([l10n, encoding])

    @property
    def user_agent(self) -> str:
        """ Format a custom user agent. """

        return f"{self.app_name}/{self._manager.version} ({self.current_os})"

    def send_event(self, **kwargs: Any) -> None:
        """
        Send a event to Google Analytics. Attach some attributes (dimensions) to ease filtering.

        [WARNING] Do not reuse old dimensions:
        https://support.google.com/analytics/answer/2709828?hl=en#Limits

        Those dimensions are transposed from Engine.get_metrics() when calling ._send_stats():
            dimension1: $sync_files
            dimension2: $sync_folders
            dimension3: $error_files
            dimension4: $conflicted_files
            dimension5: $file_size

        And those ones were deleted at some point:
            dimension9: NXDRIVE-1238
        """
        dimensions = {"dimension10": self.arch, "dimension11": self.current_os}

        engines = list(self._manager.engines.values())
        if engines:
            engine = engines[0]
            dimensions["dimension6"] = engine.hostname
            dimensions["dimension7"] = engine.server_url
            dimensions["dimension8"] = engine.remote.client.server_version

        self._tracker.set(dimensions)
        log.debug(self.fmt_event.format(**kwargs))
        try:
            self._tracker.send("event", **kwargs)
        except:
            log.exception("Error sending analytics")

    @pyqtSlot(str)
    def _send_directedit_open(self, name: str) -> None:
        _, extension = os.path.splitext(name)
        if not extension:
            extension = "unknown"

        self.send_event(
            category="DirectEdit",
            action="Open",
            label=extension.lower(),
            value=self._manager.direct_edit.get_metrics()["last_action_timing"],
        )

    @pyqtSlot(str)
    def _send_directedit_edit(self, name: str) -> None:
        _, extension = os.path.splitext(name)
        if not extension:
            extension = "unknown"

        self.send_event(
            category="DirectEdit",
            action="Edit",
            label=extension.lower(),
            value=self._manager.direct_edit.get_metrics()["last_action_timing"],
        )

    @pyqtSlot(object)
    def _send_sync_event(self, metrics: Dict[str, Any]) -> None:
        timing = metrics.get("end_time", 0) - metrics["start_time"]
        speed = metrics.get("speed", None)  # KiB/s

        if timing > 0:
            self.send_event(
                category="TransferOperation",
                action=metrics["handler"],
                label="OverallTime",
                value=timing,
            )

        if speed:
            self.send_event(
                category="TransferOperation",
                action=metrics["handler"],
                label="Speed",
                value=speed,
            )

    @pyqtSlot()
    def _send_stats(self) -> None:
        for engine in self._manager.engines.values():
            for key, value in engine.get_metrics().items():
                if not isinstance(value, int):
                    log.debug(f"Skip non integer Statistics(Engine) {key}: {value!r}")
                    continue

                self.send_event(
                    category="Statistics", action="Engine", label=key, value=value
                )

        self._stat_timer.start(60 * 60 * 1000)
