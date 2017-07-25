# coding: utf-8
import ctypes
import locale
import os
import platform
import sys

from PyQt4 import QtCore
from UniversalAnalytics import Tracker as UATracker

from nxdrive.engine.workers import Worker
from nxdrive.logging_config import get_logger
from nxdrive.osi import AbstractOSIntegration

if AbstractOSIntegration.is_mac():
    from Foundation import NSLocale

log = get_logger(__name__)


class Tracker(Worker):

    def __init__(self, manager, uid='UA-81135-23'):
        super(Tracker, self).__init__()
        self._manager = manager
        self._thread.started.connect(self.run)
        self.uid = uid
        self._tracker = UATracker.create(uid, client_id=self._manager.get_device_id(),
                                         user_agent=self.user_agent)
        self._tracker.set('appName', 'NuxeoDrive')
        self._tracker.set('appVersion', self._manager.get_version())
        self._tracker.set('encoding', sys.getfilesystemencoding())
        self._tracker.set('language', self.current_locale)
        self._manager.started.connect(self._send_stats)

        # Send stat every hour
        self._stat_timer = QtCore.QTimer()
        self._stat_timer.timeout.connect(self._send_stats)

        # Connect engines
        for _, engine in self._manager.get_engines().iteritems():
            self.connect_engine(engine)
        self._manager.newEngine.connect(self.connect_engine)
        if self._manager.get_updater() is not None:
            self._manager.get_updater().appUpdated.connect(self._send_app_update_event)
        if self._manager.direct_edit is not None:
            self._manager.direct_edit.openDocument.connect(self._send_directedit_open)
            self._manager.direct_edit.editDocument.connect(self._send_directedit_edit)

    @QtCore.pyqtSlot(object)
    def connect_engine(self, engine):
        engine.newSync.connect(self._send_sync_event)

    @property
    def current_locale(self):
        """ Detect the OS default language. """

        encoding = locale.getdefaultlocale()[1]
        if AbstractOSIntegration.is_windows():
            l10n_code = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            l10n = locale.windows_locale[l10n_code]
        elif AbstractOSIntegration.is_mac():
            l10n_code = NSLocale.currentLocale()
            l10n = NSLocale.localeIdentifier(l10n_code)
            encoding = 'UTF-8'
        else:
            l10n = locale.getdefaultlocale()[0]

        return '.'.join([l10n, encoding])

    @property
    def current_os(self):
        """ Detect the OS. """

        system = platform.system()
        if system == 'Darwin':
            name, version = 'Macintosh Intel', platform.mac_ver()[0]
        elif system == 'Linux':
            name = 'GNU/Linux'
            version = ' '.join(platform.linux_distribution()).title().strip()
        elif system == 'Windows':
            name, version = 'Microsoft Windows', platform.release()
        else:
            name, version = system, platform.release()

        return '{} {}'.format(name, version.strip())

    @property
    def user_agent(self):
        """ Format a custom user agent. """

        return 'NuxeoDrive/{} ({})'.format(self._manager.get_version(),
                                           self.current_os)

    @QtCore.pyqtSlot(object)
    def _send_app_update_event(self, version):
        self._tracker.send('event', category='AppUpdate', action='Update',
                           label='Version', value=version)

    @QtCore.pyqtSlot(object, object)
    def _send_directedit_open(self, remote_info):
        _, extension = os.path.splitext(remote_info.filename)
        if extension is None:
            extension = 'unknown'
        timing = self._manager.direct_edit.get_metrics()['last_action_timing']
        log.trace("Send DirectEdit(Open) OverallTime: %d extension: %s", timing, extension)
        self._tracker.send('event', category='DirectEdit', action="Open", label=extension, value=timing)

    @QtCore.pyqtSlot(object, object)
    def _send_directedit_edit(self, remote_info):
        _, extension = os.path.splitext(remote_info.filename)
        if extension is None:
            extension = 'unknown'
        timing = self._manager.direct_edit.get_metrics()['last_action_timing']
        log.trace("Send DirectEdit(Edit) OverallTime: %d extension: %s", timing, extension)
        self._tracker.send('event', category='DirectEdit', action="Edit", label=extension, value=timing)

    @QtCore.pyqtSlot(object, object)
    def _send_sync_event(self, _, metrics):
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
