"""GUI prompt to manage metadata"""
import sys
from nxdrive.logging_config import get_logger
from PyQt4 import QtCore, QtGui, QtWebKit, QtNetwork
from PyQt4.Qt import QUrl, QObject
from PyQt4.QtCore import Qt
from nxdrive.gui.resources import find_icon
from nxdrive.wui.dialog import WebDialog

log = get_logger(__name__)

METADATA_WEBVIEW_WIDTH = 800
METADATA_WEBVIEW_HEIGHT = 700


def CreateMetadataWebDialog(manager, file_path, application=None):
    if application is None:
        application = QtCore.QCoreApplication.instance()
    infos = manager.get_metadata_infos(file_path)
    dialog = WebDialog(application, infos[0],
                    title=manager.get_appname(), token=infos[1])
    dialog.resize(METADATA_WEBVIEW_WIDTH, METADATA_WEBVIEW_HEIGHT)
    dialog.setWindowFlags(Qt.WindowStaysOnTopHint)
    return dialog


class MetadataApplication(QtGui.QApplication):
    def __init__(self, manager, file_path):
        super(MetadataApplication, self).__init__([])
        self.manager = manager
        self._file_path = file_path
        self.dialog = CreateMetadataWebDialog(manager, file_path, self)
        self.dialog.show()

    def get_window_icon(self):
        return find_icon('nuxeo_drive_icon_64.png')
