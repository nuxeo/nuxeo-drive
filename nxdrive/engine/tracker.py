import os
import platform
import sys
from logging import getLogger
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, Callable, Dict

import requests

from ..constants import APP_NAME, MAC, WINDOWS
from ..options import Options
from ..qt.imports import pyqtSlot
from ..utils import ga_user_agent, get_current_os, if_frozen
from .workers import PollWorker

if not MAC:
    import locale

if TYPE_CHECKING:
    from .engine import Engine  # noqa
    from ..manager import Manager  # noqa

__all__ = ("Tracker",)

log = getLogger(__name__)


def analytics_enabled(meth: Callable, /) -> Callable:
    """Did the user allow to share metrics?"""

    def inner(*args: Any, **kwargs: Any) -> Any:
        if Options.is_frozen and Options.use_analytics:
            return meth(*args, **kwargs)

    return inner


class Tracker(PollWorker):
    def __init__(
        self,
        manager: "Manager",
        /,
        *,
        uid: str = "UA-81135-23",
        interval: int = 60 * 60,
    ) -> None:
        # Send stats every hour by default
        super().__init__(interval, "Tracker")

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
            "cd13": platform.machine() or "unknown",
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

        log.debug(
            f"Created the Google Analytics tracker with data {self._data} and custom dimensions {self._dimensions}"
        )

        self._hello_sent = False

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
            f"{APP_NAME.replace(' ', '-')}/{self._manager.version} ({ga_user_agent()})"
        )

    def send_event(
        self,
        /,
        *,
        category: str = "",
        action: str = "",
        label: str = "",
        value: int = -1,
        anon: bool = False,
    ) -> None:
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

        dimensions = {}

        if anon:
            _data = self._data.copy()
            _data["aip"] = "1"  # anonymize IP
        else:
            _data = self._data
            engines = list(self._manager.engines.values())
            if engines:
                engine = engines[0]
                dimensions["cd6"] = engine.hostname
                dimensions["cd7"] = engine.server_url
                dimensions["cd8"] = engine.remote.client.server_version

        data = {
            # Main data
            **_data,
            # Event data
            "t": "event",
            "ec": category,  # event category
            "ea": action,  # event action
            # Additional event data: dimensions
            **self._dimensions,
            **dimensions,
        }

        if label != "" and value != -1:
            data["el"] = label  # event label/name
            data["ev"] = str(value)  # event value
            log.debug(f"Sending {category}({action}) {label}: {value!r}")
        else:
            log.debug(f"Sending {category}({action})")

        try:
            self._session.post(self._tracking_url, data=data, timeout=5.0)
        except Exception:
            log.warning("Error sending Google Analytics")

    @analytics_enabled
    @pyqtSlot(object)
    def send_sync_event(self, metrics: Dict[str, Any], /) -> None:
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

    @analytics_enabled
    @pyqtSlot(str, int)
    def send_directedit_open(self, name: str, timing: int, /) -> None:
        _, extension = os.path.splitext(name)
        if not extension:
            extension = "unknown"

        self.send_event(
            category="DirectEdit", action="Open", label=extension.lower(), value=timing
        )

    @analytics_enabled
    @pyqtSlot(str, int)
    def send_directedit_edit(self, name: str, timing: int, /) -> None:
        _, extension = os.path.splitext(name)
        if not extension:
            extension = "unknown"

        self.send_event(
            category="DirectEdit", action="Edit", label=extension.lower(), value=timing
        )

    @analytics_enabled
    @pyqtSlot(bool, int)
    def send_direct_transfer(self, folderish: bool, size: int, /) -> None:
        nature = "folder" if folderish else "file"
        self.send_event(
            category="DirectTransfer", action="Sent", label=nature, value=size
        )

    @analytics_enabled
    @pyqtSlot()
    def send_stats(self) -> None:
        for engine in self._manager.engines.copy().values():
            for key, value in engine.get_metrics().items():
                if not isinstance(value, int):
                    log.debug(f"Skip non integer Statistics(Engine) {key}: {value!r}")
                    continue

                self.send_event(
                    category="Statistics", action="Engine", label=key, value=value
                )

    def send_hello(self) -> None:
        """Send metrics required for the good health of the project, see NXDRIVE-2254 for details."""
        # Nothing should be sent when testing the app
        if not Options.is_frozen:
            return

        # Already sent the hello, no more work is required
        if self._hello_sent:
            return

        # Send a simple event that will be completely anonymous.
        # Primordial metrics are included in dimensions and the user-agent.
        self.send_event(category="Hello", action="world", anon=True)

        self._hello_sent = True

    @if_frozen
    def send_metric(self, category: str, action: str, label: str, /) -> None:
        """Send metrics required for the good health of the project, see NXDRIVE-2439 for details."""
        self.send_event(category=category, action=action, label=label, value=1)

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        self.send_hello()
        self.send_stats()
        return True
