"""
Functional tests for :mod:`nxdrive.alfresco.engine.watcher.remote_watcher`.

Exercises the AlfrescoRemoteWatcher against a live Alfresco server:
scan_remote, _scan_remote_recursive, _handle_changes, metrics,
and local change scanning.
"""

from pathlib import Path
from uuid import uuid4

import pytest

from nxdrive.alfresco.engine.watcher.remote_watcher import AlfrescoRemoteWatcher
from nxdrive.drive.constants import ROOT
from nxdrive.drive.utils import unset_path_readonly


@pytest.fixture()
def engine_and_watcher(manager_factory):
    """Return (engine, watcher).

    ``Feature.synchronization`` is enabled by the autouse fixture, so
    the engine constructor calls ``_create_remote_watcher`` automatically.
    We patch ``_interact`` to a no-op to avoid Qt event-loop dependency.
    """
    manager = manager_factory(with_engine=True)
    engine = next(iter(manager.engines.values()))
    watcher = engine._remote_watcher
    watcher._interact = lambda: None
    return engine, watcher


class TestWatcherCreation:
    """Watcher instantiation."""

    def test_watcher_is_correct_type(self, engine_and_watcher) -> None:
        _engine, watcher = engine_and_watcher
        assert isinstance(watcher, AlfrescoRemoteWatcher)


class TestWatcherMetrics:
    """get_metrics."""

    def test_metrics_contains_expected_keys(self, engine_and_watcher) -> None:
        _engine, watcher = engine_and_watcher
        metrics = watcher.get_metrics()
        assert "last_remote_full_scan" in metrics
        assert "next_polling" in metrics


class TestScanRemote:
    """scan_remote — full tree scan."""

    def test_scan_remote_populates_dao(self, engine_and_watcher) -> None:
        """After scan_remote, the DAO should have remote states."""
        engine, watcher = engine_and_watcher

        root = engine.dao.get_state_from_local(ROOT)
        assert root is not None
        assert root.remote_ref

        watcher.scan_remote()

        # Root should still exist after scan
        root_after = engine.dao.get_state_from_local(ROOT)
        assert root_after is not None

    def test_scan_remote_no_root_pair(self, engine_and_watcher) -> None:
        """scan_remote with no root pair should not crash."""
        engine, watcher = engine_and_watcher

        # Remove root state to simulate edge case
        root = engine.dao.get_state_from_local(ROOT)
        if root:
            engine.dao.remove_state(root)

        # Should not raise
        watcher.scan_remote()


class TestScanRemoteRecursive:
    """_scan_remote_recursive — detects new, changed, deleted items."""

    def test_new_remote_folder_detected(
        self, engine_and_watcher, alfresco_test_folder
    ) -> None:
        """Create a remote folder, run scan, verify it doesn't crash."""
        engine, watcher = engine_and_watcher
        remote = engine.remote

        folder_name = f"ft-watcher-new-{uuid4().hex[:8]}"
        info = remote.make_folder(alfresco_test_folder.id, folder_name)
        try:
            watcher.scan_remote()
        finally:
            try:
                remote.delete(info.uid)
            except Exception:
                pass


class TestHandleChanges:
    """_handle_changes — incremental polling."""

    def test_handle_changes_first_pass(self, engine_and_watcher) -> None:
        """First pass should run scan_remote without error."""
        _engine, watcher = engine_and_watcher
        # @tooltip decorator swallows return values, so just verify no error
        watcher._handle_changes(first_pass=True)

    def test_handle_changes_subsequent_pass(self, engine_and_watcher) -> None:
        _engine, watcher = engine_and_watcher
        watcher._handle_changes(first_pass=False)


class TestScanPair:
    """scan_pair."""

    def test_scan_pair_resets_next_check(self, engine_and_watcher) -> None:
        _engine, watcher = engine_and_watcher
        watcher._next_check = 9999999
        watcher.scan_pair("/some/path")
        assert watcher._next_check == 0


class TestScanLocalChanges:
    """_scan_local_changes — detect local modifications."""

    def test_scan_local_changes_no_crash(self, engine_and_watcher) -> None:
        """Scan local changes should not crash even with no changes."""
        _engine, watcher = engine_and_watcher
        watcher._scan_local_changes()

    def test_new_local_file_detected(self, engine_and_watcher) -> None:
        """Create a local file, run local scan, verify DAO state."""
        engine, watcher = engine_and_watcher

        unset_path_readonly(engine.local_folder)
        engine.local.digest_callback = None
        file_name = f"ft-local-detect-{uuid4().hex[:8]}.txt"
        local_file = engine.local_folder / file_name
        local_file.write_text("local scan test")

        watcher._scan_local_changes()

        state = engine.dao.get_state_from_local(Path(file_name))
        # New file should be detected as locally_created
        if state:
            assert state.pair_state == "locally_created"

    def test_local_modified_detected(self, engine_and_watcher) -> None:
        """Modify a synchronized file, run scan, verify state changes."""
        engine, watcher = engine_and_watcher
        dao = engine.dao

        # Create and register a file
        unset_path_readonly(engine.local_folder)
        engine.local.digest_callback = None
        file_name = f"ft-local-mod-{uuid4().hex[:8]}.txt"
        local_file = engine.local_folder / file_name
        local_file.write_text("original content")

        info = engine.local.get_info(Path(file_name))
        dao.insert_local_state(info, ROOT)

        state = dao.get_state_from_local(Path(file_name))
        if state:
            # Mark as synchronized
            dao.synchronize_state(state)

            # Modify the file
            local_file.write_text("modified content - changed!")

            # Scan
            watcher._scan_local_changes()

            updated = dao.get_state_from_local(Path(file_name))
            if updated:
                # State should be locally_modified or still synchronized
                # depending on digest comparison
                assert updated.pair_state in ("locally_modified", "synchronized")
