# coding: utf-8
import time
from datetime import datetime
from logging import getLogger
from threading import Lock
from typing import Dict, Optional, TYPE_CHECKING

from PyQt5.QtCore import QObject, pyqtSignal

from .objects import DocPair
from .translator import Translator
from .utils import short_name

if TYPE_CHECKING:
    from .engine.engine import Engine  # noqa
    from .manager import Manager  # noqa

__all__ = ("DefaultNotificationService", "Notification")

log = getLogger(__name__)


class Notification:
    LEVEL_INFO = "info"
    LEVEL_WARNING = "warning"
    LEVEL_ERROR = "danger"

    # Discard notification
    FLAG_DISCARD = 1

    # Unique (not depending on time), only one by type/engine is displayed
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

    # An event will be triggered on click
    FLAG_ACTIONABLE = 128

    # Delete the notification on discard
    FLAG_REMOVE_ON_DISCARD = 256

    # Discard on trigger
    FLAG_DISCARD_ON_TRIGGER = 512

    def __init__(
        self,
        uid: str = None,
        uuid: str = None,
        engine_uid: str = None,
        level: str = LEVEL_INFO,
        flags: int = 0,
        title: str = "",
        description: str = "",
        replacements: Dict[str, str] = None,
        action: str = "",
    ) -> None:
        self.flags = flags
        self.level = level
        self.title = title
        self.description = description
        self.action = action
        self.engine_uid = engine_uid
        self._time: Optional[int] = None
        self._replacements = replacements or dict()

        self.uid = ""
        if uid:
            if engine_uid:
                uid += "_" + engine_uid
            if not self.is_unique():
                uid += "_" + str(int(time.time()))
            self.uid = uid
        elif uuid:
            self.uid = uuid

    def is_remove_on_discard(self) -> bool:
        return bool(self.flags & Notification.FLAG_REMOVE_ON_DISCARD)

    def is_persistent(self) -> bool:
        return bool(self.flags & Notification.FLAG_PERSISTENT)

    def is_unique(self) -> bool:
        return bool(self.flags & Notification.FLAG_UNIQUE)

    def is_discard(self) -> bool:
        return bool(self.flags & Notification.FLAG_DISCARD)

    def is_discardable(self) -> bool:
        return bool(self.flags & Notification.FLAG_DISCARDABLE)

    def is_systray(self) -> bool:
        return bool(self.flags & Notification.FLAG_SYSTRAY)

    def is_bubble(self) -> bool:
        return bool(self.flags & Notification.FLAG_BUBBLE)

    def is_actionable(self) -> bool:
        return bool(self.flags & Notification.FLAG_ACTIONABLE)

    def is_discard_on_trigger(self) -> bool:
        return bool(self.flags & Notification.FLAG_DISCARD_ON_TRIGGER)

    def get_replacements(self) -> Dict[str, str]:
        return self._replacements

    def __repr__(self) -> str:
        return (
            f"Notification(level={self.level!r} title={self.title!r} "
            f"uid={self.uid!r} unique={self.is_unique()!r})"
        )


class NotificationService(QObject):

    newNotification = pyqtSignal(object)
    discardNotification = pyqtSignal(object)
    triggerNotification = pyqtSignal(str, str)

    def __init__(self, manager: "Manager") -> None:
        super().__init__()
        self._lock = Lock()
        self._notifications: Dict[str, Notification] = dict()
        self._manager = manager
        self._dao = manager.get_dao()
        self.load_notifications()

    def load_notifications(self) -> None:
        notifications = self._dao.get_notifications()
        for notif in notifications:
            self._notifications[notif["uid"]] = Notification(
                uuid=notif["uid"],
                level=notif["level"],
                action=notif["action"],
                flags=notif["flags"],
                title=notif["title"],
                description=notif["description"],
            )

    def get_notifications(
        self, engine: str = None, include_generic: bool = True
    ) -> Dict[str, Notification]:
        # Might need to use lock and duplicate
        with self._lock:
            if engine is None:
                return self._notifications
            result = dict()
            for notif in self._notifications.values():
                if notif.engine_uid == engine:
                    result[notif.uid] = notif
                if notif.engine_uid is None and include_generic:
                    result[notif.uid] = notif
            return result

    def send_notification(self, notification: Notification) -> None:
        log.debug(f"Sending {notification!r}")
        notification._time = int(time.time())
        with self._lock:
            if notification.is_persistent():
                if notification.uid not in self._notifications:
                    self._dao.insert_notification(notification)
                else:
                    self._dao.update_notification(notification)
            self._notifications[notification.uid] = notification

        self.newNotification.emit(notification)

    def trigger_notification(self, uid: str) -> None:
        if uid not in self._notifications:
            return
        notification = self._notifications[uid]
        if notification.is_actionable():
            self.triggerNotification.emit(notification.action, notification.engine_uid)
        if notification.is_discard_on_trigger():
            self.discard_notification(uid)

    def discard_notification(self, uid: str) -> None:
        with self._lock:
            remove = False
            if uid in self._notifications:
                remove = self._notifications[uid].is_remove_on_discard()
                del self._notifications[uid]
            if remove:
                self._dao.remove_notification(uid)
            else:
                self._dao.discard_notification(uid)
        self.discardNotification.emit(uid)


class ErrorNotification(Notification):
    def __init__(self, engine_uid: str, doc_pair: DocPair) -> None:
        name = doc_pair.local_name or doc_pair.remote_name or ""
        values = [short_name(name)]
        super().__init__(
            "ERROR",
            title=Translator.get("ERROR", values),
            description=Translator.get("ERROR_ON_FILE", values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_ERROR,
            flags=(
                Notification.FLAG_VOLATILE
                | Notification.FLAG_ACTIONABLE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_PERSISTENT
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
            action="show_conflicts_resolution",
        )


class LockNotification(Notification):
    def __init__(self, filename: str) -> None:
        values = [short_name(filename)]
        super().__init__(
            "LOCK",
            title=Translator.get("LOCK_NOTIFICATION_TITLE", values),
            description=Translator.get("LOCK_NOTIFICATION_DESCRIPTION", values),
            flags=(
                Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
        )


class DirectEditErrorLockNotification(Notification):
    def __init__(self, action: str, filename: str, ref: str) -> None:
        values = [short_name(filename)]
        if action == "lock":
            action = "LOCK"
        elif action == "unlock":
            action = "UNLOCK"
        else:
            raise ValueError(f"Invalid action: {locals()!r} not in (lock, unlock)")
        title = f"DIRECT_EDIT_{action}_ERROR"
        description = f"{title}_DESCRIPTION"

        super().__init__(
            "ERROR",
            title=Translator.get(title, values),
            description=Translator.get(description, values),
            level=Notification.LEVEL_ERROR,
            flags=(
                Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
        )


class ConflictNotification(Notification):
    def __init__(self, engine_uid: str, doc_pair: DocPair) -> None:
        values = [short_name(doc_pair.local_name)]
        super().__init__(
            "CONFLICT_FILE",
            title=Translator.get("CONFLICT", values),
            description=Translator.get("CONFLICT_ON_FILE", values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_WARNING,
            flags=(
                Notification.FLAG_VOLATILE
                | Notification.FLAG_ACTIONABLE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_PERSISTENT
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
            action="show_conflicts_resolution",
        )


class ReadOnlyNotification(Notification):
    def __init__(self, engine_uid: str, filename: str, parent: str = None) -> None:
        values = [short_name(filename)]
        if parent:
            values.append(short_name(parent))
        description = "READONLY_FILE" if parent is None else "READONLY_FOLDER"
        super().__init__(
            "READONLY",
            title=Translator.get("READONLY", values),
            description=Translator.get(description, values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_WARNING,
            flags=Notification.FLAG_PERSISTENT | Notification.FLAG_BUBBLE,
        )


class DirectEditReadOnlyNotification(Notification):
    def __init__(self, filename: str) -> None:
        values = [short_name(filename)]
        super().__init__(
            "DIRECT_EDIT_READONLY",
            title=Translator.get("READONLY", values),
            description=Translator.get("DIRECT_EDIT_READONLY_FILE", values),
            level=Notification.LEVEL_WARNING,
            flags=Notification.FLAG_PERSISTENT | Notification.FLAG_BUBBLE,
        )


class DirectEditStartingNotification(Notification):
    def __init__(self, hostname: str, filename: str) -> None:
        values_title = [hostname]
        values_msg = [short_name(filename)]
        super().__init__(
            "DIRECT_EDIT_SARTING",
            title=Translator.get("DIRECT_EDIT_STARTING_TITLE", values_title),
            description=Translator.get("DIRECT_EDIT_STARTING_MSG", values_msg),
            level=Notification.LEVEL_INFO,
            flags=Notification.FLAG_PERSISTENT | Notification.FLAG_BUBBLE,
        )


class DeleteReadOnlyNotification(Notification):
    def __init__(self, engine_uid: str, filename: str) -> None:
        values = [short_name(filename)]
        super().__init__(
            "DELETE_READONLY",
            title=Translator.get("DELETE_READONLY", values),
            description=Translator.get("DELETE_READONLY_DOCUMENT", values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_WARNING,
            flags=Notification.FLAG_PERSISTENT | Notification.FLAG_BUBBLE,
        )


class LockedNotification(Notification):
    def __init__(
        self, engine_uid: str, filename: str, lock_owner: str, lock_created: datetime
    ) -> None:
        values = [
            short_name(filename),
            lock_owner,
            lock_created.strftime("%m/%d/%Y %H:%M:%S"),
        ]
        super().__init__(
            "LOCKED",
            title=Translator.get("LOCKED", values),
            description=Translator.get("LOCKED_FILE", values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_WARNING,
            flags=(
                Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
        )


class DirectEditLockedNotification(Notification):
    def __init__(self, filename: str, lock_owner: str, lock_created: datetime) -> None:
        values = [
            short_name(filename),
            lock_owner,
            lock_created.strftime("%m/%d/%Y %H:%M:%S"),
        ]
        super().__init__(
            "DIRECT_EDIT_LOCKED",
            title=Translator.get("LOCKED", values),
            description=Translator.get("DIRECT_EDIT_LOCKED_FILE", values),
            level=Notification.LEVEL_WARNING,
            flags=(
                Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
        )


class DirectEditUpdatedNotification(Notification):
    def __init__(self, filename: str) -> None:
        values = [short_name(filename)]
        super().__init__(
            "DIRECT_EDIT_UPDATED",
            title=Translator.get("UPDATED", values),
            description=Translator.get("DIRECT_EDIT_UPDATED_FILE", values),
            flags=(
                Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
        )


class ErrorOpenedFile(Notification):
    def __init__(self, path: str, is_folder: bool) -> None:
        values = [short_name(path)]
        msg = ("FILE", "FOLDER")[is_folder]
        super().__init__(
            "WINDOWS_ERROR",
            title=Translator.get("WINDOWS_ERROR_TITLE"),
            description=Translator.get(f"WINDOWS_ERROR_OPENED_{msg}", values),
            level=Notification.LEVEL_ERROR,
            flags=(
                Notification.FLAG_UNIQUE
                | Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
            ),
        )


class FileDeletionError(Notification):
    def __init__(self, path: str) -> None:
        values = [short_name(path)]
        super().__init__(
            "DELETION_ERROR",
            title=Translator.get("DELETION_ERROR_TITLE"),
            description=Translator.get("DELETION_ERROR_MSG", values),
            level=Notification.LEVEL_ERROR,
            flags=(
                Notification.FLAG_UNIQUE
                | Notification.FLAG_PERSISTENT
                | Notification.FLAG_BUBBLE
            ),
        )


class InvalidCredentialNotification(Notification):
    def __init__(self, engine_uid: str) -> None:
        super().__init__(
            "INVALID_CREDENTIALS",
            title=Translator.get("INVALID_CREDENTIALS"),
            engine_uid=engine_uid,
            level=Notification.LEVEL_ERROR,
            flags=(
                Notification.FLAG_UNIQUE
                | Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_ACTIONABLE
                | Notification.FLAG_SYSTRAY
            ),
            action="web_update_token",
        )


class DefaultNotificationService(NotificationService):
    def __init__(self, manager: "Manager") -> None:
        super().__init__(manager)
        self._manager = manager

    def init_signals(self) -> None:
        self._manager.initEngine.connect(self._connect_engine)
        self._manager.newEngine.connect(self._connect_engine)
        self._manager.direct_edit.directEditLockError.connect(self._directEditLockError)
        self._manager.direct_edit.directEditStarting.connect(self._directEditStarting)
        self._manager.direct_edit.directEditReadonly.connect(self._directEditReadonly)
        self._manager.direct_edit.directEditLocked.connect(self._directEditLocked)
        self._manager.direct_edit.directEditUploadCompleted.connect(
            self._directEditUpdated
        )
        self._manager.autolock_service.documentLocked.connect(self._lockDocument)

    def _connect_engine(self, engine: "Engine") -> None:
        engine.newConflict.connect(self._newConflict)
        engine.newError.connect(self._newError)
        engine.newReadonly.connect(self._newReadonly)
        engine.deleteReadonly.connect(self._deleteReadonly)
        engine.newLocked.connect(self._newLocked)
        engine.invalidAuthentication.connect(self._invalidAuthentication)
        engine.online.connect(self._validAuthentication)
        engine.errorOpenedFile.connect(self._errorOpenedFile)
        engine.fileDeletionErrorTooLong.connect(self._fileDeletionErrorTooLong)

    def _errorOpenedFile(self, doc: DocPair) -> None:
        self.send_notification(ErrorOpenedFile(str(doc.local_path), doc.folderish))

    def _fileDeletionErrorTooLong(self, doc: DocPair) -> None:
        self.send_notification(FileDeletionError(str(doc.local_path)))

    def _lockDocument(self, filename: str) -> None:
        self.send_notification(LockNotification(filename))

    def _directEditLockError(self, lock: str, filename: str, ref: str) -> None:
        if lock not in ("lock", "unlock"):
            log.debug(f"DirectEdit LockError not handled: {lock}")
            return
        self.send_notification(DirectEditErrorLockNotification(lock, filename, ref))

    def _newError(self, row_id: int) -> None:
        engine_uid = self.sender().uid
        doc_pair = self.sender().get_dao().get_state_from_id(row_id)
        if doc_pair is None:
            return
        self.send_notification(ErrorNotification(engine_uid, doc_pair))

    def _newConflict(self, row_id: int) -> None:
        engine_uid = self.sender().uid
        doc_pair = self.sender().get_dao().get_state_from_id(row_id)
        if not doc_pair:
            return
        self.send_notification(ConflictNotification(engine_uid, doc_pair))

    def _newReadonly(self, filename: str, parent: str = None) -> None:
        engine_uid = self.sender().uid
        self.send_notification(ReadOnlyNotification(engine_uid, filename, parent))

    def _directEditReadonly(self, filename: str) -> None:
        self.send_notification(DirectEditReadOnlyNotification(filename))

    def _deleteReadonly(self, filename: str) -> None:
        engine_uid = self.sender().uid
        self.send_notification(DeleteReadOnlyNotification(engine_uid, filename))

    def _newLocked(
        self, filename: str, lock_owner: str, lock_created: datetime
    ) -> None:
        engine_uid = self.sender().uid
        self.send_notification(
            LockedNotification(engine_uid, filename, lock_owner, lock_created)
        )

    def _directEditLocked(
        self, filename: str, lock_owner: str, lock_created: datetime
    ) -> None:
        self.send_notification(
            DirectEditLockedNotification(filename, lock_owner, lock_created)
        )

    def _directEditStarting(self, hostname: str, filename: str) -> None:
        self.send_notification(DirectEditStartingNotification(hostname, filename))

    def _directEditUpdated(self, filename: str) -> None:
        self.send_notification(DirectEditUpdatedNotification(filename))

    def _validAuthentication(self) -> None:
        engine_uid = self.sender().uid
        self.discard_notification("INVALID_CREDENTIALS_" + engine_uid)

    def _invalidAuthentication(self) -> None:
        engine_uid = self.sender().uid
        notif = InvalidCredentialNotification(engine_uid)
        self.send_notification(notif)
