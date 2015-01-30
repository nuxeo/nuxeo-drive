'''
Created on 27 janv. 2015

@author: Remi Cattiau
'''
from PyQt4 import QtCore
from nxdrive.logging_config import get_logger
log = get_logger(__name__)

from nxdrive.wui.dialog import WebDialog, WebDriveApi


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
