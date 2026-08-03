"""Unit tests for nxdrive.nuxeo.client.workflow module."""

from unittest.mock import Mock, patch

from nxdrive.nuxeo.client.workflow import Workflow


def _make_workflow():
    with patch.object(Workflow, "__init__", return_value=None):
        wf = Workflow.__new__(Workflow)
    wf._user_task_data = {}
    return wf


class TestFetchDocument:
    def test_fetches_and_sends_notification(self):
        wf = _make_workflow()
        engine = Mock()
        task = Mock()
        task.targetDocumentIds = [{"id": "doc-1"}]
        task.id = "task-1"
        task.directive = "wc:submit"

        doc_info = Mock()
        doc_info.path = "/ws/MyDoc"
        engine.remote.get_info.return_value = doc_info

        with patch(
            "nxdrive.nuxeo.client.workflow.get_task_type", return_value="REVIEW"
        ):
            wf.fetch_document([task], engine)

        engine.send_task_notification.assert_called_once_with(
            "task-1", "/ws/MyDoc", "REVIEW"
        )

    def test_logs_error_on_no_response(self):
        wf = _make_workflow()
        engine = Mock()
        task = Mock()
        task.targetDocumentIds = [{"id": "doc-1"}]
        task.directive = "wc:submit"
        engine.remote.get_info.return_value = None

        with patch("nxdrive.nuxeo.client.workflow.get_task_type"):
            wf.fetch_document([task], engine)
        engine.send_task_notification.assert_not_called()


class TestGetPendingTasks:
    def test_no_tasks_cleans_data(self):
        wf = _make_workflow()
        wf.clean_user_task_data = Mock()
        engine = Mock()
        engine.remote.user_id = "user1"
        engine.remote.tasks.get.return_value = []

        wf.get_pending_tasks(engine)
        wf.clean_user_task_data.assert_called_once_with("user1")

    def test_single_task_fetches_document(self):
        wf = _make_workflow()
        wf.remove_overdue_tasks = Mock(side_effect=lambda x: x)
        wf.update_user_task_data = Mock(side_effect=lambda x, y: x)
        wf.fetch_document = Mock()

        engine = Mock()
        engine.remote.user_id = "user1"
        task = Mock()
        task.targetDocumentIds = [{"id": "doc-1"}]
        engine.remote.tasks.get.return_value = [task]

        with patch("nxdrive.nuxeo.client.workflow.Feature") as mock_feat:
            mock_feat.tasks_management = True
            wf.get_pending_tasks(engine)

        wf.fetch_document.assert_called_once_with([task], engine)

    def test_multiple_tasks_sends_generic_notification(self):
        wf = _make_workflow()
        wf.remove_overdue_tasks = Mock(side_effect=lambda x: x)
        wf.update_user_task_data = Mock(side_effect=lambda x, y: x)

        engine = Mock()
        engine.remote.user_id = "user1"
        task1 = Mock()
        task1.targetDocumentIds = [{"id": "doc-1"}]
        task2 = Mock()
        task2.targetDocumentIds = [{"id": "doc-2"}]
        engine.remote.tasks.get.return_value = [task1, task2]

        with patch("nxdrive.nuxeo.client.workflow.Feature") as mock_feat:
            mock_feat.tasks_management = True
            wf.get_pending_tasks(engine)

        engine.send_task_notification.assert_called_once_with(
            "doc-1", "", "REVIEW_DOCUMENT"
        )

    def test_exception_does_not_propagate(self):
        wf = _make_workflow()
        engine = Mock()
        engine.remote.user_id = "user1"
        engine.remote.tasks.get.side_effect = RuntimeError("connection error")

        # Should not raise
        wf.get_pending_tasks(engine)

    def test_tasks_management_disabled(self):
        wf = _make_workflow()
        wf.remove_overdue_tasks = Mock(side_effect=lambda x: x)
        wf.update_user_task_data = Mock(side_effect=lambda x, y: x)
        wf.fetch_document = Mock()

        engine = Mock()
        engine.remote.user_id = "user1"
        task = Mock()
        task.targetDocumentIds = [{"id": "doc-1"}]
        engine.remote.tasks.get.return_value = [task]

        with patch("nxdrive.nuxeo.client.workflow.Feature") as mock_feat:
            mock_feat.tasks_management = False
            wf.get_pending_tasks(engine)

        wf.fetch_document.assert_not_called()
        engine.send_task_notification.assert_not_called()
