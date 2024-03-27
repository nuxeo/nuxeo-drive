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

    def __init__(self, remote: "Remote", /) -> None:
        self.remote = remote
        self.dao = remote.dao
        self.verification_needed = get_verify()

    def fetch_document(self, tasks_list: Dict, engine: Engine, /):
        """Fetch document details"""
        data = {
            "doc_id": tasks_list[0].targetDocumentIds[0]["id"],
            "task_id": tasks_list[0].id,
        }
        response = self.remote.documents.get(data["doc_id"])
        engine.send_task_notification(data["task_id"], response.path)

    def get_pending_tasks(
        self, uid: str, engine: Engine, initial_run: bool = True, /
    ) -> List[Task]:
        """Get Tasks for document review"""
        try:
            options = {"userId": f"{self.remote.user_id}"}
            tasks = self.remote.tasks.get(options)

            if tasks:
                # Triggger through workflow poll worker
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
            log.error(f"Exception occured while Fetching Tasks: {exec}")

    def filter_tasks(self, tasks):
        """Filter new tasks created between last polling time"""
        last_scheduler_time = datetime.now(tz=timezone.utc) - timedelta(minutes=4)
        log.info("Filter task created in last one hour")
        tasks = list(
            filter(
                (
                    lambda task: datetime.strptime(
                        task.created, "%Y-%m-%dT%H:%M:%S.%f%z"
                    )
                    > last_scheduler_time
                ),
                tasks,
            )
        )
        return tasks
