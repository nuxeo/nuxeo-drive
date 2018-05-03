# coding: utf-8
from logging import getLogger
from threading import Thread

from PyQt4 import QtCore, QtGui

from ..utils import find_icon

log = getLogger(__name__)


class FileInfo(object):
    def __init__(self, parent=None, state=None):
        self.parent = parent
        self.children = []
        if parent:
            parent.add_child(self)
        if state is None and parent is not None:
            state = parent.state
        elif parent is not None and parent.is_dirty():
            self.state = parent.state
            self.old_state = state
            return
        elif state is None:
            state = QtCore.Qt.Checked
        self.old_state = self.state = state

    def __repr__(self):
        return 'FileInfo<state=%r, id=%r, label=%r, parent=%r>' % (
            self.state,
            self.get_id(),
            self.get_label(),
            self.get_path(),
        )

    def add_child(self, child):
        self.children.append(child)

    def get_children(self):
        for child in self.children:
            yield child

    def enable(self):
        return True

    def selectable(self):
        return True

    def checkable(self):
        return True

    def is_dirty(self):
        return self.old_state != self.state

    def get_label(self):
        return ''

    def get_id(self):
        return ''

    def has_children(self):
        return False

    def is_hidden(self):
        return False

    def get_path(self):
        path = ''
        if self.parent is not None:
            path += self.parent.get_path()
        path += '/' + self.get_id()
        return path


class FsRootFileInfo(FileInfo):
    def __init__(self, fs_info, state=None):
        super(FsRootFileInfo, self).__init__(parent=None, state=state)
        self.fs_info = fs_info

    def get_label(self):
        return self.fs_info.get('name')

    def get_path(self):
        return self.fs_info.get('path')

    def get_id(self):
        return self.fs_info.get('id')

    def has_children(self):
        return self.fs_info.get('folder')


class FsFileInfo(FileInfo):
    def __init__(self, fs_info, parent=None, state=None):
        super(FsFileInfo, self).__init__(parent=parent, state=state)
        self.fs_info = fs_info

    def get_label(self):
        return self.fs_info.name

    def get_path(self):
        return self.fs_info.path

    def get_id(self):
        return self.fs_info.uid

    def has_children(self):
        return self.fs_info.folderish


class DocFileInfo(FileInfo):
    def __init__(self, doc, parent=None):
        super(DocFileInfo, self).__init__(parent=parent)
        self.doc = doc

    def get_label(self):
        return self.doc.get('title')

    def get_id(self):
        return self.doc.get('uid')

    def has_children(self):
        return 'Folderish' in self.doc.get('facets')

    def is_hidden(self):
        return 'HiddenInNavigation' in self.doc.get('facets')


class DocRootFileInfo(FileInfo):
    def __init__(self, doc):
        super(DocRootFileInfo, self).__init__()
        self.doc = doc

    def get_label(self):
        return self.doc.name

    def get_id(self):
        return self.doc.uid

    def has_children(self):
        return self.doc.folderish


class Client(object):
    def get_children(self, parent=None):
        return None


class FilteredFsClient(Client):
    def __init__(self, fs_client, filters=None):
        self.fs_client = fs_client
        filters = filters or []
        self.filters = [filter_obj.path for filter_obj in filters]

    def get_item_state(self, path):
        if not path.endswith('/'):
            path += '/'

        if any(path.startswith(filter_path) for filter_path in self.filters):
            return QtCore.Qt.Unchecked

        # Find partial checked
        if any(filter_path.startswith(path) for filter_path in self.filters):
            return QtCore.Qt.PartiallyChecked

        return QtCore.Qt.Checked

    def get_children(self, parent=None):
        if parent:
            for info in self.fs_client.get_fs_children(parent.get_id()):
                yield FsFileInfo(info, parent, self.get_item_state(info.path))
            return

        for root in self.fs_client.get_top_level_children():
            yield FsRootFileInfo(root, self.get_item_state(root.get('path')))


class Overlay(QtGui.QWidget):

    def __init__(self, parent=None):
        QtGui.QLabel.__init__(self, parent)
        palette = QtGui.QPalette(self.palette())
        palette.setColor(palette.Background, QtCore.Qt.transparent)
        self.setPalette(palette)
        self.movie = QtGui.QMovie(find_icon('loader.gif'))
        self.movie.frameChanged.connect(self.redraw)
        self.movie.start()

    def redraw(self, _):
        self.repaint()


class FolderTreeview(QtGui.QTreeView):

    showHideLoadingOverlay = QtCore.pyqtSignal(bool)

    def __init__(self, parent, client):
        super(FolderTreeview, self).__init__(parent)
        self.client = client
        self.cache = []
        self.root_item = QtGui.QStandardItemModel()
        self.root_item.itemChanged.connect(self.itemChanged)
        self.showHideLoadingOverlay.connect(self.setLoad)
        self.setModel(self.root_item)
        self.setHeaderHidden(True)

        # Keep track of dirty items
        self.dirty_items = []
        # Add widget overlay for loading
        self.overlay = Overlay(self)
        self.overlay.move(1, 0)
        self.overlay.hide()

        self.load_children()

        self.expanded.connect(self.itemExpanded)

    def item_check_parent(self, item):
        sum_states = sum(item.child(idx).checkState() == QtCore.Qt.Checked
                         for idx in range(item.rowCount()))
        if sum_states == item.rowCount():
            item.setCheckState(QtCore.Qt.Checked)
        else:
            item.setCheckState(QtCore.Qt.PartiallyChecked)
        self.resolve_item_up_changed(item)

    def resolve_item_up_changed(self, item):
        self.update_item_changed(item)

        parent = item.parent()
        if not parent or not parent.isCheckable():
            return

        parent.setCheckState(QtCore.Qt.PartiallyChecked)
        self.update_item_changed(parent)
        self.item_check_parent(parent)

    def update_item_changed(self, item):
        fs_info = item.data(QtCore.Qt.UserRole).toPyObject()

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

    def resolve_item_down_changed(self, item):
        """ Put the same state for every child. """
        self.update_item_changed(item)
        state = item.checkState()
        for idx in range(item.rowCount()):
            child = item.child(idx)
            child.setCheckState(state)
            self.resolve_item_down_changed(child)

    def itemChanged(self, item):
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

    def itemExpanded(self, index):
        index = self.model().index(index.row(), 0, index.parent())
        item = self.model().itemFromIndex(index)
        self.load_children(item)

    def load_children(self, item=None):
        if self.client is None:
            self.setLoad(False)
            return

        self.setLoad(True)
        load_thread = Thread(target=self.load_children_thread, args=(item,))
        load_thread.start()

    def sort_children(self, children):
        # Put in a specific method to be able to override if needed
        # NXDRIVE-12: Sort child alphabetically
        return sorted(children, key=lambda x: x.get_label().lower())

    def load_children_thread(self, parent=None):
        if not parent:
            parent = self.model().invisibleRootItem()
            parent_item = None
        else:
            parent_item = parent.data(QtCore.Qt.UserRole).toPyObject()

        if parent_item:
            if parent_item.get_id() in self.cache:
                self.showHideLoadingOverlay.emit(False)
                return

            self.cache.append(parent_item.get_id())

        # Clear previous items
        children = self.client.get_children(parent_item)

        parent.removeRows(0, parent.rowCount())
        for child in self.sort_children(children):
            subitem = QtGui.QStandardItem(child.get_label())
            if child.checkable():
                subitem.setCheckable(True)
                subitem.setCheckState(True)
                subitem.setTristate(True)
                subitem.setCheckState(child.state)
            subitem.setEnabled(child.enable())
            subitem.setSelectable(child.selectable())
            subitem.setEditable(False)
            subitem.setData(QtCore.QVariant(child), QtCore.Qt.UserRole)

            # Create a fake loading item for now
            if child.has_children():
                loaditem = QtGui.QStandardItem('')
                loaditem.setSelectable(False)
                subitem.appendRow(loaditem)
            parent.appendRow(subitem)

        self.showHideLoadingOverlay.emit(False)

    @QtCore.pyqtSlot(bool)
    def setLoad(self, value):
        (self.overlay.hide, self.overlay.show)[value]()

    def resizeEvent(self, event):
        self.overlay.resize(event.size())
        event.accept()
        self.setColumnWidth(0, self.width())
