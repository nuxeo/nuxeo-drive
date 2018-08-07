# coding: utf-8
import json
from contextlib import suppress
from logging import getLogger

from PyQt5.QtCore import Qt, QUrl

from .dialog import WebDialog
from ..api import QMLDriveApi
from ...translator import Translator

__all__ = ("auth",)

log = getLogger(__name__)


class WebAuthenticationDialog(WebDialog):
    def __init__(self, application: "Application", url: str, api: QMLDriveApi) -> None:
        title = Translator.get("WEB_AUTHENTICATION_WINDOW_TITLE")
        super().__init__(application, url, title=title, api=api)
        self.resize(1000, 800)
        self.page.urlChanged.connect(self._read_page)

    def handle_login(self, text: str) -> None:
        with suppress(json.decoder.JSONDecodeError):
            content = json.loads(text)
            self.api.handle_token(content["token"], content["username"])
            self.close()

    def _read_page(self, url: QUrl) -> None:
        self.page.toPlainText(self.handle_login)


def auth(cls: "Application", url: str) -> None:
    dialog = WebAuthenticationDialog(cls, url, cls.api)
    dialog.setWindowModality(Qt.NonModal)
    dialog.show()
