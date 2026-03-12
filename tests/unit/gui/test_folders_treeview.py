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
