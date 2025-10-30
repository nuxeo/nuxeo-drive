"""Functional tests for nxdrive.gui.folders_loader module."""

from unittest.mock import MagicMock, patch

from nxdrive.gui.folders_loader import (
    ContentLoaderMixin,
    DocumentContentLoader,
    FolderContentLoader,
)
from nxdrive.qt import constants as qt


class TestContentLoaderMixin:
    """Test cases for ContentLoaderMixin base class."""

    def create_mock_tree(self):
        """Helper to create a mock tree view."""
        mock_tree = MagicMock()
        mock_tree.model.return_value = MagicMock()
        mock_tree.model.return_value.invisibleRootItem.return_value = MagicMock()
        mock_tree.cache = []
        mock_tree.client = MagicMock()
        return mock_tree

    def test_content_loader_mixin_initialization_no_item(self):
        """Test ContentLoaderMixin initialization without specific item."""
        mock_tree = self.create_mock_tree()

        loader = ContentLoaderMixin(mock_tree)

        assert loader.tree == mock_tree
        assert loader.item == mock_tree.model().invisibleRootItem()
        assert loader.info is None
        assert loader.force_refresh is False

    def test_content_loader_mixin_initialization_with_item(self):
        """Test ContentLoaderMixin initialization with specific item."""
        mock_tree = self.create_mock_tree()
        mock_item = MagicMock()
        mock_info = MagicMock()
        mock_item.data.return_value = mock_info

        loader = ContentLoaderMixin(mock_tree, item=mock_item)

        assert loader.tree == mock_tree
        assert loader.item == mock_item
        assert loader.info == mock_info
        assert loader.force_refresh is False

    def test_content_loader_mixin_initialization_with_force_refresh(self):
        """Test ContentLoaderMixin initialization with force refresh."""
        mock_tree = self.create_mock_tree()

        loader = ContentLoaderMixin(mock_tree, force_refresh=True)

        assert loader.force_refresh is True

    def test_run_method_with_cached_item(self):
        """Test run method when item is already cached."""
        mock_tree = self.create_mock_tree()
        mock_item = MagicMock()
        mock_info = MagicMock()
        mock_info.get_id.return_value = "cached_id"
        mock_item.data.return_value = mock_info

        # Add item to cache
        mock_tree.cache = ["cached_id"]

        loader = ContentLoaderMixin(mock_tree, item=mock_item)

        with patch.object(loader, "handle_already_cached") as mock_handle_cached:
            loader.run()

            mock_tree.set_loading_cursor.assert_called_once_with(False)
            mock_handle_cached.assert_called_once()

    def test_run_method_with_force_refresh(self):
        """Test run method with force refresh ignores cache."""
        mock_tree = self.create_mock_tree()
        mock_item = MagicMock()
        mock_info = MagicMock()
        mock_info.get_id.return_value = "cached_id"
        mock_info.is_expandable.return_value = True
        mock_info.get_path.return_value = "/test/path"
        mock_item.data.return_value = mock_info

        # Add item to cache
        mock_tree.cache = ["cached_id"]

        loader = ContentLoaderMixin(mock_tree, item=mock_item, force_refresh=True)

        with patch.object(
            loader, "handle_already_cached"
        ) as mock_handle_cached, patch.object(loader, "fill_tree"):

            # Mock the client get_children method
            mock_tree.client.get_children.return_value = []

            loader.run()

            # Should not handle as cached due to force_refresh
            mock_handle_cached.assert_not_called()

    def test_run_method_adds_to_cache(self):
        """Test run method adds new items to cache."""
        mock_tree = self.create_mock_tree()
        mock_item = MagicMock()
        mock_info = MagicMock()
        mock_info.get_id.return_value = "new_id"
        mock_info.is_expandable.return_value = True
        mock_info.get_path.return_value = "/test/path"
        mock_item.data.return_value = mock_info

        loader = ContentLoaderMixin(mock_tree, item=mock_item)

        with patch.object(loader, "fill_tree"):
            mock_tree.client.get_children.return_value = []
            loader.run()

            assert "new_id" in mock_tree.cache

    def test_add_loading_subitem(self):
        """Test adding loading placeholder subitem."""
        mock_tree = self.create_mock_tree()
        loader = ContentLoaderMixin(mock_tree)

        mock_item = MagicMock()

        with patch(
            "nxdrive.gui.folders_loader.QStandardItem"
        ) as mock_qstandarditem, patch(
            "nxdrive.gui.folders_loader.Translator"
        ) as mock_translator:

            mock_loading_item = MagicMock()
            mock_qstandarditem.return_value = mock_loading_item
            mock_translator.get.return_value = "Loading..."

            loader.add_loading_subitem(mock_item)

            mock_translator.get.assert_called_once_with("LOADING")
            mock_loading_item.setSelectable.assert_called_once_with(False)
            mock_item.appendRow.assert_called_once_with(mock_loading_item)

    def test_sort_children(self):
        """Test sorting children alphabetically."""
        mock_tree = self.create_mock_tree()
        loader = ContentLoaderMixin(mock_tree)

        # Mock children with different labels
        mock_children = [
            MagicMock(get_label=lambda: "Zebra"),
            MagicMock(get_label=lambda: "Apple"),
            MagicMock(get_label=lambda: "banana"),
        ]
        sorted_children = loader.sort_children(mock_children)  # type: ignore

        # Should be sorted alphabetically (case-insensitive)
        labels = [child.get_label() for child in sorted_children]
        assert labels == ["Apple", "banana", "Zebra"]

    def test_fill_tree(self):
        """Test filling tree with children."""
        mock_tree = self.create_mock_tree()
        mock_item = MagicMock()
        loader = ContentLoaderMixin(mock_tree, item=mock_item)

        # Mock children
        mock_children = [
            MagicMock(
                get_label=lambda: "Child 1",
                folderish=lambda: True,
                selectable=lambda: True,
            ),
            MagicMock(
                get_label=lambda: "Child 2",
                folderish=lambda: False,
                selectable=lambda: True,
            ),
        ]

        with patch.object(loader, "new_subitem") as mock_new_subitem, patch.object(
            loader, "add_loading_subitem"
        ) as mock_add_loading:

            mock_subitem1 = MagicMock()
            mock_subitem2 = MagicMock()
            mock_new_subitem.side_effect = [mock_subitem1, mock_subitem2]

            loader.fill_tree(mock_children)  # type: ignore

            # Should clear existing rows
            mock_item.removeRows.assert_called_once_with(0, mock_item.rowCount())

            # Should create subitems for all children
            assert mock_new_subitem.call_count == 2

            # Should add loading subitem only for folderish items
            mock_add_loading.assert_called_once_with(mock_subitem1)

            # Should append all items
            assert mock_item.appendRow.call_count == 2

    def test_error_handling_during_run(self):
        """Test error handling during content loading."""
        mock_tree = self.create_mock_tree()
        mock_item = MagicMock()
        mock_info = MagicMock()
        mock_info.get_id.return_value = "error_item"
        mock_info.is_expandable.return_value = True
        mock_info.get_path.return_value = "/error/path"
        mock_item.data.return_value = mock_info

        loader = ContentLoaderMixin(mock_tree, item=mock_item)

        # Mock error during client call
        mock_tree.client.get_children.side_effect = Exception("Network error")

        with patch(
            "nxdrive.gui.folders_loader.QStandardItem"
        ) as mock_qstandarditem, patch(
            "nxdrive.gui.folders_loader.Translator"
        ) as mock_translator:

            mock_error_item = MagicMock()
            mock_qstandarditem.return_value = mock_error_item
            mock_translator.get.return_value = "LOADING_ERROR"

            loader.run()

            # Should clear existing items and add error message
            mock_item.removeRows.assert_called_once_with(0, mock_item.rowCount())
            mock_item.appendRow.assert_called_once_with(mock_error_item)
            mock_tree.set_loading_cursor.assert_called_with(False)


class TestDocumentContentLoader:
    """Test cases for DocumentContentLoader class."""

    def create_mock_tree(self):
        """Helper to create a mock tree view."""
        mock_tree = MagicMock()
        mock_tree.model.return_value = MagicMock()
        mock_tree.model.return_value.invisibleRootItem.return_value = MagicMock()
        mock_tree.cache = []
        mock_tree.client = MagicMock()
        return mock_tree

    def test_document_content_loader_initialization(self):
        """Test DocumentContentLoader initialization."""
        mock_tree = self.create_mock_tree()

        loader = DocumentContentLoader(mock_tree)

        assert isinstance(loader, ContentLoaderMixin)
        assert loader.tree == mock_tree

    def test_new_subitem_for_document(self):
        """Test creating new subitem for document."""
        mock_tree = self.create_mock_tree()
        loader = DocumentContentLoader(mock_tree)

        # Mock filtered document
        mock_child = MagicMock()
        mock_child.get_label.return_value = "Test Document"
        mock_child.checkable.return_value = True
        mock_child.state = qt.Checked
        mock_child.enable.return_value = True
        mock_child.selectable.return_value = True

        with patch(
            "nxdrive.gui.folders_loader.QStandardItem"
        ) as mock_qstandarditem, patch(
            "nxdrive.gui.folders_loader.QVariant"
        ) as mock_qvariant:

            mock_subitem = MagicMock()
            mock_qstandarditem.return_value = mock_subitem
            mock_variant = MagicMock()
            mock_qvariant.return_value = mock_variant

            subitem = loader.new_subitem(mock_child)

            # Verify QStandardItem creation and configuration
            mock_qstandarditem.assert_called_once_with("Test Document")
            mock_subitem.setCheckable.assert_called_once_with(True)
            mock_subitem.setCheckState.assert_called_with(qt.Checked)
            mock_subitem.setTristate.assert_called_once_with(True)
            mock_subitem.setEnabled.assert_called_once_with(True)
            mock_subitem.setSelectable.assert_called_once_with(True)
            mock_subitem.setEditable.assert_called_once_with(False)
            mock_subitem.setData.assert_called_once_with(mock_variant, qt.UserRole)

            assert subitem == mock_subitem

    def test_new_subitem_for_non_checkable_document(self):
        """Test creating new subitem for non-checkable document."""
        mock_tree = self.create_mock_tree()
        loader = DocumentContentLoader(mock_tree)

        # Mock document that is not checkable
        mock_child = MagicMock()
        mock_child.get_label.return_value = "Non-checkable Document"
        mock_child.checkable.return_value = False
        mock_child.enable.return_value = True
        mock_child.selectable.return_value = True

        with patch("nxdrive.gui.folders_loader.QStandardItem") as mock_qstandarditem:
            mock_subitem = MagicMock()
            mock_qstandarditem.return_value = mock_subitem

            loader.new_subitem(mock_child)

            # Should not set checkable properties
            mock_subitem.setCheckable.assert_not_called()
            mock_subitem.setCheckState.assert_not_called()
            mock_subitem.setTristate.assert_not_called()

            # Should still set other properties
            mock_subitem.setEnabled.assert_called_once_with(True)
            mock_subitem.setSelectable.assert_called_once_with(True)
            mock_subitem.setEditable.assert_called_once_with(False)


class TestFolderContentLoader:
    """Test cases for FolderContentLoader class."""

    def create_mock_tree(self):
        """Helper to create a mock tree view."""
        mock_tree = MagicMock()
        mock_tree.model.return_value = MagicMock()
        mock_tree.model.return_value.invisibleRootItem.return_value = MagicMock()
        mock_tree.cache = []
        mock_tree.client = MagicMock()
        mock_tree.filled = MagicMock()  # Signal for when tree is filled
        return mock_tree

    def test_folder_content_loader_initialization(self):
        """Test FolderContentLoader initialization."""
        mock_tree = self.create_mock_tree()

        loader = FolderContentLoader(mock_tree)

        assert isinstance(loader, ContentLoaderMixin)
        assert loader.tree == mock_tree

    def test_new_subitem_for_folder(self):
        """Test creating new subitem for folder."""
        mock_tree = self.create_mock_tree()
        loader = FolderContentLoader(mock_tree)

        # Mock document (folder)
        mock_child = MagicMock()
        mock_child.get_label.return_value = "Test Folder"
        mock_child.enable.return_value = True
        mock_child.selectable.return_value = True

        with patch(
            "nxdrive.gui.folders_loader.QStandardItem"
        ) as mock_qstandarditem, patch(
            "nxdrive.gui.folders_loader.QVariant"
        ) as mock_qvariant:

            mock_subitem = MagicMock()
            mock_qstandarditem.return_value = mock_subitem
            mock_variant = MagicMock()
            mock_qvariant.return_value = mock_variant

            subitem = loader.new_subitem(mock_child)

            # Verify QStandardItem creation and configuration
            mock_qstandarditem.assert_called_once_with("Test Folder")
            mock_subitem.setEnabled.assert_called_once_with(True)
            mock_subitem.setSelectable.assert_called_once_with(True)
            mock_subitem.setEditable.assert_called_once_with(False)
            mock_subitem.setData.assert_called_once_with(mock_variant, qt.UserRole)

            # Folder items are not checkable by default
            mock_subitem.setCheckable.assert_not_called()

            assert subitem == mock_subitem

    def test_handle_already_cached_emits_filled_signal(self):
        """Test that handle_already_cached emits the filled signal."""
        mock_tree = self.create_mock_tree()
        loader = FolderContentLoader(mock_tree)

        loader.handle_already_cached()

        # Should emit filled signal
        mock_tree.filled.emit.assert_called_once()


class TestLoaderIntegration:
    """Integration tests for content loaders."""

    def test_error_recovery_and_user_feedback(self):
        """Test error handling provides proper user feedback."""
        mock_tree = MagicMock()
        mock_tree.model.return_value = MagicMock()
        mock_tree.model.return_value.invisibleRootItem.return_value = MagicMock()
        mock_tree.cache = []
        mock_tree.client = MagicMock()

        mock_item = MagicMock()
        mock_info = MagicMock()
        mock_info.get_id.return_value = "error_item"
        mock_info.is_expandable.return_value = True
        mock_info.get_path.return_value = "/error/path"
        mock_item.data.return_value = mock_info

        loader = DocumentContentLoader(mock_tree, item=mock_item)

        # Simulate network error
        mock_tree.client.get_children.side_effect = Exception("Connection timeout")

        with patch(
            "nxdrive.gui.folders_loader.QStandardItem"
        ) as mock_qstandarditem, patch(
            "nxdrive.gui.folders_loader.Translator"
        ) as mock_translator, patch(
            "nxdrive.gui.folders_loader.log"
        ) as mock_log:

            mock_error_item = MagicMock()
            mock_qstandarditem.return_value = mock_error_item
            mock_translator.get.return_value = "LOADING_ERROR"

            loader.run()

            # Verify error was logged
            mock_log.warning.assert_called_once()

            # Verify user sees error message
            mock_item.removeRows.assert_called_once_with(0, mock_item.rowCount())
            mock_item.appendRow.assert_called_once_with(mock_error_item)

            # Verify loading cursor is turned off
            mock_tree.set_loading_cursor.assert_called_with(False)
