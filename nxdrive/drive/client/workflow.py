"""Server-agnostic Workflow base class.

Provides the generic task-list management (``user_task_list`` tracking,
deduplication, overdue removal, cleanup).  Server-specific operations
(fetching pending tasks, sending notifications) are abstract and must be
supplied by a subclass (e.g. ``nuxeo/client/workflow/__init__.py``).
"""

from datetime import datetime, timezone
from logging import getLogger
from typing import Any, Dict, List

log = getLogger(__name__)


class Workflow:
    """Server-agnostic Workflow Management for document reviews.

    Subclass in each server-type package and override:
    - ``fetch_document()``
    - ``get_pending_tasks()``
    """

    user_task_list: Dict[str, List[str]] = {}

    def fetch_document(self, tasks_list: Any, engine: Any) -> None:
        """Fetch document details and send notification.  **Must be overridden.**"""
        raise NotImplementedError

    def get_pending_tasks(self, engine: Any) -> Any:
        """Get pending tasks for document review.  **Must be overridden.**"""
        raise NotImplementedError

    def update_user_task_data(self, tasks: List[Any], userId: str) -> List[Any]:
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

    @staticmethod
    def remove_overdue_tasks(tasks: List[Any]) -> List[Any]:
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
