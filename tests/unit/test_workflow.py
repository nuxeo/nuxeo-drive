from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from nuxeo.models import Document, Task

from nxdrive.client.remote_client import Remote
from nxdrive.client.workflow import Workflow
from nxdrive.feature import Feature
from nxdrive.gui.api import QMLDriveApi
from nxdrive.gui.application import Application
from nxdrive.gui.view import EngineModel
from nxdrive.poll_workers import WorkflowWorker


@pytest.fixture()
def task():
    task = Task
    task.id = "taskid_test"
    task.targetDocumentIds = [{"id": f"{uuid4()}"}]
    datetime_30_min_ago = datetime.now(tz=timezone.utc) + timedelta(minutes=30)
    task.dueDate = datetime_30_min_ago.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
    task.directive = ""
    return task


@pytest.fixture()
def remote():
    remote = Remote
    remote.documents = Document
    remote.user_id = f"{uuid4()}"
    remote.tasks = Task
    return remote


@pytest.fixture()
def workflow(remote):
    return Workflow(remote)


@pytest.fixture()
def engine(engine, remote):
    engine.remote = remote
    return engine


@pytest.fixture()
def application(manager, workflow):
    application = Mock(spec=Application)
    application.manager = manager
    application._init_translator = Mock()
    application.setWindowIcon = Mock()
    application.setApplicationName = Mock()
    application.setQuitOnLastWindowClosed = Mock()
    application.show_metrics_acceptance = Mock()
    application.init_checks = Mock()
    application._setup_notification_center = Mock()
    application.manager.preferences_metrics_chosen = True
    application.manager.old_version = "1.0.0"
    application.manager.version = "1.1.0"
    application.workflow = workflow
    application.last_engine_uid = ""
    return application


@pytest.fixture()
def workflow_worker(manager, application, workflow):
    # Create a WorkflowWorker instance with mocked dependencies
    worker = WorkflowWorker(manager)
    worker.app = application
    worker.workflow = workflow
    return worker


def test_get_pending_task_for_no_doc(workflow, engine, remote):
    # No response from api for pending task for user_a
    assert Workflow.user_task_list == {}

    remote.user_id = "user_a"
    engine.remote = remote
    engine.remote.tasks.get = Mock(return_value=[])
    assert workflow.get_pending_tasks(engine) is None

    # If no tasks assigned to user remove the ID
    Workflow.user_task_list = {"user_a": ["taskid_1"]}
    engine.remote.tasks.get = Mock(return_value=[])
    assert workflow.get_pending_tasks(engine) is None
    assert not Workflow.user_task_list


def test_get_pending_task_for_single_doc(workflow, engine, task, remote):
    # Triggered through polling for single task,
    # Add new key if it doesn't exist in user_task_list
    remote.user_id = "user_a"
    engine.remote = remote
    engine.remote.tasks.get = Mock(return_value=[task])
    workflow.fetch_document = Mock()
    assert workflow.get_pending_tasks(engine) is None
    assert Workflow.user_task_list == {"user_a": ["taskid_test"]}
    Workflow.user_task_list = {}


def test_get_pending_task_for_multiple_doc(workflow, engine, task, remote):
    # Triggered through polling for multiple task
    task1 = task
    task1.id = "taskid_1"
    task2 = task
    task2.id = "taskid_2"
    remote.user_id = "user_b"
    engine.remote = remote
    engine.remote.tasks.get = Mock(return_value=[task1, task2])
    engine.send_task_notification = Mock()
    assert workflow.get_pending_tasks(engine) is None

    # user_task_list[a_user] have [tasks_a, tasks_b] and got tasks[tasks_a, tasks_b].
    # In this case no need to the send notification
    assert workflow.get_pending_tasks(engine) is None

    Workflow.user_task_list = {}


def test_update_user_task_data(workflow, task):
    # Add new key if it doesn't exist in user_task_list
    workflow.update_user_task_data([task], "user_a")
    assert Workflow.user_task_list == {"user_a": ["taskid_test"]}

    # Remove taskid_test in user_task_list[user_a] and no notification in this case
    workflow.update_user_task_data([], "user_a")
    assert Workflow.user_task_list == {"user_a": []}

    # Add taskid_test in user_task_list[user_a] and send notification for taskid_a
    workflow.update_user_task_data([task], "user_a")
    assert Workflow.user_task_list == {"user_a": ["taskid_test"]}

    Workflow.user_task_list = {}


def test_remove_overdue_tasks(workflow, engine, task):
    # No new task during an hour
    datetime_1_hr_ago = datetime.now(tz=timezone.utc) - timedelta(minutes=160)
    task.dueDate = datetime_1_hr_ago.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
    engine.remote.tasks.get = Mock(return_value=[task])
    engine.send_task_notification = Mock()
    assert workflow.get_pending_tasks(engine) is None

    # raise exception
    task.dueDate = None
    assert workflow.get_pending_tasks(engine) is None


def test_fetch_document(workflow, engine, task):
    engine.remote.documents.get = Mock(path="/doc_path/doc.txt")
    engine.send_task_notification = Mock()
    workflow.fetch_document([task], engine)

    # send notification for directive
    task.directive = "chooseParticipants"
    workflow.fetch_document([task], engine)

    task.directive = "give_opinion"
    workflow.fetch_document([task], engine)

    task.directive = "AcceptReject"
    workflow.fetch_document([task], engine)

    task.directive = "consolidate"
    workflow.fetch_document([task], engine)

    task.directive = "updateRequest"
    workflow.fetch_document([task], engine)

    # No response from remote.documents.get
    engine.remote.documents.get = Mock(return_value=None)
    workflow.fetch_document([task], engine)


def test_poll_initial_trigger(workflow_worker, manager, application, engine):
    # Test initial trigger via workflow worker
    workflow_worker._first_workflow_check = True
    assert workflow_worker._poll()

    # without manager
    workflow_worker.manager = None
    assert not workflow_worker._poll()

    # Set tasks_management feature as True
    Feature.tasks_management = True

    # with engines
    engine_model = EngineModel(application)
    engine_model.engines_uid = ["engine_uid"]
    application.engine_model = engine_model
    manager.application = application
    manager.engines = {"engine_uid": engine}
    workflow_worker.manager = manager
    workflow_worker.workflow = Mock()
    assert workflow_worker._poll()


def test_api_display_pending_task_without_exec(application, manager, engine):
    engine.get_task_url = Mock(return_value="/doc_url")
    engine.open_remote = Mock()
    manager.engines = {"engine_uid": engine}
    application.manager = manager

    drive_api = QMLDriveApi(application)
    assert (
        drive_api.display_pending_task("engine_uid", str(uuid4()), "/doc_path") is None
    )


def test_api_display_pending_task_with_exec(application, manager):
    # Test exception handling
    manager.engines = {"engine_uid": "dummy_engine"}
    application.manager = manager

    drive_api = QMLDriveApi(application)
    assert (
        drive_api.display_pending_task("engine_uid", str(uuid4()), "/doc_path") is None
    )


def test_clean_user_data_when_unbind_engine(manager, engine):
    Workflow.user_task_list == {"user_a": ["dummy_taskid"]}
    engine.unbind = Mock()
    manager.dao = Mock()
    manager.dropEngine = Mock()
    manager.get_engines = Mock()
    manager.db_backup_worker = False
    Feature.tasks_management = True
    engine.remote = Remote
    engine.remote.user_id = "user_a"
    manager.engines = {"user_a": engine}
    manager.unbind_engine(manager, "user_a")

    assert "user_a" not in Workflow.user_task_list
