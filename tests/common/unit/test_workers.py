"""Tests for nxdrive/drive/engine/workers.py"""

from time import time
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.drive.engine.workers import EngineWorker, PollWorker, Runner, Worker


def _worker_init(self, name):
    """Replacement __init__ for Worker that skips Qt setup."""
    self._name = name
    self._running = False
    self._continue = False
    self._action = None
    self.thread_id = None
    self._pause = False
    self.thread = MagicMock()
    # Worker base doesn't define _metrics but suppress(AttributeError)
    # in get_metrics expects it or AttributeError; PyQt6 raises RuntimeError
    # for undefined attrs on QObject subclasses, so we must predefine it.
    # (In production, this path is only hit via PollWorker/EngineWorker which set it.)


def _poll_worker_init(self, check_interval, name):
    """Replacement __init__ for PollWorker that skips Qt setup."""
    _worker_init(self, name)
    self._check_interval = check_interval
    self._next_check = 0
    self._metrics = {"last_poll": 0}


def _engine_worker_init(self, engine, dao, name):
    """Replacement __init__ for EngineWorker that skips Qt setup."""
    _worker_init(self, name)
    self.engine = engine
    self.dao = dao


# ─── Runner Tests ────────────────────────────────────────────────────────────


def test_runner_init():
    with patch.object(Runner, "__init__", lambda self, *a, **kw: None):
        r = Runner.__new__(Runner)
    r.fn = MagicMock()
    r.args = (1,)
    r.kwargs = {"k": "v"}
    r.error = None
    assert r.error is None


def test_runner_run_success():
    fn = MagicMock()
    with patch("nxdrive.drive.engine.workers.QRunnable.__init__", lambda self: None):
        r = Runner(fn, "a", b="c")
    r.run()
    fn.assert_called_once_with("a", b="c")
    assert r.error is None


def test_runner_run_exception():
    exc = ValueError("boom")
    fn = MagicMock(side_effect=exc)
    with patch("nxdrive.drive.engine.workers.QRunnable.__init__", lambda self: None):
        r = Runner(fn)
    r.run()
    assert r.error is exc


# ─── Worker Tests ────────────────────────────────────────────────────────────


def _make_worker():
    with patch.object(Worker, "__init__", _worker_init):
        return Worker("test-worker")


def test_worker_init():
    w = _make_worker()
    assert w._name == "test-worker"
    assert w._running is False
    assert w._continue is False
    assert w._pause is False


def test_worker_repr():
    w = _make_worker()
    w.thread_id = 123
    assert "123" in repr(w)


def test_worker_export():
    w = _make_worker()
    w._continue = True
    w._action = MagicMock()
    w._action.export.return_value = {"type": "idle"}
    export = w.export()
    assert export["name"] == "test-worker"
    assert export["started"] is True
    assert export["paused"] is False


def test_worker_is_started():
    w = _make_worker()
    assert w.is_started() is False
    w._continue = True
    assert w.is_started() is True


def test_worker_is_paused():
    w = _make_worker()
    assert w.is_paused() is False
    w._pause = True
    assert w.is_paused() is True


def test_worker_start():
    w = _make_worker()
    w.start()
    w.thread.start.assert_called_once()


def test_worker_stop_not_running():
    w = _make_worker()
    w.thread.isRunning.return_value = False
    w.stop()
    assert w._continue is False


def test_worker_stop_zombie():
    w = _make_worker()
    w.thread.isRunning.return_value = True
    w.stop()
    w.thread.wait.assert_called_once_with(5000)
    w.thread.terminate.assert_called_once()


def test_worker_resume():
    w = _make_worker()
    w._pause = True
    w.resume()
    assert w._pause is False


def test_worker_suspend():
    w = _make_worker()
    w.suspend()
    assert w._pause is True


def test_worker_quit():
    w = _make_worker()
    w._continue = True
    w.quit()
    assert w._continue is False
    w.thread.quit.assert_called_once()


def test_worker_interact_raises_thread_interrupt():
    from nxdrive.drive.exceptions import ThreadInterrupt

    w = _make_worker()
    w._continue = False
    w._pause = False
    with patch("nxdrive.drive.engine.workers.QCoreApplication"):
        with pytest.raises(ThreadInterrupt):
            w._interact()


def test_worker_interact_processes_events():
    w = _make_worker()
    w._continue = True
    w._pause = False
    with patch("nxdrive.drive.engine.workers.QCoreApplication"):
        w._interact()  # Should not raise


def test_worker_finished():
    w = _make_worker()
    w._finished()  # Just logs, should not raise


def test_worker_action_property_getter_idle():
    from nxdrive.drive.engine.activity import IdleAction

    w = _make_worker()
    w._action = None
    w.thread_id = None
    action = w.action
    assert isinstance(action, IdleAction)


def test_worker_action_property_setter():
    w = _make_worker()
    mock_action = MagicMock()
    w.action = mock_action
    assert w._action is mock_action


def test_worker_get_metrics():
    """Worker.get_metrics() — the _metrics update path is tested via PollWorker."""
    pw = _make_poll_worker()
    pw.thread_id = 42
    pw._action = MagicMock()
    metrics = pw.get_metrics()
    assert metrics["name"] == "poll-test"
    assert metrics["thread_id"] == 42
    assert "last_poll" in metrics  # from _metrics


def test_worker_get_metrics_with_extra():
    w = _make_worker()
    w._metrics = {"extra": "val"}
    w._action = MagicMock()
    metrics = w.get_metrics()
    assert metrics["extra"] == "val"


def test_worker_run_sets_state():
    from nxdrive.drive.exceptions import ThreadInterrupt

    w = _make_worker()
    w._execute = MagicMock(side_effect=ThreadInterrupt())
    with patch("nxdrive.drive.engine.workers.current_thread_id", return_value=99):
        w.run()
    assert w._running is False


def test_worker_run_already_running():
    w = _make_worker()
    w._running = True
    w._execute = MagicMock()
    w.run()
    w._execute.assert_not_called()


def test_worker_run_handles_generic_exception():
    w = _make_worker()
    w._execute = MagicMock(side_effect=RuntimeError("oops"))
    with patch("nxdrive.drive.engine.workers.current_thread_id", return_value=1):
        w.run()
    assert w._running is False


# ─── EngineWorker Tests ──────────────────────────────────────────────────────


def _make_engine_worker():
    engine = MagicMock()
    dao = MagicMock()
    with patch.object(EngineWorker, "__init__", _engine_worker_init):
        return EngineWorker(engine, dao, "engine-worker")


def test_engine_worker_init():
    ew = _make_engine_worker()
    assert ew._name == "engine-worker"


def test_engine_worker_giveup_error():
    ew = _make_engine_worker()
    doc_pair = MagicMock(pair_state="locally_modified")
    exc = ValueError("bad")
    ew.giveup_error(doc_pair, "TEST_ERROR", exception=exc)
    ew.dao.increase_error.assert_called_once()
    ew.engine.queue_manager.push_error.assert_called_once()
    ew.engine.send_metric.assert_called_once_with("sync", "error", "TEST_ERROR")


def test_engine_worker_giveup_error_no_exception():
    ew = _make_engine_worker()
    doc_pair = MagicMock(pair_state="x")
    ew.giveup_error(doc_pair, "ERR")
    call_args = ew.dao.increase_error.call_args
    assert call_args.kwargs.get("details") is None


def test_engine_worker_increase_error():
    ew = _make_engine_worker()
    doc_pair = MagicMock()
    exc = OSError("disk")
    ew.increase_error(doc_pair, "IO", exception=exc)
    ew.dao.increase_error.assert_called_once()
    ew.engine.queue_manager.push_error.assert_called_once()


def test_engine_worker_increase_error_no_exception():
    ew = _make_engine_worker()
    doc_pair = MagicMock()
    ew.increase_error(doc_pair, "IO")
    call_args = ew.dao.increase_error.call_args
    assert call_args.kwargs.get("details") is None


def test_engine_worker_remove_void_transfers_folderish():
    ew = _make_engine_worker()
    doc_pair = MagicMock(folderish=True)
    ew.remove_void_transfers(doc_pair)
    ew.dao.remove_transfer.assert_not_called()


def test_engine_worker_remove_void_transfers_non_direct():
    ew = _make_engine_worker()
    doc_pair = MagicMock(folderish=False, local_state="created", local_path="/a/b")
    ew.engine.local.abspath.return_value = "/full/a/b"
    ew.remove_void_transfers(doc_pair)
    assert ew.dao.remove_transfer.call_count == 2


def test_engine_worker_remove_void_transfers_direct():
    ew = _make_engine_worker()
    doc_pair = MagicMock(folderish=False, local_state="direct", local_path="/x/y")
    ew.remove_void_transfers(doc_pair)
    assert ew.dao.remove_transfer.call_count == 2


# ─── PollWorker Tests ────────────────────────────────────────────────────────


def _make_poll_worker():
    with patch.object(PollWorker, "__init__", _poll_worker_init):
        return PollWorker(60, "poll-test")


def test_poll_worker_init():
    pw = _make_poll_worker()
    assert pw._check_interval == 60
    assert pw._next_check == 0
    assert pw._metrics == {"last_poll": 0}


def test_poll_worker_enable():
    pw = _make_poll_worker()
    assert pw.enable is True


def test_poll_worker_get_metrics():
    pw = _make_poll_worker()
    pw._action = MagicMock()
    metrics = pw.get_metrics()
    assert "polling_interval" in metrics
    assert "polling_next" in metrics


def test_poll_worker_get_last_poll_never():
    pw = _make_poll_worker()
    assert pw.get_last_poll() == -1


def test_poll_worker_get_last_poll_has_polled():
    pw = _make_poll_worker()
    pw._metrics["last_poll"] = int(time()) - 10
    last = pw.get_last_poll()
    assert 9 <= last <= 12


def test_poll_worker_get_next_poll():
    pw = _make_poll_worker()
    pw._next_check = int(time()) + 30
    assert 28 <= pw.get_next_poll() <= 31


def test_poll_worker_force_poll():
    pw = _make_poll_worker()
    pw._next_check = 99999
    pw.force_poll()
    assert pw._next_check == 0


def test_poll_worker_default_poll():
    pw = _make_poll_worker()
    assert pw._poll() is True
