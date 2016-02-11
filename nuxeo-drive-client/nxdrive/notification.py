'''
@author: Remi Cattiau
'''
from PyQt4 import QtCore
import time
from threading import Lock
from nxdrive.logging_config import get_logger
from nxdrive.wui.translator import Translator
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
    # Delete the notifciation on discard
    FLAG_REMOVE_ON_DISCARD = 256
    # Discard on trigger
    FLAG_DISCARD_ON_TRIGGER = 512

    def __init__(self, uid=None, uuid=None, engine_uid=None, level=LEVEL_INFO, flags=0, title="", description="", replacements=None, action=""):
        self._flags = flags
        self._level = level
        self._title = title
        self._description = description
        self._action = action
        if uid is None and uuid is None:
            raise RuntimeError
        if engine_uid is not None and isinstance(engine_uid, str):
            raise RuntimeError
        self._engine_uid = engine_uid
        self._time = None
        self._uid = uid
        if uid is not None:
            if engine_uid is not None:
                self._uid = self._uid + "_" + engine_uid
            if not self.is_unique():
                self._uid = self._uid + "_" + str(int(time.time()))
        else:
            self._uid = uuid
        if replacements is None:
            self._replacements = dict()
        else:
            self._replacements = replacements

    def is_remove_on_discard(self):
        return self._flags & Notification.FLAG_REMOVE_ON_DISCARD

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

    def is_actionable(self):
        return self._flags & Notification.FLAG_ACTIONABLE

    def is_discard_on_trigger(self):
        return self._flags & Notification.FLAG_DISCARD_ON_TRIGGER

    def get_flags(self):
        return self._flags

    def add_replacement(self, key, value):
        self._replacements[key] = value

    def get_engine_uid(self):
        return self._engine_uid

    def get_action(self):
        return self._action

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
                    self._level, self.get_title(), self._uid, self.is_unique())


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
        self._manager = manager
        self._dao = manager.get_dao()
        self.load_notifications()

    def load_notifications(self):
        notifications = self._dao.get_notifications()
        for notif in notifications:
            self._notifications[notif.uid] = Notification(uuid=notif.uid, level=notif.level, action=notif.action, flags=notif.flags, title=notif.title, description=notif.description)

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
            if notification.is_persistent():
                if notification.get_uid() not in self._notifications:
                    self._dao.insert_notification(notification)
                else:
                    self._dao.update_notification(notification)
            self._notifications[notification.get_uid()] = notification
        finally:
            self._lock.release()
        self.newNotification.emit(notification)

    def trigger_notification(self, uid):
        print "Trigger notification " + uid
        if not uid in self._notifications:
            return
        notification = self._notifications[uid]
        if notification.is_actionable():
            self._manager.execute_script(notification.get_action(), notification.get_engine_uid())
        if notification.is_discard_on_trigger():
            self.discard_notification(uid)

    def discard_notification(self, uid):
        self._lock.acquire()
        try:
            remove = False
            if uid in self._notifications:
                remove = self._notifications[uid].is_remove_on_discard()
                del self._notifications[uid]
            if remove:
                self._dao.remove_notification(uid)
            else:
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


class ErrorNotification(Notification):
    def __init__(self, engine_uid, doc_pair):
        values = dict()
        if doc_pair.local_name is not None:
            values["name"] = doc_pair.local_name
        elif doc_pair.remote_name is not None:
            values["name"] = doc_pair.remote_name
        else:
            values["name"] = ""
        title = Translator.get("ERROR", values)
        description = Translator.get("ERROR_ON_FILE", values)
        super(ErrorNotification, self).__init__("ERROR", title=title, description=description,
            engine_uid=engine_uid, level=Notification.LEVEL_ERROR,
            flags=Notification.FLAG_VOLATILE|Notification.FLAG_ACTIONABLE|Notification.FLAG_BUBBLE|Notification.FLAG_PERSISTENT|Notification.FLAG_DISCARD_ON_TRIGGER|Notification.FLAG_REMOVE_ON_DISCARD,
            action="drive.showConflicts();")


class LockNotification(Notification):
    def __init__(self, filename):
        values = dict()
        values["name"] = filename
        super(LockNotification, self).__init__("LOCK",
            title=Translator.get("LOCK_NOTIFICATION_TITLE", values),
            description=Translator.get("LOCK_NOTIFICATION_DESCRIPTION", values), level=Notification.LEVEL_INFO,
            flags=Notification.FLAG_VOLATILE|Notification.FLAG_BUBBLE|Notification.FLAG_DISCARD_ON_TRIGGER|Notification.FLAG_REMOVE_ON_DISCARD)


class DriveEditErrorLockNotification(Notification):
    def __init__(self, type, filename, ref):
        values = dict()
        values["name"] = filename
        values["ref"] = ref
        if type == 'lock':
            title = Translator.get("DRIVE_EDIT_LOCK_ERROR", values)
            description = Translator.get("DRIVE_EDIT_LOCK_ERROR_DESCRIPTION", values)
        elif type == 'unlock':
            title = Translator.get("DRIVE_EDIT_UNLOCK_ERROR", values)
            description = Translator.get("DRIVE_EDIT_UNLOCK_ERROR_DESCRIPTION", values)
        else:
            raise Exception()
        super(DriveEditErrorLockNotification, self).__init__("ERROR", title=title, description=description, level=Notification.LEVEL_ERROR,
            flags=Notification.FLAG_VOLATILE|Notification.FLAG_BUBBLE|Notification.FLAG_DISCARD_ON_TRIGGER|Notification.FLAG_REMOVE_ON_DISCARD)


class ConflictNotification(Notification):
    def __init__(self, engine_uid, doc_pair):
        values = dict()
        values["name"] = doc_pair.local_name
        title = Translator.get("CONFLICT", values)
        description = Translator.get("CONFLICT_ON_FILE", values)
        super(ConflictNotification, self).__init__("CONFLICT_FILE", title=title, description=description,
            engine_uid=engine_uid, level=Notification.LEVEL_WARNING,
            flags=Notification.FLAG_VOLATILE|Notification.FLAG_ACTIONABLE|Notification.FLAG_BUBBLE|Notification.FLAG_PERSISTENT|Notification.FLAG_DISCARD_ON_TRIGGER|Notification.FLAG_REMOVE_ON_DISCARD,
            action="drive.showConflicts();")


class ReadOnlyNotification(Notification):
    def __init__(self, engine_uid, filename, parent=None):
        values = dict()
        values["name"] = filename
        values["folder"] = parent
        title = Translator.get("READONLY", values)
        if parent is None:
            description = Translator.get("READONLY_FILE", values)
        else:
            description = Translator.get("READONLY_FOLDER", values)
        super(ReadOnlyNotification, self).__init__("READONLY", title=title, description=description,
            engine_uid=engine_uid, level=Notification.LEVEL_WARNING,
            flags=Notification.FLAG_VOLATILE|Notification.FLAG_BUBBLE|Notification.FLAG_DISCARD_ON_TRIGGER|Notification.FLAG_REMOVE_ON_DISCARD)


class LockedNotification(Notification):
    def __init__(self, engine_uid, filename, lock_owner, lock_created):
        values = dict()
        values["name"] = filename
        values["lock_owner"] = lock_owner
        values["lock_created"] = lock_created.strftime("%m/%d/%Y %H:%M:%S")
        title = Translator.get("LOCKED", values)
        description = Translator.get("LOCKED_FILE", values)
        super(LockedNotification, self).__init__("LOCKED", title=title, description=description,
            engine_uid=engine_uid, level=Notification.LEVEL_WARNING,
            flags=Notification.FLAG_VOLATILE|Notification.FLAG_BUBBLE|Notification.FLAG_DISCARD_ON_TRIGGER|Notification.FLAG_REMOVE_ON_DISCARD)


class InvalidCredentialNotification(Notification):
    def __init__(self, engine_uid):
        # show_settings('Accounts_' + engine.uid)
        super(InvalidCredentialNotification, self).__init__("INVALID_CREDENTIALS",
            title=Translator.get("INVALID_CREDENTIALS"),
            description="",
            engine_uid=engine_uid, level=Notification.LEVEL_ERROR,
            flags=Notification.FLAG_UNIQUE|Notification.FLAG_VOLATILE|Notification.FLAG_BUBBLE|Notification.FLAG_ACTIONABLE|Notification.FLAG_SYSTRAY,
            action="drive.showSettings('Accounts_" + engine_uid + "');")


class DefaultNotificationService(NotificationService):
    def __init__(self, manager):
        super(DefaultNotificationService, self).__init__(manager)
        self._manager = manager
        self._manager.initEngine.connect(self._connect_engine)
        self._manager.newEngine.connect(self._connect_engine)
        self._manager.get_drive_edit().driveEditLockError.connect(self._driveEditLockError)
        self._manager.get_autolock_service().documentLocked.connect(self._lockDocument)


    def _connect_engine(self, engine):
        engine.newConflict.connect(self._newConflict)
        engine.newError.connect(self._newError)
        engine.newReadonly.connect(self._newReadonly)
        engine.newLocked.connect(self._newLocked)
        engine.invalidAuthentication.connect(self._invalidAuthentication)
        engine.online.connect(self._validAuthentication)

    def _lockDocument(self, filename):
        self.send_notification(LockNotification(filename))

    def _driveEditLockError(self, lock, filename, ref):
        if lock != 'lock' and lock != 'unlock':
            log.debug("DriveEdit LockError not handled: %s", lock)
            return
        self.send_notification(DriveEditErrorLockNotification(lock, filename, ref))

    def _newError(self, row_id):
        engine_uid = self.sender()._uid
        doc_pair = self.sender().get_dao().get_state_from_id(row_id)
        if doc_pair is None:
            return
        self.send_notification(ErrorNotification(engine_uid, doc_pair))

    def _newConflict(self, row_id):
        engine_uid = self.sender()._uid
        doc_pair = self.sender().get_dao().get_state_from_id(row_id)
        if doc_pair is None:
            return
        self.send_notification(ConflictNotification(engine_uid, doc_pair))

    def _newReadonly(self, filename, parent):
        engine_uid = self.sender()._uid
        self.send_notification(ReadOnlyNotification(engine_uid, filename, parent))

    def _newLocked(self, filename, lock_owner, lock_created):
        engine_uid = self.sender()._uid
        self.send_notification(LockedNotification(engine_uid, filename, lock_owner, lock_created))

    def _validAuthentication(self):
        engine_uid = self.sender()._uid
        log.debug("discard_notification: " + "INVALID_CREDENTIALS_" + engine_uid)
        self.discard_notification("INVALID_CREDENTIALS_" + engine_uid)

    def _invalidAuthentication(self):
        engine_uid = self.sender()._uid
        notif = InvalidCredentialNotification(engine_uid)
        log.debug("send_notification: " + notif.get_uid())
        self.send_notification(notif)
