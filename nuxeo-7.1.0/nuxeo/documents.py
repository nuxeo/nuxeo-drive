# coding: utf-8
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .comments import API as CommentsAPI
from .endpoint import APIEndpoint
from .exceptions import (
    BadQuery,
    HTTPError,
    UnavailableConvertor,
    NotRegisteredConvertor,
    UnavailableBogusConvertor,
)
from .models import Document, Workflow, Comment, Blob
from .operations import API as OperationsAPI
from .utils import version_lt
from .workflows import API as WorkflowsAPI

if TYPE_CHECKING:
    from .client import NuxeoClient


class API(APIEndpoint):
    """Endpoint for documents."""

    __slots__ = ("comments_api", "operations", "workflows_api")

    def __init__(
        self,
        client,  # type: NuxeoClient
        operations,  # type: OperationsAPI
        workflows,  # type: WorkflowsAPI
        comments,  # type: CommentsAPI
        endpoint=None,  # type: str
        headers=None,  # type: Optional[Dict[str, str]]
    ):
        # type: (...) -> None
        self.operations = operations
        self.comments_api = comments
        self.workflows_api = workflows
        super().__init__(client, endpoint=endpoint, cls=Document, headers=headers)

    def get(self, uid=None, path=None, ssl_verify=True):
        # type: (Optional[str], Optional[str], Optional[bool]) -> Document
        """
        Get the detail of a document.

        :param uid: the uid of the document
        :param path: the path of the document
        :return: the document
        """
        return super().get(path=self._path(uid=uid, path=path), ssl_verify=ssl_verify)

    def post(self, document, parent_id=None, parent_path=None, ssl_verify=True):
        # type: (Document, Optional[str], Optional[str], Optional[bool]) -> Document
        """
        Create a document.

        :param document: the document to create
        :param parent_id: the id of the parent document
        :param parent_path: the path of the parent document
        :return: the created document
        """
        return super().post(
            document,
            path=self._path(uid=parent_id, path=parent_path),
            ssl_verify=ssl_verify,
        )

    create = post  # Alias for clarity

    def put(self, document, ssl_verify=True):
        # type: (Document, bool) -> Document
        """
        Update a document.

        :param document: the document to update
        :return: the updated document
        """
        return super().put(
            document, path=self._path(uid=document.uid), ssl_verify=ssl_verify
        )

    def delete(self, document_id, ssl_verify=True):
        # type: (str, bool) -> None
        """
        Delete a document.

        :param document_id: the id of the document to delete
        """
        super().delete(self._path(uid=document_id), ssl_verify=ssl_verify)

    def exists(self, uid=None, path=None, ssl_verify=True):
        # type: (Optional[str], Optional[str], Optional[bool]) -> bool
        """
        Check if a document exists.

        :param uid: the id of the document to check
        :param path: the path of the document to check
        :return: True if it exists, else False
        """
        try:
            self.get(uid=uid, path=path, ssl_verify=ssl_verify)
            return True
        except HTTPError as e:
            if e.status != 404:
                raise e
        return False

    def add_permission(self, uid, params):
        # type: (str, Dict[str, Any]) -> None
        """
        Add a permission to a document.

        :param uid: the uid of the document
        :param params: the permissions to add
        """
        self.operations.execute(
            command="Document.AddPermission", input_obj=uid, params=params
        )

    def comment(self, uid, text, ssl_verify=True):
        # type: (str, str, bool) -> Comment
        """
        Add a new comment for a given document.

        :param uid: the ID of the document
        :param text: the content of the comment
        :return: the comment
        """
        return self.comments_api.create(uid, text, ssl_verify=ssl_verify)

    def comments(self, uid, ssl_verify=True, params=None):
        # type: (str, bool, Any) -> List[Comment]
        """
        Get the comments of a document.

        Any additionnal arguments will be passed to the *params* parent's call.

        :param uid: the ID of the document
        :return: the list of comments
        """

        return self.comments_api.get(uid, ssl_verify=ssl_verify, params=params)

    def convert(self, uid, options, ssl_verify=True):
        # type: (str, Dict[str, str], bool) -> Union[str, Dict[str, Any]]
        """
        Convert a blob into another format.

        :param uid: the uid of the blob to be converted
        :param options: the target type, target format,
                        or converter for the blob
        :return: the response from the server
        """
        xpath = options.pop("xpath", "blobholder:0")
        adapter = f"blob/{xpath}/@convert"
        if (
            "converter" not in options
            and "type" not in options
            and "format" not in options
        ):
            raise BadQuery("One of (converter, type, format) is mandatory in options")

        try:
            return super().get(
                path=self._path(uid=uid),
                params=options,
                adapter=adapter,
                raw=True,
                ssl_verify=ssl_verify,
            )
        except HTTPError as e:
            if "is not registered" in e.message:
                raise NotRegisteredConvertor(options)
            elif (
                "is not available" in e.message
                or "UnsupportedOperationException" in e.message
            ):
                raise UnavailableConvertor(options)
            elif "Internal Server Error" in e.message:
                raise UnavailableBogusConvertor(
                    e.message, options["converter"] if options["converter"] else ""
                )
            raise e

    def fetch_acls(self, uid, ssl_verify=True):
        # type: (str, bool) -> Dict[str, Any]
        """
        Fetch the ACLs of a document.

        :param uid: the uid of the document
        :return: the ACLs
        """
        req = super().get(
            path=self._path(uid=uid),
            cls=dict,
            headers=self.headers,
            enrichers=["acls"],
            ssl_verify=ssl_verify,
        )
        return req["contextParameters"]["acls"]

    def fetch_audit(self, uid, ssl_verify=True):
        # type: (str, bool) -> Dict[str, Any]
        """
        Fetch the audit of a document.

        :param uid: the uid of the document
        :return: the audit
        """
        return super().get(
            self._path(uid=uid), adapter="audit", cls=dict, ssl_verify=ssl_verify
        )

    def fetch_lock_status(self, uid):
        # type: (str) -> Dict[str, Any]
        """
        Fetch the lock status of a document.

        :param uid: the uid of the document
        :return: the lock status
        """
        headers = self.headers or {}
        headers.update({"fetch-document": "lock"})
        req = super().get(path=self._path(uid=uid), cls=dict, headers=headers)
        if "lockOwner" in req:
            return {"lockCreated": req["lockOwner"], "lockOwner": req["lockOwner"]}
        else:
            return {}

    def fetch_rendition(self, uid, name, ssl_verify=True):
        # type: (str, str, bool) -> Union[str, bytes]
        """
        Fetch a rendition of a document.

        :param uid: the uid of the document
        :param name: the name of the rendition
        :return: the corresponding rendition
        """
        adapter = f"rendition/{name}"
        return super().get(
            path=self._path(uid=uid), raw=True, adapter=adapter, ssl_verify=ssl_verify
        )

    def fetch_renditions(self, uid, ssl_verify=True):
        # type: (str, bool) -> List[Union[str, bytes]]
        """
        Fetch all renditions of a document.

        :param uid: the uid of a document
        :return: the renditions
        """
        headers = self.headers or {}
        headers.update({"enrichers-document": "renditions"})

        req = super().get(
            path=self._path(uid=uid), cls=dict, headers=headers, ssl_verify=ssl_verify
        )
        return [rend["name"] for rend in req["contextParameters"]["renditions"]]

    def follow_transition(self, uid, name):
        # type: (str, str) -> Dict[str, Any]
        """
        Follow a lifecycle transition.

        :param uid: the uid of the target document
        :param name: the name of the transition
        """
        params = {"value": name}
        return self.operations.execute(
            command="Document.FollowLifecycleTransition", input_obj=uid, params=params
        )

    def fetch_blob(self, uid=None, path=None, xpath="blobholder:0", ssl_verify=True):
        # type: (Optional[str], Optional[str], str, bool) -> Blob
        """
        Get the blob of a document.

        :param uid: the uid of the document
        :param path: the path of the document
        :param xpath: the xpath of the blob
        :return: the blob
        """
        adapter = f"blob/{xpath}"
        return super().get(
            path=self._path(uid=uid, path=path),
            raw=True,
            adapter=adapter,
            ssl_verify=ssl_verify,
        )

    def get_children(self, uid=None, path=None, enrichers=None, ssl_verify=True):
        # type: (Optional[str], Optional[str], Optional[List[str]], bool) -> List[Document]
        """
        Get the children of a document.

        :param uid: the uid of the document
        :param path: the path of the document
        :param enrichers: additionnal details to fetch at the same time, e.g.: ["permissions"]
        :return: the document children
        """
        return super().get(
            path=self._path(uid=uid, path=path),
            enrichers=enrichers,
            adapter="children",
            ssl_verify=ssl_verify,
        )

    def has_permission(self, uid, permission):
        # type: (str, str) -> bool
        """
        Check if a document has a permission.

        :param uid: the uid of the document
        :param permission: the permission to check
        :return: True if the document has it, False otherwise
        """
        req = super().get(
            path=self._path(uid=uid),
            cls=dict,
            headers=self.headers,
            enrichers=["permissions"],
        )
        return permission in req["contextParameters"]["permissions"]

    def lock(self, uid):
        # type: (str) -> Dict[str, Any]
        """Lock a document."""
        return self.operations.execute(command="Document.Lock", input_obj=uid)

    def move(self, uid, dst, name=None):
        # type: (str, str, Optional[str]) -> Dict[str, Any]
        """
        Move a document and eventually rename it.

        :param uid: the uid of the target document
        :param dst: the destination
        :param name: the new name
        """
        params = {"target": dst}
        if name:
            params["name"] = name
        return self.operations.execute(
            command="Document.Move", input_obj=uid, params=params
        )

    def query(self, opts=None, **kwargs):
        # type: (Optional[Dict[str, str]], Any) -> Dict[str, Any]
        """
        Run a query on the documents.

        :param opts: a query or a pageProvider
        :return: the corresponding documents
        """
        opts = opts.copy() if opts else {}
        if "query" in opts:
            query = "NXQL"
        elif "pageProvider" in opts:
            query = opts.pop("pageProvider")
        else:
            raise BadQuery("Need either a pageProvider or a query")

        path = f"query/{query}"
        res = super().get(path=path, params=opts, cls=dict, **kwargs)
        res["entries"] = [
            Document.parse(entry, service=self) for entry in res["entries"]
        ]
        return res

    def remove_permission(self, uid, params):
        # type: (str, Dict[str, str]) -> None
        """
        Remove a permission on a document.

        :param uid: the uid of the document
        :param params: the permission to remove
        """
        self.operations.execute(
            command="Document.RemovePermission", input_obj=uid, params=params
        )

    def trash(self, uid):
        # type: (str) -> Dict[str, Any]
        """
        Trash the document.

        :param uid: the uid of the document
        """
        if version_lt(self.client.server_version, "10.2"):
            input_obj = f"doc:{uid}"
            res_obj = self.operations.execute(
                command="Document.SetLifeCycle", input_obj=input_obj, value="delete"
            )
            res_obj["isTrashed"] = res_obj["state"] == "deleted"
            return res_obj

        return self.operations.execute(command="Document.Trash", input_obj=uid)

    def unlock(self, uid):
        # type: (str) -> Dict[str, Any]
        """Unlock a document."""
        return self.operations.execute(command="Document.Unlock", input_obj=uid)

    def untrash(self, uid):
        # type: (str) -> Dict[str, Any]
        """
        Untrash the document.

        :param uid: the uid of the document
        """
        if version_lt(self.client.server_version, "10.2"):
            input_obj = "doc:" + uid
            res_obj = self.operations.execute(
                command="Document.SetLifeCycle", input_obj=input_obj, value="undelete"
            )
            res_obj["isTrashed"] = res_obj["state"] == "deleted"
            return res_obj

        return self.operations.execute(command="Document.Untrash", input_obj=uid)

    def workflows(self, document):
        # type: (Document) -> Union[Workflow, List[Workflow]]
        """Get the workflows of a document."""
        path = f"id/{document.uid}/@workflow"
        return super(WorkflowsAPI, self.workflows_api).get(
            endpoint=self.endpoint, path=path
        )

    def _path(self, uid=None, path=None):
        # type: (Optional[str], Optional[str]) -> str
        if uid:
            path = f"repo/{self.client.repository}/id/{uid}"
        elif path:
            path = f"repo/{self.client.repository}/path{path}"
        return path
