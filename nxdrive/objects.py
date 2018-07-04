# coding: utf-8
from collections import namedtuple
from sqlite3 import Cursor
from typing import Any, Dict, List, Tuple

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

# Data Transfer Object for remote file info
RemoteFileInfo = namedtuple(
    "RemoteFileInfo",
    [
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
    ],
)

# Data Transfer Object for doc info on the Remote Nuxeo repository
NuxeoDocumentInfo = namedtuple(
    "NuxeoDocumentInfo",
    [
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
    ],
)
