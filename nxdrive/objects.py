# coding: utf-8
import hashlib
import unicodedata
from collections import namedtuple
from datetime import datetime
from sqlite3 import Cursor
from typing import Any, Dict, List, Tuple

from dateutil import parser

# Settings passed to Manager.bind_server()
Binder = namedtuple(
    "binder", ["username", "password", "token", "url", "no_check", "no_fscheck"]
)

# Document's pair state
DocPair = Cursor
DocPairs = List[Tuple[DocPair]]

# List of filters from the database
Filters = List[Tuple[str]]

# Metrics
Metrics = Dict[str, Any]


class SlotInfo:
    __slots__ = ()

    def __init__(self, **kwargs):
        for item in self.__slots__:
            setattr(self, item, kwargs.get(item, None))

    def __repr__(self) -> str:
        attrs = [f"{attr}={getattr(self, attr)!r}" for attr in sorted(self.__slots__)]
        return f"<{type(self).__name__} {', '.join(attrs)}>"

    def __str__(self) -> str:
        return repr(self)


# Data Transfer Object for remote file info
class RemoteFileInfo(SlotInfo):
    __slots__ = (
        "name",  # title of the file (not guaranteed to be locally unique)
        "uid",  # id of the file
        "parent_uid",  # id of the parent file
        "path",  # abstract file system path: useful for ordering folder trees
        "folderish",  # True is can host children
        "last_modification_time",  # last update time
        "creation_time",  # creation time
        "last_contributor",  # last contributor
        "digest",  # digest of the file
        "digest_algorithm",  # digest algorithm of the file
        "download_url",  # download URL of the file
        "can_rename",  # True is can rename
        "can_delete",  # True is can delete
        "can_update",  # True is can update content
        "can_create_child",  # True is can create child
        "lock_owner",  # lock owner
        "lock_created",  # lock creation time
        "can_scroll_descendants"  # True if the API to scroll through
        # the descendants can be used
    )

    @staticmethod
    def from_dict(fs_item: Dict[str, Any]) -> "RemoteFileInfo":
        """Convert Automation file system item description to RemoteFileInfo"""
        folderish = fs_item["folder"]

        # TODO: NXDRIVE-1236 Remove those ugly fixes
        # TODO: when https://bugs.python.org/issue29097 is fixed
        last_update = fs_item["lastModificationDate"] // 1000
        last_update = max(86400, last_update)
        last_update = datetime.fromtimestamp(last_update)
        creation = fs_item["creationDate"] // 1000
        creation = max(86400, creation)
        creation = datetime.fromtimestamp(creation)

        last_contributor = fs_item.get("lastContributor")

        if folderish:
            digest = None
            digest_algorithm = None
            download_url = None
            can_update = False
            can_create_child = fs_item["canCreateChild"]
            # Scroll API availability
            can_scroll = fs_item.get("canScrollDescendants", False)
            can_scroll_descendants = can_scroll
        else:
            digest = fs_item["digest"]
            digest_algorithm = fs_item["digestAlgorithm"] or None
            if digest_algorithm:
                digest_algorithm = digest_algorithm.lower().replace("-", "")
            download_url = fs_item["downloadURL"]
            can_update = fs_item["canUpdate"]
            can_create_child = False
            can_scroll_descendants = False

        # Lock info
        lock_info = fs_item.get("lockInfo")
        lock_owner = lock_created = None
        if lock_info:
            lock_owner = lock_info.get("owner")
            lock_created_millis = lock_info.get("created")
            if lock_created_millis:
                lock_created = datetime.fromtimestamp(lock_created_millis // 1000)

        # Normalize using NFC to make the tests more intuitive
        name = fs_item["name"]
        if name:
            name = unicodedata.normalize("NFC", name)

        return RemoteFileInfo(
            name=name,
            uid=fs_item["id"],
            parent_uid=fs_item["parentId"],
            path=fs_item["path"],
            folderish=folderish,
            last_modification_time=last_update,
            creation_time=creation,
            last_contributor=last_contributor,
            digest=digest,
            digest_algorithm=digest_algorithm,
            download_url=download_url,
            can_rename=fs_item["canRename"],
            can_delete=fs_item["canDelete"],
            can_update=can_update,
            can_create_child=can_create_child,
            lock_owner=lock_owner,
            lock_created=lock_created,
            can_scroll_descendants=can_scroll_descendants,
        )


# Data Transfer Object for doc info on the Remote Nuxeo repository
class NuxeoDocumentInfo(SlotInfo):
    __slots__ = (
        "root",  # ref of the document that serves as sync root
        "name",  # title of the document (not guaranteed to be locally unique)
        "uid",  # ref of the document
        "parent_uid",  # ref of the parent document
        "path",  # remote path (useful for ordering)
        "folderish",  # True is can host child documents
        "last_modification_time",  # last update time
        "last_contributor",  # last contributor
        "digest_algorithm",  # digest algorithm of the document's blob
        "digest",  # digest of the document's blob
        "repository",  # server repository name
        "doc_type",  # Nuxeo document type
        "version",  # Nuxeo version
        "state",  # Nuxeo lifecycle state
        "is_trashed",  # Nuxeo trashed status
        "has_blob",  # If this doc has blob
        "filename",  # Filename of document
        "lock_owner",  # lock owner
        "lock_created",  # lock creation time
        "permissions",  # permissions
    )

    @staticmethod
    def from_dict(doc: Dict[str, Any], parent_uid: str = None) -> "NuxeoDocumentInfo":
        """Convert Automation document description to NuxeoDocumentInfo"""
        props = doc["properties"]
        name = props["dc:title"]
        filename = None
        folderish = "Folderish" in doc["facets"]
        try:
            last_update = datetime.strptime(
                doc["lastModified"], "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        except ValueError:
            # no millisecond?
            last_update = datetime.strptime(doc["lastModified"], "%Y-%m-%dT%H:%M:%SZ")

        # TODO: support other main files
        has_blob = False
        if folderish:
            digest_algorithm = None
            digest = None
        else:
            blob = props.get("file:content")
            if blob is None:
                note = props.get("note:note")
                if note is None:
                    digest_algorithm = None
                    digest = None
                else:
                    m = hashlib.md5()
                    m.update(note.encode("utf-8"))
                    digest = m.hexdigest()
                    digest_algorithm = "md5"
                    ext = ".txt"
                    mime_type = props.get("note:mime_type")
                    if mime_type == "text/html":
                        ext = ".html"
                    elif mime_type == "text/xml":
                        ext = ".xml"
                    elif mime_type == "text/x-web-markdown":
                        ext = ".md"
                    if not name.endswith(ext):
                        filename = name + ext
                    else:
                        filename = name
            else:
                has_blob = True
                digest_algorithm = blob.get("digestAlgorithm")
                if digest_algorithm is not None:
                    digest_algorithm = digest_algorithm.lower().replace("-", "")
                digest = blob.get("digest")
                filename = blob.get("name")

        # Lock info
        lock_owner = doc.get("lockOwner")
        lock_created = doc.get("lockCreated")
        if lock_created is not None:
            lock_created = parser.parse(lock_created)

        # Permissions
        permissions = doc.get("contextParameters", {}).get("permissions", None)

        # Trashed
        is_trashed = doc.get("isTrashed", doc["state"] == "deleted")

        # XXX: we need another roundtrip just to fetch the parent uid...

        # Normalize using NFC to make the tests more intuitive
        if "uid:major_version" in props and "uid:minor_version" in props:
            version = (
                str(props["uid:major_version"]) + "." + str(props["uid:minor_version"])
            )
        else:
            version = None
        if name is not None:
            name = unicodedata.normalize("NFC", name)
        return NuxeoDocumentInfo(
            root=doc["root"],
            name=name,
            uid=doc["uid"],
            parent_uid=parent_uid,
            path=doc["path"],
            folderish=folderish,
            last_modification_time=last_update,
            last_contributor=props["dc:lastContributor"],
            digest_algorithm=digest_algorithm,
            digest=digest,
            repository=doc["repository"],
            doc_type=doc["type"],
            version=version,
            state=doc["state"],
            is_trashed=is_trashed,
            has_blob=has_blob,
            filename=filename,
            lock_owner=lock_owner,
            lock_created=lock_created,
            permissions=permissions,
        )
