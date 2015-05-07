'''
Created on 28 janv. 2015

@author: Remi Cattiau

TODO: Find a better way for the try/catch on slot
'''
from PyQt4 import QtGui, QtCore, QtWebKit, QtNetwork
from nxdrive.logging_config import get_logger
from nxdrive.engine.activity import FileAction, Action
from nxdrive.client.base_automation_client import Unauthorized
from nxdrive.wui.translator import Translator
from nxdrive.manager import FolderAlreadyUsed
import urllib2
import json
import sys
import time
import datetime
import calendar
from nxdrive.engine.engine import Engine
from nxdrive.notification import Notification
from nxdrive.engine.workers import Worker
from nxdrive.engine.dao.sqlite import StateRow
log = get_logger(__name__)


class WebDriveApi(QtCore.QObject):

    def __init__(self, application, dlg=None):
        super(WebDriveApi, self).__init__()
        self._manager = application.manager
        self._application = application
        self._dialog = dlg

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

    def set_dialog(self, dlg):
        self._dialog = dlg

    def _export_engine(self, engine):
        result = dict()
        result["uid"] = engine._uid
        result["type"] = engine._type
        result["name"] = engine._name
        result["metrics"] = engine.get_metrics()
        result["started"] = engine.is_started()
        result["syncing"] = engine.is_syncing()
        result["paused"] = engine.is_paused()
        result["local_folder"] = engine._local_folder
        result["queue"] = engine.get_queue_manager().get_metrics()
        # TODO Make it more generic
        bind = engine.get_binder()
        result["server_url"] = bind.server_url
        result["username"] = bind.username
        result["need_password_update"] = bind.pwd_update_required
        result["initialized"] = bind.initialized
        result["server_version"] = bind.server_version
        result["threads"] = self._get_threads(engine)
        return result

    def get_date_from_sqlite(self, d):
        if d is None:
            return 0
        format_date = "%Y-%m-%d %H:%M:%S"
        return datetime.datetime.strptime(str(d.split(".")[0]), format_date)

    def get_timestamp_from_date(self, d):
        if d == 0:
            return 0
        return int(calendar.timegm(d.timetuple()))

    def get_timestamp_from_sqlite(self, d):
        return int(calendar.timegm(self.get_date_from_sqlite(d).timetuple()))

    def _export_state(self, state):
        if state is None:
            return None
        result = dict()
        # Direction
        result["state"] = state.pair_state
        # Last sync in sec
        try:
            current_time = int(time.time())
            date_time = self.get_date_from_sqlite(state.last_sync_date)
            sync_time = self.get_timestamp_from_date(date_time)
            if state.last_local_updated > state.last_remote_updated:
                result["last_sync_direction"] = "download"
            else:
                result["last_sync_direction"] = "upload"
            result["last_sync"] = current_time - sync_time
            if date_time == 0:
                result["last_sync_date"] = ""
            else:
                result["last_sync_date"] = Translator.format_datetime(date_time)
        except Exception as e:
            log.exception(e)
        result["name"] = state.local_name
        if state.local_name is None:
            result["name"] = state.remote_name
        result["remote_name"] = state.remote_name
        result["last_error"] = state.last_error
        result["local_path"] = state.local_path
        result["local_parent_path"] = state.local_parent_path
        result["remote_ref"] = state.remote_ref
        result["last_transfer"] = state.last_transfer
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
        uid = str(uid)
        engines = self._manager.get_engines()
        if not uid in engines:
            return None
        return engines[uid]

    @QtCore.pyqtSlot(str, str, str, result=str)
    def get_last_files(self, uid, number, direction):
        try:
            uid = str(uid)
            number = str(number)
            direction = str(direction)
            engine = self._get_engine(uid)
            result = []
            if engine is not None:
                for state in engine.get_last_files(int(number), direction):
                    result.append(self._export_state(state))
            return self._json(result)
        except Exception as e:
            log.exception(e)
            return ""

    def _update_password(self, engine, password):
        engine.update_password(password)
        return ""

    @QtCore.pyqtSlot(str, str, result=str)
    def update_password(self, uid, password):
        password = str(password)
        try:
            engine = self._get_engine(uid)
            if engine is None:
                return ""
            return self._update_password(engine, password)
        except FolderAlreadyUsed:
            return "FOLDER_USED"
        except Unauthorized:
            return "UNAUTHORIZED"
        except urllib2.URLError as e:
            if e.errno == 61:
                return "CONNECTION_REFUSED"
            return "CONNECTION_ERROR"
        except urllib2.HTTPError as e:
            return "CONNECTION_ERROR"
        except Exception as e:
            log.exception(e)
            # Map error here
            return "CONNECTION_UNKNOWN"

    @QtCore.pyqtSlot()
    def close(self):
        try:
            return self._dialog.close()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(result=str)
    def get_tracker_id(self):
        try:
            return self._manager.get_tracker_id()
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(result=int)
    def get_log_level(self):
        try:
            return self._manager.get_log_level()
        except Exception as e:
            log.exception(e)
            return 10

    @QtCore.pyqtSlot(int)
    def set_log_level(self, log_level):
        try:
            return self._manager.set_log_level(log_level)
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(result=str)
    def get_appname(self):
        try:
            return self._manager.get_appname()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def set_language(self, locale):
        try:
            Translator.set(str(locale))
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot()
    def discard_notification(self, id):
        try:
            self._manager.get_notification_service().discard_notification(id)
        except Exception as e:
            log.exception(e)
            return ""

    def _export_notification(self, notif):
        result = dict()
        result["level"] = notif.get_level()
        result["type"] = notif.get_type()
        result["uid"] = notif.get_uid()
        result["replacements"] = notif.get_replacements()
        return result

    def _export_notifications(self, notifs):
        result = []
        for notif in notifs.values():
            result.append(self._export_notification(notif))
        return result

    @QtCore.pyqtSlot(str, result=str)
    def get_notifications(self, engine_uid):
        try:
            return self._json(self._export_notifications(
                        self._manager.get_notification_service().get_notifications(engine_uid)))
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(result=str)
    def get_languages(self):
        try:
            return self._json(Translator.languages())
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(result=str)
    def locale(self):
        try:
            return Translator.locale()
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(result=str)
    def get_update_status(self):
        try:
            status = self._manager.get_updater().get_status()
            return self._json(status)
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str)
    def app_update(self, version):
        try:
            self._manager.get_updater().update(version)
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str, result=str)
    def get_actions(self, uid):
        try:
            engine = self._get_engine(uid)
            result = []
            if engine is not None:
                for thread in engine.get_threads():
                    action = thread.worker.get_action()
                    # The filter should be configurable
                    if isinstance(action, FileAction):
                        result.append(self._export_action(action))
            return self._json(result)
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str, result=str)
    def get_threads(self, uid):
        try:
            engine = self._get_engine(uid)
            result = []
            if engine is None:
                return result
            result = self._get_threads(engine)
            return self._json(result)
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str, result=str)
    def get_errors(self, uid):
        try:
            engine = self._get_engine(uid)
            result = []
            if engine is None:
                return result
            result = []
            for conflict in engine.get_errors():
                result.append(self._export_state(conflict))
            return self._json(result)
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str, str)
    def show_metadata(self, uid, ref):
        try:
            engine = self._get_engine(str(uid))
            path = engine.get_abspath(str(ref))
            self._application.show_metadata(path)
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str, result=str)
    def get_conflicts(self, uid):
        try:
            engine = self._get_engine(uid)
            result = []
            if engine is None:
                return result
            result = []
            for conflict in engine.get_conflicts():
                result.append(self._export_state(conflict))
            return self._json(result)
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(result=str)
    def get_infos(self):
        try:
            return self._json(self._manager.get_metrics())
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str, result=str)
    def is_syncing(self, uid):
        try:
            engine = self._get_engine(uid)
            if engine is None:
                return "ERROR"
            if engine.is_syncing():
                return "syncing"
            return "synced"
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(bool, result=str)
    def set_auto_start(self, value):
        try:
            self._manager.set_auto_start(value)
        except Exception as e:
            log.exception(e)
        return ""

    @QtCore.pyqtSlot(result=bool)
    def get_auto_start(self):
        try:
            return self._manager.get_auto_start()
        except Exception as e:
            log.exception(e)
            return False

    @QtCore.pyqtSlot(bool, result=str)
    def set_auto_update(self, value):
        try:
            self._manager.set_auto_update(value)
        except Exception as e:
            log.exception(e)
        return ""

    @QtCore.pyqtSlot(result=bool)
    def get_auto_update(self):
        try:
            return self._manager.get_auto_update()
        except Exception as e:
            log.exception(e)
            return False

    @QtCore.pyqtSlot(result=bool)
    def is_beta_channel_available(self):
        try:
            return self._manager.is_beta_channel_available()
        except Exception as e:
            log.error('Error while checking for beta channel availability: %r', e)
            return False

    @QtCore.pyqtSlot(bool, result=str)
    def set_beta_channel(self, value):
        try:
            self._manager.set_beta_channel(value)
        except Exception as e:
            log.exception(e)
        return ""

    @QtCore.pyqtSlot(result=bool)
    def get_beta_channel(self):
        try:
            return self._manager.get_beta_channel()
        except Exception as e:
            log.exception(e)
            return False

    @QtCore.pyqtSlot(result=str)
    def generate_report(self):
        try:
            path = self._manager.generate_report()
            return path
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(bool, result=str)
    def set_tracking(self, value):
        try:
            self._manager.set_tracking(value)
        except Exception as e:
            log.exception(e)
        return ""

    @QtCore.pyqtSlot(result=bool)
    def get_tracking(self):
        try:
            return self._manager.get_tracking()
        except Exception as e:
            log.exception(e)
            return False

    @QtCore.pyqtSlot(str, result=str)
    def open_remote(self, uid):
        try:
            engine = self._get_engine(uid)
            if engine is None:
                return "ERROR"
            engine.open_remote()
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str, str, result=str)
    def open_local(self, uid, path):
        try:
            # Make sure we use unicode (comes from WebKit as QString)
            path = unicode(path)
            log.trace('Opening local file %r', path)
            if uid == '':
                self._manager.open_local_file(path)
                return ""
            engine = self._get_engine(uid)
            if engine is None:
                return "ERROR"
            filepath = engine.get_abspath(path)
            self._manager.open_local_file(filepath)
        except Exception as e:
            log.exception(e)
        # TODO Handle the exception here
        return ""

    @QtCore.pyqtSlot()
    def show_activities(self):
        try:
            self._application.show_activities()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def show_conflicts_resolution(self, uid):
        try:
            engine = self._get_engine(uid)
            self._application.show_conflicts_resolution(engine)
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def show_settings(self, page=None):
        try:
            log.debug("show settings on page %s", page)
            self._application.show_settings(section=page)
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot()
    def quit(self):
        try:
            self._application.quit()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(result=str)
    def get_engines(self):
        try:
            result = []
            for engine in self._manager.get_engines().values():
                if engine is None:
                    continue
                result.append(self._export_engine(engine))
            return self._json(result)
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str, result=str)
    def browse_folder(self, base_folder):
        try:
            local_folder_path = base_folder
            # TODO Might isolate to a specific api
            dir_path = QtGui.QFileDialog.getExistingDirectory(
                caption=self._get_caption_browse_folder(),
                directory=base_folder)
            if dir_path:
                dir_path = unicode(dir_path)
                log.debug('Selected %s as the Nuxeo Drive folder location',
                          dir_path)
                self.file_dialog_dir = dir_path
                local_folder_path = dir_path
            return local_folder_path
        except Exception as e:
            log.exception(e)
            return ""

    def _get_caption_browse_folder(self):
        return 'Select Nuxeo Drive folder location'

    @QtCore.pyqtSlot()
    def show_file_status(self):
        try:
            self._application.show_file_status()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(result=str)
    def get_version(self):
        try:
            return self._manager.get_version()
        except Exception as e:
            log.exception(e)
            return ""

    @QtCore.pyqtSlot(str, str)
    def resize(self, width, height):
        try:
            if self._dialog is not None:
                self._dialog.resize(int(width), int(height))
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def debug(self, msg):
        try:
            log.debug(msg)
        except Exception as e:
            log.exception(e)


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
        if str(req.url().path()).endswith(".ttf") and sys.platform == "darwin":
            # Block .ttf file for now as there are badly displayed
            return super(TokenNetworkAccessManager, self).createRequest(op,
                        QtNetwork.QNetworkRequest(QtCore.QUrl()), outgoingData)
        return super(TokenNetworkAccessManager, self).createRequest(op, 
                                                        req, outgoingData)


class WebDialog(QtGui.QDialog):
    '''
    classdocs
    '''
    def __init__(self, application, page, title="Nuxeo Drive", api=None, token=None):
        '''
        Constructor
        '''
        super(WebDialog, self).__init__()
        self._view = QtWebKit.QWebView()
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        if application.manager.is_debug():
            QtWebKit.QWebSettings.globalSettings().setAttribute(QtWebKit.QWebSettings.DeveloperExtrasEnabled, True)
        else:
            self._view.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        icon = application.get_window_icon()
        if icon is not None:
            self.setWindowIcon(QtGui.QIcon(icon))
        self.setWindowTitle(title)
        if not (page.startswith("http") or page.startswith("file://")):
            filename = application.get_htmlpage(page)
        else:
            filename = page
        self.networkManager = TokenNetworkAccessManager(application, token)
        self._view.page().setNetworkAccessManager(self.networkManager)
        # If connect to a remote page add the X-Authentication-Token
        if filename.startswith("http"):
            url = QtNetwork.QNetworkRequest(QtCore.QUrl(filename))
            if token is not None:
                url.setRawHeader("X-Authentication-Token", QtCore.QByteArray(token))
        else:
            log.debug("Load web file : %s", filename)
            url = QtCore.QUrl(filename)
            url.setScheme("file")
        self._view.load(url)
        self._frame = self._view.page().mainFrame()
        if api is None:
            self._api = WebDriveApi(application, self)
        else:
            api.set_dialog(self)
            self._api = api
        self._attachJsApi()
        self._frame.javaScriptWindowObjectCleared.connect(self._attachJsApi)
        self.resize(400, 400)
        self._view.resize(400, 400)
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().addWidget(self._view)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.updateGeometry()
        self.activateWindow()

    @QtCore.pyqtSlot()
    def show(self):
        super(WebDialog, self).show()
        self.raise_()
        self.activateWindow()
        self.setFocus(QtCore.Qt.ActiveWindowFocusReason)

    @QtCore.pyqtSlot()
    def _attachJsApi(self):
        self._frame.addToJavaScriptWindowObject("drive", self._api)
