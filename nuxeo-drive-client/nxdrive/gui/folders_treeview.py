'''
Created on 6 mai 2014

@author: Remi Cattiau
'''
from PyQt4 import QtGui, QtCore
from threading import Thread
import time
from nxdrive.gui.resources import find_icon

class FileInfo(object):
    def get_label(self):
        return ""
    def get_id(self):
        return ""
    def has_children(self):
        return False
    def is_hidden(self):
        return False
    def is_checked(self):
        return False

class FsRootFileInfo(FileInfo):
    def __init__(self, fs_info):
        self.fs_info = fs_info
        
    def get_label(self):
        return self.fs_info.get('name')
    
    def get_id(self):
        return self.fs_info.get('id')
    
    def has_children(self):
        return self.fs_info.get('folder')
    
    def is_checked(self):
        return True
    
class FsFileInfo(FileInfo):
    def __init__(self, fs_info):
        self.fs_info = fs_info
        
    def get_label(self):
        return self.fs_info.name
    
    def get_id(self):
        return self.fs_info.uid
    
    def has_children(self):
        return self.fs_info.folderish
    
    def is_checked(self):
        return True
    
class DocFileInfo(FileInfo):
    def __init__(self, doc):
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
        self.doc = doc
        
    def get_label(self):
        return self.doc.name
    
    def get_id(self):
        return self.doc.uid
    
    def has_children(self):
        return self.doc.folderish

class Client(object):
    def get_children(self, parent = None):
        return None


class FsClient(Client):
    def __init__(self, fsClient):
        super(FsClient, self).__init__()
        self.fsClient = fsClient
        
    def get_children(self, parent = None):
        if (parent == None):
            return [FsRootFileInfo(root) for root in self.fsClient.get_top_level_children()]
        return [FsFileInfo(file_info) for file_info in self.fsClient.get_children_info(parent.get_id())]

class DocClient(Client):
    def __init__(self, docClient):
        super(DocClient, self).__init__()
        self.docClient = docClient
        
    def get_children(self, parent = None):
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
 
    def __init__(self, parent = None):
 
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
        painter.drawPixmap((self.width()-pixmap.width())/2,(self.height()-pixmap.height())/2, pixmap)
        #painter.drawText(10,10, 'Loading ...')
        painter.end()
        
class FolderTreeview(QtGui.QTreeView):
    '''
    classdocs
    '''


    def __init__(self, parent, client):
        '''
        Constructor
        '''
        super(FolderTreeview, self).__init__(parent)
        self.client = client
        #self.childrenLoaded = QtCore.pyqtSignal()
        root_item = QtGui.QStandardItemModel();
        self.setModel(root_item)
        self.setHeaderHidden(True)
        
        # Add widget overlay for loading
        self.overlay = self.getLoadingOverlay()
        self.overlay.move(1,0);
        self.overlay.hide()
        
        self.setLoad(True)
        self.loadChildren()
        
        self.expanded.connect(self.itemExpanded)
    
    def itemExpanded(self,index):
        self.setLoad(True)
        index = self.model().index(index.row(),0,index.parent())
        item = self.model().itemFromIndex(index)
        self.loadChildren(item)
    
    def getLoadingOverlay(self):
        return Overlay(self) 
    
    def loadChildren(self,item = None):
        load_thread = Thread(target=self.loadChildrenThread,args=[item])
        load_thread.start()
        
    def loadChildrenThread(self,parent = None):
        if (parent == None):
            parent = self.model().invisibleRootItem()
            childs = self.client.get_children(None)
        else:    
            childs = self.client.get_children(parent.data(QtCore.Qt.UserRole).toPyObject())    
        # Clear previous items
        parent.removeRows(0,parent.rowCount())
        for child in childs:
            subitem = QtGui.QStandardItem(child.get_label())
            subitem.setCheckable(True)
            subitem.setEnabled(True)
            subitem.setSelectable(True)
            if child.is_checked():
                subitem.setCheckState(QtCore.Qt.Checked)
            subitem.setData(QtCore.QVariant(child),QtCore.Qt.UserRole)
            # Create a fake loading item for now
            if (child.has_children()):
                loaditem = QtGui.QStandardItem("")
                loaditem.setSelectable(False)
                subitem.appendRow(loaditem)
            parent.appendRow(subitem)
        self.setLoad(False)
        
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
        self.setColumnWidth(0,self.width())