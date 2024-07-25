from copy import deepcopy
from typing import Any, List
from unittest.mock import Mock

import pytest

from nxdrive.client.workflow import Workflow
from nxdrive.gui.application import Application
from nxdrive.gui.view import EngineModel, FileModel, TasksModel
from nxdrive.qt.imports import QModelIndex
from nxdrive.translator import Translator
from nxdrive.utils import find_resource


def test_foldersDialog():
    def func():
        return True

    file_model = FileModel(func)
    returned_val = file_model.add_files([{"key": "val"}])
    assert not returned_val


def test_set_progress(direct_transfer_model):
    """Test the finalize state after 100% progress"""
    action = {
        "engine": "51a2c2dc641311ee87fb...bfc0ec09fa",
        "doc_pair": 1,
        "progress": "100",
        "action_type": "Linking",
        "finalizing_status": "Finalize the status",
    }

    direct_transfer_model.createIndex = Mock(return_value=1)
    direct_transfer_model.setData = Mock()
    direct_transfer_model.set_progress(direct_transfer_model, action)


def test_data(direct_transfer_model):
    """Test get row data as per role"""
    index = QModelIndex
    index.row = Mock(return_value=0)
    direct_transfer_model.data(
        direct_transfer_model, index, direct_transfer_model.FINALIZING_STATUS
    )


def test_tasksModel():
    Translator(find_resource("i18n"), lang="en")

    dummy_task = Mock()
    dummy_task.actors = [{"id": "user:Administrator"}]
    dummy_task.created = "2024-04-04T08:31:04.366Z"
    dummy_task.directive = "wf.serialDocumentReview.AcceptReject"
    dummy_task.dueDate = "2024-04-09T08:31:04.365Z"
    dummy_task.id = "e7fc7a3a-5c39-479f-8382-65ed08e8116d"
    dummy_task.name = "wf.serialDocumentReview.DocumentValidation"
    dummy_task.targetDocumentIds = [{"id": "5b77e4dd-c155-410b-9d4d-e72f499638b8"}]
    dummy_task.workflowInstanceId = "81133cf7-38d9-483c-9a0b-c98fc02822a0"
    dummy_task.workflowModelName = "SerialDocumentReview"
    dummy_task1 = deepcopy(dummy_task)
    dummy_task1.dueDate = "2023-04-09T08:31:04.365Z"
    dummy_task2 = deepcopy(dummy_task)
    dummy_task2.dueDate = "2040-04-09T08:31:04.365Z"
    dummy_task2.actors = [{"id": "Administrator"}]
    dummy_task_list = [dummy_task, dummy_task1, dummy_task2]

    def translate(message: str, /, *, values: List[Any] = None) -> str:
        return Translator.get(message, values=values)

    tasks_model = TasksModel(translate)
    tasks_model.loadList(dummy_task_list, "Administrator")

    assert isinstance(tasks_model, TasksModel)
    assert tasks_model.model
    assert tasks_model.self_model

    dummy_task_list = [dummy_task, dummy_task1]
    assert not tasks_model.loadList(dummy_task_list, "Administrator")

    dummy_task_list = [dummy_task1, dummy_task2]
    assert not tasks_model.loadList(dummy_task_list, "Administrator")

    dummy_task_list = [dummy_task2]
    assert not tasks_model.loadList(dummy_task_list, "Administrator")


@pytest.fixture()
def workflow():
    return Workflow()


@pytest.fixture()
def application(manager_factory, workflow):
    manager = manager_factory()
    application = Mock(spec=Application)
    application.manager = manager
    application._init_translator = Mock()
    application.setWindowIcon = Mock()
    application.setApplicationName = Mock()
    application.setQuitOnLastWindowClosed = Mock()
    application.show_metrics_acceptance = Mock()
    application.init_checks = Mock()
    application._setup_notification_center = Mock()
    application.workflow = workflow

    return application


def test_engine_model():
    application_ = application
    application_.api = Mock()
    application_.update_workflow = Mock()
    application_.update_workflow_user_engine_list = Mock()
    application_.manager = Mock()
    application_.manager.engines = {"dummy_uid": "dummy_engine"}
    engine_model = EngineModel(application_)
    engine_model.beginInsertRows = Mock()
    engine_model.endInsertRows = Mock()
    engine_model._connect_engine = Mock()
    engine_model.removeRows = Mock()
    assert not engine_model.addEngine("dummy_uid")
    assert not engine_model.removeEngine("dummy_uid")
