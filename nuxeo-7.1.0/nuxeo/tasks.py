# coding: utf-8
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .endpoint import APIEndpoint
from .exceptions import BadQuery
from .models import Task

if TYPE_CHECKING:
    from .client import NuxeoClient


class API(APIEndpoint):
    """ Endpoint for tasks. """

    __slots__ = ()

    def __init__(self, client, endpoint="task", headers=None):
        # type: (NuxeoClient, str, Optional[Dict[str, str]]) -> None
        super().__init__(client, endpoint=endpoint, cls=Task, headers=headers)

    def get(
        self, options=None  # type: Optional[Union[Dict[str, Any], str]]
    ):
        # type: (...) -> Union[Task, List[Task]]
        """
        Get tasks by id or by options.

        :param options: the id of the task or the constraints
        :return: the task(s)
        """
        params, request_path = None, None

        if isinstance(options, dict):
            params = options
        elif isinstance(options, str):
            request_path = options

        return super().get(path=request_path, params=params)

    def post(self, **kwargs):
        # type: (Any) -> None
        raise NotImplementedError()

    def put(self, task):
        # type: (Task) -> Task
        raise NotImplementedError()

    def delete(self, task_id):
        # type: (str) -> None
        raise NotImplementedError()

    def complete(self, task, action, variables=None, comment=None):
        # type: (Task, str, Optional[Dict[str, Any]], Optional[str]) -> Task
        """
        Complete the task.

        :param task: the task
        :param action: to take
        :param variables: to add to the Task
        :param comment: for the action
        :return: Updated task
        """
        if variables:
            task.variables.update(variables)
        if comment:
            task.variables["comment"] = comment

        request_path = f"{task.uid}/{action}"
        return super().put(task, path=request_path)

    def transfer(self, task, transfer, actors, comment=None):
        # type: (Task, str, str, Optional[str]) -> None
        """
         Delegate or reassign the Task to someone else.

        :param task: the task to modify
        :param transfer: 'delegate' or 'reassign'
        :param actors: the actors involved
        :param comment: a comment
        :return:
        """
        if transfer == "delegate":
            actors_type = "delegatedActors"
        elif transfer == "reassign":
            actors_type = "actors"
        else:
            raise BadQuery("Task transfer must be either delegate or reassign.")

        params = {actors_type: actors}
        if comment:
            params["comment"] = comment

        request_path = f"{task.uid}/{transfer}"
        super().put(None, path=request_path, params=params)
