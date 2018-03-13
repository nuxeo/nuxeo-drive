# coding: utf-8
from logging import getLogger

from PyQt4 import QtCore, QtGui

from .folders_treeview import Overlay

log = getLogger(__name__)


class StatusDialog(QtGui.QDialog):
    """ Use to display the table of LastKnownState. """

    def __init__(self, dao):
        super(StatusDialog, self).__init__()
        self._dao = dao
        self.resize(500, 500)
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        self.tree_view = StatusTreeview(self, self._dao)
        self.tree_view.resizeColumnToContents(0)
        self.setWindowTitle('Nuxeo Drive File Status')
        layout.addWidget(self.tree_view)


class RetryButton(QtGui.QPushButton):
    def __init__(self, view, pair):
        super(RetryButton, self).__init__('Retry')
        self.pair = pair
        self.view = view
        self.clicked.connect(self.retry)

    @QtCore.pyqtSlot()
    def retry(self):
        self.view._dao.reset_error(self.pair)
        self.view.refresh(self.pair)


class ResolveButton(QtGui.QPushButton):
    def __init__(self, view, pair):
        super(ResolveButton, self).__init__('Resolve')
        self.pair = pair
        self.view = view
        menu = QtGui.QMenu()
        menu.addAction('Use local file', self.pick_local)
        menu.addAction('Use remote file', self.pick_remote)
        self.setMenu(menu)

    def pick_local(self):
        if self.view._dao.force_local(self.pair):
            self.view.refresh(self.pair)

    def pick_remote(self):
        if self.view._dao.force_remote(self.pair):
            self.view.refresh(self.pair)


class StatusTreeview(QtGui.QTreeView):

    def __init__(self, parent, dao):
        super(StatusTreeview, self).__init__(parent)
        self._dao = dao
        self.cache = []
        self.root_item = QtGui.QStandardItemModel()
        self.root_item.setHorizontalHeaderLabels(['Name', 'Status', 'Action'])

        self.setModel(self.root_item)
        self.setHeaderHidden(False)

        # Add widget overlay for loading
        self.overlay = Overlay(self)
        self.overlay.move(1, 0)
        self.overlay.hide()

        self.header().setStretchLastSection(False)
        self.header().setResizeMode(0, QtGui.QHeaderView.Stretch)
        self.header().setResizeMode(1, QtGui.QHeaderView.ResizeToContents)
        self.header().setResizeMode(2, QtGui.QHeaderView.ResizeToContents)
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
        path = '/'
        if not parent:
            parent = self.model().invisibleRootItem()
            parent_item = None
        else:
            parent_item = parent.data(QtCore.Qt.UserRole).toPyObject()

        if parent_item:
            path = parent_item.local_path
        childs = self._dao.get_local_children(path)

        # Remove loading child
        parent.removeRows(0, parent.rowCount())

        for child in childs:
            name = child.local_name
            if name is None:
                name = child.remote_name
            if name is None:
                continue

            subitem = QtGui.QStandardItem(name)
            on_error = child.error_count > 3
            on_conflicted = child.pair_state == 'conflicted'

            if on_error:
                subitem_status = QtGui.QStandardItem('error')
            else:
                subitem_status = QtGui.QStandardItem(child.pair_state)

            if child.last_sync_date is None:
                subitem_date = QtGui.QStandardItem('N/A')
            else:
                subitem_date = QtGui.QStandardItem(child.last_sync_date)

            if on_error or on_conflicted:
                # Put empty item
                subitem_date = QtGui.QStandardItem()

            subitem.setEnabled(True)
            subitem.setSelectable(True)
            subitem.setEditable(False)
            subitem.setData(QtCore.QVariant(child), QtCore.Qt.UserRole)
            # Create a fake loading item for now
            if child.folderish:
                loaditem = QtGui.QStandardItem('')
                loaditem.setSelectable(False)
                subitem.appendRow(loaditem)
            parent.appendRow([subitem, subitem_status, subitem_date])
            # Used later for update
            child.parent = parent
            if on_conflicted:
                self.setIndexWidget(subitem_date.index(),
                                    ResolveButton(self, child))
            if on_error:
                self.setIndexWidget(subitem_date.index(),
                                    RetryButton(self, child))

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
