'''
Created on 6 mai 2014

@author: Remi Cattiau
'''
from PyQt4 import QtGui, QtCore
from threading import Thread
import time
from nxdrive.gui.resources import find_icon
from nxdrive.logging_config import get_logger

log = get_logger(__name__)


class FileInfo(object):
    def __init__(self, parent=None, checkstate=None):
        self.parent = parent
        self.children = []
        if parent:
            parent.add_child(self)
        if checkstate is None and parent is not None:
            checkstate = parent.get_checkstate()
        elif (parent is not None and parent.is_dirty()):
            self.checkstate = parent.get_checkstate()
            self.oldvalue = checkstate
            return
        elif checkstate is None:
            checkstate = QtCore.Qt.Checked
        self.oldvalue = self.checkstate = checkstate

    def __repr__(self):
        return ("FileInfo<checkstate=%r, id=%r, "
                "label=%r, parent=%r>") % (
                    self.get_checkstate(),
                    self.get_id(),
                    self.get_label(), self.get_path())

    def add_child(self, child):
        self.children.append(child)

    def get_children(self):
        return self.children

    def enable(self):
        return True

    def selectable(self):
        return True

    def checkable(self):
        return True

    def is_dirty(self):
        return self.oldvalue != self.checkstate

    def get_label(self):
        return ""

    def get_id(self):
        return ""

    def get_old_value(self):
        return self.oldvalue

    def has_children(self):
        return False

    def get_parent(self):
        return self.parent

    def is_hidden(self):
        return False

    def get_path(self):
        path = ""
        if self.parent is not None:
            path = path + self.parent.get_path()
        path = path + "/" + self.get_id()
        return path

    def get_checkstate(self):
        return self.checkstate

    def set_checkstate(self, checkstate):
        self.checkstate = checkstate


class FsRootFileInfo(FileInfo):
    def __init__(self, fs_info, checkstate=None):
        super(FsRootFileInfo, self).__init__(None, checkstate)
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
    def __init__(self, fs_info, parent=None, checkstate=None):
        super(FsFileInfo, self).__init__(parent, checkstate)
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
        super(DocFileInfo, self).__init__(parent)
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


class FsClient(Client):
    def __init__(self, fsClient):
        super(FsClient, self).__init__()
        self.fsClient = fsClient

    def get_children(self, parent=None):
        if (parent == None):
            return [FsRootFileInfo(root) for root
                    in self.fsClient.get_top_level_children()]
        return [FsFileInfo(file_info, parent) for file_info
                in self.fsClient.get_children_info(parent.get_id())]


class FilteredFsClient(FsClient):
    def __init__(self, fsClient, filters=None):
        super(FilteredFsClient, self).__init__(fsClient)
        if filters:
            self.filters = [filter_obj.path for filter_obj in filters]
        else:
            self.filters = []

    def get_item_state(self, path):
        if not path.endswith("/"):
            path = path + "/"
        if any([path.startswith(filter_path) for filter_path in self.filters]):
            return QtCore.Qt.Unchecked
        # Find partial checked
        if any([filter_path.startswith(path) for filter_path in self.filters]):
            return QtCore.Qt.PartiallyChecked
        return QtCore.Qt.Checked

    def get_children(self, parent=None):
        if (parent == None):
            return [FsRootFileInfo(root, self.get_item_state(root.get('path')))
                    for root in self.fsClient.get_top_level_children()]
        return [FsFileInfo(file_info, parent,
                           self.get_item_state(file_info.path))
                for file_info
                in self.fsClient.get_children_info(parent.get_id())]


class DocClient(Client):

    def __init__(self, docClient):
        super(DocClient, self).__init__()
        self.docClient = docClient

    def get_children(self, parent=None):
        time.sleep(4)
        result = []
        if (parent == None):
            for root in self.docClient.get_roots():
                result.append(DocRootFileInfo(root))
        else:
            docList = self.docClient.get_children(parent.get_id())
            docList = docList.get('entries')
            for doc in docList:
                doc_info = DocFileInfo(doc)
                if (not doc_info.is_hidden()):
                    result.append(doc_info)
        return result


class Overlay(QtGui.QWidget):

    def __init__(self, parent=None):

        QtGui.QLabel.__init__(self, parent)
        palette = QtGui.QPalette(self.palette())
        palette.setColor(palette.Background, QtCore.Qt.transparent)
        self.setPalette(palette)
        self.movie = QtGui.QMovie(find_icon('loader.gif'))
        self.movie.frameChanged.connect(self.redraw)
        self.movie.start()
        #self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

    def redraw(self, frameNumber):
        self.repaint()

    def paintEvent(self, event):

        painter = QtGui.QPainter()
        painter.begin(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 64)))
        painter.fillRect(self.rect(), QtGui.QBrush(QtGui.QColor(0, 0, 0, 64)))
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 255)))
        pixmap = self.movie.currentPixmap()
        painter.drawPixmap((self.width() - pixmap.width()) / 2,
                           (self.height() - pixmap.height()) / 2, pixmap)
        painter.end()


class FolderTreeview(QtGui.QTreeView):
    '''
    classdocs
    '''

    showHideLoadingOverlay = QtCore.pyqtSignal(bool)

    def __init__(self, parent, client):
        '''
        Constructor
        '''
        super(FolderTreeview, self).__init__(parent)
        self.client = client
        self.cache = []
        #self.childrenLoaded = QtCore.pyqtSignal()
        self.root_item = QtGui.QStandardItemModel()
        self.root_item.itemChanged.connect(self.itemChanged)
        self.showHideLoadingOverlay.connect(self.setLoad)
        self.setModel(self.root_item)
        self.setHeaderHidden(True)

        # Keep track of dirty items
        self.dirtyItems = []
        # Add widget overlay for loading
        self.overlay = self.getLoadingOverlay()
        self.overlay.move(1, 0)
        self.overlay.hide()

        self.loadChildren()

        self.expanded.connect(self.itemExpanded)

    def itemCheckParent(self, item):
        i = 0
        sum_states = 0
        while i < item.rowCount():
            if item.child(i).checkState() == QtCore.Qt.Checked:
                sum_states = sum_states + 1
            i = i + 1
        if sum_states == 0:
            item.setCheckState(QtCore.Qt.Unchecked)
        elif sum_states == item.rowCount():
            item.setCheckState(QtCore.Qt.Checked)
        else:
            item.setCheckState(QtCore.Qt.PartiallyChecked)
        self.resolveItemUpChanged(item)

    def resolveItemUpChanged(self, item):
        self.updateItemChanged(item)

        if item.checkState() == QtCore.Qt.PartiallyChecked:
            if item.parent() is not None and item.parent().isCheckable():
                item.parent().setCheckState(QtCore.Qt.PartiallyChecked)
                self.updateItemChanged(item.parent())
            return
        if item.parent() is not None and item.parent().isCheckable():
            self.itemCheckParent(item.parent())

    def updateItemChanged(self, item):
        fs_info = item.data(QtCore.Qt.UserRole).toPyObject()
        # Fake children have no data attached
        if not fs_info:
            return

        fs_info.set_checkstate(item.checkState())
        is_in_dirty = fs_info in self.dirtyItems
        if fs_info.is_dirty() and not is_in_dirty:
            self.dirtyItems.append(fs_info)
        elif not fs_info.is_dirty() and is_in_dirty:
            self.dirtyItems.remove(fs_info)

    def resolveItemDownChanged(self, item):
        self.updateItemChanged(item)
        # Put the same state for every child
        i = 0
        while i < item.rowCount():
            item.child(i).setCheckState(item.checkState())
            self.resolveItemDownChanged(item.child(i))
            i = i + 1

    def itemChanged(self, item):
        # Disconnect from signal to update the tree has we want
        self.setEnabled(False)
        self.root_item.itemChanged.disconnect(self.itemChanged)
        # Dont allow partial by the user
        self.updateItemChanged(item)
        self.resolveItemDownChanged(item)
        self.resolveItemUpChanged(item)
        # Reconnect to get any user update
        self.root_item.itemChanged.connect(self.itemChanged)
        self.setEnabled(True)

    def setClient(self, client):
        self.client = client
        self.loadChildren()

    def itemExpanded(self, index):
        index = self.model().index(index.row(), 0, index.parent())
        item = self.model().itemFromIndex(index)
        self.loadChildren(item)

    def getLoadingOverlay(self):
        return Overlay(self)

    def getDirtyItems(self):
        return self.dirtyItems

    def loadChildren(self, item=None):
        if (self.client is None):
            self.setLoad(False)
            return
        self.setLoad(True)
        load_thread = Thread(target=self.loadChildrenThread, args=[item])
        load_thread.start()

    def sortChildren(self, childs):
        # Put in a specific method to be able to override if needed
        # NXDRIVE-12: Sort child alphabetically
        return sorted(childs, key=lambda x: x.get_label().lower())

    def loadChildrenThread(self, parent=None):

        if (parent == None):
            parent = self.model().invisibleRootItem()
            parentItem = None
        else:
            parentItem = parent.data(QtCore.Qt.UserRole).toPyObject()

        if parentItem:
            if parentItem.get_id() in self.cache:
                self.showHideLoadingOverlay.emit(False)
                return
            self.cache.append(parentItem.get_id())
        # Clear previous items
        childs = self.client.get_children(parentItem)
        childs = self.sortChildren(childs)

        parent.removeRows(0, parent.rowCount())
        for child in childs:
            subitem = QtGui.QStandardItem(child.get_label())
            if child.checkable():
                subitem.setCheckable(True)
                subitem.setCheckState(True)
                subitem.setTristate(True)
                subitem.setCheckState(child.get_checkstate())
            subitem.setEnabled(child.enable())
            subitem.setSelectable(child.selectable())
            subitem.setEditable(False)
            subitem.setData(QtCore.QVariant(child), QtCore.Qt.UserRole)
            # Create a fake loading item for now
            if (child.has_children()):
                loaditem = QtGui.QStandardItem("")
                loaditem.setSelectable(False)
                subitem.appendRow(loaditem)
            parent.appendRow(subitem)

        self.showHideLoadingOverlay.emit(False)

    def loadFinished(self):
        self.setLoad(False)

    @QtCore.pyqtSlot(bool)
    def setLoad(self, value):
        if (value):
            self.overlay.show()
        else:
            self.overlay.hide()

    def resizeEvent(self, event):
        self.overlay.resize(event.size())
        event.accept()
        self.setColumnWidth(0, self.width())
