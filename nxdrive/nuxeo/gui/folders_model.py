"""Nuxeo-specific folder/document tree providers.

Generic tree-model classes (``FileInfo``, ``Doc``, ``FilteredDoc``,
``FilteredDocuments``, ``Documents``) are in ``nxdrive.drive.gui.folders_model``
and re-exported here for backward compatibility.
"""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Iterator, List

from nuxeo.models import Document

from nxdrive.drive.constants import USER_WORKSPACE
from nxdrive.drive.gui.folders_model import (  # noqa: F401 – re-exports
    Doc,
    Documents,
    FileInfo,
    FilteredDoc,
    FilteredDocuments,
    FoldersOnlyBase,
    FromDict,
)
from nxdrive.drive.options import Options
from nxdrive.drive.translator import Translator

if TYPE_CHECKING:
    from nxdrive.nuxeo.client.remote_client import Remote

__all__ = (
    "Documents",
    "Doc",
    "FileInfo",
    "FilteredDoc",
    "FilteredDocuments",
    "FoldersOnly",
)

log = getLogger(__name__)


class FoldersOnly(FoldersOnlyBase):
    """Display _all_, and only, folders from the remote server. Used by the Direct Transfer feature."""

    def __init__(self, remote: Remote, /) -> None:
        super().__init__(remote)

    def get_personal_space(self) -> "Documents":
        """Retrieve the "Personal space" special folder."""
        personal_space = self.remote.personal_space()

        # Alter the title to use "Personal space" instead of "Firstname Lastname"
        personal_space.title = Translator.get("PERSONAL_SPACE")

        # Append permissions, the user always has write rights on its own space
        personal_space.contextParameters["permissions"] = [
            "AddChildren",
            "Read",
            "ReadWrite",
        ]

        return Doc(personal_space)

    def _get_personal_space(self) -> "Document":
        """Get the personal space.
        Use a try...except block to prevent loading error on the root,
        else it will also show a loading error for root folder.
        """
        try:
            return self.get_personal_space()
        except Exception:
            path = f"/default-domain/UserWorkspaces/{self.remote.user_id}"
            log.warning(f"Error while retrieving documents on {path!r}", exc_info=True)
            return Doc(
                Document(
                    title=Translator.get("PERSONAL_SPACE"),
                    contextParameters={"permissions": []},
                )
            )

    def get_roots(self) -> List:
        from nxdrive.drive.constants import QUERY_ENDPOINT

        url = f"{QUERY_ENDPOINT}select * from Document WHERE ecm:mixinType = 'Folderish' and ecm:isTrashed = 0"
        return self.remote.client.request("GET", url).json()["entries"]

    def _get_root_folders(self) -> List["Documents"]:
        """Get root folders.
        Use a try...except block to prevent loading error on the root,
        else it will also show a loading error for the personal space.
        """
        try:
            root = self.remote.documents.get(path="/")
            return [Doc(doc) for doc in self._get_children(root.uid)]
        except Exception:
            if Options.shared_folder_navigation:
                roots = self.get_roots()
                ret_list = []
                for root in roots:
                    if root["type"] == "Folder" and not root["path"].startswith(
                        USER_WORKSPACE
                    ):
                        doc = self.remote.fetch(
                            root["uid"],
                            enrichers=["permissions"],
                        )
                        if (
                            "Write" in doc["contextParameters"]["permissions"]
                            or "ReadWrite" in doc["contextParameters"]["permissions"]
                            or "Everything" in doc["contextParameters"]["permissions"]
                        ):
                            ret_list.append(Doc(doc, False, True))
                return ret_list
            else:
                log.warning("Error while retrieving documents on '/'", exc_info=True)
                context = {"permissions": [], "hasFolderishChild": False}
                return [Doc(Document(title="/", contextParameters=context))]

    def get_top_documents(self) -> Iterator["Documents"]:
        """Fetch all documents at the root."""
        if not Options.dt_hide_personal_space:
            yield self._get_personal_space()
        yield from self._get_root_folders()

    def get_children(self, parent: "Documents", /) -> Iterator["Documents"]:
        """Fetch children of a given *parent*."""
        for doc in self._get_children(parent.get_id()):
            yield Doc(doc, parent=parent)

    def _get_children(self, parent_uid: str) -> List[Document]:
        """Fetch all children of a given *parent*."""
        page_provider_args = {
            "pageProvider": "tree_children",
            "pageSize": -1,
            "queryParams": parent_uid,
        }
        docs = []
        page = 0
        while "there are children":
            page_provider_args["currentPageIndex"] = page
            new_docs = self.remote.documents.query(
                opts=page_provider_args,
                enrichers=["permissions", "hasFolderishChild"],
            )
            docs.extend(new_docs["entries"])
            if not new_docs["isNextPageAvailable"]:
                break
            page += 1
        return docs
