from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from nuxeo.models import Document, Task

from nxdrive.client.remote_client import Remote
from nxdrive.client.workflow import Workflow
from nxdrive.gui.api import QMLDriveApi
from nxdrive.gui.application import Application
from nxdrive.gui.view import EngineModel
from nxdrive.poll_workers import WorkflowWorker


@pytest.fixture()
def task():
    task = Task
    task.id = str(uuid4())
    task.targetDocumentIds = [{"id": f"{uuid4()}"}]
    datetime_30_min_ago = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
    task.created = datetime_30_min_ago.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
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
    return application


@pytest.fixture()
def workflow_worker(manager, application, workflow):
    # Create a WorkflowWorker instance with mocked dependencies
    worker = WorkflowWorker(manager)
    worker.app = application
    worker.workflow = workflow
    return worker


def test_get_pending_task_for_no_doc(workflow, engine, remote):
    # No response from api for pending task
    remote.tasks.get = Mock(return_value=[])
    assert workflow.get_pending_tasks(engine) is None


def test_get_pending_task_for_single_doc(workflow, engine, task, remote):
    # Triggered through polling for single task
    remote.tasks.get = Mock(return_value=[task])
    workflow.fetch_document = Mock()
    assert workflow.get_pending_tasks(engine, False) is None


def test_get_pending_task_for_multiple_doc(workflow, engine, task, remote):
    # Triggered through polling for multiple task
    remote.tasks.get = Mock(return_value=[task, task])
    engine.send_task_notification = Mock()
    assert workflow.get_pending_tasks(engine, False) is None


def test_filtered_task(workflow, engine, task, remote):
    # No new task during an hour
    datetime_30_min_ago = datetime.now(tz=timezone.utc) - timedelta(minutes=160)
    task.created = datetime_30_min_ago.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
    remote.tasks.get = Mock(return_value=[task])
    engine.send_task_notification = Mock()
    assert workflow.get_pending_tasks(engine, False) is None

    # raise exception
    task.created = None
    assert workflow.get_pending_tasks(engine, False) is None


def test_fetch_document(workflow, engine, task, remote):
    remote.documents.get = Mock(path="/doc_path/doc.txt")
    engine.send_task_notification = Mock()
    workflow.fetch_document([task], engine)

    # No response from remote.documents.get
    remote.documents.get = Mock(return_value=None)
    workflow.fetch_document([task], engine)


def test_poll_initial_trigger(workflow_worker, manager, application):
    # Test initial trigger via workflow worker
    workflow_worker._first_workflow_check = True
    assert workflow_worker._poll()

    # without manager
    workflow_worker.manager = None
    assert not workflow_worker._poll()

    # with engines
    engine_model = EngineModel(application)
    engine_model.engines_uid = ["engine_uid"]
    application.engine_model = engine_model
    manager.application = application
    manager.engines = {"engine_uid": "test_uid"}
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


def test_refresh_list(workflow, application, engine, remote, manager):
    engine_model = EngineModel(application)
    engine_model.engines_uid = ["engine_uid"]

    application.engine_model = engine_model

    manager.application = application
    manager.engines = {"engine_uid": "engine_uid"}

    worker_ = WorkflowWorker(manager)
    worker_.manager = manager
    worker_.app = application()
    worker_.app.api = QMLDriveApi(application)
    worker_.workflow = workflow
    worker_.app.api.last_task_list = ""
    worker_._first_workflow_check = False

    def get_Tasks_list_(*args, **kwargs):
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
        return [dummy_task]

    with patch.object(worker_.app.api, "get_Tasks_list", new=get_Tasks_list_):
        assert worker_._poll()
