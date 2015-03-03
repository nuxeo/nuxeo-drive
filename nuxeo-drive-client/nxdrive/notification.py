'''
@author: Remi Cattiau
'''
from PyQt4 import QtCore
import time
from threading import Lock
from nxdrive.logging_config import get_logger
log = get_logger(__name__)


class Notification(object):
    LEVEL_INFO = "info"
    LEVEL_WARNING = "warning"
    LEVEL_ERROR = "danger"

    def __init__(self, notification_type, engine=None, level=LEVEL_INFO, uid=None, unique=False, replacements=None):
        self._unique = unique
        self._type = notification_type
        self._level = level
        self._engine = engine
        self._time = None
        if uid is not None:
            self._uid = uid
        else:
            self._uid = notification_type
            if engine is not None:
                self._uid = self._uid + "_" + self._engine
            if not self._unique:
                self._uid = self._uid + "_" + str(int(time.time()))
        # For futur usage
        self._volatile = True
        if replacements is None:
            self._replacements = dict()
        else:
            self._replacements = replacements

    def add_replacement(self, key, value):
        self._replacements[key] = value

    def remove_replacement(self, key):
        if key in self._replacements:
            del self._replacements[key]

    def get_uid(self):
        return self._uid

    def get_type(self):
        return self._type

    def get_level(self):
        return self._level

    def is_unique(self):
        return self._unique

    def is_volatile(self):
        return self._volatile

    def get_replacements(self):
        return self._replacements

    def trigger(self):
        pass

    def __repr__(self):
        return "Notification(%s,%s,uid:%s,unique:%d)" % (
                    self._level, self._type, self._uid, self._unique)


class NotificationService(QtCore.QObject):
    newNotification = QtCore.pyqtSignal(object)
    discardNotification = QtCore.pyqtSignal(object)
    '''
    classdocs
    '''
    def __init__(self):
        super(NotificationService, self).__init__()
        self._lock = Lock()
        self._notifications = dict()

    def get_notifications(self, engine=None, include_generic=True):
        # Might need to use lock and duplicate
        self._lock.acquire()
        try:
            if engine is None:
                return self._notifications
            result = dict()
            for notif in self._notifications.values():
                if notif._engine == engine:
                    result[notif.get_uid()] = notif
                if notif._engine is None and include_generic:
                    result[notif.get_uid()] = notif
            return result
        finally:
            self._lock.release()

    def send_notification(self, notification):
        notification._time = int(time.time())
        self._lock.acquire()
        try:
            self._notifications[notification.get_uid()] = notification
        finally:
            self._lock.release()
        self.newNotification.emit(notification)

    def trigger_notification(self, uid):
        if not uid in self._notifications[uid]:
            return
        self._notifications[uid].trigger()

    def discard_notification(self, uid):
        self._lock.acquire()
        try:
            del self._notifications[uid]
        finally:
            self._lock.release()
        self.discardNotification.emit(uid)


class DefaultNotificationService(NotificationService):
    def __init__(self, manager):
        super(DefaultNotificationService, self).__init__()
        self._manager = manager
        self._manager.initEngine.connect(self._connect_engine)

    def _connect_engine(self, engine):
        engine.invalidAuthentication.connect(self._invalidAuthentication)

    def _invalidAuthentication(self):
        engine_uid = self.sender()._uid
        notification = Notification("INVALID_CREDENTIALS", engine=engine_uid,
                                        level=Notification.LEVEL_ERROR, unique=True)
        self.send_notification(notification)
