# coding: utf-8
import ctypes
import locale
import os
import platform
import sys
from logging import getLogger
from typing import Any, Dict, TYPE_CHECKING

from PyQt5.QtCore import QTimer, pyqtSlot
from UniversalAnalytics import Tracker as UATracker

from .workers import Worker
from ..constants import APP_NAME, MAC, WINDOWS
from ..objects import Blob

if MAC:
    from Foundation import NSLocale

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
        self._thread.started.connect(self.run)
        self.uid = uid
        self.app_name = APP_NAME.replace(" ", "")
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
        for _, engine in self._manager.get_engines().items():
            self.connect_engine(engine)
        self._manager.newEngine.connect(self.connect_engine)
        if self._manager.direct_edit is not None:
            self._manager.direct_edit.openDocument.connect(self._send_directedit_open)
            self._manager.direct_edit.editDocument.connect(self._send_directedit_edit)

    @pyqtSlot(object)
    def connect_engine(self, engine: "Engine") -> None:
        engine.newSync.connect(self._send_sync_event)

    @property
    def current_locale(self) -> str:
        """ Detect the OS default language. """

        encoding = locale.getdefaultlocale()[1] or ""
        if WINDOWS:
            l10n_code = (
                ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore
            )
            l10n = locale.windows_locale[l10n_code]
        elif MAC:
            l10n_code = NSLocale.currentLocale()
            l10n = NSLocale.localeIdentifier(l10n_code)
            encoding = "UTF-8"
        else:
            l10n = locale.getdefaultlocale()[0] or ""

        return ".".join([l10n, encoding])

    @property
    def current_os(self) -> str:
        """ Detect the OS. """

        system = platform.system()
        if system == "Darwin":
            name, version = "Macintosh Intel", platform.mac_ver()[0]
        elif system == "Linux":
            import distro

            name, version = distro.linux_distribution()[:2]
        elif system == "Windows":
            name, version = "Microsoft Windows", platform.release()
        else:
            name, version = system, platform.release()

        return f"{name} {version.strip()}"

    @property
    def user_agent(self) -> str:
        """ Format a custom user agent. """

        return f"{self.app_name}/{self._manager.version} ({self.current_os})"

    def send_event(self, **kwargs: Any) -> None:
        engine = list(self._manager.get_engines().values())[0]

        if engine:
            self._tracker.set(
                {
                    "dimension6": engine.hostname,
                    "dimension7": engine.server_url,
                    "dimension8": engine.remote.client.server_version,
                }
            )

        log.trace(self.fmt_event.format(**kwargs))
        try:
            self._tracker.send("event", **kwargs)
        except:
            log.exception("Error sending analytics")

    @pyqtSlot(object)
    def _send_directedit_open(self, blob: Blob) -> None:
        _, extension = os.path.splitext(blob.name)
        if extension is None:
            extension = "unknown"

        self.send_event(
            category="DirectEdit",
            action="Open",
            label=extension.lower(),
            value=self._manager.direct_edit.get_metrics()["last_action_timing"],
        )

    @pyqtSlot(object)
    def _send_directedit_edit(self, blob: Blob) -> None:
        _, extension = os.path.splitext(blob.name)
        if extension is None:
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
        speed = metrics.get("speed", None)

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
        for _, engine in self._manager.get_engines().items():
            for key, value in engine.get_metrics().items():
                if not isinstance(value, int):
                    log.trace(f"Skip non integer Statistics(Engine) {key}: {value!r}")
                    continue

                self.send_event(
                    category="Statistics", action="Engine", label=key, value=value
                )

        self._stat_timer.start(60 * 60 * 1000)
