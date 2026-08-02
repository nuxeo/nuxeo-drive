"""Tests for nxdrive/drive/notification.py"""

from unittest.mock import MagicMock, patch

import pytest

from nxdrive.drive.notification import (
    ConflictNotification,
    DirectEditErrorLockNotification,
    ErrorNotification,
    LockNotification,
    Notification,
    NotificationService,
)


# ─── Notification Tests ──────────────────────────────────────────────────────


def test_notification_init_basic():
    n = Notification(uid="TEST", title="Title", description="Desc", flags=Notification.FLAG_UNIQUE)
    assert n.uid == "TEST"
    assert n.title == "Title"
    assert n.description == "Desc"
    assert n.level == Notification.LEVEL_INFO


def test_notification_uid_with_engine():
    n = Notification(uid="TEST", engine_uid="e1", flags=Notification.FLAG_UNIQUE)
    assert n.uid == "TEST_e1"


def test_notification_uid_not_unique_has_timestamp():
    n = Notification(uid="TEST", flags=0)  # Not unique
    assert n.uid.startswith("TEST_")
    # Should have timestamp appended
    parts = n.uid.split("_")
    assert len(parts) == 2
    assert parts[1].isdigit()


def test_notification_uid_unique_no_timestamp():
    n = Notification(uid="TEST", flags=Notification.FLAG_UNIQUE)
    assert n.uid == "TEST"


def test_notification_uuid():
    n = Notification(uuid="custom-uuid-123")
    assert n.uid == "custom-uuid-123"


def test_notification_export():
    n = Notification(
        uid="X",
        title="T",
        description="D",
        flags=Notification.FLAG_UNIQUE | Notification.FLAG_DISCARDABLE | Notification.FLAG_SYSTRAY,
    )
    export = n.export()
    assert export["uid"] == "X"
    assert export["title"] == "T"
    assert export["description"] == "D"
    assert export["discardable"] is True
    assert export["systray"] is True


def test_notification_flags():
    n = Notification(
        uid="F",
        flags=(
            Notification.FLAG_UNIQUE
            | Notification.FLAG_PERSISTENT
            | Notification.FLAG_BUBBLE
            | Notification.FLAG_ACTIONABLE
            | Notification.FLAG_REMOVE_ON_DISCARD
            | Notification.FLAG_DISCARD_ON_TRIGGER
            | Notification.FLAG_DISCARDABLE
            | Notification.FLAG_DISCARD
            | Notification.FLAG_SYSTRAY
        ),
    )
    assert n.is_unique() is True
    assert n.is_persistent() is True
    assert n.is_bubble() is True
    assert n.is_actionable() is True
    assert n.is_remove_on_discard() is True
    assert n.is_discard_on_trigger() is True
    assert n.is_discardable() is True
    assert n.is_discard() is True
    assert n.is_systray() is True


def test_notification_no_flags():
    n = Notification(uid="N", flags=Notification.FLAG_UNIQUE)
    assert n.is_persistent() is False
    assert n.is_bubble() is False
    assert n.is_actionable() is False


def test_notification_repr():
    n = Notification(uid="R", title="My Title", flags=Notification.FLAG_UNIQUE)
    r = repr(n)
    assert "Notification" in r
    assert "My Title" in r


# ─── NotificationService Tests ───────────────────────────────────────────────


@pytest.fixture
def svc():
    """Create NotificationService with mocked QObject and dao."""
    with patch("nxdrive.drive.notification.QObject.__init__", lambda self, *a, **k: None):
        manager = MagicMock()
        manager.dao.get_notifications.return_value = []
        ns = NotificationService(manager)
        ns.newNotification = MagicMock()
        ns.discardNotification = MagicMock()
        ns.triggerNotification = MagicMock()
        return ns


def test_service_load_notifications(svc):
    assert svc._notifications == {}


def test_service_load_notifications_with_data():
    with patch("nxdrive.drive.notification.QObject.__init__", lambda self, *a, **k: None):
        manager = MagicMock()
        manager.dao.get_notifications.return_value = [
            {
                "uid": "n1",
                "level": "info",
                "action": "do_thing",
                "flags": Notification.FLAG_UNIQUE,
                "title": "T",
                "description": "D",
            }
        ]
        ns = NotificationService(manager)
        ns.newNotification = MagicMock()
        ns.discardNotification = MagicMock()
        ns.triggerNotification = MagicMock()
        assert "n1" in ns._notifications


def test_service_get_notifications_all(svc):
    n = Notification(uid="X", flags=Notification.FLAG_UNIQUE)
    svc._notifications[n.uid] = n
    result = svc.get_notifications()
    assert "X" in result


def test_service_get_notifications_by_engine(svc):
    n1 = Notification(uid="A", engine_uid="e1", flags=Notification.FLAG_UNIQUE)
    n2 = Notification(uid="B", engine_uid="e2", flags=Notification.FLAG_UNIQUE)
    n3 = Notification(uid="C", flags=Notification.FLAG_UNIQUE)  # generic
    svc._notifications = {n1.uid: n1, n2.uid: n2, n3.uid: n3}
    result = svc.get_notifications(engine="e1")
    assert n1.uid in result
    assert n3.uid in result  # generic included
    assert n2.uid not in result


def test_service_get_notifications_exclude_generic(svc):
    n1 = Notification(uid="A", engine_uid="e1", flags=Notification.FLAG_UNIQUE)
    n2 = Notification(uid="C", flags=Notification.FLAG_UNIQUE)  # generic
    svc._notifications = {n1.uid: n1, n2.uid: n2}
    result = svc.get_notifications(engine="e1", include_generic=False)
    assert n1.uid in result
    assert n2.uid not in result


def test_service_send_notification_persistent_new(svc):
    n = Notification(uid="P", flags=Notification.FLAG_UNIQUE | Notification.FLAG_PERSISTENT)
    svc.send_notification(n)
    assert n.uid in svc._notifications
    svc.dao.insert_notification.assert_called_once_with(n)
    svc.newNotification.emit.assert_called_once_with(n)


def test_service_send_notification_persistent_existing(svc):
    n = Notification(uid="P", flags=Notification.FLAG_UNIQUE | Notification.FLAG_PERSISTENT)
    svc._notifications[n.uid] = n
    svc.send_notification(n)
    svc.dao.update_notification.assert_called_once_with(n)


def test_service_send_notification_volatile(svc):
    n = Notification(uid="V", flags=Notification.FLAG_UNIQUE | Notification.FLAG_VOLATILE)
    svc.send_notification(n)
    svc.dao.insert_notification.assert_not_called()
    svc.newNotification.emit.assert_called_once()


def test_service_trigger_notification_not_found(svc):
    svc.trigger_notification("nonexistent")
    svc.triggerNotification.emit.assert_not_called()


def test_service_trigger_notification_actionable(svc):
    n = Notification(
        uid="T",
        flags=Notification.FLAG_UNIQUE | Notification.FLAG_ACTIONABLE,
        action="do_stuff",
        action_args=("arg1",),
    )
    svc._notifications[n.uid] = n
    svc.trigger_notification(n.uid)
    svc.triggerNotification.emit.assert_called_once_with("do_stuff", ("arg1",))


def test_service_trigger_notification_discard_on_trigger(svc):
    n = Notification(
        uid="TD",
        flags=Notification.FLAG_UNIQUE | Notification.FLAG_DISCARD_ON_TRIGGER | Notification.FLAG_REMOVE_ON_DISCARD,
    )
    svc._notifications[n.uid] = n
    svc.trigger_notification(n.uid)
    assert n.uid not in svc._notifications
    svc.dao.remove_notification.assert_called_once_with(n.uid)


def test_service_discard_notification_remove_on_discard(svc):
    n = Notification(uid="D", flags=Notification.FLAG_UNIQUE | Notification.FLAG_REMOVE_ON_DISCARD)
    svc._notifications[n.uid] = n
    svc.discard_notification(n.uid)
    assert n.uid not in svc._notifications
    svc.dao.remove_notification.assert_called_once_with(n.uid)


def test_service_discard_notification_no_remove(svc):
    n = Notification(uid="D2", flags=Notification.FLAG_UNIQUE)
    svc._notifications[n.uid] = n
    svc.discard_notification(n.uid)
    svc.dao.discard_notification.assert_called_once_with(n.uid)


def test_service_discard_notification_not_found(svc):
    svc.discard_notification("ghost")
    svc.discardNotification.emit.assert_called_once_with("ghost")


# ─── Notification Subclass Tests ─────────────────────────────────────────────


def test_error_notification():
    with patch("nxdrive.drive.notification.Translator") as mock_t:
        mock_t.get.return_value = "translated"
        doc = MagicMock(local_name="file.txt", remote_name="file.txt")
        n = ErrorNotification("eng1", doc)
    assert n.engine_uid == "eng1"
    assert n.level == Notification.LEVEL_ERROR
    assert n.is_actionable() is True


def test_lock_notification_lock():
    with patch("nxdrive.drive.notification.Translator") as mock_t:
        mock_t.get.return_value = "locked"
        n = LockNotification("file.docx", lock=True)
    assert n.is_bubble() is True


def test_lock_notification_unlock():
    with patch("nxdrive.drive.notification.Translator") as mock_t:
        mock_t.get.return_value = "unlocked"
        n = LockNotification("file.docx", lock=False)
    assert n.uid.startswith("UNLOCK")


def test_direct_edit_error_lock_notification_lock():
    with patch("nxdrive.drive.notification.Translator") as mock_t:
        mock_t.get.return_value = "err"
        n = DirectEditErrorLockNotification("lock", "f.txt", "ref1")
    assert n.level == Notification.LEVEL_ERROR


def test_direct_edit_error_lock_notification_unlock():
    with patch("nxdrive.drive.notification.Translator") as mock_t:
        mock_t.get.return_value = "err"
        n = DirectEditErrorLockNotification("unlock", "f.txt", "ref1")
    assert n.level == Notification.LEVEL_ERROR


def test_direct_edit_error_lock_notification_invalid():
    exc_raised = False
    try:
        DirectEditErrorLockNotification("invalid", "f.txt", "ref1")
    except (ValueError, AttributeError):
        exc_raised = True
    assert exc_raised, "Expected ValueError or AttributeError"


def test_conflict_notification():
    with patch("nxdrive.drive.notification.Translator") as mock_t:
        mock_t.get.return_value = "conflict"
        doc = MagicMock(local_name="conflict.txt")
        n = ConflictNotification("eng2", doc)
    assert n.level == Notification.LEVEL_WARNING
    assert n.is_actionable() is True
    assert n.engine_uid == "eng2"
