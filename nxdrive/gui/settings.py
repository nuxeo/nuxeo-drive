# coding: utf-8
from logging import getLogger
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

import requests
from PyQt5.QtCore import QSize, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QMessageBox
from nuxeo.exceptions import HTTPError, Unauthorized
from requests import ConnectionError

from .dialog import QMLDriveApi
from .translator import Translator
from .view import LanguageModel, NuxeoView
from ..client.proxy import get_proxy
from ..exceptions import (
    FolderAlreadyUsed,
    InvalidDriveException,
    NotFound,
    RootAlreadyBindWithDifferentAccount,
)
from ..objects import Binder
from ..options import Options
from ..utils import find_resource, guess_server_url

__all__ = ("QMLSettingsApi", "SettingsView")

log = getLogger(__name__)

STARTUP_PAGE_CONNECTION_TIMEOUT = 30


class StartupPageConnectionError(Exception):
    pass


class SettingsView(NuxeoView):
    def __init__(self, application: "Application", section: str) -> None:
        super().__init__(application, QMLSettingsApi(application, self))
        self._section = section
        self.language_model = LanguageModel()
        self.language_model.addLanguages(Translator.languages())

        size = QSize(640, 480)
        self.setMinimumSize(size)
        self.setMaximumSize(size)

        context = self.rootContext()
        context.setContextProperty(
            "nuxeoVersionText", "Nuxeo Drive " + self.application.manager.version
        )
        metrics = self.application.manager.get_metrics()
        context.setContextProperty(
            "modulesVersionText",
            (
                f'Python {metrics["python_version"]}, '
                f'Qt {metrics["qt_version"]}, '
                f'SIP {metrics["sip_version"]}'
            ),
        )
        self.setTitle(Translator.get("SETTINGS_WINDOW_TITLE"))
        self.init()

    def init(self) -> None:
        super().init()
        context = self.rootContext()
        context.setContextProperty("languageModel", self.language_model)
        context.setContextProperty("currentLanguage", self.current_language())

        self.setSource(QUrl(find_resource("qml", "Settings.qml")))

        root = self.rootObject()
        self.api.setMessage.connect(root.setMessage)

    def current_language(self) -> Optional[str]:
        lang = Translator.locale()
        for tag, name in self.language_model.languages:
            if tag == lang:
                return name
        return None

    def set_section(self, section: str) -> None:
        self._section = section
        sections = {"General": 0, "Accounts": 1, "About": 2}
        self.rootObject().setSection.emit(sections[section])


class QMLSettingsApi(QMLDriveApi):

    openAuthenticationDialog = pyqtSignal(str, object)

    def __init__(self, application: "Application", dlg: SettingsView=None) -> None:
        super().__init__(application, dlg)
        # Attributes for the web authentication feedback
        self.openAuthenticationDialog.connect(
            self.application._open_authentication_dialog
        )
        self.__unbinding = False

    @pyqtSlot(result=str)
    def get_default_section(self) -> str:
        try:
            return self.dialog._section
        except AttributeError:
            log.exception("Section not reachable")
            return ""

    @pyqtSlot(result=str)
    def get_default_nuxeo_drive_folder(self) -> str:
        return self._manager.get_default_nuxeo_drive_folder()

    @pyqtSlot(str)
    def unbind_server(self, uid: str) -> None:
        self.__unbinding = True
        try:
            self._manager.unbind_engine(uid)
        finally:
            self.__unbinding = False

    @pyqtSlot(str)
    def filters_dialog(self, uid: str) -> None:
        engine = self._get_engine(uid)
        if engine:
            self.application.show_filters(engine)

    def _bind_server(
        self,
        local_folder: str,
        url: str,
        username: str,
        password: str,
        name: str,
        **kwargs: Any,
    ) -> None:
        # Remove any parameters from the original URL
        parts = urlsplit(url)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))

        if name == "":
            name = None
        binder = Binder(
            username=username,
            password=password,
            token=kwargs.get("token"),
            no_check=False,
            no_fscheck=not kwargs.get("check_fs", True),
            url=url,
        )
        log.debug("Binder is : %s/%s", binder.url, binder.username)
        engine = self._manager.bind_engine(
            self._manager._get_default_server_type(),
            local_folder,
            name,
            binder,
            starts=False,
        )

        # Display the filters window to let the user choose what to sync
        self.filters_dialog(engine.uid)
        self.setMessage.emit("CONNECTION_SUCCESS", "success")

    @pyqtSlot(str, str, str, str, str)
    def bind_server(
        self,
        local_folder: str,
        url: str,
        username: str,
        password: str,
        name: str,
        **kwargs: Any,
    ) -> None:
        url = guess_server_url(url)
        if not url:
            self.setMessage.emit("CONNECTION_ERROR", "error")
            return

        try:
            return self._bind_server(
                local_folder, url, username, password, name, **kwargs
            )
        except RootAlreadyBindWithDifferentAccount as e:
            # Ask for the user
            values = [e.username, e.url]
            msgbox = QMessageBox(
                QMessageBox.Question,
                self._manager.app_name,
                Translator.get("ROOT_USED_WITH_OTHER_BINDING", values),
                QMessageBox.NoButton,
            )
            msgbox.addButton(Translator.get("CONTINUE"), QMessageBox.AcceptRole)
            cancel = msgbox.addButton(Translator.get("CANCEL"), QMessageBox.RejectRole)
            msgbox.exec_()
            if msgbox.clickedButton() == cancel:
                self.setMessage.emit("FOLDER_USED", "error")
                return

            kwargs["check_fs"] = False
            return self.bind_server(
                local_folder, url, username, password, name, **kwargs
            )
        except NotFound:
            error = "FOLDER_DOES_NOT_EXISTS"
        except InvalidDriveException:
            error = "INVALID_PARTITION"
        except Unauthorized:
            error = "UNAUTHORIZED"
        except FolderAlreadyUsed:
            error = "FOLDER_USED"
        except HTTPError:
            error = "CONNECTION_ERROR"
        except ConnectionError as e:
            if e.errno == 61:
                error = "CONNECTION_REFUSED"
            else:
                error = "CONNECTION_ERROR"
        except:
            log.exception("Unexpected error")
            # Map error here
            error = "CONNECTION_UNKNOWN"
        self.setMessage.emit(error, "error")

    @pyqtSlot(str, str)
    def web_authentication(self, server_url: str, local_folder: str) -> None:
        # Handle the server URL
        url = guess_server_url(server_url)
        if not url:
            self.setMessage.emit("CONNECTION_ERROR", "error")
            return

        parts = urlsplit(url)
        server_url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, parts.query, parts.fragment)
        )

        # Handle the engine
        engine_type = parts.fragment or self._manager._get_default_server_type()

        try:
            # Handle local folder
            if not self._manager.check_local_folder_available(local_folder):
                raise FolderAlreadyUsed()

            # Connect to startup page
            status = self._connect_startup_page(server_url)
            # Server will send a 401 in case of anonymous user configuration
            # Should maybe only check for 404
            if status < 400 or status in (401, 500, 503):
                # Page exists, let's open authentication dialog
                callback_params = {
                    "local_folder": local_folder,
                    "server_url": server_url,
                    "engine_type": engine_type,
                }
                url = self._get_authentication_url(server_url)
                log.debug(
                    "Web authentication is available on server %s, "
                    "opening login window with URL %s",
                    server_url,
                    url,
                )
                self.openAuthenticationDialog.emit(url, callback_params)
                return
            else:
                # Startup page is not available
                log.debug(
                    "Web authentication not available on server %s, "
                    "falling back on basic authentication",
                    server_url,
                )
                return
        except FolderAlreadyUsed:
            error = "FOLDER_USED"
        except StartupPageConnectionError:
            error = "CONNECTION_ERROR"
        except:
            log.exception(
                "Unexpected error while trying to open" " web authentication window"
            )
            error = "CONNECTION_UNKNOWN"
        self.setMessage.emit(error, "error")

    def _connect_startup_page(self, server_url: str) -> int:
        # Take into account URL parameters
        parts = urlsplit(guess_server_url(server_url))
        url = urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path + "/" + Options.startup_page,
                parts.query,
                parts.fragment,
            )
        )

        # Remove any parameters from the original URL
        server_url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, "", parts.fragment)
        )

        try:
            log.debug(
                "Proxy configuration for startup page connection: %s",
                self._manager.proxy,
            )
            headers = {
                "X-Application-Name": self._manager.app_name,
                "X-Device-Id": self._manager.device_id,
                "X-Client-Version": self._manager.version,
                "User-Agent": (self._manager.app_name + "/" + self._manager.version),
            }
            timeout = STARTUP_PAGE_CONNECTION_TIMEOUT
            with requests.get(url, headers=headers, timeout=timeout) as resp:
                status = resp.status_code
        except:
            log.exception(
                "Error while trying to connect to Nuxeo Drive"
                " startup page with URL %s",
                url,
            )
            raise StartupPageConnectionError()
        log.debug("Status code for %s = %d", url, status)
        return status

    def update_token(self, engine: "Engine", token: str) -> None:
        engine.update_token(token)
        self.application.set_icon_state("idle")

    @pyqtSlot(str, str, result=bool)
    def set_server_ui(self, uid: str, server_ui: str) -> bool:
        log.debug("Setting ui to %s", server_ui)
        engine = self._get_engine(uid)
        if not engine:
            self.setMessage.emit("CONNECTION_UNKNOWN", "error")
            return False
        engine.set_ui(server_ui)
        return True

    @pyqtSlot(result=str)
    def get_proxy_settings(self) -> str:
        proxy = self._manager.proxy
        result = {
            "url": getattr(proxy, "url", None),
            "config": getattr(proxy, "category", None),
            "username": getattr(proxy, "username", None),
            "authenticated": getattr(proxy, "authenticated", 0) == 1,
            "password": getattr(proxy, "password", None),
            "port": getattr(proxy, "port", None),
            "pac_url": getattr(proxy, "pac_url", None),
        }
        return self._json(result)

    @pyqtSlot(str, str, bool, str, str, str, result=bool)
    def set_proxy_settings(
        self,
        config: str,
        host: str,
        authenticated: bool,
        username: str,
        password: str,
        pac_url: str,
    ) -> bool:
        proxy = get_proxy(
            category=config,
            url=host,
            authenticated=authenticated,
            pac_url=pac_url,
            username=username,
            password=password,
        )
        result = self._manager.set_proxy(proxy)
        if result:
            self.setMessage.emit(result, "error")
            return False
        else:
            self.setMessage.emit("PROXY_APPLIED", "success")
            return True

    @pyqtSlot(str, result=bool)
    def has_invalid_credentials(self, uid: str) -> bool:
        engine = self._get_engine(uid)
        return engine.has_invalid_credentials() if engine else False
