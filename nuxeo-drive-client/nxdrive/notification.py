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

    # FLAG VALUE
    # Discard notification
    FLAG_DISCARD = 1
    # Unique ( not depending on time ), only one by type/engine is displayed
    FLAG_UNIQUE = 2
    # Can be closed by the user
    FLAG_DISCARDABLE = 4
    # Will not be stored when sent
    FLAG_VOLATILE = 8
    # Will be stored in the db
    FLAG_PERSISTENT = 16
    # Will be display as systray bubble or notification center
    FLAG_BUBBLE = 32
    # Will be displayed inside the systray menu
    FLAG_SYSTRAY = 64
    # Will be displayed inside the systray menu
    FLAG_ACTIONABLE = 128

    def __init__(self, notification_type, engine_uid=None, level=LEVEL_INFO, uid=None, flags=0, title="", description="", replacements=None, action=""):
        self._flags = flags
        self._type = notification_type
        self._level = level
        self._title = title
        self._description = description
        self._action = action
        if engine_uid is not None and isinstance(engine_uid, str):
            raise RuntimeError
        self._engine_uid = engine_uid
        self._time = None
        if uid is not None:
            self._uid = uid
        else:
            self._uid = Notification.generate_uid(notification_type, engine_uid)
            if not self.is_unique():
                self._uid = self._uid + "_" + str(int(time.time()))
        # For futur usage
        self._volatile = True
        if replacements is None:
            self._replacements = dict()
        else:
            self._replacements = replacements

    def is_persistent(self):
        return self._flags & Notification.FLAG_PERSISTENT

    def is_volatile(self):
        return self._flags & Notification.FLAG_VOLATILE

    def is_unique(self):
        return self._flags & Notification.FLAG_UNIQUE

    def is_discard(self):
        return self._flags & Notification.FLAG_DISCARD

    def is_discardable(self):
        return self._flags & Notification.FLAG_DISCARDABLE

    def is_systray(self):
        return self._flags & Notification.FLAG_SYSTRAY

    def is_bubble(self):
        return self._flags & Notification.FLAG_BUBBLE

    def get_flags(self):
        return self._flags

    def add_replacement(self, key, value):
        self._replacements[key] = value

    def get_engine_uid(self):
        return self._engine_uid

    def remove_replacement(self, key):
        if key in self._replacements:
            del self._replacements[key]

    def get_uid(self):
        return self._uid

    @staticmethod
    def generate_uid(_type, engine_uid=None):
        result = _type
        if engine_uid:
            result = result + "_" + engine_uid
        return result

    def get_type(self):
        return self._type

    def get_level(self):
        return self._level

    def get_replacements(self):
        return self._replacements

    def get_title(self):
        return self._title

    def get_description(self):
        return self._description

    def get_content(self):
        return ""

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
    def __init__(self, manager):
        super(NotificationService, self).__init__()
        self._lock = Lock()
        self._notifications = dict()
        self._dao = manager.get_dao()

    def get_notifications(self, engine=None, include_generic=True):
        # Might need to use lock and duplicate
        self._lock.acquire()
        try:
            if engine is None:
                return self._notifications
            result = dict()
            for notif in self._notifications.values():
                if notif._engine_uid == engine:
                    result[notif.get_uid()] = notif
                if notif._engine_uid is None and include_generic:
                    result[notif.get_uid()] = notif
            return result
        finally:
            self._lock.release()

    def send_notification(self, notification):
        notification._time = int(time.time())
        self._lock.acquire()
        try:
            self._notifications[notification.get_uid()] = notification
            if notification.is_persistent():
                self._dao.insert_notification(notification)
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
            if uid in self._notifications:
                del self._notifications[uid]
            self._dao.discard_notification(uid)
        finally:
            self._lock.release()
        self.discardNotification.emit(uid)


class DebugNotification(Notification):
    def __init__(self, engine_uid):
        super(InvalidCredentialNotification, self).__init__("DEBUG", engine_uid=engine_uid, level=Notification.LEVEL_ERROR, flags=Notification.FLAG_UNIQUE|Notification.FLAG_PERSISTENT)

    def get_description(self):
        return "Small description for this debug notification"

    def get_title(self):
        return "Debug notification"

    def get_action(self):
        return ""


class InvalidCredentialNotification(Notification):
    def __init__(self, engine_uid):
        super(InvalidCredentialNotification, self).__init__("INVALID_CREDENTIALS", engine_uid=engine_uid, level=Notification.LEVEL_ERROR, flags=Notification.FLAG_UNIQUE|Notification.FLAG_VOLATILE)


class DefaultNotificationService(NotificationService):
    def __init__(self, manager):
        super(DefaultNotificationService, self).__init__()
        self._manager = manager
        self._manager.initEngine.connect(self._connect_engine)

    def _connect_engine(self, engine):
        engine.invalidAuthentication.connect(self._invalidAuthentication)

    def _invalidAuthentication(self):
        engine_uid = self.sender()._uid
        self.send_notification(InvalidCredentialNotification(engine_uid))
