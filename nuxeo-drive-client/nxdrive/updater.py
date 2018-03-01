# coding: utf-8
""" Application update utilities using Esky. """

import errno
import json
import socket
import sys
from logging import getLogger
from urllib2 import HTTPError, URLError
from urlparse import urljoin

from PyQt4 import QtCore
from esky import Esky
from esky.errors import Error

from nxdrive.engine.activity import Action
from nxdrive.engine.workers import PollWorker
from nxdrive.options import Options
from nxdrive.utils import version_compare, version_compare_client

log = getLogger(__name__)

# Update statuses
UPDATE_STATUS_UPGRADE_NEEDED = 'upgrade_needed'
UPDATE_STATUS_DOWNGRADE_NEEDED = 'downgrade_needed'
UPDATE_STATUS_UPDATE_AVAILABLE = 'update_available'
UPDATE_STATUS_UPDATING = 'updating'
UPDATE_STATUS_UP_TO_DATE = 'up_to_date'
UPDATE_STATUS_UNAVAILABLE_SITE = 'unavailable_site'
UPDATE_STATUS_MISSING_INFO = 'missing_info'
UPDATE_STATUS_MISSING_VERSION = 'missing_version'

DEFAULT_SERVER_MIN_VERSION = '7.10'


class UnavailableUpdateSite(Exception):
    pass


class MissingUpdateSiteInfo(Exception):
    pass


class MissingCompatibleVersion(Exception):
    pass


class UpdateError(Error):
    pass


class FakeUpdater(QtCore.QObject):

    refreshStatus = QtCore.pyqtSignal()
    _doUpdate = QtCore.pyqtSignal(str)
    appUpdated = QtCore.pyqtSignal(str)
    updateAvailable = QtCore.pyqtSignal()

    @staticmethod
    def get_status():
        return UPDATE_STATUS_UNAVAILABLE_SITE, None

    def force_status(self, status, version):
        pass

    def refresh_status(self):
        pass

    def update(self, version):
        pass

    @staticmethod
    def get_active_version():
        from nxdrive import __version__
        return __version__


class AppUpdater(PollWorker):
    """Class for updating a frozen application.

    Basically an Esky wrapper.
    """
    refreshStatus = QtCore.pyqtSignal()
    _doUpdate = QtCore.pyqtSignal(str)
    appUpdated = QtCore.pyqtSignal(str)
    updateAvailable = QtCore.pyqtSignal()

    def __init__(self, manager, version_finder=None,
                 check_interval=Options.update_check_delay,
                 esky_app=None, local_update_site=False):
        super(AppUpdater, self).__init__(check_interval)
        self.refreshStatus.connect(self._poll)
        self._doUpdate.connect(self._update)
        self._manager = manager
        self._enable = False
        if esky_app is not None:
            self.esky_app = esky_app
            self._enable = True
        elif not hasattr(sys, 'frozen'):
            log.debug("Application is not frozen, cannot build Esky"
                      " instance, as a consequence update features"
                      " won't be available")
        elif version_finder is None:
            log.debug("Cannot initialize Esky instance with no"
                      " version finder, as a consequence update"
                      " features won't be available")
        else:
            try:
                executable = sys.executable
                log.debug("Application is frozen, building Esky instance from"
                          " executable %s and version finder %s",
                          executable.decode('utf-8'), version_finder)
                self.esky_app = Esky(executable, version_finder=version_finder)
                self._enable = True
            except UpdateError:
                log.exception('Error initializing Esky instance, as a'
                              ' consequence update features will not'
                              ' be available')
        self.local_update_site = local_update_site
        if self._enable:
            self.update_site = self.esky_app.version_finder.download_url
            if not self.local_update_site and not self.update_site.endswith('/'):
                self.update_site += '/'
        self.last_status = (UPDATE_STATUS_UP_TO_DATE, None)

    def get_status(self):
        return self.last_status

    def force_status(self, status, version):
        if status == 'updating':
            # Put a percentage
            self.last_status = (status, version, 40)
        else:
            self.last_status = (status, version)
        if status == UPDATE_STATUS_UPDATE_AVAILABLE:
            self.updateAvailable.emit()

    def refresh_status(self):
        if self._enable:
            self.refreshStatus.emit()

    @QtCore.pyqtSlot()
    def _poll(self):
        if self.last_status != UPDATE_STATUS_UPDATING:
            # Refresh update site URL
            self.set_version_finder(
                self._manager.get_version_finder())
            log.debug(
                'Polling %s for application update, current version is %s',
                self.update_site, self._manager.get_version())
            status = self._get_update_status()
            if status != self.last_status:
                self.last_status = status
            self._handle_status()
            return status != UPDATE_STATUS_UNAVAILABLE_SITE
        else:
            return True

    def _handle_status(self):
        update_status = self.last_status[0]
        update_version = self.last_status[1]
        if update_status == UPDATE_STATUS_UNAVAILABLE_SITE:
            # Update site unavailable
            log.warning("Update site is unavailable, as a consequence"
                        " update features won't be available")
        elif update_status in [UPDATE_STATUS_MISSING_INFO,
                                  UPDATE_STATUS_MISSING_VERSION]:
            # Information or version missing in update site
            log.warning("Some information or version file is missing in"
                        " the update site, as a consequence update"
                        " features won't be available")
        else:
            # Update information successfully fetched
            log.debug("Fetched information from update site %s: update"
                     " status = '%s', update version = '%s'",
                     self.update_site, update_status, update_version)
            if update_status in (UPDATE_STATUS_DOWNGRADE_NEEDED,
                                 UPDATE_STATUS_UPGRADE_NEEDED):
                # Current client version not compatible with server
                # version, upgrade or downgrade needed.
                # Let's stop synchronization.
                log.info("As current client version is not compatible with"
                         " server version, an upgrade or downgrade is"
                         " needed. Synchronization won't start until then.")
                self._manager.stop()
            elif update_status == UPDATE_STATUS_UPDATE_AVAILABLE and \
                    self._manager.get_auto_update():
                # Update available and auto-update checked, let's process update
                log.info("An application update is available and"
                         " auto-update is checked")
                self.last_status = (UPDATE_STATUS_UPDATING, update_version, 0)
                try:
                    self._update(update_version)
                except UpdateError:
                    log.exception('An error occurred while trying to '
                                  'automatically update Nuxeo Drive to '
                                  'version %s, disaling auto-update.',
                                  update_version)
                    self._manager.set_auto_update(False)
            elif update_status == UPDATE_STATUS_UPDATE_AVAILABLE and \
                    not self._manager.get_auto_update():
                # Update available and auto-update not checked, let's just
                # update the systray notification and let the user explicitly
                # choose to  update
                log.info("An update is available and auto-update is not"
                         " checked, let's just update the systray notification"
                         " and let the user explicitly choose to update")
                self.updateAvailable.emit()
            else:
                # Application is up-to-date
                log.debug("Application is up-to-date")

    def set_version_finder(self, version_finder):
        self.esky_app._set_version_finder(version_finder)
        self.update_site = self.esky_app.version_finder.download_url

    def get_active_version(self):
        return self.esky_app.active_version

    def get_current_latest_version(self):
        return self.esky_app.version

    def find_versions(self):
        versions = [self.get_current_latest_version()]

        try:
            versions.extend(
                self.esky_app.version_finder.find_versions(self.esky_app))
        except URLError as e:
            self._handle_URL_error(e)
        except socket.timeout as e:
            self._handle_timeout_error(e)
        except:
            log.exception('Impossible to find versions')

        return sorted(versions, cmp=version_compare_client)

    def get_server_min_version(self, client_version):
        info_file = client_version + '.json'
        missing_msg = (
            "Missing or invalid file '%s' in update site '%s', can't get"
            " server minimum version for client version %s" % (
                                info_file, self.update_site, client_version))
        try:
            if not self.local_update_site:
                url = urljoin(self.update_site, info_file)
            else:
                url = info_file
            info = self.esky_app.version_finder.open_url(url)
            version = json.loads(info.read())['nuxeoPlatformMinVersion']
            log.debug("Fetched server minimum version for client version %s"
                      " from %s: %s", client_version, url, version)
            return version
        except HTTPError:
            version = DEFAULT_SERVER_MIN_VERSION
            log.debug(missing_msg + ', using default one: %s', version)
        except URLError as e:
            self._handle_URL_error(e)
        except socket.timeout as e:
            self._handle_timeout_error(e)
        except:
            log.exception(missing_msg)
            raise MissingUpdateSiteInfo(missing_msg)

    def _get_client_min_version(self, server_version):
        info_file = server_version + '.json'
        missing_msg = (
            "Missing or invalid file '%s' in update site '%s', can't get"
            " client minimum version for server version %s" % (
                                info_file, self.update_site, server_version))
        try:
            if not self.local_update_site:
                url = urljoin(self.update_site, info_file)
            else:
                url = info_file
            info = self.esky_app.version_finder.open_url(url)
            version = json.loads(info.read())['nuxeoDriveMinVersion']
            log.debug("Fetched client minimum version for server version %s"
                      " from %s: %s", server_version, url, version)
            return version
        except HTTPError as exc:
            if exc.code != 404:
                log.exception('Network error')
            raise MissingUpdateSiteInfo(missing_msg)
        except URLError as e:
            self._handle_URL_error(e)
        except socket.timeout as e:
            self._handle_timeout_error(e)
        except:
            log.exception(missing_msg)
            raise MissingUpdateSiteInfo(missing_msg)

    def compute_common_versions(self):
        # Get the max minimal client version
        # Get the min minimal server version
        self.min_client_version = None
        self.min_server_version = None
        for engine in self._manager.get_engines().values():
            server_version = engine.get_server_version()
            if server_version is None:
                continue
            if self.min_server_version is None:
                self.min_server_version = server_version
            if version_compare(self.min_server_version, server_version) > 0:
                self.min_server_version = server_version
            client_version = self._get_client_min_version(server_version)
            if self.min_client_version is None:
                self.min_client_version = client_version
                continue
            # Get the maximal "minimum"
            if version_compare_client(self.min_client_version, client_version) < 0:
                self.min_client_version = client_version

    def get_latest_compatible_version(self):
        self.compute_common_versions()
        latest_version = None
        for client_version in self.find_versions():
            if version_compare_client(self.min_client_version, client_version) < 1:
                server_min_version = self.get_server_min_version(
                                                    client_version)
                if version_compare(server_min_version, self.min_server_version) < 1:
                    latest_version = client_version
        if latest_version is None:
            raise MissingCompatibleVersion(
                    "No client version compatible with server version %s"
                    " available in update site '%s'" % (
                                self.min_server_version, self.update_site))
        return latest_version

    def _get_update_status(self):
        try:
            client_version = self._manager.get_version()
            latest_version = self.get_latest_compatible_version()
            # TO_REVIEW What the need for that
            self.get_server_min_version(client_version)
            server_version = self.min_server_version
            client_min_version = self.min_client_version
            server_min_version = self.min_server_version
            if client_version == latest_version:
                log.debug("Client version %s is up-to-date regarding server"
                         " version %s.", client_version, self.min_server_version)
                return UPDATE_STATUS_UP_TO_DATE, None

            if version_compare_client(client_version, client_min_version) < 0:
                log.info("Client version %s is lighter than %s, the minimum"
                         " version compatible with the server version %s."
                         " An upgrade to version %s is needed.",
                         client_version, client_min_version, server_version,
                         latest_version)
                return UPDATE_STATUS_UPGRADE_NEEDED, latest_version

            if (version_compare(server_version, server_min_version) < 0
                    or version_compare_client(latest_version, client_version) < 0):
                log.info("Server version %s is lighter than %s, the minimum"
                         " version compatible with the client version %s."
                         " A downgrade to version %s is needed.",
                         server_version, server_min_version, client_version,
                         latest_version)
                return UPDATE_STATUS_DOWNGRADE_NEEDED, latest_version

            log.info("Client version %s is compatible with server version %s,"
                     " yet an update is available: version %s.",
                     client_version, server_version, latest_version)
            return UPDATE_STATUS_UPDATE_AVAILABLE, latest_version
        except UnavailableUpdateSite as e:
            log.error(e)
            return UPDATE_STATUS_UNAVAILABLE_SITE, None
        except MissingUpdateSiteInfo as e:
            log.warning(e)
            return UPDATE_STATUS_MISSING_INFO, None
        except MissingCompatibleVersion as e:
            log.warning(e)
            return UPDATE_STATUS_MISSING_VERSION, None

    def update(self, version):
        self.last_status = (UPDATE_STATUS_UPDATING, str(version), 0)
        self._doUpdate.emit(version)

    @QtCore.pyqtSlot(str)
    def _update(self, version):
        version = str(version)
        if sys.platform == 'win32':
            # Try to update frozen application with the given version. If it
            # fails with a permission error, escalate to root and try again.
            try:
                self._do_update(version)
                self.appUpdated.emit(version)
                return
            except:
                log.exception('Updater issue, will try to get root')
            try:
                self.esky_app.get_root()
                self._do_update(version)
                self.esky_app.drop_root()
            except EnvironmentError as e:
                if e.errno == errno.EINVAL:
                    # Under Windows, this means that the sudo popup was
                    # rejected
                    self.esky_app.sudo_proxy = None
                    log.exception('Root privilege required')
                    return
                # Other EnvironmentError, probably not related to permissions
                log.exception('UpdateError')
                return
            except UpdateError:
                # Error during update process, not related to permissions
                log.exception('UpdateError')
                return
            finally:
                self.last_status = self._get_update_status()
        else:
            try:
                self._do_update(version)
            except UpdateError:
                log.exception('UpdateError')
                return
            finally:
                self.last_status = self._get_update_status()
        self.appUpdated.emit(version)

    def _update_callback(self, status):
        if "received" in status and "size" in status:
            self.action.progress = status["received"] * 100 / status["size"]
            self.last_status = (self.last_status[0],
                                self.last_status[1],
                                self.action.progress)

    def _do_update(self, version):
        log.info("Starting application update process")

        log.info("Fetching version %s from update site %s",
                 version, self.update_site)
        self.action = Action("Downloading %s version" % version)
        self.action.progress = 0
        self._update_action(self.action)
        self.esky_app.fetch_version(version, self._update_callback)

        log.info("Installing version %s", version)
        self._update_action(Action("Installing %s version" % version))
        self.esky_app.install_version(version)

        log.debug("Reinitializing Esky internal state")
        self.action.type = "Reinitializing"
        self.esky_app.reinitialize()

        log.info("Ended application update process")
        self._end_action()

    def cleanup(self, version):
        log.info("Uninstalling version %s", version)
        self.esky_app.uninstall_version(version)
        log.info("Cleaning up Esky application")
        self.esky_app.cleanup()

    def _handle_URL_error(self, e):
        raise UnavailableUpdateSite(
            'Cannot connect to update site %r' % self.update_site)

    def _handle_timeout_error(self, e):
        raise UnavailableUpdateSite(
            'Connection to update site %r timed out' % self.update_site)


class ServerOptionsUpdater(PollWorker):
    """ Class for checking server's config.json updates on a regular basis. """

    def __init__(self, manager, check_interval=Options.update_check_delay):
        super(ServerOptionsUpdater, self).__init__(check_interval)
        self.manager = manager

    @QtCore.pyqtSlot()
    def _poll(self):
        # type: () -> bool
        """ Check for the configuration file and apply updates. """

        for _, engine in self.manager._engines.items():
            client = engine.get_remote_doc_client()
            if not client:
                continue

            try:
                raw, _ = client.do_get(client.rest_api_url + 'drive/configuration')
                conf = json.loads(raw, encoding='utf-8')
            except Exception as exc:
                log.error('Polling error: {}'.format(exc))
            else:
                Options.update(conf, setter='server', fail_on_error=True)
                break

        return True
