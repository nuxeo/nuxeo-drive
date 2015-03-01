'''
Created on 28 janv. 2015

@author: Remi Cattiau

TODO: Find a better way for the try/catch on slot
'''
from PyQt4 import QtGui, QtCore, QtWebKit
from nxdrive.logging_config import get_logger
from nxdrive.engine.activity import FileAction
from nxdrive.client.base_automation_client import Unauthorized
from nxdrive.wui.translator import Translator
from nxdrive.manager import FolderAlreadyUsed
import urllib2
import json
log = get_logger(__name__)


class WebDriveApi(QtCore.QObject):

    def __init__(self, application, dlg=None):
        super(WebDriveApi, self).__init__()
        self._manager = application.manager
        self._application = application
        self._dialog = dlg

    def _json(self, obj):
        return json.dumps(obj)

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

    def _export_state(self, state):
        if state is None:
            return None
        result = dict()
        result["name"] = state.local_name
        if state.local_name is None:
            result["name"] = state.remote_name
        result["local_path"] = state.local_path
        result["remote_ref"] = state.remote_ref
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

    @QtCore.pyqtSlot(str, result=str)
    def get_notifications(self, engine_uid):
        try:
            return self._json(self._manager.get_notification_service().get_notifications(engine_uid))
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
            for conflict in engine.get_dao().get_errors():
                result.append(self._export_state(conflict))
            return self._json(result)
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
            for conflict in engine.get_dao().get_conflicts():
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
            # Make sure it is string ( come from WebKit as QString
            path = str(path)
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
    def show_settings(self, page=None):
        try:
            log.debug("show settings on page %s", page)
            self._application.show_settings(page)
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
                caption='Select Nuxeo Drive folder location',
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


class WebDialog(QtGui.QDialog):
    '''
    classdocs
    '''
    def __init__(self, application, page, title="Nuxeo Drive", api=None):
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
        filename = application.get_htmlpage(page)
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
    def _attachJsApi(self):
        self._frame.addToJavaScriptWindowObject("drive", self._api)
