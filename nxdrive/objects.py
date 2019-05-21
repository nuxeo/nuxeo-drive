# coding: utf-8
import hashlib
import unicodedata
from collections import namedtuple
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from sqlite3 import Row
from time import time
from typing import Any, Dict, List, Optional, Tuple, Union

from dataclasses import dataclass, field
from dateutil import parser
from dateutil.tz import tzlocal

from nxdrive.constants import TransferStatus
from .exceptions import DriveError
from .translator import Translator
from .utils import get_date_from_sqlite, get_timestamp_from_date

# Settings passed to Manager.bind_server()
Binder = namedtuple(
    "binder", ["username", "password", "token", "url", "no_check", "no_fscheck"]
)

# DirectEdit details, returned from DirectEdit._extract_edit_info()
DirectEditDetails = namedtuple(
    "details", ["uid", "engine", "digest_func", "digest", "xpath", "editing"]
)

# List of filters from the database
Filters = List[str]

# Metrics
Metrics = Dict[str, Any]

# Autolocker items
Item = Tuple[int, Path]
Items = List[Item]


# Data Transfer Object for remote file info
@dataclass
class RemoteFileInfo:
    name: str  # title of the file (not guaranteed to be locally unique)
    uid: str  # id of the file
    parent_uid: str  # id of the parent file
    path: str  # abstract file system path: useful for ordering folder trees
    folderish: bool  # True is can host children
    last_modification_time: Optional[datetime]  # last update time
    creation_time: Optional[datetime]  # creation time
    last_contributor: Optional[str]  # last contributor
    digest: Optional[str]  # digest of the file
    digest_algorithm: Optional[str]  # digest algorithm of the file
    download_url: Optional[str]  # download URL of the file
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
        try:
            uid = fs_item["id"]
            parent_uid = fs_item["parentId"]
            path = fs_item["path"]
            name = unicodedata.normalize("NFC", fs_item["name"])
        except KeyError:
            raise DriveError(f"This item is missing mandatory information: {fs_item}")

        folderish = fs_item.get("folder", False)

        def to_date(timestamp: Optional[int]) -> Optional[datetime]:
            if not isinstance(timestamp, int):
                return None

            try:
                return datetime.fromtimestamp(timestamp // 1000)
            except (OSError, OverflowError):
                # OSError: [Errno 22] Invalid argument (Windows 7, see NXDRIVE-1600)
                # OverflowError: timestamp out of range for platform time_t
                return None

        last_update = to_date(fs_item.get("lastModificationDate"))
        creation = to_date(fs_item.get("creationDate"))

        if folderish:
            digest = None
            digest_algorithm = None
            download_url = None
            can_update = False
            can_create_child = fs_item.get("canCreateChild", False)
            # Scroll API availability
            can_scroll = fs_item.get("canScrollDescendants", False)
            can_scroll_descendants = can_scroll
        else:
            digest = fs_item.get("digest")
            digest_algorithm = fs_item.get("digestAlgorithm")
            if digest_algorithm:
                digest_algorithm = digest_algorithm.lower().replace("-", "")
            download_url = fs_item.get("downloadURL")
            can_update = fs_item.get("canUpdate", False)
            can_create_child = False
            can_scroll_descendants = False

        # Lock info
        lock_info = fs_item.get("lockInfo")
        lock_owner = lock_created = None
        if lock_info:
            lock_owner = lock_info.get("owner")
            lock_created = lock_info.get("created")
            if lock_created:
                lock_created = datetime.fromtimestamp(lock_created // 1000)

        return RemoteFileInfo(
            name,
            uid,
            parent_uid,
            path,
            folderish,
            last_update,
            creation,
            fs_item.get("lastContributor"),
            digest,
            digest_algorithm,
            download_url,
            fs_item.get("canRename", False),
            fs_item.get("canDelete", False),
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
        size = int(blob.get("length", 0))
        mimetype = blob.get("mime-type", "application/octet-stream")
        data = blob.get("data", "")

        if digest_algorithm:
            digest_algorithm = digest_algorithm.lower().replace("-", "")

        return Blob(name, digest, digest_algorithm, size, mimetype, data)


# Data Transfer Object for doc info on the Remote Nuxeo repository
@dataclass
class NuxeoDocumentInfo:
    root: str  # ref of the document that serves as sync root
    name: str  # title of the document (not guaranteed to be locally unique)
    uid: str  # ref of the document
    parent_uid: Optional[str]  # ref of the parent document
    path: str  # remote path (useful for ordering)
    folderish: bool  # True is can host child documents
    last_modification_time: Optional[datetime]  # last update time
    last_contributor: str  # last contributor
    repository: str  # server repository name
    doc_type: Optional[str]  # Nuxeo document type
    version: Optional[str]  # Nuxeo version
    state: Optional[str]  # Nuxeo lifecycle state
    is_trashed: bool  # Nuxeo trashed status
    is_version: bool  # is it a version of a document
    lock_owner: Optional[str]  # lock owner
    lock_created: Optional[datetime]  # lock creation time
    permissions: List[str]  # permissions
    properties: Dict[str, Any]  # properties

    @staticmethod
    def from_dict(doc: Dict[str, Any], parent_uid: str = None) -> "NuxeoDocumentInfo":
        """Convert Automation document description to NuxeoDocumentInfo"""
        try:
            root = doc["root"]
            uid = doc["uid"]
            path = doc["path"]
            props = doc["properties"]
            name = unicodedata.normalize("NFC", props["dc:title"])
            folderish = "Folderish" in doc["facets"]
            modified = doc["lastModified"]
        except KeyError:
            raise DriveError(f"This document is missing mandatory information: {doc}")

        last_update = parser.parse(modified)

        # Lock info
        lock_owner = doc.get("lockOwner")
        lock_created = doc.get("lockCreated")
        if lock_created:
            lock_created = parser.parse(lock_created)

        # Permissions
        permissions = doc.get("contextParameters", {}).get("permissions", None)

        # Trashed
        is_trashed = doc.get("isTrashed", doc.get("state") == "deleted")

        # Is version of document
        is_version = doc.get("isVersion", False)

        # XXX: we need another roundtrip just to fetch the parent uid...

        # Normalize using NFC to make the tests more intuitive
        version = None
        if "uid:major_version" in props and "uid:minor_version" in props:
            version = (
                str(props["uid:major_version"]) + "." + str(props["uid:minor_version"])
            )
        return NuxeoDocumentInfo(
            root,
            name,
            uid,
            parent_uid,
            path,
            folderish,
            last_update,
            props.get("dc:lastContributor"),
            doc.get("repository", "default"),
            doc.get("type"),
            version,
            doc.get("state"),
            is_trashed,
            is_version,
            lock_owner,
            lock_created,
            permissions,
            props,
        )

    def get_blob(self, xpath: str) -> Optional[Blob]:
        props = self.properties

        # Note editing is a special case
        if xpath == "note:note" and self.doc_type == "Note":
            note = props.get("note:note")
            if note:
                digest = hashlib.sha256()
                digest.update(note.encode("utf-8"))
                return Blob.from_dict(
                    {
                        "name": props["dc:title"],
                        "digest": digest.hexdigest(),
                        "digestAlgorithm": "sha256",
                        "length": len(note),
                        "mime-type": props.get("note:mime_type"),
                        "data": note,
                    }
                )

        # Attachments are in a specific array
        elif xpath.startswith("files:files"):
            attachments = props.get("files:files")
            if attachments:
                idx = int(xpath.split("/")[1])
                return Blob.from_dict(attachments[idx]["file"])

        # All other blobs should be directly accessible in the properties
        # and follow the default formatting. If that is not the case,
        # we'll let the error rise.
        elif xpath in props:
            return Blob.from_dict(props[xpath])

        return None


class DocPair(Row):

    id: int
    last_local_updated: str
    last_remote_updated: str
    local_digest: Optional[str]
    remote_digest: str
    local_path: Path
    remote_ref: str
    local_parent_path: Path
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
            f" local_parent_path={self.local_parent_path!r},"
            f" remote_ref={self.remote_ref!r},"
            f" local_state={self.local_state!r},"
            f" remote_state={self.remote_state!r},"
            f" pair_state={self.pair_state!r},"
            f" filter_path={self.path!r}"
            ">"
        )

    def __getattr__(self, name: str) -> Optional[Union[str, Path]]:
        with suppress(IndexError):
            if name in {"local_path", "local_parent_path"}:
                return Path((self[name] or "").lstrip("/"))
            if name == "remote_ref":
                return self[name] or ""
            return self[name]

    def export(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "state": self.pair_state,
            "last_sync_date": "",
            "last_sync_direction": "upload",
            "name": self.local_name or self.remote_name,
            "remote_name": self.remote_name,
            "last_error": self.last_error,
            "local_path": str(self.local_path),
            "local_parent_path": str(self.local_parent_path),
            "remote_ref": self.remote_ref,
            "folderish": self.folderish,
            "id": self.id,
            "size": self.size,
        }

        if self.last_local_updated or "" > self.last_remote_updated or "":
            result["last_sync_direction"] = "download"
        result["last_transfer"] = self.last_transfer or result["last_sync_direction"]

        # Last sync in sec
        current_time = int(time())
        date_time = get_date_from_sqlite(self.last_sync_date)
        sync_time = get_timestamp_from_date(date_time)
        result["last_sync"] = current_time - sync_time

        if date_time:
            # As date_time is in UTC
            result["last_sync_date"] = Translator.format_datetime(
                date_time + tzlocal().utcoffset(date_time)  # type: ignore
            )

        return result

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


class EngineDef(Row):
    local_folder: Path
    engine: str
    uid: str
    name: str

    def __getattr__(self, name: str) -> Optional[Union[str, Path]]:
        with suppress(IndexError):
            if name == "local_folder":
                return Path(self[name])
            return self[name]


@dataclass
class Transfer:
    uid: Optional[int]
    path: Path
    name: str = field(init=False)
    status: TransferStatus
    engine: str = None
    is_direct_edit: bool = False
    progress: float = 0.0
    doc_pair: Optional[int] = None

    def __post_init__(self) -> None:
        self.name = self.path.name


@dataclass
class Download(Transfer):
    transfer_type: str = field(init=False, default="download")
    tmpname: Optional[str] = None
    url: Optional[str] = None


@dataclass
class Upload(Transfer):
    transfer_type: str = field(init=False, default="upload")
    batch: Optional[str] = None
    idx: Optional[int] = None
    chunk_size: Optional[int] = None
