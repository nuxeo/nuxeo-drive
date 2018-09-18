# coding: utf-8
from logging import getLogger

from PyQt5.QtCore import QObject, QVariant, Qt, pyqtSlot
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QDialog,
    QHeaderView,
    QMenu,
    QPushButton,
    QTreeView,
    QVBoxLayout,
)

from .folders_treeview import Overlay
from ..constants import APP_NAME
from ..objects import DocPair

__all__ = ("StatusDialog",)

log = getLogger(__name__)


class StatusTreeview(QTreeView):
    def __init__(self, parent: QObject, dao: "EngineDAO") -> None:
        super().__init__(parent)
        self._dao = dao
        self.root_item = QStandardItemModel()
        self.root_item.setHorizontalHeaderLabels(["Name", "Status", "Action"])

        self.setModel(self.root_item)
        self.setHeaderHidden(False)

        # Add widget overlay for loading
        self.overlay = Overlay(self)
        self.overlay.move(1, 0)
        self.overlay.hide()

        self.header().setStretchLastSection(False)
        self.header().setResizeMode(0, QHeaderView.Stretch)
        self.header().setResizeMode(1, QHeaderView.ResizeToContents)
        self.header().setResizeMode(2, QHeaderView.ResizeToContents)
        self.load_children()

        self.expanded.connect(self.itemExpanded)

    def itemExpanded(self, index):
        index = self.model().index(index.row(), 0, index.parent())
        item = self.model().itemFromIndex(index)
        self.load_children(item)

    def load_children(self, parent=None):
        if self._dao is None:
            self.setLoad(False)
            return
        self.setLoad(True)
        path = "/"
        if not parent:
            parent = self.model().invisibleRootItem()
            parent_item = None
        else:
            parent_item = parent.data(Qt.UserRole)

        if parent_item:
            path = parent_item.local_path

        # Remove loading child
        parent.removeRows(0, parent.rowCount())

        for child in self._dao.get_local_children(path):
            name = child.local_name
            if name is None:
                name = child.remote_name
            if name is None:
                continue

            subitem = QStandardItem(name)
            on_error = child.error_count > 3
            on_conflicted = child.pair_state == "conflicted"

            if on_error:
                subitem_status = QStandardItem("error")
            else:
                subitem_status = QStandardItem(child.pair_state)

            if child.last_sync_date is None:
                subitem_date = QStandardItem("N/A")
            else:
                subitem_date = QStandardItem(child.last_sync_date)

            if on_error or on_conflicted:
                # Put empty item
                subitem_date = QStandardItem()

            subitem.setEnabled(True)
            subitem.setSelectable(True)
            subitem.setEditable(False)
            subitem.setData(QVariant(child), Qt.UserRole)

            # Create a fake loading item for now
            if child.folderish:
                loaditem = QStandardItem("")
                loaditem.setSelectable(False)
                subitem.appendRow(loaditem)
            parent.appendRow([subitem, subitem_status, subitem_date])

            # Used later for update
            child.parent = parent
            if on_conflicted:
                self.setIndexWidget(subitem_date.index(), ResolveButton(self, child))
            if on_error:
                self.setIndexWidget(subitem_date.index(), RetryButton(self, child))

        self.setLoad(False)

    def refresh(self, pair):
        self.load_children(pair.parent)

    def setLoad(self, value):
        if value:
            self.overlay.show()
        else:
            self.overlay.hide()

    def resizeEvent(self, event):
        self.overlay.resize(event.size())
        event.accept()


class StatusDialog(QDialog):
    """ Use to display the table of LastKnownState. """

    def __init__(self, dao: "EngineDAO") -> None:
        super().__init__()
        self._dao = dao
        self.resize(500, 500)
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.tree_view = StatusTreeview(self, self._dao)
        self.tree_view.resizeColumnToContents(0)
        self.setWindowTitle(f"{APP_NAME} File Status")
        layout.addWidget(self.tree_view)


class RetryButton(QPushButton):
    def __init__(self, view: StatusTreeview, pair: DocPair) -> None:
        super().__init__("Retry")
        self.pair = pair
        self.view = view
        self.clicked.connect(self.retry)

    @pyqtSlot()
    def retry(self) -> None:
        self.view._dao.reset_error(self.pair)
        self.view.refresh(self.pair)


class ResolveButton(QPushButton):
    def __init__(self, view: StatusTreeview, pair: DocPair) -> None:
        super().__init__("Resolve")
        self.pair = pair
        self.view = view
        menu = QMenu()
        menu.addAction("Use local file", self.pick_local)
        menu.addAction("Use remote file", self.pick_remote)
        self.setMenu(menu)

    def pick_local(self) -> None:
        if self.view._dao.force_local(self.pair):
            self.view.refresh(self.pair)

    def pick_remote(self) -> None:
        if self.view._dao.force_remote(self.pair):
            self.view.refresh(self.pair)
