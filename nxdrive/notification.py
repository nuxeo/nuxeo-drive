import time
from datetime import datetime
from logging import getLogger
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Dict, Tuple

from .constants import APP_NAME
from .objects import DocPair
from .qt.imports import QObject, pyqtSignal
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
        *,
        uid: str = None,
        uuid: str = None,
        engine_uid: str = None,
        level: str = LEVEL_INFO,
        flags: int = 0,
        title: str = "",
        description: str = "",
        action: str = "",
        action_args: Tuple[Any, ...] = (),
    ) -> None:
        self.flags = flags
        self.level = level
        self.title = title
        self.description = description
        self.action = action
        self.engine_uid = engine_uid
        self.action_args = action_args

        self.uid = ""
        if uid:
            if engine_uid:
                uid += "_" + engine_uid
            if not self.is_unique():
                uid += "_" + str(int(time.time()))
            self.uid = uid
        elif uuid:
            self.uid = uuid

    def export(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "uid": self.uid,
            "title": self.title,
            "description": self.description,
            "discardable": self.is_discardable(),
            "discard": self.is_discard(),
            "systray": self.is_systray(),
        }

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

    def __repr__(self) -> str:
        return (
            f"Notification(level={self.level!r} title={self.title!r} "
            f"uid={self.uid!r} unique={self.is_unique()!r})"
        )


class NotificationService(QObject):

    newNotification = pyqtSignal(object)
    discardNotification = pyqtSignal(object)
    triggerNotification = pyqtSignal(str, object)

    def __init__(self, manager: "Manager", /) -> None:
        super().__init__()
        self._lock = Lock()
        self._notifications: Dict[str, Notification] = {}
        self._manager = manager
        self.dao = manager.dao
        self.load_notifications()

    def load_notifications(self) -> None:
        notifications = self.dao.get_notifications()
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
        self, *, engine: str = None, include_generic: bool = True
    ) -> Dict[str, Notification]:
        # Might need to use lock and duplicate
        with self._lock:
            if engine is None:
                return self._notifications
            result = {}
            for notif in self._notifications.copy().values():
                if notif.engine_uid == engine:
                    result[notif.uid] = notif
                if notif.engine_uid is None and include_generic:
                    result[notif.uid] = notif
            return result

    def send_notification(self, notification: Notification, /) -> None:
        log.info(f"Sending {notification!r}")
        with self._lock:
            if notification.is_persistent():
                if notification.uid not in self._notifications:
                    self.dao.insert_notification(notification)
                else:
                    self.dao.update_notification(notification)
            self._notifications[notification.uid] = notification

        self.newNotification.emit(notification)

    def trigger_notification(self, uid: str, /) -> None:
        log.info(f"Trigger notification: {uid} = {self._notifications.get(uid)}")
        if uid not in self._notifications:
            return
        notification = self._notifications[uid]
        if notification.is_actionable():
            self.triggerNotification.emit(notification.action, notification.action_args)
        if notification.is_discard_on_trigger():
            self.discard_notification(uid)

    def discard_notification(self, uid: str, /) -> None:
        with self._lock:
            remove = False
            if uid in self._notifications:
                remove = self._notifications[uid].is_remove_on_discard()
                del self._notifications[uid]
            if remove:
                self.dao.remove_notification(uid)
            else:
                self.dao.discard_notification(uid)
        self.discardNotification.emit(uid)


class ErrorNotification(Notification):
    def __init__(self, engine_uid: str, doc_pair: DocPair, /) -> None:
        name = doc_pair.local_name or doc_pair.remote_name or ""
        values = [short_name(name)]
        super().__init__(
            uid="ERROR",
            title=Translator.get("ERROR", values=values),
            description=Translator.get("ERROR_ON_FILE", values=values),
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
            action_args=(engine_uid,),
        )


class LockNotification(Notification):
    def __init__(self, filename: str, /, *, lock: bool = True) -> None:
        values = [short_name(filename)]
        prefix = "" if lock else "UN"
        super().__init__(
            uid=f"{prefix}LOCK",
            title=Translator.get("AUTOLOCK"),
            description=Translator.get(
                f"{prefix}LOCK_NOTIFICATION_DESCRIPTION", values=values
            ),
            flags=(
                Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
        )


class DirectEditErrorLockNotification(Notification):
    def __init__(self, action: str, filename: str, ref: str, /) -> None:
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
            uid="ERROR",
            title=Translator.get(title, values=values),
            description=Translator.get(description, values=values),
            level=Notification.LEVEL_ERROR,
            flags=(
                Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
        )


class ConflictNotification(Notification):
    def __init__(self, engine_uid: str, doc_pair: DocPair, /) -> None:
        values = [short_name(doc_pair.local_name)]
        super().__init__(
            uid="CONFLICT_FILE",
            title=Translator.get("CONFLICT", values=values),
            description=Translator.get("CONFLICT_ON_FILE", values=values),
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
            action_args=(engine_uid,),
        )


class ReadOnlyNotification(Notification):
    def __init__(
        self, engine_uid: str, filename: str, /, *, parent: str = None
    ) -> None:
        values = [short_name(filename)]
        if parent:
            values.append(short_name(parent))
        description = "READONLY_FILE" if parent is None else "READONLY_FOLDER"
        super().__init__(
            uid="READONLY",
            title=Translator.get("READONLY", values=values),
            description=Translator.get(description, values=values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_WARNING,
            flags=Notification.FLAG_PERSISTENT | Notification.FLAG_BUBBLE,
        )


class DirectEditReadOnlyNotification(Notification):
    def __init__(self, filename: str, /) -> None:
        values = [short_name(filename)]
        super().__init__(
            uid="DIRECT_EDIT_READONLY",
            title=Translator.get("READONLY", values=values),
            description=Translator.get("DIRECT_EDIT_READONLY_FILE", values=values),
            level=Notification.LEVEL_WARNING,
            flags=Notification.FLAG_PERSISTENT | Notification.FLAG_BUBBLE,
        )


class DirectEditForbiddenNotification(Notification):
    def __init__(self, doc_id: str, user_id: str, hostname: str, /) -> None:
        values = [doc_id, user_id, hostname]
        super().__init__(
            uid="DIRECT_EDIT_FORBIDDEN",
            title=Translator.get("DIRECT_EDIT_FORBIDDEN_TITLE"),
            description=Translator.get("DIRECT_EDIT_FORBIDDEN_MSG", values=values),
            level=Notification.LEVEL_WARNING,
            flags=Notification.FLAG_PERSISTENT | Notification.FLAG_BUBBLE,
        )


class DirectEditStartingNotification(Notification):
    def __init__(self, hostname: str, filename: str, /) -> None:
        values_title = [hostname]
        values_msg = [short_name(filename)]
        super().__init__(
            uid="DIRECT_EDIT_SARTING",
            title=Translator.get("DIRECT_EDIT_STARTING_TITLE", values=values_title),
            description=Translator.get("DIRECT_EDIT_STARTING_MSG", values=values_msg),
            level=Notification.LEVEL_INFO,
            flags=Notification.FLAG_PERSISTENT | Notification.FLAG_BUBBLE,
        )


class DeleteReadOnlyNotification(Notification):
    def __init__(self, engine_uid: str, filename: str, /) -> None:
        values = [short_name(filename)]
        super().__init__(
            uid="DELETE_READONLY",
            title=Translator.get("DELETE_READONLY", values=values),
            description=Translator.get("DELETE_READONLY_DOCUMENT", values=values),
            engine_uid=engine_uid,
            level=Notification.LEVEL_WARNING,
            flags=Notification.FLAG_PERSISTENT | Notification.FLAG_BUBBLE,
        )


class LockedNotification(Notification):
    def __init__(
        self, engine_uid: str, filename: str, lock_owner: str, lock_created: datetime, /
    ) -> None:
        values = [
            short_name(filename),
            lock_owner,
            lock_created.strftime("%m/%d/%Y %H:%M:%S"),
        ]
        super().__init__(
            uid="LOCKED",
            title=Translator.get("LOCKED", values=values),
            description=Translator.get("LOCKED_FILE", values=values),
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
    def __init__(
        self, filename: str, lock_owner: str, lock_created: datetime, /
    ) -> None:
        values = [
            short_name(filename),
            lock_owner,
            lock_created.strftime("%m/%d/%Y %H:%M:%S"),
        ]
        super().__init__(
            uid="DIRECT_EDIT_LOCKED",
            title=Translator.get("LOCKED", values=values),
            description=Translator.get("DIRECT_EDIT_LOCKED_FILE", values=values),
            level=Notification.LEVEL_WARNING,
            flags=(
                Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
        )


class DirectEditUpdatedNotification(Notification):
    def __init__(self, filename: str, /) -> None:
        values = [short_name(filename)]
        super().__init__(
            uid="DIRECT_EDIT_UPDATED",
            title=Translator.get("UPDATED", values=values),
            description=Translator.get("DIRECT_EDIT_UPDATED_FILE", values=values),
            flags=(
                Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
        )


class DirectTransferError(Notification):
    """Display a notification when a Direct Transfer is in error."""

    def __init__(self, file: Path, /) -> None:
        values = [file.name]
        super().__init__(
            uid="DIRECT_TRANSFER_ERROR",
            title="Direct Transfer",
            description=Translator.get("DIRECT_TRANSFER_ERROR", values=values),
            level=Notification.LEVEL_ERROR,
            flags=Notification.FLAG_VOLATILE | Notification.FLAG_BUBBLE,
        )


class DirectTransferSessionFinished(Notification):
    """Display a notification when a Direct Transfer session is finished."""

    def __init__(self, engine_uid: str, remote_ref: str, remote_path: str, /) -> None:
        values = [remote_path]
        super().__init__(
            uid="DIRECT_TRANSFER_SESSION_END",
            title="Direct Transfer",
            description=Translator.get("DIRECT_TRANSFER_SESSION_END", values=values),
            level=Notification.LEVEL_INFO,
            flags=(
                Notification.FLAG_PERSISTENT
                | Notification.FLAG_BUBBLE
                | Notification.FLAG_ACTIONABLE
                | Notification.FLAG_DISCARD_ON_TRIGGER
                | Notification.FLAG_REMOVE_ON_DISCARD
            ),
            action="open_remote_document",
            action_args=(
                engine_uid,
                remote_ref,
                remote_path,
            ),
        )


class ErrorOpenedFile(Notification):
    def __init__(self, path: str, is_folder: bool, /) -> None:
        values = [short_name(path), APP_NAME]
        msg = ("FILE", "FOLDER")[is_folder]
        super().__init__(
            uid="WINDOWS_ERROR",
            title=Translator.get("WINDOWS_ERROR_TITLE"),
            description=Translator.get(f"WINDOWS_ERROR_OPENED_{msg}", values=values),
            level=Notification.LEVEL_ERROR,
            flags=(
                Notification.FLAG_UNIQUE
                | Notification.FLAG_VOLATILE
                | Notification.FLAG_BUBBLE
            ),
        )


class LongPathError(Notification):
    def __init__(self, path: str, /) -> None:
        values = [short_name(path)]
        super().__init__(
            uid="LONG_PATH_ERROR",
            title=Translator.get("LONG_PATH_ERROR_TITLE"),
            description=Translator.get("LONG_PATH_ERROR_MSG", values=values),
            level=Notification.LEVEL_ERROR,
            flags=(
                Notification.FLAG_UNIQUE
                | Notification.FLAG_PERSISTENT
                | Notification.FLAG_BUBBLE
            ),
        )


class InvalidCredentialNotification(Notification):
    def __init__(self, engine_uid: str, /) -> None:
        super().__init__(
            uid="INVALID_CREDENTIALS",
            title=Translator.get("AUTH_EXPIRED"),
            description=Translator.get("AUTH_UPDATE_ACTION"),
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
            action_args=(engine_uid,),
        )


class DefaultNotificationService(NotificationService):
    def init_signals(self) -> None:
        self._manager.initEngine.connect(self._connect_engine)
        self._manager.newEngine.connect(self._connect_engine)

    def _connect_engine(self, engine: "Engine") -> None:
        engine.newConflict.connect(self._newConflict)
        engine.newError.connect(self._newError)
        engine.newReadonly.connect(self._newReadonly)
        engine.deleteReadonly.connect(self._deleteReadonly)
        engine.newLocked.connect(self._newLocked)
        engine.invalidAuthentication.connect(self._invalidAuthentication)
        engine.online.connect(self._validAuthentication)
        engine.errorOpenedFile.connect(self._errorOpenedFile)
        engine.longPathError.connect(self._longPathError)
        engine.directTranferError.connect(self._direct_transfer_error)
        engine.directTransferSessionFinished.connect(
            self._direct_transfer_session_finshed
        )

    def _direct_transfer_error(self, file: Path, /) -> None:
        """Display a notification when a Direct Transfer is in error."""
        self.send_notification(DirectTransferError(file))

    def _direct_transfer_session_finshed(
        self, engine_uid: str, remote_ref: str, remote_path: str, /
    ) -> None:
        """Display a notification when a Direct Transfer session is finished."""
        self.send_notification(
            DirectTransferSessionFinished(engine_uid, remote_ref, remote_path)
        )

    def _errorOpenedFile(self, doc: DocPair, /) -> None:
        self.send_notification(ErrorOpenedFile(str(doc.local_path), doc.folderish))

    def _longPathError(self, doc: DocPair, /) -> None:
        self.send_notification(LongPathError(str(doc.local_path)))

    def _lockDocument(self, filename: str, /) -> None:
        self.send_notification(LockNotification(filename))

    def _unlockDocument(self, filename: str, /) -> None:
        self.send_notification(LockNotification(filename, lock=False))

    def _directEditLockError(self, lock: str, filename: str, ref: str, /) -> None:
        if lock not in ("lock", "unlock"):
            log.info(f"Direct Edit LockError not handled: {lock}")
            return
        self.send_notification(DirectEditErrorLockNotification(lock, filename, ref))

    def _newError(self, row_id: int, /) -> None:
        engine = self.sender()
        if not hasattr(engine, "dao"):
            return

        doc_pair = engine.dao.get_state_from_id(row_id)
        if not doc_pair:
            return

        self.send_notification(ErrorNotification(engine.uid, doc_pair))

    def _newConflict(self, row_id: int, /) -> None:
        engine_uid = self.sender().uid
        doc_pair = self.sender().dao.get_state_from_id(row_id)
        if not doc_pair:
            return
        self.send_notification(ConflictNotification(engine_uid, doc_pair))

    def _newReadonly(self, filename: str, /, *, parent: str = None) -> None:
        engine_uid = self.sender().uid
        self.send_notification(
            ReadOnlyNotification(engine_uid, filename, parent=parent)
        )

    def _directEditForbidden(self, doc_id: str, user_id: str, hostname: str) -> None:
        self.send_notification(
            DirectEditForbiddenNotification(doc_id, user_id, hostname)
        )

    def _directEditReadonly(self, filename: str, /) -> None:
        self.send_notification(DirectEditReadOnlyNotification(filename))

    def _deleteReadonly(self, filename: str, /) -> None:
        engine_uid = self.sender().uid
        self.send_notification(DeleteReadOnlyNotification(engine_uid, filename))

    def _newLocked(
        self, filename: str, lock_owner: str, lock_created: datetime, /
    ) -> None:
        engine_uid = self.sender().uid
        self.send_notification(
            LockedNotification(engine_uid, filename, lock_owner, lock_created)
        )

    def _directEditLocked(
        self, filename: str, lock_owner: str, lock_created: datetime, /
    ) -> None:
        self.send_notification(
            DirectEditLockedNotification(filename, lock_owner, lock_created)
        )

    def _directEditStarting(self, hostname: str, filename: str, /) -> None:
        self.send_notification(DirectEditStartingNotification(hostname, filename))

    def _directEditUpdated(self, filename: str, /) -> None:
        self.send_notification(DirectEditUpdatedNotification(filename))

    def _validAuthentication(self) -> None:
        engine_uid = self.sender().uid
        self.discard_notification("INVALID_CREDENTIALS_" + engine_uid)

    def _invalidAuthentication(self) -> None:
        engine_uid = self.sender().uid
        notif = InvalidCredentialNotification(engine_uid)
        self.send_notification(notif)
