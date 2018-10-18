# coding: utf-8
import hashlib
import unicodedata
from collections import namedtuple
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlite3 import Row

from dateutil import parser

# Settings passed to Manager.bind_server()
Binder = namedtuple(
    "binder", ["username", "password", "token", "url", "no_check", "no_fscheck"]
)

# List of filters from the database
Filters = List[str]

# Metrics
Metrics = Dict[str, Any]


# Data Transfer Object for remote file info
@dataclass
class RemoteFileInfo:
    name: str  # title of the file (not guaranteed to be locally unique)
    uid: str  # id of the file
    parent_uid: str  # id of the parent file
    path: str  # abstract file system path: useful for ordering folder trees
    folderish: bool  # True is can host children
    last_modification_time: datetime  # last update time
    creation_time: datetime  # creation time
    last_contributor: str  # last contributor
    digest: Optional[str]  # digest of the file
    digest_algorithm: Optional[str]  # digest algorithm of the file
    download_url: str  # download URL of the file
    can_rename: bool  # True is can rename
    can_delete: bool  # True is can delete
    can_update: bool  # True is can update content
    can_create_child: bool  # True is can create child
    lock_owner: Optional[str]  # lock owner
    lock_created: Optional[datetime]  # lock creation time
    can_scroll_descendants: bool  # True if the API to scroll through
    # the descendants can be used

    @staticmethod
    def from_dict(fs_item: Dict[str, Any]) -> "RemoteFileInfo":
        """Convert Automation file system item description to RemoteFileInfo"""
        folderish = fs_item["folder"]

        last_update = datetime.fromtimestamp(fs_item["lastModificationDate"] // 1000)
        creation = datetime.fromtimestamp(fs_item["creationDate"] // 1000)

        last_contributor = fs_item.get("lastContributor", "")

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

        return RemoteFileInfo(  # type: ignore
            name,
            fs_item["id"],
            fs_item["parentId"],
            fs_item["path"],
            folderish,
            last_update,
            creation,
            last_contributor,
            digest,
            digest_algorithm,
            download_url,
            fs_item["canRename"],
            fs_item["canDelete"],
            can_update,
            can_create_child,
            lock_owner,
            lock_created,
            can_scroll_descendants,
        )


@dataclass
class Blob:
    name: str  # filename of the blob
    digest: Optional[str]  # hash of the blob
    digest_algorithm: Optional[str]  # algorithm used to compute the digest
    size: int  # size of the blob in bytes
    mimetype: str  # mime-type of the blob
    data: str  # download url of the blob or content if it's a note

    @staticmethod
    def from_dict(blob: Dict[str, Any]) -> "Blob":
        """ Convert Dict to Blob object. """
        name = blob["name"]
        digest = blob.get("digest")
        digest_algorithm = blob.get("digestAlgorithm")
        size = int(blob["length"])
        mimetype = blob["mime-type"]
        data = blob["data"]

        if digest_algorithm:
            digest_algorithm = digest_algorithm.lower().replace("-", "")

        return Blob(name, digest, digest_algorithm, size, mimetype, data)


# Data Transfer Object for doc info on the Remote Nuxeo repository
@dataclass
class NuxeoDocumentInfo:
    root: str  # ref of the document that serves as sync root
    name: str  # title of the document (not guaranteed to be locally unique)
    uid: str  # ref of the document
    parent_uid: str  # ref of the parent document
    path: str  # remote path (useful for ordering)
    folderish: bool  # True is can host child documents
    last_modification_time: datetime  # last update time
    last_contributor: str  # last contributor
    repository: str  # server repository name
    doc_type: str  # Nuxeo document type
    version: Optional[str]  # Nuxeo version
    state: str  # Nuxeo lifecycle state
    is_trashed: bool  # Nuxeo trashed status
    blobs: Dict[str, Blob]  # Dictionary of blob with their xpath as key
    lock_owner: str  # lock owner
    lock_created: datetime  # lock creation time
    permissions: List[str]  # permissions

    @staticmethod
    def from_dict(doc: Dict[str, Any], parent_uid: str = None) -> "NuxeoDocumentInfo":
        """Convert Automation document description to NuxeoDocumentInfo"""
        props = doc["properties"]
        name = props["dc:title"]
        folderish = "Folderish" in doc["facets"]
        try:
            last_update = datetime.strptime(
                doc["lastModified"], "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        except ValueError:
            # no millisecond?
            last_update = datetime.strptime(doc["lastModified"], "%Y-%m-%dT%H:%M:%SZ")

        blobs: Dict[str, Blob] = {}

        if not folderish:
            main_blob = props.get("file:content")
            attachments = props.get("files:files")
            note = props.get("note:note")

            if main_blob:
                blobs["file:content"] = Blob.from_dict(main_blob)

            idx = 0
            for attachment in attachments or []:
                blobs[f"files:files/{idx}/file"] = Blob.from_dict(attachment["file"])
                idx += 1

            if note:
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
                    name += ext

                blobs["note:note"] = Blob.from_dict(
                    {
                        "name": name,
                        "digest": digest,
                        "digestAlgorithm": digest_algorithm,
                        "length": len(note),
                        "mime-type": mime_type,
                        "data": note,
                    }
                )

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
        version = None
        if "uid:major_version" in props and "uid:minor_version" in props:
            version = (
                str(props["uid:major_version"]) + "." + str(props["uid:minor_version"])
            )
        if name:
            name = unicodedata.normalize("NFC", name)
        return NuxeoDocumentInfo(  # type: ignore
            doc["root"],
            name,
            doc["uid"],
            parent_uid,
            doc["path"],
            folderish,
            last_update,
            props["dc:lastContributor"],
            doc["repository"],
            doc["type"],
            version,
            doc["state"],
            is_trashed,
            blobs,
            lock_owner,
            lock_created,
            permissions,
        )


class DocPair(Row):

    id: int
    last_local_updated: str
    last_remote_updated: str
    local_digest: Optional[str]
    remote_digest: str
    local_path: str
    remote_ref: str
    local_parent_path: str
    remote_parent_ref: str
    remote_parent_path: str
    local_name: str
    remote_name: str
    size: int
    folderish: bool
    local_state: str
    remote_state: str
    pair_state: str
    remote_can_create_child: bool
    remote_can_delete: bool
    remote_can_rename: bool
    remote_can_update: bool
    last_remote_modifier: str
    last_sync_date: str
    error_count: int
    last_sync_error_date: str
    last_error: Optional[str]
    last_error_details: str
    error_next_try: int
    version: int
    processor: int
    last_transfer: str
    creation_date: str

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__}[{self.id!r}]"
            f" local_path={self.local_path!r},"
            f" remote_ref={self.remote_ref!r},"
            f" local_state={self.local_state!r},"
            f" remote_state={self.remote_state!r},"
            f" pair_state={self.pair_state!r},"
            f" filter_path={self.path!r}"
            ">"
        )

    def __getattr__(self, name: str) -> Optional[str]:
        with suppress(IndexError):
            return self[name]

    def is_readonly(self) -> bool:
        if self.folderish:
            return self.remote_can_create_child == 0
        return (
            self.remote_can_delete & self.remote_can_rename & self.remote_can_update
        ) == 0

    def update_state(self, local_state: str = None, remote_state: str = None) -> None:
        if local_state is not None:
            self.local_state = local_state
        if remote_state is not None:
            self.remote_state = remote_state


DocPairs = List[DocPair]


@dataclass
class EngineDef(Row):
    local_folder: str
    engine: str
    uid: str
    name: str
