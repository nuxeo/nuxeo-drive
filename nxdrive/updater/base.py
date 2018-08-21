# coding: utf-8
import hashlib
import os
import uuid
from logging import getLogger
from tempfile import gettempdir
from typing import Optional

import requests
import yaml
from PyQt5.QtCore import pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication

from . import UpdateError, get_latest_compatible_version
from .constants import (
    UPDATE_STATUS_DOWNGRADE_NEEDED,
    UPDATE_STATUS_UNAVAILABLE_SITE,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_UPDATING,
    UPDATE_STATUS_UP_TO_DATE,
)
from ..engine.workers import PollWorker
from ..options import Options
from ..utils import version_le

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

    versions = {}
    nature = "release"

    chunk_size = 8192

    __update_site = None

    def __init__(self, manager: "Manager") -> None:
        super().__init__(Options.update_check_delay)
        self.manager = manager

        self.enable = getattr(self, "_can_update", Options.is_frozen)
        self.status = UPDATE_STATUS_UP_TO_DATE
        self.version = None
        self.progress = 0

        if not self.enable:
            log.info("Auto-update disabled (frozen=%r)", Options.is_frozen)

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

        self._set_status(status, version)

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

        log.info("Starting application update process to version %s", version)
        self._set_status(UPDATE_STATUS_UPDATING, version, 10)
        self._install(version, self._download(version))

    #
    # Private methods, should not try to override
    #

    def _download(self, version: str) -> str:
        """ Download a given version to a temporary file. """

        name = self.release_file.format(version=version)
        url = "/".join([self.update_site, self.nature, name])
        path = os.path.join(gettempdir(), uuid.uuid4().hex + "_" + name)

        log.info(
            "Fetching version %r from update site %r into %r",
            version,
            self.update_site,
            path,
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
            raise UpdateError("Impossible to get %r: %s" % (url, exc))

        if not self._is_valid(version, path):
            raise UpdateError("Installer integrity check failed for %r" % name)

        return path

    def _fetch_versions(self) -> None:
        """ Fetch available versions. It sets `self.versions` on success. """

        url = self.update_site + "/versions.yml"
        try:
            with requests.get(url) as resp:
                resp.raise_for_status()
                content = resp.text
        except Exception as exc:
            raise UpdateError("Impossible to get %r: %s" % (url, exc))

        try:
            versions = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise UpdateError("Parsing error: %s" % exc)
        else:
            self.versions = versions

    def _get_update_status(self) -> None:
        """ Retrieve available versions and find a possible candidate. """

        try:
            # Fetch all available versions
            self._fetch_versions()
        except UpdateError:
            self._set_status(UPDATE_STATUS_UNAVAILABLE_SITE)
        else:
            # Find the latest available version
            latest, info = get_latest_compatible_version(
                self.versions, self.nature, self.server_ver
            )

            current = self.manager.version
            if not latest or current == latest:
                self._set_status(UPDATE_STATUS_UP_TO_DATE)
            elif not version_le(latest, current):
                self._set_status(UPDATE_STATUS_UPDATE_AVAILABLE, latest)
            else:
                self._set_status(UPDATE_STATUS_DOWNGRADE_NEEDED, latest)

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
            self.manager.stop()
            return

        if self.manager.get_auto_update() or not self.manager.get_engines():
            # Automatically update if:
            #  - the auto-update option is checked
            #  - there is no bound engine
            try:
                self.update(self.version)
            except UpdateError:
                log.exception("Auto-update error")

    def _set_progress(self, progress: int) -> None:
        self.progress = progress
        self.updateProgress.emit(self.progress)
        QApplication.processEvents()

    def _set_status(self, status: str, version: str = None, progress: int = 0) -> None:
        self.status = status
        self.version = version
        self._set_progress(progress)

    def _install(self, version: str, filename: str) -> None:
        """
        OS-specific method to install the new version.
        It must take care of uninstalling the current one.
        """
        log.info("Installing %s %s", self.manager.app_name, version)
        self.install(filename)

    def _is_valid(self, version: str, filename: str) -> bool:
        """ Check the downloaded file integrity. Use SHA256 by default. """

        info = self.versions.get(version, {})
        checksums = info.get("checksum", {})
        algo = checksums.get("algo", "sha256").lower()
        checksum = checksums.get(self.ext, "").lower()
        if not checksum:
            log.error("Invalid version info %r (version=%r)", info, version)
            return False

        func = getattr(hashlib, algo, "sha256")()
        with open(filename, "rb") as installer:
            for chunk in iter(lambda: installer.read(16384), b""):
                func.update(chunk)
        computed = func.hexdigest()

        log.trace(
            "Integrity check [%s] for %r: good=%r, found=%r",
            algo.upper(),
            filename,
            checksum,
            computed,
        )
        return computed == checksum

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:

        if self.status != UPDATE_STATUS_UPDATING:
            log.debug(
                "Polling %r for update, the current version is %r",
                self.update_site,
                self.manager.version,
            )
            try:
                self._get_update_status()
                self._handle_status()
            finally:
                # Reset the update site URL to force
                # recomputation the next time
                self.__update_site = None

        return self.status != UPDATE_STATUS_UNAVAILABLE_SITE
