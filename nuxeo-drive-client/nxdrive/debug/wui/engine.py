'''
@author: Remi Cattiau
'''
from PyQt4 import QtCore
from nxdrive.wui.dialog import WebDialog
from nxdrive.wui.dialog import WebDriveApi
from nxdrive.logging_config import get_logger
from logging.handlers import BufferingHandler
import logging
import time
from copy import copy
log = get_logger(__name__)
genericLog = logging.getLogger()
MAX_LOG_DISPLAYED = 100


class CustomMemoryHandler(BufferingHandler):
    def __init__(self, capacity=MAX_LOG_DISPLAYED):
        super(CustomMemoryHandler, self).__init__(capacity)
        self._old_buffer = None

    def flush(self):
        # Flush
        self.acquire()
        try:
            self._old_buffer = copy(self.buffer)
            self.buffer = []
        finally:
            self.release()

    def get_buffer(self, size):
        adds = []
        result = []
        self.acquire()
        try:
            result = copy(self.buffer)
            result.reverse()
            if len(result) < size and self._old_buffer is not None:
                adds = copy(self._old_buffer[(size-len(result)-1):])
        finally:
            self.release()
        adds.reverse()
        for record in adds:
            result.append(record)
        return result


class DebugDriveApi(WebDriveApi):
    def __init__(self, dlg, application):
        super(DebugDriveApi, self).__init__(dlg, application)
        self.logHandler = CustomMemoryHandler(MAX_LOG_DISPLAYED)
        genericLog.addHandler(self.logHandler)

    def __del__(self):
        genericLog.removeHandler(self.logHandler)

    def _get_full_queue(self, queue, dao=None):
        result = []
        while (len(queue) > 0):
            result.append(self._export_state(dao.get_state_from_id(queue.pop().id)))
        return result

    def _export_engine(self, engine):
        result = super(DebugDriveApi, self)._export_engine(engine)
        result["metrics"] = engine.get_metrics()
        result["queue"]["metrics"] = engine.get_queue_manager().get_metrics()
        result["queue"]["local_folder_enable"] = engine.get_queue_manager()._local_folder_enable
        result["queue"]["local_file_enable"] = engine.get_queue_manager()._local_file_enable
        result["queue"]["remote_folder_enable"] = engine.get_queue_manager()._remote_folder_enable
        result["queue"]["remote_file_enable"] = engine.get_queue_manager()._remote_file_enable
        result["queue"]["remote_file"] = self._get_full_queue(
                        engine.get_queue_manager().get_remote_file_queue(), engine.get_dao())
        result["queue"]["remote_folder"] = self._get_full_queue(
                        engine.get_queue_manager().get_remote_folder_queue(), engine.get_dao())
        result["queue"]["local_folder"] = self._get_full_queue(
                        engine.get_queue_manager().get_local_folder_queue(), engine.get_dao())
        result["queue"]["local_file"] = self._get_full_queue(
                        engine.get_queue_manager().get_local_file_queue(), engine.get_dao())
        result["local_watcher"] = self._export_worker(engine._local_watcher)
        result["remote_watcher"] = self._export_worker(engine._remote_watcher)
        try:
            result["logs"] = self._get_logs()
        except:
            # Dont fail on logs extraction
            result["logs"] = []
        return result

    def _export_log_record(self, record):
        rec = dict()
        rec["severity"] = record.levelname
        rec["message"] = record.getMessage()
        rec["thread"] = record.thread
        rec["name"] = record.name
        rec["funcName"] = record.funcName
        rec["time"] = time.strftime("%H:%M:%S,",time.localtime(record.created)) + str(round(record.msecs))
        return rec

    def _get_logs(self, limit=MAX_LOG_DISPLAYED):
        logs = []
        buffer = self.logHandler.get_buffer(limit)
        for record in buffer:
            logs.append(self._export_log_record(record))
            limit = limit - 1
            if limit == 0:
                return logs
        return logs

    def _export_worker(self, worker):
        result = super(DebugDriveApi, self)._export_worker(worker)
        result["metrics"] = worker.get_metrics()
        if "action" in result["metrics"]:
            result["metrics"]["action"] = self._export_action(result["metrics"]["action"])
        return result

    @QtCore.pyqtSlot(result=str)
    def get_logs(self):
        return str(self.logHandler.get_buffer())

    @QtCore.pyqtSlot(str, result=str)
    def get_engine(self, uid):
        engine = self._get_engine(uid)
        result = self._export_engine(engine)
        return self._json(result)

    @QtCore.pyqtSlot(str)
    def resume_remote_watcher(self, uid):
        engine = self._get_engine(uid)
        engine._remote_watcher.resume()

    @QtCore.pyqtSlot(str)
    def resume_local_watcher(self, uid):
        engine = self._get_engine(uid)
        engine._local_watcher.resume()

    @QtCore.pyqtSlot(str)
    def suspend_remote_watcher(self, uid):
        engine = self._get_engine(uid)
        engine._remote_watcher.suspend()

    @QtCore.pyqtSlot(str)
    def suspend_local_watcher(self, uid):
        engine = self._get_engine(uid)
        engine._local_watcher.suspend()

    @QtCore.pyqtSlot(str)
    def resume_engine(self, uid):
        engine = self._get_engine(uid)
        engine.resume()

    @QtCore.pyqtSlot(str)
    def suspend_engine(self, uid):
        engine = self._get_engine(uid)
        engine.suspend()

    @QtCore.pyqtSlot(str, str)
    def resume_queue(self, uid, queue):
        engine = self._get_engine(uid)
        if queue == "local_file_queue":
            engine.get_queue_manager().enable_local_file_queue(value=True)
        elif queue == "local_folder_queue":
            engine.get_queue_manager().enable_local_folder_queue(value=True)
        elif queue == "remote_folder_queue":
            engine.get_queue_manager().enable_remote_folder_queue(value=True)
        elif queue == "remote_file_queue":
            engine.get_queue_manager().enable_remote_file_queue(value=True)

    @QtCore.pyqtSlot(str, str)
    def suspend_queue(self, uid, queue):
        engine = self._get_engine(uid)
        if queue == "local_file_queue":
            engine.get_queue_manager().enable_local_file_queue(value=False)
        elif queue == "local_folder_queue":
            engine.get_queue_manager().enable_local_folder_queue(value=False)
        elif queue == "remote_folder_queue":
            engine.get_queue_manager().enable_remote_folder_queue(value=False)
        elif queue == "remote_file_queue":
            engine.get_queue_manager().enable_remote_file_queue(value=False)

    @QtCore.pyqtSlot(str, str)
    def get_queue(self, uid, queue):
        engine = self._get_engine(uid)
        res = None
        if queue == "local_file_queue":
            res = engine.get_queue_manager().get_local_file_queue()
        elif queue == "local_folder_queue":
            res = engine.get_queue_manager().get_local_folder_queue()
        elif queue == "remote_folder_queue":
            res = engine.get_queue_manager().get_remote_folder_queue()
        elif queue == "remote_file_queue":
            res = engine.get_queue_manager().get_remote_file_queue()
        if res is None:
            return ""
        queue = self._get_full_queue(res, engine.get_dao())
        return self._json(queue)


class EngineDialog(WebDialog):
    '''
    classdocs
    '''

    def __init__(self, application):
        '''
        Constructor
        '''
        super(EngineDialog, self).__init__(application, "engines.html",
                                                 api=DebugDriveApi(self, application), title="Nuxeo Drive - Engines")
