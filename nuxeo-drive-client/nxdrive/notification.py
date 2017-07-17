# coding: utf-8
import time
from threading import Lock

from PyQt4 import QtCore

from nxdrive.logging_config import get_logger
from nxdrive.wui.translator import Translator

log = get_logger(__name__)


class Notification(object):
    LEVEL_INFO = 'info'
    LEVEL_WARNING = 'warning'
    LEVEL_ERROR = 'danger'

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

    def __init__(
        self,
        uid=None,
        uuid=None,
        engine_uid=None,
        level=LEVEL_INFO,
        flags=0,
        title='',
        description='',
        replacements=None,
        action=''
    ):
        self.flags = flags
        self.level = level
        self.title = title
        self.description = description
        self.action = action
        self.engine_uid = engine_uid
        self._time = None
        self._replacements = replacements or dict()

        if uid is None and uuid is None:
            raise RuntimeError

        if engine_uid is not None and isinstance(engine_uid, str):
            raise RuntimeError

        self.uid = uid
        if uid is not None:
            if engine_uid is not None:
                self.uid = self.uid + '_' + engine_uid
            if not self.is_unique():
                self.uid = self.uid + '_' + str(int(time.time()))
        else:
            self.uid = uuid

    def is_remove_on_discard(self):
        return self.flags & Notification.FLAG_REMOVE_ON_DISCARD

    def is_persistent(self):
        return self.flags & Notification.FLAG_PERSISTENT

    def is_volatile(self):
        return self.flags & Notification.FLAG_VOLATILE

    def is_unique(self):
        return self.flags & Notification.FLAG_UNIQUE

    def is_discard(self):
        return self.flags & Notification.FLAG_DISCARD

    def is_discardable(self):
        return self.flags & Notification.FLAG_DISCARDABLE

    def is_systray(self):
        return self.flags & Notification.FLAG_SYSTRAY

    def is_bubble(self):
        return self.flags & Notification.FLAG_BUBBLE

    def is_actionable(self):
        return self.flags & Notification.FLAG_ACTIONABLE

    def is_discard_on_trigger(self):
        return self.flags & Notification.FLAG_DISCARD_ON_TRIGGER

    def add_replacement(self, key, value):
        self._replacements[key] = value

    def remove_replacement(self, key):
        try:
            del self._replacements[key]
        except KeyError:
            pass

    @staticmethod
    def generate_uid(_type, engine_uid=None):
        result = _type
        if engine_uid:
            result = result + '_' + engine_uid
        return result

    def get_type(self):
        return self._type

    def get_replacements(self):
        return self._replacements

    def get_content(self):
        return ''

    def trigger(self):
        pass

    def __repr__(self):
        return 'Notification(level=%r title=%r uid=%r unique=%r)' % (
            self.level, self.title, self.uid, self.is_unique())


class NotificationService(QtCore.QObject):

    newNotification = QtCore.pyqtSignal(object)
    discardNotification = QtCore.pyqtSignal(object)

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
            self._notifications[notif.uid] = Notification(
                uuid=notif.uid,
                level=notif.level,
                action=notif.action,
                flags=notif.flags,
                title=notif.title,
                description=notif.description,
            )

    def get_notifications(self, engine=None, include_generic=True):
        # Might need to use lock and duplicate
        self._lock.acquire()
        try:
            if engine is None:
                return self._notifications
            result = dict()
            for notif in self._notifications.values():
                if notif.engine_uid == engine:
                    result[notif.uid] = notif
                if notif.engine_uid is None and include_generic:
                    result[notif.uid] = notif
            return result
        finally:
            self._lock.release()

    def send_notification(self, notification):
        notification._time = int(time.time())
        self._lock.acquire()
        try:
            if notification.is_persistent():
                if notification.uid not in self._notifications:
                    self._dao.insert_notification(notification)
                else:
                    self._dao.update_notification(notification)
            self._notifications[notification.uid] = notification
        finally:
            self._lock.release()
        self.newNotification.emit(notification)

    def trigger_notification(self, uid):
        if uid not in self._notifications:
            return
        notification = self._notifications[uid]
        if notification.is_actionable():
            self._manager.execute_script(notification.action,
                                         notification.engine_uid)
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
        super(DebugNotification, self).__init__(
            'DEBUG',
            engine_uid=engine_uid,
            level=Notification.LEVEL_ERROR,
            flags=Notification.FLAG_UNIQUE | Notification.FLAG_PERSISTENT,
        )
        self.title = 'Debug notification'
        self.description = 'Small description for this debug notification'
        self.action = ''


class ErrorNotification(Notification):
    def __init__(self, engine_uid, doc_pair):
        values = dict(name='')
        if doc_pair.local_name is not None:
            values['name'] = doc_pair.local_name
        elif doc_pair.remote_name is not None:
            values['name'] = doc_pair.remote_name
        super(ErrorNotification, self).__init__(
            'ERROR',
            title=Translator.get('ERROR', values),
            description=Translator.get('ERROR_ON_FILE', values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_ERROR,
            flags=(Notification.FLAG_VOLATILE
                   | Notification.FLAG_ACTIONABLE
                   | Notification.FLAG_BUBBLE
                   | Notification.FLAG_PERSISTENT
                   | Notification.FLAG_DISCARD_ON_TRIGGER
                   | Notification.FLAG_REMOVE_ON_DISCARD),
            action='drive.showConflicts();',
        )


class LockNotification(Notification):
    def __init__(self, filename):
        values = dict(name=filename)
        super(LockNotification, self).__init__(
            'LOCK',
            title=Translator.get('LOCK_NOTIFICATION_TITLE', values),
            description=Translator.get('LOCK_NOTIFICATION_DESCRIPTION', values),
            level=Notification.LEVEL_INFO,
            flags=(Notification.FLAG_VOLATILE
                   | Notification.FLAG_BUBBLE
                   | Notification.FLAG_DISCARD_ON_TRIGGER
                   | Notification.FLAG_REMOVE_ON_DISCARD),
        )


class DirectEditErrorLockNotification(Notification):
    def __init__(self, action, filename, ref):
        values = dict(name=filename, ref=ref)
        if action == 'lock':
            title = 'DIRECT_EDIT_LOCK_ERROR'
            description = 'DIRECT_EDIT_LOCK_ERROR_DESCRIPTION'
        elif action == 'unlock':
            title = 'DIRECT_EDIT_UNLOCK_ERROR'
            description = 'DIRECT_EDIT_UNLOCK_ERROR_DESCRIPTION'
        else:
            raise ValueError('Invalid action: %r not in (lock, unlock)',
                             locals())

        super(DirectEditErrorLockNotification, self).__init__(
            'ERROR',
            title=Translator.get(title, values),
            description=Translator.get(description, values),
            level=Notification.LEVEL_ERROR,
            flags=(Notification.FLAG_VOLATILE
                   | Notification.FLAG_BUBBLE
                   | Notification.FLAG_DISCARD_ON_TRIGGER
                   | Notification.FLAG_REMOVE_ON_DISCARD),
        )


class ConflictNotification(Notification):
    def __init__(self, engine_uid, doc_pair):
        values = dict(name=doc_pair.local_name)
        super(ConflictNotification, self).__init__(
            'CONFLICT_FILE',
            title=Translator.get('CONFLICT', values),
            description=Translator.get('CONFLICT_ON_FILE', values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_WARNING,
            flags=(Notification.FLAG_VOLATILE
                   | Notification.FLAG_ACTIONABLE
                   | Notification.FLAG_BUBBLE
                   | Notification.FLAG_PERSISTENT
                   | Notification.FLAG_DISCARD_ON_TRIGGER
                   | Notification.FLAG_REMOVE_ON_DISCARD),
            action='drive.showConflicts();',
        )


class ReadOnlyNotification(Notification):
    def __init__(self, engine_uid, filename, parent=None):
        values = dict(name=filename, folder=parent)
        description = 'READONLY_FILE' if parent is None else 'READONLY_FOLDER'
        super(ReadOnlyNotification, self).__init__(
            'READONLY',
            title=Translator.get('READONLY', values),
            description=Translator.get(description, values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_WARNING,
            flags=(Notification.FLAG_VOLATILE
                   | Notification.FLAG_BUBBLE
                   | Notification.FLAG_DISCARD_ON_TRIGGER
                   | Notification.FLAG_REMOVE_ON_DISCARD),
        )


class DirectEditReadOnlyNotification(Notification):
    def __init__(self, filename):
        values = dict(name=filename)
        super(DirectEditReadOnlyNotification, self).__init__(
            'DIRECT_EDIT_READONLY',
            title=Translator.get('READONLY', values),
            description=Translator.get('DIRECT_EDIT_READONLY_FILE', values),
            level=Notification.LEVEL_WARNING,
            flags=(Notification.FLAG_VOLATILE
                   | Notification.FLAG_BUBBLE
                   | Notification.FLAG_DISCARD_ON_TRIGGER
                   | Notification.FLAG_REMOVE_ON_DISCARD),
        )


class DeleteReadOnlyNotification(Notification):
    def __init__(self, engine_uid, filename):
        values = dict(name=filename)
        super(DeleteReadOnlyNotification, self).__init__(
            'DELETE_READONLY',
            title=Translator.get('DELETE_READONLY', values),
            description=Translator.get('DELETE_READONLY_DOCUMENT', values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_INFO,
            flags=(Notification.FLAG_VOLATILE
                   | Notification.FLAG_BUBBLE
                   | Notification.FLAG_DISCARD_ON_TRIGGER
                   | Notification.FLAG_REMOVE_ON_DISCARD),
        )


class LockedNotification(Notification):
    def __init__(self, engine_uid, filename, lock_owner, lock_created):
        values = {
            'name': filename,
            'lock_owner': lock_owner,
            'lock_created': lock_created.strftime('%m/%d/%Y %H:%M:%S'),
        }
        super(LockedNotification, self).__init__(
            'LOCKED',
            title=Translator.get('LOCKED', values),
            description=Translator.get('LOCKED_FILE', values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_WARNING,
            flags=(Notification.FLAG_VOLATILE
                   | Notification.FLAG_BUBBLE
                   | Notification.FLAG_DISCARD_ON_TRIGGER
                   | Notification.FLAG_REMOVE_ON_DISCARD),
        )


class DirectEditLockedNotification(Notification):
    def __init__(self, filename, lock_owner, lock_created):
        values = {
            'name': filename,
            'lock_owner': lock_owner,
            'lock_created': lock_created.strftime('%m/%d/%Y %H:%M:%S'),
        }
        super(DirectEditLockedNotification, self).__init__(
            'DIRECT_EDIT_LOCKED',
            title=Translator.get('LOCKED', values),
            description=Translator.get('DIRECT_EDIT_LOCKED_FILE', values),
            level=Notification.LEVEL_WARNING,
            flags=(Notification.FLAG_VOLATILE
                   | Notification.FLAG_BUBBLE
                   | Notification.FLAG_DISCARD_ON_TRIGGER
                   | Notification.FLAG_REMOVE_ON_DISCARD),
        )


class InvalidCredentialNotification(Notification):
    def __init__(self, engine_uid):
        super(InvalidCredentialNotification, self).__init__(
            'INVALID_CREDENTIALS',
            title=Translator.get('INVALID_CREDENTIALS'),
            description='',
            engine_uid=engine_uid,
            level=Notification.LEVEL_ERROR,
            flags=(Notification.FLAG_UNIQUE
                   | Notification.FLAG_VOLATILE
                   | Notification.FLAG_BUBBLE
                   | Notification.FLAG_ACTIONABLE
                   | Notification.FLAG_SYSTRAY),
            action='drive.showSettings("Accounts_{}");'.format(engine_uid))


class DefaultNotificationService(NotificationService):
    def __init__(self, manager):
        super(DefaultNotificationService, self).__init__(manager)
        self._manager = manager
        self._manager.initEngine.connect(self._connect_engine)
        self._manager.newEngine.connect(self._connect_engine)
        self._manager.direct_edit.directEditLockError.connect(self._directEditLockError)
        self._manager.direct_edit.directEditReadonly.connect(self._directEditReadonly)
        self._manager.direct_edit.directEditLocked.connect(self._directEditLocked)
        self._manager.get_autolock_service().documentLocked.connect(self._lockDocument)

    def _connect_engine(self, engine):
        engine.newConflict.connect(self._newConflict)
        engine.newError.connect(self._newError)
        engine.newReadonly.connect(self._newReadonly)
        engine.deleteReadonly.connect(self._deleteReadonly)
        engine.newLocked.connect(self._newLocked)
        engine.invalidAuthentication.connect(self._invalidAuthentication)
        engine.online.connect(self._validAuthentication)

    def _lockDocument(self, filename):
        self.send_notification(LockNotification(filename))

    def _directEditLockError(self, lock, filename, ref):
        if lock not in ('lock', 'unlock'):
            log.debug("DirectEdit LockError not handled: %s", lock)
            return
        self.send_notification(DirectEditErrorLockNotification(lock, filename, ref))

    def _newError(self, row_id):
        engine_uid = self.sender().uid
        doc_pair = self.sender().get_dao().get_state_from_id(row_id)
        if doc_pair is None:
            return
        self.send_notification(ErrorNotification(engine_uid, doc_pair))

    def _newConflict(self, row_id):
        engine_uid = self.sender().uid
        doc_pair = self.sender().get_dao().get_state_from_id(row_id)
        if doc_pair is None:
            return
        self.send_notification(ConflictNotification(engine_uid, doc_pair))

    def _newReadonly(self, filename, parent):
        engine_uid = self.sender().uid
        self.send_notification(ReadOnlyNotification(engine_uid, filename, parent))

    def _directEditReadonly(self, filename):
        self.send_notification(DirectEditReadOnlyNotification(filename))

    def _deleteReadonly(self, filename):
        engine_uid = self.sender().uid
        self.send_notification(DeleteReadOnlyNotification(engine_uid, filename))

    def _newLocked(self, filename, lock_owner, lock_created):
        engine_uid = self.sender().uid
        self.send_notification(LockedNotification(engine_uid, filename, lock_owner, lock_created))

    def _directEditLocked(self, filename, lock_owner, lock_created):
        self.send_notification(DirectEditLockedNotification(filename, lock_owner, lock_created))

    def _validAuthentication(self):
        engine_uid = self.sender().uid
        log.debug('discard_notification: ' + 'INVALID_CREDENTIALS_' + engine_uid)
        self.discard_notification('INVALID_CREDENTIALS_' + engine_uid)

    def _invalidAuthentication(self):
        engine_uid = self.sender().uid
        notif = InvalidCredentialNotification(engine_uid)
        log.debug('send_notification: ' + notif.uid)
        self.send_notification(notif)
