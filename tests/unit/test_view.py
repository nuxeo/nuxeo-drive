from typing import Any, List
from unittest.mock import Mock

from nxdrive.gui.view import FileModel, TasksModel
from nxdrive.qt.imports import QModelIndex
from nxdrive.translator import Translator


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


def test_tasksModel():  # manager_factory):
    # manager, engine = manager_factory()
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
    dummy_task1 = dummy_task
    dummy_task1.dueDate = "2023-04-09T08:31:04.365Z"
    dummy_task2 = dummy_task
    dummy_task2.dueDate = "2040-04-09T08:31:04.365Z"
    dummy_task_list = [dummy_task]

    def translate(message: str, /, *, values: List[Any] = None) -> str:
        return Translator.get(message, values=values)

    tasks_model = TasksModel(translate)
    tasks_model.loadList(dummy_task_list, "Administrator")
    assert isinstance(tasks_model, TasksModel)
    assert tasks_model.model
    assert tasks_model.self_model
