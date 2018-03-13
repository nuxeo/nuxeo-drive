# coding: utf-8
import hashlib
import os
import shutil
import uuid
from logging import getLogger
from tempfile import gettempdir

import requests
import yaml
from PyQt4.QtCore import pyqtSignal, pyqtSlot

from . import UpdateError, get_latest_compatible_version
from .constants import (UPDATE_STATUS_DOWNGRADE_NEEDED,
                        UPDATE_STATUS_UNAVAILABLE_SITE,
                        UPDATE_STATUS_UPDATE_AVAILABLE,
                        UPDATE_STATUS_UPDATING,
                        UPDATE_STATUS_UP_TO_DATE)
from ..engine.workers import PollWorker
from ..options import Options
from ..utils import version_le

log = getLogger(__name__)


class BaseUpdater(PollWorker):
    """ Updater class for frozen application. """

    # Used on macOS to trigger the application exit on sucessful update
    appUpdated = pyqtSignal()

    # Used to display a notification when a new version is available
    updateAvailable = pyqtSignal()

    versions = {}
    nature = 'release'

    __update_site = None

    def __init__(self, manager):
        # type: (Manager) -> None

        super(BaseUpdater, self).__init__(Options.update_check_delay)
        self.manager = manager

        self.enable = getattr(self, '_enable', Options.is_frozen)
        self.last_status = (UPDATE_STATUS_UP_TO_DATE, None)

        if not self.enable:
            log.info('Auto-update disabled (frozen=%r)', Options.is_frozen)

    #
    # Read-only properties
    #

    @property
    def server_ver(self):
        # type: () -> Union[None, unicode]
        """
        Get the current Nuxeo version.
        It will take the server version of the first found engine.
        `None` if no bound engine.
        """

        for engine in self.manager.get_engines().values():
            return engine.get_server_version()
        return None

    @property
    def update_site(self):
        # type: () -> unicode
        """ The update site URL without trailing slash. """

        if not self.__update_site:

            if self.manager.get_beta_channel():
                log.debug('Update beta channel activated')
                url, self.nature = Options.beta_update_site_url, 'beta'
            else:
                url, self.nature = Options.update_site_url, 'release'
            self.__update_site = url.rstrip('/')

        return self.__update_site

    #
    # Public methods that can be overrided
    #

    def force_status(self, status, version):
        # type: (unicode, unicode) -> None
        """
        Trigger the auto-update notification with given status and version.
        Used for debugging purposes only.
        """

        if status == UPDATE_STATUS_UPDATING:
            # Put a percentage
            self.last_status = (status, version, 40)
        else:
            self.last_status = (status, version)

        if status == UPDATE_STATUS_UPDATE_AVAILABLE:
            self.updateAvailable.emit()

    def install(self, filename):
        # type: (unicode) -> None
        """
        Install the new version.
        Uninstallation of the old one or any actions needed to install
        the new one has to be handled by this method.
        """
        raise NotImplementedError()

    def refresh_status(self):
        # type: () -> None
        """
        Check for an update.
        Used when changing the beta channel option or when
        binding a new engine.
        """

        if not self.enable:
            return

        self._poll()

    @pyqtSlot(str)
    def update(self, version):
        if not self.enable:
            return

        log.info('Starting application update process')
        version = str(version)
        filename = self._download(version)
        self._install(version, filename)

    #
    # Private methods, should not try to override
    #

    def _download(self, version):
        # type: (unicode) -> unicode
        """ Download a given version to a temporary file. """

        name = self.release_file.format(version=version)
        url = '/'.join([self.update_site, self.nature, name])
        path = os.path.join(gettempdir(), uuid.uuid4().hex + '_' + name)

        log.info('Fetching version %r from update site %r into %r',
                 version, self.update_site, path)
        try:
            with requests.get(url, stream=True) as req, open(path, 'wb') as tmp:
                req.raw.decode_content = True  # Handle gzipped data
                shutil.copyfileobj(req.raw, tmp)
        except Exception as exc:
            raise UpdateError('Impossible to get %r: %s' % (url, exc))

        if not self._is_valid(version, path):
            raise UpdateError('Installer integrity check failed for %r' % name)

        return path

    def _fetch_versions(self):
        # type: () -> None
        """ Fetch available versions. It sets `self.versions` on success. """

        url = self.update_site + '/versions.yml'
        try:
            req = requests.get(url)
            req.raise_for_status()
        except Exception as exc:
            raise UpdateError('Impossible to get %r: %s' % (url, exc))
        else:
            content = req.text

        try:
            versions = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise UpdateError('Parsing error: %s' % exc)
        else:
            self.versions = versions

    def _get_update_status(self):
        # type: () -> Tuple[unicode, Union[None, bool]]
        """ Retrieve available versions and find a possible candidate. """

        try:
            # Fetch all available versions
            self._fetch_versions()
        except UpdateError:
            status = (UPDATE_STATUS_UNAVAILABLE_SITE, None)
        else:
            # Find the latest available version
            latest, info = get_latest_compatible_version(
                self.versions, self.nature, self.server_ver)

            current = self.manager.version
            if not latest or current == latest:
                status = (UPDATE_STATUS_UP_TO_DATE, None)
            elif not version_le(latest, current):
                status = (UPDATE_STATUS_UPDATE_AVAILABLE, latest)
            else:
                status = (UPDATE_STATUS_DOWNGRADE_NEEDED, latest)

        return status

    def _handle_status(self):
        # type: () -> None
        """ Handle update check status. """

        status, version = self.last_status[:2]

        if status == UPDATE_STATUS_UNAVAILABLE_SITE:
            log.warning('Update site is unavailable, as a consequence'
                        ' update features won\'t be available')
        elif status == UPDATE_STATUS_DOWNGRADE_NEEDED:
            log.info('Downgrade to version %r is needed', version)
            log.info('As current client version is not compatible with'
                     ' server version, a downgrade is needed.'
                     ' Synchronization won\'t start until then.')
            self.manager.stop()
            self.updateAvailable.emit()
        elif status == UPDATE_STATUS_UPDATE_AVAILABLE:
            if self.manager.get_auto_update():
                log.info('An application update is available and'
                         ' auto-update is checked')
                self.last_status = (UPDATE_STATUS_UPDATING, version, 0)
                try:
                    self.update(version)
                except UpdateError:
                    log.exception('An error occurred while trying to '
                                  'automatically update Nuxeo Drive to '
                                  'version %r', version)
            else:
                log.info('An update is available and auto-update is not'
                         ' checked, let\'s just update the systray notification'
                         ' and let the user explicitly choose to update')
                self.updateAvailable.emit()
        else:
            log.debug('You are up-to-date!')

    def _install(self, version, filename):
        # type: (unicode, unicode) -> None
        """
        OS-specific method to install the new version.
        It must take care of uninstalling the current one.
        """

        log.info('Installing %s %s', self.manager.app_name, version)
        self.install(filename)

    def _is_valid(self, version, filename):
        # type: (unicode, unicode) -> bool
        """ Check the downloaded file integrity. Use SHA256 by default. """

        info = self.versions.get(version, {})
        checksums = info.get('checksum', {})
        algo = checksums.get('algo', 'sha256').lower()
        checksum = checksums.get(self.ext, '').lower()
        if not checksum:
            log.error('Invalid version info %r (version=%r)', info, version)
            return False

        func = getattr(hashlib, algo, 'sha256')()
        with open(filename, 'rb') as installer:
            for chunk in iter(lambda: installer.read(16384), ''):
                func.update(chunk)
        computed = func.hexdigest()

        log.trace('Integrity check [%s] for %r: good=%r, found=%r',
                  algo.upper(), filename, checksum, computed)
        return computed == checksum

    @pyqtSlot()
    def _poll(self):
        ret = True

        if self.enable and self.last_status != UPDATE_STATUS_UPDATING:
            log.debug('Polling %r for update, the current version is %r',
                      self.update_site, self.manager.version)
            try:
                status = self._get_update_status()
                if status != self.last_status:
                    self.last_status = status
                self._handle_status()
                ret = status != UPDATE_STATUS_UNAVAILABLE_SITE
            finally:
                # Reset the update site URL to force
                # recomputation the next time
                self.__update_site = None

        return ret
