"""Integration tests for FoldersDialog.get_tree_view method - macOS only."""

from unittest.mock import Mock, patch, MagicMock

from ....markers import mac_only

# The real get_tree_view lives on FoldersDialog (a QDialog subclass).
# We test it by calling the unbound method with a mock self and patching
# the server-type registry (_st) and FolderTreeView.

_PATCH_ST = "nxdrive.drive.gui.folders_dialog._st"
_PATCH_FTV = "nxdrive.drive.gui.folders_dialog.FolderTreeView"


def _make_dialog(selected_folder="/"):
    """Build a minimal mock that satisfies FoldersDialog.get_tree_view."""
    dialog = MagicMock()
    dialog.engine = Mock()
    dialog.engine.remote = Mock()
    dialog.engine.type = "nuxeo"
    dialog.selected_folder = selected_folder
    return dialog


def _call_get_tree_view(dialog):
    """Call the real get_tree_view on a mock dialog."""
    from nxdrive.drive.gui.folders_dialog import FoldersDialog

    return FoldersDialog.get_tree_view(dialog)


@mac_only
def test_get_tree_view_basic():
    """Test get_tree_view creates FolderTreeView with the loaded folders client."""
    dialog = _make_dialog("/")

    with patch(_PATCH_ST) as mock_st, patch(_PATCH_FTV) as mock_tree_view:
        mock_cls = Mock()
        mock_client = Mock()
        mock_cls.return_value = mock_client
        mock_config = Mock()
        mock_st.get_by_engine_type.return_value = mock_config
        mock_st.load_class.return_value = mock_cls
        mock_tree = Mock()
        mock_tree_view.return_value = mock_tree

        result = _call_get_tree_view(dialog)

        dialog.resize.assert_called_once_with(800, 450)
        mock_cls.assert_called_once_with(dialog.engine.remote)
        mock_tree_view.assert_called_once_with(dialog, mock_client, "/")
        assert result == mock_tree


@mac_only
def test_get_tree_view_with_different_selected_folder():
    """Test get_tree_view with different selected_folder value."""
    dialog = _make_dialog("/documents/folder1")

    with patch(_PATCH_ST) as mock_st, patch(_PATCH_FTV) as mock_tree_view:
        mock_cls = Mock(return_value=Mock())
        mock_st.get_by_engine_type.return_value = Mock()
        mock_st.load_class.return_value = mock_cls
        mock_tree = Mock()
        mock_tree_view.return_value = mock_tree

        result = _call_get_tree_view(dialog)

        mock_tree_view.assert_called_once_with(
            dialog, mock_cls.return_value, "/documents/folder1"
        )
        assert result == mock_tree


@mac_only
def test_get_tree_view_with_none_selected_folder():
    """Test get_tree_view with None as selected_folder."""
    dialog = _make_dialog(None)

    with patch(_PATCH_ST) as mock_st, patch(_PATCH_FTV) as mock_tree_view:
        mock_cls = Mock(return_value=Mock())
        mock_st.get_by_engine_type.return_value = Mock()
        mock_st.load_class.return_value = mock_cls
        mock_tree = Mock()
        mock_tree_view.return_value = mock_tree

        result = _call_get_tree_view(dialog)

        mock_tree_view.assert_called_once_with(dialog, mock_cls.return_value, None)
        assert result == mock_tree


@mac_only
def test_get_tree_view_resize_dimensions():
    """Test get_tree_view calls resize with correct dimensions."""
    dialog = _make_dialog("/")

    with patch(_PATCH_ST) as mock_st, patch(_PATCH_FTV) as mock_tree_view:
        mock_cls = Mock(return_value=Mock())
        mock_st.get_by_engine_type.return_value = Mock()
        mock_st.load_class.return_value = mock_cls
        mock_tree_view.return_value = Mock()

        _call_get_tree_view(dialog)

        dialog.resize.assert_called_once_with(800, 450)


@mac_only
def test_get_tree_view_folders_only_client_creation():
    """Test get_tree_view creates the folders client with engine.remote."""
    dialog = _make_dialog("/")

    with patch(_PATCH_ST) as mock_st, patch(_PATCH_FTV) as mock_tree_view:
        mock_cls = Mock(return_value=Mock())
        mock_st.get_by_engine_type.return_value = Mock()
        mock_st.load_class.return_value = mock_cls
        mock_tree_view.return_value = Mock()

        _call_get_tree_view(dialog)

        mock_cls.assert_called_once_with(dialog.engine.remote)


@mac_only
def test_get_tree_view_folder_tree_view_parameters():
    """Test get_tree_view passes correct parameters to FolderTreeView."""
    dialog = _make_dialog("/workspace")

    with patch(_PATCH_ST) as mock_st, patch(_PATCH_FTV) as mock_tree_view:
        mock_client = Mock()
        mock_cls = Mock(return_value=mock_client)
        mock_st.get_by_engine_type.return_value = Mock()
        mock_st.load_class.return_value = mock_cls
        mock_tree_view.return_value = Mock()

        _call_get_tree_view(dialog)

        mock_tree_view.assert_called_once()
        call_args = mock_tree_view.call_args[0]
        assert len(call_args) == 3
        assert call_args[0] == dialog
        assert call_args[1] == mock_client
        assert call_args[2] == "/workspace"


@mac_only
def test_get_tree_view_return_value():
    """Test get_tree_view returns the FolderTreeView instance."""
    dialog = _make_dialog("/")

    with patch(_PATCH_ST) as mock_st, patch(_PATCH_FTV) as mock_tree_view:
        mock_cls = Mock(return_value=Mock())
        mock_st.get_by_engine_type.return_value = Mock()
        mock_st.load_class.return_value = mock_cls
        expected_tree = Mock()
        mock_tree_view.return_value = expected_tree

        result = _call_get_tree_view(dialog)

        assert result is expected_tree


@mac_only
def test_get_tree_view_call_order():
    """Test get_tree_view calls methods in correct order: resize, load class, create tree."""
    dialog = _make_dialog("/")
    call_order = []
    dialog.resize.side_effect = lambda w, h: call_order.append("resize")

    with patch(_PATCH_ST) as mock_st, patch(_PATCH_FTV) as mock_tree_view:

        def load_class_side_effect(path):
            call_order.append("load_class")
            cls = Mock()
            cls.side_effect = (
                lambda remote: call_order.append("create_client") or Mock()
            )
            return cls

        mock_st.get_by_engine_type.return_value = Mock()
        mock_st.load_class.side_effect = load_class_side_effect
        mock_tree_view.side_effect = (
            lambda *a: call_order.append("FolderTreeView") or Mock()
        )

        _call_get_tree_view(dialog)

        assert call_order == [
            "resize",
            "load_class",
            "create_client",
            "FolderTreeView",
        ]
