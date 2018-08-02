# coding: utf-8
import re
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


def auth(cls: "Application", url: str) -> None:
    dialog = WebAuthenticationDialog(cls, url, cls.api)
    dialog.setWindowModality(Qt.NonModal)
    dialog.show()
