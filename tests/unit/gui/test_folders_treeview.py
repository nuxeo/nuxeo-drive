"""Unit tests for TreeViewMixin.expand_item and TreeViewMixin.load_children."""

from unittest.mock import MagicMock, Mock, patch


_UNSET = object()  # sentinel for "use default MagicMock"


class TestExpandItem:
    """Unit tests for TreeViewMixin.expand_item."""

    def _make_tree_view(self, root_item=_UNSET, client=_UNSET):
        """Return a TreeViewMixin-like object with mocked Qt internals.

        Pass root_item=None explicitly to make tree.root_item falsy.
        """
        from nxdrive.gui.folders_treeview import TreeViewMixin

        with (
            patch("nxdrive.gui.folders_treeview.QTreeView.__init__", return_value=None),
            patch.object(TreeViewMixin, "setHeaderHidden"),
            patch.object(TreeViewMixin, "setModel"),
            patch.object(TreeViewMixin, "load_children"),
            patch.object(TreeViewMixin, "expanded", create=True),
        ):
            tree = TreeViewMixin.__new__(TreeViewMixin)
            tree.parent = MagicMock()
            tree.client = MagicMock() if client is _UNSET else client
            tree.cache = []
            tree.root_item = MagicMock() if root_item is _UNSET else root_item
            tree.load_children = MagicMock()
            return tree

    def test_expand_item_calls_load_children_with_item(self):
        """expand_item should call load_children with the resolved item."""
        mock_item = Mock()
        mock_root = MagicMock()
        mock_index = MagicMock()
        resolved_index = MagicMock()

        mock_index.row.return_value = 2
        mock_root.index.return_value = resolved_index
        mock_root.itemFromIndex.return_value = mock_item

        tree = self._make_tree_view(root_item=mock_root)
        tree.expand_item(mock_index)

        mock_root.index.assert_called_once_with(2, 0, mock_index.parent())
        mock_root.itemFromIndex.assert_called_once_with(resolved_index)
        tree.load_children.assert_called_once_with(item=mock_item)

    def test_expand_item_logs_error_when_item_is_none(self):
        """expand_item should log an error when itemFromIndex returns None."""
        mock_root = MagicMock()
        mock_index = MagicMock()
        mock_index.row.return_value = 0
        mock_root.index.return_value = MagicMock()
        mock_root.itemFromIndex.return_value = None

        tree = self._make_tree_view(root_item=mock_root)

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            tree.expand_item(mock_index)

        mock_log.error.assert_called_once_with(
            "Cannot get the item to load its children"
        )
        tree.load_children.assert_not_called()

    def test_expand_item_does_nothing_when_root_item_is_none(self):
        """expand_item should skip all logic when root_item is falsy."""
        tree = self._make_tree_view(root_item=None)
        mock_index = MagicMock()

        # Should not raise or call load_children
        tree.expand_item(mock_index)
        tree.load_children.assert_not_called()

    def test_expand_item_uses_correct_row_from_index(self):
        """expand_item should use index.row() when resolving the child index."""
        mock_item = Mock()
        mock_root = MagicMock()
        mock_index = MagicMock()
        mock_index.row.return_value = 5
        mock_root.itemFromIndex.return_value = mock_item

        tree = self._make_tree_view(root_item=mock_root)
        tree.expand_item(mock_index)

        # Verify row=5 was passed to root_item.index
        args, _ = mock_root.index.call_args
        assert args[0] == 5
        assert args[1] == 0

    def test_expand_item_passes_parent_to_root_index(self):
        """expand_item should pass index.parent() as the parent when building the child index."""
        mock_item = Mock()
        mock_root = MagicMock()
        mock_index = MagicMock()
        mock_parent = Mock()
        mock_index.row.return_value = 1
        mock_index.parent.return_value = mock_parent
        mock_root.itemFromIndex.return_value = mock_item

        tree = self._make_tree_view(root_item=mock_root)
        tree.expand_item(mock_index)

        args, _ = mock_root.index.call_args
        assert args[2] == mock_parent


class TestLoadChildren:
    """Unit tests for TreeViewMixin.load_children."""

    def _make_tree_view(self, client=_UNSET):
        """Return a TreeViewMixin instance with mocked Qt internals."""
        from nxdrive.gui.folders_treeview import TreeViewMixin

        with (
            patch("nxdrive.gui.folders_treeview.QTreeView.__init__", return_value=None),
            patch.object(TreeViewMixin, "setHeaderHidden"),
            patch.object(TreeViewMixin, "setModel"),
            patch.object(TreeViewMixin, "load_children"),
            patch.object(TreeViewMixin, "expanded", create=True),
        ):
            tree = TreeViewMixin.__new__(TreeViewMixin)
            tree.parent = MagicMock()
            tree.client = MagicMock() if client is _UNSET else client
            tree.cache = []
            tree.root_item = MagicMock()
            tree.loader = MagicMock()
            tree.set_loading_cursor = MagicMock()
            return tree

    def test_load_children_no_client_calls_set_loading_cursor_false(self):
        """load_children should call set_loading_cursor(False) and return immediately when client is falsy."""
        from nxdrive.gui.folders_treeview import TreeViewMixin

        tree = self._make_tree_view(client=None)

        TreeViewMixin.load_children(tree)

        tree.set_loading_cursor.assert_called_once_with(False)
        tree.loader.assert_not_called()

    def test_load_children_sets_busy_cursor_when_client_present(self):
        """load_children should call set_loading_cursor(True) when a client exists."""
        from nxdrive.gui.folders_treeview import TreeViewMixin

        mock_loader_instance = MagicMock()
        tree = self._make_tree_view()
        tree.loader.return_value = mock_loader_instance

        with patch("nxdrive.gui.folders_treeview.QThreadPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.globalInstance.return_value = mock_pool
            TreeViewMixin.load_children(tree)

        tree.set_loading_cursor.assert_called_once_with(True)

    def test_load_children_creates_loader_and_starts_it(self):
        """load_children should instantiate the loader and submit it to the thread pool."""
        from nxdrive.gui.folders_treeview import TreeViewMixin

        mock_loader_instance = MagicMock()
        tree = self._make_tree_view()
        tree.loader.return_value = mock_loader_instance

        with patch("nxdrive.gui.folders_treeview.QThreadPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.globalInstance.return_value = mock_pool
            TreeViewMixin.load_children(tree)

        tree.loader.assert_called_once_with(tree, item=None, force_refresh=False)
        mock_pool.start.assert_called_once_with(mock_loader_instance)

    def test_load_children_passes_item_argument(self):
        """load_children should forward the item kwarg to the loader."""
        from nxdrive.gui.folders_treeview import TreeViewMixin

        mock_item = MagicMock()
        mock_loader_instance = MagicMock()
        tree = self._make_tree_view()
        tree.loader.return_value = mock_loader_instance

        with patch("nxdrive.gui.folders_treeview.QThreadPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.globalInstance.return_value = mock_pool
            TreeViewMixin.load_children(tree, item=mock_item)

        tree.loader.assert_called_once_with(tree, item=mock_item, force_refresh=False)

    def test_load_children_passes_force_refresh_argument(self):
        """load_children should forward force_refresh=True to the loader."""
        from nxdrive.gui.folders_treeview import TreeViewMixin

        mock_loader_instance = MagicMock()
        tree = self._make_tree_view()
        tree.loader.return_value = mock_loader_instance

        with patch("nxdrive.gui.folders_treeview.QThreadPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.globalInstance.return_value = mock_pool
            TreeViewMixin.load_children(tree, force_refresh=True)

        tree.loader.assert_called_once_with(tree, item=None, force_refresh=True)

    def test_load_children_logs_error_when_pool_is_none(self):
        """load_children should log an error when the global thread pool is unavailable."""
        from nxdrive.gui.folders_treeview import TreeViewMixin

        mock_loader_instance = MagicMock()
        tree = self._make_tree_view()
        tree.loader.return_value = mock_loader_instance

        with (
            patch("nxdrive.gui.folders_treeview.QThreadPool") as mock_pool_cls,
            patch("nxdrive.gui.folders_treeview.log") as mock_log,
        ):
            mock_pool_cls.globalInstance.return_value = None
            TreeViewMixin.load_children(tree)

        mock_log.error.assert_called_once_with(
            "Cannot get the global thread pool to load children"
        )

    def test_load_children_does_not_start_pool_when_pool_is_none(self):
        """load_children should not attempt pool.start when pool is None."""
        from nxdrive.gui.folders_treeview import TreeViewMixin

        mock_loader_instance = MagicMock()
        tree = self._make_tree_view()
        tree.loader.return_value = mock_loader_instance

        with patch("nxdrive.gui.folders_treeview.QThreadPool") as mock_pool_cls:
            mock_pool_cls.globalInstance.return_value = None
            # Should not raise AttributeError
            TreeViewMixin.load_children(tree)


# ---------------------------------------------------------------------------
# Shared sentinel (already defined above) – reused by FolderTreeView helpers
# ---------------------------------------------------------------------------

def _make_folder_tree(root_item=_UNSET, current=_UNSET, selected_folder=None):
    """Return a FolderTreeView created via __new__ with Qt internals mocked out."""
    from nxdrive.gui.folders_treeview import FolderTreeView

    with (
        patch("nxdrive.gui.folders_treeview.QTreeView.__init__", return_value=None),
        patch.object(FolderTreeView, "setHeaderHidden"),
        patch.object(FolderTreeView, "setModel"),
        patch.object(FolderTreeView, "load_children"),
        patch.object(FolderTreeView, "expanded", create=True),
        patch.object(FolderTreeView, "update", create=True),
        patch.object(FolderTreeView, "filled", create=True),
    ):
        tree = FolderTreeView.__new__(FolderTreeView)
        tree.parent = MagicMock()
        tree.client = MagicMock()
        tree.cache = []
        tree.root_item = MagicMock() if root_item is _UNSET else root_item
        tree.current = MagicMock() if current is _UNSET else current
        tree.selected_folder = selected_folder
        tree.load_children = MagicMock()
        return tree


# ---------------------------------------------------------------------------
# TestSetLoadingCursor
# ---------------------------------------------------------------------------

class TestSetLoadingCursor:
    """Unit tests for TreeViewMixin.set_loading_cursor."""

    def _make_tree_view(self):
        from nxdrive.gui.folders_treeview import TreeViewMixin

        with (
            patch("nxdrive.gui.folders_treeview.QTreeView.__init__", return_value=None),
            patch.object(TreeViewMixin, "setHeaderHidden"),
            patch.object(TreeViewMixin, "setModel"),
            patch.object(TreeViewMixin, "load_children"),
            patch.object(TreeViewMixin, "expanded", create=True),
        ):
            tree = TreeViewMixin.__new__(TreeViewMixin)
            tree.setCursor = MagicMock()
            tree.unsetCursor = MagicMock()
            return tree

    def test_busy_true_calls_set_cursor(self):
        """busy=True should call setCursor with BusyCursor."""
        from nxdrive.gui.folders_treeview import TreeViewMixin
        from nxdrive.qt import constants as qt

        tree = self._make_tree_view()
        TreeViewMixin.set_loading_cursor(tree, True)

        tree.setCursor.assert_called_once_with(qt.BusyCursor)
        tree.unsetCursor.assert_not_called()

    def test_busy_false_calls_unset_cursor(self):
        """busy=False should call unsetCursor."""
        from nxdrive.gui.folders_treeview import TreeViewMixin

        tree = self._make_tree_view()
        TreeViewMixin.set_loading_cursor(tree, False)

        tree.unsetCursor.assert_called_once_with()
        tree.setCursor.assert_not_called()

    def test_runtime_error_on_set_cursor_is_swallowed(self):
        """RuntimeError raised inside setCursor should be silently ignored."""
        from nxdrive.gui.folders_treeview import TreeViewMixin

        tree = self._make_tree_view()
        tree.setCursor.side_effect = RuntimeError("wrapped C/C++ object deleted")

        TreeViewMixin.set_loading_cursor(tree, True)  # must not raise

    def test_runtime_error_on_unset_cursor_is_swallowed(self):
        """RuntimeError raised inside unsetCursor should be silently ignored."""
        from nxdrive.gui.folders_treeview import TreeViewMixin

        tree = self._make_tree_view()
        tree.unsetCursor.side_effect = RuntimeError("wrapped C/C++ object deleted")

        TreeViewMixin.set_loading_cursor(tree, False)  # must not raise


# ---------------------------------------------------------------------------
# TestOnSelectionChanged
# ---------------------------------------------------------------------------

class TestOnSelectionChanged:
    """Unit tests for FolderTreeView.on_selection_changed."""

    def test_no_root_item_logs_error(self):
        """on_selection_changed should log an error when root_item is falsy."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree(root_item=None)

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            FolderTreeView.on_selection_changed(tree, MagicMock(), MagicMock())

        mock_log.error.assert_called_once_with(
            "Cannot get the model for FolderTreeView"
        )

    def test_no_standard_item_logs_error(self):
        """on_selection_changed should log an error when itemFromIndex returns None."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()
        tree.root_item.itemFromIndex.return_value = None

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            FolderTreeView.on_selection_changed(tree, MagicMock(), MagicMock())

        mock_log.error.assert_called_once_with(
            "Cannot get item data from selection"
        )

    def test_item_with_no_user_role_data_logs_error(self):
        """on_selection_changed should log an error when UserRole data is None."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()
        mock_item = MagicMock()
        mock_item.data.return_value = None
        tree.root_item.itemFromIndex.return_value = mock_item

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            FolderTreeView.on_selection_changed(tree, MagicMock(), MagicMock())

        mock_log.error.assert_called_once_with(
            "Cannot get item data from selection"
        )

    def test_happy_path_sets_parent_fields_and_calls_callbacks(self):
        """on_selection_changed should set all parent attributes and call callbacks."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()
        current_index = MagicMock()

        mock_data = MagicMock()
        mock_data.get_path.return_value = "/test/path"
        mock_data.get_id.return_value = "doc-id-123"
        mock_data.get_label.return_value = "My Folder"

        mock_item = MagicMock()
        mock_item.data.return_value = mock_data
        tree.root_item.itemFromIndex.return_value = mock_item

        FolderTreeView.on_selection_changed(tree, current_index, MagicMock())

        tree.parent.remote_folder.setText.assert_called_once_with("/test/path")
        assert tree.parent.remote_folder_ref == "doc-id-123"
        assert tree.parent.remote_folder_title == "My Folder"
        assert tree.current is current_index
        tree.parent.button_ok_state.assert_called_once()
        tree.parent.update_file_group.assert_called_once()


# ---------------------------------------------------------------------------
# TestRefreshSelected
# ---------------------------------------------------------------------------

class TestRefreshSelected:
    """Unit tests for FolderTreeView.refresh_selected."""

    def test_no_root_item_logs_error(self):
        """refresh_selected should log an error when root_item is falsy."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree(root_item=None)

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            FolderTreeView.refresh_selected(tree)

        mock_log.error.assert_called_once_with(
            "Cannot force reload the the current selected index"
        )
        tree.load_children.assert_not_called()

    def test_no_item_at_current_index_logs_error(self):
        """refresh_selected should log an error when itemFromIndex returns None."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()
        tree.root_item.itemFromIndex.return_value = None

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            FolderTreeView.refresh_selected(tree)

        mock_log.error.assert_called_once_with(
            "Cannot get the item to force reload the current selected index"
        )
        tree.load_children.assert_not_called()

    def test_calls_load_children_with_force_refresh(self):
        """refresh_selected should call load_children with force_refresh=True."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()
        mock_item = MagicMock()
        tree.root_item.itemFromIndex.return_value = mock_item

        FolderTreeView.refresh_selected(tree)

        tree.load_children.assert_called_once_with(item=mock_item, force_refresh=True)


# ---------------------------------------------------------------------------
# TestFindCurrentAndSelectIt
# ---------------------------------------------------------------------------

class TestFindCurrentAndSelectIt:
    """Unit tests for FolderTreeView._find_current_and_select_it."""

    def test_no_root_item_logs_error(self):
        """_find_current_and_select_it should log an error when root_item is falsy."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree(root_item=None)

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            FolderTreeView._find_current_and_select_it(tree)

        mock_log.error.assert_called_once_with(
            "Cannot expand the tree view and select the current index"
        )

    def test_no_item_falls_back_to_invisible_root(self):
        """When itemFromIndex returns None, invisibleRootItem should be used."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()
        tree.root_item.itemFromIndex.return_value = None

        mock_root_item = MagicMock()
        mock_root_item.rowCount.return_value = 0
        tree.root_item.invisibleRootItem.return_value = mock_root_item

        FolderTreeView._find_current_and_select_it(tree)

        tree.root_item.invisibleRootItem.assert_called_once()

    def test_no_item_and_no_invisible_root_logs_error(self):
        """_find_current_and_select_it should log an error when both item sources are None."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()
        tree.root_item.itemFromIndex.return_value = None
        tree.root_item.invisibleRootItem.return_value = None

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            FolderTreeView._find_current_and_select_it(tree)

        mock_log.error.assert_called_once_with("Cannot get item or invisible root item")

    def test_child_matching_selected_folder_is_selected(self):
        """A child whose path matches selected_folder should be selected."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree(selected_folder="/remote/target")
        tree.parent.remote_folder.text.return_value = "/other/path"

        mock_data = MagicMock()
        mock_data.get_path.return_value = "/remote/target"

        mock_child = MagicMock()
        mock_child.data.return_value = mock_data

        mock_item = MagicMock()
        mock_item.rowCount.return_value = 1
        mock_item.child.return_value = mock_child
        tree.root_item.itemFromIndex.return_value = mock_item

        mock_selection_model = MagicMock()
        tree.selectionModel = MagicMock(return_value=mock_selection_model)

        FolderTreeView._find_current_and_select_it(tree)

        mock_selection_model.select.assert_called_once()
        mock_selection_model.currentChanged.emit.assert_called_once()

    def test_child_matching_remote_folder_text_is_selected(self):
        """A child whose path matches parent.remote_folder.text() should be selected."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree(selected_folder=None)
        tree.parent.remote_folder.text.return_value = "/remote/target"

        mock_data = MagicMock()
        mock_data.get_path.return_value = "/remote/target"

        mock_child = MagicMock()
        mock_child.data.return_value = mock_data

        mock_item = MagicMock()
        mock_item.rowCount.return_value = 1
        mock_item.child.return_value = mock_child
        tree.root_item.itemFromIndex.return_value = mock_item

        mock_selection_model = MagicMock()
        tree.selectionModel = MagicMock(return_value=mock_selection_model)

        FolderTreeView._find_current_and_select_it(tree)

        mock_selection_model.select.assert_called_once()
        mock_selection_model.currentChanged.emit.assert_called_once()

    def test_no_selection_model_logs_error(self):
        """An unavailable selection model should log an error."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree(selected_folder="/remote/target")
        tree.parent.remote_folder.text.return_value = "/other"

        mock_data = MagicMock()
        mock_data.get_path.return_value = "/remote/target"

        mock_child = MagicMock()
        mock_child.data.return_value = mock_data

        mock_item = MagicMock()
        mock_item.rowCount.return_value = 1
        mock_item.child.return_value = mock_child
        tree.root_item.itemFromIndex.return_value = mock_item

        tree.selectionModel = MagicMock(return_value=None)

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            FolderTreeView._find_current_and_select_it(tree)

        mock_log.error.assert_called_once_with(
            "Cannot get the selection model to select the current index"
        )

    def test_partial_path_match_sets_longest_parent_and_expands(self):
        """A child whose path is a prefix of the remote folder text becomes longest_parent."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree(selected_folder=None)
        tree.parent.remote_folder.text.return_value = "/remote/target/deep"

        # Child: partial match (its path is within remote_folder.text())
        mock_data = MagicMock()
        mock_data.get_path.return_value = "/remote/target"

        mock_child = MagicMock()
        mock_child.data.return_value = mock_data

        mock_item = MagicMock()
        mock_item.rowCount.return_value = 1
        mock_item.child.return_value = mock_child
        tree.root_item.itemFromIndex.return_value = mock_item

        tree.setExpanded = MagicMock()

        FolderTreeView._find_current_and_select_it(tree)

        # current should be updated to the longest_parent's index
        assert tree.current == mock_child.index()
        tree.setExpanded.assert_called_once_with(mock_child.index(), True)

    def test_child_with_no_data_is_skipped(self):
        """Children without UserRole data should be skipped without error."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree(selected_folder="/remote/x")
        tree.parent.remote_folder.text.return_value = "/other"

        mock_child = MagicMock()
        mock_child.data.return_value = None  # no data

        mock_item = MagicMock()
        mock_item.rowCount.return_value = 1
        mock_item.child.return_value = mock_child
        tree.root_item.itemFromIndex.return_value = mock_item

        tree.setExpanded = MagicMock()

        # Should complete without error and without expanding anything
        FolderTreeView._find_current_and_select_it(tree)
        tree.setExpanded.assert_not_called()


# ---------------------------------------------------------------------------
# TestSelectItemFromPath
# ---------------------------------------------------------------------------

class TestSelectItemFromPath:
    """Unit tests for FolderTreeView.select_item_from_path."""

    def test_no_root_item_logs_error(self):
        """select_item_from_path should log an error when root_item is falsy."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree(root_item=None)

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            FolderTreeView.select_item_from_path(tree, "/some/path")

        mock_log.error.assert_called_once_with(
            "Cannot find and select an item in the tree view"
        )

    def test_no_item_at_current_logs_error(self):
        """select_item_from_path should log an error when current index has no item."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()
        tree.root_item.itemFromIndex.return_value = None

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            FolderTreeView.select_item_from_path(tree, "/some/path")

        mock_log.error.assert_called_once_with(
            "Cannot get item from current index"
        )

    def test_matching_child_sets_remote_folder_text(self):
        """When a child's path matches new_remote_path, remote_folder.setText is called."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()

        mock_data = MagicMock()
        mock_data.get_path.return_value = "/remote/new"

        mock_child = MagicMock()
        mock_child.data.return_value = mock_data

        mock_item = MagicMock()
        mock_item.rowCount.return_value = 1
        mock_item.child.return_value = mock_child
        tree.root_item.itemFromIndex.return_value = mock_item

        FolderTreeView.select_item_from_path(tree, "/remote/new")

        tree.parent.remote_folder.setText.assert_called_once_with("/remote/new")

    def test_no_matching_child_does_nothing(self):
        """When no child matches, remote_folder.setText should not be called."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()

        mock_data = MagicMock()
        mock_data.get_path.return_value = "/remote/other"

        mock_child = MagicMock()
        mock_child.data.return_value = mock_data

        mock_item = MagicMock()
        mock_item.rowCount.return_value = 1
        mock_item.child.return_value = mock_child
        tree.root_item.itemFromIndex.return_value = mock_item

        FolderTreeView.select_item_from_path(tree, "/remote/new")

        tree.parent.remote_folder.setText.assert_not_called()

    def test_child_with_no_data_is_skipped(self):
        """Children without UserRole data should be skipped without error."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()

        mock_child = MagicMock()
        mock_child.data.return_value = None

        mock_item = MagicMock()
        mock_item.rowCount.return_value = 1
        mock_item.child.return_value = mock_child
        tree.root_item.itemFromIndex.return_value = mock_item

        FolderTreeView.select_item_from_path(tree, "/remote/new")

        tree.parent.remote_folder.setText.assert_not_called()


# ---------------------------------------------------------------------------
# TestGetItemFromPosition
# ---------------------------------------------------------------------------

class TestGetItemFromPosition:
    """Unit tests for FolderTreeView.get_item_from_position."""

    def test_no_root_item_logs_error_and_returns_none(self):
        """get_item_from_position should log an error and return None when root_item is falsy."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree(root_item=None)
        tree.indexAt = MagicMock(return_value=MagicMock())

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            result = FolderTreeView.get_item_from_position(tree, MagicMock())

        assert result is None
        mock_log.error.assert_called_once_with(
            "Cannot get the item at the current position"
        )

    def test_item_found_is_returned(self):
        """get_item_from_position should return the item when found."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()
        mock_item = MagicMock()
        tree.root_item.itemFromIndex.return_value = mock_item
        tree.indexAt = MagicMock(return_value=MagicMock())

        result = FolderTreeView.get_item_from_position(tree, MagicMock())

        assert result is mock_item

    def test_no_item_found_logs_error_and_returns_none(self):
        """get_item_from_position should log an error and return None when no item exists."""
        from nxdrive.gui.folders_treeview import FolderTreeView

        tree = _make_folder_tree()
        tree.root_item.itemFromIndex.return_value = None
        tree.indexAt = MagicMock(return_value=MagicMock())

        with patch("nxdrive.gui.folders_treeview.log") as mock_log:
            result = FolderTreeView.get_item_from_position(tree, MagicMock())

        assert result is None
        mock_log.error.assert_called_once_with(
            "No item found at the current position"
        )
