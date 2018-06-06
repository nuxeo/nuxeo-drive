# coding: utf-8
import calendar
import datetime
import json
import os.path
import sys
import time
import uuid
from logging import getLogger
from urllib.parse import urlparse

from PyQt5 import QtNetwork
from PyQt5.QtGui import QIcon
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineView, QWebEngineSettings
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QObject, QUrl, QByteArray, Qt
from PyQt5.QtNetwork import (QNetworkProxy, QNetworkProxyFactory,
                             QSslCertificate)
from PyQt5.QtWidgets import QDialog, QFileDialog, QVBoxLayout
from dateutil.tz import tzlocal
from nuxeo.exceptions import Unauthorized
from requests import ConnectionError

from .translator import Translator
from ..engine.activity import Action, FileAction
from ..engine.dao.sqlite import StateRow
from ..engine.engine import Engine
from ..engine.workers import Worker
from ..manager import FolderAlreadyUsed
from ..notification import Notification
from ..options import Options

log = getLogger(__name__)


class PromiseWrapper(QObject):
    def __init__(self, promise):
        super(PromiseWrapper, self).__init__()
        self._promise = promise

    @pyqtSlot()
    def run(self):
        self._promise.run()


class Promise(Worker):
    _promise_success = pyqtSignal(str, str)
    _promise_error = pyqtSignal(str, str)

    def __init__(self, runner, *args, **kwargs):
        self.uid = uuid.uuid1().hex
        self._runner = runner
        self._kwargs = kwargs
        self._args = args
        super(Promise, self).__init__(name='Promise_' + self.uid)
        self._result = None
        self._wrapper = PromiseWrapper(self)
        self._wrapper.moveToThread(self._thread)

    def moveToThread(self, QThread):
        # Prevent this object to be move to other threads
        pass

    @pyqtSlot(result=str)
    def _promise_uid(self):
        return self.uid

    @pyqtSlot()
    def start(self):
        self._thread.started.connect(self._wrapper.run)
        self._thread.start()

    def _execute(self):
        try:
            result = self._runner(*self._args, **self._kwargs)
            self._promise_success.emit(self.uid, result)
        except Exception as e:
            self._promise_error.emit(self.uid, str(e))


class WebDriveApi(QObject):

    def __init__(self, application, dlg=None):
        super(WebDriveApi, self).__init__()
        self._manager = application.manager
        self.application = application
        self.dialog = dlg
        self.last_url = None

    def _json_default(self, obj):
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

    def _json(self, obj):
        # Avoid to fail on non serializable object
        return json.dumps(obj, default=self._json_default)

    def _export_engine(self, engine):
        if not engine:
            return {}

        bind = engine.get_binder()
        return {
            'uid': engine.uid,
            'type': engine.type,
            'name': engine.name,
            'offline': engine.is_offline(),
            'metrics': engine.get_metrics(),
            'started': engine.is_started(),
            'syncing': engine.is_syncing(),
            'paused': engine.is_paused(),
            'local_folder': engine.local_folder,
            'queue': engine.get_queue_manager().get_metrics(),
            'web_authentication': bind.web_authentication,
            'server_url': bind.server_url,
            'default_ui': engine._ui,
            'ui': engine._force_ui or engine._ui,
            'username': bind.username,
            'need_password_update': bind.pwd_update_required,
            'initialized': bind.initialized,
            'server_version': bind.server_version,
            'threads': self._get_threads(engine),
        }

    def get_date_from_sqlite(self, d):
        format_date = '%Y-%m-%d %H:%M:%S'
        try:
            return datetime.datetime.strptime(str(d.split('.')[0]), format_date)
        except BaseException:
            return 0

    def get_timestamp_from_date(self, d):
        if d == 0:
            return 0
        return int(calendar.timegm(d.timetuple()))

    def _export_state(self, state):
        if state is None:
            return None

        result = dict(state=state.pair_state,
                      last_sync_date='',
                      last_sync_direction='upload')

        # Last sync in sec
        current_time = int(time.time())
        date_time = self.get_date_from_sqlite(state.last_sync_date)
        sync_time = self.get_timestamp_from_date(date_time)
        if state.last_local_updated > state.last_remote_updated:
            result['last_sync_direction'] = 'download'
        result['last_sync'] = current_time - sync_time
        if date_time != 0:
            # As date_time is in UTC
            result['last_sync_date'] = Translator.format_datetime(date_time + tzlocal()._dst_offset)

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

    def _export_action(self, action):
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

    def _export_worker(self, worker):
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

    def _get_threads(self, engine):
        result = []
        for thread in engine.get_threads():
            result.append(self._export_worker(thread.worker))
        return result

    def _get_engine(self, uid):
        engines = self._manager.get_engines()
        return engines.get(uid)

    @pyqtSlot()
    def retry(self):
        self.dialog.load(self.last_url, self)

    @pyqtSlot(str, int, str, result=str)
    def get_last_files(self, uid, number, direction):
        engine = self._get_engine(str(uid))
        result = []
        if engine is not None:
            for state in engine.get_last_files(number, str(direction)):
                result.append(self._export_state(state))
        return self._json(result)

    @pyqtSlot(str, str, result=QObject)
    def update_password_async(self, uid, password):
        return Promise(self._update_password, uid, password)

    def _update_password(self, uid, password):
        """
        Convert password from unicode to string to support utf-8 character
        """
        try:
            time.sleep(5.0)
            engine = self._get_engine(str(uid))
            if engine is None:
                return ''
            engine.update_password(password)
            return ''
        except FolderAlreadyUsed:
            return 'FOLDER_USED'
        except Unauthorized:
            return 'UNAUTHORIZED'
        except ConnectionError as e:
            if e.errno == 61:
                return 'CONNECTION_REFUSED'
            return 'CONNECTION_ERROR'
        except:
            log.exception('Unexpected error')
            # Map error here
            return 'CONNECTION_UNKNOWN'

    @pyqtSlot(result=str)
    def get_tracker_id(self):
        return self._manager.get_tracker_id()

    @pyqtSlot(str)
    def set_language(self, locale):
        try:
            Translator.set(str(locale))
        except RuntimeError:
            log.exception('Set language error')

    @pyqtSlot(str)
    def trigger_notification(self, id_):
        self._manager.notification_service.trigger_notification(str(id_))

    @pyqtSlot(str)
    def discard_notification(self, id_):
        self._manager.notification_service.discard_notification(str(id_))

    @staticmethod
    def _export_notification(notif):
        return {
            'level': notif.level,
            'uid': notif.uid,
            'title': notif.title,
            'description': notif.description,
            'discardable': notif.is_discardable(),
            'discard': notif.is_discard(),
            'systray': notif.is_systray(),
            'replacements': notif.get_replacements(),
        }

    def _export_notifications(self, notifs):
        return [self._export_notification(notif) for notif in notifs.values()]

    @pyqtSlot(str, result=str)
    def get_notifications(self, engine_uid):
        engine_uid = str(engine_uid)
        center = self._manager.notification_service
        notif = self._export_notifications(center.get_notifications(engine_uid))
        return self._json(notif)

    @pyqtSlot(result=str)
    def get_languages(self):
        try:
            return self._json(Translator.languages())
        except RuntimeError:
            log.exception('Get language error')
            return ''

    @pyqtSlot(result=str)
    def get_translations(self):
        try:
            return self._json(Translator.translations())
        except RuntimeError:
            log.exception('Get translations error')
            return ''

    @pyqtSlot(result=str)
    def locale(self):
        try:
            return Translator.locale()
        except RuntimeError as e:
            log.exception('Get locale error')
            return ''

    @pyqtSlot(result=str)
    def get_update_status(self):
        return self._json(self._manager.updater.last_status)

    @pyqtSlot(result=str)
    def get_os_version(self):
        return sys.platform

    @pyqtSlot(str)
    def app_update(self, version):
        self._manager.updater.update(version)

    @pyqtSlot(str, result=str)
    def get_actions(self, uid):
        engine = self._get_engine(str(uid))
        result = []
        if engine is not None:
            for count, thread in enumerate(engine.get_threads(), 1):
                action = thread.worker.action
                # The filter should be configurable
                if isinstance(action, FileAction):
                    result.append(self._export_action(action))
                if count == 4:
                    break
        return self._json(result)

    @pyqtSlot(str, result=str)
    def get_threads(self, uid):
        engine = self._get_engine(str(uid))
        return self._json(self._get_threads(engine) if engine else [])

    @pyqtSlot(str, result=str)
    def get_errors(self, uid):
        result = []
        engine = self._get_engine(str(uid))
        if engine:
            for conflict in engine.get_errors():
                result.append(self._export_state(conflict))
        return self._json(result)

    @pyqtSlot(result=bool)
    def is_frozen(self):
        return Options.is_frozen

    @pyqtSlot(str, str)
    def show_metadata(self, uid, ref):
        engine = self._get_engine(str(uid))
        if engine:
            path = engine.local.abspath(str(ref))
            self.application.show_metadata(path)

    @pyqtSlot(str, result=str)
    def get_unsynchronizeds(self, uid):
        result = []
        engine = self._get_engine(str(uid))
        if engine:
            for conflict in engine.get_dao().get_unsynchronizeds():
                result.append(self._export_state(conflict))
        return self._json(result)

    @pyqtSlot(str, result=str)
    def get_conflicts(self, uid):
        result = []
        engine = self._get_engine(str(uid))
        if engine:
            for conflict in engine.get_conflicts():
                result.append(self._export_state(conflict))
        return self._json(result)

    @pyqtSlot(result=str)
    def get_infos(self):
        return self._json(self._manager.get_metrics())

    @pyqtSlot(str, result=str)
    def is_syncing(self, uid):
        engine = self._get_engine(str(uid))
        if not engine:
            return 'ERROR'
        if engine.is_syncing():
            return 'syncing'
        return 'synced'

    @pyqtSlot(bool)
    def set_direct_edit_auto_lock(self, value):
        self._manager.set_direct_edit_auto_lock(value)

    @pyqtSlot(result=bool)
    def get_direct_edit_auto_lock(self):
        return self._manager.get_direct_edit_auto_lock()

    @pyqtSlot(bool)
    def set_auto_start(self, value):
        self._manager.set_auto_start(value)

    @pyqtSlot(result=bool)
    def get_auto_start(self):
        return self._manager.get_auto_start()

    @pyqtSlot(bool)
    def set_auto_update(self, value):
        self._manager.set_auto_update(value)

    @pyqtSlot(result=bool)
    def get_auto_update(self):
        return self._manager.get_auto_update()

    @pyqtSlot(bool)
    def set_beta_channel(self, value):
        self._manager.set_beta_channel(value)

    @pyqtSlot(result=bool)
    def get_beta_channel(self):
        return self._manager.get_beta_channel()

    @pyqtSlot(result=str)
    def generate_report(self):
        try:
            return self._manager.generate_report()
        except Exception as e:
            log.exception('Report error')
            return '[ERROR] ' + str(e)

    @pyqtSlot(bool)
    def set_tracking(self, value):
        self._manager.set_tracking(value)

    @pyqtSlot(result=bool)
    def get_tracking(self):
        return self._manager.get_tracking()

    @pyqtSlot(str)
    def open_remote(self, uid):
        engine = self._get_engine(str(uid))
        if engine:
            engine.open_remote()

    @pyqtSlot(str)
    def open_report(self, path):
        self._manager.open_local_file(str(path), select=True)

    @pyqtSlot(str, str)
    def open_local(self, uid, path):
        uid = str(uid)
        path = str(path)
        log.trace('Opening local file %r', path)
        if not uid:
            self._manager.open_local_file(path)
        else:
            engine = self._get_engine(uid)
            if engine:
                filepath = engine.local.abspath(path)
                self._manager.open_local_file(filepath)

    @pyqtSlot()
    def show_activities(self):
        self.application.show_activities()

    @pyqtSlot(str)
    def show_conflicts_resolution(self, uid):
        engine = self._get_engine(str(uid))
        if engine:
            self.application.show_conflicts_resolution(engine)

    @pyqtSlot(str)
    def show_settings(self, page):
        page = str(page)
        log.debug('Show settings on page %s', page)
        self.application.show_settings(section=page or None)

    @pyqtSlot()
    def quit(self):
        try:
            self.application.quit()
        except:
            log.exception('Application exit error')

    @pyqtSlot(result=str)
    def get_engines(self):
        result = []
        for engine in self._manager.get_engines().values():
            if engine:
                result.append(self._export_engine(engine))
        return self._json(result)

    @pyqtSlot(str, result=str)
    def browse_folder(self, base_folder):
        local_folder_path = str(base_folder)
        # TODO Might isolate to a specific api
        dir_path = QFileDialog.getExistingDirectory(
            caption=Translator.get('BROWSE_DIALOG_CAPTION'),
            directory=base_folder)
        if dir_path:
            dir_path = str(dir_path)
            log.debug('Selected %r as the Nuxeo Drive folder location', dir_path)
            local_folder_path = dir_path
        return local_folder_path

    @pyqtSlot()
    def show_file_status(self):
        self.application.show_file_status()

    @pyqtSlot(result=str)
    def get_version(self):
        return self._manager.version

    @pyqtSlot(result=str)
    def get_update_url(self):
        if self._manager.get_beta_channel():
            return Options.beta_update_site_url
        return Options.update_site_url

    @pyqtSlot(int, int)
    def resize(self, width, height):
        if self.dialog:
            self.dialog.resize(width, height)


class TokenNetworkAccessManager(QtNetwork.QNetworkAccessManager):
    def __init__(self, application, token):
        super(TokenNetworkAccessManager, self).__init__()
        self.token = token

        if not Options.debug:
            cache = QtNetwork.QNetworkDiskCache(self)
            cache.setCacheDirectory(application.get_cache_folder())
            self.setCache(cache)

    def createRequest(self, operation, request, data):
        if self.token:
            request.setRawHeader(
                'X-Authentication-Token', QByteArray(self.token))

        return super(TokenNetworkAccessManager, self).createRequest(
            operation, request, data)


class DriveWebPage(QWebEnginePage):

    @pyqtSlot()
    def shouldInterruptJavaScript(self):
        return True

    def javaScriptConsoleMessage(self, level, msg, lineno, source):
        # type: (str, int, str) -> None
        """ Prints client console message in current output stream. """
        super(DriveWebPage, self).javaScriptConsoleMessage(level, msg, lineno, source)

        filename = source.split(os.path.sep)[-1]
        log.log(level, 'JS console(%s:%d): %s', filename, lineno, msg)


class WebDialog(QDialog):

    def __init__(
        self,
        application,
        page=None,
        title='Nuxeo Drive',
        api=None,
        token=None,
    ):
        super(WebDialog, self).__init__()
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon(application.get_window_icon()))
        self.view = QWebEngineView()
        self.frame = None
        self.page = DriveWebPage()
        self.api = api
        self.token = token
        self.request = None
        self.zoom_factor = application.osi.zoom_factor

        if Options.debug:
            self.view.settings().setAttribute(
                QWebEngineSettings.DeveloperExtrasEnabled, True)
        else:
            self.view.setContextMenuPolicy(Qt.NoContextMenu)

        self.setWindowFlags(Qt.WindowCloseButtonHint)
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.view)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.updateGeometry()
        self.view.setPage(self.page)
        self.networkManager = TokenNetworkAccessManager(application, token)

        if not Options.consider_ssl_errors:
            self.networkManager.sslErrors.connect(self._ssl_error_handler)

        # self.page.setNetworkAccessManager(self.networkManager)
        if page is not None:
            self.load(page, api, application)

    def load(self, page, api=None, application=None):
        if application is None and api is not None:
            application = api.application
        if api is None:
            self.api = WebDriveApi(application, self)
        else:
            api.dialog = self
            self.api = api
        if not page.startswith(('http', 'file://')):
            filename = application.get_htmlpage(page)
        else:
            filename = page
        # If connect to a remote page add the X-Authentication-Token
        if filename.startswith('http'):
            log.trace('Load web page %r', filename)
            self.request = url = QtNetwork.QNetworkRequest(QUrl(filename))
            if self.token is not None:
                url.setRawHeader('X-Authentication-Token',
                                 QByteArray(self.token))
            self._set_proxy(application.manager, server_url=page)
            self.api.last_url = filename
        else:
            self.request = None
            log.trace('Load web file %r', filename)
            url = QUrl.fromLocalFile(os.path.realpath(filename))
            url.setScheme('file')

        self.page.load(url)
        # self.attachJsApi()
        # self.frame.javaScriptWindowObjectCleared.connect(self.attachJsApi)
        self.activateWindow()

    def resize(self, width, height):
        super(WebDialog, self).resize(width * self.zoom_factor,
                                      height * self.zoom_factor)

    @staticmethod
    def _ssl_error_handler(reply, error_list):
        log.warning('--- Bypassing SSL errors listed below ---')
        for error in error_list:
            certificate = error.certificate()
            o = certificate.issuerInfo(QSslCertificate.Organization)
            cn = certificate.issuerInfo(QSslCertificate.CommonName)
            l = certificate.issuerInfo(QSslCertificate.LocalityName)
            ou = certificate.issuerInfo(QSslCertificate.OrganizationalUnitName)
            c = certificate.issuerInfo(QSslCertificate.CountryName)
            st = certificate.issuerInfo(QSslCertificate.StateOrProvinceName)
            log.warning(
                '%s, certificate: [o=%s, cn=%s, l=%s, ou=%s, c=%s, st=%s]',
                str(error.errorString()), o, cn, l, ou, c, st)
        reply.ignoreSslErrors()

    @staticmethod
    def _set_proxy(manager, server_url=None):
        proxy = manager.proxy
        if proxy.category == 'System':
            QNetworkProxyFactory.setUseSystemConfiguration(True)
            return

        if proxy.category == 'Manual':
            q_proxy = QNetworkProxy(QNetworkProxy.HttpProxy,
                                    hostName=proxy.host,
                                    port=int(proxy.port))
            if proxy.authenticated:
                q_proxy.setPassword(proxy.password)
                q_proxy.setUser(proxy.username)

        elif proxy.category == 'Automatic':
            proxy_url = proxy.settings(server_url)['http']
            parsed_url = urlparse(proxy_url)
            q_proxy = QNetworkProxy(QNetworkProxy.HttpProxy,
                                    hostName=parsed_url.hostname,
                                    port=parsed_url.port)
        else:
            q_proxy = QNetworkProxy(QNetworkProxy.NoProxy)

        QNetworkProxy.setApplicationProxy(q_proxy)

    @pyqtSlot()
    def attachJsApi(self):
        if self.frame is None:
            return
        self.frame.addToJavaScriptWindowObject('drive', self.api)
        self.frame.setZoomFactor(self.zoom_factor)
