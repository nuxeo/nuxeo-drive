from functools import partial
from logging import getLogger
from typing import Iterator, List, Union

from nuxeo.models import Document

from ..client.remote_client import Remote
from ..objects import Filters, RemoteFileInfo
from ..options import Options
from ..qt import constants as qt
from ..qt.imports import QObject, Qt
from ..translator import Translator

__all__ = ("Documents", "FileInfo", "FilteredDocuments", "FilteredDoc")


log = getLogger(__name__)


class FileInfo:
    """The base class of a document."""

    def __init__(self, *, parent: QObject = None) -> None:
        self.parent = parent
        self.children: List["FileInfo"] = []

        # Append the current document as a child of its parent
        if parent:
            parent.add_child(self)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}<id={self.get_id()}, "
            f"label={self.get_label()}, parent={self.get_path()!r}>"
        )

    def add_child(self, child: "FileInfo", /) -> None:
        """Add a new child to the parent item."""
        self.children.append(child)

    def get_children(self) -> Iterator["FileInfo"]:
        """Get all children."""
        yield from self.children

    def enable(self) -> bool:
        """The document can be clicked."""
        return True

    def selectable(self) -> bool:
        """The document can be selected, e.g.: its children can be fetched."""
        return True

    def checkable(self) -> bool:
        """The document can be checked."""
        return True

    def get_label(self) -> str:
        """The document's name as it is showed in the tree."""
        return ""

    def get_id(self) -> str:
        """The document's UID."""
        return ""

    def folderish(self) -> bool:
        """True if the document has the Folderish facet."""
        return False

    def is_hidden(self) -> bool:
        """True if the document is hidden."""
        return False

    def get_path(self) -> str:
        """Guess the document's path on the server."""
        path = ""
        if self.parent is not None:
            path += self.parent.get_path()
        path += "/" + self.get_id()
        return path


class Doc(FileInfo):
    """A folderish document. Used by the Direct Transfer feature."""

    def __init__(self, doc: Document, /, *, parent: FileInfo = None) -> None:
        super().__init__(parent=parent)
        self.doc = doc

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}<id={self.get_id()}, label={self.get_label()}, "
            f"parent={self.get_path()!r}, enable={self.enable()!r}, selectable={self.selectable()!r}>"
        )

    def folderish(self) -> bool:
        """Only folders are used, so it is always True."""
        return True

    def enable(self) -> bool:
        """Allow to select the folder only if the user can effectively create documents inside."""
        return (
            "HiddenInCreation" not in self.doc.facets
            and self.doc.type not in Options.disallowed_types_for_dt
            and "AddChildren" in self.doc.contextParameters["permissions"]
        )

    def get_id(self) -> str:
        """The document's UID."""
        return self.doc.uid

    def get_label(self) -> str:
        """The document's name as it is showed in the tree."""
        return self.doc.title

    def get_path(self) -> str:
        """Guess the document's path on the server."""
        return self.doc.path

    def selectable(self) -> bool:
        """Allow to fetch its children only if the user has at least the "Read" privilege."""
        return "Read" in self.doc.contextParameters["permissions"]


class FilteredDoc(FileInfo):
    """A document. Used by the filters feature."""

    def __init__(
        self,
        fs_info: RemoteFileInfo,
        state: Qt.CheckState,
        /,
        *,
        parent: "Documents" = None,
    ) -> None:
        super().__init__(parent=parent)

        self.fs_info = fs_info

        # Handle the document's state
        if parent and parent.is_dirty():  # type: ignore
            self.state: Qt.CheckState = parent.state  # type: ignore
            self.old_state = state
        else:
            self.old_state = self.state = state

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}<state={self.state}, id={self.get_id()}, "
            f"label={self.get_label()}, folderish={self.folderish()!r}, parent={self.get_path()!r}>"
        )

    def get_label(self) -> str:
        """The document's name as it is showed in the tree."""
        return self.fs_info.name

    def get_path(self) -> str:
        """Guess the document's path on the server."""
        return self.fs_info.path

    def get_id(self) -> str:
        """The document's UID."""
        return self.fs_info.uid

    def folderish(self) -> bool:
        """True if the document has the Folderish facet."""
        return self.fs_info.folderish

    def is_dirty(self) -> bool:
        """The document's state has changed and need to be updated."""
        return self.old_state != self.state


class FilteredDocuments:
    """Display all documents (files and folders) of all sync roots. Used by the filters feature."""

    def __init__(self, remote: Remote, filters: Filters, /) -> None:
        self.remote = remote
        self.filters = tuple(filters)
        self.roots: List["Documents"] = []

    def get_item_state(self, path: str, /) -> Qt.CheckState:
        """Guess the new item state based on its parent state from actual filtered documents."""
        if not path.endswith("/"):
            path += "/"

        if path.startswith(self.filters):
            # The document is filtered
            return qt.Unchecked
        elif any(filter_path.startswith(path) for filter_path in self.filters):
            # The document has a child that is filtered
            return qt.PartiallyChecked

        # The document is not filtered at all
        return qt.Checked

    def get_top_documents(self) -> Iterator["Documents"]:
        """Fetch all sync roots."""
        root_info = self.remote.get_filesystem_root_info()
        for sync_root in self.remote.get_fs_children(root_info.uid, filtered=False):
            root = FilteredDoc(sync_root, self.get_item_state(sync_root.path))
            self.roots.append(root)
            yield root

    def get_children(self, parent: "Documents", /) -> Iterator["Documents"]:
        """Fetch children of a given *parent*."""
        for info in self.remote.get_fs_children(parent.get_id(), filtered=False):
            yield FilteredDoc(info, self.get_item_state(info.path), parent=parent)


class FoldersOnly:
    """Display _all_, and only, folders from the remote server. Used by the Direct Transfer feature."""

    def __init__(self, remote: Remote, /) -> None:
        self.remote = remote
        self.children = partial(
            self.remote.documents.get_children, enrichers=["permissions"]
        )

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

    def _get_root_folders(self) -> List["Documents"]:
        """Get root folders.
        Use a try...except block to prevent loading error on the root,
        else it will also show a loading error for the personal space.
        """
        try:
            return [
                Doc(doc) for doc in self.children(path="/") if "Folderish" in doc.facets
            ]
        except Exception:
            log.warning("Error while retrieving documents on '/'", exc_info=True)
            return [Doc(Document(title="/", contextParameters={"permissions": []}))]

    def get_top_documents(self) -> Iterator["Documents"]:
        """Fetch all documents at the root."""
        if not Options.dt_hide_personal_space:
            yield self._get_personal_space()
        yield from self._get_root_folders()

    def get_children(self, parent: "Documents", /) -> Iterator["Documents"]:
        """Fetch children of a given *parent*."""
        for doc in self.children(uid=parent.get_id()):
            if "Folderish" in doc.facets:
                yield Doc(doc, parent=parent)


Documents = Union[Doc, FilteredDoc]
