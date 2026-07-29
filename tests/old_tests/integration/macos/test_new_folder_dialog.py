"""Integration tests for NewFolderDialog class - macOS only."""

from unittest.mock import Mock

from ...markers import mac_only


@mac_only
def test_new_folder_dialog_init():
    """Test NewFolderDialog.__init__ method."""

    class MockEngine:
        def __init__(self):
            self.directTransferNewFolderSuccess = MockSignal()
            self.directTransferNewFolderError = MockSignal()

    class MockSignal:
        def __init__(self):
            self.connected_slots = []

        def connect(self, slot):
            self.connected_slots.append(slot)

    class MockNewFolderDialog:
        def __init__(self, engine, parent_path):
            self.engine = engine
            self.parent_path = parent_path
            self.created_remote_path = None
            self.folder_tree_view = Mock()

            # Connect signals
            self.engine.directTransferNewFolderSuccess.connect(
                self.handle_creation_success
            )
            self.engine.directTransferNewFolderError.connect(
                self.handle_creation_failure
            )

        def handle_creation_success(self, remote_path):
            pass

        def handle_creation_failure(self, error):
            pass

    mock_engine = MockEngine()
    dialog = MockNewFolderDialog(mock_engine, "/parent/path")

    # Verify initialization
    assert dialog.engine is mock_engine
    assert dialog.parent_path == "/parent/path"
    assert dialog.created_remote_path is None
    assert len(mock_engine.directTransferNewFolderSuccess.connected_slots) == 1
    assert len(mock_engine.directTransferNewFolderError.connected_slots) == 1


@mac_only
def test_new_folder_dialog_close_event_with_success():
    """Test NewFolderDialog.closeEvent when folder was created successfully."""

    class MockNewFolderDialog:
        def __init__(self):
            self.created_remote_path = "/remote/new_folder"
            self.close_success_called = False

        def closeEvent(self, event):
            if self.created_remote_path:
                self.close_success()

        def close_success(self):
            self.close_success_called = True

    dialog = MockNewFolderDialog()
    mock_event = Mock()

    dialog.closeEvent(mock_event)

    # Verify close_success was called
    assert dialog.close_success_called is True


@mac_only
def test_new_folder_dialog_close_event_without_success():
    """Test NewFolderDialog.closeEvent when no folder was created."""

    class MockNewFolderDialog:
        def __init__(self):
            self.created_remote_path = None
            self.close_success_called = False

        def closeEvent(self, event):
            if self.created_remote_path:
                self.close_success()

        def close_success(self):
            self.close_success_called = True

    dialog = MockNewFolderDialog()
    mock_event = Mock()

    dialog.closeEvent(mock_event)

    # Verify close_success was NOT called
    assert dialog.close_success_called is False


@mac_only
def test_new_folder_dialog_accept_creates_folder():
    """Test NewFolderDialog.accept creates folder via engine."""

    class MockEngine:
        def __init__(self):
            self.direct_transfer_async_called = False
            self.folder_name = None
            self.folder_type = None
            self.parent_path = None

        def direct_transfer_async(self, folder_name, folder_type, parent_path):
            self.direct_transfer_async_called = True
            self.folder_name = folder_name
            self.folder_type = folder_type
            self.parent_path = parent_path

    class MockNewFolderDialog:
        def __init__(self, engine):
            self.engine = engine
            self.parent_path = "/parent/path"
            self.folder_name_input = Mock()
            self.folder_name_input.text.return_value = "New Folder"
            self.folder_type_combo = Mock()
            self.folder_type_combo.currentText.return_value = "Folder"

        def accept(self):
            folder_name = self.folder_name_input.text()
            folder_type = self.folder_type_combo.currentText()
            self.engine.direct_transfer_async(
                folder_name, folder_type, self.parent_path
            )

    mock_engine = MockEngine()
    dialog = MockNewFolderDialog(mock_engine)

    dialog.accept()

    # Verify folder creation was initiated
    assert mock_engine.direct_transfer_async_called is True
    assert mock_engine.folder_name == "New Folder"
    assert mock_engine.folder_type == "Folder"
    assert mock_engine.parent_path == "/parent/path"


@mac_only
def test_new_folder_dialog_accept_checks_duplicates():
    """Test NewFolderDialog.accept checks for duplicate folder names."""

    class MockEngine:
        def __init__(self):
            self.direct_transfer_async_called = False

    class MockNewFolderDialog:
        def __init__(self, engine):
            self.engine = engine
            self.parent_path = "/parent/path"
            self.folder_name_input = Mock()
            self.folder_name_input.text.return_value = "Existing Folder"
            self.existing_folders = ["Existing Folder", "Another Folder"]
            self.error_shown = False

        def accept(self):
            folder_name = self.folder_name_input.text()

            # Check for duplicates
            if folder_name in self.existing_folders:
                self.error_shown = True
                return

            self.engine.direct_transfer_async(folder_name, "Folder", self.parent_path)

    mock_engine = MockEngine()
    dialog = MockNewFolderDialog(mock_engine)

    dialog.accept()

    # Verify duplicate was detected
    assert dialog.error_shown is True
    assert mock_engine.direct_transfer_async_called is False


@mac_only
def test_new_folder_dialog_button_ok_state_enabled():
    """Test NewFolderDialog._button_ok_state enables button when valid."""

    class MockNewFolderDialog:
        def __init__(self):
            self.ok_button = Mock()
            self.folder_name_input = Mock()
            self.folder_name_input.text.return_value = "Valid Name"

        def _button_ok_state(self):
            folder_name = self.folder_name_input.text().strip()
            self.ok_button.setEnabled(bool(folder_name))

    dialog = MockNewFolderDialog()

    dialog._button_ok_state()

    # Verify button was enabled
    dialog.ok_button.setEnabled.assert_called_once_with(True)


@mac_only
def test_new_folder_dialog_button_ok_state_disabled():
    """Test NewFolderDialog._button_ok_state disables button when invalid."""

    class MockNewFolderDialog:
        def __init__(self):
            self.ok_button = Mock()
            self.folder_name_input = Mock()
            self.folder_name_input.text.return_value = ""

        def _button_ok_state(self):
            folder_name = self.folder_name_input.text().strip()
            self.ok_button.setEnabled(bool(folder_name))

    dialog = MockNewFolderDialog()

    dialog._button_ok_state()

    # Verify button was disabled
    dialog.ok_button.setEnabled.assert_called_once_with(False)


@mac_only
def test_new_folder_dialog_show_result_message_show():
    """Test NewFolderDialog._show_result_message shows result frame."""

    class MockNewFolderDialog:
        def __init__(self):
            self.creation_frame = Mock()
            self.result_frame = Mock()

        def _show_result_message(self, show):
            self.creation_frame.setVisible(not show)
            self.result_frame.setVisible(show)

    dialog = MockNewFolderDialog()

    dialog._show_result_message(True)

    # Verify frames visibility
    dialog.creation_frame.setVisible.assert_called_once_with(False)
    dialog.result_frame.setVisible.assert_called_once_with(True)


@mac_only
def test_new_folder_dialog_show_result_message_hide():
    """Test NewFolderDialog._show_result_message hides result frame."""

    class MockNewFolderDialog:
        def __init__(self):
            self.creation_frame = Mock()
            self.result_frame = Mock()

        def _show_result_message(self, show):
            self.creation_frame.setVisible(not show)
            self.result_frame.setVisible(show)

    dialog = MockNewFolderDialog()

    dialog._show_result_message(False)

    # Verify frames visibility
    dialog.creation_frame.setVisible.assert_called_once_with(True)
    dialog.result_frame.setVisible.assert_called_once_with(False)


@mac_only
def test_new_folder_dialog_handle_creation_success():
    """Test NewFolderDialog.handle_creation_success updates state."""

    class MockNewFolderDialog:
        def __init__(self):
            self.created_remote_path = None
            self.result_message = Mock()
            self.show_result_called = False

        def handle_creation_success(self, remote_path):
            self.created_remote_path = remote_path
            self.result_message.setText("Folder created successfully!")
            self._show_result_message(True)

        def _show_result_message(self, show):
            self.show_result_called = show

    dialog = MockNewFolderDialog()

    dialog.handle_creation_success("/remote/new_folder")

    # Verify success was handled
    assert dialog.created_remote_path == "/remote/new_folder"
    dialog.result_message.setText.assert_called_once_with(
        "Folder created successfully!"
    )
    assert dialog.show_result_called is True


@mac_only
def test_new_folder_dialog_handle_creation_failure():
    """Test NewFolderDialog.handle_creation_failure displays error."""

    class MockNewFolderDialog:
        def __init__(self):
            self.result_message = Mock()
            self.show_result_called = False

        def handle_creation_failure(self, error):
            self.result_message.setText(f"Error: {error}")
            self._show_result_message(True)

        def _show_result_message(self, show):
            self.show_result_called = show

    dialog = MockNewFolderDialog()

    dialog.handle_creation_failure("Permission denied")

    # Verify error was handled
    dialog.result_message.setText.assert_called_once_with("Error: Permission denied")
    assert dialog.show_result_called is True


@mac_only
def test_new_folder_dialog_close_success_selects_item():
    """Test NewFolderDialog.close_success selects created folder."""

    class MockNewFolderDialog:
        def __init__(self):
            self.created_remote_path = "/remote/new_folder"
            self.folder_tree_view = Mock()

        def close_success(self):
            if self.created_remote_path:
                self.folder_tree_view.select_and_expand(self.created_remote_path)

    dialog = MockNewFolderDialog()

    dialog.close_success()

    # Verify folder was selected
    dialog.folder_tree_view.select_and_expand.assert_called_once_with(
        "/remote/new_folder"
    )


@mac_only
def test_new_folder_dialog_close_success_no_path():
    """Test NewFolderDialog.close_success when no folder was created."""

    class MockNewFolderDialog:
        def __init__(self):
            self.created_remote_path = None
            self.folder_tree_view = Mock()

        def close_success(self):
            if self.created_remote_path:
                self.folder_tree_view.select_and_expand(self.created_remote_path)

    dialog = MockNewFolderDialog()

    dialog.close_success()

    # Verify folder selection was NOT attempted
    dialog.folder_tree_view.select_and_expand.assert_not_called()


@mac_only
def test_new_folder_dialog_add_folder_creation_layout():
    """Test NewFolderDialog._add_folder_creation_layout creates widgets."""

    class MockNewFolderDialog:
        def __init__(self):
            self.layout = Mock()
            self.folder_name_input = None
            self.folder_type_combo = None

        def _add_folder_creation_layout(self):
            # Mock widget creation
            self.folder_name_input = Mock()
            self.folder_type_combo = Mock()

            # Mock adding to layout
            self.layout.addWidget(self.folder_name_input)
            self.layout.addWidget(self.folder_type_combo)

    dialog = MockNewFolderDialog()

    dialog._add_folder_creation_layout()

    # Verify widgets were created
    assert dialog.folder_name_input is not None
    assert dialog.folder_type_combo is not None
    assert dialog.layout.addWidget.call_count == 2


@mac_only
def test_new_folder_dialog_add_operation_result_layout():
    """Test NewFolderDialog._add_operation_result_layout creates result widgets."""

    class MockNewFolderDialog:
        def __init__(self):
            self.layout = Mock()
            self.result_message = None

        def _add_operation_result_layout(self):
            # Mock widget creation
            self.result_message = Mock()

            # Mock adding to layout
            self.layout.addWidget(self.result_message)

    dialog = MockNewFolderDialog()

    dialog._add_operation_result_layout()

    # Verify widgets were created
    assert dialog.result_message is not None
    dialog.layout.addWidget.assert_called_once()


@mac_only
def test_new_folder_dialog_folder_name_validation():
    """Test NewFolderDialog validates folder names."""

    class MockNewFolderDialog:
        def __init__(self):
            self.ok_button = Mock()
            self.folder_name_input = Mock()

        def _button_ok_state(self):
            folder_name = self.folder_name_input.text().strip()
            self.ok_button.setEnabled(bool(folder_name))

    dialog = MockNewFolderDialog()

    # Test with whitespace-only name
    dialog.folder_name_input.text.return_value = "   "
    dialog._button_ok_state()
    dialog.ok_button.setEnabled.assert_called_with(False)

    # Test with valid name
    dialog.folder_name_input.text.return_value = "Valid Name"
    dialog._button_ok_state()
    dialog.ok_button.setEnabled.assert_called_with(True)


@mac_only
def test_new_folder_dialog_full_lifecycle():
    """Test NewFolderDialog full lifecycle from creation to close."""

    class MockEngine:
        def __init__(self):
            self.directTransferNewFolderSuccess = MockSignal()
            self.direct_transfer_calls = []

        def direct_transfer_async(self, folder_name, folder_type, parent_path):
            self.direct_transfer_calls.append((folder_name, folder_type, parent_path))

    class MockSignal:
        def __init__(self):
            self.connected_slots = []

        def connect(self, slot):
            self.connected_slots.append(slot)

        def emit(self, *args):
            for slot in self.connected_slots:
                slot(*args)

    class MockNewFolderDialog:
        def __init__(self, engine, parent_path):
            self.engine = engine
            self.parent_path = parent_path
            self.created_remote_path = None
            self.folder_tree_view = Mock()
            self.folder_name_input = Mock()
            self.folder_name_input.text.return_value = "Test Folder"
            self.folder_type_combo = Mock()
            self.folder_type_combo.currentText.return_value = "Folder"

            self.engine.directTransferNewFolderSuccess.connect(
                self.handle_creation_success
            )

        def accept(self):
            folder_name = self.folder_name_input.text()
            folder_type = self.folder_type_combo.currentText()
            self.engine.direct_transfer_async(
                folder_name, folder_type, self.parent_path
            )

        def handle_creation_success(self, remote_path):
            self.created_remote_path = remote_path

        def closeEvent(self, event):
            if self.created_remote_path:
                self.close_success()

        def close_success(self):
            self.folder_tree_view.select_and_expand(self.created_remote_path)

    mock_engine = MockEngine()
    dialog = MockNewFolderDialog(mock_engine, "/parent/path")

    # Simulate user accepting dialog
    dialog.accept()

    # Verify folder creation was initiated
    assert len(mock_engine.direct_transfer_calls) == 1
    assert mock_engine.direct_transfer_calls[0] == (
        "Test Folder",
        "Folder",
        "/parent/path",
    )

    # Simulate successful creation
    mock_engine.directTransferNewFolderSuccess.emit("/remote/test_folder")

    # Verify success was handled
    assert dialog.created_remote_path == "/remote/test_folder"

    # Simulate closing dialog
    mock_event = Mock()
    dialog.closeEvent(mock_event)

    # Verify folder was selected in tree view
    dialog.folder_tree_view.select_and_expand.assert_called_once_with(
        "/remote/test_folder"
    )
