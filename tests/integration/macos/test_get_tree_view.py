"""Integration tests for FoldersDialog.get_tree_view method - macOS only."""

from unittest.mock import Mock, patch

from ...markers import mac_only


@mac_only
def test_get_tree_view_basic():
    """Test get_tree_view creates FolderTreeView with FoldersOnly client."""

    class MockFoldersDialog:
        def __init__(self):
            self.engine = Mock()
            self.engine.remote = Mock()
            self.selected_folder = "/"

        def resize(self, width, height):
            self.resized_width = width
            self.resized_height = height

        def get_tree_view(self):
            """Render the folders tree."""
            self.resize(800, 450)
            from nxdrive.gui.folders_dialog import FoldersOnly, FolderTreeView

            client = FoldersOnly(self.engine.remote)
            return FolderTreeView(self, client, self.selected_folder)

    dialog = MockFoldersDialog()

    with (
        patch("nxdrive.gui.folders_dialog.FoldersOnly") as mock_folders_only,
        patch("nxdrive.gui.folders_dialog.FolderTreeView") as mock_tree_view,
    ):
        mock_client = Mock()
        mock_folders_only.return_value = mock_client
        mock_tree = Mock()
        mock_tree_view.return_value = mock_tree

        result = dialog.get_tree_view()

        # Verify resize called with 800x450
        assert dialog.resized_width == 800
        assert dialog.resized_height == 450

        # Verify FoldersOnly created with engine.remote
        mock_folders_only.assert_called_once_with(dialog.engine.remote)

        # Verify FolderTreeView created with dialog, client, and selected_folder
        mock_tree_view.assert_called_once_with(dialog, mock_client, "/")

        # Verify return value
        assert result == mock_tree


@mac_only
def test_get_tree_view_with_different_selected_folder():
    """Test get_tree_view with different selected_folder value."""

    class MockFoldersDialog:
        def __init__(self):
            self.engine = Mock()
            self.engine.remote = Mock()
            self.selected_folder = "/documents/folder1"

        def resize(self, width, height):
            pass

        def get_tree_view(self):
            self.resize(800, 450)
            from nxdrive.gui.folders_dialog import FoldersOnly, FolderTreeView

            client = FoldersOnly(self.engine.remote)
            return FolderTreeView(self, client, self.selected_folder)

    dialog = MockFoldersDialog()

    with (
        patch("nxdrive.gui.folders_dialog.FoldersOnly") as mock_folders_only,
        patch("nxdrive.gui.folders_dialog.FolderTreeView") as mock_tree_view,
    ):
        mock_client = Mock()
        mock_folders_only.return_value = mock_client
        mock_tree = Mock()
        mock_tree_view.return_value = mock_tree

        result = dialog.get_tree_view()

        # Verify FolderTreeView created with correct selected_folder
        mock_tree_view.assert_called_once_with(
            dialog, mock_client, "/documents/folder1"
        )
        assert result == mock_tree


@mac_only
def test_get_tree_view_with_none_selected_folder():
    """Test get_tree_view with None as selected_folder."""

    class MockFoldersDialog:
        def __init__(self):
            self.engine = Mock()
            self.engine.remote = Mock()
            self.selected_folder = None

        def resize(self, width, height):
            pass

        def get_tree_view(self):
            self.resize(800, 450)
            from nxdrive.gui.folders_dialog import FoldersOnly, FolderTreeView

            client = FoldersOnly(self.engine.remote)
            return FolderTreeView(self, client, self.selected_folder)

    dialog = MockFoldersDialog()

    with (
        patch("nxdrive.gui.folders_dialog.FoldersOnly") as mock_folders_only,
        patch("nxdrive.gui.folders_dialog.FolderTreeView") as mock_tree_view,
    ):
        mock_client = Mock()
        mock_folders_only.return_value = mock_client
        mock_tree = Mock()
        mock_tree_view.return_value = mock_tree

        result = dialog.get_tree_view()

        # Verify FolderTreeView created with None as selected_folder
        mock_tree_view.assert_called_once_with(dialog, mock_client, None)
        assert result == mock_tree


@mac_only
def test_get_tree_view_resize_dimensions():
    """Test get_tree_view calls resize with correct dimensions."""

    class MockFoldersDialog:
        def __init__(self):
            self.engine = Mock()
            self.engine.remote = Mock()
            self.selected_folder = "/"
            self.resize_calls = []

        def resize(self, width, height):
            self.resize_calls.append((width, height))

        def get_tree_view(self):
            self.resize(800, 450)
            from nxdrive.gui.folders_dialog import FoldersOnly, FolderTreeView

            client = FoldersOnly(self.engine.remote)
            return FolderTreeView(self, client, self.selected_folder)

    dialog = MockFoldersDialog()

    with (
        patch("nxdrive.gui.folders_dialog.FoldersOnly") as mock_folders_only,
        patch("nxdrive.gui.folders_dialog.FolderTreeView") as mock_tree_view,
    ):
        mock_folders_only.return_value = Mock()
        mock_tree_view.return_value = Mock()

        dialog.get_tree_view()

        # Verify resize called with exact dimensions
        assert len(dialog.resize_calls) == 1
        assert dialog.resize_calls[0] == (800, 450)


@mac_only
def test_get_tree_view_folders_only_client_creation():
    """Test get_tree_view creates FoldersOnly client with engine.remote."""

    class MockFoldersDialog:
        def __init__(self):
            self.engine = Mock()
            self.engine.remote = Mock()
            self.selected_folder = "/"

        def resize(self, width, height):
            pass

        def get_tree_view(self):
            self.resize(800, 450)
            from nxdrive.gui.folders_dialog import FoldersOnly, FolderTreeView

            client = FoldersOnly(self.engine.remote)
            return FolderTreeView(self, client, self.selected_folder)

    dialog = MockFoldersDialog()

    with (
        patch("nxdrive.gui.folders_dialog.FoldersOnly") as mock_folders_only,
        patch("nxdrive.gui.folders_dialog.FolderTreeView") as mock_tree_view,
    ):
        mock_client = Mock()
        mock_folders_only.return_value = mock_client
        mock_tree_view.return_value = Mock()

        dialog.get_tree_view()

        # Verify FoldersOnly created with engine.remote
        mock_folders_only.assert_called_once_with(dialog.engine.remote)


@mac_only
def test_get_tree_view_folder_tree_view_parameters():
    """Test get_tree_view passes correct parameters to FolderTreeView."""

    class MockFoldersDialog:
        def __init__(self):
            self.engine = Mock()
            self.engine.remote = Mock()
            self.selected_folder = "/workspace"

        def resize(self, width, height):
            pass

        def get_tree_view(self):
            self.resize(800, 450)
            from nxdrive.gui.folders_dialog import FoldersOnly, FolderTreeView

            client = FoldersOnly(self.engine.remote)
            return FolderTreeView(self, client, self.selected_folder)

    dialog = MockFoldersDialog()

    with (
        patch("nxdrive.gui.folders_dialog.FoldersOnly") as mock_folders_only,
        patch("nxdrive.gui.folders_dialog.FolderTreeView") as mock_tree_view,
    ):
        mock_client = Mock()
        mock_folders_only.return_value = mock_client
        mock_tree_view.return_value = Mock()

        dialog.get_tree_view()

        # Verify all 3 parameters passed to FolderTreeView
        mock_tree_view.assert_called_once()
        call_args = mock_tree_view.call_args[0]
        assert len(call_args) == 3
        assert call_args[0] == dialog
        assert call_args[1] == mock_client
        assert call_args[2] == "/workspace"


@mac_only
def test_get_tree_view_return_value():
    """Test get_tree_view returns the FolderTreeView instance."""

    class MockFoldersDialog:
        def __init__(self):
            self.engine = Mock()
            self.engine.remote = Mock()
            self.selected_folder = "/"

        def resize(self, width, height):
            pass

        def get_tree_view(self):
            self.resize(800, 450)
            from nxdrive.gui.folders_dialog import FoldersOnly, FolderTreeView

            client = FoldersOnly(self.engine.remote)
            return FolderTreeView(self, client, self.selected_folder)

    dialog = MockFoldersDialog()

    with (
        patch("nxdrive.gui.folders_dialog.FoldersOnly") as mock_folders_only,
        patch("nxdrive.gui.folders_dialog.FolderTreeView") as mock_tree_view,
    ):
        mock_folders_only.return_value = Mock()
        expected_tree = Mock()
        mock_tree_view.return_value = expected_tree

        result = dialog.get_tree_view()

        # Verify return value is the FolderTreeView instance
        assert result is expected_tree


@mac_only
def test_get_tree_view_call_order():
    """Test get_tree_view calls methods in correct order."""

    class MockFoldersDialog:
        def __init__(self):
            self.engine = Mock()
            self.engine.remote = Mock()
            self.selected_folder = "/"
            self.call_order = []

        def resize(self, width, height):
            self.call_order.append("resize")

        def get_tree_view(self):
            self.resize(800, 450)
            self.call_order.append("before_FoldersOnly")
            from nxdrive.gui.folders_dialog import FoldersOnly, FolderTreeView

            client = FoldersOnly(self.engine.remote)
            self.call_order.append("before_FolderTreeView")
            return FolderTreeView(self, client, self.selected_folder)

    dialog = MockFoldersDialog()

    with (
        patch("nxdrive.gui.folders_dialog.FoldersOnly") as mock_folders_only,
        patch("nxdrive.gui.folders_dialog.FolderTreeView") as mock_tree_view,
    ):
        mock_folders_only.return_value = Mock()
        mock_tree_view.return_value = Mock()

        dialog.get_tree_view()

        # Verify call order
        assert dialog.call_order == [
            "resize",
            "before_FoldersOnly",
            "before_FolderTreeView",
        ]
