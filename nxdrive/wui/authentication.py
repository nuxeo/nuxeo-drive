# coding: utf-8
from logging import getLogger

from PyQt5.QtCore import pyqtSlot
from requests import ConnectionError

from .dialog import WebDialog, WebDriveApi
from .translator import Translator

log = getLogger(__name__)


class WebAuthenticationApi(WebDriveApi):
    def __init__(self, settings_api, callback_params):
        super(WebAuthenticationApi, self).__init__(settings_api.application)
        self._settings_api = settings_api
        self._callback_params = callback_params

    @pyqtSlot(str, str)
    def create_account(self, username, token):
        """
        This method is called by a JavaScript instruction on
        the <nuxeo_url>/drive_login.jsp page.
        """
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
            self.dialog.accept()
            if error is not None:
                self._settings_api.set_account_creation_error(error)
            self._settings_api.dialog.view.reload()

    @pyqtSlot(str)
    def update_token(self, token):
        error = None
        engine = self._callback_params['engine']
        try:
            token = str(token)
            log.debug('Updating token for account [%s, %s, %s]',
                      engine.local_folder, engine.server_url, engine.remote_user)
            self._settings_api.update_token(engine, token)
        except ConnectionError as e:
            log.exception('HTTP Error')
            if e.errno == 61:
                error = 'CONNECTION_REFUSED'
            else:
                error = 'CONNECTION_ERROR'
        except:
            log.exception('Unexpected error while trying to update token for account [%s, %s, %s]',
                          engine.local_folder, engine.server_url, engine.remote_user)
            error = 'CONNECTION_UNKNOWN'
        finally:
            self.dialog.accept()
            if error is not None:
                self._settings_api.set_token_update_error(error)
            self._settings_api.dialog.view.reload()


class WebAuthenticationDialog(WebDialog):
    def __init__(self, application, url, api):
        title = Translator.get('WEB_AUTHENTICATION_WINDOW_TITLE')
        super(WebAuthenticationDialog, self).__init__(
            application, url, title=title, api=api)
        self.resize(1000, 800)
