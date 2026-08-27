"""Shared isolation for macOS Application integration tests."""

from unittest.mock import MagicMock

import pytest

from nxdrive.drive import manager as manager_module
from nxdrive.drive.manager import Manager


@pytest.fixture(autouse=True)
def isolate_manager_workers(monkeypatch):
    """Keep method-level tests from accumulating native Qt worker threads."""

    def worker(*_args, **_kwargs):
        return MagicMock(first_run=False)

    monkeypatch.setattr(Manager, "_create_server_config_updater", worker)
    monkeypatch.setattr(Manager, "_create_updater", worker)
    monkeypatch.setattr(Manager, "_create_db_backup_worker", lambda self: None)
    monkeypatch.setattr(Manager, "create_sentry_metrics", worker)
    monkeypatch.setattr(Manager, "_create_extension_listener", lambda self: None)
    monkeypatch.setattr(manager_module, "SyncAndQuitWorker", worker)
    monkeypatch.setattr(Manager, "_create_autolock_service", worker)
    monkeypatch.setattr(Manager, "_create_direct_edit", lambda self: None)
    monkeypatch.setattr(Manager, "_create_direct_download", lambda self: None)
    monkeypatch.setattr(Manager, "_create_workflow_worker", lambda self: None)
