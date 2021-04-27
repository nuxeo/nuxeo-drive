import hashlib
import os
import uuid
from logging import getLogger
from tempfile import gettempdir
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

import requests
import yaml
from nuxeo.utils import version_lt

from ..constants import APP_NAME, CONNECTION_ERROR, NO_SPACE_ERRORS
from ..engine.workers import PollWorker
from ..feature import Feature
from ..metrics.utils import user_agent
from ..options import Options
from ..qt.imports import QApplication, pyqtSignal, pyqtSlot
from . import UpdateError, UpdateIntegrityError
from .constants import (
    UPDATE_STATUS_INCOMPATIBLE_SERVER,
    UPDATE_STATUS_UNAVAILABLE_SITE,
    UPDATE_STATUS_UP_TO_DATE,
    UPDATE_STATUS_UPDATE_AVAILABLE,
    UPDATE_STATUS_UPDATING,
    UPDATE_STATUS_WRONG_CHANNEL,
    AutoUpdateState,
    Login,
)
from .utils import auto_updates_state, get_update_status

if TYPE_CHECKING:
    from ..manager import Manager  # noqa

__all__ = ("BaseUpdater",)

log = getLogger(__name__)


class BaseUpdater(PollWorker):
    """Updater class for frozen application."""

    # Used to trigger the application exit on successful update
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

    def __init__(self, manager: "Manager", /) -> None:
        super().__init__(Options.update_check_delay, "Updater")
        self.manager = manager

        self.status = UPDATE_STATUS_UP_TO_DATE
        self.version: str = ""
        self.progress = 0.0
        self.update_site = Options.update_site_url.rstrip("/")

        self._update_in_progress = False

    @property
    def enable(self) -> bool:
        """That attribute is dynamic as it may change over the application runtime."""
        state = auto_updates_state()

        if state is AutoUpdateState.FORCED:
            # We need to update that attribute to prevent checking for updates every seconds
            if self._check_interval <= 0:
                self._check_interval = 3600

        return state is not AutoUpdateState.DISABLED

    #
    # Read-only properties
    #

    @property
    def can_update(self) -> bool:
        """Whenever the application can be automatycally updated right now."""

        # Special case to test the auto-updater without the need for an account
        if os.getenv("FORCE_USE_LATEST_VERSION", "0") == "1":
            return True

        # Check if the server's config has been fetched
        if self.manager.server_config_updater.first_run:
            log.warning("No server configuration retrieved => no update allowed yet.")
            return False

        state = auto_updates_state()

        # Force the auto-update
        if state is AutoUpdateState.FORCED:
            return True

        # Cannot update has it is not allowed
        if state is AutoUpdateState.DISABLED:
            return False

        # The auto-update can be done but let's check the user preference, finally
        return bool(self.manager.get_auto_update())

    @property
    def server_ver(self) -> Optional[str]:
        """
        Get the current Nuxeo version.
        It will take the server version of the first found engine.
        `None` if no bound engine.
        """

        for engine in self.manager.engines.copy().values():
            if engine.remote:
                return engine.remote.client.server_version  # type: ignore
        return None

    #
    # Public methods that can be overridden
    #

    def install(self, filename: str, /) -> None:
        """
        Install the new version.
        Uninstallation of the old one or any actions needed to install
        the new one has to be handled by this method.
        """
        raise NotImplementedError()

    def refresh_status(self) -> None:
        """
        Check for an update.
        Used when changing the channel option or when binding a new engine.
        """
        if self.enable:
            self._poll()

    @pyqtSlot(str)
    def update(self, version: str, /) -> None:
        log.info(f"Starting application update process to version {version!r}")
        self._set_status(UPDATE_STATUS_UPDATING, version=version, progress=10)
        try:
            self._install(version, self._download(version))
        except OSError as exc:
            self._set_status(UPDATE_STATUS_UPDATE_AVAILABLE, version=version)
            if exc.errno in NO_SPACE_ERRORS:
                log.warning("Update failed, disk space needed", exc_info=True)
                self.noSpaceLeftOnDevice.emit()
            else:
                raise
        except CONNECTION_ERROR:
            log.warning("Error during update request", exc_info=True)
        except UpdateIntegrityError as exc:
            log.warning(exc)
        except Exception:
            self._set_status(UPDATE_STATUS_UPDATE_AVAILABLE, version=version)
            log.exception("Update failed")

    #
    # Private methods, should not try to override
    #

    def _download(self, version: str, /) -> str:
        """Download a given version to a temporary file."""

        name = self.release_file.format(version=version)
        url = "/".join([self.update_site, self.versions[version]["type"], name])
        path = os.path.join(gettempdir(), uuid.uuid4().hex + "_" + name)
        headers = {"User-Agent": user_agent()}

        log.info(f"Fetching {APP_NAME} {version} from {url!r} into {path!r}")
        try:
            # Note: I do not think we should pass the `verify` kwarg here
            # because updates are critical and must be stored on a secured server.
            req = requests.get(url, headers=headers, stream=True)
            req.raise_for_status()
            size = int(req.headers["content-length"])

            with open(path, "wb") as tmp:
                incr = self.chunk_size * 100 / size
                for i, chunk in enumerate(req.iter_content(self.chunk_size)):
                    tmp.write(chunk)
                    if i % 100 == 0:
                        self._set_progress(self.progress + incr * 50)

                # Force write of file to disk
                tmp.flush()
                os.fsync(tmp.fileno())
        except CONNECTION_ERROR:
            raise
        except Exception as exc:
            raise UpdateError(f"Impossible to get {url!r}: {exc}")

        self._check_validity(version, path)
        return path

    def _fetch_versions(self) -> None:
        """Fetch available versions. It sets `self.versions` on success."""

        url = f"{self.update_site}/versions.yml"
        headers = {"User-Agent": user_agent()}
        try:
            # Note: I do not think we should pass the `verify` kwarg here
            # because updates are critical and must be stored on a secured server.
            with requests.get(url, headers=headers) as resp:
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
        """Retrieve available versions and find a possible candidate."""

        try:
            # Fetch all available versions
            self._fetch_versions()
        except UpdateError:
            status, version = UPDATE_STATUS_UNAVAILABLE_SITE, None
        else:
            # Special case to test the auto-updater without the need for an account
            if os.getenv("FORCE_USE_LATEST_VERSION", "0") == "1":
                version = max(self.versions)
                if version_lt(self.manager.version, version):
                    log.info(
                        f"FORCE_USE_LATEST_VERSION is set, upgrading to {version!r}"
                    )
                    self._set_status(UPDATE_STATUS_UPDATE_AVAILABLE, version=version)
                else:
                    log.info(
                        f"FORCE_USE_LATEST_VERSION is set, but {version!r} not newer than the current version"
                    )
                return

            login_type = Login.NONE
            for engine in self.manager.engines.copy().values():
                url = engine.server_url
                login_type |= self.manager.get_server_login_type(url, _raise=False)

            channel = self.manager.get_update_channel()
            log.info(
                f"Getting update status for version {self.manager.version!r}"
                f" (channel={channel}, desired client_version={Options.client_version!r})"
                f" on server {self.server_ver}"
            )
            status, version = get_update_status(
                self.manager.version,
                self.versions,
                channel,
                self.server_ver,
                login_type,
            )
            log.debug(f"Guessed status {status!r} and version {version!r}.")

        # Check the digest is available for that version on that OS
        if version:
            info = self.versions.get(version, {})
            checksums = info.get("checksum", {})
            checksum = checksums.get(self.ext, "").lower()
            if not checksum:
                log.warning(
                    f"There is no downloadable file for the version {version!r} on that OS."
                )
                return

        if status and version and self.enable and self.can_update:
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
                self._set_status(UPDATE_STATUS_INCOMPATIBLE_SERVER, version=version)
        self.serverIncompatible.emit()

    def _handle_status(self) -> None:
        """Handle update check status."""

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

        if not self.version:
            # This is the case when the updater has done a first check before
            # the server config was retrieved. As it is forbidden, we just stop here.
            return

        self.updateAvailable.emit()

        if self.status == UPDATE_STATUS_INCOMPATIBLE_SERVER:
            # In case of a downgrade, stop the engines
            # and try to install the older version.
            self.manager.restartNeeded.emit()
            self.serverIncompatible.emit()
            return

        if self.can_update:
            self.update(self.version)

    def _set_progress(self, progress: Union[int, float], /) -> None:
        self.progress = progress
        self.updateProgress.emit(int(self.progress))
        QApplication.processEvents()

    def _set_status(
        self, status: str, /, *, version: str = "", progress: Union[int, float] = 0
    ) -> None:
        self.status = status
        self.version = version
        self._set_progress(progress)

    def get_version_channel(self, version: str, /) -> str:
        info = self.versions.get(version)
        if info:
            return info.get("type", None) or ""

        log.debug(f"No version {version} in record.")
        return ""

    def _install(self, version: str, filename: str, /) -> None:
        """
        OS-specific method to install the new version.
        It must take care of uninstalling the current one.
        """
        log.info(f"Installing {APP_NAME} {version}")
        self.install(filename)

    def _check_validity(self, version: str, filename: str, /) -> None:
        """Check the downloaded file integrity. Use SHA256 by default."""

        info = self.versions.get(version, {})
        checksums = info.get("checksum", {})
        checksum = checksums.get(self.ext, "").lower()
        algo = checksums.get("algo", "sha256").lower()
        func = getattr(hashlib, algo, "sha256")()

        with open(filename, "rb") as installer:
            for chunk in iter(lambda: installer.read(16384), b""):
                func.update(chunk)
        computed = func.hexdigest()

        if computed != checksum:
            raise UpdateIntegrityError(filename, algo, checksum, computed)

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        if not Feature.auto_update:
            log.debug("The auto-update feature is disabled.")
            return False

        if self._update_in_progress:
            log.debug("The update is already ongoing ...")
            return False

        self._update_in_progress = True
        try:
            if self.status != UPDATE_STATUS_UPDATING:
                self._get_update_status()
                self._handle_status()

            return self.status != UPDATE_STATUS_UNAVAILABLE_SITE
        finally:
            self._update_in_progress = False
