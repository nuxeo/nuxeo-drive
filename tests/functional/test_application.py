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

from nxdrive.gui.api import QMLDriveApi
from nxdrive.gui.application import Application
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
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
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
        mock_task_manager.return_value = None
        mock_execute.return_value = None
        mock_run.return_value = None
        mock_exec.return_value = None
        mock_question.return_value = None
        app = Application(manager)
        yield app


@not_linux(reason="Qt does not work correctly on linux")
def test_application(app_obj, manager_factory):
    from PyQt5.QtWidgets import QMessageBox

    from nxdrive.constants import DelAction

    app = app_obj
    mock_qt = Mock_Qt()
    # create_custom_window_for_task_manager
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
    # update_workflow
    assert app.update_workflow() is None
    # updat_feature_state
    assert app._update_feature_state("auto_update", True) is None
    # _msbox
    assert isinstance(app._msgbox(), QMessageBox)
    # display_info
    assert (
        app.display_info("Warning title", "Warning message", ["value1", "value2"])
        is None
    )
    # display_warning
    with patch("nxdrive.gui.application.Application._msgbox") as mock_msgbox:
        mock_msgbox.return_value = None
        assert (
            app.display_warning(
                "Warning title", "Warning message", ["value1", "value2"]
            )
            is None
        )
    # direct_edit_conflict
    with patch("nxdrive.gui.application.Application.question") as mock_question:
        mock_question.return_value = mock_qt
        assert (
            app._direct_edit_conflict(
                "dummy_filename", Path("tests/resources/files"), "md5"
            )
            is None
        )
    # _root_deleted
    with patch("PyQt5.QtCore.QObject.sender") as mock_sender, patch(
        "nxdrive.gui.application.Application.question"
    ) as mock_question:
        mock_question.return_value = mock_qt
        mock_engine = Mock_Engine()
        mock_sender.return_value = mock_engine
        assert app._root_deleted() is None
    # root_moved
    with patch("nxdrive.gui.application.Application.question") as mock_question, patch(
        "PyQt5.QtCore.QObject.sender"
    ) as mock_sender:
        mock_question.return_value = mock_qt
        mock_engine = Mock_Engine()
        mock_sender.return_value = mock_engine
        assert app._root_moved(Path("tests/resources")) is None
    # confirm_deletion
    with patch("nxdrive.gui.application.Application.question") as mock_question:
        mock_question.return_value = mock_qt
        assert isinstance(app.confirm_deletion(Path("tests/resources")), DelAction)
    # doc_deleted
    with patch("nxdrive.gui.application.Application.question") as mock_question, patch(
        "PyQt5.QtCore.QObject.sender"
    ) as mock_sender:
        mock_question.return_value = mock_qt
        mock_engine = Mock_Engine()
        mock_sender.return_value = mock_engine
        assert app._doc_deleted(Path("tests/resources/files/testFile.txt")) is None
    # file_already_exists
    with patch("nxdrive.gui.application.Application.question") as mock_question, patch(
        "PyQt5.QtCore.QObject.sender"
    ) as mock_sender, patch("pathlib.Path.unlink") as mock_unlink:
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
    # exit_app
    assert app.exit_app() is None
    # _shutdown
    app.app_engine = object()
    app.task_manager_window = object()
    assert app._shutdown() is None

    # open_server_folders in QMLDriveApi
    with patch("nxdrive.gui.api.QMLDriveApi._get_engine") as mock_engine, patch(
        "nxdrive.gui.application.Application.hide_systray"
    ) as mock_hide:
        manager, engine = manager_factory()
        drive_api = QMLDriveApi(app)
        mock_engine.return_value = engine
        mock_hide.return_value = None
        assert drive_api.open_server_folders("engine.uid") is None

    # Functional test case written as part of user story : https://hyland.atlassian.net/browse/NXDRIVE-3011
    # Covers the changes made for Direct Transfer with workspace path specified from WebUI
    mock_url = (
        "nxdrive://direct-transfer/https/random.com/nuxeo/default-domain/UserWorkspaces"
    )
    mock_url2 = f"nxdrive://direct-transfer{engine.local_folder}"
    assert app._handle_nxdrive_url(mock_url) is True
    assert app._handle_nxdrive_url(mock_url2) is True
