'''
Created on 26 juin 2014

@author: Remi Cattiau
'''
from PyQt4 import QtGui, QtCore


class ProgressDialog(QtGui.QDialog):
    '''
    Use to display the table of LastKnownState
    '''

    def __init__(self, action, autoclose=True):
        super(ProgressDialog, self).__init__()
        self.resize(200, 80)
        self.setFixedSize(200, 80)
        self.setModal(True)
        layout = QtGui.QVBoxLayout()
        self.action = action
        self.action.finished = False
        self.timer = QtCore.QTimer(self)
        self.autoclose = autoclose
        self.progress = QtGui.QProgressBar(self)
        self.label = QtGui.QLabel(self)
        self.label.setText(self.action.type)
        layout.addWidget(self.label)
        layout.addWidget(self.progress)
        self.setLayout(layout)
        if action.progress is None:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
        self.timer.timeout.connect(self.update)

    def exec_(self):
        self.update()
        self.timer.start(1000)
        super(ProgressDialog, self).exec_()

    def update(self):
        if self.action.get_percent() is not None:
            self.progress.setRange(0, 100)
            self.progress.setValue(self.action.get_percent())
            if (self.action.get_percent() == 100 and self.autoclose):
                self.action.finished = True
        else:
            self.progress.setRange(0, 0)
        self.label.setText(self.action.type)
        if self.action.finished:
            self.close()
