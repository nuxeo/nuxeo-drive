# coding: utf-8
import urllib2
from logging import getLogger

from PyQt4 import QtCore

from .dialog import WebDialog, WebDriveApi
from .translator import Translator

log = getLogger(__name__)


class WebAuthenticationApi(WebDriveApi):
    def __init__(self, settings_api, callback_params):
        super(WebAuthenticationApi, self).__init__(settings_api.application)
        self._settings_api = settings_api
        self._callback_params = callback_params

    @QtCore.pyqtSlot(str)
    def update_token(self, token):
        error = None
        engine = self._callback_params['engine']
        try:
            token = str(token)
            log.debug('Updating token for account [%s, %s, %s]',
                      engine.local_folder, engine.server_url, engine.remote_user)
            self._settings_api.update_token(engine, token)
        except urllib2.URLError as e:
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
