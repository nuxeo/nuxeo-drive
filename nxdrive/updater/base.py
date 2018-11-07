# coding: utf-8
import hashlib
import os
import uuid
from logging import getLogger
from tempfile import gettempdir
from typing import Any, Dict, Optional, Union, TYPE_CHECKING

import requests
import yaml
from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication

from . import UpdateError
from .constants import (
    UPDATE_STATUS_DOWNGRADE_NEEDED,
    UPDATE_STATUS_UNAVAILABLE_SITE,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_UPDATING,
    UPDATE_STATUS_UP_TO_DATE,
)
from .utils import get_update_status
from ..constants import APP_NAME
from ..engine.workers import PollWorker
from ..options import Options
from ..utils import version_lt

if TYPE_CHECKING:
    from ..manager import Manager  # noqa

__all__ = ("BaseUpdater",)

log = getLogger(__name__)


class BaseUpdater(PollWorker):
    """ Updater class for frozen application. """

    # Used to trigger the application exit on sucessful update
    appUpdated = pyqtSignal()

    # Used to display a notification when a new version is available
    updateAvailable = pyqtSignal()

    # Used to refresh the update progress bar in the systray
    updateProgress = pyqtSignal(int)

    # Used when the server doesn't have the new browser login
    serverIncompatible = pyqtSignal()

    versions: Dict[str, Any] = {}
    nature = "release"

    chunk_size = 8192

    __update_site = None

    def __init__(self, manager: "Manager") -> None:
        super().__init__(Options.update_check_delay)
        self.manager = manager

        self.enable = getattr(self, "_can_update", Options.is_frozen)
        self.status = UPDATE_STATUS_UP_TO_DATE
        self.version: str = ""
        self.progress = .0

        if not self.enable:
            log.info(f"Auto-update disabled (frozen={Options.is_frozen!r})")

    #
    # Read-only properties
    #

    @property
    def server_ver(self) -> Optional[str]:
        """
        Get the current Nuxeo version.
        It will take the server version of the first found engine.
        `None` if no bound engine.
        """

        for engine in self.manager.get_engines().values():
            if engine.remote:
                return engine.remote.client.server_version
        return None

    @property
    def update_site(self) -> str:
        """ The update site URL without trailing slash. """

        if not self.__update_site:

            if self.manager.get_beta_channel():
                log.debug("Update beta channel activated")
                url, self.nature = Options.beta_update_site_url, "beta"
            else:
                url, self.nature = Options.update_site_url, "release"
            self.__update_site = url.rstrip("/")

        return self.__update_site

    #
    # Public methods that can be overrided
    #

    def force_status(self, status: str, version: str) -> None:
        """
        Trigger the auto-update notification with given status and version.
        Used for debugging purposes only.
        """

        self._set_status(status, version=version)

        if status == UPDATE_STATUS_UPDATING:
            # Put a percentage
            self._set_progress(40)

        if status == UPDATE_STATUS_UPDATE_AVAILABLE:
            self.updateAvailable.emit()

    def install(self, filename: str) -> None:
        """
        Install the new version.
        Uninstallation of the old one or any actions needed to install
        the new one has to be handled by this method.
        """
        raise NotImplementedError()

    def refresh_status(self) -> None:
        """
        Check for an update.
        Used when changing the beta channel option or when binding a new engine.
        """
        self._poll()

    @pyqtSlot(str)
    def update(self, version: str) -> None:
        if not self.enable:
            return

        log.info(f"Starting application update process to version {version}")
        self._set_status(UPDATE_STATUS_UPDATING, version=version, progress=10)
        self._install(version, self._download(version))

    #
    # Private methods, should not try to override
    #

    def _download(self, version: str) -> str:
        """ Download a given version to a temporary file. """

        name = self.release_file.format(version=version)
        url = "/".join([self.update_site, self.versions[version]["type"], name])
        path = os.path.join(gettempdir(), uuid.uuid4().hex + "_" + name)

        log.info(
            f"Fetching version {version!r} from update site {self.update_site!r} "
            f"into {path!r}"
        )
        try:
            req = requests.get(url, stream=True)
            size = int(req.headers["content-length"])
            incr = self.chunk_size * 100 / size
            i = 0

            with open(path, "wb") as tmp:
                for chunk in req.iter_content(self.chunk_size):
                    tmp.write(chunk)
                    if i % 100 == 0:
                        self._set_progress(self.progress + incr * 50)
                    i += 1
        except Exception as exc:
            raise UpdateError(f"Impossible to get {url!r}: {exc}")

        if not self._is_valid(version, path):
            raise UpdateError(f"Installer integrity check failed for {name!r}")

        return path

    def _fetch_versions(self) -> None:
        """ Fetch available versions. It sets `self.versions` on success. """

        url = f"{self.update_site}/versions.yml"
        try:
            with requests.get(url) as resp:
                resp.raise_for_status()
                content = resp.text
        except Exception as exc:
            raise UpdateError(f"Impossible to get {url!r}: {exc}")

        try:
            versions = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise UpdateError(f"Parsing error: {exc}")
        else:
            self.versions = versions

    def _get_update_status(self) -> None:
        """ Retrieve available versions and find a possible candidate. """

        try:
            # Fetch all available versions
            self._fetch_versions()
        except UpdateError:
            status, version = UPDATE_STATUS_UNAVAILABLE_SITE, None
        else:
            has_browser_login = all(
                [
                    self.manager._server_has_browser_login(engine.server_url)
                    for engine in self.manager._engines.values()
                ]
            )
            log.debug(
                f"Getting update status for version {self.manager.version} ({self.nature}) on server {self.server_ver}"
            )
            status, version = get_update_status(
                self.manager.version,
                self.versions,
                self.nature,
                self.server_ver,
                has_browser_login,
            )
        if status and version:
            self._set_status(status, version=version)

    def _force_downgrade(self) -> None:
        try:
            # Fetch all available versions
            self._fetch_versions()
        except UpdateError:
            self._set_status(UPDATE_STATUS_UNAVAILABLE_SITE)
        else:
            versions = {
                version: info
                for version, info in self.versions.items()
                if info.get("type", "").lower() in (self.nature, "release")
                and version_lt(version, "4")
            }
            if versions:
                version = max(versions.keys())
                self._set_status(UPDATE_STATUS_DOWNGRADE_NEEDED, version)
            self.serverIncompatible.emit()

    def _handle_status(self) -> None:
        """ Handle update check status. """

        if self.status == UPDATE_STATUS_UNAVAILABLE_SITE:
            log.warning(
                "Update site is unavailable, as a consequence"
                " update features won't be available."
            )
            return

        if self.status not in (
            UPDATE_STATUS_DOWNGRADE_NEEDED,
            UPDATE_STATUS_UPDATE_AVAILABLE,
        ):
            log.debug("You are up-to-date!")
            return

        self.updateAvailable.emit()

        if self.status == UPDATE_STATUS_DOWNGRADE_NEEDED:
            # In case of a downgrade, stop the engines
            # and try to install the older version.
            self.manager.stop()
            self.serverIncompatible.emit()
            return

        if self.manager.get_auto_update():
            try:
                self.update(self.version)
            except UpdateError:
                log.exception("Auto-update error")

    def _set_progress(self, progress: Union[int, float]) -> None:
        self.progress = progress
        self.updateProgress.emit(self.progress)
        QApplication.processEvents()

    def _set_status(
        self, status: str, version: str = "", progress: Union[int, float] = 0
    ) -> None:
        self.status = status
        self.version = version
        self._set_progress(progress)

    def _install(self, version: str, filename: str) -> None:
        """
        OS-specific method to install the new version.
        It must take care of uninstalling the current one.
        """
        log.info(f"Installing {APP_NAME} {version}")
        self.install(filename)

    def _is_valid(self, version: str, filename: str) -> bool:
        """ Check the downloaded file integrity. Use SHA256 by default. """

        info = self.versions.get(version, {})
        checksums = info.get("checksum", {})
        algo = checksums.get("algo", "sha256").lower()
        checksum = checksums.get(self.ext, "").lower()
        if not checksum:
            log.error(f"Invalid version info {info!r} (version={version})")
            return False

        func = getattr(hashlib, algo, "sha256")()
        with open(filename, "rb") as installer:
            for chunk in iter(lambda: installer.read(16384), b""):
                func.update(chunk)
        computed = func.hexdigest()

        log.trace(
            f"Integrity check [{algo.upper()}] for {filename!r}: "
            f"good={checksum!r}, found={computed!r}"
        )
        return computed == checksum

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:

        if self.status != UPDATE_STATUS_UPDATING:
            try:
                self._get_update_status()
                self._handle_status()
            finally:
                # Reset the update site URL to force
                # recomputation the next time
                self.__update_site = None

        return self.status != UPDATE_STATUS_UNAVAILABLE_SITE
