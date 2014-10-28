"""Main API to perform Nuxeo Drive operations"""

import os
import sys
import urllib2
from threading import local
import subprocess
from datetime import datetime
from datetime import timedelta
import calendar

from cookielib import CookieJar

from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import asc
from sqlalchemy import desc
from sqlalchemy import or_

import nxdrive
from nxdrive.client import Unauthorized
from nxdrive.client import LocalClient
from nxdrive.client import RemoteFileSystemClient
from nxdrive.client import RemoteFilteredFileSystemClient
from nxdrive.client import RemoteDocumentClient
from nxdrive.client.common import LOCALLY_EDITED_FOLDER_NAME
from nxdrive.client.base_automation_client import get_proxies_for_handler
from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_PREFIX
from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_SUFFIX
from nxdrive.client import NotFound
from nxdrive.model import init_db
from nxdrive.model import DeviceConfig
from nxdrive.model import ServerBinding
from nxdrive.model import LastKnownState
from nxdrive.synchronizer import Synchronizer
from nxdrive.synchronizer import POSSIBLE_NETWORK_ERROR_TYPES
from nxdrive.logging_config import get_logger
from nxdrive.utils import ENCODING
from nxdrive.utils import deprecated
from nxdrive.utils import normalized_path
from nxdrive.utils import safe_long_path
from nxdrive.utils import encrypt
from nxdrive.utils import decrypt
from nxdrive.migration import migrate_db
from nxdrive.activity import FileAction
from nxdrive.utils import PidLockFile


log = get_logger(__name__)

NUXEO_DRIVE_FOLDER_NAME = 'Nuxeo Drive'
DEFAULT_NUMBER_RECENTLY_MODIFIED = 5
DRIVE_METADATA_VIEW = 'view_drive_metadata'


class MissingToken(Exception):
    pass


def default_nuxeo_drive_folder():
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
                                              NUXEO_DRIVE_FOLDER_NAME)
            log.info("Will use '%s' as default Nuxeo Drive folder location"
                     " under Windows", nuxeo_drive_folder)
            return nuxeo_drive_folder

    # Fall back on home folder otherwise
    user_home = os.path.expanduser('~')
    user_home = unicode(user_home.decode(ENCODING))
    nuxeo_drive_folder = os.path.join(user_home, NUXEO_DRIVE_FOLDER_NAME)
    log.info("Will use '%s' as default Nuxeo Drive folder location",
             nuxeo_drive_folder)
    return nuxeo_drive_folder


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

    def __init__(self, config='System', proxy_type=None,
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

    def __repr__(self):
        return ("ProxySettings<config=%s, proxy_type=%s, server=%s, port=%s, "
                "authenticated=%r, username=%s, exceptions=%s>") % (
                    self.config, self.proxy_type, self.server, self.port,
                    self.authenticated, self.username, self.exceptions)


class GeneralSettings(object):
    """Summarize general settings"""

    def __init__(self, auto_update=False):
        self.auto_update = auto_update

    def __repr__(self):
        return "GeneralSettings<auto_update=%r>" % self.auto_update


class Controller(object):
    """Manage configuration and perform Nuxeo Drive Operations

    This class is thread safe: instance can be shared by multiple threads
    as DB sessions and Nuxeo clients are thread locals.
    """

    # Used for binding server / roots and managing tokens
    remote_doc_client_factory = RemoteDocumentClient

    # Used for FS synchronization operations
    remote_fs_client_factory = RemoteFileSystemClient
    # Used for FS synchronization operations
    remote_filtered_fs_client_factory = RemoteFilteredFileSystemClient

    def __init__(self, config_folder, echo=False, echo_pool=False,
                 poolclass=None, handshake_timeout=60, timeout=20,
                 page_size=None, max_errors=3,
                 update_url=None):
        self.update_url = update_url
        # Log the installation location for debug
        nxdrive_install_folder = os.path.dirname(nxdrive.__file__)
        nxdrive_install_folder = os.path.realpath(nxdrive_install_folder)
        log.info("nxdrive installed in '%s'", nxdrive_install_folder)

        # Log the configuration location for debug
        config_folder = os.path.expanduser(config_folder)
        self.config_folder = os.path.realpath(config_folder)
        if not os.path.exists(self.config_folder):
            os.makedirs(self.config_folder)
        log.info("nxdrive configured in '%s'", self.config_folder)

        if not echo:
            echo = os.environ.get('NX_DRIVE_LOG_SQL', None) is not None
        self.handshake_timeout = handshake_timeout
        self.timeout = timeout
        self.max_errors = max_errors

        # Handle connection to the local Nuxeo Drive configuration and
        # metadata SQLite database.
        self._engine, self._session_maker = init_db(
            self.config_folder, echo=echo, echo_pool=echo_pool,
            poolclass=poolclass)

        # Migrate SQLite database if needed
        migrate_db(self._engine)

        # Thread-local storage for the remote client cache
        self._local = local()
        self._client_cache_timestamps = dict()

        self._remote_error = None
        self._local_error = None

        device_config = self.get_device_config()
        self.device_id = device_config.device_id
        self.version = nxdrive.__version__
        self.updated = self.update_version(device_config)

        # HTTP proxy settings
        self.proxies = None
        self.proxy_exceptions = None
        self.refresh_proxies(device_config=device_config)

        # Recently modified items for each server binding
        self.recently_modified = {}

        self.synchronizer = self.get_synchronizer(page_size)

        # Make all the automation client related to this controller
        # share cookies using threadsafe jar
        self.cookie_jar = CookieJar()

    def get_synchronizer(self, page_size):
        return Synchronizer(self, page_size=page_size)

    def use_watchdog(self):
        # TODO NXDRIVE-112: enable back when fixed!
        return False

    def trash_modified_file(self):
        return False

    def local_rollback(self):
        return False

    def get_session(self):
        """Reuse the thread local session for this controller

        Using the controller in several thread should be thread safe as long as
        this method is always called to fetch the session instance.
        """
        return self._session_maker()

    def get_device_config(self, session=None):
        """Fetch the singleton configuration object for this device"""
        if session is None:
            session = self.get_session()
        try:
            return session.query(DeviceConfig).one()
        except NoResultFound:
            device_config = DeviceConfig()  # generate a unique device id
            session.add(device_config)
            session.commit()
            return device_config

    def get_version(self):
        return self.version

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

    def is_updated(self):
        return self.updated

    def refresh_update_info(self, local_folder):
        session = self.get_session()
        sb = self.get_server_binding(local_folder, session=session)
        self._set_update_info(sb)
        session.commit()

    def _set_update_info(self, server_binding, remote_client=None):
        try:
            remote_client = (remote_client if remote_client is not None
                             else self.get_remote_doc_client(server_binding))
            update_info = remote_client.get_update_info()
            log.info("Fetched update info from server: %r", update_info)
            server_binding.server_version = update_info['serverVersion']
            server_binding.update_url = update_info['updateSiteURL']
        except Exception as e:
            log.warning("Cannot get update info from server because of: %s", e)

        # Fall back on default server version if needed
        if server_binding.server_version is None:
            server_binding.server_version = self.get_default_server_version()
            log.debug("Server version is null or not available, falling back"
                      " on default one: %s", server_binding.server_version)
        # Fall back on default update site URL if needed
        if server_binding.update_url is None:
            server_binding.update_url = self.get_default_update_site_url()
            log.debug("Update site URL is null or not available, falling back"
                      " on default one: %s", server_binding.update_url)

    @deprecated
    def get_default_server_version(self):
        return None

    def get_default_update_site_url(self):
        return self.update_url

    def get_proxy_settings(self, device_config=None):
        """Fetch proxy settings from database"""
        dc = (self.get_device_config() if device_config is None
              else device_config)
        # Decrypt password with token as the secret
        token = self.get_first_token()
        if dc.proxy_password is not None and token is not None:
            password = decrypt(dc.proxy_password, token)
        else:
            # If no server binding or no token available
            # (possibly after token revocation) reset password
            password = ''
        return ProxySettings(config=dc.proxy_config,
                                       proxy_type=dc.proxy_type,
                                       server=dc.proxy_server,
                                       port=dc.proxy_port,
                                       authenticated=dc.proxy_authenticated,
                                       username=dc.proxy_username,
                                       password=password,
                                       exceptions=dc.proxy_exceptions)

    def set_proxy_settings(self, proxy_settings):
        session = self.get_session()
        device_config = self.get_device_config(session)

        device_config.proxy_config = proxy_settings.config
        device_config.proxy_type = proxy_settings.proxy_type
        device_config.proxy_server = proxy_settings.server
        device_config.proxy_port = proxy_settings.port
        device_config.proxy_exceptions = proxy_settings.exceptions
        device_config.proxy_authenticated = proxy_settings.authenticated
        device_config.proxy_username = proxy_settings.username
        # Encrypt password with token as the secret
        token = self.get_first_token(session)
        if token is None:
            raise MissingToken("Your token has been revoked,"
                        " please update your password to acquire a new one.")
        password = encrypt(proxy_settings.password, token)
        device_config.proxy_password = password

        session.commit()
        log.info("Proxy settings successfully updated: %r", proxy_settings)
        self.invalidate_client_cache()

    def get_general_settings(self, device_config=None):
        """Fetch general settings from database"""
        dc = (self.get_device_config() if device_config is None
              else device_config)
        return GeneralSettings(auto_update=dc.auto_update)

    def set_general_settings(self, general_settings):
        session = self.get_session()
        device_config = self.get_device_config(session)
        device_config.auto_update = general_settings.auto_update
        session.commit()
        log.info("General settings successfully updated: %r", general_settings)

    def is_auto_update(self, device_config=None):
        return self.get_general_settings(
                        device_config=device_config).auto_update

    def set_auto_update(self, auto_update):
        session = self.get_session()
        device_config = self.get_device_config(session)
        device_config.auto_update = auto_update
        session.commit()
        log.info("Auto update setting successfully updated: %r", auto_update)

    def refresh_proxies(self, proxy_settings=None, device_config=None):
        """Refresh current proxies with the given settings"""
        # If no proxy settings passed fetch them from database
        proxy_settings = (proxy_settings if proxy_settings is not None
                          else self.get_proxy_settings(
                                                device_config=device_config))
        self.proxies, self.proxy_exceptions = get_proxies_for_handler(
                                                            proxy_settings)

    def get_server_binding(self, local_folder, raise_if_missing=False,
                           session=None):
        """Find the ServerBinding instance for a given local_folder"""
        local_folder = normalized_path(local_folder)
        if session is None:
            session = self.get_session()
        try:
            return session.query(ServerBinding).filter(
                ServerBinding.local_folder == local_folder).one()
        except NoResultFound:
            if raise_if_missing:
                raise RuntimeError(
                    "Folder '%s' is not bound to any Nuxeo server"
                    % local_folder)
            return None

    def list_server_bindings(self, session=None):
        if session is None:
            session = self.get_session()
        return session.query(ServerBinding).all()

    def get_first_token(self, session=None):
        """Get the token from the first server binding"""
        if session is None:
            session = self.get_session()
        server_bindings = self.list_server_bindings(session)
        if not server_bindings:
            return None
        sb = server_bindings[0]
        return sb.remote_token

    def get_server_binding_settings(self):
        """Fetch server binding settings from database"""
        server_bindings = self.list_server_bindings()
        if not server_bindings:
            return ServerBindingSettings(
                local_folder=default_nuxeo_drive_folder())
        else:
            # TODO: handle multiple server bindings, for now take the first one
            # See https://jira.nuxeo.com/browse/NXP-12716
            sb = server_bindings[0]
            return ServerBindingSettings(server_url=sb.server_url,
                            server_version=sb.server_version,
                            username=sb.remote_user,
                            local_folder=sb.local_folder,
                            initialized=True,
                            pwd_update_required=sb.has_invalid_credentials())

    def is_credentials_update_required(self):
        server_bindings = self.list_server_bindings()
        if not server_bindings:
            return True
        else:
            # TODO: handle multiple server bindings, for now consider that
            # credentials update is required if at least one binding has
            # invalid credentials
            # See https://jira.nuxeo.com/browse/NXP-12716
            for server_binding in server_bindings:
                if server_binding.has_invalid_credentials():
                    return True
            return  False

    def stop(self):
        """Stop the Nuxeo Drive synchronization thread

        As the process asking the synchronization to stop might not be the same
        as the process running the synchronization (especially when used from
        the commandline without the graphical user interface and its tray icon
        menu) we use a simple empty marker file a cross platform way to pass
        the stop message between the two.

        """
        pid_lock_file = PidLockFile(self.config_folder, "sync")
        pid = pid_lock_file.check_running(process_name="sync")
        if pid is not None:
            # Create a stop file marker for the running synchronization
            # process
            log.info("Telling synchronization process %d to stop." % pid)
            stop_file = os.path.join(self.config_folder, "stop_%d" % pid)
            open(safe_long_path(stop_file), 'wb').close()
        else:
            log.info("No running synchronization process to stop.")

    def children_states(self, folder_path):
        """List the status of the children of a folder

        The state of the folder is a summary of their descendant rather
        than their own instric synchronization step which is of little
        use for the end user.

        """
        session = self.get_session()
        # Find the server binding for this absolute path
        try:
            binding, path = self._binding_path(folder_path, session=session)
        except NotFound:
            return []

        try:
            folder_state = session.query(LastKnownState).filter_by(
                local_folder=binding.local_folder,
                local_path=path,
            ).one()
        except NoResultFound:
            return []

        states = self._pair_states_recursive(session, folder_state)

        return [(os.path.basename(s.local_path), pair_state)
                for s, pair_state in states
                if s.local_parent_path == path]

    def _pair_states_recursive(self, session, doc_pair):
        """Recursive call to collect pair state under a given location."""
        if not doc_pair.folderish:
            return [(doc_pair, doc_pair.pair_state)]

        if doc_pair.local_path is not None and doc_pair.remote_ref is not None:
            f = or_(
                LastKnownState.local_parent_path == doc_pair.local_path,
                LastKnownState.remote_parent_ref == doc_pair.remote_ref,
            )
        elif doc_pair.local_path is not None:
            f = LastKnownState.local_parent_path == doc_pair.local_path
        elif doc_pair.remote_ref is not None:
            f = LastKnownState.remote_parent_ref == doc_pair.remote_ref
        else:
            raise ValueError("Illegal state %r: at least path or remote_ref"
                             " should be not None." % doc_pair)

        children_states = session.query(LastKnownState).filter_by(
            local_folder=doc_pair.local_folder).filter(f).order_by(
                asc(LastKnownState.local_name),
                asc(LastKnownState.remote_name),
            ).all()

        results = []
        for child_state in children_states:
            sub_results = self._pair_states_recursive(session, child_state)
            results.extend(sub_results)

        # A folder stays synchronized (or unknown) only if all the descendants
        # are themselfves synchronized.
        pair_state = doc_pair.pair_state
        for _, sub_pair_state in results:
            if sub_pair_state != 'synchronized':
                pair_state = 'children_modified'
            break
        # Pre-pend the folder state to the descendants
        return [(doc_pair, pair_state)] + results

    def _binding_path(self, local_path, session=None):
        """Find a server binding and relative path for a given FS path"""
        local_path = normalized_path(local_path)

        # Check exact binding match
        binding = self.get_server_binding(local_path, session=session,
            raise_if_missing=False)
        if binding is not None:
            return binding, u'/'

        # Check for bindings that are prefix of local_path
        session = self.get_session()
        all_bindings = session.query(ServerBinding).all()
        matching_bindings = [sb for sb in all_bindings
                             if local_path.startswith(
                                sb.local_folder + os.path.sep)]
        if len(matching_bindings) == 0:
            raise NotFound("Could not find any server binding for "
                               + local_path)
        elif len(matching_bindings) > 1:
            raise RuntimeError("Found more than one binding for %s: %r" % (
                local_path, matching_bindings))
        binding = matching_bindings[0]
        path = local_path[len(binding.local_folder):]
        path = path.replace(os.path.sep, u'/')
        return binding, path

    def bind_server(self, local_folder, server_url, username, password):
        """Bind a local folder to a remote nuxeo server"""
        session = self.get_session()
        local_folder = normalized_path(local_folder)

        # check the connection to the server by issuing an authentication
        # request
        server_url = self._normalize_url(server_url)
        nxclient = self.remote_doc_client_factory(
            server_url, username, self.device_id, self.version,
            proxies=self.proxies, proxy_exceptions=self.proxy_exceptions,
            password=password, timeout=self.handshake_timeout)
        token = nxclient.request_token()
        if token is not None:
            # The server supports token based identification: do not store the
            # password in the DB
            password = None
        try:
            try:
                # Look for an existing server binding for the given local
                # folder
                server_binding = session.query(ServerBinding).filter(
                    ServerBinding.local_folder == local_folder).one()
                if server_binding.server_url != server_url:
                    raise RuntimeError(
                        "%s is already bound to '%s'" % (
                            local_folder, server_binding.server_url))

                if server_binding.remote_user != username:
                    # Update username info if required
                    server_binding.remote_user = username
                    log.info("Updating username to '%s' on server '%s'",
                            username, server_url)

                if (token is None
                    and server_binding.remote_password != password):
                    # Update password info if required
                    server_binding.remote_password = password
                    log.info("Updating password for user '%s' on server '%s'",
                            username, server_url)

                if token is not None and server_binding.remote_token != token:
                    log.info("Updating token for user '%s' on server '%s'",
                            username, server_url)
                    # Update the token info if required
                    server_binding.remote_token = token

                    # Ensure that the password is not stored in the DB
                    if server_binding.remote_password is not None:
                        server_binding.remote_password = None

                # If the top level state for the server binding doesn't exist,
                # create the local folder and the top level state. This can be
                # the case when initializing the DB manually with a SQL script.
                try:
                    session.query(LastKnownState).filter_by(local_path='/',
                                            local_folder=local_folder).one()
                except NoResultFound:
                    self._make_local_folder(local_folder)
                    self._add_top_level_state(server_binding, session)

            except NoResultFound:
                # No server binding found for the given local folder
                # First create local folder in the file system
                self._make_local_folder(local_folder)

                # Create ServerBinding instance in DB
                log.info("Binding '%s' to '%s' with account '%s'",
                         local_folder, server_url, username)
                server_binding = ServerBinding(local_folder, server_url,
                                               username,
                                               remote_password=password,
                                               remote_token=token)
                session.add(server_binding)

                # Create the top level state for the server binding
                self._add_top_level_state(server_binding, session)

            # Set update info
            self._set_update_info(server_binding, remote_client=nxclient)

        except:
            # In case an AddonNotInstalled exception is raised, need to
            # invalidate the remote client cache for it to be aware of the new
            # operations when the addon gets installed
            if server_binding is not None:
                self.invalidate_client_cache(server_binding.server_url)
            session.rollback()
            raise

        session.commit()
        return server_binding

    def _add_top_level_state(self, server_binding, session):
        local_client = self.get_local_client(server_binding.local_folder)
        local_info = local_client.get_info(u'/')

        remote_client = self.get_remote_fs_client(server_binding)
        remote_info = remote_client.get_filesystem_root_info()

        state = LastKnownState(server_binding.local_folder,
                               local_info=local_info,
                               remote_info=remote_info)
        # The root should also be sync
        state.update_state('synchronized', 'synchronized')
        session.add(state)

    def _make_local_folder(self, local_folder):
        if not os.path.exists(local_folder):
            os.makedirs(local_folder)
            self.register_folder_link(local_folder)
        # Put the ROOT in readonly
        from nxdrive.client.common import BaseClient
        BaseClient.set_path_readonly(local_folder)

    def unbind_server(self, local_folder):
        """Remove the binding to a Nuxeo server

        Local files are not deleted"""
        session = self.get_session()
        local_folder = normalized_path(local_folder)
        binding = self.get_server_binding(local_folder, raise_if_missing=True,
                                          session=session)

        # Revoke token if necessary
        if binding.remote_token is not None:
            try:
                nxclient = self.remote_doc_client_factory(
                        binding.server_url,
                        binding.remote_user,
                        self.device_id,
                        self.version,
                        proxies=self.proxies,
                        proxy_exceptions=self.proxy_exceptions,
                        token=binding.remote_token,
                        timeout=self.timeout)
                log.info("Revoking token for '%s' with account '%s'",
                         binding.server_url, binding.remote_user)
                nxclient.revoke_token()
            except POSSIBLE_NETWORK_ERROR_TYPES:
                log.warning("Could not connect to server '%s' to revoke token",
                            binding.server_url)
            except Unauthorized:
                # Token is already revoked
                pass

        # Invalidate client cache
        self.invalidate_client_cache(binding.server_url)

        # Delete binding info in local DB
        log.info("Unbinding '%s' from '%s' with account '%s'",
                 local_folder, binding.server_url, binding.remote_user)
        session.delete(binding)
        session.commit()

    def unbind_all(self):
        """Unbind all server and revoke all tokens

        This is useful for cleanup in integration test code.
        """
        session = self.get_session()
        for sb in session.query(ServerBinding).all():
            self.unbind_server(sb.local_folder)

    def bind_root(self, local_folder, remote_ref, repository='default',
                  session=None):
        """Bind local root to a remote root (folderish document in Nuxeo).

        local_folder must be already bound to an existing Nuxeo server.

        remote_ref must be the IdRef or PathRef of an existing folderish
        document on the remote server bound to the local folder.

        """
        session = self.get_session() if session is None else session
        local_folder = normalized_path(local_folder)
        server_binding = self.get_server_binding(
            local_folder, raise_if_missing=True, session=session)

        nxclient = self.get_remote_doc_client(server_binding,
                                              repository=repository)

        # Register the root on the server
        nxclient.register_as_root(remote_ref)

    def unbind_root(self, local_folder, remote_ref, repository='default',
                    session=None):
        """Remove binding to remote folder"""
        session = self.get_session() if session is None else session
        server_binding = self.get_server_binding(
            local_folder, raise_if_missing=True, session=session)

        nxclient = self.get_remote_doc_client(server_binding,
                                              repository=repository)

        # Unregister the root on the server
        nxclient.unregister_as_root(remote_ref)

    def get_max_errors(self):
        return self.max_errors

    def list_on_errors(self, limit=100, session=None):
        if session is None:
            session = self.get_session()

        # Only consider pair states that are not synchronized
        # and ignore unsynchronized ones
        predicates = [LastKnownState.pair_state != 'synchronized',
                      LastKnownState.pair_state != 'unsynchronized']
        # Don't try to sync file that have too many error
        predicates.append(LastKnownState.error_count >= self.get_max_errors())
        return session.query(LastKnownState).filter(
            *predicates
        ).order_by(
            # Ensure that newly created remote folders will be synchronized
            # before their children while keeping a fixed named based
            # deterministic ordering to make the tests readable
            asc(LastKnownState.remote_parent_path),
            asc(LastKnownState.remote_name),
            asc(LastKnownState.remote_ref),

            # Ensure that newly created local folders will be synchronized
            # before their children
            asc(LastKnownState.local_path)
        ).limit(limit).all()

    def list_pending(self, limit=100, local_folder=None, ignore_in_error=None,
                     session=None):
        """List pending files to synchronize, ordered by path

        Ordering by path makes it possible to synchronize sub folders content
        only once the parent folders have already been synchronized.

        If ingore_in_error is not None and is a duration in second, skip pair
        states that have recently triggered a synchronization error.
        """
        if session is None:
            session = self.get_session()

        # Only consider pair states that are not synchronized
        # and ignore unsynchronized ones
        predicates = [LastKnownState.pair_state != 'synchronized',
                      LastKnownState.pair_state != 'unsynchronized']
        # Don't try to sync file that have too many error
        predicates.append(LastKnownState.error_count < self.get_max_errors())
        if local_folder is not None:
            predicates.append(LastKnownState.local_folder == local_folder)

        if ignore_in_error is not None and ignore_in_error > 0:
            max_date = datetime.utcnow() - timedelta(seconds=ignore_in_error)
            predicates.append(or_(
                LastKnownState.last_sync_error_date == None,
                LastKnownState.last_sync_error_date < max_date))

        return session.query(LastKnownState).filter(
            *predicates
        ).order_by(
            # Ensure that newly created remote folders will be synchronized
            # before their children while keeping a fixed named based
            # deterministic ordering to make the tests readable
            asc(LastKnownState.remote_parent_path),
            asc(LastKnownState.remote_name),
            asc(LastKnownState.remote_ref),

            # Ensure that newly created local folders will be synchronized
            # before their children
            asc(LastKnownState.local_path)
        ).limit(limit).all()

    def next_pending(self, local_folder=None, session=None):
        """Return the next pending file to synchronize or None"""
        pending = self.list_pending(limit=1, local_folder=local_folder,
                                    session=session)
        return pending[0] if len(pending) > 0 else None

    def init_recently_modified(self):
        server_bindings = self.list_server_bindings()
        if server_bindings:
            for sb in server_bindings:
                self.recently_modified[sb.local_folder] = (
                                self.list_recently_modified(sb.local_folder))
                log.info("Initialized list of recently modified items"
                         " in %s: %r", sb.local_folder,
                         [item.local_name for item
                          in self.get_recently_modified(sb.local_folder)])

    def get_recently_modified(self, local_folder):
        return self.recently_modified[local_folder]

    def get_metadata_view_url(self, file_path):
        local_path = None
        sb = None
        session = self.get_session()
        server_bindings = self.list_server_bindings(session)
        for sb_ in server_bindings:
            if file_path.startswith(sb_.local_folder):
                sb = sb_
                local_path = file_path.split(sb_.local_folder, 1)[1]
        if sb is None:
            log.error('Could not find server binding for file %s', file_path)
            return

        metadata_url = sb.server_url
        try:
            # Replace os path for windows
            local_path = local_path.replace(os.path.sep, "/")
            predicates = [LastKnownState.local_folder == sb.local_folder,
                          LastKnownState.local_path == local_path]
            doc_pair = session.query(LastKnownState).filter(*predicates).one()
            if (doc_pair.remote_ref is not None):
                remote_ref_segments = doc_pair.remote_ref.split("#", 2)
                repo = remote_ref_segments[1]
                doc_id = remote_ref_segments[2]
                metadata_url += ("nxdoc/" + repo + "/" + doc_id +
                                 "/" + DRIVE_METADATA_VIEW)
                return metadata_url, sb.remote_token
        except NoResultFound:
            raise ValueError('Could not find file %s in Nuxeo Drive database' %
                             file_path)

    def update_recently_modified(self, doc_pair):
        local_folder = doc_pair.local_folder
        self.recently_modified[local_folder] = self.list_recently_modified(
                                                                local_folder)
        log.trace("Updated list of recently modified items in %s: %r",
                 local_folder, [item.local_name for item
                                in self.get_recently_modified(local_folder)])

    def list_recently_modified(self, local_folder):
        """List recently modified pairs ordered by last local modification.
        """
        session = self.get_session()

        predicates = [LastKnownState.local_folder == local_folder]
        # Only consider pair states that are synchronized
        predicates.append(LastKnownState.pair_state == 'synchronized')
        # Don't consider folders
        predicates.append(LastKnownState.folderish == False)

        items = session.query(LastKnownState).filter(
            *predicates
        ).order_by(
            desc(LastKnownState.last_sync_date),
        ).options().limit(self.get_number_recently_modified()).all()
        # Remove objects from session
        result = []
        for item in items:
            session.expunge(item)
            result.append(item)
        return result

    def get_number_recently_modified(self):
        return DEFAULT_NUMBER_RECENTLY_MODIFIED

    def _get_client_cache(self):
        if not hasattr(self._local, 'remote_clients'):
            self._local.remote_clients = dict()
        return self._local.remote_clients

    def get_remote_fs_client(self, server_binding, filtered=True):
        """Return a client for the FileSystem abstraction."""
        cache = self._get_client_cache()
        sb = server_binding
        cache_key = (sb.server_url, sb.remote_user, self.device_id, filtered)
        remote_client_cache = cache.get(cache_key)
        if remote_client_cache is not None:
            remote_client = remote_client_cache[0]
            timestamp = remote_client_cache[1]
        client_cache_timestamp = self._client_cache_timestamps.get(cache_key)

        if remote_client_cache is None or timestamp < client_cache_timestamp:
            if filtered:
                remote_client = self.remote_filtered_fs_client_factory(
                        sb.server_url, sb.remote_user, self.device_id,
                        self.version, self.get_session(),
                        proxies=self.proxies,
                        proxy_exceptions=self.proxy_exceptions,
                        password=sb.remote_password, token=sb.remote_token,
                        timeout=self.timeout, cookie_jar=self.cookie_jar,
                        check_suspended=self.synchronizer.check_suspended)
            else:
                remote_client = self.remote_fs_client_factory(
                        sb.server_url, sb.remote_user, self.device_id,
                        self.version,
                        proxies=self.proxies,
                        proxy_exceptions=self.proxy_exceptions,
                        password=sb.remote_password, token=sb.remote_token,
                        timeout=self.timeout, cookie_jar=self.cookie_jar,
                        check_suspended=self.synchronizer.check_suspended)
            if client_cache_timestamp is None:
                client_cache_timestamp = 0
                self._client_cache_timestamps[cache_key] = 0
            cache[cache_key] = remote_client, client_cache_timestamp
        # Make it possible to have the remote client simulate any kind of
        # network or server failure: this is useful for example to ensure that
        # cookies used for load balancer affinity (e.g. AWSELB) are shared by
        # all the Automation clients managed by a given controller.
        remote_client.make_remote_raise(self._remote_error)
        # Make it possible to have the remote client simulate any kind of
        # local device failure: this is useful for example to test a "No space
        # left on device" issue when downloading a file.
        remote_client.make_local_raise(self._local_error)
        return remote_client

    def get_remote_doc_client(self, server_binding, repository='default',
                              base_folder=None):
        """Return an instance of Nuxeo Document Client"""
        sb = server_binding
        return self.remote_doc_client_factory(
            sb.server_url, sb.remote_user, self.device_id, self.version,
            proxies=self.proxies, proxy_exceptions=self.proxy_exceptions,
            password=sb.remote_password, token=sb.remote_token,
            repository=repository, base_folder=base_folder,
            timeout=self.timeout, cookie_jar=self.cookie_jar)

    def get_local_client(self, local_folder):
        """Return a file system client for the given local folder"""
        return LocalClient(local_folder)

    def invalidate_client_cache(self, server_url=None):
        for key in self._client_cache_timestamps:
            if server_url is None or key[0] == server_url:
                now = datetime.utcnow().utctimetuple()
                self._client_cache_timestamps[key] = calendar.timegm(now)
        # Re-fetch HTTP proxy settings
        self.refresh_proxies()

    def get_state(self, server_url, remote_ref):
        """Find a pair state for the provided remote document identifiers."""
        server_url = self._normalize_url(server_url)
        session = self.get_session()
        states = session.query(LastKnownState).filter_by(
            remote_ref=remote_ref,
        ).all()
        for state in states:
            if (state.server_binding.server_url == server_url):
                return state

    def get_state_for_local_path(self, local_os_path):
        """Find a DB state from a local filesystem path"""
        session = self.get_session()
        sb, local_path = self._binding_path(local_os_path, session=session)
        return session.query(LastKnownState).filter_by(
            local_folder=sb.local_folder, local_path=local_path).one()

    def edit(self, server_url, remote_ref):
        """Find the local file if any and start OS editor on it."""

        state = self.get_state(server_url, remote_ref)
        if state is None:
            log.warning('Could not find local file for server_url=%s '
                        'and remote_ref=%s', server_url, remote_ref)
            return

        # TODO: check synchronization of this state first

        # Find the best editor for the file according to the OS configuration
        self.open_local_file(state.get_local_abspath())

    def download_edit(self, server_url, repo, doc_id, filename):
        """Locally edit document with the given id."""

        # Find server binding from server URL
        sb = None
        server_url = self._normalize_url(server_url)
        session = self.get_session()
        server_bindings = self.list_server_bindings(session)
        for sb_ in server_bindings:
            if (sb_.server_url == server_url):
                sb = sb_

        if sb is None:
            log.warning('Could not find server binding for server_url=%s ',
                        server_url)
            return

        # Check for a possibly existing doc pair, in which case edit it only
        doc_pair = session.query(LastKnownState).filter(
            LastKnownState.local_folder == sb.local_folder,
            LastKnownState.local_parent_path.endswith(
                                                LOCALLY_EDITED_FOLDER_NAME),
            LastKnownState.remote_ref.endswith('#%s#%s' % (repo, doc_id))
        ).first()
        if doc_pair is not None:
            self.open_local_file(doc_pair.get_local_abspath())
            return

        # Create "Locally Edited" folder if not exists
        local_client = LocalClient(sb.local_folder)
        locally_edited_path = '/' + LOCALLY_EDITED_FOLDER_NAME
        locally_edited = local_client.get_info(locally_edited_path,
                                               raise_if_missing=False)
        if locally_edited is None:
            locally_edited_path = local_client.make_folder('/',
                                                    LOCALLY_EDITED_FOLDER_NAME)

        # Download file to edit locally in "Locally Edited" folder
        doc_client = self.get_remote_doc_client(sb, repository=repo)
        doc_url = (server_url + 'nxbigfile/' + repo + '/' + doc_id + '/'
                   + 'blobholder:0/' + filename)
        unquoted_filename = urllib2.unquote(filename)
        decoded_filename = unquoted_filename.decode('utf-8')
        _, os_path, name = local_client.get_new_file(locally_edited_path,
                                                     decoded_filename)
        file_dir = os.path.dirname(os_path)
        file_out = os.path.join(file_dir, DOWNLOAD_TMP_FILE_PREFIX + name
                                + DOWNLOAD_TMP_FILE_SUFFIX)
        log.debug("Downloading file '%s' in '%s' with URL '%s'", name,
                  file_dir, doc_url)
        doc_client.current_action = FileAction("Download", file_out, name, 0)
        _, tmp_file = doc_client.do_get(doc_url, file_out=file_out)
        local_client.rename(local_client.get_path(tmp_file), name)

        # Find the best editor for the file according to the OS configuration
        self.open_local_file(os_path)

        # Add document to "Locally Edited" collection
        doc_client.add_to_locally_edited_collection(doc_id)

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

    def make_remote_raise(self, error):
        """Helper method to simulate network failure for testing"""
        self._remote_error = error

    def make_local_raise(self, error):
        """Helper method to simulate local device failure for testing"""
        self._local_error = error

    def dispose(self):
        """Release database resources.

        Close thread-local Session, ending any transaction in progress and
        releasing underlying connections from the pool.

        Note that releasing all connections from the pool using
        Session.close_all() or SingletonThreadPool.dispose() is not an option
        here as the Python SQLite driver pysqlite used by SQLAlchemy doesn't
        let you close a connection from a thread that didn't create it (except
        under Windows, see below).
        In our case at least two threads are involved, the GUI and the
        synchronization one, so each one needs to close its own Session by
        calling this function.

        Beware that starting more threads than the pool size (default  is 5)
        might lead to a ProgrammingError when SingletonThreadPool._cleanup()
        gets called, for the reason just mentioned.

        Also note that calling Session.close() never seems to remove the
        connection object from the pool, even if the thread owning it is dead.

        Under Windows we need to release all connections from the pool
        calling SingletonThreadPool.dispose(), which strangely doesn't raise a
        ProgrammingError - probably due to a different implementation of the
        pysqlite driver -, otherwise we might get a WindowsError at tear down
        in tests using multiple threads when trying to remove the temporary
        test folder because of it being used by another Python process than the
        main one...
        """
        session = self.get_session()
        log.debug("Closing thread-local Session %r, ending any transaction"
                  " in progress and releasing underlying connections from"
                  " the pool", session)
        session.close()
        if sys.platform == 'win32':
            log.debug("As we are under Windows, dispose connection pool to"
                      " make sure all connections are closed, avoiding any"
                      " WindowsError due to a Python process using the"
                      " database file")
            self._engine.pool.dispose()

    def _normalize_url(self, url):
        """Ensure that user provided url always has a trailing '/'"""
        if url is None or not url:
            raise ValueError("Invalid url: %r" % url)
        if not url.endswith(u'/'):
            return url + u'/'
        return url

    def register_folder_link(self, folder_path):
        if sys.platform == 'darwin':
            self.register_folder_link_darwin(folder_path)
        # TODO: implement Windows and Linux support here

    def register_folder_link_darwin(self, folder_path):
        try:
            from LaunchServices import LSSharedFileListCreate
            from LaunchServices import kLSSharedFileListFavoriteItems
            from LaunchServices import LSSharedFileListInsertItemURL
            from LaunchServices import kLSSharedFileListItemBeforeFirst
            from LaunchServices import CFURLCreateWithString
        except ImportError:
            log.warning("PyObjC package is not installed:"
                        " skipping favorite link creation")
            return
        folder_path = normalized_path(folder_path)
        folder_name = os.path.basename(folder_path)

        lst = LSSharedFileListCreate(None, kLSSharedFileListFavoriteItems,
                                     None)
        if lst is None:
            log.warning("Could not fetch the Finder favorite list.")
            return

        url = CFURLCreateWithString(None, "file://"
                                    + urllib2.quote(folder_path), None)
        if url is None:
            log.warning("Could not generate valid favorite URL for: %s",
                folder_path)
            return

        # Register the folder as favorite if not already there
        item = LSSharedFileListInsertItemURL(
            lst, kLSSharedFileListItemBeforeFirst, folder_name, None, url,
            {}, [])
        if item is not None:
            log.debug("Registered new favorite in Finder for: %s", folder_path)
