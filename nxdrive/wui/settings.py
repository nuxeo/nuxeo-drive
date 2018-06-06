# coding: utf-8
from collections import namedtuple
from logging import getLogger
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests
from PyQt5 import QtGui
from PyQt5.QtCore import QCoreApplication, QObject, Qt, pyqtSignal, pyqtSlot
from nuxeo.exceptions import HTTPError, Unauthorized
from requests import ConnectionError

from .authentication import WebAuthenticationApi, WebAuthenticationDialog
from .dialog import Promise, WebDialog, WebDriveApi
from .translator import Translator
from ..client.proxy import get_proxy
from ..constants import TOKEN_PERMISSION
from ..exceptions import (InvalidDriveException, NotFound,
                          RootAlreadyBindWithDifferentAccount)
from ..manager import FolderAlreadyUsed
from ..options import Options
from ..utils import get_device, guess_server_url

log = getLogger(__name__)

STARTUP_PAGE_CONNECTION_TIMEOUT = 30


class StartupPageConnectionError(Exception):
    pass


class WebSettingsApi(WebDriveApi):

    openAuthenticationDialog = pyqtSignal(str, object)

    def __init__(self, application, dlg=None):
        super(WebSettingsApi, self).__init__(application, dlg)
        # Attributes for the web authentication feedback
        self.openAuthenticationDialog.connect(self._open_authentication_dialog)
        self._new_local_folder = ''
        self._account_creation_error = ''
        self._token_update_error = ''
        self.__unbinding = False

    @pyqtSlot(result=str)
    def get_default_section(self):
        try:
            return self.dialog._section
        except AttributeError:
            log.exception('Section not reachable')
            return ''

    @pyqtSlot(result=str)
    def get_default_nuxeo_drive_folder(self):
        return self._manager.get_default_nuxeo_drive_folder()

    @pyqtSlot(str, result=QObject)
    def unbind_server_async(self, uid):
        if not self.__unbinding:
            return Promise(self.unbind_server, uid)

    @pyqtSlot(str, result=str)
    def unbind_server(self, uid):
        self.__unbinding = True
        try:
            self._manager.unbind_engine(str(uid))
        finally:
            self.__unbinding = False
        return ''

    @pyqtSlot(str)
    def filters_dialog(self, uid):
        engine = self._get_engine(str(uid))
        if engine:
            self.application.show_filters(engine)

    def _bind_server(self, local_folder, url, username, password, name, **kwargs):
        # Remove any parameters from the original URL
        parts = urlsplit(url)
        url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, '', parts.fragment))

        if name == '':
            name = None
        binder = namedtuple('binder', ['username', 'password', 'token', 'url',
                                       'no_check', 'no_fscheck'])
        binder.username = username
        binder.password = password
        binder.token = kwargs.get('token')
        binder.no_check = False
        binder.no_fscheck = not kwargs.get('check_fs', True)
        binder.url = url
        log.debug("Binder is : %s/%s", binder.url, binder.username)
        engine = self._manager.bind_engine(
            self._manager._get_default_server_type(), local_folder, name,
            binder, starts=False)

        # Display the filters window to let the user choose what to sync
        self.filters_dialog(engine.uid)

        return ''

    @pyqtSlot(str, str, str, str, str, result=QObject)
    def bind_server_async(self, *args, **kwargs):
        # Check bind_server signature for arguments.
        return Promise(self.bind_server, *args, **kwargs)

    @pyqtSlot(str, str, str, str, str, result=str)
    def bind_server(self, local_folder, url, username, password, name, **kwargs):
        url = guess_server_url(str(url))
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
        except InvalidDriveException:
            return 'INVALID_PARTITION'
        except Unauthorized:
            return 'UNAUTHORIZED'
        except FolderAlreadyUsed:
            return 'FOLDER_USED'
        except HTTPError:
            return 'CONNECTION_ERROR'
        except ConnectionError as e:
            if e.errno == 61:
                return 'CONNECTION_REFUSED'
            return 'CONNECTION_ERROR'
        except:
            log.exception('Unexpected error')
            # Map error here
            return 'CONNECTION_UNKNOWN'

    @pyqtSlot(str, str, str, result=QObject)
    def web_authentication_async(self, *args):
        # Check web_authentication signature for arguments.
        return Promise(self.web_authentication, *args)

    @pyqtSlot(str, str, str, result=str)
    def web_authentication(self, local_folder, server_url, engine_name):
        # Handle the server URL
        url = guess_server_url(str(server_url))
        if not url:
            return 'CONNECTION_ERROR'

        parts = urlsplit(url)
        server_url = urlunsplit(
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
                engine_name = str(engine_name)
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
        parts = urlsplit(guess_server_url(server_url))
        url = urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path + '/' + Options.startup_page,
            parts.query,
            parts.fragment))

        # Remove any parameters from the original URL
        server_url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, '', parts.fragment))

        try:
            log.debug('Proxy configuration for startup page connection: %s',
                      self._manager.proxy)
            headers = {
                'X-Application-Name': self._manager.app_name,
                'X-Device-Id': self._manager.device_id,
                'X-Client-Version': self._manager.version,
                'User-Agent': (self._manager.app_name
                               + '/' + self._manager.version),
            }
            timeout = STARTUP_PAGE_CONNECTION_TIMEOUT
            with requests.get(
                    url, headers=headers, timeout=timeout) as resp:
                status = resp.status_code
        except:
            log.exception('Error while trying to connect to Nuxeo Drive'
                          ' startup page with URL %s', url)
            raise StartupPageConnectionError()
        log.debug('Status code for %s = %d', url, status)
        return status

    def update_token(self, engine, token):
        engine.update_token(token)
        self.application.set_icon_state('idle')

    @pyqtSlot(str, result=str)
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

    @pyqtSlot(str, str, result=str)
    def set_server_ui(self, uid, server_ui):
        log.debug('Setting ui to %s', server_ui)
        engine = self._get_engine(str(uid))
        if engine is None:
            return 'CONNECTION_UNKNOWN'
        engine.set_ui(str(server_ui))
        return ''

    @pyqtSlot(str, object)
    def _open_authentication_dialog(self, url, callback_params):
        api = WebAuthenticationApi(self, callback_params)
        dialog = WebAuthenticationDialog(QCoreApplication.instance(),
                                         str(url), api)
        dialog.setWindowModality(Qt.NonModal)
        dialog.show()

    def _get_authentication_url(self, server_url):
        token_params = {
            'deviceId': self._manager.device_id,
            'applicationName': self._manager.app_name,
            'permission': TOKEN_PERMISSION,
            'deviceDescription': get_device(),
            'forceAnonymousLogin': 'true',
        }

        # Handle URL parameters
        parts = urlsplit(guess_server_url(server_url))
        path = (parts.path + '/' + Options.startup_page).replace('//', '/')
        params = (parts.query + '&' + urlencode(token_params)
                  if parts.query
                  else urlencode(token_params))
        url = urlunsplit(
            (parts.scheme, parts.netloc, path, params, parts.fragment))

        return url

    @pyqtSlot(result=str)
    def get_new_local_folder(self):
        return self._new_local_folder

    @pyqtSlot(str)
    def set_new_local_folder(self, local_folder):
        self._new_local_folder = str(local_folder)

    @pyqtSlot(result=str)
    def get_account_creation_error(self):
        return self._account_creation_error

    @pyqtSlot(str)
    def set_account_creation_error(self, error):
        self._account_creation_error = str(error)

    @pyqtSlot(result=str)
    def get_token_update_error(self):
        return self._token_update_error

    @pyqtSlot(str)
    def set_token_update_error(self, error):
        self._token_update_error = str(error)

    @pyqtSlot(result=str)
    def get_proxy_settings(self):
        proxy = self._manager.proxy
        result = {
            'url': getattr(proxy, 'url', None),
            'config': getattr(proxy, 'category', None),
            'scheme': getattr(proxy, 'scheme', None),
            'host': getattr(proxy, 'host', None),
            'username': getattr(proxy, 'username', None),
            'authenticated': getattr(proxy, 'authenticated', 0) == 1,
            'password': getattr(proxy, 'password', None),
            'port': getattr(proxy, 'port', None),
            'pac_url': getattr(proxy, 'pac_url', None),
            }
        return self._json(result)

    @pyqtSlot(str, str, bool, str, str, str, result=QObject)
    def set_proxy_settings_async(self, *args):
        # Check set_proxy_settings signature for arguments.
        return Promise(self.set_proxy_settings, *args)

    @pyqtSlot(str, str, bool, str, str, str, result=str)
    def set_proxy_settings(self, config, host, authenticated, username,
                           password, pac_url):
        proxy = get_proxy(
            category=str(config), url=str(host), authenticated=authenticated,
            pac_url=str(pac_url), username=str(username),
            password=str(password))
        return self._manager.set_proxy(proxy)


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
