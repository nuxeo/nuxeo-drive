from logging import getLogger
from typing import TYPE_CHECKING, List, Optional

from ..qt import constants as qt
from ..qt.imports import QRunnable, QStandardItem, QStandardItemModel, QVariant
from ..translator import Translator
from .folders_model import Doc, Documents, FilteredDoc

if TYPE_CHECKING:
    from .folders_treeview import TreeViewMixin  # noqa

__all__ = ("DocumentContentLoader", "FolderContentLoader")

log = getLogger(__name__)


class ContentLoaderMixin(QRunnable):
    """The base class for content loading of the tree view."""

    def __init__(
        self, tree: "TreeViewMixin", /, *, item: QStandardItemModel = None
    ) -> None:
        super().__init__()
        self.tree = tree
        self.item = item or self.tree.model().invisibleRootItem()
        self.info: Optional[Documents] = None
        if item:
            self.info = self.item.data(qt.UserRole)

    def run(self) -> None:
        """Fetch children of a given item."""
        item, info = self.item, self.info
        if info:
            if info.get_id() in self.tree.cache:
                self.tree.set_loading_cursor(False)
                return

            self.tree.cache.append(info.get_id())

        try:
            if info:
                children = list(self.tree.client.get_children(info))
            else:
                children = list(self.tree.client.get_top_documents())
        except Exception:
            path = info.get_path() if info else "root"
            log.warning(f"Error while retrieving documents on {path!r}", exc_info=True)
            self.tree.set_loading_cursor(False)
            item.removeRows(0, item.rowCount())
            item.appendRow(
                QStandardItem(Translator.get("LOADING_ERROR") + " \U0001F937")
            )
            return

        # Used with the filters window only
        if not info and not children and hasattr(self.tree, "noRoots"):
            self.tree.noRoots.emit(True)

        self.fill_tree(children)
        self.tree.set_loading_cursor(False)

    def add_loading_subitem(self, item: QStandardItem, /) -> None:
        """Add "Loading..." entry in advance for when the user will click on an item to expand it."""
        load_item = QStandardItem(Translator.get("LOADING"))
        load_item.setSelectable(False)
        item.appendRow(load_item)

    def new_subitem(self, child: QStandardItem) -> QStandardItem:
        """A new child of an item is available. To be implemented by specific classes."""
        raise NotImplementedError()

    def sort_children(self, children: List[Documents], /) -> List[Documents]:
        """Sort child alphabetically (NXDRIVE-12).
        Put in a specific method to be able to override if needed.
        """
        return sorted(children, key=lambda x: x.get_label().lower())

    def fill_tree(self, children: List[Documents], /) -> None:
        """Fill the tree view with the new fetched children."""
        self.item.removeRows(0, self.item.rowCount())
        for child in self.sort_children(children):
            subitem = self.new_subitem(child)
            if child.folderish() and child.selectable():
                # Add a placeholder subitem to subitmen to show a loading message
                self.add_loading_subitem(subitem)
            self.item.appendRow(subitem)


class DocumentContentLoader(ContentLoaderMixin):
    """A contents loader for synced documents. Used by the filters feature."""

    def new_subitem(self, child: FilteredDoc, /) -> QStandardItem:
        """A new child of an item is available. Create an item to append to its parent.
        The new item is a checkable item with 3 states.
        """
        subitem = QStandardItem(child.get_label())
        if child.checkable():
            subitem.setCheckable(True)
            subitem.setCheckState(True)
            subitem.setTristate(True)
            subitem.setCheckState(child.state)
        subitem.setEnabled(child.enable())
        subitem.setSelectable(child.selectable())
        subitem.setEditable(False)
        subitem.setData(QVariant(child), qt.UserRole)
        return subitem


class FolderContentLoader(ContentLoaderMixin):
    """A contents loader for folderish documents. Used by the Direct Transfer feature."""

    def new_subitem(self, child: Doc, /) -> QStandardItem:
        """A new child of an item is available. Create an item to append to its parent.
        The new item is a simple selectable item (if the user has enough right to).
        """
        subitem = QStandardItem(child.get_label())
        subitem.setEnabled(child.enable())
        subitem.setSelectable(child.selectable())
        subitem.setEditable(False)
        subitem.setData(QVariant(child), qt.UserRole)
        return subitem
