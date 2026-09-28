"""Acknowledgement semantics for the Device Sync delta feed (C10).

The Sync Service is at-least-once: an uncleared sync is re-delivered on the
next ``start_sync``. ``clear_sync`` is therefore the acknowledgement, and
calling it on a sync we did not finish silently discards its changes. Not
clearing costs a server-side cursor that stays pinned (there is no reaper),
so it must be skipped only on genuine failures.
"""

from unittest.mock import MagicMock, patch

import pytest
from alfresco.exceptions import AuthenticationError as AlfrescoAuthError
from alfresco.models.subscription import SyncState

from nxdrive.alfresco.client.device_sync import CONF_BOOTSTRAPPED_FOR
from nxdrive.alfresco.engine.watcher.remote_watcher import (
    CHANGE_FAILED_ERROR,
    MAX_CHANGE_RETRIES,
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
    watcher._provisioner = MagicMock(
        subscriber_id="sub-1", subscription_id="subscription-1", client_version="1.0.3"
    )
    engine.remote.start_sync.return_value = MagicMock(
        status=SyncState.OK, sync_id="sync-1", message=None
    )
    return watcher


def _status(
    *,
    state=SyncState.READY,
    changes=None,
    more=False,
    resets=None,
    missing=None,
    message=None
):
    return MagicMock(
        status=state,
        changes=changes if changes is not None else [],
        more_changes=more,
        resets=resets or [],
        missing=missing or [],
        message=message,
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
