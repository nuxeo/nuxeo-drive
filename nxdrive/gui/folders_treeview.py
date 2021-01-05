from typing import TYPE_CHECKING, List, Union

from ..qt import constants as qt
from ..qt.imports import (
    QItemSelection,
    QModelIndex,
    QObject,
    QStandardItemModel,
    QThreadPool,
    QTreeView,
    pyqtSignal,
)
from .folders_loader import DocumentContentLoader, FolderContentLoader
from .folders_model import FilteredDocuments, FoldersOnly

if TYPE_CHECKING:
    from .folders_dialog import DialogMixin, DocumentsDialog, FoldersDialog  # noqa

__all__ = ("DocumentTreeView", "FolderTreeView")


class TreeViewMixin(QTreeView):
    """The base class of a tree view."""

    def __init__(
        self, parent: "DialogMixin", client: Union[FoldersOnly, FilteredDocuments], /
    ) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)

        self.parent = parent
        self.client = client

        self.cache: List[str] = []
        self.root_item = QStandardItemModel()
        self.setModel(self.root_item)

        # At start, fetch top level folders (Direct Transfer) or sync roots (filters)
        self.load_children()

        # When an item is clicked, load its children
        self.expanded.connect(self.expand_item)

    def expand_item(self, index: QModelIndex, /) -> None:
        """When an item is clicked, load its children."""
        index = self.model().index(index.row(), 0, index.parent())
        item = self.model().itemFromIndex(index)
        self.load_children(item=item)

    def load_children(self, *, item: QStandardItemModel = None) -> None:
        """Load children of a given *item*."""
        if not self.client:
            # May happen when the user has invalid credentials
            self.set_loading_cursor(False)
            return

        self.set_loading_cursor(True)
        loader = self.loader(self, item=item)
        QThreadPool.globalInstance().start(loader)

    def set_loading_cursor(self, busy: bool, /) -> None:
        """Set the cursor based on the actual status.
        When busy, it means children are being fetched (i.e. a HTTP call is ongoing).
        In that case, change the cursor to let the user know something is happening.
        """
        try:
            if busy:
                self.setCursor(qt.BusyCursor)
            else:
                self.unsetCursor()
        except RuntimeError:
            # RuntimeError: wrapped C/C++ object of type FolderTreeView has been deleted
            # May happen if the window is deleted early.
            pass


class DocumentTreeView(TreeViewMixin):
    """A tree view of all sync roots and their documents. Used by the filters feature."""

    # Signal emitted when the user has no sync root yet
    noRoots = pyqtSignal(bool)

    # The content's loader for synced documents
    loader = DocumentContentLoader

    def __init__(self, parent: "DocumentsDialog", client: FilteredDocuments, /) -> None:
        super().__init__(parent, client)

        # When an item is changed, update its eventual parents and children states
        self.root_item.itemChanged.connect(self.resolve_item)

        # Keep track of dirty items
        self.dirty_items: List[QStandardItemModel] = []

    def update_item_changed(self, item: QObject, /) -> None:
        """Append the item the the *.dirty_items* dict.
        That dict will be used by DocumentsDialog.apply_filters() tp update the view.
        """
        fs_info = item.data(qt.UserRole)

        # Fake children have no data attached
        if not fs_info:
            return

        fs_info.state = item.checkState()
        is_in_dirty = fs_info in self.dirty_items
        is_dirty = fs_info.is_dirty()

        if is_dirty and not is_in_dirty:
            self.dirty_items.append(fs_info)
        elif not is_dirty and is_in_dirty:
            self.dirty_items.remove(fs_info)

    def item_check_parent(self, item: QObject, /) -> None:
        """Retrieve the state of all children to update its own state accordingly."""
        sum_states = sum(
            item.child(idx).checkState() == qt.Checked for idx in range(item.rowCount())
        )
        if sum_states == item.rowCount():
            item.setCheckState(qt.Checked)
        else:
            item.setCheckState(qt.PartiallyChecked)
        self.resolve_item_up_changed(item)

    def resolve_item_down_changed(self, item: QObject, /) -> None:
        """Put the same state for every child."""
        self.update_item_changed(item)
        state = item.checkState()
        for idx in range(item.rowCount()):
            child = item.child(idx)
            child.setCheckState(state)
            self.resolve_item_down_changed(child)

    def resolve_item_up_changed(self, item: QObject, /) -> None:
        """Update the state of the parent."""
        self.update_item_changed(item)

        parent = item.parent()
        if not (parent and parent.isCheckable()):
            return

        parent.setCheckState(qt.PartiallyChecked)
        self.update_item_changed(parent)
        self.item_check_parent(parent)

    def resolve_item(self, item: QObject, /) -> None:
        """When an item is changed, update its eventual parents and children states."""
        # Disconnect from signal to update the tree has we want
        self.setEnabled(False)
        self.root_item.itemChanged.disconnect(self.resolve_item)

        # Don't allow partial by the user
        self.update_item_changed(item)
        self.resolve_item_down_changed(item)
        self.resolve_item_up_changed(item)

        # Reconnect to get any user update
        self.root_item.itemChanged.connect(self.resolve_item)
        self.setEnabled(True)


class FolderTreeView(TreeViewMixin):
    """A tree view of all folderish documents. Used by the Direct Transfer feature."""

    # The content's loader for folderish documents
    loader = FolderContentLoader

    def __init__(self, parent: "FoldersDialog", client: FoldersOnly, /) -> None:
        super().__init__(parent, client)

        # Actions to do when a folder is (de)selected
        self.selectionModel().selectionChanged.connect(self.on_selection_changed)

    def on_selection_changed(self, new: QItemSelection, /) -> None:
        """Actions to do when a folder is (de)selected."""
        try:
            # Get the index of the current selection
            index = new.indexes()[0]
        except IndexError:
            # The selection has been cleared
            path = ""
            path_ref = ""
            title = ""
        else:
            # Get the selected folder's path
            item = self.model().itemFromIndex(index).data(qt.UserRole)
            path = item.get_path()
            path_ref = item.get_id()
            title = item.get_label()

        # Set the remote folder according to the selected folder
        self.parent.remote_folder.setText(path)
        self.parent.remote_folder_ref = path_ref
        self.parent.remote_folder_title = title

        # Set the OK button state depending of the current selection
        self.parent.button_ok_state()
