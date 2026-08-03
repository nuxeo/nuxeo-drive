import os
import re
from unittest.mock import Mock
from uuid import uuid4

from nxdrive.manager import Manager


def test_send_sync_status(manager, engine):
    """This method is to test weather drive need to send sync status
    or not based on which directory user is currently watching.
    Is it drive local_folder e.g "/Users/test/Nuxeo Drive" or watching
    some other folder like Downloads, Applications etc.
    """
    tmp_path = os.path.expandvars("C:\\test\\%username%\\Downloads")
    manager.engines = {f"{uuid4()}": engine}
    manager.osi.send_content_sync_status = Mock()
    engine.dao.get_local_children = Mock()

    manager.send_sync_status(manager, tmp_path)

    # No need to send status as user is watching Downloads folder
    assert not re.search(f"{str(engine.local_folder)}/", f"{str(tmp_path)}/")


class TestInitDirectTransferResumption:
    """Test cases for Manager._init_direct_transfer_resumption method."""

    def test_skips_empty_and_zero_schedules(self):
        """Session without usable schedule should be ignored."""
        engine = Mock()
        engine.dao.get_active_sessions_raw.return_value = [
            {"uid": 1, "scheduled_at": None},
            {"uid": 2, "scheduled_at": 0},
            {"uid": 3, "scheduled_at": "0"},
            {"uid": 4},
        ]
        manager = Mock()
        manager.engines = {"e1": engine}

        Manager._init_direct_transfer_resumption(manager)

        engine.resume_scheduled_session.assert_not_called()
        engine.startTimerSignal.emit.assert_not_called()

    def test_resumes_when_schedule_has_passed(self):
        """Past schedule should resume session immediately."""
        engine = Mock()
        engine.dao.get_active_sessions_raw.return_value = [
            {"uid": 10, "scheduled_at": "2000-01-01T00:00:00+00:00"}
        ]
        manager = Mock()
        manager.engines = {"e1": engine}

        Manager._init_direct_transfer_resumption(manager)

        engine.resume_scheduled_session.assert_called_once_with(10)
        engine.startTimerSignal.emit.assert_not_called()

    def test_emits_timer_when_schedule_is_in_future(self):
        """Future schedule should emit timer restart signal with positive delay."""
        engine = Mock()
        engine.dao.get_active_sessions_raw.return_value = [
            {"uid": 20, "scheduled_at": "2999-01-01T00:00:00+00:00"}
        ]
        manager = Mock()
        manager.engines = {"e1": engine}

        Manager._init_direct_transfer_resumption(manager)

        engine.resume_scheduled_session.assert_not_called()
        engine.startTimerSignal.emit.assert_called_once()
        args = engine.startTimerSignal.emit.call_args.args
        assert args[0] == 20
        assert isinstance(args[1], int)
        assert args[1] > 0

    def test_future_naive_datetime_emits_timer(self):
        """Naive datetime should be treated as UTC and emit timer restart."""
        engine = Mock()
        engine.dao.get_active_sessions_raw.return_value = [
            {"uid": 30, "scheduled_at": "2999-01-01T00:00:00"}
        ]
        manager = Mock()
        manager.engines = {"e1": engine}

        Manager._init_direct_transfer_resumption(manager)

        engine.resume_scheduled_session.assert_not_called()
        engine.startTimerSignal.emit.assert_called_once()
        args = engine.startTimerSignal.emit.call_args.args
        assert args[0] == 30
        assert isinstance(args[1], int)
        assert args[1] > 0

    def test_invalid_schedule_is_logged_and_continues(self):
        """Invalid schedule should not crash and should continue loop."""
        engine = Mock()
        engine.dao.get_active_sessions_raw.return_value = [
            {"uid": 40, "scheduled_at": "not-a-date"},
            {"uid": 41, "scheduled_at": "2000-01-01T00:00:00+00:00"},
        ]
        manager = Mock()
        manager.engines = {"e1": engine}

        Manager._init_direct_transfer_resumption(manager)

        # First item fails parsing, second one should still be handled.
        engine.resume_scheduled_session.assert_called_once_with(41)
        engine.startTimerSignal.emit.assert_not_called()
