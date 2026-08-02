# coding: utf-8
import os
from io import StringIO
from typing import TYPE_CHECKING, Any, BinaryIO, Dict, List, Optional, Union

from .constants import UP_AMAZON_S3

from .exceptions import InvalidBatch
from .utils import guess_mimetype

if TYPE_CHECKING:
    from .endpoint import APIEndpoint

# Base classes


class Model(object):
    """Base class for all entities."""

    __slots__ = {"service": None}  # type: Dict[str, Any]

    def __init__(self, service=None, **kwargs):
        # type: (Optional[APIEndpoint], Any) -> None
        self.service = service  # type: APIEndpoint

        # Declare attributes
        for key, default in type(self).__slots__.copy().items():
            # Reset mutable objects to prevent data leaks
            if isinstance(default, dict):
                default = {}
            elif isinstance(default, list):
                default = []
            key = key.replace("-", "_")
            setattr(self, key, kwargs.get(key, default))

    def __repr__(self):
        # type: () -> str
        attrs = ", ".join(
            f"{attr.replace('_', '-')}={getattr(self, attr, None)!r}"
            for attr in sorted(self.__slots__)
        )
        return f"<{self.__class__.__name__} {attrs}>"

    def as_dict(self):
        # type: () -> Dict[str, Any]
        """Returns a dict representation of the resource."""
        result = {}
        for key in self.__slots__:
            val = getattr(self, key)
            if val is None:
                continue
            # Parse lists of objects
            elif isinstance(val, list) and len(val) > 0 and isinstance(val[0], Model):
                val = [item.as_dict() for item in val]

            result[key.replace("_", "-")] = val
        return result

    @classmethod
    def parse(cls, json, service=None):
        # type: (Dict[str, Any], Optional[APIEndpoint]) -> Model
        """Parse a JSON object into a model instance."""
        kwargs = {k: v for k, v in json.items()}
        return cls(service=service, **kwargs)

    def save(self):
        # type: () -> None
        """Save the resource."""
        self.service.put(self)


class RefreshableModel(Model):

    __slots__ = ()

    def load(self, model=None):
        # type: (Optional[Union[Model, Dict[str, Any]]]) -> None
        """
        Reload the Model.

        If model is not None, copy from its attributes,
        otherwise query the server for the entity with its uid.

        :param model: the entity to copy
        :return: the refreshed model
        """
        if not model:
            model = self.service.get(self.uid)

        if isinstance(model, dict):

            def get_prop(obj, key):
                return obj.get(key)

        else:

            def get_prop(obj, key):
                return getattr(obj, key)

        for key in self.__slots__.keys():
            setattr(self, key, get_prop(model, key))


# Entities


class Batch(Model):
    """Upload batch."""

    __slots__ = {
        "batchId": None,
        "blobs": {},
        "dropped": None,
        "extraInfo": None,
        "etag": None,
        "key": "",
        "multiPartUploadId": None,
        "provider": None,
        "upload_idx": 0,
    }

    @property
    def uid(self):
        # type: () -> str
        return self.batchId

    @uid.setter
    def uid(self, value):
        # type: (str) -> None
        self.batchId = value

    def cancel(self):
        # type: () -> None
        """Cancel an upload batch."""
        if not self.batchId:
            return
        self.service.delete(self.uid)
        self.batchId = None

    def delete(self, file_idx, ssl_verify=True):
        """Delete a blob from the batch."""
        if self.batchId:
            self.service.delete(self.uid, file_idx=file_idx, ssl_verify=ssl_verify)
            self.blobs[file_idx] = None

    def get(self, file_idx, ssl_verify=True):
        # type: (int, bool) -> Blob
        """
        Get the blob info.

        :param file_idx: the index of the blob in the batch
        :return: the corresponding blob
        """
        if self.batchId is None:
            raise InvalidBatch("Cannot fetch blob for inexistant/deleted batch.")
        blob = self.service.get(self.uid, file_idx=file_idx, ssl_verify=ssl_verify)
        self.blobs[file_idx] = blob
        return blob

    def get_uploader(self, blob, ssl_verify=True, **kwargs):
        # type: (Blob, bool, Any) -> Blob
        """
        Get an uploader for blob.

        :param blob: the blob to upload
        :param kwargs: the upload settings
        :return: the uploader
        """
        return self.service.get_uploader(self, blob, **kwargs)

    def is_s3(self):
        # type: () -> bool
        """Return True if the upload provider is Amazon S3."""
        provider = self.provider or ""
        if not provider:
            return False

        if isinstance(self.extraInfo, dict):
            provider = self.extraInfo.get("provider_type", "") or provider

        return provider.lower() == UP_AMAZON_S3

    def upload(self, blob, ssl_verify=True, **kwargs):
        # type: (Blob, bool, Any) -> Blob
        """
        Upload a blob.

        :param blob: the blob to upload
        :param kwargs: the upload settings
        :return: the blob info
        """
        return self.service.upload(self, blob, ssl_verify=ssl_verify, **kwargs)

    def execute(self, operation, file_idx=None, params=None, ssl_verify=True):
        # type: (str, int, Dict[str, Any], bool) -> Any
        """
        Execute an operation on this batch.

        :param operation: operation to execute
        :param file_idx: target file of the operation
        :param params: parameters of the operation
        :return: the output of the operation
        """
        return self.service.execute(
            self, operation, file_idx, params, ssl_verify=ssl_verify
        )

    def attach(self, doc, file_idx=None, ssl_verify=True):
        # type: (str, Optional[int], bool) -> Any
        """
        Attach one or all files of this batch to a document.

        :param doc: document to attach
        :param file_idx: target file
        :return: the output of the attach operation
        """
        return self.service.attach(self, doc, file_idx, ssl_verify=ssl_verify)

    def complete(self, ssl_verify=True, **kwargs):
        # type: (bool, Any) -> Any
        """
        Complete a S3 Direct Upload.

        :param kwargs: additional arguments fowarded at the underlying level
        :return: the output of the complete operation
        """
        return self.service.complete(self, ssl_verify=ssl_verify, **kwargs)


class Blob(Model):
    """Blob superclass used for metadata."""

    __slots__ = {
        "batchId": "",
        "chunkCount": 0,
        "fileIdx": None,
        "mimetype": None,
        "name": None,
        "size": 0,
        "uploadType": None,
        "uploaded": "true",
        "uploadedChunkIds": [],
        "uploadedSize": 0,
    }

    @classmethod
    def parse(cls, json, service=None):
        # type: (Dict[str, Any], Optional[APIEndpoint]) -> Blob
        """Parse a JSON object into a blob instance."""
        kwargs = {k: v for k, v in json.items()}
        model = cls(service=service, **kwargs)

        if model.uploaded and model.uploadedSize == 0:
            model.uploadedSize = model.size
        return model

    def to_json(self):
        # type: () -> Dict[str, str]
        """Return a JSON object used during the upload."""
        return {"upload-batch": self.batchId, "upload-fileId": str(self.fileIdx)}


class BufferBlob(Blob):
    """
    InMemory content to upload to Nuxeo.

    Acts as a context manager so its data can be read
    with the `with` statement.
    """

    def __init__(self, data, **kwargs):
        # type: (str, Any) -> None
        """
        :param data: content to upload to Nuxeo
        :param **kwargs: named attributes
        """
        super().__init__(**kwargs)
        self.stringio = None  # type: Optional[StringIO]
        self.buffer = data
        self.size = len(self.buffer)
        self.mimetype = "application/octet-stream"

    @property
    def data(self):
        # type: () -> StringIO
        """Request data."""
        return self.stringio

    def __enter__(self):
        if not self.buffer:
            return None
        self.stringio = StringIO(self.buffer)
        return self.stringio

    def __exit__(self, *args):
        if self.stringio:
            self.stringio.close()


class Comment(Model):
    """Comment."""

    __slots__ = {
        "ancestorIds": [],
        "author": None,
        "creationDate": None,
        "entity": None,
        "entity_type": "comment",
        "entityId": None,
        "id": None,
        "lastReplyDate": None,
        "modificationDate": None,
        "numberOfReplies": 0,
        "origin": None,
        "parentId": None,
        "text": None,
    }

    @property
    def uid(self):
        # type: () -> str
        return self.id

    def delete(self, ssl_verify=True):
        # type: (bool) -> None
        """Delete the comment."""
        self.service.delete(self.uid, ssl_verify=ssl_verify)

    def has_replies(self):
        # type: () -> bool
        """Return True is the comment has at least one reply."""
        return self.numberOfReplies > 0

    def replies(self, **params):
        # type: (str, Any) -> List[Comment]
        """
        Get the replies of the comment.

        Any additionnal arguments will be passed to the *params* parent's call.

        :param uid: the ID of the comment
        :return: the list of replies
        """
        return self.service.replies(self.uid, params=params)

    def reply(self, text):
        # type: (str) -> Comment
        """Add a reply to the comment."""
        # Add the reply
        reply_comment = self.service.post(self.uid, text)

        # Update comment attributes
        self.numberOfReplies += 1
        self.lastReplyDate = reply_comment.creationDate

        # And return the reply
        return reply_comment


class FileBlob(Blob):
    """
    File to upload to Nuxeo.

    Acts as a context manager so its data can be read
    with the `with` statement.
    """

    def __init__(self, path, **kwargs):
        # type: (str, Any) -> None
        """
        :param path: file path
        :param **kwargs: named attributes
        """
        super().__init__(**kwargs)
        self.fd = None  # type: Optional[BinaryIO]
        self.path = path
        self.name = os.path.basename(self.path)
        self.size = os.path.getsize(self.path)
        self.mimetype = self.mimetype or guess_mimetype(self.path)  # type: str

    @property
    def data(self):
        # type: () -> BinaryIO
        """
        Request data.

        The caller has to close the file descriptor
        himself if he doesn't open it with the
        context manager.
        """
        return self.fd

    def __enter__(self):
        self.fd = open(self.path, "rb")
        return self.fd

    def __exit__(self, *args):
        if self.fd:
            self.fd.close()


class Directory(Model):
    """Directory."""

    __slots__ = {
        "directoryName": None,
        "entries": [],
        "entity_type": "directory",
    }

    @property
    def uid(self):
        # type: () -> str
        return self.directoryName

    def get(self, entry):
        # type: (str) -> DirectoryEntry
        """
        Get an entry of the directory.

        :param entry: the name of the entry
        :return: the corresponding directory entry
        """
        return self.service.get(self.uid, dir_entry=entry)

    def create(self, entry):
        # type: (DirectoryEntry) -> DirectoryEntry
        """Create an entry in the directory."""
        return self.service.post(entry, dir_name=self.uid)

    def save(self, entry):
        # type: (DirectoryEntry) -> DirectoryEntry
        """Save a modified entry of the directory."""
        return self.service.put(entry, dir_name=self.uid)

    def delete(self, entry):
        # type: (str) -> None
        """
        Delete one of the directory's entries.

        :param entry: the entry to delete
        """
        self.service.delete(self.uid, entry)

    def exists(self, entry):
        # type: (str) -> bool
        """
        Check if an entry is in the directory.

        :param entry: the entry name
        :return: True if it exists, else False
        """
        return self.service.exists(self.uid, dir_entry=entry)


class DirectoryEntry(Model):
    """Directory entry."""

    __slots__ = {
        "directoryName": None,
        "entity_type": "directoryEntry",
        "properties": {},
    }

    @property
    def uid(self):
        # type: () -> str
        return self.properties["id"]

    def save(self):
        # type: () -> DirectoryEntry
        """Save the entry."""
        return self.service.put(self, self.directoryName)

    def delete(self):
        # type: () -> None
        """Delete the entry."""
        self.service.delete(self.directoryName, self.uid)


class Document(RefreshableModel):
    """Document."""

    __slots__ = {
        "changeToken": None,
        "contextParameters": {},
        "entity_type": "document",
        "facets": [],
        "isCheckedOut": False,
        "isProxy": False,
        "isTrashed": False,
        "isVersion": False,
        "lastModified": None,
        "name": None,
        "parentRef": None,
        "path": None,
        "properties": {},
        "repository": "default",
        "state": None,
        "title": None,
        "type": None,
        "uid": None,
        "versionLabel": None,
    }

    @property
    def workflows(self):
        # type: () -> List[Workflow]
        """Return the workflows associated with the document."""
        return self.service.workflows(self)

    def add_permission(self, params, ssl_verify=True):
        # type: (Dict[str, Any], bool) -> None
        """
        Add a permission to a document.

        :param params: permission to add
        """
        return self.service.add_permission(self.uid, params)

    def comment(self, text, ssl_verify=True):
        # type: (str, bool) -> Comment
        """
        Add a comment to the document.

        :param text: the comment message
        :return: a comment object
        """
        return self.service.comment(self.uid, text, ssl_verify=ssl_verify)

    def comments(self, ssl_verify=True, **params):
        # type: (bool, Any) -> List[Comment]
        """Return the comments associated with the document.
        Any additionnal arguments will be passed to the *params* parent's call.
        """
        return self.service.comments(self.uid, params=params, ssl_verify=ssl_verify)

    def convert(self, params, ssl_verify=True):
        # type: (Dict[str, Any], bool) -> Union[Dict[str, Any], str]
        """
        Convert the document to another format.

        :param params: Converter permission
        :return: the converter result
        """

        return self.service.convert(self.uid, params)

    def delete(self, ssl_verify=True):
        # type: (bool) -> None
        """Delete the document."""
        self.service.delete(self.uid, ssl_verify=ssl_verify)

    def fetch_acls(self, ssl_verify=True):
        # type: (bool) -> Dict[str, Any]
        """Fetch document ACLs."""
        return self.service.fetch_acls(self.uid, ssl_verify=ssl_verify)

    def fetch_audit(self, ssl_verify=True):
        # type: (bool) -> Dict[str, Any]
        """Fetch audit for current document."""
        return self.service.fetch_audit(self.uid, ssl_verify=ssl_verify)

    def fetch_blob(self, xpath="blobholder:0", ssl_verify=True):
        # type: (str, bool) -> Blob
        """
        Retrieve one of the blobs attached to the document.

        :param xpath: the xpath to the blob
        :return: the blob
        """
        return self.service.fetch_blob(uid=self.uid, xpath=xpath, ssl_verify=ssl_verify)

    def fetch_lock_status(self, ssl_verify=True):
        # type: (bool) -> Dict[str, Any]
        """Get lock informations."""
        return self.service.fetch_lock_status(self.uid)

    def fetch_rendition(self, name, ssl_verify=True):
        # type: (str, bool) -> Union[str, bytes]
        """
        :param name: Rendition name to use
        :return: The rendition content
        """
        return self.service.fetch_rendition(self.uid, name, ssl_verify=ssl_verify)

    def fetch_renditions(self, ssl_verify=True):
        # type: (bool) -> List[Union[str, bytes]]
        """
        :return: Available renditions for this document
        """
        return self.service.fetch_renditions(self.uid, ssl_verify=ssl_verify)

    def follow_transition(self, name, ssl_verify=True):
        # type: (str, bool) -> None
        """
        Follow a lifecycle transition on this document.

        :param name: transition name
        """
        doc = self.service.follow_transition(self.uid, name)
        self.load(doc)

    def get(self, prop):
        # type: (str) -> Any
        """Get a property of the document by its name."""
        return self.properties[prop]

    def has_permission(self, permission, ssl_verify=True):
        # type: (str, bool) -> bool
        """Verify if a document has the permission."""
        return self.service.has_permission(self.uid, permission)

    def is_locked(self):
        # type: () -> bool
        """Get the lock status."""
        return not not self.fetch_lock_status()

    def lock(self, ssl_verify=True):
        # type: (bool) -> Dict[str, Any]
        """Lock the document."""
        return self.service.lock(self.uid)

    def move(self, dst, name=None, ssl_verify=True):
        # type: (str, Optional[str], bool) -> None
        """
        Move a document into another parent.

        :param dst: The new parent path
        :param name: Rename the document if specified
        """
        doc = self.service.move(self.uid, dst, name)
        self.load(doc)

    def remove_permission(self, params, ssl_verify=True):
        # type: (Dict[str, Any], bool) -> None
        """Remove a permission to a document."""
        return self.service.remove_permission(self.uid, params)

    def set(self, properties):
        # type: (Dict[str, Any]) -> None
        """Add/update the properties of the document."""
        self.properties.update(properties)

    def trash(self, ssl_verify=True):
        # type: (bool) -> None
        doc = self.service.trash(self.uid)
        self.load(doc)

    def unlock(self, ssl_verify=True):
        # type: (bool) -> Dict[str, Any]
        """Unlock the document."""
        return self.service.unlock(self.uid)

    def untrash(self, ssl_verify=True):
        # type: (bool) -> None
        doc = self.service.untrash(self.uid)
        self.load(doc)


class Group(Model):
    """User group."""

    __slots__ = {
        "entity_type": "group",
        "grouplabel": None,
        "groupname": None,
        "memberGroups": [],
        "memberUsers": [],
    }

    @property
    def uid(self):
        # type: () -> str
        return self.groupname

    def delete(self, ssl_verify=True):
        # type: (bool) -> None
        """Delete the group."""
        self.service.delete(self.uid, ssl_verify=ssl_verify)


class Operation(Model):
    """Automation operation."""

    __slots__ = {
        "command": None,
        "context": None,
        "input_obj": None,
        "params": {},
        "progress": 0,
    }

    def execute(self, **kwargs):
        # type: (Any) -> Any
        """Execute the operation."""
        return self.service.execute(self, **kwargs)


class Task(RefreshableModel):
    """Workflow task."""

    __slots__ = {
        "actors": [],
        "comments": [],
        "created": None,
        "directive": None,
        "dueDate": None,
        "entity_type": "task",
        "id": None,
        "name": None,
        "nodeName": None,
        "state": None,
        "targetDocumentIds": [],
        "taskInfo": {},
        "variables": {},
        "workflowInstanceId": None,
        "workflowModelName": None,
    }

    @property
    def uid(self):
        # type: () -> str
        return self.id

    def complete(self, action, variables=None, comment=None):
        # type: (str, Optional[Dict[str, Any]], Optional[str]) -> None
        """Complete the action of a task."""
        updated_task = self.service.complete(
            self, action, variables=variables, comment=comment
        )
        self.load(updated_task)

    def delegate(self, actors, comment=None):
        # type: (str, Optional[str]) -> None
        """Delegate the task to someone else."""
        self.service.transfer(self, "delegate", actors, comment=comment)
        self.load()

    def reassign(self, actors, comment=None):
        # type: (str, Optional[str]) -> None
        """Reassign the task to someone else."""
        self.service.transfer(self, "reassign", actors, comment=comment)
        self.load()


class User(RefreshableModel):
    """User."""

    __slots__ = {
        "entity_type": "user",
        "extendedGroups": [],
        "id": None,
        "isAdministrator": False,
        "isAnonymous": False,
        "properties": {},
    }

    @property
    def uid(self):
        # type: () -> str
        return self.id

    def change_password(self, password):
        # type: (str) -> None
        """
        Change user password.

        :param password: New password to set
        """
        self.properties["password"] = password
        self.save()

    def delete(self, ssl_verify=True):
        # type: (bool) -> None
        """Delete the user."""
        self.service.delete(self.uid, ssl_verify=ssl_verify)


class Workflow(Model):
    """Workflow."""

    __slots__ = {
        "attachedDocumentIds": [],
        "entity_type": "workflow",
        "graphResource": None,
        "id": None,
        "initiator": None,
        "name": None,
        "state": None,
        "title": None,
        "variables": {},
        "workflowModelName": None,
    }

    @property
    def tasks(self):
        # type: () -> List[Task]
        """Return the tasks associated with the workflow."""
        return self.service.tasks(self)

    @property
    def uid(self):
        # type: () -> str
        return self.id

    def delete(self):
        # type: () -> None
        """Delete the workflow."""
        self.service.delete(self.uid)

    def graph(self):
        # type: () -> Dict[str, Any]
        """Return a JSON representation of the workflow graph."""
        return self.service.graph(self)
