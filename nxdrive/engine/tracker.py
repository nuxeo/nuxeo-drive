# coding: utf-8
import ctypes
import locale
import os
import platform
import sys
import urlparse
from logging import getLogger

from PyQt4 import QtCore
from UniversalAnalytics import Tracker as UATracker

from .workers import Worker

if sys.platform == 'darwin':
    from Foundation import NSLocale

log = getLogger(__name__)


class Tracker(Worker):

    fmt_event = 'Send {category}({action}) {label}: {value!r}'

    def __init__(self, manager, uid='UA-81135-23'):
        super(Tracker, self).__init__()
        self._manager = manager
        self._thread.started.connect(self.run)
        self.uid = uid
        self._tracker = UATracker.create(
            uid, client_id=self._manager.device_id, user_agent=self.user_agent)
        self._tracker.set('appName', 'NuxeoDrive')
        self._tracker.set('appVersion', self._manager.version)
        self._tracker.set('encoding', sys.getfilesystemencoding())
        self._tracker.set('language', self.current_locale)
        self._manager.started.connect(self._send_stats)

        # Send stat every hour
        self._stat_timer = QtCore.QTimer()
        self._stat_timer.timeout.connect(self._send_stats)

        # Connect engines
        for _, engine in self._manager.get_engines().items():
            self.connect_engine(engine)
        self._manager.newEngine.connect(self.connect_engine)
        if self._manager.direct_edit is not None:
            self._manager.direct_edit.openDocument.connect(
                self._send_directedit_open)
            self._manager.direct_edit.editDocument.connect(
                self._send_directedit_edit)

    @QtCore.pyqtSlot(object)
    def connect_engine(self, engine):
        engine.newSync.connect(self._send_sync_event)

    @property
    def current_locale(self):
        """ Detect the OS default language. """

        encoding = locale.getdefaultlocale()[1]
        if sys.platform == 'win32':
            l10n_code = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            l10n = locale.windows_locale[l10n_code]
        elif sys.platform == 'darwin':
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

        return 'NuxeoDrive/{} ({})'.format(self._manager.version,
                                           self.current_os)

    def send_event(self, **kwargs):
        engine = self._manager.get_engines().values()[0]

        if engine:
            self._tracker.set({
                'dimension6': urlparse.urlsplit(engine.server_url).hostname,
                'dimension7': engine.server_url,
                'dimension8': engine.remote.client.server_version,
                'dimension9': engine.remote_user,
            })

        log.trace(self.fmt_event.format(**kwargs))
        try:
            self._tracker.send('event', **kwargs)
        except:
            log.exception('Error sending analytics')

    @QtCore.pyqtSlot(object, object)
    def _send_directedit_open(self, remote_info):
        _, extension = os.path.splitext(remote_info.filename)
        if extension is None:
            extension = 'unknown'

        self.send_event(
            category='DirectEdit',
            action='Open',
            label=extension.lower(),
            value=self._manager.direct_edit.get_metrics()['last_action_timing'])

    @QtCore.pyqtSlot(object, object)
    def _send_directedit_edit(self, remote_info):
        _, extension = os.path.splitext(remote_info.filename)
        if extension is None:
            extension = 'unknown'

        self.send_event(
            category='DirectEdit',
            action='Edit',
            label=extension.lower(),
            value=self._manager.direct_edit.get_metrics()['last_action_timing'])

    @QtCore.pyqtSlot(object, object)
    def _send_sync_event(self, metrics):
        timing = metrics.get('end_time', 0) - metrics['start_time']
        speed = metrics.get('speed', None)

        if timing > 0:
            self.send_event(
                category='TransferOperation',
                action=metrics['handler'],
                label='OverallTime',
                value=timing)

        if speed:
            self.send_event(
                category='TransferOperation',
                action=metrics['handler'],
                label='Speed',
                value=speed)

    @QtCore.pyqtSlot()
    def _send_stats(self):
        for _, engine in self._manager.get_engines().items():
            for key, value in engine.get_metrics().items():
                if not isinstance(value, int):
                    log.trace('Skip non integer Statistics(Engine) %s: %r',
                              key, value)
                    continue

                self.send_event(
                    category='Statistics',
                    action='Engine',
                    label=key,
                    value=value)

        self._stat_timer.start(60 * 60 * 1000)
