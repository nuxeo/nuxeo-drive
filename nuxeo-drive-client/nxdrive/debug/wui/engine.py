'''
@author: Remi Cattiau
'''
from PyQt4 import QtCore
from nxdrive.wui.dialog import WebDialog
from nxdrive.wui.dialog import WebDriveApi
from nxdrive.logging_config import get_logger
from nxdrive.logging_config import MAX_LOG_DISPLAYED, get_handler
from nxdrive.osi import parse_protocol_url
import logging
import time
log = get_logger(__name__)


class DebugDriveApi(WebDriveApi):
    def __init__(self, application, dlg):
        super(DebugDriveApi, self).__init__(application, dlg)

    def _get_full_queue(self, queue, dao=None):
        result = []
        while (len(queue) > 0):
            result.append(self._export_state(dao.get_state_from_id(queue.pop().id)))
        return result

    def _export_engine(self, engine):
        result = super(DebugDriveApi, self)._export_engine(engine)
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
        handler = get_handler(get_logger(None), "memory")
        log_buffer = handler.get_buffer(limit)
        for record in log_buffer:
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

    @QtCore.pyqtSlot(str, str, str, str, str, str, str, result=str)
    def send_notification(self, notification_type, engine_uid, level, title, description, flags, action):
        from nxdrive.notification import Notification
        try:
            if engine_uid is not None:
                engine_uid = str(engine_uid)
            if level is not None:
                level = str(level)
            if action is not None:
                action = str(action)
            if title is not None:
                title = str(title)
            if description is not None:
                description = str(description)
            if notification_type is not None:
                notification_type = str(notification_type)
            if flags is None:
                flags = 0
            else:
                flags = int(flags)
            if engine_uid == '':
                engine_uid = None
            notification = Notification(uid=notification_type, engine_uid=engine_uid, flags=flags, level=level, action=action, description=description, title=title)
            self._manager.get_notification_service().send_notification(notification)
            return ""
        except Exception as e:
            log.exception(e)
            return "ERROR"

    @QtCore.pyqtSlot(result=str)
    def get_logs(self):
        try:
            handler = get_handler(get_logger(None), "memory")
            return str(handler.get_buffer(MAX_LOG_DISPLAYED))
        except Exception as e:
            log.exception(e)
            return None

    @QtCore.pyqtSlot(str, result=str)
    def get_engine(self, uid):
        try:
            engine = self._get_engine(uid)
            result = self._export_engine(engine)
            return self._json(result)
        except Exception as e:
            log.exception(e)
            return None

    @QtCore.pyqtSlot(str)
    def resume_remote_watcher(self, uid):
        try:
            engine = self._get_engine(uid)
            engine._remote_watcher.resume()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def resume_local_watcher(self, uid):
        try:
            engine = self._get_engine(uid)
            engine._local_watcher.resume()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def suspend_remote_watcher(self, uid):
        try:
            engine = self._get_engine(uid)
            engine._remote_watcher.suspend()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def suspend_local_watcher(self, uid):
        try:
            engine = self._get_engine(uid)
            engine._local_watcher.suspend()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def resume_engine(self, uid):
        try:
            engine = self._get_engine(uid)
            engine.resume()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def suspend_engine(self, uid):
        try:
            engine = self._get_engine(uid)
            engine.suspend()
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str)
    def direct_edit(self, url):
        try:
            self._manager.get_direct_edit().handle_url(str(url))
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str, str)
    def set_app_update(self, status, version):
        try:
            self._manager.get_updater().force_status(str(status), str(version))
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str, str)
    def resume_queue(self, uid, queue):
        try:
            engine = self._get_engine(uid)
            if queue == "local_file_queue":
                engine.get_queue_manager().enable_local_file_queue(value=True)
            elif queue == "local_folder_queue":
                engine.get_queue_manager().enable_local_folder_queue(value=True)
            elif queue == "remote_folder_queue":
                engine.get_queue_manager().enable_remote_folder_queue(value=True)
            elif queue == "remote_file_queue":
                engine.get_queue_manager().enable_remote_file_queue(value=True)
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str, str)
    def suspend_queue(self, uid, queue):
        try:
            engine = self._get_engine(uid)
            if queue == "local_file_queue":
                engine.get_queue_manager().enable_local_file_queue(value=False)
            elif queue == "local_folder_queue":
                engine.get_queue_manager().enable_local_folder_queue(value=False)
            elif queue == "remote_folder_queue":
                engine.get_queue_manager().enable_remote_folder_queue(value=False)
            elif queue == "remote_file_queue":
                engine.get_queue_manager().enable_remote_file_queue(value=False)
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str, str)
    def get_queue(self, uid, queue):
        try:
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
        except Exception as e:
            log.exception(e)
            return ""


class EngineDialog(WebDialog):
    '''
    classdocs
    '''

    def __init__(self, application):
        '''
        Constructor
        '''
        super(EngineDialog, self).__init__(application, "debug.html",
                                                 api=DebugDriveApi(application, self), title="Nuxeo Drive - Engines")
