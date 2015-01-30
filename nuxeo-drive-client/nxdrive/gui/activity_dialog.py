'''
Created on 26 janv. 2015

@author: Remi Cattiau
'''
from PyQt4 import QtGui, QtCore
from nxdrive.engine.activity import FileAction
from nxdrive.logging_config import get_logger
log = get_logger(__name__)


class ThreadWidget(QtGui.QFrame):
    def __init__(self, parent, thread):
        super(ThreadWidget, self).__init__(parent)
        self.setFrameStyle(QtGui.QFrame.StyledPanel)
        self.setBackgroundRole(QtGui.QPalette.Base)
        self._thread = thread
        self.setMaximumHeight(80)
        self._worker = thread.worker
        layout = QtGui.QVBoxLayout()
        layout.setAlignment(QtCore.Qt.AlignTop)
        self._thread_label = QtGui.QLabel()
        self._thread_label.setBackgroundRole(QtGui.QPalette.Base)
        layout.addWidget(self._thread_label)
        self._action_label = QtGui.QLabel()
        self._action_label.setBackgroundRole(QtGui.QPalette.Base)
        self._progress = QtGui.QProgressBar()
        layout.addWidget(self._action_label)
        layout.addWidget(self._progress)
        self.setLayout(layout)
        self.update()

    def get_thread(self):
        return self._thread

    def update(self):
        self._thread_label.setText(self._worker._name)
        action = self._worker.get_action()
        if action is not None:
            text = action.type
            if isinstance(action, FileAction):
                text = text + " " + action.filename
            if text != self._action_label.text():
                self._action_label.setText(text)
            if action.get_percent() is not None:
                self._progress.setValue(action.get_percent())
                self._progress.setVisible(True)
            else:
                self._progress.setVisible(False)
        else:
            self._action_label.setText("Idle")
            self._progress.setVisible(False)


class EngineWidget(QtGui.QWidget):
    def __init__(self, parent, engine):
        super(EngineWidget, self).__init__(parent)
        self._layout = QtGui.QVBoxLayout()
        self._layout.setAlignment(QtCore.Qt.AlignTop)
        self._childs = dict()
        self._engine = engine
        self._layout.addWidget(QtGui.QLabel(engine._type + ": " + engine._local_folder))
        self.setLayout(self._layout)
        self.update()

    @QtCore.pyqtSlot()
    def remove_thread(self):
        to_delete = []
        for tid, child in self._childs.iteritems():
            if child.get_thread().isFinished():
                child.hide()
                self.layout().removeWidget(child)
                to_delete.append(tid)
        for tid in to_delete:
            del self._childs[tid]
        self.updateGeometry()

    def update(self):
        for thread in self._engine.get_threads():
            # Connect the finished to remove
            if thread.worker._thread_id is None:
                continue
            tid = thread.worker._name + str(thread.worker._thread_id)
            if tid is None:
                continue
            if tid in self._childs:
                self._childs[tid].update()
            else:
                self._childs[tid] = ThreadWidget(self, thread)
                thread.terminated.connect(self.remove_thread)
                thread.finished.connect(self.remove_thread)
                self.layout().addWidget(self._childs[tid])
        self.updateGeometry()


class ActivityDialog(QtGui.QDialog):
    '''
    classdocs
    '''
    def __init__(self, manager):
        '''
        Constructor
        '''
        super(ActivityDialog, self).__init__()
        self._manager = manager
        self._childs = dict()
        self.setWindowTitle("Activity window")
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setAlignment(QtCore.Qt.AlignTop)
        self.resize(400, 400)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(1000)
        self.update()

    @QtCore.pyqtSlot()
    def update(self):
        childs = self._childs.copy()
        for uid, engine in self._manager.get_engines().iteritems():
            if uid in childs:
                self._childs[uid].update()
                del childs[uid]
                continue
            self._childs[uid] = EngineWidget(self, engine)
            self.layout().addWidget(self._childs[uid])
        for child in childs:
            self.layout().removeWidget(childs[child])