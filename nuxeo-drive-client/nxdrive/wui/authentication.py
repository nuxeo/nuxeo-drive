from PyQt4 import QtCore
from nxdrive.logging_config import get_logger
from nxdrive.manager import FolderAlreadyUsed
from nxdrive.wui.dialog import WebDialog
from nxdrive.wui.translator import Translator
import urllib2

log = get_logger(__name__)


class WebAuthenticationApi(QtCore.QObject):
    def __init__(self, settings_api, callback_params):
        super(WebAuthenticationApi, self).__init__()
        self._settings_api = settings_api
        self._callback_params = callback_params

    def set_dialog(self, dlg):
        self._dialog = dlg

    @QtCore.pyqtSlot(str, str)
    def create_account(self, username, token):
        error = None
        try:
            username = str(username)
            token = str(token)
            local_folder = self._callback_params['local_folder']
            server_url = self._callback_params['server_url']
            engine_name = self._callback_params['engine_name']
            engine_type = self._callback_params['engine_type']
            server_url = server_url + '#' + engine_type
            log.debug('Creating new account [%s, %s, %s]', local_folder, server_url, username)
            error = self._settings_api.bind_server(local_folder, server_url, username, password=None, token=token, name=engine_name)
            log.debug("RETURN FROM BIND_SERVER IS: '%s'", error)
            if error == "":
                error = None
                self._settings_api.set_new_local_folder(local_folder)
        except:
            log.exception('Unexpected error while trying to create a new account [%s, %s, %s]',
                          local_folder, server_url, username)
            error = 'CONNECTION_UNKNOWN'
        finally:
            self._dialog.accept()
            if error is not None:
                self._settings_api.set_account_creation_error(error)
            self._settings_api.get_dialog().get_view().reload()

    @QtCore.pyqtSlot(str)
    def update_token(self, token):
        error = None
        engine = self._callback_params['engine']
        try:
            token = str(token)
            log.debug('Updating token for account [%s, %s, %s]',
                      engine.get_local_folder(), engine.get_server_url(), engine.get_remote_user())
            self._settings_api.update_token(engine, token)
        except urllib2.URLError as e:
            log.exception(e)
            if e.errno == 61:
                error = 'CONNECTION_REFUSED'
            else:
                error = 'CONNECTION_ERROR'
        except urllib2.HTTPError as e:
            log.exception(e)
            error = 'CONNECTION_ERROR'
        except:
            log.exception('Unexpected error while trying to update token for account [%s, %s, %s]',
                          engine.get_local_folder(), engine.get_server_url(), engine.get_remote_user())
            error = 'CONNECTION_UNKNOWN'
        finally:
            self._dialog.accept()
            if error is not None:
                self._settings_api.set_token_update_error(error)
            self._settings_api.get_dialog().get_view().reload()


class WebAuthenticationDialog(WebDialog):
    def __init__(self, application, url, api):
        super(WebAuthenticationDialog, self).__init__(application, url,
                                                      title=Translator.get("WEB_AUTHENTICATION_WINDOW_TITLE"), api=api)
        self.resize(1000, 800)
