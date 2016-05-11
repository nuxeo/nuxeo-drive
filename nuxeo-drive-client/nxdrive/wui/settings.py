'''
Created on 27 janv. 2015

@author: Remi Cattiau
'''
from PyQt4 import QtCore, QtGui
from nxdrive.logging_config import get_logger
from nxdrive.client.common import NotFound
log = get_logger(__name__)

from nxdrive.wui.dialog import WebDialog, WebDriveApi, Promise
from nxdrive.wui.authentication import WebAuthenticationApi
from nxdrive.wui.authentication import WebAuthenticationDialog
from nxdrive.manager import ProxySettings, FolderAlreadyUsed
from nxdrive.client.base_automation_client import Unauthorized
from nxdrive.client.base_automation_client import get_proxy_handler
from nxdrive.client.base_automation_client import get_opener_proxies
from nxdrive.client.base_automation_client import AddonNotInstalled
from nxdrive.engine.engine import RootAlreadyBindWithDifferentAccount
from nxdrive.engine.engine import InvalidDriveException
from nxdrive.wui.translator import Translator
from nxdrive.utils import DEVICE_DESCRIPTIONS
from nxdrive.utils import TOKEN_PERMISSION
import sys
import urllib2
from urllib import urlencode

DRIVE_STARTUP_PAGE = 'drive_login.jsp'
STARTUP_PAGE_CONNECTION_TIMEOUT = 30


class StartupPageConnectionError(Exception):
    pass


class WebSettingsApi(WebDriveApi):

    openAuthenticationDialog = QtCore.pyqtSignal(str, object)

    def __init__(self, application, dlg=None):
        super(WebSettingsApi, self).__init__(application, dlg)
        # Attributes for the web authentication feedback
        self.openAuthenticationDialog.connect(self._open_authentication_dialog)
        self._new_local_folder = ""
        self._account_creation_error = ""
        self._token_update_error = ""

    @QtCore.pyqtSlot(result=str)
    def get_default_section(self):
        try:
            return self._dialog._section
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(result=str)
    def get_default_nuxeo_drive_folder(self):
        try:
            folder = self._manager.get_default_nuxeo_drive_folder()
            return folder
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str, result=QtCore.QObject)
    def unbind_server_async(self, uid):
        return Promise(self.unbind_server, uid)

    @QtCore.pyqtSlot(str, result=str)
    def unbind_server(self, uid):
        try:
            self._manager.unbind_engine(str(uid))
        except Exception as e:
            log.exception(e)
        return ""

    @QtCore.pyqtSlot(str, result=str)
    def filters_dialog(self, uid):
        try:
            engine = self._get_engine(uid)
            if engine is None:
                return "ERROR"
            self._application.show_filters(engine)
        except Exception as e:
            log.exception(e)
        return ""

    def _bind_server(self, local_folder, url, username, password, name, start_engine=True, check_fs=True, token=None):
        from collections import namedtuple
        if isinstance(local_folder, QtCore.QString):
            local_folder = str(local_folder.toUtf8()).decode('utf-8')
        url = str(url)
        # On first time login convert QString(having special characters) to str
        if username and isinstance(username, QtCore.QString):
            username = unicode(username).encode('utf-8')
        if password and isinstance(password, QtCore.QString):
            password = unicode(password).encode('utf-8')
        name = unicode(username)
        if name == '':
            name = None
        binder = namedtuple('binder', ['username', 'password', 'token', 'url', 'no_check', 'no_fscheck'])
        binder.username = username
        binder.password = password
        binder.token = token
        binder.no_check = False
        binder.no_fscheck = not check_fs
        binder.url = url
        log.debug("Binder is : %s/%s", binder.url, binder.username)
        self._manager.bind_engine(self._manager._get_default_server_type(), local_folder, name, binder,
                                  starts=start_engine)
        return ""

    @QtCore.pyqtSlot(str, str, str, str, str, result=QtCore.QObject)
    def bind_server_async(self, local_folder, url, username, password, name, check_fs=True, token=None):
        return Promise(self.bind_server, local_folder, url, username, password, name, check_fs, token)

    @QtCore.pyqtSlot(str, str, str, str, str, result=str)
    def bind_server(self, local_folder, url, username, password, name, check_fs=True, token=None):
        try:
            # Allow to override for other exception handling
            log.debug("URL: '%s'", url)
            return self._bind_server(local_folder, url, username, password, name, check_fs=check_fs, token=token)
        except RootAlreadyBindWithDifferentAccount as e:
            # Ask for the user
            values = dict()
            values["username"] = e.get_username()
            values["url"] = e.get_url()
            msgbox = QtGui.QMessageBox(QtGui.QMessageBox.Question, self._manager.get_appname(),
                                       Translator.get("ROOT_USED_WITH_OTHER_BINDING", values),
                                       QtGui.QMessageBox.NoButton, self._dialog)
            msgbox.addButton(Translator.get("ROOT_USED_CONTINUE"), QtGui.QMessageBox.AcceptRole)
            cancel = msgbox.addButton(Translator.get("ROOT_USED_CANCEL"), QtGui.QMessageBox.RejectRole)
            msgbox.exec_()
            if (msgbox.clickedButton() == cancel):
                return "FOLDER_USED"
            return self.bind_server(local_folder, url, username, password, name, check_fs=False, token=token)
        except NotFound:
            return "FOLDER_DOES_NOT_EXISTS"
        except AddonNotInstalled:
            return "ADDON_NOT_INSTALLED"
        except InvalidDriveException:
            return "INVALID_PARTITION"
        except Unauthorized:
            return "UNAUTHORIZED"
        except FolderAlreadyUsed:
            return "FOLDER_USED"
        except urllib2.HTTPError as e:
            if (isinstance(url, QtCore.QString)):
                url = str(url)
            if e.code == 404 and not url.endswith("nuxeo/"):
                if not url.endswith("/"):
                    url += "/"
                return self.bind_server(local_folder, url + "nuxeo/", username, password, name, check_fs, token)
            return "CONNECTION_ERROR"
        except urllib2.URLError as e:
            if e.errno == 61:
                return "CONNECTION_REFUSED"
            return "CONNECTION_ERROR"
        except Exception as e:
            log.exception(e)
            # Map error here
            return "CONNECTION_UNKNOWN"

    @QtCore.pyqtSlot(str, str, str, result=QtCore.QObject)
    def web_authentication_async(self, local_folder, server_url, engine_name):
        return Promise(self.web_authentication, local_folder, server_url, engine_name)

    @QtCore.pyqtSlot(str, str, str, result=str)
    def web_authentication(self, local_folder, server_url, engine_name):
        try:
            # Handle local folder
            local_folder = str(local_folder.toUtf8()).decode('utf-8')
            self._check_local_folder(local_folder)

            # Handle server URL
            server_url = str(server_url)
            engine_type = 'NXDRIVE'
            if '#' in server_url:
                info = server_url.split('#')
                server_url = info[0]
                engine_type = info[1]
            if not server_url.endswith('/'):
                server_url += '/'

            # Connect to startup page
            status = self._connect_startup_page(server_url)
            if status == 404 and not server_url.endswith("nuxeo/"):
                status = self._connect_startup_page(server_url + "nuxeo/")
                if status < 400 or status in (401, 500, 503):
                    server_url = server_url + "nuxeo/"
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
                log.debug('Web authentication is available on server %s, opening login window with URL %s',
                          server_url, url)
                self.openAuthenticationDialog.emit(url, callback_params)
                return "true"
            else:
                # Startup page is not available
                log.debug('Web authentication not available on server %s, falling back on basic authentication',
                          server_url)
                return "false"
        except FolderAlreadyUsed:
            return 'FOLDER_USED'
        except StartupPageConnectionError:
            return 'CONNECTION_ERROR'
        except:
            log.exception('Unexpected error while trying to open web authentication window')
            return 'CONNECTION_UNKNOWN'

    def _check_local_folder(self, local_folder):
        if not self._manager.check_local_folder_available(local_folder):
            raise FolderAlreadyUsed()

    def _connect_startup_page(self, server_url):
        url = server_url + DRIVE_STARTUP_PAGE
        try:
            proxy_handler = get_proxy_handler(self._manager.get_proxies())
            opener = urllib2.build_opener(proxy_handler)
            log.debug('Proxy configuration for startup page connection: %s, effective proxy list: %r',
                      self._manager.get_proxy_settings().config, get_opener_proxies(opener))
            headers = {
                'X-Application-Name': self._manager.get_appname(),
                'X-Device-Id': self._manager.get_device_id(),
                'X-Client-Version': self._manager.get_version(),
                'User-Agent': self._manager.get_appname() + "/" + self._manager.get_version(),
            }
            req = urllib2.Request(url, headers=headers)
            response = opener.open(req, timeout=STARTUP_PAGE_CONNECTION_TIMEOUT)
            status = response.getcode()
        except urllib2.HTTPError as e:
            status = e.code
        except:
            log.exception('Error while trying to connect to Nuxeo Drive startup page with URL %s', url)
            raise StartupPageConnectionError()
        log.debug('Status code for %s = %d', url, status)
        return status

    def update_token(self, engine, token):
        engine.update_token(token)

    @QtCore.pyqtSlot(str, result=str)
    def web_update_token(self, uid):
        try:
            engine = self._get_engine(uid)
            if engine is None:
                return 'CONNECTION_UNKNOWN'
            server_url = engine.get_server_url()
            url = self._get_authentication_url(server_url) + '&' + urlencode({'updateToken': True})
            callback_params = {
                'engine': engine,
            }
            log.debug('Opening login window for token update with URL %s', url)
            self._open_authentication_dialog(url, callback_params)
            return ''
        except:
            log.exception('Unexpected error while trying to open web authentication window for token update')
            return 'CONNECTION_UNKNOWN'

    @QtCore.pyqtSlot(str, object)
    def _open_authentication_dialog(self, url, callback_params):
        api = WebAuthenticationApi(self, callback_params)
        dialog = WebAuthenticationDialog(QtCore.QCoreApplication.instance(), str(url), api)
        dialog.setWindowModality(QtCore.Qt.NonModal)
        dialog.show()

    def _get_authentication_url(self, server_url):
        token_params = {
            'deviceId': self._manager.get_device_id(),
            'applicationName': self._manager.get_appname(),
            'permission': TOKEN_PERMISSION,
        }
        device_description = DEVICE_DESCRIPTIONS.get(sys.platform)
        if device_description:
            token_params['deviceDescription'] = device_description
        # Force login in case of anonymous user configuration
        token_params['forceAnonymousLogin'] = 'true'
        return server_url + DRIVE_STARTUP_PAGE + '?' + urlencode(token_params)

    @QtCore.pyqtSlot(result=str)
    def get_new_local_folder(self):
        try:
            return self._new_local_folder
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def set_new_local_folder(self, local_folder):
        try:
            self._new_local_folder = local_folder
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(result=str)
    def get_account_creation_error(self):
        try:
            return self._account_creation_error
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def set_account_creation_error(self, error):
        try:
            self._account_creation_error = error
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(result=str)
    def get_token_update_error(self):
        try:
            return self._token_update_error
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def set_token_update_error(self, error):
        try:
            self._token_update_error = error
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(result=str)
    def get_proxy_settings(self):
        try:
            result = dict()
            settings = self._manager.get_proxy_settings()
            result["url"] = settings.to_url(with_credentials=False)
            result["config"] = settings.config
            result["type"] = settings.proxy_type
            result["server"] = settings.server
            result["username"] = settings.username
            result["authenticated"] = (settings.authenticated == 1)
            result["password"] = settings.password
            result["port"] = settings.port
            return self._json(result)
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str, str, str, str, str, result=QtCore.QObject)
    def set_proxy_settings_async(self, config='System', server=None, authenticated=False, username=None, password=None):
        return Promise(self.set_proxy_settings, config, server, authenticated, username, password)

    @QtCore.pyqtSlot(str, str, str, str, str, result=str)
    def set_proxy_settings(self, config='System', server=None, authenticated=False, username=None, password=None):
        try:
            config = str(config)
            url = str(server)
            settings = ProxySettings(config=config)
            if config == "Manual":
                settings.from_url(url)
            settings.authenticated = "true" == authenticated
            settings.username = str(username)
            settings.password = str(password)
            return self._manager.set_proxy_settings(settings)
        except Exception as e:
            log.exception(e)
        return ""


class WebSettingsDialog(WebDialog):
    '''
    classdocs
    '''
    def __init__(self, application, section, api=None):
        '''
        Constructor
        '''
        self._section = section
        if api is None:
            api = WebSettingsApi(application)
        super(WebSettingsDialog, self).__init__(application, "settings.html",
                                                api=api,
                                                title=Translator.get("SETTINGS_WINDOW_TITLE"))

    def set_section(self, section):
        self._section = section
        self._view.reload()
