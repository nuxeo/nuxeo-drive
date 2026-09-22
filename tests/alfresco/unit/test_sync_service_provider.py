"""
Unit tests for :class:`SyncServiceChangeProvider` behaviour — provisioning,
the async poll drain-loop, delta application and seeding/reconciliation
bookkeeping — driven by lightweight fakes (no Qt, DAO, or network).
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

from nxdrive.alfresco.engine.watcher.sync_service import (
    KIND_CREATE,
    KIND_DELETE,
    ChangeAction,
    SyncServiceChangeProvider,
)


class FakePair:
    def __init__(
        self,
        remote_ref: str,
        *,
        remote_parent_path: str = "/root",
        local_path: str = "/root/x",
        pair_state: str = "synchronized",
        last_remote_updated: str = "",
    ) -> None:
        self.remote_ref = remote_ref
        self.remote_parent_path = remote_parent_path
        self.local_path = Path(local_path)
        self.local_name = Path(local_path).name
        self.pair_state = pair_state
        self.last_remote_updated = last_remote_updated


class FakeDao:
    def __init__(self) -> None:
        self._config: dict = {}
        self.by_remote: dict = {}
        self.deleted: list = []

    def get_config(self, key, default=None):
        return self._config.get(key, default)

    def update_config(self, key, value):
        self._config[key] = value

    def get_states_from_remote(self, ref):
        pair = self.by_remote.get(ref)
        return [pair] if pair else []

    def get_normal_state_from_remote(self, ref):
        return self.by_remote.get(ref)

    def delete_remote_state(self, pair):
        self.deleted.append(pair.remote_ref)

    def is_filter(self, path):
        return False


class FakeSyncSvc:
    """Scripts start/get/clear to return a queue of raw SyncStatus dicts."""

    def __init__(self, script, *, poll_status="running") -> None:
        self._script = list(script)
        self._poll_status = poll_status
        self.cleared: list = []

    def start_sync(self, sub, subscription, req):
        raw = self._script.pop(0) if self._script else {"status": "ready"}
        return SimpleNamespace(
            sync_id="sync-1",
            status=raw.get("status", "ready"),
            more_changes=bool(raw.get("moreChanges", False)),
            _raw=raw,
        )

    def get_sync(self, sub, subscription, sync_id):
        # Simulates a still-running sync until the poll window is exhausted.
        return SimpleNamespace(
            sync_id=sync_id, status=self._poll_status, more_changes=False, _raw={}
        )

    def clear_sync(self, sub, subscription, sync_id):
        self.cleared.append(sync_id)


class FakeRemote:
    def __init__(
        self, *, edition="Enterprise", url="http://sync:9090/alfresco"
    ) -> None:
        self.sync_service_url = url
        self.device_id = "dev-123"
        self._cfg = SimpleNamespace(
            uri=url,
            dsync_client_version_min="1.0.1",
            repo_info=SimpleNamespace(edition=edition),
        )
        self.created_subscribers = 0
        self.created_subscriptions = []
        self._svc = FakeSyncSvc([])
        self.nodes: dict = {}

    # capability + provisioning
    def get_device_sync_config(self):
        return self._cfg

    def create_subscriber(self, device_os, client_version):
        self.created_subscribers += 1
        return SimpleNamespace(id="subscriber-1")

    def create_subscription(self, subscriber_id, target_node_id, subtype="BOTH"):
        self.created_subscriptions.append((subscriber_id, target_node_id, subtype))
        return SimpleNamespace(id="subscription-1")

    # sync passthroughs
    def start_sync(self, *a):
        return self._svc.start_sync(*a)

    def get_sync(self, *a):
        return self._svc.get_sync(*a)

    def clear_sync(self, *a):
        return self._svc.clear_sync(*a)

    # node fetch
    def get_node(self, node_id, include=None):
        if node_id not in self.nodes:
            raise KeyError(node_id)
        return self.nodes[node_id]

    def _node_to_remote_file_info(self, node):
        return node


class FakeWatcher:
    def __init__(self, dao, remote) -> None:
        self.dao = dao
        self.engine = SimpleNamespace(remote=remote)
        self.updates: list = []
        self.created: list = []

    def _apply_remote_update(self, pair, info, remote_parent_path):
        self.updates.append((pair.remote_ref, remote_parent_path))

    def _match_or_create_child(
        self, info, local_path, local_parent, remote_parent_path
    ):
        self.created.append((getattr(info, "uid", None), str(local_path)))
        return None


def make_provider(remote=None, dao=None):
    remote = remote or FakeRemote()
    dao = dao or FakeDao()
    watcher = FakeWatcher(dao, remote)
    return SyncServiceChangeProvider(watcher), remote, dao


class TestAvailability(unittest.TestCase):
    def test_enterprise_available(self) -> None:
        provider, _, _ = make_provider()
        self.assertTrue(provider.is_available())

    def test_community_unavailable(self) -> None:
        provider, _, _ = make_provider(FakeRemote(edition="Community"))
        self.assertFalse(provider.is_available())

    def test_no_url_unavailable(self) -> None:
        provider, _, _ = make_provider(FakeRemote(url=""))
        self.assertFalse(provider.is_available())


class TestProvisioning(unittest.TestCase):
    def test_creates_and_persists(self) -> None:
        provider, remote, dao = make_provider()
        self.assertTrue(provider.ensure_provisioned("root-node"))
        self.assertEqual(remote.created_subscribers, 1)
        self.assertEqual(dao.get_config("alfresco_sync_subscriber_id"), "subscriber-1")
        self.assertEqual(
            dao.get_config("alfresco_sync_subscription_id"), "subscription-1"
        )
        self.assertEqual(dao.get_config("alfresco_sync_target_node_id"), "root-node")

    def test_reuses_when_same_target(self) -> None:
        provider, remote, dao = make_provider()
        provider.ensure_provisioned("root-node")
        provider.ensure_provisioned("root-node")  # second call
        self.assertEqual(remote.created_subscribers, 1)  # not re-created

    def test_reprovisions_when_target_changes(self) -> None:
        provider, remote, dao = make_provider()
        provider.ensure_provisioned("root-a")
        provider._subscriber_id = provider._subscription_id = ""  # simulate reload
        provider.ensure_provisioned("root-b")
        self.assertEqual(remote.created_subscribers, 2)


class TestPullAndApply(unittest.TestCase):
    def _provision(self, dao):
        dao.update_config("alfresco_sync_subscriber_id", "subscriber-1")
        dao.update_config("alfresco_sync_subscription_id", "subscription-1")

    def test_drains_multiple_batches_and_acks_after_apply(self) -> None:
        provider, remote, dao = make_provider()
        self._provision(dao)
        remote._svc = FakeSyncSvc(
            [
                {
                    "status": "ready",
                    "moreChanges": True,
                    "changes": [{"type": "DELETE_REPOS", "nodeId": "n1", "seqNo": 10}],
                },
                {
                    "status": "ready",
                    "moreChanges": False,
                    "changes": [{"type": "DELETE_REPOS", "nodeId": "n2", "seqNo": 11}],
                },
            ]
        )
        dao.by_remote["n1"] = FakePair("n1")
        dao.by_remote["n2"] = FakePair("n2")
        handled = provider.pull_and_apply()
        self.assertTrue(handled)
        # Both batches applied (deleted) AND acknowledged.
        self.assertEqual(dao.deleted, ["n1", "n2"])
        self.assertEqual(len(remote._svc.cleared), 2)
        self.assertEqual(dao.get_config("alfresco_sync_last_seqno"), "11")

    def test_error_status_resets_and_falls_back(self) -> None:
        provider, remote, dao = make_provider()
        self._provision(dao)
        remote._svc = FakeSyncSvc([{"status": "error", "message": "unknown"}])
        handled = provider.pull_and_apply()
        self.assertFalse(handled)
        # Provisioning is dropped so the next cycle re-registers.
        self.assertIsNone(dao.get_config("alfresco_sync_subscriber_id"))

    def test_reset_request_resets_and_falls_back(self) -> None:
        provider, remote, dao = make_provider()
        self._provision(dao)
        remote._svc = FakeSyncSvc([{"status": "ready", "resets": ["subscription-1"]}])
        handled = provider.pull_and_apply()
        self.assertFalse(handled)
        self.assertIsNone(dao.get_config("alfresco_sync_subscription_id"))

    def test_incomplete_sync_not_acked(self) -> None:
        provider, remote, dao = make_provider()
        self._provision(dao)
        # A sync that never reaches 'ready' must fall back WITHOUT acking.
        provider._POLL_ATTEMPTS = 2
        provider._POLL_INTERVAL = 0
        remote._svc = FakeSyncSvc([{"status": "running"}], poll_status="running")
        handled = provider.pull_and_apply()
        self.assertFalse(handled)
        self.assertEqual(remote._svc.cleared, [])

    def test_needs_full_scan_makes_it_unhandled_but_acks(self) -> None:
        provider, remote, dao = make_provider()
        self._provision(dao)
        # An unknown change type flips needs_full_scan; the batch is still acked
        # so it is not redelivered forever.
        remote._svc = FakeSyncSvc(
            [
                {
                    "status": "ready",
                    "moreChanges": False,
                    "changes": [{"type": "WEIRD_FUTURE", "nodeId": "n1", "seqNo": 5}],
                },
            ]
        )
        handled = provider.pull_and_apply()
        self.assertFalse(handled)
        self.assertTrue(provider.needs_full_scan)
        self.assertEqual(len(remote._svc.cleared), 1)

    def test_not_provisioned_falls_back(self) -> None:
        provider, remote, dao = make_provider()
        self.assertFalse(provider.pull_and_apply())


class TestApply(unittest.TestCase):
    def test_delete_calls_dao(self) -> None:
        provider, remote, dao = make_provider()
        dao.by_remote["n1"] = FakePair("n1")
        provider.apply([ChangeAction(kind=KIND_DELETE, node_id="n1", seq_no=1)])
        self.assertEqual(dao.deleted, ["n1"])

    def test_delete_skips_local_changes(self) -> None:
        provider, remote, dao = make_provider()
        dao.by_remote["n1"] = FakePair("n1", pair_state="locally_modified")
        provider.apply([ChangeAction(kind=KIND_DELETE, node_id="n1", seq_no=1)])
        self.assertEqual(dao.deleted, [])

    def test_update_existing_pair(self) -> None:
        provider, remote, dao = make_provider()
        dao.by_remote["n1"] = FakePair("n1")
        remote.nodes["n1"] = SimpleNamespace(uid="n1", path="/root/x", folderish=False)
        provider.apply([ChangeAction(kind="update", node_id="n1", seq_no=1)])
        self.assertEqual(len(provider.watcher.updates), 1)

    def test_create_with_known_parent(self) -> None:
        provider, remote, dao = make_provider()
        dao.by_remote["parent"] = FakePair("parent")
        remote.nodes["n2"] = SimpleNamespace(
            uid="n2", name="x", path="/root/x", folderish=False
        )
        provider.apply(
            [
                ChangeAction(
                    kind=KIND_CREATE,
                    node_id="n2",
                    seq_no=1,
                    parent_node_ids=["parent"],
                    name="x",
                )
            ]
        )
        self.assertEqual(len(provider.watcher.created), 1)
        self.assertFalse(provider.needs_full_scan)

    def test_create_with_unknown_parent_requests_full_scan(self) -> None:
        provider, remote, dao = make_provider()
        remote.nodes["n2"] = SimpleNamespace(
            uid="n2", name="x", path="/root/x", folderish=False
        )
        provider.apply(
            [
                ChangeAction(
                    kind=KIND_CREATE,
                    node_id="n2",
                    seq_no=1,
                    parent_node_ids=["ghost"],
                    name="x",
                )
            ]
        )
        self.assertTrue(provider.needs_full_scan)

    def test_unknown_kind_requests_full_scan(self) -> None:
        provider, remote, dao = make_provider()
        provider.apply([ChangeAction(kind="unknown", node_id="n9", seq_no=1)])
        self.assertTrue(provider.needs_full_scan)

    def test_move_requests_full_scan(self) -> None:
        # A move can't be applied in place (only folder *renames* relocate via
        # update_remote_state); it must reconcile through a full scan.
        provider, remote, dao = make_provider()
        dao.by_remote["n1"] = FakePair("n1")
        from nxdrive.alfresco.engine.watcher.sync_service import KIND_MOVE

        provider.apply(
            [
                ChangeAction(
                    kind=KIND_MOVE,
                    node_id="n1",
                    seq_no=1,
                    parent_node_ids=["old"],
                    to_parent_node_ids=["new"],
                )
            ]
        )
        self.assertTrue(provider.needs_full_scan)
        # No in-place update happened.
        self.assertEqual(provider.watcher.updates, [])

    def test_missing_node_treated_as_delete(self) -> None:
        provider, remote, dao = make_provider()
        dao.by_remote["n1"] = FakePair("n1")
        # node not in remote.nodes -> get_node raises -> delete path
        provider.apply([ChangeAction(kind="update", node_id="n1", seq_no=1)])
        self.assertEqual(dao.deleted, ["n1"])


class TestSeedingReconcile(unittest.TestCase):
    def test_seed_lifecycle(self) -> None:
        provider, remote, dao = make_provider()
        self.assertFalse(provider.is_seeded())
        provider.on_full_scan_done()
        self.assertTrue(provider.is_seeded())
        self.assertEqual(dao.get_config("alfresco_sync_cycle"), "0")

    def test_reconcile_counter(self) -> None:
        provider, remote, dao = make_provider()
        self.assertFalse(provider.due_for_reconcile(3))  # 1
        self.assertFalse(provider.due_for_reconcile(3))  # 2
        self.assertTrue(provider.due_for_reconcile(3))  # 3 -> due
        provider.on_full_scan_done()
        self.assertFalse(provider.due_for_reconcile(3))  # counter reset

    def test_reconcile_disabled(self) -> None:
        provider, remote, dao = make_provider()
        self.assertFalse(provider.due_for_reconcile(0))


if __name__ == "__main__":
    unittest.main()
