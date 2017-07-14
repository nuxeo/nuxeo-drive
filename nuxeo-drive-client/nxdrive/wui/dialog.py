# coding: utf-8
import calendar
import datetime
import json
import sys
import time
import urllib2
import uuid
from os.path import realpath

from PyQt4 import QtCore, QtGui, QtNetwork, QtWebKit
from PyQt4.QtNetwork import QNetworkProxy, QNetworkProxyFactory, QSslCertificate
from dateutil.tz import tzlocal

from nxdrive.client.base_automation_client import Unauthorized
from nxdrive.client.common import DEFAULT_BETA_SITE_URL
from nxdrive.engine.activity import Action, FileAction
from nxdrive.engine.dao.sqlite import StateRow
from nxdrive.engine.engine import Engine
from nxdrive.engine.workers import Worker
from nxdrive.logging_config import get_logger
from nxdrive.manager import DEFAULT_UPDATE_SITE_URL, FolderAlreadyUsed
from nxdrive.notification import Notification
from nxdrive.updater import UPDATE_STATUS_UNAVAILABLE_SITE
from nxdrive.wui.translator import Translator

log = get_logger(__name__)


class PromiseWrapper(QtCore.QObject):
    def __init__(self, promise):
        super(PromiseWrapper, self).__init__()
        self._promise = promise

    @QtCore.pyqtSlot()
    def run(self):
        self._promise.run()


class Promise(Worker):
    _promise_success = QtCore.pyqtSignal(str, str)
    _promise_error = QtCore.pyqtSignal(str, str)

    def __init__(self, runner, *args, **kwargs):
        self._uid = uuid.uuid1().hex
        self._runner = runner
        self._kwargs = kwargs
        self._args = args
        super(Promise, self).__init__(name="Promise_" + self._uid)
        self._result = None
        self._wrapper = PromiseWrapper(self)
        self._wrapper.moveToThread(self._thread)

    def moveToThread(self, QThread):
        # Prevent this object to be move to other threads
        pass

    @QtCore.pyqtSlot(result=str)
    def _promise_uid(self):
        return self._uid

    @QtCore.pyqtSlot()
    def start(self):
        self._thread.started.connect(self._wrapper.run)
        self._thread.start()

    def _execute(self):
        try:
            result = self._runner(*self._args, **self._kwargs)
            self._promise_success.emit(self._uid, result)
        except Exception as e:
            self._promise_error.emit(self._uid, repr(e))


class WebDriveApi(QtCore.QObject):

    def __init__(self, application, dlg=None):
        super(WebDriveApi, self).__init__()
        self._manager = application.manager
        self._application = application
        self._dialog = dlg
        self._last_url = None

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

    def get_dialog(self):
        return self._dialog

    def set_dialog(self, dlg):
        self._dialog = dlg

    def _export_engine(self, engine):
        result = dict()
        if engine is None:
            return result
        result["uid"] = engine._uid
        result["type"] = engine._type
        result["name"] = engine._name
        result["offline"] = engine.is_offline()
        result["metrics"] = engine.get_metrics()
        result["started"] = engine.is_started()
        result["syncing"] = engine.is_syncing()
        result["paused"] = engine.is_paused()
        result["local_folder"] = engine._local_folder
        result["queue"] = engine.get_queue_manager().get_metrics()
        # TODO Make it more generic
        bind = engine.get_binder()
        result["web_authentication"] = bind.web_authentication
        result["server_url"] = bind.server_url
        result["username"] = bind.username
        result["need_password_update"] = bind.pwd_update_required
        result["initialized"] = bind.initialized
        result["server_version"] = bind.server_version
        result["threads"] = self._get_threads(engine)
        return result

    def get_date_from_sqlite(self, d):
        format_date = '%Y-%m-%d %H:%M:%S'
        try:
            return datetime.datetime.strptime(str(d.split('.')[0]), format_date)
        except StandardError:
            return 0

    def get_timestamp_from_date(self, d):
        if d == 0:
            return 0
        return int(calendar.timegm(d.timetuple()))

    def get_timestamp_from_sqlite(self, d):
        return int(calendar.timegm(self.get_date_from_sqlite(d).timetuple()))

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
        action = worker.get_action()
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
        try:
            return engines[uid]
        except KeyError:
            return None

    def set_last_url(self, url):
        self._last_url = url

    @QtCore.pyqtSlot(result=str)
    def get_last_url(self):
        return self._last_url

    @QtCore.pyqtSlot()
    def retry(self):
        self._dialog.load(self._last_url, self)

    @QtCore.pyqtSlot(str, int, str, result=str)
    def get_last_files(self, uid, number, direction):
        engine = self._get_engine(str(uid))
        result = []
        if engine is not None:
            for state in engine.get_last_files(number, str(direction)):
                result.append(self._export_state(state))
        return self._json(result)

    @QtCore.pyqtSlot(str, str, result=QtCore.QObject)
    def update_password_async(self, uid, password):
        return Promise(self._update_password, uid, password)

    def _update_password(self, uid, password, result=str):
        """
        Convert password from unicode to string to support utf-8 character
        """
        if isinstance(password, QtCore.QString):
            password = unicode(password).encode('utf-8')
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
        except urllib2.URLError as e:
            if e.errno == 61:
                return 'CONNECTION_REFUSED'
            return 'CONNECTION_ERROR'
        except:
            log.exception('Unexpected error')
            # Map error here
            return 'CONNECTION_UNKNOWN'

    @QtCore.pyqtSlot()
    def close(self):
        self._dialog.close()

    @QtCore.pyqtSlot(result=str)
    def get_tracker_id(self):
        return self._manager.get_tracker_id()

    @QtCore.pyqtSlot(result=str)
    def get_appname(self):
        return self._manager.get_appname()

    @QtCore.pyqtSlot(str)
    def set_language(self, locale):
        try:
            Translator.set(str(locale))
        except RuntimeError as e:
            log.exception(repr(e))

    @QtCore.pyqtSlot(str)
    def trigger_notification(self, id_):
        self._manager.get_notification_service().trigger_notification(str(id_))

    @QtCore.pyqtSlot(str)
    def discard_notification(self, id_):
        self._manager.get_notification_service().discard_notification(str(id_))

    @staticmethod
    def _export_notification(notif):
        result = dict()
        result["level"] = notif.get_level()
        result["uid"] = notif.get_uid()
        result["title"] = notif.get_title()
        result["description"] = notif.get_description()
        result["discardable"] = notif.is_discardable()
        result["discard"] = notif.is_discard()
        result["systray"] = notif.is_systray()
        result["replacements"] = notif.get_replacements()
        return result

    def _export_notifications(self, notifs):
        result = []
        for notif in notifs.values():
            result.append(self._export_notification(notif))
        return result

    @QtCore.pyqtSlot(str, result=str)
    def get_notifications(self, engine_uid):
        engine_uid = str(engine_uid)
        center = self._manager.get_notification_service()
        notif = self._export_notifications(center.get_notifications(engine_uid))
        return self._json(notif)

    @QtCore.pyqtSlot(result=str)
    def get_languages(self):
        try:
            return self._json(Translator.languages())
        except RuntimeError as e:
            log.exception(repr(e))
            return ''

    @QtCore.pyqtSlot(result=str)
    def locale(self):
        try:
            return Translator.locale()
        except RuntimeError as e:
            log.exception(repr(e))
            return ''

    @QtCore.pyqtSlot(result=str)
    def get_update_status(self):
        status = UPDATE_STATUS_UNAVAILABLE_SITE, None
        updater = self._manager.get_updater()
        if updater:
            status = updater.get_status()
        return self._json(status)

    @QtCore.pyqtSlot(str)
    def app_update(self, version):
        updater = self._manager.get_updater()
        if updater:
            updater.update(str(version))

    @QtCore.pyqtSlot(str, result=str)
    def get_actions(self, uid):
        engine = self._get_engine(str(uid))
        result = []
        if engine is not None:
            for count, thread in enumerate(engine.get_threads(), 1):
                action = thread.worker.get_action()
                # The filter should be configurable
                if isinstance(action, FileAction):
                    result.append(self._export_action(action))
                if count == 4:
                    break
        return self._json(result)

    @QtCore.pyqtSlot(str, result=str)
    def get_threads(self, uid):
        engine = self._get_engine(str(uid))
        return self._json(self._get_threads(engine) if engine else [])

    @QtCore.pyqtSlot(str, result=str)
    def get_errors(self, uid):
        result = []
        engine = self._get_engine(str(uid))
        if engine:
            for conflict in engine.get_errors():
                result.append(self._export_state(conflict))
        return self._json(result)

    @QtCore.pyqtSlot(str, str)
    def show_metadata(self, uid, ref):
        engine = self._get_engine(str(uid))
        if engine:
            path = engine.get_abspath(unicode(ref))
            self._application.show_metadata(path)

    @QtCore.pyqtSlot(str, result=str)
    def get_unsynchronizeds(self, uid):
        result = []
        engine = self._get_engine(str(uid))
        if engine:
            for conflict in engine.get_dao().get_unsynchronizeds():
                result.append(self._export_state(conflict))
        return self._json(result)

    @QtCore.pyqtSlot(str, result=str)
    def get_conflicts(self, uid):
        result = []
        engine = self._get_engine(str(uid))
        if engine:
            for conflict in engine.get_conflicts():
                result.append(self._export_state(conflict))
        return self._json(result)

    @QtCore.pyqtSlot(result=str)
    def get_infos(self):
        return self._json(self._manager.get_metrics())

    @QtCore.pyqtSlot(str, result=str)
    def is_syncing(self, uid):
        engine = self._get_engine(str(uid))
        if not engine:
            return 'ERROR'
        if engine.is_syncing():
            return 'syncing'
        return 'synced'

    @QtCore.pyqtSlot(bool)
    def set_direct_edit_auto_lock(self, value):
        self._manager.set_direct_edit_auto_lock(value)

    @QtCore.pyqtSlot(result=bool)
    def get_direct_edit_auto_lock(self):
        return self._manager.get_direct_edit_auto_lock()

    @QtCore.pyqtSlot(bool)
    def set_auto_start(self, value):
        self._manager.set_auto_start(value)

    @QtCore.pyqtSlot(result=bool)
    def get_auto_start(self):
        return self._manager.get_auto_start()

    @QtCore.pyqtSlot(bool)
    def set_auto_update(self, value):
        self._manager.set_auto_update(value)

    @QtCore.pyqtSlot(result=bool)
    def get_auto_update(self):
        return self._manager.get_auto_update()

    @QtCore.pyqtSlot(result=bool)
    def is_beta_channel_available(self):
        return self._manager.is_beta_channel_available()

    @QtCore.pyqtSlot(bool)
    def set_beta_channel(self, value):
        self._manager.set_beta_channel(value)

    @QtCore.pyqtSlot(result=bool)
    def get_beta_channel(self):
        return self._manager.get_beta_channel()

    @QtCore.pyqtSlot(result=str)
    def generate_report(self):
        try:
            return self._manager.generate_report()
        except Exception as e:
            log.exception('Report error')
            return '[ERROR] ' + repr(e)

    @QtCore.pyqtSlot(bool)
    def set_tracking(self, value):
        self._manager.set_tracking(value)

    @QtCore.pyqtSlot(result=bool)
    def get_tracking(self):
        return self._manager.get_tracking()

    @QtCore.pyqtSlot(str)
    def open_remote(self, uid):
        engine = self._get_engine(str(uid))
        if engine:
            engine.open_remote()

    @QtCore.pyqtSlot(str)
    def open_report(self, path):
        self._manager.open_local_file(str(path), select=True)

    @QtCore.pyqtSlot(str, str)
    def open_local(self, uid, path):
        uid = str(uid)
        path = unicode(path)
        log.trace('Opening local file %r', path)
        if not uid:
            self._manager.open_local_file(path)
        else:
            engine = self._get_engine(uid)
            if engine:
                filepath = engine.get_abspath(path)
                self._manager.open_local_file(filepath)

    @QtCore.pyqtSlot()
    def show_activities(self):
        self._application.show_activities()

    @QtCore.pyqtSlot(str)
    def show_conflicts_resolution(self, uid):
        engine = self._get_engine(str(uid))
        if engine:
            self._application.show_conflicts_resolution(engine)

    @QtCore.pyqtSlot(str)
    def show_settings(self, page):
        page = str(page)
        log.debug('Show settings on page %s', page)
        self._application.show_settings(section=page or None)

    @QtCore.pyqtSlot()
    def quit(self):
        try:
            self._application.quit()
        except:
            log.exception('Application exit error')

    @QtCore.pyqtSlot(result=str)
    def get_engines(self):
        result = []
        for engine in self._manager.get_engines().values():
            if engine:
                result.append(self._export_engine(engine))
        return self._json(result)

    @QtCore.pyqtSlot(str, result=str)
    def browse_folder(self, base_folder):
        local_folder_path = str(base_folder)
        # TODO Might isolate to a specific api
        dir_path = QtGui.QFileDialog.getExistingDirectory(
            caption=Translator.get('BROWSE_DIALOG_CAPTION'),
            directory=base_folder)
        if dir_path:
            dir_path = unicode(dir_path)
            log.debug('Selected %s as the Nuxeo Drive folder location',
                      dir_path)
            self.file_dialog_dir = dir_path
            local_folder_path = dir_path
        return local_folder_path

    @QtCore.pyqtSlot()
    def show_file_status(self):
        self._application.show_file_status()

    @QtCore.pyqtSlot(result=str)
    def get_version(self):
        return self._manager.get_version()

    @QtCore.pyqtSlot(result=str)
    def get_update_url(self):
        if self._manager.get_beta_channel():
            return self._manager._dao.get_config('beta_update_url', DEFAULT_BETA_SITE_URL)
        return self._manager._dao.get_config('update_url', DEFAULT_UPDATE_SITE_URL)

    @QtCore.pyqtSlot(int, int)
    def resize(self, width, height):
        if self._dialog:
            self._dialog.resize(width, height)


class TokenNetworkAccessManager(QtNetwork.QNetworkAccessManager):
    def __init__(self, application, token):
        super(TokenNetworkAccessManager, self).__init__()
        self.token = token
        if not application.manager.is_debug():
            cache = QtNetwork.QNetworkDiskCache(self)
            cache.setCacheDirectory(application.get_cache_folder())
            self.setCache(cache)

    def createRequest(self, op, req, outgoingData):
        if self.token is not None:
            req.setRawHeader("X-Authentication-Token", QtCore.QByteArray(self.token))
        # Block TTF under Mac
        if sys.platform == "darwin" and unicode(req.url().path()).endswith(".ttf"):
            # Block .ttf file for now as there are badly displayed
            return super(TokenNetworkAccessManager, self).createRequest(op,
                        QtNetwork.QNetworkRequest(QtCore.QUrl()), outgoingData)
        return super(TokenNetworkAccessManager, self).createRequest(op, req, outgoingData)


class DriveWebPage(QtWebKit.QWebPage):
    @QtCore.pyqtSlot()
    def shouldInterruptJavaScript(self):
        return True


class WebDialog(QtGui.QDialog):
    # An error has been raised while loading the html
    loadError = QtCore.pyqtSignal(object)

    def __init__(self, application, page=None, title="Nuxeo Drive", api=None, token=None):
        super(WebDialog, self).__init__()
        self.setWindowTitle(title)
        self._view = QtWebKit.QWebView()
        self._frame = None
        self._page = DriveWebPage()
        self._token = None
        self._request = None
        self._zoomFactor = application.get_osi().get_zoom_factor()
        if application.manager.is_debug():
            QtWebKit.QWebSettings.globalSettings().setAttribute(QtWebKit.QWebSettings.DeveloperExtrasEnabled, True)
        else:
            self._view.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        icon = application.get_window_icon()
        if icon is not None:
            self.setWindowIcon(QtGui.QIcon(icon))
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.setWindowFlags(QtCore.Qt.WindowCloseButtonHint)
        self.resize(550, 600)
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().addWidget(self._view)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.updateGeometry()
        self._view.setPage(self._page)
        self.networkManager = TokenNetworkAccessManager(application, token)
        if not hasattr(application, 'options') or (application.options is not None and
                                                        not application.options.consider_ssl_errors):
            self.networkManager.sslErrors.connect(self._sslErrorHandler)
        self.networkManager.finished.connect(self.requestFinished)
        self._page.setNetworkAccessManager(self.networkManager)
        self.set_token(token)
        if page is not None:
            self.load(page, api, application)

    def set_token(self, token):
        self._token = token

    def load(self, page, api=None, application=None):
        if application is None and api is not None:
            application = api._application
        if api is None:
            self._api = WebDriveApi(application, self)
        else:
            api.set_dialog(self)
            self._api = api
        if not (page.startswith("http") or page.startswith("file://")):
            filename = application.get_htmlpage(page)
        else:
            filename = page
        # If connect to a remote page add the X-Authentication-Token
        if filename.startswith("http"):
            log.trace("Load web page: %s", filename)
            self._request = url = QtNetwork.QNetworkRequest(QtCore.QUrl(filename))
            if self._token is not None:
                url.setRawHeader("X-Authentication-Token", QtCore.QByteArray(self._token))
            self._set_proxy(application.manager, server_url=page)
            self._api.set_last_url(filename)
        else:
            self._request = None
            log.trace("Load web file: %s", filename)
            url = QtCore.QUrl.fromLocalFile(realpath(filename))
            url.setScheme("file")

        self._frame = self._page.mainFrame()
        self._frame.load(url)
        self._attachJsApi()
        self._frame.javaScriptWindowObjectCleared.connect(self._attachJsApi)
        self.activateWindow()

    def __del__(self):
        # For unknown reason, need to have a destructor to avoid segfault
        #
        # QThreadStorage: Thread 0x7fe0973afce0 exited after QThreadStorage 7 destroyed
        # Although this warning is still displayed
        self.disconnect()
        super(WebDialog, self).__del__()

    @QtCore.pyqtSlot(object)
    def requestFinished(self, reply):
        if (self._request is not None
                and reply.request().url() == self._request.url()
                and reply.error() != QtNetwork.QNetworkReply.NoError):
            # See http://doc.qt.io/qt-4.8/qnetworkreply.html#NetworkError-enum
            error = dict(code=reply.error())
            self.loadError.emit(error)

    def get_frame(self):
        return self._frame

    def resize(self, width, height):
        super(WebDialog, self).resize(width * self._zoomFactor, height * self._zoomFactor)

    def _sslErrorHandler(self, reply, errorList):
        log.warning('--- Bypassing SSL errors listed below ---')
        for error in errorList:
            certificate = error.certificate()
            o = str(certificate.issuerInfo(QSslCertificate.Organization))
            cn = str(certificate.issuerInfo(QSslCertificate.CommonName))
            l = str(certificate.issuerInfo(QSslCertificate.LocalityName))
            ou = str(certificate.issuerInfo(QSslCertificate.OrganizationalUnitName))
            c = str(certificate.issuerInfo(QSslCertificate.CountryName))
            st = str(certificate.issuerInfo(QSslCertificate.StateOrProvinceName))
            log.warning(
                '%s, certificate: [o=%s, cn=%s, l=%s, ou=%s, c=%s, st=%s]',
                str(error.errorString()), o, cn, l, ou, c, st)
        reply.ignoreSslErrors()

    def _set_proxy(self, manager, server_url=None):
        proxy_settings = manager.get_proxy_settings()
        if proxy_settings.config == 'Manual':
            if proxy_settings.server and proxy_settings.port:
                proxy = QNetworkProxy(QNetworkProxy.HttpProxy, hostName=proxy_settings.server,
                                      port=int(proxy_settings.port))
                if proxy_settings.authenticated:
                    proxy.setPassword(proxy_settings.password)
                    proxy.setUser(proxy_settings.username)
                QNetworkProxy.setApplicationProxy(proxy)
        elif proxy_settings.config == 'System':
            QNetworkProxyFactory.setUseSystemConfiguration(True)
        elif proxy_settings.config == 'Automatic':
            proxy_settings = manager.get_proxies(server_url)
            protocol = server_url.split(":")[0]
            proxy_server_info = urllib2.urlparse.urlparse(proxy_settings[protocol])
            proxy = QNetworkProxy(QNetworkProxy.HttpProxy, hostName=proxy_server_info.hostname, 
                                  port=proxy_server_info.port)
            QNetworkProxy.setApplicationProxy(proxy)
        else:
            QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.NoProxy))

    def get_view(self):
        return self._view

    @QtCore.pyqtSlot()
    def show(self):
        super(WebDialog, self).show()
        self.raise_()
        self.activateWindow()
        self.setFocus(QtCore.Qt.ActiveWindowFocusReason)

    @QtCore.pyqtSlot()
    def _attachJsApi(self):
        if self._frame is None:
            return
        self._frame.addToJavaScriptWindowObject("drive", self._api)
        self._frame.setZoomFactor(self._zoomFactor)
