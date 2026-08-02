# coding: utf-8
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .endpoint import APIEndpoint
from .models import Document, Task, Workflow
from .tasks import API as TasksAPI

if TYPE_CHECKING:
    from .client import NuxeoClient


class API(APIEndpoint):
    """ Endpoint for workflows. """

    __slots__ = ("tasks_api",)

    def __init__(
        self,
        client,  # type: NuxeoClient
        tasks,  # type: TasksAPI
        endpoint="workflow",  # type: str
        headers=None,  # type: Optional[Dict[str, str]]
    ):
        # type: (...) -> None
        self.tasks_api = tasks
        super().__init__(client, endpoint=endpoint, cls=Workflow, headers=headers)

    def get(self, workflow_id=None):
        # type: (Optional[str]) -> Workflow
        """
        Get the detail of a workflow.

        :param workflow_id: the id of the workflow
        :return: the workflow
        """
        return super().get(path=workflow_id)

    def post(
        self,
        model,  # type: str
        document=None,  # type: Optional[Document]
        options=None,  # type: Optional[Dict[str, Any]]
    ):
        # type: (...) -> Workflow
        """
        Start a workflow.

        :param model: the workflow to start
        :param document: the document to start the workflow on
        :param options: options for the workflow
        :return: the created workflow
        """
        data = {"workflowModelName": model, "entity-type": "workflow"}
        options = options or {}
        if "attachedDocumentIds" in options:
            data["attachedDocumentIds"] = options["attachedDocumentIds"]
        if "variables" in options:
            data["variables"] = options["variables"]

        kwargs = {}
        if document:
            kwargs["endpoint"] = self.client.api_path
            kwargs["path"] = f"id/{document.uid}/@workflow"
        return super().post(data, **kwargs)

    start = post  # Alias for clarity

    def put(self, **kwargs):
        # type: (Any) -> None
        raise NotImplementedError()

    def delete(self, workflow_id):
        # type: (str) -> None
        """
        Delete a workflow.

        :param workflow_id: the id of the workflow to delete
        """
        super().delete(workflow_id)

    def graph(self, workflow):
        # type: (Workflow) -> Dict[str, Any]
        """
        Get the graph of the workflow in JSON format.

        :param workflow: the worklow to get the graph from
        :return: the graph
        """
        request_path = f"{workflow.uid}/graph"
        return super().get(path=request_path)

    def started(self, model):
        # type: (str) -> List[Workflow]
        """
        Get started workflows having the specified model.

        :param model: the workflow model
        :return: the started workflows
        """
        return super().get(params={"workflowModelName": model})

    def tasks(self, workflow):
        # type: (Workflow) -> List[Task]
        """ Get the tasks of a workflow. """
        return self.tasks_api.get(workflow.as_dict())
