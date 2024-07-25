"""Task Management to check for pending document reviews and send notifications"""

from datetime import datetime, timezone
from logging import getLogger
from typing import Dict, List

from nuxeo.models import Task

from nxdrive.engine.engine import Engine

from ...feature import Feature
from ...utils import get_task_type

log = getLogger(__name__)


class Workflow:
    """Workflow Management for document Review"""

    user_task_list: Dict[str, List[str]] = {}

    def fetch_document(self, tasks_list: Dict, engine: Engine) -> None:
        """Fetch document details"""
        first_task = tasks_list[0]
        doc_id = first_task.targetDocumentIds[0]["id"]

        if response := engine.remote.get_info(doc_id, fetch_parent_uid=False):
            task_type = get_task_type(first_task.directive)
            engine.send_task_notification(first_task.id, response.path, task_type)
        else:
            log.error("Failed to fetch document details.")

    def update_user_task_data(self, tasks: List[Task], userId: str) -> List[Task]:
        """Update user_task_list for below scenarios
        1. Add new key if it doesn't exist in user_task_list
        2. If user_task_list[a_user] have [tasks_a, tasks_b] and got tasks[tasks_a, tasks_c] then
            a. Add tasks_c in user_task_list[a_user] and send notification.
            b. Remove tasks_b from user_task_list[a_user] and no notification in this case
        3. If user_task_list[a_user] have [tasks_a, tasks_b] and got tasks[tasks_a, tasks_b].
        In this case no need to the send notification
        """
        task_ids = [task.id for task in tasks]

        if userId not in self.user_task_list:
            self.user_task_list[userId] = task_ids
            return tasks
        # Get the existing task IDs for the user
        existing_task_ids = set(self.user_task_list[userId])

        # Determine new tasks added for the user
        if new_task_ids := set(task_ids).difference(existing_task_ids):
            self.user_task_list[userId] = task_ids
            return [task for task in tasks if task.id in new_task_ids]

        # Determine old/completed tasks to be removed
        if old_task_ids := existing_task_ids.difference(task_ids):
            self.user_task_list[userId] = [
                id for id in existing_task_ids if id not in old_task_ids
            ]
            return []

        # If no new tasks added or removed
        return []

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

    @staticmethod
    def remove_overdue_tasks(tasks: List[Task]) -> List[Task]:
        """Remove overdue tasks"""
        current_time = datetime.now(tz=timezone.utc)
        log.info("Remove overdue tasks")
        return [
            task
            for task in tasks
            if (
                datetime.strptime(task.dueDate, "%Y-%m-%dT%H:%M:%S.%f%z") > current_time
            )
        ]

    def clean_user_task_data(self, userId: str = "", /) -> None:
        """Remove user data for below scenarios:
        1. If no tasks assigned to user remove the ID
        2. If account has been removed than remove the ID if it exist
        """
        if userId and userId in self.user_task_list.keys():
            self.user_task_list.pop(userId)
