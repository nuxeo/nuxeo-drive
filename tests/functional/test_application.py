"""
Functional tests for nxdrive/gui/application.py
"""

from pathlib import Path
from unittest.mock import patch

from PyQt5.QtCore import QObject

from nxdrive.gui.application import Application
from tests.functional.mocked_classes import Mock_Engine, Mock_Qt

from ..markers import mac_only, not_linux, windows_only


@not_linux(reason="Qt does not work correctly on Linux")
def test_exit_app(manager_factory):
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
    ) as mock_download_repr:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        app = Application(manager)
        assert app.exit_app() is None


@not_linux(reason="Qt does not work correctly on Linux")
def test_shutdown(manager_factory):
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
    ) as mock_download_repr:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        app = Application(manager)
        assert app._shutdown() is None


@windows_only
def test_create_custom_window_for_task_manager(manager_factory):
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
    ) as mock_download_repr:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        app = Application(manager)
        assert app.create_custom_window_for_task_manager() is None


@not_linux(reason="Qt does not work correctly on Linux")
def test_update_workflow(manager_factory):
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
    ) as mock_download_repr:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        app = Application(manager)
        assert app.update_workflow() is None


@not_linux(reason="Qt does not work correctly on Linux")
def test_update_feature_state(manager_factory):
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
    ) as mock_download_repr:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        app = Application(manager)
        assert app._update_feature_state("tasks_management", True) is None


@mac_only
def test_msbox(manager_factory):
    from PyQt5.QtWidgets import QMessageBox

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
        "PyQt5.QtWidgets.QDialog.exec_"
    ) as mock_exec, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_exec.return_value = None
        mock_execute.return_value = None
        app = Application(manager)
        assert isinstance(app._msgbox(), QMessageBox)


# @mac_only
# def test_direct_edit_conflict(manager_factory):
#     manager, engine = manager_factory()
#     mock_qt = Mock_Qt()
#     with patch(
#         "PyQt5.QtQml.QQmlApplicationEngine.rootObjects"
#     ) as mock_root_objects, patch(
#         "PyQt5.QtCore.QObject.findChild"
#     ) as mock_find_child, patch(
#         "nxdrive.gui.application.Application.init_nxdrive_listener"
#     ) as mock_listener, patch(
#         "nxdrive.gui.application.Application.show_metrics_acceptance"
#     ) as mock_show_metrics, patch(
#         "nxdrive.engine.activity.FileAction.__repr__"
#     ) as mock_download_repr, patch(
#         "PyQt5.QtWidgets.QDialog.exec_"
#     ) as mock_exec, patch(
#         "nxdrive.engine.workers.PollWorker._execute"
#     ) as mock_execute:
#         mock_root_objects.return_value = [QObject()]
#         mock_find_child.return_value = mock_qt
#         mock_listener.return_value = None
#         mock_show_metrics.return_value = None
#         mock_download_repr.return_value = "Nuxeo Drive"
#         mock_exec.return_value = None
#         mock_execute.return_value = None
#         app = Application(manager)
#         assert (
#             app._direct_edit_conflict("dummy_file_name", "dummr_ref_path", "md5")
#             is None
#         )


@mac_only
def test_root_moved(manager_factory):
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
        "PyQt5.QtWidgets.QDialog.exec_"
    ) as mock_exec, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute, patch(
        "PyQt5.QtCore.QObject.sender"
    ) as mock_engine:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_exec.return_value = None
        mock_execute.return_value = None
        mock_engine.return_value = Mock_Engine()
        app = Application(manager)
        assert app._root_moved(Path("tests/resources")) is None
