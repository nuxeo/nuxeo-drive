"""Nuxeo-specific data transfer objects."""

import hashlib
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from dateutil import parser

from nxdrive.drive.exceptions import DriveError
from nxdrive.drive.objects import Blob, DocumentInfo

__all__ = ("NuxeoDocumentInfo",)


# Data Transfer Object for doc info on the Remote Nuxeo repository
@dataclass
class NuxeoDocumentInfo(DocumentInfo):
    root: str = ""  # ref of the document that serves as sync root
    repository: str = ""  # server repository name
    doc_type: Optional[str] = None  # Nuxeo document type
    version: Optional[str] = None  # Nuxeo version
    state: Optional[str] = None  # Nuxeo lifecycle state
    is_trashed: bool = False  # Nuxeo trashed status
    is_proxy: bool = False  # Is a proxy of a document
    is_version: bool = False  # is it a version of a document
    properties: Dict[str, Any] = field(default_factory=dict)  # properties

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
            name=name,
            uid=uid,
            parent_uid=parent_uid,
            path=path,
            folderish=folderish,
            last_modification_time=last_update,
            last_contributor=props.get("dc:lastContributor"),
            lock_owner=lock_owner,
            lock_created=lock_created,
            permissions=permissions,
            root=root,
            repository=doc.get("repository", "default"),
            doc_type=doc.get("type"),
            version=version,
            state=doc.get("state"),
            is_trashed=is_trashed,
            is_proxy=is_proxy,
            is_version=is_version,
            properties=props,
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
