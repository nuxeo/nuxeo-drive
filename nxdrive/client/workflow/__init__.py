from typing import TYPE_CHECKING, Dict, List

from nuxeo.models import Task

from nxdrive.engine.engine import Engine
from nxdrive.utils import get_verify

if TYPE_CHECKING:
    from ..remote_client import Remote  # noqa


class Workflow:
    """"""

    def __init__(self, remote: "Remote", /) -> None:
        self.remote = remote
        self.dao = remote.dao
        self.verification_needed = get_verify()

    def fetch_document_name(self, tasks_list: Dict, engine: Engine, /):
        # doc_id = tasks_list[0].targetDocumentIds[0]["id"]
        doc_ids = [x.targetDocumentIds[0]["id"] for x in tasks_list]
        print(f">>> doc_id: {doc_ids}")
        for doc_id in doc_ids:
            response = self.remote.documents.get(doc_id)
            document_data = {
                "doc_id": response.uid,
                "name": response.title,
                "doc_path": response.path,
            }
            print(document_data)
            engine.fetch_pending_task_list(response.uid, response.path)
            return document_data


class Tasks(Workflow):
    """"""

    def get_pending_tasks(self, uid: str, engine: Engine, /) -> List[Task]:
        """Fetch tasks"""
        try:
            print(f">>> username: {self.remote.user_id}")
            options = {"userId": f"{self.remote.user_id}"}
            tasks = self.remote.tasks.get(options)
            print(f">>>> tasks: {tasks}")
            self.fetch_document_name(tasks, engine)
        except Exception as e:
            print(f">>> exception: {e}")
