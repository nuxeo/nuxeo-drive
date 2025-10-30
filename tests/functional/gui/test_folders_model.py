"""Functional tests for nxdrive.gui.folders_model module."""

from unittest.mock import MagicMock, patch

from nxdrive.gui.folders_model import (
    Doc,
    FileInfo,
    FilteredDoc,
    FilteredDocuments,
    FoldersOnly,
)
from nxdrive.qt import constants as qt


class TestFileInfo:
    """Test cases for FileInfo base class."""

    def test_file_info_initialization_no_parent(self):
        """Test FileInfo initialization without parent."""
        file_info = FileInfo()

        assert file_info.parent is None
        assert file_info.children == []

    def test_file_info_add_child(self):
        """Test adding children to FileInfo."""
        parent = FileInfo()
        child1 = FileInfo()
        child2 = FileInfo()

        parent.add_child(child1)
        parent.add_child(child2)

        assert child1 in parent.children
        assert child2 in parent.children
        assert len(parent.children) == 2

    def test_file_info_get_children(self):
        """Test getting children from FileInfo."""
        parent = FileInfo()
        child1 = FileInfo()
        child2 = FileInfo()
        parent.add_child(child1)
        parent.add_child(child2)

        children = list(parent.get_children())

        assert len(children) == 2
        assert child1 in children
        assert child2 in children

    def test_file_info_default_methods(self):
        """Test default method implementations."""
        file_info = FileInfo()

        assert file_info.enable() is True
        assert file_info.selectable() is True
        assert file_info.checkable() is True
        assert file_info.get_label() == ""
        assert file_info.get_id() == ""
        assert file_info.folderish() is False
        assert file_info.is_hidden() is False

    def test_file_info_get_path_no_parent(self):
        """Test get_path with no parent."""
        file_info = FileInfo()

        # Mock get_id to return a value
        with patch.object(file_info, "get_id", return_value="test_id"):
            path = file_info.get_path()
            assert path == "/test_id"

    def test_file_info_repr(self):
        """Test string representation of FileInfo."""
        file_info = FileInfo()

        with patch.object(file_info, "get_id", return_value="test_id"), patch.object(
            file_info, "get_label", return_value="Test Label"
        ), patch.object(file_info, "get_path", return_value="/test/path"):

            repr_str = repr(file_info)
            assert "FileInfo" in repr_str
            assert "test_id" in repr_str
            assert "Test Label" in repr_str
            assert "/test/path" in repr_str


class TestDoc:
    """Test cases for Doc class."""

    def create_mock_document(self, uid="doc123", title="Test Document"):
        """Helper to create a mock document."""
        mock_doc = MagicMock()
        mock_doc.uid = uid
        mock_doc.title = title
        mock_doc.path = f"/test/path/{uid}"
        mock_doc.type = "Folder"
        mock_doc.facets = ["Folderish"]
        mock_doc.contextParameters = {"permissions": ["Read", "AddChildren"]}
        return mock_doc

    def test_doc_initialization_basic(self):
        """Test basic Doc initialization."""
        mock_document = self.create_mock_document()

        doc = Doc(mock_document)

        assert doc.parent is None
        assert doc.children == []

    def test_doc_methods(self):
        """Test Doc method implementations."""
        mock_document = self.create_mock_document()

        doc = Doc(mock_document)

        assert doc.get_id() == "doc123"
        assert doc.get_label() == "Test Document"
        assert doc.get_path() == "/test/path/doc123"
        assert doc.folderish() is True

    def test_doc_enable_method(self):
        """Test Doc enable method with different permissions."""
        mock_document = self.create_mock_document()

        with patch("nxdrive.gui.folders_model.Options") as mock_options:
            mock_options.disallowed_types_for_dt = []

            doc = Doc(mock_document)
            assert doc.enable() is True

            # Test with disallowed type
            mock_options.disallowed_types_for_dt = ["Folder"]
            assert doc.enable() is False

    def test_doc_selectable_method(self):
        """Test Doc selectable method."""
        mock_document = self.create_mock_document()

        doc = Doc(mock_document)
        assert doc.selectable() is True

        # Test without Read permission
        mock_document.contextParameters["permissions"] = ["AddChildren"]
        doc = Doc(mock_document)
        assert doc.selectable() is False

    def test_doc_repr(self):
        """Test Doc string representation."""
        mock_document = self.create_mock_document()

        doc = Doc(mock_document)

        repr_str = repr(doc)
        assert "Doc" in repr_str
        assert "doc123" in repr_str
        assert "Test Document" in repr_str


class TestFilteredDoc:
    """Test cases for FilteredDoc class."""

    def create_mock_fs_info(self, uid="file123", name="test.pdf"):
        """Helper to create mock filesystem info."""
        mock_fs = MagicMock()
        mock_fs.uid = uid
        mock_fs.name = name
        mock_fs.path = f"/test/path/{name}"
        mock_fs.folderish = False
        return mock_fs

    def test_filtered_doc_initialization(self):
        """Test FilteredDoc initialization."""
        mock_fs_info = self.create_mock_fs_info()

        filtered_doc = FilteredDoc(mock_fs_info, qt.Checked)

        assert isinstance(filtered_doc, FilteredDoc)
        assert isinstance(filtered_doc, FileInfo)
        assert filtered_doc.state == qt.Checked
        assert filtered_doc.old_state == qt.Checked

    def test_filtered_doc_methods(self):
        """Test FilteredDoc method implementations."""
        mock_fs_info = self.create_mock_fs_info()

        filtered_doc = FilteredDoc(mock_fs_info, qt.Checked)

        assert filtered_doc.get_id() == "file123"
        assert filtered_doc.get_label() == "test.pdf"
        assert filtered_doc.get_path() == "/test/path/test.pdf"
        assert filtered_doc.folderish() is False

    def test_filtered_doc_is_dirty(self):
        """Test FilteredDoc is_dirty method."""
        mock_fs_info = self.create_mock_fs_info()

        filtered_doc = FilteredDoc(mock_fs_info, qt.Checked)

        # Initially not dirty
        assert filtered_doc.is_dirty() is False

        # Change state to make it dirty
        filtered_doc.state = qt.Unchecked
        assert filtered_doc.is_dirty() is True

    def test_filtered_doc_repr(self):
        """Test FilteredDoc string representation."""
        mock_fs_info = self.create_mock_fs_info()

        filtered_doc = FilteredDoc(mock_fs_info, qt.Checked)

        repr_str = repr(filtered_doc)
        assert "FilteredDoc" in repr_str
        assert "file123" in repr_str
        assert "test.pdf" in repr_str


class TestFilteredDocuments:
    """Test cases for FilteredDocuments class."""

    def test_filtered_documents_initialization(self):
        """Test FilteredDocuments initialization."""
        mock_remote = MagicMock()
        mock_filters = ["filter1", "filter2"]

        filtered_docs = FilteredDocuments(mock_remote, mock_filters)

        assert filtered_docs.remote == mock_remote
        assert filtered_docs.filters == tuple(mock_filters)
        assert filtered_docs.roots == []

    def test_get_item_state_filtered(self):
        """Test get_item_state for filtered items."""
        mock_remote = MagicMock()
        mock_filters = ["/test/filtered/"]

        filtered_docs = FilteredDocuments(mock_remote, mock_filters)

        # Test filtered path
        state = filtered_docs.get_item_state("/test/filtered/file.txt")
        assert state == qt.Unchecked

    def test_get_item_state_parent_of_filtered(self):
        """Test get_item_state for parent of filtered items."""
        mock_remote = MagicMock()
        mock_filters = ["/test/parent/filtered/"]

        filtered_docs = FilteredDocuments(mock_remote, mock_filters)

        # Test parent path
        state = filtered_docs.get_item_state("/test/parent/")
        assert state == qt.PartiallyChecked

    def test_get_item_state_not_filtered(self):
        """Test get_item_state for non-filtered items."""
        mock_remote = MagicMock()
        mock_filters = ["/other/path/"]

        filtered_docs = FilteredDocuments(mock_remote, mock_filters)

        # Test non-filtered path
        state = filtered_docs.get_item_state("/test/file.txt")
        assert state == qt.Checked

    @patch("nxdrive.gui.folders_model.FilteredDoc")
    def test_get_top_documents(self, mock_filtered_doc_class):
        """Test get_top_documents method."""
        mock_remote = MagicMock()
        mock_filters = []

        # Mock filesystem root and children
        mock_root_info = MagicMock()
        mock_root_info.uid = "root123"
        mock_remote.get_filesystem_root_info.return_value = mock_root_info

        mock_sync_root = MagicMock()
        mock_sync_root.path = "/sync/root"
        mock_remote.get_fs_children.return_value = [mock_sync_root]

        mock_filtered_doc = MagicMock()
        mock_filtered_doc_class.return_value = mock_filtered_doc

        filtered_docs = FilteredDocuments(mock_remote, mock_filters)

        # Get top documents
        top_docs = list(filtered_docs.get_top_documents())

        assert len(top_docs) == 1
        assert mock_filtered_doc in filtered_docs.roots
        mock_remote.get_filesystem_root_info.assert_called_once()
        mock_remote.get_fs_children.assert_called_once_with("root123", filtered=False)

    @patch("nxdrive.gui.folders_model.FilteredDoc")
    def test_get_children(self, mock_filtered_doc_class):
        """Test get_children method."""
        mock_remote = MagicMock()
        mock_filters = []

        # Mock parent and children
        mock_parent = MagicMock()
        mock_parent.get_id.return_value = "parent123"

        mock_child_info = MagicMock()
        mock_child_info.path = "/parent/child"
        mock_remote.get_fs_children.return_value = [mock_child_info]

        mock_filtered_doc = MagicMock()
        mock_filtered_doc_class.return_value = mock_filtered_doc

        filtered_docs = FilteredDocuments(mock_remote, mock_filters)

        # Get children
        children = list(filtered_docs.get_children(mock_parent))

        assert len(children) == 1
        assert mock_filtered_doc in children
        mock_remote.get_fs_children.assert_called_once_with("parent123", filtered=False)


class TestFoldersOnly:
    """Test cases for FoldersOnly class."""

    def test_folders_only_initialization(self):
        """Test FoldersOnly initialization."""
        mock_remote = MagicMock()

        folders_only = FoldersOnly(mock_remote)

        assert folders_only.remote == mock_remote

    @patch("nxdrive.gui.folders_model.Translator")
    @patch("nxdrive.gui.folders_model.Doc")
    def test_get_personal_space(self, mock_doc_class, mock_translator):
        """Test get_personal_space method."""
        mock_remote = MagicMock()
        mock_translator.get.return_value = "Personal Space"

        # Mock personal space document
        mock_personal_space = MagicMock()
        mock_personal_space.title = "User Name"
        mock_personal_space.contextParameters = {"permissions": []}
        mock_remote.personal_space.return_value = mock_personal_space

        mock_doc = MagicMock()
        mock_doc_class.return_value = mock_doc

        folders_only = FoldersOnly(mock_remote)
        folders_only.get_personal_space()

        # Verify title was changed
        assert mock_personal_space.title == "Personal Space"
        # Verify permissions were added
        expected_permissions = ["AddChildren", "Read", "ReadWrite"]
        assert (
            mock_personal_space.contextParameters["permissions"] == expected_permissions
        )

        mock_translator.get.assert_called_once_with("PERSONAL_SPACE")
        mock_doc_class.assert_called_once_with(mock_personal_space)

    @patch("nxdrive.gui.folders_model.Translator")
    @patch("nxdrive.gui.folders_model.Doc")
    def test_get_personal_space_with_exception(self, mock_doc_class, mock_translator):
        """Test _get_personal_space with exception handling."""
        mock_remote = MagicMock()
        mock_remote.personal_space.side_effect = Exception("Network error")
        mock_translator.get.return_value = "Personal Space"

        mock_doc = MagicMock()
        mock_doc_class.return_value = mock_doc

        folders_only = FoldersOnly(mock_remote)
        folders_only._get_personal_space()

        # Should create a fallback document
        mock_doc_class.assert_called_once()
        call_args = mock_doc_class.call_args[0][0]
        assert call_args.title == "Personal Space"
        assert call_args.contextParameters["permissions"] == []

    @patch("nxdrive.gui.folders_model.Doc")
    def test_get_children(self, mock_doc_class):
        """Test get_children method."""
        mock_remote = MagicMock()
        folders_only = FoldersOnly(mock_remote)

        # Mock parent and children documents
        mock_parent = MagicMock()
        mock_parent.get_id.return_value = "parent123"

        mock_child_doc = MagicMock()
        mock_child_doc.uid = "child123"
        mock_child_doc.title = "Child Document"

        # Mock _get_children method
        with patch.object(folders_only, "_get_children", return_value=[mock_child_doc]):
            mock_doc_instance = MagicMock()
            mock_doc_class.return_value = mock_doc_instance

            children = list(folders_only.get_children(mock_parent))

            assert len(children) == 1
            assert mock_doc_instance in children

    @patch("nxdrive.gui.folders_model.Options")
    def test_get_top_documents(self, mock_options):
        """Test get_top_documents method."""
        mock_remote = MagicMock()
        folders_only = FoldersOnly(mock_remote)

        # Configure options
        mock_options.dt_hide_personal_space = False

        # Mock methods
        mock_personal_space = MagicMock()
        mock_root_folders = [MagicMock(), MagicMock()]

        with patch.object(
            folders_only, "_get_personal_space", return_value=mock_personal_space
        ), patch.object(
            folders_only, "_get_root_folders", return_value=mock_root_folders
        ):

            top_docs = list(folders_only.get_top_documents())

            # Should include personal space + root folders
            assert len(top_docs) == 3
            assert mock_personal_space in top_docs
            assert all(folder in top_docs for folder in mock_root_folders)

    @patch("nxdrive.gui.folders_model.Options")
    def test_get_top_documents_hide_personal_space(self, mock_options):
        """Test get_top_documents with hidden personal space."""
        mock_remote = MagicMock()
        folders_only = FoldersOnly(mock_remote)

        # Configure options to hide personal space
        mock_options.dt_hide_personal_space = True

        # Mock methods
        mock_root_folders = [MagicMock(), MagicMock()]

        with patch.object(
            folders_only, "_get_personal_space"
        ) as mock_personal_space_method, patch.object(
            folders_only, "_get_root_folders", return_value=mock_root_folders
        ):

            top_docs = list(folders_only.get_top_documents())

            # Should only include root folders
            assert len(top_docs) == 2
            assert all(folder in top_docs for folder in mock_root_folders)
            # Personal space method should not be called
            mock_personal_space_method.assert_not_called()


class TestIntegrationScenarios:
    """Integration test scenarios for folders_model."""

    def create_mock_document(self, uid, title, doc_type="Folder"):
        """Helper to create mock documents."""
        mock_doc = MagicMock()
        mock_doc.uid = uid
        mock_doc.title = title
        mock_doc.path = f"/test/{uid}"
        mock_doc.type = doc_type
        mock_doc.facets = ["Folderish"] if doc_type == "Folder" else []
        mock_doc.contextParameters = {"permissions": ["Read", "AddChildren"]}
        return mock_doc

    def test_file_info_hierarchy_manipulation(self):
        """Test manual hierarchy manipulation."""
        # Create hierarchy avoiding Qt type system
        root = FileInfo()
        child1 = FileInfo()
        child2 = FileInfo()

        # Manually build hierarchy using add_child
        root.add_child(child1)
        root.add_child(child2)

        # Verify structure
        assert len(root.children) == 2
        assert child1 in root.children
        assert child2 in root.children

    def test_document_method_interactions(self):
        """Test interactions between different document methods."""
        mock_doc = self.create_mock_document("test123", "Test Document")
        doc = Doc(mock_doc)

        # Test method interactions
        assert doc.get_id() == "test123"
        assert doc.get_label() == "Test Document"
        assert doc.folderish() is True
        assert doc.enable() is True
        assert doc.selectable() is True

        # Test repr includes all relevant info
        repr_str = repr(doc)
        assert "test123" in repr_str
        assert "Test Document" in repr_str

    def test_filtered_documents_state_management(self):
        """Test state management in FilteredDocuments."""
        mock_remote = MagicMock()
        mock_filters = ["/filtered/path/"]

        filtered_docs = FilteredDocuments(mock_remote, mock_filters)

        # Test different path scenarios
        assert filtered_docs.get_item_state("/filtered/path/file.txt") == qt.Unchecked
        assert filtered_docs.get_item_state("/filtered/") == qt.PartiallyChecked
        assert filtered_docs.get_item_state("/other/file.txt") == qt.Checked

    def test_complex_filtering_scenarios(self):
        """Test complex filtering scenarios."""
        mock_remote = MagicMock()
        # Multiple filter patterns
        mock_filters = ["/temp/", "/cache/", "/logs/debug/"]

        filtered_docs = FilteredDocuments(mock_remote, mock_filters)

        # Test various paths
        assert filtered_docs.get_item_state("/temp/file.txt") == qt.Unchecked
        assert filtered_docs.get_item_state("/cache/data.bin") == qt.Unchecked
        assert filtered_docs.get_item_state("/logs/debug/error.log") == qt.Unchecked
        assert filtered_docs.get_item_state("/logs/") == qt.PartiallyChecked
        assert filtered_docs.get_item_state("/docs/readme.txt") == qt.Checked
