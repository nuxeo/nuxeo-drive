from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
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
    # application.manager.preferences_metrics_chosen = True
    # application.manager.old_version = "1.0.0"
    # application.manager.version = "1.1.0"
    application.workflow = workflow
    return application


@pytest.fixture()
def workflow_worker(manager_factory, application, workflow):
    # Create a WorkflowWorker instance with mocked dependencies
    manager = manager_factory()
    worker = WorkflowWorker(manager)
    worker.app = application
    worker.workflow = workflow
    return worker


def test_refresh_list(manager_factory, workflow, application):
    manager, engine = manager_factory()
    application_ = application
    application_.api = Mock()
    application_.task_manager_window = Mock()
    engine_model = EngineModel(application_)
    engine_model.engines_uid = [engine.uid]

    application_.engine_model = engine_model
    application_.last_engine_uid = engine.uid
    application_.show_hide_refresh_button = Mock()

    manager.application = application_

    worker_ = WorkflowWorker(manager)
    worker_.manager = manager
    worker_.app = application()
    worker_.app.api = QMLDriveApi(application_)
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

    Feature.tasks_management = True

    with patch.object(worker_.app.api, "get_Tasks_list", new=get_Tasks_list_):
        assert worker_._poll()

    worker_.app.last_engine_uid = engine.uid
    worker_.app.api.engine_changed = True
    with patch.object(worker_.app.api, "get_Tasks_list", new=get_Tasks_list_):
        assert worker_._poll()
