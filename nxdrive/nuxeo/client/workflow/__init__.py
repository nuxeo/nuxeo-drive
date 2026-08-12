"""Nuxeo-specific Task Management for document reviews."""

from logging import getLogger
from typing import Dict, List

from nuxeo.models import Task

from nxdrive.drive.client.workflow import Workflow as _WorkflowBase
from nxdrive.drive.feature import Feature
from nxdrive.drive.utils import get_task_type
from nxdrive.nuxeo.engine.engine import Engine

log = getLogger(__name__)


class Workflow(_WorkflowBase):
    """Nuxeo-specific Workflow Management for document Review."""

    def fetch_document(self, tasks_list: Dict, engine: Engine) -> None:
        """Fetch document details"""
        first_task = tasks_list[0]
        doc_id = first_task.targetDocumentIds[0]["id"]

        if response := engine.remote.get_info(doc_id, fetch_parent_uid=False):
            task_type = get_task_type(first_task.directive)
            engine.send_task_notification(first_task.id, response.path, task_type)
        else:
            log.error("Failed to fetch document details.")

    def get_pending_tasks(self, engine: Engine) -> List[Task]:  # type: ignore
        """Get Tasks for document review"""
        try:
            options = {"userId": engine.remote.user_id}
            if tasks := engine.remote.tasks.get(options):
                if tasks := self.remove_overdue_tasks(tasks):
                    tasks = self.update_user_task_data(tasks, options["userId"])

                if tasks and Feature.tasks_management:
                    if len(tasks) > 1:
                        # Send generic notification for multiple tasks
                        engine.send_task_notification(
                            tasks[0].targetDocumentIds[0]["id"],
                            "",
                            "REVIEW_DOCUMENT",
                        )
                    else:
                        # Fetch document data
                        self.fetch_document(tasks, engine)
                else:
                    log.info("No Task for processing...")
            else:
                self.clean_user_task_data(options["userId"])
                log.info("No Task for processing...")
        except Exception as exec:
            log.error(f"Exception occurred while Fetching Tasks: {exec}")
