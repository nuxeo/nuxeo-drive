"""Unit tests for nxdrive.drive.client.workflow module."""

from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

import pytest

from nxdrive.drive.client.workflow import Workflow


@pytest.fixture
def workflow():
    wf = Workflow()
    wf.user_task_list = {}
    return wf


def _make_task(task_id, due_offset_hours=24):
    """Create a mock task with a dueDate offset from now."""
    task = Mock()
    task.id = task_id
    due = datetime.now(tz=timezone.utc) + timedelta(hours=due_offset_hours)
    task.dueDate = due.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
    return task


class TestUpdateUserTaskData:
    def test_new_user_adds_all_tasks(self, workflow):
        tasks = [_make_task("t1"), _make_task("t2")]
        result = workflow.update_user_task_data(tasks, "user1")
        assert result == tasks
        assert workflow.user_task_list["user1"] == ["t1", "t2"]

    def test_new_tasks_returned(self, workflow):
        workflow.user_task_list["user1"] = ["t1"]
        t1 = _make_task("t1")
        t2 = _make_task("t2")
        result = workflow.update_user_task_data([t1, t2], "user1")
        assert len(result) == 1
        assert result[0].id == "t2"

    def test_removed_tasks_returns_empty(self, workflow):
        workflow.user_task_list["user1"] = ["t1", "t2"]
        t1 = _make_task("t1")
        result = workflow.update_user_task_data([t1], "user1")
        assert result == []
        assert "t2" not in workflow.user_task_list["user1"]

    def test_no_change_returns_empty(self, workflow):
        workflow.user_task_list["user1"] = ["t1", "t2"]
        t1 = _make_task("t1")
        t2 = _make_task("t2")
        result = workflow.update_user_task_data([t1, t2], "user1")
        assert result == []


class TestRemoveOverdueTasks:
    def test_removes_past_due(self, workflow):
        overdue = _make_task("old", due_offset_hours=-24)
        future = _make_task("new", due_offset_hours=24)
        result = Workflow.remove_overdue_tasks([overdue, future])
        assert len(result) == 1
        assert result[0].id == "new"

    def test_keeps_all_future(self, workflow):
        tasks = [_make_task("t1", 1), _make_task("t2", 48)]
        result = Workflow.remove_overdue_tasks(tasks)
        assert len(result) == 2


class TestCleanUserTaskData:
    def test_removes_user(self, workflow):
        workflow.user_task_list["user1"] = ["t1"]
        workflow.clean_user_task_data("user1")
        assert "user1" not in workflow.user_task_list

    def test_nonexistent_user_no_error(self, workflow):
        workflow.clean_user_task_data("ghost")

    def test_empty_userid_no_error(self, workflow):
        workflow.clean_user_task_data("")


class TestFetchDocumentRaises:
    def test_not_implemented(self, workflow):
        with pytest.raises(NotImplementedError):
            workflow.fetch_document([], Mock())


class TestGetPendingTasksRaises:
    def test_not_implemented(self, workflow):
        with pytest.raises(NotImplementedError):
            workflow.get_pending_tasks(Mock())
