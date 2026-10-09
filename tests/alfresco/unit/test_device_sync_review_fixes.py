"""Regression tests for the Device Sync review findings on PR #6486.

Each test pins one failure mode that previously went unnoticed because the
change feed never replays content it has already reported.
"""

from datetime import datetime, timezone
from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

import pytest
from alfresco.exceptions import AlfrescoError
from alfresco.exceptions import AuthenticationError as AlfrescoAuthError
from alfresco.exceptions import NotFoundError
from alfresco.models.subscription import SyncState

from nxdrive.alfresco.client.device_sync import (
    CONF_BOOTSTRAPPED_FOR,
    CONF_ORPHAN_SUBSCRIPTIONS,
    CONF_SEEDING_FOR,
    CONF_SUBSCRIBER_ID,
    CONF_SUBSCRIPTION_ID,
    DeviceSyncProvisioner,
)
from nxdrive.alfresco.engine.watcher.remote_watcher import (
    LISTING_RETRIES,
    AlfrescoRemoteWatcher,
)
from nxdrive.drive.exceptions import ThreadInterrupt

#: Total listing attempts: the first try plus its retries.
MAX_LISTING_ATTEMPTS = LISTING_RETRIES + 1


def _watcher():
    engine = MagicMock()
    dao = MagicMock()
    dao.get_config.return_value = None
    # Nothing has been checkpointed yet, otherwise every folder looks scanned.
    dao.is_path_scanned.return_value = False
    dao.get_paths_to_scan.return_value = []
    with patch.object(AlfrescoRemoteWatcher, "__init__", return_value=None):
        watcher = AlfrescoRemoteWatcher(engine, dao)
    watcher.engine = engine
    watcher.dao = dao
    watcher._next_check = 0
    watcher._interact = MagicMock()
    watcher._unfiltered_nodes = set()
    watcher._unfiltered_needs_scan = False
    watcher.remoteScanFinished = MagicMock()
    return watcher


def _remote_info(name, *, uid="node-1", folderish=False, path=None):
    info = MagicMock()
    info.name = name
    info.uid = uid
    info.folderish = folderish
    info.path = path or f"/Company Home/{name}"
    info.parent_uid = "parent-1"
    info.last_modification_time = None
    return info


# -- B3: a partial walk must not be recorded as a completed bootstrap --------


def test_scan_remote_recursive_reports_failure_when_children_unlistable():
    watcher = _watcher()
    remote = watcher.engine.remote
    remote.client.nodes.iter_children.side_effect = OSError("boom")

    pair = MagicMock(remote_parent_path="", remote_ref="root-id")
    with patch("nxdrive.alfresco.engine.watcher.remote_watcher.sleep"):
        assert (
            watcher._scan_remote_recursive(pair, _remote_info("root", folderish=True))
            is False
        )
    # The folder is recorded so the next cycle retries only what failed.
    watcher.dao.add_path_to_scan.assert_called_once_with("node-1")


def test_scan_remote_recursive_propagates_failure_from_subtree():
    """The root lists fine but a nested folder does not: still incomplete."""
    watcher = _watcher()
    remote = watcher.engine.remote
    root = _remote_info("root", uid="root-id", folderish=True)
    child = _remote_info("sub", uid="sub-1", folderish=True)

    def _iter_children(uid, **kwargs):
        if uid == "root-id":
            return [MagicMock()]
        raise OSError("subtree unavailable")

    remote.client.nodes.iter_children.side_effect = _iter_children
    remote._node_to_remote_file_info.return_value = child
    watcher._is_filtered_path = MagicMock(return_value=False)
    watcher.dao.get_remote_children.return_value = []
    watcher._reconcile_child = MagicMock(
        return_value=MagicMock(remote_parent_path="", remote_ref="sub-1")
    )

    pair = MagicMock(remote_parent_path="", remote_ref="root-id")
    with patch("nxdrive.alfresco.engine.watcher.remote_watcher.sleep"):
        assert watcher._scan_remote_recursive(pair, root) is False


# -- Resumable seeding: a retry costs only what actually failed -------------


def test_already_scanned_folder_is_skipped():
    """The whole point of resumption: no HTTP call for a done subtree."""
    watcher = _watcher()
    watcher.dao.is_path_scanned.return_value = True

    pair = MagicMock(remote_parent_path="", remote_ref="root-id")
    assert (
        watcher._scan_remote_recursive(pair, _remote_info("root", folderish=True))
        is True
    )
    watcher.engine.remote.client.nodes.iter_children.assert_not_called()


def test_completed_folder_is_checkpointed_by_node_id():
    watcher = _watcher()
    remote = watcher.engine.remote
    remote.client.nodes.iter_children.return_value = []
    watcher.dao.get_remote_children.return_value = []

    pair = MagicMock(remote_parent_path="", remote_ref="root-id")
    watcher._scan_remote_recursive(pair, _remote_info("root", folderish=True))

    # Keyed on the node id, not the path, which changes on rename.
    watcher.dao.add_path_scanned.assert_called_once_with("node-1")


def test_listing_is_retried_before_giving_up():
    watcher = _watcher()
    remote = watcher.engine.remote
    remote.client.nodes.iter_children.side_effect = OSError("Errno 49")

    with patch("nxdrive.alfresco.engine.watcher.remote_watcher.sleep") as mock_sleep:
        watcher._list_children(remote, _remote_info("root", folderish=True))

    assert remote.client.nodes.iter_children.call_count == MAX_LISTING_ATTEMPTS
    assert mock_sleep.call_count == LISTING_RETRIES


def test_listing_recovers_on_a_later_attempt():
    watcher = _watcher()
    remote = watcher.engine.remote
    remote.client.nodes.iter_children.side_effect = [OSError("Errno 49"), []]

    with patch("nxdrive.alfresco.engine.watcher.remote_watcher.sleep"):
        assert watcher._list_children(remote, _remote_info("root")) == []


def test_completed_seed_clears_its_checkpoints():
    watcher = _watcher()
    watcher._provisioner = MagicMock(subscription_id="sub-1")
    watcher._scan_remote_tree = MagicMock(return_value=True)
    watcher.engine.queue_manager.get_overall_size.return_value = 0

    watcher._bootstrap_if_needed()

    watcher.dao.clean_scanned.assert_called()


def test_incomplete_seed_keeps_its_checkpoints():
    """Checkpoints must survive so the retry skips finished folders."""
    watcher = _watcher()
    watcher._provisioner = MagicMock(subscription_id="sub-1")
    watcher.dao.get_config.return_value = "sub-1"
    watcher._scan_remote_tree = MagicMock(return_value=False)

    watcher._bootstrap_if_needed()

    watcher.dao.clean_scanned.assert_not_called()


def test_new_subscription_discards_stale_checkpoints():
    watcher = _watcher()
    watcher._provisioner = MagicMock(subscription_id="sub-2")
    # Progress recorded against a different subscription.
    watcher.dao.get_config.side_effect = lambda key: (
        "sub-1" if key == CONF_SEEDING_FOR else None
    )
    watcher._scan_remote_tree = MagicMock(return_value=False)

    watcher._bootstrap_if_needed()

    watcher.dao.clean_scanned.assert_called_once()


def test_bootstrap_not_recorded_when_scan_incomplete():
    watcher = _watcher()
    provisioner = MagicMock(subscription_id="sub-1")
    watcher._provisioner = provisioner
    watcher.dao.get_config.return_value = None
    watcher._scan_remote_tree = MagicMock(return_value=False)

    watcher._bootstrap_if_needed()

    # Any update_config call must not be the one that marks seeding done.
    for call in watcher.dao.update_config.call_args_list:
        assert call.args[:2] != (CONF_BOOTSTRAPPED_FOR, "sub-1")


def test_bootstrap_recorded_when_scan_completes():
    watcher = _watcher()
    watcher._provisioner = MagicMock(subscription_id="sub-1")
    watcher.dao.get_config.return_value = None
    watcher._scan_remote_tree = MagicMock(return_value=True)
    watcher.engine.queue_manager.get_overall_size.return_value = 0

    watcher._bootstrap_if_needed()

    watcher.dao.update_config.assert_any_call(CONF_BOOTSTRAPPED_FOR, "sub-1")


# -- B4: a failed un-filter must keep its node id for a retry ----------------


def test_unfiltered_node_is_requeued_when_fetch_fails():
    watcher = _watcher()
    watcher._unfiltered_nodes = {"node-1"}
    watcher.engine.remote.get_node.side_effect = OSError("transient")

    watcher._apply_unfiltered()

    assert watcher._unfiltered_nodes == {"node-1"}


def test_unfiltered_node_is_dropped_when_gone_server_side():
    watcher = _watcher()
    watcher._unfiltered_nodes = {"node-1"}
    watcher.engine.remote.get_node.side_effect = NotFoundError("gone")

    watcher._apply_unfiltered()

    assert watcher._unfiltered_nodes == set()


def test_unfiltered_auth_failure_propagates():
    watcher = _watcher()
    watcher._unfiltered_nodes = {"node-1"}
    watcher.engine.remote.get_node.side_effect = AlfrescoAuthError("expired")

    with pytest.raises(AlfrescoAuthError):
        watcher._apply_unfiltered()


def test_unfiltered_auth_failure_keeps_every_pending_id():
    """The raise aborts the loop, so untouched ids must survive it too."""
    watcher = _watcher()
    watcher._unfiltered_nodes = {"node-1", "node-2", "node-3"}
    watcher.engine.remote.get_node.side_effect = AlfrescoAuthError("expired")

    with pytest.raises(AlfrescoAuthError):
        watcher._apply_unfiltered()

    assert watcher._unfiltered_nodes == {"node-1", "node-2", "node-3"}


def test_unfiltered_ids_after_the_failure_are_not_dropped():
    watcher = _watcher()
    watcher._unfiltered_nodes = {"a", "b", "c"}
    # "a" resolves, "b" blows up, "c" was never reached.
    watcher._resolve_unfiltered_node = MagicMock(
        side_effect=[True, AlfrescoAuthError("expired")]
    )

    with pytest.raises(AlfrescoAuthError):
        watcher._apply_unfiltered()

    assert watcher._unfiltered_nodes == {"b", "c"}


# -- C2: a reset is only acknowledged once the replay is guaranteed --------


def test_failed_resubscribe_leaves_the_sync_unacknowledged():
    watcher = _watcher()
    watcher._provisioner = MagicMock(subscriber_id="s", subscription_id="sub-1")
    watcher._provisioner.resubscribe.return_value = False
    watcher._root_node_id = "root-id"
    watcher.engine.remote.get_sync.return_value = MagicMock(
        status=SyncState.READY,
        changes=[],
        more_changes=False,
        resets=["sub-1"],
        missing=[],
    )
    watcher.engine.remote.start_sync.return_value = MagicMock(
        status=SyncState.OK, sync_id="sync-1", message=None
    )

    watcher._poll_device_sync()

    watcher.engine.remote.clear_sync.assert_not_called()


def test_successful_resubscribe_acknowledges_the_sync():
    watcher = _watcher()
    watcher._provisioner = MagicMock(subscriber_id="s", subscription_id="sub-1")
    watcher._provisioner.resubscribe.return_value = True
    watcher._root_node_id = "root-id"
    watcher.engine.remote.get_sync.return_value = MagicMock(
        status=SyncState.READY,
        changes=[],
        more_changes=False,
        resets=["sub-1"],
        missing=[],
    )
    watcher.engine.remote.start_sync.return_value = MagicMock(
        status=SyncState.OK, sync_id="sync-1", message=None
    )

    watcher._poll_device_sync()

    watcher.engine.remote.clear_sync.assert_called_once()


def test_resubscribe_without_a_provisioner_reports_failure():
    watcher = _watcher()
    watcher._provisioner = None
    assert watcher._resubscribe() is False


# -- C3: an unknown parent must not be silently acknowledged ---------------


def test_unknown_parent_schedules_a_reseed():
    watcher = _watcher()
    info = _remote_info("orphan.txt", uid="child-1")
    info.parent_uid = "missing-parent"
    watcher.engine.remote._change_to_remote_file_info.return_value = info
    watcher._is_filtered_path = MagicMock(return_value=False)
    watcher._fetch_node_info = MagicMock(return_value=info)
    watcher._resolve_parent = MagicMock(return_value=None)
    watcher.dao.get_normal_state_from_remote.return_value = None

    change = MagicMock(node_id="child-1", change_type="CREATE_REPOS", seq_no=1)

    assert watcher._apply_change(change) is False
    watcher.dao.add_path_to_scan.assert_called_once_with("missing-parent")
    watcher.dao.update_config.assert_any_call(CONF_BOOTSTRAPPED_FOR, None)


# -- C11: nothing may escape the poll and kill the watcher thread -----------


def _pollable():
    """A watcher whose four remote steps are individually controllable."""
    watcher = _watcher()
    watcher.engine.remote = MagicMock()
    watcher.engine.queue_manager.get_overall_size.return_value = 0
    watcher.updated = MagicMock()
    watcher._ensure_provisioned = MagicMock(return_value=True)
    watcher._bootstrap_if_needed = MagicMock()
    watcher._apply_unfiltered = MagicMock()
    watcher._poll_device_sync = MagicMock()
    watcher._scan_local_changes = MagicMock()
    watcher.empty_polls = 0
    return watcher


@pytest.mark.parametrize(
    "step",
    [
        "_ensure_provisioned",
        "_bootstrap_if_needed",
        "_apply_unfiltered",
        "_poll_device_sync",
    ],
)
def test_unexpected_error_in_any_step_is_contained(step):
    watcher = _pollable()
    getattr(watcher, step).side_effect = OSError("transient")

    assert watcher._do_handle_changes(False) is False
    watcher.updated.emit.assert_called_once_with()


@pytest.mark.parametrize(
    "step",
    [
        "_ensure_provisioned",
        "_bootstrap_if_needed",
        "_apply_unfiltered",
        "_poll_device_sync",
    ],
)
def test_auth_error_in_any_step_flags_credentials(step):
    watcher = _pollable()
    getattr(watcher, step).side_effect = AlfrescoAuthError("expired")

    assert watcher._do_handle_changes(False) is False
    watcher.engine.set_invalid_credentials.assert_called_once()


def test_thread_interrupt_still_propagates():
    """Cooperative shutdown must not be swallowed as a poll failure."""
    watcher = _pollable()
    watcher._poll_device_sync.side_effect = ThreadInterrupt()

    with pytest.raises(ThreadInterrupt):
        watcher._do_handle_changes(False)

    watcher.engine.set_invalid_credentials.assert_not_called()


# -- B5: widening the selection must revive a remotely_deleted row -----------


@pytest.mark.parametrize(
    "state",
    [
        ("deleted", "remotely_deleted"),
        ("deleted", "parent_remotely_deleted"),
    ],
)
def test_reconcile_child_forces_restore_of_deleted_row(state):
    remote_state, pair_state = state
    watcher = _watcher()
    pair = MagicMock(id=7, remote_state=remote_state, pair_state=pair_state)
    info = _remote_info("file.txt")

    watcher._reconcile_child(pair, info, "/parent", PurePosixPath("local"))

    kwargs = watcher.dao.update_remote_state.call_args.kwargs
    assert kwargs["force_update"] is True
    assert kwargs["versioned"] is False
    watcher.dao.force_remote.assert_called_once_with(pair)


def test_reconcile_child_leaves_healthy_row_alone():
    watcher = _watcher()
    stamp = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    pair = MagicMock(
        remote_state="synchronized",
        pair_state="synchronized",
        folderish=False,
        remote_version="1.0",
        last_remote_updated="2026-08-01 10:00:00",
    )
    info = _remote_info("file.txt")
    info.last_modification_time = stamp
    info.version_label = "1.0"

    watcher._reconcile_child(pair, info, "/parent", PurePosixPath("local"))

    watcher.dao.force_remote.assert_not_called()


# -- B6: an expired token must not degrade into a partial row ----------------


def test_fetch_node_info_reraises_auth_error():
    watcher = _watcher()
    watcher.engine.remote.get_node.side_effect = AlfrescoAuthError("expired")
    change = MagicMock(node_id="node-1", name="file.txt")

    with pytest.raises(AlfrescoAuthError):
        watcher._fetch_node_info(change)


def test_fetch_node_info_swallows_recoverable_error():
    watcher = _watcher()
    watcher.engine.remote.get_node.side_effect = OSError("transient")
    change = MagicMock(node_id="node-1", name="file.txt")

    assert watcher._fetch_node_info(change) is None


# -- B8: ids survive a failed teardown so it can be retried ------------------


def _provisioner(dao=None):
    remote = MagicMock()
    dao = dao or MagicMock()
    dao.get_config.return_value = None
    prov = DeviceSyncProvisioner(remote, dao, device_os="macos", client_version="1.0.3")
    prov.subscriber_id = "subscriber-1"
    prov.subscription_id = "subscription-1"
    return prov


def test_teardown_keeps_ids_when_subscriber_delete_fails():
    prov = _provisioner()
    prov.remote.client.sync_amp.delete_subscriber.side_effect = AlfrescoError("503")

    prov.teardown()

    cleared = [c.args[0] for c in prov.dao.update_config.call_args_list]
    assert CONF_SUBSCRIBER_ID not in cleared
    assert prov.subscriber_id == "subscriber-1"


def test_teardown_clears_ids_on_success():
    prov = _provisioner()

    prov.teardown()

    cleared = [c.args[0] for c in prov.dao.update_config.call_args_list]
    assert CONF_SUBSCRIBER_ID in cleared
    assert CONF_SUBSCRIPTION_ID in cleared
    assert prov.subscriber_id == ""


def test_teardown_treats_already_absent_as_success():
    prov = _provisioner()
    prov.remote.client.sync_amp.delete_subscriber.side_effect = NotFoundError("gone")

    prov.teardown()

    cleared = [c.args[0] for c in prov.dao.update_config.call_args_list]
    assert CONF_SUBSCRIBER_ID in cleared


# -- B7: the watcher must be stopped before server-side state is removed -----


def test_unbind_stops_engine_before_teardown():
    from nxdrive.alfresco.engine.engine import AlfrescoEngine

    # A real instance is required so the zero-arg super() call resolves.
    engine = AlfrescoEngine.__new__(AlfrescoEngine)
    order = []
    engine.stop = lambda: order.append("stop")
    engine._teardown_device_sync = lambda: order.append("teardown")

    with patch(
        "nxdrive.drive.engine.engine.Engine.unbind",
        side_effect=lambda: order.append("super"),
    ):
        engine.unbind()

    assert order == ["stop", "teardown", "super"]


# -- Tier 2: a refused delete is not a transient one -------------------------


def _refusal():
    return AlfrescoError("Duplicate/invalid target", 400)


class TestTeardownDeleteOutcome:
    """A refusal never succeeds alone, a transient fault is worth retrying.

    Deleting the subscriber takes the only route to its subscriptions with
    it, so it must not run while the subscription delete is still retryable.
    """

    def test_a_transient_failure_spares_the_subscriber(self):
        prov = _provisioner()
        prov.remote.client.sync_amp.delete_subscription.side_effect = AlfrescoError(
            "503", 503
        )

        prov.teardown()

        prov.remote.client.sync_amp.delete_subscriber.assert_not_called()
        cleared = [c.args[0] for c in prov.dao.update_config.call_args_list]
        assert CONF_SUBSCRIBER_ID not in cleared
        assert prov.subscription_id == "subscription-1"

    def test_a_refusal_still_removes_the_subscriber(self):
        """It is the only cleanup left for a subscription the server keeps."""
        prov = _provisioner()
        prov.remote.client.sync_amp.delete_subscription.side_effect = _refusal()

        prov.teardown()

        prov.remote.client.sync_amp.delete_subscriber.assert_called_once()

    def test_a_refusal_is_recorded_as_an_orphan(self):
        prov = _provisioner()
        prov.remote.client.sync_amp.delete_subscription.side_effect = _refusal()

        prov.teardown()

        recorded = [
            c.args[1]
            for c in prov.dao.update_config.call_args_list
            if c.args[0] == CONF_ORPHAN_SUBSCRIPTIONS
        ]
        assert recorded == ["subscription-1"]

    def test_a_refusal_still_clears_the_live_ids(self):
        """The orphan list holds the handle, so these need not stay pinned."""
        prov = _provisioner()
        prov.remote.client.sync_amp.delete_subscription.side_effect = _refusal()

        prov.teardown()

        cleared = [c.args[0] for c in prov.dao.update_config.call_args_list]
        assert CONF_SUBSCRIBER_ID in cleared
        assert CONF_SUBSCRIPTION_ID in cleared


class TestResubscribeDeleteOutcome:
    def test_a_transient_failure_keeps_the_id(self):
        """The next line erases it, and it is the only handle we have."""
        prov = _provisioner()
        prov.remote.client.sync_amp.delete_subscription.side_effect = AlfrescoError(
            "503", 503
        )

        assert prov.resubscribe("root-node") is False
        assert prov.subscription_id == "subscription-1"
        prov.remote.client.sync_amp.create_subscription.assert_not_called()

    def test_a_refusal_records_the_orphan_and_continues(self):
        prov = _provisioner()
        prov.remote.client.sync_amp.delete_subscription.side_effect = _refusal()
        prov.remote.client.sync_amp.create_subscription.return_value = MagicMock(
            id="subscription-2"
        )

        assert prov.resubscribe("root-node") is True

        recorded = [
            c.args[1]
            for c in prov.dao.update_config.call_args_list
            if c.args[0] == CONF_ORPHAN_SUBSCRIPTIONS
        ]
        assert recorded == ["subscription-1"]


class TestSyncServiceUrlRebind:
    """Rebinding swaps the auth handler on a client the processors may use."""

    def _resolve(self, *, bound_url):
        prov = _provisioner()
        prov.remote.sync_service_url = bound_url
        prov.dao.get_config.return_value = "0"
        syncer = MagicMock(uri="https://acs.example.com/syncservice")
        prov.remote.client.sync_amp.get_syncer.return_value = syncer
        assert prov._ensure_service_url("subscriber-1") is True
        return prov

    def test_no_rebind_when_the_url_is_unchanged(self):
        prov = self._resolve(bound_url="https://acs.example.com/syncservice")

        prov.remote.set_sync_service_url.assert_not_called()

    def test_rebind_when_the_url_differs(self):
        prov = self._resolve(bound_url="https://old.example.com/syncservice")

        prov.remote.set_sync_service_url.assert_called_once_with(
            "https://acs.example.com/syncservice"
        )

    def test_a_fresh_client_is_always_bound(self):
        """After a restart the config is set but the client is not."""
        prov = self._resolve(bound_url=None)

        prov.remote.set_sync_service_url.assert_called_once()


# -- Expired credentials must reach the watcher, not look like "unprovisioned" --


class TestAuthErrorsEscapeProvisioning:
    """`AuthenticationError` subclasses `AlfrescoError`, so the recoverable
    handlers would otherwise swallow it and the watcher would retry forever
    without ever prompting for a re-login."""

    def _prov(self):
        prov = _provisioner()
        prov.dao.get_config.return_value = None
        return prov

    def test_amp_probe(self):
        prov = self._prov()
        prov.remote.device_sync_available.side_effect = AlfrescoAuthError("401")

        with pytest.raises(AlfrescoAuthError):
            prov._check_amp_available()

    def test_subscriber_registration(self):
        prov = self._prov()
        prov.remote.client.sync_amp.create_subscriber.side_effect = AlfrescoAuthError(
            "401"
        )

        with pytest.raises(AlfrescoAuthError):
            prov._create_subscriber()

    def test_syncer_lookup(self):
        prov = self._prov()
        prov.dao.get_config.return_value = "0"
        prov.remote.client.sync_amp.get_syncer.side_effect = AlfrescoAuthError("401")

        with pytest.raises(AlfrescoAuthError):
            prov._ensure_service_url("subscriber-1")

    def test_health_check(self):
        prov = self._prov()
        prov.remote.sync_service_reachable.side_effect = AlfrescoAuthError("401")

        with pytest.raises(AlfrescoAuthError):
            prov._check_service_reachable()

    def test_subscription_creation(self):
        prov = self._prov()
        prov.remote.client.sync_amp.create_subscription.side_effect = AlfrescoAuthError(
            "401"
        )

        with pytest.raises(AlfrescoAuthError):
            prov._create_subscription("subscriber-1", "root-node")

    def test_a_plain_transport_failure_is_still_recoverable(self):
        """Only auth escapes; everything else keeps the retry behaviour."""
        prov = self._prov()
        prov.remote.sync_service_reachable.side_effect = AlfrescoError("503", 503)

        assert prov._check_service_reachable() is False


class TestCleanupOrphansGuard:
    """Without an id to keep, every registration looks like an orphan.

    This is a recovery tool, so it is reached exactly when provisioning has
    not completed and ``subscriber_id`` is still empty.
    """

    def _prov(self, *, stored=None, current=""):
        prov = _provisioner()
        prov.subscriber_id = current
        prov.dao.get_config.return_value = stored
        prov.remote.client.sync_amp.iter_subscribers.return_value = [
            MagicMock(id="subscriber-1"),
            MagicMock(id="other-machine"),
        ]
        return prov

    def test_it_refuses_without_an_id_to_keep(self):
        prov = self._prov()

        assert prov.cleanup_orphans() == 0
        prov.remote.client.sync_amp.delete_subscriber.assert_not_called()

    def test_the_persisted_id_makes_it_usable_after_a_restart(self):
        """The in-memory id is only set once provisioning completes."""
        prov = self._prov(stored="subscriber-1")

        assert prov.cleanup_orphans() == 1
        prov.remote.client.sync_amp.delete_subscriber.assert_called_once_with(
            "other-machine"
        )

    def test_an_explicit_keep_id_wins(self):
        prov = self._prov(stored="subscriber-1")

        assert prov.cleanup_orphans(keep_id="other-machine") == 1
        prov.remote.client.sync_amp.delete_subscriber.assert_called_once_with(
            "subscriber-1"
        )

    def test_the_subscriber_being_used_is_never_deleted(self):
        prov = self._prov(current="subscriber-1")

        prov.cleanup_orphans()

        deleted = [
            c.args[0]
            for c in prov.remote.client.sync_amp.delete_subscriber.call_args_list
        ]
        assert "subscriber-1" not in deleted
