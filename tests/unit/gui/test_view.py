"""Unit tests for view.py model classes."""

from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import Mock, patch

import pytest

from nxdrive.constants import TransferStatus
from nxdrive.gui.view import (
    ActiveSessionModel,
    CompletedSessionModel,
    DirectTransferModel,
    EngineModel,
    FeatureModel,
    FileModel,
    LanguageModel,
    TasksModel,
    TransferModel,
)
from nxdrive.qt.imports import QModelIndex


@pytest.fixture
def mock_application():
    """Create a mock application for testing."""
    app = Mock()
    app.manager = Mock()
    app.manager.engines = {}
    app.update_workflow = Mock()
    app.update_workflow_user_engine_list = Mock()
    return app


@pytest.fixture
def mock_engine():
    """Create a mock engine for testing."""
    engine = Mock()
    engine.uid = "test-engine-uid"
    engine.type = "NXDRIVE"
    engine.folder = "/path/to/folder"
    engine.server_url = "https://test.nuxeo.com"
    engine.wui = "web"
    engine.force_ui = ""
    engine.remote_user = "testuser"
    engine.invalidAuthentication = Mock()
    engine.newConflict = Mock()
    engine.newError = Mock()
    engine.syncCompleted = Mock()
    engine.syncResumed = Mock()
    engine.syncStarted = Mock()
    engine.syncSuspended = Mock()
    engine.uiChanged = Mock()
    engine.authChanged = Mock()
    return engine


@pytest.fixture
def translate_func():
    """Create a mock translation function."""

    def tr(key, values=None):
        return key

    return tr


class TestEngineModel:
    """Test cases for EngineModel class."""

    def test_init(self, mock_application):
        """Test EngineModel initialization."""
        model = EngineModel(mock_application)
        assert model.application == mock_application
        assert model.engines_uid == []
        assert model.rowCount() == 0
        assert model.count == 0

    def test_role_names(self, mock_application):
        """Test roleNames returns correct mapping."""
        model = EngineModel(mock_application)
        roles = model.roleNames()
        assert roles[model.UID_ROLE] == b"uid"
        assert roles[model.TYPE_ROLE] == b"type"
        assert roles[model.FOLDER_ROLE] == b"folder"
        assert roles[model.URL_ROLE] == b"server_url"
        assert roles[model.UI_ROLE] == b"wui"
        assert roles[model.FORCE_UI_ROLE] == b"force_ui"
        assert roles[model.ACCOUNT_ROLE] == b"remote_user"

    def test_name_roles(self, mock_application):
        """Test nameRoles returns correct reverse mapping."""
        model = EngineModel(mock_application)
        name_roles = model.nameRoles()
        assert name_roles[b"uid"] == model.UID_ROLE
        assert name_roles[b"type"] == model.TYPE_ROLE

    def test_add_engine(self, mock_application, mock_engine):
        """Test adding an engine to the model."""
        model = EngineModel(mock_application)
        mock_application.manager.engines["test-engine-uid"] = mock_engine

        model.addEngine("test-engine-uid")

        assert "test-engine-uid" in model.engines_uid
        assert model.count == 1
        mock_application.update_workflow.assert_called_once()

    def test_add_engine_duplicate(self, mock_application, mock_engine):
        """Test adding duplicate engine does nothing."""
        model = EngineModel(mock_application)
        mock_application.manager.engines["test-engine-uid"] = mock_engine

        model.addEngine("test-engine-uid")
        initial_count = model.count

        model.addEngine("test-engine-uid")

        assert model.count == initial_count

    def test_remove_engine(self, mock_application, mock_engine):
        """Test removing an engine from the model."""
        model = EngineModel(mock_application)
        mock_application.manager.engines["test-engine-uid"] = mock_engine

        model.addEngine("test-engine-uid")
        assert model.count == 1

        model.removeEngine("test-engine-uid")

        assert "test-engine-uid" not in model.engines_uid
        assert model.count == 0
        mock_application.update_workflow_user_engine_list.assert_called_once_with(
            True, "test-engine-uid"
        )

    def test_data(self, mock_application, mock_engine):
        """Test data retrieval from model."""
        model = EngineModel(mock_application)
        mock_application.manager.engines["test-engine-uid"] = mock_engine
        model.addEngine("test-engine-uid")

        index = model.index(0, 0)

        # Test UID role
        uid = model.data(index, model.UID_ROLE)
        assert uid == "test-engine-uid"

        # Test TYPE role
        engine_type = model.data(index, model.TYPE_ROLE)
        assert engine_type == "NXDRIVE"

        # Test URL role
        url = model.data(index, model.URL_ROLE)
        assert url == "https://test.nuxeo.com"

    def test_data_invalid_index(self, mock_application):
        """Test data retrieval with invalid index."""
        model = EngineModel(mock_application)

        index = model.index(-1, 0)
        data = model.data(index, model.UID_ROLE)
        assert data == ""

        index = model.index(999, 0)
        data = model.data(index, model.UID_ROLE)
        assert data == ""

    def test_data_missing_engine(self, mock_application):
        """Test data retrieval when engine is missing."""
        model = EngineModel(mock_application)
        model.engines_uid.append("missing-engine")

        index = model.index(0, 0)
        data = model.data(index, model.UID_ROLE)
        assert data == ""

    def test_get(self, mock_application, mock_engine):
        """Test get method."""
        model = EngineModel(mock_application)
        mock_application.manager.engines["test-engine-uid"] = mock_engine
        model.addEngine("test-engine-uid")

        uid = model.get(0, "uid")
        assert uid == "test-engine-uid"

        url = model.get(0, "server_url")
        assert url == "https://test.nuxeo.com"

    def test_get_invalid_index(self, mock_application):
        """Test get method with invalid index."""
        model = EngineModel(mock_application)

        result = model.get(-1)
        assert result == ""

        result = model.get(999)
        assert result == ""

    def test_remove_rows(self, mock_application, mock_engine):
        """Test removeRows method."""
        model = EngineModel(mock_application)
        mock_application.manager.engines["engine1"] = mock_engine
        mock_application.manager.engines["engine2"] = mock_engine

        model.addEngine("engine1")
        model.addEngine("engine2")
        assert model.count == 2

        result = model.removeRows(0, 1)
        assert result is True
        assert model.count == 1

    def test_empty(self, mock_application, mock_engine):
        """Test empty method."""
        model = EngineModel(mock_application)
        mock_application.manager.engines["engine1"] = mock_engine
        mock_application.manager.engines["engine2"] = mock_engine

        model.addEngine("engine1")
        model.addEngine("engine2")
        assert model.count == 2

        model.empty()
        assert model.count == 0
        assert len(model.engines_uid) == 0

    def test_connect_engine(self, mock_application, mock_engine):
        """Test _connect_engine connects all signals."""
        model = EngineModel(mock_application)
        mock_application.manager.engines["test-engine-uid"] = mock_engine

        model._connect_engine(mock_engine)

        # Verify all signals are connected
        mock_engine.invalidAuthentication.connect.assert_called_once()
        mock_engine.newConflict.connect.assert_called_once()
        mock_engine.newError.connect.assert_called_once()
        mock_engine.syncCompleted.connect.assert_called_once()
        mock_engine.syncResumed.connect.assert_called_once()
        mock_engine.syncStarted.connect.assert_called_once()
        mock_engine.syncSuspended.connect.assert_called_once()
        mock_engine.uiChanged.connect.assert_called_once()
        mock_engine.authChanged.connect.assert_called_once()

    def test_relay_engine_events(self, mock_application, mock_engine):
        """Test _relay_engine_events emits statusChanged signal."""
        model = EngineModel(mock_application)

        with patch.object(model, "sender", return_value=mock_engine):
            with patch.object(model, "statusChanged") as mock_signal:
                model._relay_engine_events()
                mock_signal.emit.assert_called_once_with(mock_engine)


class TestTransferModel:
    """Test cases for TransferModel class."""

    def test_init(self, translate_func):
        """Test TransferModel initialization."""
        model = TransferModel(translate_func)
        assert model.tr == translate_func
        assert model.transfers == []
        assert model.rowCount() == 0
        assert model.count == 0

    def test_role_names(self, translate_func):
        """Test roleNames returns correct mapping."""
        model = TransferModel(translate_func)
        roles = model.roleNames()
        assert roles[model.ID] == b"uid"
        assert roles[model.NAME] == b"name"
        assert roles[model.STATUS] == b"status"
        assert roles[model.PROGRESS] == b"progress"
        assert roles[model.TYPE] == b"transfer_type"
        assert roles[model.ENGINE] == b"engine"

    def test_set_transfers(self, translate_func):
        """Test set_transfers method."""
        model = TransferModel(translate_func)
        transfers = [
            {
                "uid": "transfer1",
                "name": "file1.txt",
                "status": TransferStatus.ONGOING,
                "progress": 50.0,
                "transfer_type": "upload",
                "engine": "engine1",
                "is_direct_edit": False,
                "filesize": 1024,
            },
            {
                "uid": "transfer2",
                "name": "file2.txt",
                "status": TransferStatus.ONGOING,
                "progress": 75.0,
                "transfer_type": "download",
                "engine": "engine2",
                "is_direct_edit": False,
                "filesize": 2048,
            },
        ]

        model.set_transfers(transfers)

        assert model.count == 2
        assert len(model.transfers) == 2

    def test_get_progress_download(self, translate_func):
        """Test get_progress for download."""
        model = TransferModel(translate_func)

        with NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"x" * 512)
            tmp_path = Path(tmp.name)

        row = {
            "filesize": 1024,
            "transfer_type": "download",
            "tmpname": tmp_path,
            "progress": 50.0,
        }

        progress_str = model.get_progress(row)
        assert "512" in progress_str or "0.5" in progress_str
        assert "1024" in progress_str or "1.0" in progress_str

        tmp_path.unlink()

    def test_get_progress_upload(self, translate_func):
        """Test get_progress for upload."""
        model = TransferModel(translate_func)

        row = {
            "filesize": 1024,
            "transfer_type": "upload",
            "progress": 50.0,
            "speed": 100,
        }

        progress_str = model.get_progress(row)
        assert "512" in progress_str or "0.5" in progress_str
        assert "50%" in progress_str
        assert "↑" in progress_str  # Upload icon

    def test_get_progress_download_with_speed(self, translate_func):
        """Test get_progress with speed for download."""
        model = TransferModel(translate_func)

        with NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        row = {
            "filesize": 1024,
            "transfer_type": "download",
            "tmpname": tmp_path,
            "progress": 50.0,
            "speed": 200,
        }

        progress_str = model.get_progress(row)
        assert "↓" in progress_str  # Download icon
        assert "/s" in progress_str

        tmp_path.unlink()

    def test_data(self, translate_func):
        """Test data retrieval."""
        model = TransferModel(translate_func)
        transfers = [
            {
                "uid": "transfer1",
                "name": "file1.txt",
                "status": TransferStatus.ONGOING,
                "progress": 50.0,
                "transfer_type": "upload",
                "engine": "engine1",
                "is_direct_edit": False,
                "finalizing": False,
                "filesize": 1024,
            }
        ]
        model.set_transfers(transfers)

        index = model.index(0, 0)

        # Test NAME
        name = model.data(index, model.NAME)
        assert name == "file1.txt"

        # Test STATUS
        status = model.data(index, model.STATUS)
        assert status == "ONGOING"

        # Test FINALIZING
        finalizing = model.data(index, model.FINALIZING)
        assert finalizing is False

    def test_set_data(self, translate_func):
        """Test setData method."""
        model = TransferModel(translate_func)
        transfers = [
            {
                "uid": "transfer1",
                "name": "file1.txt",
                "status": TransferStatus.ONGOING,
                "progress": 50.0,
                "transfer_type": "upload",
                "engine": "engine1",
                "is_direct_edit": False,
                "filesize": 1024,
            }
        ]
        model.set_transfers(transfers)

        index = model.index(0, 0)
        model.setData(index, 75.0, role=model.PROGRESS)

        assert model.transfers[0]["progress"] == 75.0

    def test_set_progress(self, translate_func):
        """Test set_progress method."""
        model = TransferModel(translate_func)
        transfers = [
            {
                "uid": "transfer1",
                "name": "file1.txt",
                "status": TransferStatus.ONGOING,
                "progress": 50.0,
                "transfer_type": "upload",
                "engine": "engine1",
                "is_direct_edit": False,
                "filesize": 1024,
            }
        ]
        model.set_transfers(transfers)

        action = {
            "name": "file1.txt",
            "progress": 80.0,
            "action_type": "Transfer",
            "speed": 1024.0,
        }

        model.set_progress(action)

        assert model.transfers[0]["progress"] == 80.0

    def test_set_progress_linking(self, translate_func):
        """Test set_progress with Linking action."""
        model = TransferModel(translate_func)
        transfers = [
            {
                "uid": "transfer1",
                "name": "file1.txt",
                "status": TransferStatus.ONGOING,
                "progress": 100.0,
                "transfer_type": "upload",
                "engine": "engine1",
                "is_direct_edit": False,
                "finalizing": False,
                "filesize": 1024,
            }
        ]
        model.set_transfers(transfers)

        action = {
            "name": "file1.txt",
            "progress": 100.0,
            "action_type": "Linking",
        }

        model.set_progress(action)

        assert model.transfers[0]["finalizing"] is True

    def test_flags(self, translate_func):
        """Test flags method."""
        model = TransferModel(translate_func)
        index = model.index(0, 0)
        flags = model.flags(index)
        # Check that the flags include editable, enabled, and selectable
        from nxdrive.qt import constants as qt

        assert bool(flags & qt.ItemIsEditable)
        assert bool(flags & qt.ItemIsEnabled)
        assert bool(flags & qt.ItemIsSelectable)


class TestDirectTransferModel:
    """Test cases for DirectTransferModel class."""

    def test_init(self, translate_func):
        """Test DirectTransferModel initialization."""
        model = DirectTransferModel(translate_func)
        assert model.tr == translate_func
        assert model.items == []
        assert model.shadow_item == {}
        assert model.rowCount() == 0

    def test_role_names(self, translate_func):
        """Test roleNames returns correct mapping."""
        model = DirectTransferModel(translate_func)
        roles = model.roleNames()
        assert roles[model.ID] == b"uid"
        assert roles[model.NAME] == b"name"
        assert roles[model.STATUS] == b"status"
        assert roles[model.PROGRESS] == b"progress"
        assert roles[model.SHADOW] == b"shadow"
        assert roles[model.FINALIZING] == b"finalizing"

    def test_set_items(self, translate_func):
        """Test set_items creates shadow items."""
        model = DirectTransferModel(translate_func)
        items = [
            {
                "uid": "item1",
                "name": "file1.txt",
                "status": TransferStatus.ONGOING,
                "progress": 50.0,
                "engine": "engine1",
                "filesize": 1024,
                "remote_parent_path": "/path",
                "remote_parent_ref": "ref1",
                "doc_pair": 1,
            }
        ]

        model.set_items(items)

        # Should have shadow items to fill up to DT_MONITORING_MAX_ITEMS
        from nxdrive.constants import DT_MONITORING_MAX_ITEMS

        assert model.rowCount() == DT_MONITORING_MAX_ITEMS
        assert model.shadow_item != {}
        assert model.shadow_item["shadow"] is True

    def test_update_items(self, translate_func):
        """Test update_items method."""
        model = DirectTransferModel(translate_func)
        initial_items = [
            {
                "uid": "item1",
                "name": "file1.txt",
                "status": TransferStatus.ONGOING,
                "progress": 50.0,
                "engine": "engine1",
                "filesize": 1024,
                "remote_parent_path": "/path",
                "remote_parent_ref": "ref1",
                "doc_pair": 1,
                "finalizing": False,
            }
        ]
        model.set_items(initial_items)

        updated_items = [
            {
                "uid": "item1",
                "name": "file1.txt",
                "status": TransferStatus.DONE,
                "progress": 100.0,
                "engine": "engine1",
                "filesize": 1024,
                "remote_parent_path": "/path",
                "remote_parent_ref": "ref1",
                "doc_pair": 1,
                "finalizing": False,
            }
        ]

        model.update_items(updated_items)

        assert model.items[0]["progress"] == 100.0
        assert model.items[0]["status"] == TransferStatus.DONE

    def test_data(self, translate_func):
        """Test data retrieval."""
        model = DirectTransferModel(translate_func)
        items = [
            {
                "uid": "item1",
                "name": "file1.txt",
                "status": TransferStatus.ONGOING,
                "progress": 50.0,
                "engine": "engine1",
                "filesize": 1024,
                "remote_parent_path": "/path",
                "remote_parent_ref": "ref1",
                "shadow": False,
                "doc_pair": 1,
                "finalizing": False,
            }
        ]
        model.set_items(items)

        index = model.index(0, 0)

        # Test NAME
        name = model.data(index, model.NAME)
        assert name == "file1.txt"

        # Test STATUS
        status = model.data(index, model.STATUS)
        assert status == "ONGOING"

        # Test PROGRESS (formatted)
        progress = model.data(index, model.PROGRESS)
        assert "50.0" in progress

        # Test SHADOW
        shadow = model.data(index, model.SHADOW)
        assert shadow is False

        # Test SIZE (formatted)
        size = model.data(index, model.SIZE)
        assert "1.0" in size or "1024" in size

        # Test TRANSFERRED (calculated)
        transferred = model.data(index, model.TRANSFERRED)
        assert "512" in transferred or "0.5" in transferred

    def test_set_progress(self, translate_func):
        """Test set_progress method."""
        model = DirectTransferModel(translate_func)
        items = [
            {
                "uid": "item1",
                "name": "file1.txt",
                "status": TransferStatus.ONGOING,
                "progress": 50.0,
                "engine": "engine1",
                "filesize": 1024,
                "remote_parent_path": "/path",
                "remote_parent_ref": "ref1",
                "doc_pair": 1,
                "finalizing": False,
            }
        ]
        model.set_items(items)

        action = {
            "engine": "engine1",
            "doc_pair": 1,
            "progress": 75.0,
            "action_type": "Transfer",
        }

        model.set_progress(action)

        assert model.items[0]["progress"] == 75.0

    def test_set_progress_linking(self, translate_func):
        """Test set_progress with Linking action."""
        model = DirectTransferModel(translate_func)
        items = [
            {
                "uid": "item1",
                "name": "file1.txt",
                "status": TransferStatus.ONGOING,
                "progress": 100.0,
                "engine": "engine1",
                "filesize": 1024,
                "remote_parent_path": "/path",
                "remote_parent_ref": "ref1",
                "doc_pair": 1,
                "finalizing": False,
            }
        ]
        model.set_items(items)

        action = {
            "engine": "engine1",
            "doc_pair": 1,
            "progress": 100.0,
            "action_type": "Linking",
            "finalizing_status": "Linking document",
        }

        model.set_progress(action)

        assert model.items[0]["finalizing"] is True

    def test_add_item(self, translate_func):
        """Test add_item method."""
        model = DirectTransferModel(translate_func)
        item = {
            "uid": "item1",
            "name": "file1.txt",
            "status": TransferStatus.ONGOING,
            "progress": 50.0,
            "engine": "engine1",
            "filesize": 1024,
            "remote_parent_path": "/path",
            "remote_parent_ref": "ref1",
            "doc_pair": 1,
        }

        parent = QModelIndex()
        model.add_item(parent, item)

        assert model.rowCount() == 1
        assert model.items[0] == item

    def test_edit_item(self, translate_func):
        """Test edit_item method."""
        model = DirectTransferModel(translate_func)
        items = [
            {
                "uid": "item1",
                "name": "file1.txt",
                "status": TransferStatus.ONGOING,
                "progress": 50.0,
                "engine": "engine1",
                "filesize": 1024,
                "remote_parent_path": "/path",
                "remote_parent_ref": "ref1",
                "doc_pair": 1,
                "finalizing": False,
            }
        ]
        model.set_items(items)

        new_item = {
            "uid": "item1",
            "name": "file1_updated.txt",
            "status": TransferStatus.DONE,
            "progress": 100.0,
            "engine": "engine1",
            "filesize": 1024,
            "remote_parent_path": "/path",
            "remote_parent_ref": "ref1",
            "doc_pair": 1,
        }

        model.edit_item(0, new_item)

        assert model.items[0]["name"] == "file1_updated.txt"
        assert model.items[0]["status"] == TransferStatus.DONE
        assert model.items[0]["finalizing"] is False


class TestActiveSessionModel:
    """Test cases for ActiveSessionModel class."""

    def test_init(self, translate_func):
        """Test ActiveSessionModel initialization."""
        model = ActiveSessionModel(translate_func)
        assert model.tr == translate_func
        assert model.sessions == []
        assert model.shadow_session == {}
        assert model.rowCount() == 0

    def test_role_names(self, translate_func):
        """Test roleNames returns correct mapping."""
        model = ActiveSessionModel(translate_func)
        roles = model.roleNames()
        assert roles[model.UID] == b"uid"
        assert roles[model.STATUS] == b"status"
        assert roles[model.UPLOADED] == b"uploaded"
        assert roles[model.TOTAL] == b"total"
        assert roles[model.SHADOW] == b"shadow"

    def test_set_sessions(self, translate_func):
        """Test set_sessions creates shadow sessions."""
        model = ActiveSessionModel(translate_func)
        now = datetime.now().isoformat()
        sessions = [
            {
                "uid": 1,
                "status": TransferStatus.ONGOING,
                "remote_ref": "ref1",
                "remote_path": "/path1",
                "uploaded": 5,
                "total": 10,
                "engine": "engine1",
                "created_on": now,
                "completed_on": None,
                "description": "Test Session",
            }
        ]

        model.set_sessions(sessions)

        # Should have shadow sessions to fill up to DT_ACTIVE_SESSIONS_MAX_ITEMS
        from nxdrive.constants import DT_ACTIVE_SESSIONS_MAX_ITEMS

        assert model.rowCount() == DT_ACTIVE_SESSIONS_MAX_ITEMS
        assert model.shadow_session != {}
        assert model.shadow_session["shadow"] is True

    def test_update_sessions(self, translate_func):
        """Test update_sessions method."""
        model = ActiveSessionModel(translate_func)
        now = datetime.now().isoformat()
        initial_sessions = [
            {
                "uid": 1,
                "status": TransferStatus.ONGOING,
                "remote_ref": "ref1",
                "remote_path": "/path1",
                "uploaded": 5,
                "total": 10,
                "engine": "engine1",
                "created_on": now,
                "completed_on": None,
                "description": "Test Session",
            }
        ]
        model.set_sessions(initial_sessions)

        updated_sessions = [
            {
                "uid": 1,
                "status": TransferStatus.ONGOING,
                "remote_ref": "ref1",
                "remote_path": "/path1",
                "uploaded": 8,
                "total": 10,
                "engine": "engine1",
                "created_on": now,
                "completed_on": None,
                "description": "Test Session",
            }
        ]

        model.update_sessions(updated_sessions)

        assert model.sessions[0]["uploaded"] == 8

    def test_data(self, translate_func):
        """Test data retrieval."""
        model = ActiveSessionModel(translate_func)
        now = datetime.now().isoformat()
        sessions = [
            {
                "uid": 1,
                "status": TransferStatus.DONE,
                "remote_ref": "ref1",
                "remote_path": Path("/path1"),
                "uploaded": 10,
                "total": 10,
                "engine": "engine1",
                "created_on": now,
                "completed_on": now,
                "description": "Test Session",
            }
        ]
        model.set_sessions(sessions)

        index = model.index(0, 0)

        # Test STATUS
        status = model.data(index, model.STATUS)
        assert status == "COMPLETED"

        # Test REMOTE_PATH
        remote_path = model.data(index, model.REMOTE_PATH)
        assert "path1" in remote_path

        # Test DESCRIPTION
        description = model.data(index, model.DESCRIPTION)
        assert description == "Test Session"

        # Test PROGRESS
        progress = model.data(index, model.PROGRESS)
        assert "[10 / 10]" in progress

    def test_data_no_description(self, translate_func):
        """Test data retrieval with no description."""
        model = ActiveSessionModel(translate_func)
        now = datetime.now().isoformat()
        sessions = [
            {
                "uid": 1,
                "status": TransferStatus.ONGOING,
                "remote_ref": "ref1",
                "remote_path": Path("/path1"),
                "uploaded": 5,
                "total": 10,
                "engine": "engine1",
                "created_on": now,
                "completed_on": None,
                "description": "",
            }
        ]
        model.set_sessions(sessions)

        index = model.index(0, 0)
        description = model.data(index, model.DESCRIPTION)
        assert "Session 1" in description

    def test_count_properties(self, translate_func):
        """Test count and count_no_shadow properties."""
        model = ActiveSessionModel(translate_func)
        now = datetime.now().isoformat()
        sessions = [
            {
                "uid": 1,
                "status": TransferStatus.ONGOING,
                "remote_ref": "ref1",
                "remote_path": Path("/path1"),
                "uploaded": 5,
                "total": 10,
                "engine": "engine1",
                "created_on": now,
                "completed_on": None,
                "description": "Test",
            }
        ]
        model.set_sessions(sessions)

        from nxdrive.constants import DT_ACTIVE_SESSIONS_MAX_ITEMS

        assert model.count == DT_ACTIVE_SESSIONS_MAX_ITEMS
        assert model.count_no_shadow == 1
        assert model.is_full is False

    def test_is_full(self, translate_func):
        """Test is_full property."""
        model = ActiveSessionModel(translate_func)
        now = datetime.now().isoformat()

        from nxdrive.constants import DT_ACTIVE_SESSIONS_MAX_ITEMS

        sessions = [
            {
                "uid": i,
                "status": TransferStatus.ONGOING,
                "remote_ref": f"ref{i}",
                "remote_path": Path(f"/path{i}"),
                "uploaded": 5,
                "total": 10,
                "engine": "engine1",
                "created_on": now,
                "completed_on": None,
                "description": f"Session {i}",
            }
            for i in range(DT_ACTIVE_SESSIONS_MAX_ITEMS)
        ]

        model.set_sessions(sessions)

        assert model.is_full is True

    def test_add_session(self, translate_func):
        """Test add_session method."""
        model = ActiveSessionModel(translate_func)
        now = datetime.now().isoformat()
        session = {
            "uid": 1,
            "status": TransferStatus.ONGOING,
            "remote_ref": "ref1",
            "remote_path": "/path1",
            "uploaded": 5,
            "total": 10,
            "engine": "engine1",
            "created_on": now,
            "completed_on": None,
            "description": "Test",
        }

        parent = QModelIndex()
        model.add_session(parent, session)

        assert model.rowCount() == 1
        assert model.sessions[0] == session

    def test_edit_session(self, translate_func):
        """Test edit_session method."""
        model = ActiveSessionModel(translate_func)
        now = datetime.now().isoformat()
        sessions = [
            {
                "uid": 1,
                "status": TransferStatus.ONGOING,
                "remote_ref": "ref1",
                "remote_path": "/path1",
                "uploaded": 5,
                "total": 10,
                "engine": "engine1",
                "created_on": now,
                "completed_on": None,
                "description": "Test",
            }
        ]
        model.set_sessions(sessions)

        new_session = {
            "uid": 1,
            "status": TransferStatus.DONE,
            "remote_ref": "ref1",
            "remote_path": "/path1",
            "uploaded": 10,
            "total": 10,
            "engine": "engine1",
            "created_on": now,
            "completed_on": now,
            "description": "Test Complete",
        }

        model.edit_session(0, new_session)

        assert model.sessions[0]["status"] == TransferStatus.DONE
        assert model.sessions[0]["description"] == "Test Complete"


class TestCompletedSessionModel:
    """Test cases for CompletedSessionModel class."""

    def test_init(self, translate_func):
        """Test CompletedSessionModel initialization."""
        model = CompletedSessionModel(translate_func)
        assert model.tr == translate_func
        assert model.sessions == []
        assert model.rowCount() == 0

    def test_role_names(self, translate_func):
        """Test roleNames returns correct mapping."""
        model = CompletedSessionModel(translate_func)
        roles = model.roleNames()
        assert roles[model.UID] == b"uid"
        assert roles[model.STATUS] == b"status"
        assert roles[model.CSV_PATH] == b"csv_path"

    def test_set_sessions(self, translate_func):
        """Test set_sessions method."""
        model = CompletedSessionModel(translate_func)
        now = datetime.now().isoformat()
        sessions = [
            {
                "uid": 1,
                "status": TransferStatus.DONE,
                "remote_ref": "ref1",
                "remote_path": Path("/path1"),
                "uploaded": 10,
                "planned_items": 10,
                "engine": "engine1",
                "created_on": now,
                "completed_on": now,
                "description": "Completed Session",
                "csv_path": "/path/to/csv",
            }
        ]

        model.set_sessions(sessions)

        assert model.count == 1
        assert len(model.sessions) == 1

    def test_data(self, translate_func):
        """Test data retrieval."""
        model = CompletedSessionModel(translate_func)
        now = datetime.now().isoformat()
        sessions = [
            {
                "uid": 1,
                "status": TransferStatus.DONE,
                "remote_ref": "ref1",
                "remote_path": Path("/path1"),
                "uploaded": 10,
                "planned_items": 10,
                "engine": "engine1",
                "created_on": now,
                "completed_on": now,
                "description": "Completed Session",
            }
        ]
        model.set_sessions(sessions)

        index = model.index(0, 0)

        # Test STATUS
        status = model.data(index, model.STATUS)
        assert status == "COMPLETED"

        # Test PROGRESS
        progress = model.data(index, model.PROGRESS)
        assert "[10 / 10]" in progress

        # Test SHADOW (should always be False)
        shadow = model.data(index, model.SHADOW)
        assert shadow is False

    def test_data_cancelled_session(self, translate_func):
        """Test data retrieval for cancelled session."""
        model = CompletedSessionModel(translate_func)
        now = datetime.now().isoformat()
        sessions = [
            {
                "uid": 1,
                "status": TransferStatus.CANCELLED,
                "remote_ref": "ref1",
                "remote_path": Path("/path1"),
                "uploaded": 5,
                "planned_items": 10,
                "engine": "engine1",
                "created_on": now,
                "completed_on": now,
                "description": "",
            }
        ]
        model.set_sessions(sessions)

        index = model.index(0, 0)

        # Test STATUS for cancelled
        status = model.data(index, model.STATUS)
        assert status == "CANCELLED"

        # Test COMPLETED_ON label
        completed = model.data(index, model.COMPLETED_ON)
        assert "CANCELLED" in completed


class TestFileModel:
    """Test cases for FileModel class."""

    def test_init(self, translate_func):
        """Test FileModel initialization."""
        model = FileModel(translate_func)
        assert model.tr == translate_func
        assert model.files == []
        assert model.rowCount() == 0
        assert model.count == 0

    def test_role_names(self, translate_func):
        """Test roleNames returns correct mapping."""
        model = FileModel(translate_func)
        roles = model.roleNames()
        assert roles[model.ID] == b"id"
        assert roles[model.NAME] == b"name"
        assert roles[model.STATE] == b"state"
        assert roles[model.SIZE] == b"size"
        assert roles[model.LOCAL_PATH] == b"local_path"

    def test_add_files(self, translate_func):
        """Test add_files method."""
        model = FileModel(translate_func)
        files = [
            {
                "id": 1,
                "name": "file1.txt",
                "state": "synced",
                "size": 1024,
                "local_path": Path("/path/to/file1.txt"),
                "local_parent_path": Path("/path/to"),
                "folderish": False,
                "last_contributor": "user1",
                "last_error": None,
                "last_remote_update": "2025-01-01",
                "last_sync_date": "2025-01-01",
                "last_transfer": "download",
                "remote_name": "file1.txt",
                "remote_ref": "ref1",
                "last_error_details": None,
            }
        ]

        model.add_files(files)

        assert model.count == 1
        assert len(model.files) == 1

    def test_add_files_with_limit(self, translate_func):
        """Test add_files with multiple files."""
        model = FileModel(translate_func)
        files = [
            {
                "id": i,
                "name": f"file{i}.txt",
                "state": "synced",
                "size": 1024,
                "local_path": Path(f"/path/to/file{i}.txt"),
                "local_parent_path": Path("/path/to"),
                "folderish": False,
                "last_contributor": "user1",
                "last_error": None,
                "last_remote_update": "2025-01-01",
                "last_sync_date": "2025-01-01",
                "last_transfer": "download",
                "remote_name": f"file{i}.txt",
                "remote_ref": f"ref{i}",
                "last_error_details": None,
            }
            for i in range(5)
        ]

        model.add_files(files)

        assert model.count == 5

    def test_data(self, translate_func):
        """Test data retrieval."""
        model = FileModel(translate_func)
        files = [
            {
                "id": 1,
                "name": "file1.txt",
                "state": "synced",
                "size": 1024,
                "local_path": Path("/path/to/file1.txt"),
                "local_parent_path": Path("/path/to"),
                "folderish": False,
                "last_contributor": "user1",
                "last_error": None,
                "last_remote_update": "2025-01-01",
                "last_sync_date": "2025-01-01",
                "last_transfer": "download",
                "remote_name": "file1.txt",
                "remote_ref": "ref1",
                "last_error_details": None,
            }
        ]
        model.add_files(files)

        index = model.index(0, 0)

        # Test NAME
        name = model.data(index, model.NAME)
        assert name == "file1.txt"

        # Test SIZE (formatted)
        size = model.data(index, model.SIZE)
        assert "1.0" in size or "1024" in size
        assert "(" in size and ")" in size

        # Test LOCAL_PATH
        local_path = model.data(index, model.LOCAL_PATH)
        assert "file1.txt" in local_path
        assert "path" in local_path and "to" in local_path

        # Test LOCAL_PARENT_PATH
        parent_path = model.data(index, model.LOCAL_PARENT_PATH)
        assert "path" in parent_path and "to" in parent_path

    def test_set_data(self, translate_func):
        """Test setData method."""
        model = FileModel(translate_func)
        files = [
            {
                "id": 1,
                "name": "file1.txt",
                "state": "synced",
                "size": 1024,
                "local_path": Path("/path/to/file1.txt"),
                "local_parent_path": Path("/path/to"),
                "folderish": False,
                "last_contributor": "user1",
                "last_error": None,
                "last_remote_update": "2025-01-01",
                "last_sync_date": "2025-01-01",
                "last_transfer": "download",
                "remote_name": "file1.txt",
                "remote_ref": "ref1",
                "last_error_details": None,
            }
        ]
        model.add_files(files)

        index = model.index(0, 0)
        model.setData(index, "error", role=model.STATE)

        assert model.files[0]["state"] == "error"


class TestLanguageModel:
    """Test cases for LanguageModel class."""

    def test_init(self):
        """Test LanguageModel initialization."""
        model = LanguageModel()
        assert model.languages == []
        assert model.rowCount() == 0

    def test_role_names(self):
        """Test roleNames returns correct mapping."""
        model = LanguageModel()
        roles = model.roleNames()
        assert roles[model.NAME_ROLE] == b"name"
        assert roles[model.TAG_ROLE] == b"tag"

    def test_add_languages(self):
        """Test addLanguages method."""
        model = LanguageModel()
        languages = [("en", "English"), ("fr", "Français"), ("de", "Deutsch")]

        model.addLanguages(languages)

        assert model.rowCount() == 3
        assert len(model.languages) == 3

    def test_data(self):
        """Test data retrieval."""
        model = LanguageModel()
        languages = [("en", "English"), ("fr", "Français")]
        model.addLanguages(languages)

        index = model.index(0, 0)

        # Test NAME role
        name = model.data(index, model.NAME_ROLE)
        assert name == "English"

        # Test TAG role
        tag = model.data(index, model.TAG_ROLE)
        assert tag == "en"

    def test_get_tag(self):
        """Test getTag method."""
        model = LanguageModel()
        languages = [("en", "English"), ("fr", "Français")]
        model.addLanguages(languages)

        tag = model.getTag(0)
        assert tag == "en"

        tag = model.getTag(1)
        assert tag == "fr"

    def test_get_name(self):
        """Test getName method."""
        model = LanguageModel()
        languages = [("en", "English"), ("fr", "Français")]
        model.addLanguages(languages)

        name = model.getName(0)
        assert name == "English"

        name = model.getName(1)
        assert name == "Français"

    def test_remove_rows(self):
        """Test removeRows method."""
        model = LanguageModel()
        languages = [("en", "English"), ("fr", "Français"), ("de", "Deutsch")]
        model.addLanguages(languages)

        assert model.rowCount() == 3

        result = model.removeRows(1, 1)
        assert result is True
        assert model.rowCount() == 2
        assert model.languages[0] == ("en", "English")
        assert model.languages[1] == ("de", "Deutsch")


class TestFeatureModel:
    """Test cases for FeatureModel class."""

    def test_init(self):
        """Test FeatureModel initialization."""
        model = FeatureModel(True)
        assert model.enabled is True
        assert model.restart_needed is False

    def test_init_with_restart_needed(self):
        """Test FeatureModel initialization with restart_needed."""
        model = FeatureModel(False, restart_needed=True)
        assert model.enabled is False
        assert model.restart_needed is True

    def test_enabled_property(self):
        """Test enabled property getter."""
        model = FeatureModel(True)
        assert model.enabled is True

    def test_enabled_setter(self):
        """Test enabled property setter."""
        model = FeatureModel(True)

        with patch.object(model, "stateChanged") as mock_signal:
            model._enabled = False
            model.stateChanged.emit()
            assert model.enabled is False
            mock_signal.emit.assert_called_once()

    def test_restart_needed_property(self):
        """Test restart_needed property."""
        model = FeatureModel(True, restart_needed=True)
        assert model.restart_needed is True


class TestTasksModel:
    """Test cases for TasksModel class."""

    def test_init(self, translate_func):
        """Test TasksModel initialization."""
        model = TasksModel(translate_func)
        assert model.taskmodel is not None
        assert model.self_taskmodel is not None

    def test_get_model(self, translate_func):
        """Test get_model method."""
        model = TasksModel(translate_func)
        task_model = model.get_model()
        assert task_model is not None
        assert task_model == model.taskmodel

    def test_get_self_model(self, translate_func):
        """Test get_self_model method."""
        model = TasksModel(translate_func)
        self_model = model.get_self_model()
        assert self_model is not None
        assert self_model == model.self_taskmodel

    def test_load_list(self, translate_func):
        """Test loadList method."""
        from unittest.mock import MagicMock, patch

        model = TasksModel(translate_func)

        # Mock Translator.get to return string templates
        with patch("nxdrive.gui.view.Translator.get") as mock_translator:
            mock_translator.side_effect = lambda key: {
                "DAYS": "DAYS",
                "MONTHS": "MONTHS",
                "YEARS": "YEARS",
                "AGO": "AGO",
                "IN": "IN",
                "DUE": "DUE",
            }.get(key, key)

            # Create mock task objects with all required attributes
            task1 = MagicMock()
            task1.id = "task1"
            task1.name = "Test Task 1"
            task1.directive = "Approve"
            task1.workflowModelName = "TestWorkflow"
            task1.actors = [{"id": "user1"}]
            task1.dueDate = (datetime.now() + timedelta(days=5)).strftime(
                "%Y-%m-%dT%H:%M:%S.%f+00:00"
            )

            task2 = MagicMock()
            task2.id = "task2"
            task2.name = "Test Task 2"
            task2.directive = "Review"
            task2.workflowModelName = "ReviewWorkflow"
            task2.actors = [{"id": "user2"}]
            task2.dueDate = (datetime.now() - timedelta(days=2)).strftime(
                "%Y-%m-%dT%H:%M:%S.%f+00:00"
            )

            tasks = [task1, task2]

            model.loadList(tasks, "user1")

            # Verify self task was added to self_taskmodel
            assert model.self_taskmodel.rowCount() > 0

            # Verify other task was added to taskmodel
            assert model.taskmodel.rowCount() > 0

    def test_add_row(self, translate_func):
        """Test add_row method."""
        model = TasksModel(translate_func)
        task = {"id": "task1", "name": "Test Task"}

        model.add_row(task, model.TASK_ROLE, self_task=False)
        assert model.taskmodel.rowCount() == 1

        model.add_row(task, model.TASK_ROLE, self_task=True)
        assert model.self_taskmodel.rowCount() == 1

    def test_due_date_calculation_days(self, translate_func):
        """Test due_date_calculation for days."""
        from unittest.mock import patch

        model = TasksModel(translate_func)

        # Mock Translator.get to return string templates
        with patch("nxdrive.gui.view.Translator.get") as mock_translator:
            mock_translator.side_effect = lambda key: {
                "DAYS": "DAYS",
                "AGO": "AGO",
                "IN": "IN",
            }.get(key, key)

            # Future date with timezone
            future_date = (datetime.now() + timedelta(days=5)).strftime(
                "%Y-%m-%dT%H:%M:%S.%f+00:00"
            )
            result = model.due_date_calculation(future_date)
            assert "5" in result
            assert "IN" in result or "DAYS" in result

            # Past date with timezone
            past_date = (datetime.now() - timedelta(days=3)).strftime(
                "%Y-%m-%dT%H:%M:%S.%f+00:00"
            )
            result = model.due_date_calculation(past_date)
            assert "3" in result
            assert "AGO" in result or "DAYS" in result

    def test_due_date_calculation_months(self, translate_func):
        """Test due_date_calculation for months."""
        from unittest.mock import patch

        model = TasksModel(translate_func)

        # Mock Translator.get to return string templates
        with patch("nxdrive.gui.view.Translator.get") as mock_translator:
            mock_translator.side_effect = lambda key: {
                "MONTHS": "MONTHS",
                "AGO": "AGO",
                "IN": "IN",
            }.get(key, key)

            # Future date (2 months) with timezone
            future_date = (datetime.now() + timedelta(days=60)).strftime(
                "%Y-%m-%dT%H:%M:%S.%f+00:00"
            )
            result = model.due_date_calculation(future_date)
            assert "2" in result
            assert "MONTHS" in result

    def test_due_date_calculation_years(self, translate_func):
        """Test due_date_calculation for years."""
        from unittest.mock import patch

        model = TasksModel(translate_func)

        # Mock Translator.get to return string templates
        with patch("nxdrive.gui.view.Translator.get") as mock_translator:
            mock_translator.side_effect = lambda key: {
                "YEARS": "YEARS",
                "AGO": "AGO",
                "IN": "IN",
            }.get(key, key)

            # Future date (2 years) with timezone
            future_date = (datetime.now() + timedelta(days=730)).strftime(
                "%Y-%m-%dT%H:%M:%S.%f+00:00"
            )
            result = model.due_date_calculation(future_date)
            assert "2" in result
            assert "YEARS" in result
