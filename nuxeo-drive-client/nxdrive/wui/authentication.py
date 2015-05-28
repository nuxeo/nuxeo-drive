from PyQt4 import QtCore
from urllib import urlencode
from nxdrive.logging_config import get_logger
from nxdrive.wui.dialog import WebDialog
from nxdrive.wui.translator import Translator

log = get_logger(__name__)


class WebAuthenticationApi(QtCore.QObject):

    def __init__(self, settings_view, callback, local_folder, server_url, engine_name):
        super(WebAuthenticationApi, self).__init__()
        self._settings_view = settings_view
        self._callback = callback
        self._local_folder = local_folder
        self._server_url = server_url
        self._engine_name = engine_name

    def set_dialog(self, dlg):
        self._dialog = dlg

    @QtCore.pyqtSlot(str, str)
    def create_account(self, username, token):
        self._callback(self._local_folder, self._server_url, username, token, self._engine_name)
        self._dialog.accept()
        self._settings_view.reload()


class WebAuthenticationDialog(WebDialog):

    def __init__(self, application, server_url, token_params, api):
        url = server_url
        if not url.endswith('/'):
            url += '/'
        url += 'drive_login.jsp?'
        url += urlencode(token_params)
        super(WebAuthenticationDialog, self).__init__(application, url,
                                                      title=Translator.get("WEB_AUTHENTICATION_WINDOW_TITLE"), api=api)
        # TODO
        self.resize(800, 800)
#         self.setWindowFlags(Qt.WindowStaysOnTopHint)
