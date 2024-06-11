from datetime import datetime, timezone  # ,timedelta
from logging import getLogger
from typing import Dict, List

from nuxeo.models import Task

from nxdrive.engine.engine import Engine

from ..remote_client import Remote  # noqa

log = getLogger(__name__)


class Workflow:
    """Workflow Management for document Review"""

    user_task_list = {}

    def __init__(self, remote: "Remote") -> None:
        self.remote = remote
        # self.user_task_list = {}

    def fetch_document(self, tasks_list: Dict, engine: Engine) -> None:
        """Fetch document details"""
        first_task = tasks_list[0]
        doc_id = first_task.targetDocumentIds[0]["id"]
        task_id = first_task.id

        response = self.remote.documents.get(doc_id)
        if response:
            # check if user have to choose participants
            if "chooseParticipants" in first_task.directive:
                engine.send_task_notification(
                    task_id, response.path, "Choose Participants"
                )
            else:
                engine.send_task_notification(task_id, response.path, "Review Document")
        else:
            log.error("Failed to fetch document details.")

    def update_user_task_data(self, tasks: List[Task], userId: str) -> List[Task]:
        task_ids = [task.id for task in tasks]
        if userId not in self.user_task_list:
            self.user_task_list[userId] = task_ids
            print(f">>>> self.user_task_list: {self.user_task_list}")
            return tasks
        # print(set(tasks + user_task_list[userId]))
        new_task_ids = set(task_ids).difference(set(self.user_task_list[userId]))
        if new_task_ids:
            # new tasks added
            self.user_task_list[userId] = task_ids
            print(f">>>> self.user_task_list: {self.user_task_list}")
            return [task for task in tasks if task.id in new_task_ids]
            # if diff in self.user_task_list[userId]:
            #     self.user_task_list[userId].extend([task_id for task_id in diff])
            #     print(self.user_task_list)
        # if new tasks added and also removed tasks from existing list
        else:
            print("No new tasks")
            return []

        # print("diff: ", diff)
        # print("intersection: ", set(tasks).difference(set(self.user_task_list[userId])))
        # print(diff in self.user_task_list[userId])

    def get_pending_tasks(self, engine: Engine, initial_run: bool = True) -> List[Task]:  # type: ignore
        """Get Tasks for document review"""
        try:
            options = {"userId": engine.remote.user_id}
            print(f">>> user: {options}")
            tasks = self.remote.tasks.get(options)
            print(f">>>> self.user_task_list: {self.user_task_list}")
            if tasks:
                # tasks = self.filter_overdue_tasks(tasks)
                # Add tasks in global dictionary
                # self.update_user_task_data(tasks, self.remote.user_id)
                # if not initial_run:
                # tasks = self.filter_tasks(tasks)
                tasks = self.remove_overdue_tasks(tasks)
                if tasks:
                    tasks = self.update_user_task_data(tasks, self.remote.user_id)

                if tasks:
                    if len(tasks) > 1:
                        # Send generic notification for multiple tasks
                        engine.send_task_notification(
                            tasks[0].targetDocumentIds[0]["id"], "", "Review Document"
                        )
                    else:
                        # Fetch document data
                        self.fetch_document(tasks, engine)
                else:
                    log.info("No Task for processing...")
            else:
                log.info("No Task for processing...")
        except Exception as exec:
            log.error(f"Exception occurred while Fetching Tasks: {exec}")

    # @staticmethod
    # def filter_tasks(tasks: List[Task]) -> List[Task]:
    #     """Filter new tasks created within the last hour"""
    #     current_time = datetime.now(tz=timezone.utc)
    #     last_hour = current_time - timedelta(minutes=60)
    #     log.info("Filtering tasks created in the last hour.")
    #     return [
    #         task
    #         for task in tasks
    #         if (
    #             datetime.strptime(task.created, "%Y-%m-%dT%H:%M:%S.%f%z") > last_hour
    #             and datetime.strptime(task.dueDate, "%Y-%m-%dT%H:%M:%S.%f%z")
    #             < current_time
    #         )
    #     ]

    @staticmethod
    def remove_overdue_tasks(tasks: List[Task]) -> List[Task]:
        """Filter new tasks created within the last hour"""
        current_time = datetime.now(tz=timezone.utc)
        log.info("Remove overdue tasks")
        return [
            task
            for task in tasks
            if (
                datetime.strptime(task.dueDate, "%Y-%m-%dT%H:%M:%S.%f%z") > current_time
            )
        ]
