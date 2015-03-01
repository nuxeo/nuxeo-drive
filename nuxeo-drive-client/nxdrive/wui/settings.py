'''
Created on 27 janv. 2015

@author: Remi Cattiau
'''
from PyQt4 import QtCore
from nxdrive.logging_config import get_logger
log = get_logger(__name__)

from nxdrive.wui.dialog import WebDialog, WebDriveApi
from nxdrive.manager import ProxySettings, FolderAlreadyUsed
from nxdrive.client.base_automation_client import Unauthorized
from nxdrive.wui.translator import Translator
import urllib2


class WebSettingsApi(WebDriveApi):
    def __init__(self, application, dlg=None):
        super(WebSettingsApi, self).__init__(application, dlg)

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

    def _bind_server(self, local_folder, url, username, password, name):
        local_folder = str(local_folder)
        url = str(url)
        username = str(username)
        password = str(password)
        name = str(name)
        if name == '':
            name = None
        self._manager.bind_server(local_folder, url, username, password, name)
        return ""

    @QtCore.pyqtSlot(str, str, str, str, str, result=str)
    def bind_server(self, local_folder, url, username, password, name):
        try:
            # Allow to override for other exception handling
            return self._bind_server(local_folder, url, username, password, name)
        except Unauthorized:
            return "UNAUTHORIZED"
        except FolderAlreadyUsed:
            return "FOLDER_USED"
        except urllib2.URLError as e:
            if e.errno == 61:
                return "CONNECTION_REFUSED"
            return "CONNECTION_ERROR"
        except urllib2.HTTPError as e:
            return "CONNECTION_ERROR"
        except Exception as e:
            log.exception(e)
            # Map error here
            return "CONNECTION_UNKNOWN"

    @QtCore.pyqtSlot(result=str)
    def get_proxy_settings(self):
        try:
            result = dict()
            settings = self._manager.get_proxy_settings()
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

    @QtCore.pyqtSlot(str, str, str, str, str, str, str, result=str)
    def set_proxy_settings(self, config='System', proxy_type=None,
                 server=None, port=None,
                 authenticated=False, username=None, password=None):
        try:
            config = str(config)
            proxy_type = str(proxy_type)
            server = str(server)
            port = int(str(port))
            authenticated = "true" == authenticated
            username = str(username)
            password = str(password)
            settings = ProxySettings(config=config, proxy_type=proxy_type, port=port, server=server,
                                     authenticated=authenticated, username=username, password=password)
            self._manager.set_proxy_settings(settings)
        except Exception as e:
            log.exception(e)
        return ""


class WebSettingsDialog(WebDialog):
    '''
    classdocs
    '''
    def __init__(self, application, section):
        '''
        Constructor
        '''
        self._section = section
        super(WebSettingsDialog, self).__init__(application, "settings.html",
                                                 api=WebSettingsApi(application),
                                                title=Translator.get("SETTINGS_WINDOW_TITLE"))

    def set_section(self, section):
        self._section = section
        self._view.reload()
