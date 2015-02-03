'''
Created on 27 janv. 2015

@author: Remi Cattiau
'''
from PyQt4 import QtCore
from nxdrive.logging_config import get_logger
log = get_logger(__name__)

from nxdrive.wui.dialog import WebDialog, WebDriveApi
from nxdrive.manager import ProxySettings


class WebSettingsApi(WebDriveApi):
    @QtCore.pyqtSlot(result=str)
    def get_default_section(self):
        return self._dialog._section

    @QtCore.pyqtSlot(str, str, str, str, str, result=str)
    def bind_server(self, local_folder, url, username, password, name):
        local_folder = str(local_folder)
        url = str(url)
        username = str(username)
        password = str(password)
        name = str(name)
        if name == '':
            name = None
        try:
            self._manager.bind_server(local_folder, url, username, password, name)
        except Exception as e:
            log.debug(e)
            return "ERROR"
        return ""

    @QtCore.pyqtSlot(result=str)
    def get_proxy_settings(self):
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

    @QtCore.pyqtSlot(str, str, str, str, str, str, str, result=str)
    def set_proxy_settings(self, config='System', proxy_type=None,
                 server=None, port=None,
                 authenticated=False, username=None, password=None):
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
                                                 api=WebSettingsApi(self, application), title="Nuxeo Drive - Settings")
