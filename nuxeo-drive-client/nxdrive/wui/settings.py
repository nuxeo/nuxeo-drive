# coding: utf-8
import urllib2
import urlparse
from collections import namedtuple
from urllib import urlencode

from PyQt4 import QtCore, QtGui

from nxdrive.client.base_automation_client import AddonNotInstalled, \
    Unauthorized, get_opener_proxies, get_proxy_handler
from nxdrive.client.common import DRIVE_STARTUP_PAGE, NotFound
from nxdrive.engine.engine import InvalidDriveException, \
    RootAlreadyBindWithDifferentAccount
from nxdrive.logging_config import get_logger
from nxdrive.manager import FolderAlreadyUsed, ProxySettings
from nxdrive.utils import TOKEN_PERMISSION, get_device, guess_server_url
from nxdrive.wui.authentication import WebAuthenticationApi, \
    WebAuthenticationDialog
from nxdrive.wui.dialog import Promise, WebDialog, WebDriveApi
from nxdrive.wui.translator import Translator

log = get_logger(__name__)

STARTUP_PAGE_CONNECTION_TIMEOUT = 30


class StartupPageConnectionError(Exception):
    pass


class WebSettingsApi(WebDriveApi):

    openAuthenticationDialog = QtCore.pyqtSignal(str, object)

    def __init__(self, application, dlg=None):
        super(WebSettingsApi, self).__init__(application, dlg)
        # Attributes for the web authentication feedback
        self.openAuthenticationDialog.connect(self._open_authentication_dialog)
        self._new_local_folder = ''
        self._account_creation_error = ''
        self._token_update_error = ''
        self.__unbinding = False

    @QtCore.pyqtSlot(result=str)
    def get_default_section(self):
        try:
            return self.dialog._section
        except AttributeError:
            log.exception('Section not reachable')
            return ''

    @QtCore.pyqtSlot(result=str)
    def get_default_nuxeo_drive_folder(self):
        return self._manager.get_default_nuxeo_drive_folder()

    @QtCore.pyqtSlot(str, result=QtCore.QObject)
    def unbind_server_async(self, uid):
        if not self.__unbinding:
            return Promise(self.unbind_server, uid)

    @QtCore.pyqtSlot(str, result=str)
    def unbind_server(self, uid):
        self.__unbinding = True
        try:
            self._manager.unbind_engine(str(uid))
        finally:
            self.__unbinding = False
        return ''

    @QtCore.pyqtSlot(str)
    def filters_dialog(self, uid):
        engine = self._get_engine(str(uid))
        if engine:
            self.application.show_filters(engine)

    def _bind_server(self, local_folder, url, username, password, name, **kwargs):
        # Remove any parameters from the original URL
        parts = urlparse.urlsplit(url)
        url = urlparse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, '', parts.fragment))

        # On first time login convert QString(having special characters) to str
        if isinstance(local_folder, QtCore.QString):
            local_folder = str(local_folder.toUtf8()).decode('utf-8')
        if username and isinstance(username, QtCore.QString):
            username = unicode(username).encode('utf-8')
        if password and isinstance(password, QtCore.QString):
            password = unicode(password).encode('utf-8')
        if name == '':
            name = None
        elif name and isinstance(name, QtCore.QString):
            name = unicode(name).encode('utf-8')
        binder = namedtuple('binder', ['username', 'password', 'token', 'url',
                                       'no_check', 'no_fscheck'])
        binder.username = username
        binder.password = password
        binder.token = kwargs.get('token')
        binder.no_check = False
        binder.no_fscheck = not kwargs.get('check_fs', True)
        binder.url = url
        log.debug("Binder is : %s/%s", binder.url, binder.username)
        self._manager.bind_engine(
            self._manager._get_default_server_type(), local_folder, name,
            binder, starts=kwargs.get('start_engine', True))
        return ''

    @QtCore.pyqtSlot(str, str, str, str, str, result=QtCore.QObject)
    def bind_server_async(self, *args, **kwargs):
        # Check bind_server signature for arguments.
        return Promise(self.bind_server, *args, **kwargs)

    @QtCore.pyqtSlot(str, str, str, str, str, result=str)
    def bind_server(self, local_folder, url, username, password, name, **kwargs):
        url = guess_server_url(unicode(url))
        if not url:
            return 'CONNECTION_ERROR'

        try:
            return self._bind_server(local_folder, url, username, password, name, **kwargs)
        except RootAlreadyBindWithDifferentAccount as e:
            # Ask for the user
            values = {'username': e.username, 'url': e.url}
            msgbox = QtGui.QMessageBox(
                QtGui.QMessageBox.Question, self._manager.app_name,
                Translator.get('ROOT_USED_WITH_OTHER_BINDING', values),
                QtGui.QMessageBox.NoButton, self.dialog)
            msgbox.addButton(Translator.get('ROOT_USED_CONTINUE'),
                             QtGui.QMessageBox.AcceptRole)
            cancel = msgbox.addButton(Translator.get('ROOT_USED_CANCEL'),
                                      QtGui.QMessageBox.RejectRole)
            msgbox.exec_()
            if msgbox.clickedButton() == cancel:
                return 'FOLDER_USED'

            kwargs['check_fs'] = False
            return self.bind_server(
                local_folder, url, username, password, name, **kwargs)
        except NotFound:
            return 'FOLDER_DOES_NOT_EXISTS'
        except AddonNotInstalled:
            return 'ADDON_NOT_INSTALLED'
        except InvalidDriveException:
            return 'INVALID_PARTITION'
        except Unauthorized:
            return 'UNAUTHORIZED'
        except FolderAlreadyUsed:
            return 'FOLDER_USED'
        except urllib2.HTTPError:
            return 'CONNECTION_ERROR'
        except urllib2.URLError as e:
            if e.errno == 61:
                return 'CONNECTION_REFUSED'
            return 'CONNECTION_ERROR'
        except:
            log.exception('Unexpected error')
            # Map error here
            return 'CONNECTION_UNKNOWN'

    @QtCore.pyqtSlot(str, str, str, result=QtCore.QObject)
    def web_authentication_async(self, *args):
        # Check web_authentication signature for arguments.
        return Promise(self.web_authentication, *args)

    @QtCore.pyqtSlot(str, str, str, result=str)
    def web_authentication(self, local_folder, server_url, engine_name):
        # Handle the server URL
        url = guess_server_url(unicode(server_url))
        if not url:
            return 'CONNECTION_ERROR'

        parts = urlparse.urlsplit(url)
        server_url = urlparse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, parts.query, parts.fragment))

        # Handle the engine
        engine_type = parts.fragment or self._manager._get_default_server_type()

        try:
            # Handle local folder
            local_folder = str(local_folder.toUtf8()).decode('utf-8')
            self._check_local_folder(local_folder)

            # Connect to startup page
            status = self._connect_startup_page(server_url)
            # Server will send a 401 in case of anonymous user configuration
            # Should maybe only check for 404
            if status < 400 or status in (401, 500, 503):
                # Page exists, let's open authentication dialog
                engine_name = unicode(engine_name)
                if engine_name == '':
                    engine_name = None
                callback_params = {
                    'local_folder': local_folder,
                    'server_url': server_url,
                    'engine_name': engine_name,
                    'engine_type': engine_type
                }
                url = self._get_authentication_url(server_url)
                log.debug('Web authentication is available on server %s, '
                          'opening login window with URL %s', server_url, url)
                self.openAuthenticationDialog.emit(url, callback_params)
                return 'true'
            else:
                # Startup page is not available
                log.debug('Web authentication not available on server %s, '
                          'falling back on basic authentication', server_url)
                return 'false'
        except FolderAlreadyUsed:
            return 'FOLDER_USED'
        except StartupPageConnectionError:
            return 'CONNECTION_ERROR'
        except:
            log.exception('Unexpected error while trying to open'
                          ' web authentication window')
            return 'CONNECTION_UNKNOWN'

    def _check_local_folder(self, local_folder):
        if not self._manager.check_local_folder_available(local_folder):
            raise FolderAlreadyUsed()

    def _connect_startup_page(self, server_url):
        # Take into account URL parameters
        parts = urlparse.urlsplit(guess_server_url(server_url))
        url = urlparse.urlunsplit((parts.scheme,
                                   parts.netloc,
                                   parts.path + '/' + DRIVE_STARTUP_PAGE,
                                   parts.query,
                                   parts.fragment))

        # Remove any parameters from the original URL
        server_url = urlparse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, '', parts.fragment))

        try:
            proxy_handler = get_proxy_handler(
                self._manager.get_proxies(server_url))
            opener = urllib2.build_opener(proxy_handler)
            log.debug('Proxy configuration for startup page connection: %s,'
                      ' effective proxy list: %r',
                      self._manager.get_proxy_settings().config,
                      get_opener_proxies(opener))
            headers = {
                'X-Application-Name': self._manager.app_name,
                'X-Device-Id': self._manager.get_device_id(),
                'X-Client-Version': self._manager.get_version(),
                'User-Agent': (self._manager.app_name
                               + '/' + self._manager.get_version()),
            }
            req = urllib2.Request(url, headers=headers)
            response = opener.open(req, timeout=STARTUP_PAGE_CONNECTION_TIMEOUT)
            status = response.getcode()
        except urllib2.HTTPError as e:
            status = e.code
        except:
            log.exception('Error while trying to connect to Nuxeo Drive'
                          ' startup page with URL %s', url)
            raise StartupPageConnectionError()
        log.debug('Status code for %s = %d', url, status)
        return status

    def update_token(self, engine, token):
        engine.update_token(token)
        self.application.set_icon_state('asleep')

    @QtCore.pyqtSlot(str, result=str)
    def web_update_token(self, uid):
        try:
            engine = self._get_engine(str(uid))
            if engine is None:
                return 'CONNECTION_UNKNOWN'
            params = urlencode({'updateToken': True})
            url = self._get_authentication_url(engine.server_url) + '&' + params
            callback_params = {
                'engine': engine,
            }
            log.debug('Opening login window for token update with URL %s', url)
            self._open_authentication_dialog(url, callback_params)
            return ''
        except:
            log.exception('Unexpected error while trying to open web'
                          ' authentication window for token update')
            return 'CONNECTION_UNKNOWN'

    @QtCore.pyqtSlot(str, object)
    def _open_authentication_dialog(self, url, callback_params):
        api = WebAuthenticationApi(self, callback_params)
        dialog = WebAuthenticationDialog(QtCore.QCoreApplication.instance(),
                                         str(url), api)
        dialog.setWindowModality(QtCore.Qt.NonModal)
        dialog.show()

    def _get_authentication_url(self, server_url):
        token_params = {
            'deviceId': self._manager.get_device_id(),
            'applicationName': self._manager.app_name,
            'permission': TOKEN_PERMISSION,
            'deviceDescription': get_device(),
            'forceAnonymousLogin': 'true',
        }

        # Handle URL parameters
        parts = urlparse.urlsplit(guess_server_url(server_url))
        path = (parts.path + '/' + DRIVE_STARTUP_PAGE).replace('//', '/')
        params = (parts.query + '&' + urlencode(token_params)
                  if parts.query
                  else urlencode(token_params))
        url = urlparse.urlunsplit(
            (parts.scheme, parts.netloc, path, params, parts.fragment))

        return url

    @QtCore.pyqtSlot(result=str)
    def get_new_local_folder(self):
        return self._new_local_folder

    @QtCore.pyqtSlot(str)
    def set_new_local_folder(self, local_folder):
        self._new_local_folder = str(local_folder)

    @QtCore.pyqtSlot(result=str)
    def get_account_creation_error(self):
        return self._account_creation_error

    @QtCore.pyqtSlot(str)
    def set_account_creation_error(self, error):
        self._account_creation_error = str(error)

    @QtCore.pyqtSlot(result=str)
    def get_token_update_error(self):
        return self._token_update_error

    @QtCore.pyqtSlot(str)
    def set_token_update_error(self, error):
        self._token_update_error = str(error)

    @QtCore.pyqtSlot(result=str)
    def get_proxy_settings(self):
        settings = self._manager.get_proxy_settings()
        result = {
            'url': settings.to_url(with_credentials=False),
            'config': settings.config,
            'type': settings.proxy_type,
            'server': settings.server,
            'username': settings.username,
            'authenticated': settings.authenticated == 1,
            'password': settings.password,
            'port': settings.port,
            'pac_url': settings.pac_url,
            }
        return self._json(result)

    @QtCore.pyqtSlot(str, str, bool, str, str, str, result=QtCore.QObject)
    def set_proxy_settings_async(self, *args):
        # Check set_proxy_settings signature for arguments.
        return Promise(self.set_proxy_settings, *args)

    @QtCore.pyqtSlot(str, str, bool, str, str, str, result=str)
    def set_proxy_settings(self, config, server, authenticated, username, password, pac_url):
        config = str(config) or 'System'
        url = str(server)
        settings = ProxySettings(config=config)
        if config == 'Manual':
            settings.from_url(url)
        elif config == 'Automatic':
            settings.pac_url = str(pac_url)
        settings.authenticated = authenticated
        settings.username = str(username)
        settings.password = str(password)
        return self._manager.set_proxy_settings(settings)


class WebSettingsDialog(WebDialog):
    def __init__(self, application, section, api=None):
        self._section = section
        if not api:
            api = WebSettingsApi(application)

        super(WebSettingsDialog, self).__init__(
            application, 'settings.html', api=api,
            title=Translator.get('SETTINGS_WINDOW_TITLE'))

    def set_section(self, section):
        self._section = section
        self.view.reload()
