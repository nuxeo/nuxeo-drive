'''
Created on 28 janv. 2015

@author: Remi Cattiau
'''
from PyQt4 import QtGui, QtCore, QtWebKit
from nxdrive.logging_config import get_logger
from nxdrive.utils import find_resource_dir
from nxdrive.gui.resources import find_icon
from nxdrive.engine.activity import FileAction
import os
import json
log = get_logger(__name__)


class WebDriveApi(QtCore.QObject):

    def __init__(self, dlg, application):
        super(WebDriveApi, self).__init__()
        self._manager = application.manager
        self._application = application
        self._dialog = dlg

    def _json(self, obj):
        return json.dumps(obj)

    def _export_engine(self, engine):
        result = dict()
        result["uid"] = engine._uid
        result["type"] = engine._type
        result["name"] = engine._name
        result["syncing"] = engine.is_syncing()
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
        result = dict()
        result["name"] = state.local_name
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
        uid = str(uid)
        number = str(number)
        direction = str(direction)
        engine = self._get_engine(uid)
        result = []
        if engine is not None:
            for state in engine.get_last_files(int(number), direction):
                result.append(self._export_state(state))
        return self._json(result)

    @QtCore.pyqtSlot(str, result=str)
    def get_actions(self, uid):
        engine = self._get_engine(uid)
        result = []
        if engine is not None:
            for thread in engine.get_threads():
                action = thread.worker.get_action()
                # The filter should be configurable
                if isinstance(action, FileAction):
                    result.append(self._export_action(action))
        return self._json(result)

    @QtCore.pyqtSlot(str, result=str)
    def get_threads(self, uid):
        engine = self._get_engine(uid)
        result = []
        if engine is None:
            return result
        result = self._get_threads(engine)
        return self._json(result)

    @QtCore.pyqtSlot(str, result=str)
    def is_syncing(self, uid):
        engine = self._get_engine(uid)
        if engine is None:
            return "ERROR"
        if engine.is_syncing():
            return "syncing"
        return "synced"

    @QtCore.pyqtSlot(bool, result=str)
    def set_auto_update(self, value):
        self._manager.get_configuration()
        self._manager.set_auto_update(value)
        return ""

    @QtCore.pyqtSlot(result=bool)
    def get_auto_update(self):
        return self._manager.get_auto_update()

    @QtCore.pyqtSlot(bool, result=str)
    def set_tracking(self, value):
        self._manager.set_tracking(value)
        return ""

    @QtCore.pyqtSlot(result=bool)
    def get_tracking(self):
        return self._manager.get_tracking()

    @QtCore.pyqtSlot(str, result=str)
    def open_remote(self, uid):
        engine = self._get_engine(uid)
        if engine is None:
            return "ERROR"
        filepath = engine.get_remote_url()
        self._manager.open_local_file(filepath)
        # TODO Handle the exception here
        return ""

    @QtCore.pyqtSlot(str, str, result=str)
    def open_local(self, uid, path):
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
        # TODO Handle the exception here
        return ""

    @QtCore.pyqtSlot()
    def show_activities(self):
        log.error("SHOW ACTIVITIES")
        self._application.show_activities()

    @QtCore.pyqtSlot()
    def show_settings(self):
        self._application.show_settings()

    @QtCore.pyqtSlot()
    def quit(self):
        self._application.quit()

    @QtCore.pyqtSlot(result=str)
    def get_engines(self):
        result = []
        for _, engine in self._manager.get_engines().iteritems():
            result.append(self._export_engine(engine))
        return self._json(result)

    @QtCore.pyqtSlot(str, result=str)
    def browse_folder(self, base_folder):
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
            # Dont append if it is already
            # TO_REVIEW not forcing the name will be better no ?
            from nxdrive.utils import NUXEO_DRIVE_FOLDER_NAME
            if not dir_path.endswith(NUXEO_DRIVE_FOLDER_NAME):
                local_folder_path = os.path.join(dir_path, NUXEO_DRIVE_FOLDER_NAME)
            else:
                local_folder_path = dir_path
        return local_folder_path

    @QtCore.pyqtSlot()
    def show_file_status(self):
        self._application.show_file_status()

    @QtCore.pyqtSlot(result=str)
    def get_version(self):
        return self._manager.get_version()

    @QtCore.pyqtSlot(str, str)
    def resize(self, width, height):
        self._dialog.resize(int(width), int(height))

    @QtCore.pyqtSlot(str)
    def debug(self, msg):
        log.debug(msg)


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
        QtWebKit.QWebSettings.globalSettings().setAttribute(QtWebKit.QWebSettings.DeveloperExtrasEnabled, True)
        icon = find_icon('nuxeo_drive_icon_64.png')
        if icon is not None:
            self.setWindowIcon(QtGui.QIcon(icon))
        self.setWindowTitle(title)
        import nxdrive
        nxdrive_path = os.path.dirname(nxdrive.__file__)
        ui_path = os.path.join(nxdrive_path, 'data', 'ui5')
        filename = os.path.join(find_resource_dir("ui5", ui_path), page)
        log.debug("Load web file : %s", filename)
        self._view.load(QtCore.QUrl(filename))
        self._frame = self._view.page().mainFrame()
        if api is None:
            self._api = WebDriveApi(self, application)
        else:
            self._api = api
        self._attachJsApi()
        self._frame.javaScriptWindowObjectCleared.connect(self._attachJsApi)
        self.resize(400,400)
        self._view.resize(400,400)
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().addWidget(self._view)
        self.layout().setContentsMargins(0,0,0,0)
        self.updateGeometry()
        self.activateWindow()

    @QtCore.pyqtSlot()
    def _attachJsApi(self):
        self._frame.addToJavaScriptWindowObject("drive", self._api)
