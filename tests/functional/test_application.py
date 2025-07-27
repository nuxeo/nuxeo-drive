"""
Functional tests for nxdrive/gui/application.py

Known issue with pyinstaller and Windows on Github workflow
Hence, functional tests for application will be run only on Mac
https://github.com/orgs/pyinstaller/discussions/7287
"""

from pathlib import Path
from unittest.mock import patch

from PyQt5.QtCore import QObject

from nxdrive.gui.application import Application
from tests.functional.mocked_classes import Mock_Engine, Mock_Qt

from ..markers import mac_only


@mac_only
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
    ) as mock_download_repr, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute, patch(
        "nxdrive.engine.workers.Worker.run"
    ) as mock_run:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_task_manager.return_value = None
        mock_execute.return_value = None
        mock_run.return_value = None
        app = Application(manager)
        assert app.exit_app() is None
        app.exit(0)


@mac_only
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
    ) as mock_download_repr, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute, patch(
        "nxdrive.engine.workers.Worker.run"
    ) as mock_run:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_task_manager.return_value = None
        mock_execute.return_value = None
        mock_run.return_value = None
        app = Application(manager)
        assert app._shutdown() is None
        app.exit(0)


# @mac_only -- potential issue
# def test_create_custom_window_for_task_manager(manager_factory):
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
#         "nxdrive.gui.application.Application._fill_qml_context"
#     ) as mock_qml_context, patch(
#         "nxdrive.gui.application.CustomWindow"
#     ) as mock_custom_window, patch(
#         "" "tests.functional.mocked_classes.Mock_Qt.rootContext"
#     ) as mock_root_context, patch(
#         "nxdrive.engine.workers.PollWorker._execute"
#     ) as mock_execute, patch(
#         "nxdrive.engine.workers.Worker.run"
#     ) as mock_run:
#         mock_root_objects.return_value = [QObject()]
#         mock_find_child.return_value = mock_qt
#         mock_listener.return_value = None
#         mock_show_metrics.return_value = None
#         mock_download_repr.return_value = "Nuxeo Drive"
#         mock_qml_context.return_value = None
#         mock_custom_window.return_value = Mock_Qt
#         mock_root_context.return_value = None
#         mock_execute.return_value = None
#         mock_run.return_value = None
#         app = Application(manager)
#         assert app.create_custom_window_for_task_manager() is None
#         app.exit(0)


@mac_only
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
    ) as mock_download_repr, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute, patch(
        "nxdrive.engine.workers.Worker.run"
    ) as mock_run:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_task_manager.return_value = None
        mock_execute.return_value = None
        mock_run.return_value = None
        app = Application(manager)
        assert app.update_workflow() is None
        app.exit(0)


@mac_only
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
    ) as mock_download_repr, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_task_manager.return_value = None
        mock_execute.return_value = None
        app = Application(manager)
        assert app._update_feature_state("auto_update", True) is None
        app.exit(0)


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
    ) as mock_execute, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_exec.return_value = None
        mock_execute.return_value = None
        mock_task_manager.return_value = None
        app = Application(manager)
        assert isinstance(app._msgbox(), QMessageBox)
        app.exit(0)


@mac_only
def test_display_info(manager_factory):
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
        "nxdrive.gui.application.Application.translate"
    ) as mock_translate, patch(
        "nxdrive.gui.application.Application._msgbox"
    ) as mock_msgbox, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_translate.return_value = None
        mock_msgbox.return_value = None
        mock_task_manager.return_value = None
        mock_execute.return_value = None
        app = Application(manager)
        assert (
            app.display_info("Warning title", "Warning message", ["value1", "value2"])
            is None
        )
        app.exit(0)


@mac_only
def test_display_warning(manager_factory):
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
        "nxdrive.gui.application.Application.translate"
    ) as mock_translate, patch(
        "nxdrive.gui.application.Application._msgbox"
    ) as mock_msgbox, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_translate.return_value = None
        mock_msgbox.return_value = None
        mock_task_manager.return_value = None
        mock_execute.return_value = None
        app = Application(manager)
        assert (
            app.display_warning(
                "Warning title", "Warning message", ["value1", "value2"]
            )
            is None
        )
        app.exit(0)


@mac_only
def test_direct_edit_conflict(manager_factory):
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
        "nxdrive.gui.application.Application.translate"
    ) as mock_translate, patch(
        "nxdrive.gui.application.Application._msgbox"
    ) as mock_msgbox, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.gui.application.Application.question"
    ) as mock_question, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_translate.return_value = None
        mock_msgbox.return_value = None
        mock_task_manager.return_value = None
        mock_question.return_value = mock_qt
        mock_execute.return_value = None
        app = Application(manager)
        assert app._direct_edit_conflict("dummy_filename", "dummy_ref", "md5") is None
        app.exit(0)


@mac_only
def test_root_deleted(manager_factory):
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
        "nxdrive.gui.application.Application.translate"
    ) as mock_translate, patch(
        "nxdrive.gui.application.Application._msgbox"
    ) as mock_msgbox, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.gui.application.Application.question"
    ) as mock_question, patch(
        "PyQt5.QtCore.QObject.sender"
    ) as mock_sender, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_translate.return_value = None
        mock_msgbox.return_value = None
        mock_task_manager.return_value = None
        mock_question.return_value = mock_qt
        mock_engine = Mock_Engine()
        mock_sender.return_value = mock_engine
        mock_execute.return_value = None
        app = Application(manager)
        assert app._root_deleted() is None
        app.exit(0)


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
        "nxdrive.gui.application.Application.translate"
    ) as mock_translate, patch(
        "nxdrive.gui.application.Application._msgbox"
    ) as mock_msgbox, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.gui.application.Application.question"
    ) as mock_question, patch(
        "PyQt5.QtCore.QObject.sender"
    ) as mock_sender, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_translate.return_value = None
        mock_msgbox.return_value = None
        mock_task_manager.return_value = None
        mock_question.return_value = mock_qt
        mock_engine = Mock_Engine()
        mock_sender.return_value = mock_engine
        mock_execute.return_value = None
        app = Application(manager)
        assert app._root_moved(Path("tests/resources")) is None
        app.exit(0)


@mac_only
def test_confirm_deletion(manager_factory):
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
        "nxdrive.gui.application.Application.translate"
    ) as mock_translate, patch(
        "nxdrive.gui.application.Application._msgbox"
    ) as mock_msgbox, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.gui.application.Application.question"
    ) as mock_question, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        from nxdrive.constants import DelAction

        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_translate.return_value = None
        mock_msgbox.return_value = None
        mock_task_manager.return_value = None
        mock_question.return_value = mock_qt
        mock_execute.return_value = None
        app = Application(manager)
        assert isinstance(app.confirm_deletion(Path("tests/resources")), DelAction)


@mac_only
def test_doc_deleted(manager_factory):
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
        "nxdrive.gui.application.Application.translate"
    ) as mock_translate, patch(
        "nxdrive.gui.application.Application._msgbox"
    ) as mock_msgbox, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.gui.application.Application.question"
    ) as mock_question, patch(
        "PyQt5.QtCore.QObject.sender"
    ) as mock_sender, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_translate.return_value = None
        mock_msgbox.return_value = None
        mock_task_manager.return_value = None
        mock_question.return_value = mock_qt
        mock_engine = Mock_Engine()
        mock_sender.return_value = mock_engine
        mock_execute.return_value = None
        app = Application(manager)
        assert app._doc_deleted(Path("tests/resources/files/testFile.txt")) is None
        app.exit(0)


@mac_only
def test_file_already_exists(manager_factory):
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
        "nxdrive.gui.application.Application.translate"
    ) as mock_translate, patch(
        "nxdrive.gui.application.Application._msgbox"
    ) as mock_msgbox, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.gui.application.Application.question"
    ) as mock_question, patch(
        "PyQt5.QtCore.QObject.sender"
    ) as mock_sender, patch(
        "pathlib.Path.unlink"
    ) as mock_unlink, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_translate.return_value = None
        mock_msgbox.return_value = None
        mock_task_manager.return_value = None
        mock_question.return_value = mock_qt
        mock_execute.return_value = None
        mock_engine = Mock_Engine()
        mock_sender.return_value = mock_engine
        mock_unlink.return_value = None
        app = Application(manager)
        assert (
            app._file_already_exists(
                Path("tests/resources/files/testFile.txt"),
                Path("tests/resources/files/testFile.txt"),
            )
            is None
        )
        app.exit(0)


@mac_only
def test_show_systray(manager_factory):
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
        "nxdrive.gui.application.Application.translate"
    ) as mock_translate, patch(
        "nxdrive.gui.application.Application._msgbox"
    ) as mock_msgbox, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.gui.application.Application.question"
    ) as mock_question, patch(
        "PyQt5.QtCore.QObject.sender"
    ) as mock_sender, patch(
        "nxdrive.gui.application.Application.close_tasks_window"
    ) as mock_close_tasks, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_translate.return_value = None
        mock_msgbox.return_value = None
        mock_task_manager.return_value = None
        mock_question.return_value = mock_qt
        mock_engine = Mock_Engine()
        mock_sender.return_value = mock_engine
        mock_close_tasks.return_value = None
        mock_execute.return_value = None
        app = Application(manager)
        assert app.show_systray() is None
        app.exit(0)


@mac_only
def test_show_filters(manager_factory):
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
        "nxdrive.gui.application.Application.translate"
    ) as mock_translate, patch(
        "nxdrive.gui.application.Application._msgbox"
    ) as mock_msgbox, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.gui.application.Application.question"
    ) as mock_question, patch(
        "PyQt5.QtCore.QObject.sender"
    ) as mock_sender, patch(
        "nxdrive.gui.application.Application.close_tasks_window"
    ) as mock_close_tasks, patch(
        "nxdrive.gui.application.Application._center_on_screen"
    ) as mock_center_on_screen, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_translate.return_value = None
        mock_msgbox.return_value = None
        mock_task_manager.return_value = None
        mock_question.return_value = mock_qt
        mock_engine = Mock_Engine()
        mock_sender.return_value = mock_engine
        mock_close_tasks.return_value = None
        mock_center_on_screen.return_value = None
        mock_execute.return_value = None
        app = Application(manager)
        assert app.show_filters(engine) is None
        app.exit(0)


@mac_only
def test_show_server_folders(manager_factory):
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
        "nxdrive.gui.application.Application.translate"
    ) as mock_translate, patch(
        "nxdrive.gui.application.Application._msgbox"
    ) as mock_msgbox, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.gui.application.Application.close_tasks_window"
    ) as mock_close_tasks, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_translate.return_value = None
        mock_msgbox.return_value = None
        mock_task_manager.return_value = None
        mock_close_tasks.return_value = None
        mock_execute.return_value = None
        app = Application(manager)
        assert app.show_server_folders(engine, Path("tests/resources/files")) is None
        app.exit(0)
