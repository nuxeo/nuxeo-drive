"""Tests for nxdrive/drive/poll_workers.py"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _patch_qt():
    """Patch Qt classes for PollWorker hierarchy."""
    mock_thread_cls = MagicMock()
    mock_thread_cls.return_value = MagicMock()

    patches = [
        patch(
            "nxdrive.drive.engine.workers.QObject.__init__", lambda self, *a, **k: None
        ),
        patch(
            "nxdrive.drive.engine.workers.QObject.moveToThread", lambda self, t: None
        ),
        patch("nxdrive.drive.engine.workers.QCoreApplication", MagicMock()),
        patch("nxdrive.drive.engine.workers.QThread", mock_thread_cls),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


# ─── DatabaseBackupWorker Tests ──────────────────────────────────────────────


def _make_backup_worker():
    from nxdrive.drive.poll_workers import DatabaseBackupWorker

    manager = MagicMock()
    w = DatabaseBackupWorker(manager)
    w.thread = MagicMock()
    return w


def test_backup_worker_init():
    w = _make_backup_worker()
    assert w._check_interval == 60 * 60
    assert w._name == "DatabaseBackup"


def test_backup_worker_poll_success():
    w = _make_backup_worker()
    w.manager.dao = MagicMock()
    engine1 = MagicMock()
    engine2 = MagicMock()
    w.manager.engines.copy.return_value.values.return_value = [engine1, engine2]

    result = w._poll()
    assert result is True
    w.manager.dao.save_backup.assert_called_once()
    engine1.dao.save_backup.assert_called_once()
    engine2.dao.save_backup.assert_called_once()


def test_backup_worker_poll_no_manager():
    w = _make_backup_worker()
    w.manager = None
    result = w._poll()
    assert result is False


def test_backup_worker_poll_no_manager_dao():
    w = _make_backup_worker()
    w.manager.dao = None
    w.manager.engines.copy.return_value.values.return_value = []
    result = w._poll()
    assert result is True


def test_backup_worker_poll_engine_no_dao():
    w = _make_backup_worker()
    w.manager.dao = MagicMock()
    engine = MagicMock()
    engine.dao = None
    w.manager.engines.copy.return_value.values.return_value = [engine]
    result = w._poll()
    assert result is True


# ─── ServerOptionsUpdater Tests ──────────────────────────────────────────────


def _make_options_updater():
    from nxdrive.drive.poll_workers import ServerOptionsUpdater

    manager = MagicMock()
    with patch.object(ServerOptionsUpdater, "firstRunCompleted", MagicMock()), patch(
        "nxdrive.drive.poll_workers.PollWorker.__init__", lambda self, *a, **k: None
    ):
        w = ServerOptionsUpdater.__new__(ServerOptionsUpdater)
        w.manager = manager
        w.first_run = True
        w._name = "ServerOptionsUpdater"
        w._check_interval = 3600
        w._next_check = 0
        w._metrics = {"last_poll": 0}
        w._running = False
        w._continue = False
        w._pause = False
        w._action = None
        w.thread_id = None
        w.firstRunCompleted = MagicMock()
    w.thread = MagicMock()
    return w


def test_options_updater_init():
    w = _make_options_updater()
    assert w._name == "ServerOptionsUpdater"
    assert w.first_run is True


def test_options_updater_first_run_done():
    w = _make_options_updater()
    w._first_run_done()
    assert w.first_run is False


def test_options_updater_poll_no_remote():
    w = _make_options_updater()
    engine = MagicMock()
    engine.remote = None
    w.manager.engines.copy.return_value.values.return_value = [engine]
    result = w._poll()
    assert result is True


def test_options_updater_poll_empty_config():
    w = _make_options_updater()
    engine = MagicMock()
    engine.remote.get_server_configuration.return_value = {}
    w.manager.engines.copy.return_value.values.return_value = [engine]
    result = w._poll()
    assert result is True
    engine.set_ui.assert_called_once_with("web", overwrite=False)


def test_options_updater_poll_none_config():
    w = _make_options_updater()
    engine = MagicMock()
    engine.remote.get_server_configuration.return_value = None
    w.manager.engines.copy.return_value.values.return_value = [engine]
    result = w._poll()
    assert result is True
    engine.set_ui.assert_called_once_with("web", overwrite=False)


def test_options_updater_poll_with_ui():
    w = _make_options_updater()
    engine = MagicMock()
    engine.remote.get_server_configuration.return_value = {"ui": "jsx"}
    w.manager.engines.copy.return_value.values.return_value = [engine]
    w._poll()
    engine.set_ui.assert_called_once_with("jsx", overwrite=False)


def test_options_updater_poll_with_beta_channel():
    w = _make_options_updater()
    engine = MagicMock()
    engine.remote.get_server_configuration.return_value = {"beta_channel": True}
    w.manager.engines.copy.return_value.values.return_value = [engine]

    with patch("nxdrive.drive.poll_workers.Options") as mock_opts:
        mock_opts.feature_synchronization = True
        w._poll()
        mock_opts.update.assert_called_once()
        call_args = mock_opts.update.call_args
        assert call_args[0][0].get("channel") == "beta"


def test_options_updater_poll_with_behavior():
    from nxdrive.drive.behavior import Behavior

    w = _make_options_updater()
    engine = MagicMock()
    engine.remote.get_server_configuration.return_value = {
        "behavior": {"server_deletion": False}
    }
    w.manager.engines.copy.return_value.values.return_value = [engine]

    original = Behavior.server_deletion
    try:
        Behavior.server_deletion = True
        with patch("nxdrive.drive.poll_workers.Options") as mock_opts:
            mock_opts.feature_synchronization = True
            w._poll()
        assert Behavior.server_deletion is False
    finally:
        Behavior.server_deletion = original


def test_options_updater_poll_with_invalid_behavior():
    w = _make_options_updater()
    engine = MagicMock()
    engine.remote.get_server_configuration.return_value = {
        "behavior": {"nonexistent_attr": True}
    }
    w.manager.engines.copy.return_value.values.return_value = [engine]

    with patch("nxdrive.drive.poll_workers.Options") as mock_opts:
        mock_opts.feature_synchronization = True
        # Should not raise
        w._poll()


def test_options_updater_poll_with_feature():
    w = _make_options_updater()
    engine = MagicMock()
    engine.remote.get_server_configuration.return_value = {
        "feature": {"direct_edit": True}
    }
    w.manager.engines.copy.return_value.values.return_value = [engine]

    with patch("nxdrive.drive.poll_workers.Options") as mock_opts:
        mock_opts.feature_synchronization = True
        w._poll()
    w.manager.set_feature_state.assert_called_once_with(
        "direct_edit", True, setter="server"
    )
