"""Coverage tests for small shared GUI widgets and tree helpers."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from nxdrive.drive.gui import folders_dialog as dialog_module
from nxdrive.drive.gui import folders_loader as loader_module
from nxdrive.drive.gui import folders_treeview as tree_module
from nxdrive.drive.gui import multi_folder_dialog as multi_module
from nxdrive.drive.gui import systray as systray_module
from nxdrive.drive.qt import constants as qt
from nxdrive.drive.qt.imports import QDialog, QStandardItemModel


def make_folder_tree(*, selected_folder=None):
    tree = tree_module.FolderTreeView.__new__(tree_module.FolderTreeView)
    tree.root_item = Mock()
    tree.current = Mock()
    tree.parent = Mock()
    tree.selected_folder = selected_folder
    return tree


def test_folder_tree_constructor_handles_missing_selection_model(monkeypatch):
    monkeypatch.setattr(tree_module.TreeViewMixin, "__init__", lambda self, *_a: None)
    monkeypatch.setattr(tree_module.FolderTreeView, "selectionModel", lambda self: None)
    with patch.object(tree_module.log, "error") as log_error:
        tree_module.FolderTreeView(Mock(), Mock())
    log_error.assert_called_once_with(
        "Cannot get the selection model for FolderTreeView"
    )


def test_find_current_skips_missing_child_and_chooses_longest_parent():
    tree = make_folder_tree()
    tree.parent.remote_folder.text.return_value = "/root/long/target"
    item = Mock()
    item.rowCount.return_value = 3
    short_data = Mock()
    short_data.get_path.return_value = "/root"
    short = Mock()
    short.data.return_value = short_data
    long_data = Mock()
    long_data.get_path.return_value = "/root/long"
    long = Mock()
    long.data.return_value = long_data
    item.child.side_effect = [None, short, long]
    tree.root_item.itemFromIndex.return_value = item
    tree.setExpanded = Mock()

    with patch.object(tree_module.log, "error") as log_error:
        tree._find_current_and_select_it()

    log_error.assert_called_once_with("Cannot get child at index 0")
    assert tree.current is long.index.return_value
    tree.setExpanded.assert_called_once_with(long.index.return_value, True)


def test_expand_current_selected_expands_once_and_loads():
    tree = make_folder_tree()
    tree.isExpanded = Mock(return_value=False)
    tree.setExpanded = Mock()
    tree.expand_item = Mock()

    tree.expand_current_selected()

    tree.setExpanded.assert_called_once_with(tree.current, True)
    tree.expand_item.assert_called_once_with(tree.current)


def test_select_from_path_skips_missing_child_then_selects():
    tree = make_folder_tree()
    item = Mock()
    item.rowCount.return_value = 2
    data = Mock()
    data.get_path.return_value = "/new"
    child = Mock()
    child.data.return_value = data
    item.child.side_effect = [None, child]
    tree.root_item.itemFromIndex.return_value = item

    with patch.object(tree_module.log, "error") as log_error:
        tree.select_item_from_path("/new")

    log_error.assert_called_once_with("Cannot get child at index 0")
    tree.parent.remote_folder.setText.assert_called_once_with("/new")


def test_is_item_enabled_checks_user_data():
    tree = make_folder_tree()
    item = Mock()
    item.data.return_value = None
    assert tree.is_item_enabled(item) is False

    data = Mock()
    data.enable.return_value = True
    item.data.return_value = data
    assert tree.is_item_enabled(item) is True


def make_loader_tree():
    root_model = QStandardItemModel()
    tree = Mock()
    tree.root_item = root_model
    tree.cache = []
    tree.client = Mock()
    tree.filled = Mock()
    return tree


def test_content_loader_root_fetch_no_roots_and_abstract_method():
    tree = make_loader_tree()
    tree.client.get_top_documents.return_value = []
    tree.noRoots = Mock()
    loader = loader_module.ContentLoaderMixin(tree)
    loader.fill_tree = Mock()

    loader.run()

    tree.client.get_top_documents.assert_called_once_with()
    tree.noRoots.emit.assert_called_once_with(True)
    loader.fill_tree.assert_called_once_with([])
    with pytest.raises(NotImplementedError):
        loader.new_subitem(Mock())


def test_content_loader_without_item_logs_and_folder_loader_emits():
    tree = Mock(root_item=None)
    loader = loader_module.ContentLoaderMixin(tree)
    loader.item = None
    with patch.object(loader_module.log, "error") as log_error:
        loader.fill_tree([])
    log_error.assert_called_once_with("No item to fill in the tree view")

    folder_tree = make_loader_tree()
    folder_loader = loader_module.FolderContentLoader(folder_tree)
    children = [Mock()]
    with patch.object(loader_module.ContentLoaderMixin, "fill_tree") as base_fill:
        folder_loader.fill_tree(children)
    base_fill.assert_called_once_with(children)
    folder_tree.filled.emit.assert_called_once_with()


def test_documents_dialog_syncing_returns_disabled_label(qapp):
    dialog = dialog_module.DocumentsDialog.__new__(dialog_module.DocumentsDialog)
    QDialog.__init__(dialog)
    dialog.engine = Mock()
    dialog.engine.is_syncing.return_value = True
    try:
        with patch.object(
            dialog_module.Translator,
            "get",
            side_effect=lambda key, **_kwargs: key,
        ):
            label = dialog.get_tree_view()
        assert label.text() == "FILTERS_DISABLED"
        assert label.margin() == 15
        assert label.alignment() == qt.AlignHCenter | qt.AlignVCenter
    finally:
        dialog.deleteLater()
        qapp.processEvents()


def test_documents_dialog_accept_logs_filter_failure_and_closes(qapp):
    dialog = dialog_module.DocumentsDialog.__new__(dialog_module.DocumentsDialog)
    QDialog.__init__(dialog)
    dialog.tree_view = dialog_module.DocumentTreeView.__new__(
        dialog_module.DocumentTreeView
    )
    dialog.apply_filters = Mock(side_effect=RuntimeError("failure"))
    try:
        with patch.object(dialog_module.log, "error") as log_error:
            dialog.accept()
        log_error.assert_called_once_with(
            "apply_filters() raised; dialog will still close", exc_info=True
        )
        assert dialog.result() == QDialog.DialogCode.Accepted.value
    finally:
        dialog.deleteLater()
        qapp.processEvents()


def test_folders_dialog_accept_default_container_type():
    host = SimpleNamespace(
        cbDocType=Mock(),
        cbContainerType=Mock(),
        cb=Mock(),
        paths={},
        remote_folder=Mock(),
        remote_folder_ref="ref",
        remote_folder_title="title",
        application=Mock(),
        engine=Mock(),
        last_local_selected_location=None,
        last_local_selected_doc_type="",
        scheduled_time="",
        scheduled_delay=0,
        scheduled_at_iso="",
        _find_folders_duplicates=Mock(return_value=[]),
        get_known_type_key=lambda _folder, value: value,
    )
    host.cbDocType.currentData.return_value = "Automatic"
    host.cbDocType.currentIndex.return_value = 0
    host.cbContainerType.currentIndex.return_value = 0
    host.cb.currentData.return_value = "create"

    with patch("builtins.super") as super_mock:
        dialog_module.FoldersDialog.accept(host)

    host.engine.direct_transfer_async.assert_called_once()
    assert host.engine.direct_transfer_async.call_args.kwargs["container_type"] == ""
    super_mock.return_value.accept.assert_called_once_with()


def test_dark_mode_change_light_path_and_widget_deletion(tmp_path):
    styles = tmp_path / "styles"
    styles.mkdir()
    (styles / "multi_folder_dialog_light.qss").write_text(
        "QDialog { color: black; }", encoding="utf-8"
    )
    widget = Mock()
    layout_item = Mock()
    layout_item.widget.return_value = widget
    host = SimpleNamespace(
        _dark_mode=True,
        setStyleSheet=Mock(),
        btnHome=Mock(),
        btnUp=Mock(),
        fetch_icon=Mock(),
        panel_layout=Mock(),
        panel_locations=Mock(return_value=Mock()),
    )
    host.panel_layout.takeAt.return_value = layout_item

    options = type(multi_module.Options).options
    original_res_dir = options["res_dir"]
    options["res_dir"] = (tmp_path, "test")
    try:
        multi_module.MultiFolderDialog._on_dark_mode_changed(host, False)
    finally:
        options["res_dir"] = original_res_dir

    host.setStyleSheet.assert_called_once_with("QDialog { color: black; }")
    widget.deleteLater.assert_called_once_with()


def test_linux_mount_points_skips_non_directory_base():
    path = Mock()
    path.is_dir.return_value = False
    host = SimpleNamespace()
    with patch.object(multi_module, "Path", return_value=path):
        assert multi_module.MultiFolderDialog.linux_mount_points(host) == {}
    assert path.is_dir.call_count == 2


def _bookmark_header(*, entries=0, toc_offset=4):
    data = bytearray(80)
    data[:4] = b"book"
    data[12:16] = (48).to_bytes(4, "little")
    data[48:52] = toc_offset.to_bytes(4, "little")
    toc = 48 + toc_offset
    data[toc + 16 : toc + 20] = entries.to_bytes(4, "little")
    return data


def test_bookmark_parser_truncated_entry_record_and_component():
    host = SimpleNamespace()
    data = _bookmark_header(entries=2)
    # One complete TOC entry followed by a truncated second entry.
    data[72:80] = (0x1004).to_bytes(4, "little") + (28).to_bytes(4, "little")
    assert multi_module.MultiFolderDialog._path_from_bookmark(host, bytes(data)) is None

    out_of_bounds_record = _bookmark_header(entries=1)
    out_of_bounds_record[72:80] = (0x1004).to_bytes(4, "little") + (500).to_bytes(
        4, "little"
    )
    assert (
        multi_module.MultiFolderDialog._path_from_bookmark(
            host, bytes(out_of_bounds_record)
        )
        is None
    )

    malformed = _bookmark_header(entries=1)
    malformed[72:80] = (0x1004).to_bytes(4, "little") + (28).to_bytes(4, "little")
    malformed.extend(b"\x00" * 24)
    # Array record length is not divisible by four, covering the trailing break.
    malformed[76:84] = (5).to_bytes(4, "little") + (0x601).to_bytes(4, "little")
    assert (
        multi_module.MultiFolderDialog._path_from_bookmark(host, bytes(malformed))
        is None
    )


def test_bookmark_parser_swallows_unpack_failure():
    host = SimpleNamespace()
    with patch.object(multi_module.struct, "unpack_from", side_effect=ValueError):
        assert (
            multi_module.MultiFolderDialog._path_from_bookmark(
                host, b"book" + b"0" * 60
            )
            is None
        )


def test_systray_clicks_settings_and_missing_style(qapp):
    application = Mock()
    application.systray_window.isVisible.side_effect = [True, False]
    icon = systray_module.DriveSystrayIcon.__new__(systray_module.DriveSystrayIcon)
    icon.application = application

    icon.handle_mouse_click(qt.Trigger)
    icon.handle_mouse_click(qt.Trigger)
    icon.handle_mouse_click(qt.MiddleClick)

    application.hide_systray.assert_called_once_with()
    application.show_systray.assert_called_once_with()
    application.show_settings.assert_called_once_with("Advanced")

    with (
        patch.object(systray_module.QApplication, "style", return_value=None),
        patch.object(systray_module.log, "error") as log_error,
    ):
        assert icon.get_context_menu() is None
    log_error.assert_called_once_with(
        "Could not get QApplication style for systray menu"
    )
