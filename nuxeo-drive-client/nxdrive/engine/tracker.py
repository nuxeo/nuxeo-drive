'''
@author: Remi Cattiau
'''
from nxdrive.engine.workers import Worker
from PyQt4 import QtCore
from nxdrive.logging_config import get_logger
import platform
import os
log = get_logger(__name__)


class Tracker(Worker):
    '''
    classdocs
    '''

    def __init__(self, manager, uid="UA-81135-23"):
        '''
        Constructor
        '''
        super(Tracker, self).__init__()
        from UniversalAnalytics import Tracker as UATracker
        self._manager = manager
        self._thread.started.connect(self.run)
        self._user_agent = self.get_user_agent(self._manager.get_version())
        self.uid = uid
        self._tracker = UATracker.create(uid, client_id=self._manager.get_device_id(),
                                        user_agent=self._user_agent)
        self._tracker.set("appName", "NuxeoDrive")
        self._tracker.set("appVersion", self._manager.get_version())
        self._manager.started.connect(self._send_stats)
        # Send stat every hour
        self._stat_timer = QtCore.QTimer()
        self._stat_timer.timeout.connect(self._send_stats)
        # Connect engines
        for _, engine in self._manager.get_engines().iteritems():
            self.connect_engine(engine)
        self._manager.newEngine.connect(self.connect_engine)
        self._manager.get_updater().appUpdated.connect(self._send_app_update_event)
        self._manager.get_drive_edit().openDocument.connect(self._send_directedit_open)
        self._manager.get_drive_edit().editDocument.connect(self._send_directedit_edit)

    @QtCore.pyqtSlot(object)
    def connect_engine(self, engine):
        engine.newSync.connect(self._send_sync_event)

    @staticmethod
    def get_user_agent(version):
        user_agent = "NuxeoDrive/" + version
        user_agent = user_agent + " ("
        if platform.system() == "Windows":
            user_agent = user_agent + " Windows " + platform.release()
        if platform.system() == "Darwin":
            user_agent = user_agent + "Macintosh; Intel Mac OS X "
            user_agent = user_agent + platform.mac_ver()[0].replace(".", "_")
        if platform.system() == "Linux":
            user_agent = user_agent + "Linux)"
        user_agent = user_agent + ")"
        return user_agent

    @QtCore.pyqtSlot(object)
    def _send_app_update_event(self, version):
        self._tracker.send('event', category='AppUpdate', action='Update', label="Version",
                               value=version)

    @QtCore.pyqtSlot(object, object)
    def _send_directedit_open(self, remote_info):
        _, extension = os.path.splitext(remote_info.filename)
        if extension is None:
            extension = 'unknown'
        timing = self._manager.get_drive_edit().get_metrics()['last_action_timing']
        log.trace("Send DirectEdit(Open) OverallTime: %d extension: %s", timing, extension)
        self._tracker.send('event', category='DirectEdit', action="Open", label=extension, value=timing)

    @QtCore.pyqtSlot(object, object)
    def _send_directedit_edit(self, remote_info):
        _, extension = os.path.splitext(remote_info.filename)
        if extension is None:
            extension = 'unknown'
        timing = self._manager.get_drive_edit().get_metrics()['last_action_timing']
        log.trace("Send DirectEdit(Edit) OverallTime: %d extension: %s", timing, extension)
        self._tracker.send('event', category='DirectEdit', action="Edit", label=extension, value=timing)

    @QtCore.pyqtSlot(object, object)
    def _send_sync_event(self, pair, metrics):
        speed = None
        timing = None
        if "start_time" in metrics and "end_time" in metrics:
            timing = metrics["end_time"] - metrics["start_time"]
        if "speed" in metrics:
            speed = metrics["speed"]
        if timing is not None:
            log.trace("Send TransferOperation(%s) OverallTime: %d", metrics["handler"], timing)
            self._tracker.send('event', category='TransferOperation', action=metrics["handler"], label="OverallTime",
                               value=timing)
        if speed is not None:
            log.trace("Send TransferOperation(%s) Speed: %d", metrics["handler"], speed)
            self._tracker.send('event', category='TransferOperation', action=metrics["handler"], label="Speed",
                               value=speed)

    @QtCore.pyqtSlot()
    def _send_stats(self):
        engines = self._manager.get_engines()
        for _, engine in engines.iteritems():
            stats = engine.get_metrics()
            for key, value in stats.iteritems():
                log.trace("Send Statistics(Engine) %s:%d", key, value)
                self._tracker.send('event', category='Statistics', action='Engine', label=key, value=value)
        self._stat_timer.start(60 * 60 * 1000)
