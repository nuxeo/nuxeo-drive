# coding: utf-8
from logging import getLogger
from threading import Thread
from typing import Iterator, List

from PyQt5.QtCore import QModelIndex, QObject, QVariant, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QMovie, QPalette, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QDialog, QLabel, QTreeView, QWidget

from ..client.remote_client import Remote
from ..objects import Filters, RemoteFileInfo
from ..utils import find_icon

__all__ = ("FilteredFsClient", "FolderTreeview", "Overlay")

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

    def has_children(self) -> bool:
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

    def has_children(self) -> bool:
        return self.fs_info.folderish


class Client:
    pass


class FilteredFsClient(Client):
    def __init__(self, fs_client: Remote, filters: Filters = None) -> None:
        self.fs_client = fs_client
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
            for info in self.fs_client.get_fs_children(parent.get_id(), filtered=False):
                yield FsFileInfo(info, parent, self.get_item_state(info.path))
            return

        root_info = self.fs_client.get_filesystem_root_info()
        for sync_root in self.fs_client.get_fs_children(root_info.uid, filtered=False):
            root = FsFileInfo(sync_root, state=self.get_item_state(sync_root.path))
            self.roots.append(root)
            yield root


class FolderTreeview(QTreeView):

    showHideLoadingOverlay = pyqtSignal(bool)
    noRoots = pyqtSignal(bool)

    def __init__(self, parent: QDialog, client: FilteredFsClient) -> None:
        # parent is FiltersDialog
        super().__init__(parent)
        self.client = client
        self.cache: List[str] = []
        self.root_item = QStandardItemModel()
        self.root_item.itemChanged.connect(self.itemChanged)
        self.showHideLoadingOverlay.connect(self.setLoad)
        self.setModel(self.root_item)
        self.setHeaderHidden(True)

        # Keep track of dirty items
        self.dirty_items: List[QStandardItemModel] = []
        # Add widget overlay for loading
        self.overlay = Overlay(self)
        self.overlay.move(1, 0)
        self.overlay.hide()

        self.load_children()

        self.expanded.connect(self.itemExpanded)

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

    def itemChanged(self, item: QObject) -> None:
        # Disconnect from signal to update the tree has we want
        self.setEnabled(False)
        self.root_item.itemChanged.disconnect(self.itemChanged)

        # Don't allow partial by the user
        self.update_item_changed(item)
        self.resolve_item_down_changed(item)
        self.resolve_item_up_changed(item)

        # Reconnect to get any user update
        self.root_item.itemChanged.connect(self.itemChanged)
        self.setEnabled(True)

    def itemExpanded(self, index: QModelIndex) -> None:
        index = self.model().index(index.row(), 0, index.parent())
        item = self.model().itemFromIndex(index)
        self.load_children(item)

    def load_children(self, item: QStandardItemModel = None) -> None:
        if self.client is None:
            self.setLoad(False)
            return

        self.setLoad(True)
        load_thread = Thread(target=self.load_children_thread, args=(item,))
        load_thread.start()

    def sort_children(self, children: List[FsFileInfo]) -> List[FsFileInfo]:
        # Put in a specific method to be able to override if needed
        # NXDRIVE-12: Sort child alphabetically
        return sorted(children, key=lambda x: x.get_label().lower())

    def load_children_thread(self, parent: QStandardItemModel = None) -> None:
        if not parent:
            parent = self.model().invisibleRootItem()
            parent_item = None
        else:
            parent_item = parent.data(Qt.UserRole)

        if parent_item:
            if parent_item.get_id() in self.cache:
                self.showHideLoadingOverlay.emit(False)
                return

            self.cache.append(parent_item.get_id())

        # Clear previous items
        children = list(self.client.get_children(parent_item))

        if not parent_item and not children:
            self.noRoots.emit(True)

        parent.removeRows(0, parent.rowCount())
        for child in self.sort_children(children):
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

            # Create a fake loading item for now
            if child.has_children():
                loaditem = QStandardItem("")
                loaditem.setSelectable(False)
                subitem.appendRow(loaditem)
            parent.appendRow(subitem)

        self.showHideLoadingOverlay.emit(False)

    @pyqtSlot(bool)
    def setLoad(self, value: bool) -> None:
        (self.overlay.hide, self.overlay.show)[value]()

    def resizeEvent(self, event: QObject) -> None:
        self.overlay.resize(event.size())
        event.accept()
        self.setColumnWidth(0, self.width())


class Overlay(QWidget):
    def __init__(self, parent: QTreeView = None) -> None:
        QLabel.__init__(self, parent)
        palette = QPalette(self.palette())
        palette.setColor(palette.Background, Qt.transparent)
        self.setPalette(palette)
        self.movie = QMovie(str(find_icon("loader.gif")))
        self.movie.frameChanged.connect(self.redraw)
        self.movie.start()

    def redraw(self, _) -> None:
        self.repaint()
