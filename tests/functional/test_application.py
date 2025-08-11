"""
Functional tests for nxdrive/gui/application.py

Known issue with pyinstaller and Windows on Github workflow
Hence, functional tests for application will be run only on Mac
https://github.com/orgs/pyinstaller/discussions/7287
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt5.QtCore import QObject

from nxdrive.constants import WINDOWS
from nxdrive.gui.api import QMLDriveApi
from nxdrive.gui.application import Application
from nxdrive.gui.folders_dialog import FoldersDialog
from nxdrive.options import Options
from tests.functional.mocked_classes import Mock_Engine, Mock_Qt

from ..markers import not_linux


@pytest.fixture
def app_obj(manager_factory):
    manager, engine = manager_factory()
    mock_qt = Mock_Qt()
    with patch(
        "PyQt5.QtQml.QQmlApplicationEngine.rootObjects"
    ) as mock_root_objects, patch(
        "PyQt5.QtCore.QObject.findChild"
    ) as mock_find_child, patch(
        "nxdrive.gui.application.Application.init_nxdrive_listener"
    ) as mock_listener, patch(
        "nxdrive.gui.application.Application.show_metrics_acceptance"
    ) as mock_show_metrics, patch(
        "nxdrive.engine.activity.FileAction.__repr__"
    ) as mock_download_repr, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute, patch(
        "nxdrive.engine.workers.Worker.run"
    ) as mock_run, patch(
        "PyQt5.QtWidgets.QDialog.exec_"
    ) as mock_exec, patch(
        "nxdrive.gui.application.Application.question"
    ) as mock_question:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_execute.return_value = None
        mock_run.return_value = None
        mock_exec.return_value = None
        mock_question.return_value = None
        app = Application(manager)
        yield app


@not_linux(reason="Qt does not work correctly on linux")
def test_application(app_obj, manager_factory):
    from PyQt5.QtCore import QRect
    from PyQt5.QtWidgets import QMessageBox

    from nxdrive.constants import DelAction

    app = app_obj
    manager, engine = manager_factory()
    mock_qt = Mock_Qt()
    # Covering create_custom_window_for_task_manager
    with patch(
        "nxdrive.gui.application.Application._fill_qml_context"
    ) as mock_qml_context, patch(
        "nxdrive.gui.application.CustomWindow"
    ) as mock_custom_window, patch(
        "tests.functional.mocked_classes.Mock_Qt.rootContext"
    ) as mock_root_context:
        mock_qml_context.return_value = None
        mock_custom_window.return_value = Mock_Qt
        mock_root_context.return_value = None
        assert app.create_custom_window_for_task_manager() is None
    # Covering update_workflow
    assert app.update_workflow() is None
    # Covering updat_feature_state
    assert app._update_feature_state("auto_update", True) is None
    # Covering _msbox
    assert isinstance(app._msgbox(), QMessageBox)
    # Covering display_info
    assert (
        app.display_info("Warning title", "Warning message", ["value1", "value2"])
        is None
    )
    # Covering display_warning
    with patch("nxdrive.gui.application.Application._msgbox") as mock_msgbox:
        mock_msgbox.return_value = None
        assert (
            app.display_warning(
                "Warning title", "Warning message", ["value1", "value2"]
            )
            is None
        )
    # Covering direct_edit_conflict
    with patch("nxdrive.gui.application.Application.question") as mock_question:
        mock_question.return_value = mock_qt
        assert (
            app._direct_edit_conflict(
                "dummy_filename", Path("tests/resources/files"), "md5"
            )
            is None
        )
    if not WINDOWS:  # For some reason, the values don't get mocked on Windows
        # Covering _root_deleted
        with patch("PyQt5.QtCore.QObject.sender") as mock_sender, patch(
            "nxdrive.gui.application.Application.question"
        ) as mock_question:
            mock_question.return_value = mock_qt
            mock_engine = Mock_Engine()
            mock_sender.return_value = mock_engine
            assert app._root_deleted() is None
        # Covering root_moved
        with patch(
            "nxdrive.gui.application.Application.question"
        ) as mock_question, patch("PyQt5.QtCore.QObject.sender") as mock_sender:
            mock_question.return_value = mock_qt
            mock_engine = Mock_Engine()
            mock_sender.return_value = mock_engine
            assert app._root_moved(Path("tests/resources")) is None
        # Covering doc_deleted
        with patch(
            "nxdrive.gui.application.Application.question"
        ) as mock_question, patch("PyQt5.QtCore.QObject.sender") as mock_sender:
            mock_question.return_value = mock_qt
            mock_engine = Mock_Engine()
            mock_sender.return_value = mock_engine
            assert app._doc_deleted(Path("tests/resources/files/testFile.txt")) is None
        # Covering file_already_exists
        with patch(
            "nxdrive.gui.application.Application.question"
        ) as mock_question, patch("PyQt5.QtCore.QObject.sender") as mock_sender, patch(
            "pathlib.Path.unlink"
        ) as mock_unlink:
            mock_question.return_value = mock_qt
            mock_engine = Mock_Engine()
            mock_sender.return_value = mock_engine
            mock_unlink.return_value = None
            assert (
                app._file_already_exists(
                    Path("tests/resources/files/testFile.txt"),
                    Path("tests/resources/files/testFile.txt"),
                )
                is None
            )
        # Covering open_authentication_dialog
        Options.is_frozen = True
        assert app.open_authentication_dialog("url", {"server_url": "value"}) is None
        Options.is_frozen = False
        assert (
            app.open_authentication_dialog("url", {"server_url": "url_value"}) is None
        )
    # Covering confirm_deletion
    with patch("nxdrive.gui.application.Application.question") as mock_question:
        mock_question.return_value = mock_qt
        assert isinstance(app.confirm_deletion(Path("tests/resources")), DelAction)
    # Covering show_systray
    assert app.show_systray() is None
    with patch("PyQt5.QtWidgets.QStyle.alignedRect") as mock_align_rect:
        mock_align_rect.return_value = QRect()
        # Covering show_filters
        assert app.show_filters(engine) is None
        # Covering show_conflicts_resolution
        assert app.show_conflicts_resolution(engine) is None
        # Covering show_settings
        assert app.show_settings("About") is None
        # Covering _show_direct_transfer_window
        assert app._show_direct_transfer_window() is None
    # Covering folder_duplicate_warning
    duplicates = ["dup1", "dup2", "dup3", "dup4", "dup5"]
    assert app.folder_duplicate_warning(duplicates, "remote_path", "remote_url") is None
    # Covering confirm_cancel_transfer
    with patch("nxdrive.gui.application.Application.question") as mock_question:
        mock_question.return_value = mock_qt
        uid = list(app.manager.engines.keys())[0]
        assert app.confirm_cancel_transfer(uid, 1, "localhost") is None
        assert app.confirm_cancel_transfer("engine_uid", 1, "localhost") is None
    # Covering confirm_cancel_session
    with patch("nxdrive.gui.application.Application.question") as mock_question:
        mock_question.return_value = mock_qt
        uid = list(app.manager.engines.keys())[0]
        assert app.confirm_cancel_session(uid, 1, "localhost", 1) is True
    # Covering exit_app
    assert app.exit_app() is None
    # Covering _shutdown
    app.app_engine = object()
    app.task_manager_window = object()
    assert app._shutdown() is None

    # Covering open_server_folders in QMLDriveApi
    with patch("nxdrive.gui.api.QMLDriveApi._get_engine") as mock_engine, patch(
        "nxdrive.gui.application.Application.hide_systray"
    ) as mock_hide:
        drive_api = QMLDriveApi(app)
        mock_engine.return_value = engine
        mock_hide.return_value = None
        assert drive_api.open_server_folders("engine.uid") is None

    # Functional test case written as part of user story : https://hyland.atlassian.net/browse/NXDRIVE-3011
    # Covers the changes made for Direct Transfer with workspace path specified from WebUI
    mock_url = (
        "nxdrive://direct-transfer/https/random.com/nuxeo/default-domain/UserWorkspaces"
    )
    mock_url2 = f"nxdrive://direct-transfer/{engine.local_folder}"
    assert app._handle_nxdrive_url(mock_url) is True
    assert app._handle_nxdrive_url(mock_url2) is True


@pytest.fixture
def dialog(app_obj, manager_factory):
    manager, engine = manager_factory()
    app = app_obj
    return FoldersDialog(app, engine, None)


def test_add_valid_single_file_within_limit(tmp_path, dialog):
    test_file = tmp_path / "file1.txt"
    test_file.write_bytes(b"A" * 1024 * 100)  # 100 KB

    original_limit = Options.direct_transfer_file_upper_limit
    Options.direct_transfer_file_upper_limit = 1  # MB

    try:
        dialog._process_additionnal_local_paths([str(test_file)])
    finally:
        Options.direct_transfer_file_upper_limit = original_limit

    assert test_file in dialog.paths
    assert dialog.paths[test_file] == 102400


def test_skip_file_exceeding_limit(tmp_path, dialog):
    test_file = tmp_path / "big_file.txt"
    test_file.write_bytes(b"A" * 1024 * 1024 * 10)  # 10 MB

    original_limit = Options.direct_transfer_file_upper_limit
    Options.direct_transfer_file_upper_limit = 5  # MB

    try:
        dialog._process_additionnal_local_paths([str(test_file)])
    finally:
        Options.direct_transfer_file_upper_limit = original_limit

    assert test_file not in dialog.paths
    assert "big_file.txt" in dialog.local_path_msg_lbl.text()


def test_ignore_zero_byte_file(tmp_path, dialog):
    test_file = tmp_path / "empty.txt"
    test_file.touch()  # Zero-byte

    dialog._process_additionnal_local_paths([str(test_file)])
    assert test_file not in dialog.paths


def test_duplicate_file_skipped(tmp_path, dialog):
    test_file = tmp_path / "file.txt"
    test_file.write_text("Hello")

    dialog.paths[test_file] = 5  # Already added

    dialog._process_additionnal_local_paths([str(test_file)])
    assert len(dialog.paths) == 1


def test_multiple_files_exceeding_combined_limit(tmp_path, dialog):
    # Create two files: each 6 MB, total = 12 MB
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"
    file1.write_bytes(b"A" * 1024 * 1024 * 6)
    file2.write_bytes(b"A" * 1024 * 1024 * 6)

    # Set the combined multiple files size limit to 10 MB
    original_limit = Options.direct_transfer_file_upper_limit
    Options.direct_transfer_folder_upper_limit = 10  # MB

    try:
        dialog._process_additionnal_local_paths([str(file1), str(file2)])
    finally:
        Options.direct_transfer_folder_upper_limit = original_limit

    assert file1 not in dialog.paths
    assert file2 not in dialog.paths
    assert "Combined file size exceeds limit" in dialog.local_path_msg_lbl.text()


def test_directory_within_folder_limit(tmp_path, dialog):
    dir_path = tmp_path / "my_folder"
    dir_path.mkdir()
    (dir_path / "file1.txt").write_bytes(b"A" * 1024 * 100)  # 100 KB
    (dir_path / "file2.txt").write_bytes(b"A" * 1024 * 200)  # 200 KB

    files = [(dir_path / "file1.txt", 102400), (dir_path / "file2.txt", 204800)]

    with patch("nxdrive.gui.folders_dialog.get_tree_list", return_value=files):
        original_limit = Options.direct_transfer_folder_upper_limit
        Options.direct_transfer_folder_upper_limit = 5  # MB

        try:
            dialog._process_additionnal_local_paths([str(dir_path)])
        finally:
            Options.direct_transfer_folder_upper_limit = original_limit

    assert (dir_path / "file1.txt") in dialog.paths
    assert (dir_path / "file2.txt") in dialog.paths


def test_skip_directory_exceeding_folder_limit(tmp_path, dialog):
    dir_path = tmp_path / "big_folder"
    dir_path.mkdir()
    (dir_path / "file.txt").write_bytes(b"A" * 1024 * 1024 * 10)  # 10 MB

    files = [(dir_path / "file.txt", 10 * 1024 * 1024)]

    with patch("nxdrive.gui.folders_dialog.get_tree_list", return_value=files):
        original_limit = Options.direct_transfer_folder_upper_limit
        Options.direct_transfer_folder_upper_limit = 5  # MB

        try:
            dialog._process_additionnal_local_paths([str(dir_path)])
        finally:
            Options.direct_transfer_folder_upper_limit = original_limit

    assert not dialog.paths
    assert "big_folder" in dialog.local_path_msg_lbl.text()
