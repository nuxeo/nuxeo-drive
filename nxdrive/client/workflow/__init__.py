from datetime import datetime, timedelta, timezone
from logging import getLogger
from typing import TYPE_CHECKING, Dict, List

from nuxeo.models import Task

from nxdrive.engine.engine import Engine
from nxdrive.utils import get_verify

if TYPE_CHECKING:
    from ..remote_client import Remote  # noqa

log = getLogger(__name__)


class Workflow:
    """Workflow Management for document Review"""

    def __init__(self, remote: "Remote") -> None:
        self.remote = remote
        self.verification_needed = get_verify()

    def fetch_document(self, tasks_list: Dict, engine: Engine) -> None:
        """Fetch document details"""
        first_task = tasks_list[0]
        doc_id = first_task.targetDocumentIds[0]["id"]
        task_id = first_task.id

        response = self.remote.documents.get(doc_id)
        if response:
            engine.send_task_notification(task_id, response.path)
        else:
            log.error("Failed to fetch document details.")

    def get_pending_tasks(self, engine: Engine, initial_run: bool = True) -> List[Task]:  # type: ignore
        """Get Tasks for document review"""
        try:
            options = {"userId": self.remote.user_id}
            tasks = self.remote.tasks.get(options)

            if tasks:
                if not initial_run:
                    tasks = self.filter_tasks(tasks)

                if tasks:
                    if len(tasks) > 1:
                        # Send generic notification for multiple tasks
                        engine.send_task_notification(
                            tasks[0].targetDocumentIds[0]["id"], ""
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

    @staticmethod
    def filter_tasks(tasks: List[Task]) -> List[Task]:
        """Filter new tasks created within the last hour"""
        last_hour = datetime.now(tz=timezone.utc) - timedelta(minutes=60)
        log.info("Filtering tasks created in the last hour.")
        return [
            task
            for task in tasks
            if datetime.strptime(task.created, "%Y-%m-%dT%H:%M:%S.%f%z") > last_hour
        ]
