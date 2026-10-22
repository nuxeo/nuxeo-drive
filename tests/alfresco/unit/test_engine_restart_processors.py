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
    return engine


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

        engine.queue_manager.init_processors.assert_called_once()

    def test_the_engine_still_starts_normally(self, engine):
        engine._remote_watcher.first_pass_done = True

        base_start = _start(engine)

        base_start.assert_called_once()

    def test_rearming_happens_for_every_restart(self, engine):
        """A second re-login must work as well as the first."""
        engine._remote_watcher.first_pass_done = True

        _start(engine)
        _start(engine)

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
