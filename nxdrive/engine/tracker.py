# coding: utf-8
import os
import sys
from logging import getLogger
from time import monotonic_ns
from typing import Any, Dict, TYPE_CHECKING

from PyQt5.QtCore import pyqtSlot
import requests

from .workers import PollWorker
from ..constants import APP_NAME, MAC, WINDOWS
from ..options import Options
from ..utils import ga_user_agent, get_current_os

if not MAC:
    import locale

if TYPE_CHECKING:
    from .engine import Engine  # noqa
    from ..manager import Manager  # noqa

__all__ = ("Tracker",)

log = getLogger(__name__)


class Tracker(PollWorker):
    def __init__(
        self, manager: "Manager", uid: str = "UA-81135-23", interval: int = 60 * 60
    ) -> None:
        # Send stats every hour by default
        super().__init__(check_interval=interval)

        self._manager = manager
        self.uid = uid

        self._current_os = " ".join(get_current_os()).strip()
        if WINDOWS:
            self._current_os = f"Microsoft {self._current_os}"

        self._session = requests.sessions.Session()
        self._tracking_url = "https://ssl.google-analytics.com/collect"
        self.__current_locale = ""

        # Main dimensions, see .send_event() docstring for details.
        self._dimensions = {
            "cd10": self._manager.arch,
            "cd11": self._current_os,
            "cd12": Options.channel,
        }

        # https://developers.google.com/analytics/devguides/collection/protocol/v1/parameters
        # Main data to send every HTTP call
        self._data = {
            "v": "1",  # protocol version
            # "aip": "1",  # anonymize IP
            "tid": self.uid,  # tracking ID
            "cid": self._manager.device_id,  # client ID
            "ua": self.user_agent,  # user agent
            "de": sys.getfilesystemencoding(),  # encoding
            "ul": self.current_locale,  # language
            "an": APP_NAME,  # application name
            "av": self._manager.version,  # application version
        }

        self._session.headers.update({"user-agent": self.user_agent})

        log.debug(f"Created the Google Analytics tracker with data {self._data}")

    @property
    def current_locale(self) -> str:
        """ Detect the OS default language. """

        if self.__current_locale:
            return self.__current_locale

        # Guess the encoding
        if MAC:
            # Always UTF-8 on macOS
            encoding = "UTF-8"
        else:
            encoding = locale.getdefaultlocale()[1] or ""

        # Guess the current locale name
        if WINDOWS:
            import ctypes

            l10n_code = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            l10n = locale.windows_locale[l10n_code]
        elif MAC:
            from CoreServices import NSLocale

            l10n_code = NSLocale.currentLocale()
            l10n = NSLocale.localeIdentifier(l10n_code)
        else:
            l10n = locale.getdefaultlocale()[0] or ""

        self.__current_locale = ".".join([l10n, encoding])
        return self.__current_locale

    @property
    def user_agent(self) -> str:
        """ Format a custom user agent. """

        return (
            f"{APP_NAME.replace(' ', '')}/{self._manager.version} ({ga_user_agent()})"
        )

    def send_event(self, category: str, action: str, label: str, value: int) -> None:
        """
        Send a event to Google Analytics. Attach some attributes (dimensions) to ease filtering.

        [WARNING] Do not reuse old dimensions:
        https://support.google.com/analytics/answer/2709828?hl=en#Limits

        Those dimensions are transposed from Engine.get_metrics() when calling .send_stats():
            dimension1: $sync_files
            dimension2: $sync_folders
            dimension3: $error_files
            dimension4: $conflicted_files
            dimension5: $file_size

        And those ones were deleted at some point:
            dimension9: NXDRIVE-1238
        """

        engines = list(self._manager.engines.values())
        dimensions = {}
        if engines:
            engine = engines[0]
            dimensions["cd6"] = engine.hostname
            dimensions["cd7"] = engine.server_url
            dimensions["cd8"] = engine.remote.client.server_version

        data = {
            # Main data
            **self._data,
            # Event data
            "t": "event",
            "ec": category,  # event catagory
            "ea": action,  # event action
            "el": label,  # event label/name
            "ev": str(value),  # event value
            # Additionnal event data: dimensions
            **self._dimensions,
            **dimensions,
        }

        log.debug(f"Send {category}({action}) {label}: {value!r}")
        try:
            self._session.post(self._tracking_url, data=data, timeout=5.0)
        except Exception:
            log.warning("Error sending Google Analytics")

    @pyqtSlot(object)
    def send_sync_event(self, metrics: Dict[str, Any]) -> None:
        """Sent each time the Processor handles an event.
        This is mostly to have real time stats on GA.
        """
        elapsed = monotonic_ns() - metrics["start_ns"]
        if elapsed > 0.0:
            self.send_event(
                category="TransferOperation",
                action=metrics["handler"],
                label="OverallTime",
                value=elapsed,
            )

    @pyqtSlot(str, int)
    def send_directedit_open(self, name: str, timing: int) -> None:
        _, extension = os.path.splitext(name)
        if not extension:
            extension = "unknown"

        self.send_event(
            category="DirectEdit", action="Open", label=extension.lower(), value=timing
        )

    @pyqtSlot(str, int)
    def send_directedit_edit(self, name: str, timing: int) -> None:
        _, extension = os.path.splitext(name)
        if not extension:
            extension = "unknown"

        self.send_event(
            category="DirectEdit", action="Edit", label=extension.lower(), value=timing
        )

    @pyqtSlot(bool, int)
    def send_direct_transfer(self, folderish: bool, size: int) -> None:
        nature = "folder" if folderish else "file"
        self.send_event(
            category="DirectTransfer", action="Sent", label=nature, value=size
        )

    @pyqtSlot()
    def send_stats(self) -> None:
        for engine in self._manager.engines.values():
            for key, value in engine.get_metrics().items():
                if not isinstance(value, int):
                    log.debug(f"Skip non integer Statistics(Engine) {key}: {value!r}")
                    continue

                self.send_event(
                    category="Statistics", action="Engine", label=key, value=value
                )

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        self.send_stats()
        return True
