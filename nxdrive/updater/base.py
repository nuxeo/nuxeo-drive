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
    UPDATE_STATUS_INCOMPATIBLE_SERVER,
    UPDATE_STATUS_UNAVAILABLE_SITE,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_UPDATING,
    UPDATE_STATUS_UP_TO_DATE,
    UPDATE_STATUS_WRONG_CHANNEL,
    Login,
)
from .utils import get_update_status
from ..constants import APP_NAME, CONNECTION_ERROR, NO_SPACE_ERRORS
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

    # Used when on a version that exists only in another channel
    wrongChannel = pyqtSignal()

    # Used to alert the user there is no more space to update the app
    noSpaceLeftOnDevice = pyqtSignal()

    versions: Dict[str, Any] = {}

    chunk_size = 8192

    def __init__(self, manager: "Manager") -> None:
        super().__init__(Options.update_check_delay)
        self.manager = manager

        self.enable = getattr(self, "_can_update", Options.is_frozen)
        self.status = UPDATE_STATUS_UP_TO_DATE
        self.version: str = ""
        self.progress = 0.0
        self.update_site = Options.update_site_url.rstrip("/")

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

        for engine in self.manager.engines.copy().values():
            if engine.remote:
                return engine.remote.client.server_version
        return None

    #
    # Public methods that can be overrided
    #

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
        try:
            self._install(version, self._download(version))
        except OSError as exc:
            self._set_status(UPDATE_STATUS_UPDATE_AVAILABLE)
            if exc.errno in NO_SPACE_ERRORS:
                log.warning("Update failed, disk space needed", exc_info=True)
                self.noSpaceLeftOnDevice.emit()
            else:
                raise
        except CONNECTION_ERROR:
            log.warning("Error during update request", exc_info=True)
        except Exception:
            self._set_status(UPDATE_STATUS_UPDATE_AVAILABLE)
            log.exception("Update failed")

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
            # Note: I do not think we should pass the `verify` kwarg here
            # because updates are critical and must be stored on a secured server.
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

                # Force write of file to disk
                tmp.flush()
                os.fsync(tmp.fileno())
        except CONNECTION_ERROR:
            raise
        except Exception as exc:
            raise UpdateError(f"Impossible to get {url!r}: {exc}")

        if not self._is_valid(version, path):
            raise UpdateError(f"Installer integrity check failed for {name!r}")

        return path

    def _fetch_versions(self) -> None:
        """ Fetch available versions. It sets `self.versions` on success. """

        url = f"{self.update_site}/versions.yml"
        try:
            # Note: I do not think we should pass the `verify` kwarg here
            # because updates are critical and must be stored on a secured server.
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
            if not isinstance(versions, dict):
                versions = {}
            self.versions = versions

    def _get_update_status(self) -> None:
        """ Retrieve available versions and find a possible candidate. """

        try:
            # Fetch all available versions
            self._fetch_versions()
        except UpdateError:
            status, version = UPDATE_STATUS_UNAVAILABLE_SITE, None
        else:
            login_type = Login.NONE
            for engine in list(self.manager.engines.values()):
                url = engine.server_url
                login_type |= self.manager.get_server_login_type(url, _raise=False)

            channel = self.manager.get_update_channel()
            log.info(
                f"Getting update status for version {self.manager.version}"
                f" (channel={channel}) on server {self.server_ver}"
            )
            status, version = get_update_status(
                self.manager.version,
                self.versions,
                channel,
                self.server_ver,
                login_type,
            )
        if status and version:
            self._set_status(status, version=version)
        elif status:
            self.status = status
            self.version = ""

    def force_downgrade(self) -> None:
        try:
            # Fetch all available versions
            self._fetch_versions()
        except UpdateError:
            self._set_status(UPDATE_STATUS_UNAVAILABLE_SITE)
        else:
            versions = {
                version: info
                for version, info in self.versions.items()
                if info.get("type", "").lower()
                in (self.manager.get_update_channel(), "release")
                and version_lt(version, "4")
            }
            if versions:
                version = max(versions.keys())
                self._set_status(UPDATE_STATUS_INCOMPATIBLE_SERVER, version)
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
            UPDATE_STATUS_INCOMPATIBLE_SERVER,
            UPDATE_STATUS_UPDATE_AVAILABLE,
            UPDATE_STATUS_WRONG_CHANNEL,
        ):
            log.info("You are up-to-date!")
            return

        if self.status == UPDATE_STATUS_WRONG_CHANNEL:
            self.wrongChannel.emit()
            return

        self.updateAvailable.emit()

        if self.status == UPDATE_STATUS_INCOMPATIBLE_SERVER:
            # In case of a downgrade, stop the engines
            # and try to install the older version.
            self.manager.restart_needed = True
            self.manager.suspend()
            self.serverIncompatible.emit()
            return

        if self.manager.get_auto_update():
            self.update(self.version)

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

    def get_version_channel(self, version: str) -> str:
        info = self.versions.get(version)
        if info:
            return info.get("type", "")
        else:
            log.debug(f"No version {version} in record.")
        return ""

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

        log.debug(
            f"Integrity check [{algo.upper()}] for {filename!r}: "
            f"good={checksum!r}, found={computed!r}"
        )
        return computed == checksum

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:

        if self.status != UPDATE_STATUS_UPDATING:
            self._get_update_status()
            self._handle_status()

        return self.status != UPDATE_STATUS_UNAVAILABLE_SITE
