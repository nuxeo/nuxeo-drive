"""Tests for nxdrive/drive/notification.py"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nxdrive.drive.notification import (
    ConcurrentEditingError,
    ConflictNotification,
    DefaultNotificationService,
    DeleteReadOnlyNotification,
    DirectEditErrorLockNotification,
    DirectEditForbiddenNotification,
    DirectEditLockedNotification,
    DirectEditReadOnlyNotification,
    DirectEditStartingNotification,
    DirectEditUpdatedNotification,
    DirectTransferError,
    DirectTransferSessionFinished,
    DisplayPendingTask,
    ErrorNotification,
    ErrorOpenedFile,
    InvalidCredentialNotification,
    LockedNotification,
    LockNotification,
    LongPathError,
    Notification,
    NotificationService,
    ReadOnlyNotification,
)

# ─── Notification Tests ──────────────────────────────────────────────────────


class TestNotification:
    def test_default_construction(self):
        n = Notification()
        assert n.level == Notification.LEVEL_INFO
        assert n.flags == 0
        assert n.title == ""
        assert n.description == ""
        assert n.action == ""
        assert n.engine_uid is None
        assert n.action_args == ()
        assert n.uid == ""

    def test_construction_with_uid(self):
        n = Notification(uid="TEST", title="hello", description="world")
        assert n.title == "hello"
        assert n.description == "world"
        # uid without engine_uid, not unique → includes timestamp
        assert n.uid.startswith("TEST_")

    def test_construction_with_uid_and_engine_uid(self):
        n = Notification(uid="TEST", engine_uid="engine1")
        # uid = "TEST_engine1_<timestamp>"
        assert n.uid.startswith("TEST_engine1_")

    def test_construction_with_uid_unique(self):
        n = Notification(uid="TEST", flags=Notification.FLAG_UNIQUE)
        # unique → no timestamp suffix
        assert n.uid == "TEST"

    def test_construction_with_uid_unique_and_engine_uid(self):
        n = Notification(uid="TEST", engine_uid="eng1", flags=Notification.FLAG_UNIQUE)
        assert n.uid == "TEST_eng1"

    def test_construction_with_uuid(self):
        n = Notification(uuid="my-uuid-123")
        assert n.uid == "my-uuid-123"

    def test_uid_precedence_uid_over_uuid(self):
        """When both uid and uuid are given, uid-based logic takes precedence."""
        n = Notification(
            uid="TEST", uuid="uuid-fallback", flags=Notification.FLAG_UNIQUE
        )
        assert n.uid == "TEST"

    def test_construction_with_level(self):
        n = Notification(level=Notification.LEVEL_ERROR)
        assert n.level == "danger"

    def test_construction_with_action(self):
        n = Notification(action="do_something", action_args=("a", "b"))
        assert n.action == "do_something"
        assert n.action_args == ("a", "b")

    # ─── Flag checks ─────────────────────────────────────────────────────

    def test_is_unique_true(self):
        n = Notification(flags=Notification.FLAG_UNIQUE)
        assert n.is_unique() is True

    def test_is_unique_false(self):
        n = Notification(flags=0)
        assert n.is_unique() is False

    def test_is_discard(self):
        n = Notification(flags=Notification.FLAG_DISCARD)
        assert n.is_discard() is True

    def test_is_discard_false(self):
        n = Notification(flags=0)
        assert n.is_discard() is False

    def test_is_discardable(self):
        n = Notification(flags=Notification.FLAG_DISCARDABLE)
        assert n.is_discardable() is True

    def test_is_discardable_false(self):
        n = Notification(flags=0)
        assert n.is_discardable() is False

    def test_is_systray(self):
        n = Notification(flags=Notification.FLAG_SYSTRAY)
        assert n.is_systray() is True

    def test_is_systray_false(self):
        n = Notification(flags=0)
        assert n.is_systray() is False

    def test_is_bubble(self):
        n = Notification(flags=Notification.FLAG_BUBBLE)
        assert n.is_bubble() is True

    def test_is_bubble_false(self):
        n = Notification(flags=0)
        assert n.is_bubble() is False

    def test_is_actionable(self):
        n = Notification(flags=Notification.FLAG_ACTIONABLE)
        assert n.is_actionable() is True

    def test_is_actionable_false(self):
        n = Notification(flags=0)
        assert n.is_actionable() is False

    def test_is_persistent(self):
        n = Notification(flags=Notification.FLAG_PERSISTENT)
        assert n.is_persistent() is True

    def test_is_persistent_false(self):
        n = Notification(flags=0)
        assert n.is_persistent() is False

    def test_is_discard_on_trigger(self):
        n = Notification(flags=Notification.FLAG_DISCARD_ON_TRIGGER)
        assert n.is_discard_on_trigger() is True

    def test_is_discard_on_trigger_false(self):
        n = Notification(flags=0)
        assert n.is_discard_on_trigger() is False

    def test_is_remove_on_discard(self):
        n = Notification(flags=Notification.FLAG_REMOVE_ON_DISCARD)
        assert n.is_remove_on_discard() is True

    def test_is_remove_on_discard_false(self):
        n = Notification(flags=0)
        assert n.is_remove_on_discard() is False

    def test_combined_flags(self):
        flags = (
            Notification.FLAG_UNIQUE
            | Notification.FLAG_PERSISTENT
            | Notification.FLAG_BUBBLE
            | Notification.FLAG_ACTIONABLE
        )
        n = Notification(flags=flags)
        assert n.is_unique() is True
        assert n.is_persistent() is True
        assert n.is_bubble() is True
        assert n.is_actionable() is True
        assert n.is_discard() is False
        assert n.is_discardable() is False
        assert n.is_systray() is False

    # ─── export() ────────────────────────────────────────────────────────

    def test_export(self):
        n = Notification(
            uuid="export-uid",
            level=Notification.LEVEL_WARNING,
            title="Export Title",
            description="Export Desc",
            flags=Notification.FLAG_DISCARDABLE | Notification.FLAG_SYSTRAY,
        )
        result = n.export()
        assert result["uid"] == "export-uid"
        assert result["level"] == "warning"
        assert result["title"] == "Export Title"
        assert result["description"] == "Export Desc"
        assert result["discardable"] is True
        assert result["systray"] is True
        assert result["discard"] is False

    def test_export_minimal(self):
        n = Notification()
        result = n.export()
        assert result["uid"] == ""
        assert result["level"] == "info"
        assert result["title"] == ""
        assert result["description"] == ""
        assert result["discardable"] is False
        assert result["systray"] is False
        assert result["discard"] is False

    # ─── __repr__ ────────────────────────────────────────────────────────

    def test_repr(self):
        n = Notification(
            uuid="my-uid",
            level=Notification.LEVEL_ERROR,
            title="Test Repr",
            flags=Notification.FLAG_UNIQUE,
        )
        r = repr(n)
        assert "Notification(" in r
        assert "level='danger'" in r
        assert "title='Test Repr'" in r
        assert "uid='my-uid'" in r
        assert "unique=True" in r

    def test_repr_non_unique(self):
        n = Notification(uuid="abc", title="No Unique")
        r = repr(n)
        assert "unique=False" in r


# ─── NotificationService Fixture ─────────────────────────────────────────────


@pytest.fixture
def service():
    with patch("nxdrive.drive.notification.QObject.__init__"):
        manager = Mock()
        manager.dao = Mock()
        manager.dao.get_notifications.return_value = []
        svc = NotificationService(manager)
        svc.newNotification = Mock()
        svc.discardNotification = Mock()
        svc.triggerNotification = Mock()
        return svc


# ─── NotificationService Construction ────────────────────────────────────────


class TestNotificationServiceConstruction:
    def test_init_attributes(self, service):
        assert service._notifications == {}
        assert service.dao is not None

    def test_load_notifications_called(self, service):
        service.dao.get_notifications.assert_called_once()


# ─── load_notifications ──────────────────────────────────────────────────────


class TestLoadNotifications:
    def test_load_empty(self, service):
        assert len(service._notifications) == 0

    def test_load_from_dao(self):
        with patch("nxdrive.drive.notification.QObject.__init__"):
            manager = Mock()
            manager.dao = Mock()
            manager.dao.get_notifications.return_value = [
                {
                    "uid": "notif-1",
                    "level": "info",
                    "action": "do_thing",
                    "flags": Notification.FLAG_PERSISTENT,
                    "title": "Test Notif",
                    "description": "A test",
                },
                {
                    "uid": "notif-2",
                    "level": "warning",
                    "action": "",
                    "flags": 0,
                    "title": "Another",
                    "description": "Another test",
                },
            ]
            svc = NotificationService(manager)
            svc.newNotification = Mock()
            svc.discardNotification = Mock()
            svc.triggerNotification = Mock()

        assert len(svc._notifications) == 2
        assert "notif-1" in svc._notifications
        assert "notif-2" in svc._notifications
        assert svc._notifications["notif-1"].title == "Test Notif"
        assert svc._notifications["notif-2"].level == "warning"


# ─── send_notification ───────────────────────────────────────────────────────


class TestSendNotification:
    def test_send_non_persistent(self, service):
        notif = Notification(uuid="np-1", title="Non Persistent")
        service.send_notification(notif)
        assert "np-1" in service._notifications
        service.dao.insert_notification.assert_not_called()
        service.dao.update_notification.assert_not_called()
        service.newNotification.emit.assert_called_once_with(notif)

    def test_send_persistent_insert(self, service):
        notif = Notification(
            uuid="p-1",
            title="Persistent",
            flags=Notification.FLAG_PERSISTENT,
        )
        service.send_notification(notif)
        assert "p-1" in service._notifications
        service.dao.insert_notification.assert_called_once_with(notif)
        service.dao.update_notification.assert_not_called()
        service.newNotification.emit.assert_called_once_with(notif)

    def test_send_persistent_update(self, service):
        """Sending a persistent notification that already exists should update."""
        existing = Notification(
            uuid="p-2",
            title="Existing",
            flags=Notification.FLAG_PERSISTENT,
        )
        service._notifications["p-2"] = existing

        updated = Notification(
            uuid="p-2",
            title="Updated",
            flags=Notification.FLAG_PERSISTENT,
        )
        service.send_notification(updated)
        assert service._notifications["p-2"].title == "Updated"
        service.dao.update_notification.assert_called_once_with(updated)
        service.dao.insert_notification.assert_not_called()

    def test_send_emits_signal(self, service):
        notif = Notification(uuid="sig-1")
        service.send_notification(notif)
        service.newNotification.emit.assert_called_once_with(notif)


# ─── trigger_notification ────────────────────────────────────────────────────


class TestTriggerNotification:
    def test_trigger_unknown_uid(self, service):
        """Triggering a non-existent uid should do nothing."""
        service.trigger_notification("nonexistent")
        service.triggerNotification.emit.assert_not_called()

    def test_trigger_actionable(self, service):
        notif = Notification(
            uuid="act-1",
            flags=Notification.FLAG_ACTIONABLE,
            action="my_action",
            action_args=("x", "y"),
        )
        service._notifications["act-1"] = notif
        service.trigger_notification("act-1")
        service.triggerNotification.emit.assert_called_once_with(
            "my_action", ("x", "y")
        )

    def test_trigger_non_actionable(self, service):
        notif = Notification(uuid="noact-1", flags=0)
        service._notifications["noact-1"] = notif
        service.trigger_notification("noact-1")
        service.triggerNotification.emit.assert_not_called()

    def test_trigger_discard_on_trigger(self, service):
        notif = Notification(
            uuid="dot-1",
            flags=Notification.FLAG_DISCARD_ON_TRIGGER,
        )
        service._notifications["dot-1"] = notif
        service.trigger_notification("dot-1")
        # Should have been discarded
        assert "dot-1" not in service._notifications
        service.discardNotification.emit.assert_called_once_with("dot-1")

    def test_trigger_actionable_and_discard_on_trigger(self, service):
        notif = Notification(
            uuid="ad-1",
            flags=Notification.FLAG_ACTIONABLE | Notification.FLAG_DISCARD_ON_TRIGGER,
            action="combined_action",
            action_args=("arg1",),
        )
        service._notifications["ad-1"] = notif
        service.trigger_notification("ad-1")
        service.triggerNotification.emit.assert_called_once_with(
            "combined_action", ("arg1",)
        )
        assert "ad-1" not in service._notifications


# ─── discard_notification ────────────────────────────────────────────────────


class TestDiscardNotification:
    def test_discard_existing(self, service):
        notif = Notification(uuid="d-1", flags=0)
        service._notifications["d-1"] = notif
        service.discard_notification("d-1")
        assert "d-1" not in service._notifications
        service.dao.discard_notification.assert_called_once_with("d-1")
        service.dao.remove_notification.assert_not_called()
        service.discardNotification.emit.assert_called_once_with("d-1")

    def test_discard_with_remove_on_discard(self, service):
        notif = Notification(uuid="d-2", flags=Notification.FLAG_REMOVE_ON_DISCARD)
        service._notifications["d-2"] = notif
        service.discard_notification("d-2")
        assert "d-2" not in service._notifications
        service.dao.remove_notification.assert_called_once_with("d-2")
        service.dao.discard_notification.assert_not_called()
        service.discardNotification.emit.assert_called_once_with("d-2")

    def test_discard_nonexistent(self, service):
        """Discarding a uid that doesn't exist should still emit and call dao."""
        service.discard_notification("nonexistent")
        service.dao.discard_notification.assert_called_once_with("nonexistent")
        service.discardNotification.emit.assert_called_once_with("nonexistent")


# ─── get_notifications ───────────────────────────────────────────────────────


class TestGetNotifications:
    def test_get_all(self, service):
        n1 = Notification(uuid="g-1")
        n2 = Notification(uuid="g-2")
        service._notifications["g-1"] = n1
        service._notifications["g-2"] = n2
        result = service.get_notifications()
        assert len(result) == 2
        assert "g-1" in result
        assert "g-2" in result

    def test_get_filtered_by_engine(self, service):
        n1 = Notification(uuid="e-1")
        n1.engine_uid = "engine-A"
        n2 = Notification(uuid="e-2")
        n2.engine_uid = "engine-B"
        n3 = Notification(uuid="e-3")
        n3.engine_uid = None  # generic
        service._notifications = {"e-1": n1, "e-2": n2, "e-3": n3}
        result = service.get_notifications(engine="engine-A")
        assert "e-1" in result
        assert "e-3" in result  # generic included by default
        assert "e-2" not in result

    def test_get_filtered_by_engine_exclude_generic(self, service):
        n1 = Notification(uuid="f-1")
        n1.engine_uid = "engine-X"
        n2 = Notification(uuid="f-2")
        n2.engine_uid = None
        service._notifications = {"f-1": n1, "f-2": n2}
        result = service.get_notifications(engine="engine-X", include_generic=False)
        assert "f-1" in result
        assert "f-2" not in result

    def test_get_filtered_no_match(self, service):
        n1 = Notification(uuid="nm-1")
        n1.engine_uid = "engine-Y"
        service._notifications = {"nm-1": n1}
        result = service.get_notifications(engine="engine-Z")
        assert len(result) == 0


# ─── DefaultNotificationService Tests ────────────────────────────────────────


@pytest.fixture
def default_service():
    with patch("nxdrive.drive.notification.QObject.__init__"):
        manager = Mock()
        manager.dao = Mock()
        manager.dao.get_notifications.return_value = []
        manager.initEngine = Mock()
        manager.newEngine = Mock()
        svc = DefaultNotificationService(manager)
        svc.newNotification = Mock()
        svc.discardNotification = Mock()
        svc.triggerNotification = Mock()
        return svc


class TestDefaultNotificationService:
    def test_construction(self, default_service):
        assert isinstance(default_service, NotificationService)

    def test_init_signals(self, default_service):
        default_service.init_signals()
        default_service._manager.initEngine.connect.assert_called_once_with(
            default_service._connect_engine
        )
        default_service._manager.newEngine.connect.assert_called_once_with(
            default_service._connect_engine
        )

    def test_connect_engine(self, default_service):
        engine = Mock()
        default_service._connect_engine(engine)
        engine.newConflict.connect.assert_called_once()
        engine.newError.connect.assert_called_once()
        engine.newReadonly.connect.assert_called_once()
        engine.deleteReadonly.connect.assert_called_once()
        engine.newLocked.connect.assert_called_once()
        engine.invalidAuthentication.connect.assert_called_once()
        engine.online.connect.assert_called_once()
        engine.errorOpenedFile.connect.assert_called_once()
        engine.longPathError.connect.assert_called_once()
        engine.directTranferError.connect.assert_called_once()
        engine.directTransferSessionFinished.connect.assert_called_once()
        engine.displayPendingTask.connect.assert_called_once()


# ─── Notification Subclass Tests ──────────────────────────────────────────────


class TestNotificationSubclasses:
    """Test all Notification subclasses to cover their constructors."""

    @patch("nxdrive.drive.notification.Translator")
    def test_error_notification(self, mock_translator):
        mock_translator.get.return_value = "translated"
        doc_pair = Mock()
        doc_pair.local_name = "file.txt"
        doc_pair.remote_name = "file.txt"
        n = ErrorNotification("eng1", doc_pair)
        assert n.level == Notification.LEVEL_ERROR
        assert n.action == "show_conflicts_resolution"
        assert n.action_args == ("eng1",)
        assert n.is_actionable()
        assert n.is_bubble()
        assert n.is_persistent()

    @patch("nxdrive.drive.notification.Translator")
    def test_error_notification_no_local_name(self, mock_translator):
        mock_translator.get.return_value = "translated"
        doc_pair = Mock()
        doc_pair.local_name = ""
        doc_pair.remote_name = "remote.txt"
        n = ErrorNotification("eng1", doc_pair)
        assert n.level == Notification.LEVEL_ERROR

    @patch("nxdrive.drive.notification.Translator")
    def test_lock_notification_lock(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = LockNotification("file.txt")
        assert "LOCK" in n.uid
        assert n.is_bubble()

    @patch("nxdrive.drive.notification.Translator")
    def test_lock_notification_unlock(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = LockNotification("file.txt", lock=False)
        assert "UNLOCK" in n.uid

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_error_lock_notification_lock(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = DirectEditErrorLockNotification("lock", "file.txt", "ref1")
        assert n.level == Notification.LEVEL_ERROR

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_error_lock_notification_unlock(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = DirectEditErrorLockNotification("unlock", "file.txt", "ref1")
        assert n.level == Notification.LEVEL_ERROR

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_error_lock_notification_invalid(self, mock_translator):
        mock_translator.get.return_value = "translated"
        with pytest.raises((ValueError, AttributeError)):
            DirectEditErrorLockNotification("bad", "file.txt", "ref1")

    @patch("nxdrive.drive.notification.Translator")
    def test_conflict_notification(self, mock_translator):
        mock_translator.get.return_value = "translated"
        doc_pair = Mock()
        doc_pair.local_name = "conflict.txt"
        n = ConflictNotification("eng1", doc_pair)
        assert n.level == Notification.LEVEL_WARNING
        assert n.action == "show_conflicts_resolution"
        assert n.is_actionable()

    @patch("nxdrive.drive.notification.Translator")
    def test_readonly_notification_no_parent(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = ReadOnlyNotification("eng1", "file.txt")
        assert n.level == Notification.LEVEL_WARNING
        assert n.is_persistent()
        assert n.is_bubble()

    @patch("nxdrive.drive.notification.Translator")
    def test_readonly_notification_with_parent(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = ReadOnlyNotification("eng1", "file.txt", parent="folder")
        assert n.level == Notification.LEVEL_WARNING

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_readonly_notification(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = DirectEditReadOnlyNotification("file.txt")
        assert n.level == Notification.LEVEL_WARNING

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_forbidden_notification(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = DirectEditForbiddenNotification("doc1", "user1", "host1")
        assert n.level == Notification.LEVEL_WARNING

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_starting_notification(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = DirectEditStartingNotification("host1", "file.txt")
        assert n.level == Notification.LEVEL_INFO

    @patch("nxdrive.drive.notification.Translator")
    def test_delete_readonly_notification(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = DeleteReadOnlyNotification("eng1", "file.txt")
        assert n.level == Notification.LEVEL_WARNING

    @patch("nxdrive.drive.notification.Translator")
    def test_locked_notification(self, mock_translator):
        mock_translator.get.return_value = "translated"
        from datetime import datetime

        dt = datetime(2024, 1, 1, 12, 0, 0)
        n = LockedNotification("eng1", "file.txt", "owner", dt)
        assert n.level == Notification.LEVEL_WARNING

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_locked_notification(self, mock_translator):
        mock_translator.get.return_value = "translated"
        from datetime import datetime

        dt = datetime(2024, 1, 1, 12, 0, 0)
        n = DirectEditLockedNotification("file.txt", "owner", dt)
        assert n.level == Notification.LEVEL_WARNING

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_updated_notification(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = DirectEditUpdatedNotification("file.txt")
        assert n.is_bubble()

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_transfer_error(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = DirectTransferError(Path("/tmp/file.txt"))
        assert n.level == Notification.LEVEL_ERROR

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_transfer_session_finished(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = DirectTransferSessionFinished("eng1", "ref1", "/path")
        assert n.level == Notification.LEVEL_INFO
        assert n.action == "open_remote_document"
        assert n.action_args == ("eng1", "ref1", "/path")

    @patch("nxdrive.drive.notification.Translator")
    def test_error_opened_file_file(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = ErrorOpenedFile("/tmp/file.txt", False)
        assert n.level == Notification.LEVEL_ERROR

    @patch("nxdrive.drive.notification.Translator")
    def test_error_opened_file_folder(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = ErrorOpenedFile("/tmp/folder", True)
        assert n.level == Notification.LEVEL_ERROR

    @patch("nxdrive.drive.notification.Translator")
    def test_long_path_error(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = LongPathError("/tmp/very/long/path.txt")
        assert n.level == Notification.LEVEL_ERROR
        assert n.is_persistent()

    @patch("nxdrive.drive.notification.Translator")
    def test_invalid_credential_notification(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = InvalidCredentialNotification("eng1")
        assert n.level == Notification.LEVEL_ERROR
        assert n.action == "web_update_token"
        assert n.is_systray()

    @patch("nxdrive.drive.notification.Translator")
    def test_display_pending_task(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = DisplayPendingTask("eng1", "ref1", "/path", "TASK_TITLE")
        assert n.level == Notification.LEVEL_INFO
        assert n.action == "display_pending_task"
        assert n.is_actionable()

    @patch("nxdrive.drive.notification.Translator")
    def test_concurrent_editing_error(self, mock_translator):
        mock_translator.get.return_value = "translated"
        n = ConcurrentEditingError("file.txt")
        assert n.level == Notification.LEVEL_WARNING


# ─── DefaultNotificationService Handler Tests ────────────────────────────────


class TestDefaultNotificationServiceHandlers:
    """Test the handler methods of DefaultNotificationService."""

    @pytest.fixture
    def service(self):
        manager = Mock()
        manager.dao.get_notifications.return_value = []
        with patch.object(NotificationService, "__init__", lambda self, m: None):
            svc = DefaultNotificationService.__new__(DefaultNotificationService)
            svc._manager = manager
            svc._lock = __import__("threading").Lock()
            svc._notifications = {}
            svc.dao = manager.dao
            svc.newNotification = Mock()
            svc.discardNotification = Mock()
            svc.triggerNotification = Mock()
        return svc

    @patch("nxdrive.drive.notification.Translator")
    def test_concurrent_locked(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._concurrentLocked("file.txt")
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_transfer_error_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._direct_transfer_error(Path("/tmp/file.txt"))
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_transfer_session_finished_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._direct_transfer_session_finshed("eng1", "ref1", "/path")
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_error_opened_file_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        doc = Mock()
        doc.local_path = "/tmp/file.txt"
        doc.folderish = False
        service._errorOpenedFile(doc)
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_long_path_error_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        doc = Mock()
        doc.local_path = "/tmp/very/long/path.txt"
        service._longPathError(doc)
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_lock_document_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._lockDocument("file.txt")
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_unlock_document_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._unlockDocument("file.txt")
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_lock_error_lock(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._directEditLockError("lock", "file.txt", "ref1")
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_lock_error_unlock(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._directEditLockError("unlock", "file.txt", "ref1")
        assert service.newNotification.emit.called

    def test_direct_edit_lock_error_invalid(self, service):
        service._directEditLockError("invalid", "file.txt", "ref1")
        assert not service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_new_error_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        engine = Mock()
        engine.uid = "eng1"
        doc_pair = Mock()
        doc_pair.local_name = "file.txt"
        doc_pair.remote_name = "file.txt"
        engine.dao.get_state_from_id.return_value = doc_pair
        with patch.object(service, "sender", return_value=engine):
            service._newError(1)
        assert service.newNotification.emit.called

    def test_new_error_no_sender(self, service):
        with patch.object(service, "sender", return_value=None):
            service._newError(1)
        assert not service.newNotification.emit.called

    def test_new_error_no_doc_pair(self, service):
        engine = Mock()
        engine.dao.get_state_from_id.return_value = None
        with patch.object(service, "sender", return_value=engine):
            service._newError(1)
        assert not service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_new_conflict_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        engine = Mock()
        engine.uid = "eng1"
        doc_pair = Mock()
        doc_pair.local_name = "file.txt"
        engine.dao.get_state_from_id.return_value = doc_pair
        with patch.object(service, "sender", return_value=engine):
            service._newConflict(1)
        assert service.newNotification.emit.called

    def test_new_conflict_no_sender(self, service):
        with patch.object(service, "sender", return_value=None):
            service._newConflict(1)
        assert not service.newNotification.emit.called

    def test_new_conflict_no_doc_pair(self, service):
        engine = Mock()
        engine.dao.get_state_from_id.return_value = None
        with patch.object(service, "sender", return_value=engine):
            service._newConflict(1)
        assert not service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_new_readonly_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        engine = Mock()
        engine.uid = "eng1"
        with patch.object(service, "sender", return_value=engine):
            service._newReadonly("file.txt")
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_new_readonly_with_parent(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        engine = Mock()
        engine.uid = "eng1"
        with patch.object(service, "sender", return_value=engine):
            service._newReadonly("file.txt", parent="folder")
        assert service.newNotification.emit.called

    def test_new_readonly_no_sender(self, service):
        with patch.object(service, "sender", return_value=None):
            service._newReadonly("file.txt")
        assert not service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_forbidden_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._directEditForbidden("doc1", "user1", "host1")
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_readonly_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._directEditReadonly("file.txt")
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_delete_readonly_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        engine = Mock()
        engine.uid = "eng1"
        with patch.object(service, "sender", return_value=engine):
            service._deleteReadonly("file.txt")
        assert service.newNotification.emit.called

    def test_delete_readonly_no_sender(self, service):
        with patch.object(service, "sender", return_value=None):
            service._deleteReadonly("file.txt")
        assert not service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_new_locked_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        from datetime import datetime

        engine = Mock()
        engine.uid = "eng1"
        dt = datetime(2024, 1, 1, 12, 0, 0)
        with patch.object(service, "sender", return_value=engine):
            service._newLocked("file.txt", "owner", dt)
        assert service.newNotification.emit.called

    def test_new_locked_no_sender(self, service):
        from datetime import datetime

        dt = datetime(2024, 1, 1, 12, 0, 0)
        with patch.object(service, "sender", return_value=None):
            service._newLocked("file.txt", "owner", dt)
        assert not service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_locked_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        from datetime import datetime

        dt = datetime(2024, 1, 1, 12, 0, 0)
        service._directEditLocked("file.txt", "owner", dt)
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_starting_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._directEditStarting("host1", "file.txt")
        assert service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_direct_edit_updated_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._directEditUpdated("file.txt")
        assert service.newNotification.emit.called

    def test_valid_authentication_handler(self, service):
        engine = Mock()
        engine.uid = "eng1"
        service._notifications["INVALID_CREDENTIALS_eng1"] = Mock()
        with patch.object(service, "sender", return_value=engine):
            service._validAuthentication()
        assert service.discardNotification.emit.called

    def test_valid_authentication_no_sender(self, service):
        with patch.object(service, "sender", return_value=None):
            service._validAuthentication()
        assert not service.discardNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_invalid_authentication_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        engine = Mock()
        engine.uid = "eng1"
        with patch.object(service, "sender", return_value=engine):
            service._invalidAuthentication()
        assert service.newNotification.emit.called

    def test_invalid_authentication_no_sender(self, service):
        with patch.object(service, "sender", return_value=None):
            service._invalidAuthentication()
        assert not service.newNotification.emit.called

    @patch("nxdrive.drive.notification.Translator")
    def test_display_pending_task_handler(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        service._display_pending_task("eng1", "ref1", "/path", "TASK_TITLE")
        assert service.newNotification.emit.called
