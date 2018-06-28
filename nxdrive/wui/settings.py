# coding: utf-8
from collections import namedtuple
from logging import getLogger
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests
from PyQt5 import QtGui
from PyQt5.QtCore import pyqtProperty, pyqtSignal, pyqtSlot, QObject, QCoreApplication, QSize, Qt, QUrl
from PyQt5.QtQml import QQmlListProperty, qmlRegisterType
from PyQt5.QtQuick import QQuickView
from nuxeo.exceptions import HTTPError, Unauthorized
from requests import ConnectionError

from .authentication import WebAuthenticationApi, WebAuthenticationDialog
from .dialog import Promise, WebDialog, WebDriveApi
from .translator import Translator
from .view import LanguageModel, NuxeoView
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
    setMessage = pyqtSignal(str, str)

    def __init__(self, application, dlg=None):
        super(WebSettingsApi, self).__init__(application, dlg)
        # Attributes for the web authentication feedback
        self.openAuthenticationDialog.connect(self._open_authentication_dialog)
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

    @pyqtSlot(str)
    def unbind_server(self, uid):
        self.__unbinding = True
        try:
            self._manager.unbind_engine(str(uid))
        finally:
            self.__unbinding = False

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
        self.setMessage.emit('CONNECTION_SUCCESS', 'success')

    @pyqtSlot(str, str, str, str, str)
    def bind_server(self, local_folder, url, username, password, name, **kwargs):
        url = guess_server_url(str(url))
        if not url:
            self.setMessage.emit('CONNECTION_ERROR', 'error')
            return

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
                self.setMessage.emit('FOLDER_USED', 'error')
                return

            kwargs['check_fs'] = False
            return self.bind_server(
                local_folder, url, username, password, name, **kwargs)
        except NotFound:
            error = 'FOLDER_DOES_NOT_EXISTS'
        except InvalidDriveException:
            error = 'INVALID_PARTITION'
        except Unauthorized:
            error = 'UNAUTHORIZED'
        except FolderAlreadyUsed:
            error = 'FOLDER_USED'
        except HTTPError:
            error = 'CONNECTION_ERROR'
        except ConnectionError as e:
            if e.errno == 61:
                error = 'CONNECTION_REFUSED'
            error = 'CONNECTION_ERROR'
        except:
            log.exception('Unexpected error')
            # Map error here
            error = 'CONNECTION_UNKNOWN'
        self.setMessage.emit(error, 'error')

    @pyqtSlot(str, str, str)
    def web_authentication(self, engine_name, server_url, local_folder):
        # Handle the server URL
        url = guess_server_url(str(server_url))
        if not url:
            self.setMessage.emit('CONNECTION_ERROR', 'error')
            return

        parts = urlsplit(url)
        server_url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, parts.query, parts.fragment))

        # Handle the engine
        engine_type = parts.fragment or self._manager._get_default_server_type()

        try:
            # Handle local folder
            local_folder = str(local_folder)
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
                return
            else:
                # Startup page is not available
                log.debug('Web authentication not available on server %s, '
                          'falling back on basic authentication', server_url)
                return 'false'
        except FolderAlreadyUsed:
            error = 'FOLDER_USED'
        except StartupPageConnectionError:
            error = 'CONNECTION_ERROR'
        except:
            log.exception('Unexpected error while trying to open'
                          ' web authentication window')
            error = 'CONNECTION_UNKNOWN'
        self.setMessage.emit(error, 'error')

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

    @pyqtSlot(str)
    def web_update_token(self, uid):
        try:
            engine = self._get_engine(str(uid))
            if engine is None:
                self.setMessage.emit('CONNECTION_UNKNOWN', 'error')
                return
            params = urlencode({'updateToken': True})
            url = self._get_authentication_url(engine.server_url) + '&' + params
            callback_params = {
                'engine': engine,
            }
            log.debug('Opening login window for token update with URL %s', url)
            self._open_authentication_dialog(url, callback_params)
        except:
            log.exception('Unexpected error while trying to open web'
                          ' authentication window for token update')
            self.setMessage.emit('CONNECTION_UNKNOWN', 'error')

    @pyqtSlot(str, str, result=bool)
    def set_server_ui(self, uid, server_ui):
        log.debug('Setting ui to %s', server_ui)
        engine = self._get_engine(str(uid))
        if engine is None:
            self.setMessage.emit('CONNECTION_UNKNOWN', 'error')
            return False
        engine.set_ui(str(server_ui))
        return True

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
    def get_proxy_settings(self):
        proxy = self._manager.proxy
        result = {
            'url': getattr(proxy, 'url', None),
            'config': getattr(proxy, 'category', None),
            'username': getattr(proxy, 'username', None),
            'authenticated': getattr(proxy, 'authenticated', 0) == 1,
            'password': getattr(proxy, 'password', None),
            'port': getattr(proxy, 'port', None),
            'pac_url': getattr(proxy, 'pac_url', None),
        }
        return self._json(result)

    @pyqtSlot(str, str, bool, str, str, str, result=bool)
    def set_proxy_settings(self, config, host, authenticated, username,
                           password, pac_url):
        proxy = get_proxy(
            category=str(config), url=str(host), authenticated=authenticated,
            pac_url=str(pac_url), username=str(username),
            password=str(password))
        result = self._manager.set_proxy(proxy)
        if result:
            self.setMessage.emit(result, 'error')
            return False
        else:
            self.setMessage.emit('PROXY_APPLIED', 'success')
            return True

    @pyqtSlot(str, result=bool)
    def has_invalid_credentials(self, uid):
        engine = self._get_engine(str(uid))
        if engine:
            return engine.has_invalid_credentials()


class SettingsView(NuxeoView):
    def __init__(self, application, section):
        super(SettingsView, self).__init__(
            application, WebSettingsApi(application, self))
        self._section = section
        self.language_model = LanguageModel()
        self.language_model.addLanguages(Translator.languages())

        size = QSize(640, 480)
        self.setMinimumSize(size)
        self.setMaximumSize(size)

        context = self.rootContext()
        context.setContextProperty(
            'nuxeoVersionText',
            'Nuxeo Drive ' + self.application.manager.version)
        metrics = self.application.manager.get_metrics()
        context.setContextProperty(
            'modulesVersionText', (
                f'Python {metrics["python_version"]}, '
                f'Qt {metrics["qt_version"]}, '
                f'PyQt {metrics["pyqt_version"]}, '
                f'SIP {metrics["sip_version"]}'))
        self.setTitle(Translator.get('SETTINGS_WINDOW_TITLE'))
        self.init()

    def init(self):
        super(SettingsView, self).init()
        context = self.rootContext()
        context.setContextProperty('languageModel', self.language_model)
        context.setContextProperty('currentLanguage', self.current_language())

        self.setSource(QUrl('nxdrive/data/qml/Settings.qml'))

        root = self.rootObject()
        self.api.setMessage.connect(root.setMessage)

    def current_language(self):
        lang = Translator.locale()
        for tag, name in self.language_model.languages:
            if tag == lang:
                return name
        return None

    def set_section(self, section):
        self._section = section
        sections = {
            "General": 0,
            "Accounts": 1,
            "About": 2,
        }
        self.rootObject().setSection.emit(sections[section])
