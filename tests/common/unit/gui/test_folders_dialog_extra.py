"""Deterministic widget tests for the folders dialogs."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.drive.feature import Feature
from nxdrive.drive.gui import folders_dialog as dialog_module
from nxdrive.drive.gui.folders_dialog import FoldersDialog, NewFolderDialog
from nxdrive.drive.options import Options
from nxdrive.drive.qt import constants as qt
from nxdrive.drive.qt.imports import (
    QDialog,
    QEvent,
    QIcon,
    QKeyEvent,
    QModelIndex,
    Qt,
    QTreeView,
    pyqtSignal,
)
from nxdrive.drive.translator import Translator
from nxdrive.drive.utils import find_resource


@pytest.fixture(scope="module", autouse=True)
def translator():
    if Translator.singleton is None:
        Translator(find_resource("i18n"), lang="en")


@pytest.fixture()
def engine():
    engine = MagicMock()
    engine.type = "nuxeo"
    engine.remote_user = "alice"
    engine.have_folder_upload = True
    engine.remote.get_doc_enricher.side_effect = lambda _ref, _name, folder=False: (
        ["Folder", "CustomFolder"] if folder else ["File", "CustomFile"]
    )
    config = {
        "dt_last_remote_location_ref": "remote-ref",
        "dt_last_remote_location_title": "Remote title",
        "dt_last_remote_location": "/remote/previous",
        "dt_last_local_selected_location": "/local/previous",
        "dt_last_local_selected_doc_type": "CustomFile",
        "dt_last_duplicates_behavior": "ignore",
    }
    engine.dao.get_config.side_effect = lambda key, default=None: config.get(
        key, default
    )
    return engine


@pytest.fixture()
def application():
    application = MagicMock()
    application.icon = QIcon()
    application.is_dark_mode.return_value = False
    return application


class StubFolderTreeView(QTreeView):
    """A real QWidget with the small FolderTreeView API used by the dialog."""

    update = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.current = QModelIndex()
        self.get_item_from_position = MagicMock(return_value=None)
        self.is_item_enabled = MagicMock(return_value=True)
        self.expand_current_selected = MagicMock()
        self.select_item_from_path = MagicMock()
        self.update_spy = MagicMock()
        self.update.connect(self.update_spy)


@pytest.fixture()
def tree_view(monkeypatch):
    tree = StubFolderTreeView()
    monkeypatch.setattr(FoldersDialog, "get_tree_view", lambda _self: tree)
    return tree


def close_widget(widget, qapp):
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


def make_dialog(qapp, application, engine, tree_view, path=None, selected_folder=None):
    dialog = FoldersDialog(application, engine, path, selected_folder)
    return dialog


def test_constructor_builds_real_widget_and_initial_state(
    qapp, application, engine, tree_view, tmp_path
):
    source = tmp_path / "source.txt"
    source.write_bytes(b"payload")

    dialog = make_dialog(
        qapp, application, engine, tree_view, source, "/remote/selected"
    )
    try:
        assert "alice" in dialog.windowTitle()
        assert dialog.remote_folder.text() == "/remote/selected"
        assert dialog.remote_folder_title == "selected"
        assert dialog.path == source
        assert dialog.paths == {source: 7}
        assert dialog.overall_count == 1
        assert dialog.overall_size == 7
        assert dialog.local_path.text() == str(source)
        assert dialog.upload_now_button.isEnabled()
        assert dialog.upload_later_button.isEnabled()
        assert dialog.new_folder_button.isHidden() is False
        assert dialog.cb.currentData() == "ignore"
        assert dialog.cbDocType.currentText() == "CustomFile"
        engine.dao.get_config.assert_any_call(
            "dt_last_duplicates_behavior", default="create"
        )
        assert tree_view.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    finally:
        close_widget(dialog, qapp)


def test_constructor_without_folder_upload_hides_new_folder_button(
    qapp, application, engine, tree_view
):
    engine.have_folder_upload = False
    dialog = make_dialog(qapp, application, engine, tree_view)
    try:
        assert dialog.paths == {}
        assert dialog.path is None
        assert dialog.local_path.text() == ""
        assert not dialog.upload_now_button.isEnabled()
        assert not dialog.upload_later_button.isEnabled()
        assert dialog.new_folder_button.isHidden()
    finally:
        close_widget(dialog, qapp)


def test_info_icon_and_duplicates_document(qapp, application, engine, tree_view):
    dialog = make_dialog(qapp, application, engine, tree_view)
    try:
        button = dialog._add_info_icon("DUPLICATE_BEHAVIOR_TOOLTIP")
        assert button.isFlat()
        assert button.maximumSize().width() == 16
        with patch.object(dialog_module.webbrowser, "open_new_tab") as open_tab:
            dialog._open_duplicates_doc(False)
        open_tab.assert_called_once_with(dialog_module.DOC_URL)
        button.deleteLater()
    finally:
        close_widget(dialog, qapp)


def test_key_press_escape_none_and_other_key(qapp, application, engine, tree_view):
    dialog = make_dialog(qapp, application, engine, tree_view)
    try:
        with patch.object(dialog, "showNormal") as show_normal:
            dialog.keyPressEvent(None)
            dialog.keyPressEvent(
                QKeyEvent(
                    QEvent.Type.KeyPress,
                    qt.Key_Escape,
                    Qt.KeyboardModifier.NoModifier,
                )
            )
            show_normal.assert_called_once_with()

        dialog.keyPressEvent(
            QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_A,
                Qt.KeyboardModifier.NoModifier,
            )
        )
    finally:
        close_widget(dialog, qapp)


def test_open_menu_no_item_and_missing_action(qapp, application, engine, tree_view):
    dialog = make_dialog(qapp, application, engine, tree_view)
    position = dialog_module.QPoint(2, 3)
    menu = MagicMock()
    try:
        tree_view.get_item_from_position.return_value = None
        with patch.object(dialog_module, "QMenu", return_value=menu):
            dialog.open_menu(position)
        menu.exec.assert_not_called()

        menu.reset_mock()
        menu.addAction.return_value = None
        item = MagicMock()
        tree_view.get_item_from_position.return_value = item
        with patch.object(dialog_module, "QMenu", return_value=menu):
            dialog.open_menu(position)
        tree_view.is_item_enabled.assert_not_called()
        menu.exec.assert_called_once_with(tree_view.viewport().mapToGlobal(position))
    finally:
        close_widget(dialog, qapp)


def test_get_tree_view_uses_registered_client(qapp, application, engine):
    class Client:
        def __init__(self, remote):
            self.remote = remote

    fake_config = SimpleNamespace(folders_only_class_path="client.path")
    expected_tree = MagicMock()
    dialog = FoldersDialog.__new__(FoldersDialog)
    QDialog.__init__(dialog)
    dialog.engine = engine
    dialog.selected_folder = "/chosen"
    try:
        with (
            patch.object(
                dialog_module._st, "get_by_engine_type", return_value=fake_config
            ),
            patch.object(dialog_module._st, "load_class", return_value=Client),
            patch.object(
                dialog_module, "FolderTreeView", return_value=expected_tree
            ) as tree_cls,
        ):
            result = FoldersDialog.get_tree_view(dialog)

        assert result is expected_tree
        client = tree_cls.call_args.args[1]
        assert isinstance(client, Client)
        assert client.remote is engine.remote
        tree_cls.assert_called_once_with(dialog, client, "/chosen")
    finally:
        dialog.deleteLater()
        qapp.processEvents()


def test_get_tree_view_rejects_backend_without_browser(qapp, engine):
    fake_config = SimpleNamespace(folders_only_class_path=None)
    dialog = FoldersDialog.__new__(FoldersDialog)
    QDialog.__init__(dialog)
    dialog.engine = engine
    dialog.selected_folder = None
    try:
        with (
            patch.object(
                dialog_module._st, "get_by_engine_type", return_value=fake_config
            ),
            patch.object(dialog_module._st, "load_class", return_value=None),
            pytest.raises(RuntimeError, match="not available"),
        ):
            FoldersDialog.get_tree_view(dialog)
    finally:
        dialog.deleteLater()
        qapp.processEvents()


def test_button_state_tracks_paths_schedule_selection_and_feature(
    qapp, application, engine, tree_view, tmp_path, monkeypatch
):
    source = tmp_path / "source.txt"
    source.write_text("data")
    dialog = make_dialog(qapp, application, engine, tree_view, source)
    try:
        # ``QModelIndex`` instances are truthy even when invalid; the dialog
        # uses a plain truthiness check, so ``None`` represents no selection.
        tree_view.current = None
        dialog.remote_folder_ref = "ref"
        monkeypatch.setattr(Feature, "document_type_selection", True)
        dialog.scheduled_time = "later"
        dialog.button_ok_state()
        assert dialog.upload_now_button.isEnabled()
        assert not dialog.upload_later_button.isEnabled()
        assert not dialog.new_folder_button.isEnabled()
        assert not dialog.cbDocType.isEnabled()
        assert not dialog.cbContainerType.isEnabled()

        tree_view.current = MagicMock()
        dialog.scheduled_time = ""
        dialog.button_ok_state()
        assert dialog.upload_later_button.isEnabled()
        assert dialog.new_folder_button.isEnabled()
        assert dialog.cbDocType.isEnabled()
        assert dialog.cbContainerType.isEnabled()
    finally:
        close_widget(dialog, qapp)


def test_accept_dispatches_selected_types_and_schedule(
    qapp, application, engine, tree_view, tmp_path
):
    source = tmp_path / "source.txt"
    source.write_bytes(b"abc")
    dialog = make_dialog(qapp, application, engine, tree_view, source)
    try:
        dialog.remote_folder.setText("/remote/target")
        dialog.remote_folder_ref = "target-ref"
        dialog.remote_folder_title = "Target"
        dialog.cbDocType.setCurrentText(dialog.KNOWN_FILE_TYPES["File"])
        dialog.cbContainerType.setCurrentText(dialog.KNOWN_FOLDER_TYPES["Folder"])
        dialog.cb.setCurrentIndex(dialog.cb.findData("override"))
        dialog.scheduled_time = "2030-01-02 03:04:05"
        dialog.scheduled_delay = 42
        dialog.scheduled_at_iso = "2030-01-02T03:04:05+00:00"

        with patch.object(dialog, "_find_folders_duplicates", return_value=[]):
            dialog.accept()

        assert dialog.result() == dialog.DialogCode.Accepted
        engine.direct_transfer_async.assert_called_once_with(
            {source: 3},
            "/remote/target",
            "target-ref",
            "Target",
            document_type="File",
            container_type="Folder",
            duplicate_behavior="override",
            last_local_selected_location=tmp_path,
            last_local_selected_doc_type=dialog.KNOWN_FILE_TYPES["File"],
            paused=True,
            schedule_delay=42,
            scheduled_at="2030-01-02T03:04:05+00:00",
        )
    finally:
        close_widget(dialog, qapp)


def test_accept_duplicate_warns_without_transfer(
    qapp, application, engine, tree_view, tmp_path
):
    source = tmp_path / "folder"
    source.mkdir()
    (source / "a.txt").write_text("x")
    dialog = make_dialog(qapp, application, engine, tree_view, source)
    try:
        engine.get_metadata_url.return_value = "https://server/doc/ref"
        with patch.object(dialog, "_find_folders_duplicates", return_value=["folder"]):
            dialog.accept()

        application.folder_duplicate_warning.assert_called_once_with(
            ["folder"], "Remote title", "https://server/doc/ref"
        )
        engine.direct_transfer_async.assert_not_called()
    finally:
        close_widget(dialog, qapp)


def test_find_folder_duplicates_uses_real_top_level_directories(
    qapp, application, engine, tree_view, tmp_path
):
    parent = tmp_path / "parent"
    child = parent / "child"
    parent.mkdir()
    child.mkdir()
    file_path = tmp_path / "file.txt"
    file_path.write_text("x")
    dialog = make_dialog(qapp, application, engine, tree_view)
    try:
        dialog.paths = {parent: 0, child: 0, file_path: 1}
        engine.remote.exists_in_parent.return_value = True
        assert dialog._find_folders_duplicates() == ["parent"]
        engine.remote.exists_in_parent.assert_called_once_with(
            "remote-ref", "parent", True
        )
    finally:
        close_widget(dialog, qapp)


def test_process_additional_paths_real_files_and_ignored_entries(
    qapp, application, engine, tree_view, tmp_path, monkeypatch
):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    empty = tmp_path / "empty.txt"
    ignored = tmp_path / ".ignored"
    first.write_bytes(b"123")
    second.write_bytes(b"45")
    empty.touch()
    ignored.write_bytes(b"ignored")
    dialog = make_dialog(qapp, application, engine, tree_view)
    original_file_limit = Options.direct_transfer_file_upper_limit
    original_folder_limit = Options.direct_transfer_folder_upper_limit
    Options.direct_transfer_file_upper_limit = 0
    Options.direct_transfer_folder_upper_limit = 0
    try:
        dialog._process_additionnal_local_paths(
            ["", str(first), str(first), str(empty), str(ignored), str(second)]
        )
        assert dialog.paths == {first: 3, second: 2}
        assert dialog.path == first
        assert dialog.last_local_selected_location == tmp_path
        assert dialog.local_path.text() == f"{first} (+1)"
        assert dialog.overall_count == 2
        assert dialog.overall_size == 5
        assert dialog.local_path_msg_lbl.text() == ""
    finally:
        Options.direct_transfer_file_upper_limit = original_file_limit
        Options.direct_transfer_folder_upper_limit = original_folder_limit
        close_widget(dialog, qapp)


def test_process_multiple_files_rejects_selection_over_total_limit(
    qapp, application, engine, tree_view, tmp_path, monkeypatch
):
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"a" * 600_000)
    second.write_bytes(b"b" * 600_000)
    dialog = make_dialog(qapp, application, engine, tree_view)
    original_file_limit = Options.direct_transfer_file_upper_limit
    original_folder_limit = Options.direct_transfer_folder_upper_limit
    Options.direct_transfer_file_upper_limit = 0
    Options.direct_transfer_folder_upper_limit = 1
    try:
        dialog._process_additionnal_local_paths([str(first), str(second)])
        assert dialog.paths == {}
        assert dialog.local_path_msg_lbl.text() == dialog_module.Translator.get(
            "SIZE_LIMIT_FOLDER"
        )
    finally:
        Options.direct_transfer_file_upper_limit = original_file_limit
        Options.direct_transfer_folder_upper_limit = original_folder_limit
        close_widget(dialog, qapp)


def test_process_file_limits_and_errors(qapp, application, engine, tree_view, tmp_path):
    dialog = make_dialog(qapp, application, engine, tree_view)
    path = tmp_path / "large.bin"
    path.write_bytes(b"12345")
    skipped = []
    try:
        assert dialog._process_file(path, 10, 4, None, skipped) == 10
        assert skipped == ["large.bin"]
        skipped.clear()
        assert dialog._process_file(path, 10, None, 14, skipped) == 10
        assert skipped == ["large.bin"]

        zero = tmp_path / "zero"
        zero.touch()
        assert dialog._process_file(zero, 10, None, None, []) == 10

        with patch.object(dialog, "get_size", side_effect=OSError("stat")):
            assert dialog._process_file(path, 10, None, None, []) == 10
        with patch.object(dialog, "get_size", side_effect=RuntimeError("unexpected")):
            assert dialog._process_file(path, 10, None, None, []) == 10
    finally:
        close_widget(dialog, qapp)


def test_process_directory_limits_children_and_errors(
    qapp, application, engine, tree_view, tmp_path
):
    folder = tmp_path / "folder"
    folder.mkdir()
    small = folder / "small.txt"
    large = folder / "large.txt"
    empty = folder / "empty.txt"
    small.write_bytes(b"12")
    large.write_bytes(b"12345")
    empty.touch()
    dialog = make_dialog(qapp, application, engine, tree_view)
    try:
        skipped = []
        assert dialog._process_directory(folder, 0, 3, None, skipped) == 2
        assert dialog.paths[folder] == 0
        assert dialog.paths[small] == 2
        assert large not in dialog.paths
        assert empty not in dialog.paths
        assert skipped == ["large.txt"]

        dialog.paths.clear()
        skipped.clear()
        assert dialog._process_directory(folder, 7, None, 6, skipped) == 7
        assert skipped == ["folder"]

        dialog.paths.clear()
        skipped.clear()
        assert dialog._process_directory(folder, 1, None, 7, skipped) == 1
        assert skipped == ["folder"]

        with patch.object(dialog_module, "get_tree_list", side_effect=OSError("scan")):
            assert dialog._process_directory(folder, 4, None, None, []) == 4
        with patch.object(
            dialog_module, "get_tree_list", side_effect=RuntimeError("unexpected")
        ):
            assert dialog._process_directory(folder, 4, None, None, []) == 4
    finally:
        close_widget(dialog, qapp)


def test_skipped_items_summary(qapp, application, engine, tree_view):
    dialog = make_dialog(qapp, application, engine, tree_view)
    try:
        assert dialog._skipped_items_summary([]) == ""
        one = dialog._skipped_items_summary(["one"])
        two = dialog._skipped_items_summary(["one", "two"])
        many = dialog._skipped_items_summary(["one", "two", "three", "four"])
        assert "one" in one
        assert "one, two" in two
        assert "one, two (+2)" in many
    finally:
        close_widget(dialog, qapp)


def test_select_files_and_folders_accept_and_cancel(
    qapp, application, engine, tree_view
):
    dialog = make_dialog(qapp, application, engine, tree_view)
    try:
        chooser = MagicMock()
        chooser.exec.return_value = 1
        chooser.selected_paths.return_value = ["/tmp/a", "/tmp/b"]
        with (
            patch.object(
                dialog_module, "MultiFolderDialog", return_value=chooser
            ) as cls,
            patch.object(dialog, "_process_additionnal_local_paths") as process,
        ):
            dialog._select_files_and_folders()
        cls.assert_called_once_with(
            dark_mode=False,
            dark_mode_signal=application.dark_mode_signal,
            parent=dialog,
        )
        process.assert_called_once_with(["/tmp/a", "/tmp/b"])

        chooser.exec.return_value = 0
        process.reset_mock()
        with (
            patch.object(dialog_module, "MultiFolderDialog", return_value=chooser),
            patch.object(dialog, "_process_additionnal_local_paths") as process,
        ):
            dialog._select_files_and_folders()
        process.assert_not_called()
    finally:
        close_widget(dialog, qapp)


def test_schedule_later_cancel_none_and_accepted_time(
    qapp, application, engine, tree_view
):
    dialog = make_dialog(qapp, application, engine, tree_view)
    try:
        schedule = MagicMock()
        schedule.exec.return_value = 0
        with (
            patch.object(dialog_module, "ScheduleDialog", return_value=schedule),
            patch.object(dialog, "accept") as accept,
        ):
            dialog._schedule_later_action()
        accept.assert_not_called()

        schedule.exec.return_value = 1
        schedule.get_time.return_value = None
        with (
            patch.object(dialog_module, "ScheduleDialog", return_value=schedule),
            patch.object(dialog, "accept") as accept,
        ):
            dialog._schedule_later_action()
        accept.assert_called_once_with()
        assert dialog.scheduled_time == ""

        future = datetime.now(timezone.utc) + timedelta(seconds=90)
        time_value = MagicMock()
        time_value.toString.return_value = "2030-01-02 03:04:05"
        time_value.toPython.return_value = future
        schedule.get_time.return_value = time_value
        with (
            patch.object(dialog_module, "ScheduleDialog", return_value=schedule),
            patch.object(dialog, "accept") as accept,
        ):
            dialog._schedule_later_action()
        accept.assert_called_once_with()
        assert dialog.scheduled_time == "2030-01-02 03:04:05"
        assert dialog.scheduled_at_iso == future.isoformat()
        assert 88 <= dialog.scheduled_delay <= 90

        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        time_value.toPython.return_value = past
        with (
            patch.object(dialog_module, "ScheduleDialog", return_value=schedule),
            patch.object(dialog, "accept"),
        ):
            dialog._schedule_later_action()
        assert dialog.scheduled_delay == 0
    finally:
        close_widget(dialog, qapp)


def test_new_folder_dialog_constructor_layout_and_validation(
    qapp, application, engine, tree_view
):
    parent = make_dialog(qapp, application, engine, tree_view)
    child = NewFolderDialog(parent)
    try:
        assert child.parent() is parent
        assert child.facetList == ["File", "CustomFile"]
        assert child.operation_result_frame.isHidden()
        assert child.folder_creation_frame.isVisible() is False
        assert child.new_folder_name.maxLength() == 64
        assert child.new_folder_name.validator() is not None
        assert child.cb.itemText(0) == "Automatic"
        assert not child.create_button.isEnabled()
        child.new_folder_name.setText("Created folder")
        assert child.create_button.isEnabled()
        state, _, _ = child.new_folder_name.validator().validate("bad/name", 8)
        assert state != dialog_module.QRegularExpressionValidator.State.Acceptable
    finally:
        close_widget(child, qapp)
        close_widget(parent, qapp)


def test_new_folder_accept_duplicate_and_dispatch(qapp, application, engine, tree_view):
    parent = make_dialog(qapp, application, engine, tree_view)
    child = NewFolderDialog(parent)
    try:
        parent.remote_folder.setText("/remote/parent")
        parent.last_local_selected_location = Path("/local")
        child.new_folder_name.setText("Duplicate")
        engine.remote.exists_in_parent.return_value = True
        child.accept()
        # The child dialog itself is not shown in this unit test, therefore
        # QWidget.isVisible() is false for every descendant. isHidden()
        # captures the explicit show/hide state changed by the method.
        assert not child.operation_result_frame.isHidden()
        assert child.folder_creation_frame.isHidden()
        assert child.operation_result_status.text() == dialog_module.Translator.get(
            "ERROR"
        )
        engine.direct_transfer_async.assert_not_called()

        child.folder_creation_frame.show()
        child.operation_result_frame.hide()
        engine.remote.exists_in_parent.return_value = False
        child.new_folder_name.setText("Fresh")
        child.cb.setCurrentText("CustomFile")
        child.accept()
        engine.direct_transfer_async.assert_called_once_with(
            {},
            "/remote/parent",
            "remote-ref",
            "Remote title",
            document_type="",
            container_type="",
            duplicate_behavior="ignore",
            last_local_selected_location=Path("/local"),
            new_folder="Fresh",
            new_folder_type="CustomFile",
        )
    finally:
        close_widget(child, qapp)
        close_widget(parent, qapp)


def test_new_folder_success_failure_close_and_close_event(
    qapp, application, engine, tree_view
):
    parent = make_dialog(qapp, application, engine, tree_view)
    child = NewFolderDialog(parent)
    try:
        child.handle_creation_failure()
        assert child.operation_result_status.text() == dialog_module.Translator.get(
            "ERROR"
        )
        assert child.operation_result_message.text() == dialog_module.Translator.get(
            "NEW_REMOTE_FOLDER_FAILURE"
        )

        child.handle_creation_success("/remote/parent/new")
        assert child.created_remote_path == "/remote/parent/new"
        tree_view.update_spy.assert_called_once_with()
        assert child.operation_result_status.text() == dialog_module.Translator.get(
            "SUCCESS"
        )

        with patch.object(child, "close") as close:
            child.close_success()
        assert tree_view.expand_current_selected.call_count == 2
        tree_view.select_item_from_path.assert_called_once_with("/remote/parent/new")
        close.assert_called_once_with()

        with patch.object(child, "close_success") as close_success:
            child.created_remote_path = ""
            child.closeEvent(QEvent(QEvent.Type.Close))
            close_success.assert_not_called()
            child.created_remote_path = "/created"
            child.closeEvent(QEvent(QEvent.Type.Close))
            close_success.assert_called_once_with()
    finally:
        close_widget(child, qapp)
        close_widget(parent, qapp)


def test_new_folder_engine_signals_reach_handlers(qapp, application, engine, tree_view):
    class Signal:
        def __init__(self):
            self.callback = None

        def connect(self, callback):
            self.callback = callback

        def emit(self, *args):
            self.callback(*args)

    engine.directTransferNewFolderSuccess = Signal()
    engine.directTransferNewFolderError = Signal()
    parent = make_dialog(qapp, application, engine, tree_view)
    child = NewFolderDialog(parent)
    try:
        engine.directTransferNewFolderError.emit()
        assert child.operation_result_status.text() == dialog_module.Translator.get(
            "ERROR"
        )
        engine.directTransferNewFolderSuccess.emit("/remote/created")
        assert child.created_remote_path == "/remote/created"
    finally:
        child.created_remote_path = ""
        close_widget(child, qapp)
        close_widget(parent, qapp)
