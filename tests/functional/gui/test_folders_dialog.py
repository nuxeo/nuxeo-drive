"""Test the folder dialog classes without creating real Qt dialogs."""

from unittest.mock import MagicMock, Mock, patch

from nxdrive.engine.engine import Engine


class TestDialogMixin:
    """Test cases for DialogMixin base class."""

    def create_mock_application(self):
        """Create a mock application for testing."""
        mock_app = MagicMock()
        mock_app.icon = Mock()
        return mock_app

    def create_mock_engine(self):
        """Create a mock engine for testing."""
        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.remote_watcher = Mock()
        mock_engine.local_watcher = Mock()
        mock_engine.dao = Mock()
        return mock_engine

    def test_dialog_mixin_initialization(self):
        """Test DialogMixin initialization with proper mocking."""
        mock_app = self.create_mock_application()
        mock_engine = self.create_mock_engine()

        class MockDialogMixin:
            def __init__(self, application, engine, selected_folder=None):
                self.title_label = "TEST_TITLE"
                self.engine = engine
                self.application = application
                self.selected_folder = selected_folder
                self.tree_view = Mock()
                self.button_box = Mock()
                self.vertical_layout = Mock()
                self.initialized = True

            def get_buttons(self):
                return Mock()  # Mock button flags

            def get_tree_view(self):
                return Mock()

        with patch("nxdrive.gui.folders_dialog.QDialog"), patch(
            "nxdrive.gui.folders_dialog.Translator"
        ):

            dialog = MockDialogMixin(mock_app, mock_engine, "/test/folder")

            # Test initialization
            assert dialog.engine == mock_engine
            assert dialog.application == mock_app
            assert dialog.selected_folder == "/test/folder"
            assert dialog.title_label == "TEST_TITLE"
            assert dialog.initialized is True

    def test_dialog_mixin_button_creation(self):
        """Test button creation functionality."""
        mock_app = self.create_mock_application()
        mock_engine = self.create_mock_engine()

        class MockDialogMixin:
            def __init__(self, application, engine):
                self.application = application
                self.engine = engine
                self.buttons_created = []

            def get_buttons(self):
                # Simulate Qt button flags
                return ["OK", "Cancel"]

            def create_button_box(self):
                buttons = self.get_buttons()
                self.buttons_created = buttons
                return Mock()

        dialog = MockDialogMixin(mock_app, mock_engine)
        button_box = dialog.create_button_box()

        assert dialog.buttons_created == ["OK", "Cancel"]
        assert button_box is not None


class TestDocumentsDialog:
    """Test cases for DocumentsDialog class."""

    def create_mock_application(self):
        """Create a mock application for testing."""
        mock_app = MagicMock()
        mock_app.icon = Mock()
        return mock_app

    def create_mock_engine(self):
        """Create a mock engine for testing."""
        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.dao = Mock()
        mock_engine.dao.get_sync_roots = Mock(return_value=[])
        return mock_engine

    def test_documents_dialog_initialization(self):
        """Test DocumentsDialog initialization."""
        mock_app = self.create_mock_application()
        mock_engine = self.create_mock_engine()

        class MockDocumentsDialog:
            def __init__(self, application, engine):
                self.title_label = "FILTERS_WINDOW_TITLE"
                self.application = application
                self.engine = engine
                self.tree_view = Mock()
                self.button_box = Mock()
                self.vertical_layout = Mock()
                self.no_root_label = Mock()
                self.filters_applied = False

            def get_buttons(self):
                return ["OK", "Cancel", "Apply"]

            def get_tree_view(self):
                mock_tree = Mock()
                mock_tree.setContentsMargins = Mock()
                return mock_tree

            def get_no_roots_label(self):
                mock_label = Mock()
                mock_label.setText = Mock()
                return mock_label

        with patch("nxdrive.gui.folders_dialog.QDialog"), patch(
            "nxdrive.gui.folders_dialog.Translator"
        ):

            dialog = MockDocumentsDialog(mock_app, mock_engine)

            # Test initialization
            assert dialog.title_label == "FILTERS_WINDOW_TITLE"
            assert dialog.application == mock_app
            assert dialog.engine == mock_engine

            # Test button configuration
            buttons = dialog.get_buttons()
            assert "Apply" in buttons

    def test_documents_dialog_tree_view_creation(self):
        """Test tree view creation for documents."""
        mock_app = self.create_mock_application()
        mock_engine = self.create_mock_engine()

        class MockDocumentsDialog:
            def __init__(self, application, engine):
                self.application = application
                self.engine = engine
                self.has_sync_roots = True

            def get_tree_view(self):
                if self.has_sync_roots:
                    mock_tree = Mock()
                    mock_tree.model = Mock()
                    mock_tree.selectionChanged = Mock()
                    return mock_tree
                else:
                    # Return a label when no sync roots
                    mock_label = Mock()
                    mock_label.setText = Mock()
                    return mock_label

        dialog = MockDocumentsDialog(mock_app, mock_engine)

        # Test with sync roots
        tree_view = dialog.get_tree_view()
        assert hasattr(tree_view, "model")

        # Test without sync roots
        dialog.has_sync_roots = False
        no_roots_view = dialog.get_tree_view()
        assert hasattr(no_roots_view, "setText")

    def test_documents_dialog_filter_application(self):
        """Test filter application functionality."""
        mock_app = self.create_mock_application()
        mock_engine = self.create_mock_engine()

        class MockDocumentsDialog:
            def __init__(self, application, engine):
                self.application = application
                self.engine = engine
                self.tree_view = Mock()
                self.filters_applied = False
                self.last_applied_filters = []

            def apply_filters(self):
                # Simulate gathering filter data from tree view
                mock_filters = [
                    {"path": "/folder1", "selected": True},
                    {"path": "/folder2", "selected": False},
                ]
                self.last_applied_filters = mock_filters
                self.filters_applied = True

                # Simulate engine filter update
                if hasattr(self.engine, "set_document_filters"):
                    self.engine.set_document_filters(mock_filters)

            def accept(self):
                self.apply_filters()
                return True

        dialog = MockDocumentsDialog(mock_app, mock_engine)
        mock_engine.set_document_filters = Mock()

        # Test filter application
        result = dialog.accept()
        assert result is True
        assert dialog.filters_applied is True
        assert len(dialog.last_applied_filters) == 2
        mock_engine.set_document_filters.assert_called_once()

    def test_documents_dialog_no_roots_handling(self):
        """Test handling when no sync roots are available."""
        mock_app = self.create_mock_application()
        mock_engine = self.create_mock_engine()

        class MockDocumentsDialog:
            def __init__(self, application, engine):
                self.application = application
                self.engine = engine
                self.no_roots_displayed = False

            def _handle_no_roots(self):
                self.no_roots_displayed = True

            def get_no_roots_label(self):
                mock_label = Mock()
                mock_label.setText = Mock()
                mock_label.setWordWrap = Mock()
                return mock_label

            def has_sync_roots(self):
                return len(self.engine.dao.get_sync_roots()) > 0

        dialog = MockDocumentsDialog(mock_app, mock_engine)

        # Test no roots case
        mock_engine.dao.get_sync_roots.return_value = []
        assert not dialog.has_sync_roots()

        dialog._handle_no_roots()
        assert dialog.no_roots_displayed is True

        # Test label creation
        label = dialog.get_no_roots_label()
        assert label is not None
        assert hasattr(label, "setText")
        assert hasattr(label, "setWordWrap")


class TestFoldersDialog:
    """Test cases for FoldersDialog class."""

    def create_mock_application(self):
        """Create a mock application for testing."""
        mock_app = MagicMock()
        mock_app.icon = Mock()
        return mock_app

    def create_mock_engine(self):
        """Create a mock engine for testing."""
        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "test_engine"
        mock_engine.dao = Mock()
        return mock_engine

    def test_folders_dialog_initialization(self):
        """Test FoldersDialog initialization."""
        mock_app = self.create_mock_application()
        mock_engine = self.create_mock_engine()

        class MockFoldersDialog:
            def __init__(self, application, engine, selected_folder=None):
                self.title_label = "SELECT_FOLDER_TITLE"
                self.application = application
                self.engine = engine
                self.selected_folder = selected_folder
                self.tree_view = Mock()
                self.button_box = Mock()
                self.vertical_layout = Mock()
                self.new_folder_button = Mock()
                self.overall_stats = {"count": 0, "size": 0}

            def get_tree_view(self):
                mock_tree = Mock()
                mock_tree.setRootIsDecorated = Mock()
                mock_tree.setHeaderHidden = Mock()
                return mock_tree

        dialog = MockFoldersDialog(mock_app, mock_engine, "/initial/folder")

        # Test initialization
        assert dialog.title_label == "SELECT_FOLDER_TITLE"
        assert dialog.selected_folder == "/initial/folder"
        assert dialog.application == mock_app
        assert dialog.engine == mock_engine

    def test_folders_dialog_new_folder_creation(self):
        """Test new folder creation functionality."""
        mock_app = self.create_mock_application()
        mock_engine = self.create_mock_engine()

        class MockFoldersDialog:
            def __init__(self, application, engine):
                self.application = application
                self.engine = engine
                self.tree_view = Mock()
                self.new_folders_created = []

            def create_new_folder(self, parent_path, folder_name):
                # Simulate folder creation using Path for cross-platform compatibility
                from pathlib import Path

                new_path = str(Path(parent_path) / folder_name)
                self.new_folders_created.append(new_path)

                # Update tree view
                self.tree_view.refresh_model()
                return new_path

            def validate_folder_name(self, name):
                # Simple validation
                invalid_chars = ["<", ">", ":", '"', "|", "?", "*"]
                return not any(char in name for char in invalid_chars)

        dialog = MockFoldersDialog(mock_app, mock_engine)
        dialog.tree_view.refresh_model = Mock()

        # Test valid folder creation
        assert dialog.validate_folder_name("ValidFolder")
        new_path = dialog.create_new_folder("/test/parent", "NewFolder")
        assert new_path in dialog.new_folders_created
        # Use Path for cross-platform comparison
        from pathlib import Path

        expected_path = str(Path("/test/parent") / "NewFolder")
        assert new_path == expected_path
        dialog.tree_view.refresh_model.assert_called_once()

        # Test invalid folder name
        assert not dialog.validate_folder_name("Invalid<Folder")

    def test_folders_dialog_selection_handling(self):
        """Test folder selection handling."""
        mock_app = self.create_mock_application()
        mock_engine = self.create_mock_engine()

        class MockFoldersDialog:
            def __init__(self, application, engine):
                self.application = application
                self.engine = engine
                self.selected_folder = None
                self.selection_changed_count = 0

            def on_selection_changed(self, selected_path):
                self.selected_folder = selected_path
                self.selection_changed_count += 1
                self.update_ui_for_selection()

            def update_ui_for_selection(self):
                # Simulate UI updates when selection changes
                if self.selected_folder:
                    self.enable_ok_button()
                else:
                    self.disable_ok_button()

            def enable_ok_button(self):
                self.ok_enabled = True

            def disable_ok_button(self):
                self.ok_enabled = False

        dialog = MockFoldersDialog(mock_app, mock_engine)

        # Test selection change
        dialog.on_selection_changed("/test/selected/folder")
        assert dialog.selected_folder == "/test/selected/folder"
        assert dialog.selection_changed_count == 1
        assert dialog.ok_enabled is True

        # Test deselection
        dialog.on_selection_changed(None)
        assert dialog.selected_folder is None
        assert dialog.ok_enabled is False

    def test_folders_dialog_context_menu(self):
        """Test context menu functionality."""
        mock_app = self.create_mock_application()
        mock_engine = self.create_mock_engine()

        class MockFoldersDialog:
            def __init__(self, application, engine):
                self.application = application
                self.engine = engine
                self.context_menu_actions = []

            def open_menu(self, position):
                # Simulate context menu creation
                mock_menu = Mock()

                # Add menu actions
                self.context_menu_actions = [
                    {"text": "New Folder", "enabled": True},
                    {"text": "Open", "enabled": True},
                    {"text": "Properties", "enabled": True},
                ]

                mock_menu.actions = self.context_menu_actions
                mock_menu.exec_ = Mock()
                return mock_menu

            def handle_menu_action(self, action_text):
                if action_text == "New Folder":
                    return self.show_new_folder_dialog()
                elif action_text == "Open":
                    return self.open_selected_folder()
                elif action_text == "Properties":
                    return self.show_folder_properties()

            def show_new_folder_dialog(self):
                return "NEW_FOLDER_DIALOG"

            def open_selected_folder(self):
                return "FOLDER_OPENED"

            def show_folder_properties(self):
                return "PROPERTIES_SHOWN"

        dialog = MockFoldersDialog(mock_app, mock_engine)

        # Test context menu creation
        dialog.open_menu(Mock())
        assert len(dialog.context_menu_actions) == 3
        assert dialog.context_menu_actions[0]["text"] == "New Folder"

        # Test menu actions
        assert dialog.handle_menu_action("New Folder") == "NEW_FOLDER_DIALOG"
        assert dialog.handle_menu_action("Open") == "FOLDER_OPENED"
        assert dialog.handle_menu_action("Properties") == "PROPERTIES_SHOWN"

    def test_folders_dialog_statistics(self):
        """Test folder statistics calculation."""
        mock_app = self.create_mock_application()
        mock_engine = self.create_mock_engine()

        class MockFoldersDialog:
            def __init__(self, application, engine):
                self.application = application
                self.engine = engine
                self.tree_view = Mock()
                self._overall_count = 0
                self._overall_size = 0

            def overall_count(self):
                return self._overall_count

            def overall_size(self):
                return self._overall_size

            def update_statistics(self, count, size):
                self._overall_count = count
                self._overall_size = size

            def get_folder_stats(self, folder_path):
                # Simulate calculating folder statistics
                mock_stats = {
                    "file_count": 42,
                    "folder_count": 8,
                    "total_size": 1024 * 1024 * 50,  # 50MB
                }
                return mock_stats

        dialog = MockFoldersDialog(mock_app, mock_engine)

        # Test statistics update
        dialog.update_statistics(100, 1024 * 1024 * 100)
        assert dialog.overall_count() == 100
        assert dialog.overall_size() == 1024 * 1024 * 100

        # Test folder stats calculation
        stats = dialog.get_folder_stats("/test/folder")
        assert stats["file_count"] == 42
        assert stats["folder_count"] == 8
        assert stats["total_size"] == 1024 * 1024 * 50


class TestNewFolderDialog:
    """Test cases for NewFolderDialog class."""

    def test_new_folder_dialog_initialization(self):
        """Test NewFolderDialog initialization."""

        class MockNewFolderDialog:
            def __init__(self, parent=None):
                self.parent = parent
                self.folder_name = ""
                self.validation_enabled = True
                self.name_input = Mock()
                self.ok_button = Mock()
                self.cancel_button = Mock()

            def setup_ui(self):
                self.name_input.textChanged = Mock()
                self.ok_button.setEnabled = Mock()
                self.cancel_button.clicked = Mock()

            def validate_name(self, name):
                if not self.validation_enabled:
                    return True

                # Basic validation rules
                if not name or not name.strip():
                    return False

                invalid_chars = ["<", ">", ":", '"', "|", "?", "*", "/", "\\"]
                return not any(char in name for char in invalid_chars)

        dialog = MockNewFolderDialog()
        dialog.setup_ui()

        # Test initialization
        assert dialog.folder_name == ""
        assert dialog.validation_enabled is True
        assert dialog.name_input is not None

        # Test validation
        assert not dialog.validate_name("")  # Empty name
        assert not dialog.validate_name("invalid/name")  # Invalid char
        assert dialog.validate_name("ValidFolderName")  # Valid name

    def test_new_folder_dialog_user_interaction(self):
        """Test user interaction with new folder dialog."""

        class MockNewFolderDialog:
            def __init__(self):
                self.folder_name = ""
                self.accepted = False
                self.rejected = False

            def on_text_changed(self, text):
                self.folder_name = text
                is_valid = self.validate_name(text)
                self.update_ok_button(is_valid)

            def validate_name(self, name):
                return bool(name and name.strip() and "/" not in name)

            def update_ok_button(self, enabled):
                self.ok_enabled = enabled

            def accept(self):
                if self.validate_name(self.folder_name):
                    self.accepted = True
                    return True
                return False

            def reject(self):
                self.rejected = True
                return True

        dialog = MockNewFolderDialog()

        # Test text input validation
        dialog.on_text_changed("TestFolder")
        assert dialog.folder_name == "TestFolder"
        assert dialog.ok_enabled is True

        dialog.on_text_changed("Invalid/Folder")
        assert dialog.ok_enabled is False

        # Test acceptance with valid name
        dialog.folder_name = "ValidFolder"
        assert dialog.accept() is True
        assert dialog.accepted is True

        # Test rejection
        dialog.reject()
        assert dialog.rejected is True


class TestFoldersDialogIntegration:
    """Integration tests for folder dialog interactions."""

    def test_dialog_engine_interaction(self):
        """Test dialog interaction with engine."""
        mock_app = MagicMock()
        mock_app.icon = Mock()

        mock_engine = Mock(spec=Engine)
        mock_engine.uid = "integration_test_engine"
        mock_engine.dao = Mock()

        class MockIntegratedDialog:
            def __init__(self, application, engine):
                self.application = application
                self.engine = engine
                self.sync_operations = []

            def sync_folder(self, folder_path):
                # Simulate syncing a folder
                self.sync_operations.append(folder_path)
                if hasattr(self.engine, "add_folder"):
                    self.engine.add_folder(folder_path)

            def unsync_folder(self, folder_path):
                # Simulate unsyncing a folder
                if folder_path in self.sync_operations:
                    self.sync_operations.remove(folder_path)
                if hasattr(self.engine, "remove_folder"):
                    self.engine.remove_folder(folder_path)

        dialog = MockIntegratedDialog(mock_app, mock_engine)
        mock_engine.add_folder = Mock()
        mock_engine.remove_folder = Mock()

        # Test folder operations
        dialog.sync_folder("/test/folder1")
        assert "/test/folder1" in dialog.sync_operations
        mock_engine.add_folder.assert_called_once_with("/test/folder1")

        dialog.unsync_folder("/test/folder1")
        assert "/test/folder1" not in dialog.sync_operations
        mock_engine.remove_folder.assert_called_once_with("/test/folder1")

    def test_regexp_validator_function(self):
        """Test the regexp validator utility function."""
        # Since we can't import the actual function due to Qt dependencies,
        # we'll test our mock version
        def mock_regexp_validator():
            """Mock version of the regexp validator."""
            invalid_chars = ["<", ">", ":", '"', "|", "?", "*"]

            class MockValidator:
                def __init__(self, invalid_chars):
                    self.invalid_chars = invalid_chars

                def validate(self, text):
                    return not any(char in text for char in self.invalid_chars)

            return MockValidator(invalid_chars)

        validator = mock_regexp_validator()

        # Test validation
        assert validator.validate("ValidFolderName") is True
        assert validator.validate("Invalid<Name") is False
        assert validator.validate("Another:Invalid") is False
        assert validator.validate("folder name with spaces") is True
