import hashlib
import unicodedata
from collections import namedtuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from sqlite3 import Row
from time import time
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

from dateutil import parser
from dateutil.tz import tzlocal
from nuxeo.models import Batch
from nuxeo.utils import get_digest_algorithm

from .auth import Token
from .constants import TransferStatus
from .exceptions import DriveError
from .translator import Translator
from .utils import get_date_from_sqlite, get_timestamp_from_date


class Binder(NamedTuple):
    """Settings passed to Manager.bind_server()."""

    username: str
    password: str
    token: Optional[Token]
    url: str
    no_check: bool
    no_fscheck: bool


# Direct Edit details, returned from DirectEdit._extract_edit_info()
DirectEditDetails = namedtuple(
    "DirectEditDetails", ["uid", "engine", "digest_func", "digest", "xpath", "editing"]
)

# List of filters from the database
Filters = List[str]

# Metrics
Metrics = Dict[str, Any]

# Autolocker items
Item = Tuple[int, Path]
Items = List[Item]


def _guess_digest_and_algo(item: Dict[str, Any]) -> Tuple[str, str]:
    """Guess the digest and the algorithm used, if not already specified."""
    digest = item.get("digest") or ""
    digest_algorithm = item.get("digestAlgorithm") or ""
    if digest_algorithm:
        digest_algorithm = digest_algorithm.lower().replace("-", "")
    elif digest:
        digest_algorithm = get_digest_algorithm(digest) or ""
    return digest, digest_algorithm


def _to_date(timestamp: Optional[int]) -> Optional[datetime]:
    if not isinstance(timestamp, int):
        return None

    try:
        return datetime.fromtimestamp(timestamp // 1000)
    except (OSError, OverflowError):
        # OSError: [Errno 22] Invalid argument (Windows 7, see NXDRIVE-1600)
        # OverflowError: timestamp out of range for platform time_t
        return None


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
    # True if the API to scroll through the descendants can be used
    can_scroll_descendants: bool

    @staticmethod
    def from_dict(fs_item: Dict[str, Any], /) -> "RemoteFileInfo":
        """Convert Automation file system item description to RemoteFileInfo"""
        try:
            uid = fs_item["id"]
            parent_uid = fs_item["parentId"]
            path = fs_item["path"]
            name = unicodedata.normalize("NFC", fs_item["name"])
        except (KeyError, TypeError):
            raise DriveError(f"This item is missing mandatory information: {fs_item}")

        folderish = fs_item.get("folder", False)
        last_update = _to_date(fs_item.get("lastModificationDate"))
        creation = _to_date(fs_item.get("creationDate"))

        if folderish:
            digest = None
            digest_algorithm = None
            download_url = None
            can_update = False
            can_create_child = fs_item.get("canCreateChild", False)
            # Scroll API availability
            can_scroll_descendants = fs_item.get("canScrollDescendants", False)
        else:
            digest, digest_algorithm = _guess_digest_and_algo(fs_item)
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
    digest: str  # hash of the blob
    digest_algorithm: str  # algorithm used to compute the digest
    size: int  # size of the blob in bytes
    mimetype: str  # mime-type of the blob
    data: str  # download url of the blob or content if it's a note

    @staticmethod
    def from_dict(blob: Dict[str, Any], /) -> "Blob":
        """Convert Dict to Blob object."""
        name = blob["name"]
        digest, digest_algorithm = _guess_digest_and_algo(blob)
        size = int(blob.get("length", 0))
        mimetype = blob.get("mime-type") or ""
        data = blob.get("data") or ""
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
    is_proxy: bool  # Is a proxy of a document
    is_version: bool  # is it a version of a document
    lock_owner: Optional[str]  # lock owner
    lock_created: Optional[datetime]  # lock creation time
    permissions: List[str]  # permissions
    properties: Dict[str, Any]  # properties

    @staticmethod
    def from_dict(
        doc: Dict[str, Any], /, *, parent_uid: str = None
    ) -> "NuxeoDocumentInfo":
        """Convert Automation document description to NuxeoDocumentInfo"""
        try:
            root = doc["root"]
            uid = doc["uid"]
            path = doc["path"]
            props = doc["properties"]
            name = unicodedata.normalize("NFC", props["dc:title"])
            folderish = "Folderish" in doc["facets"]
            modified = doc["lastModified"]
        except (KeyError, TypeError):
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

        # Is a proxy
        is_proxy = doc.get("isProxy", False)

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
            is_proxy,
            is_version,
            lock_owner,
            lock_created,
            permissions,
            props,
        )

    def get_blob(self, xpath: str, /) -> Optional[Blob]:
        """Retrieve blob details from a given *xpath*.
        There is no real limitation on the *xpath*.
        Those are all valid if they are present in the *properties* attribute
        (given "s" for string and "n" for number):

            - s:s (file:content, foo:bar, note:note)
            - s:s/n (files:files/0, foo:bar/0)
            - s:s/n/s (files:files/0/file)
            - s:s/n/n/n/n/s/n/s/... (foo:baz/0/0/0/0/file/0/real:file...)

        Notes handling is stricter, only "note:note" *xpath* is taken into account.
        """
        props = self.properties

        # Note is a special case
        if xpath == "note:note" and self.doc_type == "Note":
            note = props.get("note:note")
            if not note:
                return None

            digest = hashlib.md5()
            digest.update(note.encode("utf-8"))
            return Blob.from_dict(
                {
                    "name": props["dc:title"],
                    "digest": digest.hexdigest(),
                    "digestAlgorithm": "md5",
                    "length": len(note),
                    "mime-type": props.get("note:mime_type"),
                    "data": note,
                }
            )

        # Attachments are in a specific array
        attachment: Optional[Dict[str, Any]] = None

        parts = xpath.split("/")
        while parts:
            part = parts.pop(0)

            # Handle numeric values: "0" -> 0
            key = int(part) if part.isnumeric() else part

            if attachment is None:
                # The first "get" is from the *properties* dict
                attachment = props.get(key)  # type: ignore
            else:
                # Then we iterate over the structure (either a list or a dict)
                try:
                    attachment = attachment[key]  # type: ignore
                except (IndexError, KeyError):
                    attachment = None

            if not attachment:
                # Malformed data
                break

        return Blob.from_dict(attachment) if attachment else None


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
    duplicate_behavior: str
    session: int

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__}[{self.id!r}]"
            f" local_path={self.local_path!r},"
            f" local_parent_path={self.local_parent_path!r},"
            f" remote_ref={self.remote_ref!r},"
            f" local_state={self.local_state!r},"
            f" remote_state={self.remote_state!r},"
            f" pair_state={self.pair_state!r},"
            f" last_error={self.last_error!r}"
            ">"
        )

    def __getattr__(self, name: str, /) -> Optional[Union[str, Path]]:
        if name in ("local_path", "local_parent_path"):
            return Path((self[name] or "").lstrip("/"))
        if name == "remote_ref":
            return self[name] or ""
        return self[name]  # type: ignore

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

        if (self.last_local_updated or "") > (self.last_remote_updated or ""):
            result["last_sync_direction"] = "download"
        result["last_transfer"] = self.last_transfer or result["last_sync_direction"]

        # Last sync in sec
        current_time = int(time())
        date_time = get_date_from_sqlite(self.last_sync_date)
        sync_time = get_timestamp_from_date(date_time)
        result["last_sync"] = current_time - sync_time

        if date_time:
            # As date_time is in UTC
            offset = tzlocal().utcoffset(date_time)
            if offset:
                result["last_sync_date"] = Translator.format_datetime(
                    date_time + offset
                )

        return result

    def is_readonly(self) -> bool:
        if self.folderish:
            return self.remote_can_create_child == 0
        return (
            self.remote_can_delete & self.remote_can_rename & self.remote_can_update
        ) == 0

    def update_state(self, local_state: str, remote_state: str) -> None:
        self.local_state = local_state
        self.remote_state = remote_state


DocPairs = List[DocPair]


class EngineDef(Row):
    local_folder: Path
    engine: str
    uid: str
    name: str

    def __getattr__(self, name: str, /) -> Optional[Union[str, Path]]:
        if name == "local_folder":
            return Path(self[name])
        return self[name]  # type: ignore

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} "
            f"name={self.name!r}, "
            f"local_folder={str(self.local_folder)!r}, "
            f"uid={self.uid!r}, "
            f"type={self.engine!r}>"
        )


@dataclass
class Transfer:
    uid: Optional[int]
    path: Path
    name: str = field(init=False)
    status: TransferStatus
    engine: str
    is_direct_edit: bool = False
    is_direct_transfer: bool = False
    progress: float = 0.0
    doc_pair: Optional[int] = None
    filesize: int = 0

    def __post_init__(self) -> None:
        self.name = self.path.name


@dataclass
class Download(Transfer):
    transfer_type: str = field(init=False, default="download")
    tmpname: Optional[Path] = None
    url: Optional[str] = None


@dataclass
class Upload(Transfer):
    transfer_type: str = field(init=False, default="upload")
    batch: dict = field(default_factory=dict)
    chunk_size: int = 0
    remote_parent_path: str = ""
    remote_parent_ref: str = ""
    batch_obj: Batch = None
    request_uid: Optional[str] = None
    is_dirty: bool = field(init=False, default=False)

    def token_callback(self, batch: Batch, _: Dict[str, Any]) -> None:
        """Callback triggered when token is refreshed."""
        self.batch = batch.as_dict()
        self.is_dirty = True


@dataclass
class Session:
    uid: int
    remote_path: str
    remote_ref: str
    status: TransferStatus
    uploaded_items: int
    total_items: int
    engine: str
    created_on: str
    completed_on: str
    description: str
    planned_items: int
