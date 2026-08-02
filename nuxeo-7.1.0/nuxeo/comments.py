# coding: utf-8
from typing import TYPE_CHECKING, Dict, Optional, Any, List

from .endpoint import APIEndpoint
from .models import Comment

if TYPE_CHECKING:
    from .client import NuxeoClient


class API(APIEndpoint):
    """Endpoint for comments."""

    __slots__ = ()

    def __init__(self, client, endpoint="id", headers=None):
        # type: (NuxeoClient, str, Optional[Dict[str, str]]) -> None
        super().__init__(client, endpoint=endpoint, cls=Comment, headers=headers)

    def get(self, docuid, uid=None, ssl_verify=True, params=None):
        # type: (str, str, bool, Any) -> Comment
        """
        Get the detail of a comment.

        :param uid: the ID of the comment
        :return: the comment
        """
        path = f"{docuid}/@comment"
        if uid:
            path += f"/{uid}"

        # Adding "&fetch-comment=repliesSummary" to the URL to retrieve replies number as well
        kwargs = {"fetch-comment": "repliesSummary"}
        if isinstance(params, dict):
            kwargs.update(params)

        return super().get(ssl_verify=ssl_verify, path=path, params=kwargs)

    def post(self, docuid, text, ssl_verify=True):
        # type: (str, str, bool) -> Comment
        """
        Create a comment.

        :param comment: the comment to create
        :return: the created comment
        """
        kwargs = {"entity-type": "comment", "parentId": docuid, "text": text}

        return super().post(
            ssl_verify=ssl_verify, path=docuid, adapter="comment", resource=kwargs
        )

    create = post  # Alias for clarity

    def put(self, comment, ssl_verify=True):
        # type: (Comment, bool) -> None
        """
        Update a comment.

        :param resource: the entry to update
        :return: the entry updated
        """
        path = f"{comment.parentId}/@comment/{comment.uid}"
        return super().put(resource=comment, path=path, ssl_verify=ssl_verify)

    def delete(self, uid, ssl_verify=True):
        # type: (str, bool) -> None
        """
        Delete a comment.

        :param uid: the ID of the comment to delete
        """
        super().delete(uid, ssl_verify=ssl_verify)

    def replies(self, uid, ssl_verify=True, params=None):
        # type: (str, bool, Any) -> List[Comment]
        """
        Get the replies of the comment.

        Any additionnal arguments will be passed to the *params* parent's call.

        :param uid: the ID of the comment
        :return: the list of replies
        """
        # Adding "&fetch-comment=repliesSummary" to the URL to retrieve replies number as well
        kwargs = {"fetch-comment": "repliesSummary"}
        if isinstance(params, dict):
            kwargs.update(params)

        return super().get(
            path=uid, adapter="comment", ssl_verify=ssl_verify, params=kwargs
        )
