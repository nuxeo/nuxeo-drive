from urllib2 import URLError
import subprocess
import os
import uuid
import platform
import sys
import logging
from urlparse import urlparse

from PyQt4 import QtCore
from PyQt4.QtScript import QScriptEngine

from nxdrive.utils import encrypt
from nxdrive.utils import decrypt
from nxdrive.logging_config import get_logger, FILE_HANDLER
from nxdrive.client.base_automation_client import get_proxies_for_handler
from nxdrive.utils import normalized_path
from nxdrive.updater import AppUpdater
from nxdrive.osi import AbstractOSIntegration
from nxdrive.commandline import DEFAULT_UPDATE_SITE_URL
from nxdrive import __version__
from nxdrive.utils import ENCODING, OSX_SUFFIX

log = get_logger(__name__)


try:
    # Set the cffi tmp path to lib for xattr
    if sys.platform == 'darwin' or sys.platform.startswith('linux') and hasattr(sys, 'frozen'):
        from cffi.verifier import set_tmpdir
        import nxdrive
        nxdrive_path = os.path.dirname(nxdrive.__file__)
        nxdrive_path = os.path.dirname(nxdrive_path)
        nxdrive_path = os.path.dirname(nxdrive_path)
        if sys.platform == 'darwin':
            lib_path = os.path.join(nxdrive_path, 'lib-dynload')
        else:
            lib_path = nxdrive_path
        log.debug('Using %s as tmpdir for cffi module', lib_path)
        set_tmpdir(lib_path)
except Exception as e:
    pass


class FolderAlreadyUsed(Exception):
    pass


class EngineTypeMissing(Exception):
    pass


class MissingToken(Exception):
    pass


class ServerBindingSettings(object):
    """Summarize server binding settings"""

    def __init__(self, web_authentication=False, server_url=None, server_version=None,
                 username=None, password=None,
                 local_folder=None, initialized=False,
                 pwd_update_required=False):
        self.web_authentication = web_authentication
        self.server_url = server_url
        self.server_version = server_version
        self.username = username
        self.password = password
        self.local_folder = local_folder
        self.initialized = initialized
        self.pwd_update_required = pwd_update_required

    def __repr__(self):
        return ("ServerBindingSettings<web_authentication=%r, server_url=%s, server_version=%s, "
                "username=%s, local_folder=%s, initialized=%r, "
                "pwd_update_required=%r>") % (
                    self.web_authentication, self.server_url, self.server_version, self.username,
                    self.local_folder, self.initialized,
                    self.pwd_update_required)


class ProxySettings(object):
    """Summarize HTTP proxy settings"""

    def __init__(self, dao=None, config='System', proxy_type=None,
                 server=None, port=None,
                 authenticated=False, username=None, password=None,
                 exceptions=None):
        self.config = config
        self.proxy_type = proxy_type
        self.server = server
        self.port = port
        self.authenticated = authenticated
        self.username = username
        self.password = password
        self.exceptions = exceptions
        if dao is not None:
            self.load(dao)

    def from_url(self, url):
        if not "://" in url:
            url = "all://" + url
        url_obj = urlparse(url)
        self.username = url_obj.username
        self.password = url_obj.password
        self.authenticated = (self.username is not None and
                              self.password is not None)
        self.port = url_obj.port
        self.server = url_obj.hostname
        if url_obj.scheme == "all":
            self.proxy_type = None
        else:
            self.proxy_type = url_obj.scheme
        self.config = "Manual"

    def to_url(self, with_credentials=True):
        if self.config != "Manual":
            return ""
        result = ""
        if self.proxy_type is not None:
            result = self.proxy_type + "://"
        if with_credentials and self.authenticated:
            result = result + self.username + ":" + self.password + "@"
        if self.server is not None:
            if self.port is None:
                result = result + self.server
            else:
                result = result + self.server + ":" + str(self.port)
        return result

    def set_exceptions(self, exceptions):
        self.exceptions = exceptions

    def save(self, dao, token=None):
        # Encrypt password with token as the secret
        if token is None:
            token = dao.get_config("device_id", None)
        if token is None:
            raise MissingToken("Your token has been revoked,"
                        " please update your password to acquire a new one.")
        token = token + "_proxy"
        password = encrypt(self.password, token)
        dao.update_config("proxy_password", password)
        dao.update_config("proxy_username", self.username)
        dao.update_config("proxy_exceptions", self.exceptions)
        dao.update_config("proxy_port", self.port)
        dao.update_config("proxy_type", self.proxy_type)
        dao.update_config("proxy_config", self.config)
        dao.update_config("proxy_server", self.server)
        dao.update_config("proxy_authenticated", self.authenticated)

    def load(self, dao, token=None):
        self.config = dao.get_config("proxy_config", "System")
        self.proxy_type = dao.get_config("proxy_type", None)
        self.port = dao.get_config("proxy_port", None)
        self.server = dao.get_config("proxy_server", None)
        self.username = dao.get_config("proxy_username", None)
        password = dao.get_config("proxy_password", None)
        self.exceptions = dao.get_config("proxy_exceptions", None)
        self.authenticated = (dao.get_config("proxy_authenticated", "0") == "1")
        if token is None:
            token = dao.get_config("device_id", None)
        if password is not None and token is not None:
            token = token + "_proxy"
            self.password = decrypt(password, token)
        else:
            # If no server binding or no token available
            # (possibly after token revocation) reset password
            self.password = ''

    def __repr__(self):
        return ("ProxySettings<config=%s, proxy_type=%s, server=%s, port=%s, "
                "authenticated=%r, username=%s, exceptions=%s>") % (
                    self.config, self.proxy_type, self.server, self.port,
                    self.authenticated, self.username, self.exceptions)


class Manager(QtCore.QObject):
    '''
    classdocs
    '''
    proxyUpdated = QtCore.pyqtSignal(object)
    clientUpdated = QtCore.pyqtSignal(object, object)
    engineNotFound = QtCore.pyqtSignal(object)
    newEngine = QtCore.pyqtSignal(object)
    dropEngine = QtCore.pyqtSignal(object)
    initEngine = QtCore.pyqtSignal(object)
    aboutToStart = QtCore.pyqtSignal(object)
    started = QtCore.pyqtSignal()
    stopped = QtCore.pyqtSignal()
    suspended = QtCore.pyqtSignal()
    resumed = QtCore.pyqtSignal()
    _singleton = None

    @staticmethod
    def get():
        return Manager._singleton

    def __init__(self, options):
        '''
        Constructor
        '''
        if Manager._singleton is not None:
            raise Exception("Only one instance of Manager can be create")
        Manager._singleton = self
        super(Manager, self).__init__()

        # Let's bypass HTTPS verification unless --consider-ssl-errors is passed
        # since many servers unfortunately have invalid certificates.
        # See https://www.python.org/dev/peps/pep-0476/
        # and https://jira.nuxeo.com/browse/NXDRIVE-506
        if not options.consider_ssl_errors:
            log.warn("--consider-ssl-errors option is False, won't verify HTTPS certificates")
            import ssl
            try:
                _create_unverified_https_context = ssl._create_unverified_context
            except AttributeError:
                log.info("Legacy Python that doesn't verify HTTPS certificates by default")
            else:
                log.info("Handle target environment that doesn't support HTTPS verification:"
                         " globally disable verification by monkeypatching the ssl module though highly discouraged")
                ssl._create_default_https_context = _create_unverified_https_context
        else:
            log.info("--consider-ssl-errors option is True, will verify HTTPS certificates")
        self._autolock_service = None
        self.client_version = __version__
        self.nxdrive_home = os.path.expanduser(options.nxdrive_home)
        self.nxdrive_home = os.path.realpath(self.nxdrive_home)
        if not os.path.exists(self.nxdrive_home):
            os.mkdir(self.nxdrive_home)
        self.remote_watcher_delay = options.delay
        self._nofscheck = options.nofscheck
        self._debug = options.debug
        self._engine_definitions = None
        self._engine_types = dict()
        from nxdrive.engine.next.engine_next import EngineNext
        from nxdrive.engine.engine import Engine
        self._engine_types["NXDRIVE"] = Engine
        self._engine_types["NXDRIVENEXT"] = EngineNext
        self._engines = None
        self.proxies = None
        self.proxy_exceptions = None
        self._app_updater = None
        self._dao = None
        self._create_dao()
        if options.proxy_server is not None:
            proxy = ProxySettings()
            proxy.from_url(options.proxy_server)
            proxy.save(self._dao)
        # Now we can update the logger if needed
        if options.log_level_file is not None:
            # Set the log_level_file option
            handler = self._get_file_log_handler()
            if handler is not None:
                handler.setLevel(options.log_level_file)
                # Store it in the database
                self._dao.update_config("log_level_file", str(handler.level))
        else:
            # No log_level provide, use the one from db default is INFO
            self._update_logger(int(self._dao.get_config("log_level_file", "20")))
        # Add auto lock on edit
        res = self._dao.get_config("drive_edit_auto_lock")
        if res is None:
            self._dao.update_config("update_url", "1")
        # Persist update URL infos
        self._dao.update_config("update_url", options.update_site_url)
        self._dao.update_config("beta_update_url", options.beta_update_site_url)
        self.refresh_proxies()
        self._os = AbstractOSIntegration.get(self)
        # Create DriveEdit
        self._create_autolock_service()
        self._create_drive_edit(options.protocol_url)
        # Create notification service
        self._script_engine = None
        self._script_object = None
        self._create_notification_service()
        self._started = False
        # Pause if in debug
        self._pause = self.is_debug()
        self.device_id = self._dao.get_config("device_id")
        self.updated = False  # self.update_version()
        if self.device_id is None:
            self.generate_device_id()

        self.load()

        # Create the application update verification thread
        self._create_updater(options.update_check_delay)

        # Force language
        if options.force_locale is not None:
            self.set_config("locale", options.force_locale)
        # Setup analytics tracker
        self._tracker = None
        if self.get_tracking():
            self._create_tracker()

    def _get_file_log_handler(self):
        # Might store it in global static
        return FILE_HANDLER

    def get_metrics(self):
        result = dict()
        result["version"] = self.get_version()
        result["auto_start"] = self.get_auto_start()
        result["auto_update"] = self.get_auto_update()
        result["beta_channel"] = self.get_beta_channel()
        result["device_id"] = self.get_device_id()
        result["tracker_id"] = self.get_tracker_id()
        result["tracking"] = self.get_tracking()
        result["qt_version"] = QtCore.QT_VERSION_STR
        result["pyqt_version"] = QtCore.PYQT_VERSION_STR
        result["python_version"] = platform.python_version()
        result["platform"] = platform.system()
        result["appname"] = self.get_appname()
        return result

    def open_help(self):
        self.open_local_file("http://doc.nuxeo.com/display/USERDOC/Nuxeo+Drive")

    def get_log_level(self):
        handler = self._get_file_log_handler()
        if handler:
            return handler.level
        return logging.getLogger().getEffectiveLevel()

    def set_log_level(self, log_level):
        self._dao.update_config("log_level_file", str(log_level))
        self._update_logger(log_level)

    def _update_logger(self, log_level):
        logging.getLogger().setLevel(
                        min(log_level, logging.getLogger().getEffectiveLevel()))
        handler = self._get_file_log_handler()
        if handler:
            handler.setLevel(log_level)

    def get_osi(self):
        return self._os

    def _handle_os(self):
        # Be sure to register os
        self._os.register_contextual_menu()
        self._os.register_protocol_handlers()
        if self.get_auto_start():
            self._os.register_startup()

    def get_appname(self):
        return "Nuxeo Drive"

    def is_debug(self):
        return self._debug

    def is_checkfs(self):
        return not self._nofscheck

    def get_device_id(self):
        return self.device_id

    def get_notification_service(self):
        return self._notification_service

    def _create_notification_service(self):
        # Dont use it for now
        from nxdrive.notification import DefaultNotificationService
        self._notification_service = DefaultNotificationService(self)
        return self._notification_service

    def get_autolock_service(self):
        return self._autolock_service

    def _create_autolock_service(self):
        from nxdrive.autolocker import ProcessAutoLockerWorker
        self._autolock_service = ProcessAutoLockerWorker(30, self)
        self.started.connect(self._autolock_service._thread.start)
        return self._autolock_service

    def _create_tracker(self):
        from nxdrive.engine.tracker import Tracker
        self._tracker = Tracker(self)
        # Start the tracker when we launch
        self.started.connect(self._tracker._thread.start)
        return self._tracker

    def get_tracker_id(self):
        if self.get_tracking() and self._tracker is not None:
            return self._tracker.uid
        return ""

    def get_tracker(self):
        return self._tracker

    def _get_db(self):
        return os.path.join(normalized_path(self.nxdrive_home), "manager.db")

    def get_dao(self):
        return self._dao

    def _migrate(self):
        from nxdrive.engine.dao.sqlite import ManagerDAO
        self._dao = ManagerDAO(self._get_db())
        old_db = os.path.join(normalized_path(self.nxdrive_home), "nxdrive.db")
        if os.path.exists(old_db):
            import sqlite3
            from nxdrive.engine.dao.sqlite import CustomRow
            conn = sqlite3.connect(old_db)
            conn.row_factory = CustomRow
            c = conn.cursor()
            cfg = c.execute("SELECT * FROM device_config LIMIT 1").fetchone()
            if cfg is not None:
                self.device_id = cfg.device_id
                self._dao.update_config("device_id", cfg.device_id)
                self._dao.update_config("proxy_config", cfg.proxy_config)
                self._dao.update_config("proxy_type", cfg.proxy_type)
                self._dao.update_config("proxy_server", cfg.proxy_server)
                self._dao.update_config("proxy_port", cfg.proxy_port)
                self._dao.update_config("proxy_authenticated", cfg.proxy_authenticated)
                self._dao.update_config("proxy_username", cfg.proxy_username)
                self._dao.update_config("auto_update", cfg.auto_update)
            # Copy first server binding
            rows = c.execute("SELECT * FROM server_bindings").fetchall()
            if not rows:
                return
            first_row = True
            for row in rows:
                row.url = row.server_url
                log.debug("Binding server from Nuxeo Drive V1: [%s, %s]", row.url, row.remote_user)
                row.username = row.remote_user
                row.password = None
                row.token = row.remote_token
                row.no_fscheck = True
                engine = self.bind_engine(self._get_default_server_type(), row["local_folder"],
                                          self._get_engine_name(row.url), row, starts=False)
                log.trace("Resulting server binding remote_token %r", row.remote_token)
                if first_row:
                    first_engine_def = row
                    first_engine = engine
                    first_row = False
                else:
                    engine.dispose_db()
            # Copy filters for first engine as V1 only supports filtering for the first server binding
            filters = c.execute("SELECT * FROM filters")
            for filter_obj in filters:
                if first_engine_def.local_folder != filter_obj.local_folder:
                    continue
                log.trace("Filter Row from DS1 %r", filter_obj)
                first_engine.add_filter(filter_obj["path"])
            first_engine.dispose_db()

    def _create_dao(self):
        from nxdrive.engine.dao.sqlite import ManagerDAO
        if not os.path.exists(self._get_db()):
            try:
                self._migrate()
                return
            except Exception as e:
                log.error(e, exc_info=True)
        self._dao = ManagerDAO(self._get_db())

    def _create_updater(self, update_check_delay):
        # Enable the capacity to extend the AppUpdater
        self._app_updater = AppUpdater(self, version_finder=self.get_version_finder(),
                                       check_interval=update_check_delay)
        self.started.connect(self._app_updater._thread.start)
        return self._app_updater

    def get_version_finder(self, refresh_engines=False):
        # Used by extended application to inject version finder
        if self.get_beta_channel():
            log.debug('Update beta channel activated')
            update_site_url = self._get_beta_update_url(refresh_engines)
        else:
            update_site_url = self._get_update_url(refresh_engines)
        if update_site_url is None:
            update_site_url = DEFAULT_UPDATE_SITE_URL
        if not update_site_url.endswith('/'):
            update_site_url += '/'
        return update_site_url

    def _get_update_url(self, refresh_engines):
        update_url = self._dao.get_config("update_url", DEFAULT_UPDATE_SITE_URL)
        # If update site URL is not overridden in config.ini nor through the command line, refresh engine update infos
        # and use first engine configuration
        if update_url == DEFAULT_UPDATE_SITE_URL:
            try:
                if refresh_engines:
                    self._refresh_engine_update_infos()
                engines = self.get_engines()
                if engines:
                    first_engine = engines.itervalues().next()
                    update_url = first_engine.get_update_url()
                    log.debug('Update site URL has not been overridden in config.ini nor through the command line,'
                              ' using configuration from first engine [%s]: %s', first_engine._name, update_url)
            except URLError as e:
                log.error('Cannot refresh engine update infos, using default update site URL', exc_info=True)
        return update_url

    def _get_beta_update_url(self, refresh_engines):
        beta_update_url = self._dao.get_config("beta_update_url")
        if beta_update_url is None:
            if refresh_engines:
                self._refresh_engine_update_infos()
            engines = self.get_engines()
            if engines:
                for engine in engines.itervalues():
                    beta_update_url = engine.get_beta_update_url()
                    if beta_update_url is not None:
                        log.debug('Beta update site URL has not been defined in config.ini nor through the command'
                                  ' line, using configuration from engine [%s]: %s', engine._name, beta_update_url)
                        return beta_update_url
        return beta_update_url

    def is_beta_channel_available(self):
        return self._get_beta_update_url(False) is not None

    def get_updater(self):
        return self._app_updater

    def refresh_update_status(self):
        if self.get_updater() is not None:
            self.get_updater().refresh_status()

    def _refresh_engine_update_infos(self):
        log.debug('Refreshing engine infos')
        engines = self.get_engines()
        if engines:
            for engine in engines.itervalues():
                engine.get_update_infos()

    def _create_drive_edit(self, url):
        from nxdrive.drive_edit import DriveEdit
        self._drive_edit = DriveEdit(self, os.path.join(normalized_path(self.nxdrive_home), "edit"), url)
        self.started.connect(self._drive_edit._thread.start)
        return self._drive_edit

    def get_drive_edit(self):
        return self._drive_edit

    def is_paused(self):
        return self._pause

    def resume(self, euid=None):
        if not self._pause:
            return
        self._pause = False
        for uid, engine in self._engines.items():
            if euid is not None and euid != uid:
                continue
            log.debug("Resume engine %s", uid)
            engine.resume()
        self.resumed.emit()

    def suspend(self, euid=None):
        if self._pause:
            return
        self._pause = True
        for uid, engine in self._engines.items():
            if euid is not None and euid != uid:
                continue
            log.debug("Suspend engine %s", uid)
            engine.suspend()
        self.suspended.emit()

    def stop(self, euid=None):
        for uid, engine in self._engines.items():
            if euid is not None and euid != uid:
                continue
            if engine.is_started():
                log.debug("Stop engine %s", uid)
                engine.stop()
        self.stopped.emit()

    def start(self, euid=None):
        self._started = True
        for uid, engine in self._engines.items():
            if euid is not None and euid != uid:
                continue
            if not self._pause:
                self.aboutToStart.emit(engine)
                log.debug("Launch engine %s", uid)
                try:
                    engine.start()
                except Exception as e:
                    log.debug("Could not start the engine: %s [%r]", uid, e)
        log.debug("Emitting started")
        # Check only if manager is started
        self._handle_os()
        self.started.emit()

    def load(self):
        if self._engine_definitions is None:
            self._engine_definitions = self._dao.get_engines()
        in_error = dict()
        self._engines = dict()
        for engine in self._engine_definitions:
            if not engine.engine in self._engine_types:
                log.warn("Can't find engine %s anymore", engine.engine)
                if not engine.engine in in_error:
                    in_error[engine.engine] = True
                    self.engineNotFound.emit(engine)
            self._engines[engine.uid] = self._engine_types[engine.engine](self, engine,
                                                                        remote_watcher_delay=self.remote_watcher_delay)
            self._engines[engine.uid].online.connect(self._force_autoupdate)
            self.initEngine.emit(self._engines[engine.uid])

    def _get_default_nuxeo_drive_name(self):
        return 'Nuxeo Drive'

    def _force_autoupdate(self):
        if (self._app_updater.get_next_poll() > 60 and self._app_updater.get_last_poll() > 1800):
            self._app_updater.force_poll()

    def get_default_nuxeo_drive_folder(self):
        # TODO: Factorize with utils.default_nuxeo_drive_folder
        """Find a reasonable location for the root Nuxeo Drive folder

        This folder is user specific, typically under the home folder.

        Under Windows, try to locate My Documents as a home folder, using the
        win32com shell API if allowed, else falling back on a manual detection.

        Note that we need to decode the path returned by os.path.expanduser with
        the local encoding because the value of the HOME environment variable is
        read as a byte string. Using os.path.expanduser(u'~') fails if the home
        path contains non ASCII characters since Unicode coercion attempts to
        decode the byte string as an ASCII string.
        """
        if sys.platform == "win32":
            from win32com.shell import shell, shellcon
            try:
                my_documents = shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL,
                                                     None, 0)
            except:
                # In some cases (not really sure how this happens) the current user
                # is not allowed to access its 'My Documents' folder path through
                # the win32com shell API, which raises the following error:
                # com_error: (-2147024891, 'Access is denied.', None, None)
                # We noticed that in this case the 'Location' tab is missing in the
                # Properties window of 'My Documents' accessed through the
                # Explorer.
                # So let's fall back on a manual (and poor) detection.
                # WARNING: it's important to check 'Documents' first as under
                # Windows 7 there also exists a 'My Documents' folder invisible in
                # the Explorer and cmd / powershell but visible from Python.
                # First try regular location for documents under Windows 7 and up
                log.debug("Access denied to win32com shell API: SHGetFolderPath,"
                          " falling back on manual detection of My Documents")
                my_documents = os.path.expanduser(r'~\Documents')
                my_documents = unicode(my_documents.decode(ENCODING))
                if not os.path.exists(my_documents):
                    # Compatibility for Windows XP
                    my_documents = os.path.expanduser(r'~\My Documents')
                    my_documents = unicode(my_documents.decode(ENCODING))

            if os.path.exists(my_documents):
                nuxeo_drive_folder = self._increment_local_folder(my_documents, self._get_default_nuxeo_drive_name())
                log.debug("Will use '%s' as default Nuxeo Drive folder location under Windows", nuxeo_drive_folder)
                return nuxeo_drive_folder

        # Fall back on home folder otherwise
        user_home = os.path.expanduser('~')
        user_home = unicode(user_home.decode(ENCODING))
        nuxeo_drive_folder = self._increment_local_folder(user_home, self._get_default_nuxeo_drive_name())
        log.debug("Will use '%s' as default Nuxeo Drive folder location", nuxeo_drive_folder)
        return nuxeo_drive_folder

    def _increment_local_folder(self, basefolder, name):
        nuxeo_drive_folder = os.path.join(basefolder, name)
        num = 2
        while (not self.check_local_folder_available(nuxeo_drive_folder)):
            nuxeo_drive_folder = os.path.join(basefolder, name + " " + str(num))
            num = num + 1
            if num > 10:
                return ""
        return nuxeo_drive_folder

    def get_configuration_folder(self):
        return self.nxdrive_home

    def open_local_file(self, file_path):
        """Launch the local OS program on the given file / folder."""
        log.debug('Launching editor on %s', file_path)
        if sys.platform == 'win32':
            os.startfile(file_path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', file_path])
        else:
            try:
                subprocess.Popen(['xdg-open', file_path])
            except OSError:
                # xdg-open should be supported by recent Gnome, KDE, Xfce
                log.error("Failed to find and editor for: '%s'", file_path)

    def check_version_updated(self):
        last_version = self._dao.get_config("client_version")
        if last_version != self.client_version:
            self.clientUpdated.emit(last_version, self.client_version)

    def generate_device_id(self):
        self.device_id = uuid.uuid1().hex
        self._dao.update_config("device_id", self.device_id)

    def get_proxy_settings(self, device_config=None):
        """Fetch proxy settings from database"""
        return ProxySettings(dao=self._dao)

    def list_server_bindings(self):
        if self._engines is None:
            self.load()
        result = []
        for definition in self._engine_definitions:
            row = definition
            row.server_version = None
            row.update_url = ""
            self._engines[row.uid].complete_binder(row)
            result.append(row)
        return result

    def get_config(self, value, default=None):
        return self._dao.get_config(value, default)

    def set_config(self, key, value):
        return self._dao.update_config(key, value)

    def get_drive_edit_auto_lock(self):
        return self._dao.get_config("drive_edit_auto_lock", "1") == "1"

    def set_drive_edit_auto_lock(self, value):
        self._dao.update_config("drive_edit_auto_lock", value)

    def get_auto_update(self):
        # By default auto update
        return self._dao.get_config("auto_update", "1") == "1"

    def set_auto_update(self, value):
        self._dao.update_config("auto_update", value)

    def get_auto_start(self):
        return self._dao.get_config("auto_start", "1") == "1"

    def _get_binary_name(self):
        return 'ndrive'

    def generate_report(self, path=None):
        from nxdrive.report import Report
        report = Report(self, path)
        report.generate()
        return report.get_path()

    def find_exe_path(self):
        """Introspect the Python runtime to find the frozen Windows exe"""
        import nxdrive
        nxdrive_path = os.path.realpath(os.path.dirname(nxdrive.__file__))
        log.trace("nxdrive_path: %s", nxdrive_path)

        # Detect frozen win32 executable under Windows
        executable = sys.executable
        if "appdata" in executable:
            executable = os.path.join(os.path.dirname(executable),
                                      "..","..",os.path.basename(
                                      sys.executable))
            exe_path = os.path.abspath(executable)
            if os.path.exists(exe_path):
                log.trace("Returning exe path: %s", exe_path)
                return exe_path

        # Detect OSX frozen app
        if nxdrive_path.endswith(OSX_SUFFIX):
            log.trace("Detected OS X frozen app")
            exe_path = nxdrive_path.replace(OSX_SUFFIX, "Contents/MacOS/"
                                                + self._get_binary_name())
            if os.path.exists(exe_path):
                log.trace("Returning exe path: %s", exe_path)
                return exe_path

        # Fall-back to the regular method that should work both the ndrive script
        exe_path = sys.argv[0]
        log.trace("Returning default exe path: %s", exe_path)
        return exe_path

    def set_auto_start(self, value):
        self._dao.update_config("auto_start", value)
        if value:
            self._os.register_startup()
        else:
            self._os.unregister_startup()

    def get_beta_channel(self):
        return self._dao.get_config("beta_channel", "0") == "1"

    def set_beta_channel(self, value):
        self._dao.update_config("beta_channel", value)
        # Trigger update status refresh
        self.refresh_update_status()

    def get_tracking(self):
        return self._dao.get_config("tracking", "1") == "1" and not self.get_version().endswith("-dev")

    def set_tracking(self, value):
        self._dao.update_config("tracking", value)
        if value:
            self._create_tracker()
        elif self._tracker is not None:
            self._tracker._thread.quit()
            self._tracker = None

    def validate_proxy_settings(self, proxy_settings):
        try:
            import urllib2
            proxies, _ = get_proxies_for_handler(proxy_settings)
            # Try google website
            url = "http://www.google.com"
            opener = urllib2.build_opener(urllib2.ProxyHandler(proxies),
                                      urllib2.HTTPBasicAuthHandler(),
                                      urllib2.HTTPHandler)
            urllib2.install_opener(opener)
            conn = urllib2.urlopen(url)
            conn.read()
        except Exception as e:
            log.error("Exception setting proxy : %s", e)
            return False
        return True

    def set_proxy_settings(self, proxy_settings, force=False):
        if force or self.validate_proxy_settings(proxy_settings):
            proxy_settings.save(self._dao)
            self.refresh_proxies(proxy_settings)
            log.info("Proxy settings successfully updated: %r", proxy_settings)
            return ""
        else:
            return "PROXY_INVALID"

    def refresh_proxies(self, proxy_settings=None, device_config=None):
        """Refresh current proxies with the given settings"""
        # If no proxy settings passed fetch them from database
        proxy_settings = (proxy_settings if proxy_settings is not None
                          else self.get_proxy_settings())
        self.proxies, self.proxy_exceptions = get_proxies_for_handler(
                                                            proxy_settings)
        self.proxyUpdated.emit(proxy_settings)

    def get_proxies(self):
        return self.proxies

    def get_engine(self, local_folder):
        if self._engines is None:
            self.load()
        for engine_def in self._engine_definitions:
            if local_folder.startswith(engine_def.local_folder):
                return self._engines[engine_def.uid]
        return None

    def edit(self, engine, remote_ref):
        """Find the local file if any and start OS editor on it."""

        doc_pair = engine.get_dao().get_normal_state_from_remote(remote_ref)
        if doc_pair is None:
            log.warning('Could not find local file for engine %s and remote_ref %s', engine.get_uid(), remote_ref)
            return

        # TODO: check synchronization of this state first

        # Find the best editor for the file according to the OS configuration
        local_client = engine.get_local_client()
        self.open_local_file(local_client._abspath(doc_pair.local_path))

    def _get_default_server_type(self):
        return "NXDRIVE"

    def bind_server(self, local_folder, url, username, password, token=None, name=None, start_engine=True, check_credentials=True):
        from collections import namedtuple
        if name is None:
            name = self._get_engine_name(url)
        binder = namedtuple('binder', ['username', 'password', 'token', 'url', 'no_check', 'no_fscheck'])
        binder.username = username
        binder.password = password
        binder.token = token
        binder.no_check = not check_credentials
        binder.no_fscheck = False
        binder.url = url
        return self.bind_engine(self._get_default_server_type(), local_folder, name, binder, starts=start_engine)

    def _get_engine_name(self, server_url):
        import urlparse
        urlp = urlparse.urlparse(server_url)
        return urlp.hostname

    def check_local_folder_available(self, local_folder):
        if self._engine_definitions is None:
            return True
        if not local_folder.endswith('/'):
            local_folder = local_folder + '/'
        for engine in self._engine_definitions:
            other = engine.local_folder
            if not other.endswith('/'):
                other = other + '/'
            if (other.startswith(local_folder) or local_folder.startswith(other)):
                return False
        return True

    def update_engine_path(self, uid, local_folder):
        # Dont update the engine by itself, should be only used by engine.update_engine_path
        if uid in self._engine_definitions:
            self._engine_definitions[uid].local_folder = local_folder
        self._dao.update_engine_path(uid, local_folder)

    def bind_engine(self, engine_type, local_folder, name, binder, starts=True):
        """Bind a local folder to a remote nuxeo server"""
        if name is None and hasattr(binder, 'url'):
            name = self._get_engine_name(binder.url)
        if hasattr(binder, 'url'):
            url = binder.url
            if '#' in url:
                # Last part of the url is the engine type
                engine_type = url.split('#')[1]
                binder.url = url.split('#')[0]
                log.debug("Engine type has been specified in the url: %s will be used", engine_type)
        if not self.check_local_folder_available(local_folder):
            raise FolderAlreadyUsed()
        if not engine_type in self._engine_types:
            raise EngineTypeMissing()
        if self._engines is None:
            self.load()
        local_folder = normalized_path(local_folder)
        if local_folder == self.get_configuration_folder():
            # Prevent from binding in the configuration folder
            raise FolderAlreadyUsed()
        uid = uuid.uuid1().hex
        # TODO Check that engine is not inside another or same position
        engine_def = self._dao.add_engine(engine_type, local_folder, uid, name)
        try:
            self._engines[uid] = self._engine_types[engine_type](self, engine_def, binder=binder,
                                                                 remote_watcher_delay=self.remote_watcher_delay)
            self._engine_definitions.append(engine_def)
        except Exception as e:
            log.exception(e)
            if uid in self._engines:
                del self._engines[uid]
            self._dao.delete_engine(uid)
            # TODO Remove the db ?
            raise e
        # As new engine was just bound, refresh application update status
        self.refresh_update_status()
        if starts:
            self._engines[uid].start()
        self.newEngine.emit(self._engines[uid])
        return self._engines[uid]
        #server_url, username, password
        # check the connection to the server by issuing an authentication
        # request

    def unbind_engine(self, uid):
        if self._engines is None:
            self.load()
        self._engines[uid].suspend()
        self._engines[uid].unbind()
        self._dao.delete_engine(uid)
        # Refresh the engines definition
        del self._engines[uid]
        self.dropEngine.emit(uid)
        self._engine_definitions = self._dao.get_engines()

    def unbind_all(self):
        if self._engines is None:
            self.load()
        for engine in self._engine_definitions:
            self.unbind_engine(engine.uid)

    def dispose_db(self):
        if self._dao is not None:
            self._dao.dispose()

    def dispose_all(self):
        for engine in self.get_engines().values():
            engine.dispose_db()
        self.dispose_db()

    def get_engines(self):
        return self._engines

    def get_engines_type(self):
        return self._engine_types

    def get_version(self):
        return self.client_version

    def update_version(self, device_config):
        if self.version != device_config.client_version:
            log.info("Detected version upgrade: current version = %s,"
                      " new version = %s => upgrading current version,"
                      " yet DB upgrade might be needed.",
                      device_config.client_version,
                      self.version)
            device_config.client_version = self.version
            self.get_session().commit()
            return True
        return False

    def is_started(self):
        return self._started

    def is_updated(self):
        return self.updated

    def is_syncing(self):
        syncing_engines = []
        for uid, engine in self._engines.items():
            if engine.is_syncing():
                syncing_engines.append(uid)
        if syncing_engines:
            log.debug("Some engines are currently synchronizing: %s", syncing_engines)
            return True
        else:
            log.debug("No engine currently synchronizing")
            return False

    def get_root_id(self, file_path):
        from nxdrive.client import LocalClient
        ref = LocalClient.get_path_remote_id(file_path, 'ndriveroot')
        if ref is None:
            parent = os.path.dirname(file_path)
            # We can't find in any parent
            if parent == file_path or parent is None:
                return None
            return self.get_root_id(parent)
        return ref

    def get_cf_bundle_identifier(self):
        return "org.nuxeo.drive"

    def get_metadata_infos(self, file_path):
        from nxdrive.client import LocalClient
        remote_ref = LocalClient.get_path_remote_id(file_path)
        if remote_ref is None:
            raise ValueError('Could not find file %s as Nuxeo Drive managed' % file_path)
        root_id = self.get_root_id(file_path)
        # TODO Add a class to handle root info
        root_values = root_id.split("|")
        try:
            engine = self.get_engines()[root_values[3]]
        except:
            raise ValueError('Unknown engine %s for %s' %
                             (root_values[3], file_path))
        metadata_url = engine.get_metadata_url(remote_ref)
        return (metadata_url, engine.get_remote_token(), engine, remote_ref)

    def set_script_object(self, obj):
        # Used to enhance scripting with UI
        self._script_object = obj

    def _create_script_engine(self):
        from nxdrive.scripting import DriveScript
        self._script_engine = QScriptEngine()
        if self._script_object is None:
            self._script_object = DriveScript(self)
        self._script_engine.globalObject().setProperty("drive", self._script_engine.newQObject(self._script_object))

    def execute_script(self, script, engine_uid=None):
        if self._script_engine is None:
            self._create_script_engine()
            if self._script_engine is None:
                return
        self._script_object.set_engine_uid(engine_uid)
        log.debug("Will execute '%s'", script)
        result = self._script_engine.evaluate(script)
        if self._script_engine.hasUncaughtException():
            log.debug("Execution exception: %r", result.toString())
