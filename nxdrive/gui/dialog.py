# coding: utf-8
import calendar
import json
import os.path
from datetime import datetime
from logging import getLogger
from time import struct_time, time
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode, urlparse, urlsplit, urlunsplit

from PyQt5.QtCore import QObject, QUrl, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QIcon
from PyQt5.QtNetwork import QNetworkProxy, QNetworkProxyFactory
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.QtWebEngineWidgets import (QWebEnginePage, QWebEngineSettings,
                                      QWebEngineView,
                                      QWebEngineCertificateError)
from PyQt5.QtWidgets import QDialog, QVBoxLayout
from dateutil.tz import tzlocal

from .translator import Translator
from ..constants import TOKEN_PERMISSION
from ..engine.activity import Action, FileAction
from ..engine.dao.sqlite import StateRow
from ..engine.engine import Engine
from ..engine.workers import Worker
from ..notification import Notification
from ..options import Options
from ..utils import find_resource, get_device, guess_server_url

__all__ = ("QMLDriveApi", "WebDialog")

log = getLogger(__name__)


class QMLDriveApi(QObject):
    setMessage = pyqtSignal(str, str)

    def __init__(
        self, application: "Application", dlg: Union[QDialog, "QQuickView"] = None
    ) -> None:
        super().__init__()
        self._manager = application.manager
        self.application = application
        self.dialog = dlg
        self.last_url = None

    def _json_default(self, obj: Any) -> Any:
        if isinstance(obj, Action):
            return self._export_action(obj)
        if isinstance(obj, Engine):
            return self._export_engine(obj)
        if isinstance(obj, Notification):
            return self._export_notification(obj)
        if isinstance(obj, StateRow):
            return self._export_state(obj)
        if isinstance(obj, Worker):
            return self._export_worker(obj)
        return obj

    def _json(self, obj: Any) -> Any:
        # Avoid to fail on non serializable object
        return json.dumps(obj, default=self._json_default)

    def _export_engine(self, engine: Engine) -> Dict[str, Any]:
        if not engine:
            return {}

        bind = engine.get_binder()
        return {
            "uid": engine.uid,
            "type": engine.type,
            "name": engine.name,
            "offline": engine.is_offline(),
            "metrics": engine.get_metrics(),
            "started": engine.is_started(),
            "syncing": engine.is_syncing(),
            "paused": engine.is_paused(),
            "local_folder": engine.local_folder,
            "queue": engine.get_queue_manager().get_metrics(),
            "web_authentication": bind.web_authentication,
            "server_url": bind.server_url,
            "default_ui": engine._ui,
            "ui": engine._force_ui or engine._ui,
            "username": bind.username,
            "need_password_update": bind.pwd_update_required,
            "initialized": bind.initialized,
            "server_version": bind.server_version,
            "threads": self._get_threads(engine),
        }

    def get_date_from_sqlite(self, d: str) -> Optional[struct_time]:
        format_date = "%Y-%m-%d %H:%M:%S"
        try:
            return datetime.strptime(str(d.split(".")[0]), format_date)
        except BaseException:
            return None

    def get_timestamp_from_date(self, d: struct_time = None) -> int:
        if not d:
            return 0
        return int(calendar.timegm(d.timetuple()))

    def _export_state(self, state: "DocPair" = None) -> Dict[str, Any]:
        if state is None:
            return {}

        result = dict(
            state=state.pair_state, last_sync_date="", last_sync_direction="upload"
        )

        # Last sync in sec
        current_time = int(time())
        date_time = self.get_date_from_sqlite(state.last_sync_date)
        sync_time = self.get_timestamp_from_date(date_time)
        if state.last_local_updated or "" > state.last_remote_updated or "":
            result["last_sync_direction"] = "download"
        result["last_sync"] = current_time - sync_time
        if date_time:
            # As date_time is in UTC
            result["last_sync_date"] = Translator.format_datetime(
                date_time + tzlocal()._dst_offset
            )

        result["name"] = state.local_name
        if state.local_name is None:
            result["name"] = state.remote_name
        result["remote_name"] = state.remote_name
        result["last_error"] = state.last_error
        result["local_path"] = state.local_path
        result["local_parent_path"] = state.local_parent_path
        result["remote_ref"] = state.remote_ref
        result["folderish"] = state.folderish
        result["last_transfer"] = state.last_transfer
        if result["last_transfer"] is None:
            result["last_transfer"] = result["last_sync_direction"]
        result["id"] = state.id
        return result

    def _export_action(self, action: Action) -> Dict[str, Any]:
        result = dict()
        result["name"] = action.type
        percent = action.get_percent()
        if percent:
            result["percent"] = percent
        if isinstance(action, FileAction):
            result["size"] = action.size
            result["filename"] = action.filename
            result["filepath"] = action.filepath
        return result

    def _export_worker(self, worker: Worker) -> Dict[str, Any]:
        result = dict()
        action = worker.action
        if action is None:
            result["action"] = None
        else:
            result["action"] = self._export_action(action)
        result["thread_id"] = worker._thread_id
        result["name"] = worker._name
        result["paused"] = worker.is_paused()
        result["started"] = worker.is_started()
        return result

    def _get_threads(self, engine: Engine) -> Dict[str, Any]:
        result = []
        for thread in engine.get_threads():
            result.append(self._export_worker(thread.worker))
        return result

    def _get_engine(self, uid: str) -> Engine:
        engines = self._manager.get_engines()
        return engines.get(uid)

    @pyqtSlot()
    def retry(self) -> None:
        self.dialog.load(self.last_url, self)

    def get_last_files(
        self, uid: str, number: int, direction: str
    ) -> List[Dict[str, Any]]:
        engine = self._get_engine(uid)
        result = []
        if engine is not None:
            for state in engine.get_last_files(number, direction):
                result.append(self._export_state(state))
        return result

    @pyqtSlot(result=str)
    def get_tracker_id(self) -> str:
        return self._manager.get_tracker_id()

    @pyqtSlot(str)
    def set_language(self, locale: str) -> None:
        try:
            Translator.set(locale)
        except RuntimeError as e:
            log.exception("Set language error")

    @pyqtSlot(str)
    def trigger_notification(self, id_: str) -> None:
        self._manager.notification_service.trigger_notification(id_)

    @pyqtSlot(str)
    def discard_notification(self, id_) -> None:
        self._manager.notification_service.discard_notification(id_)

    @staticmethod
    def _export_notification(notif: Notification) -> Dict[str, Any]:
        return {
            "level": notif.level,
            "uid": notif.uid,
            "title": notif.title,
            "description": notif.description,
            "discardable": notif.is_discardable(),
            "discard": notif.is_discard(),
            "systray": notif.is_systray(),
            "replacements": notif.get_replacements(),
        }

    def _export_notifications(
        self, notifs: Dict[str, Notification]
    ) -> List[Dict[str, Any]]:
        return [self._export_notification(notif) for notif in notifs.values()]

    @pyqtSlot(str, result=str)
    def get_notifications(self, engine_uid: str) -> str:
        engine_uid = engine_uid
        center = self._manager.notification_service
        notif = self._export_notifications(center.get_notifications(engine_uid))
        return self._json(notif)

    @pyqtSlot(result=str)
    def get_update_status(self) -> str:
        return self._json(self._manager.updater.last_status)

    @pyqtSlot(str)
    def app_update(self, version: str) -> None:
        self._manager.updater.update(version)

    @pyqtSlot(str, result=str)
    def get_actions(self, uid: str) -> str:
        engine = self._get_engine(uid)
        result = []
        if engine:
            for count, thread in enumerate(engine.get_threads(), 1):
                action = thread.worker.action
                # The filter should be configurable
                if isinstance(action, FileAction):
                    result.append(self._export_action(action))
                if count == 4:
                    break
        return self._json(result)

    @pyqtSlot(str, result=str)
    def get_threads(self, uid: str) -> str:
        engine = self._get_engine(uid)
        return self._json(self._get_threads(engine) if engine else [])

    def get_errors(self, uid: str) -> List[Dict[str, Any]]:
        result = []
        engine = self._get_engine(uid)
        if engine:
            for conflict in engine.get_errors():
                result.append(self._export_state(conflict))
        return result

    @pyqtSlot(result=bool)
    def is_frozen(self) -> bool:
        return Options.is_frozen

    @pyqtSlot(str, str)
    def show_metadata(self, uid: str, ref: str) -> None:
        engine = self._get_engine(uid)
        if engine:
            path = engine.local.abspath(ref)
            self.application.show_metadata(path)

    def get_unsynchronizeds(self, uid: str) -> List[Dict[str, Any]]:
        result = []
        engine = self._get_engine(uid)
        if engine:
            for conflict in engine.get_dao().get_unsynchronizeds():
                result.append(self._export_state(conflict))
        return result

    def get_conflicts(self, uid: str) -> List[Dict[str, Any]]:
        result = []
        engine = self._get_engine(uid)
        if engine:
            for conflict in engine.get_conflicts():
                result.append(self._export_state(conflict))
        return result

    @pyqtSlot(result=str)
    def get_infos(self) -> str:
        return self._json(self._manager.get_metrics())

    @pyqtSlot(str, result=str)
    def is_syncing(self, uid: str) -> str:
        engine = self._get_engine(uid)
        if not engine:
            return "ERROR"
        if engine.is_syncing():
            return "syncing"
        return "synced"

    @pyqtSlot(bool)
    def set_direct_edit_auto_lock(self, value: bool) -> None:
        self._manager.set_direct_edit_auto_lock(value)

    @pyqtSlot(result=bool)
    def get_direct_edit_auto_lock(self) -> bool:
        return self._manager.get_direct_edit_auto_lock()

    @pyqtSlot(bool)
    def set_auto_start(self, value: bool) -> None:
        self._manager.set_auto_start(value)

    @pyqtSlot(result=bool)
    def get_auto_start(self) -> bool:
        return self._manager.get_auto_start()

    @pyqtSlot(bool)
    def set_auto_update(self, value: bool) -> None:
        self._manager.set_auto_update(value)

    @pyqtSlot(result=bool)
    def get_auto_update(self) -> bool:
        return self._manager.get_auto_update()

    @pyqtSlot(bool)
    def set_beta_channel(self, value: bool) -> None:
        self._manager.set_beta_channel(value)

    @pyqtSlot(result=bool)
    def get_beta_channel(self) -> bool:
        return self._manager.get_beta_channel()

    @pyqtSlot(result=str)
    def generate_report(self) -> str:
        try:
            return self._manager.generate_report()
        except Exception as e:
            log.exception("Report error")
            return "[ERROR] " + str(e)

    @pyqtSlot(bool)
    def set_tracking(self, value: bool) -> None:
        self._manager.set_tracking(value)

    @pyqtSlot(result=bool)
    def get_tracking(self) -> bool:
        return self._manager.get_tracking()

    @pyqtSlot(str)
    def open_remote(self, uid: str) -> None:
        engine = self._get_engine(uid)
        if engine:
            engine.open_remote()

    @pyqtSlot(str)
    def open_report(self, path: str) -> None:
        self._manager.open_local_file(path, select=True)

    @pyqtSlot(str, str)
    def open_local(self, uid: str, path: str) -> None:
        log.trace("Opening local file %r", path)
        if not uid:
            self._manager.open_local_file(path)
        else:
            engine = self._get_engine(uid)
            if engine:
                filepath = engine.local.abspath(path)
                self._manager.open_local_file(filepath)

    @pyqtSlot(str)
    def show_conflicts_resolution(self, uid: str) -> None:
        engine = self._get_engine(uid)
        if engine:
            self.application.show_conflicts_resolution(engine)

    @pyqtSlot(str)
    def show_settings(self, page: str) -> None:
        log.debug("Show settings on page %s", page)
        self.application.show_settings(section=page or None)

    @pyqtSlot()
    def quit(self) -> None:
        try:
            self.application.quit()
        except:
            log.exception("Application exit error")

    @pyqtSlot(result=str)
    def get_version(self) -> str:
        return self._manager.version

    @pyqtSlot(result=str)
    def get_update_url(self) -> str:
        if self._manager.get_beta_channel():
            return Options.beta_update_site_url
        return Options.update_site_url

    @pyqtSlot(int, int)
    def resize(self, width: int, height: int) -> None:
        if self.dialog:
            self.dialog.resize(width, height)

    @pyqtSlot(str)
    def web_update_token(self, uid: str) -> None:
        try:
            engine = self._get_engine(uid)
            if not engine:
                self.setMessage.emit("CONNECTION_UNKNOWN", "error")
                return
            params = urlencode({"updateToken": True})
            url = self._get_authentication_url(engine.server_url) + "&" + params
            callback_params = {"engine": engine}
            log.debug("Opening login window for token update with URL %s", url)
            self.application._open_authentication_dialog(url, callback_params)
        except:
            log.exception(
                "Unexpected error while trying to open web"
                " authentication window for token update"
            )
            self.setMessage.emit("CONNECTION_UNKNOWN", "error")

    def _get_authentication_url(self, server_url: str) -> str:
        token_params = {
            "deviceId": self._manager.device_id,
            "applicationName": self._manager.app_name,
            "permission": TOKEN_PERMISSION,
            "deviceDescription": get_device(),
            "forceAnonymousLogin": "true",
        }

        # Handle URL parameters
        parts = urlsplit(guess_server_url(server_url))
        path = (parts.path + "/" + Options.startup_page).replace("//", "/")
        params = (
            parts.query + "&" + urlencode(token_params)
            if parts.query
            else urlencode(token_params)
        )
        url = urlunsplit((parts.scheme, parts.netloc, path, params, parts.fragment))

        return url


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
