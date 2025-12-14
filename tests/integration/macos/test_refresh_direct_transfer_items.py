"""Integration tests for refresh_direct_transfer_items method - macOS only."""

from unittest.mock import MagicMock, Mock

import pytest

from nxdrive.dao.engine import EngineDAO
from nxdrive.gui.application import Application
from nxdrive.manager import Manager
from tests.markers import mac_only


@mac_only
class TestRefreshDirectTransferItems:
    """Test suite for refresh_direct_transfer_items method - macOS only."""

    @pytest.fixture
    def mock_application(self, tmp):
        """Create a mock Application with manager and models."""
        manager = Manager(tmp())
        app = MagicMock(spec=Application)
        app.manager = manager
        app.api = Mock()
        app.direct_transfer_model = Mock()
        app.direct_transfer_model.items = []

        yield app, manager

        manager.close()

    def test_refresh_direct_transfer_items_initial_load(self, mock_application):
        """Test refresh_direct_transfer_items on initial load with empty items."""
        app, manager = mock_application

        mock_dao = Mock(spec=EngineDAO)

        # Mock transfers from API
        mock_transfers = [
            {"doc_pair": 1, "name": "file1.txt", "status": "ongoing"},
            {"doc_pair": 2, "name": "file2.txt", "status": "completed"},
        ]

        app.api.get_direct_transfer_items.return_value = mock_transfers
        app.direct_transfer_model.items = []

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_direct_transfer_items.__get__(app, Application)
        bound_method(mock_dao)

        # Verify API was called
        app.api.get_direct_transfer_items.assert_called_once_with(mock_dao)

        # Verify set_items was called for initial load
        app.direct_transfer_model.set_items.assert_called_once_with(mock_transfers)

        # Verify update_items was not called
        app.direct_transfer_model.update_items.assert_not_called()

    def test_refresh_direct_transfer_items_no_changes(self, mock_application):
        """Test refresh_direct_transfer_items when transfers haven't changed."""
        app, manager = mock_application

        mock_dao = Mock(spec=EngineDAO)

        # Mock transfers - same as current items
        mock_transfers = [
            {"doc_pair": 1, "name": "file1.txt", "status": "ongoing"},
        ]

        app.api.get_direct_transfer_items.return_value = mock_transfers
        app.direct_transfer_model.items = mock_transfers

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_direct_transfer_items.__get__(app, Application)
        bound_method(mock_dao)

        # Verify neither set_items nor update_items was called
        app.direct_transfer_model.set_items.assert_not_called()
        app.direct_transfer_model.update_items.assert_not_called()

    def test_refresh_direct_transfer_items_update(self, mock_application):
        """Test refresh_direct_transfer_items with existing items updates."""
        app, manager = mock_application

        mock_dao = Mock(spec=EngineDAO)

        # Mock current items
        current_items = [
            {
                "doc_pair": 1,
                "name": "file1.txt",
                "status": "ongoing",
                "finalizing": False,
            },
        ]

        # Mock new transfers from API
        mock_transfers = [
            {"doc_pair": 1, "name": "file1.txt", "status": "completed"},
            {"doc_pair": 2, "name": "file2.txt", "status": "ongoing"},
        ]

        app.api.get_direct_transfer_items.return_value = mock_transfers
        app.direct_transfer_model.items = current_items

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_direct_transfer_items.__get__(app, Application)
        bound_method(mock_dao)

        # Verify update_items was called (not set_items)
        app.direct_transfer_model.update_items.assert_called_once_with(mock_transfers)
        app.direct_transfer_model.set_items.assert_not_called()

    def test_refresh_direct_transfer_items_preserves_finalizing(self, mock_application):
        """Test refresh_direct_transfer_items preserves finalizing status."""
        app, manager = mock_application

        mock_dao = Mock(spec=EngineDAO)

        # Mock current items with finalizing status
        current_items = [
            {
                "doc_pair": 1,
                "name": "file1.txt",
                "status": "ongoing",
                "finalizing": True,
            },
            {
                "doc_pair": 2,
                "name": "file2.txt",
                "status": "completed",
                "finalizing": False,
            },
        ]

        # Mock new transfers from API (without finalizing)
        mock_transfers = [
            {"doc_pair": 1, "name": "file1.txt", "status": "ongoing"},
            {"doc_pair": 2, "name": "file2.txt", "status": "completed"},
        ]

        app.api.get_direct_transfer_items.return_value = mock_transfers
        app.direct_transfer_model.items = current_items

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_direct_transfer_items.__get__(app, Application)
        bound_method(mock_dao)

        # Verify update_items was called
        app.direct_transfer_model.update_items.assert_called_once()

        # Verify finalizing status was preserved for doc_pair 1
        updated_transfers = app.direct_transfer_model.update_items.call_args[0][0]
        assert updated_transfers[0]["finalizing"] is True
        assert updated_transfers[0]["doc_pair"] == 1

    def test_refresh_direct_transfer_items_ignores_shadow_items(self, mock_application):
        """Test refresh_direct_transfer_items ignores shadow items when preserving finalizing."""
        app, manager = mock_application

        mock_dao = Mock(spec=EngineDAO)

        # Mock current items with shadow item
        current_items = [
            {
                "doc_pair": 1,
                "name": "file1.txt",
                "status": "ongoing",
                "finalizing": True,
            },
            {
                "doc_pair": 2,
                "name": "file2.txt",
                "status": "completed",
                "finalizing": True,
                "shadow": True,
            },
        ]

        # Mock new transfers from API
        mock_transfers = [
            {"doc_pair": 1, "name": "file1.txt", "status": "ongoing"},
            {"doc_pair": 2, "name": "file2.txt", "status": "completed"},
        ]

        app.api.get_direct_transfer_items.return_value = mock_transfers
        app.direct_transfer_model.items = current_items

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_direct_transfer_items.__get__(app, Application)
        bound_method(mock_dao)

        # Verify update_items was called
        app.direct_transfer_model.update_items.assert_called_once()

        # Verify only non-shadow finalizing was preserved
        updated_transfers = app.direct_transfer_model.update_items.call_args[0][0]
        assert updated_transfers[0]["finalizing"] is True
        assert updated_transfers[0]["doc_pair"] == 1
        # doc_pair 2 should not have finalizing set (shadow item was ignored)
        assert (
            "finalizing" not in updated_transfers[1]
            or updated_transfers[1].get("finalizing") is False
        )

    def test_refresh_direct_transfer_items_only_finalizing_items(
        self, mock_application
    ):
        """Test refresh_direct_transfer_items only preserves finalizing=True items."""
        app, manager = mock_application

        mock_dao = Mock(spec=EngineDAO)

        # Mock current items - one finalizing, one not
        current_items = [
            {
                "doc_pair": 1,
                "name": "file1.txt",
                "status": "ongoing",
                "finalizing": True,
            },
            {
                "doc_pair": 2,
                "name": "file2.txt",
                "status": "ongoing",
                "finalizing": False,
            },
        ]

        # Mock new transfers from API
        mock_transfers = [
            {"doc_pair": 1, "name": "file1.txt", "status": "ongoing"},
            {"doc_pair": 2, "name": "file2.txt", "status": "ongoing"},
        ]

        app.api.get_direct_transfer_items.return_value = mock_transfers
        app.direct_transfer_model.items = current_items

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_direct_transfer_items.__get__(app, Application)
        bound_method(mock_dao)

        # Verify update_items was called
        updated_transfers = app.direct_transfer_model.update_items.call_args[0][0]

        # Only doc_pair 1 should have finalizing preserved
        assert updated_transfers[0]["finalizing"] is True
        assert updated_transfers[0]["doc_pair"] == 1
        # doc_pair 2 should not have finalizing (it was False)
        assert (
            "finalizing" not in updated_transfers[1]
            or updated_transfers[1].get("finalizing") is False
        )

    def test_refresh_direct_transfer_items_new_item_no_finalizing(
        self, mock_application
    ):
        """Test refresh_direct_transfer_items doesn't add finalizing to new items."""
        app, manager = mock_application

        mock_dao = Mock(spec=EngineDAO)

        # Mock current items with one finalizing
        current_items = [
            {
                "doc_pair": 1,
                "name": "file1.txt",
                "status": "ongoing",
                "finalizing": True,
            },
        ]

        # Mock new transfers with additional item
        mock_transfers = [
            {"doc_pair": 1, "name": "file1.txt", "status": "ongoing"},
            {"doc_pair": 3, "name": "file3.txt", "status": "ongoing"},  # New item
        ]

        app.api.get_direct_transfer_items.return_value = mock_transfers
        app.direct_transfer_model.items = current_items

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_direct_transfer_items.__get__(app, Application)
        bound_method(mock_dao)

        # Verify update_items was called
        updated_transfers = app.direct_transfer_model.update_items.call_args[0][0]

        # doc_pair 1 should have finalizing preserved
        assert updated_transfers[0]["finalizing"] is True
        # doc_pair 3 should not have finalizing (new item)
        assert (
            "finalizing" not in updated_transfers[1]
            or updated_transfers[1].get("finalizing") is False
        )

    def test_refresh_direct_transfer_items_multiple_finalizing(self, mock_application):
        """Test refresh_direct_transfer_items preserves multiple finalizing items."""
        app, manager = mock_application

        mock_dao = Mock(spec=EngineDAO)

        # Mock current items with multiple finalizing
        current_items = [
            {
                "doc_pair": 1,
                "name": "file1.txt",
                "status": "ongoing",
                "finalizing": True,
            },
            {
                "doc_pair": 2,
                "name": "file2.txt",
                "status": "ongoing",
                "finalizing": True,
            },
            {
                "doc_pair": 3,
                "name": "file3.txt",
                "status": "ongoing",
                "finalizing": False,
            },
        ]

        # Mock new transfers from API
        mock_transfers = [
            {"doc_pair": 1, "name": "file1.txt", "status": "ongoing"},
            {"doc_pair": 2, "name": "file2.txt", "status": "ongoing"},
            {"doc_pair": 3, "name": "file3.txt", "status": "ongoing"},
        ]

        app.api.get_direct_transfer_items.return_value = mock_transfers
        app.direct_transfer_model.items = current_items

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_direct_transfer_items.__get__(app, Application)
        bound_method(mock_dao)

        # Verify update_items was called
        updated_transfers = app.direct_transfer_model.update_items.call_args[0][0]

        # doc_pair 1 and 2 should have finalizing preserved
        assert updated_transfers[0]["finalizing"] is True
        assert updated_transfers[1]["finalizing"] is True
        # doc_pair 3 should not have finalizing
        assert (
            "finalizing" not in updated_transfers[2]
            or updated_transfers[2].get("finalizing") is False
        )

    def test_refresh_direct_transfer_items_empty_to_populated(self, mock_application):
        """Test refresh_direct_transfer_items from empty to populated list."""
        app, manager = mock_application

        mock_dao = Mock(spec=EngineDAO)

        # Start with empty items
        app.direct_transfer_model.items = []

        # Mock new transfers from API
        mock_transfers = [
            {"doc_pair": 1, "name": "file1.txt", "status": "ongoing"},
            {"doc_pair": 2, "name": "file2.txt", "status": "completed"},
        ]

        app.api.get_direct_transfer_items.return_value = mock_transfers

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_direct_transfer_items.__get__(app, Application)
        bound_method(mock_dao)

        # Verify set_items was called for initial population
        app.direct_transfer_model.set_items.assert_called_once_with(mock_transfers)
        app.direct_transfer_model.update_items.assert_not_called()

    def test_refresh_direct_transfer_items_populated_to_empty(self, mock_application):
        """Test refresh_direct_transfer_items from populated to empty list."""
        app, manager = mock_application

        mock_dao = Mock(spec=EngineDAO)

        # Start with items
        current_items = [
            {"doc_pair": 1, "name": "file1.txt", "status": "completed"},
        ]
        app.direct_transfer_model.items = current_items

        # Mock empty transfers from API
        mock_transfers = []

        app.api.get_direct_transfer_items.return_value = mock_transfers

        from nxdrive.gui.application import Application as RealApp

        bound_method = RealApp.refresh_direct_transfer_items.__get__(app, Application)
        bound_method(mock_dao)

        # Verify update_items was called with empty list
        app.direct_transfer_model.update_items.assert_called_once_with([])
        app.direct_transfer_model.set_items.assert_not_called()
