'''
Created on 26 juin 2014

@author: Remi Cattiau
'''
from PyQt4 import QtGui, QtCore
from folders_treeview import Overlay
from nxdrive.logging_config import get_logger
log = get_logger(__name__)


class StatusDialog(QtGui.QDialog):
    '''
    Use to display the table of LastKnownState
    '''
    def __init__(self, dao):
        '''
        Constructor
        '''
        super(StatusDialog,self).__init__()
        self._dao = dao
        self.resize(500, 500)
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        self.treeView = StatusTreeview(self, dao)
        self.treeView.resizeColumnToContents(0)
        self.setWindowTitle('Nuxeo Drive File Status')
        layout.addWidget(self.treeView)


class RetryButton(QtGui.QPushButton):
    def __init__(self, view, pair):
        super(RetryButton, self).__init__("Retry")
        self._pair = pair
        self._view = view
        self.clicked.connect(self.retry)

    @QtCore.pyqtSlot()
    def retry(self):
        self._view._dao.reset_error(self._pair)
        self._view.refresh(self._pair)


class ResolveButton(QtGui.QPushButton):
    def __init__(self, view, pair):
        super(ResolveButton, self).__init__("Resolve")
        self._pair = pair
        self._view = view
        menu = QtGui.QMenu()
        menu.addAction("Use local file", self.pick_local)
        menu.addAction("Use remote file", self.pick_remote)
        self.setMenu(menu)

    def pick_local(self):
        if not self._view._dao.force_local(self._pair):
            # TODO Display error message
            pass
        else:
            self._view.refresh(self._pair)

    def pick_remote(self):
        if not self._view._dao.force_remote(self._pair):
            # TODO Display error message
            pass
        else:
            self._view.refresh(self._pair)


class StatusTreeview(QtGui.QTreeView):
    '''
    classdocs
    '''

    def __init__(self, parent, dao):
        '''
        Constructor
        '''
        super(StatusTreeview, self).__init__(parent)
        self._dao = dao
        self.cache = []
        self.root_item = QtGui.QStandardItemModel()
        self.root_item.setHorizontalHeaderLabels(['Name', 'Status',
                                                  'Action'])

        self.filter_sync = True
        self.setModel(self.root_item)
        self.setHeaderHidden(False)

        # Add widget overlay for loading
        self.overlay = self.getLoadingOverlay()
        self.overlay.move(1, 0)
        self.overlay.hide()

        self.header().setStretchLastSection(False)
        self.header().setResizeMode(0, QtGui.QHeaderView.Stretch)
        self.header().setResizeMode(1, QtGui.QHeaderView.ResizeToContents)
        self.header().setResizeMode(2, QtGui.QHeaderView.ResizeToContents)
        self.loadChildren()

        self.expanded.connect(self.itemExpanded)

    def itemExpanded(self, index):
        index = self.model().index(index.row(), 0, index.parent())
        item = self.model().itemFromIndex(index)
        self.loadChildren(item)

    def getLoadingOverlay(self):
        return Overlay(self)

    def loadChildren(self, parent=None):
        if (self._dao is None):
            self.setLoad(False)
            return
        self.setLoad(True)
        path = '/'
        if not parent:
            parent = self.model().invisibleRootItem()
            parentItem = None
        else:
            parentItem = parent.data(QtCore.Qt.UserRole).toPyObject()

        if parentItem:
            path = parentItem.local_path
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
            on_conflicted = child.pair_state == "conflicted"
            if (on_error):
                subitemStatus = QtGui.QStandardItem("error")
            else:
                subitemStatus = QtGui.QStandardItem(child.pair_state)
            if child.last_sync_date is None:
                subitemDate = QtGui.QStandardItem("N/A")
            else:
                subitemDate = QtGui.QStandardItem(
                            child.last_sync_date)
            if on_error or on_conflicted:
                # Put empty item
                subitemDate = QtGui.QStandardItem()
            subitem.setEnabled(True)
            subitem.setSelectable(True)
            subitem.setEditable(False)
            subitem.setData(QtCore.QVariant(child), QtCore.Qt.UserRole)
            # Create a fake loading item for now
            if (child.folderish):
                loaditem = QtGui.QStandardItem("")
                loaditem.setSelectable(False)
                subitem.appendRow(loaditem)
            parent.appendRow([subitem, subitemStatus, subitemDate])
            # Used later for update
            child.parent = parent
            if on_conflicted:
                self.setIndexWidget(subitemDate.index(), ResolveButton(self, child))
            if on_error:
                self.setIndexWidget(subitemDate.index(), RetryButton(self, child))

        self.setLoad(False)

    def refresh(self, pair):
        self.loadChildren(pair.parent)
        return

    def loadFinished(self):
        self.setLoad(False)

    def setLoad(self, value):
        if (value):
            self.overlay.show()
        else:
            self.overlay.hide()

    def resizeEvent(self, event):
        self.overlay.resize(event.size())
        event.accept()
