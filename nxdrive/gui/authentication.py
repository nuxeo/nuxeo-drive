# coding: utf-8
import re
from logging import getLogger
from typing import Any, Dict

import requests
from PyQt5.QtCore import QUrl, pyqtSlot
from nuxeo.auth import TokenAuth
from nuxeo.client import Nuxeo

from .dialog import QMLDriveApi, WebDialog
from ..translator import Translator

__all__ = ("QMLAuthenticationApi", "WebAuthenticationDialog")

log = getLogger(__name__)


class QMLAuthenticationApi(QMLDriveApi):
    def __init__(
        self, settings_api: "QMLSettingsApi", callback_params: Dict[str, Any]
    ) -> None:
        super().__init__(settings_api.application)
        self._settings_api = settings_api
        self._callback_params = callback_params

    @pyqtSlot(str)
    def handle_token(self, token: str) -> None:
        if "engine" in self._callback_params:
            error = self.update_token(token)
        else:
            error = self.create_account(token)
        if error:
            self._settings_api.setMessage.emit(error, "error")

    def create_account(self, token: str) -> str:
        error = None
        try:
            local_folder = self._callback_params["local_folder"]
            server_url = self._callback_params["server_url"]
            engine_type = self._callback_params["engine_type"]
            server = Nuxeo(
                host=server_url,
                auth=TokenAuth(token),
                proxies=self.application.manager.proxy.settings(),
            )
            user = server.operations.execute(command="User.Get")
            username = user["uid"]

            server_url = server_url + "#" + engine_type

            log.debug(
                "Creating new account [%s, %s, %s]", local_folder, server_url, username
            )

            error = self._settings_api.bind_server(
                local_folder,
                server_url,
                username,
                password=None,
                token=token,
                name=None,
            )

            log.debug("RETURN FROM BIND_SERVER IS: '%s'", error)
        except:
            log.exception(
                "Unexpected error while trying to create a new account [%s, %s, %s]",
                local_folder,
                server_url,
                username,
            )
            error = "CONNECTION_UNKNOWN"
        finally:
            return error

    def update_token(self, token: str) -> str:
        error = None
        engine = self._callback_params["engine"]
        try:
            log.debug(
                "Updating token for account [%s, %s, %s]",
                engine.local_folder,
                engine.server_url,
                engine.remote_user,
            )
            self._settings_api.update_token(engine, token)
        except requests.ConnectionError as e:
            log.exception("HTTP Error")
            if e.errno == 61:
                error = "CONNECTION_REFUSED"
            else:
                error = "CONNECTION_ERROR"
        except:
            log.exception(
                "Unexpected error while trying to update token for account [%s, %s, %s]",
                engine.local_folder,
                engine.server_url,
                engine.remote_user,
            )
            error = "CONNECTION_UNKNOWN"
        finally:
            return error


class WebAuthenticationDialog(WebDialog):
    def __init__(
        self, application: "Application", url: str, api: QMLAuthenticationApi
    ) -> None:
        title = Translator.get("WEB_AUTHENTICATION_WINDOW_TITLE")
        super().__init__(application, url, title=title, api=api)
        self.resize(1000, 800)
        self.page.urlChanged.connect(self.handle_login)

    def handle_login(self, url: QUrl) -> None:
        m = re.search(
            "#token=([0-F]{8}-[0-F]{4}-[0-F]{4}-[0-F]{4}-[0-F]{12})",
            url.toString(),
            re.I,
        )
        if m:
            token = m.group(1)
            error = self.api.handle_token(token)
            if error:
                # Handle error
                pass
            self.close()
