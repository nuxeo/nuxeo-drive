from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from nuxeo.models import Document, Task

from nxdrive.client.remote_client import Remote


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


def test_get_pending_task_for_no_doc(workflow, engine, task, remote):
    # No response from api for pending task
    remote.tasks.get = Mock(return_value=[])
    assert workflow.get_pending_tasks(workflow, engine) is None


def test_get_pending_task_for_single_doc(workflow, engine, task, remote):
    # Triggered through polling for single task
    remote.tasks.get = Mock(return_value=[task])
    workflow.fetch_document = Mock()
    assert workflow.get_pending_tasks(workflow, engine, False) is None


def test_get_pending_task_for_multiple_doc(workflow, engine, task, remote):
    # Triggered through polling for multiple task
    remote.tasks.get = Mock(return_value=[task, task])
    engine.send_task_notification = Mock()
    assert workflow.get_pending_tasks(workflow, engine, False) is None


def test_filtered_task(workflow, engine, task, remote):
    # No new task during an hour
    datetime_30_min_ago = datetime.now(tz=timezone.utc) - timedelta(minutes=160)
    task.created = datetime_30_min_ago.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
    remote.tasks.get = Mock(return_value=[task])
    engine.send_task_notification = Mock()
    assert workflow.get_pending_tasks(workflow, engine, False) is None

    # raise exception
    task.created = None
    assert workflow.get_pending_tasks(workflow, engine, False) is None


def test_fetch_document(workflow, engine, task, remote):
    remote.documents.get = Mock(path="/doc_path/doc.txt")
    engine.send_task_notification = Mock()
    workflow.fetch_document(workflow, [task], engine)

    # No response from remote.documents.get
    remote.documents.get = Mock(return_value=None)
    workflow.fetch_document(workflow, [task], engine)
