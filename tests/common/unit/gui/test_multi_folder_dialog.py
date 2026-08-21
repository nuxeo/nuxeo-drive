"""Deterministic unit tests for the multi-folder selection dialog."""

import ctypes as stdlib_ctypes
import plistlib
import struct
import subprocess as stdlib_subprocess
from pathlib import Path as RealPath
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

from nxdrive.drive.gui import multi_folder_dialog as dialog_module
from nxdrive.drive.qt.imports import (
    QCoreApplication,
    QDialog,
    QDialogButtonBox,
    QDir,
    QEvent,
    QFileSystemModel,
    QIcon,
    QItemSelectionModel,
    QKeyEvent,
    QListWidget,
    QListWidgetItem,
    QSize,
    QStandardItemModel,
    Qt,
)

TRANSLATIONS = {
    "ADD": "Add",
    "CANCEL": "Cancel",
    "FDA_POPUP_CHECKBOX_LABEL": "Do not show again",
    "FDA_POPUP_MESSAGE_PART_1": "First clause",
    "FDA_POPUP_MESSAGE_PART_2": "Second clause",
    "FDA_POPUP_MESSAGE_PART_3": "Third clause",
    "FDA_POPUP_NOT_NOW": "Not now",
    "FDA_POPUP_SYSTEM_SETTINGS": "System Settings",
    "FDA_POPUP_WARNING_LABEL": "Permission required",
    "SELECT_FILES_FOLDERS": "Select files and folders",
    "SELECT_FILES_FOLDERS_LABEL": "Choose one or more folders",
    "SHOW_HIDDEN": "Show hidden files",
}


def _path_api(home: RealPath):
    """Return a module-local Path facade with a controlled home directory."""

    class TestPath:
        def __new__(cls, *args, **kwargs):
            return RealPath(*args, **kwargs)

        @staticmethod
        def home():
            return home

    return TestPath


def _set_platform(monkeypatch, platform):
    monkeypatch.setattr(dialog_module, "MAC", platform == "mac")
    monkeypatch.setattr(dialog_module, "WINDOWS", platform == "windows")
    monkeypatch.setattr(dialog_module, "LINUX", platform == "linux")


@pytest.fixture(autouse=True)
def deterministic_environment(monkeypatch, tmp_path):
    """Keep every platform and filesystem boundary inside the test directory."""
    home = tmp_path / "home"
    home.mkdir()
    resources = tmp_path / "resources"
    styles = resources / "styles"
    styles.mkdir(parents=True)
    (styles / "multi_folder_dialog_light.qss").write_text(
        "QDialog { color: #111111; }", encoding="utf-8"
    )
    (styles / "multi_folder_dialog_dark.qss").write_text(
        "QDialog { color: #eeeeee; }", encoding="utf-8"
    )

    path_api = _path_api(home)

    class TestQDir:
        Filter = QDir.Filter

        @staticmethod
        def homePath():
            return str(home)

    translator_get = Mock(side_effect=lambda key, **kwargs: TRANSLATIONS.get(key, key))
    option_store = type(dialog_module.Options).options
    original_resources_option = option_store["res_dir"]
    monkeypatch.setattr(dialog_module.Translator, "get", staticmethod(translator_get))
    # Options uses a metaclass-backed dynamic attribute.  Preserve the whole
    # (value, setter) tuple so this test cannot leak option provenance.
    option_store["res_dir"] = (resources, "test")
    monkeypatch.setattr(dialog_module, "Path", path_api)
    monkeypatch.setattr(dialog_module, "QDir", TestQDir)
    monkeypatch.setattr(
        dialog_module, "find_icon", lambda name: resources / "icons" / name
    )
    _set_platform(monkeypatch, "none")
    dialog_module.FDAAlert.visible = False

    try:
        yield SimpleNamespace(
            home=home,
            resources=resources,
            styles=styles,
            path_api=path_api,
            translator_get=translator_get,
        )
    finally:
        option_store["res_dir"] = original_resources_option
        dialog_module.FDAAlert.visible = False


@pytest.fixture
def keep_object(qapp):
    """Track Qt objects and reliably process their deferred deletion."""
    objects = []

    def keep(obj):
        objects.append(obj)
        return obj

    yield keep

    for obj in reversed(objects):
        close = getattr(obj, "close", None)
        if close is not None:
            close()
        obj.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


@pytest.fixture
def dialog(keep_object):
    """Create a neutral-platform dialog backed by the shared QApplication."""
    return keep_object(dialog_module.MultiFolderDialog())


def _set_path_without_signal(dialog, value):
    dialog.path_bar.blockSignals(True)
    dialog.path_bar.setText(str(value))
    dialog.path_bar.blockSignals(False)


def _location_item(location, *, display=None, user_role=True):
    item = QListWidgetItem(display if display is not None else location)
    if user_role:
        item.setData(Qt.ItemDataRole.UserRole, location)
    return item


def _panel_texts(panel):
    return [panel.item(row).text() for row in range(panel.count())]


# ---------------------------------------------------------------------------
# Model and FDA alert
# ---------------------------------------------------------------------------


def test_centered_header_model_centers_only_alignment_role(qapp, keep_object):
    model = keep_object(dialog_module.CenteredHeaderFileSystemModel())

    assert (
        model.headerData(
            0,
            Qt.Orientation.Horizontal,
            Qt.ItemDataRole.TextAlignmentRole,
        )
        == Qt.AlignmentFlag.AlignCenter
    )
    assert (
        model.headerData(0, Qt.Orientation.Horizontal) != Qt.AlignmentFlag.AlignCenter
    )


def test_fda_alert_constructor_builds_expected_controls(keep_object):
    alert = keep_object(dialog_module.FDAAlert())

    assert alert.objectName() == "fdaAlertDialog"
    assert alert.size() == QSize(570, 225)
    assert alert.ok_button.text() == "System Settings"
    assert alert.not_now_button.text() == "Not now"
    assert alert.dont_show_checkbox.text() == "Do not show again"
    assert alert.ok_button.objectName() == "fda_popup_ok_button"
    assert alert.not_now_button.objectName() == "fda_popup_dont_show_again_button"
    assert alert.dont_show_checkbox.objectName() == "fda_popup_dont_show_checkbox"
    message = alert.findChild(dialog_module.QLabel, "fda_popup_message")
    assert message is not None
    assert message.text() == ("First clause<br><br>Second clause<br><br>Third clause")


def test_fda_alert_logs_when_style_is_unavailable(keep_object, monkeypatch):
    class NoStyleFDAAlert(dialog_module.FDAAlert):
        def style(self):
            return None

    log = Mock()
    monkeypatch.setattr(dialog_module, "log", log)
    alert = keep_object(NoStyleFDAAlert())

    assert alert.ok_button is not None
    log.warning.assert_called_once_with(
        "Failed to load fda popup warning icon from style"
    )


def test_fda_alert_buttons_close_and_open_settings(keep_object, monkeypatch):
    navigate = Mock()
    monkeypatch.setattr(
        dialog_module.MultiFolderDialog,
        "navigate_to_system_settings",
        staticmethod(navigate),
    )
    alert = keep_object(dialog_module.FDAAlert())
    dialog_module.FDAAlert.visible = True

    alert.ok_button.click()

    navigate.assert_called_once()
    assert dialog_module.FDAAlert.visible is False
    assert not alert.isVisible()

    second = keep_object(dialog_module.FDAAlert())
    dialog_module.FDAAlert.visible = True
    second.not_now_button.click()
    assert dialog_module.FDAAlert.visible is False


def test_fda_alert_accept_toggles_only_focused_checkbox():
    checkbox = Mock()
    checkbox.hasFocus.return_value = True
    host = SimpleNamespace(dont_show_checkbox=checkbox)

    dialog_module.FDAAlert.accept(host)
    checkbox.toggle.assert_called_once_with()

    checkbox.reset_mock()
    checkbox.hasFocus.return_value = False
    dialog_module.FDAAlert.accept(host)
    checkbox.toggle.assert_not_called()


def test_fda_alert_reject_and_close_alert_clear_visible(keep_object):
    alert = keep_object(dialog_module.FDAAlert())
    dialog_module.FDAAlert.visible = True

    alert.reject()

    assert dialog_module.FDAAlert.visible is False
    assert alert.result() == QDialog.DialogCode.Rejected.value

    dialog_module.FDAAlert.visible = True
    alert.close_alert()
    assert dialog_module.FDAAlert.visible is False


def test_fda_alert_key_events_dispatch_without_side_effects(keep_object):
    class RecordingAlert(dialog_module.FDAAlert):
        def __init__(self):
            super().__init__()
            self.accept_count = 0
            self.reject_count = 0

        def accept(self):
            self.accept_count += 1

        def reject(self):
            self.reject_count += 1

    alert = keep_object(RecordingAlert())
    no_modifiers = Qt.KeyboardModifier.NoModifier

    alert.keyPressEvent(None)
    alert.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, no_modifiers)
    )
    alert.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, no_modifiers)
    )
    alert.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Enter, no_modifiers))
    alert.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, no_modifiers))

    assert alert.reject_count == 1
    assert alert.accept_count == 2


def test_remember_close_choice_creates_and_removes_private_marker(
    keep_object, deterministic_environment
):
    alert = keep_object(dialog_module.FDAAlert())
    marker = deterministic_environment.home / ".nuxeo-drive" / "dont_show_fda_alert"

    alert.remember_close_choice(Qt.CheckState.Checked)
    assert marker.is_file()

    alert.remember_close_choice(Qt.CheckState.Checked)
    assert marker.is_file()

    alert.remember_close_choice(Qt.CheckState.Unchecked)
    assert not marker.exists()


# ---------------------------------------------------------------------------
# Constructor, theme switching, and core navigation
# ---------------------------------------------------------------------------


def test_constructor_builds_light_dialog(dialog, deterministic_environment):
    assert dialog.windowTitle() == "Select files and folders"
    assert dialog.styleSheet() == "QDialog { color: #111111; }"
    assert dialog.minimumWidth() == 700
    assert dialog.minimumHeight() == 450
    assert dialog.path_bar.text() == str(deterministic_environment.home)
    assert dialog.showHidden.text() == "Show hidden files"
    assert not dialog.showHidden.isChecked()
    assert isinstance(dialog.model, QFileSystemModel)
    assert dialog.tree.model() is dialog.model
    assert (
        dialog.tree.selectionMode()
        == dialog_module.QTreeView.SelectionMode.ExtendedSelection
    )
    assert not dialog.tree.isHeaderHidden()
    assert dialog.fda_alert_widget.isHidden()
    assert dialog.fda_alert_button.text() == "FDA_SETTINGS_BUTTON_TEXT"

    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None
    ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
    cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
    assert ok_button is not None and ok_button.text() == "Add"
    assert cancel_button is not None and cancel_button.text() == "Cancel"


def test_constructor_loads_dark_qss_and_connects_theme_signal(
    keep_object, deterministic_environment
):
    signal = Mock()

    dialog = keep_object(
        dialog_module.MultiFolderDialog(dark_mode=True, dark_mode_signal=signal)
    )

    assert dialog._dark_mode is True
    assert dialog.styleSheet() == "QDialog { color: #eeeeee; }"
    signal.connect.assert_called_once_with(dialog._on_dark_mode_changed)


def test_constructor_missing_qss_and_missing_style_are_safe(
    keep_object, deterministic_environment, monkeypatch
):
    class NoStyleMultiFolderDialog(dialog_module.MultiFolderDialog):
        def style(self):
            return None

    (deterministic_environment.styles / "multi_folder_dialog_light.qss").unlink()
    log = Mock()
    monkeypatch.setattr(dialog_module, "log", log)

    dialog = keep_object(NoStyleMultiFolderDialog())

    assert dialog.styleSheet() == ""
    assert log.warning.call_args_list == [
        call(
            "QSS stylesheet not found at %s",
            deterministic_environment.styles / "multi_folder_dialog_light.qss",
        ),
        call("Failed to load warning icon from style"),
    ]


def test_dark_mode_change_reloads_qss_icons_and_panel(
    dialog, deterministic_environment, monkeypatch
):
    icon = QIcon()
    fetch_icon = Mock(return_value=icon)
    replacement = QListWidget()
    panel_locations = Mock(return_value=replacement)
    monkeypatch.setattr(dialog, "fetch_icon", fetch_icon)
    monkeypatch.setattr(dialog, "panel_locations", panel_locations)

    dialog._on_dark_mode_changed(True)

    assert dialog._dark_mode is True
    assert dialog.styleSheet() == "QDialog { color: #eeeeee; }"
    assert fetch_icon.call_args_list[:2] == [call("Home"), call("Up Arrow")]
    panel_locations.assert_called_once_with()
    assert dialog.panel_layout.itemAt(0).widget() is replacement


def test_dark_mode_change_missing_qss_logs_and_still_rebuilds_panel(
    dialog, deterministic_environment, monkeypatch
):
    (deterministic_environment.styles / "multi_folder_dialog_dark.qss").unlink()
    replacement = QListWidget()
    monkeypatch.setattr(dialog, "panel_locations", Mock(return_value=replacement))
    log = Mock()
    monkeypatch.setattr(dialog_module, "log", log)

    dialog._on_dark_mode_changed(True)

    assert dialog.panel_layout.itemAt(0).widget() is replacement
    log.warning.assert_called_once_with(
        "QSS stylesheet not found (while switching) at %s",
        deterministic_environment.styles / "multi_folder_dialog_dark.qss",
    )


def test_selected_paths_custom_model_deduplicates_column_zero_values():
    first = Mock()
    first.column.return_value = 0
    first.data.return_value = "/one"
    duplicate = Mock()
    duplicate.column.return_value = 0
    duplicate.data.return_value = "/one"
    missing = Mock()
    missing.column.return_value = 0
    missing.data.return_value = None
    other_column = Mock()
    other_column.column.return_value = 1
    selection = Mock()
    selection.selectedIndexes.return_value = [first, duplicate, missing, other_column]
    host = SimpleNamespace(
        _using_custom_model=True,
        tree=Mock(selectionModel=Mock(return_value=selection)),
    )

    assert dialog_module.MultiFolderDialog.selected_paths(host) == ["/one"]
    first.data.assert_called_once_with(Qt.ItemDataRole.UserRole)
    other_column.data.assert_not_called()


def test_selected_paths_handles_absent_custom_selection_model():
    host = SimpleNamespace(
        _using_custom_model=True,
        tree=Mock(selectionModel=Mock(return_value=None)),
    )

    assert dialog_module.MultiFolderDialog.selected_paths(host) == []


def test_selected_paths_filesystem_model_filters_columns_and_duplicates():
    first = Mock()
    first.column.return_value = 0
    duplicate = Mock()
    duplicate.column.return_value = 0
    other_column = Mock()
    other_column.column.return_value = 2
    selection = Mock()
    selection.selectedIndexes.return_value = [first, duplicate, other_column]
    model = Mock()
    model.filePath.side_effect = ["/folder", "/folder"]
    host = SimpleNamespace(
        _using_custom_model=False,
        tree=Mock(selectionModel=Mock(return_value=selection)),
        model=model,
    )

    assert dialog_module.MultiFolderDialog.selected_paths(host) == ["/folder"]
    assert model.filePath.call_count == 2

    host.tree.selectionModel.return_value = None
    assert dialog_module.MultiFolderDialog.selected_paths(host) == []


def test_restore_filesystem_model_only_when_custom():
    filesystem_model = object()
    tree = Mock()
    host = SimpleNamespace(
        _using_custom_model=True,
        tree=tree,
        model=filesystem_model,
    )

    dialog_module.MultiFolderDialog._restore_filesystem_model(host)

    assert host._using_custom_model is False
    tree.setModel.assert_called_once_with(filesystem_model)

    tree.reset_mock()
    dialog_module.MultiFolderDialog._restore_filesystem_model(host)
    tree.setModel.assert_not_called()


def test_show_empty_drive_installs_header_only_model(dialog):
    dialog._show_empty_drive("X:\\")

    model = dialog.tree.model()
    assert isinstance(model, QStandardItemModel)
    assert model.rowCount() == 0
    assert model.columnCount() == 4
    assert model.headerData(0, Qt.Orientation.Horizontal) == "NAME"
    assert model.headerData(3, Qt.Orientation.Horizontal) == "DATE_MODIFIED"
    assert dialog._using_custom_model is True
    assert dialog.path_bar.text() == "X:\\"
    assert dialog.path_bar.styleSheet() == ""
    assert not dialog.path_bar.signalsBlocked()


def test_path_changed_switches_back_to_filesystem_and_marks_invalid_path(
    tmp_path,
):
    valid = tmp_path / "valid"
    valid.mkdir()
    model = Mock()
    tree = Mock()
    path_bar = Mock()
    path_bar.text.return_value = str(valid)
    host = SimpleNamespace(
        _using_custom_model=True,
        model=model,
        tree=tree,
        path_bar=path_bar,
    )
    host._restore_filesystem_model = lambda: (
        dialog_module.MultiFolderDialog._restore_filesystem_model(host)
    )

    # Use a mocked QFileSystemModel here. Calling setRootPath() on a live
    # model launches asynchronous OS directory watchers, which can outlive
    # the test and crash Qt during teardown on Windows CI.
    dialog_module.MultiFolderDialog.path_changed(host)

    assert host._using_custom_model is False
    tree.setModel.assert_called_once_with(model)
    model.setRootPath.assert_called_once_with(str(valid))
    tree.setRootIndex.assert_called_once_with(model.index.return_value)
    tree.resizeColumnToContents.assert_called_once_with(0)
    path_bar.setStyleSheet.assert_called_once_with("")

    model.reset_mock()
    tree.reset_mock()
    path_bar.reset_mock()
    path_bar.text.return_value = str(tmp_path / "missing")
    dialog_module.MultiFolderDialog.path_changed(host)
    model.setRootPath.assert_not_called()
    path_bar.setStyleSheet.assert_called_once_with("background-color: #ffcccc")


def test_show_hidden_files_updates_filter_and_refreshes_existing_root(tmp_path):
    current = tmp_path / "visible"
    current.mkdir()
    model = Mock()
    tree = Mock()
    path_bar = Mock()
    path_bar.text.return_value = str(current)
    show_hidden = Mock()
    show_hidden.isChecked.return_value = True
    host = SimpleNamespace(
        model=model,
        tree=tree,
        path_bar=path_bar,
        showHidden=show_hidden,
    )

    # Exercise the method without a live QFileSystemModel. Repeatedly
    # resetting a real model root can crash Qt's asynchronous Windows file
    # watcher during test teardown.
    dialog_module.MultiFolderDialog.show_hidden_files(host)
    model.setFilter.assert_called_once_with(
        QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden
    )
    model.setRootPath.assert_called_once_with(str(current))
    tree.setRootIndex.assert_called_once_with(model.index.return_value)

    model.reset_mock()
    tree.reset_mock()
    show_hidden.isChecked.return_value = False
    dialog_module.MultiFolderDialog.show_hidden_files(host)
    model.setFilter.assert_called_once_with(
        QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot
    )

    model.reset_mock()
    tree.reset_mock()
    path_bar.text.return_value = str(tmp_path / "missing")
    dialog_module.MultiFolderDialog.show_hidden_files(host)
    model.setRootPath.assert_not_called()
    tree.setRootIndex.assert_not_called()


def test_load_directory_only_navigates_for_directory_column_zero(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    file_path = tmp_path / "file.txt"
    file_path.write_text("data", encoding="utf-8")
    model = Mock()
    path_bar = Mock()
    host = SimpleNamespace(model=model, path_bar=path_bar)
    index = Mock()
    index.column.return_value = 0

    model.filePath.return_value = str(folder)
    dialog_module.MultiFolderDialog.load_directory(host, index)
    path_bar.setText.assert_called_once_with(str(folder))

    path_bar.reset_mock()
    model.filePath.return_value = str(file_path)
    dialog_module.MultiFolderDialog.load_directory(host, index)
    path_bar.setText.assert_not_called()

    index.column.return_value = 1
    dialog_module.MultiFolderDialog.load_directory(host, index)
    assert model.filePath.call_count == 2


def test_home_up_and_resize_actions(dialog, deterministic_environment, tmp_path):
    nested = tmp_path / "parent" / "child"
    nested.mkdir(parents=True)
    _set_path_without_signal(dialog, nested)

    dialog.go_up()
    assert dialog.path_bar.text() == str(nested.parent)

    _set_path_without_signal(dialog, tmp_path / "does-not-exist")
    dialog.go_up()
    assert dialog.path_bar.text() == str(tmp_path / "does-not-exist")

    dialog.go_home()
    assert dialog.path_bar.text() == str(deterministic_environment.home)

    with patch.object(dialog.tree, "resizeColumnToContents") as resize:
        dialog._resize_column_to_contents("ignored")
    resize.assert_called_once_with(0)


@pytest.mark.parametrize(
    ("location", "suffix"),
    [
        ("Home", ""),
        ("Applications", "/Applications"),
        ("Desktop", "/Desktop"),
        ("Documents", "/Documents"),
        ("Downloads", "/Downloads"),
        ("Pictures", "/Pictures"),
        ("Music", "/Music"),
        ("Movies", "/Movies"),
    ],
)
def test_navigate_to_macos_standard_locations(
    monkeypatch, deterministic_environment, location, suffix
):
    _set_platform(monkeypatch, "mac")
    host = SimpleNamespace(
        path_bar=Mock(),
        _restore_filesystem_model=Mock(),
        _finder_favorites={},
        _finder_tags=[],
        macos_mount_points=Mock(return_value={}),
        _show_tagged_files=Mock(),
    )

    dialog_module.MultiFolderDialog.navigate_to_location(
        host, _location_item(location, display="translated")
    )

    expected = (
        str(deterministic_environment.home)
        if location == "Home"
        else (
            suffix
            if location == "Applications"
            else str(deterministic_environment.home) + suffix
        )
    )
    host.path_bar.setText.assert_called_once_with(expected)
    host._restore_filesystem_model.assert_called_once_with()


def test_navigate_to_macos_mount_favorite_and_tag(monkeypatch, tmp_path):
    _set_platform(monkeypatch, "mac")
    favorite = tmp_path / "favorite"
    mount = tmp_path / "volume"
    host = SimpleNamespace(
        path_bar=Mock(),
        _restore_filesystem_model=Mock(),
        _finder_favorites={"Favorite": str(favorite)},
        _finder_tags=["Red"],
        macos_mount_points=Mock(return_value={"Mount/USB": str(mount)}),
        _show_tagged_files=Mock(),
    )

    dialog_module.MultiFolderDialog.navigate_to_location(
        host, _location_item("Mount/USB", user_role=False)
    )
    host.path_bar.setText.assert_called_with(str(mount))

    dialog_module.MultiFolderDialog.navigate_to_location(
        host, _location_item("Favorite", user_role=False)
    )
    host.path_bar.setText.assert_called_with(str(favorite))

    restore_count = host._restore_filesystem_model.call_count
    dialog_module.MultiFolderDialog.navigate_to_location(
        host, _location_item("Red", user_role=False)
    )
    host._show_tagged_files.assert_called_once_with("Red")
    assert host._restore_filesystem_model.call_count == restore_count

    host.path_bar.reset_mock()
    dialog_module.MultiFolderDialog.navigate_to_location(
        host, _location_item("Mount/Missing", user_role=False)
    )
    host.path_bar.setText.assert_not_called()


@pytest.mark.parametrize(
    ("location", "suffix"),
    [
        ("Home", ""),
        ("Desktop", "/Desktop"),
        ("Downloads", "/Downloads"),
        ("Documents", "/Documents"),
        ("Pictures", "/Pictures"),
        ("Music", "/Music"),
        ("Videos", "/Videos"),
    ],
)
def test_navigate_to_windows_standard_locations(
    monkeypatch, deterministic_environment, location, suffix
):
    _set_platform(monkeypatch, "windows")
    host = SimpleNamespace(
        path_bar=Mock(),
        _windows_onedrive_paths={},
        _windows_drives={},
        _windows_pinned_items={},
        _windows_network_locations={},
        _show_empty_drive=Mock(),
    )

    dialog_module.MultiFolderDialog.navigate_to_location(host, _location_item(location))

    expected = str(deterministic_environment.home) + suffix
    host.path_bar.setText.assert_called_once_with(expected)


def test_navigate_to_windows_dynamic_locations_and_drives(monkeypatch, tmp_path):
    _set_platform(monkeypatch, "windows")
    onedrive = tmp_path / "OneDrive"
    pinned = tmp_path / "Pinned"
    network = tmp_path / "Network"
    full_drive = tmp_path / "full-drive"
    full_drive.mkdir()
    (full_drive / "entry").write_text("x", encoding="utf-8")
    empty_drive = tmp_path / "empty-drive"
    empty_drive.mkdir()
    host = SimpleNamespace(
        path_bar=Mock(),
        _windows_onedrive_paths={"OneDrive": str(onedrive)},
        _windows_drives={
            "Full": ["Win_fixed", str(full_drive)],
            "Empty": ["Win_removable", str(empty_drive)],
            "Broken": ["Win_cdrom", "BROKEN"],
        },
        _windows_pinned_items={"Pinned": str(pinned)},
        _windows_network_locations={"Network": str(network)},
        _show_empty_drive=Mock(),
    )

    for location, expected in (
        ("OneDrive", onedrive),
        ("Pinned", pinned),
        ("Network", network),
    ):
        dialog_module.MultiFolderDialog.navigate_to_location(
            host, _location_item(location, user_role=False)
        )
        host.path_bar.setText.assert_called_with(str(expected))

    dialog_module.MultiFolderDialog.navigate_to_location(
        host, _location_item("Full", user_role=False)
    )
    host.path_bar.setText.assert_called_with(str(full_drive))

    dialog_module.MultiFolderDialog.navigate_to_location(
        host, _location_item("Empty", user_role=False)
    )
    host._show_empty_drive.assert_called_with(str(empty_drive))

    real_path_api = dialog_module.Path

    class BrokenPath:
        def exists(self):
            return True

        def iterdir(self):
            raise OSError("not ready")

    monkeypatch.setattr(
        dialog_module,
        "Path",
        lambda value: BrokenPath() if value == "BROKEN" else real_path_api(value),
    )
    dialog_module.MultiFolderDialog.navigate_to_location(
        host, _location_item("Broken", user_role=False)
    )
    host._show_empty_drive.assert_called_with("BROKEN")


def test_navigate_to_linux_standard_mount_and_unknown(monkeypatch, tmp_path):
    _set_platform(monkeypatch, "linux")
    host = SimpleNamespace(
        path_bar=Mock(),
        _restore_filesystem_model=Mock(),
        _linux_mount_points={"USB": "/media/USB"},
        linux_standard_locations=Mock(return_value={"Home": str(tmp_path)}),
    )

    dialog_module.MultiFolderDialog.navigate_to_location(host, _location_item("Home"))
    host.path_bar.setText.assert_called_with(str(tmp_path))

    dialog_module.MultiFolderDialog.navigate_to_location(
        host, _location_item("USB", user_role=False)
    )
    host.path_bar.setText.assert_called_with("/media/USB")

    calls_before = host.path_bar.setText.call_count
    dialog_module.MultiFolderDialog.navigate_to_location(
        host, _location_item("Unknown", user_role=False)
    )
    assert host.path_bar.setText.call_count == calls_before
    assert host._restore_filesystem_model.call_count == 3


# ---------------------------------------------------------------------------
# Linux and macOS boundaries
# ---------------------------------------------------------------------------


def test_linux_standard_locations_are_based_on_controlled_home(
    dialog, deterministic_environment
):
    locations = dialog.linux_standard_locations()

    assert locations == {
        "Root": "/",
        "Home": str(deterministic_environment.home),
        "Desktop": str(deterministic_environment.home) + "/Desktop",
        "Documents": str(deterministic_environment.home) + "/Documents",
        "Downloads": str(deterministic_environment.home) + "/Downloads",
        "Pictures": str(deterministic_environment.home) + "/Pictures",
        "Music": str(deterministic_environment.home) + "/Music",
        "Videos": str(deterministic_environment.home) + "/Videos",
    }


def test_linux_mount_points_discovers_media_devices_and_mnt_entries(
    dialog, monkeypatch, tmp_path
):
    media = tmp_path / "media"
    mnt = tmp_path / "mnt"
    (media / "user" / "Camera").mkdir(parents=True)
    (media / "user" / "USB").mkdir()
    (media / "loose-file").write_text("ignore", encoding="utf-8")
    (mnt / "Archive").mkdir(parents=True)
    (mnt / "ignore.txt").write_text("ignore", encoding="utf-8")

    def mapped_path(value):
        if value == "/media":
            return media
        if value == "/mnt":
            return mnt
        return RealPath(value)

    monkeypatch.setattr(dialog_module, "Path", mapped_path)

    assert dialog.linux_mount_points() == {
        "Camera": str(media / "user" / "Camera"),
        "USB": str(media / "user" / "USB"),
        "Archive": str(mnt / "Archive"),
    }


def test_linux_mount_points_logs_permission_and_outer_errors(dialog, monkeypatch):
    class FakeEntry:
        def __init__(self, name, *, directory=True, children=None, error=None):
            self.name = name
            self._directory = directory
            self._children = children or []
            self._error = error

        def __lt__(self, other):
            return self.name < other.name

        def __str__(self):
            return f"/fake/{self.name}"

        def is_dir(self):
            return self._directory

        def iterdir(self):
            if self._error:
                raise self._error
            return iter(self._children)

    denied = FakeEntry("denied", error=PermissionError("denied"))
    media = FakeEntry("media", children=[denied])
    mnt = FakeEntry("mnt", error=RuntimeError("failed"))
    missing = FakeEntry("missing", directory=False)
    monkeypatch.setattr(
        dialog_module,
        "Path",
        lambda value: {"/media": media, "/mnt": mnt}.get(value, missing),
    )
    log = Mock()
    monkeypatch.setattr(dialog_module, "log", log)

    assert dialog.linux_mount_points() == {}
    assert log.error.call_count == 2
    assert (
        "Permission error while fetching mount points"
        in log.error.call_args_list[0].args[0]
    )
    assert (
        "Error while fetching mount points in Linux"
        in log.error.call_args_list[1].args[0]
    )


def test_macos_mount_points_parses_only_volume_mounts(dialog, monkeypatch):
    output = (
        b"/dev/disk3s1 on /Volumes/USB (apfs, local)\n"
        b"server on /Volumes/Team Share (smbfs, nodev)\n"
        b"/dev/disk1 on / (apfs, local)\n"
        b"malformed line\n"
    )
    check_output = Mock(return_value=output)
    monkeypatch.setattr(dialog_module.subprocess, "check_output", check_output)

    assert dialog.macos_mount_points() == {
        "Mount/USB": "/Volumes/USB",
        "Mount/Team Share": "/Volumes/Team Share",
    }
    check_output.assert_called_once_with(["mount"])


def test_macos_finder_favorites_uses_first_existing_sfl(
    dialog, deterministic_environment, monkeypatch
):
    sfl_dir = (
        deterministic_environment.home
        / "Library/Application Support/com.apple.sharedfilelist"
    )
    sfl_dir.mkdir(parents=True)
    sfl3 = sfl_dir / "com.apple.LSSharedFileList.FavoriteItems.sfl3"
    sfl2 = sfl_dir / "com.apple.LSSharedFileList.FavoriteItems.sfl2"
    sfl3.write_bytes(b"new")
    sfl2.write_bytes(b"old")
    parse = Mock(return_value={"Work": "/work"})
    monkeypatch.setattr(dialog, "_parse_sfl_file", parse)

    assert dialog.macos_finder_favorites() == {"Work": "/work"}
    parse.assert_called_once_with(sfl3)


def test_macos_finder_favorites_handles_parse_error_and_missing_files(
    dialog, deterministic_environment, monkeypatch
):
    sfl_dir = (
        deterministic_environment.home
        / "Library/Application Support/com.apple.sharedfilelist"
    )
    sfl_dir.mkdir(parents=True)
    sfl4 = sfl_dir / "com.apple.LSSharedFileList.FavoriteItems.sfl4"
    sfl4.write_bytes(b"bad")
    monkeypatch.setattr(
        dialog, "_parse_sfl_file", Mock(side_effect=ValueError("bad plist"))
    )
    log = Mock()
    monkeypatch.setattr(dialog_module, "log", log)

    assert dialog.macos_finder_favorites() == {}
    log.error.assert_called_once_with(
        "Failed to parse Finder favorites from %s",
        sfl4,
        exc_info=True,
    )

    sfl4.unlink()
    assert dialog.macos_finder_favorites() == {}


def test_macos_finder_tags_parses_defaults_output(dialog, monkeypatch):
    check_output = Mock(
        return_value=b'(\n    "Red",\n    Blue,\n    "",\n    Green\n)\n'
    )
    monkeypatch.setattr(dialog_module.subprocess, "check_output", check_output)

    assert dialog.macos_finder_tags() == ["Red", "Blue", "Green"]
    check_output.assert_called_once_with(
        ["defaults", "read", "com.apple.finder", "FavoriteTagNames"],
        stderr=dialog_module.subprocess.DEVNULL,
    )


def test_macos_finder_tags_returns_empty_on_failure(dialog, monkeypatch):
    monkeypatch.setattr(
        dialog_module.subprocess,
        "check_output",
        Mock(side_effect=OSError("defaults unavailable")),
    )

    assert dialog.macos_finder_tags() == []


def test_show_tagged_files_builds_selectable_custom_model(
    dialog, monkeypatch, tmp_path
):
    alpha = tmp_path / "alpha.txt"
    beta = tmp_path / "beta.txt"
    alpha.write_text("a", encoding="utf-8")
    beta.write_text("b", encoding="utf-8")
    output = f"{beta}\n{tmp_path / 'missing'}\n{alpha}\n".encode()
    check_output = Mock(return_value=output)
    monkeypatch.setattr(dialog_module.subprocess, "check_output", check_output)

    dialog._show_tagged_files("Red")

    model = dialog.tree.model()
    assert isinstance(model, QStandardItemModel)
    assert model.rowCount() == 2
    assert model.columnCount() == 2
    assert model.data(model.index(0, 0)) == "alpha.txt"
    assert model.data(model.index(0, 0), Qt.ItemDataRole.UserRole) == str(alpha)
    assert model.data(model.index(1, 1)) == str(beta)
    assert not model.item(0, 0).isEditable()
    assert not model.item(0, 1).isEditable()
    assert dialog._using_custom_model is True
    assert dialog.path_bar.text() == "Tag: Red"
    assert not dialog.path_bar.signalsBlocked()
    check_output.assert_called_once_with(
        ["mdfind", 'kMDItemUserTags == "Red"'],
        stderr=dialog_module.subprocess.DEVNULL,
        timeout=10,
    )

    selection = dialog.tree.selectionModel()
    assert selection is not None
    selection.select(model.index(0, 0), QItemSelectionModel.SelectionFlag.Select)
    assert dialog.selected_paths() == [str(alpha)]


def test_show_tagged_files_handles_search_failure(dialog, monkeypatch):
    monkeypatch.setattr(
        dialog_module.subprocess,
        "check_output",
        Mock(side_effect=stdlib_subprocess.CalledProcessError(1, "mdfind")),
    )

    dialog._show_tagged_files("Missing")

    assert dialog.tree.model().rowCount() == 0
    assert dialog.path_bar.text() == "Tag: Missing"


def test_load_fda_alert_opens_once_and_honors_marker(
    deterministic_environment, monkeypatch
):
    instances = []

    class FakeAlert:
        visible = False

        def __init__(self, parent):
            self.parent = parent
            self.open = Mock()
            instances.append(self)

    monkeypatch.setattr(dialog_module, "FDAAlert", FakeAlert)
    host = object()

    dialog_module.MultiFolderDialog._load_fda_alert(host)
    assert len(instances) == 1
    instances[0].open.assert_called_once_with()
    assert FakeAlert.visible is True

    dialog_module.MultiFolderDialog._load_fda_alert(host)
    assert len(instances) == 1

    FakeAlert.visible = False
    marker = deterministic_environment.home / ".nuxeo-drive" / "dont_show_fda_alert"
    marker.parent.mkdir(parents=True)
    marker.touch()
    dialog_module.MultiFolderDialog._load_fda_alert(host)
    assert len(instances) == 1


def test_navigate_to_system_settings_uses_expected_url(monkeypatch):
    run = Mock()
    monkeypatch.setattr(dialog_module.subprocess, "run", run)

    dialog_module.MultiFolderDialog.navigate_to_system_settings()

    run.assert_called_once_with(
        [
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
        ]
    )


def test_parse_sfl_file_reads_keyed_archive_bookmarks(tmp_path):
    target = tmp_path / "Favorite"
    target.mkdir()
    bookmark = b"book" + b"x" * 60
    sfl = tmp_path / "favorites.sfl4"
    with sfl.open("wb") as stream:
        plistlib.dump({"$objects": ["$null", b"short", bookmark]}, stream)
    host = SimpleNamespace(_path_from_bookmark=Mock(return_value=str(target)))

    result = dialog_module.MultiFolderDialog._parse_sfl_file(host, sfl)

    assert result == {"Favorite": str(target)}
    host._path_from_bookmark.assert_called_once_with(bookmark)


def test_parse_sfl_file_reads_legacy_items_and_skips_invalid(tmp_path):
    first = tmp_path / "First"
    second = tmp_path / "Second"
    first.mkdir()
    second.mkdir()
    sfl = tmp_path / "favorites.sfl2"
    with sfl.open("wb") as stream:
        plistlib.dump(
            {
                "items": [
                    {"Name": "Named", "Bookmark": b"first"},
                    {"Bookmark": b"second"},
                    {"Name": "No bookmark"},
                    {"Name": "Missing", "Bookmark": b"missing"},
                ]
            },
            stream,
        )
    paths = {
        b"first": str(first),
        b"second": str(second),
        b"missing": str(tmp_path / "missing"),
    }
    host = SimpleNamespace(
        _path_from_bookmark=Mock(side_effect=lambda data: paths[data])
    )

    assert dialog_module.MultiFolderDialog._parse_sfl_file(host, sfl) == {
        "Named": str(first),
        "Second": str(second),
    }


def test_parse_sfl_file_permission_fallback_success(tmp_path):
    target = tmp_path / "Recovered"
    target.mkdir()
    bookmark = b"book" + b"r" * 60
    host = SimpleNamespace(
        _read_plist_via_plutil=Mock(return_value={"$objects": [bookmark]}),
        _path_from_bookmark=Mock(return_value=str(target)),
        _load_fda_alert=Mock(),
        fda_alert_widget=Mock(),
    )

    with patch("builtins.open", side_effect=PermissionError("TCC denied")):
        result = dialog_module.MultiFolderDialog._parse_sfl_file(
            host, tmp_path / "denied.sfl4"
        )

    assert result == {"Recovered": str(target)}
    host._load_fda_alert.assert_not_called()
    host.fda_alert_widget.setVisible.assert_not_called()


def test_parse_sfl_file_permission_fallback_failure_shows_warning(tmp_path):
    host = SimpleNamespace(
        _read_plist_via_plutil=Mock(return_value=None),
        _path_from_bookmark=Mock(),
        _load_fda_alert=Mock(),
        fda_alert_widget=Mock(),
    )

    with patch("builtins.open", side_effect=PermissionError("TCC denied")):
        result = dialog_module.MultiFolderDialog._parse_sfl_file(
            host, tmp_path / "denied.sfl4"
        )

    assert result == {}
    host._load_fda_alert.assert_called_once_with()
    host.fda_alert_widget.setVisible.assert_called_once_with(True)


def test_read_plist_via_plutil_parses_xml(dialog, monkeypatch, tmp_path):
    payload = {"items": [{"Name": "Documents"}]}
    check_output = Mock(return_value=plistlib.dumps(payload))
    monkeypatch.setattr(dialog_module.subprocess, "check_output", check_output)
    path = tmp_path / "favorites.sfl"

    assert dialog._read_plist_via_plutil(path) == payload
    check_output.assert_called_once_with(
        ["plutil", "-convert", "xml1", "-o", "-", str(path)],
        stderr=dialog_module.subprocess.DEVNULL,
    )


@pytest.mark.parametrize(
    "error",
    [
        stdlib_subprocess.CalledProcessError(1, "plutil"),
        ValueError("invalid plist"),
    ],
)
def test_read_plist_via_plutil_returns_none_on_failure(
    dialog, monkeypatch, tmp_path, error
):
    monkeypatch.setattr(
        dialog_module.subprocess, "check_output", Mock(side_effect=error)
    )

    assert dialog._read_plist_via_plutil(tmp_path / "bad.sfl") is None


def _bookmark_data(*, include_volume=True, array_dtype=0x601, components=True):
    data_start = 48
    data = bytearray(256)
    data[:4] = b"book"
    struct.pack_into("<I", data, 12, data_start)
    toc_relative = 104
    struct.pack_into("<I", data, data_start, toc_relative)
    toc_offset = data_start + toc_relative

    records = []

    def write_record(relative_offset, raw, dtype):
        absolute = data_start + relative_offset
        struct.pack_into("<II", data, absolute, len(raw), dtype)
        data[absolute + 8 : absolute + 8 + len(raw)] = raw

    if include_volume:
        write_record(8, b"/Volumes/Test", 0x101)
        records.append((0x2002, 8, 0))

    component_offsets = struct.pack("<II", 56, 80) if components else b""
    write_record(32, component_offsets, array_dtype)
    records.append((0x1004, 32, 0))
    if components:
        write_record(56, b"Users", 0x101)
        write_record(80, b"Documents", 0x101)

    struct.pack_into("<IIIII", data, toc_offset, 0, 0, 0, 0, len(records))
    position = toc_offset + 20
    for record in records:
        struct.pack_into("<IIi", data, position, *record)
        position += 12
    return bytes(data)


def test_path_from_bookmark_extracts_volume_and_components(dialog):
    assert dialog._path_from_bookmark(_bookmark_data()) == (
        "/Volumes/Test/Users/Documents"
    )
    assert (
        dialog._path_from_bookmark(_bookmark_data(include_volume=False))
        == "/Users/Documents"
    )


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not-a-bookmark" + b"x" * 50,
        b"book" + b"x" * 20,
        _bookmark_data(array_dtype=0x101),
        _bookmark_data(components=False),
    ],
    ids=[
        "empty",
        "wrong-magic",
        "short-header",
        "wrong-array-type",
        "no-components",
    ],
)
def test_path_from_bookmark_rejects_invalid_records(dialog, data):
    assert dialog._path_from_bookmark(data) is None


def test_path_from_bookmark_rejects_bad_toc_and_excessive_entries(dialog):
    bad_toc = bytearray(_bookmark_data())
    struct.pack_into("<I", bad_toc, 48, 1000)
    assert dialog._path_from_bookmark(bytes(bad_toc)) is None

    too_many = bytearray(_bookmark_data())
    struct.pack_into("<I", too_many, 48 + 104 + 16, 101)
    assert dialog._path_from_bookmark(bytes(too_many)) is None

    no_path_record = bytearray(_bookmark_data())
    struct.pack_into("<I", no_path_record, 48 + 104 + 16, 1)
    struct.pack_into("<I", no_path_record, 48 + 104 + 20, 0x2002)
    assert dialog._path_from_bookmark(bytes(no_path_record)) is None


# ---------------------------------------------------------------------------
# Windows boundaries
# ---------------------------------------------------------------------------


def test_get_windows_onedrive_paths_reads_valid_accounts(dialog, monkeypatch, tmp_path):
    personal_path = tmp_path / "OneDrive - Personal"
    personal_path.mkdir()
    root_key = object()
    personal_key = object()
    broken_key = object()

    class FakeWinreg:
        HKEY_CURRENT_USER = object()

        def __init__(self):
            self.closed = []

        def OpenKey(self, parent, name):
            if parent is self.HKEY_CURRENT_USER:
                assert name == r"Software\Microsoft\OneDrive\Accounts"
                return root_key
            if parent is root_key and name == "Personal":
                return personal_key
            if parent is root_key and name == "Broken":
                return broken_key
            raise AssertionError((parent, name))

        @staticmethod
        def EnumKey(key, index):
            if key is root_key and index == 0:
                return "Personal"
            if key is root_key and index == 1:
                return "Broken"
            raise OSError("done")

        @staticmethod
        def QueryValueEx(key, name):
            assert name == "UserFolder"
            if key is personal_key:
                return str(personal_path), 1
            raise OSError("missing value")

        def CloseKey(self, key):
            self.closed.append(key)

    winreg = FakeWinreg()
    monkeypatch.setattr(dialog_module, "winreg", winreg, raising=False)

    assert dialog.get_windows_onedrive_paths() == {
        "OneDrive - Personal": str(personal_path)
    }
    assert winreg.closed == [personal_key, broken_key, root_key]


def test_get_windows_onedrive_paths_handles_registry_open_failure(dialog, monkeypatch):
    winreg = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        OpenKey=Mock(side_effect=OSError("registry unavailable")),
    )
    monkeypatch.setattr(dialog_module, "winreg", winreg, raising=False)

    assert dialog.get_windows_onedrive_paths() == {}


def test_get_windows_drives_classifies_and_labels_supported_drives(dialog, monkeypatch):
    kernel32 = Mock()
    kernel32.GetLogicalDrives.return_value = 0b1111
    kernel32.GetDriveTypeW.side_effect = lambda root: {
        "A:\\": 2,
        "B:\\": 3,
        "C:\\": 5,
        "D:\\": 4,
    }[root]

    def volume_information(root, buffer, *args):
        if root == "A:\\":
            buffer.value = "USB"
            return 1
        if root == "C:\\":
            buffer.value = "Installer"
            return 1
        return 0

    kernel32.GetVolumeInformationW.side_effect = volume_information
    fake_ctypes = SimpleNamespace(
        windll=SimpleNamespace(kernel32=kernel32),
        create_unicode_buffer=stdlib_ctypes.create_unicode_buffer,
    )
    monkeypatch.setattr(dialog_module, "ctypes", fake_ctypes, raising=False)

    assert dialog.get_windows_drives() == {
        "USB (A:)": ["Win_removable", "A:\\"],
        "B:\\": ["Win_fixed", "B:\\"],
        "Installer (C:)": ["Win_cdrom", "C:\\"],
    }


def test_get_windows_drives_returns_empty_on_api_failure(dialog, monkeypatch):
    kernel32 = Mock()
    kernel32.GetLogicalDrives.side_effect = RuntimeError("Win32 failure")
    monkeypatch.setattr(
        dialog_module,
        "ctypes",
        SimpleNamespace(windll=SimpleNamespace(kernel32=kernel32)),
        raising=False,
    )

    assert dialog.get_windows_drives() == {}


def test_get_windows_pinned_items_hides_console_and_filters_paths(
    dialog, monkeypatch, tmp_path
):
    first = tmp_path / "Pinned One"
    second = tmp_path / "Pinned Two"
    first.mkdir()
    second.mkdir()
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("x", encoding="utf-8")

    class StartupInfo:
        def __init__(self):
            self.dwFlags = 0
            self.wShowWindow = None

    check_output = Mock(
        return_value=f"{first}\r\n{file_path}\r\n{second}\r\n\r\n".encode()
    )
    fake_subprocess = SimpleNamespace(
        STARTUPINFO=StartupInfo,
        STARTF_USESHOWWINDOW=1,
        SW_HIDE=0,
        CREATE_NO_WINDOW=0x08000000,
        DEVNULL=object(),
        check_output=check_output,
    )
    monkeypatch.setattr(dialog_module, "subprocess", fake_subprocess)

    assert dialog.get_windows_pinned_items() == {
        "Pinned One": str(first),
        "Pinned Two": str(second),
    }
    kwargs = check_output.call_args.kwargs
    assert kwargs["timeout"] == 10
    assert kwargs["creationflags"] == 0x08000000
    assert kwargs["startupinfo"].dwFlags == 1
    assert kwargs["startupinfo"].wShowWindow == 0


def test_get_windows_pinned_items_handles_missing_startup_api_and_failure(
    dialog, monkeypatch
):
    check_output = Mock(side_effect=OSError("powershell missing"))
    fake_subprocess = SimpleNamespace(
        DEVNULL=object(),
        check_output=check_output,
    )
    monkeypatch.setattr(dialog_module, "subprocess", fake_subprocess)

    assert dialog.get_windows_pinned_items() == {}
    assert check_output.call_args.kwargs["startupinfo"] is None
    assert check_output.call_args.kwargs["creationflags"] == 0


def _windows_network_fakes(*, open_error=None):
    kernel32 = Mock()
    kernel32.GetLogicalDrives.return_value = 0b101
    kernel32.GetDriveTypeW.side_effect = lambda root: 4 if root == "A:\\" else 3
    root_key = object()
    z_key = object()
    y_key = object()

    class FakeWinreg:
        HKEY_CURRENT_USER = object()

        def OpenKey(self, parent, name):
            if parent is self.HKEY_CURRENT_USER:
                if open_error:
                    raise open_error
                assert name == r"Network"
                return root_key
            if parent is root_key and name == "Z":
                return z_key
            if parent is root_key and name == "Y":
                return y_key
            raise AssertionError((parent, name))

        @staticmethod
        def EnumKey(key, index):
            if key is root_key and index == 0:
                return "Z"
            if key is root_key and index == 1:
                return "Y"
            raise OSError("done")

        @staticmethod
        def QueryValueEx(key, name):
            assert name == "RemotePath"
            if key is z_key:
                return r"\\server\share", 1
            raise OSError("missing")

        @staticmethod
        def CloseKey(key):
            return None

    ctypes_api = SimpleNamespace(windll=SimpleNamespace(kernel32=kernel32))
    return ctypes_api, FakeWinreg()


def test_get_windows_network_locations_merges_api_and_registry(dialog, monkeypatch):
    ctypes_api, winreg = _windows_network_fakes()
    monkeypatch.setattr(dialog_module, "ctypes", ctypes_api, raising=False)
    monkeypatch.setattr(dialog_module, "winreg", winreg, raising=False)

    assert dialog.get_windows_network_locations() == {
        "A:\\": "A:\\",
        r"Z: (\\server\share)": "Z:\\",
    }


def test_get_windows_network_locations_keeps_mapped_drives_on_registry_errors(
    dialog, monkeypatch
):
    ctypes_api, winreg = _windows_network_fakes(open_error=OSError("registry denied"))
    monkeypatch.setattr(dialog_module, "ctypes", ctypes_api, raising=False)
    monkeypatch.setattr(dialog_module, "winreg", winreg, raising=False)

    assert dialog.get_windows_network_locations() == {"A:\\": "A:\\"}

    _, generic_winreg = _windows_network_fakes(
        open_error=ValueError("unexpected registry failure")
    )
    monkeypatch.setattr(dialog_module, "winreg", generic_winreg, raising=False)
    assert dialog.get_windows_network_locations() == {"A:\\": "A:\\"}


def test_get_windows_network_locations_handles_drive_api_failure(dialog, monkeypatch):
    kernel32 = Mock()
    kernel32.GetLogicalDrives.side_effect = RuntimeError("drive API failed")
    winreg = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        OpenKey=Mock(side_effect=OSError("registry unavailable")),
    )
    monkeypatch.setattr(
        dialog_module,
        "ctypes",
        SimpleNamespace(windll=SimpleNamespace(kernel32=kernel32)),
        raising=False,
    )
    monkeypatch.setattr(dialog_module, "winreg", winreg, raising=False)

    assert dialog.get_windows_network_locations() == {}


# ---------------------------------------------------------------------------
# Platform panels, icons, item helpers, and hover behavior
# ---------------------------------------------------------------------------


def test_panel_locations_macos_favorites_mounts_and_tags(
    dialog, keep_object, monkeypatch, tmp_path
):
    _set_platform(monkeypatch, "mac")
    monkeypatch.setattr(
        dialog,
        "macos_finder_favorites",
        Mock(
            return_value={
                "Desktop": str(tmp_path / "Desktop"),
                "Work": str(tmp_path / "Work"),
            }
        ),
    )
    monkeypatch.setattr(
        dialog,
        "macos_mount_points",
        Mock(return_value={"Mount/USB": "/Volumes/USB"}),
    )
    monkeypatch.setattr(dialog, "macos_finder_tags", Mock(return_value=["Red"]))
    icons = Mock(return_value=QIcon())
    monkeypatch.setattr(dialog, "fetch_icon", icons)

    panel = keep_object(dialog.panel_locations())
    texts = _panel_texts(panel)

    assert texts == ["HOME", "Desktop", "Work", "", "Mount/USB", "", "Red"]
    assert panel.item(0).data(Qt.ItemDataRole.UserRole) == "Home"
    assert dialog._finder_tags == ["Red"]
    assert dialog._finder_favorites["Work"] == str(tmp_path / "Work")
    assert icons.call_args_list == [
        call("Home"),
        call("Desktop"),
        call("Work"),
        call("Mount/USB"),
        call("tag"),
    ]
    assert panel.hasMouseTracking()
    assert panel.minimumWidth() == panel.maximumWidth()
    assert panel.minimumWidth() >= 80


def test_panel_locations_macos_fallback_without_tags(dialog, keep_object, monkeypatch):
    _set_platform(monkeypatch, "mac")
    monkeypatch.setattr(dialog, "macos_finder_favorites", Mock(return_value={}))
    monkeypatch.setattr(
        dialog,
        "macos_mount_points",
        Mock(return_value={"Mount/Disk": "/Volumes/Disk"}),
    )
    monkeypatch.setattr(dialog, "macos_finder_tags", Mock(return_value=[]))
    monkeypatch.setattr(dialog, "fetch_icon", Mock(return_value=QIcon()))

    panel = keep_object(dialog.panel_locations())

    assert _panel_texts(panel) == [
        "HOME",
        "APPLICATIONS",
        "DESKTOP",
        "DOCUMENTS",
        "DOWNLOADS",
        "PICTURES",
        "MUSIC",
        "MOVIES",
        "",
        "Mount/Disk",
    ]
    assert dialog._finder_tags == []


def test_panel_locations_windows_pinned_deduplicates_sections(
    dialog, keep_object, monkeypatch
):
    _set_platform(monkeypatch, "windows")
    monkeypatch.setattr(
        dialog,
        "get_windows_pinned_items",
        Mock(return_value={"Pinned": "C:\\Pinned", "Shared": "C:\\Shared"}),
    )
    monkeypatch.setattr(
        dialog,
        "get_windows_drives",
        Mock(return_value={"System (C:)": ["Win_fixed", "C:\\"]}),
    )
    monkeypatch.setattr(
        dialog,
        "get_windows_onedrive_paths",
        Mock(return_value={"Shared": "C:\\Shared", "Cloud": "C:\\Cloud"}),
    )
    monkeypatch.setattr(
        dialog,
        "get_windows_network_locations",
        Mock(return_value={"Cloud": "Z:\\", "Server": "Y:\\"}),
    )
    icons = Mock(return_value=QIcon())
    monkeypatch.setattr(dialog, "fetch_icon", icons)

    panel = keep_object(dialog.panel_locations())

    assert _panel_texts(panel) == [
        "HOME",
        "Pinned",
        "Shared",
        "",
        "System (C:)",
        "",
        "Cloud",
        "",
        "Server",
    ]
    assert call("Win_fixed\\System (C:)") in icons.call_args_list
    assert call("Win_onedrive\\Cloud") in icons.call_args_list
    assert call("Win_network\\Server") in icons.call_args_list


def test_panel_locations_windows_fallback_populates_all_sections(
    dialog, keep_object, monkeypatch
):
    _set_platform(monkeypatch, "windows")
    monkeypatch.setattr(dialog, "get_windows_pinned_items", Mock(return_value={}))
    monkeypatch.setattr(
        dialog,
        "get_windows_drives",
        Mock(return_value={"DVD (D:)": ["Win_cdrom", "D:\\"]}),
    )
    monkeypatch.setattr(
        dialog,
        "get_windows_onedrive_paths",
        Mock(return_value={"OneDrive": "C:\\OneDrive"}),
    )
    monkeypatch.setattr(
        dialog,
        "get_windows_network_locations",
        Mock(return_value={"Network": "Z:\\"}),
    )
    monkeypatch.setattr(dialog, "fetch_icon", Mock(return_value=QIcon()))

    panel = keep_object(dialog.panel_locations())

    assert _panel_texts(panel) == [
        "HOME",
        "DESKTOP",
        "DOWNLOADS",
        "DOCUMENTS",
        "PICTURES",
        "MUSIC",
        "VIDEOS",
        "",
        "DVD (D:)",
        "",
        "OneDrive",
        "",
        "Network",
    ]


def test_panel_locations_linux_filters_missing_standard_paths_and_adds_mounts(
    dialog, keep_object, monkeypatch, tmp_path
):
    _set_platform(monkeypatch, "linux")
    existing = tmp_path / "existing"
    existing.mkdir()
    monkeypatch.setattr(
        dialog,
        "linux_standard_locations",
        Mock(
            return_value={
                "Home": str(existing),
                "Documents": str(tmp_path / "missing"),
            }
        ),
    )
    monkeypatch.setattr(
        dialog,
        "linux_mount_points",
        Mock(return_value={"USB": "/media/USB"}),
    )
    icons = Mock(return_value=QIcon())
    monkeypatch.setattr(dialog, "fetch_icon", icons)

    panel = keep_object(dialog.panel_locations())

    assert _panel_texts(panel) == ["HOME", "", "USB"]
    assert dialog._linux_mount_points == {"USB": "/media/USB"}
    assert icons.call_args_list == [call("Home"), call("Mount/USB")]


@pytest.mark.parametrize(
    ("name", "filename"),
    [
        ("Home", "home_dark.svg"),
        ("Up Arrow", "up_arrow_dark.svg"),
        ("Applications", "applications_dark.svg"),
        ("Desktop", "desktop_dark.svg"),
        ("Documents", "documents_dark.svg"),
        ("Downloads", "downloads_dark.svg"),
        ("Pictures", "pictures_dark.svg"),
        ("Music", "music_dark.svg"),
        ("Movies", "videos_dark.svg"),
        ("Videos", "videos_dark.svg"),
        ("Mount/USB", "mount_point_dark.svg"),
        ("tag", "tag_dark.svg"),
        ("Win_removable\\USB", "win_removable_dark.svg"),
        ("Win_fixed\\C", "win_drive_dark.svg"),
        ("Win_cdrom\\D", "win_cdrom_dark.svg"),
        ("Win_onedrive\\Cloud", "win_onedrive_dark.svg"),
        ("Win_network\\Share", "win_network_dark.svg"),
        ("Unknown", "folder_generic_dark.svg"),
    ],
)
def test_fetch_icon_maps_names_with_light_theme(monkeypatch, name, filename):
    find_icon = Mock(side_effect=lambda candidate: RealPath("/icons") / candidate)
    monkeypatch.setattr(dialog_module, "find_icon", find_icon)
    monkeypatch.setattr(dialog_module, "QIcon", lambda path: path)
    host = SimpleNamespace(_dark_mode=False)

    assert dialog_module.MultiFolderDialog.fetch_icon(host, name) == str(
        RealPath("/icons") / filename
    )
    find_icon.assert_called_once_with(filename)


def test_fetch_icon_uses_light_assets_for_dark_mode(monkeypatch):
    monkeypatch.setattr(dialog_module, "find_icon", lambda name: name)
    monkeypatch.setattr(dialog_module, "QIcon", lambda path: path)
    host = SimpleNamespace(_dark_mode=True)

    assert dialog_module.MultiFolderDialog.fetch_icon(host, "Home") == "home_light.svg"


@pytest.mark.parametrize(
    ("rgb", "expected"),
    [((50, 60, 70), "home_light.svg"), ((150, 160, 170), "home_dark.svg")],
)
def test_fetch_icon_linux_uses_actual_background(monkeypatch, rgb, expected):
    _set_platform(monkeypatch, "linux")
    color = SimpleNamespace(
        red=lambda: rgb[0], green=lambda: rgb[1], blue=lambda: rgb[2]
    )
    palette = SimpleNamespace(color=lambda role: color)
    host = SimpleNamespace(
        _dark_mode=False,
        palette=lambda: palette,
        backgroundRole=lambda: object(),
    )
    monkeypatch.setattr(dialog_module, "find_icon", lambda name: name)
    monkeypatch.setattr(dialog_module, "QIcon", lambda path: path)

    assert dialog_module.MultiFolderDialog.fetch_icon(host, "Home") == expected


def test_add_standard_location_item_translates_and_preserves_navigation_key(
    keep_object,
):
    panel = keep_object(QListWidget())

    dialog_module.MultiFolderDialog._add_std_loc_item(panel, "Home")
    dialog_module.MultiFolderDialog._add_std_loc_item(panel, "Custom")

    assert panel.item(0).text() == "HOME"
    assert panel.item(0).data(Qt.ItemDataRole.UserRole) == "Home"
    assert panel.item(1).text() == "Custom"
    assert panel.item(1).data(Qt.ItemDataRole.UserRole) == "Custom"


@pytest.mark.parametrize(
    ("rgb", "expected_color"),
    [((240, 240, 240), "#555555"), ((20, 20, 20), "#aaaaaa")],
)
def test_add_separator_disables_item_and_selects_contrasting_color(
    qapp, keep_object, rgb, expected_color
):
    color = SimpleNamespace(
        red=lambda: rgb[0], green=lambda: rgb[1], blue=lambda: rgb[2]
    )
    locations = Mock()
    locations.palette.return_value.color.return_value = color
    host = SimpleNamespace()

    dialog_module.MultiFolderDialog._add_separator(host, locations)

    item = locations.addItem.call_args.args[0]
    separator = locations.setItemWidget.call_args.args[1]
    keep_object(separator)
    assert item.flags() == Qt.ItemFlag.NoItemFlags
    assert item.sizeHint() == QSize(0, 12)
    assert separator.objectName() == "panelSeparator"
    assert expected_color in separator.styleSheet()
    locations.setItemWidget.assert_called_once_with(item, separator)


def test_hover_and_selection_helpers_update_bold_fonts(dialog, keep_object):
    panel = keep_object(QListWidget())
    first = QListWidgetItem("First")
    second = QListWidgetItem("Second")
    panel.addItem(first)
    panel.addItem(second)
    dialog._hovered_item = None

    dialog._on_item_hover(first)
    assert first.font().bold()
    assert dialog._hovered_item is first

    dialog._on_item_hover(second)
    assert not first.font().bold()
    assert second.font().bold()

    first.setSelected(True)
    dialog._on_item_hover(first)
    dialog._on_item_hover(second)
    assert first.font().bold()

    second.setSelected(False)
    dialog._on_selection_changed(panel)
    assert first.font().bold()
    assert not second.font().bold()


def test_event_filter_clears_unselected_hover_on_viewport_leave(dialog, keep_object):
    panel = keep_object(QListWidget())
    item = QListWidgetItem("Hover")
    panel.addItem(item)
    dialog._locations_widget = panel
    dialog._hovered_item = item
    dialog._set_item_bold(item, True)
    viewport = panel.viewport()
    assert viewport is not None

    result = dialog.eventFilter(viewport, QEvent(QEvent.Type.Leave))

    assert result is False
    assert dialog._hovered_item is None
    assert not item.font().bold()


def test_event_filter_preserves_selected_font_and_handles_deleted_widget(
    dialog, keep_object, monkeypatch
):
    panel = keep_object(QListWidget())
    item = QListWidgetItem("Selected")
    panel.addItem(item)
    item.setSelected(True)
    dialog._locations_widget = panel
    dialog._hovered_item = item
    dialog._set_item_bold(item, True)
    viewport = panel.viewport()
    assert viewport is not None

    dialog.eventFilter(viewport, QEvent(QEvent.Type.Leave))
    assert item.font().bold()
    assert dialog._hovered_item is None

    deleted_widget = Mock()
    deleted_widget.viewport.side_effect = RuntimeError("wrapped object deleted")
    dialog._locations_widget = deleted_widget
    log = Mock()
    monkeypatch.setattr(dialog_module, "log", log)
    assert dialog.eventFilter(dialog, QEvent(QEvent.Type.User)) is False
    log.error.assert_called_once_with(
        "Skipping eventFilter on deleted locations widget: %s",
        deleted_widget.viewport.side_effect,
    )


def test_dialog_buttons_and_navigation_signals_are_connected(
    keep_object, deterministic_environment, tmp_path
):
    accepted = keep_object(dialog_module.MultiFolderDialog())
    button_box = accepted.findChild(QDialogButtonBox)
    assert button_box is not None
    ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button is not None
    ok_button.click()
    assert accepted.result() == QDialog.DialogCode.Accepted.value

    rejected = keep_object(dialog_module.MultiFolderDialog())
    button_box = rejected.findChild(QDialogButtonBox)
    assert button_box is not None
    cancel = button_box.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel is not None
    cancel.click()
    assert rejected.result() == QDialog.DialogCode.Rejected.value

    navigated = keep_object(dialog_module.MultiFolderDialog())
    nested = tmp_path / "one" / "two"
    nested.mkdir(parents=True)
    _set_path_without_signal(navigated, nested)
    navigated.btnUp.click()
    assert navigated.path_bar.text() == str(nested.parent)
    navigated.btnHome.click()
    assert navigated.path_bar.text() == str(deterministic_environment.home)


def test_fda_settings_button_connection_is_safe(keep_object, monkeypatch):
    navigate = Mock()
    monkeypatch.setattr(
        dialog_module.MultiFolderDialog,
        "navigate_to_system_settings",
        staticmethod(navigate),
    )
    dialog = keep_object(dialog_module.MultiFolderDialog())

    dialog.fda_alert_button.click()

    navigate.assert_called_once()
