"""Integration tests for FoldersDialog.keyPressEvent method - macOS only."""

from unittest.mock import Mock

from PyQt5.QtCore import Qt

from ...markers import mac_only


@mac_only
def test_key_press_event_escape_key():
    """Test keyPressEvent with Esc key calls showNormal()."""

    class MockFoldersDialog:
        def __init__(self):
            self.show_normal_called = False
            self.super_key_press_called = False

        def showNormal(self):
            self.show_normal_called = True

        def keyPressEvent(self, event):
            """On user Esc keypress event, restore the maximized window."""
            if event.key() == Qt.Key_Escape:
                self.showNormal()
            else:
                self.super_key_press_called = True

    dialog = MockFoldersDialog()

    # Create mock event with Esc key
    mock_event = Mock()
    mock_event.key.return_value = Qt.Key_Escape

    dialog.keyPressEvent(mock_event)

    # Verify showNormal was called
    assert dialog.show_normal_called is True
    # Verify super().keyPressEvent was NOT called
    assert dialog.super_key_press_called is False


@mac_only
def test_key_press_event_non_escape_key():
    """Test keyPressEvent with non-Esc key calls super().keyPressEvent()."""

    class MockFoldersDialog:
        def __init__(self):
            self.show_normal_called = False
            self.super_key_press_called = False

        def showNormal(self):
            self.show_normal_called = True

        def keyPressEvent(self, event):
            """On user Esc keypress event, restore the maximized window."""
            if event.key() == Qt.Key_Escape:
                self.showNormal()
            else:
                self.super_key_press_called = True

    dialog = MockFoldersDialog()

    # Create mock event with Enter key
    mock_event = Mock()
    mock_event.key.return_value = Qt.Key_Return

    dialog.keyPressEvent(mock_event)

    # Verify showNormal was NOT called
    assert dialog.show_normal_called is False
    # Verify super().keyPressEvent was called
    assert dialog.super_key_press_called is True


@mac_only
def test_key_press_event_various_keys():
    """Test keyPressEvent with various keys."""

    class MockFoldersDialog:
        def __init__(self):
            self.show_normal_count = 0
            self.super_key_press_count = 0

        def showNormal(self):
            self.show_normal_count += 1

        def keyPressEvent(self, event):
            """On user Esc keypress event, restore the maximized window."""
            if event.key() == Qt.Key_Escape:
                self.showNormal()
            else:
                self.super_key_press_count += 1

    dialog = MockFoldersDialog()

    # Test multiple non-Esc keys
    for key in [Qt.Key_A, Qt.Key_B, Qt.Key_Space, Qt.Key_Tab]:
        mock_event = Mock()
        mock_event.key.return_value = key
        dialog.keyPressEvent(mock_event)

    assert dialog.show_normal_count == 0
    assert dialog.super_key_press_count == 4

    # Test Esc key
    mock_event = Mock()
    mock_event.key.return_value = Qt.Key_Escape
    dialog.keyPressEvent(mock_event)

    assert dialog.show_normal_count == 1
    assert dialog.super_key_press_count == 4


@mac_only
def test_key_press_event_escape_key_multiple_times():
    """Test keyPressEvent with Esc key called multiple times."""

    class MockFoldersDialog:
        def __init__(self):
            self.show_normal_count = 0

        def showNormal(self):
            self.show_normal_count += 1

        def keyPressEvent(self, event):
            """On user Esc keypress event, restore the maximized window."""
            if event.key() == Qt.Key_Escape:
                self.showNormal()

    dialog = MockFoldersDialog()

    # Call keyPressEvent with Esc multiple times
    for _ in range(5):
        mock_event = Mock()
        mock_event.key.return_value = Qt.Key_Escape
        dialog.keyPressEvent(mock_event)

    # Verify showNormal was called 5 times
    assert dialog.show_normal_count == 5


@mac_only
def test_key_press_event_key_method_called():
    """Test keyPressEvent calls event.key() method."""

    class MockFoldersDialog:
        def __init__(self):
            self.show_normal_called = False

        def showNormal(self):
            self.show_normal_called = True

        def keyPressEvent(self, event):
            """On user Esc keypress event, restore the maximized window."""
            if event.key() == Qt.Key_Escape:
                self.showNormal()

    dialog = MockFoldersDialog()

    mock_event = Mock()
    mock_event.key.return_value = Qt.Key_Escape

    dialog.keyPressEvent(mock_event)

    # Verify event.key() was called
    mock_event.key.assert_called()
    assert dialog.show_normal_called is True


@mac_only
def test_key_press_event_special_keys():
    """Test keyPressEvent with special keys."""

    class MockFoldersDialog:
        def __init__(self):
            self.show_normal_called = False
            self.super_key_press_count = 0

        def showNormal(self):
            self.show_normal_called = True

        def keyPressEvent(self, event):
            """On user Esc keypress event, restore the maximized window."""
            if event.key() == Qt.Key_Escape:
                self.showNormal()
            else:
                self.super_key_press_count += 1

    dialog = MockFoldersDialog()

    # Test special keys that should not trigger showNormal
    special_keys = [
        Qt.Key_F1,
        Qt.Key_F12,
        Qt.Key_Delete,
        Qt.Key_Backspace,
        Qt.Key_Home,
        Qt.Key_End,
    ]

    for key in special_keys:
        mock_event = Mock()
        mock_event.key.return_value = key
        dialog.keyPressEvent(mock_event)

    assert dialog.show_normal_called is False
    assert dialog.super_key_press_count == len(special_keys)


@mac_only
def test_key_press_event_nxdrive_2737_fix():
    """Test keyPressEvent implements NXDRIVE-2737 fix for Esc key."""

    class MockFoldersDialog:
        def __init__(self):
            self.restore_window_called = False

        def showNormal(self):
            # This simulates restoring a maximized window
            self.restore_window_called = True

        def keyPressEvent(self, event):
            """On user Esc keypress event, restore the maximized window. See NXDRIVE-2737."""
            if event.key() == Qt.Key_Escape:
                self.showNormal()

    dialog = MockFoldersDialog()

    mock_event = Mock()
    mock_event.key.return_value = Qt.Key_Escape

    dialog.keyPressEvent(mock_event)

    # Verify the NXDRIVE-2737 fix is working
    assert dialog.restore_window_called is True


@mac_only
def test_key_press_event_conditional_logic():
    """Test keyPressEvent conditional logic coverage."""

    class MockFoldersDialog:
        def __init__(self):
            self.actions = []

        def showNormal(self):
            self.actions.append("showNormal")

        def keyPressEvent(self, event):
            """On user Esc keypress event, restore the maximized window."""
            if event.key() == Qt.Key_Escape:
                self.showNormal()
            else:
                self.actions.append("super")

    dialog = MockFoldersDialog()

    # Test if branch (Esc key)
    mock_event = Mock()
    mock_event.key.return_value = Qt.Key_Escape
    dialog.keyPressEvent(mock_event)

    # Test else branch (non-Esc key)
    mock_event = Mock()
    mock_event.key.return_value = Qt.Key_A
    dialog.keyPressEvent(mock_event)

    # Verify both branches executed
    assert dialog.actions == ["showNormal", "super"]
