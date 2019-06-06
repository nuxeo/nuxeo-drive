# coding: utf-8
from logging import getLogger
from typing import Iterator, List, Optional

from PyQt5.QtCore import (
    QModelIndex,
    QObject,
    QRunnable,
    QThreadPool,
    QVariant,
    Qt,
    pyqtSignal,
)
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QDialog, QTreeView

from ..client.remote_client import Remote
from ..objects import Filters, RemoteFileInfo
from ..translator import Translator

__all__ = ("FolderTreeview", "FsClient")

log = getLogger(__name__)


class FileInfo:
    def __init__(self, parent: QObject = None, state: int = None) -> None:
        self.parent = parent
        self.children: List["FileInfo"] = []
        if parent:
            parent.add_child(self)
        if state is None and parent is not None:
            state = parent.state
        elif parent is not None and parent.is_dirty():
            self.state = parent.state
            self.old_state = state
            return
        elif state is None:
            state = Qt.Checked
        self.old_state = self.state = state

    def __repr__(self) -> str:
        return (
            f"FileInfo<state={self.state}, id={self.get_id()}, "
            f"label={self.get_label()}, parent={self.get_path()!r}>"
        )

    def add_child(self, child: "FileInfo") -> None:
        self.children.append(child)

    def get_children(self) -> Iterator["FileInfo"]:
        for child in self.children:
            yield child

    def enable(self) -> bool:
        return True

    def selectable(self) -> bool:
        return True

    def checkable(self) -> bool:
        return True

    def is_dirty(self) -> bool:
        return self.old_state != self.state

    def get_label(self) -> str:
        return ""

    def get_id(self) -> str:
        return ""

    def folderish(self) -> bool:
        return False

    def is_hidden(self) -> bool:
        return False

    def get_path(self) -> str:
        path = ""
        if self.parent is not None:
            path += self.parent.get_path()
        path += "/" + self.get_id()
        return path


class FsFileInfo(FileInfo):
    def __init__(
        self, fs_info: RemoteFileInfo, parent: FileInfo = None, state: int = None
    ) -> None:
        super().__init__(parent=parent, state=state)
        self.fs_info = fs_info

    def get_label(self) -> str:
        return self.fs_info.name

    def get_path(self) -> str:
        return self.fs_info.path

    def get_id(self) -> str:
        return self.fs_info.uid

    def folderish(self) -> bool:
        return self.fs_info.folderish


class FsClient:
    def __init__(self, remote: Remote, filters: Filters = None) -> None:
        self.remote = remote
        self.filters = filters or []
        self.roots: List[FsFileInfo] = []

    def get_item_state(self, path: str) -> int:
        if not path.endswith("/"):
            path += "/"

        if any(path.startswith(filter_path) for filter_path in self.filters):
            return Qt.Unchecked

        # Find partial checked
        if any(filter_path.startswith(path) for filter_path in self.filters):
            return Qt.PartiallyChecked

        return Qt.Checked

    def get_children(self, parent: FileInfo = None) -> Iterator[FsFileInfo]:
        if parent:
            for info in self.remote.get_fs_children(parent.get_id(), filtered=False):
                yield FsFileInfo(info, parent, self.get_item_state(info.path))
            return

        root_info = self.remote.get_filesystem_root_info()
        for sync_root in self.remote.get_fs_children(root_info.uid, filtered=False):
            root = FsFileInfo(sync_root, state=self.get_item_state(sync_root.path))
            self.roots.append(root)
            yield root


class FolderTreeview(QTreeView):

    noRoots = pyqtSignal(bool)

    def __init__(self, parent: QDialog, client: FsClient) -> None:
        # parent is FiltersDialog
        super().__init__(parent)
        self.client = client
        self.cache: List[str] = []
        self.root_item = QStandardItemModel()
        self.root_item.itemChanged.connect(self.resolve_item)
        self.setModel(self.root_item)
        self.setHeaderHidden(True)

        # Keep track of dirty items
        self.dirty_items: List[QStandardItemModel] = []

        self.load_children()

        self.expanded.connect(self.expand_item)

    def item_check_parent(self, item: QObject) -> None:
        sum_states = sum(
            item.child(idx).checkState() == Qt.Checked for idx in range(item.rowCount())
        )
        if sum_states == item.rowCount():
            item.setCheckState(Qt.Checked)
        else:
            item.setCheckState(Qt.PartiallyChecked)
        self.resolve_item_up_changed(item)

    def resolve_item_up_changed(self, item: QObject) -> None:
        self.update_item_changed(item)

        parent = item.parent()
        if not parent or not parent.isCheckable():
            return

        parent.setCheckState(Qt.PartiallyChecked)
        self.update_item_changed(parent)
        self.item_check_parent(parent)

    def update_item_changed(self, item: QObject) -> None:
        fs_info = item.data(Qt.UserRole)

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

    def resolve_item_down_changed(self, item: QObject) -> None:
        """ Put the same state for every child. """
        self.update_item_changed(item)
        state = item.checkState()
        for idx in range(item.rowCount()):
            child = item.child(idx)
            child.setCheckState(state)
            self.resolve_item_down_changed(child)

    def resolve_item(self, item: QObject) -> None:
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

    def expand_item(self, index: QModelIndex) -> None:
        index = self.model().index(index.row(), 0, index.parent())
        item = self.model().itemFromIndex(index)
        self.load_children(item)

    def load_children(self, item: QStandardItemModel = None) -> None:
        if not self.client:
            self.set_loading_cursor(False)
            return

        self.set_loading_cursor(True)
        loader = ContentLoader(self, item)
        QThreadPool.globalInstance().start(loader)

    def sort_children(self, children: List[FsFileInfo]) -> List[FsFileInfo]:
        # Put in a specific method to be able to override if needed
        # NXDRIVE-12: Sort child alphabetically
        return sorted(children, key=lambda x: x.get_label().lower())

    def set_loading_cursor(self, busy: bool) -> None:
        if busy:
            self.setCursor(Qt.BusyCursor)
        else:
            self.unsetCursor()

    def resizeEvent(self, event: QObject) -> None:
        event.accept()
        self.setColumnWidth(0, self.width())


class ContentLoader(QRunnable):
    def __init__(self, tree: FolderTreeview, item: QStandardItemModel = None) -> None:
        super().__init__()
        self.tree = tree
        self.item = item or self.tree.model().invisibleRootItem()
        self.info: Optional[FsFileInfo] = None
        if item:
            self.info = self.item.data(Qt.UserRole)

    def run(self) -> None:
        item, info = self.item, self.info
        if info:
            if info.get_id() in self.tree.cache:
                self.tree.set_loading_cursor(False)
                return

            self.tree.cache.append(info.get_id())

        try:
            children = list(self.tree.client.get_children(info))
        except Exception:
            path = info.get_path() if info else "root"
            log.warning(f"Error while retrieving filters on {path!r}", exc_info=True)
            self.tree.set_loading_cursor(False)
            item.removeRows(0, item.rowCount())
            item.appendRow(
                QStandardItem(Translator.get("LOADING_ERROR") + " \U0001F937")
            )
            return

        if not info and not children:
            self.tree.noRoots.emit(True)

        self.fill_tree(children)
        self.tree.set_loading_cursor(False)

    def fill_tree(self, children: List[FsFileInfo]) -> None:

        self.item.removeRows(0, self.item.rowCount())
        for child in self.tree.sort_children(children):
            subitem = QStandardItem(child.get_label())
            if child.checkable():
                subitem.setCheckable(True)
                subitem.setCheckState(True)
                subitem.setTristate(True)
                subitem.setCheckState(child.state)
            subitem.setEnabled(child.enable())
            subitem.setSelectable(child.selectable())
            subitem.setEditable(False)
            subitem.setData(QVariant(child), Qt.UserRole)

            if child.folderish():
                # Add "Loading..." entry in advance for when the user
                # will click to expand it.
                loaditem = QStandardItem(Translator.get("LOADING"))
                loaditem.setSelectable(False)
                subitem.appendRow(loaditem)

            self.item.appendRow(subitem)
