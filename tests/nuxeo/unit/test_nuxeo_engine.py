"""Unit tests for nxdrive.nuxeo.engine.engine module."""

from pathlib import Path
from unittest.mock import Mock, patch


class TestEngineNeedsFiltersSelection:
    def _make_engine(self):
        from nxdrive.nuxeo.engine.engine import Engine

        with patch.object(Engine, "__init__", return_value=None):
            engine = Engine.__new__(Engine)
        engine.dao = Mock()
        engine._sync_started = False
        return engine

    def test_sync_disabled(self):
        engine = self._make_engine()
        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = False
            assert engine.needs_filters_selection() is False

    def test_filters_already_configured(self):
        engine = self._make_engine()
        engine.dao.get_config.return_value = "1"
        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = True
            assert engine.needs_filters_selection() is False

    def test_root_pair_exists_marks_configured(self):
        engine = self._make_engine()
        engine.dao.get_config.return_value = None
        engine.dao.get_state_from_local.return_value = Mock()
        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = True
            assert engine.needs_filters_selection() is False
        engine.dao.update_config.assert_called_with("filters_configured", "1")

    def test_no_root_returns_true(self):
        engine = self._make_engine()
        engine.dao.get_config.return_value = None
        engine.dao.get_state_from_local.return_value = None
        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = True
            assert engine.needs_filters_selection() is True


class TestEngineMarkFiltersConfigured:
    def _make_engine(self):
        from nxdrive.nuxeo.engine.engine import Engine

        with patch.object(Engine, "__init__", return_value=None):
            engine = Engine.__new__(Engine)
        engine.dao = Mock()
        engine._check_root = Mock()
        return engine

    def test_marks_and_checks_root(self):
        engine = self._make_engine()
        engine.mark_filters_configured()
        engine.dao.update_config.assert_any_call("filters_configured", "1")
        engine.dao.update_config.assert_any_call("remote_need_full_scan", "/")
        engine._check_root.assert_called_once()


class TestEngineExport:
    def _make_engine(self):
        from nxdrive.nuxeo.engine.engine import Engine

        with patch.object(Engine, "__init__", return_value=None):
            engine = Engine.__new__(Engine)
        engine.dao = Mock()
        engine.uid = "eng-1"
        engine.is_syncing = Mock(return_value=True)
        engine.get_binder = Mock(return_value=Mock(initialized=True))
        return engine

    def test_export_contains_syncing_and_initialized(self):
        engine = self._make_engine()
        with patch(
            "nxdrive.drive.engine.engine.Engine.export", return_value={"uid": "eng-1"}
        ):
            result = engine.export()
        assert result["syncing"] is True
        assert result["initialized"] is True


class TestEngineManageStaledTransfers:
    def _make_engine(self):
        from nxdrive.nuxeo.engine.engine import Engine

        with patch.object(Engine, "__init__", return_value=None):
            engine = Engine.__new__(Engine)
        engine.dao = Mock()
        return engine

    def test_crashed_suspends_transfers(self):
        from nxdrive.drive.constants import TransferStatus
        from nxdrive.drive.engine.engine import State

        engine = self._make_engine()
        transfer = Mock()
        transfer.status = TransferStatus.ONGOING
        engine.dao.get_downloads_with_status.return_value = [transfer]
        engine.dao.get_uploads_with_status.return_value = []

        with patch.object(State, "has_crashed", True):
            engine._manage_staled_transfers()
        assert transfer.status == TransferStatus.SUSPENDED
        engine.dao.set_transfer_status.assert_called_once()

    def test_not_crashed_removes_transfers(self):
        from nxdrive.drive.constants import TransferStatus
        from nxdrive.drive.engine.engine import State

        engine = self._make_engine()
        transfer = Mock()
        transfer.status = TransferStatus.ONGOING
        transfer.path = Path("/tmp/f.txt")
        transfer.is_direct_transfer = False
        engine.dao.get_downloads_with_status.return_value = []
        engine.dao.get_uploads_with_status.return_value = [transfer]

        with patch.object(State, "has_crashed", False):
            engine._manage_staled_transfers()
        engine.dao.remove_transfer.assert_called_once()


class TestEngineCancelSession:
    def _make_engine(self):
        from nxdrive.nuxeo.engine.engine import Engine

        with patch.object(Engine, "__init__", return_value=None):
            engine = Engine.__new__(Engine)
        engine.dao = Mock()
        engine.remote = Mock()
        engine.cancelTimerSignal = Mock()
        return engine

    def test_cancel_session_sends_metrics(self):
        engine = self._make_engine()
        engine.dao.get_session_items.return_value = [
            {"facets": ["Folderish"]},
            {"facets": []},
            {"facets": []},
        ]
        engine.cancel_session(123)
        engine.cancelTimerSignal.emit.assert_called_once_with(123)
        engine.dao.cancel_session.assert_called_once_with(123)
        engine.remote.metrics.send.assert_called_once()
        sent = engine.remote.metrics.send.call_args[0][0]
        assert sent["directTransfer.session.file.count"] == 2
        assert sent["directTransfer.session.folder.count"] == 1


class TestEngineHaveFolderUpload:
    def _make_engine(self):
        from nxdrive.nuxeo.engine.engine import Engine

        with patch.object(Engine, "__init__", return_value=None):
            engine = Engine.__new__(Engine)
        engine.dao = Mock()
        engine.remote = Mock()
        return engine

    def test_cached_true(self):
        engine = self._make_engine()
        engine.dao.get_bool.return_value = True
        assert engine.have_folder_upload is True
        engine.remote.can_use.assert_not_called()

    def test_not_cached_checks_remote(self):
        engine = self._make_engine()
        engine.dao.get_bool.return_value = False
        engine.remote.can_use.return_value = True
        assert engine.have_folder_upload is True
        engine.dao.store_bool.assert_called_once_with("have_folder_upload", True)

    def test_not_cached_remote_false(self):
        engine = self._make_engine()
        engine.dao.get_bool.return_value = False
        engine.remote.can_use.return_value = False
        assert engine.have_folder_upload is False


class TestEngineSendRootsMetrics:
    def _make_engine(self):
        from nxdrive.nuxeo.engine.engine import Engine

        with patch.object(Engine, "__init__", return_value=None):
            engine = Engine.__new__(Engine)
        engine.dao = Mock()
        engine.remote = Mock()
        return engine

    def test_sends_when_sync_enabled(self):
        engine = self._make_engine()
        engine.dao.get_count.return_value = 3
        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = True
            engine._send_roots_metrics()
        engine.remote.metrics.send.assert_called_once()

    def test_skips_when_no_remote(self):
        engine = self._make_engine()
        engine.remote = None
        with patch("nxdrive.nuxeo.engine.engine.Feature") as mock_feat:
            mock_feat.synchronization = True
            engine._send_roots_metrics()
        # No assertion needed - just ensure no exception
