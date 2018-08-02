# coding: utf-8
import os.path
from logging import getLogger
from urllib.parse import urlparse

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QIcon
from PyQt5.QtNetwork import QNetworkProxy, QNetworkProxyFactory
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.QtWebEngineWidgets import (
    QWebEngineCertificateError,
    QWebEnginePage,
    QWebEngineSettings,
    QWebEngineView,
)
from PyQt5.QtWidgets import QDialog, QVBoxLayout

from ..api import QMLDriveApi
from ...options import Options
from ...utils import find_resource

__all__ = ("WebDialog",)

log = getLogger(__name__)


class TokenRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, token: str) -> None:
        super().__init__()
        self.token = token

    def interceptRequest(self, info):
        if self.token:
            info.setHttpHeader("X-Authentication-Token", self.token)


class DriveWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        msg: str,
        lineno: int,
        source: str,
    ) -> None:
        """ Prints client console message in current output stream. """
        super().javaScriptConsoleMessage(level, msg, lineno, source)

        filename = source.split(os.path.sep)[-1]
        log.log(level, "JS console(%s:%d): %s", filename, lineno, msg)

    def certificateError(self, certificate_error: QWebEngineCertificateError) -> bool:
        """ Allows the SSL error to rise or not.

            Upon encountering an SSL error, the web page will call this method.
            If it returns True, the web page ignores the error, otherwise it will
            take it into account.
        """
        log.warning(certificate_error.errorDescription())
        return not Options.consider_ssl_errors


class WebDialog(QDialog):
    def __init__(
        self,
        application: "Application",
        page: str = None,
        title: str = "Nuxeo Drive",
        api: QMLDriveApi = None,
        token: str = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon(application.get_window_icon()))
        self.view = QWebEngineView()
        self.page = DriveWebPage()
        self.api = api
        self.token = token
        self.request = None
        self.zoom_factor = application.osi.zoom_factor

        if Options.debug:
            self.view.settings().setAttribute(
                QWebEngineSettings.DeveloperExtrasEnabled, True
            )
        else:
            self.view.setContextMenuPolicy(Qt.NoContextMenu)

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.view)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.updateGeometry()
        self.view.setPage(self.page)
        log.trace("Web Engine cache path is %s", self.page.profile().cachePath())

        self.request_interceptor = TokenRequestInterceptor(self.token)

        if page:
            self.load(page, api, application)

    def load(
        self, page: str, api: QMLDriveApi = None, application: "Application" = None
    ) -> None:
        if application is None and api is not None:
            application = api.application
        if api is None:
            self.api = QMLDriveApi(application, self)
        else:
            api.dialog = self
            self.api = api
        if not page.startswith(("http", "file://")):
            filename = find_resource(Options.theme, page).replace("\\", "/")
        else:
            filename = page
        # If connect to a remote page add the X-Authentication-Token
        if filename.startswith("http"):
            log.trace("Load web page %r", filename)
            self.request = url = QUrl(filename)
            self._set_proxy(application.manager, server_url=page)
            self.api.last_url = filename
        else:
            self.request = None
            log.trace("Load web file %r", filename)
            url = QUrl.fromLocalFile(os.path.realpath(filename))
            url.setScheme("file")

        self.page.profile().setRequestInterceptor(self.request_interceptor)
        self.page.load(url)
        self.activateWindow()

    def resize(self, width: int, height: int) -> None:
        super(WebDialog, self).resize(
            width * self.zoom_factor, height * self.zoom_factor
        )

    @staticmethod
    def _set_proxy(manager: "Manager", server_url: str = None) -> None:
        proxy = manager.proxy
        if proxy.category == "System":
            QNetworkProxyFactory.setUseSystemConfiguration(True)
            return

        if proxy.category == "Manual":
            q_proxy = QNetworkProxy(
                QNetworkProxy.HttpProxy, hostName=proxy.host, port=int(proxy.port)
            )
            if proxy.authenticated:
                q_proxy.setPassword(proxy.password)
                q_proxy.setUser(proxy.username)

        elif proxy.category == "Automatic":
            proxy_url = proxy.settings(server_url)["http"]
            parsed_url = urlparse(proxy_url)
            q_proxy = QNetworkProxy(
                QNetworkProxy.HttpProxy,
                hostName=parsed_url.hostname,
                port=parsed_url.port,
            )
        else:
            q_proxy = QNetworkProxy(QNetworkProxy.NoProxy)

        QNetworkProxy.setApplicationProxy(q_proxy)
