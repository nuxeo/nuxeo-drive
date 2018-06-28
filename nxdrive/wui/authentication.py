# coding: utf-8
import re
from logging import getLogger
from urllib.parse import urlparse

import requests
from nuxeo.auth import TokenAuth
from PyQt5.QtCore import Qt, QUrl, pyqtSlot
from PyQt5.QtGui import QIcon
from PyQt5.QtNetwork import QNetworkProxy, QNetworkProxyFactory
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineView

from .dialog import WebDialog, WebDriveApi
from .translator import Translator

log = getLogger(__name__)


class WebAuthenticationApi(WebDriveApi):
    def __init__(self, settings_api, callback_params):
        super(WebAuthenticationApi, self).__init__(settings_api.application)
        self._settings_api = settings_api
        self._callback_params = callback_params

    @pyqtSlot(str)
    def handle_token(self, token):
        if 'engine' in self._callback_params:
            error = self.update_token(token)
        else:
            error = self.create_account(token)
        if error:
            self._settings_api.setMessage.emit(error, 'error')

    def create_account(self, token):
        error = None
        try:
            token = str(token)
            local_folder = self._callback_params['local_folder']
            server_url = self._callback_params['server_url']
            engine_name = self._callback_params['engine_name']
            engine_type = self._callback_params['engine_type']
            user = requests.get(
                server_url.rstrip('/') + '/api/v1/me', auth=TokenAuth(token),
                proxies=self.application.manager.proxy.settings()).json()
            username = user['properties']['username']

            server_url = server_url + '#' + engine_type
            
            log.debug('Creating new account [%s, %s, %s]',
                      local_folder, server_url, username)

            error = self._settings_api.bind_server(
                local_folder, server_url, username,
                password=None, token=token, name=engine_name)

            log.debug("RETURN FROM BIND_SERVER IS: '%s'", error)
            if error == "":
                error = None
                self._settings_api.set_new_local_folder(local_folder)
        except:
            log.exception('Unexpected error while trying to create a new account [%s, %s, %s]',
                          local_folder, server_url, username)
            error = 'CONNECTION_UNKNOWN'
        finally:
            return error

    def update_token(self, token):
        error = None
        engine = self._callback_params['engine']
        try:
            token = str(token)
            log.debug('Updating token for account [%s, %s, %s]',
                      engine.local_folder, engine.server_url, engine.remote_user)
            self._settings_api.update_token(engine, token)
        except requests.ConnectionError as e:
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
            return error

class WebAuthenticationDialog(WebDialog):
    def __init__(self, application, url, api):
        title = Translator.get('WEB_AUTHENTICATION_WINDOW_TITLE')
        super(WebAuthenticationDialog, self).__init__(
            application, url, title=title, api=api)
        self.resize(1000, 800)
        self.page.urlChanged.connect(self.handle_login)
    
    def handle_login(self, url):
        m = re.search('#token=([0-F]{8}-[0-F]{4}-[0-F]{4}-[0-F]{4}-[0-F]{12})',
                      url.toString(), re.I)
        if m:
            token = m.group(1)
            error = self.api.handle_token(token)
            if error:
                # Handle error
                pass
            self.close()
