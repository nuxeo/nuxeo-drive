from PyQt4.QtCore import QObject, pyqtSignal, QCoreApplication
from nxdrive.utils import encrypt
from nxdrive.utils import decrypt
from nxdrive.logging_config import get_logger, configure
from nxdrive.client.base_automation_client import get_proxies_for_handler
from nxdrive.utils import normalized_path
from nxdrive import __version__
import subprocess
from nxdrive.utils import ENCODING
import os
import uuid
import sys
log = get_logger(__name__)


try:
    # Set the cffi tmp path to lib for xattr
    if sys.platform != "win32":
        from cffi.verifier import set_tmpdir
        import nxdrive
        nxdrive_path = os.path.dirname(nxdrive.__file__)
        nxdrive_path = os.path.dirname(nxdrive_path)
        nxdrive_path = os.path.dirname(nxdrive_path)
        lib_path = os.path.join(nxdrive_path, 'lib-dynload')
        set_tmpdir(lib_path)
except Exception as e:
    pass

class EngineTypeMissing(Exception):
    pass

class MissingToken(Exception):
    pass


class GeneralSettings(object):
    """Summarize general settings"""

    def __init__(self, auto_update=False):
        self.auto_update = auto_update

    def __repr__(self):
        return "GeneralSettings<auto_update=%r>" % self.auto_update


class ServerBindingSettings(object):
    """Summarize server binding settings"""

    def __init__(self, server_url=None, server_version=None,
                 username=None, password=None,
                 local_folder=None, initialized=False,
                 pwd_update_required=False):
        self.server_url = server_url
        self.server_version = server_version
        self.username = username
        self.password = password
        self.local_folder = local_folder
        self.initialized = initialized
        self.pwd_update_required = pwd_update_required

    def __repr__(self):
        return ("ServerBindingSettings<server_url=%s, server_version=%s, "
                "username=%s, local_folder=%s, initialized=%r, "
                "pwd_update_required=%r>") % (
                    self.server_url, self.server_version, self.username,
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

    def save(self, dao, token = None):
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


class Manager(QObject):
    '''
    classdocs
    '''
    proxyUpdated = pyqtSignal(object)
    clientUpdated = pyqtSignal(object, object)
    engineNotFound = pyqtSignal(object)
    newEngine = pyqtSignal(object)
    dropEngine = pyqtSignal(object)
    initEngine = pyqtSignal(object)
    started = pyqtSignal()
    stopped = pyqtSignal()
    suspended = pyqtSignal()
    resumed = pyqtSignal()
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
        self.nxdrive_home = os.path.expanduser(options.nxdrive_home)
        self._debug = options.debug
        self._dao = self._create_dao()
        self.proxies = None
        self.proxy_exceptions = None
        self._engines = None
        # Pause if in debug
        self._pause = self.is_debug()
        self._engine_definitions = None
        self._engine_types = dict()
        self.device_id = self._dao.get_config("device_id")
        self.updated = False#self.update_version()
        if self.device_id is None:
            self.generate_device_id()
        self.client_version = __version__
        from nxdrive.engine.engine import Engine
        self._engine_types["NXDRIVE"] = Engine
        self.load()
        # Setup analytics tracker
        if self.get_tracking():
            self._create_tracker()

    def is_debug(self):
        return self._debug

    def get_device_id(self):
        return self.device_id

    def _create_tracker(self):
        from nxdrive.engine.tracker import Tracker
        self._tracker = Tracker(self)
        # Start the tracker when we launch
        self.started.connect(self._tracker._thread.start)
        return self._tracker

    def get_tracker(self):
        return self._tracker

    def _get_db(self):
        return os.path.join(self.nxdrive_home, "manager.db")

    def _create_dao(self):
        from nxdrive.engine.dao.sqlite import ManagerDAO
        return ManagerDAO(self._get_db())

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
            log.debug("Stop engine %s", uid)
            engine.stop()
        self.stopped.emit()

    def start(self, euid=None):
        for uid, engine in self._engines.items():
            if euid is not None and euid != uid:
                continue
            log.debug("Launch engine %s", uid)
            if not self._pause:
                engine.start()
        log.debug("Emitting started")
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
            self._engines[engine.uid] = self._engine_types[engine.engine](self, engine)
            self.initEngine.emit(self._engines[engine.uid])

    def _get_default_nuxeo_drive_name(self):
        return 'Nuxeo Drive'

    def _get_default_nuxeo_drive_folder(self):
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
                nuxeo_drive_folder = os.path.join(my_documents,
                                                  self._get_default_nuxeo_drive_name())
                log.info("Will use '%s' as default Nuxeo Drive folder location"
                         " under Windows", nuxeo_drive_folder)
                return nuxeo_drive_folder

        # Fall back on home folder otherwise
        user_home = os.path.expanduser('~')
        user_home = unicode(user_home.decode(ENCODING))
        nuxeo_drive_folder = os.path.join(user_home, self._get_default_nuxeo_drive_name())
        log.info("Will use '%s' as default Nuxeo Drive folder location",
                 nuxeo_drive_folder)
        return nuxeo_drive_folder

    def get_configuration_folder(self):
        return self.nxdrive_home

    def get_server_binding_settings(self):
        """Fetch server binding settings from database"""
        if len(self._engine_definitions) == 0:
            return ServerBindingSettings(
                local_folder=self._get_default_nuxeo_drive_folder())
        else:
            # TODO: handle multiple server bindings, for now take the first one
            # See https://jira.nuxeo.com/browse/NXP-12716
            sb = self._engine_definitions[0]
            engine = self._engines[sb.uid]
            return engine.get_binder()

    def refresh_update_info(self, local_folder):
        # TO_REVIEW Not logical to review per folder
        pass

    def is_credentials_update_required(self):
        if len(self._engine_definitions) == 0:
            return True
        # TO_REVIEW Check per engine if auth is required ?
        for engine in self._engines.values():
            if engine.has_invalid_credentials():
                return True
        return False

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

    def check_update(self):
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

    def dispose(self):
        # TO_REVIEW Might need to remove it
        pass

    def get_auto_update(self):
        return self._dao.get_config("auto_update", "0") == "1"

    def set_auto_update(self, value):
        self._dao.update_config("auto_update", value)

    def get_tracking(self):
        return self._dao.get_config("tracking", "1") == "1"

    def set_tracking(self, value):
        self._dao.update_config("tracking", value)
        if value:
            self._create_tracker()
        elif self._tracker is not None:
            self._tracker._thread.quit()
            self._tracker = None

    def set_general_settings(self, settings):
        self._dao.update_config("auto_update", settings.auto_update)

    def get_general_settings(self):
        return GeneralSettings(self._dao.get_config("auto_update", "False") == "True")

    def set_proxy_settings(self, proxy_settings):
        proxy_settings.save(self._dao)
        self.refresh_proxies(proxy_settings)
        log.info("Proxy settings successfully updated: %r", proxy_settings)

    def refresh_proxies(self, proxy_settings=None, device_config=None):
        """Refresh current proxies with the given settings"""
        # If no proxy settings passed fetch them from database
        proxy_settings = (proxy_settings if proxy_settings is not None
                          else self.get_proxy_settings())
        self.proxies, self.proxy_exceptions = get_proxies_for_handler(
                                                            proxy_settings)
        self.proxyUpdated.emit(proxy_settings)

    def get_engine(self, local_folder):
        if self._engines is None:
            self.load()
        for engine_def in self._engine_definitions:
            if local_folder.startswith(engine_def.local_folder):
                return self._engines[engine_def.uid]
        return None

    def bind_server(self, local_folder, url, username, password, name=None, start_engine=True):
        from collections import namedtuple
        if name is None:
            import urlparse
            urlp = urlparse.urlparse(url)
            name = urlp.hostname
        binder = namedtuple('binder', ['username','password','url'])
        binder.username = username
        binder.password = password
        binder.url = url
        return self.bind_engine('NXDRIVE', local_folder, name, binder, starts=start_engine)

    def bind_engine(self, engine_type, local_folder, name, binder, starts=True):
        """Bind a local folder to a remote nuxeo server"""
        if not engine_type in self._engine_types:
            raise EngineTypeMissing()
        if self._engines is None:
            self.load()
        local_folder = normalized_path(local_folder)
        uid = uuid.uuid1().hex
        # TODO Check that engine is not inside another or same position
        engine_def = self._dao.add_engine(engine_type, local_folder, uid, name)
        try:
            self._engines[uid] = self._engine_types[engine_type](self, engine_def, binder=binder)
            self._engine_definitions.append(engine_def)
        except Exception as e:
            log.exception(e)
            self._dao.delete_engine(uid)
            # TODO Remove the db ?
            raise e
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
        return True

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
