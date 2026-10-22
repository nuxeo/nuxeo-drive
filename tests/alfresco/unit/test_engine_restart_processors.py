#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""Regression tests: nothing downloads after an SSO re-authentication.

``QueueManager.init_processors()`` is connected to the remote watcher's
``initiate`` signal, which only fires on the watcher's *first* polling pass.
Stopping the engine disconnects the processors via ``remoteWatcherStopped`` ->
``shutdown_processors()``, but the watcher object outlives the stop with
``first_pass_done`` still ``True``. The next start therefore polls without
emitting ``initiate``, the processors stay disconnected, and the watcher
queues work that nobody consumes -- the logs show changes being found while no
file ever lands on disk.

An expired token takes exactly that path: ``set_invalid_credentials()`` ->
``invalidAuthentication`` -> ``stop()``, then ``update_token()`` -> ``start()``.
Suspending and resuming by hand papered over it because
``QueueManager.resume()`` emits ``queueProcessing``, which *is* connected to
``launch_processors``.
"""

from unittest.mock import Mock, patch

import pytest

from nxdrive.alfresco.engine.engine import AlfrescoEngine
from nxdrive.alfresco.engine.watcher.remote_watcher import AlfrescoRemoteWatcher


class _FakeSignal:
    """Just enough of a Qt signal to record and fire its slots."""

    def __init__(self) -> None:
        self.slots: list = []

    def connect(self, slot) -> None:
        self.slots.append(slot)

    def disconnect(self, slot) -> None:
        self.slots.remove(slot)

    def emit(self) -> None:
        for slot in list(self.slots):
            slot()


@pytest.fixture
def engine():
    """A real AlfrescoEngine with ``__init__`` bypassed.

    Subclassing keeps normal method resolution, so ``start()`` reaches the
    real ``_rearm_processors()`` instead of a mock stand-in.
    """

    class _Engine(AlfrescoEngine):
        def __init__(self) -> None:  # noqa: D107 — the real one needs a server
            pass

        # Unrelated to the queue wiring under test, and both need a Manager.
        def _check_open_file_permission(self, *, prompt_again: bool = False) -> None:
            pass

        def _cleanup_after_sync_disabled(self) -> None:
            pass

    engine = _Engine()
    engine.queue_manager = Mock()
    engine.dao = Mock()
    engine._remote_watcher = Mock()
    engine._local_watcher = Mock()
    engine._local_watcher.localScanFinished = _FakeSignal()
    return engine


def _finish_local_scan(engine):
    """The local watcher thread reaches the end of its scan."""
    engine._local_watcher.localScanFinished.emit()


def _start(engine, *, sync_enabled=True):
    with patch("nxdrive.alfresco.engine.engine.Feature") as feature, patch(
        "nxdrive.drive.engine.engine.Engine.start"
    ) as base_start:
        feature.synchronization = sync_enabled
        engine.start()
    return base_start


class TestARestartReconnectsTheProcessors:
    """The reported failure: sync looks alive but no file arrives."""

    def test_a_restart_after_the_first_pass_rearms_them(self, engine):
        engine._remote_watcher.first_pass_done = True

        _start(engine)
        _finish_local_scan(engine)

        engine.queue_manager.init_processors.assert_called_once()

    def test_the_engine_still_starts_normally(self, engine):
        engine._remote_watcher.first_pass_done = True

        base_start = _start(engine)

        base_start.assert_called_once()

    def test_rearming_happens_for_every_restart(self, engine):
        """A second re-login must work as well as the first."""
        engine._remote_watcher.first_pass_done = True

        _start(engine)
        _finish_local_scan(engine)
        _start(engine)
        _finish_local_scan(engine)

        assert engine.queue_manager.init_processors.call_count == 2


class TestAFirstStartIsUnchanged:
    """The initiate -> init_processors path must keep its old behaviour."""

    def test_a_never_polled_watcher_waits_for_initiate(self, engine):
        engine._remote_watcher.first_pass_done = False

        _start(engine)

        engine.queue_manager.init_processors.assert_not_called()

    def test_an_engine_without_a_watcher_does_not_crash(self, engine):
        engine._remote_watcher = None

        _start(engine)

        engine.queue_manager.init_processors.assert_not_called()


class TestTheWiringThatMakesThisNecessary:
    """Pins the signal behaviour the fix compensates for."""

    def test_initiate_only_fires_on_a_first_pass(self):
        """``_handle_changes`` emits ``initiate`` for the first pass only."""
        watcher = Mock(spec=AlfrescoRemoteWatcher)
        watcher.engine = Mock()
        watcher._do_handle_changes = Mock(return_value=True)
        handle = AlfrescoRemoteWatcher._handle_changes.__get__(watcher)

        handle(False)

        watcher.initiate.emit.assert_not_called()
        watcher.updated.emit.assert_called_once()

    def test_a_completed_first_pass_is_remembered(self):
        watcher = Mock(spec=AlfrescoRemoteWatcher)
        watcher.engine = Mock()
        watcher._do_handle_changes = Mock(return_value=True)
        handle = AlfrescoRemoteWatcher._handle_changes.__get__(watcher)

        handle(True)

        watcher.initiate.emit.assert_called_once()
        assert watcher.first_pass_done is True


class TestAStaleStopNotificationIsIgnored:
    """An immediate stop/start must not be undone by the queued notification.

    ``remoteWatcherStopped`` is emitted from the watcher thread, so it is
    delivered to the main thread asynchronously. ``Engine.stop()`` blocks the
    main thread while waiting for that thread, so the notification is still
    pending when it returns, and a caller that restarts right away (the
    re-login handler does ``stop()`` then ``start()``) receives it only
    *after* the processors have been reconnected.
    """

    def _restart(self, engine):
        """stop() happened: the notification is queued, then start() runs."""
        engine._remote_watcher.first_pass_done = True
        engine._stopped = True

        def _base_start():
            engine._stopped = False  # what the real Engine.start() does

        with patch("nxdrive.alfresco.engine.engine.Feature") as feature, patch(
            "nxdrive.drive.engine.engine.Engine.start", side_effect=_base_start
        ):
            feature.synchronization = True
            engine.start()
        _finish_local_scan(engine)

    def test_the_late_notification_does_not_disconnect_the_processors(self, engine):
        self._restart(engine)
        engine.queue_manager.init_processors.assert_called_once()

        # The event loop finally delivers the notification from the old run.
        engine._on_remote_watcher_stopped()

        engine.queue_manager.shutdown_processors.assert_not_called()

    def test_a_genuine_stop_still_disconnects_the_processors(self, engine):
        """The guard must not break the normal stop path."""
        engine._stopped = True

        engine._on_remote_watcher_stopped()

        engine.queue_manager.shutdown_processors.assert_called_once()


class TestQueuedWorkWaitsForTheLocalScan:
    """Items left over from before the stop must not run too early.

    ``init_processors()`` emits ``queueProcessing`` immediately, and
    ``Engine.start()`` only *starts* the watcher threads, so reconnecting
    there would let processors act on the pre-stop queues before
    ``LocalWatcher._scan()`` has recorded what the user changed on disk while
    sync was off. A queued remote deletion would delete an edited file, and a
    queued remote update would overwrite a same-size edit.
    """

    def test_nothing_runs_while_the_local_scan_is_still_going(self, engine):
        engine._remote_watcher.first_pass_done = True

        _start(engine)

        engine.queue_manager.init_processors.assert_not_called()

    def test_the_processors_come_back_once_the_scan_is_done(self, engine):
        engine._remote_watcher.first_pass_done = True

        _start(engine)
        _finish_local_scan(engine)

        engine.queue_manager.init_processors.assert_called_once()

    def test_restarting_twice_before_the_scan_connects_only_once(self, engine):
        """Repeated starts must not stack handlers on the same signal."""
        engine._remote_watcher.first_pass_done = True

        _start(engine)
        _start(engine)

        assert len(engine._local_watcher.localScanFinished.slots) == 1

        _finish_local_scan(engine)

        engine.queue_manager.init_processors.assert_called_once()

    def test_the_handler_is_released_after_it_runs(self, engine):
        """Later scans must not keep re-triggering an old restart."""
        engine._remote_watcher.first_pass_done = True

        _start(engine)
        _finish_local_scan(engine)
        _finish_local_scan(engine)

        assert engine._local_watcher.localScanFinished.slots == []
        engine.queue_manager.init_processors.assert_called_once()
