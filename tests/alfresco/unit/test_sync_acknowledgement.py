"""Acknowledgement semantics for the Device Sync delta feed (C10).

The Sync Service is at-least-once: an uncleared sync is re-delivered on the
next ``start_sync``. ``clear_sync`` is therefore the acknowledgement, and
calling it on a sync we did not finish silently discards its changes. Not
clearing costs a server-side cursor that stays pinned (there is no reaper),
so it must be skipped only on genuine failures.
"""

from time import time
from unittest.mock import MagicMock, patch

import pytest
from alfresco.exceptions import AuthenticationError as AlfrescoAuthError
from alfresco.models.subscription import SyncState

from nxdrive.alfresco.client.device_sync import (
    CONF_BOOTSTRAPPED_FOR,
    CONF_LAST_SYNC_CLEAR,
)
from nxdrive.alfresco.engine.watcher.remote_watcher import (
    CHANGE_FAILED_ERROR,
    MAX_CHANGE_RETRIES,
    SYNC_KEEPALIVE_INTERVAL,
    AlfrescoRemoteWatcher,
)
from nxdrive.drive.exceptions import ThreadInterrupt


def _watcher():
    engine = MagicMock()
    dao = MagicMock()
    with patch.object(AlfrescoRemoteWatcher, "__init__", return_value=None):
        watcher = AlfrescoRemoteWatcher(engine, dao)
    watcher.engine = engine
    watcher.dao = dao
    watcher._interact = MagicMock()
    watcher._change_failures = {}
    # Left as a MagicMock this reads as a float, so the keepalive would always
    # look due and the idle-batch branch would never be exercised.
    dao.get_config.return_value = None
    watcher._provisioner = MagicMock(
        subscriber_id="sub-1", subscription_id="subscription-1", client_version="1.0.3"
    )
    engine.remote.start_sync.return_value = MagicMock(
        status=SyncState.OK, sync_id="sync-1", message=None
    )
    return watcher


def _changes(*seq_nos):
    """Changes carrying a ``seq_no``, which the batch-repeat guard reads."""
    return [MagicMock(node_id=f"node-{n}", seq_no=n) for n in seq_nos]


def _status(
    *,
    state=SyncState.READY,
    changes=None,
    more=False,
    resets=None,
    missing=None,
    message=None,
    sync_id="sync-1",
):
    return MagicMock(
        status=state,
        changes=changes if changes is not None else [],
        more_changes=more,
        resets=resets or [],
        missing=missing or [],
        message=message,
        sync_id=sync_id,
    )


def test_fully_drained_sync_is_acknowledged():
    watcher = _watcher()
    watcher.engine.remote.get_sync.return_value = _status()

    watcher._poll_device_sync()

    watcher.engine.remote.clear_sync.assert_called_once_with(
        "sub-1", "subscription-1", "sync-1"
    )


def test_errored_sync_is_not_acknowledged():
    """Clearing here would discard changes the server would otherwise resend."""
    watcher = _watcher()
    watcher.engine.remote.get_sync.return_value = _status(
        state=SyncState.ERROR, message="boom"
    )

    watcher._poll_device_sync()

    watcher.engine.remote.clear_sync.assert_not_called()


def test_timed_out_sync_is_not_acknowledged():
    watcher = _watcher()
    watcher.engine.remote.get_sync.return_value = _status(state=SyncState.NOT_READY)

    with patch("nxdrive.alfresco.engine.watcher.remote_watcher.sleep"), patch(
        "nxdrive.alfresco.engine.watcher.remote_watcher.MAX_SYNC_POLLS", 3
    ):
        watcher._poll_device_sync()

    watcher.engine.remote.clear_sync.assert_not_called()


def test_missing_subscription_is_not_acknowledged():
    watcher = _watcher()
    watcher.engine.remote.get_sync.return_value = _status(missing=["subscription-1"])
    watcher._invalidate_provisioning = MagicMock()

    watcher._poll_device_sync()

    watcher.engine.remote.clear_sync.assert_not_called()
    watcher._invalidate_provisioning.assert_called_once()


def test_reset_is_acknowledged_because_resubscribe_replays_everything():
    """Re-subscription resends all content, so the cursor can be released."""
    watcher = _watcher()
    watcher.engine.remote.get_sync.return_value = _status(resets=["subscription-1"])
    watcher._resubscribe = MagicMock()

    watcher._poll_device_sync()

    watcher._resubscribe.assert_called_once()
    watcher.engine.remote.clear_sync.assert_called_once()


def test_exception_while_draining_leaves_sync_unacknowledged():
    watcher = _watcher()
    watcher.engine.remote.get_sync.side_effect = OSError("connection reset")

    with pytest.raises(OSError):
        watcher._poll_device_sync()

    watcher.engine.remote.clear_sync.assert_not_called()


# -- retry then escalate: transient faults recover, poison changes surface --


def test_failing_change_is_retried_not_skipped():
    """First failures must propagate so the sync goes unacknowledged."""
    watcher = _watcher()
    watcher._change_failures = {}
    change = MagicMock(node_id="b", seq_no=2)
    watcher._dedupe_changes = MagicMock(return_value=[change])
    watcher._apply_change = MagicMock(side_effect=ValueError("bad node"))

    with pytest.raises(ValueError):
        watcher._apply_changes([change])

    assert watcher._change_failures["b"] == 1


def test_change_is_abandoned_after_the_retry_budget():
    watcher = _watcher()
    change = MagicMock(node_id="b", seq_no=2)
    watcher._change_failures = {"b": MAX_CHANGE_RETRIES - 1}
    watcher._dedupe_changes = MagicMock(return_value=[change])
    watcher._apply_change = MagicMock(side_effect=ValueError("bad node"))
    watcher._report_change_failure = MagicMock()

    # No raise: the page completes so later changes are not blocked.
    assert watcher._apply_changes([change]) == 0
    watcher._report_change_failure.assert_called_once()
    assert "b" not in watcher._change_failures


def test_success_clears_the_failure_counter():
    watcher = _watcher()
    change = MagicMock(node_id="b", seq_no=2)
    watcher._change_failures = {"b": 2}
    watcher._dedupe_changes = MagicMock(return_value=[change])
    watcher._apply_change = MagicMock(return_value=True)

    assert watcher._apply_changes([change]) == 1
    assert "b" not in watcher._change_failures


def test_abandoned_change_is_reported_to_the_user():
    """The pair must cross the give-up threshold so the systray lists it."""
    watcher = _watcher()
    pair = MagicMock(id=7)
    watcher.dao.get_normal_state_from_remote.return_value = pair
    watcher.engine.queue_manager.get_error_threshold.return_value = 3
    change = MagicMock(node_id="b", seq_no=2)

    watcher._report_change_failure(change, ValueError("bad node"))

    kwargs = watcher.dao.increase_error.call_args.kwargs
    assert kwargs["incr"] == 4
    assert watcher.dao.increase_error.call_args.args[1] == CHANGE_FAILED_ERROR
    watcher.engine.queue_manager.push_error.assert_called_once_with(pair)


def test_abandoned_change_without_a_pair_forces_a_reseed():
    """No row to flag, so the tree walk is the only route back to correctness."""
    watcher = _watcher()
    watcher.dao.get_normal_state_from_remote.return_value = None
    change = MagicMock(node_id="b", seq_no=2)

    watcher._report_change_failure(change, ValueError("bad node"))

    watcher.dao.update_config.assert_called_once_with(CONF_BOOTSTRAPPED_FOR, None)
    watcher.dao.increase_error.assert_not_called()


def test_auth_error_in_a_change_still_propagates():
    watcher = _watcher()
    watcher._change_failures = {}
    change = MagicMock(node_id="a", seq_no=1)
    watcher._dedupe_changes = MagicMock(return_value=[change])
    watcher._apply_change = MagicMock(side_effect=AlfrescoAuthError("expired"))

    with pytest.raises(AlfrescoAuthError):
        watcher._apply_changes([change])

    # Auth is not the change's fault, so it must not consume the budget.
    assert watcher._change_failures == {}


def test_thread_interrupt_in_a_change_still_propagates():
    watcher = _watcher()
    change = MagicMock(node_id="a", seq_no=1)
    watcher._dedupe_changes = MagicMock(return_value=[change])
    watcher._apply_change = MagicMock(side_effect=ThreadInterrupt())

    with pytest.raises(ThreadInterrupt):
        watcher._apply_changes([change])


class TestBatching:
    """A backlog is drained one POST/GET/DELETE round per batch.

    The service caps a batch at 100 changes and only moves ``last_seq_num``
    when a sync is cleared, so re-polling one sync returns the identical
    payload forever -- the cause of "only 100 of 500 files arrived".
    """

    def test_a_new_sync_is_started_for_every_batch(self):
        watcher = _watcher()
        watcher._apply_changes = MagicMock(return_value=1)
        watcher.engine.remote.get_sync.side_effect = [
            _status(changes=_changes(1), more=True),
            _status(changes=_changes(2), more=True),
            _status(changes=_changes(3), more=False),
        ]

        watcher._poll_device_sync()

        assert watcher.engine.remote.start_sync.call_count == 3
        assert watcher.engine.remote.clear_sync.call_count == 3

    def test_every_batch_is_applied(self):
        watcher = _watcher()
        watcher._apply_changes = MagicMock(return_value=1)
        batches = [_changes(1), _changes(2), _changes(3)]
        watcher.engine.remote.get_sync.side_effect = [
            _status(changes=batches[0], more=True),
            _status(changes=batches[1], more=True),
            _status(changes=batches[2], more=False),
        ]

        watcher._poll_device_sync()

        assert [c.args[0] for c in watcher._apply_changes.call_args_list] == batches

    def test_each_batch_is_cleared_before_the_next_is_started(self):
        """Clearing is what commits the cursor, so it must precede the next POST."""
        watcher = _watcher()
        watcher._apply_changes = MagicMock(return_value=1)
        watcher.engine.remote.get_sync.side_effect = [
            _status(changes=_changes(1), more=True),
            _status(changes=_changes(2), more=False),
        ]
        calls = []
        watcher.engine.remote.start_sync.side_effect = lambda *a, **k: (
            calls.append("start") or MagicMock(status=SyncState.OK, sync_id="sync-1")
        )
        watcher.engine.remote.clear_sync.side_effect = lambda *a: calls.append("clear")

        watcher._poll_device_sync()

        assert calls == ["start", "clear", "start", "clear"]

    def test_a_single_batch_stops_after_one_round(self):
        watcher = _watcher()
        watcher.engine.remote.get_sync.return_value = _status(more=False)

        watcher._poll_device_sync()

        assert watcher.engine.remote.start_sync.call_count == 1
        watcher.engine.remote.clear_sync.assert_called_once_with(
            "sub-1", "subscription-1", "sync-1"
        )

    def test_an_unapplied_batch_is_not_cleared_and_stops_the_loop(self):
        """Clearing here advances the cursor past changes we dropped."""
        watcher = _watcher()
        watcher.engine.remote.get_sync.return_value = _status(
            state=SyncState.ERROR, message="boom"
        )

        watcher._poll_device_sync()

        watcher.engine.remote.clear_sync.assert_not_called()
        assert watcher.engine.remote.start_sync.call_count == 1

    def test_a_failed_clear_stops_the_loop(self):
        """The cursor did not move, so another round would re-apply the batch."""
        watcher = _watcher()
        watcher._apply_changes = MagicMock(return_value=1)
        watcher.engine.remote.get_sync.return_value = _status(
            changes=_changes(1), more=True
        )
        watcher.engine.remote.clear_sync.side_effect = OSError("network")

        watcher._poll_device_sync()

        assert watcher.engine.remote.start_sync.call_count == 1

    def test_a_repeated_batch_stops_instead_of_looping(self):
        """An expired sync clears with 204 without moving the cursor."""
        watcher = _watcher()
        watcher._apply_changes = MagicMock(return_value=1)
        watcher.engine.remote.get_sync.return_value = _status(
            changes=_changes(7), more=True
        )

        watcher._poll_device_sync()

        assert watcher.engine.remote.start_sync.call_count == 2

    def test_the_round_budget_is_bounded(self):
        watcher = _watcher()
        watcher._apply_changes = MagicMock(return_value=1)
        seqs = iter(range(1, 500))
        watcher.engine.remote.get_sync.side_effect = lambda *a: _status(
            changes=_changes(next(seqs)), more=True
        )

        with patch("nxdrive.alfresco.engine.watcher.remote_watcher.MAX_SYNC_ROUNDS", 4):
            watcher._poll_device_sync()

        assert watcher.engine.remote.start_sync.call_count == 4


class TestIdleBatch:
    """An empty batch must not be acknowledged.

    Its pending bookmark is the highest sequence number ever handed out, which
    runs ahead of changes that are allocated but not yet visible -- committing
    it skips them permanently.
    """

    def test_an_empty_batch_is_not_cleared(self):
        watcher = _watcher()
        watcher.dao.get_config.return_value = str(time())
        watcher.engine.remote.get_sync.return_value = _status(more=False)

        watcher._poll_device_sync()

        watcher.engine.remote.clear_sync.assert_not_called()

    def test_a_non_empty_batch_is_still_cleared(self):
        watcher = _watcher()
        watcher.dao.get_config.return_value = str(time())
        watcher._apply_changes = MagicMock(return_value=1)
        watcher.engine.remote.get_sync.return_value = _status(
            changes=_changes(1), more=False
        )

        watcher._poll_device_sync()

        watcher.engine.remote.clear_sync.assert_called_once()

    def test_an_empty_batch_is_cleared_once_the_keepalive_is_due(self):
        """Only a cleared sync refreshes the server's staleness clock."""
        watcher = _watcher()
        watcher.dao.get_config.return_value = str(time() - SYNC_KEEPALIVE_INTERVAL - 1)
        watcher.engine.remote.get_sync.return_value = _status(more=False)

        watcher._poll_device_sync()

        watcher.engine.remote.clear_sync.assert_called_once()

    def test_a_subscription_that_never_cleared_is_due(self):
        watcher = _watcher()
        watcher.dao.get_config.return_value = None
        watcher.engine.remote.get_sync.return_value = _status(more=False)

        watcher._poll_device_sync()

        watcher.engine.remote.clear_sync.assert_called_once()

    def test_clearing_records_when_it_happened(self):
        watcher = _watcher()
        watcher._apply_changes = MagicMock(return_value=1)
        watcher.engine.remote.get_sync.return_value = _status(
            changes=_changes(1), more=False
        )

        watcher._poll_device_sync()

        key, value = watcher.dao.update_config.call_args.args
        assert key == CONF_LAST_SYNC_CLEAR
        assert abs(time() - float(value)) < 5

    def test_a_failed_clear_is_not_recorded(self):
        watcher = _watcher()
        watcher._apply_changes = MagicMock(return_value=1)
        watcher.engine.remote.get_sync.return_value = _status(
            changes=_changes(1), more=False
        )
        watcher.engine.remote.clear_sync.side_effect = OSError("network")

        watcher._poll_device_sync()

        watcher.dao.update_config.assert_not_called()
